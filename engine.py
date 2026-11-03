"""
मुख्य ट्रेडिंग इंजिन — स्वयंचलित लूप (MULTI-SYMBOL: BANKNIFTY + 5 MCX).

प्रवाह (प्रत्येक POLL_SEC सेकंदांनी, सिम्बॉल-प्रमाणे):
  ① बाजार वेळ तपासा (BN: सोम–शुक्र 9:15–15:30 | MCX: सोम–शुक्र 9:00–23:30)
  ② टोकन आहे का? → नाही तर Telegram वर पाठवा
  ③ पोझिशन उघडी असल्यास तिचे निरीक्षण करा (SL/टार्गेट/ट्रेल/वेळ)
  ④ उघडी नसल्यास ORB सिग्नल तपासा → ATM ऑप्शन निवडा → एंट्री
  ⑤ BN 15:05 ला / MCX 23:05 ला जबरदस्ती स्क्वेअर-ऑफ
  ⑥ दैनिक अहवाल: BN 15:20 | CU 23:10 | GOLD 23:12 | SILVER 23:14 |
     CRUDE 23:16 | NATGAS 23:18

BANKNIFTY: जुनेच नियम — TP लॅडर 10+10+10 (लॉट 30), ₹50,000 भांडवल.
MCX (Copper/Gold/Silver/Crude/NatGas): प्रत्येकी स्वतंत्र भांडवल, 1 लॉट →
  +20% → SL breakeven लॉक | +40% → पूर्ण बुकिंग | SL −20% | 23:05 स्क्वेअर-ऑफ.
  कॉन्ट्रॅक्ट रोज Upstox instruments फाईलमधून (फक्त main series) आपोआप;
  ऑप्शनचा खरा lot त्याच फाईलमधून (GOLD: 1 kg = 100 × 10g config ओव्हरराईड).
"""

import os
import threading
import time
import traceback
from datetime import datetime as dtm, time as dtime, timedelta

import cards
import config as C
import instruments
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
    threading.Thread(target=_watchdog, daemon=True,
                     name="watchdog").start()
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
    syms = " + ".join(s["label"] for s in C.active_symbols())
    times = " | ".join(f"{s['market_open']}–{s['market_close']} ({s['short']})"
                        for s in C.active_symbols())
    try:
        notify(f"🤖 बॉट सुरू झाला — मोड: {store.get_state('mode', 'PAPER')}\n"
               f"सिम्बॉल्स: {syms}\n"
               f"मोड: ORB | SL: -{C.SL_PCT:.0f}% | TP लॅडर: +{C.TP1_PCT:.0f}% / "
               f"+{C.TARGET_PCT:.0f}% / +{C.TP3_PCT:.0f}% (भागाकार बुकिंग)\n"
               f"बाजार वेळ: {times} IST")
    except Exception:
        pass                      # सुरुवातीचा अलर्ट नाको — इंजिन तरीच चालणे आवश्यक
    while True:
        try:
            # हृदयस्पंदन — प्रत्येक फेरीत लिहा (watchdog + /status यांसाठी)
            store.set_state("engine_beat",
                            ist_now().strftime("%Y-%m-%d %H:%M:%S"))
            _tick()
        except UpstoxError as e:
            if "TOKEN_INVALID" in str(e):
                store.set_state("upstox_token", "")
                store.log_event("🚪 टोकन संपला/अवैध (TOKEN_INVALID) — सर्व सिम्बॉल्स थांबले; नवीन /code हवा")
                notify("⚠️ टोकन अवैध/संपले!\nनवीन टोकन पाठवा: /code XXXXXX किंवा /token XXXXXX")
            else:
                store.log_event("engine: " + str(e))
                notify("⚠️ API त्रुटी: " + str(e)[:200])
        except Exception as e:                      # कधीही लूप मरू नये
            store.log_event("engine err: " + repr(e) + traceback.format_exc()[:300])
            try:
                notify("⚠️ इंजिन त्रुटी: " + repr(e)[:200])
            except Exception:
                pass
        time.sleep(C.POLL_SEC)


