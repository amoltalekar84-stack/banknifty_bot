#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model_ab_test.py — VM-वर लहान vs मोठा मॉडेल A/B चाचणी (एक-वेळ निदान-साधन).

उद्देश: qwen3:1.7b ची मराठी-भाषा उराडलेली आहे (1.7b-छत); मोठा मॉडेल
(qwen3:4b — config.py चे मूळ डीफॉल्ट) आता प्रयत्न करून final ठरवणे.

काय मोजतो (प्रत्येक फेरी):
  • wall-लॅटिन्सी + ollama-मेट्रिक्स (load_s, prompt_tok, out_tok, gen-tok/s)
  • चालू-काळ किमान उपलब्ध RAM (MemAvailable, MB) — 5.8Gi-VM-शिस्त
  • JSON-पार्स (ai_brain._parse_ai_json — तंतोतंत उत्पादन-पथ) + tone/मोजणी
  • भाषा-मॅट्रिक्स: देवनागरी-गुणोत्तर, >80-अक्षरी-ओळी (मॅट्रिक्स तुलनात्मकच)

फेरी: base-थंड → cand-थंड → cand-उष्ण (keep_alive 5m चाचणी-आवृत्ती).
num_predict 400 = ai_brain.py उत्पादन-प्रमाणेच (न्याय्य तुलना; कुंपण = लॅटिन्सी-लीवर).

वापर:
  python3 tools/model_ab_test.py                     # 1.7b vs 4b + 4b-उष्ण
  python3 tools/model_ab_test.py --cand qwen3:4b --force
  python3 tools/model_ab_test.py --cand llama3.2:3b --no-warm

टीप: बाजार/MCX-वेळी (सोम-शुक्री 09:00-23:30) 1-OCPU-स्पर्धा होते — स्क्रिप्ट
10 सेकांद प्रतीक्षा करते (Ctrl-C); --force दिल्यास लगेच. निकाल /tmp/model_ab/.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import zoneinfo
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(sys.path[0])

import ai_brain as AB  # noqa: E402  (_prompt/_parse_ai_json/_lines_from — तंतोतंत उत्पादन-पथ)

URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
NUM_PREDICT = 400          # ai_brain.py उत्पादन-प्रमाणेच
TEST_HTTP_TIMEOUT = 900    # चाचणी-मोजमापासाठीच — उत्पादन AI_TIMEOUT वेगळाच (bot.env)

# — नमुना-दिवस: 2026-11-12 खऱ्या VM-कार्डाचे आकडे (NIFTY −419.63 / SENSEX −6063.79)
DATA = {
    "date": "2026-11-12", "mode": "PAPER",
    "symbols": [
        {"key": "NIFTY", "seg": "NSE_FO", "trades": 4, "closed": 4,
         "wins": 2, "losses": 2, "pnl": -419.63, "daily_loss_limit": 1600.0,
         "limit_used_pct": 26, "halt": False, "charges": 118.4, "mtd": 5132.6,
         "reasons": ["TP1 booked", "SL hit", "TP2 booked", "SL hit"]},
        {"key": "SENSEX", "seg": "BSE_FO", "trades": 3, "closed": 3,
         "wins": 0, "losses": 3, "pnl": -6063.79, "daily_loss_limit": 4800.0,
         "limit_used_pct": 126, "halt": True, "charges": 204.7, "mtd": -8341.2,
         "reasons": ["SL hit", "SL hit", "SL hit"]},
        {"key": "COPPER", "seg": "MCX_FO", "trades": 2, "closed": 2,
         "wins": 1, "losses": 1, "pnl": 640.25, "daily_loss_limit": 2000.0,
         "limit_used_pct": 8, "halt": False, "charges": 96.3, "mtd": 1487.5,
         "reasons": ["TP2 booked", "SL hit"]},
    ],
    "swing": {"trades": 1, "closed": 1, "wins": 0, "losses": 1, "pnl": -220.5},
    "family": {"trades": 2, "closed": 1, "wins": 1, "losses": 0, "pnl": 148.3},
}
DATA["total"] = round(sum(s["pnl"] for s in DATA["symbols"])
                      + DATA["swing"]["pnl"] + DATA["family"]["pnl"], 2)


