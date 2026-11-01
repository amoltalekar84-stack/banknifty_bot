"""
Upstox instruments सहाय्यक — MCX COPPER चे खरे कॉन्ट्रॅक्ट रोज आपोआप ओळखतो.

का आवश्यक?
• MCX Copper lot = 2500 kg (SEBI चा किमान ₹15 लाख कॉन्ट्रॅक्ट नियम —
  Copper Mini आता नाहीच), म्हणून कॉन्ट्रॅक्ट रोल होताना symbols बदलतात
• Upstox चा option-chain API MCX साठी खात्रीने समर्थित नाही → आपण
  Upstox ची सार्वजनिक instruments file वापरतो (टोकन लागत नाही):
  https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz

काय मिळते?  copper_snapshot() →
{
  "date": "2026-11-01",
  "fut":   {"key": "MCX_FO|578634", "symbol": "COPPER26NOVFUT",
            "expiry": "2026-11-30"},
  "opt_expiry": "2026-11-23",
  "strikes": {"1400.0": {"CE": "MCX_FO|…", "PE": "MCX_FO|…"}, …},
  "lot": 2500, "tick": 1.0,
}
डाउनलोड/पार्झ अयशस्वी → None (इंजिन त्या दिवशी Copper वगळते + नोंद करते).

फाईल दिवसातून एकदाच डाउनलोड → DATA_DIR मध्ये लहान JSON कॅश.
"""

import csv
import gzip
import io
import json
import os
import tempfile

import requests

INSTR_URL = ("https://assets.upstox.com/market-quote/instruments/"
             "exchange/complete.csv.gz")
DATA_DIR = os.getenv("DATA_DIR",
                     os.path.join(tempfile.gettempdir(), "bnb_data"))
_snapshot = None          # प्रक्रिया-कॅश (मेमरी)
_failing = False          # अयशस्वी झाल्यास लगेच लगेच पुन्हा नको


def _cache_path(date):
    return os.path.join(DATA_DIR, f"copper_instr_{date}.json")


def _pick(rows, today):
    """MCX COPPER rows मधून futures + ATM स्ट्राइक नकाशा बनवा."""
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
    for r in opts:
        if r["expiry"] != near:
            continue
        node = strikes.setdefault(r["strike"], {})
        node[r["option_type"]] = r["instrument_key"]
    # CE व PE दोन्ही असलेलेच स्ट्राइक ठेवा
    strikes = {k: v for k, v in strikes.items()
               if v.get("CE") and v.get("PE")}
    if not strikes:
        return None
    return {
        "date": today,
        "fut": {"key": f0["instrument_key"], "symbol": f0["tradingsymbol"],
                "expiry": f0["expiry"]},
        "opt_expiry": near,
        "strikes": strikes,
        "lot": int(f0["lot_size"] or 2500),
        "tick": float(f0["tick_size"] or 1),
    }


def copper_snapshot(force=False):
    """आजचा Copper कॉन्ट्रॅक्ट स्नॅपशॉट (कॅशसह) — None = Copper आज नाही."""
    global _snapshot, _failing
    if _failing and not force:
        return None
    if _snapshot and _snapshot.get("date") == _today_str():
        return _snapshot

    from datetime import date
    today = _today_str()
    os.makedirs(DATA_DIR, exist_ok=True)
    cp = _cache_path(today)

    # ① डिस्क कॅश (VM रीस्टार्ट झाला तरी पुन्हा 15MB नको)
    if not force and os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as fh:
                snap = json.load(fh)
            if snap.get("date") == today and snap.get("strikes"):
                _snapshot = snap
                _failing = False
                return _snapshot
        except (ValueError, OSError):
            pass

    # ② डाउनलोड + पार्झ
    try:
        resp = requests.get(INSTR_URL, timeout=40)
        resp.raise_for_status()
        raw = gzip.decompress(resp.content)
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        rows = [r for r in reader
                if r.get("exchange") == "MCX_FO"
                and r.get("name") == "COPPER"]
        snap = _pick(rows, today)
        if not snap:
            raise ValueError("COPPER कॉन्ट्रॅक्ट सापडले नाहीत")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh)
        _snapshot = snap
        _failing = False
        return _snapshot
    except Exception as e:
        import store
        store.log_event(f"instruments: {repr(e)[:200]}")
        _failing = True
        return None


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
    # चाचणी: खरी फाईल वापरून बघू (डाउनलोड ~15MB)
    import sys
    os.environ.setdefault("DATA_DIR", "/tmp/bnb_instr_test")
    s = copper_snapshot(force=True)
    if not s:
        print("❌ snapshot मिळाला नाही")
        sys.exit(1)
    print("✅ Copper snapshot:", s["date"])
    print("  फ्यूचर्स:", s["fut"]["symbol"], s["fut"]["key"],
          "exp", s["fut"]["expiry"])
    print("  ऑप्शन एक्सपायरी:", s["opt_expiry"], "| स्ट्राइक संख्या:",
          len(s["strikes"]), "| lot:", s["lot"], "| tick:", s["tick"])
    ks = sorted(float(k) for k in s["strikes"])
    print("  स्ट्राइक रेंज:", ks[0], "–", ks[-1])
    near = atm_strikes(s, 1400.0)
    print("  ATM(1400) जवळचे स्ट्राइक:", near)
    if near:
        k0 = str(near[0])
        print("  नकाशा:", s["strikes"].get(k0))
