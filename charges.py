"""
सर्व खर्च (Upstox + NSE + सरकारी कर) — BANKNIFTY ऑप्शन ट्रेडसाठी.

महत्त्वाचे: PAPER (कागदी) मोडमध्येही हेच खर्च P&L मधून वजा जातात
→ म्हणजे कागदी निकाल = जवळपास खरा निकाल (वास्तववादी हिशोब).

दर (चालू दर — Upstox चा दरवर्षी बदलू शकतो; contract note मध्ये तुम्हाला
हेच आकडे दिसतील. बदल झाल्यास फक्त खालील कॉन्स्टन्ट बदला):

• ब्रोकरेज (Upstox):       ₹20 प्रत्येक ऑर्डरला (बाय + सेल = ₹40/राउंड-ट्रिप)
• STT (सरकार):             विक्रीच्या प्रीमियमवर 0.1% (1 ऑक्टोबर 2024 पासूनचा दर)
• NSE ट्रान्झॅक्शन चार्ज:   प्रीमियमवर 0.035% (₹3,500/कोटी, दोन्ही बाजू)
• SEBI फी:                 0.0001% (₹10/कोटी, दोन्ही बाजू)
• NSE IPFT:                0.0001% (₹10/कोटी, दोन्ही बाजू)
• स्टॅम्प ड्यूटी (महाराष्ट्र): फक्त खरेदीवर 0.003%
• GST:                     18% (ब्रोकरेज + एक्स्चेंज चार्ज + SEBI + IPFT वर)
"""

BROKERAGE_PER_ORDER = 20.0     # रु. प्रति ऑर्डर
STT_SELL_PCT = 0.1             # फक्त विक्रीवर
NSE_TXN_PCT = 0.035            # दोन्ही बाजू
SEBI_PCT = 0.0001              # दोन्ही बाजू
IPFT_PCT = 0.0001              # दोन्ही बाजू
STAMP_BUY_PCT = 0.003          # फक्त खरेदीवर
GST_PCT = 18.0                 # ब्रोकरेज+NSE+SEBI+IPFT वर

# ---------------- MCX (जिल्हे — Copper/Gold/Crude...) ----------------
# स्त्रोत: Upstox दर + MCX 1 ऑक्टोबर 2024 पासूनचे फी (₹41.80/लाख प्रीमियम)
MCX_CTT_SELL_PCT = 0.05        # CTT फक्त विक्रीच्या प्रीमियमवर (जिल्हे options)
MCX_TXN_PCT = 0.0418           # MCX ट्रान्झॅक्शन (दोन्ही बाजू, प्रीमियमवर)
MCX_SEBI_PCT = 0.0001          # SEBI ₹10/कोटी (दोन्ही बाजू)
MCX_STAMP_BUY_PCT = 0.003      # स्टॅम्प फक्त खरेदीवर
MCX_GST_PCT = 18.0             # GST (ब्रोकरेज+MCX+SEBI वर)

MCX_LABELS = {
    "brokerage": "ब्रोकरेज (₹20 × ऑर्डर)",
    "ctt": "CTT (विक्रीवर 0.05%)",
    "mcx_txn": "MCX ट्रान्झॅक्शन (0.0418%)",
    "sebi": "SEBI फी",
    "stamp": "स्टॅम्प ड्यूटी (खरेदीवर)",
    "gst": "GST 18%",
    "total": "एकूण",
}

LABELS = {
    "brokerage": "ब्रोकरेज (₹20 × 2 ऑर्डर)",
    "stt": "STT (विक्रीवर 0.1%)",
    "nse_txn": "NSE ट्रान्झॅक्शन (0.035%)",
    "sebi": "SEBI फी",
    "ipft": "NSE IPFT",
    "stamp": "स्टॅम्प ड्यूटी (खरेदीवर)",
    "gst": "GST 18%",
    "total": "एकूण",
}


def option_charges(buy_value, sell_value):
    """
    बाय + सेल टर्नओव्हरवर सर्व खर्च काढा.
    buy_value  = एंट्री किंमत × qty (उदा. 150 × 30 = 4500)
    sell_value = एग्झिट किंमत × qty
    येणारे → dict: brokerage, stt, nse_txn, sebi, ipft, stamp, gst, total
    """
    buy_value = max(float(buy_value or 0), 0.0)
    sell_value = max(float(sell_value or 0), 0.0)

    brokerage = 0.0
    if buy_value > 0:
        brokerage += BROKERAGE_PER_ORDER
    if sell_value > 0:
        brokerage += BROKERAGE_PER_ORDER

    stt = sell_value * STT_SELL_PCT / 100.0
    nse = (buy_value + sell_value) * NSE_TXN_PCT / 100.0
    sebi = (buy_value + sell_value) * SEBI_PCT / 100.0
    ipft = (buy_value + sell_value) * IPFT_PCT / 100.0
    stamp = buy_value * STAMP_BUY_PCT / 100.0
    gst = (brokerage + nse + sebi + ipft) * GST_PCT / 100.0

    total = brokerage + stt + nse + sebi + ipft + stamp + gst
    return {"brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "nse_txn": round(nse, 2),
            "sebi": round(sebi, 2),
            "ipft": round(ipft, 2),
            "stamp": round(stamp, 2),
            "gst": round(gst, 2),
            "total": round(total, 2)}


