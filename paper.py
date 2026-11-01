"""
PAPER mode (कागदी ट्रेडिंग) — पैसे धोक्यात न टाकता वास्तविक किंमतींवर सराव.
• खरेदी: LTP + 0.05% स्लिपेज
• विक्री: LTP - 0.05% स्लिपेज
• सर्व खर्च (ब्रोकरेज ₹20×2, STT, NSE चार्ज, GST, स्टॅम्प...) वजा → निव्वळ P&L
• नफा-तोटा SQLite मध्ये नोंदवला जातो
"""

import charges
import store
from config import SL_PCT, TARGET_PCT, SLIPPAGE, LOT_SIZE, CAPITAL


def _capital():
    """Telegram वरून /setcapital ने बदललेले भांडवल (नसेल तर default)"""
    try:
        return float(store.get_state("capital") or CAPITAL)
    except (TypeError, ValueError):
        return CAPITAL


def round_trip_charges(entry, exitp, qty):
    """एका ट्रेडचा पूर्ण खर्च (बाय+सेल दोन्ही ऑर्डर, सर्व करांसह)"""
    return charges.option_charges(entry * qty, exitp * qty)["total"]


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
    tg = round(entry * (1 + TARGET_PCT / 100.0), 2)
    tid = store.open_trade(date, mode, sig["side"], opt["key"], opt["strike"],
                           opt["expiry"], qty, entry, sl, tg,
                           sig.get("time", ""))
    return {"id": tid, "entry": entry, "sl": sl, "target": tg, "qty": qty}, ""


def close_trade(tid, ltp, reason, now_str):
    """
    कागदी ट्रेड बंद करा → (निव्वळ pnl, exit_price, खर्च)
    निव्वळ P&L = (एग्झिट − एंट्री) × qty − सर्व खर्च (ब्रोकरेज/STT/GST/स्टॅम्प...)
    """
    t = store.get_trade(tid)
    if not t:
        return 0.0, 0.0, 0.0
    exitp = round(ltp * (1 - SLIPPAGE), 2)
    gross = (exitp - t["entry"]) * t["qty"]
    chg = round_trip_charges(t["entry"], exitp, t["qty"])
    pnl = round(gross - chg, 2)
    store.close_trade(tid, exitp, pnl, reason, now_str, chg)
    return pnl, exitp, chg
