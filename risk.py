"""
रिस्क मॅनेजर — बॉटचे सुरक्षा कवच:
• दिवसाला कमाल ट्रेड मर्यादा (सिम्बॉल-प्रमाणे)
• दैनिक नुकसान मर्यादा (BANKNIFTY ₹2,500 / COPPER ₹10,000 = 5%) → त्या दिवशी पुढे ट्रेड नाही
• KILL स्विच व पॉज तपासणी (ग्लोबल — दोन्ही सिम्बॉल्सवर)
"""

import store


def can_enter(date, S):
    """नवीन एंट्री करता येईल का? (S = सिम्बॉल config) → (चालू, कारण)"""
    if store.get_state("killed") == "1":
        return False, "KILL स्विच चालू आहे (परत सुरू करण्यासाठी /resume)"
    if store.get_state("paused") == "1":
        return False, "बॉट पॉजमध्ये आहे (/resume)"
    if store.get_state("halt_" + date + "_" + S["key"]) == "1":
        return False, f"आजची नुकसान मर्यादा संपली ({S['label']})"
    closed = store.closed_trades_today(date, S["key"])
    if len(closed) >= S["max_trades"]:
        return False, "आजची ट्रेड मर्यादा संपली"
    return True, ""


def register_exit(date, pnl, S):
    """एग्झिट नोंदवा; दैनिक मर्यादा ओलांडल्यास त्या दिवसासाठी हॉल्ट करा"""
    day = store.today_pnl(date, S["key"])
    if day <= -abs(S["max_daily_loss"]):
        store.set_state("halt_" + date + "_" + S["key"], "1")
        return True
    return False
