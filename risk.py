"""
रिस्क मॅनेजर — बॉटचे सुरक्षा कवच:
• दिवसाला कमाल ट्रेड मर्यादा
• दैनिक नुकसान मर्यादा (₹2,500 = 5%) → त्या दिवशी पुढे ट्रेड नाही
• KILL स्विच व पॉज तपासणी
"""

import store
from config import MAX_DAILY_LOSS, MAX_TRADES_PER_DAY


def can_enter(date):
    """नवीन एंट्री करता येईल का? → (चालू, कारण)"""
    if store.get_state("killed") == "1":
        return False, "KILL स्विच चालू आहे (परत सुरू करण्यासाठी /resume)"
    if store.get_state("paused") == "1":
        return False, "बॉट पॉजमध्ये आहे (/resume)"
    if store.get_state("halt_" + date) == "1":
        return False, "आजची नुकसान मर्यादा संपली"
    closed = store.closed_trades_today(date)
    if len(closed) >= MAX_TRADES_PER_DAY:
        return False, "आजची ट्रेड मर्यादा संपली"
    return True, ""


def register_exit(date, pnl):
    """एग्झिट नोंदवा; दैनिक मर्यादा ओलांडल्यास त्या दिवसासाठी हॉल्ट करा"""
    day = store.today_pnl(date)
    if day <= -abs(MAX_DAILY_LOSS):
        store.set_state("halt_" + date, "1")
        return True
    return False
