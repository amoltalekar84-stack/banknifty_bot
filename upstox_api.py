"""
Upstox API v2 हेल्पर — फक्त गरजेची फंक्शन्स.
स्रोत: https://upstox.com/developer/api-documentation/
"""

import time
import urllib.parse

import requests
from config import ist_now

BASE = "https://api.upstox.com/v2"
BASE_V3 = "https://api.upstox.com/v3"


class UpstoxError(Exception):
    """Upstox API त्रुटी"""
    pass


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _get(path_or_url, token, params=None, retries=2):
    """GET विनंती + रीट्राय + 401/429 हाताळणी"""
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=15)
            if r.status_code == 429:          # वेग मर्यादा — थांबा व पुन्हा प्रयत्न
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 401:          # टोकन संपले/अवैध
                raise UpstoxError("TOKEN_INVALID")
            r.raise_for_status()
            return r.json()
        except UpstoxError:
            raise
        except Exception as e:
            if attempt == retries:
                body = ""
                resp = getattr(e, "response", None)
                if resp is not None:
                    try:
                        body = (resp.text or "")[:180]
                    except Exception:
                        body = ""
                raise UpstoxError(f"GET fail: {e}"
                                  + (f" | body: {body}" if body else "")) from e
            time.sleep(1.0)
    raise UpstoxError("GET fail: retries exhausted")


# ------------------------------------------------------------------
# टोकन
# ------------------------------------------------------------------
def validate_token(token):
    """टोकन वैध आहे का? → (True, वापरकर्तानाव) किंवा (False, कारण)"""
    try:
        j = _get("/user/profile", token)
        d = j.get("data", {}) or {}
        return True, d.get("user_name") or d.get("user_id") or "OK"
    except UpstoxError as e:
        return False, str(e)


def exchange_code(code, client_id, client_secret, redirect_uri):
    """
    लॉगिन कोड → access_token
    (टोकन दुसऱ्या दिवशी सकाळी 3:30 ला संपतो — म्हणून रोज नवीन लागतो)
    """
    url = BASE + "/login/authorization/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        r = requests.post(url, data=data, timeout=20,
                          headers={"Accept": "application/json",
                                   "Content-Type": "application/x-www-form-urlencoded"})
        j = r.json()
    except Exception as e:
        raise UpstoxError(f"token exchange fail: {e}") from e
    tok = j.get("access_token")
    if not tok:
        raise UpstoxError("token exchange fail: " + str(j)[:300])
    return tok


# ------------------------------------------------------------------
# बाजार डेटा
# ------------------------------------------------------------------
def get_ltp(key, token):
    """एखाद्या इन्स्ट्रुमेंटची सध्याची किंमत (LTP)"""
    try:
        j = _get("/market-quote/ltp", token, params={"instrument_key": key})
    except UpstoxError:
        raise
    except Exception as e:
        raise UpstoxError(f"ltp fail: {e}") from e
    data = j.get("data", {}) or {}
    for v in data.values():
        lp = (v or {}).get("last_price")
        if lp is not None:
            return float(lp)
    return None


def get_today_candles(token, instrument_key, date_str):
    """आजचे 1-मिनिट कॅन्डल (ORB साठी)"""
    key_enc = urllib.parse.quote(instrument_key, safe="")
    url = f"{BASE}/historical-candle/{key_enc}/1minute/{date_str}/{date_str}"
    j = _get(url, token)
    candles = ((j.get("data") or {}).get("candles")) or []
    return sorted(candles, key=lambda c: c[0])


def get_prev_close(token, instrument_key, from_date, to_date):
    """आदल्या दिवसाची बंद किंमत (गॅप तपासणीसाठी)"""
    key_enc = urllib.parse.quote(instrument_key, safe="")
    url = f"{BASE}/historical-candle/{key_enc}/1day/{to_date}/{from_date}"
    j = _get(url, token)
    rows = ((j.get("data") or {}).get("candles")) or []
    if not rows:
        return None
    rows.sort(key=lambda c: c[0])
    return float(rows[-1][4])


