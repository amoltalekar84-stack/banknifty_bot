"""
टेलिग्राम सुंदर कार्ड (HTML) — एंट्री कार्ड, TP अपडेट, एग्झिट रसीद.
फक्त मजकूर बनवते — कोणताही नेटवर्क/DB वापर नाही → सहज चाचणी करता येते.
"""

import html as _html

# मराठी वार
WEEKDAYS = ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार",
            "शनिवार", "रविवार"]
MONTHS = ["", "जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून",
          "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"]


def day_name(dt):
    return WEEKDAYS[dt.weekday()]


def fmt_date(dstr):
    """'2026-11-05' → '05 नोव्हेंबर 2026 (गुरुवार)' — चुकीचा फॉरमॅट असल्यास तसाच"""
    try:
        from datetime import date as _d
        y, m, dd = [int(x) for x in dstr.split("-")][:3]
        return (f"{dd:02d} {MONTHS[m]} {y} ({WEEKDAYS[_d(y, m, dd).weekday()]})")
    except (ValueError, TypeError, IndexError):
        return str(dstr)


def _esc(s):
    return _html.escape(str(s))


def _rs(amount):
    """₹ रक्कम — निगेटिव्हसाठी −₹ चिन्ह"""
    if amount < 0:
        return f"−₹{abs(amount):,.0f}"
    return f"₹{amount:,.0f}"


# ------------------------------------------------------------------
# ① एंट्री कार्ड
# ------------------------------------------------------------------
def entry_card(mode, side, strike, expiry, entry, qty, lots, spot,
               or_high, or_low, breakout, sl, tp1, tp2, tp3, est_chg,
               est_orders, in_ts, index_label="BANKNIFTY"):
    now_dt = in_ts
    date_line = (f"{now_dt.strftime('%d-%m-%Y')} ({day_name(now_dt)})")
    emo = "🟢" if side == "CE" else "🔴"
    side_full = "CALL (CE) — भाव वर जाण्याची शर्त" if side == "CE" \
        else "PUT (PE) — भाव खाली जाण्याची शर्त"
    invest = entry * qty
    q1, q2, q3 = thirds_qty(qty)
    pnl1 = (tp1 - entry) * q1
    pnl2 = (tp2 - entry) * q2
    pnl3 = (tp3 - entry) * q3
    sl_loss = (sl - entry) * qty

    return f"""{emo} <b>{_esc(index_label)} {strike:.0f} {side} — नवीन ट्रेड ({_esc(mode)})</b>
━━━━━━━━━━━━━━━━━━━━━━
🏷️ <b>ट्रेड तपशील</b>
• ऑप्शन: <b>{strike:.0f} {side}</b> — {side_full}
• एक्सपायरी: {fmt_date(expiry)}
• ⏰ {now_dt.strftime('%H:%M:%S')} | {date_line}
• 📦 रक्कम: {qty} ({lots} लॉट) | 💵 प्रीमियम <b>₹{entry:.2f}</b>
• 💳 गुंतवणूक: <b>{_rs(invest)}</b>
• 📍 {_esc(index_label)} स्पॉट: {_rs(spot)}
────────────────────
🎯 <b>प्लॅन (TP लॅडर)</b>
🛑 SL: ₹{sl:.2f} (−20%) → कमाल तोटा {_rs(sl_loss)}
1️⃣ TP1: ₹{tp1:.2f} (+20%) → {q1} बुक → {_rs(pnl1)}
2️⃣ TP2: ₹{tp2:.2f} (+40%) → {q2} बुक → {_rs(pnl2)}
3️⃣ TP3: ₹{tp3:.2f} (+60%) → {q3} बुक → {_rs(pnl3)}
🔒 TP1 झाल्यावर SL breakeven वर — तोटा अशक्य!
────────────────────
📌 OR रेंज: {or_high:.0f} / {or_low:.0f} | ब्रेकआउट: {breakout:.0f}
🧾 अंदाजे खर्च ({est_orders} ऑर्डर + सर्व कर): {_rs(est_chg)}"""


