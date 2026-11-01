"""
सर्व्हर एंट्री पॉइंट (Render.com / कोणताही Python होस्ट):
• बॅकग्राउंडमध्ये: ट्रेडिंग इंजिन + टेलिग्राम बॉट
• मुख्य पान: सार्वजनिक डॅशबोर्ड (कोणतीही गोपनिय माहिती दाखवत नाही)
• /api/eval: दैनिक मूल्यांकन JSON — फक्त ट्रेड आकडे (कोणताही टोकन/गुप्त माहिती नाही)
"""

import os
import re

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


# ------------------------------------------------------------------
# /api/eval — दैनिक मूल्यांकन डेटा (फक्त वाचन; कोणतीही गुप्त माहिती नाही)
# ------------------------------------------------------------------
def eval_payload(date=None):
    """?date=YYYY-MM-DD (नसेल तर आज) — दिवसभरचे ट्रेड + खर्च + नियम-माहिती"""
    from config import (CAPITAL, LOT_SIZE, MARKET_CLOSE, MARKET_OPEN,
                        MAX_DAILY_LOSS, MAX_TRADES_PER_DAY, SL_PCT,
                        SQUARE_OFF, TARGET_PCT, TP1_PCT, TP3_PCT)
    n = ist_now()
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
        date = n.strftime("%Y-%m-%d")

    trades = []
    wins = losses = 0
    for t in store.trades_today(date):
        legs = store.get_legs(t["id"])
        booked = sum(int(l.get("qty") or 0) for l in legs)
        entry = float(t["entry"] or 0)
        gross = round(sum((float(l["price"]) - entry) * int(l["qty"])
                          for l in legs), 2)
        pnl = t["pnl"]
        if t["status"] == "CLOSED" and pnl is not None:
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
        trades.append({
            "id": t["id"],
            "opened": (t["opened"] or "")[-8:] or None,
            "closed": (t["closed"] or "")[-8:] or None,
            "side": t["side"], "strike": t["strike"],
            "expiry": t["expiry"], "qty": t["qty"],
            "entry": entry, "exit": t["exit"],
            "sl": t["sl"], "target": t["target"],
            "status": t["status"], "reason": t["reason"],
            "charges": t["charges"], "pnl_net": pnl, "gross_pnl": gross,
            "booked_qty": booked, "remaining_qty": int(t["qty"] or 0) - booked,
            "legs": [{"label": l.get("label"), "price": l.get("price"),
                      "qty": l.get("qty")} for l in legs],
        })

    closed = [t for t in trades if t["status"] == "CLOSED"]
    n_tot = wins + losses

    # महिना-दरम्यान (MTD) आकडे — मासिक धोरण-मूल्यांकनासाठी
    mts = store.month_trades(date[:7])
    mt_closed = [t for t in mts if t["status"] == "CLOSED"]
    m_wins = sum(1 for t in mt_closed if (t["pnl"] or 0) >= 0)
    m_losses = len(mt_closed) - m_wins

    return {
        "ok": True,
        "generated_at": n.strftime("%Y-%m-%d %H:%M:%S IST"),
        "date": date,
        "mode": store.get_state("mode", "PAPER"),
        "market_open_now": (n.weekday() < 5 and
                            dtime(9, 15) <= n.time() <= dtime(15, 30)),
        "flags": {
            "killed": store.get_state("killed") == "1",
            "paused": store.get_state("paused") == "1",
            "daily_halt": store.get_state("halt_" + date) == "1",
            "token_present": bool(store.get_state("upstox_token")),
            "last_skip_note": store.get_state("blockednote_" + date),
        },
        "trades": trades,
        "summary": {
            "trades_total": len(trades),
            "trades_closed": len(closed),
            "trades_open": len(trades) - len(closed),
            "wins": wins, "losses": losses,
            "win_rate_pct": round(100.0 * wins / n_tot, 1) if n_tot else None,
            "day_pnl_net": store.today_pnl(date),
            "day_charges": store.today_charges(date),
            "total_pnl_net": store.total_pnl(),
            "total_charges": store.total_charges(),
        },
        "month": {
            "month": date[:7],
            "trades": len(mts),
            "closed": len(mt_closed),
            "wins": m_wins, "losses": m_losses,
            "win_rate_pct": round(100.0 * m_wins / len(mt_closed), 1)
                            if mt_closed else None,
            "pnl_net": round(sum((t["pnl"] or 0) for t in mt_closed), 2),
            "charges": round(sum((t["charges"] or 0) for t in mt_closed), 2),
            "gross_pnl": round(sum(
                (float(l.get("price") or 0) - float(t["entry"] or 0))
                * int(l.get("qty") or 0)
                for t in mt_closed for l in store.get_legs(t["id"])), 2),
        },
        "rules": {
            "sl_pct": SL_PCT, "tp1_pct": TP1_PCT, "tp2_pct": TARGET_PCT,
            "tp3_pct": TP3_PCT, "max_trades_per_day": MAX_TRADES_PER_DAY,
            "max_daily_loss": MAX_DAILY_LOSS, "lot_size": LOT_SIZE,
            "capital": CAPITAL, "square_off": SQUARE_OFF,
            "market_open": MARKET_OPEN, "market_close": MARKET_CLOSE,
        },
    }


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
    _fapi = None
    try:
        # prevent_thread_lock=True → launch() FastAPI app परत देतो;
        # त्यावरच /api/eval जोडून मग मुख्य थ्रेड ब्लॉक करू (जुन्या पद्धतीप्रमाणेच)
        _res = demo.launch(server_name="0.0.0.0", server_port=_port,
                           prevent_thread_lock=True)
        if isinstance(_res, tuple):
            _fapi = _res[0]
        elif _res is not None and hasattr(_res, "get"):
            _fapi = _res
        if _fapi is None:
            _fapi = getattr(demo, "app", None)
        if _fapi is not None:
            _fapi.get("/api/eval")(eval_payload)
            print("✅ /api/eval endpoint सुरू")
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        print("⚠️ /api/eval जोडण्यात अडचण (डॅशबोर्ड तरी चालेल):", repr(e))
    if _fapi is not None:
        try:
            demo.block_thread()
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        demo.launch(server_name="0.0.0.0", server_port=_port)
