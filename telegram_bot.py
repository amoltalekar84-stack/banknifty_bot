"""
टेलिग्राम बॉट — तुमचं नियंत्रण केंद्र (सर्व संदेश मराठीत).

सुरक्षा:
• फक्त ADMIN (पहिल्यांदा /start करणारा) कमांड्स चालवू शकतो
• KILL स्विच — इमर्जन्सीमध्ये सगळं थांबवा
"""

import asyncio
import queue
import threading
import urllib.parse
from datetime import datetime as dtm, time as dtime

import config as C
import dash
import paper
import store
from config import ist_now
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)
from upstox_api import UpstoxError, exchange_code, get_ltp, validate_token

NOTIFY_Q = queue.Queue()
_pending_live = {}          # chat_id → True (LIVE पुष्टी वाटत बघत आहोत)


def _t(s):
    """'09:15' → time(9,15)"""
    h, m = s.split(":")
    return dtime(int(h), int(m))

HELP = """🤖 BankNifty + Copper AI बॉट — कमांड्स:

/start — बॉट सुरू + तुम्ही admin होता (एकदाच)
/token — आजची लॉग-इन लिंक मागा (रोज सकाळी पहिले पाऊल)
/code <कोड> — लिंकमधून मिळालेला कोड → बॉट स्वतः टोकन बनवतो ⭐ 🔒 आपोआप पुसला जातो
/settoken <टोकन> — थेट access token (बॅकअप पर्याय) 🔒 आपोआप पुसला जातो
/status — सध्याची स्थिती (दोन्ही सिम्बॉल्स)
/dashkey — डॅशबोर्डचा गुप्त लिंक 🔒 60 सेकंदांत आपोआप पुसला जातो
/positions — उघड्या पोझिशन्स (BANKNIFTY + COPPER)
/trades — आजचे सर्व ट्रेड्स
/eod — आजचा दिवस-समाप्ती अहवाल (🌙 रात्री 23:10 ला आपोआपही येतो)
/pause — नवीन ट्रेड थांबवा (दोन्ही)
/resume — पुन्हा सुरू
/kill — 🚨 इमर्जन्सी: सगळं बंद + पोझिशन बंद
/mode paper — कागदी मोड (डीफॉल्ट)
/mode live — प्रत्यक्ष पैशांचा मोड (कुलूपबंद)
/setcapital 50000 — BANKNIFTY भांडवल बदला
/setcapitalcu 200000 — COPPER भांडवल बदला
/setcapitalgold 800000 — GOLD भांडवल बदला
/setcapitalsilver 500000 — SILVER भांडवल बदला
/setcapitalcrude 200000 — CRUDE भांडवल बदला
/setcapitalng 100000 — NATGAS भांडवल बदला
(सर्व भांडवले स्वतंत्र — एकमेकांना स्पर्श नाहीत)
/backtest 30 — जुन्या डेटावर धोरणाची चाचणी (सर्व खर्चांसह) 🧪
/help — हे मेनू"""


# ------------------------------------------------------------------
# सुरक्षा हेल्पर
# ------------------------------------------------------------------
def notify(text, html=False):
    """इंजिन → टेलिग्राम अलर्ट (थ्रेड-सेफ क्यु); html=True असल्यास सुंदर कार्ड"""
    NOTIFY_Q.put((text, bool(html)))


async def _vanish(update: Update):
    """🔒 टोकन/कोड असलेला संदेश चॅटमधून लगेच पुसा — इतिहासात काही शिल्लक राहणार नाही"""
    try:
        await update.effective_message.delete()
    except Exception:
        pass


def _admin_id():
    a = C.ADMIN_CHAT_ID or 0
    if not a:
        try:
            a = int(store.get_state("admin_chat_id") or 0)
        except (TypeError, ValueError):
            a = 0
    return a


