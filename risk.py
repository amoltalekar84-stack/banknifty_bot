"""
रिस्क मॅनेजर — बॉटचे सुरक्षा कवच:
• दिवसाला कमाल ट्रेड मर्यादा (सिम्बॉल-प्रमाणे + quality.py ची प्रोब/बेंच लॅडर)
• दैनिक नुकसान मर्यादा (BANKNIFTY ₹2,500 / COPPER ₹10,000 = 5%) → त्या दिवशी पुढे ट्रेड नाही
• तोटा-कूलडाउन व बेंच — quality.py मधून (डेटा-आधारित)
• KILL स्विच व पॉज तपासणी (ग्लोबल — सर्व सिम्बॉल्सवर)
"""

import quality
import store
from config import BANKNIFTY, ist_now


def can_enter(date, S=None, now=None):
    """नवीन एंट्री करता येईल का? (S = सिम्बॉल config) → (चालू, कारण)"""
    S = S or BANKNIFTY            # जुन्या सिंगल-सिम्बॉल कॉल्स साठी
    if store.get_state("killed") == "1":
        return False, "KILL स्विच चालू आहे (परत सुरू करण्यासाठी /resume)"
    if store.get_state("paused") == "1":
        return False, "बॉट पॉजमध्ये आहे (/resume)"
    if store.get_state("halt_" + date + "_" + S["key"]) == "1":
        return False, f"आजची नुकसान मर्यादा संपली ({S['label']})"

    # 🛡️ गुणवत्ता-दरवाजे: बेंच + तोटा-कूलडाउन
    ok, why = quality.entry_block(date, S, now)
    if not ok:
        return False, why

    closed = store.closed_trades_today(date, S["key"])
    cap = quality.effective_max_trades(date, S)
    if len(closed) >= cap:
        if cap == 0:
            return False, f"गुणवत्ता-बेंच आजचा दिवस बंद ({S['label']})"
        if cap < S.get("max_trades", 2):
            return False, "गुणवत्ता-प्रोब मोड — आज फक्त 1 ट्रेड (मर्यादा संपली)"
        return False, "आजची ट्रेड मर्यादा संपली"
    return True, ""


def register_exit(date, pnl, S=None, now=None):
    """एग्झिट नोंदवा; दैनिक मर्यादा ओलांडल्यास त्या दिवसासाठी हॉल्ट करा.
    तोट्यात बंद झाल्यास quality.note_loss तोटा-कूलडाउन नोंदवते."""
    S = S or BANKNIFTY            # जुन्या सिंगल-सिम्बॉल कॉल्स साठी
    now = now or ist_now()
    quality.note_loss(date, S, pnl, now)
    day = store.today_pnl(date, S["key"])
    if day <= -abs(S["max_daily_loss"]):
        store.set_state("halt_" + date + "_" + S["key"], "1")
        return True
    return False