class RamWatch:
    """प्रत्येक सेकादाला MemAvailable — चालू-फेरीचा किमान निर्देशांक (MB)."""

    def __init__(self):
        self.min_avail_kb = None
        self._run = False
        self._stop = False
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    @staticmethod
    def _avail_kb():
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                for ln in f:
                    if ln.startswith("MemAvailable"):
                        return int(ln.split()[1])
        except OSError:
            pass
        return 0

    def _loop(self):
        while not self._stop:
            if self._run:
                a = self._avail_kb()
                if self.min_avail_kb is None or a < self.min_avail_kb:
                    self.min_avail_kb = a
            time.sleep(1.0)

    def start(self):
        self.min_avail_kb = None
        self._run = True

    def stop_mb(self):
        self._run = False
        return round((self.min_avail_kb or 0) / 1024.0, 1)


def ollama_list():
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True,
                           timeout=30)
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError) as e:
        print("  ollama list चूक:", repr(e)[:100])
        return ""


def ensure_pull(model, need_mb=4000):
    tags = "\n".join(l.split()[0] for l in ollama_list().splitlines()[1:]
                     if l.strip())
    if model in tags.splitlines():
        print("  " + model + " आधीच उपलब्ध — pull वगळले")
        return True
    free_mb = shutil.disk_usage("/").free / (1024 * 1024)
    if free_mb < need_mb:
        print("  ❗ डिस्क-जागा कमी (" + str(round(free_mb)) + "MB शिल्लक) — "
              + model + " pull नाही; तो मॉडेल वगळतो")
        return False
    print("  " + model + " pull होत आहे (~" + str(round(free_mb))
          + "MB डिस्क शिल्लक)…")
    try:
        subprocess.run(["ollama", "pull", model], check=True, timeout=1800)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        print("  ❗ pull अपयशी:", repr(e)[:120])
        return False


def chat(model, prompt, timeout):
    """ai_brain._ask_ollama ची तंतोतंत उत्पादन-बांधणी — फक्त keep_alive 5m (चाचणी)."""
    body = {"model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "format": "json", "think": False,
            "keep_alive": "5m",
            "options": {"temperature": 0.2, "num_predict": NUM_PREDICT,
                        "repeat_penalty": 1.2, "repeat_last_n": 256}}
    t0 = time.time()
    try:
        j = AB._post_json(URL, body, {}, timeout)
        return j, round(time.time() - t0, 1)
    except urllib.error.HTTPError:
        body.pop("think", None)            # जुनी Ollama — think-पॅराम नाही
        t0 = time.time()
        j = AB._post_json(URL, body, {}, timeout)
        return j, round(time.time() - t0, 1)


DEVA = re.compile(r"[\u0900-\u097F]")
LETTER = re.compile(r"[A-Za-z\u0900-\u097F]")