def _guard(chat_id):
    """कमांड admin साठीच आहे का?"""
    a = _admin_id()
    if a == 0:
        return "प्रथम /start पाठवा — पहिलाच वापरकर्ता admin होतो."
    if chat_id != a:
        return "⛔ ही कमांड फक्त admin साठी आहे."
    return ""


# ------------------------------------------------------------------
# कमांड हँडलर
# ------------------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    a = _admin_id()
    if a == 0:
        store.set_state("admin_chat_id", str(cid))
        store.log_event(f"admin registered: {cid}")
        await update.effective_message.reply_text(
            "✅ तुम्ही या बॉटचे ADMIN आहात!\n"
            "आता सेटअप पूर्ण करा: रोज सकाळी /code पाठवा.\n\n" + HELP)
    elif cid != a:
        await update.effective_message.reply_text(
            "⛔ हा बॉट खाजगी आहे. तुमचा बॉट बनवण्यासाठी README पहा.")
    else:
        await update.effective_message.reply_text(HELP)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    await update.effective_message.reply_text(HELP)


async def cmd_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """रोजचा लॉगिन कोड → टोकन ऑटो तयार"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    if not ctx.args:
        await update.effective_message.reply_text(
            "वापर: /code XXXXXX\n"
            "सकाळी Upstox लॉगिन केल्यावर ब्राउजर URL मधून code कॉपी करा "
            "(README पायरी 4 पहा).")
        return
    if not (C.UPSTOX_CLIENT_ID and C.UPSTOX_CLIENT_SECRET and C.UPSTOX_REDIRECT_URI):
        await update.effective_message.reply_text(
            "⚠️ bot.env मध्ये UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, "
            "UPSTOX_REDIRECT_URI सेट करा (server वर).")
        return
    code = ctx.args[0].strip()
    await _vanish(update)          # 🔒 कोड चॅटमधून गायब
    prog = await update.effective_message.reply_text("⏳ टोकन मिळवत आहे...")
    loop = asyncio.get_running_loop()
    try:
        tok = await loop.run_in_executor(
            None, exchange_code, code,
            C.UPSTOX_CLIENT_ID, C.UPSTOX_CLIENT_SECRET, C.UPSTOX_REDIRECT_URI)
        ok, who = await loop.run_in_executor(None, validate_token, tok)
        if not ok:
            await prog.edit_text("❌ टोकन अवैध: " + str(who)[:200])
            return
        store.set_state("upstox_token", tok)
        store.set_state("token_date", ist_now().strftime("%Y-%m-%d"))
        await prog.edit_text(
            f"✅ टोकन सेट झाला! स्वागत {who}\n"
            f"आज बॉट स्वयंचलित ट्रेड करेल "
            f"({store.get_state('mode', 'PAPER')} मोड).\n"
            "🔔 ENTRY/EXIT अलर्ट इथेच येतील.\n"
            "🔒 कोड चॅटमधून आपोआप पुसला गेला.")
    except UpstoxError as ex:
        await prog.edit_text(
            "❌ अयशस्वी: " + str(ex)[:250] +
            "\n\n💡 लक्षात ठेवा: एक code एकदाच वापरता येते — "
            "नवीन लॉगिन URL उघडा व नवीन code घ्या.")


async def cmd_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/token (रिकामा) → आजची लॉग-इन लिंक;  /settoken <टोकन> → थेट access token 🔒"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    if not ctx.args:
        # रोजच्या /code पद्धतीसाठी लॉग-इन लिंक स्वतः पाठवा
        if not (C.UPSTOX_CLIENT_ID and C.UPSTOX_REDIRECT_URI):
            await update.effective_message.reply_text(
                "⚠️ लॉग-इन लिंक साठी server वर bot.env मध्ये UPSTOX_CLIENT_ID "
                "व UPSTOX_REDIRECT_URI हवे आहेत.\n"
                "किंवा थेट टोकन पाठवा: /settoken <access_token>")
            return
        link = ("https://api.upstox.com/v2/login/authorization/dialog"
                "?client_id=" + urllib.parse.quote(C.UPSTOX_CLIENT_ID, safe="") +
                "&redirect_uri=" + urllib.parse.quote(C.UPSTOX_REDIRECT_URI, safe="") +
                "&response_type=code")
        await update.effective_message.reply_text(
            "☀️ आजची लॉग-इन लिंक:\n" + link + "\n\n"
            "1) लिंक उघडा → Upstox लॉग-इन + OTP\n"
            "2) त्यानंतर ब्राउझरच्या URL मध्ये code=XXXXXX असा भाग दिसेल — "
            "फक्त code= नंतरचा भाग कॉपी करा\n"
            "3) इथे पाठवा: /code XXXXXX\n"
            "मग बॉट स्वतः टोकन बनवेल व तपासेल.")
        return
    tok = ctx.args[0].strip()
    await _vanish(update)          # 🔒 टोकन चॅटमधून गायब!
    prog = await update.effective_message.reply_text("⏳ तपासत आहे...")
    loop = asyncio.get_running_loop()
    ok, who = await loop.run_in_executor(None, validate_token, tok)
    if not ok:
        await prog.edit_text("❌ टोकन अवैध: " + str(who)[:200])
        return
    store.set_state("upstox_token", tok)
    store.set_state("token_date", ist_now().strftime("%Y-%m-%d"))
    await prog.edit_text(
        f"✅ टोकन सेट! स्वागत {who}\nबॉट स्वयंचलित ट्रेड करेल.\n"
        "🔒 टोकन चॅटमधून आपोआप पुसला गेला.")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    now = ist_now()
    date = now.strftime("%Y-%m-%d")
    mode = store.get_state("mode", "PAPER")
    tok = store.get_state("upstox_token")
    import config as _C
    lines = [f"📊 स्थिती ({now.strftime('%H:%M')} IST)",
             f"मोड: {mode} | टोकन: {'✅ आहे' if tok else '❌ नाही — /code पाठवा'}",
             f"पॉज: {'हो' if store.get_state('paused') == '1' else 'नाही'} | "
             f"KILL: {'🚨 चालू' if store.get_state('killed') == '1' else 'नाही'}"]
    for S in _C.active_symbols():
        mkt = ("🟢 सुरू" if (now.weekday() < 5 and
                             _t(S["market_open"]) <= now.time() <= _t(S["market_close"]))
               else "🔴 बंद")
        pos = store.get_open_trade(date, S["key"])
        pos_txt = (f"{pos['strike']:.0f} {pos['side']} @ ₹{pos['entry']:.2f} "
                   f"(SL ₹{pos['sl']:.2f})" if pos else "—")
        lines.append(
            f"\n▪ <b>{S['label']}</b> {mkt}\n"
            f"  आजचे ट्रेड्स: {len(store.trades_today(date, S['key']))} | "
            f"आजचा निव्वल: ₹{store.today_pnl(date, S['key']):,.0f}\n"
            f"  पोझिशन: {pos_txt} | सुरुवातीपासून: "
            f"₹{store.total_pnl_symbol(S['key']):,.0f}")
    lines.append(f"\nएकूण (सर्व सिम्बॉल्स) निव्वल P&L: ₹{store.total_pnl():,.0f} "
                 f"(खर्च ₹{store.total_charges():,.0f})")
    try:
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="HTML")
    except Exception:
        # HTML नाकारल्यास टॅग्ज काढून साधा मजकूर पाठवा
        import re as _re
        await update.effective_message.reply_text(
            _re.sub(r"</?b>", "", "\n".join(lines)))


async def _vanish_later(bot, chat_id, message_id, delay=60):
    """🔒 पाठवलेला संदेश थोड्या वेळाने चॅटमधून आपोआप पुसा"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def cmd_dashkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/dashkey — डॅशबोर्डचा गुप्त लिंक; 🔒 60 सेकंदांत आपोआप पुसला जातो"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    link = dash.dashboard_link()
    msg = await update.effective_message.reply_text(
        "🔐 डॅशबोर्डचा गुप्त लिंक — एकदाच टॅप करा:\n\n"
        + link + "\n\n"
        "✅ उघडताच ब्राउझर 30 दिवस लॉगिन लक्षात ठेवतो — नंतर साधा पत्ता टाइप करूनही "
        "डॅशबोर्ड उघडेल (की URL मध्ये दिसत नाही).\n"
        "🔒 हा संदेश 60 सेकंदांत आपोआप पुसला जाईल.\n"
        "💡 पुन्हा हवा असेल तर /dashkey पाठवा.")
    asyncio.create_task(
        _vanish_later(ctx.bot, msg.chat_id, msg.message_id, 60))


