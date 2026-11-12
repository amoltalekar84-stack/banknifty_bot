"""
🧠 AI ब्रेन — सल्लागार-विश्लेषक (ट्रेडर नाही!)
रोज सायंकाळी (AI_BRAIN_AT, डीफॉल्ट 20:32 — EVAL-DAILY 20:30 नंतर) दिवसाचे
आकडे वाचून स्थानिक/मोफत डोक्याकडून मराठी विश्लेषण तयार करतो.

नियम (डिझाइन-वचन):
  • AI कधीही ऑर्डर/गेट/halt हाताळत नाही — अंतिम निर्णय नेहमी नियम-इंजिनचा.
  • प्रोव्हाइडर साखळी (सर्व मोफत): Ollama (VM-वर) → Groq → HF Inference → शांत-स्किप.
  • ब्रेन बंद पडला तरी बॉटचे व्यापार आजच्याप्रमाणे — AI हे बोनस, जीवनरेषा नाही.
  • मराठी वाक्यांची भाषा टेम्पलेटमधून येते; मॉडेल फक्त आकड्यांवर आधारित
    कारणे/लक्षे (JSON) देतो — भाषा 100% नियंत्रित.
  • प्रत्येक कॉल 300से-टाइमआउट + सर्किट-ब्रेकर (लागोपाठ अपयशावर 30 मि थांबा).
  • लहान-मॉडेल सुरक्षा-जाळी: num_predict 500 (थंड-लोड ~90से + जनरेशन ≈ 255से
    < 300से-टाइमआउट) + repeat_penalty 1.2 (पोपट-पुनरावृत्ती आटोकास) +
    प्रॉम्प्ट "लहान वाक्ये" + अर्धवट-JSON बंद-करा-वाचन (_close_partial_json) +
    पार्स-वेळी शीर्षक/आधीच्या-ओळी जुळणारी पोपट-पुनरावृत्ती काढणे (VM-निदान 2026-11-12).

पर्यावरण (env):
  AI_BRAIN_ENABLED=YES|NO   AI_BRAIN_AT=20:32     AI_MODEL=qwen3:4b
  OLLAMA_URL=http://127.0.0.1:11434            AI_TIMEOUT=300
  GROQ_API_KEY=... (बैकअप)  AI_CLOUD_MODEL=llama-3.3-70b-versatile
  HF_TOKEN=... (बैकअप)      AI_HF_MODEL=Qwen/Qwen2.5-7B-Instruct
"""

import html
import json
import re
import threading
import time
import urllib.error
import urllib.request

import config as C
import store


def enabled():
    """किल-स्विच — AI_BRAIN_ENABLED=NO म्हणजे ब्रेन संपूर्ण शांत."""
    return bool(getattr(C, "AI_BRAIN_ENABLED", True))


# ----------------------------------------------------------------
# 1) दिवसाचा डेटा — फक्त आकडे (टोकन/गुप्त काहीही नाही)
# ----------------------------------------------------------------
def collect_day_data(date):
    """दिवसभरचे आकडे एका लहान JSON मध्ये (प्रॉम्प्टसाठी + रिपोर्टमध्ये जतन)."""
    out = {"date": date,
           "mode": store.get_state("mode", "PAPER"),
           "symbols": []}
    tot = 0.0
    for S in C.active_symbols():
        trs = store.trades_today(date, S["key"])
        closed = [t for t in trs if t["status"] == "CLOSED"]
        w = sum(1 for t in closed if (t["pnl"] or 0) >= 0)
        l = len(closed) - w
        pnl = store.today_pnl(date, S["key"])
        lim = float(S.get("max_daily_loss") or 0)
        used = (abs(pnl) * 100.0 / lim) if lim > 0 else 0.0
        tot += pnl
        reasons = []
        for t in closed:
            r = str(t.get("reason") or "").strip()
            if r:
                reasons.append(r[:80])
        out["symbols"].append({
            "key": S["key"], "seg": S.get("seg", ""),
            "trades": len(trs), "closed": len(closed),
            "wins": w, "losses": l,
            "pnl": round(pnl, 2),
            "daily_loss_limit": lim,
            "limit_used_pct": round(used),
            "halt": store.get_state("halt_" + date + "_" + S["key"]) == "1",
            "charges": store.today_charges(date, S["key"]),
            "mtd": round(sum((t["pnl"] or 0) for t in
                             store.month_trades(date[:7], S["key"])
                             if t["status"] == "CLOSED"), 2),
            "reasons": reasons[:4],
        })
    # 🎯 Swing व 👨‍👩‍👧 Family — स्वतंत्र बाजू (आकडे फक्त)
    for tag, fn in (("swing", store.swing_today), ("family", store.family_today)):
        try:
            rows = fn(date)
            cl = [t for t in rows if t["status"] == "CLOSED"]
            pnl = round(sum((t["pnl"] or 0) for t in cl), 2)
            w = sum(1 for t in cl if (t["pnl"] or 0) >= 0)
            out[tag] = {"trades": len(rows), "closed": len(cl), "wins": w,
                        "losses": len(cl) - w, "pnl": pnl}
            tot += pnl
        except Exception:
            out[tag] = {"trades": 0, "closed": 0, "wins": 0, "losses": 0,
                        "pnl": 0.0}
    out["total"] = round(tot, 2)
    return out


