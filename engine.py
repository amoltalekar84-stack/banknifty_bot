"""
मुख्य ट्रेडिंग इंजिन — स्वयंचलित लूप.

प्रवाह (प्रत्येक POLL_SEC सेकंदांनी):
  ① बाजार वेळ तपासा (सोम–शुक्र, 9:15–15:30 IST)
  ② टोकन आहे का? → नाही तर Telegram वर पाठवा
  ③ पोझिशन उघडी असल्यास तिचे निरीक्षण करा (SL/टार्गेट/ट्रेल/वेळ)
  ④ उघडी नसल्यास ORB सिग्नल तपासा → ATM ऑप्शन निवडा → एंट्री
  ⑤ 15:05 ला जबरदस्ती स्क्वेअर-ऑफ, 15:20 ला दैनिक अहवाल
"""

import threading
import time
import traceback
from datetime import time as dtime, timedelta

import config as C
import paper
import risk
import store
from config import ist_now
from strategy import analyze, parse_candles
from upstox_api import (UpstoxError, get_ltp, get_option_chain,
                        get_prev_close, get_today_candles, place_order)

_started = False
_lock = threading.Lock()


def _t(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def start_engine():
    """इंजिन थ्रेड सुरू करा (एकदाच)"""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    store.init_db()
    # env मध्ये टोकन दिले असेल तर seed करा
    if C.UPSTOX_ACCESS_TOKEN and not store.get_state("upstox_token"):
        store.set_state("upstox_token", C.UPSTOX_ACCESS_TOKEN)
    if C.MODE and not store.get_state("mode"):
        store.set_state("mode", C.MODE)
    t = threading.Thread(target=_loop, daemon=True, name="engine")
    t.start()


def _loop():
    from telegram_bot import notify
    notify(f"🤖 बॉट सुरू झाला — मोड: {store.get_state('mode', 'PAPER')}\n"
           f"बाजार वेळ: {C.MARKET_OPEN}–{C.MARKET_CLOSE} IST (सोम–शुक्र)\n"
           f"धोरण: ORB | SL: -{C.SL_PCT:.0f}% | टार्गेट: +{C.TARGET_PCT:.0f}%")
    while True:
        try:
            _tick()
        except UpstoxError as e:
            if "TOKEN_INVALID" in str(e):
                store.set_state("upstox_token", "")
                notify("⚠️ टोकन अवैध/संपले!\nनवीन टोकन पाठवा: /code XXXXXX किंवा /token XXXXXX")
            else:
                store.log_event("engine: " + str(e))
                notify("⚠️ API त्रुटी: " + str(e)[:200])
        except Exception as e:                      # कधीही लूप मरू नये
            store.log_event("engine err: " + repr(e) + traceback.format_exc()[:300])
            notify("⚠️ इंजिन त्रुटी: " + repr(e)[:200])
        time.sleep(C.POLL_SEC)


def _tick():
    from telegram_bot import notify
    now = ist_now()
    date = now.strftime("%Y-%m-%d")

    if now.weekday() >= 5:          # शनिवार/रविवारी
        return

    # नवीन दिवस → स्वागत संदेश
    if store.get_state("day_init") != date:
        store.set_state("day_init", date)
        notify(f"🌅 नवीन दिवस: {date}\n"
               f"मोड: {store.get_state('mode', 'PAPER')} | "
               f"टोकन: {'✅' if store.get_state('upstox_token') else '❌ नाही (/code पाठवा)'}")

    # 15:20 → दैनिक अहवाल
    if now.time() >= _t("15:20") and store.get_state("summary_" + date) != "1":
        store.set_state("summary_" + date, "1")
        _send_summary(date)
        return

    if not (_t(C.MARKET_OPEN) <= now.time() <= _t(C.MARKET_CLOSE)):
        return

    token = store.get_state("upstox_token")
    if not token:
        if now.time() >= _t("09:10") and store.get_state("tokwarn_" + date) != "1":
            store.set_state("tokwarn_" + date, "1")
            notify("⚠️ आजचा Upstox टोकन अजून आला नाही!\n"
                   "सकाळी लॉगिन करून /code XXXXXX पाठवा — नाहीतर आज ट्रेड होणार नाही.")
        return

    pos = store.get_open_trade(date)
    if store.get_state("killed") == "1":
        if pos:
            _force_close(pos, token, now)     # KILL → तात्काळ बंद
        return
    if pos:
        _monitor(pos, token, now)
        return

    ok, _why = risk.can_enter(date)
    if not ok:
        return
    _maybe_enter(date, token, now)


# ------------------------------------------------------------------
# एंट्री
# ------------------------------------------------------------------
def _maybe_enter(date, token, now):
    from telegram_bot import notify

    if not (_t(C.ENTRY_START) <= now.time() <= _t(C.ENTRY_END)):
        return

    # आजचे 1-मिनिट कॅन्डल
    candles = get_today_candles(token, C.INDEX_KEY, date)
    cs = parse_candles(candles)
    if len(cs) < 16:
        if now.time() >= _t("09:40") and store.get_state("mktclosed_" + date) != "1":
            store.set_state("mktclosed_" + date, "1")
            notify("ℹ️ कॅन्डल डेटा मिळत नाही — आज बाजार सुट्टी असावी. बॉट पहरा देत राहील.")
        return

    spot = get_ltp(C.INDEX_KEY, token)

    prev_close = None
    try:
        frm = (now - timedelta(days=10)).strftime("%Y-%m-%d")
        to = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_close = get_prev_close(token, C.INDEX_KEY, frm, to)
    except Exception:
        prev_close = None          # गॅप फिल्टर वगळा

    sig = analyze(cs, spot, now, prev_close)
    if not sig:
        return

    if "blocked" in sig:
        note = sig["blocked"][:40]
        if store.get_state("blockednote_" + date) != note:
            store.set_state("blockednote_" + date, note)
            notify("🚫 सिग्नल वगळला: " + sig["blocked"])
        return

    # एकाच 5-मिनिट कॅन्डलवर दोनदा एंट्री नको
    acted_key = "acted_" + date
    if store.get_state(acted_key) == sig["candle_ts"]:
        return
    store.set_state(acted_key, sig["candle_ts"])

    # ATM ऑप्शन निवडा
    try:
        opt = _pick_option(token, spot, sig["side"])
    except Exception as e:
        notify("⚠️ ऑप्शन निवड अयशस्वी: " + str(e)[:200])
        return
    if not opt:
        notify("⚠️ योग्य ATM ऑप्शन सापडला नाही — ही कॅन्डल वगळली")
        return

    mode = store.get_state("mode", "PAPER")
    sig2 = dict(sig)
    sig2["time"] = now.strftime("%Y-%m-%d %H:%M:%S")

    if mode == "LIVE":
        tr, err = _live_open(sig2, opt, token, date, now)
    else:
        tr, err = paper.open_trade(sig2, opt, date, mode)
    if err:
        notify("🚫 एंट्री रद्द: " + err)
        return

    emo = "🟢" if sig["side"] == "CE" else "🔴"
    notify(f"""{emo} ENTRY ({mode})
📊 {C.INDEX_LABEL} {opt['strike']:.0f} {sig['side']} (एक्सपायरी: {opt['expiry']})
💰 एंट्री: ₹{tr['entry']:.2f} × {tr['qty']} = ₹{tr['entry']*tr['qty']:,.0f}
🛑 स्टॉप लॉस: ₹{tr['sl']:.2f}
🎯 टार्गेट: ₹{tr['target']:.2f}
📌 OR: {sig['or_high']:.0f} / {sig['or_low']:.0f} | ब्रेकआउट: {sig['breakout']:.0f}
🕐 {now.strftime('%H:%M:%S')} IST""")


def _pick_option(token, spot, side):
    """ATM (सर्वात जवळचा स्ट्राइक) ऑप्शन निवडा; महाग पडल्यास शेजारचा बघा"""
    chain = get_option_chain(token, C.INDEX_KEY)
    if not chain:
        return None
    expiries = sorted({r.get("expiry_date") for r in chain if r.get("expiry_date")})
    if not expiries:
        return None
    near = expiries[0]                      # सर्वात जवळची एक्सपायरी
    rows = sorted([r for r in chain if r.get("expiry_date") == near],
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
            ltp = get_ltp(key, token)
        if not ltp or float(ltp) <= 0:
            continue
        ltp = float(ltp)
        if ltp * C.LOT_SIZE > _capital() * 0.90:
            continue                         # हा ऑप्शन महाग → पुढचा बघा
        return {"key": key, "strike": float(row.get("strike_price") or 0),
                "expiry": near, "ltp": ltp}
    return None


def _capital():
    try:
        return float(store.get_state("capital") or C.CAPITAL)
    except (TypeError, ValueError):
        return C.CAPITAL


# ------------------------------------------------------------------
# एग्झिट / निरीक्षण
# ------------------------------------------------------------------
def _monitor(pos, token, now):
    from telegram_bot import notify

    ltp = get_ltp(pos["option_key"], token)
    if ltp is None or ltp <= 0:
        return

    # ट्रेल: +25% झाल्यावर SL खर्चाच्या (breakeven) ठिकाणी आणा
    if ltp >= pos["entry"] * (1 + C.TRAIL_START_PCT / 100.0) and pos["sl"] < pos["entry"]:
        store.update_sl(pos["id"], pos["entry"])
        pos["sl"] = pos["entry"]
        notify(f"🔒 SL breakeven वर आणले — {C.INDEX_LABEL} {pos['strike']:.0f} {pos['side']} "
               f"(आता तोटा शक्य नाही)")

    reason = None
    if now.time() >= _t(C.SQUARE_OFF):
        reason = "वेळ एग्झिट (15:05)"
    elif ltp <= pos["sl"]:
        reason = "स्टॉप लॉस" if pos["sl"] < pos["entry"] else "ट्रेल SL 🔒"
    elif ltp >= pos["target"]:
        reason = "टार्गेट पोहोचला ✅"
    if not reason:
        return

    mode = pos["mode"]
    if mode == "LIVE":
        pnl, exitp = _live_close(pos, token, ltp, now, reason)
    else:
        pnl, exitp = paper.close_trade(pos["id"], ltp, reason,
                                       now.strftime("%Y-%m-%d %H:%M:%S"))

    halted = risk.register_exit(pos["date"], pnl)
    icon = "✅" if pnl >= 0 else "❌"
    msg = f"""{icon} EXIT ({mode}) — {reason}
📊 {C.INDEX_LABEL} {pos['strike']:.0f} {pos['side']}
💰 एंट्री ₹{pos['entry']:.2f} → एग्झिट ₹{exitp:.2f}
📈 P&L: ₹{pnl:,.0f}
📊 आजचा P&L: ₹{store.today_pnl(pos['date']):,.0f} | एकूण: ₹{store.total_pnl():,.0f}"""
    if halted:
        msg += ("\n🛑 दैनिक नुकसान मर्यादा (₹{:,.0f}) ओलांडली — "
                "आज पुढे कोणताही ट्रेड नाही.".format(-abs(C.MAX_DAILY_LOSS)))
    notify(msg)


# ------------------------------------------------------------------
# LIVE mode (फक्त ३ गेट उघडल्यावरच चालते)
# ------------------------------------------------------------------
def _force_close(pos, token, now):
    """KILL स्विच — पोझिशन तात्काळ बंद"""
    from telegram_bot import notify
    try:
        ltp = get_ltp(pos["option_key"], token)
    except Exception:
        ltp = None
    if ltp is None or ltp <= 0:
        return                                  # पुढील लूपमध्ये पुन्हा प्रयत्न
    if pos["mode"] == "LIVE":
        pnl, exitp = _live_close(pos, token, ltp, now, "KILL स्विच 🚨")
    else:
        pnl, exitp = paper.close_trade(pos["id"], ltp, "KILL स्विच 🚨",
                                       now.strftime("%Y-%m-%d %H:%M:%S"))
    notify(f"🚨 KILL: पोझिशन बंद केली — {pos['strike']:.0f} {pos['side']}\n"
           f"एग्झिट ₹{exitp:.2f} | P&L ₹{pnl:,.0f}\n"
           f"परत सुरू करण्यासाठी: /resume")


def _live_open(sig, opt, token, date, now):
    order_id = place_order(token, opt["key"], C.LOT_SIZE, "BUY")
    store.log_event(f"LIVE BUY {opt['key']} qty={C.LOT_SIZE} order={order_id}")
    entry = round(opt["ltp"] * (1 + C.SLIPPAGE), 2)
    sl = round(entry * (1 - C.SL_PCT / 100.0), 2)
    tg = round(entry * (1 + C.TARGET_PCT / 100.0), 2)
    tid = store.open_trade(date, "LIVE", sig["side"], opt["key"], opt["strike"],
                           opt["expiry"], C.LOT_SIZE, entry, sl, tg, sig.get("time", ""))
    return {"id": tid, "entry": entry, "sl": sl, "target": tg, "qty": C.LOT_SIZE}, ""


def _live_close(pos, token, ltp, now, reason):
    order_id = place_order(token, pos["option_key"], pos["qty"], "SELL")
    store.log_event(f"LIVE SELL {pos['option_key']} qty={pos['qty']} order={order_id}")
    exitp = round(ltp * (1 - C.SLIPPAGE), 2)
    pnl = round((exitp - pos["entry"]) * pos["qty"], 2)
    store.close_trade(pos["id"], exitp, pnl, reason,
                      now.strftime("%Y-%m-%d %H:%M:%S"))
    return pnl, exitp


# ------------------------------------------------------------------
# दैनिक अहवाल
# ------------------------------------------------------------------
def _send_summary(date):
    from telegram_bot import notify
    ts = store.trades_today(date)
    closed = [t for t in ts if t["status"] == "CLOSED"]
    open_t = [t for t in ts if t["status"] == "OPEN"]
    pnl = store.today_pnl(date)

    lines = [f"🌇 दैनिक अहवाल — {date}",
             f"मोड: {store.get_state('mode', 'PAPER')}",
             f"एकूण ट्रेड्स: {len(ts)} (पूर्ण: {len(closed)})",
             f"आजचा P&L: ₹{pnl:,.0f}",
             f"सुरुवातीपासून एकूण: ₹{store.total_pnl():,.0f}"]
    for t in closed:
        icon = "✅" if (t["pnl"] or 0) >= 0 else "❌"
        lines.append(f"{icon} {t['strike']:.0f} {t['side']}: ₹{t['pnl']:,.0f} ({t['reason']})")
    for t in open_t:
        lines.append(f"⏳ {t['strike']:.0f} {t['side']}: अजून उघडी आहे — तपासा /positions")
    lines.append("🙏 उद्या सकाळी नवीन /code पाठवायला विसरू नका!")
    notify("\n".join(lines))
