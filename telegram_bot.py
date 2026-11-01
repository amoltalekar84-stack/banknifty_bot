"""
टेलिग्राम बॉट — तुमचं नियंत्रण केंद्र (सर्व संदेश मराठीत).

सुरक्षा:
• फक्त ADMIN (पहिल्यांदा /start करणारा) कमांड्स चालवू शकतो
• KILL स्विच — इमर्जन्सीमध्ये सगळं थांबवा
"""

import asyncio
import queue
import threading
from datetime import time as dtime

import config as C
import store
from config import ist_now
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)
from upstox_api import UpstoxError, exchange_code, get_ltp, validate_token

NOTIFY_Q = queue.Queue()
_pending_live = {}          # chat_id → True (LIVE पुष्टी वाटत बघत आहोत)

HELP = """🤖 BankNifty AI बॉट — कमांड्स:

/start — बॉट सुरू + तुम्ही admin होता (एकदाच)
/settoken <टोकन> — थेट access token पाठवा ⭐ 🔒 संदेश आपोआप पुसला जातो
/code <कोड> — Upstox लॉगिन कोड 🔒 संदेश आपोआप पुसला जातो (पर्याय)
/status — सध्याची स्थिती
/positions — उघड्या पोझिशन्स
/trades — आजचे सर्व ट्रेड्स
/pause — नवीन ट्रेड थांबवा
/resume — पुन्हा सुरू
/kill — 🚨 इमर्जन्सी: सगळं बंद + पोझिशन बंद
/mode paper — कागदी मोड (डीफॉल्ट)
/mode live — प्रत्यक्ष पैशांचा मोड (कुलूपबंद)
/setcapital 50000 — भांडवल बदला
/help — हे मेनू"""


# ------------------------------------------------------------------
# सुरक्षा हेल्पर
# ------------------------------------------------------------------
def notify(text):
    """इंजिन → टेलिग्राम अलर्ट (थ्रेड-सेफ क्यु)"""
    NOTIFY_Q.put(text)


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
    """/settoken <टोकन> — थेट access token; संदेश आपोआप पुसला जातो 🔒"""
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    if not ctx.args:
        await update.effective_message.reply_text(
            "वापर: /settoken <access_token>\n"
            "🔒 पाठवलेला संदेश आपोआप पुसला जाईल.")
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
    mkt = ("🟢 सुरू" if (now.weekday() < 5 and
                         dtime(9, 15) <= now.time() <= dtime(15, 30)) else "🔴 बंद")
    pos = store.get_open_trade(date)
    pos_txt = (f"{pos['strike']:.0f} {pos['side']} @ ₹{pos['entry']:.2f} "
               f"(SL ₹{pos['sl']:.2f} / T ₹{pos['target']:.2f})" if pos else "—")
    txt = f"""📊 स्थिती ({now.strftime('%H:%M')} IST)
मोड: {mode} | बाजार: {mkt}
टोकन: {'✅ आहे' if tok else '❌ नाही — /code पाठवा'}
आजचे ट्रेड्स: {len(store.trades_today(date))}
आजचा P&L: ₹{store.today_pnl(date):,.0f}
सुरुवातीपासून P&L: ₹{store.total_pnl():,.0f}
पोझिशन: {pos_txt}
पॉज: {'हो' if store.get_state('paused') == '1' else 'नाही'} | KILL: {'🚨 चालू' if store.get_state('killed') == '1' else 'नाही'}"""
    await update.effective_message.reply_text(txt)


async def cmd_positions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    e = _guard(update.effective_chat.id)
    if e:
        await update.effective_message.reply_text(e)
        return
    date = ist_now().strftime("%Y-%m-%d")
    pos = store.get_open_trade(date)
    if not pos:
        await update.effective_message.reply_text("📭 सध्या कोणती पोझिशन नाही.")
        return
    tok = store.get_state("upstox_token")
    ltp_txt = ""
    if tok:
        try:
            ltp = get_ltp(pos["option_key"], tok)
            if ltp:
                unreal = (ltp - pos["entry"]) * pos["qty"]
                ltp_txt = f"\nधारमान P&L: ₹{unreal:,.0f}"
        except Exception:
            pass
    await update.effective_message.reply_text(
        f"📂 उघडी पोझिशन:\n{pos['strike']:.0f} {pos['side']} × {pos['qty']}\n"
        f"एंट्री: ₹{pos['entry']:.2f}\nSL: ₹{pos['sl']:.2f} | टार्गेट: ₹{pos['target']:.2f}"
        f"{ltp_txt}")


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
        if t["status"] == "CLOSED":
            lines.append(f"{icon} {t['strike']:.0f} {t['side']}: "
                         f"₹{t['entry']:.1f} → ₹{t['exit']:.1f} = ₹{t['pnl']:,.0f} "
                         f"({t['reason']})")
        else:
            lines.append(f"⏳ {t['strike']:.0f} {t['side']}: उघडी @ ₹{t['entry']:.1f}")
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
    pos = store.get_open_trade(date)
    msg = "🚨 KILL स्विच चालू!\nइंजिन पुढील 30 सेकंदांत उघडी पोझिशन बंद करेल व नवीन ट्रेड नाही."
    if pos:
        msg += f"\n⚠️ उघडी पोझिशन: {pos['strike']:.0f} {pos['side']} @ ₹{pos['entry']:.2f}"
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
        await update.effective_message.reply_text("वापर: /setcapital 50000")
        return
    try:
        val = float(ctx.args[0].replace(",", ""))
        if val < 10000:
            raise ValueError
        store.set_state("capital", str(val))
        await update.effective_message.reply_text(f"✅ भांडवल ₹{val:,.0f} सेट झाले.")
    except ValueError:
        await update.effective_message.reply_text("अवैध रक्कम — उदा. /setcapital 50000")


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
    """क्युमधले अलर्ट टेलिग्रामला पाठवत राहा"""
    loop = asyncio.get_running_loop()
    while True:
        text = await loop.run_in_executor(None, NOTIFY_Q.get)
        a = _admin_id()
        if not a:
            continue
        try:
            await app.bot.send_message(chat_id=a, text=text)
        except Exception as ex:
            print("TG send fail:", repr(ex))


async def _serve():
    app = Application.builder().token(C.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("token", cmd_token))
    app.add_handler(CommandHandler("settoken", cmd_token))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("setcapital", cmd_setcapital))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print("Telegram bot polling started")
    asyncio.create_task(_drain(app))
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
