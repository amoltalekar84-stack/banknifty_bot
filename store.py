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

        CREATE TABLE IF NOT EXISTS oi_snap(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, date TEXT, symbol TEXT,
            spot REAL, atm REAL, pcr REAL,
            ce_oi REAL, pe_oi REAL, ce_chg REAL, pe_chg REAL,
            max_pain REAL, atm_iv REAL, ce_wall REAL, pe_wall REAL,
            chain BLOB);

        CREATE INDEX IF NOT EXISTS idx_oi_sym_date ON oi_snap(symbol, date);

        CREATE TABLE IF NOT EXISTS vix_snap(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, date TEXT, vix REAL);

        CREATE INDEX IF NOT EXISTS idx_vix_date ON vix_snap(date);

        CREATE TABLE IF NOT EXISTS swing_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, symbol TEXT, side TEXT,
            option_key TEXT, strike REAL, expiry TEXT,
            qty INTEGER, entry REAL, sl REAL,
            spot_entry REAL, ema20 REAL, ema50 REAL,
            status TEXT, reason TEXT, pnl REAL, charges REAL,
            exit_price REAL, closed TEXT, legs TEXT);

        CREATE INDEX IF NOT EXISTS idx_sw_status ON swing_trades(status);

        CREATE TABLE IF NOT EXISTS swing_scan(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, symbol TEXT, spot REAL, prev_high REAL,
            prev_close REAL, trend INTEGER, triggered INTEGER,
            note TEXT);

        CREATE INDEX IF NOT EXISTS idx_swscan_date ON swing_scan(date);
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


def get_state_ts(k, default=None):
    """state कीचा शेवटचा अपडेट-वेळ (epoch) — निदानासाठी (उदा. टोकन कधी सेट झाला)"""
    row = _q("SELECT ts FROM state WHERE k=?", (str(k),), fetch="one")
    return row["ts"] if row else default


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


# ---------------- OI स्नॅपशॉट्स (PCR / Max Pain / ग्रीक्स) ----------------
def oi_insert(sym, date, m, chain_blob=None):
    """एक OI स्नॅपशॉट जतन करा (m = oicollect.compute_chain चा dict)"""
    return _q(
        "INSERT INTO oi_snap(ts,date,symbol,spot,atm,pcr,ce_oi,pe_oi,"
        "ce_chg,pe_chg,max_pain,atm_iv,ce_wall,pe_wall,chain) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (m.get("ts"), date, sym, m.get("spot"), m.get("atm"), m.get("pcr"),
         m.get("ce_oi"), m.get("pe_oi"), m.get("ce_chg"), m.get("pe_chg"),
         m.get("max_pain"), m.get("atm_iv"), m.get("ce_wall"),
         m.get("pe_wall"), chain_blob), commit=True)


def oi_last(sym, date=None):
    """शेवटचा स्नॅपशॉट (date दिला तर त्या दिवसाचाच)"""
    if date:
        return _q("SELECT * FROM oi_snap WHERE symbol=? AND date=? "
                  "ORDER BY id DESC LIMIT 1", (sym, date), fetch="one")
    return _q("SELECT * FROM oi_snap WHERE symbol=? ORDER BY id DESC LIMIT 1",
              (sym,), fetch="one")


def oi_count(sym, date):
    r = _q("SELECT COUNT(*) AS c FROM oi_snap WHERE symbol=? AND date=?",
           (sym, date), fetch="one")
    return int(r["c"] or 0) if r else 0


def oi_pcr_range(sym, date):
    """आजची PCR किमान-कमाल रेंज"""
    r = _q("SELECT MIN(pcr) AS lo, MAX(pcr) AS hi FROM oi_snap "
           "WHERE symbol=? AND date=?", (sym, date), fetch="one")
    if r:
        return r["lo"], r["hi"]
    return None, None


def oi_days(sym, limit=90):
    """मागच्या दिवसांचे दिवस-समारोप (प्रति दिवस शेवटचा स्नॅपशॉट) — स्ट्रॅटेजी-अभ्यासासाठी"""
    return _q(
        "SELECT date, spot, atm, pcr, ce_oi, pe_oi, ce_chg, pe_chg, "
        "max_pain, atm_iv, ce_wall, pe_wall FROM oi_snap o "
        "WHERE symbol=? AND id IN (SELECT MAX(id) FROM oi_snap "
        "WHERE symbol=o.symbol GROUP BY date) ORDER BY date DESC LIMIT ?",
        (sym, limit), fetch="all")


