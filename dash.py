"""
डॅशबोर्ड UI — "Midnight Terminal Pro"
फक्त दिसायचा भाग (HTML/CSS); डेटा store.py मधून, /api/eval अबाधित.
app.py:  gr.HTML(dash.build_dashboard()) + timer/button.
"""

from datetime import time as dtime
from datetime import datetime
from zoneinfo import ZoneInfo
import html as _h
import os
import re as _re
import secrets

import config as C
import store
from config import ist_now

IST = ZoneInfo("Asia/Kolkata")
_MONO = "'JetBrains Mono','Noto Sans Devanagari',monospace"


def _hhmm(s):
    """'2026-11-02 09:52:00' किंवा '09:52' दोन्हीतून HH:MM"""
    m = _re.search(r"(\d{1,2}:\d{2})", str(s or ""))
    return m.group(1) if m else "—"

# सिम्बॉल रंग/चिन्ह
SYM_STYLE = {
    "BANKNIFTY": {"c": "#818cf8", "icon": "🏦"},
    "NIFTY":     {"c": "#60a5fa", "icon": "🎯"},
    "SENSEX":    {"c": "#f472b6", "icon": "🗼"},
    "FINNIFTY":  {"c": "#a78bfa", "icon": "💳"},
    "COPPER":    {"c": "#fb923c", "icon": "⚡"},
    "GOLD":      {"c": "#fbbf24", "icon": "🪙"},
    "SILVER":    {"c": "#cbd5e1", "icon": "🥈"},
    "CRUDE":     {"c": "#f87171", "icon": "🛢️"},
    "NATGAS":    {"c": "#34d399", "icon": "🔥"},
}