def get_hist_candles(token, instrument_key, interval, from_date, to_date):
    """
    इतिहासातील कॅन्डल (बॅकटेस्टसाठी).
    interval: '1minute' / '30minute' / 'day' (Upstox v2)
    """
    key_enc = urllib.parse.quote(instrument_key, safe="")
    url = f"{BASE}/historical-candle/{key_enc}/{interval}/{to_date}/{from_date}"
    j = _get(url, token)
    return ((j.get("data") or {}).get("candles")) or []


def get_hist_candles_v3(token, instrument_key, unit, interval, from_date, to_date):
    """
    v3 historical API — इतर अंतराळ देते (उदा. unit='minutes', interval='5' → 5-मिनिट).
    उत्तराचे स्वरूप v2 प्रमाणेच [ts,o,h,l,c,v,oi] यादी.
    """
    key_enc = urllib.parse.quote(instrument_key, safe="")
    url = (f"{BASE_V3}/historical-candle/{key_enc}/{unit}/{interval}/"
           f"{to_date}/{from_date}")
    j = _get(url, token)
    d = j.get("data") or {}
    if isinstance(d, dict):
        if d.get("candles"):
            return d["candles"]
        inner = d.get("data") or {}
        if isinstance(inner, dict):
            return inner.get("candles") or []
    return []


_expiry_cache = {}            # index_key → (आजची तारीख, expiry) — दिवसात एकदाच resolve


def get_near_expiry(token, index_key):
    """option/contract (expiry ऐच्छिक) → आजपासून जवळची expiry (YYYY-MM-DD)"""
    today = ist_now().strftime("%Y-%m-%d")
    j = _get("/option/contract", token, params={"instrument_key": index_key})
    exps = sorted({r.get("expiry") for r in (j.get("data") or [])
                   if r.get("expiry")})
    future = [e for e in exps if e >= today]
    return future[0] if future else (exps[-1] if exps else None)


def get_option_chain(token, index_key):
    """ऑप्शन चेन. ⚠️ Upstox नवीन नियम: expiry_date आता आवश्यक
    (नसेल तर 400 Bad Request!). → दिवसात एकदा option/contract मधून
    जवळची expiry resolve करून cache; रिकामी चेन आली तर cache तोडून
    पुढच्या वेळी पुन्हा resolve."""
    today = ist_now().strftime("%Y-%m-%d")
    c = _expiry_cache.get(index_key)
    if not c or c[0] != today:
        exp = get_near_expiry(token, index_key)
        if not exp:
            raise UpstoxError(f"near-expiry सापडली नाही ({index_key})")
        _expiry_cache[index_key] = (today, exp)
        c = _expiry_cache[index_key]
    j = _get("/option/chain", token, params={"instrument_key": index_key,
                                             "expiry_date": c[1]})
    rows = j.get("data", []) or []
    if not rows:
        _expiry_cache.pop(index_key, None)
    return rows


# ------------------------------------------------------------------
# ऑर्डर (फक्त LIVE mode साठी — PAPER मध्ये कधीही कॉल होत नाही)
# ------------------------------------------------------------------
def place_order(token, instrument_key, qty, side):
    """MARKET ऑर्डर (side = 'BUY' किंवा 'SELL')"""
    payload = {
        "quantity": int(qty),
        "product": "I",              # इन्ट्राडे
        "validity": "DAY",
        "price": 0,
        "tag": "bnb_ai_bot",
        "instrument_token": instrument_key,
        "order_type": "MARKET",
        "transaction_type": side,
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False,
    }
    try:
        r = requests.post(BASE + "/order/place", json=payload, timeout=20,
                          headers={**_headers(token),
                                   "Content-Type": "application/json"})
        j = r.json()
    except Exception as e:
        raise UpstoxError(f"order fail: {e}") from e
    if r.status_code not in (200, 201) or j.get("status") not in ("success", "ok"):
        raise UpstoxError("order fail: " + str(j)[:300])
    return ((j.get("data") or {}).get("order_id")) or ""