def option_charges_ladder(buy_value, sell_legs):
    """
    TP-लॅडर ट्रेडसाठी: एक बाय ऑर्डर + अनेक वेगवेगळे सेल ऑर्डर.
    buy_value = एंट्री × एकूण qty
    sell_legs = [(किंमत, qty), ...] — प्रत्येक बुकिंग एक वेगळा सेल ऑर्डर
    (प्रत्येक सेल ऑर्डरला वेगळे ₹20 ब्रोकरेज लागते — हेच वास्तव!)
    """
    buy_value = max(float(buy_value or 0), 0.0)
    legs = [(float(p), float(q)) for (p, q) in sell_legs if float(q) > 0]
    sell_value = sum(p * q for p, q in legs)

    n_orders = (1 if buy_value > 0 else 0) + len(legs)
    brokerage = BROKERAGE_PER_ORDER * n_orders
    stt = sell_value * STT_SELL_PCT / 100.0
    nse = (buy_value + sell_value) * NSE_TXN_PCT / 100.0
    sebi = (buy_value + sell_value) * SEBI_PCT / 100.0
    ipft = (buy_value + sell_value) * IPFT_PCT / 100.0
    stamp = buy_value * STAMP_BUY_PCT / 100.0
    gst = (brokerage + nse + sebi + ipft) * GST_PCT / 100.0

    total = brokerage + stt + nse + sebi + ipft + stamp + gst
    return {"brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "nse_txn": round(nse, 2),
            "sebi": round(sebi, 2),
            "ipft": round(ipft, 2),
            "stamp": round(stamp, 2),
            "gst": round(gst, 2),
            "total": round(total, 2),
            "orders": n_orders}


def mcx_option_charges_ladder(buy_value, sell_legs):
    """
    MCX जिल्हे (Copper/Gold/Crude...) ऑप्शन TP-लॅडर खर्च:
    एक बाय ऑर्डर + n सेल ऑर्डर; ब्रोकरेज ₹20/ऑर्डर, CTT 0.05% विक्रीवर,
    MCX ट्रान्झॅक्शन 0.0418%, SEBI, स्टॅम्प 0.003% खरेदीवर, GST 18%.
    → dict: brokerage, ctt, mcx_txn, sebi, stamp, gst, total, orders
    """
    buy_value = max(float(buy_value or 0), 0.0)
    legs = [(float(p), float(q)) for (p, q) in sell_legs if float(q) > 0]
    sell_value = sum(p * q for p, q in legs)

    n_orders = (1 if buy_value > 0 else 0) + len(legs)
    brokerage = BROKERAGE_PER_ORDER * n_orders
    ctt = sell_value * MCX_CTT_SELL_PCT / 100.0
    txn = (buy_value + sell_value) * MCX_TXN_PCT / 100.0
    sebi = (buy_value + sell_value) * MCX_SEBI_PCT / 100.0
    stamp = buy_value * MCX_STAMP_BUY_PCT / 100.0
    gst = (brokerage + txn + sebi) * MCX_GST_PCT / 100.0

    total = brokerage + ctt + txn + sebi + stamp + gst
    return {"brokerage": round(brokerage, 2),
            "ctt": round(ctt, 2),
            "mcx_txn": round(txn, 2),
            "sebi": round(sebi, 2),
            "stamp": round(stamp, 2),
            "gst": round(gst, 2),
            "total": round(total, 2),
            "orders": n_orders}


def mcx_option_charges(buy_value, sell_value):
    """MCX साधा राउंड-ट्रिप (1 बाय + 1 सेल)"""
    return mcx_option_charges_ladder(buy_value, [(float(sell_value), 1)])


if __name__ == "__main__":
    # उदाहरण: ₹150 प्रीमियमला 1 lot बाय → ₹160 ला सेल (जिंकीचा ट्रेड)
    b = option_charges(150 * 30, 160 * 30)
    print("उदाहरण 1: ₹150 → ₹160 (1 lot = 30)")
    for k, v in b.items():
        print(f"  {LABELS.get(k, k):28s}: ₹{v:,.2f}")
    # उदाहरण 2: स्टॉप लॉस ट्रेड (−20%)
    b2 = option_charges(150 * 30, 120 * 30)
    print("\nउदाहरण 2: ₹150 → ₹120 (स्टॉप लॉस)")
    for k, v in b2.items():
        print(f"  {LABELS.get(k, k):28s}: ₹{v:,.2f}")
    # उदाहरण 3: MCX Copper — ATM प्रीमियम ₹27.5/kg × 2500 = ₹68,750 गुंतवणूक
    # (₹1,374 स्ट्राइक) → ₹30/kg ला विक्री (+9%)
    m = mcx_option_charges_ladder(27.5 * 2500, [(30.0, 2500)])
    print("\nउदाहरण 3: MCX COPPER 1 लॉट (2500 kg) — ₹27.50 → ₹30.00 (+9%)")
    for k, v in m.items():
        if k != "orders":
            print(f"  {MCX_LABELS.get(k, k):28s}: ₹{v:,.2f}")
    # उदाहरण 4: MCX GOLD — ATM ₹3,200 × 1 kg → ₹3,400 (+6%)
    g = mcx_option_charges_ladder(3200 * 1, [(3400.0, 1)])
    print("\nउदाहरण 4: MCX GOLD 1 लॉट (1 kg) — ₹3,200 → ₹3,400 (+6%)")
    for k, v in g.items():
        if k != "orders":
            print(f"  {MCX_LABELS.get(k, k):28s}: ₹{v:,.2f}")