CSS = """
footer{display:none!important}
body,gradio-container{background:#04060c!important}
.dash{font-family:'Inter','Noto Sans Devanagari','Segoe UI',sans-serif;color:#e2e8f0;
background:radial-gradient(1100px 480px at 12% -8%,rgba(99,102,241,.16),transparent 60%),
radial-gradient(900px 420px at 92% -6%,rgba(34,211,238,.11),transparent 55%),
radial-gradient(800px 460px at 50% 115%,rgba(52,211,153,.07),transparent 60%),#04060c;
min-height:100vh;padding:20px 22px 26px}
.dash *{box-sizing:border-box}
.dash .gx{background:linear-gradient(180deg,rgba(148,163,184,.07),rgba(148,163,184,.025));
border:1px solid rgba(148,163,184,.15);border-radius:18px;
box-shadow:0 12px 32px -14px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.045)}
.dash .hero{position:relative;overflow:hidden;border-radius:22px;padding:22px 26px;
display:flex;justify-content:space-between;align-items:center;gap:18px;flex-wrap:wrap;
background:linear-gradient(120deg,rgba(99,102,241,.18),rgba(14,165,233,.10) 48%,rgba(16,185,129,.12));
border:1px solid rgba(129,140,248,.28)}
.dash .hero::before{content:'';position:absolute;inset:0;
background:repeating-linear-gradient(90deg,rgba(255,255,255,.03) 0 1px,transparent 1px 46px),
repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 46px);
-webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,.8),transparent 75%);
mask-image:linear-gradient(180deg,rgba(0,0,0,.8),transparent 75%);pointer-events:none}
.dash .hleft{display:flex;gap:16px;align-items:center;z-index:1}
.dash .logo{width:56px;height:56px;border-radius:16px;display:flex;align-items:center;justify-content:center;
font-size:28px;background:linear-gradient(135deg,#6366f1,#0ea5e9);flex:none;
box-shadow:0 8px 24px -6px rgba(99,102,241,.55)}
.dash .htitle{font-size:25px;font-weight:800;letter-spacing:.3px;line-height:1.25;
background:linear-gradient(90deg,#f8fafc,#c7d2fe);-webkit-background-clip:text;background-clip:text;color:transparent}
.dash .hsub{font-size:12.5px;color:#9fb0c8;margin-top:4px;font-weight:500}
.dash .clock{text-align:right;z-index:1}
.dash .clock .t{font-family:MONOFONT;font-size:33px;font-weight:700;color:#f8fafc;letter-spacing:1px;line-height:1.05}
.dash .clock .d{font-size:12px;color:#8ea0b9;margin-top:3px;font-weight:600}
.dash .pills{display:flex;gap:9px;flex-wrap:wrap;margin-top:15px;z-index:1;position:relative}
.dash .pill{display:inline-flex;align-items:center;gap:7px;padding:6px 13px;border-radius:999px;
font-size:12px;font-weight:600;border:1px solid rgba(148,163,184,.22);color:#cbd5e1;
background:rgba(148,163,184,.06);white-space:nowrap}
.dash .pill .dot{width:8px;height:8px;border-radius:50%;flex:none}
.dash .dot.on{background:#22c55e;animation:pulse 2.2s infinite}
.dash .dot.off{background:#ef4444;box-shadow:0 0 8px rgba(239,68,68,.6)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.45)}70%{box-shadow:0 0 0 8px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
.dash .pill.paper{background:rgba(245,158,11,.13);border-color:rgba(245,158,11,.45);color:#fcd34d;position:relative;overflow:hidden}
.dash .pill.paper::after{content:'';position:absolute;top:0;left:-70%;width:45%;height:100%;
background:linear-gradient(90deg,transparent,rgba(255,255,255,.2),transparent);animation:shine 3s infinite}
@keyframes shine{to{left:140%}}
.dash .pill.ok{background:rgba(34,197,94,.11);border-color:rgba(34,197,94,.4);color:#6ee7b7}
.dash .pill.bad{background:rgba(239,68,68,.13);border-color:rgba(239,68,68,.45);color:#fca5a5}
.dash .pill.info{background:rgba(56,189,248,.11);border-color:rgba(56,189,248,.4);color:#7dd3fc}
.dash .pill.warn{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.45);color:#fcd34d}
.dash .sec{display:flex;align-items:center;gap:12px;margin:22px 0 12px}
.dash .sec .t{font-size:12.5px;font-weight:700;color:#8ea0b9;letter-spacing:1.6px}
.dash .sec .ln{flex:1;height:1px;background:linear-gradient(90deg,rgba(148,163,184,.3),transparent)}
.dash .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:13px}
.dash .kpi{padding:15px 17px;border-radius:16px;position:relative;overflow:hidden}
.dash .kpi .lab{font-size:11.5px;color:#8ea0b9;font-weight:600;letter-spacing:.3px}
.dash .kpi .val{font-family:MONOFONT;font-size:21.5px;font-weight:700;margin-top:7px;color:#f1f5f9}
.dash .kpi .sub{font-size:11px;color:#64748b;margin-top:4px}
.dash .kpi .ic{position:absolute;right:13px;top:12px;font-size:19px;opacity:.95;filter:drop-shadow(0 2px 6px rgba(0,0,0,.4))}
.dash .pos{color:#34d399!important}.dash .neg{color:#f87171!important}.dash .zer{color:#e2e8f0!important}
.dash .syms{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}
.dash .sym{padding:15px 17px 13px;border-radius:18px;position:relative;overflow:hidden;
transition:transform .16s ease,box-shadow .16s ease}
.dash .sym:hover{transform:translateY(-3px);box-shadow:0 16px 36px -14px rgba(0,0,0,.75)}
.dash .sym .acc{position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--sc);box-shadow:0 0 14px var(--sc)}
.dash .shead{display:flex;justify-content:space-between;align-items:center;gap:8px}
.dash .sname{font-size:15.5px;font-weight:700;color:#f1f5f9;display:flex;align-items:center;gap:8px}
.dash .sname .sic{font-size:17px}
.dash .segc{font-size:9.5px;font-weight:700;letter-spacing:.8px;padding:2.5px 7px;border-radius:6px;
border:1px solid rgba(148,163,184,.3);color:#94a3b8}
.dash .scap{font-size:11.5px;color:#8ea0b9;margin-top:7px}
.dash .scap b{color:#cbd5e1;font-weight:700;font-family:MONOFONT}
.dash .spnl{display:flex;align-items:baseline;gap:10px;margin-top:7px;flex-wrap:wrap}
.dash .spnl .big{font-family:MONOFONT;font-size:23px;font-weight:700}
.dash .spnl .mtd{font-size:11px;color:#64748b}
.dash .smeta{display:flex;gap:14px;align-items:center;margin-top:9px;font-size:11.5px;color:#8ea0b9;flex-wrap:wrap}
.dash .tdots{display:inline-flex;gap:4px;align-items:center}
.dash .tdots i{width:8px;height:8px;border-radius:50%;border:1.5px solid #475569;display:inline-block}
.dash .tdots i.f{background:var(--sc);border-color:var(--sc);box-shadow:0 0 6px var(--sc)}
.dash .lbar{height:5px;border-radius:99px;background:rgba(148,163,184,.13);margin-top:9px;overflow:hidden}
.dash .lbar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#f59e0b,#ef4444)}
.dash .chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.dash .chip{font-size:10px;font-weight:600;padding:3.5px 8px;border-radius:7px;color:#94a3b8;
background:rgba(148,163,184,.07);border:1px solid rgba(148,163,184,.15);white-space:nowrap}
.dash .chip.hot{color:#fda4af;border-color:rgba(244,63,94,.35);background:rgba(244,63,94,.08)}
.dash .chip.good{color:#6ee7b7;border-color:rgba(16,185,129,.3);background:rgba(16,185,129,.08)}
.dash .opstrip{margin-top:10px;padding:8px 11px;border-radius:11px;font-size:11.5px;font-weight:600;
background:rgba(34,197,94,.09);border:1px dashed rgba(34,197,94,.4);color:#86efac;font-family:MONOFONT}
.dash .haltr{margin-top:10px;padding:7px 11px;border-radius:10px;font-size:11.5px;font-weight:700;
background:rgba(239,68,68,.13);border:1px solid rgba(239,68,68,.4);color:#fca5a5}
.dash .tlwrap{padding:20px 24px 15px;display:flex}
.dash .node{flex:1;text-align:center;position:relative;min-width:0}
.dash .node:not(:first-child)::before{content:'';position:absolute;top:6px;left:-50%;width:100%;height:2px;
background:rgba(148,163,184,.16);border-radius:2px}
.dash .node.done:not(:first-child)::before{background:rgba(34,197,94,.5)}
.dash .nd{width:13px;height:13px;border-radius:50%;margin:0 auto;background:#0f172a;border:2.5px solid #3b4a63;position:relative;z-index:1}
.dash .node.done .nd{background:#22c55e;border-color:#22c55e}
.dash .node.cur .nd{background:#38bdf8;border-color:#38bdf8;box-shadow:0 0 0 5px rgba(56,189,248,.16);animation:pulse 1.8s infinite}
.dash .ntt{font-family:MONOFONT;font-size:12.5px;color:#cbd5e1;margin-top:9px;font-weight:600}
.dash .nll{font-size:10.5px;color:#64748b;margin-top:2px}
.dash .node.cur .ntt{color:#7dd3fc}
.dash .duo{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.dash .panel{padding:16px 18px;border-radius:16px}
.dash .ptitle{font-size:12px;font-weight:700;color:#8ea0b9;letter-spacing:1.2px;margin-bottom:12px}
.dash .bars{display:flex;justify-content:space-around;align-items:flex-end;height:118px;
border-bottom:1px solid rgba(148,163,184,.2);padding:0 6px}
.dash .bcol{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:5px;height:100%}
.dash .bcol .bv{font-family:MONOFONT;font-size:10.5px;font-weight:700}
.dash .bcol .bar{width:26px;border-radius:6px 6px 2px 2px}
.dash .blabels{display:flex;justify-content:space-around;padding:7px 6px 0}
.dash .blabels span{width:64px;text-align:center;font-size:10.5px;color:#8ea0b9;font-weight:600}
.dash .jr{font-family:MONOFONT;font-size:11.5px;display:flex;flex-direction:column;gap:8px}
.dash .jr .row{display:flex;gap:10px;color:#94a3b8;line-height:1.45}
.dash .jr .tm{color:#64748b;flex:none}
.dash .tblwrap{padding:6px 8px 4px;border-radius:16px;overflow:auto}
.dash table.tbl{width:100%;border-collapse:collapse;font-size:12.8px;min-width:840px}
.dash .tbl th{text-align:left;font-size:10.5px;letter-spacing:1px;text-transform:uppercase;color:#64748b;
padding:11px 13px;border-bottom:1px solid rgba(148,163,184,.16);font-weight:700}
.dash .tbl td{padding:10px 13px;border-bottom:1px solid rgba(148,163,184,.07);color:#cbd5e1}
.dash .tbl tr:last-child td{border-bottom:none}
.dash .tbl tr.oi td{background:rgba(34,197,94,.05)}
.dash .m{font-family:MONOFONT}
.dash .badge{padding:3px 10px;border-radius:7px;font-size:10.5px;font-weight:700;white-space:nowrap}
.dash .badge.open{background:rgba(34,197,94,.16);color:#4ade80;border:1px solid rgba(34,197,94,.4)}
.dash .badge.closed{background:rgba(148,163,184,.12);color:#94a3b8;border:1px solid rgba(148,163,184,.22)}
.dash .sbu{color:#4ade80;font-weight:700}.dash .sbd{color:#f87171;font-weight:700}
.dash .symdot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:1px}
.dash .empty{padding:34px 10px!important;text-align:center;color:#64748b;font-size:13px}
.dash .empty .e1{font-size:26px;margin-bottom:8px}
.dash .empty small{color:#475569}
.dash .foot{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:20px;flex-wrap:wrap}
.dash .fn{font-size:11.5px;color:#64748b}
#refresh-btn button,#refresh-btn,#refresh-btn>div{background:linear-gradient(135deg,#6366f1,#0ea5e9)!important;
color:#fff!important;border:none!important;border-radius:12px!important;font-weight:700!important;font-size:14px!important;
padding:10px 26px!important;box-shadow:0 10px 24px -8px rgba(99,102,241,.6)!important;transition:transform .15s!important}
#refresh-btn button:hover,#refresh-btn:hover{transform:translateY(-2px)!important}
@media(max-width:1100px){.dash .syms{grid-template-columns:repeat(2,1fr)}.dash .kpis{grid-template-columns:repeat(3,1fr)}}
@media(max-width:760px){.dash .syms{grid-template-columns:1fr}.dash .kpis{grid-template-columns:repeat(2,1fr)}.dash .duo{grid-template-columns:1fr}}
""".replace("MONOFONT", _MONO)

HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800'
    '&family=JetBrains+Mono:wght@500;700&family=Noto+Sans+Devanagari:wght@400;600;700;800'
    '&display=swap" rel="stylesheet">\n'
    '<script>(function(){function tick(){var el=document.getElementById("bot-clock");'
    "if(!el)return;try{el.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',"
    "hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date());}catch(e){}}"
    "setInterval(tick,1000);})();</script>"
    '<script>try{var m=location.search.match(/[?&]k=([A-Za-z0-9]+)/);'
    "if(m){document.cookie='dk='+m[1]+';path=/;max-age=2592000;SameSite=Lax';"
    "history.replaceState(null,'',location.pathname);}}catch(e){}</script>"
)


# ----------------------------------------------------------------
# गुप्त की-लॉक — डॅशबोर्ड फक्त /?k=गुप्तकी असल्यासच उघडेल
# bot.env मध्ये DASH_KEY दिल्यास तोच (रीबूटवरही टिकतो);
# नसेल तर पहिल्यांदा वापरल्यावर आपोआप नवीन तयार (state मध्ये).
# ----------------------------------------------------------------
DASH_URL = os.getenv("DASH_PUBLIC_URL", "http://130.210.62.151:7860")


def get_or_create_dash_key():
    k = (os.getenv("DASH_KEY") or "").strip()
    if k:
        return k
    k = store.get_state("dash_key")
    if not k:
        k = secrets.token_hex(8)
        store.set_state("dash_key", k)
    return k


