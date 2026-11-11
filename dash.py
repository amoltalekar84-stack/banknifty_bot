"""
डॅशबोर्ड UI — "Midnight Terminal Pro"
फक्त दिसायचा भाग (HTML/CSS); डेटा store.py मधून, /api/eval अबाधित.
app.py:  gr.HTML(dash.build_dashboard()) + timer/button.
"""

from datetime import time as dtime
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo
import calendar
import csv as _csv
import html as _h
import os
import re as _re
import secrets
import tempfile
import time

import config as C
import store
from config import ist_now

try:
    import swing
except Exception:                                  # module नसेल तरी डॅश चालणार
    swing = None

try:
    import family
except Exception:                                  # module नसेल तरी डॅश चालणार
    family = None

try:
    import ai_brain                                # 🧠 रात्रीचा सल्लागार-विश्लेषक
except Exception:                                  # module नसेल तरी डॅश चालणार
    ai_brain = None

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

FAM_STYLE = {
    "F1": {"c": "#f59e0b", "icon": "🪙"},
    "F2": {"c": "#22d3ee", "icon": "🎯"},
    "F3": {"c": "#a78bfa", "icon": "📏"},
    "F4": {"c": "#34d399", "icon": "⚙️"},
}

# ------------------------------------------------------------------
# 🎨 डॅश-थीम इंजिन — "रंगांची भाषा बदलते, आकार नाही"
# ------------------------------------------------------------------
# यंत्रणा (super-mind): build_dashboard() च्या शेवटी एकच remap-पास —
# बेस-पॅलेटमधील hex → थीम-hex (case-insensitive, एकच पास = chain नाही:
# 86efac→22c55e पुन्हा 15803d होत नाही), आणि rgba(r,g,b, प्रिफिक्स →
# थीम-ग्लास (बॉर्डर/डिव्हाइडर/ग्लो सगळे एकत्र थीमात रंगतात). dash.CSS
# पण त्याच पासने थीम होऊन <style> टॅगमध्ये कॉम्पोनेंटबरोबर जाते — पान-पातळी
# CSS जुना राहतो पण डॉक्युमेंटमध्ये नंतर आलेला नियम जिंकतो.
# नियम: 5 'डार्क' थीम फक्त सरफेस/मजकूर/म्यूट बदलतात — मोड्यूल-प्रतीक-रंग
# (BANKNIFTY जांभळा, GOLD सोनं, SILVER चंदेरी…) आणि P&L हिरवा-लाल सर्व
# थीममध्ये तसेच (वाचनीयता + ओळख). 'dawn' (लाईट) एकच पूर्ण-रीमॅप —
# उजळ लेख्यावर वाचनीयतेसाठी सगळे उलटे करते.
THEMES = {
    "midnight": {"label": "🌑 रातराणी (सध्याची)", "hex": {}, "rgb": {}},
    "dawn": {"label": "🌅 सोनेरी पहाट (लाईट)", "rgb": {
        "rgba(148,163,184,": "rgba(101,88,62,",
        "rgba(255,255,255,": "rgba(255,253,246,",
        "rgba(2,6,17,": "rgba(59,48,28,",
        "rgba(4,6,12,": "rgba(59,48,28,",
        "rgba(0,0,0,": "rgba(68,58,38,",}, "hex": {
        "#04060c": "#f2e9d5", "#0f172a": "#fffdf6",
        "#f1f5f9": "#292524", "#f8fafc": "#33302b", "#e2e8f0": "#3f3a33",
        "#e0f2fe": "#0c4a6e", "#c7d2fe": "#3730a3", "#a5b4fc": "#4338ca",
        "#8ea0b9": "#8c7a5c", "#9fb0c8": "#7d6f55", "#aab8cf": "#6e6250",
        "#94a3b8": "#8a7a5f", "#64748b": "#8a7355", "#475569": "#6d5f44",
        "#334155": "#5a4d36", "#3b4a63": "#665840", "#cbd5e1": "#5f5850",
        "#6366f1": "#4338ca", "#818cf8": "#4f46e5", "#60a5fa": "#2563eb",
        "#0ea5e9": "#0284c7", "#38bdf8": "#0ea5e9", "#7dd3fc": "#38bdf8",
        "#22d3ee": "#0891b2", "#a78bfa": "#7c3aed", "#f472b6": "#db2777",
        "#fb923c": "#ea580c", "#fbbf24": "#d97706", "#f59e0b": "#b45309",
        "#fcd34d": "#ca8a04",
        "#4ade80": "#16a34a", "#86efac": "#22c55e", "#6ee7b7": "#0d9488",
        "#34d399": "#059669", "#22c55e": "#15803d", "#059669": "#047857",
        "#f87171": "#dc2626", "#fca5a5": "#ef4444", "#fda4af": "#e11d48",
        "#ef4444": "#b91c1c", "#b91c1c": "#991b1b"}},
    "ocean": {"label": "🌊 अरबी सागर", "rgb": {
        "rgba(148,163,184,": "rgba(64,146,160,",
        "rgba(2,6,17,": "rgba(2,16,24,",
        "rgba(4,6,12,": "rgba(3,20,29,",}, "hex": {
        "#04060c": "#02141d", "#0f172a": "#052734",
        "#f1f5f9": "#e2f6fa", "#f8fafc": "#d9f1f6", "#e2e8f0": "#c4e6ee",
        "#e0f2fe": "#a7dbe8", "#c7d2fe": "#9ec9dd", "#a5b4fc": "#8fc0d8",
        "#8ea0b9": "#7aa7b5", "#9fb0c8": "#8ab5c2", "#aab8cf": "#98c2cd",
        "#94a3b8": "#74a5b3", "#64748b": "#5c8e9c", "#475569": "#376371",
        "#334155": "#29525f", "#3b4a63": "#2e5e6c"}},
    "forest": {"label": "🌲 घनदाट जंगल", "rgb": {
        "rgba(148,163,184,": "rgba(62,140,90,",
        "rgba(2,6,17,": "rgba(3,15,9,",
        "rgba(4,6,12,": "rgba(4,18,11,",}, "hex": {
        "#04060c": "#04120b", "#0f172a": "#0a2416",
        "#f1f5f9": "#e3f3e8", "#f8fafc": "#d8ecdf", "#e2e8f0": "#c4e2cf",
        "#e0f2fe": "#a8d8bb", "#c7d2fe": "#9ccdb0", "#a5b4fc": "#8fc2a3",
        "#8ea0b9": "#79a88a", "#9fb0c8": "#8ab697", "#aab8cf": "#99c3a6",
        "#94a3b8": "#73a184", "#64748b": "#5c8a6c", "#475569": "#376b49",
        "#334155": "#2a593a", "#3b4a63": "#2f6642"}},
    "diwali": {"label": "🪔 दिवाळी (लावण्या)", "rgb": {
        "rgba(148,163,184,": "rgba(205,153,73,",
        "rgba(2,6,17,": "rgba(22,10,7,",
        "rgba(4,6,12,": "rgba(26,12,8,",}, "hex": {
        "#04060c": "#160a07", "#0f172a": "#2a180c",
        "#f1f5f9": "#f8ecd9", "#f8fafc": "#f2e3cb", "#e2e8f0": "#e9d5b5",
        "#e0f2fe": "#d6b98a", "#c7d2fe": "#d2ab72", "#a5b4fc": "#c69c60",
        "#8ea0b9": "#a98e62", "#9fb0c8": "#b89a6e", "#aab8cf": "#c3a578",
        "#94a3b8": "#a0855c", "#64748b": "#8a7146", "#475569": "#6e5731",
        "#334155": "#5c4826", "#3b4a63": "#6a5228"}},
    "oled": {"label": "⚫ OLED काळा (बॅटरी-सेव्हर)", "rgb": {
        "rgba(148,163,184,": "rgba(108,108,116,",
        "rgba(2,6,17,": "rgba(0,0,0,",
        "rgba(4,6,12,": "rgba(4,4,5,",}, "hex": {
        "#04060c": "#000000", "#0f172a": "#0c0c0e",
        "#f1f5f9": "#fafafa", "#f8fafc": "#f1f1f3", "#e2e8f0": "#d6d6da",
        "#e0f2fe": "#b9d8e4", "#c7d2fe": "#b6bdf0", "#a5b4fc": "#9aa5ec",
        "#8ea0b9": "#8d8d95", "#9fb0c8": "#9c9ca4", "#aab8cf": "#a8a8b0",
        "#94a3b8": "#8a8a92", "#64748b": "#5f5f66", "#475569": "#45454c",
        "#334155": "#34343a", "#3b4a63": "#3a3a41"}},
}
_THEME_RE_CACHE = {}                   # theme-key → compiled regex