# ------------------------------------------------------------------
# 🌙 EOD — दिवस-समाप्ती अहवाल (कमांड + रात्री 23:10 ला आपोआप)
# ------------------------------------------------------------------
_WD = ("सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार")


def _inrn(v):
    """₹ फॉरमॅट — नकारी असल्यास −₹810 असा (मायनस ₹ च्या आधी)"""
    v = float(v or 0)
    return ("−₹" if v < 0 else "₹") + f"{abs(v):,.0f}"


def _eod_text(date=None):
    """सर्व सक्रिय सिम्बॉल्सचा दिवस-समाप्ती सारांश (HTML मजकूर)"""
    n = ist_now()
    date = date or n.strftime("%Y-%m-%d")
    try:
        wd = _WD[dtm.strptime(date, "%Y-%m-%d").weekday()]
    except ValueError:
        wd = _WD[n.weekday()]
    mode = store.get_state("mode", "PAPER")
    tok_date = store.get_state("token_date")
    flags = []
    if store.get_state("killed") == "1":
        flags.append("🚨 KILL")
    if store.get_state("paused") == "1":
        flags.append("⏸ पॉज")
    lines = [f"🌙 <b>EOD अहवाल — {date} ({wd})</b>",
             f"मोड: {mode} | टोकन: "
             + ("✅ आजचा" if tok_date == date else "⚠️ जुना/नाही — उद्या /code विसरू नको")
             + ((" | " + " ".join(flags)) if flags else "")]
    day_tot = 0.0
    for S in C.active_symbols():
        d = store.today_pnl(date, S["key"])
        chg = store.today_charges(date, S["key"])
        trs = store.trades_today(date, S["key"])
        closed = [t for t in trs if t["status"] == "CLOSED"]
        w = sum(1 for t in closed if (t["pnl"] or 0) >= 0)
        l = len(closed) - w
        op = store.get_open_trade(date, S["key"])
        halt = store.get_state(f"halt_{date}_{S['key']}") == "1"
        mts = [t for t in store.month_trades(date[:7], S["key"])
               if t["status"] == "CLOSED"]
        mtd = sum((t["pnl"] or 0) for t in mts)
        tot = store.total_pnl_symbol(S["key"])
        day_tot += d
        icon = "🟢" if d > 0 else ("🔴" if d < 0 else "⚪")
        lines.append(
            f"\n{icon} <b>{S['label']}</b>"
            + (" ⛔ दैनिक-हॉल्ट" if halt else "")
            + (f"\n   ट्रेड {len(trs)} | जिंक {w} • हरले {l}"
               f" | दिवस {_inrn(d)} (खर्च ₹{chg:,.0f})"
               if trs else "\n   ट्रेड 0 | दिवस ₹0")
            + ("\n   ⚠️ पोझिशन अजून OPEN!" if op else "\n   सर्व पोझिशन बंद ✅")
            + f"\n   MTD {_inrn(mtd)} | सुरुवातीपासून {_inrn(tot)}")
    lines.append(f"\n💰 <b>आजचे एकूण निव्वल: {_inrn(day_tot)}</b>"
                 f" | सर्वकालीन: {_inrn(store.total_pnl())}"
                 f" (खर्च ₹{store.total_charges():,.0f})")
    lines.append("🤖 सर्व स्क्वेअर-ऑफ नियमांनुसार पार पडले — उद्या सकाळी टोकन रिन्यू विसरू नको!")
    return "\n".join(lines)


