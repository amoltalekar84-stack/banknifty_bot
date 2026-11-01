"""
PAPER mode (कागदी ट्रेडिंग) — पैसे धोक्यात न टाकता वास्तविक किंमतींवर सराव.
• खरेदी: LTP + 0.05% स्लिपेज
• विक्री: LTP - 0.05% स्लिपेज
• सर्व खर्च (ब्रोकरेज, STT, NSE चार्ज, GST, स्टॅम्प...) वजा → निव्वळ P&L
• TP-लॅडर: 1 बाय ऑर्डर + 3 वेगवेगळे सेल ऑर्डर (TP1/TP2/TP3) — प्रत्येकी
  वेगळे ₹20 ब्रोकरेज, म्हणजे हिशोब 100% वास्तववादी
• नफा-तोटा SQLite मध्ये नोंदवला जातो
"""

import charges
import store
from config import SLIPPAGE


def _capital(S):
    """Telegram वरून /setcapital (BN) / /setcapitalcu (CU) ने बदललेले भांडवल"""
    try:
        return float(store.get_state(S["capital_state"]) or S["capital"])
    except (TypeError, ValueError):
        return S["capital"]


def round_trip_charges(entry, exitp, qty, S=None):
    """एका ट्रेडचा पूर्ण खर्च (बाय+सेल दोन्ही ऑर्डर, सर्व करांसह)"""
    if S and S.get("mcx"):
        return charges.mcx_option_charges(entry * qty, exitp * qty)["total"]
    return charges.option_charges(entry * qty, exitp * qty)["total"]