# दिवसाचे नोड्स — वेळापत्रक आणि ⏭ पुढील-घटना काउंटडाउन दोन्ही इथूनच
_TL_NODES = [("09:00", "MCX ओपन"), ("09:15", "NSE ओपन + ORB"),
             ("09:20", "🎯 Swing स्कॅन"), ("09:35", "👨‍👩‍👧 Family स्कॅन"),
             ("09:45", "एंट्री कार्ड्स"), ("15:05", "BN स्क्वेअर-ऑफ"),
             ("20:30", "EVAL-DAILY अहवाल"), ("23:05", "MCX स्क्वेअर-ऑफ")]

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
/* 🛡️ धोका-तापमान • 📉 इक्विटी-कर्व्ह • 📆 वार-विश्लेषण */
.dash .rk{display:grid;grid-template-columns:168px 1fr 172px 56px;gap:12px;align-items:center;
padding:7.5px 0;border-bottom:1px solid rgba(148,163,184,.09)}
.dash .rk:last-child{border-bottom:none}
.dash .rk .nm{font-size:12px;font-weight:700;color:#f1f5f9;display:flex;align-items:center;gap:7px;
min-width:0;white-space:nowrap;overflow:hidden}
.dash .rkbar{height:9px;border-radius:99px;background:rgba(148,163,184,.13);overflow:hidden}
.dash .rkfill{display:block;height:100%;border-radius:99px;transition:width .35s ease}
.dash .rkval{font-size:11px;color:#8ea0b9;text-align:right;white-space:nowrap;font-family:MONOFONT}
.dash .rkval .m{color:#64748b;font-size:10px}
.dash .rkpct{font-size:13px;font-weight:800;text-align:right;font-family:MONOFONT}
.dash .rkagg{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}
.dash .rknote{font-size:11.5px;color:#8ea0b9;line-height:1.75;margin-top:10px;padding-top:9px;
border-top:1px dashed rgba(148,163,184,.16)}
.dash .rknote b{color:#f1f5f9}
.dash .eqsvg{width:100%;height:150px;display:block;border-radius:11px;background:rgba(2,6,17,.35)}
.dash .eqchips{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}
.dash .wk{display:grid;grid-template-columns:62px 1fr 158px;gap:10px;align-items:center;padding:4.5px 0}
.dash .wk.dim{opacity:.42}
.dash .wkl{font-size:11.5px;font-weight:700;color:#94a3b8}
.dash .wkbar{height:10px;border-radius:99px;background:rgba(148,163,184,.13);overflow:hidden}
.dash .wkfill{display:block;height:100%;border-radius:99px}
.dash .wkv{font-size:11.5px;text-align:right;white-space:nowrap;font-family:MONOFONT}
.dash .wkv .m{font-size:10px}
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
.dash .blabels span{width:64px;text-align:center;font-size:10.5px;color:#8ea0b9;font-weight:600;min-width:0}
.dash .jr{font-family:MONOFONT;font-size:11.5px;display:flex;flex-direction:column;gap:8px}
.dash .jr .row{display:flex;gap:10px;color:#94a3b8;line-height:1.45}
.dash .jr .row span{min-width:0;overflow-wrap:anywhere}
.dash .jr .tm{color:#64748b;flex:none}
.dash .tblwrap{padding:6px 8px 4px;border-radius:16px;overflow:auto}
.dash table.tbl{width:100%;border-collapse:collapse;font-size:12.8px}
.dash table.tbl.has{min-width:840px}
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
@media(max-width:760px){
  gradio-container,.gradio-container{padding:0!important;margin:0!important;max-width:100%!important;gap:0!important}
  .gradio-container .block,.gradio-container .form{padding:0!important;border:none!important;background:transparent!important;box-shadow:none!important}
  .dash{padding:12px 10px 20px}
  .dash .hero{padding:14px 14px;gap:10px;border-radius:16px}
  .dash .hleft{gap:11px}
  .dash .logo{width:44px;height:44px;border-radius:12px;font-size:22px}
  .dash .htitle{font-size:18px}
  .dash .hsub{font-size:10.8px}
  .dash .clock{text-align:left}
  .dash .clock .t{font-size:23px}
  .dash .pills{margin-top:11px;gap:7px}
  .dash .pill{font-size:11px;padding:5px 10px}
  .dash .sec{margin:16px 0 10px;gap:9px}
  .dash .kpis{grid-template-columns:repeat(2,1fr);gap:9px}
  .dash .kpi{padding:12px 13px;border-radius:14px}
  .dash .kpi .val{font-size:17.5px;margin-top:5px}
  .dash .kpi .ic{font-size:15px;right:10px;top:11px}
  .dash .syms{grid-template-columns:1fr;gap:10px}
  .dash .sym{padding:13px 13px 11px;border-radius:15px}
  .dash .sname{font-size:14.5px}
  .dash .spnl .big{font-size:20px}
  .dash .smeta{gap:10px;font-size:11px}
  .dash .tlwrap{padding:13px 8px 10px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .dash .node{min-width:66px}
  .dash .ntt{font-size:11px}
  .dash .nll{font-size:9.5px}
  .dash .duo{grid-template-columns:1fr;gap:10px}
  .dash .panel{padding:13px 13px;border-radius:14px}
  .dash .bars{height:98px}
  .dash .bar{width:22px}
  .dash .bcol .bv{font-size:9.5px}
  .dash .blabels span{width:auto;flex:1 1 0;min-width:0;font-size:8.8px;letter-spacing:0}
  .dash .tblwrap{padding:4px 5px 3px;border-radius:13px;-webkit-overflow-scrolling:touch;scrollbar-width:thin}
  .dash table.tbl{font-size:12px}
  .dash table.tbl.has{min-width:700px}
  .dash .duo>.panel{min-width:0;overflow:hidden}
  .dash .tbl th{padding:9px 10px}
  .dash .tbl td{padding:8px 10px}
  .dash .empty{padding:22px 8px!important}
  #refresh-btn{width:100%!important}
  #refresh-btn button{width:100%!important}
  #csv-btn{width:100%!important;margin-top:8px}
  #csv-btn button{width:100%!important}
  .dash .rk{grid-template-columns:96px 1fr 50px;gap:5px 7px;padding:8px 0}
  .dash .rkbar{grid-column:2;grid-row:1}
  .dash .rkpct{grid-column:3;grid-row:1;font-size:11.5px}
  .dash .rkval{grid-column:1/3;grid-row:2;text-align:left;font-size:10px}
  .dash .wk{grid-template-columns:50px 1fr 120px;gap:8px}
  .dash .wkv{font-size:10.5px}
  .dash .eqsvg{height:120px}
  .dash .foot{margin-top:14px}
  .dash .fn{font-size:10.5px;width:100%;text-align:center}
}
@media(max-width:400px){
  .dash .htitle{font-size:16.5px}
  .dash .clock .t{font-size:21px}
  .dash .kpi .val{font-size:16px}
  .dash table.tbl.has{min-width:620px}
  .dash .kpis{gap:8px}
  .dash .rk{grid-template-columns:84px 1fr 46px}
  .dash .wkv{max-width:104px;overflow:hidden;text-overflow:ellipsis}
}
/* 📋 प्रति-instrument ट्रेड-तपशील — click-एक्सपॅन्ड (10s-रिफ्रेशनंतरही उघडं राहतं) */
.dash details.symdet{margin-top:8px;border-radius:12px;
  border:1px solid rgba(148,163,184,.18);background:rgba(2,6,17,.60);
  padding:2px 12px 10px}
.dash .detbtn{display:flex;justify-content:space-between;align-items:center;gap:8px;
  margin-top:10px;padding:9px 12px;border-radius:10px;cursor:pointer;user-select:none;
  font-size:11.5px;font-weight:700;color:#a5b4fc;background:rgba(99,102,241,.10);
  border:1px solid rgba(99,102,241,.30);list-style:none;
  -webkit-tap-highlight-color:transparent}
.dash .detbtn:hover{background:rgba(99,102,241,.22)}
.dash .detbtn::-webkit-details-marker{display:none}
.dash .detbtn .cnt{color:#818cf8}
.dash .detbtn .when-open{display:none;color:#fca5a5}
.dash details[open]>.detbtn .when-shut{display:none}
.dash details[open]>.detbtn .when-open{display:inline}
.dash .detbody{margin-top:6px}
.dash .dth{font-size:11px;font-weight:800;letter-spacing:.06em;color:#7dd3fc;margin:12px 0 4px}
.dash .dthsub{font-size:10px;color:#64748b;margin:8px 0 2px;font-weight:700}
.dash .trow{padding:6px 0;border-bottom:1px dashed rgba(148,163,184,.10);
  font-size:11.8px;line-height:1.5;color:#e2e8f0}
.dash .trow .tl{display:block;color:#94a3b8;font-size:10.8px;padding-left:14px}
.dash .evline{display:flex;gap:8px;padding:4.5px 0;
  border-bottom:1px dashed rgba(148,163,184,.08);font-size:11.6px;line-height:1.45}
.dash .evline .ets{color:#38bdf8;font-family:MONOFONT;white-space:nowrap;
  font-size:10.4px;padding-top:1px}
.dash .evline .emsg{color:#cbd5e1;word-break:break-word}
.dash .dtempty{color:#475569;font-size:11.5px;padding:6px 0}
.dash .sym .shead{cursor:pointer}
/* 🔝 स्टिकी जंप-नेव्ह — लांब पानावर एक-क्लिक वर/खाली */
.dash .nav{position:sticky;top:0;z-index:90;display:flex;gap:7px;align-items:center;
padding:10px 22px;margin:0 -22px 8px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;
background:linear-gradient(180deg,rgba(4,6,12,.98) 55%,rgba(4,6,12,.86));backdrop-filter:blur(10px);
border-bottom:1px solid rgba(148,163,184,.14)}
.dash .nav::-webkit-scrollbar{display:none}
.dash .nav a{flex:none;display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;
font-size:11.5px;font-weight:700;color:#aab8cf;text-decoration:none;white-space:nowrap;transition:all .15s ease;
border:1px solid rgba(148,163,184,.22);background:rgba(148,163,184,.05)}
.dash .nav a:hover{color:#e2e8f0;border-color:rgba(129,140,248,.55);background:rgba(99,102,241,.16)}
.dash [id^="sec-"]{scroll-margin-top:64px}
html{scroll-behavior:smooth}
/* 📅 14-दिवस दैनिक निव्वल P&L हिस्ट्री */
.dash .hbars{display:flex;align-items:flex-end;gap:3px;height:112px;
border-bottom:1px solid rgba(148,163,184,.2);padding:0 2px}
.dash .hcol{flex:1 1 0;min-width:0;display:flex;flex-direction:column;align-items:center;
justify-content:flex-end;gap:4px}
.dash .hcol .hv{font-family:MONOFONT;font-size:9.8px;font-weight:700;white-space:nowrap}
.dash .hcol .hbar{width:74%;max-width:34px;min-width:7px;border-radius:5px 5px 2px 2px}
.dash .hcol.today .hbar{box-shadow:0 0 0 1.5px rgba(56,189,248,.8),0 0 14px rgba(56,189,248,.45)}
.dash .hlabels{display:flex;gap:3px;padding:6px 2px 0}
.dash .hlabels span{flex:1 1 0;min-width:0;text-align:center;font-size:9.3px;color:#8ea0b9;
font-weight:600;white-space:nowrap}
.dash .hlabels span i{font-style:normal;color:#64748b}
.dash .histduo{align-items:start}
.dash .hnote{font-size:10.8px;color:#64748b;margin-top:10px;display:flex;gap:14px;flex-wrap:wrap}
.dash .hnote b{color:#cbd5e1;font-family:MONOFONT}
/* 🧮 MTD सारांश-तक्ता */
.dash table.tbl.mtd{min-width:430px}
.dash table.tbl.mtd td,.dash table.tbl.mtd th{padding:8.5px 10px}
.dash table.tbl.mtd tr.tot td{border-top:1.5px solid rgba(148,163,184,.35);font-weight:800;
color:#f1f5f9;background:rgba(148,163,184,.05)}
.dash .wr{display:inline-block;min-width:42px;text-align:center;font-family:MONOFONT;
font-weight:700;font-size:11px;padding:2px 7px;border-radius:6px}
/* ⏭ पुढील घटना-काउंटडाउन */
.dash .nextn{margin-top:9px;padding:8px 13px;border-radius:11px;font-size:12px;font-weight:600;
display:flex;align-items:center;gap:9px;flex-wrap:wrap;
background:rgba(56,189,248,.08);border:1px dashed rgba(56,189,248,.35);color:#7dd3fc}
.dash .nextn b{font-family:MONOFONT;color:#e0f2fe}
/* 📍 सेशन-प्रगती पट्टी — दिवस कुठे आहे ते एका दृष्टीत */
.dash .sess{padding:13px 20px 11px;margin:0 0 2px}
.dash .stitle{font-size:11px;font-weight:700;color:#8ea0b9;letter-spacing:1.2px}
.dash .strack{position:relative;height:3px;border-radius:2px;background:rgba(148,163,184,.16);margin:34px 8px 30px}
.dash .sfill{position:absolute;left:0;top:0;bottom:0;border-radius:2px;
background:linear-gradient(90deg,rgba(34,211,238,.4),rgba(56,189,248,.8))}
.dash .snode{position:absolute;top:50%;width:9px;height:9px;border-radius:50%;transform:translate(-50%,-50%);
background:#334155;border:1.5px solid rgba(148,163,184,.45);z-index:1}
.dash .snode.done{background:#22d3ee;border-color:#7dd3fc;box-shadow:0 0 8px rgba(34,211,238,.5)}
.dash .snlab{position:absolute;top:11px;transform:translateX(-50%);text-align:center;
font-size:9.2px;font-weight:600;color:#64748b;white-space:nowrap;line-height:1.35}
.dash .snlab b{display:block;font-family:MONOFONT;font-size:9.4px;font-weight:700;color:#8ea0b9}
.dash .snow{position:absolute;top:50%;width:15px;height:15px;border-radius:50%;transform:translate(-50%,-50%);
background:radial-gradient(circle,#e0f2fe 22%,#38bdf8 75%);border:2px solid #e0f2fe;z-index:3;animation:snowpulse 2.2s infinite}
@keyframes snowpulse{0%,100%{box-shadow:0 0 10px rgba(56,189,248,.75),0 0 24px rgba(56,189,248,.3)}50%{box-shadow:0 0 16px rgba(56,189,248,.95),0 0 38px rgba(56,189,248,.5)}}
.dash .snowlab{position:absolute;top:-30px;transform:translateX(-50%);font-family:MONOFONT;font-size:10px;font-weight:800;
color:#e0f2fe;white-space:nowrap;background:rgba(56,189,248,.13);border:1px solid rgba(56,189,248,.55);
border-radius:999px;padding:2.5px 9px;backdrop-filter:blur(4px)}
.dash .sess.we .snowlab{border-color:rgba(148,163,184,.4);background:rgba(148,163,184,.1);color:#94a3b8}
/* 🧠 बुद्धीचा डब्बा */
.dash .ins{padding:7px 18px}
.dash .irow{padding:8.5px 0;border-bottom:1px dashed rgba(148,163,184,.09);font-size:12.4px;color:#cbd5e1;line-height:1.6}
.dash .irow:last-child{border-bottom:none}
.dash .irow b{color:#f1f5f9;font-family:MONOFONT}
/* 🗓️ महिना P&L कॅलेंडर-हीटमॅप */
.dash .cal{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;margin-top:6px}
.dash .cal .ch{font-size:9.6px;font-weight:700;color:#64748b;text-align:center;padding:2px 0;letter-spacing:.4px}
.dash .cd{position:relative;min-height:42px;border-radius:9px;display:flex;align-items:center;justify-content:center;
font-family:MONOFONT;font-size:10.8px;font-weight:700;color:#f1f5f9;
background:rgba(148,163,184,.06);border:1px solid rgba(148,163,184,.08)}
.dash .cd .dn{position:absolute;top:3px;left:6px;font-size:8px;font-weight:700;
font-family:MONOFONT;color:rgba(226,232,240,.5)}
.dash .cd.emp{background:transparent;border-color:transparent}
.dash .cd.we{background:rgba(148,163,184,.025)}
.dash .cd.we .dn{color:rgba(148,163,184,.32)}
.dash .cd.fut{background:transparent;border:1px dashed rgba(148,163,184,.14);color:transparent}
.dash .cd.fut .dn{color:rgba(148,163,184,.3)}
.dash .cd.today{border:1.5px solid rgba(56,189,248,.8);box-shadow:0 0 10px rgba(56,189,248,.35)}
.dash .cleg{display:flex;gap:14px;flex-wrap:wrap;margin-top:11px;font-size:10.8px;color:#64748b;align-items:center}
.dash .cleg b{font-family:MONOFONT;color:#cbd5e1}
.dash .cscale{display:inline-flex;gap:3px;align-items:center}
.dash .cscale i{width:11px;height:11px;border-radius:3px;display:inline-block;border:1px solid rgba(255,255,255,.06)}
/* 🏆 मेडल-लीडरबोर्ड */
.dash .lbr{display:flex;align-items:center;gap:9px;padding:7.5px 10px;border-radius:11px;
border:1px solid rgba(148,163,184,.10);background:rgba(148,163,184,.04);margin-bottom:6px}
.dash .lbr .rk{font-size:13.5px;width:28px;flex:none;text-align:center;font-family:MONOFONT;font-weight:800;color:#94a3b8}
.dash .lbr .nm{flex:1;min-width:0;font-size:12.4px;font-weight:700;color:#e2e8f0;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dash .lbr .nt{font-size:10px;color:#64748b;font-weight:600;white-space:nowrap}
.dash .lbr .lv{font-family:MONOFONT;font-weight:700;font-size:12.2px;flex:none}
.dash .lbr.top1{border-color:rgba(251,191,36,.45);background:rgba(251,191,36,.07)}
.dash .lbr.top1 .rk{font-size:16px}
.dash .lbfoot{font-size:10.8px;color:#64748b;margin-top:9px}
/* 🎯 स्ट्रॅटेजी परफॉर्मन्स ट्रॅकर */
.dash table.tbl.perf{min-width:660px}
.dash table.tbl.perf td,.dash table.tbl.perf th{padding:8.5px 10px}
.dash .grd{display:inline-block;min-width:30px;text-align:center;font-family:MONOFONT;
font-weight:800;font-size:11px;padding:2.5px 8px;border-radius:7px}
/* ⏱️ वेळ-अभ्यास — बुकिंग-तास पट्टी */
.dash .tstrip{display:flex;gap:4px;align-items:stretch;margin-top:4px;
overflow-x:auto;padding-bottom:2px;scrollbar-width:thin}
.dash .thc{flex:0 0 44px;min-width:0;display:flex;flex-direction:column;align-items:center}
.dash .thw{position:relative;width:100%;height:96px;border-radius:8px;
background:rgba(148,163,184,.05);border:1px solid rgba(148,163,184,.07);overflow:hidden}
.dash .thw::before{content:'';position:absolute;left:0;right:0;top:50%;height:1px;
background:rgba(148,163,184,.20)}
.dash .thb{position:absolute;left:14%;right:14%;border-radius:4px}
.dash .thb.up{bottom:50%;background:linear-gradient(180deg,rgba(52,211,153,.95),rgba(52,211,153,.40))}
.dash .thb.dn{top:50%;background:linear-gradient(180deg,rgba(248,113,113,.40),rgba(248,113,113,.95))}
.dash .thl{font-family:MONOFONT;font-size:9.3px;font-weight:700;color:#64748b;margin-top:5px}
.dash .tcall{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}
.dash .tchip{font-size:11.3px;font-weight:600;padding:5.5px 11px;border-radius:9px;
border:1px dashed rgba(148,163,184,.25);color:#cbd5e1;background:rgba(148,163,184,.05)}
.dash .tchip b{font-family:MONOFONT;color:#f1f5f9}
/* 📈 ट्रेड-लाइव्ह कॅन्डल-चार्ट */
.dash .tcards{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.dash .tcard{padding:13px 14px 11px;border-radius:16px}
.dash .tchead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:9px}
.dash .tcn{font-size:13.5px;font-weight:800;display:flex;align-items:center;gap:6px}
.dash .tcn small{color:#64748b;font-weight:600;font-size:10.5px;font-family:MONOFONT}
.dash .tct{font-family:MONOFONT;font-size:10.5px;color:#64748b;margin-left:auto}
.dash svg.csvg{width:100%;height:auto;display:block;border-radius:10px;
background:rgba(2,6,17,.55);border:1px solid rgba(148,163,184,.12)}
.dash .tcchips{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}
.dash .tcno{padding:30px 12px;text-align:center;color:#64748b;font-size:11.8px;line-height:1.5;
border:1px dashed rgba(148,163,184,.2);border-radius:10px;background:rgba(148,163,184,.03)}
.dash .tnote{font-size:10.8px;color:#64748b;margin-top:9px;display:flex;gap:12px;flex-wrap:wrap}
@media(max-width:760px){
  .dash .nav{padding:9px 10px;margin:0 -10px 6px;gap:6px}
  .dash .nav a{font-size:10.5px;padding:5px 9px}
  .dash [id^="sec-"]{scroll-margin-top:58px}
  .dash .hbars{height:92px;gap:2px}
  .dash .hcol .hv{font-size:8.6px}
  .dash .hlabels span{font-size:8.4px}
  .dash .hlabels span i{display:none}
  .dash table.tbl.mtd{min-width:350px}
  .dash table.tbl.mtd td,.dash table.tbl.mtd th{padding:8px 6px}
  .dash .hnote{font-size:10px;gap:8px}
  .dash .nextn{font-size:11px}
  .dash .sess{padding:11px 12px 8px}
  .dash .strack{margin:30px 4px 24px}
  .dash .snlab{display:none}
  .dash .snowlab{font-size:9px;padding:2px 7px}
  .dash .cal{gap:3px}
  .dash .cd{min-height:33px;font-size:9.2px;border-radius:7px}
  .dash .cd .dn{font-size:7.2px;left:4px;top:2px}
  .dash .lbr{padding:6px 7px;gap:6px}
  .dash .lbr .nt{display:none}
  .dash table.tbl.perf{min-width:560px}
  .dash .tcards{grid-template-columns:1fr;gap:10px}
  .dash .thw{height:78px}
  .dash .thc{flex:0 0 34px}
  .dash .thl{font-size:8.2px}
  .dash .tchip{font-size:10.5px}
  .dash .tcard{padding:12px 11px 10px}
}
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
    # 📋 ट्रेड-तपशील पॅनेल — उघड-स्थिती लक्षात ठेवून 10s-रिफ्रेशनंतर पुन्हा उघडी करतो
    '<script>(function(){var OPEN={};'
    "document.addEventListener('toggle',function(e){var t=e.target;"
    "if(t&&t.classList&&t.classList.contains('symdet')){"
    "try{OPEN[t.getAttribute('data-detid')]=t.open;}catch(e){}}},true);"
    "document.addEventListener('click',function(ev){"
    "var el=ev.target.closest('[data-detid]');"
    "if(!el||el.tagName==='SUMMARY'||!el.classList.contains('shead'))return;"
    "var d=document.getElementById('det-'+el.getAttribute('data-detid'));"
    "if(d){d.open=!d.open;}},false);"
    "function apply(){var ds=document.querySelectorAll('details.symdet');"
    "for(var i=0;i<ds.length;i++){var id=ds[i].getAttribute('data-detid');"
    "if(id in OPEN){try{ds[i].open=OPEN[id];}catch(e){}}}}"
    "new MutationObserver(apply).observe(document.documentElement,"
    "{childList:true,subtree:true});})();</script>"
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

    # 🫀 इंजिन हृदयस्पंदन — beat 2 मि< नं ग्रीन, 10 मि> नं लाल (watchdog 15 मि वर रीस्टार्ट)
    beat = store.get_state("engine_beat") or ""
    beat_pill = '<span class="pill bad">🚨 इंजिन बीट नाही</span>'
    if beat:
        try:
            bt = datetime.strptime(beat, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            age = int((n - bt).total_seconds())
            if age <= 120:
                beat_pill = ('<span class="pill ok"><i class="dot on"></i>'
                             '🫀 इंजिन जिवंत</span>')
            elif age <= 600:
                beat_pill = ('<span class="pill warn">🫀 बीट ' +
                             str(max(1, age // 60)) + ' मि जुना</span>')
            else:
                beat_pill = ('<span class="pill bad">🚨 बीट ' +
                             str(age // 60) + ' मि जुना</span>')
        except ValueError:
            pass

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
      <div class="hsub">{len(C.SYMBOLS)} दरवाजे • ORB ब्रेकआउट • TP लॅडर • डिटरमिनिस्टिक रिस्क नियम • Telegram नियंत्रण</div>
    </div>
  </div>
  <div class="clock">
    <div class="t" id="bot-clock">{n.strftime('%H:%M:%S')}</div>
    <div class="d">{wd}वार, {n.strftime('%d %b %Y')} • IST</div>
  </div>
  <div class="pills">
    {mode_pill}{tok_pill}{beat_pill}{mkt_pills}{flags}
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

    # 📋 प्रति-instrument तपशील — आजचे ट्रेड्स + सर्व इव्हेंट (मागील 3 दिवस)
    mid = n.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        evs = store.events_for([S["label"], "engine[" + S["key"] + "]"],
                               since_ts=mid - 3 * 86400, limit=200)
        det_html = _inst_detail(S, date, trs, evs, mid)
    except Exception:
        det_html = ""

    return f"""
<div class="sym gx" style="--sc:{st['c']}">
  <i class="acc"></i>
  <div class="shead" data-detid="{S['key']}">
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
  {det_html}
</div>"""


def _timeline(n):
    nowm = n.strftime("%H:%M")
    holiday = n.weekday() >= 5
    out = []
    cur_set = False
    for tt, ll in _TL_NODES:
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
    if holiday:
        note = ('<div style="text-align:center;font-size:11px;color:#64748b;margin-top:8px">'
                '🌙 आज बाजार सुट्टी — नियम तसेच सक्रिय, सोमवारी पुढे</div>')
    else:
        nxt = None
        for tt, ll in _TL_NODES:
            if nowm < tt:
                nxt = (tt, ll)
                break
        if nxt:
            hh, mm = int(nxt[0][:2]), int(nxt[0][3:])
            tgt = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
            rem = int((tgt - n).total_seconds())
            if rem <= 59:
                left = "आत्ताच!"
            elif rem < 3600:
                left = str(rem // 60) + " मिनिटे"
            else:
                left = str(rem // 3600) + " ता " + str((rem % 3600) // 60) + " मि"
            note = ('<div class="nextn">⏭ पुढील नोड: <b>' + nxt[0] + '</b> — ' +
                    _h.escape(nxt[1]) + ' • यापुढे <b>' + left + '</b></div>')
        else:
            note = ('<div class="nextn">🌙 आजचे सर्व नोड्स पूर्ण — '
                    'पुढील सत्र उद्या 09:00 (MCX)</div>')
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
    tcls = "tbl has" if rows else "tbl"
    return (f'<div class="tblwrap gx"><table class="{tcls}"><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def _evblocks(evs, mid, empty="इव्हेंट नाहीत"):
    """इव्हेंट-यादी → आज + मागील 3 दिवस असे दोन गट (जुने→नवीन)"""
    today_evs = [e for e in evs if e["ts"] >= mid]
    old_evs = [e for e in evs if e["ts"] < mid]

    def lines(rows, with_date):
        out = []
        for e in sorted(rows, key=lambda x: x["ts"]):
            tm = datetime.fromtimestamp(e["ts"], IST).strftime(
                "%d-%m %H:%M" if with_date else "%H:%M")
            out.append(f'<div class="evline"><span class="ets">{tm}</span>'
                       f'<span class="emsg">{_h.escape(str(e["msg"]))}</span></div>')
        return "".join(out)

    html = ""
    if today_evs:
        html += (f'<div class="dthsub">— आज ({len(today_evs)}) —</div>'
                 + lines(today_evs, False))
    if old_evs:
        html += (f'<div class="dthsub">— आधीचे, मागील 3 दिवस ({len(old_evs)}) —</div>'
                 + lines(old_evs, True))
    return html or f'<div class="dtempty">{empty}</div>'


def _trade_rows(trs):
    """ट्रेड-यादी → कॉम्पॅक्ट ओळी (लेग/आंशिक-बुकिंगसह)"""
    out = []
    for t in trs:
        pnl = t.get("pnl")
        ic = "◉" if t["status"] == "OPEN" else ("✅" if (pnl or 0) >= 0 else "❌")
        ex = f" → ₹{float(t['exit']):.2f}" if t.get("exit") else ""
        pnl_s = (f'<span class="{_cls(pnl)}">{_sign(pnl)}{_inr(abs(pnl))}</span>'
                 if pnl is not None else '<span class="m">चालू</span>')
        legs = store.get_legs(t["id"])
        leg_html = ""
        if legs:
            leg_html = '<span class="tl">↳ ' + " • ".join(
                f"{_h.escape(str(l.get('label') or 'leg'))} "
                f"₹{float(l.get('price') or 0):.2f}×{l.get('qty')}"
                for l in legs) + "</span>"
        reason = _h.escape(str(t.get("reason") or ""))[:48] or "—"
        out.append(
            f'<div class="trow">{ic} {_hhmm(t.get("opened"))} • '
            f'{t["strike"]:.0f} {t["side"]} @ ₹{float(t["entry"]):.2f}{ex} '
            f'• {reason} • {pnl_s}{leg_html}</div>')
    return "".join(out)


def _inst_detail(S, date, trs, evs, mid):
    """📋 click-एक्सपॅन्ड — एका instrument चे आजचे ट्रेड्स (लेगसह) + सर्व इव्हेंट"""
    st = SYM_STYLE.get(S["key"], {"c": "#818cf8", "icon": "📊"})
    today_n = sum(1 for e in evs if e["ts"] >= mid)
    trades_html = (_trade_rows(trs) if trs
                   else '<div class="dtempty">आज ट्रेड नाही</div>')
    return (
        f'<details class="symdet" id="det-{S["key"]}" data-detid="{S["key"]}">'
        f'<summary class="detbtn" data-detid="{S["key"]}">'
        f'<span class="when-shut">📋 सर्व ट्रेड-तपशील व इव्हेंट '
        f'<span class="cnt">(आज {today_n} इव्हेंट • {len(trs)} ट्रेड)</span></span>'
        f'<span class="when-open">✕ तपशील लपवा</span></summary>'
        f'<div class="detbody">'
        f'<div class="dth">💹 आजचे ट्रेड्स — {st["icon"]} {_h.escape(S["label"])}</div>'
        f'{trades_html}'
        f'<div class="dth">📡 इव्हेंट-जर्नल — नियम/एंट्री/एग्झिट/एरर सर्व</div>'
        f'{_evblocks(evs, mid)}'
        f'</div></details>')


def _wr_chip(w, l):
    """WR% — रंगीत चिप (≥60% हिरवा, ≥40% पिवळा, अन्यथा लाल)"""
    t = w + l
    if t <= 0:
        return ('<span class="wr" style="background:rgba(148,163,184,.12);'
                'color:#94a3b8">—</span>')
    p = w * 100.0 / t
    if p >= 60:
        col = "rgba(16,185,129,.14);color:#4ade80"
    elif p >= 40:
        col = "rgba(245,158,11,.16);color:#fbbf24"
    else:
        col = "rgba(239,68,68,.15);color:#f87171"
    return ('<span class="wr" style="background:' + col + '">' +
            "{:.0f}%".format(p) + "</span>")


def _mtd_summary(date):
    """🧮 MTD सारांश — सर्व मोड्यूल (9 दरवाजे + Swing + Family):
    ट्रेड / W-L / WR% / खर्च / निव्वल — EVAL-DAILY प्रमाणे बंद-ट्रेड्सवर"""
    ym = date[:7]

    def agg(rows):
        cl = [t for t in rows if t.get("status") == "CLOSED"]
        w = sum(1 for t in cl if (t.get("pnl") or 0) > 0.004)
        l = sum(1 for t in cl if (t.get("pnl") or 0) < -0.004)
        return (len(cl), w, l,
                round(sum((t.get("charges") or 0) for t in cl), 2),
                round(sum((t.get("pnl") or 0) for t in cl), 2))

    rows_html = []
    tot = [0, 0, 0, 0.0, 0.0]

    def add_row(icon, name, color, st5):
        n_, w, l, chg, net = st5
        tot[0] += n_
        tot[1] += w
        tot[2] += l
        tot[3] += chg
        tot[4] += net
        rows_html.append(
            '<tr><td><span class="symdot" style="background:' + color +
            '"></span>' + icon + " " + _h.escape(name) + "</td>"
            '<td class="m">' + str(n_) + "</td>"
            '<td class="m">' + str(w) + "/" + str(l) + "</td>"
            "<td>" + _wr_chip(w, l) + "</td>"
            '<td class="m" style="color:#fbbf24">' + _inr(chg) + "</td>"
            '<td class="m">' + _spnl(net) + "</td></tr>")

    for s in C.active_symbols():
        st = SYM_STYLE.get(s["key"], {"c": "#818cf8", "icon": "📊"})
        add_row(st["icon"], s["short"], st["c"],
                agg(store.month_trades(ym, s["key"])))
    if swing is not None and getattr(swing, "ENABLED", False):
        add_row("🎯", "Swing", "#22d3ee", agg(store.swing_month(ym)))
    if family is not None and getattr(family, "ENABLED", False):
        add_row("👨‍👩‍👧", "Family", "#f59e0b", agg(store.family_month(ym)))
    ths = "".join("<th>" + h + "</th>" for h in
                  ["मोड्यूल", "ट्रेड", "W/L", "WR%", "खर्च", "MTD निव्वल"])
    trow = ('<tr class="tot"><td>🧮 एकूण</td><td class="m">' + str(tot[0]) +
            '</td><td class="m">' + str(tot[1]) + "/" + str(tot[2]) +
            "</td><td>" + _wr_chip(tot[1], tot[2]) +
            '</td><td class="m" style="color:#fbbf24">' + _inr(tot[3]) +
            '</td><td class="m">' + _spnl(tot[4]) + "</td></tr>")
    return ('<div class="panel gx"><div class="ptitle">🧮 MTD सारांश — ' + ym +
            " (सर्व मोड्यूल, बंद-ट्रेड्स)</div>"
            '<div class="tblwrap"><table class="tbl mtd"><thead><tr>' + ths +
            "</tr></thead><tbody>" + "".join(rows_html) + trow +
            "</tbody></table></div></div>")


def _daily_hist(n, date):
    """📅 शेवटचे 14 दिवस — सर्व मोड्यूल एकत्र दैनिक निव्वल P&L बार-चार्ट + MTD सारांश"""
    days = [n - timedelta(days=13 - i) for i in range(14)]
    start = days[0].strftime("%Y-%m-%d")
    try:
        hist = store.daily_net_hist(start)
    except Exception:
        hist = {}
    vals = []
    for d in days:
        e = hist.get(d.strftime("%Y-%m-%d")) or (0.0, 0.0, 0)
        vals.append((d, float(e[0]), float(e[1]), int(e[2])))
    mx = max([abs(v[1]) for v in vals] + [1.0])
    bars = []
    for d, net, _chg, _nt in vals:
        h = 4 if abs(net) < 0.005 else max(10, int(88 * abs(net) / mx))
        col = ("linear-gradient(180deg,#34d399,#059669)" if net > 0 else
               "linear-gradient(180deg,#f87171,#b91c1c)" if net < 0 else "#334155")
        lab = _k(net) if abs(net) >= 0.005 else ""
        if abs(net) >= 0.005:
            tip = (d.strftime("%d %b") + " • " + _sign(net) + _inr(abs(net)) +
                   " • " + str(_nt) + " ट्रेड")
        else:
            tip = d.strftime("%d %b") + " • ट्रेड नाही"
        tcls = "hcol today" if d.strftime("%Y-%m-%d") == date else "hcol"
        bars.append('<div class="' + tcls + '" title="' + _h.escape(tip) + '">'
                    '<div class="hv ' + _cls(net) + '">' + lab + "</div>"
                    '<div class="hbar" style="height:' + str(h) +
                    "px;background:" + col + '"></div></div>')
    labels = "".join("<span>" + v[0].strftime("%d") + "<i>" +
                     v[0].strftime(" %b") + "</i></span>" for v in vals)
    tot14 = round(sum(v[1] for v in vals), 2)
    chg14 = round(sum(v[2] for v in vals), 2)
    n14 = sum(v[3] for v in vals)
    note = ('<div class="hnote"><span>14 दिवस: <b class="' + _cls(tot14) + '">'
            + _sign(tot14) + _inr(abs(tot14)) + "</b> निव्वल</span>"
            "<span>🧾 खर्च <b>" + _inr(chg14) + "</b></span>"
            "<span>💹 ट्रेड्स <b>" + str(n14) + "</b></span>")
    act = [v for v in vals if abs(v[1]) >= 0.005]
    if act:
        bd = max(act, key=lambda x: x[1])
        wd = min(act, key=lambda x: x[1])
        note += ('<span>🏆 सर्वोत्तम <b>' + _sign(bd[1]) + _inr(abs(bd[1])) +
                 "</b> (" + bd[0].strftime("%d %b") + ")</span>"
                 "<span>📉 सर्वात वाईट <b>" + _sign(wd[1]) + _inr(abs(wd[1])) +
                 "</b> (" + wd[0].strftime("%d %b") + ")</span>")
    else:
        note += "<span>या कालावधीत ट्रेड नाहीत</span>"
    note += "</div>"
    return ('<div class="duo histduo">'
            '<div class="panel gx"><div class="ptitle">📅 दैनिक निव्वल P&L — '
            "शेवटचे 14 दिवस (सर्व मोड्यूल एकत्र)</div>"
            '<div class="hbars">' + "".join(bars) + "</div>"
            '<div class="hlabels">' + labels + "</div>" + note + "</div>"
            + _mtd_summary(date) + "</div>")


_MAR_M = ["जानु", "फेब्रु", "मार्च", "एप्रि", "मे", "जून", "जुलै", "ऑग",
          "सप्टें", "ऑक्टो", "नोव्हें", "डिसें"]
_MAR_W = ["सोम", "मंगळ", "बुध", "गुरु", "शुक्र", "शनि", "रवि"]


def _sessbar(n, date):
    """📍 सेशन-प्रगती पट्टी — दिवसाचे नोड्स एकसारखे पसरून, आता-सूचक खर्या वेळेप्रमाणे
    (नोड्समधील तोटा piecewise-linear मॅपिंगने जागा मिळतो — वेळ अचूकच दिसते)"""
    pts = []
    for hhmm, lab in _TL_NODES:
        h, m = hhmm.split(":")
        pts.append((int(h) * 60 + int(m), hhmm, lab))
    k = len(pts) - 1
    pct = [round(i * 100.0 / k, 2) for i in range(len(pts))]
    cur = n.hour * 60 + n.minute
    we = n.weekday() >= 5

    def vis(mins):
        if mins <= pts[0][0]:
            return 0.0
        if mins >= pts[-1][0]:
            return 100.0
        for i in range(k):
            a, b = pts[i][0], pts[i + 1][0]
            if a <= mins <= b:
                f = (mins - a) / float(b - a) if b > a else 0.0
                return (i + f) * 100.0 / k
        return 100.0

    dots, labs = [], []
    for i, (mn, hhmm, lab) in enumerate(pts):
        cls = "snode done" if (not we and cur >= mn) else "snode"
        dots.append('<div class="' + cls + '" style="left:' + str(pct[i]) + '%"></div>')
        labs.append('<div class="snlab" style="left:' + str(pct[i]) + '%"><b>' +
                    hhmm + "</b>" + _h.escape(lab) + "</div>")
    if we:
        head = "📍 आज बाजार सुट्टी — सोम–शुक्र ट्रेडिंग"
        now_h = ""
    else:
        pos = vis(cur)
        if cur < pts[0][0]:
            bub = "उघडण्यापूर्वी"
        elif cur >= pts[-1][0]:
            bub = "आजचा दिवस संपला"
        else:
            bub = "आता " + n.strftime("%H:%M")
        fill = ('<div class="sfill" style="width:' + str(round(pos, 2)) +
                '%"></div>') if pos > 0.3 else ""
        lab_pos = min(max(pos, 7.0), 93.0)
        now_h = (fill + '<div class="snow" style="left:' + str(round(pos, 2)) +
                 '%"></div><div class="snowlab" style="left:' +
                 str(round(lab_pos, 2)) + '%">' + bub + "</div>")
        head = "📍 दिवस कुठे आहे? — 09:00 → 23:05 एका दृष्टीत"
    return ('<div class="panel gx sess"><div class="stitle">' + head + "</div>"
            '<div class="strack">' + "".join(dots) + "".join(labs) + now_h +
            "</div></div>")


def _agg5(trs):
    """(n, W, L, खर्च, निव्वल) — बंद-ट्रेड्सवर"""
    cl = [t for t in trs if t.get("status") == "CLOSED"]
    w = sum(1 for t in cl if (t.get("pnl") or 0) > 0)
    l = sum(1 for t in cl if (t.get("pnl") or 0) < 0)
    return (len(cl), w, l,
            round(sum((t.get("charges") or 0) for t in cl), 2),
            round(sum((t.get("pnl") or 0) for t in cl), 2))


def _month_rows(date):
    """MTD — प्रत्येक मोड्यूलची सारांश-ओळ (लीडरबोर्ड + बुद्धीचा डब्बा दोन्ही वापरतात)"""
    ym = date[:7]
    rows = []
    for s in C.active_symbols():
        st = SYM_STYLE.get(s["key"], {"c": "#818cf8", "icon": "📊"})
        trs = store.month_trades(ym, s["key"])
        n_, w, l, chg, net = _agg5(trs)
        rows.append({"key": s["key"], "icon": st["icon"], "name": s["short"],
                     "c": st["c"], "n": n_, "w": w, "l": l, "chg": chg,
                     "net": net,
                     "pnls": [float(t.get("pnl") or 0) for t in trs
                              if t.get("status") == "CLOSED"]})
    if swing is not None and getattr(swing, "ENABLED", False):
        trs = store.swing_month(ym)
        n_, w, l, chg, net = _agg5(trs)
        rows.append({"key": "SWING", "icon": "🎯", "name": "Swing",
                     "c": "#22d3ee", "n": n_, "w": w, "l": l, "chg": chg,
                     "net": net,
                     "pnls": [float(t.get("pnl") or 0) for t in trs
                              if t.get("status") == "CLOSED"]})
    if family is not None and getattr(family, "ENABLED", False):
        trs = store.family_month(ym)
        n_, w, l, chg, net = _agg5(trs)
        rows.append({"key": "FAMILY", "icon": "👨‍👩‍👧", "name": "Family",
                     "c": "#f59e0b", "n": n_, "w": w, "l": l, "chg": chg,
                     "net": net,
                     "pnls": [float(t.get("pnl") or 0) for t in trs
                              if t.get("status") == "CLOSED"]})
    return rows


def _calheat(date):
    """🗓️ महिना-भर P&L कॅलेंडर-हीटमॅप — प्रत्येक दिवसाची पेशी निव्वल-प्रमाणे हिरवी/लाल"""
    ym = date[:7]
    yy, mm = int(ym[:4]), int(ym[5:7])
    first_wd, ndays = calendar.monthrange(yy, mm)
    try:
        hist = store.daily_net_hist(ym + "-01")
    except Exception:
        hist = {}
    today_i = int(date[8:10])
    mx = max([abs(float(v[0])) for v in hist.values()] + [1.0])
    cells = ['<div class="ch">' + w + "</div>" for w in _MAR_W]
    cells += ['<div class="cd emp"></div>'] * first_wd
    for dnum in range(1, ndays + 1):
        wd = (first_wd + dnum - 1) % 7
        we = wd >= 5
        cls = "cd" + (" we" if we else "")
        style = ""
        val = "·"
        dstr = ym + "-" + ("%02d" % dnum)
        dmar = str(dnum) + " " + _MAR_M[mm - 1]
        if dnum > today_i:
            cls += " fut"
            val = ""
            tip = dmar
        else:
            e = hist.get(dstr)
            if e and abs(float(e[0])) >= 0.005:
                net = float(e[0])
                a = 0.20 + 0.70 * min(1.0, abs(net) / mx)
                col = "52,211,153" if net > 0 else "248,113,113"
                style = "background:rgba(" + col + "," + str(round(a, 2)) + ")"
                val = _k(net)
                tip = (dmar + " • " + _sign(net) + _inr(abs(net)) + " • " +
                       str(int(e[2] or 0)) + " ट्रेड")
            else:
                tip = dmar + (" • सुट्टी" if we else " • ट्रेड नाही")
        if dnum == today_i:
            cls += " today"
        cells.append('<div class="' + cls + '" style="' + style +
                     '" title="' + _h.escape(tip) + '"><span class="dn">' +
                     str(dnum) + "</span>" + val + "</div>")
    mnet = round(sum(float(v[0]) for v in hist.values()), 2)
    mtr = sum(int(v[2] or 0) for v in hist.values())
    scale = "".join('<i style="background:rgba(52,211,153,' +
                    str(round(0.20 + 0.70 * f, 2)) + ')"></i>'
                    for f in (0.0, 0.33, 0.66, 1.0))
    scale += ('<i style="background:rgba(248,113,113,.85)"></i>'
              '<i style="background:rgba(248,113,113,.45)"></i>'
              '<i style="background:rgba(248,113,113,.2)"></i>')
    leg = ('<div class="cleg"><span class="cscale">' + scale +
           " तोटा ← निव्वल → नफा</span>"
           "<span>महिना: <b class='" + _cls(mnet) + "'>" + _sign(mnet) +
           _inr(abs(mnet)) + "</b></span>"
           "<span>💹 <b>" + str(mtr) + "</b> बंद-ट्रेड</span></div>")
    return ('<div class="panel gx"><div class="ptitle">🗓️ ' + _MAR_M[mm - 1] +
            " MTD कॅलेंडर — प्रत्येक दिवसाचा निव्वल</div>"
            '<div class="cal">' + "".join(cells) + "</div>" + leg + "</div>")


def _leaderboard(date):
    """🏆 मेडल-लीडरबोर्ड — MTD निव्वलानुसार सर्व मोड्यूल क्रमवारी"""
    rows = [r for r in _month_rows(date) if r["n"] > 0]
    if not rows:
        return ('<div class="panel gx"><div class="ptitle">🏆 मेडल-लीडरबोर्ड '
                "— MTD निव्वलानुसार</div>"
                '<div class="dtempty">अजून बंद-ट्रेड नाहीत — दरवाजे उघडताच इथे '
                "क्रमवारी येईल</div></div>")
    rows.sort(key=lambda r: r["net"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    out = []
    for i, r in enumerate(rows):
        rk = medals[i] if i < 3 else str(i + 1) + "."
        cls = "lbr" + (" top1" if i == 0 else "")
        out.append('<div class="' + cls + '"><span class="rk">' + rk +
                   '</span><span class="nm">' + r["icon"] + " " +
                   _h.escape(r["name"]) + '</span><span class="nt">' +
                   str(r["n"]) + " ट्रेड</span>" + _wr_chip(r["w"], r["l"]) +
                   '<span class="lv">' + _spnl(r["net"]) + "</span></div>")
    tot = round(sum(r["net"] for r in rows), 2)
    foot = ('<div class="lbfoot">एकूण ' + str(len(rows)) +
            " मोड्यूल सक्रिय • MTD निव्वल " + _spnl(tot) + "</div>")
    return ('<div class="panel gx"><div class="ptitle">🏆 मेडल-लीडरबोर्ड — MTD '
            "निव्वलानुसार</div>" + "".join(out) + foot + "</div>")


def _insights(date):
    """🧠 बुद्धीचा डब्बा — डेटामधून आपोआप तयार होणारे विचार (सर्व आकडे खरे, काहीच बनावट नाही)"""
    rows = _month_rows(date)
    act = [r for r in rows if r["n"] > 0]
    bullets = []
    if act:
        tot_net = round(sum(r["net"] for r in rows), 2)
        tot_chg = round(sum(r["chg"] for r in rows), 2)
        best = max(act, key=lambda r: r["net"])
        if best["net"] > 0.005:
            share = int(round(best["net"] * 100.0 / tot_net)) if tot_net > 0.005 else 0
            t = ("🥇 <b>" + _h.escape(best["name"]) + "</b> सध्या सर्वात जबाबदार — " +
                 _spnl(best["net"]) + " (" + str(best["w"]) + "/" +
                 str(best["w"] + best["l"]) + " हिट)")
            if share >= 20:
                t += " — MTD चा " + str(share) + "% इथूनच!"
            bullets.append(t)
        worst = min(act, key=lambda r: r["net"])
        if worst["net"] < -0.005:
            bullets.append("⚠️ <b>" + _h.escape(worst["name"]) +
                           "</b> आडवा येतोय — " + _spnl(worst["net"]) + " (" +
                           str(worst["l"]) +
                           (" तोटा" if worst["l"] == 1 else " तोटे") +
                           ") — याचा दरवाजा आज सावध")
        hist, d0 = {}, None
        try:
            d0 = datetime.strptime(date, "%Y-%m-%d")
            hist = store.daily_net_hist(
                (d0 - timedelta(days=15)).strftime("%Y-%m-%d"))
        except Exception:
            pass
        if d0 is not None:
            streak, sgn = 0, 0
            for i in range(1, 16):
                e = hist.get((d0 - timedelta(days=i)).strftime("%Y-%m-%d"))
                if not e or int(e[2] or 0) == 0:
                    continue
                s = 1 if float(e[0]) > 0.005 else \
                    (-1 if float(e[0]) < -0.005 else 0)
                if s == 0:
                    break
                if sgn == 0:
                    sgn = s
                if s != sgn:
                    break
                streak += 1
            if streak >= 2:
                if sgn > 0:
                    bullets.append("🔥 सातत्य: शेवटचे <b>" + str(streak) +
                                   "</b> ट्रेडिंग-दिवस सलग हिरवे — मोमेंटम चालू")
                else:
                    bullets.append("❄️ सावध: शेवटचे <b>" + str(streak) +
                                   "</b> ट्रेडिंग-दिवस सलग लाल — भांडवलावर पाणी")
        try:
            mhist = store.daily_net_hist(date[:7] + "-01")
        except Exception:
            mhist = {}
        act_days = [(ds, float(v[0])) for ds, v in mhist.items()
                    if abs(float(v[0])) >= 0.005]
        if act_days:
            bd, bnet = max(act_days, key=lambda x: x[1])
            bullets.append("🏆 सर्वोत्तम दिवस <b>" + bd[8:10] + " " +
                           _MAR_M[int(date[5:7]) - 1] + "</b> — " + _spnl(bnet))
        gross = tot_net + tot_chg
        if gross > 0.005 and tot_chg > 0.005:
            pct = tot_chg * 100.0 / gross
            bullets.append("🧾 MTD ब्रोकरेज+टॅक्स <b>" + _inr(tot_chg) +
                           "</b> — gross चा " +
                           ("{:.1f}%".format(pct) if pct < 100 else ">100%") +
                           " (म्हणूच निव्वल-गेट महत्त्वाचा)")
        bullets.append("💼 MTD एकूण निव्वल <b>" + _sign(tot_net) +
                       _inr(abs(tot_net)) + "</b> — " +
                       str(sum(r["n"] for r in rows)) + " बंद-ट्रेड")
    else:
        bullets.append("🌱 अजून बंद-ट्रेड नाहीत — दरवाजे उघडताच इथे आपोआप विचार "
                       "येत राहतील")
    body = "".join('<div class="irow">' + b + "</div>" for b in bullets[:6])
    return '<div class="panel gx ins">' + body + "</div>"


# ----------------------------------------------------------------
# 🤖 AI ब्रेन सल्ला — रात्रीचे स्थानिक-डोक्याचे (Ollama) दैनिक विश्लेषण.
# सल्लागार-विश्लेषणच — AI कधी ऑर्डर/गेट हाताळत नाही; आकडे सगळे खरे
# (store मधून), वाक्ये टेम्पलेटमधून; मॉडेल-मजकूर escape केलेला.
# ----------------------------------------------------------------
def _ai_card(n, date):
    if ai_brain is None or not ai_brain.enabled():
        return ""
    rep = ai_brain.load_report(date)
    stale = ""
    if not rep:
        rep = ai_brain.load_last()
        if rep and rep.get("date") != date:
            stale = str(rep.get("date") or "")
        else:
            rep = None
    if not rep:
        return ('<div class="panel gx"><div class="irow">🤖 आजचे AI-ब्रेन विश्लेषण '
                'रात्री ~20:32 नंतर आपोआप इथे येईल — तोपर्यंत व्यापार '
                'नियम-इंजिनवर सामान्य चालू आहे.</div></div>')
    chips = []
    if rep.get("provider"):
        chips.append("डोके: " + str(rep["provider"]) + ":" + str(rep.get("model") or ""))
    chips.append("वेळ: " + _hhmm(str(rep.get("ts") or "")))
    if rep.get("latency_s") is not None:
        chips.append(str(rep["latency_s"]) + " से")
    if stale:
        chips.append("शेवटचे अहवाल: " + stale)
    tot = float((rep.get("data") or {}).get("total") or 0)
    ok = bool(rep.get("ok"))
    tone = ((rep.get("ai") or {}).get("tone") or "warn") if ok else "neutral"
    tc = {"good": "#4ade80", "warn": "#fbbf24", "bad": "#f87171"}.get(tone, "#94a3b8")
    if ok:
        headline = str((rep.get("ai") or {}).get("headline") or "")
        lines = list(rep.get("lines") or [])[1:]          # headline आधी दाखवला
    else:
        headline = "AI ब्रेन आज उपलब्ध नव्हता"
        lines = list(rep.get("lines") or [])
    head = ('<div style="display:flex;justify-content:space-between;align-items:baseline;'
            'gap:10px;flex-wrap:wrap;margin-bottom:4px">'
            '<div style="font-size:13.4px;font-weight:700;color:' + tc + '">'
            + _h.escape(headline, quote=False) + '</div>'
            '<div class="chips" style="margin-top:0">'
            + "".join('<span class="chip">' + _h.escape(c, quote=False) + '</span>'
                      for c in chips)
            + '<span class="chip">दिवस: ' + _spnl(tot) + '</span></div></div>')
    rows = "".join('<div class="irow">' + _h.escape(str(ln), quote=False)
                   + "</div>" for ln in lines[:7])
    foot = ('<div style="font-size:10.5px;color:#64748b;margin-top:8px">'
            'सल्लागार-विश्लेषण — अंतिम निर्णय नियम-इंजिनचा (9 दरवाजे) • '
            'AI ऑर्डर कधी देत नाही • बंद करायचे: AI_BRAIN_ENABLED=NO</div>')
    return '<div class="panel gx">' + head + rows + foot + "</div>"


# ----------------------------------------------------------------
# 🎯 स्ट्रॅटेजी परफॉर्मन्स ट्रॅकर — निव्वल नाही, गुणवत्ता (PF • अपेक्षा • ग्रेड)
# ----------------------------------------------------------------
def _pgrade(gw, gl):
    """gross नफा/तोटा → (ग्रेड, bg, fg) — A+ सोनी, A हिरवी, B सियान, C पिवळी, D लाल"""
    if gl <= 0.005:
        if gw > 0.005:
            return "A+", "rgba(251,191,36,.16)", "#fbbf24"     # तोटाच नाही
        return "—", "rgba(148,163,184,.12)", "#94a3b8"
    pf = gw / gl
    if pf >= 2:
        return "A", "rgba(16,185,129,.15)", "#4ade80"
    if pf >= 1.5:
        return "B", "rgba(34,211,238,.14)", "#22d3ee"
    if pf >= 1.0:
        return "C", "rgba(245,158,11,.16)", "#fbbf24"
    return "D", "rgba(239,68,68,.16)", "#f87171"


def _perftrack(date):
    """🎯 स्ट्रॅटेजी परफॉर्मन्स ट्रॅकर (MTD, बंद-ट्रेड्सवर) — प्रत्येक मोड्यूलची
    गुणवत्ता: PF • ₹/ट्रेड अपेक्षा • सरासरी नफा/तोटा • सर्वोत्तम/निकृष्ट • ग्रेड"""
    rows = [r for r in _month_rows(date) if r["n"] > 0]
    if not rows:
        return ('<div class="panel gx"><div class="ptitle">🎯 स्ट्रॅटेजी परफॉर्मन्स '
                "ट्रॅकर — गुणवत्ता अभ्यास</div>"
                '<div class="dtempty">अजून बंद-ट्रेड नाहीत — पहिला ट्रेड बंद होताच इथे '
                "प्रत्येक मोड्यूलची गुणवत्ता (PF • ₹/ट्रेड • ग्रेड) दिसेल</div></div>")
    rows.sort(key=lambda r: r["net"], reverse=True)
    trs = []
    for r in rows:
        pn = [float(p) for p in r["pnls"]]
        gw = round(sum(p for p in pn if p > 0), 2)
        gl = round(abs(sum(p for p in pn if p < 0)), 2)
        g, bg, fg = _pgrade(gw, gl)
        nw = sum(1 for p in pn if p > 0)
        nl = sum(1 for p in pn if p < 0)
        if gw > 0.005:
            pf = "∞" if gl <= 0.005 else "{:.2f}".format(gw / gl)
        else:
            pf = "0"
        exp = r["net"] / r["n"]
        aw = (gw / nw) if nw else 0.0
        al = (gl / nl) if nl else 0.0
        btr = _spnl(max(pn)) if pn else "—"
        wtr = _spnl(min(pn)) if pn else "—"
        aw_s = ('<span class="pos">+' + _inr(aw) + "</span>" if aw > 0.005
                else '<span class="m">₹0</span>')
        al_s = ('<span class="neg">−' + _inr(al) + "</span>" if al > 0.005
                else '<span class="m">₹0</span>')
        trs.append(
            '<tr><td><span class="symdot" style="background:' + r["c"] +
            '"></span>' + r["icon"] + " " + _h.escape(r["name"]) + "</td>"
            '<td class="m">' + str(r["n"]) + "</td><td>" + _wr_chip(r["w"], r["l"]) +
            '</td><td class="m">' + pf + "</td><td>" + _spnl(exp) +
            '</td><td class="m">' + aw_s + " / " + al_s + "</td>"
            '<td class="m">' + btr + " / " + wtr + "</td>"
            '<td><span class="grd" style="background:' + bg + ";color:" + fg +
            '">' + g + "</span></td></tr>")
    ths = "".join("<th>" + h + "</th>" for h in
                  ["मोड्यूल", "ट्रेड", "WR", "PF", "₹/ट्रेड",
                   "सरा. नफा / तोटा", "सर्वोत्तम / निकृष्ट", "ग्रेड"])
    foot = ('<div class="lbfoot">PF (Profit Factor) = एकूण नफा ÷ एकूण तोटा — '
            "<b>2.0+</b> उत्कृष्ट • <b>1.5+</b> मजबूत • <b>1.0</b> खाली सावध • "
            "₹/ट्रेड = प्रत्येक ट्रेडची सरासरी अपेक्षा • MTD बंद-ट्रेड्सवर</div>")
    return ('<div class="panel gx"><div class="ptitle">🎯 स्ट्रॅटेजी परफॉर्मन्स ट्रॅकर — '
            "गुणवत्ता अभ्यास (MTD)</div>"
            '<table class="tbl has perf"><thead><tr>' + ths + "</tr></thead><tbody>" +
            "".join(trs) + "</tbody></table>" + foot + "</div>")


# ----------------------------------------------------------------
# ⏱️ पैसा कधी कमावतो? — बुकिंग-तास अभ्यास (super-mind: सुरुवातीपासूनचा इतिहास)
# ----------------------------------------------------------------
def _timeatlas(date):
    """⏱️ सर्व बंद-ट्रेड्स (तिन्ही मोड्यूल-कुटुंब) चा बुकिंग-तास अभ्यास —
    कोणत्या तासात नफा आणि कोणत्या तासात तोटा बुक होतो, एका दृष्टीत"""
    try:
        rows = store.all_closed_pnl_hours()
    except Exception:
        rows = []
    if len(rows) < 3:
        return ('<div class="panel gx"><div class="ptitle">⏱️ पैसा कधी कमावतो? — '
                "बुकिंग-तास अभ्यास</div>"
                '<div class="dtempty">अजून माहिती जमा होत आहे (आतापर्यंत ' +
                str(len(rows)) + " बंद-ट्रेड • किमान 3 लागतील) — नंतर इथे कोणत्या "
                "तासात नफा आणि कोणत्या तासात तोटा बुक होतो ते दिसेल</div></div>")
    bk = {}
    for cs, pnl in rows:
        m = _re.search(r"(\d{1,2}):\d{2}", str(cs or ""))
        if not m:
            continue
        h = int(m.group(1))
        if h < 4 or h > 23:
            continue
        b = bk.setdefault(h, [0.0, 0])
        b[0] += float(pnl or 0)
        b[1] += 1
    if not bk:
        return ('<div class="panel gx"><div class="ptitle">⏱️ पैसा कधी कमावतो?</div>'
                '<div class="dtempty">बुकिंग-वेळ वाचता आली नाही</div></div>')
    hours = sorted(bk)
    mx = max(abs(bk[h][0]) for h in hours) or 1.0
    cols = []
    for h in hours:
        net, ntr = bk[h]
        nxt = (h + 1) % 24
        tip = (f"{h:02d}:00–{nxt:02d}:00 • निव्वल " + _sign(net) + _inr(abs(net)) +
               " • " + str(ntr) + " ट्रेड")
        bh = int(round((abs(net) / mx) ** 0.5 * 46))
        bar = ""
        if abs(net) >= 0.005 and bh >= 3:
            bar = ('<i class="thb ' + ("up" if net > 0 else "dn") +
                   '" style="height:' + str(max(5, bh)) + '%"></i>')
        cols.append('<div class="thc" title="' + _h.escape(tip) +
                    '"><div class="thw">' + bar + '</div><div class="thl">' +
                    f"{h:02d}" + "</div></div>")
    best = max(hours, key=lambda h: bk[h][0])
    worst = min(hours, key=lambda h: bk[h][0])
    nall = sum(bk[h][1] for h in hours)
    calls = []
    if bk[best][0] > 0.005:
        calls.append(f'🏆 सर्वोत्तम बुकिंग-तास <b>{best:02d}:00–{(best + 1) % 24:02d}:00</b> — ' +
                     _sign(bk[best][0]) + _inr(abs(bk[best][0])) +
                     " (" + str(bk[best][1]) + " ट्रेड)")
    if bk[worst][0] < -0.005:
        calls.append(f'⚠️ काळजीचा तास <b>{worst:02d}:00–{(worst + 1) % 24:02d}:00</b> — ' +
                     _sign(bk[worst][0]) + _inr(abs(bk[worst][0])) +
                     " — या तासात सावध एंट्री")
    calls.append("📊 एकूण <b>" + str(nall) + "</b> बंद-ट्रेड (सुरुवातीपासून) • सर्व "
                 "मोड्यूल एकत्र")
    body = ('<div class="tstrip">' + "".join(cols) + "</div>"
            '<div class="tcall">' +
            "".join('<span class="tchip">' + c + "</span>" for c in calls) + "</div>"
            '<div class="tnote">बुकिंग-तास = ट्रेड बंद झाला तो तास • उभा दांडा = त्या '
            "तासाचे एकूण निव्वल (वर हिरवा = नफा, खाली लाल = तोटा) • hover वर तपशील</div>")
    return ('<div class="panel gx"><div class="ptitle">⏱️ पैसा कधी कमावतो? — '
            "बुकिंग-तास अभ्यास</div>" + body + "</div>")


# ----------------------------------------------------------------
# 🛡️ धोका-तापमान • 📉 इक्विटी-कर्व्ह • 📆 वार-विश्लेषण (super-mind बॅच)
# ----------------------------------------------------------------
def _rk_col(used, halted):
    """मर्यादा-वापर टक्केवारी → (बार/पेक्ट-रंग) — हिरवा→पिवळा→केशरी→लाल"""
    if halted or used >= 100:
        return "#f87171"
    if used >= 80:
        return "#fb923c"
    if used >= 50:
        return "#fbbf24"
    return "#34d399"


def _riskheat(n, date):
    """🛡️ धोका-तापमान — प्रत्येक दरवाजाची दैनिक तोटा-मर्यादा किती वापरली गेली?
    थांब-मर्यादेला किती जवळ आहोत ते एका दृष्टीत (आज NIFTY 140% / COPPER 104%
    प्रमाणे घटना आधीच दिसायला हव्या होत्या — हा पॅनेल तेच आधी दाखवतो)"""
    rows_html = []
    worst_pct, worst_nm = 0.0, ""
    n_halt, halt_names = 0, []
    tot_day, tot_lim = 0.0, 0.0
    for s in C.active_symbols():
        st = SYM_STYLE.get(s["key"], {"c": "#818cf8", "icon": "📊"})
        day = store.today_pnl(date, s["key"])
        lim = float(s.get("max_daily_loss") or 0)
        halted = store.get_state("halt_" + date + "_" + s["key"]) == "1"
        used = 0.0 if (day >= 0 or lim <= 0) else min(200.0, -day / lim * 100.0)
        tot_day += day
        tot_lim += lim
        col = _rk_col(used, halted)
        if halted:
            n_halt += 1
            halt_names.append(s["short"])
        elif used > worst_pct:
            worst_pct, worst_nm = used, s["short"]
        fill = ('<i class="rkfill" style="width:' +
                str(round(min(used, 100.0), 1)) + "%;background:" + col + '"></i>')
        val = ('<span class="' + _cls(day) + '">' + _sign(day) + _inr(abs(day)) +
               '</span><span class="m"> / −' + _inr(lim) + "</span>")
        pct_s = ("{:.0f}%".format(used) if used >= 0.5 else "0%")
        badge = ('<span class="badge closed" style="margin-left:6px">🛑</span>'
                 if halted else "")
        rows_html.append(
            '<div class="rk"><span class="nm"><span class="symdot" style="background:' +
            st["c"] + '"></span>' + st["icon"] + " " + _h.escape(s["short"]) + badge +
            '</span><div class="rkbar">' + fill + '</div><span class="rkval">' + val +
            '</span><span class="rkpct" style="color:' + col + '">' + pct_s + "</span></div>")
    if n_halt:
        verdict = ('🔴 <b>' + str(n_halt) + " दरवाजा हॉल्ट</b> (" +
                   ", ".join(halt_names) + ") — आजचे नवे ट्रेड बंद")
    elif worst_pct >= 100:
        verdict = ('🔴 <b>' + _h.escape(worst_nm) + "</b> मर्यादा ओलांडली — थांब-नियम सक्रिय")
    elif worst_pct >= 80:
        verdict = ('🟠 <b>' + _h.escape(worst_nm) + "</b> मर्यादेच्या " +
                   "{:.0f}%".format(worst_pct) + " वर — पुढचा तोटा हॉल्ट ओलांडेल")
    elif worst_pct >= 50:
        verdict = ('🟡 <b>' + _h.escape(worst_nm) + "</b> मर्यादेच्या " +
                   "{:.0f}%".format(worst_pct) + " वर — लक्ष द्या")
    else:
        verdict = "🟢 सर्व दरवाजे निरोगी — आज एकही मर्यादा धोक्यात नाही"
    agg_used = (0.0 if (tot_day >= 0 or tot_lim <= 0)
                else min(200.0, -tot_day / tot_lim * 100.0))
    agg = ('<div class="rkagg"><span class="tchip">एकत्र आजचा निव्वल ' + _spnl(tot_day) +
           '</span><span class="tchip">एकत्र मर्यादा −' + _inr(tot_lim) +
           '</span><span class="tchip">एकत्र वापर ' + "{:.0f}%".format(agg_used) +
           "</span></div>")
    note = ('<div class="rknote">' + verdict + " • मर्यादा = प्रति-दरवाजा दैनिक तोटा-थांब "
            "(max_daily_loss) • हॉल्ट झालेला दरवाजा आज नवे ट्रेड घेत नाही — बाकीचे "
            "दरवाजे चालू राहतात • उजवीकडे: आजचा निव्वल / मर्यादा</div>")
    return ('<div class="panel gx"><div class="ptitle">🛡️ धोका-तापमान — दैनिक तोटा-मर्यादा '
            "किती वापरली?</div><div class=\"rkgrid\">" + "".join(rows_html) + "</div>" +
            agg + note + "</div>")


def _equity(date):
    """📉 इक्विटी-कर्व्ह — या महिन्याचा संचित बंद-ट्रेड निव्वल (सर्व मोड्यूल एकत्र),
    दिवस-दर-दिवस; शिखर-बिंदू, मॅक्स-ड्रॉडाउन-बिंदू आणि सारांश-चिप्ससह"""
    ym = date[:7]
    try:
        hist = store.daily_net_hist(ym + "-01")
    except Exception:
        hist = {}
    yy, mm = int(ym[:4]), int(ym[5:7])
    ndays = calendar.monthrange(yy, mm)[1]
    today_i = min(int(date[8:10]), ndays)
    days = [ym + "-" + ("%02d" % d) for d in range(1, today_i + 1)]
    pts, cum = [], 0.0
    for ds in days:
        e = hist.get(ds)
        if e:
            cum += float(e[0] or 0)
        pts.append((ds, cum))
    if not pts or max(abs(v) for _, v in pts) < 0.005:
        return ('<div class="panel gx"><div class="ptitle">📉 इक्विटी-कर्व्ह — ' +
                _MAR_M[mm - 1] + " MTD संचित निव्वल</div>"
                '<div class="dtempty">या महिन्यात अजून बंद-ट्रेड नाहीत — पहिला ट्रेड '
                "बंद होताच इक्विटी-कर्व्ह उभी राहील</div></div>")
    vals = [v for _, v in pts]
    W, H, P = 640, 150, 12
    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    span = (hi - lo) or 1.0

    def xy(i, v):
        x = P + (i * (W - 2 * P) / max(1, len(pts) - 1))
        y = P + (hi - v) / span * (H - 2 * P)
        return round(x, 1), round(y, 1)

    pstr = " ".join("{:.1f},{:.1f}".format(*xy(i, v)) for i, v in enumerate(vals))
    zero_y = xy(0, 0)[1]
    final = vals[-1]
    curve_col = ("#34d399" if final > 0.005 else
                 ("#f87171" if final < -0.005 else "#94a3b8"))
    peak_i = max(range(len(vals)), key=lambda i: vals[i])
    run_pk, maxdd, dd_i, dd_pk = 0, 0.0, 0, 0
    for i, v in enumerate(vals):
        if v > vals[run_pk]:
            run_pk = i
        if vals[run_pk] - v > maxdd:
            maxdd, dd_i, dd_pk = vals[run_pk] - v, i, run_pk
    lx, ly = xy(len(pts) - 1, final)
    px, py = xy(peak_i, vals[peak_i])
    dx, dy = xy(dd_i, vals[dd_i])
    svg = (f'<svg class="eqsvg" viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
           f'role="img" aria-label="MTD इक्विटी-कर्व्ह">'
           f'<defs><linearGradient id="eqg" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{curve_col}" stop-opacity="0.22"/>'
           f'<stop offset="1" stop-color="{curve_col}" stop-opacity="0.02"/>'
           f'</linearGradient></defs>'
           f'<line x1="{P}" y1="{zero_y}" x2="{W - P}" y2="{zero_y}" '
           f'stroke="#475569" stroke-width="1" stroke-dasharray="4 4"/>'
           f'<polygon points="{pstr} {W - P},{zero_y} {P},{zero_y}" fill="url(#eqg)"/>'
           f'<polyline points="{pstr}" fill="none" stroke="{curve_col}" '
           f'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
           f'<circle cx="{px}" cy="{py}" r="3.6" fill="#fbbf24">'
           f"<title>शिखर {_sign(vals[peak_i])}{_inr(abs(vals[peak_i]))}</title></circle>")
    if maxdd > 0.005:
        svg += (f'<circle cx="{dx}" cy="{dy}" r="3.6" fill="#f87171">'
                f"<title>मॅक्स ड्रॉडाउन −{_inr(maxdd)}</title></circle>")
    svg += (f'<circle cx="{lx}" cy="{ly}" r="4" fill="{curve_col}">'
            f"<title>आता {_sign(final)}{_inr(abs(final))}</title></circle>")
    for i in sorted({0, len(pts) // 2, len(pts) - 1}):
        x, _y = xy(i, lo)
        svg += (f'<text x="{x}" y="{H - 1}" font-size="9" fill="#64748b" '
                f'text-anchor="middle">{i + 1}</text>')
    svg += "</svg>"
    chips = ['<span class="tchip">📈 आता: <b class="' + _cls(final) + '">' +
             _sign(final) + _inr(abs(final)) + "</b></span>",
             '<span class="tchip">⛰ शिखर: <b class="pos">' + _inr(vals[peak_i]) +
             "</b> (" + str(int(pts[peak_i][0][8:10])) + " " + _MAR_M[mm - 1] + ")</span>"]
    if maxdd > 0.005:
        chips.append('<span class="tchip">🕳 मॅक्स ड्रॉडाउन: <b class="neg">−' +
                     _inr(maxdd) + "</b> (" + str(int(pts[dd_i][0][8:10])) + " " +
                     _MAR_M[mm - 1] + ")</span>")
    cur_dd = vals[run_pk] - final
    if cur_dd > 0.005:
        chips.append('<span class="tchip">💧 सध्याचा ड्रॉडाउन: <b class="neg">−' +
                     _inr(cur_dd) + "</b></span>")
    st_w = st_l = cw = cl = 0
    for ds in days:
        e = hist.get(ds)
        net = float(e[0]) if e else 0.0
        if net > 0.005:
            cw, cl = cw + 1, 0
        elif net < -0.005:
            cl, cw = cl + 1, 0
        else:
            cw = cl = 0
        st_w = max(st_w, cw)
        st_l = max(st_l, cl)
    if st_w >= 2:
        chips.append('<span class="tchip">🔥 सलग <b class="pos">' + str(st_w) +
                     "</b> हिरवे दिवस</span>")
    if st_l >= 2:
        chips.append('<span class="tchip">❄️ सलग <b class="neg">' + str(st_l) +
                     "</b> लाल दिवस</span>")
    return ('<div class="panel gx"><div class="ptitle">📉 इक्विटी-कर्व्ह — ' +
            _MAR_M[mm - 1] + " MTD संचित बंद-ट्रेड निव्वल (सर्व मोड्यूल एकत्र)</div>" +
            svg + '<div class="tcall">' + "".join(chips) + "</div>"
            '<div class="tnote">पिवळा बिंदू = महिन्याचे शिखर • लाल बिंदू = मॅक्स '
            "ड्रॉडाउन • डॅश-ओळ = ₹0 • hover वर आकडे</div></div>")


def _weekday(date):
    """📆 वार-विश्लेषण — 'कोणत्या वारी पैसा कमावतो?' (सुरुवातीपासून सर्व मोड्यूल;
    ⏱️ बुकिंग-तास अभ्यासाचा वार-बहिण)"""
    try:
        hist = store.daily_net_hist("2000-01-01")
    except Exception:
        hist = {}
    agg = {}
    for ds, e in hist.items():
        try:
            wd = datetime.strptime(ds, "%Y-%m-%d").weekday()
        except ValueError:
            continue
        b = agg.setdefault(wd, [0.0, 0])
        b[0] += float(e[0] or 0)
        b[1] += int(e[2] or 0)
    n_all = sum(v[1] for v in agg.values())
    if n_all < 1:
        return ('<div class="panel gx"><div class="ptitle">📆 वार-विश्लेषण — कोणत्या '
                'वारी पैसा कमावतो?</div><div class="dtempty">अजून बंद-ट्रेड नाहीत — '
                "ट्रेड सुरू झाल्यावर प्रत्येक वारीची कमाई इथे दिसेल</div></div>")
    mx = max([abs(v[0]) for v in agg.values() if v[1]] or [1.0])
    rows = []
    for wd in range(6):                    # सोम–शनि (रविवारी बाजार बंदच)
        net, ntr = agg.get(wd, [0.0, 0])
        w = int(round(abs(net) / mx * 92)) if (ntr and abs(net) >= 0.005) else 0
        col = ("linear-gradient(90deg,#34d399,#059669)" if net > 0 else
               "linear-gradient(90deg,#f87171,#b91c1c)")
        fill = ('<i class="wkfill" style="width:' + str(w) + "%;background:" + col +
                '"></i>') if w else ""
        val = (_spnl(net) if abs(net) >= 0.005 else '<span class="m">—</span>')
        cnt = ('<span class="m"> • ' + str(ntr) + " ट्रेड</span>") if ntr else ""
        rows.append('<div class="wk' + ("" if ntr else " dim") + '"><span class="wkl">' +
                    _MAR_W[wd] + 'वार</span><div class="wkbar">' + fill +
                    '</div><span class="wkv">' + val + cnt + "</span></div>")
    act = [(wd, v) for wd, v in agg.items() if v[1]]
    best = max(act, key=lambda x: x[1][0])
    worst = min(act, key=lambda x: x[1][0])
    calls = ['🏆 सर्वोत्तम वार: <b>' + _MAR_W[best[0]] + "वार</b> " + _spnl(best[1][0])]
    if worst[1][0] < -0.005:
        calls.append('⚠️ काळजीचा वार: <b>' + _MAR_W[worst[0]] + "वार</b> " +
                     _spnl(worst[1][0]))
    calls.append("📊 एकूण <b>" + str(n_all) + "</b> बंद-ट्रेड (सुरुवातीपासून)")
    return ('<div class="panel gx"><div class="ptitle">📆 वार-विश्लेषण — कोणत्या वारी '
            'पैसा कमावतो?</div><div class="wkgrid">' + "".join(rows) + "</div>"
            '<div class="tcall">' +
            "".join('<span class="tchip">' + c + "</span>" for c in calls) + "</div>"
            '<div class="tnote">दांडा = त्या वारीचे एकूण निव्वल (हिरवा = नफा, लाल = तोटा) '
            "• सुरुवातीपासून सर्व मोड्यूल एकत्र</div></div>")


def _calduo(date):
    """🗓️ कॅलेंडर-हीटमॅप + 🏆 लीडरबोर्ड — महिन्याच्या आढाव्याची जोडी"""
    return ('<div class="duo calduo">' + _calheat(date) + _leaderboard(date) +
            "</div>")


# ----------------------------------------------------------------
# 📈 ट्रेड-लाइव्ह कॅन्डल-चार्ट — ट्रेड झालेल्या प्रत्येक instrument चे आजचे
# कॅन्डल (Upstox 1-मिनिट) + एंट्री/SL/TP ओळी + एग्झिट-बिंदू. 55 से कॅशमुळे
# API वर ताण नाही (प्रति instrument एक मिनिटाला जास्तीत जास्त 1 विचारणा).
# ----------------------------------------------------------------
_CCH = {}                                  # option_key -> (epoch, candles|[])


def _hhmm_min(s):
    """कोणतीही वेळ-स्ट्रिंग → दिवसाच्या मिनिटांत (नाही तर None)"""
    m = _re.search(r"(\d{1,2}):(\d{2})", str(s or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _candles_cached(okey, date):
    """1-मिनिट कॅन्डल — कॅश 55 से (ताजे) / 20 से (अपयश); टोकन नसेल None"""
    if not okey:
        return None
    now = time.time()
    e = _CCH.get(okey)
    if e and (now - e[0]) < (55 if e[1] else 20):
        return e[1]
    tok = store.get_state("upstox_token") or ""
    if not tok:
        return None
    try:
        import upstox_api as U
        cs = U.get_today_candles(tok, okey, date) or []
    except Exception:
        cs = []
    _CCH[okey] = (now, cs)
    return cs


def _aggc(cs, step):
    """1-मिनिट → step-मिनिट बंडल [(min, o, h, l, c)]"""
    b = {}
    for c in cs:
        m = _hhmm_min(c[0])
        if m is None:
            continue
        k = (m // step) * step
        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        e = b.get(k)
        if e is None:
            b[k] = [o, h, l, cl]
        else:
            if h > e[1]:
                e[1] = h
            if l < e[2]:
                e[2] = l
            e[3] = cl
    return [(k, v[0], v[1], v[2], v[3]) for k, v in sorted(b.items())]


def _svg_candles(ac, tr, o0, o1):
    """बंडल-कॅन्डल्स + E/SL/TP ओळी + एग्झिट-बिंदू → SVG (डेटा नसेल None)"""
    if not ac or len(ac) < 2:
        return None
    W, H = 760.0, 240.0
    pl, pr, pt, pb = 10.0, 60.0, 16.0, 27.0
    entry = float(tr.get("entry") or 0)
    lo = min(c[3] for c in ac)
    hi = max(c[2] for c in ac)
    if hi <= lo:
        hi = lo + max(0.5, abs(lo) * 0.002)
    sp = (hi - lo) * 0.08
    lo, hi = lo - sp, hi + sp
    lo, hi = min(lo, entry), max(hi, entry)
    sl = float(tr.get("sl") or 0)
    tp = float(tr.get("target") or 0)
    rng = hi - lo
    for v in (sl, tp):
        if v > 0 and (lo - rng * 0.6) <= v <= (hi + rng * 0.6):
            lo, hi = min(lo, v), max(hi, v)

    def Y(p):
        p = min(max(p, lo), hi)
        return round(pt + (hi - p) / (hi - lo) * (H - pt - pb), 1)

    nb = len(ac)
    slot = (W - pl - pr) / nb
    cw = min(13.0, max(2.2, slot * 0.62))
    parts = []
    for gi in range(4):                     # क्षितिज-रेषा + किंमत-लेबल
        p = lo + (hi - lo) * gi / 3.0
        y = Y(p)
        plab = "{:.1f}".format(p) if abs(p) < 1000 else "{:.0f}".format(p)
        parts.append(f'<line x1="{pl}" y1="{y}" x2="{W - pr}" y2="{y}" '
                     f'stroke="rgba(148,163,184,.10)" stroke-width="1"/>')
        parts.append(f'<text x="{W - pr + 5}" y="{round(y + 3.2, 1)}" font-size="9.5" '
                     f'fill="#64748b" font-family="monospace">{plab}</text>')
    for i, (m, o, h, l, c) in enumerate(ac):   # कॅन्डल (hover-टिपसह)
        x = round(pl + i * slot + slot / 2 - cw / 2, 1)
        xc = round(x + cw / 2, 1)
        col = "#34d399" if c >= o else "#f87171"
        tip = (f"{m // 60:02d}:{m % 60:02d} • O {o:.1f} H {h:.1f} "
               f"L {l:.1f} C {c:.1f}")
        yo, yc, yh, yl = Y(o), Y(c), Y(h), Y(l)
        parts.append(f'<g><title>{_h.escape(tip)}</title>'
                     f'<line x1="{xc}" y1="{yh}" x2="{xc}" y2="{yl}" '
                     f'stroke="{col}" stroke-width="1"/>'
                     f'<rect x="{x}" y="{min(yo, yc)}" width="{round(cw, 1)}" '
                     f'height="{max(1.4, abs(yo - yc))}" fill="{col}" rx="1"/></g>')

    def hline(p, col, lab, right):
        """क्षैतिज सूचक-रेषा (एंट्री/SL/TP) — लेबलसह"""
        if p <= 0:
            return ""
        y = Y(p)
        if right:
            tx, anch = W - pr - 5, "end"
        else:
            tx, anch = pl + 5, "start"
        return (f'<line x1="{pl}" y1="{y}" x2="{W - pr}" y2="{y}" stroke="{col}" '
                f'stroke-width="1.2" stroke-dasharray="5 4" opacity=".85"/>'
                f'<text x="{round(tx, 1)}" y="{round(y - 4, 1)}" font-size="10" '
                f'font-weight="700" fill="{col}" text-anchor="{anch}" '
                f'style="paint-order:stroke" stroke="#04060c" '
                f'stroke-width="3">{lab}</text>')

    parts.append(hline(entry, "#38bdf8", "E {:g}".format(entry), False))
    parts.append(hline(sl, "#f87171", "SL {:g}".format(sl), True))
    parts.append(hline(tp, "#34d399", "TP {:g}".format(tp), True))
    ex = tr.get("exit")
    if tr.get("status") != "OPEN" and ex:   # एग्झिट-बिंदू
        em = min(max(_hhmm_min(tr.get("closed")) or o0, o0), o1)
        xe = round(pl + (em - o0) / max(1, o1 - o0) * (W - pl - pr), 1)
        ye = Y(float(ex))
        parts.append(f'<circle cx="{xe}" cy="{ye}" r="4" fill="#e2e8f0" '
                     f'stroke="#04060c" stroke-width="1.5">'
                     f'<title>एग्झिट {_hhmm(tr.get("closed"))} • '
                     f'₹{float(ex):.2f}</title></circle>')
    for f_ in (0.0, 1 / 3.0, 2 / 3.0, 1.0):  # वेळ-लेबल
        m = int(o0 + (o1 - o0) * f_)
        tx = pl + (W - pl - pr) * f_
        anch = "middle"
        if f_ == 0.0:
            anch = "start"
        elif f_ == 1.0:
            anch = "end"
        parts.append(f'<text x="{round(tx, 1)}" y="{H - 9}" font-size="9.5" '
                     f'fill="#64748b" text-anchor="{anch}" '
                     f'font-family="monospace">{m // 60:02d}:{m % 60:02d}</text>')
    return ('<svg class="csvg" viewBox="0 0 760 240" '
            'preserveAspectRatio="xMidYMid meet" '
            'xmlns="http://www.w3.org/2000/svg">' + "".join(parts) + "</svg>")


def _tcard(tr, n, date):
    """एका ट्रेडचे चार्ट-कार्ड — शीर्षक + SVG + E/SL/TP/LTP/निव्वल चिप्स"""
    is_mcx = str(tr["okey"] or "").upper().startswith("MCX")
    mo, mc = (540, 1410) if is_mcx else (555, 930)
    om = _hhmm_min(tr.get("opened")) or (545 if is_mcx else 560)
    if tr["status"] == "OPEN":
        em = n.hour * 60 + n.minute
    else:
        em = _hhmm_min(tr.get("closed")) or om + 30
    o0 = max(mo, om - 25)
    o1 = min(mc, max(em + 25, o0 + 20))
    cs = _candles_cached(tr["okey"], date)
    svg = None
    ltp = None
    if cs:
        step = 1 if (o1 - o0) <= 90 else (5 if (o1 - o0) <= 480 else 15)
        ac = [c for c in _aggc(cs, step) if o0 <= c[0] <= o1]
        svg = _svg_candles(ac, tr, o0, o1)
        if ac:
            ltp = ac[-1][4]
    cp = "CE" if "CE" in str(tr["okey"] or "").upper() else \
         ("PE" if "PE" in str(tr["okey"] or "").upper() else "")
    nm = (tr["icon"] + ' <span style="color:' + tr["c"] + '">' +
          _h.escape(tr["sym"]) + "</span> <small>" +
          f'{float(tr["strike"] or 0):,.0f} {cp}</small>')
    sideb = ('<span class="sbu">BUY</span>' if tr["side"] == "BUY"
             else '<span class="sbd">SELL</span>')
    statb = ('<span class="badge open">◉ चालू</span>' if tr["status"] == "OPEN"
             else '<span class="badge closed">पूर्ण</span>')
    tend = "आता" if tr["status"] == "OPEN" else _hhmm(tr.get("closed"))
    tms = _hhmm(tr.get("opened")) + " → " + tend
    if svg:
        body = svg
    elif not (store.get_state("upstox_token") or ""):
        body = ('<div class="tcno">🔇 Upstox टोकन नाही — चार्टसाठी टोकन लागते '
                "(Telegram वर /code). बाकी आकडे बरोबर आहेत</div>")
    else:
        body = ('<div class="tcno">🔇 कॅन्डल डेटा आला नाही (API) — पुढील '
                "रिफ्रेशमध्ये पुन्हा प्रयत्न होईल</div>")
    chips = ['<span class="chip">E ₹{:,.2f}</span>'.format(float(tr["entry"] or 0))]
    if tr.get("sl"):
        chips.append('<span class="chip hot">SL ₹{:,.2f}</span>'.format(float(tr["sl"])))
    if tr.get("target"):
        chips.append('<span class="chip good">TP ₹{:,.2f}</span>'.format(
            float(tr["target"])))
    if ltp:
        chips.append('<span class="chip">LTP ₹{:,.2f}</span>'.format(float(ltp)))
    if tr["status"] != "OPEN" and tr.get("pnl") is not None:
        chips.append('<span class="chip">निव्वल ' + _spnl(float(tr["pnl"])) +
                     "</span>")
    if tr.get("reason"):
        chips.append('<span class="chip">' + _h.escape(str(tr["reason"]))[:42] +
                     "</span>")
    return (f'<div class="tcard gx"><div class="tchead"><span class="tcn">{nm}</span>'
            f'{sideb}{statb}<span class="tct">{tms}</span></div>{body}'
            f'<div class="tcchips">{"".join(chips)}</div></div>')


def _tradecharts(n, date):
    """📈 आज ट्रेड झालेल्या प्रत्येक instrument चे लाइव्ह कॅन्डल-चार्ट-कार्ड
    (चालू आधी, मग शेवटचे बंद — जास्तीत जास्त 6)"""
    tds = []
    for t in store.trades_today(date):
        S = _sym_of(t.get("symbol") or "BANKNIFTY")
        st = SYM_STYLE.get(t.get("symbol") or "BANKNIFTY",
                           {"c": "#818cf8", "icon": "📊"})
        tds.append({"okey": t.get("option_key"),
                    "sym": S["short"] if S else (t.get("symbol") or "?"),
                    "icon": st["icon"], "c": st["c"],
                    "strike": t.get("strike") or 0, "side": t.get("side"),
                    "entry": t.get("entry"), "sl": t.get("sl"),
                    "target": t.get("target"), "opened": t.get("opened"),
                    "closed": t.get("closed"), "status": t.get("status"),
                    "exit": t.get("exit"), "pnl": t.get("pnl"),
                    "reason": t.get("reason")})
    if swing is not None:
        for t in store.swing_today(date):
            tds.append({"okey": t.get("option_key"),
                        "sym": str(t.get("symbol") or "?"), "icon": "🎯",
                        "c": "#22d3ee", "strike": t.get("strike") or 0,
                        "side": t.get("side"), "entry": t.get("entry"),
                        "sl": t.get("sl"), "target": None,
                        "opened": t.get("opened") or "09:20",
                        "closed": t.get("closed"), "status": t.get("status"),
                        "exit": t.get("exit_price"), "pnl": t.get("pnl"),
                        "reason": t.get("reason")})
    if family is not None:
        for t in store.family_today(date):
            fs = FAM_STYLE.get(t.get("member"), {"c": "#f59e0b", "icon": "👨‍👩‍👧"})
            tds.append({"okey": t.get("option_key"),
                        "sym": "Family " + str(t.get("member") or ""),
                        "icon": fs["icon"], "c": fs["c"],
                        "strike": t.get("strike") or 0, "side": t.get("side"),
                        "entry": t.get("entry"), "sl": t.get("sl"),
                        "target": t.get("target"),
                        "opened": t.get("opened") or "09:35",
                        "closed": t.get("closed"), "status": t.get("status"),
                        "exit": t.get("exit_price"), "pnl": t.get("pnl"),
                        "reason": t.get("reason")})
    if not tds:
        return ('<div class="panel gx"><div class="ptitle">📈 ट्रेड-लाइव्ह '
                "कॅन्डल-चार्ट</div>"
                '<div class="empty"><div class="e1">🌙</div>आज अजून ट्रेड नाही<br>'
                "<small>पहिलाच ट्रेड झाल्यावर त्या instrument चा लाइव्ह कॅन्डल-चार्ट "
                "इथे येईल — एंट्री • SL • टार्गेट ओळींसह, दर 10 सेकंदांनी ताजा</small>"
                "</div></div>")
    opn = [t for t in tds if t["status"] == "OPEN"]
    clz = sorted([t for t in tds if t["status"] != "OPEN"],
                 key=lambda t: str(t.get("closed") or ""), reverse=True)
    shown = (opn + clz)[:6]
    extra = len(tds) - len(shown)
    cards = "".join(_tcard(t, n, date) for t in shown)
    note = ('<div class="tnote">🔵 E = एंट्री • लाल SL • हिरवा TP • ⚪ एग्झिट-बिंदू • '
            "कॅन्डलवर hover = O/H/L/C • 1-मिनिट डेटा 5/15-मिनिटांत बंडल • "
            "55 सेकंद कॅश — दर 10 सेकंदांनी ताजे</div>")
    if extra > 0:
        note = ('<div class="tnote">… आणि आजचे आधीचे ' + str(extra) +
                " ट्रेड — सर्व 💹 ट्रेड्स टेबलमध्ये</div>" + note)
    return '<div class="tcards">' + cards + "</div>" + note


def _nav(swing_on, family_on):
    """🔝 स्टिकी जंप-नेव्ह — लांब डॅशबोर्डवर एका-क्लिकमध्ये विभागापर्यंत"""
    links = [("sec-kpi", "📊 स्थिती"), ("sec-ins", "🧠 बुद्धी"),
             ("sec-perf", "🎯 ट्रॅकर"), ("sec-time", "⏱️ वेळ"),
             ("sec-risk", "🛡️ रिस्क"), ("sec-gates", "🚪 दरवाजे")]
    if swing_on:
        links.append(("sec-swing", "🎯 Swing"))
    if family_on:
        links.append(("sec-family", "👨‍👩‍👧 Family"))
    links += [("sec-tl", "🕒 वेळापत्रक"), ("sec-ov", "📡 आढावा"),
              ("sec-chart", "📈 चार्ट"), ("sec-hist", "📅 MTD"),
              ("sec-tr", "💹 ट्रेड्स")]
    items = "".join('<a href="#' + a + '">' + t + "</a>" for a, t in links)
    return '<div class="nav">' + items + "</div>"


def _swing_scan_rows(date):
    rows = store.swing_scan_today(date)
    if not rows:
        return ('<div class="row" style="color:#475569">आजचा स्कॅन अजून झाला नाही '
                '(रोज 09:20 नंतर)…</div>')
    out = []
    for r in rows[:10]:
        icon = "🎯" if r["triggered"] else ("👁" if r["trend"] else "—")
        spot = ("₹{:,.2f}".format(r["spot"]) if r["spot"] else "—")
        hi = ("₹{:,.2f}".format(r["prev_high"]) if r["prev_high"] else "—")
        out.append(f'<div class="row"><span class="tm">{icon}</span>'
                   f'<span>{_h.escape(str(r["symbol"]))} · {spot} · '
                   f'हाय {hi} · {_h.escape(str(r["note"] or ""))}</span></div>')
    return "".join(out)


def _swing(n, date):
    """🎯 Swing विभाग — वैयक्तिक शेअर्सचे ऑप्शन-बायिंग (स्वतंत्र ₹1L बाजू)"""
    if swing is None or not getattr(swing, "ENABLED", False):
        return ""
    cap = swing._capital()
    opens = store.swing_open()
    dep = swing.deployed_premium()
    orisk = swing.open_risk()
    mts = [t for t in store.swing_month(date[:7]) if t["status"] == "CLOSED"]
    mtd = round(sum((t["pnl"] or 0) for t in mts), 2)
    tot = store.swing_total_pnl()
    risk_pct = min(100.0, orisk / swing.OPEN_RISK_CAP * 100.0) \
        if swing.OPEN_RISK_CAP else 0

    # 📋 Swing तपशील — आजचे swing ट्रेड्स + सर्व swing इव्हेंट
    mid = n.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        sw_evs = store.events_for(["Swing"], since_ts=mid - 3 * 86400, limit=200)
    except Exception:
        sw_evs = []
    sw_today = store.swing_today(date)
    sw_rows = []
    for t in sw_today:
        pnl = t.get("pnl")
        ic = "◉" if t["status"] == "OPEN" else ("✅" if (pnl or 0) >= 0 else "❌")
        ex = f" → ₹{float(t['exit']):.2f}" if t.get("exit") else ""
        pnl_s = (f'<span class="{_cls(pnl)}">{_sign(pnl)}{_inr(abs(pnl))}</span>'
                 if pnl is not None else '<span class="m">चालू</span>')
        reason = _h.escape(str(t.get("reason") or ""))[:48] or "—"
        held = swing.sessions_held(t["date"], date)
        sw_rows.append(
            f'<div class="trow">{ic} {_hhmm(t.get("opened") or t["date"])} • '
            f'{_h.escape(t["symbol"])} {t["strike"]:.0f}CE @ ₹{float(t["entry"]):.2f}{ex} '
            f'• {held} सेशन • {reason} • {pnl_s}</div>')
    sw_ev_n = sum(1 for e in sw_evs if e["ts"] >= mid)
    sw_empty = '<div class="dtempty">आज Swing ट्रेड नाही</div>'
    sw_trades_html = "".join(sw_rows) or sw_empty
    sw_det = (
        f'<details class="symdet" id="det-SWING" data-detid="SWING">'
        f'<summary class="detbtn" data-detid="SWING">'
        f'<span class="when-shut">📋 सर्व Swing ट्रेड-तपशील व इव्हेंट '
        f'<span class="cnt">(आज {sw_ev_n} इव्हेंट • {len(sw_today)} ट्रेड)</span></span>'
        f'<span class="when-open">✕ तपशील लपवा</span></summary>'
        f'<div class="detbody">'
        f'<div class="dth">🎯 आजचे Swing ट्रेड्स — वैयक्तिक शेअर्स</div>'
        f'{sw_trades_html}'
        f'<div class="dth">📡 Swing इव्हेंट-जर्नल</div>'
        f'{_evblocks(sw_evs, mid, "Swing इव्हेंट नाहीत")}'
        f'</div></details>')

    # उघड्या स्थितींची ओळी
    pos_rows = []
    for p in opens:
        ltp = store.swing_get_ltp(p["id"])
        mtm = round((ltp - float(p["entry"])) * int(p["qty"]), 2) if ltp else None
        mtm_html = (f'<span class="{_cls(mtm)} m">{_sign(mtm)}{_inr(abs(mtm))}</span>'
                    if mtm is not None else '<span class="m">—</span>')
        held = swing.sessions_held(p["date"], date)
        ce = "CE" if "CE" in str(p.get("option_key") or "").upper() else "PE"
        pos_rows.append(
            f'<tr class="oi"><td>{_h.escape(p["symbol"])}</td>'
            f'<td class="m">{p["strike"]:.0f} {ce}</td>'
            f'<td class="m">{_hhmm(p["opened"] if "opened" in p.keys() else p["date"])}</td>'
            f'<td class="m">{held} सेशन</td>'
            f'<td class="m">₹{float(p["entry"]):.2f}</td>'
            f'<td class="m">{("₹%.2f" % ltp) if ltp else "—"}</td>'
            f'<td>{mtm_html}</td>'
            f'<td class="m">₹{float(p["sl"]):.2f}</td></tr>')
    pos_html = (
        '<div class="tblwrap"><table class="tbl"><thead><tr><th>शेअर</th><th>कॉन्ट्रॅक्ट</th>'
        '<th>एंट्री</th><th>धरला</th><th>प्रीमियम</th><th>LTP</th><th>MTM</th><th>SL</th></tr></thead>'
        f'<tbody>{"".join(pos_rows)}</tbody></table></div>'
        if pos_rows else
        '<div class="row" style="color:#475569">उघडी स्थिती नाही — '
        'सिग्नल भेटला की इथे दिसेल (Telegram वरही कार्ड येते)</div>')

    # आज बुक झालेले (शेवटचे 4)
    closed_today = [t for t in store.swing_today(date) if t["status"] == "CLOSED"]
    cl_rows = []
    for t in closed_today[-4:]:
        pnl = t["pnl"] or 0
        cl_rows.append(f'<div class="row"><span class="tm">{"✅" if pnl >= 0 else "❌"}</span>'
                       f'<span>{_h.escape(t["symbol"])} {t["strike"]:.0f}CE · '
                       f'{_h.escape(str(t["reason"] or ""))[:40]} · '
                       f'{_spnl(pnl)}</span></div>')

    return f"""
<div class="sec" id="sec-swing"><span class="t">🎯 Swing — वैयक्तिक शेअर्स ({len(swing.UNIVERSE)} निवडक · ऑप्शन-बायिंग · 2–10 दिवस)</span><span class="ln"></span></div>
<div class="kpis">
  <div class="kpi gx"><div class="ic">💰</div><div class="lab">Swing बाजू (स्वतंत्र)</div>
    <div class="val">{_inr(cap)}</div><div class="sub">ORB भांडवलापासून वेगळी</div></div>
  <div class="kpi gx"><div class="ic">◉</div><div class="lab">उघड्या स्थिती</div>
    <div class="val">{len(opens)}/{swing.MAX_POS}</div><div class="sub">प्रीमियम {_inr(dep)} वापरला</div></div>
  <div class="kpi gx"><div class="ic">🛡️</div><div class="lab">उघड-धोका (SL-आधारित)</div>
    <div class="val">{_inr(orisk)}</div><div class="sub">मर्यादा {_inr(swing.OPEN_RISK_CAP)}</div>
    <div class="lbar" title="उघड-धोका {risk_pct:.0f}%"><i style="width:{risk_pct:.0f}%"></i></div></div>
  <div class="kpi gx"><div class="ic">📈</div><div class="lab">Swing MTD</div>
    <div class="val {_cls(mtd)}">{_sign(mtd)}{_inr(abs(mtd))}</div>
    <div class="sub">सुरुवातीपासून {_k(tot)} • {len(mts)} ट्रेड्स</div></div>
</div>
<div class="duo">
  <div class="panel gx"><div class="ptitle">◉ उघड्या Swing स्थिती</div>{pos_html}
    {(''.join(cl_rows)) if cl_rows else ''}</div>
  <div class="panel gx"><div class="ptitle">🔍 आजचा स्कॅन — ट्रेंड+ट्रिगर (टॉप 10)</div>
    <div class="jr">{_swing_scan_rows(date)}</div></div>
</div>
{sw_det}"""


def _family(n, date):
    """👨‍👩‍👧 Low Capital Family विभाग — 4 सदस्य, स्वस्त-स्ट्राइक शोध + निव्वल-नफा गेट"""
    if family is None or not getattr(family, "ENABLED", False):
        return ""
    b = family.eval_block(date)
    if not b.get("enabled"):
        return ""

    mid = n.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        f_evs = store.events_for(["Family", "FAM-"],
                                 since_ts=mid - 3 * 86400, limit=200)
    except Exception:
        f_evs = []
    f_ev_n = sum(1 for e in f_evs if e["ts"] >= mid)

    # प्रत्येक सदस्याचे कार्ड
    cards_html = []
    for s in b["members"]:
        st = FAM_STYLE.get(s["key"], {"c": "#818cf8", "icon": "👨‍👩‍👧"})
        open_row = ""
        if s["open"]:
            op = s["open"][0]
            side = "CE" if "CE" in str(op.get("option_key") or "").upper() else "PE"
            open_row = ('<div class="opstrip">◉ चालू — {:.0f} {} @ ₹{:.2f} • '
                        'SL ₹{:.2f} • गेट: {}</div>'.format(
                            float(op["strike"]), side, float(op["entry"]),
                            float(op["sl"]), _h.escape(
                                str(op.get("gate_note") or "")[:52])))
        halt_row = ('<div class="haltr">🛑 दैनिक तोटा-मर्यादा भितली</div>'
                    if s["halted"] else "")
        be_chip = ('<span class="chip good">BE +{}%</span>'
                   .format(s["avg_be_move"])
                   if s["avg_be_move"] is not None else "")
        wr_chip = ('<span class="chip">WR {}%</span>'.format(s["win_rate"])
                   if s["win_rate"] is not None else "")
        cards_html.append(
            '<div class="sym gx" style="--sc:{c}">'
            '<i class="acc"></i>'
            '<div class="shead"><div class="sname"><span class="sic">{ic}</span>'
            '{name}<span class="segc">{seg}</span></div>'
            '<span class="badge closed">{filter}</span></div>'
            '<div class="scap">भांडवल <b>{cap}</b> • {style}</div>'
            '<div class="spnl"><span class="big {cls}">{sign}{today}</span>'
            '<span class="mtd">MTD {mtd} • {w}W/{l}L • सुरुवातीपासून {tot}</span></div>'
            '<div class="chips">{be_chip}{wr_chip}'
            '<span class="chip">गेट ≥₹{netmin} • BE ≤{bemax}%</span></div>'
            '{open_row}{halt_row}</div>'.format(
                c=st["c"], ic=st["icon"], name=_h.escape(s["name"]),
                seg=s["seg"], filter=_h.escape(s["key"]),
                cap=_inr(s["capital"]), style=_h.escape(s["style"]),
                cls=_cls(s["today_pnl"]), sign=_sign(s["today_pnl"]),
                today=_inr(abs(s["today_pnl"])),
                mtd=_k(s["mtd_pnl"]), w=s["mtd_wins"], l=s["mtd_losses"],
                tot=_k(s["total_pnl"]), be_chip=be_chip, wr_chip=wr_chip,
                netmin=int(family.NET_MIN), bemax=int(family.BE_MOVE_MAX),
                open_row=open_row, halt_row=halt_row))

    best_line = ""
    if b.get("best_finder_week"):
        bkey = b["best_finder_week"]
        bname = bkey
        for s in b["members"]:
            if s["key"] == bkey:
                bname = s["name"]
        best_line = ('<div class="opstrip" style="margin-top:10px">'
                     '🏅 Best Strike Finder (MTD निव्वल): <b>{}</b></div>'
                     .format(_h.escape(str(bname))))

    # आजचे family ट्रेड-ओळी (शेवटचे 6)
    f_today = store.family_today(date)
    t_rows = []
    for t in f_today[-6:]:
        pnl = t.get("pnl")
        ic = "◉" if t["status"] == "OPEN" else \
            ("✅" if (pnl or 0) >= 0 else "❌")
        ex = " → ₹{:.2f}".format(float(t["exit"])) if t.get("exit") else ""
        pnl_s = ('<span class="{cls}">{sign}{amt}</span>'.format(
            cls=_cls(pnl or 0), sign=_sign(pnl or 0),
            amt=_inr(abs(pnl or 0))) if pnl is not None
            else '<span class="m">चालू</span>')
        t_rows.append(
            '<div class="trow">{ic} [{m}] {_hhmm} • {strike:.0f} {side} '
            '@ ₹{entry:.2f}{ex} • {reason} • {pnl}</div>'.format(
                ic=ic, m=_h.escape(str(t["member"])),
                _hhmm=_hhmm(t.get("opened") or t["date"]),
                strike=float(t["strike"]), side=_h.escape(str(t["side"])),
                entry=float(t["entry"]), ex=ex,
                reason=_h.escape(str(t.get("reason") or ""))[:40] or "—",
                pnl=pnl_s))
    f_det = (
        '<details class="symdet" id="det-FAMILY" data-detid="FAMILY">'
        '<summary class="detbtn" data-detid="FAMILY">'
        '<span class="when-shut">📋 सर्व Family ट्रेड-तपशील व इव्हेंट '
        '<span class="cnt">(आज {ev} इव्हेंट • {tr} ट्रेड)</span></span>'
        '<span class="when-open">✕ तपशील लपवा</span></summary>'
        '<div class="detbody">'
        '<div class="dth">👨‍👩‍👧 आजचे Family ट्रेड्स</div>{rows}'
        '<div class="dth">📡 Family इव्हेंट-जर्नल</div>{evs}'
        '</div></details>').format(
            ev=f_ev_n, tr=len(f_today),
            rows="".join(t_rows) or
            '<div class="dtempty">आज Family ट्रेड नाही</div>',
            evs=_evblocks(f_evs, mid, "Family इव्हेंट नाहीत"))

    return (
        '<div class="sec" id="sec-family"><span class="t">👨‍👩‍👧 Low Capital Family — '
        'कमी-भांडवल शोध-कुटुंब (स्वस्त स्ट्राइक + निव्वल-नफा गेट • '
        'एकूण वर्चुअल ₹{:,.0f})</span><span class="ln"></span></div>'
        '<div class="syms">{}</div>{}{}').format(
            sum(family._capital(M) for M in family.MEMBERS),
            "".join(cards_html), best_line, f_det)


# ------------------------------------------------------------------
# 🎨 थीम-साहाय्यी — एकच remap-पास, थीम-निवड store मध्ये सुरू राहते
# ------------------------------------------------------------------
def _theme_hex_re(key):
    """थीम-मॅपमधील सर्व hex कींचे एक compiled regex (cache एकदाच)"""
    pat = _THEME_RE_CACHE.get(key)
    if pat is None:
        keys = sorted(THEMES[key]["hex"], key=len, reverse=True)
        pat = _re.compile("|".join(_re.escape(k) for k in keys), _re.IGNORECASE)
        _THEME_RE_CACHE[key] = pat
    return pat


def _apply_theme(s, key):
    """एका string वर थीम-रीमॅप: hex case-insensitive (एकच पास — chain नाही)
    + rgba(r,g,b, प्रिफिक्स → थीम-ग्लास. रिकामी मॅप = जसं तसं परत."""
    th = THEMES[key]
    hx, rg = th.get("hex") or {}, th.get("rgb") or {}
    if hx:
        s = _theme_hex_re(key).sub(lambda m: hx[m.group(0).lower()], s)
    for k, v in rg.items():
        s = s.replace(k, v)
    return s


def current_theme():
    """store मधून निवडलेली थीम; नसेल/अवैध असेल तर midnight"""
    k = store.get_state("dash_theme")
    return k if k in THEMES else "midnight"


def set_theme(key):
    """थीम निवड store मध्ये सुरू — रिफ्रेश/डिव्हाइस-बदलानंतरही टिकते"""
    if key in THEMES:
        store.set_state("dash_theme", key)


def theme_labels():
    """Dropdown साठी लेबल-यादी (क्रम = THEMES क्रम)"""
    return [t["label"] for t in THEMES.values()]


def theme_label_of(key):
    """थीम-की → लेबल (अवैध असेल तर midnight-लेबल)"""
    return THEMES[key]["label"] if key in THEMES else THEMES["midnight"]["label"]


def set_theme_by_label(label):
    """Dropdown-लेबल → थीम-की store मध्ये; न मिळाले तर सायन"""
    for k, t in THEMES.items():
        if t["label"] == label:
            store.set_state("dash_theme", k)
            return k
    return None


def month_csv(date=None):
    """📥 MTD CSV एक्सपोर्ट — सर्व मोड्यूलचे (ORB दरवाजे + Swing + Family) या
    महिन्याचे सर्व ट्रेड्स एका CSV फाइलीत (Excel-मैत्री utf-8-sig) —
    परत फाइल-पथ (Gradio DownloadButton साठी)"""
    n = ist_now()
    ym = (date or n.strftime("%Y-%m-%d"))[:7]

    def opt_side(key):
        kk = str(key or "").upper()
        return "CE" if "CE" in kk else ("PE" if "PE" in kk else "")

    heads = ["तारीख", "उघडला", "बंद", "मोड्यूल", "सिम्बॉल", "कॉन्ट्रॅक्ट", "साईड",
             "Qty", "एंट्री", "एग्झिट", "SL", "निव्वल P&L", "खर्च", "स्थिती", "कारण"]
    rows = []
    for t in store.month_trades(ym):
        S = _sym_of(str(t.get("symbol") or ""))
        rows.append([t.get("date") or "", t.get("opened") or "", t.get("closed") or "",
                     "ORB-दरवाजा", S["short"] if S else (t.get("symbol") or ""),
                     (str(t.get("strike") or "") + " " +
                      opt_side(t.get("option_key"))).strip(),
                     t.get("side") or "", t.get("qty") or "", t.get("entry") or "",
                     t.get("exit") or "", t.get("sl") or "", t.get("pnl") or "",
                     t.get("charges") or "", t.get("status") or "", t.get("reason") or ""])
    for t in store.swing_month(ym):
        rows.append([t.get("date") or "", t.get("opened") or t.get("date") or "",
                     t.get("closed") or "", "Swing", t.get("symbol") or "",
                     (str(t.get("strike") or "") + " " +
                      opt_side(t.get("option_key"))).strip(),
                     t.get("side") or "", t.get("qty") or "", t.get("entry") or "",
                     t.get("exit") or "", t.get("sl") or "", t.get("pnl") or "",
                     t.get("charges") or "", t.get("status") or "", t.get("reason") or ""])
    for t in store.family_month(ym):
        rows.append([t.get("date") or "", t.get("opened") or t.get("date") or "",
                     t.get("closed") or "", "Family", t.get("member") or "",
                     (str(t.get("strike") or "") + " " +
                      opt_side(t.get("option_key"))).strip(),
                     t.get("side") or "", t.get("qty") or "", t.get("entry") or "",
                     t.get("exit") or "", t.get("sl") or "", t.get("pnl") or "",
                     t.get("charges") or "", t.get("status") or "", t.get("reason") or ""])
    rows.sort(key=lambda r: (str(r[0]), str(r[1])))
    path = os.path.join(tempfile.gettempdir(), "mtd_trades_" + ym + ".csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f)
        w.writerow(heads)
        w.writerows(rows)
    return path


def build_dashboard(theme=None):
    n = ist_now()
    # 🎨 थीम: स्पष्ट दिलेली > store मधली > midnight (अवैध असल्यास पण midnight)
    tkey = (current_theme() if theme is None else theme)
    tkey = tkey if tkey in THEMES else "midnight"
    date = n.strftime("%Y-%m-%d")
    swing_html = _swing(n, date)
    family_html = _family(n, date)
    parts = [
        '<div class="dash">',
        _nav(bool(swing_html), bool(family_html)),
        _hero(n, date),
        _sessbar(n, date),
        '<div class="sec" id="sec-kpi"><span class="t">📌 आजची स्थिती</span><span class="ln"></span></div>',
        _kpis(n, date),
        '<div class="sec" id="sec-ins"><span class="t">🧠 बुद्धीचा डब्बा — डेटामधून आपोआप तयार होणारे विचार</span><span class="ln"></span></div>',
        _insights(date),
        *(('<div class="sec" id="sec-ai"><span class="t">🤖 AI ब्रेन सल्ला — मोफत स्थानिक डोके (Ollama) दैनिक विश्लेषण</span><span class="ln"></span></div>',
           _ai_card(n, date)) if ai_brain is not None and ai_brain.enabled() else ()),
        '<div class="sec" id="sec-perf"><span class="t">🎯 स्ट्रॅटेजी परफॉर्मन्स ट्रॅकर — निव्वल नाही, गुणवत्ता (PF • अपेक्षा • ग्रेड)</span><span class="ln"></span></div>',
        _perftrack(date),
        '<div class="sec" id="sec-time"><span class="t">⏱️ पैसा कधी कमावतो? — बुकिंग-तास अभ्यास (सुरुवातीपासून)</span><span class="ln"></span></div>',
        _timeatlas(date),
        '<div class="sec" id="sec-risk"><span class="t">🛡️ धोका-तापमान — थांब-मर्यादेला किती जवळ?</span><span class="ln"></span></div>',
        _riskheat(n, date),
        '<div class="sec" id="sec-gates"><span class="t">🚪 {} दरवाजे — प्रत्येकी स्वतंत्र भांडवल व नियम</span><span class="ln"></span></div>'.format(len(C.active_symbols())),
        '<div class="syms">' + "".join(_sym_card(s, n, date) for s in C.active_symbols()) + "</div>",
        swing_html,
        family_html,
        '<div class="sec" id="sec-tl"><span class="t">🕒 दिवसाचे वेळापत्रक (डिटरमिनिस्टिक)</span><span class="ln"></span></div>',
        _timeline(n),
        '<div class="sec" id="sec-ov"><span class="t">📡 लाइव्ह आढावा</span><span class="ln"></span></div>',
        _overview(n, date),
        '<div class="sec" id="sec-chart"><span class="t">📈 ट्रेड-लाइव्ह कॅन्डल-चार्ट — ट्रेड झालेल्या प्रत्येक instrument चे</span><span class="ln"></span></div>',
        _tradecharts(n, date),
        '<div class="sec" id="sec-hist"><span class="t">📅 महिन्याचा आढावा — कॅलेंडर • लीडरबोर्ड • दैनिक निव्वल • MTD</span><span class="ln"></span></div>',
        _calduo(date),
        '<div class="duo eqduo">' + _equity(date) + _weekday(date) + "</div>",
        _daily_hist(n, date),
        '<div class="sec" id="sec-tr"><span class="t">💹 आजचे ट्रेड्स</span><span class="ln"></span></div>',
        _table(date),
        f'<div class="foot"><div class="fn">🧪 PAPER मोड — सर्व ऑर्डर कागदी • आपोआप रिफ्रेश दर 10 सेकंद • '
        f'संपूर्ण नियंत्रण Telegram बॉटवर</div>'
        f'<div class="fn m">अपडेट: {n.strftime("%H:%M:%S")} IST • 🎨 थीम: {theme_label_of(tkey)}</div></div>',
        "</div>",
    ]
    html = "".join(parts)
    if tkey == "midnight":                 # बेस-थीम = पान-पातळी CSS तसेच
        return html
    # थीम CSS <style> टॅगमध्ये कॉम्पोनेंटबरोबर — नंतर आलेला नियम पान-पातळीवर विजयी
    return "<style>" + _apply_theme(CSS, tkey) + "</style>" + _apply_theme(html, tkey)
