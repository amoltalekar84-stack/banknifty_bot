"""
Upstox instruments सहाय्यक — MCX COMMODITIES (Copper/Gold/Silver/
Natural Gas/Crude) चे खरे कॉन्ट्रॅक्ट रोज आपोआप ओळखतो.

का आवश्यक?
• MCX लॉट साईज (SEBI किमान ₹15 लाख कॉन्ट्रॅक्ट नियमानंतर) कालांतराने
  बदलतात व कॉन्ट्रॅक्ट रोल होताना symbols बदलतात → कधीही हार्ड-कोड नको
• Upstox चा option-chain API MCX साठी खात्रीने समर्थित नाही → आपण
  Upstox ची सार्वजनिक instruments file वापरतो (टोकन लागत नाही):
  https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz

काय मिळते?  mcx_snapshot("COPPER") →
{
  "date": "2026-11-01", "commodity": "COPPER",
  "fut":   {"key": "MCX_FO|578634", "symbol": "COPPER26NOVFUT",
            "expiry": "2026-11-30"},
  "opt_expiry": "2026-11-23",
  "strikes": {"1400.0": {"CE": "MCX_FO|…", "PE": "MCX_FO|…"}, …},
  "lot": 2500,        # फ्यूचर्स लॉट (fallback)
  "opt_lot": 2500,    # ऑप्शनचा खरा लॉट (trade qty यातून)
  "tick": 1.0,
}
डाउनलोड/पार्झ अयशस्वी → None (इंजिन त्या दिवशी ती वस्तू वगळते + नोंद करते).

फाईल दिवसातून एकदाच डाउनलोड → DATA_DIR मध्ये लहान JSON कॅश (प्रति वस्तू).
"""

import csv
import gzip
import io
import json
import os
import re
import tempfile

import requests

INSTR_URL = ("https://assets.upstox.com/market-quote/instruments/"
             "exchange/complete.csv.gz")
DATA_DIR = os.getenv("DATA_DIR",
                     os.path.join(tempfile.gettempdir(), "bnb_data"))
_snapshots = {}           # commodity → प्रक्रिया-कॅश (मेमरी)
_failing = {}             # commodity → True (अयशस्वी झाल्यास लगेच पुन्हा नको)


def _cache_path(commodity, date):
    return os.path.join(DATA_DIR, f"mcx_instr_{commodity}_{date}.json")


def _pick(rows, today, commodity="?", ts_pattern=None):
    r"""MCX rows मधून futures + ATM स्ट्राइक नकाशा बनवा.
    ts_pattern — फक्त MAIN series (उदा. ^SILVER(?!100)\d → SILVER26DEC,
    SILVERM/SILVER100 वगळले). नाहीतर mini-सीरीज चुकून निवडली जाऊ शकते."""
    if ts_pattern:
        rows = [r for r in rows if re.match(ts_pattern,
                                            r.get("tradingsymbol") or "")]
    fut = [r for r in rows if r["instrument_type"] == "FUTCOM"
           and r["expiry"] >= today]
    if not fut:
        return None
    fut.sort(key=lambda r: r["expiry"])
    f0 = fut[0]

    opts = [r for r in rows if r["instrument_type"] == "OPTFUT"
            and r["expiry"] >= today]
    if not opts:
        return None
    expiries = sorted({r["expiry"] for r in opts})
    near = expiries[0]                     # सर्वात जवळची एक्सपायरी

    strikes = {}
    lots = {}
    for r in opts:
        if r["expiry"] != near:
            continue
        node = strikes.setdefault(r["strike"], {})
        node[r["option_type"]] = r["instrument_key"]
        try:
            lots[r["lot_size"]] = lots.get(r["lot_size"], 0) + 1
        except (TypeError, ValueError):
            pass
    # CE व PE दोन्ही असलेलेच स्ट्राइक ठेवा
    strikes = {k: v for k, v in strikes.items()
               if v.get("CE") and v.get("PE")}
    if not strikes:
        return None
    # खरा ऑप्शन lot = या मालिकेतला सर्वात सामान्य lot_size (mode)
    opt_lot = None
    if lots:
        opt_lot = int(max(lots.items(), key=lambda kv: kv[1])[0] or 0) or None
    return {
        "date": today, "commodity": commodity,
        "fut": {"key": f0["instrument_key"], "symbol": f0["tradingsymbol"],
                "expiry": f0["expiry"]},
        "opt_expiry": near,
        "strikes": strikes,
        "lot": int(f0["lot_size"] or 0),
        "opt_lot": opt_lot,
        "tick": float(f0["tick_size"] or 1),
    }