# ----------------------------------------------------------------
# 2) प्रॉम्प्ट + उत्तर-तपासणी (JSON स्कीमा)
# ----------------------------------------------------------------
_SCHEMA = ("tone", "headline", "causes", "focus", "risk")   # संपूर्ण योजना (कागजपत्र)


def _prompt(data):
    return (
        "तुम्ही भारतीय शेअर-बाजारातील जबाबदार ट्रेडिंग-विश्लेषक आहात. खाली एका "
        "कागदी-ट्रेडिंग बॉटच्या एका दिवसाचे आकडे आहेत — हेच खरे आकडे; नवीन आकडे "
        "बनवू नका, बाह्य बातमी वापरू नका.\n\n"
        "नियम:\n"
        "1) उत्तर फक्त वैध JSON ऑब्जेक्ट — इतर कोणताही मजकूर नको.\n"
        "2) सर्व वाक्ये मराठीत, प्रत्येकी एक ओळ, कमाल 80 अक्षरे — लहान व सुटे "
        "ठेवा; एकच विचार पुन्हा पुन्हा लिहू नका.\n"
        "3) causes = आजच्या आकड्यांमधून दिसणारी कारणे (कमाल 2); "
        "focus = उद्यासाठी लक्षात ठेवायची बाब (कमाल 2); risk = सावधाता-बाब (कमाल 1).\n"
        "4) 'कोणता शेअर खरेदी करा/विक्री करा' असा व्यापार-सल्ला देऊ नका — "
        "फक्त वर्तन-विश्लेषण (नियम/धोरण/शिस्त स्तरावर).\n"
        "5) tone = good (नफा/शिस्त) | warn (मिश्र/सावध) | bad (मोठा तोटा/शिस्त-भंग).\n\n"
        "आजचे आकडे:\n" + json.dumps(data, ensure_ascii=False) + "\n\n"
        'JSON योजना: {"tone":"good|warn|bad","headline":"एक वाक्य",'
        '"causes":["..."],"focus":["..."],"risk":["..."]}'
    )


def _clean(s, n=160):
    """मॉडेल-मजकूर सुरक्षित करा: एक ओळ, टॅग-मुक्त, लांबी-मर्यादा."""
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


def _close_partial_json(s):
    """अर्धवट (टोकन-मर्यादेत तुटलेला) JSON शक्य तिथे बंद करा — शेवटची गरज.
    उघड्या अवतरणांची/कंसांची मोजणी करून पूरक बंद-चिन्हे जोडतो; शेवटचे
    अपूर्ण तुकडे (अनाथ-की/स्वल्प) काढतो. नंतरही अवैध असल्यास पार्सर None देईल."""
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            stack.append("]")
        elif ch == "{":
            stack.append("}")
        elif ch in "]}" and stack and stack[-1] == ch:
            stack.pop()
    out = s
    if in_str:
        if esc:
            out = out[:-1]             # अर्धवट backslash-पलायन काढा
        out += '"'
    out = out.rstrip()
    for _ in range(3):                 # शेवटचे अपूर्ण तुकडे काढा
        if out.endswith(":"):
            out = re.sub(r'"[^"]*"\s*$', "", out[:-1]).rstrip()
        elif out.endswith(","):
            out = out[:-1].rstrip()
        else:
            break
    return out + "".join(reversed(stack))