def run_one(label, model, watch, timeout, results):
    print("\n" + "=" * 66)
    print("फेरी: " + label + " — " + model)
    print("=" * 66, flush=True)
    watch.start()
    wall = None
    try:
        j, wall = chat(model, AB._prompt(DATA), timeout)
    except (urllib.error.URLError, OSError, ValueError) as e:
        mb = watch.stop_mb()
        print("❗ कॉल अपयशी (" + (str(wall) + "से" if wall else "मध्येच")
              + "): " + repr(e)[:160] + " | किमान-उपलब्ध RAM " + str(mb) + "MB")
        results.append({"label": label, "model": model, "ok": False,
                        "err": repr(e)[:160], "min_ram_mb": mb})
        return
    mb = watch.stop_mb()
    raw = (j.get("message") or {}).get("content") or ""
    load_s = round((j.get("load_duration") or 0) / 1e9, 1)
    ptok = j.get("prompt_eval_count") or 0
    otok = j.get("eval_count") or 0
    gt = (j.get("eval_duration") or 0) / 1e9
    tps = round(otok / gt, 2) if gt > 0 else 0.0
    cap_hit = otok >= NUM_PREDICT - 5
    ai = AB._parse_ai_json(raw)
    rec = {"label": label, "model": model, "ok": bool(ai), "wall_s": wall,
           "load_s": load_s, "prompt_tok": ptok, "out_tok": otok,
           "gen_tok_s": tps, "cap_hit": cap_hit, "min_ram_mb": mb,
           "raw_len": len(raw)}
    print("लॅटिन्सी wall=" + str(wall) + "से (load=" + str(load_s) + "से) | "
          "prompt=" + str(ptok) + " टोकन, उत्तर=" + str(otok) + " टोकन ("
          + str(tps) + " टोकन/से"
          + (", कुंपणाला आटोकास!" if cap_hit else "") + ")")
    print("किमान-उपलब्ध RAM चालू-काळ: " + str(mb) + " MB")
    if not ai:
        print("❗ JSON-पार्स अपयश — RAW (" + str(len(raw)) + " अक्षरे):")
        print(raw[:1500])
        results.append(rec)
        return
    lines = AB._lines_from(DATA, ai)
    txt = "|".join([ai.get("headline", "")] + ai.get("causes", [])
                   + ai.get("focus", []) + ai.get("risk", []))
    letters = len(LETTER.findall(txt))
    deva = round(100 * len(DEVA.findall(txt)) / letters) if letters else 0
    long80 = sum(1 for ln in txt.split("|") if len(ln) > 80)
    rec.update({"tone": ai.get("tone"),
                "causes": len(ai.get("causes", [])),
                "focus": len(ai.get("focus", [])),
                "risk": len(ai.get("risk", [])),
                "deva_pct": deva, "over80_lines": long80})
    print("पार्स: यश | tone=" + str(ai.get("tone")) + " | causes="
          + str(rec["causes"]) + " focus=" + str(rec["focus"]) + " risk="
          + str(rec["risk"]) + " | देवनागरी " + str(deva) + "% | >80-अक्षरी-ओळी "
          + str(long80))
    print("— कार्ड-ओळी (_lines_from, उत्पादन-प्रमाणेच) —")
    for ln in lines:
        print("  " + ln)
    print("— RAW मॉडेल-उत्तर —")
    print(raw)
    results.append(rec)