def mcx_snapshot(commodity, force=False, ts_pattern=None):
    """आजचा कॉन्ट्रॅक्ट स्नॅपशॉट (कॅशसह) — None = आज ती वस्तू नाही.
    commodity = Upstox च्या फाईलमधले खरे नाव:
    COPPER / GOLD / SILVER / NATURALGAS / CRUDE OIL
    ts_pattern = फक्त main series निवडण्याचा regex (config मधून येतो)."""
    commodity = (commodity or "").strip().upper()
    if _failing.get(commodity) and not force:
        return None
    if _snapshots.get(commodity) and \
            _snapshots[commodity].get("date") == _today_str():
        return _snapshots[commodity]

    today = _today_str()
    os.makedirs(DATA_DIR, exist_ok=True)
    cp = _cache_path(commodity, today)

    # ① डिस्क कॅश (VM रीस्टार्ट झाला तरी पुन्हा 15MB नको)
    if not force and os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as fh:
                snap = json.load(fh)
            if snap.get("date") == today and snap.get("strikes"):
                _snapshots[commodity] = snap
                _failing[commodity] = False
                return snap
        except (ValueError, OSError):
            pass

    # ② डाउनलोड + पार्झ (एकाच डाउनलोडमधून सर्व वस्तू)
    try:
        resp = requests.get(INSTR_URL, timeout=40)
        resp.raise_for_status()
        raw = gzip.decompress(resp.content)
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        rows = [r for r in reader
                if r.get("exchange") == "MCX_FO"
                and r.get("name") == commodity]
        snap = _pick(rows, today, commodity, ts_pattern)
        if not snap:
            raise ValueError(commodity + " कॉन्ट्रॅक्ट सापडले नाहीत")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh)
        _snapshots[commodity] = snap
        _failing[commodity] = False
        return snap
    except Exception as e:
        import store
        store.log_event(f"instruments[{commodity}]: {repr(e)[:200]}")
        _failing[commodity] = True
        return None


def copper_snapshot(force=False):
    """जुने नाव अबाधित (सुसंगतता) — Copper स्नॅपशॉट."""
    return mcx_snapshot("COPPER", force=force, ts_pattern=r"^COPPER\d")


def atm_strikes(snap, spot, n=4):
    """स्पॉटच्या सर्वात जवळचे n स्ट्राइक (CE+PE असलेले) → sorted keys (float)."""
    try:
        ks = [(abs(float(k) - float(spot)), float(k))
              for k in (snap or {}).get("strikes", {})]
    except (TypeError, ValueError):
        return []
    ks.sort()
    return [k for _, k in ks[:n]]


def _today_str():
    from config import ist_now
    return ist_now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    # चाचणी: खरी फाईल वापरून बघू (डाउनलोड ~15MB — सर्व वस्तू एकदाच)
    import sys
    os.environ.setdefault("DATA_DIR", "/tmp/bnb_instr_test")
    for comm in ["COPPER", "GOLD", "SILVER", "NATURALGAS", "CRUDEOIL"]:
        s = mcx_snapshot(comm, force=True)
        if not s:
            print(f"❌ {comm}: snapshot मिळाला नाही")
            continue
        ks = sorted(float(k) for k in s["strikes"])
        print(f"✅ {comm}: फ्यू {s['fut']['symbol']} (exp {s['fut']['expiry']}) | "
              f"ऑप्शन exp {s['opt_expiry']} | स्ट्राइक {len(s['strikes'])} "
              f"({ks[0]}–{ks[-1]}) | lot {s['lot']} / opt_lot {s['opt_lot']} "
              f"| tick {s['tick']}")
        if comm == "COPPER":
            near = atm_strikes(s, 1400.0)
            print("   ATM(1400) जवळचे स्ट्राइक:", near)