def dashboard_link():
    """Telegram /dashkey साठी संपूर्ण तयार लिंक — एकदा उघडले की /login
    ब्राउझरमध्ये 30-दिवसांची गुप्त कुकी बसवते व स्वच्छ URL वर नेते;
    नंतर की कुठेच (अ‍ॅड्रेस बार/history/लॉग्स) दिसत नाही."""
    return DASH_URL + "/login?k=" + get_or_create_dash_key()


LOCKED_HTML = """
<div class="dash" style="display:flex;align-items:center;justify-content:center;min-height:92vh">
  <div class="gx" style="max-width:440px;padding:36px 32px;text-align:center;border-radius:20px">
    <div style="font-size:46px">🔒</div>
    <div style="font-size:19px;font-weight:800;color:#f1f5f9;margin-top:12px">खाजगी डॅशबोर्ड</div>
    <div style="font-size:13px;color:#8ea0b9;margin-top:10px;line-height:1.8">हे पान फक्त गुप्त लिंकने उघडते.<br>
    की विसरलात? Telegram बॉटवर <b style="color:#fcd34d">/dashkey</b> पाठवा —
    एकदा उघडले की ब्राउझर 30 दिवस लॉगिन लक्षात ठेवतो.</div>
  </div>
</div>"""


# ---------------------------------------------------------------- helpers
def _t(hhmm):
    h, m = str(hhmm).split(":")
    return dtime(int(h), int(m))