def _parse_ai_json(txt):
    """मॉडेल उत्तर → स्कीमा-पाळलेला dict, नाहीतर None (कधीही बनावट आकडे नाहीत)."""
    if not txt:
        return None
    s = str(txt)
    s = re.sub(r"<think>.*?</think>", " ", s, flags=re.S)  # विचार-मजकूर पूर्ण काढा
    if "```" in s:
        m = re.findall(r"```(?:json)?\s*(.*?)```", s, re.S)
        if m:
            s = m[0]
    a, b = s.find("{"), s.rfind("}")
    if a < 0:
        return None
    frag = s[a:b + 1] if b > a else s[a:]      # अर्धवट → शेवटपर्यंतचा तुकडा
    try:
        j = json.loads(frag)
    except (ValueError, TypeError):
        j = None
    if not isinstance(j, dict):
        try:   # टोकन-मर्यादेत तुटलेला उत्तर — बंद करून शक्य तिथे वाचा
            j = json.loads(_close_partial_json(frag))
        except (ValueError, TypeError):
            return None            # कचरा → None (कधीही बनावट नाही)
    if not isinstance(j, dict) or "headline" not in j:
        return None                # किमान आवश्यक: headline; बाकी की ऐच्छिक (लवचिक)
    tone = str(j.get("tone") or "").strip().lower()
    if tone not in ("good", "warn", "bad"):
        tone = "warn"

    def _lst(v, cap):
        if not isinstance(v, list):
            v = [v] if v else []
        out = [_clean(x) for x in v]
        return [x for x in out if x][:cap]

    def _norm(x):
        return re.sub(r"[^0-9a-z\u0900-\u097F]+", "", str(x or "").lower())

    def _dedup(items, seen):
        """पोपट-पुनरावृत्ती काढा — शीर्षक/आधीच्या ओळीशी तंतोतंत किंवा
        पहिल्या 30 अक्षरांपर्यंत जुळणारी वाक्य वगळा (लहान-मॉडेल जबाबदाई)."""
        out = []
        for t in items:
            n = _norm(t)
            if not n or n[:30] in seen:
                continue
            seen.add(n[:30])
            out.append(t)
        return out

    head = _clean(j.get("headline"), 140)
    seen = {_norm(head)[:30]}
    return {"tone": tone,
            "headline": head,
            "causes": _dedup(_lst(j.get("causes"), 3), seen),
            "focus": _dedup(_lst(j.get("focus"), 3), seen),
            "risk": _dedup(_lst(j.get("risk"), 2), seen)}


