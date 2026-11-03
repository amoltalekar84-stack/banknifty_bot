"""
OI/ग्रीक्स कलेक्टर — "स्मार्ट-पैसा" डेटा जमा करणे (स्ट्रॅटेजी-अभ्यासासाठी).

बाजार वेळेत दर 5 मिनिटांनी प्रत्येक इंडेक्सची ऑप्शन चेन आणून साठवतो:
  • PCR (OI-आधारित)              • CE/PE एकूण OI + आजचा बदल
  • Max Pain (सेटलमेंट व्हॅल्यू)    • CE भिंत (प्रतिकार) / PE भिंत (आधार)
  • ATM IV                       • कमी केलेली संपूर्ण चेन (zlib BLOB:
    delta/gamma/theta/vega/IV/volume प्रति स्ट्राइक — ATM ग्रीक्स /oi कार्डावर)
  • India VIX (रेजिम-फिल्टर) — vix_snap टेबल, दर 5 मिनिटांनी

साठवण: store.oi_snap टेबल. वापर:
  • engine.start_engine() → start_collector() (स्वयंचलित thread)
  • अलग तपासणी (VM वर स्कीमा पडताळणी): ./venv/bin/python oicollect.py
"""
import json
import os
import threading
import time
import traceback
import zlib
from datetime import time as dtime

import config as C
import store
from config import ist_now
from upstox_api import get_ltp, get_market_status, get_option_chain

INTERVAL_SEC = 300                     # 5 मिनिटे
VIX_KEY = "NSE_INDEX|India VIX"        # रेजिम-फिल्टर — स्ट्रॅटेजी अभ्यासासाठी
ENABLED = os.getenv("OI_COLLECT", "YES").strip().upper() != "NO"
_chain_cache = {}                      # सिम्बॉल → अंतिम metrics (eval/स्टेटससाठी)
_last_journal = 0.0                    # तासाला एकदाच journal सारांश


def _num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _oi_of(node):
    """node → (oi, prev_oi, pchange%).
    नवीन Upstox योजना: market_data.oi / prev_oi; जुनी: open_interest /
    pchangeinopeninterest — दोन्ही हाताळल्या."""
    md = node.get("market_data") or {}
    oi = md.get("oi", md.get("open_interest", node.get("open_interest")))
    prev = md.get("prev_oi")
    pch = md.get("pchangeinopeninterest", node.get("pchangeinopeninterest"))
    if prev is None:
        prev = (oi / (1.0 + _num(pch) / 100.0)) if (oi and pch) else oi
    return _num(oi), _num(prev), _num(pch)


def _vol_of(node):
    """call_options/put_options node → आजचा ट्रेड-व्हॉल्यूम (भिंतीची पुष्टी)"""
    md = node.get("market_data") or {}
    return _num(md.get("volume"))


def _iv_of(node):
    """option_greeks.iv — % मध्ये अपेक्षा (उदा. 12.4); बर्ड असल्यास 0"""
    g = node.get("option_greeks") or {}
    iv = _num(g.get("iv"), 0.0)
    return iv if 0 < iv < 500 else 0.0


def _max_pain(strikes):
    """सेटलमेंट-व्हॅल्यू जिथे ऑप्शन-लेखकांचे एकूण नुकसान किमान.
    strikes = [{"k", "ce_oi", "pe_oi"}]"""
    ks = sorted({s["k"] for s in strikes if s["k"]})
    if not ks:
        return None
    best, best_pain = None, None
    for w in ks:
        pain = 0.0
        for s in strikes:
            k, coi, poi = s["k"], s["ce_oi"], s["pe_oi"]
            if w > k:
                pain += (w - k) * coi          # CE लेखकांचे नुकसान
            if k > w:
                pain += (k - w) * poi          # PE लेखकांचे नुकसान
        if best_pain is None or pain < best_pain:
            best, best_pain = w, pain
    return best


