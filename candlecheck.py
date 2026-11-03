#!/usr/bin/env python3
"""कॅन्डल-तपासणी: कोणता हिस्टॉरिकल-एंडपॉइंट आजचे 1-मिनिट कॅन्डल देतो?
    ./venv/bin/python candlecheck.py
प्रत्येक सिम्बॉलसाठी V2 (जुना) आणि V3 (नवीन) यांची कॅन्डल-संख्या दाखवतो —
बाजारबंदीतही आजचे कॅन्डल मिळायला हवेत; 0-0 आले तर एरर-मजकूर दिसेल."""
import os
import urllib.parse

if not os.getenv("DATA_DIR"):
    _dd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if os.path.isdir(_dd):
        os.environ["DATA_DIR"] = _dd

import config as C
import engine
import store
import upstox_api as U
from config import ist_now


def _rows(j):
    d = j.get("data") or {}
    rows = d.get("candles") or []
    if not rows and isinstance(d.get("data"), dict):
        rows = d["data"].get("candles") or []
    return rows


def _count(token, key, route, date):
    ke = urllib.parse.quote(key, safe="")
    if route == "intraday":
        url = f"{U.BASE}/historical-candle/intraday/{ke}/1minute"
    elif route == "V3":
        url = f"{U.BASE_V3}/historical-candle/{ke}/minutes/1/{date}/{date}"
    else:
        url = f"{U.BASE}/historical-candle/{ke}/1minute/{date}/{date}"
    try:
        return "%d कॅन्डल" % len(_rows(U._get(url, token)))
    except Exception as e:
        return "एरर: " + repr(e)[:110]


def main():
    tok = C.UPSTOX_ACCESS_TOKEN or store.get_state("upstox_token")
    if not tok:
        print("टोकन नाही — आधी /code चालवा")
        raise SystemExit(1)
    date = ist_now().strftime("%Y-%m-%d")
    print("तारीख: %s — आजचे 1-मिनिट कॅन्डल (V2 जुना मार्ग vs V3 नवीन मार्ग)" % date)
    print()
    for S in C.SYMBOLS:
        dnote = ""
        try:
            dkey, _snap = engine._data_key(S, ist_now())
        except Exception as e:
            dkey = None
            dnote = " (contract-एरर: " + repr(e)[:60] + ")"
        if not dkey:
            dkey = S.get("index_key")
            if not dnote:
                dnote = " (contract नाही — index_key वापरतो)"
        print("%-14s dkey=%s" % (S["label"], dkey))
        print("   intraday: %s" % _count(tok, dkey, "intraday", date))
        print("   V3:       %s" % _count(tok, dkey, "V3", date))
        print("   V2 dated: %s%s" % (_count(tok, dkey, "V2", date), dnote))
    print()
    print("टीप: intraday >0 = ORB चालेल (मुख्य मार्ग); बाजारबंदीतही आजचे कॅन्डल दिसतील.")


if __name__ == "__main__":
    main()
