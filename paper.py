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
from config import (CAPITAL, LOT_SIZE, SL_PCT, SLIPPAGE, TARGET_PCT, TP1_PCT,
                    TP3_PCT)


def _capital():
    """Telegram वरून /setcapital ने बदललेले भांडवल (नसेल तर default)"""
    try:
        return float(store.get_state("capital") or CAPITAL)
    except (TypeError, ValueError):
        return CAPITAL


def round_trip_charges(entry, exitp, qty):
    """एका ट्रेडचा पूर्ण खर्च (बाय+सेल दोन्ही ऑर्डर, सर्व करांसह)"""
    return charges.option_charges(entry * qty, exitp * qty)["total"]


def ladder_charges_estimate(entry, qty):
    """एंट्री-कार्डसाठी अंदाजे खर्च: 1 बाय + 3 सेल (TP1/TP2/TP3 वर)"""
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


def tp_prices(entry):
    """TP1/TP2/TP3 किंमती"""
    return (round(entry * (1 + TP1_PCT / 100.0), 2),
            round(entry * (1 + TARGET_PCT / 100.0), 2),
            round(entry * (1 + TP3_PCT / 100.0), 2))


def open_trade(sig, opt, date, mode="PAPER"):
    """
    नवीन कागदी ट्रेड उघडा.
    sig = {side, or_high, or_low, breakout, time...}, opt = {key, strike, expiry, ltp}
    यशास → (trade_dict, ""), अपयशास → (None, कारण)
    """
    qty = LOT_SIZE
    entry = round(opt["ltp"] * (1 + SLIPPAGE), 2)
    cost = entry * qty
    if cost > _capital() * 0.90:
        return None, (f"भांडवल अपुरे: 1 lot साठी ₹{cost:,.0f} लागतील, "
                      f"उपलब्ध ₹{_capital():,.0f} (90% वापरले जातात)")
    sl = round(entry * (1 - SL_PCT / 100.0), 2)
    tp1, tp2, tp3 = tp_prices(entry)
    tid = store.open_trade(date, mode, sig["side"], opt["key"], opt["strike"],
                           opt["expiry"], qty, entry, sl, tp2,
                           sig.get("time", ""))
    store.set_legs(tid, [])
    return {"id": tid, "entry": entry, "sl": sl, "target": tp2,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "qty": qty}, ""


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


def close_trade(tid, ltp, reason, now_str, final_price=None):
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