def compute_chain(chain, spot, near=None):
    """Upstox चेन rows → metrics dict; रिकामी/बर्ड असल्यास None.
    कधीच एक्सेप्शन टाकत नाही — पर्स अयशस्वी तरी कलेक्टर जगला पाहिजे."""
    try:
        if not chain:
            return None
        exps = sorted({(r.get("expiry_date") or r.get("expiry")) for r in chain
                       if (r.get("expiry_date") or r.get("expiry"))})
        near = near or (exps[0] if exps else None)
        rows = ([r for r in chain
                 if (r.get("expiry_date") or r.get("expiry")) == near]
                if near else list(chain))
        if not rows:
            return None
        spot = _num(spot)

        ce_oi = pe_oi = ce_chg = pe_chg = 0.0
        strikes, small = [], []
        for r in rows:
            k = _num(r.get("strike_price"))
            if not k:
                continue
            c = r.get("call_options") or {}
            p = r.get("put_options") or {}
            coi, cprev, cp = _oi_of(c)
            poi, pprev, pp = _oi_of(p)
            ce_oi += coi
            pe_oi += poi
            ce_chg += coi - cprev                 # खरा absolute बदल
            pe_chg += poi - pprev
            strikes.append({"k": k, "ce_oi": coi, "pe_oi": poi})
            g_c = c.get("option_greeks") or {}
            g_p = p.get("option_greeks") or {}
            small.append({"k": k, "ce_oi": coi, "pe_oi": poi,
                          "ce_vol": _vol_of(c), "pe_vol": _vol_of(p),
                          "ce_iv": _iv_of(c), "pe_iv": _iv_of(p),
                          "ce_d": _num(g_c.get("delta")),
                          "pe_d": _num(g_p.get("delta")),
                          "ce_g": _num(g_c.get("gamma")),
                          "pe_g": _num(g_p.get("gamma")),
                          "ce_t": _num(g_c.get("theta")),
                          "pe_t": _num(g_p.get("theta")),
                          "ce_v": _num(g_c.get("vega")),
                          "pe_v": _num(g_p.get("vega"))})

        if not strikes:
            return None

        atm_row = min(rows, key=lambda r: abs(_num(r.get("strike_price")) - spot))
        atm = _num(atm_row.get("strike_price"))
        c_atm = atm_row.get("call_options") or {}
        p_atm = atm_row.get("put_options") or {}
        civ, piv = _iv_of(c_atm), _iv_of(p_atm)
        atm_iv = (civ + piv) / 2.0 if (civ and piv) else (civ or piv)

        ce_wall = max(strikes, key=lambda s: s["ce_oi"])["k"] if ce_oi else None
        pe_wall = max(strikes, key=lambda s: s["pe_oi"])["k"] if pe_oi else None

        return {
            "spot": spot, "atm": atm, "near_expiry": near,
            "pcr": (pe_oi / ce_oi) if ce_oi > 0 else None,
            "ce_oi": round(ce_oi), "pe_oi": round(pe_oi),
            "ce_chg": round(ce_chg), "pe_chg": round(pe_chg),
            "max_pain": _max_pain(strikes), "atm_iv": round(atm_iv, 2) or None,
            "ce_wall": ce_wall, "pe_wall": pe_wall,
            "chain_blob": zlib.compress(json.dumps(small).encode()),
        }
    except Exception:
        return None


def atm_greeks(blob, atm):
    """chain BLOB → ATM स्ट्राइकचा ग्रीक्स-ओळ (dict) — नाहीतर None.
    जुने स्नॅपशॉट (gamma नसलेले) सुद्धा चालतील — गहाळ की = None."""
    try:
        rows = json.loads(zlib.decompress(blob))
        if not rows:
            return None
        atm = _num(atm)
        return min(rows, key=lambda r: abs(_num(r.get("k")) - atm))
    except Exception:
        return None


def collect_symbol(S, token, spot=None):
    """एका सिम्बॉलचा स्नॅपशॉट आणून जतन करा → (metrics, error)"""
    key = S.get("index_key")
    if not key:
        return None, "index_key नाही (MCX — आत्ता सुटलेले नाही)"
    try:
        chain = get_option_chain(token, key)
    except Exception as e:
        return None, repr(e)[:120]
    if spot is None:
        try:
            spot = get_ltp(key, token) or 0.0
        except Exception:
            spot = 0.0
    m = compute_chain(chain, spot)
    if not m:
        return None, "चेन रिकामी/अवैध"
    n = ist_now()
    m["ts"] = n.strftime("%Y-%m-%d %H:%M:%S")
    blob = m.pop("chain_blob", None)
    _chain_cache[S["key"]] = dict(m)
    store.oi_insert(S["key"], n.strftime("%Y-%m-%d"), m, blob)
    return m, None


def collect_vix(token):
    """India VIX एक LTP → store.vix_snap; अयशस्वी → None (कधीच एक्सेप्शन नाही)"""
    try:
        v = _num(get_ltp(VIX_KEY, token))
        if v > 0:
            store.vix_insert(ist_now().strftime("%Y-%m-%d"), v)
            return v
    except Exception:
        pass
    return None


def _in_market_hours(n):
    return n.weekday() < 5 and dtime(9, 15) <= n.time() <= dtime(15, 30)