async def cmd_eod(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/eod — आजचा दिवस-समाप्ती अहवाल तत्काळ"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    txt = _eod_text()
    try:
        await update.effective_message.reply_text(txt, parse_mode="HTML")
    except Exception:
        await update.effective_message.reply_text(txt)


async def _eod_loop(app):
    """🌙 रोज रात्री 23:10 IST (सर्व स्क्वेअर-ऑफ नंतर) — EOD अहवाल आपोआप"""
    while True:
        try:
            n = ist_now()
            if n.weekday() < 5 and n.hour == 23 and n.minute >= 10:
                date = n.strftime("%Y-%m-%d")
                if store.get_state("eod_sent_" + date) != "1":
                    a = _admin_id()
                    if a:
                        txt = _eod_text(date)
                        sent = False
                        try:
                            await app.bot.send_message(chat_id=a, text=txt,
                                                       parse_mode="HTML")
                            sent = True
                        except Exception:
                            try:
                                await app.bot.send_message(chat_id=a, text=txt)
                                sent = True
                            except Exception as ex2:
                                print("EOD send fail:", repr(ex2))
                        if sent:
                            store.set_state("eod_sent_" + date, "1")
                            store.log_event("🌙 EOD अहवाल आपोआप पाठवला")
        except Exception as e:
            print("EOD loop err:", repr(e))
        await asyncio.sleep(60)


async def cmd_positions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    date = ist_now().strftime("%Y-%m-%d")
    pos_all = store.open_trades(date)
    if not pos_all:
        await update.effective_message.reply_text("📭 सध्या कोणती पोझिशन नाही.")
        return
    tok = store.get_state("upstox_token")
    import config as _C
    smap = {s["key"]: s for s in _C.active_symbols()}
    for pos in pos_all:
        S = smap.get(pos.get("symbol"), _C.BANKNIFTY)
        legs = store.get_legs(pos["id"])
        booked = sum(int(l.get("qty") or 0) for l in legs)
        rem = int(pos["qty"]) - booked
        tp1, tp2, tp3 = paper.tp_prices(pos["entry"], S)
        leg_txt = ""
        if legs:
            leg_txt = "\n📖 बुक झालेले भाग:" + "".join(
                f"\n  ✅ {l.get('label')}: ₹{float(l['price']):.2f} × {int(l['qty'])}"
                for l in legs)
        ltp_txt = ""
        if tok:
            try:
                ltp = get_ltp(pos["option_key"], tok)
                if ltp:
                    unreal = (ltp - pos["entry"]) * rem if rem else 0
                    ltp_txt = (f"\n📍 LTP: ₹{ltp:.2f} | उर्वरित भागाचा धारमान "
                               f"P&L: ₹{unreal:,.0f}")
            except Exception:
                pass
        if S.get("ladder"):
            tp_line = f"🎯 TP1 ₹{tp1:.2f} | TP2 ₹{tp2:.2f} | TP3 ₹{tp3:.2f}"
        else:
            tp_line = f"🎯 +20% वर SL breakeven | +40% ₹{tp2:.2f} पूर्ण बुकिंग"
        await update.effective_message.reply_text(
            f"📂 उघडी पोझिशन — {S['label']}:\n"
            f"{pos['strike']:.0f} {pos['side']} — एंट्री ₹{pos['entry']:.2f} × {pos['qty']}\n"
            f"📦 उर्वरित: {rem} | बुक: {booked}\n"
            f"🛑 SL: ₹{pos['sl']:.2f}\n"
            f"{tp_line}"
            f"{leg_txt}{ltp_txt}")


async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    date = ist_now().strftime("%Y-%m-%d")
    ts = store.trades_today(date)
    if not ts:
        await update.effective_message.reply_text("📭 आज अजून कोणता ट्रेड झाला नाही.")
        return
    lines = [f"📋 आजचे ट्रेड्स ({len(ts)}):"]
    for t in ts:
        icon = "✅" if (t["pnl"] or 0) >= 0 else "❌"
        sym = (t.get("symbol") or "BANKNIFTY")
        if t["status"] == "CLOSED":
            lines.append(f"{icon} [{sym}] {t['strike']:.0f} {t['side']}: "
                         f"₹{t['entry']:.1f} → ₹{t['exit']:.1f} = निव्वळ ₹{t['pnl']:,.0f} "
                         f"(खर्च ₹{(t['charges'] or 0):,.0f}) ({t['reason']})")
        else:
            lines.append(f"⏳ [{sym}] {t['strike']:.0f} {t['side']}: उघडी @ ₹{t['entry']:.1f}")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    store.set_state("paused", "1")
    await update.effective_message.reply_text(
        "⏸ बॉट पॉज झाला — नवीन एंट्री नाहीत. उघडी पोझिशन असल्यास ती सामान्यपणे "
        "मॅनेज होईल. सुरू करण्यासाठी /resume")


async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    store.set_state("paused", "0")
    store.set_state("killed", "0")
    await update.effective_message.reply_text("▶️ बॉट पुन्हा सुरू!")


async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    store.set_state("killed", "1")
    date = ist_now().strftime("%Y-%m-%d")
    pos_all = store.open_trades(date)
    msg = "🚨 KILL स्विच चालू!\nइंजिन पुढील 30 सेकंदांत उघड्या पोझिशन्स बंद करेल व नवीन ट्रेड नाही."
    for pos in pos_all:
        msg += (f"\n⚠️ [{pos.get('symbol') or 'BANKNIFTY'}] उघडी पोझिशन: "
                f"{pos['strike']:.0f} {pos['side']} @ ₹{pos['entry']:.2f}")
    msg += "\nपरत सुरू करण्यासाठी: /resume"
    notify("🚨 KILL दाबला गेला — इंजिन स्क्वेअर-ऑफ करत आहे...")
    await update.effective_message.reply_text(msg)


async def cmd_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    if not ctx.args:
        await update.effective_message.reply_text(
            f"सध्याचा मोड: {store.get_state('mode', 'PAPER')}\n"
            "वापर: /mode paper किंवा /mode live")
        return
    want = ctx.args[0].strip().upper()
    if want == "PAPER":
        store.set_state("mode", "PAPER")
        await update.effective_message.reply_text("✅ मोड: PAPER (कागदी ट्रेडिंग — सुरक्षित)")
    elif want == "LIVE":
        if not C.ALLOW_LIVE:
            await update.effective_message.reply_text(
                "🚫 LIVE मोड कुलूपबंद आहे.\n"
                "चालू करण्यासाठी Space Secrets मध्ये ALLOW_LIVE=YES टाका "
                "(README पायरी 7 पहा).\n"
                "💡 कमीत कमी 4 आठवडे PAPER मध्ये यश मिळाल्याशिवाय live करू नका!")
            return
        _pending_live[update.effective_chat.id] = True
        await update.effective_message.reply_text(
            "⚠️ धोका पुष्टीकरण:\n"
            "LIVE मोडमध्ये प्रत्यक्ष पैसे धोक्यात येतात. "
            "नफ्याची हमी नाही.\n\nपुष्टीसाठी हे वाक्य टाइप करा:\n"
            f"「{C.LIVE_CONFIRM_TEXT}」\n\n(रद्द करण्यासाठी काहीही दुसरं पाठवा)")
    else:
        await update.effective_message.reply_text("वापर: /mode paper किंवा /mode live")


async def cmd_setcapital(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    if not ctx.args:
        await update.effective_message.reply_text("वापर: /setcapital 50000 (BANKNIFTY)")
        return
    try:
        val = float(ctx.args[0].replace(",", ""))
        if val < 10000:
            raise ValueError
        store.set_state("capital_BANKNIFTY", str(val))
        store.set_state("capital", str(val))   # जुने key पण अपडेट (सुसंगतता)
        await update.effective_message.reply_text(
            f"✅ BANKNIFTY भांडवल ₹{val:,.0f} सेट झाले.\n"
            f"(COPPER बदलण्यासाठी: /setcapitalcu 200000)")
    except ValueError:
        await update.effective_message.reply_text("अवैध रक्कम — उदा. /setcapital 50000")


async def cmd_setcapitalcu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """COPPER चे स्वतंत्र भांडवल (डीफॉल्ट ₹2,00,000 — MCX lot 2500 kg असल्याने)"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    if not ctx.args:
        await update.effective_message.reply_text(
            "वापर: /setcapitalcu 200000\n"
            "(Copper 1 लॉट = 2500 kg; ATM ऑप्शन ~₹75,000+ असल्याने "
            "₹2 लाख शिफारसीय)")
        return
    try:
        val = float(ctx.args[0].replace(",", ""))
        if val < 50000:
            raise ValueError
        store.set_state("capital_COPPER", str(val))
        await update.effective_message.reply_text(
            f"✅ COPPER भांडवल ₹{val:,.0f} सेट झाले (स्वतंत्र — BANKNIFTY ला स्पर्श नाही).")
    except ValueError:
        await update.effective_message.reply_text("अवैध रक्कम — उदा. /setcapitalcu 200000")


def _mk_cap_cmd(S):
    """MCX सिम्बॉलसाठी /setcapital<सिम्बॉल> हँडलर तयार करा (स्वतंत्र भांडवल)"""
    cmd = "setcapital" + S["short"].lower()

    async def _cap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        e = _guard(update.effective_chat.id)
        if e:
            await update.effective_message.reply_text(e)
            return
        if not ctx.args:
            await update.effective_message.reply_text(
                f"वापर: /{cmd} {int(S['capital'])}\n"
                f"({S['label']} स्वतंत्र भांडवल; डीफॉल्ट ₹{S['capital']:,.0f} — "
                f"दैनिक तोटा मर्यादा 5% = ₹{S['max_daily_loss']:,.0f})")
            return
        try:
            val = float(ctx.args[0].replace(",", ""))
            if val < 50000:
                raise ValueError
            store.set_state(S["capital_state"], str(val))
            await update.effective_message.reply_text(
                f"✅ {S['label']} भांडवल ₹{val:,.0f} सेट झाले "
                "(स्वतंत्र — इतर सिम्बॉल्सना स्पर्श नाही).")
        except ValueError:
            await update.effective_message.reply_text(
                f"अवैध रक्कम — उदा. /{cmd} {int(S['capital'])}")

    _cap.__name__ = "cmd_" + cmd
    return _cap


async def cmd_backtest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/backtest [दिवस] — ORB धोरण जुन्या खऱ्या डेटावर चालवा (सर्व खर्चांसह)"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    tok = store.get_state("upstox_token")
    if not tok:
        await update.effective_message.reply_text(
            "❌ टोकन नाही — आधी /settoken पाठवा.\n"
            "(बॅकटेस्टला Upstox चा खरा डेटा लागतो)")
        return
    days = 30
    if ctx.args:
        try:
            days = int(ctx.args[0])
        except (TypeError, ValueError):
            await update.effective_message.reply_text("वापर: /backtest 30")
            return
    prog = await update.effective_message.reply_text(
        f"⏳ बॅकटेस्ट चालू ({days} दिवस)...\n"
        "1-2 मिनिटं लागू शकतात — प्रत्येक दिवसाचा खरा डेटा आणला जातो आहे.")
    loop = asyncio.get_running_loop()
    import backtest
    try:
        txt, _csv = await loop.run_in_executor(
            None, lambda: backtest.run(days=days))
        await prog.edit_text(txt)
    except UpstoxError as ex:
        if "TOKEN_INVALID" in str(ex):
            store.set_state("upstox_token", "")
            await prog.edit_text("❌ टोकन संपले — नवीन /settoken पाठवा")
        else:
            await prog.edit_text("❌ बॅकटेस्ट अयशस्वी: " + str(ex)[:250])
    except Exception as ex:
        await prog.edit_text("❌ बॅकटेस्ट त्रुटी: " + repr(ex)[:250])


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """साधा मजकूर — LIVE पुष्टी तपासा"""
    chat_id = update.effective_chat.id
    text = (update.effective_message.text or "").strip()
    if _pending_live.get(chat_id):
        _pending_live.pop(chat_id, None)
        if text == C.LIVE_CONFIRM_TEXT and _guard(chat_id) == "":
            store.set_state("mode", "LIVE")
            notify("🔴 मोड बदलला: LIVE (प्रत्यक्ष पैसे)\n"
                   "सुरक्षा: 1 lot फक्त | दैनिक तोटा मर्यादा चालू | 15:05 स्क्वेअर-ऑफ")
            await update.effective_message.reply_text(
                "🔴 LIVE मोड चालू!\n⚠️ आता ट्रेड प्रत्यक्ष खात्यात होतील.\n"
                "परत कागदी करण्यासाठी: /mode paper")
        else:
            await update.effective_message.reply_text("❌ रद्द झाले — मोड बदलला नाही.")
        return
    if not text.startswith("/"):
        await update.effective_message.reply_text(
            "🤖 मला कमांड्स पाठवा — मेनूसाठी /help टाइप करा.")


# ------------------------------------------------------------------
# बॅकग्राउंड सर्व्हिस
# ------------------------------------------------------------------
async def _drain(app):
    """क्युमधले अलर्ट टेलिग्रामला पाठवत राहा (HTML कार्डांसह)"""
    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, NOTIFY_Q.get)
        if isinstance(item, tuple):
            text, html_mode = item
        else:                      # जुन्या सवयी प्रमाणे साधा मजकूर
            text, html_mode = item, False
        a = _admin_id()
        if not a:
            continue
        try:
            await app.bot.send_message(
                chat_id=a, text=text,
                parse_mode="HTML" if html_mode else None)
        except Exception as ex:
            # HTML नाकारले गेल्यास साधा मजकूर म्हणून पुन्हा प्रयत्न
            try:
                await app.bot.send_message(chat_id=a, text=text)
            except Exception as ex2:
                print("TG send fail:", repr(ex), repr(ex2))


async def _serve():
    app = Application.builder().token(C.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("token", cmd_token))
    app.add_handler(CommandHandler("settoken", cmd_token))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("dashkey", cmd_dashkey))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("eod", cmd_eod))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("setcapital", cmd_setcapital))
    app.add_handler(CommandHandler("setcapitalcu", cmd_setcapitalcu))
    for _S in C.SYMBOLS:
        if _S["mcx"] and _S["key"] != "COPPER":
            app.add_handler(CommandHandler(
                "setcapital" + _S["short"].lower(), _mk_cap_cmd(_S)))
    app.add_handler(CommandHandler("backtest", cmd_backtest))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print("Telegram bot polling started")
    asyncio.create_task(_drain(app))
    asyncio.create_task(_eod_loop(app))   # 🌙 रात्री 23:10 ला आपोआप EOD
    while True:
        await asyncio.sleep(3600)


def start_telegram():
    if not C.BOT_TOKEN:
        print("⚠️ BOT_TOKEN नाही — टेलिग्राम बंद; फक्त डॅशबोर्ड चालेल")
        return
    threading.Thread(target=_run, daemon=True, name="telegram").start()


def _run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_serve())
