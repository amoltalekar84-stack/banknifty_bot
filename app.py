"""
सर्व्हर एंट्री पॉइंट (Render.com / कोणताही Python होस्ट):
• बॅकग्राउंडमध्ये: ट्रेडिंग इंजिन + टेलिग्राम बॉट
• मुख्य पान: सार्वजनिक डॅशबोर्ड (कोणतीही गोपनिय माहिती दाखवत नाही)
"""

import os

import gradio as gr

import config as C
import store
from config import ist_now
from datetime import time as dtime
from engine import start_engine
from telegram_bot import start_telegram

store.init_db()
start_engine()
start_telegram()


def _market_open():
    n = ist_now()
    return ("🟢 सुरू (9:15–15:30)" if (n.weekday() < 5 and
            dtime(9, 15) <= n.time() <= dtime(15, 30)) else "🔴 बंद / सुट्टी")


def dashboard():
    n = ist_now()
    date = n.strftime("%Y-%m-%d")
    mode = store.get_state("mode", "PAPER")
    badges = []
    if store.get_state("killed") == "1":
        badges.append("🚨KILL")
    if store.get_state("paused") == "1":
        badges.append("⏸पॉज")
    if store.get_state("halt_" + date) == "1":
        badges.append("🛑मर्यादा")
    mode_txt = mode + (" " + " ".join(badges) if badges else "")

    tok = "✅ आहे" if store.get_state("upstox_token") else "❌ नाही (Telegram वर /code पाठवा)"

    pos = store.get_open_trade(date)
    pos_txt = ("—" if not pos else
               f"{pos['strike']:.0f} {pos['side']} @ ₹{pos['entry']:.2f} | "
               f"SL ₹{pos['sl']:.2f} | T ₹{pos['target']:.2f}")

    rows = []
    for t in store.trades_today(date):
        rows.append([
            (t["opened"] or "")[-8:-3] if t["opened"] else "—",
            f"{t['strike']:.0f}",
            t["side"],
            t["qty"],
            f"₹{t['entry']:.2f}",
            f"₹{t['exit']:.2f}" if t["exit"] else "—",
            (f"₹{t['pnl']:,.0f}" if t["pnl"] is not None else "—"),
            t["status"] + (f" ({t['reason']})" if t["reason"] else ""),
        ])
    if not rows:
        rows = [["—", "—", "—", "—", "—", "—", "—", "अजून ट्रेड नाही"]]

    return (mode_txt, _market_open(), tok,
            f"₹{store.today_pnl(date):,.0f}",
            f"₹{store.total_pnl():,.0f}",
            pos_txt, rows)


with gr.Blocks(title="BankNifty AI Bot") as demo:
    gr.Markdown(
        "# 🤖 BankNifty AI Trading Bot\n"
        "**PAPER mode** — कागदी ट्रेडिंग (पैसे धोक्यात नाही). "
        "संपूर्ण नियंत्रण तुमच्या Telegram बॉटवर.\n\n"
        f"धोरण: ORB | SL: -{C.SL_PCT:.0f}% | टार्गेट: +{C.TARGET_PCT:.0f}% | "
        f"दैनिक तोटा मर्यादा: ₹{C.MAX_DAILY_LOSS:,.0f}")
    with gr.Row():
        m_mode = gr.Textbox(label="मोड", interactive=False)
        m_mkt = gr.Textbox(label="बाजार", interactive=False)
        m_tok = gr.Textbox(label="Upstox टोकन", interactive=False)
    with gr.Row():
        m_day = gr.Textbox(label="आजचा P&L", interactive=False)
        m_tot = gr.Textbox(label="सुरुवातीपासून P&L", interactive=False)
        m_pos = gr.Textbox(label="उघडी पोझिशन", interactive=False)
    tbl = gr.DataFrame(
        headers=["वेळ", "स्ट्राइक", "SIDE", "Qty", "एंट्री", "एग्झिट", "P&L", "स्थिती"],
        label="आजचे ट्रेड्स", interactive=False)
    btn = gr.Button("🔄 रिफ्रेश")
    outs = [m_mode, m_mkt, m_tok, m_day, m_tot, m_pos, tbl]
    demo.load(dashboard, None, outs)
    gr.Timer(30).tick(dashboard, None, outs)     # दर 30 सेकंदांनी अपडेट
    btn.click(dashboard, None, outs)

if __name__ == "__main__":
    # Render आपोआप PORT env var देतो; स्थानिक चाचणीसाठी 7860
    _port = int(os.environ.get("PORT", "7860"))
    demo.launch(server_name="0.0.0.0", server_port=_port)