def collect_all_once(token):
    """सर्व इंडेक्सचे एक फेरी → [{short, pcr, err}]"""
    out = []
    for S in C.active_symbols():
        if not S.get("index_key"):
            continue                          # MCX — आत्ता फक्त इंडेक्स
        m, err = collect_symbol(S, token)
        out.append({"short": S["short"], "m": m, "err": err})
    return out


def start_collector():
    """engine मधून एकदाच — स्वतंत्र daemon thread"""
    if not ENABLED:
        print("OI कलेक्टर बंद (OI_COLLECT=NO)")
        return
    threading.Thread(target=_loop, daemon=True, name="oicollect").start()


def _loop():
    global _last_journal
    time.sleep(20)                            # इंजिन पूर्ण उघडू द्या
    while True:
        try:
            n = ist_now()
            tok = store.get_state("upstox_token")
            tdate = store.get_state("token_date")
            if (tok and tdate == n.strftime("%Y-%m-%d")
                    and _in_market_hours(n)):
                st = None                     # 🏳️ NSE सुट्टी तपासा — fail-open
                try:
                    st = get_market_status(tok, "NSE")
                except Exception:
                    st = None
                if st == "NORMAL_CLOSE":      # चेन जुनीच राहील — कॉल वाया
                    time.sleep(INTERVAL_SEC)
                    continue
                vix = collect_vix(tok)        # 📈 VIX — चेनहून स्वतंत्र, निरागद
                res = collect_all_once(tok)
                ok = [r for r in res if r["m"]]
                if ok and time.time() - _last_journal > 3600:
                    _last_journal = time.time()
                    s = ", ".join(f"{r['short']} PCR "
                                  f"{(r['m']['pcr'] or 0):.2f}" for r in ok)
                    if vix:
                        s += f" | VIX {vix:.2f}"
                    store.log_event(f"🧠 OI स्नॅपशॉट जमा होतोय ({len(ok)} "
                                    f"सिम्बॉल्स): {s}")
                bad = [r for r in res if r["err"]]
                if bad and not ok:
                    msg = "oi: " + "; ".join(
                        f"{r['short']}→{r['err']}" for r in bad)[:200]
                    if vix:
                        msg += f" | VIX {vix:.2f} तरी जमा ✓"
                    store.log_event(msg)
        except Exception as e:
            try:
                store.log_event("oi err: " + repr(e)
                                + traceback.format_exc()[:200])
            except Exception:
                pass
        time.sleep(INTERVAL_SEC)


# ------------------------------------------------------------------
# स्वतंत्र पडताळणी: ./venv/bin/python oicollect.py  → स्कीमा + नमुना आकडे
# ------------------------------------------------------------------
if __name__ == "__main__":
    # systemd सेवा DATA_DIR=<repo>/data घेऊन चालते (deploy.sh);
    # बेअर probe ने तीच DB बघावी — नाहीतर /tmp/bnb_data (रिकामी) बघून
    # सेवेकडे टोकन असतानाही चुकीचे "टोकन नाही" दिसते.
    if not os.getenv("DATA_DIR"):
        _dd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        if os.path.isdir(_dd):
            os.environ["DATA_DIR"] = _dd
            store.DATA_DIR = _dd
            store.DB_PATH = os.path.join(_dd, "bot.db")
    store.init_db()
    tok = C.UPSTOX_ACCESS_TOKEN or store.get_state("upstox_token")
    if not tok:
        print("टोकन नाही — आधी /code चालवा")
        raise SystemExit(1)
    S = next(s for s in C.SYMBOLS if s["key"] == "BANKNIFTY")
    chain = get_option_chain(tok, S["index_key"])
    print("चेन rows:", len(chain))
    if chain:
        r0 = chain[0]
        print("row keys:", sorted(r0.keys()))
        c = r0.get("call_options") or {}
        print("call node keys:", sorted(c.keys()))
        print("market_data keys:", sorted((c.get("market_data") or {}).keys()))
        print("greeks keys:", sorted((c.get("option_greeks") or {}).keys()))
    try:
        spot = get_ltp(S["index_key"], tok) or 0.0
    except Exception:
        spot = 0.0
    m = compute_chain(chain, spot)
    if m:
        blob = m.pop("chain_blob", b"")
        print("spot:", spot)
        for k, v in m.items():
            print(f"  {k}: {v}")
        print("chain blob:", len(blob), "bytes compressed,",
              len(zlib.decompress(blob)) // 1024, "KB raw")
    else:
        print("compute_chain अयशस्वी — वरील keys पहा")
    print("VIX:", collect_vix(tok))