def main():
    ap = argparse.ArgumentParser(
        description="VM-वर लहान vs मोठा मॉडेल A/B चाचणी (ai_brain-पथ)")
    ap.add_argument("--base", default="qwen3:1.7b")
    ap.add_argument("--cand", default="qwen3:4b")
    ap.add_argument("--timeout", type=int, default=TEST_HTTP_TIMEOUT)
    ap.add_argument("--no-warm", action="store_true", help="cand-उष्ण-फेरी वगळा")
    ap.add_argument("--force", action="store_true",
                    help="बाजार-वेळ-प्रतीक्षा वगळा")
    a = ap.parse_args()

    now = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    print("A/B चाचणी सुरू — IST " + now.strftime("%Y-%m-%d %H:%M:%S %a")
          + " | base=" + a.base + " cand=" + a.cand)
    with open("/proc/meminfo", encoding="utf-8") as f:
        mi = {l.split(":")[0]: int(l.split()[1]) for l in f
              if l.startswith(("MemTotal", "MemAvailable"))}
    print("RAM: एकूण " + str(round(mi["MemTotal"] / 1048576, 1)) + "Gi, उपलब्ध "
          + str(round(mi["MemAvailable"] / 1048576, 1)) + "Gi | डिस्क शिल्लक "
          + str(round(shutil.disk_usage("/").free / (1024 ** 3), 1)) + "Gi")

    if not a.force and now.weekday() < 5 \
            and "09:00" <= now.strftime("%H:%M") < "23:30":
        print("⚠️ बाजार/MCX-वेळ — 1-OCPU-वर चाचणी CPU-स्पर्धा करेल; "
              "10 सेकांद प्रतीक्षा (थांबवायचे असल्यास Ctrl-C, किंवा --force)")
        for i in range(10, 0, -1):
            print("  " + str(i) + "…", flush=True)
            time.sleep(1)

    if not ensure_pull(a.base):
        print("base-मॉडेलच नाही — समाप्त")
        return 1
    have_cand = ensure_pull(a.cand)

    watch = RamWatch()
    results = []
    run_one(a.base + "-थंड", a.base, watch, a.timeout, results)
    if have_cand:
        run_one(a.cand + "-थंड", a.cand, watch, a.timeout, results)
        if not a.no_warm:
            run_one(a.cand + "-उष्ण", a.cand, watch, a.timeout, results)

    print("\n" + "=" * 66)
    print("निकाल-सारांश")
    print("=" * 66)
    hdr = ("फेरी", "wall-से", "load-से", "उत्तर-टोकन", "टोकन/से",
           "RAM-min-MB", "JSON", "देवनागरी%", ">80-ओळी")
    print("{:<16}{:>9}{:>9}{:>10}{:>9}{:>12}{:>6}{:>10}{:>10}".format(*hdr))
    for r in results:
        print("{:<16}{:>9}{:>9}{:>10}{:>9}{:>12}{:>6}{:>10}{:>10}".format(
            r["label"][:16], str(r.get("wall_s", "-")),
            str(r.get("load_s", "-")), str(r.get("out_tok", "-")),
            str(r.get("gen_tok_s", "-")), str(r.get("min_ram_mb", "-")),
            ("यश" if r.get("ok") else "नाही"), str(r.get("deva_pct", "-")),
            str(r.get("over80_lines", "-"))))

    cand_cold = next((r for r in results
                      if r["label"].endswith("-थंड") and a.cand in r["model"]),
                     None)
    ram_floor = min((r["min_ram_mb"] for r in results
                     if r.get("min_ram_mb") is not None), default=0)
    if not have_cand:
        print("\nशिफारस: उमेदवार-मॉडेल उपलब्ध नाही — 1.7b तसेच (काही बदल नाही)")
    elif cand_cold and not cand_cold["ok"]:
        print("\nशिफारस: " + a.cand + " नाकारणे — JSON-पार्स/RAM-अपयश; "
              "1.7b तसेच (bot.env अबाधित)")
    elif ram_floor < 300:
        print("\nशिफारस: " + a.cand + " धोकादायक — किमान-उपलब्ध RAM "
              + str(ram_floor) + "MB < 300MB (OOM-धोका); 1.7b तसेच")
    elif cand_cold and cand_cold.get("wall_s", 9999) > 720:
        print("\nशिफारस: " + a.cand + " लॅटिन्सी-मर्यादेबाहेर (थंड "
              + str(cand_cold["wall_s"]) + "से > 720से); 1.7b तसेच")
    else:
        print("\nशिफारस: " + a.cand + " स्वीकार्य — bot.env मध्ये लिहा:")
        print("  AI_MODEL=" + a.cand)
        print("  AI_TIMEOUT=700")
        print("नंतर: sudo systemctl restart banknifty")
        print("(भाषा-गुणवत्ता डोळ्यांनी पडताळा — वरील RAW उत्तरे; उराडलेली वाटतील "
              "तर 1.7b तसेच — दोन्ही मॉडेल अमार्याद स्थापित राहतील)")

    outd = "/tmp/model_ab"
    os.makedirs(outd, exist_ok=True)
    with open(os.path.join(outd, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"when": now.isoformat(), "base": a.base, "cand": a.cand,
                   "ram_floor_mb": ram_floor, "results": results},
                  f, ensure_ascii=False, indent=1)
    print("तपशील साठवले: " + outd + "/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
