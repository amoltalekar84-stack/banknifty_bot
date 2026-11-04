"""
🎯 Swing मॉड्यूल — वैयक्तिक शेअर्सचे ऑप्शन-बायिंग स्विंग ट्रेडिंग.
(ORB इंजिन अबाधित — स्वतंत्र थ्रेड, स्वतंत्र swing_* टेबल्स, स्वतंत्र ₹1L बाजू)

नियम (दैनिक, यंत्रणा-अनुकूल):
  ① ट्रेंड-फिल्टर: आदल्या दिवसाचा क्लोज > EMA50  आणि  EMA20 > EMA50
  ② ट्रिगर: आजचा LTP > आदल्या दिवसाचा HIGH (प्रतिदिन एकदाच स्कॅन 09:20 नंतर)
  ③ गॅप-फिल्टर: LTP आदल्या क्लोजपेक्षा +5% वर → वगळा (अति-विस्तार)
  ④ वगळणी-यादी: SWING_SKIP env ("TCS,INFY") — earnings असलेले शेअर
  ⑤ एंट्री: ATM CE (फक्त लाँग), जवळची महिना-expiry, DTE ≥ 10 लागतो;
     1 लॉट; प्रीमियम ≤ ₹35,000; बरोबर 2 स्थिती; एकूण उघड-धोका (SL-आधारित)
     ≤ ₹20,000; एंट्री-विंडो 09:20–14:30
एग्झिट:
  • SL −35% (दर 60 सेकंदांनी LTP तपासणी) — निश्चित
  • +60% → पूर्ण बुकिंग (नफा-कुलूप)
  • दैनिक क्लोज < EMA10 → एग्झिट (15:20 तपासणी)
  • 10-सेशन वेळेची मर्यादा (15:20 तपासणी)
  • Expiry-दिवशी 15:00 जबरदस्ती बंद (गामा-जोखीम नाही)
  • KILL स्विच → सर्व तात्काळ बंद
भांडवल: swing_capital (SWING_CAPITAL env, ₹1,00,000) — ORB भांडवलापासून पूर्ण वेगळे.
"""

import os
import threading
import time
import traceback
from datetime import datetime as dtm, time as dtime, timedelta

import charges
import config as C
import store
from config import ist_now
from upstox_api import (chain_lot, get_hist_candles, get_ltp,
                        get_market_status, get_option_chain)

_started = False
_lock = threading.Lock()

# ------------------------------------------------------------------
# Universe — 25 लिक्विड F&O शेअर्स (NSE_EQ keys, नोव्हेंबर 2026 पडताळले;
# TATAMOTORS → TMPV demerger-नंतरचे नाव)
# ------------------------------------------------------------------
UNIVERSE = [
    ("RELIANCE",   "NSE_EQ|INE002A01018"), ("HDFCBANK", "NSE_EQ|INE040A01034"),
    ("ICICIBANK",  "NSE_EQ|INE090A01021"), ("SBIN",     "NSE_EQ|INE062A01020"),
    ("AXISBANK",   "NSE_EQ|INE238A01034"), ("KOTAKBANK", "NSE_EQ|INE237A01036"),
    ("BAJFINANCE", "NSE_EQ|INE296A01032"), ("TCS",      "NSE_EQ|INE467B01029"),
    ("INFY",       "NSE_EQ|INE009A01021"), ("HCLTECH",  "NSE_EQ|INE860A01027"),
    ("LT",         "NSE_EQ|INE018A01030"), ("TATASTEEL", "NSE_EQ|INE081A01020"),
    ("JSWSTEEL",   "NSE_EQ|INE019A01038"), ("HINDALCO", "NSE_EQ|INE038A01020"),
    ("TMPV",       "NSE_EQ|INE155A01022"), ("M&M",      "NSE_EQ|INE101A01026"),
    ("MARUTI",     "NSE_EQ|INE585B01010"), ("TITAN",    "NSE_EQ|INE280A01028"),
    ("SUNPHARMA",  "NSE_EQ|INE044A01036"), ("CIPLA",    "NSE_EQ|INE059A01026"),
    ("ITC",        "NSE_EQ|INE154A01025"), ("HINDUNILVR", "NSE_EQ|INE030A01027"),
    ("NTPC",       "NSE_EQ|INE733E01010"), ("ONGC",     "NSE_EQ|INE213A01029"),
    ("DLF",        "NSE_EQ|INE271C01023"),
]