def _watchdog():
    """पहरेदार थ्रेड: इंजिन-थ्रेड अटकला/गप्प झाला तर प्रक्रिया नव्याने सुरू करा.
    systemd Restart=always (RestartSec=10) → ~10-15 सेकंदांत ताजा इंजिन.
    चुकीचा शिक्का टाळण्यासाठी मुभा: सुरुवातीला 3 मिनिटे; सीमा 15 मिनिटे
    (Upstox अर्ध-अप असताना सर्वात हळू टिक ≈ 9-10 मिनिटे)."""
    t0 = time.monotonic()
    while True:
        time.sleep(60)
        if time.monotonic() - t0 < 180:
            continue                      # सुरुवातीची मुभा
        try:
            beat = store.get_state("engine_beat") or ""
            bt = dtm.strptime(beat, "%Y-%m-%d %H:%M:%S") if beat else None
            age = 99999.0
            if bt:
                now = ist_now()
                if bt.tzinfo is None:
                    bt = bt.replace(tzinfo=now.tzinfo)
                age = (now - bt).total_seconds()
        except Exception:
            age = 99999.0
        if age > 900:                     # 15 मिनिटांत एकही फेरी नाही → अडकला
            try:
                from telegram_bot import notify
                notify("🚨 इंजिन अडकला/थांबला होता — आपोआप रीस्टार्ट होत आहे…")
            except Exception:
                pass
            try:
                store.log_event(f"🚨 watchdog: engine_beat {age:.0f}s जुना "
                                f"— process restart")
            except Exception:
                pass
            os._exit(1)                   # systemd लगेच पुन्हा सुरू करेल


def _tick():
    now = ist_now()
    date = now.strftime("%Y-%m-%d")

    if now.weekday() >= 5:          # शनिवार/रविवारी
        return

    # नवीन दिवस → स्वागत संदेश
    if store.get_state("day_init") != date:
        store.set_state("day_init", date)
        from telegram_bot import notify
        notify(f"🌅 नवीन दिवस: {date}\n"
               f"मोड: {store.get_state('mode', 'PAPER')} | "
               f"टोकन: {'✅' if store.get_state('upstox_token') else '❌ नाही (/code पाठवा)'}")

    token = store.get_state("upstox_token")
    if not token:
        if now.time() >= _t("08:55") and store.get_state("tokwarn_" + date) != "1":
            store.set_state("tokwarn_" + date, "1")
            store.log_event("⚠️ बाजार-वेळेत टोकन नाही — सर्व सिम्बॉल्स तटस्थ (उशीर /code?)")
            from telegram_bot import notify
            notify("⚠️ आजचा Upstox टोकन अजून आला नाही!\n"
                   "सकाळी लॉगिन करून /code XXXXXX पाठवा — नाहीतर आज "
                   "कोणताही सिम्बॉल ट्रेड होणार नाही.")
        return

    # प्रत्येक सिम्बॉल आपल्या वेळेत, आपल्या नियमांनी चालतो
    for S in C.active_symbols():
        try:
            _tick_symbol(S, token, now)
        except UpstoxError as e:
            if "TOKEN_INVALID" in str(e):
                raise
            store.log_event(f"engine[{S['key']}]: " + str(e))


def _tick_symbol(S, token, now):
    from telegram_bot import notify
    date = now.strftime("%Y-%m-%d")
    skey = S["key"]

    # दैनिक अहवाल (BN 15:20 / CU 23:10) — बाजार-वेळ तपासणीच्या आधी
    if now.time() >= _t(S["summary_at"]) and \
            store.get_state("summary_" + date + "_" + skey) != "1":
        store.set_state("summary_" + date + "_" + skey, "1")
        _send_summary(S, date)

    if not (_t(S["market_open"]) <= now.time() <= _t(S["market_close"])):
        return

    pos = store.get_open_trade(date, skey)
    if store.get_state("killed") == "1":
        if pos:
            _force_close(S, pos, token, now)     # KILL → तात्काळ बंद
        return
    if pos:
        _monitor(S, pos, token, now)
        return

    ok, _why = risk.can_enter(date, S)
    if not ok:
        return
    _maybe_enter(S, date, token, now)


