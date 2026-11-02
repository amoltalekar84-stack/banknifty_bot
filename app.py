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
import dash
import store
from config import ist_now
from datetime import datetime as _dtm, time as dtime
from engine import start_engine
from telegram_bot import start_telegram

store.init_db()
start_engine()
start_telegram()


def _market_open():
    n = ist_now()
    return ("🟢 सुरू (9:15–15:30)" if (n.weekday() < 5 and
            dtime(9, 15) <= n.time() <= dtime(15, 30)) else "🔴 बंद / सुट्टी")


def _mcx_open():
    n = ist_now()
    return ("🟢 सुरू (9:00–23:30)" if (n.weekday() < 5 and
            dtime(9, 0) <= n.time() <= dtime(23, 30)) else "🔴 बंद / सुट्टी")


# ------------------------------------------------------------------
# /api/eval — दैनिक मूल्यांकन डेटा (फक्त वाचन; कोणतीही गुप्त माहिती नाही)
# ------------------------------------------------------------------
def eval_payload(date=None, k: str = ""):
    """?date=YYYY-MM-DD (नसेल तर आज) + ?k=गुप्त-की (लागतेच).
    दिवसभरचे ट्रेड + खर्च + नियम-माहिती.
    वरचा भाग (trades/summary/month/rules) = BANKNIFTY (जुने स्वरूप अबाधित);
    "copper" block = COPPER चे स्वतंत्र आकडे."""
    if k != dash.get_or_create_dash_key():
        return {"ok": False, "error": "locked",
                "hint": "गुप्त की हवी: URL ला ?k=… जोडा (Telegram वर /dashkey)"}
    from config import (CAPITAL, LOT_SIZE, MARKET_CLOSE, MARKET_OPEN,
                        MAX_DAILY_LOSS, MAX_TRADES_PER_DAY, SL_PCT,
                        SQUARE_OFF, TARGET_PCT, TP1_PCT, TP3_PCT)
    n = ist_now()
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
        date = n.strftime("%Y-%m-%d")

    trades = []
    wins = losses = 0
    for t in store.trades_today(date, "BANKNIFTY"):
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
    mts = store.month_trades(date[:7], "BANKNIFTY")
    mt_closed = [t for t in mts if t["status"] == "CLOSED"]
    m_wins = sum(1 for t in mt_closed if (t["pnl"] or 0) >= 0)
    m_losses = len(mt_closed) - m_wins

    data = {
        "ok": True,
        "generated_at": n.strftime("%Y-%m-%d %H:%M:%S IST"),
        "date": date,
        "mode": store.get_state("mode", "PAPER"),
        "symbols": [s["key"] for s in C.active_symbols()],
        "market_open_now": (n.weekday() < 5 and
                            dtime(9, 15) <= n.time() <= dtime(15, 30)),
        "flags": {
            "killed": store.get_state("killed") == "1",
            "paused": store.get_state("paused") == "1",
            "daily_halt": any(store.get_state("halt_" + date + "_" + s["key"]) == "1"
                              for s in C.active_symbols()),
            "token_present": bool(store.get_state("upstox_token")),
            "token_date": store.get_state("token_date"),
            "last_skip_note": store.get_state("blockednote_" + date + "_BANKNIFTY"),
        },
        "trades": trades,
        "summary": {
            "trades_total": len(trades),
            "trades_closed": len(closed),
            "trades_open": len(trades) - len(closed),
            "wins": wins, "losses": losses,
            "win_rate_pct": round(100.0 * wins / n_tot, 1) if n_tot else None,
            "day_pnl_net": store.today_pnl(date, "BANKNIFTY"),
            "day_charges": store.today_charges(date, "BANKNIFTY"),
            "total_pnl_net": store.total_pnl_symbol("BANKNIFTY"),
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
    # टोकन कधी सेट झाला — निदानासाठी (सकाळी उशीर /code झाला तर ORB विंडो चुकते)
    try:
        _ts = store.get_state_ts("token_date")
        data["flags"]["token_set_at"] = (
            _dtm.fromtimestamp(_ts, ist_now().tzinfo)
            .strftime("%Y-%m-%d %H:%M:%S IST") if _ts else None)
    except Exception:
        data["flags"]["token_set_at"] = None
    # सर्व MCX सिम्बॉल्सचे स्वतंत्र ब्लॉक: copper / gold / silver / crude / natgas
    for s in C.SYMBOLS:
        if s["mcx"]:
            data[s["key"].lower()] = _sym_payload(s, date)
    # बॉट जर्नल — शेवटचे इव्हेंट (EOD रिपोर्ट/पडताळणीसाठी)
    try:
        data["events"] = [{"ts": e["ts"], "msg": str(e.get("msg", ""))}
                          for e in store.last_events(10)]
    except Exception:
        data["events"] = []
    return data


def _sym_payload(S, date):
    """एका MCX सिम्बॉलचा /api/eval ब्लॉक — स्वतंत्र भांडवल/नियम/आकडे"""
    skey = S["key"]
    if skey not in [s["key"] for s in C.active_symbols()]:
        return {"enabled": False}

    def _trades_for(rows):
        out = []
        wins_ = losses_ = 0
        for t in rows:
            legs = store.get_legs(t["id"])
            booked = sum(int(l.get("qty") or 0) for l in legs)
            entry = float(t["entry"] or 0)
            gross = round(sum((float(l["price"]) - entry) * int(l["qty"])
                              for l in legs), 2)
            pnl = t["pnl"]
            if t["status"] == "CLOSED" and pnl is not None:
                if pnl >= 0:
                    wins_ += 1
                else:
                    losses_ += 1
            out.append({
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
        return out, wins_, losses_

    rows = store.trades_today(date, skey)
    ctrades, c_wins, c_losses = _trades_for(rows)
    c_closed = [t for t in ctrades if t["status"] == "CLOSED"]

    # महिना आकडे कच्च्या rows वरून (eval-आकार नाही)
    mts = store.month_trades(date[:7], skey)
    mt_raw = [t for t in mts if t["status"] == "CLOSED"]
    m_wins = sum(1 for t in mt_raw if (t["pnl"] or 0) >= 0)
    m_losses = len(mt_raw) - m_wins

    return {
        "enabled": True,
        "flags": {
            "daily_halt": store.get_state("halt_" + date + "_" + skey) == "1",
            "last_skip_note": store.get_state("blockednote_" + date + "_" + skey),
        },
        "trades": ctrades,
        "summary": {
            "trades_total": len(ctrades),
            "trades_closed": len(c_closed),
            "trades_open": len(ctrades) - len(c_closed),
            "wins": c_wins, "losses": c_losses,
            "win_rate_pct": round(100.0 * c_wins / (c_wins + c_losses), 1)
                            if (c_wins + c_losses) else None,
            "day_pnl_net": store.today_pnl(date, skey),
            "day_charges": store.today_charges(date, skey),
            "total_pnl_net": store.total_pnl_symbol(skey),
        },
        "month": {
            "month": date[:7],
            "trades": len(mts),
            "closed": len(mt_raw),
            "wins": m_wins, "losses": m_losses,
            "win_rate_pct": round(100.0 * m_wins / len(mt_raw), 1)
                            if mt_raw else None,
            "pnl_net": round(sum((t["pnl"] or 0) for t in mt_raw), 2),
            "charges": round(sum((t["charges"] or 0) for t in mt_raw), 2),
        },
        "rules": {
            "sl_pct": S["sl_pct"], "breakeven_pct": S["tp1_pct"],
            "full_book_pct": S["tp2_pct"], "ladder": S["ladder"],
            "max_trades_per_day": S["max_trades"],
            "max_daily_loss": S["max_daily_loss"],
            "lot_size": S["lot"], "capital": S["capital"],
            "square_off": S["square_off"],
            "market_open": S["market_open"], "market_close": S["market_close"],
            "orb_range": S["orb_start"] + "–" + S["orb_end"],
        },
    }


# ------------------------------------------------------------------
# डॅशबोर्ड UI — "Midnight Terminal Pro" (dash.py मधून)
# ------------------------------------------------------------------
def _refresh():
    return dash.build_dashboard()


def _load_gate(request: gr.Request):
    """पान प्रथम उघडतानाच — URL मध्ये ?k=गुप्तकी किंवा ब्राउझरमध्ये वैध dk कुकी
    (ही फक्त /login मार्फत बसते) असल्यासच डॅशबोर्ड; नसेल तर लॉक स्क्रीन.
    परत (HTML, unlocked_flag) — flag नंतरच्या timer/refresh साठी."""
    key = dash.get_or_create_dash_key()
    try:
        qp = getattr(request, "query_params", None)
        if qp is None:
            qp = getattr(getattr(request, "request", None), "query_params", {}) or {}
        k = (qp.get("k") or "") if hasattr(qp, "get") else ""
    except Exception:
        k = ""
    if not k:
        # /login ने बसवलेली 30-दिवसांची कुकी — नंतरच्या भेटींसाठी URL शिवाय अनलॉक
        try:
            hd = getattr(request, "headers", None)
            raw = (hd.get("cookie") or "") if hasattr(hd, "get") else ""
            m = re.search(r"(?:^|;\s*)dk=([A-Za-z0-9]+)", raw)
            k = m.group(1) if m else ""
        except Exception:
            k = ""
    ok = bool(k) and k == key
    return (dash.build_dashboard() if ok else dash.LOCKED_HTML), ok


def _refresh_gate(unlocked):
    """timer/refresh — फक्त load वेळी की जुळली असल्यासच डॅशबोर्ड परत येतो"""
    return dash.build_dashboard() if unlocked else dash.LOCKED_HTML


def _make_blocks():
    """head param जुन्या Gradio मध्ये नसेल तरी डॅशबोर्ड चालण्यासाठी fallback"""
    try:
        return gr.Blocks(title="BankNifty + MCX AI Bot",
                         css=dash.CSS, head=dash.HEAD)
    except TypeError:
        return gr.Blocks(title="BankNifty + MCX AI Bot", css=dash.CSS)


with _make_blocks() as demo:
    board = gr.HTML(dash.LOCKED_HTML)          # सुरुवातीला नेहमी लॉक (की-विना डेटा नाही)
    unlocked = gr.State(False)                 # की जुळली का? (लोड वेळी ठरते)
    btn = gr.Button("🔄 रिफ्रेश", elem_id="refresh-btn")
    demo.load(_load_gate, None, [board, unlocked])
    gr.Timer(10).tick(_refresh_gate, unlocked, board)   # दर 10 सेकंदांनी — फक्त अनलॉक असल्यास
    btn.click(_refresh_gate, unlocked, board)

if __name__ == "__main__":
    # Render आपोआप PORT env var देतो; स्थानिक चाचणीसाठी 7860
    _port = int(os.environ.get("PORT", "7860"))

    def _launch(d, **kw):
        """Gradio 6: css/head launch() ला; Gradio 5: Blocks() ला — दोन्ही हाताळा"""
        try:
            return d.launch(css=dash.CSS, head=dash.HEAD, **kw)
        except TypeError:
            return d.launch(**kw)

    _fapi = None
    try:
        # prevent_thread_lock=True → launch() FastAPI app परत देतो;
        # त्यावरच /api/eval जोडून मग मुख्य थ्रेड ब्लॉक करू (जुन्या पद्धतीप्रमाणेच)
        _res = _launch(demo, server_name="0.0.0.0", server_port=_port,
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
            # /login — गुप्त की दिल्यास 30-दिवसांची HttpOnly कुकी बसवून
            # स्वच्छ URL वर redirect (म्हणजे की कधीच अ‍ॅड्रेस बार/history मध्ये राहत नाही)
            try:
                from fastapi.responses import HTMLResponse, RedirectResponse

                def _login(k: str = ""):
                    if k and k == dash.get_or_create_dash_key():
                        r = RedirectResponse("/", status_code=302)
                        r.set_cookie("dk", k, max_age=60 * 60 * 24 * 30,
                                     httponly=True, samesite="lax")
                        return r
                    return HTMLResponse(
                        "<html><head><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        "<title>लॉक</title></head>"
                        "<body style='margin:0;background:#0b0f19'>"
                        + dash.LOCKED_HTML + "</body></html>")

                _fapi.get("/login")(_login)
                print("✅ /login (कुकी-लॉगिन) endpoint सुरू")
            except Exception as e:
                print("⚠️ /login जोडण्यात अडचण:", repr(e))
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
        _launch(demo, server_name="0.0.0.0", server_port=_port)