# ------------------------------------------------------------------
# पॅरामीटर्स (env ने बदलता येतात)
# ------------------------------------------------------------------
ENABLED = os.getenv("ENABLE_SWING", "YES").strip().upper() != "NO"
CAPITAL = float(os.getenv("SWING_CAPITAL", "100000"))
MAX_POS = int(os.getenv("SWING_MAX_POS", "2"))
PREMIUM_CAP = float(os.getenv("SWING_PREMIUM_CAP", "35000"))
OPEN_RISK_CAP = float(os.getenv("SWING_OPEN_RISK_CAP", "20000"))
SL_PCT = float(os.getenv("SWING_SL_PCT", "35"))          # SL = −35% प्रीमियम
TP_PCT = float(os.getenv("SWING_TP_PCT", "60"))          # +60% → पूर्ण बुकिंग
MAX_SESSIONS = int(os.getenv("SWING_MAX_SESSIONS", "10"))
MIN_DTE = int(os.getenv("SWING_MIN_DTE", "10"))
GAP_SKIP_PCT = float(os.getenv("SWING_GAP_SKIP_PCT", "5"))
ENTRY_START = os.getenv("SWING_ENTRY_START", "09:20")
ENTRY_END = os.getenv("SWING_ENTRY_END", "14:30")
SCAN_AT = os.getenv("SWING_SCAN_AT", "09:20")
EOD_CHECK = os.getenv("SWING_EOD_CHECK", "15:20")
EXPIRY_FORCE_EXIT = os.getenv("SWING_EXP_EXIT", "15:00")


