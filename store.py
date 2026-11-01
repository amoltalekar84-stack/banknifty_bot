"""
डेटा साठवण (SQLite) — ट्रेड्स, सेटिंग्ज, लॉग.
प्रत्येक क्वेरीसाठी स्वतंत्र कनेक्शन → थ्रेड-सेफ.
"""

import json
import os
import sqlite3
import tempfile
import time

# Hugging Face वर DATA_DIR=/data दिल्यास तिथे साठवा (persistent storage)
DATA_DIR = os.getenv("DATA_DIR", os.path.join(tempfile.gettempdir(), "bnb_data"))
DB_PATH = os.path.join(DATA_DIR, "bot.db")


def _conn():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def _q(sql, params=(), fetch=None, commit=False):
    con = _conn()
    try:
        cur = con.execute(sql, params)
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()
        if commit:
            con.commit()
            return cur.lastrowid
        return None
    finally:
        con.close()


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS state(
            k TEXT PRIMARY KEY, v TEXT, ts REAL);

        CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, mode TEXT, side TEXT,
            option_key TEXT, strike REAL, expiry TEXT,
            qty INTEGER, entry REAL, exit REAL,
            sl REAL, target REAL, pnl REAL,
            status TEXT, reason TEXT,
            opened TEXT, closed TEXT);

        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, msg TEXT);
        """)
        # जुन्या DB मध्ये charges column नाही → जोडा (migration)
        try:
            con.execute("ALTER TABLE trades ADD COLUMN charges REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass                      # column आधीच आहे
        # multi-symbol: सिम्बॉल column (जुन्या rows = BANKNIFTY)
        try:
            con.execute("ALTER TABLE trades ADD COLUMN symbol TEXT DEFAULT 'BANKNIFTY'")
        except sqlite3.OperationalError:
            pass                      # column आधीच आहे


# ---------------- TP-लॅडर legs (partial बुकिंग नोंदी) ----------------
def get_legs(tid):
    """या ट्रेडच्या झालेल्या बुकिंग भाग → [{label, price, qty}, ...]"""
    v = get_state(f"legs_{tid}")
    if not v:
        return []
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return []


def set_legs(tid, legs):
    """बुकिंग भाग नोंदवा / साफ करा ([] = साफ)"""
    set_state(f"legs_{tid}", json.dumps(legs or []))


# ---------------- state (सेटिंग्ज/स्थिती) ----------------
def set_state(k, v):
    _q("INSERT INTO state(k,v,ts) VALUES(?,?,?) "
       "ON CONFLICT(k) DO UPDATE SET v=excluded.v, ts=excluded.ts",
       (str(k), str(v), time.time()), commit=True)


def get_state(k, default=None):
    row = _q("SELECT v FROM state WHERE k=?", (str(k),), fetch="one")
    return row["v"] if row else default


# ---------------- events (लॉग) ----------------
def log_event(msg):
    _q("INSERT INTO events(ts,msg) VALUES(?,?)",
       (time.time(), str(msg)[:500]), commit=True)


def last_events(n=20):
    rows = _q("SELECT * FROM events ORDER BY id DESC LIMIT ?", (n,), fetch="all") or []
    return [dict(r) for r in rows]


# ---------------- trades (ट्रेड्स) ----------------
def open_trade(date, mode, side, option_key, strike, expiry, qty, entry,
               sl, target, opened, symbol="BANKNIFTY"):
    return _q(
        """INSERT INTO trades(date,mode,side,option_key,strike,expiry,
                              qty,entry,sl,target,status,opened,symbol)
           VALUES(?,?,?,?,?,?,?,?,?,?,'OPEN',?,?)""",
        (date, mode, side, option_key, strike, expiry, qty, entry, sl,
         target, opened, symbol),
        commit=True)


def close_trade(tid, exit_price, pnl, reason, closed, charges=0.0):
    """charges = सर्व खर्च (ब्रोकरेज+STT+GST+...); pnl = निव्वळ (खर्च वजा)"""
    _q("UPDATE trades SET exit=?, pnl=?, charges=?, status='CLOSED', reason=?, closed=? WHERE id=?",
       (exit_price, pnl, charges, reason, closed, tid), commit=True)


def update_sl(tid, sl):
    _q("UPDATE trades SET sl=? WHERE id=?", (sl, tid), commit=True)


def get_trade(tid):
    row = _q("SELECT * FROM trades WHERE id=?", (tid,), fetch="one")
    return dict(row) if row else None


def get_open_trade(date, symbol=None):
    """symbol=None → कोणताही (नवीनतम); symbol='BANKNIFTY' → फक्त तोच"""
    if symbol:
        row = _q("SELECT * FROM trades WHERE status='OPEN' AND date=? AND symbol=? "
                 "ORDER BY id DESC LIMIT 1", (date, symbol), fetch="one")
    else:
        row = _q("SELECT * FROM trades WHERE status='OPEN' AND date=? "
                 "ORDER BY id DESC LIMIT 1", (date,), fetch="one")
    return dict(row) if row else None


def open_trades(date):
    """आजच्या सर्व उघड्या पोझिशन्स (सर्व सिम्बॉल्स)"""
    rows = _q("SELECT * FROM trades WHERE status='OPEN' AND date=? ORDER BY id",
              (date,), fetch="all") or []
    return [dict(r) for r in rows]


def trades_today(date, symbol=None):
    if symbol:
        rows = _q("SELECT * FROM trades WHERE date=? AND symbol=? ORDER BY id",
                  (date, symbol), fetch="all") or []
    else:
        rows = _q("SELECT * FROM trades WHERE date=? ORDER BY id",
                  (date,), fetch="all") or []
    return [dict(r) for r in rows]


def month_trades(prefix, symbol=None):
    """'YYYY-MM' उपसर्ग जुळणारे सर्व ट्रेड्स (महिना-दरम्यानच्या आकड्यांसाठी)"""
    if symbol:
        rows = _q("SELECT * FROM trades WHERE date LIKE ? AND symbol=? ORDER BY id",
                  (prefix + "%", symbol), fetch="all") or []
    else:
        rows = _q("SELECT * FROM trades WHERE date LIKE ? ORDER BY id",
                  (prefix + "%",), fetch="all") or []
    return [dict(r) for r in rows]


def closed_trades_today(date, symbol=None):
    return [t for t in trades_today(date, symbol) if t["status"] == "CLOSED"]


def today_pnl(date, symbol=None):
    return round(sum((t["pnl"] or 0)
                     for t in closed_trades_today(date, symbol)), 2)


def total_pnl():
    row = _q("SELECT COALESCE(SUM(pnl),0) AS s FROM trades WHERE status='CLOSED'",
             fetch="one")
    return round(row["s"], 2) if row else 0.0


def total_pnl_symbol(symbol):
    """एका सिम्बॉलचा सुरुवातीपासूनचा निव्वल P&L"""
    row = _q("SELECT COALESCE(SUM(pnl),0) AS s FROM trades "
             "WHERE status='CLOSED' AND symbol=?",
             (symbol,), fetch="one")
    return round(row["s"], 2) if row else 0.0


def today_charges(date, symbol=None):
    """आजचा एकूण खर्च (ब्रोकरेज+कर) — फक्त पूर्ण झालेल्या ट्रेड्सचा"""
    return round(sum((t["charges"] or 0)
                     for t in closed_trades_today(date, symbol)), 2)


def total_charges():
    """सुरुवातीपासून एकूण खर्च"""
    row = _q("SELECT COALESCE(SUM(charges),0) AS s FROM trades WHERE status='CLOSED'",
             fetch="one")
    return round(row["s"], 2) if row else 0.0