def ladder_charges_estimate(entry, qty, S=None):
    """एंट्री-कार्डसाठी अंदाजे खर्च — ladder सिम्बॉल: 1 बाय + 3 सेल;
    Copper (ladder=False): 1 बाय + 1 सेल (TP2 वर पूर्ण बुकिंग)"""
    if S and not S.get("ladder"):
        tp2 = entry * (1 + S["tp2_pct"] / 100.0)
        chg = charges.mcx_option_charges_ladder(entry * qty, [(tp2, qty)])
        return chg["total"], chg["orders"]
    from config import TARGET_PCT, TP1_PCT, TP3_PCT
    tp1 = entry * (1 + TP1_PCT / 100.0)
    tp2 = entry * (1 + TARGET_PCT / 100.0)
    tp3 = entry * (1 + TP3_PCT / 100.0)
    q3 = max(int(qty) // 3, 1)
    q1, q2 = q3, q3
    q3r = int(qty) - q1 - q2
    chg = charges.option_charges_ladder(
        entry * qty, [(tp1, q1), (tp2, q2), (tp3, max(q3r, 0))])
    return chg["total"], chg["orders"]


def thirds(qty):
    """एकूण qty 3 भागांत (उदा. 30 → 10, 10, 10)"""
    qty = max(int(qty), 1)
    q3 = max(qty // 3, 1)
    q1, q2 = q3, q3
    q3r = qty - q1 - q2
    if q3r <= 0:                      # खूप लहान qty — शेवटचा भाग किमान 1
        q3r = 1
    return q1, q2, q3r


def tp_prices(entry, S=None):
    """TP1/TP2/TP3 किंमती (सिम्बॉल-अनुसार प्रतिशत — BN व CU सारखेच 20/40/60)"""
    tp1p = S["tp1_pct"] if S else 20.0
    tp2p = S["tp2_pct"] if S else 40.0
    tp3p = S["tp3_pct"] if S else 60.0
    return (round(entry * (1 + tp1p / 100.0), 2),
            round(entry * (1 + tp2p / 100.0), 2),
            round(entry * (1 + tp3p / 100.0), 2))


def open_trade(sig, opt, date, mode="PAPER", S=None):
    """
    नवीन कागदी ट्रेड उघडा.
    sig = {side, or_high, or_low, breakout, time...},
    opt = {key, strike, expiry, ltp, lot?}
    S = सिम्बॉल config (None = BANKNIFTY)
    qty = ऑप्शनचा खरा lot (opt["lot"]) — MCX साठी फाईलमधून; नसेल तर S["lot"]
    यशास → (trade_dict, ""), अपयशास → (None, कारण)
    """
    S = S or _BN()
    qty = int(opt.get("lot") or S["lot"])
    entry = round(opt["ltp"] * (1 + SLIPPAGE), 2)
    cost = entry * qty
    if cost > _capital(S) * 0.90:
        return None, (f"भांडवल अपुरे ({S['label']}): 1 lot साठी ₹{cost:,.0f} लागतील, "
                      f"उपलब्ध ₹{_capital(S):,.0f} (90% वापरले जातात)")
    sl = round(entry * (1 - S["sl_pct"] / 100.0), 2)
    tp1, tp2, tp3 = tp_prices(entry, S)
    tid = store.open_trade(date, mode, sig["side"], opt["key"], opt["strike"],
                           opt["expiry"], qty, entry, sl, tp2,
                           sig.get("time", ""), S["key"])
    store.set_legs(tid, [])
    return {"id": tid, "entry": entry, "sl": sl, "target": tp2,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "qty": qty}, ""


def _BN():
    """जुन्या कॉलसाठी डीफॉल्ट सिम्बॉल config"""
    from config import BANKNIFTY
    return BANKNIFTY


def book_partial(tid, ltp, label, now_str):
    """
    पुढचा 1/3 भाग वर्तमान किंमतीवर बुक करा (PAPER).
    → {"price", "qty", "gross", "booked", "remaining", "legs"} किंवा None
    """
    t = store.get_trade(tid)
    if not t:
        return None
    legs = store.get_legs(tid)
    booked = sum(int(l.get("qty") or 0) for l in legs)
    rem = int(t["qty"]) - booked
    if rem <= 0:
        return None
    q1, q2, q3r = thirds(t["qty"])
    leg_q = q1 if booked < q1 else (q2 if booked < q1 + q2 else rem)
    leg_q = min(leg_q, rem)
    price = round(ltp * (1 - SLIPPAGE), 2)
    legs.append({"label": label, "price": price, "qty": leg_q,
                 "ts": now_str})
    store.set_legs(tid, legs)
    gross = round((price - t["entry"]) * leg_q, 2)
    return {"price": price, "qty": leg_q, "gross": gross,
            "booked": booked + leg_q, "remaining": rem - leg_q,
            "legs": legs}


def record_leg(tid, price, qty, label, now_str):
    """LIVE मोड: अंमलात आलेला सेल ऑर्डर नोंदवा (ऑर्डर engine ने आधीच पाठवलेला असतो)"""
    legs = store.get_legs(tid)
    legs.append({"label": label, "price": round(float(price), 2),
                 "qty": int(qty), "ts": now_str})
    store.set_legs(tid, legs)
    return legs


def close_trade(tid, ltp, reason, now_str, final_price=None, S=None):
    """
    ट्रेड पूर्णपणे बंद करा — शिल्लक भाग वर्तमान किंमतीवर + आधीच्या बुकिंग
    भागांसह एकत्रित हिशोब (सर्व खर्च: 1 बाय + n सेल ऑर्डर).
    → (निव्वळ pnl, सरासरी exit, एकूण खर्च, legs यादी)
    """
    t = store.get_trade(tid)
    if not t:
        return 0.0, 0.0, 0.0, []
    legs = store.get_legs(tid)
    booked = sum(int(l.get("qty") or 0) for l in legs)
    rem = int(t["qty"]) - booked
    if final_price is None:
        final_price = round(ltp * (1 - SLIPPAGE), 2)
    final_price = round(float(final_price), 2)
    if rem > 0:
        legs.append({"label": reason, "price": final_price, "qty": rem,
                     "ts": now_str})
    qty = max(int(t["qty"]), 1)
    gross = round(sum((float(l["price"]) - t["entry"]) * int(l["qty"])
                      for l in legs), 2)
    if S and S.get("mcx"):
        chg = charges.mcx_option_charges_ladder(
            t["entry"] * qty,
            [(float(l["price"]), int(l["qty"])) for l in legs])
    else:
        chg = charges.option_charges_ladder(
            t["entry"] * qty,
            [(float(l["price"]), int(l["qty"])) for l in legs])
    chg_total = chg["total"]
    pnl = round(gross - chg_total, 2)
    sell_value = sum(float(l["price"]) * int(l["qty"]) for l in legs)
    exit_avg = round(sell_value / qty, 2) if sell_value else final_price
    full_reason = " + ".join(str(l.get("label") or "?") for l in legs)
    store.close_trade(tid, exit_avg, pnl, full_reason[:200], now_str, chg_total)
    # संपूर्ण बुकिंग इतिहास (TP भाग + शेवटचा एग्झिट भाग) कायम ठेवा —
    # /api/eval दैनिक मूल्यांकन आणि भविष्यातील विश्लेषणासाठी
    store.set_legs(tid, legs)
    return pnl, exit_avg, chg_total, legs