def _mkt_open(S, n):
    return (n.weekday() < 5 and _t(S["market_open"]) <= n.time() <= _t(S["market_close"]))


def _grp(x):
    x = str(int(abs(x)))
    if len(x) <= 3:
        return x
    head, tail = x[:-3], x[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def _inr(v, dec=0):
    """भारतीय शैली: ₹18,50,000 / −₹2,454.00"""
    neg = v < 0
    a = abs(v)
    s = _grp(round(a))
    if dec:
        s += "." + f"{a:.{dec}f}".split(".")[1]
    return ("−" if neg else "") + "₹" + s


def _cls(v):
    if abs(v) < 0.005:
        return "zer"
    return "pos" if v > 0 else "neg"


def _sign(v):
    if abs(v) < 0.005:
        return ""
    return "+" if v > 0 else "−"


def _spnl(v):
    return f'<span class="{_cls(v)}">{_sign(v)}{_inr(abs(v), 2 if abs(v) < 100 else 0)}</span>'


def _k(v):
    a = abs(v)
    s = "+" if v > 0.005 else ("−" if v < -0.005 else "")
    if a >= 100000:
        return f"{s}{a / 100000:.1f}L"
    if a >= 1000:
        return f"{s}{a / 1000:.1f}k"
    return f"{s}{a:.0f}"


def _cap_of(S):
    try:
        return float(store.get_state(S["capital_state"]) or S["capital"])
    except (TypeError, ValueError):
        return float(S["capital"])


def _sym_of(key):
    for s in C.SYMBOLS:
        if s["key"] == key:
            return s
    return None


# ---------------------------------------------------------------- भाग
def _hero(n, date):
    mode = store.get_state("mode", "PAPER")
    killed = store.get_state("killed") == "1"
    paused = store.get_state("paused") == "1"
    tok = bool(store.get_state("upstox_token"))
    tdate = store.get_state("token_date")

    mode_pill = ('<span class="pill paper">🧪 PAPER मोड — खरी ऑर्डर नाहीत</span>'
                 if mode != "LIVE" else
                 '<span class="pill bad">🔴 LIVE मोड — खरे पैसे!</span>')

    if tok and tdate == date:
        tok_pill = '<span class="pill ok"><i class="dot on"></i>Upstox टोकन आजचा ✅</span>'
    elif tok:
        tok_pill = (f'<span class="pill warn">⚠️ टोकन जुना ({tdate or "?"}) — '
                    f'Telegram वर /code पाठवा</span>')
    else:
        tok_pill = '<span class="pill bad">❌ टोकन नाही — Telegram वर /token</span>'

    bn_live = (n.weekday() < 5 and dtime(9, 15) <= n.time() <= dtime(15, 30))
    mcx_live = (n.weekday() < 5 and dtime(9, 0) <= n.time() <= dtime(23, 30))
    mkt_pills = (
        f'<span class="pill {"ok" if bn_live else "bad"}"><i class="dot {"on" if bn_live else "off"}"></i>'
        f'NSE 9:15–15:30 • {"सुरू" if bn_live else "बंद"}</span>'
        f'<span class="pill {"ok" if mcx_live else "bad"}"><i class="dot {"on" if mcx_live else "off"}"></i>'
        f'MCX 9:00–23:30 • {"सुरू" if mcx_live else "बंद"}</span>')

    flags = ""
    if killed:
        flags += '<span class="pill bad">🚨 KILL — सर्व थांबले</span>'
    if paused:
        flags += '<span class="pill warn">⏸ पॉज</span>'
    for s in C.SYMBOLS:
        if store.get_state(f"halt_{date}_{s['key']}") == "1":
            flags += f'<span class="pill bad">🛑 {s["short"]} हॉल्ट</span>'

    wd = ["सोम", "मंगळ", "बुध", "गुरु", "शुक्र", "शनि", "रवि"][n.weekday()]
    return f"""
<div class="hero gx">
  <div class="hleft">
    <div class="logo">🤖</div>
    <div>
      <div class="htitle">BankNifty + MCX AI Trading Bot</div>
      <div class="hsub">6 दरवाजे • ORB ब्रेकआउट • TP लॅडर • डिटरमिनिस्टिक रिस्क नियम • Telegram नियंत्रण</div>
    </div>
  </div>
  <div class="clock">
    <div class="t" id="bot-clock">{n.strftime('%H:%M:%S')}</div>
    <div class="d">{wd}वार, {n.strftime('%d %b %Y')} • IST</div>
  </div>
  <div class="pills">
    {mode_pill}{tok_pill}{mkt_pills}{flags}
  </div>
</div>"""


def _kpis(n, date):
    acts = C.active_symbols()
    tot_cap = sum(_cap_of(s) for s in acts)
    day = sum(store.today_pnl(date, s["key"]) for s in acts)
    day_chg = sum(store.today_charges(date, s["key"]) for s in acts)
    allp = store.total_pnl()
    chg = store.total_charges()
    rows = store.trades_today(date)
    n_open = len(store.open_trades(date))

    return f"""
<div class="kpis">
  <div class="kpi gx"><div class="ic">💼</div><div class="lab">एकूण पेपर भांडवल</div>
    <div class="val">{_inr(tot_cap)}</div><div class="sub">{len(acts)} दरवाजे • प्रत्येकी स्वतंत्र</div></div>
  <div class="kpi gx"><div class="ic">📊</div><div class="lab">आजचा निव्वल P&L</div>
    <div class="val {_cls(day)}">{_sign(day)}{_inr(abs(day))}</div>
    <div class="sub">आजचा खर्च {_inr(day_chg)}</div></div>
  <div class="kpi gx"><div class="ic">🏆</div><div class="lab">सुरुवातीपासून P&L</div>
    <div class="val {_cls(allp)}">{_sign(allp)}{_inr(abs(allp))}</div>
    <div class="sub">सर्व सिम्बॉल्स एकत्र</div></div>
  <div class="kpi gx"><div class="ic">🧾</div><div class="lab">एकूण खर्च</div>
    <div class="val" style="color:#fbbf24">{_inr(chg)}</div>
    <div class="sub">ब्रोकरेज + कर (निव्वळ P&L मध्ये वजा)</div></div>
  <div class="kpi gx"><div class="ic">🎯</div><div class="lab">आजचे ट्रेड्स</div>
    <div class="val">{len(rows)}</div>
    <div class="sub">उघडे {n_open} • पूर्ण {len(rows) - n_open}</div></div>
</div>"""


def _sym_card(S, n, date):
    st = SYM_STYLE.get(S["key"], {"c": "#818cf8", "icon": "📊"})
    cap = _cap_of(S)
    day = store.today_pnl(date, S["key"])
    chg = store.today_charges(date, S["key"])
    mts = [t for t in store.month_trades(date[:7], S["key"]) if t["status"] == "CLOSED"]
    mtd = round(sum((t["pnl"] or 0) for t in mts), 2)
    tot = store.total_pnl_symbol(S["key"])
    trs = store.trades_today(date, S["key"])
    op = store.get_open_trade(date, S["key"])
    halted = store.get_state(f"halt_{date}_{S['key']}") == "1"
    live = _mkt_open(S, n)

    dots = "".join(f'<i class="{"f" if i < len(trs) else ""}"></i>'
                   for i in range(int(S["max_trades"])))
    mkt_chip = (f'<span class="pill ok" style="padding:3px 10px;font-size:10.5px">'
                f'<i class="dot on"></i>सुरू</span>' if live else
                f'<span class="pill bad" style="padding:3px 10px;font-size:10.5px">'
                f'<i class="dot off"></i>बंद</span>')

    chips = [f"ORB {S['orb_start']}–{S['orb_end']}",
             f'<span class="chip hot">SL −{S["sl_pct"]:.0f}%</span>']
    if S["ladder"]:
        chips += [f'<span class="chip good">TP1 +{S["tp1_pct"]:.0f}% → BE</span>',
                  f"TP2 +{S['tp2_pct']:.0f}% → SL+10%",
                  f'<span class="chip good">TP3 +{S["tp3_pct"]:.0f}%</span>']
    else:
        chips += [f'<span class="chip good">+{S["tp1_pct"]:.0f}% → BE लॉक</span>',
                  f'<span class="chip good">+{S["tp2_pct"]:.0f}% → पूर्ण बुक</span>']
    chips.append(f"ऑफ {S['square_off']}")

    loss_bar = ""
    if day < 0 and S["max_daily_loss"] > 0:
        pct = min(100.0, (-day) / S["max_daily_loss"] * 100.0)
        loss_bar = (f'<div class="lbar" title="दैनिक तोटा मर्यादा '
                    f'{pct:.0f}% वापरली"><i style="width:{pct:.0f}%"></i></div>')

    opstrip = ""
    if op:
        opstrip = (f'<div class="opstrip">◉ चालू — {op["strike"]:.0f} {op["side"]} '
                   f'@ ₹{op["entry"]:.2f} • SL ₹{op["sl"]:.2f}</div>')
    halt_html = ('<div class="haltr">🛑 दैनिक तोटा मर्यादा भितली — आज पुढचे ट्रेड नाहीत</div>'
                 if halted else "")

    return f"""
<div class="sym gx" style="--sc:{st['c']}">
  <i class="acc"></i>
  <div class="shead">
    <div class="sname"><span class="sic">{st['icon']}</span>{_h.escape(S['label'])}
      <span class="segc">{S['seg']}</span></div>
    {mkt_chip}
  </div>
  <div class="scap">भांडवल <b>{_inr(cap)}</b> • लॉट {S['lot']}</div>
  <div class="spnl"><span class="big {_cls(day)}">{_sign(day)}{_inr(abs(day))}</span>
    <span class="mtd">MTD {_k(mtd)} • एकूण {_k(tot)}</span></div>
  <div class="smeta"><span class="tdots">{dots}</span> ट्रेड्स {len(trs)}/{S['max_trades']}
    <span>•</span> खर्च {_inr(chg)}</div>
  {loss_bar}{opstrip}{halt_html}
  <div class="chips">{''.join(f'<span class="chip">{c}</span>' if not c.startswith('<') else c for c in chips)}</div>
</div>"""


def _timeline(n):
    nodes = [("09:00", "MCX ओपन"), ("09:15", "NSE ओपन + ORB"),
             ("09:45", "एंट्री कार्ड्स"), ("15:05", "BN स्क्वेअर-ऑफ"),
             ("20:30", "EVAL-DAILY अहवाल"), ("23:05", "MCX स्क्वेअर-ऑफ")]
    nowm = n.strftime("%H:%M")
    holiday = n.weekday() >= 5
    out = []
    cur_set = False
    for tt, ll in nodes:
        if holiday:
            cls = ""
        elif nowm >= tt:
            cls = "done"
        elif not cur_set:
            cls, cur_set = "cur", True
        else:
            cls = ""
        out.append(f'<div class="node {cls}"><div class="nd"></div>'
                   f'<div class="ntt">{tt}</div><div class="nll">{ll}</div></div>')
    note = ('<div style="text-align:center;font-size:11px;color:#64748b;margin-top:8px">'
            '🌙 आज बाजार सुट्टी — नियम तसेच सक्रिय, सोमवारी पुढे</div>' if holiday else "")
    return ('<div class="tlwrap gx">' + "".join(out) + "</div>" + note)


def _overview(n, date):
    acts = C.active_symbols()
    vals = [(s, store.today_pnl(date, s["key"])) for s in acts]
    mx = max([abs(v) for _, v in vals] + [1.0])
    bars, labels = [], []
    for s, v in vals:
        h = 4 if abs(v) < 0.005 else max(8, int(92 * abs(v) / mx))
        col = ("linear-gradient(180deg,#34d399,#059669)" if v > 0 else
               "linear-gradient(180deg,#f87171,#b91c1c)" if v < 0 else "#475569")
        bars.append(f'<div class="bcol"><div class="bv {_cls(v)}">{_k(v)}</div>'
                    f'<div class="bar" style="height:{h}px;background:{col}"></div></div>')
        labels.append(f'<span>{_h.escape(s["short"])}</span>')
    jr_rows = []
    for e in store.last_events(7):
        tm = datetime.fromtimestamp(e["ts"], IST).strftime("%H:%M")
        jr_rows.append(f'<div class="row"><span class="tm">{tm}</span>'
                       f'<span>{_h.escape(str(e["msg"]))[:90]}</span></div>')
    if not jr_rows:
        jr_rows = '<div class="row" style="color:#475569">अजून इव्हेंट नाहीत…</div>'
    return f"""
<div class="duo">
  <div class="panel gx"><div class="ptitle">📈 आजचा P&L वितरण (प्रति सिम्बॉल)</div>
    <div class="bars">{''.join(bars)}</div>
    <div class="blabels">{''.join(labels)}</div></div>
  <div class="panel gx"><div class="ptitle">⚡ बॉट जर्नल — शेवटचे इव्हेंट</div>
    <div class="jr">{''.join(jr_rows)}</div></div>
</div>"""


def _table(date):
    rows = store.trades_today(date)
    heads = ["वेळ", "सिम्बॉल", "कॉन्ट्रॅक्ट", "SIDE", "Qty", "एंट्री", "एग्झिट",
             "निव्वळ P&L", "स्थिती"]
    trs = []
    if not rows:
        trs.append('<tr><td colspan="9" class="empty"><div class="e1">🌙</div>'
                   'आज अजून ट्रेड नाही<br><small>सिग्नल आल्यावर इथे दिसेल — '
                   'त्याच वेळी Telegram वर एंट्री कार्डही येते</small></td></tr>')
    for t in rows:
        S = _sym_of(t.get("symbol") or "BANKNIFTY")
        st = SYM_STYLE.get(t.get("symbol") or "BANKNIFTY", {"c": "#818cf8"})
        dot = f'<span class="symdot" style="background:{st["c"]}"></span>'
        side = (f'<span class="sbu">BUY</span>' if t["side"] == "BUY"
                else f'<span class="sbd">SELL</span>')
        if t["status"] == "OPEN":
            badge = '<span class="badge open">◉ चालू</span>'
            rowc = ' class="oi"'
        else:
            badge = f'<span class="badge closed">पूर्ण</span>'
            rowc = ""
        reason = (f'<div style="font-size:10px;color:#64748b;margin-top:3px">'
                  f'{_h.escape(str(t["reason"] or ""))}</div>' if t.get("reason") else "")
        pnl = (f'<span class="{_cls(t["pnl"])} m">{_sign(t["pnl"])}{_inr(abs(t["pnl"]))}</span>'
               if t["pnl"] is not None else '<span class="m">—</span>')
        trs.append(f'<tr{rowc}><td class="m">{_hhmm(t["opened"])}</td>'
                   f'<td>{dot}{_h.escape(S["short"] if S else "?")}</td>'
                   f'<td class="m">{t["strike"]:,.0f} '
                   f'<span style="color:#64748b">{"CE" if "CE" in str(t.get("option_key") or "").upper() else "PE" if "PE" in str(t.get("option_key") or "").upper() else ""}</span></td>'
                   f'<td>{side}</td><td class="m">{t["qty"]}</td>'
                   f'<td class="m">₹{t["entry"]:.2f}</td>'
                   f'<td class="m">{"₹%.2f" % t["exit"] if t["exit"] else "—"}</td>'
                   f'<td>{pnl}</td><td>{badge}{reason}</td></tr>')
    ths = "".join(f"<th>{h}</th>" for h in heads)
    return (f'<div class="tblwrap gx"><table class="tbl"><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def build_dashboard():
    n = ist_now()
    date = n.strftime("%Y-%m-%d")
    parts = [
        '<div class="dash">',
        _hero(n, date),
        '<div class="sec"><span class="t">📌 आजची स्थिती</span><span class="ln"></span></div>',
        _kpis(n, date),
        '<div class="sec"><span class="t">🚪 6 दरवाजे — प्रत्येकी स्वतंत्र भांडवल व नियम</span><span class="ln"></span></div>',
        '<div class="syms">' + "".join(_sym_card(s, n, date) for s in C.active_symbols()) + "</div>",
        '<div class="sec"><span class="t">🕒 दिवसाचे वेळापत्रक (डिटरमिनिस्टिक)</span><span class="ln"></span></div>',
        _timeline(n),
        '<div class="sec"><span class="t">📡 लाइव्ह आढावा</span><span class="ln"></span></div>',
        _overview(n, date),
        '<div class="sec"><span class="t">💹 आजचे ट्रेड्स</span><span class="ln"></span></div>',
        _table(date),
        f'<div class="foot"><div class="fn">🧪 PAPER मोड — सर्व ऑर्डर कागदी • आपोआप रिफ्रेश दर 10 सेकंद • '
        f'संपूर्ण नियंत्रण Telegram बॉटवर</div>'
        f'<div class="fn m">अपडेट: {n.strftime("%H:%M:%S")} IST</div></div>',
        "</div>",
    ]
    return "".join(parts)