# ----------------------------------------------------------------
# 3) प्रोव्हाइडर साखळी — सर्व मोफत, सर्व टाइमआउट-संरक्षित
# ----------------------------------------------------------------
def _post_json(url, body, headers, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _ask_ollama(prompt):
    """① VM-वरील मोफत डोके (Ollama) — ना की, ना मर्यादा, ना बिल."""
    body = {"model": C.AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "format": "json", "think": False,
            "keep_alive": "15m",
            # num_predict 500: थंड-सुरुवात (लोड ~90से) + जनरेशन ≈ 255से < 300से;
            # repeat_penalty/last_n: लहान-मॉडेल एकच-वाक्य-पोपटपणा आटोकास
            "options": {"temperature": 0.2, "num_predict": 500,
                        "repeat_penalty": 1.2, "repeat_last_n": 256}}
    try:
        j = _post_json(C.OLLAMA_URL.rstrip("/") + "/api/chat", body, {},
                       C.AI_TIMEOUT)
    except urllib.error.HTTPError:
        body.pop("think", None)        # जुनी Ollama — think-पॅराम नाही
        j = _post_json(C.OLLAMA_URL.rstrip("/") + "/api/chat", body, {},
                       C.AI_TIMEOUT)
    return ((j.get("message") or {}).get("content") or "")


def _ask_openai_style(url, key, model, prompt):
    """OpenAI-सुसंगत cloud endpoint (Groq / HF router) — फक्त बैकअप."""
    body = {"model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 500,
            "response_format": {"type": "json_object"}}
    j = _post_json(url, body, {"Authorization": "Bearer " + key}, C.AI_TIMEOUT)
    ch = (j.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    return msg.get("content") or ""


def _ask_groq(prompt):
    return _ask_openai_style(
        "https://api.groq.com/openai/v1/chat/completions",
        C.GROQ_API_KEY, C.AI_CLOUD_MODEL, prompt)


def _ask_hf(prompt):
    return _ask_openai_style(
        "https://router.huggingface.co/v1/chat/completions",
        C.HF_TOKEN, C.AI_HF_MODEL, prompt)


_PROVIDERS = (
    ("ollama", "ask_ollama", None),
    ("groq", "ask_groq", "GROQ_API_KEY"),
    ("hf", "ask_hf", "HF_TOKEN"),
)


def _ask_any(prompt):
    """साखळी: पहिला उपलब्ध-यशी प्रोव्हाइडर. परत (provider, model, raw) किंवा
    (None, None, शेवटची-चूक)."""
    last_err = ""
    for name, fname, keyfield in _PROVIDERS:
        if keyfield and not getattr(C, keyfield, ""):
            continue                 # की नाही → हा बैकअप वगळा (शांत)
        fn = {"ask_ollama": _ask_ollama, "ask_groq": _ask_groq,
              "ask_hf": _ask_hf}[fname]
        try:
            raw = fn(prompt)
            if raw and raw.strip():
                model = (C.AI_MODEL if name == "ollama"
                         else (C.AI_CLOUD_MODEL if name == "groq"
                               else C.AI_HF_MODEL))
                return name, model, raw
        except (urllib.error.URLError, OSError, ValueError,
                KeyError, TypeError) as e:
            last_err = name + ": " + repr(e)[:120]
    return None, None, last_err


# ----------------------------------------------------------------
# 4) मराठी टेम्पलेट — आकडे आपले (खरे), वाक्ये आपली
# ----------------------------------------------------------------
_TONE_ICON = {"good": "🟢", "warn": "🟡", "bad": "🔴"}
_TONE_WORD = {"good": "निरोगी दिवस", "warn": "मिश्र/सावध दिवस", "bad": "जबरदस्त तोटा"}


def _inr(v):
    v = float(v or 0)
    return ("−₹" if v < 0 else "₹") + "{:,.0f}".format(abs(v))


def _lines_from(data, ai):
    """खरे आकडे + मॉडेल-कारणे → मराठी ओळी (डॅश/EOD दोन्हीत वापर)."""
    syms = [s for s in data.get("symbols", []) if s.get("trades")]
    worst = min(syms, key=lambda s: s["pnl"]) if syms else None
    best = max(syms, key=lambda s: s["pnl"]) if syms else None
    tone = ai.get("tone", "warn")
    lines = []
    hl = ai.get("headline") or ("आज: " + _TONE_WORD[tone] + " — एकूण "
                                + _inr(data.get("total", 0)))
    lines.append(_TONE_ICON.get(tone, "⚪") + " " + hl)
    if worst and worst["pnl"] < -0.005:
        lines.append("📉 सर्वात मोठा दबाव: " + worst["key"] + " "
                     + _inr(worst["pnl"]) + " (मर्यादेचा "
                     + str(worst["limit_used_pct"]) + "% वापर"
                     + (", हॉल्ट ⛔" if worst["halt"] else "") + ")")
    if best and len(syms) > 1 and best["pnl"] > 0.005 and best["key"] != worst["key"]:
        lines.append("📈 सर्वात चांगले: " + best["key"] + " " + _inr(best["pnl"]))
    for c in ai.get("causes", []):
        lines.append("• " + c)
    for r in ai.get("risk", []):
        lines.append("⚠️ " + r)
    if ai.get("focus"):
        lines.append("🎯 उद्याची लक्षे: " + " | ".join(ai["focus"]))
    return lines


# ----------------------------------------------------------------
# 5) जतन/वाचन + सर्किट-ब्रेकर
# ----------------------------------------------------------------
def save_report(date, rep):
    store.set_state("aibrain_" + date, json.dumps(rep, ensure_ascii=False))
    store.set_state("aibrain_last", json.dumps(rep, ensure_ascii=False))


def load_report(date):
    try:
        v = store.get_state("aibrain_" + str(date))
        return json.loads(v) if v else None
    except (ValueError, TypeError):
        return None


def load_last():
    try:
        v = store.get_state("aibrain_last")
        return json.loads(v) if v else None
    except (ValueError, TypeError):
        return None


def _tries(date):
    try:
        return int(store.get_state("aibrain_tries_" + date, "0") or 0)
    except (ValueError, TypeError):
        return 0


def _hold_left():
    try:
        until = float(store.get_state("aibrain_hold_until", "0") or 0)
        return max(0.0, until - time.time())
    except (ValueError, TypeError):
        return 0.0


def should_attempt(n=None, date=None):
    """वेळ-गेट: व्यावसायिक दिवस + AI_BRAIN_AT नंतर + होल्ड नाही + जागीव नाही."""
    if not enabled():
        return False
    n = n or C.ist_now()
    date = date or n.strftime("%Y-%m-%d")
    if n.weekday() >= 5:
        return False
    if n.strftime("%H:%M") < str(getattr(C, "AI_BRAIN_AT", "20:32")):
        return False
    if store.get_state("aibrain_done_" + date) == "1":
        return False
    if _tries(date) >= 2:
        return False
    if _hold_left() > 0:
        return False
    return True


# ----------------------------------------------------------------
# 6) मुख्य प्रवाह — एक विश्लेषण चालवा
# ----------------------------------------------------------------
def run_once(date=None, force=False):
    """एकदाच: आकडे → साखळी → JSON → मराठी ओळी → जतन.
    परत रिपोर्ट-dict (ok True/False) किंवा None (बंद/होल्ड/गेट-आधी)."""
    if not enabled():
        return None
    n = C.ist_now()
    date = date or n.strftime("%Y-%m-%d")
    if not force:
        if store.get_state("aibrain_done_" + date) == "1":
            return None
        if _tries(date) >= 2 or _hold_left() > 0:
            return None
    data = collect_day_data(date)
    t0 = time.time()
    provider, model, raw = _ask_any(_prompt(data))
    latency = round(time.time() - t0, 1)
    ai = _parse_ai_json(raw) if provider else None
    if provider and ai:
        rep = {"ok": True, "date": date,
               "ts": n.strftime("%Y-%m-%d %H:%M:%S"),
               "provider": provider, "model": model,
               "latency_s": latency, "ai": ai, "data": data,
               "lines": _lines_from(data, ai)}
        save_report(date, rep)
        store.set_state("aibrain_tries_" + date, str(_tries(date) + 1))
        store.set_state("aibrain_done_" + date, "1")
        store.set_state("aibrain_hold_until", "0")
        store.log_event("🧠 AI ब्रेन विश्लेषण तयार ({}:{})".format(
            provider, model))
        return rep
    # ---- सर्व प्रोव्हाइडर अपयशी → शांत नोंद + सर्किट-ब्रेकर ----
    tries = _tries(date) + 1
    store.set_state("aibrain_tries_" + date, str(tries))
    if tries >= 2:
        store.set_state("aibrain_done_" + date, "1")
    hold_min = int(getattr(C, "AI_BRAIN_HOLD_MIN", 30) or 30)
    store.set_state("aibrain_hold_until", str(time.time() + hold_min * 60))
    rep = {"ok": False, "date": date,
           "ts": n.strftime("%Y-%m-%d %H:%M:%S"),
           "provider": None, "model": None, "latency_s": None,
           "err": str(raw or "सर्व प्रोव्हाइडर नाहीत")[:200],
           "data": data,
           "lines": ["⚪ आज ब्रेन उपलब्ध नव्हता — व्यापार तसेच नियम-इंजिनवर "
                     "सामान्य चालू; उद्या पुन्हा प्रयत्न."]}
    save_report(date, rep)
    store.log_event("🧠 AI ब्रेन अपयशी — " + str(raw)[:80])
    return rep


def start_aibrain():
    """बॅकग्राउंड लूप — दर 60 सेकंदांनी वेळ-गेट तपास; गेट उघडला की विश्लेषण."""
    def _loop():
        while True:
            try:
                n = C.ist_now()
                if should_attempt(n):
                    run_once(n.strftime("%Y-%m-%d"))
            except Exception as e:            # लूप कधीच मरणार नाही
                try:
                    store.log_event("🧠 AI ब्रेन लूप-चूक: " + repr(e)[:100])
                except Exception:
                    pass
            time.sleep(60)
    t = threading.Thread(target=_loop, name="aibrain", daemon=True)
    t.start()
    return t


# ----------------------------------------------------------------
# 7) EOD-ओळी (telegram_bot._eod_text साठी — swing/family पॅटर्न प्रमाणे)
# ----------------------------------------------------------------
def eod_lines(date):
    """🌙 EOD अहवालासाठी AI-ब्रेन ओळी (HTML-सुरक्षित). नाही असल्यास []."""
    rep = load_report(date)
    if not rep:
        return []
    lines = ["\n🧠 <b>AI ब्रेन सल्ला</b>"
             + (f" ({rep.get('provider')}:{rep.get('model')})"
                if rep.get("provider") else "")]
    for ln in (rep.get("lines") or [])[:6]:
        lines.append("  " + html.escape(str(ln), quote=False))
    lines.append("  <i>(सल्लागार-विश्लेषण; अंतिम निर्णय नियम-इंजिनचा)</i>")
    return lines