def thirds_qty(qty):
    qty = max(int(qty), 1)
    q3 = max(qty // 3, 1)
    q1, q2 = q3, q3
    q3r = qty - q1 - q2
    if q3r <= 0:
        q3r = 1
    return q1, q2, q3r


# ------------------------------------------------------------------
# ② TP बुकिंग अपडेट कार्ड
# ------------------------------------------------------------------
def tp_card(mode, side, strike, tp_no, price, qty, leg_gross,
            remaining, new_sl, entry, out_time, index_label="BANKNIFTY"):
    lock = ""
    if tp_no == 1:
        lock = "\n🔒 शिल्लक SL breakeven वर आला — <b>आता तोटा शक्य नाही</b>"
    elif tp_no == 2:
        lock = "\n🔒 शिल्लक SL ₹" + f"{new_sl:.2f} (+10%) वर — <b>किमान नफा लॉक</b>"
    return f"""🎯 <b>TP{tp_no} बुक झाला!</b> ({_esc(mode)})
━━━━━━━━━━━━━━━━━━━━━━
📊 {_esc(index_label)} {strike:.0f} {side}
💰 विक्री: <b>₹{price:.2f}</b> × {qty} | एंट्री ₹{entry:.2f}
💵 या भागाचा करपूर्व नफा: <b>{_rs(leg_gross)}</b>
📦 उर्वरित: {remaining} qty{lock}
⏰ {out_time} | TP{tp_no} बुकिंग पूर्ण ✅"""


# ------------------------------------------------------------------
# ③ एग्झिट रसीद कार्ड
# ------------------------------------------------------------------
def exit_card(mode, side, strike, reason, entry, exit_avg, chg, pnl,
              legs, day_pnl, total_pnl, halted, max_daily_loss,
              in_ts, out_ts, index_label="BANKNIFTY"):
    icon = "✅" if pnl >= 0 else "❌"
    lines = [f"{icon} <b>ट्रेड पूर्ण — रसीद ({_esc(mode)})</b>",
             "━━━━━━━━━━━━━━━━━━━━━━",
             f"📊 {_esc(index_label)} {strike:.0f} {side}",
             f"📋 कारण: <b>{_esc(reason)}</b>",
             f"⏰ एंट्री {in_ts} → एग्झिट {out_ts}",
             "────────────────────",
             f"💰 एंट्री ₹{entry:.2f} → सरासरी एग्झिट <b>₹{exit_avg:.2f}</b>",
             f"🧾 एकूण खर्च (1 बाय + {max(len(legs)-1, 0)} सेल + कर): {_rs(chg)}",
             f"📉 <b>निव्वळ P&L: {_rs(pnl)}</b>"]
    if len(legs) > 1 or (legs and legs[0].get("label", "").startswith("TP")):
        lines.append("────────────────────")
        lines.append("📖 <b>बुकिंग तपशील:</b>")
        for i, l in enumerate(legs, 1):
            g = (float(l["price"]) - entry) * int(l["qty"])
            tag = _esc(l.get("label") or f"भाग {i}")
            lines.append(f"  {i}) {tag}: ₹{float(l['price']):.2f} × "
                         f"{int(l['qty'])} → {_rs(g)}")
    lines.append("────────────────────")
    lines.append(f"📊 आजचा निव्वल: {_rs(day_pnl)} | सुरुवातीपासून: {_rs(total_pnl)}")
    if halted:
        lines.append(f"🛑 दैनिक नुकसान मर्यादा (₹{abs(max_daily_loss):,.0f}) "
                     "ओलांडली — आज पुढे कोणताही ट्रेड नाही.")
    return "\n".join(lines)


# ------------------------------------------------------------------
# चाचणी:  python3 cards.py
# ------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import datetime
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
    t = datetime(2026, 11, 2, 9, 45, 12, tzinfo=IST)
    e = 195.10
    c1 = entry_card("PAPER", "CE", 55600, "2026-11-05", e, 30, 1, 55180,
                    55120, 55250, 55260, round(e * 0.8, 2),
                    round(e * 1.2, 2), round(e * 1.4, 2), round(e * 1.6, 2),
                    131.90, 4, t)
    print("===== एंट्री कार्ड =====")
    print(c1)
    print()
    print("===== TP1 कार्ड =====")
    print(tp_card("PAPER", "CE", 55600, 1, 234.20, 10, 391.0, 20,
                  round(e, 2), e, "09:52:30"))
    print()
    legs = [{"label": "TP1", "price": 234.20, "qty": 10},
            {"label": "TP2", "price": 273.20, "qty": 10},
            {"label": "वेळ एग्झिट (15:05)", "price": 288.0, "qty": 10}]
    print("===== एग्झिट कार्ड =====")
    print(exit_card("PAPER", "CE", 55600, "TP1 + TP2 + वेळ एग्झिट (15:05)",
                    e, 265.13, 131.90, 2100.0, legs, 2100.0, 2100.0,
                    False, 2500, "09:45", "15:05"))