# ------------------------------------------------------------------
# एंट्री
# ------------------------------------------------------------------
def _data_key(S, now):
    """सिम्बॉलचा डेटा-स्रोत: BN/NIFTY/SENSEX/FINNIFTY = निर्देशांक; MCX = फ्यूचर्स."""
    if not S["mcx"]:
        return S.get("index_key") or C.INDEX_KEY, None
    snap = instruments.mcx_snapshot(S["commodity"],
                                    ts_pattern=S.get("ts_pattern"))
    if not snap:
        return None, None
    return snap["fut"]["key"], snap


def _maybe_enter(S, date, token, now):
    from telegram_bot import notify
    skey = S["key"]
    notekey = "mktclosed_" + date + "_" + skey

    # एंट्री-विंडो संपल्यावर एकदाच नोंद — आज काही झाले नाही तरी जर्नल/EOD सांगतील
    if now.time() > _t(S["entry_end"]) and \
            store.get_state("orbwin_" + date + "_" + skey) != "1":
        store.set_state("orbwin_" + date + "_" + skey, "1")
        n_t = len(store.trades_today(date, skey))
        store.log_event(
            f"{S['label']}: ORB विंडो ({S['entry_start']}–{S['entry_end']}) संपली — "
            + (f"आज {n_t} एंट्री झाल्या." if n_t else
               "आज एकही एंट्री नाही — सिग्नल भेटला नाही किंवा टोकन/डेटा नव्हता."))

    if not (_t(S["entry_start"]) <= now.time() <= _t(S["entry_end"])):
        return

    dkey, snap = _data_key(S, now)
    if not dkey:
        if store.get_state("instrnote_" + date + "_" + skey) != "1":
            store.set_state("instrnote_" + date + "_" + skey, "1")
            store.log_event(f"{S['label']}: कॉन्ट्रॅक्ट डेटा आज मिळाला नाही — आज वगळला")
            notify(f"⚠️ {S['label']} कॉन्ट्रॅक्ट डेटा आज मिळाला नाही — "
                   f"आज {S['short']} वगळला (इतर सिम्बॉल्स सामान्य चालू राहतील).")
        return

    # आजचे 1-मिनिट कॅन्डल
    candles = get_today_candles(token, dkey, date)
    cs = parse_candles(candles)
    if len(cs) < S["min_candles"]:
        if now.time() >= _t(S["entry_start"]) and \
                store.get_state(notekey) != "1" and \
                now.time() >= _t("10:00"):
            store.set_state(notekey, "1")
            store.log_event(f"{S['label']}: कॅन्डल डेटा मिळत नाही "
                            f"({len(cs)}/{S['min_candles']}) — आज वगळला")
            notify(f"ℹ️ {S['label']}: कॅन्डल डेटा मिळत नाही — "
                   "आज बाजार सुट्टी असावी. बॉट पहरा देत राहील.")
        return

    spot = get_ltp(dkey, token)

    prev_close = None
    try:
        frm = (now - timedelta(days=10)).strftime("%Y-%m-%d")
        to = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_close = get_prev_close(token, dkey, frm, to)
    except Exception:
        prev_close = None          # गॅप फिल्टर वगळा

    sig = analyze(cs, spot, now, prev_close,
                  orb_start=S["orb_start"], orb_end=S["orb_end"])
    if not sig:
        return

    if "blocked" in sig:
        note = sig["blocked"][:40]
        if store.get_state("blockednote_" + date + "_" + skey) != note:
            store.set_state("blockednote_" + date + "_" + skey, note)
            notify(f"🚫 {S['label']} सिग्नल वगळला: " + sig["blocked"])
        return

    # एकाच 5-मिनिट कॅन्डलवर दोनदा एंट्री नको
    acted_key = "acted_" + date + "_" + skey
    if store.get_state(acted_key) == sig["candle_ts"]:
        return
    store.set_state(acted_key, sig["candle_ts"])

    # ATM ऑप्शन निवडा
    try:
        if S["mcx"]:
            opt = _pick_option_file(S, snap, token, spot, sig["side"])
        else:
            opt = _pick_option(S, token, spot, sig["side"])
    except Exception as e:
        notify(f"⚠️ {S['label']} ऑप्शन निवड अयशस्वी: " + str(e)[:200])
        return
    if not opt:
        notify(f"⚠️ {S['label']}: योग्य ATM ऑप्शन सापडला नाही — ही कॅन्डल वगळली")
        return

    mode = store.get_state("mode", "PAPER")
    sig2 = dict(sig)
    sig2["time"] = now.strftime("%Y-%m-%d %H:%M:%S")

    if mode == "LIVE":
        tr, err = _live_open(sig2, opt, token, date, now, S)
    else:
        tr, err = paper.open_trade(sig2, opt, date, mode, S)
    if err:
        notify("🚫 एंट्री रद्द: " + err)
        return

    tp1, tp2, tp3 = paper.tp_prices(tr["entry"], S)
    lots = max(int(tr["qty"]) // max(S["lot"], 1), 1)
    est_chg, est_orders = paper.ladder_charges_estimate(tr["entry"], tr["qty"], S)
    card = cards.entry_card(
        mode, sig["side"], opt["strike"], opt["expiry"], tr["entry"],
        tr["qty"], lots, spot, sig["or_high"], sig["or_low"],
        sig["breakout"], tr["sl"], tp1, tp2, tp3, est_chg, est_orders,
        now, S["label"], ladder=S["ladder"])
    notify(card, html=True)


def _pick_option(S, token, spot, side):
    """NSE/BSE इंडेक्स: ATM (सर्वात जवळचा स्ट्राइक) ऑप्शन निवडा;
    महाग पडल्यास शेजारचा बघा. S = सिम्बॉल config (आपला index_key + lot + भांडवल)"""
    chain = get_option_chain(token, S["index_key"])
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
        if ltp * S["lot"] > paper._capital(S) * 0.90:
            continue                         # हा ऑप्शन महाग → पुढचा बघा
        return {"key": key, "strike": float(row.get("strike_price") or 0),
                "expiry": near, "ltp": ltp}
    return None


def _pick_option_file(S, snap, token, spot, side):
    """MCX: instruments फाईलमधून ATM स्ट्राइक + खरा LTP.
    trade qty = ऑप्शनचा खरा lot (फाईलमधून); GOLD साठी config ओव्हरराईड."""
    opt_lot = S.get("trade_lot") or snap.get("opt_lot") or S["lot"]
    for k in instruments.atm_strikes(snap, spot, 4):
        node = snap["strikes"].get(str(k)) or snap["strikes"].get(int(k)) \
            or snap["strikes"].get(k)
        if not node:
            continue
        key = node.get(side)
        if not key:
            continue
        ltp = get_ltp(key, token)
        if not ltp or float(ltp) <= 0:
            continue
        ltp = float(ltp)
        if ltp * opt_lot > paper._capital(S) * 0.90:
            continue                         # हा ऑप्शन महाग → पुढचा बघा
        return {"key": key, "strike": float(k),
                "expiry": snap["opt_expiry"], "ltp": ltp, "lot": int(opt_lot)}
    return None


def _capital(S):
    try:
        return float(store.get_state(S["capital_state"]) or S["capital"])
    except (TypeError, ValueError):
        return S["capital"]


def _monitor(S, pos, token, now):
    from telegram_bot import notify

    ltp = get_ltp(pos["option_key"], token)
    if ltp is None or ltp <= 0:
        return

    tp1, tp2, tp3 = paper.tp_prices(pos["entry"], S)
    legs = store.get_legs(pos["id"])
    booked = sum(int(l.get("qty") or 0) for l in legs)
    rem = int(pos["qty"]) - booked
    q1, q2, _q3 = paper.thirds(pos["qty"])

    # ---------- प्रथम सुरक्षा: स्क्वेअर-ऑफ व SL ----------
    if now.time() >= _t(S["square_off"]):
        _finish(S, pos, token, ltp, now, S["square_off_label"])
        return
    if ltp <= pos["sl"]:
        reason = "स्टॉप लॉस" if pos["sl"] < pos["entry"] else "ट्रेल SL 🔒"
        _finish(S, pos, token, ltp, now, reason)
        return

    if S["ladder"]:
        # ---------- BANKNIFTY: TP लॅडर — भागाकार बुकिंग (लॉट 30 → 10+10+10) ----------
        if booked < q1:
            if ltp >= tp1:                        # ① TP1: 1/3 बुक + breakeven लॉक
                info = _book_leg(pos, token, ltp, now, "TP1")
                if info:
                    if pos["sl"] < pos["entry"]:
                        store.update_sl(pos["id"], pos["entry"])
                        pos["sl"] = pos["entry"]
                    notify(cards.tp_card(pos["mode"], pos["side"], pos["strike"],
                                         1, info["price"], info["qty"],
                                         info["gross"], info["remaining"],
                                         pos["entry"], pos["entry"],
                                         now.strftime("%H:%M:%S"),
                                         S["label"]), html=True)
        elif booked < q1 + q2:
            if ltp >= tp2:                        # ② TP2: दुसरा 1/3 + SL +10% वर
                info = _book_leg(pos, token, ltp, now, "TP2")
                if info:
                    new_sl = round(pos["entry"] * 1.10, 2)
                    store.update_sl(pos["id"], new_sl)
                    pos["sl"] = new_sl
                    notify(cards.tp_card(pos["mode"], pos["side"], pos["strike"],
                                         2, info["price"], info["qty"],
                                         info["gross"], info["remaining"],
                                         new_sl, pos["entry"],
                                         now.strftime("%H:%M:%S"),
                                         S["label"]), html=True)
        else:
            if ltp >= tp3:                        # ③ TP3: शेवटचा भाग → ट्रेड पूर्ण
                info = _book_leg(pos, token, ltp, now, "TP3")
                if info:
                    _finish(S, pos, token, ltp, now, "TP3 पूर्ण ✅")
    else:
        # ---------- COPPER: 1 लॉट — भागाकार बुकिंग शक्य नाही ----------
        #  +20% → SL breakeven लॉक | +40% → संपूर्ण बुकिंग
        if ltp >= tp2:
            _finish(S, pos, token, ltp, now, "TP2 पूर्ण ✅ (+40%)")
            return
        if ltp >= tp1 and pos["sl"] < pos["entry"]:
            new_sl = pos["entry"]
            store.update_sl(pos["id"], new_sl)
            pos["sl"] = new_sl
            notify(cards.lock_card(pos["mode"], pos["side"], pos["strike"],
                                   new_sl, pos["entry"],
                                   now.strftime("%H:%M:%S"),
                                   S["label"]), html=True)


def _book_leg(pos, token, ltp, now, label):
    """पुढचा 1/3 भाग वर्तमान किंमतीवर बुक करा (PAPER/LIVE) → info dict"""
    from telegram_bot import notify
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    if pos["mode"] == "LIVE":
        legs = store.get_legs(pos["id"])
        booked = sum(int(l.get("qty") or 0) for l in legs)
        q1, q2, _q3 = paper.thirds(pos["qty"])
        leg_q = q1 if booked < q1 else (q2 if booked < q1 + q2
                                        else int(pos["qty"]) - booked)
        leg_q = min(leg_q, int(pos["qty"]) - booked)
        if leg_q <= 0:
            return None
        order_id = place_order(token, pos["option_key"], leg_q, "SELL")
        store.log_event(f"LIVE SELL(leg) {pos['option_key']} qty={leg_q} "
                        f"order={order_id}")
        price = round(ltp * (1 - C.SLIPPAGE), 2)
        legs = paper.record_leg(pos["id"], price, leg_q, label, now_str)
        booked2 = sum(int(l.get("qty") or 0) for l in legs)
        return {"price": price, "qty": leg_q,
                "gross": round((price - pos["entry"]) * leg_q, 2),
                "remaining": int(pos["qty"]) - booked2, "legs": legs}
    try:
        return paper.book_partial(pos["id"], ltp, label, now_str)
    except Exception as e:
        store.log_event("book_leg err: " + repr(e))
        notify("⚠️ TP बुकिंग त्रुटी: " + repr(e)[:150])
        return None


def _finish(S, pos, token, ltp, now, reason):
    """ट्रेड पूर्ण बंद (शिल्लक भाग + आधीचे भाग एकत्र) → एग्झिट रसीद कार्ड"""
    from telegram_bot import notify
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    if pos["mode"] == "LIVE":
        legs0 = store.get_legs(pos["id"])
        booked = sum(int(l.get("qty") or 0) for l in legs0)
        rem = int(pos["qty"]) - booked
        if rem > 0:
            order_id = place_order(token, pos["option_key"], rem, "SELL")
            store.log_event(f"LIVE SELL {pos['option_key']} qty={rem} "
                            f"order={order_id}")
        exitp = round(ltp * (1 - C.SLIPPAGE), 2)
        pnl, exit_avg, chg, legs = paper.close_trade(
            pos["id"], ltp, reason, now_str, final_price=exitp, S=S)
    else:
        pnl, exit_avg, chg, legs = paper.close_trade(pos["id"], ltp, reason,
                                                     now_str, S=S)
    halted = risk.register_exit(pos["date"], pnl, S)
    full_reason = (" + ".join(str(l.get("label") or "") for l in legs)
                   or reason)
    in_ts = (pos["opened"] or "")[-8:-3] or "--:--"
    card = cards.exit_card(pos["mode"], pos["side"], pos["strike"],
                           full_reason, pos["entry"], exit_avg, chg, pnl,
                           legs, store.today_pnl(pos["date"], S["key"]),
                           store.total_pnl(), halted, S["max_daily_loss"],
                           in_ts, now.strftime("%H:%M"), S["label"])
    notify(card, html=True)
    return pnl


def _force_close(S, pos, token, now):
    """KILL स्विच — पोझिशन (शिल्लक भाग) तात्काळ बंद"""
    from telegram_bot import notify
    try:
        ltp = get_ltp(pos["option_key"], token)
    except Exception:
        ltp = None
    if ltp is None or ltp <= 0:
        return                                  # पुढील लूपमध्ये पुन्हा प्रयत्न
    _finish(S, pos, token, ltp, now, "KILL स्विच 🚨")
    notify(f"🚨 KILL: {S['label']} पोझिशन बंद केली — परत सुरू करण्यासाठी: /resume")


def _live_open(sig, opt, token, date, now, S=None):
    S = S or C.BANKNIFTY
    order_id = place_order(token, opt["key"], S["lot"], "BUY")
    store.log_event(f"LIVE BUY {opt['key']} qty={S['lot']} order={order_id}")
    entry = round(opt["ltp"] * (1 + C.SLIPPAGE), 2)
    sl = round(entry * (1 - S["sl_pct"] / 100.0), 2)
    tg = round(entry * (1 + S["tp2_pct"] / 100.0), 2)
    tid = store.open_trade(date, "LIVE", sig["side"], opt["key"], opt["strike"],
                           opt["expiry"], S["lot"], entry, sl, tg,
                           sig.get("time", ""), S["key"])
    store.set_legs(tid, [])
    return {"id": tid, "entry": entry, "sl": sl, "target": tg,
            "qty": S["lot"]}, ""


# ------------------------------------------------------------------
# दैनिक अहवाल (प्रति सिम्बॉल)
# ------------------------------------------------------------------
def _send_summary(S, date):
    from telegram_bot import notify
    ts = store.trades_today(date, S["key"])
    closed = [t for t in ts if t["status"] == "CLOSED"]
    open_t = [t for t in ts if t["status"] == "OPEN"]
    pnl = store.today_pnl(date, S["key"])

    lines = [f"🌇 दैनिक अहवाल — {S['label']} — {date}",
             f"मोड: {store.get_state('mode', 'PAPER')}",
             f"एकूण ट्रेड्स: {len(ts)} (पूर्ण: {len(closed)})",
             f"आजचा निव्वल P&L: ₹{pnl:,.0f} "
             f"(खर्च ₹{store.today_charges(date, S['key']):,.0f} वजा)",
             f"{S['label']} सुरुवातीपासून निव्वल: "
             f"₹{store.total_pnl_symbol(S['key']):,.0f} | "
             f"एकूण खर्च: ₹{store.total_charges():,.0f}"]
    for t in closed:
        icon = "✅" if (t["pnl"] or 0) >= 0 else "❌"
        lines.append(f"{icon} {t['strike']:.0f} {t['side']}: ₹{t['pnl']:,.0f} ({t['reason']})")
    for t in open_t:
        lines.append(f"⏳ {t['strike']:.0f} {t['side']}: अजून उघडी आहे — तपासा /positions")
    if S["key"] == "BANKNIFTY":
        lines.append("🙏 उद्या सकाळी नवीन /code पाठवायला विसरू नका!")
    notify("\n".join(lines))
