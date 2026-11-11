"""
सेटिंग्ज — सर्व पॅरामीटर्स इथे आहेत.
(Marathi: इथे बदल करून धोरण बदलता येते; Render Environment वरूनही सेट होते.)
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo


def _f(name, default):
    """env var → float (चुकीची व्हॅल्यू असल्यास default)"""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _i(name, default):
    """env var → int"""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------
# 1. टेलिग्राम (Render → Environment मध्ये सेट करा)
# ---------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = _i("ADMIN_CHAT_ID", 1664307086)   # तुमची चॅट ID — आधीच बेक-इन (Secret दिल्यास ते वर चढेल)

# ---------------------------------------------------------------
# 2. Upstox (Render → Environment मध्ये सेट करा)
# ---------------------------------------------------------------
UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "").strip()          # API Key
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "").strip()  # API Secret
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "").strip()    # तुमचा Render URL
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()    # (ऐच्छिक) सुरुवातीचा टोकन

# ---------------------------------------------------------------
# 3. LIVE mode कुलूपबंद (सुरक्षा)
#    live चालू करण्यासाठी ३ गेट आहेत:
#    ① Secrets मध्ये ALLOW_LIVE=YES   ② /mode live   ③ खालील वाक्य टाइप करा
# ---------------------------------------------------------------
ALLOW_LIVE = os.getenv("ALLOW_LIVE", "").strip().upper() == "YES"
LIVE_CONFIRM_TEXT = os.getenv("LIVE_CONFIRM_TEXT", "मला धोका मान्य आहे")

# ---------------------------------------------------------------
# 4. बाजार / इन्स्ट्रुमेंट — फक्त BANKNIFTY (तुमची मागणी)
# ---------------------------------------------------------------
INDEX_KEY = os.getenv("INDEX_KEY", "NSE_INDEX|Nifty Bank")
INDEX_LABEL = "BANKNIFTY"
TZ_NAME = "Asia/Kolkata"

# ---------------------------------------------------------------
# 5. भांडवल व साईझिंग (तुमची मागणी: किमान ₹50,000)
# ---------------------------------------------------------------
CAPITAL = _f("CAPITAL", 50000.0)   # भांडवल ₹
LOT_SIZE = _i("LOT_SIZE", 30)      # BankNifty lot = 30 (NSE नियम, जाने. 2026 पासून)
MAX_LOTS = _i("MAX_LOTS", 1)       # एका वेळेस कमाल 1 lot — सुरक्षित साईझिंग

# ---------------------------------------------------------------
# 6. धोरण: ORB (Opening Range Breakout)
#    9:15–9:30 ची रेंज तुटल्यावर ATM CE/PE खरेदी
# ---------------------------------------------------------------
ORB_START = "09:15"        # ओपनिंग रेंज सुरुवात
ORB_END = "09:30"          # ओपनिंग रेंज समाप्ती
ENTRY_START = "09:30"      # एंट्री विंडो सुरुवात
ENTRY_END = "12:00"        # एंट्री विंडो शेवट (दुपारी नवीन एंट्री नाही)
SQUARE_OFF = "15:05"       # 15:05 ला जबरदस्ती बंद
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"

# "AI फिल्टर" — वाईट परिस्थितीत सिग्नल वगळणे:
MIN_OR_WIDTH_PCT = _f("MIN_OR_WIDTH_PCT", 0.15)   # रेंज खूप छोटी (मंदी) → वगळा
MAX_OR_WIDTH_PCT = _f("MAX_OR_WIDTH_PCT", 2.00)   # रेंज खूप मोठी (गोंधळ) → वगळा
MAX_GAP_PCT = _f("MAX_GAP_PCT", 1.00)             # गॅप १% पेक्षा जास्त → वगळा

# ---------------------------------------------------------------
# 7. रिस्क मॅनेजमेंट (सुरक्षा कवच)
#    TP लॅडर: जिंक 3 भागांत बुक होतो (लॉट 30 → 10+10+10)
#    TP1 झाल्यावर शिल्लक SL breakeven वर → तोटा शक्य नाही
#    TP2 झाल्यावर SL +10% वर → किमान नफा लॉक
# ---------------------------------------------------------------
SL_PCT = _f("SL_PCT", 20.0)                    # स्टॉप लॉस = एंट्रीच्या किंमतीच्या -20%
TARGET_PCT = _f("TARGET_PCT", 40.0)            # TP2 = +40% (जुना टार्गेट)
TP1_PCT = _f("TP1_PCT", 20.0)                  # TP1 = +20% → 1/3 भाग बुक
TP3_PCT = _f("TP3_PCT", 60.0)                  # TP3 = +60% → शेवटचा 1/3 भाग बुक
TRAIL_START_PCT = _f("TRAIL_START_PCT", 25.0)  # (जुना नियम — बॅकटेस्टसाठी वापरला जातो)
MAX_TRADES_PER_DAY = _i("MAX_TRADES_PER_DAY", 2)    # दिवसाला कमाल 2 ट्रेड
MAX_DAILY_LOSS = _f("MAX_DAILY_LOSS", 2500.0)       # दैनिक तोटा मर्यादा ₹2,500 (भांडवलाच्या 5%)

# ---------------------------------------------------------------
# 7.5 COPPER (MCX) — दुसरा सिम्बॉल, स्वतंत्र ताजे भांडवल
#     खऱ्या नियमांचा लॉजिकल रूपांतर (MCX lot 2500 kg असल्याने
#     10+10+10 भागाकार शक्य नाही):
#       • +20% (TP1) → SL breakeven वर लॉक (कोणताही भाग बुक नाही)
#       • +40% (TP2) → संपूर्ण लॉट बुकिंग
#     वेळ: MCX 9:00–23:30/23:55 (US DST नुसार) — आपला
#     स्क्वेअर-ऑफ 23:05 दोन्ही परिस्थितीत सुरक्षित.
#     Copper चे ORB: रेंज 9:15–9:45 (30 मिनिटं), एंट्री 9:45–12:00.
# ---------------------------------------------------------------
CU_LOT = _i("CU_LOT", 2500)                 # MCX Copper lot = 2500 kg (SEBI ₹15L नियम)
CU_CAPITAL = _f("CU_CAPITAL", 200000.0)     # स्वतंत्र ताजे paper भांडवल ₹2 लाख
CU_MAX_DAILY_LOSS = _f("CU_MAX_DAILY_LOSS", 10000.0)  # 5% of ₹2L
CU_MAX_TRADES = _i("CU_MAX_TRADES", 2)
CU_ORB_START = "09:15"
CU_ORB_END = "09:45"
CU_ENTRY_START = "09:45"
CU_ENTRY_END = "12:00"
CU_SQUARE_OFF = "23:05"
CU_MARKET_OPEN = "09:00"
CU_MARKET_CLOSE = "23:30"      # DST-काळ 23:30; हिवाळी 23:55 — 23:05 square-off दोन्हीत सुरक्षित

COPPER = {
    "key": "COPPER",
    "label": "COPPER (MCX)",
    "short": "CU",
    "seg": "MCX",
    "lot": CU_LOT,
    "capital": CU_CAPITAL,
    "capital_state": "capital_COPPER",
    "max_trades": CU_MAX_TRADES,
    "max_daily_loss": CU_MAX_DAILY_LOSS,
    "orb_start": CU_ORB_START, "orb_end": CU_ORB_END,
    "entry_start": CU_ENTRY_START, "entry_end": CU_ENTRY_END,
    "square_off": CU_SQUARE_OFF,
    "square_off_label": "वेळ एग्झिट (23:05)",
    "market_open": CU_MARKET_OPEN, "market_close": CU_MARKET_CLOSE,
    "sl_pct": SL_PCT, "tp1_pct": TP1_PCT, "tp2_pct": TARGET_PCT, "tp3_pct": TP3_PCT,
    "ladder": False,          # 1 lot (2500) — भागाकार बुकिंग शक्य नाही
    "brk_buffer_pct": _f("CU_BRK_BUFFER_PCT", 0.0),  # breakout-बफर % (नकली-ब्रेक चाळणी)
    "mcx": True,
    "commodity": "COPPER",                  # Upstox फाईलमधले खरे नाव
    "ts_pattern": r"^COPPER\d",             # फक्त main series
    "trade_lot": None,                      # ऑप्शनचा lot फाईलमधून
    "min_candles": 31,        # OR रेंज 9:15–9:45 = 30 कॅन्डल + 1
    "summary_at": "23:10",    # Copper दैनिक अहवाल — स्क्वेअर-ऑफ नंतर
}

# ----------------------------------------------------------------
# 7.6 GOLD / SILVER / NATURAL GAS / CRUDE — प्रत्येकी स्वतंत्र भांडवल
#     तत्त्व Copper प्रमाणेच: 1 लॉट → +20% breakeven लॉक, +40% पूर्ण बुकिंग.
#     लॉट/कॉन्ट्रॅक्ट रोज Upstox instruments फाईलमधून (main series);
#     खालील lot फक्त fallback.
#     GOLD ऑप्शन: 1 kg = 100 × 10g, प्रीमियम प्रति 10 g (MCX स्पेक)
#     → trade_lot = 100; म्हणून भांडवलही त्याच प्रमाणात.
# ----------------------------------------------------------------

def _mcx_symbol(key, label, short, commodity, ts_pattern, capital,
                max_daily_loss, lot, trade_lot=None, summary_at="23:10"):
    return {
        "key": key, "label": label, "short": short, "seg": "MCX",
        "lot": lot,
        "capital": capital, "capital_state": "capital_" + key,
        "max_trades": 2, "max_daily_loss": max_daily_loss,
        "orb_start": CU_ORB_START, "orb_end": CU_ORB_END,
        "entry_start": CU_ENTRY_START, "entry_end": CU_ENTRY_END,
        "square_off": CU_SQUARE_OFF,
        "square_off_label": "वेळ एग्झिट (23:05)",
        "market_open": CU_MARKET_OPEN, "market_close": CU_MARKET_CLOSE,
        "sl_pct": SL_PCT, "tp1_pct": TP1_PCT, "tp2_pct": TARGET_PCT,
        "tp3_pct": TP3_PCT,
        "ladder": False,          # 1 लॉट — भागाकार बुकिंग शक्य नाही
        "brk_buffer_pct": 0.0,    # breakout-बफर % (सुरुवातीला बंद — बॅकटेस्टनंतर चालू)
        "mcx": True,
        "commodity": commodity, "ts_pattern": ts_pattern,
        "trade_lot": trade_lot,
        "min_candles": 31,
        "summary_at": summary_at,
    }

GOLD = _mcx_symbol(
    "GOLD", "GOLD (MCX)", "GOLD", "GOLD", r"^GOLD\d",
    capital=_f("GOLD_CAPITAL", 800000.0),
    max_daily_loss=_f("GOLD_MAX_DAILY_LOSS", 40000.0),   # 5% of ₹8L
    lot=100, trade_lot=100,           # ऑप्शन 1 kg = 100 × 10g
    summary_at="23:12")

SILVER = _mcx_symbol(
    "SILVER", "SILVER (MCX)", "SILVER", "SILVER", r"^SILVER(?!100)\d",
    capital=_f("SILVER_CAPITAL", 500000.0),
    max_daily_loss=_f("SILVER_MAX_DAILY_LOSS", 25000.0),  # 5% of ₹5L
    lot=30, summary_at="23:14")

CRUDE = _mcx_symbol(
    "CRUDE", "CRUDE (MCX)", "CRUDE", "CRUDE OIL", r"^CRUDEOIL\d",
    capital=_f("CRUDE_CAPITAL", 200000.0),
    max_daily_loss=_f("CRUDE_MAX_DAILY_LOSS", 10000.0),   # 5% of ₹2L
    lot=100, summary_at="23:16")

NATGAS = _mcx_symbol(
    "NATGAS", "NATGAS (MCX)", "NG", "NATURALGAS", r"^NATURALGAS\d",
    capital=_f("NG_CAPITAL", 100000.0),
    max_daily_loss=_f("NG_MAX_DAILY_LOSS", 5000.0),       # 5% of ₹1L
    lot=1250, summary_at="23:18")

BANKNIFTY = {
    "key": "BANKNIFTY",
    "label": "BANKNIFTY",
    "short": "BN",
    "seg": "NSE",
    "index_key": INDEX_KEY,
    "lot": LOT_SIZE,
    "capital": CAPITAL,
    "capital_state": "capital_BANKNIFTY",
    "max_trades": MAX_TRADES_PER_DAY,
    "max_daily_loss": MAX_DAILY_LOSS,
    "orb_start": ORB_START, "orb_end": ORB_END,
    "entry_start": ENTRY_START, "entry_end": ENTRY_END,
    "square_off": SQUARE_OFF,
    "square_off_label": "वेळ एग्झिट (15:05)",
    "market_open": MARKET_OPEN, "market_close": MARKET_CLOSE,
    "sl_pct": SL_PCT, "tp1_pct": TP1_PCT, "tp2_pct": TARGET_PCT, "tp3_pct": TP3_PCT,
    "ladder": True,           # लॉट 30 → 10+10+10 भागाकार
    "brk_buffer_pct": _f("BRK_BUFFER_BANKNIFTY", 0.0),  # breakout-बफर %
    "mcx": False,
    "min_candles": 16,
    "summary_at": "15:20",
}

# ----------------------------------------------------------------
# 7.7 NIFTY 50 / SENSEX / FINNIFTY — बॉट आता All Rounder (एकूण 9 सिम्बॉल्स)
#     • BANKNIFTY प्रमाणेच वेळा/नियम: ORB 09:15–09:30, एंट्री 09:30–12:00,
#       SL −20%, TP लॅडर 1/3+1/3+1/3, breakeven लॉक, 15:05 स्क्वेअर-ऑफ.
#     • लॉट (Upstox instruments, नोव्हेंबर 2026): NIFTY 65 | SENSEX 20 |
#       FINNIFTY 60 — सर्व 3 भागांत विभागण्यायोग्य/समर्थित.
#     • प्रत्येकाला स्वतंत्र paper भांडवल ₹50,000 + दैनिक तोटा मर्यादा ₹2,500.
#     • SENSEX = BSE (BSE_INDEX|SENSEX); ऑप्शन चेन त्याच API ने.
# ----------------------------------------------------------------

def _index_symbol(key, label, short, seg, index_key, lot,
                  capital, max_daily_loss, summary_at):
    return {
        "key": key, "label": label, "short": short, "seg": seg,
        "index_key": index_key,
        "lot": lot,
        "capital": capital, "capital_state": "capital_" + key,
        "max_trades": MAX_TRADES_PER_DAY, "max_daily_loss": max_daily_loss,
        "orb_start": ORB_START, "orb_end": ORB_END,
        "entry_start": ENTRY_START, "entry_end": ENTRY_END,
        "square_off": SQUARE_OFF,
        "square_off_label": "वेळ एग्झिट (15:05)",
        "market_open": MARKET_OPEN, "market_close": MARKET_CLOSE,
        "sl_pct": SL_PCT, "tp1_pct": TP1_PCT, "tp2_pct": TARGET_PCT,
        "tp3_pct": TP3_PCT,
        "ladder": True,           # TP लॅडर — thirds() शिल्लक स्वयंहाताळते
        "brk_buffer_pct": _f("BRK_BUFFER_" + key, 0.0),  # breakout-बफर %
        "mcx": False,
        "min_candles": 16,
        "summary_at": summary_at,
    }

NIFTY = _index_symbol(
    "NIFTY", "NIFTY 50", "NIFTY", "NSE", "NSE_INDEX|Nifty 50",
    lot=_i("NIFTY_LOT", 65),
    capital=_f("NIFTY_CAPITAL", 50000.0),
    max_daily_loss=_f("NIFTY_MAX_DAILY_LOSS", 2500.0),
    summary_at="15:22")

SENSEX = _index_symbol(
    "SENSEX", "SENSEX (BSE)", "SENSEX", "BSE", "BSE_INDEX|SENSEX",
    lot=_i("SENSEX_LOT", 20),
    capital=_f("SENSEX_CAPITAL", 50000.0),
    max_daily_loss=_f("SENSEX_MAX_DAILY_LOSS", 2500.0),
    summary_at="15:24")

FINNIFTY = _index_symbol(
    "FINNIFTY", "FINNIFTY", "FN", "NSE", "NSE_INDEX|Nifty Fin Service",
    lot=_i("FINNIFTY_LOT", 60),
    capital=_f("FINNIFTY_CAPITAL", 50000.0),
    max_daily_loss=_f("FINNIFTY_MAX_DAILY_LOSS", 2500.0),
    summary_at="15:26")

# इंजिन या क्रमाने प्रत्येक सिम्बॉल चालवते
SYMBOLS = [BANKNIFTY, NIFTY, SENSEX, FINNIFTY,
           COPPER, GOLD, SILVER, CRUDE, NATGAS]

# प्रत्येक सिम्बॉल स्वतंत्र बंद करता येतो (env मध्ये ENABLE_<SYMBOL>=NO)
_ENABLERS = {
    "BANKNIFTY": True,
    "NIFTY": os.getenv("ENABLE_NIFTY", "YES").strip().upper() != "NO",
    "SENSEX": os.getenv("ENABLE_SENSEX", "YES").strip().upper() != "NO",
    "FINNIFTY": os.getenv("ENABLE_FINNIFTY", "YES").strip().upper() != "NO",
    "COPPER": os.getenv("ENABLE_COPPER", "YES").strip().upper() != "NO",
    "GOLD": os.getenv("ENABLE_GOLD", "YES").strip().upper() != "NO",
    "SILVER": os.getenv("ENABLE_SILVER", "YES").strip().upper() != "NO",
    "CRUDE": os.getenv("ENABLE_CRUDE", "YES").strip().upper() != "NO",
    "NATGAS": os.getenv("ENABLE_NATGAS", "YES").strip().upper() != "NO",
}

# ---------------------------------------------------------------
# 8. इंजिन
# ---------------------------------------------------------------
POLL_SEC = _i("POLL_SEC", 30)      # दर 30 सेकंदांनी बाजार तपासणी
SLIPPAGE = _f("SLIPPAGE", 0.0005)  # कागदी ट्रेडमध्ये 0.05% स्लिपेज (वास्तववादी हिशोब)

# डीफॉल्ट मोड — नेहमी PAPER (कागद) ने सुरु!
MODE = os.getenv("TRADING_MODE", "PAPER").strip().upper()


# ---------------------------------------------------------------
# 9. 🧠 AI ब्रेन — सल्लागार-विश्लेषक (सर्व मार्ग मोफत, शून्य खर्च)
#    रोज AI_BRAIN_AT नंतर दिवसाचे आकडे वाचून मराठी विश्लेषण तयार करतो.
#    AI कधीही ऑर्डर/गेट/halt हाताळत नाही — फक्त सल्ला.
#    साखळी: Ollama (VM-वर, मोफत-अमर्यादित) → Groq (बैकअप) → HF (बैकअप) → स्किप.
#    बंद करायचे: AI_BRAIN_ENABLED=NO (बॉटचे व्यापार तसेच चालू)
# ---------------------------------------------------------------
AI_BRAIN_ENABLED = os.getenv("AI_BRAIN_ENABLED", "YES").strip().upper() != "NO"
AI_BRAIN_AT = os.getenv("AI_BRAIN_AT", "20:32")   # EVAL-DAILY (20:30) नंतर
AI_MODEL = os.getenv("AI_MODEL", "qwen3:4b")      # Ollama मॉडेल (HF वर मोफत)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
AI_TIMEOUT = _i("AI_TIMEOUT", 90)                 # प्रोव्हाइडर-कॉल टाइमआउट से
AI_BRAIN_HOLD_MIN = _i("AI_BRAIN_HOLD_MIN", 30)   # सर्किट-ब्रेकर धारणा मिनिटे
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()   # बैकअप-डोके (की असेल तरच)
AI_CLOUD_MODEL = os.getenv("AI_CLOUD_MODEL", "llama-3.3-70b-versatile")
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()           # बैकअप-डोके (की असेल तरच)
AI_HF_MODEL = os.getenv("AI_HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")


def active_symbols():
    """चालू करण्यायोग्य सिम्बॉल्स (ENABLE_<SYM>=NO असल्यास तो वगळला)"""
    return [s for s in SYMBOLS if _ENABLERS.get(s["key"], True)]


def ist_now():
    """भारतीय प्रमाणित वेळ (IST) — सर्व्हर UTC मध्ये असला तरी बरोबर वेळ येईल."""
    return datetime.now(ZoneInfo(TZ_NAME))