# ---------------- India VIX (रेजिम-फिल्टर — स्ट्रॅटेजी अभ्यासासाठी) ----------------
def vix_insert(date, vix):
    """एक VIX स्नॅपशॉट जतन करा (कलेक्टर दर 5 मिनिटांनी)"""
    from config import ist_now
    n = ist_now()
    return _q("INSERT INTO vix_snap(ts,date,vix) VALUES(?,?,?)",
              (n.strftime("%Y-%m-%d %H:%M:%S"), date, vix), commit=True)


def vix_last(date=None):
    """शेवटचा VIX स्नॅपशॉट (date दिला तर त्या दिवसाचाच)"""
    if date:
        return _q("SELECT * FROM vix_snap WHERE date=? ORDER BY id DESC LIMIT 1",
                  (date,), fetch="one")
    return _q("SELECT * FROM vix_snap ORDER BY id DESC LIMIT 1", fetch="one")


def vix_range(date):
    """आजचा VIX किमान-कमाल"""
    r = _q("SELECT MIN(vix) AS lo, MAX(vix) AS hi FROM vix_snap WHERE date=?",
           (date,), fetch="one")
    if r:
        return r["lo"], r["hi"]
    return None, None


# ---------------- Swing (वैयक्तिक शेअर्स — वेगळा मॉड्यूल) ----------------
def swing_insert(date, symbol, side, option_key, strike, expiry, qty,
                 entry, sl, spot_entry, ema20, ema50):
    return _q(
        """INSERT INTO swing_trades(date,symbol,side,option_key,strike,expiry,
                                      qty,entry,sl,spot_entry,ema20,ema50,status,legs)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'OPEN','[]')""",
        (date, symbol, side, option_key, strike, expiry, qty, entry, sl,
         spot_entry, ema20, ema50), commit=True)


def swing_get(tid):
    row = _q("SELECT * FROM swing_trades WHERE id=?", (tid,), fetch="one")
    return dict(row) if row else None


def swing_open(symbol=None):
    if symbol:
        rows = _q("SELECT * FROM swing_trades WHERE status='OPEN' AND symbol=? "
                  "ORDER BY id", (symbol,), fetch="all") or []
    else:
        rows = _q("SELECT * FROM swing_trades WHERE status='OPEN' ORDER BY id",
                  fetch="all") or []
    return [dict(r) for r in rows]


def swing_update_sl(tid, sl):
    _q("UPDATE swing_trades SET sl=? WHERE id=?", (sl, tid), commit=True)


def swing_close(tid, exit_price, pnl, charges, reason, closed_str):
    _q("""UPDATE swing_trades SET exit_price=?, pnl=?, charges=?,
              status='CLOSED', reason=?, closed=? WHERE id=?""",
       (exit_price, pnl, charges, str(reason)[:200], closed_str, tid),
       commit=True)


def swing_today(date, symbol=None):
    if symbol:
        rows = _q("SELECT * FROM swing_trades WHERE date=? AND symbol=? ORDER BY id",
                  (date, symbol), fetch="all") or []
    else:
        rows = _q("SELECT * FROM swing_trades WHERE date=? ORDER BY id",
                  (date,), fetch="all") or []
    return [dict(r) for r in rows]


def swing_month(prefix):
    rows = _q("SELECT * FROM swing_trades WHERE date LIKE ? ORDER BY id",
              (prefix + "%",), fetch="all") or []
    return [dict(r) for r in rows]


def swing_total_pnl():
    row = _q("SELECT COALESCE(SUM(pnl),0) AS s FROM swing_trades "
             "WHERE status='CLOSED'", fetch="one")
    return round(row["s"], 2) if row else 0.0


def swing_scan_upsert(date, symbol, spot, prev_high, prev_close,
                      trend, triggered, note):
    row = _q("SELECT id FROM swing_scan WHERE date=? AND symbol=?",
             (date, symbol), fetch="one")
    if row:
        _q("""UPDATE swing_scan SET spot=?, prev_high=?, prev_close=?,
                  trend=?, triggered=?, note=? WHERE id=?""",
           (spot, prev_high, prev_close, trend, triggered, note, row["id"]),
           commit=True)
        return row["id"]
    return _q("""INSERT INTO swing_scan(date,symbol,spot,prev_high,
                          prev_close,trend,triggered,note)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (date, symbol, spot, prev_high, prev_close, trend,
               triggered, note), commit=True)


def swing_scan_today(date):
    rows = _q("SELECT * FROM swing_scan WHERE date=? ORDER BY triggered DESC, symbol",
              (date,), fetch="all") or []
    return [dict(r) for r in rows]


def swing_set_ltp(tid, ltp):
    set_state("swing_ltp_" + str(tid), str(ltp))


def swing_get_ltp(tid, default=None):
    try:
        return float(get_state("swing_ltp_" + str(tid), default))
    except (TypeError, ValueError):
        return default