def _t(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _capital():
    try:
        return float(store.get_state("swing_capital") or CAPITAL)
    except (TypeError, ValueError):
        return CAPITAL


def _skip_list():
    return {s.strip().upper() for s in
            os.getenv("SWING_SKIP", "").split(",") if s.strip()}


# ------------------------------------------------------------------
# तांत्रिक मोजमाप
# ------------------------------------------------------------------
def ema(values, n):
    """साधा EMA — यादी [क्लोज...] → EMA-यादी (समान लांबी; पहिले मूल्य = पहिला क्लोज)"""
    if not values:
        return []
    k = 2.0 / (n + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _daily_closes(candles):
    return [float(c[4]) for c in candles]


def compute_signal(candles):
    """आदल्या दिवसाच्या (पूर्ण) दैनिक कॅन्डलवरून सिग्नल-घटक.
    candles = [[ts,o,h,l,c,v], ...] क्रमवार (जुने→नवीन), शेवटचा = आदला दिवस.
    → dict(trend, prev_high, prev_close, ema10, ema20, ema50, note)"""
    closes = _daily_closes(candles)
    if len(closes) < 60:
        return None
    e10 = ema(closes, 10)[-1]
    e20 = ema(closes, 20)[-1]
    e50 = ema(closes, 50)[-1]
    last = candles[-1]
    prev_close = float(last[4])
    prev_high = float(last[2])
    trend = 1 if (prev_close > e50 and e20 > e50) else 0
    return {"trend": trend, "prev_high": prev_high, "prev_close": prev_close,
            "ema10": round(e10, 2), "ema20": round(e20, 2),
            "ema50": round(e50, 2)}


def sessions_held(entry_date, today):
    """एंट्री-दिवसापासून आजपर्यंत किती बाजार-सेशन (सोम–शुक्र, सुट्टी-अंदाज)"""
    try:
        d0 = dtm.strptime(entry_date, "%Y-%m-%d").date()
        d1 = dtm.strptime(today, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0
    if d1 <= d0:
        return 0
    n, d = 0, d0
    while d < d1:
        d = d.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            n += 1
    return n


# ------------------------------------------------------------------
# ATM ऑप्शन निवड (चेन-API → शेअर-अंतर्निहित)
# ------------------------------------------------------------------
def pick_atm(token, eq_key, spot, side, premium_cap):
    """चेन → जवळची expiry (DTE ≥ MIN_DTE) → ATM स्ट्राइक → CE/PE node.
    → {key, strike, expiry, ltp, lot} किंवा None"""
    _dbg = os.getenv("SWING_DEBUG")
    try:
        chain = get_option_chain(token, eq_key)
    except Exception as _e:
        if _dbg:
            print("  [pick_atm] chain err:", repr(_e))
        return None
    if not chain:
        if _dbg:
            print("  [pick_atm] chain रिकामी")
        return None
    today = ist_now().strftime("%Y-%m-%d")
    exps = sorted({(r.get("expiry_date") or r.get("expiry"))
                   for r in chain
                   if (r.get("expiry_date") or r.get("expiry"))})
    near = None
    for e in exps:
        dte = (dtm.strptime(e, "%Y-%m-%d").date()
               - dtm.strptime(today, "%Y-%m-%d").date()).days
        if dte >= MIN_DTE:
            near = e
            break
    if not near:
        return None                       # सर्व expiry-या जवळ — एंट्री नाही
    qlot = chain_lot(eq_key) or 0
    rows = sorted([r for r in chain
                   if (r.get("expiry_date") or r.get("expiry")) == near],
                  key=lambda r: abs(float(r.get("strike_price") or 0) - spot))
    for row in rows[:4]:
        node = row.get("call_options") if side == "CE" else row.get("put_options")
        if not node:
            continue
        key = node.get("instrument_key")
        if not key:
            continue
        ltp = (node.get("market_data") or {}).get("ltp")
        if ltp in (None, 0):
            try:
                ltp = get_ltp(key, token)
            except Exception:
                ltp = None
        if not ltp or float(ltp) <= 0:
            continue
        ltp = float(ltp)
        lot = qlot or int(row.get("lot_size") or 0)
        if lot <= 0 or ltp * lot > premium_cap:
            continue
        return {"key": key, "strike": float(row.get("strike_price") or 0),
                "expiry": near, "ltp": ltp, "lot": int(lot)}
    return None


# ------------------------------------------------------------------
# उघड-धोका (SL-आधारित) — ₹20k मर्यादेसाठी
# ------------------------------------------------------------------
def open_risk():
    return round(sum((float(p["entry"]) - float(p["sl"])) * int(p["qty"])
                     for p in store.swing_open()), 2)


def deployed_premium():
    return round(sum(float(p["entry"]) * int(p["qty"])
                     for p in store.swing_open()), 2)


# ------------------------------------------------------------------
# स्कॅन (दिवसात एकदा) + एंट्री
# ------------------------------------------------------------------
def _scan(token, now, force=False):
    date = now.strftime("%Y-%m-%d")
    key = "swing_scan_" + date
    if store.get_state(key) == "1" and not force:
        return
    store.set_state(key, "1")
    skips = _skip_list()
    entries = 0
    try:
        for sym, eq_key in UNIVERSE:
            note = ""
            try:
                if sym in skips:
                    note = "SKIP(earnings-यादी)"
                    store.swing_scan_upsert(date, sym, None, None, None,
                                            0, 0, note)
                    continue
                frm = (now - timedelta(days=230)).strftime("%Y-%m-%d")
                to = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                candles = get_hist_candles(token, eq_key, "day", frm, to)
                candles = sorted(candles, key=lambda c: c[0])
                sig = compute_signal(candles)
                if not sig:
                    store.swing_scan_upsert(date, sym, None, None, None,
                                            0, 0, "इतिहास अपुरा")
                    continue
                spot = get_ltp(eq_key, token)
                if not spot or spot <= 0:
                    store.swing_scan_upsert(date, sym, None,
                                            sig["prev_high"],
                                            sig["prev_close"], sig["trend"],
                                            0, "LTP नाही")
                    continue
                gap_ok = spot <= sig["prev_close"] * (1 + GAP_SKIP_PCT / 100.0)
                triggered = 1 if (sig["trend"] and gap_ok and
                                  spot > sig["prev_high"]) else 0
                note = ("🎯 ट्रिगर" if triggered else
                        ("गॅप +%.1f%%" % (100 * (spot / sig["prev_close"] - 1))
                         if spot > sig["prev_high"] else
                         ("👁 ट्रेंड-सेटअप" if sig["trend"] else "प्रतीक्षा")))
                store.swing_scan_upsert(date, sym, round(spot, 2),
                                        sig["prev_high"], sig["prev_close"],
                                        sig["trend"], triggered, note)
                if triggered and _t(ENTRY_START) <= now.time() <= _t(ENTRY_END):
                    if _try_enter(token, sym, eq_key, spot, sig, now):
                        entries += 1
                time.sleep(0.35)          # API-दर मर्यादा सन्मान
            except Exception as e:
                store.swing_scan_upsert(date, sym, None, None, None, 0, 0,
                                        "त्रुटी: " + str(e)[:60])
        store.log_event(f"🎯 Swing स्कॅन पूर्ण ({date}): {entries} एंट्री")
    except Exception:
        store.log_event("swing scan err: " + traceback.format_exc()[:250])


def _try_enter(token, sym, eq_key, spot, sig, now):
    from telegram_bot import notify
    date = now.strftime("%Y-%m-%d")
    acted = "swing_acted_" + date + "_" + sym
    if store.get_state(acted) == "1":
        return False                     # याच शेअरची दुसारी एंट्री नाही
    opens = store.swing_open()
    if len(opens) >= MAX_POS:
        store.swing_scan_upsert(date, sym, round(spot, 2), sig["prev_high"],
                                sig["prev_close"], sig["trend"], 1,
                                "सीमा: बरोबर " + str(MAX_POS) + " भरले")
        return False
    opt = pick_atm(token, eq_key, spot, "CE", PREMIUM_CAP)
    if not opt:
        store.swing_scan_upsert(date, sym, round(spot, 2), sig["prev_high"],
                                sig["prev_close"], sig["trend"], 1,
                                "प्रीमियम-कॅप/DTE — एंट्री नाही")
        return False
    entry = round(opt["ltp"] * 1.0005, 2)          # 0.05% स्लिपेज
    qty = int(opt["lot"])
    cost = entry * qty
    if cost > _capital() * 0.90 - deployed_premium():
        store.swing_scan_upsert(date, sym, round(spot, 2), sig["prev_high"],
                                sig["prev_close"], sig["trend"], 1,
                                "स्लीव्ह-जागा नाही")
        return False
    sl = round(entry * (1 - SL_PCT / 100.0), 2)
    new_risk = (entry - sl) * qty
    if open_risk() + new_risk > OPEN_RISK_CAP:
        store.swing_scan_upsert(date, sym, round(spot, 2), sig["prev_high"],
                                sig["prev_close"], sig["trend"], 1,
                                "उघड-धोका-मर्यादा")
        return False
    tid = store.swing_insert(date, sym, "CE", opt["key"], opt["strike"],
                             opt["expiry"], qty, entry, sl, round(spot, 2),
                             sig["ema20"], sig["ema50"])
    store.set_state(acted, "1")          # आज या शेअरची एंट्री झाली
    store.swing_set_ltp(tid, entry)
    store.log_event(f"🎯 Swing ENTRY {sym} {opt['strike']:.0f}CE "
                    f"exp={opt['expiry']} qty={qty} @₹{entry:.2f}")
    chg = charges.option_charges_ladder(
        entry * qty, [(round(entry * (1 + TP_PCT / 100.0), 2), qty)])
    notify(
        f"🎯 <b>SWING ENTRY</b> — {sym}\n"
        f"{opt['strike']:.0f} CE | expiry {opt['expiry']} (महिना)\n"
        f"स्पॉट ₹{spot:,.2f} • आदला हाय ₹{sig['prev_high']:,.2f} भेदला ✅\n"
        f"प्रीमियम ₹{entry:.2f} × {qty} = ₹{cost:,.0f}\n"
        f"SL ₹{sl:.2f} (−{SL_PCT:.0f}%) | टार्गेट +{TP_PCT:.0f}% | "
        f"वेळ-मर्यादा {MAX_SESSIONS} सेशन\n"
        f"EMA20 ₹{sig['ema20']:.1f} / EMA50 ₹{sig['ema50']:.1f} | "
        f"अंदाजे खर्च ₹{chg['total']:,.0f}\n"
        f"🧪 PAPER — swing बाजू ₹{_capital():,.0f}",
        html=True)
    return True


# ------------------------------------------------------------------
# निरीक्षण (दर ~60 से) + एग्झिट
# ------------------------------------------------------------------
def _exit_position(p, ltp, reason, now, extra_price=None):
    from telegram_bot import notify
    tid = p["id"]
    entry = float(p["entry"])
    qty = int(p["qty"])
    exitp = round(float(extra_price if extra_price is not None
                        else ltp) * (1 - 0.0005), 2)
    chg = charges.option_charges_ladder(
        entry * qty, [(exitp, qty)])["total"]
    pnl = round((exitp - entry) * qty - chg, 2)
    when = now.strftime("%Y-%m-%d %H:%M:%S")
    store.swing_close(tid, exitp, pnl, chg, reason, when)
    store.log_event(f"🎯 Swing EXIT {p['symbol']} {p['strike']:.0f}CE "
                    f"{reason}: ₹{pnl:,.0f}")
    icon = "✅" if pnl >= 0 else "❌"
    notify(
        f"{icon} <b>SWING EXIT</b> — {p['symbol']}\n"
        f"{p['strike']:.0f} CE | एंट्री ₹{entry:.2f} → एग्झिट ₹{exitp:.2f}\n"
        f"कारण: {reason} | धरला: {sessions_held(p['date'], now.strftime('%Y-%m-%d'))} सेशन\n"
        f"निव्वल P&L: <b>₹{pnl:,.0f}</b> (खर्च ₹{chg:,.0f} वजा) | "
        f"स्लीव्ह सुरुवातीपासून ₹{store.swing_total_pnl():,.0f}\n"
        f"🧪 PAPER", html=True)
    return pnl


def _monitor(token, now):
    date = now.strftime("%Y-%m-%d")
    for p in store.swing_open():
        try:
            ltp = get_ltp(p["option_key"], token)
            if not ltp or ltp <= 0:
                continue
            store.swing_set_ltp(p["id"], round(ltp, 2))
            # expiry-दिवशी 15:00 जबरदस्ती
            if p["expiry"] == date and now.time() >= _t(EXPIRY_FORCE_EXIT):
                _exit_position(p, ltp, "Expiry-दिवशी जबरदस्ती बंद", now)
                continue
            if ltp <= float(p["sl"]):
                _exit_position(p, ltp, f"SL −{SL_PCT:.0f}% 🛑", now)
                continue
            if ltp >= float(p["entry"]) * (1 + TP_PCT / 100.0):
                _exit_position(p, ltp, f"टार्गेट +{TP_PCT:.0f}% ✅", now)
        except Exception as e:
            store.log_event(f"swing monitor[{p['symbol']}]: " + str(e)[:120])


def _eod_check(token, now):
    """15:20 नंतर एकदा: EMA10-खाली क्लोज + वेळेची मर्यादा"""
    date = now.strftime("%Y-%m-%d")
    if store.get_state("swing_eod_" + date) == "1":
        return
    store.set_state("swing_eod_" + date, "1")
    for p in store.swing_open():
        try:
            held = sessions_held(p["date"], date)
            if held >= MAX_SESSIONS:
                ltp = get_ltp(p["option_key"], token) or \
                    store.swing_get_ltp(p["id"]) or float(p["entry"])
                _exit_position(p, ltp,
                               f"वेळेची मर्यादा ({MAX_SESSIONS} सेशन)", now)
                continue
            eq_key = _eq_key(p["symbol"])
            if not eq_key:
                continue
            frm = (now - timedelta(days=230)).strftime("%Y-%m-%d")
            candles = sorted(
                get_hist_candles(token, eq_key, "day", frm, date),
                key=lambda c: c[0])
            closes = _daily_candles_closes(candles)
            if len(closes) < 15:
                continue
            e10 = ema(closes, 10)[-1]
            last_close = closes[-1]
            # EMA10-नियम फक्त आजची दैनिक कॅन्डल खरोखर मिळाली तरच (नाहीतर
            # आदलाच क्लोज पुन्हा तपासून चुकीचा एग्झिट होईल)
            if candles and str(candles[-1][0])[:10] == date and \
                    last_close < e10 and held >= 1:
                ltp = get_ltp(p["option_key"], token) or last_close
                _exit_position(p, ltp,
                               f"क्लोज < EMA10 (₹{last_close:,.1f} < ₹{e10:,.1f})",
                               now)
        except Exception as e:
            store.log_event(f"swing eod[{p['symbol']}]: " + str(e)[:120])


def _daily_candles_closes(candles):
    return [float(c[4]) for c in candles]


def _eq_key(symbol):
    for s, k in UNIVERSE:
        if s == symbol:
            return k
    return None


# ------------------------------------------------------------------
# मुख्य लूप (स्वतंत्र थ्रेड)
# ------------------------------------------------------------------
def _loop():
    store.log_event("🎯 Swing मॉड्यूल सुरू — "
                    f"{len(UNIVERSE)} शेअर्स, बाजू ₹{_capital():,.0f}, "
                    f"बरोबर {MAX_POS}, SL −{SL_PCT:.0f}%")
    while True:
        try:
            now = ist_now()
            if now.weekday() >= 5 or not ENABLED:
                time.sleep(60)
                continue
            token = store.get_state("upstox_token")
            if not token:
                time.sleep(60)
                continue
            date = now.strftime("%Y-%m-%d")
            # KILL → सर्व swing स्थिती तात्काळ बंद
            if store.get_state("killed") == "1":
                if store.get_state("swing_killdone_" + date) != "1":
                    store.set_state("swing_killdone_" + date, "1")
                    for p in store.swing_open():
                        try:
                            ltp = get_ltp(p["option_key"], token)
                            if ltp and ltp > 0:
                                _exit_position(p, ltp, "KILL स्विच 🚨", now)
                        except Exception:
                            pass
                time.sleep(30)
                continue
            # NSE बंद (सुट्टी) → काहीच नाही
            try:
                if get_market_status(token, "NSE") == "NORMAL_CLOSE":
                    time.sleep(300)
                    continue
            except Exception:
                pass
            in_mkt = _t("09:15") <= now.time() <= _t("15:30")
            if in_mkt:
                # निरीक्षण — पोझिशन असतील तर दर फेरीत
                if store.swing_open():
                    _monitor(token, now)
                # स्कॅन — दिवसात एकदा, 09:20 नंतर
                if now.time() >= _t(SCAN_AT):
                    _scan(token, now)
            # 15:20 EMA10/वेळ-मर्यादा तपासणी
            if now.time() >= _t(EOD_CHECK) and now.time() <= _t("15:45"):
                _eod_check(token, now)
            time.sleep(60)
        except Exception as e:
            try:
                store.log_event("swing loop err: " + repr(e)
                                + traceback.format_exc()[:200])
            except Exception:
                pass
            time.sleep(60)


def start_swing():
    """swing थ्रेड सुरू करा (engine.start_engine मधून; एकदाच)"""
    global _started
    if not ENABLED:
        return
    with _lock:
        if _started:
            return
        _started = True
    store.init_db()
    threading.Thread(target=_loop, daemon=True, name="swing").start()


# ------------------------------------------------------------------
# दृश्य-मार्ग: डॅशबोर्ड + /api/eval + Telegram
# ------------------------------------------------------------------
def eval_block(date):
    """/api/eval चा 'swing' ब्लॉक"""
    opens = []
    for p in store.swing_open():
        ltp = store.swing_get_ltp(p["id"])
        mtm = round((ltp - float(p["entry"])) * int(p["qty"]), 2) \
            if ltp else None
        opens.append({
            "id": p["id"], "symbol": p["symbol"], "strike": p["strike"],
            "expiry": p["expiry"], "qty": p["qty"], "entry": p["entry"],
            "sl": p["sl"], "entry_date": p["date"],
            "sessions_held": sessions_held(p["date"], date),
            "last_ltp": ltp, "mtm": mtm,
        })
    mts = [t for t in store.swing_month(date[:7]) if t["status"] == "CLOSED"]
    today_closed = [t for t in store.swing_today(date)
                    if t["status"] == "CLOSED"]
    scan = store.swing_scan_today(date)
    return {
        "enabled": ENABLED,
        "rules": {
            "capital": _capital(), "max_positions": MAX_POS,
            "premium_cap": PREMIUM_CAP, "open_risk_cap": OPEN_RISK_CAP,
            "sl_pct": SL_PCT, "tp_pct": TP_PCT,
            "max_sessions": MAX_SESSIONS, "min_dte": MIN_DTE,
            "entry_window": ENTRY_START + "–" + ENTRY_END,
            "universe": len(UNIVERSE),
        },
        "positions": opens,
        "deployed_premium": deployed_premium(),
        "open_risk": open_risk(),
        "today": {
            "entries": len(store.swing_today(date)),
            "closed": len(today_closed),
            "pnl_net": round(sum((t["pnl"] or 0) for t in today_closed), 2),
        },
        "month": {
            "trades": len(mts),
            "wins": sum(1 for t in mts if (t["pnl"] or 0) >= 0),
            "losses": sum(1 for t in mts if (t["pnl"] or 0) < 0),
            "pnl_net": round(sum((t["pnl"] or 0) for t in mts), 2),
            "charges": round(sum((t["charges"] or 0) for t in mts), 2),
        },
        "total_pnl": store.swing_total_pnl(),
        "scan": [{"symbol": r["symbol"], "spot": r["spot"],
                  "prev_high": r["prev_high"], "trend": r["trend"],
                  "triggered": r["triggered"], "note": r["note"]}
                 for r in scan],
    }


def tele_text(date=None):
    """/swing — Telegram सारांश"""
    n = ist_now()
    date = date or n.strftime("%Y-%m-%d")
    b = eval_block(date)
    lines = [f"🎯 <b>Swing — वैयक्तिक शेअर्स</b> ({date})",
             f"बाजू ₹{b['rules']['capital']:,.0f} | उघडे {len(b['positions'])}"
             f"/{b['rules']['max_positions']} | उघड-धोका ₹{b['open_risk']:,.0f}"
             f"/₹{b['rules']['open_risk_cap']:,.0f}"]
    for p in b["positions"]:
        mtm = f" | MTM {('₹%+.0f' % p['mtm']) if p['mtm'] is not None else '—'}"
        lines.append(f"  ◉ {p['symbol']} {p['strike']:.0f}CE "
                     f"@ ₹{p['entry']:.2f} • {p['sessions_held']} सेशन{mtm}")
    if not b["positions"]:
        lines.append("  (कोणतीही उघडी स्थिती नाही)")
    tg = [s for s in b["scan"] if s["triggered"]]
    setup = [s for s in b["scan"] if s["trend"] and not s["triggered"]]
    lines.append(f"\nस्कॅन: {len(b['scan'])} शेअर्स | "
                 f"🎯 ट्रिगर {len(tg)} | 👁 सेटअप {len(setup)}")
    for s in tg[:6]:
        lines.append(f"  🎯 {s['symbol']} स्पॉट {s['spot']} > हाय {s['prev_high']}")
    lines.append(f"\nMTD ₹{b['month']['pnl_net']:,.0f} "
                 f"({b['month']['wins']}W/{b['month']['losses']}L) | "
                 f"सुरुवातीपासून ₹{b['total_pnl']:,.0f}")
    lines.append("नियम: ट्रेंड EMA50 + ट्रिगर आदला-हाय भेद | SL −35% | "
                 "+60% बुक | EMA10-खाली क्लोज → एग्झिट | 10-सेशन मर्यादा")
    return "\n".join(lines)


def eod_lines(date):
    """EOD अहवालासाठी swing-ओळी (telegram_bot._eod_text मधून)"""
    b = eval_block(date)
    if not b["enabled"]:
        return []
    out = [f"\n🎯 <b>SWING</b> — उघडे {len(b['positions'])}"
           f"/{b['rules']['max_positions']} | आज +₹{b['today']['pnl_net']:,.0f} "
           f"| MTD ₹{b['month']['pnl_net']:,.0f} | "
           f"सुरुवातीपासून ₹{b['total_pnl']:,.0f}"]
    for p in b["positions"]:
        mtm = ("₹%+.0f" % p["mtm"]) if p["mtm"] is not None else "—"
        out.append(f"   ◉ {p['symbol']} {p['strike']:.0f}CE "
                   f"@{p['entry']:.2f} • {p['sessions_held']} सेशन • MTM {mtm}")
    return out
