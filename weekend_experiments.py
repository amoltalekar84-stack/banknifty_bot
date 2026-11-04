#!/usr/bin/env python3
"""
weekend_experiments.py — शनिवारीचे 4 ORB-प्रयोग (बॅकटेस्ट, BANKNIFTY)

चालवा:   ./venv/bin/python weekend_experiments.py [FROM TO]
उदा.:    ./venv/bin/python weekend_experiments.py 2026-10-01 2026-11-03
डीफॉल्ट: 2026-10-01 → कालपर्यंत

प्रयोग (सर्वजण BASE शी तुलनेत):
  BASE — आजचेच जिवंत नियम: OR 09:15–09:30, रुंदी-फिल्टर 0.15–2.0%, गॅप 1%,
         5m-क्लोज ब्रेकआउट, SL −20%, TP-लॅडर +20/+40/+60% (1/3 बुक + BE-lock),
         15:05 स्क्वेअर-ऑफ, 0.05% स्लिपेज, खरे ब्रोकरेज-कर (charges.py), लॉट 30,
         दिवसाला कमाल 2 ट्रेड, ₹2,500 दैनिक-हॉल्ट, 90% भांडवल-गार्ड.
  EXP1 — ब्रेकआउट-बफर: क्लोज OR-किनार + 0.10% (स्पॉटच्या) बाहेर तरच एंट्री
         (1-पॉईंटसारखे अरुंद खोटे ब्रेकआउट गाळण्याचा प्रयत्न)
  EXP2 — मिडलाइन-रिआर्म: बंद ट्रेडनंतर त्याच दिशेचा पुढचा सिग्नल फक्त तेव्हा
         जेव्हा क्लोज OR-मध्यबिंदू परत क्रॉस करतो (LuxAlgo anti-reentry)
  EXP3 — डेली-बायस: आदल्या दिवसाचा OR-mid आजच्यापेक्षा वर → CE सोपे, PE ला
         अजून 0.5×रुंदी बफर (उलटे तसेच) — विरुद्ध-बायस ब्रेकआउट कठीण
  EXP4 — OR-विंडो: 5 मिनिटे (9:15–9:20) vs 15 (BASE) vs 30 (9:15–9:45)

टोकन: UPSTOX_TOKEN env → नसेल तर <repo>/data/bot.db (सेवेशीच टोकन).
डेटा: न असलेला प्रत्येक (दिवस,स्ट्राइक,side) Upstox कडून आणून <repo>/bt_cache मध्ये
      साठवला जातो; टोकन नसेल/अपयशी झाला तर तो ट्रेड "skip" — निकाल अपूर्ण दिसेल.
टीप: एक्सपायरी-नकाशे 2026-10-27 (expired) व 2026-11-23 (लाइव्ह) घातले आहेत —
     या खिडकीबाहेरच्या तारखांसाठी कॉन्स्टंट बदला.

निकाल: कन्सोल-तक्ता + experiments_result.csv (gitignored)
"""
import gzip
import json
import os
import sqlite3
import sys
import time
from datetime import date as _date, datetime, time as dtime, timedelta, \
    timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charges as CHG   # noqa: E402
import config as C      # noqa: E402
import strategy as S    # noqa: E402  (parse_candles + last_completed_5m)

REPO = os.path.dirname(os.path.abspath(__file__))
CACHE = os.getenv("BT_CACHE", os.path.join(REPO, "bt_cache"))
os.makedirs(CACHE, exist_ok=True)

IDX = "NSE_INDEX|Nifty Bank"
EXPIRED_EXPIRY = "2026-10-27"
LIVE_EXPIRY = "2026-11-23"
BASE = "https://api.upstox.com/v2"


class AuthFail(Exception):
    pass


# ---------------------------------------------------------------
# टोकन
# ---------------------------------------------------------------
def get_token():
    tok = os.getenv("UPSTOX_TOKEN", "").strip()
    if tok:
        return tok
    db = os.path.join(REPO, "data", "bot.db")
    if os.path.exists(db):
        try:
            con = sqlite3.connect(db, timeout=10)
            row = con.execute(
                "SELECT v FROM state WHERE k='upstox_token'").fetchone()
            con.close()
            if row and row[0]:
                return row[0].strip()
        except Exception as e:
            print(f"⚠️ DB टोकन-वाचन अपयशी: {e!r}")
    return None


TOKEN = get_token()
HDR = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"} \
    if TOKEN else {"Accept": "application/json"}
if not TOKEN:
    print("⚠️ टोकन नाही (env UPSTOX_TOKEN किंवा <repo>/data/bot.db) — "
          "फक्त कॅश-डेटा वापरणार; न असलेले ट्रेड skip दिसतील.\n")


# ---------------------------------------------------------------
# API + फाईल-कॅश
# ---------------------------------------------------------------
def _cache_load(tag):
    fn = os.path.join(CACHE, tag + ".json")
    if os.path.exists(fn):
        j = json.load(open(fn))
        return S.parse_candles(j.get("data", {}).get("candles", []) or [])
    return None


def _cache_save(tag, j):
    json.dump(j, open(os.path.join(CACHE, tag + ".json"), "w"))


def api_get(path, params=None, tag=None):
    fn = os.path.join(CACHE, (tag or path.replace("/", "_")) + ".json")
    if os.path.exists(fn):
        return json.load(open(fn))
    if not TOKEN:
        raise AuthFail("टोकन नाही")
    for attempt in range(3):
        try:
            r = requests.get(BASE + path, headers=HDR, params=params, timeout=25)
        except requests.RequestException as e:
            if attempt == 2:
                raise AuthFail(f"नेटवर्क: {e!r}")
            time.sleep(2.0 * (attempt + 1))
            continue
        if r.status_code == 401:
            raise AuthFail("टोकन अवैध/संपला (401)")
        if r.status_code == 429:
            time.sleep(2.0 * (attempt + 1))
            continue
        j = r.json()
        if j.get("status") != "success":
            raise AuthFail(f"API fail {path}: {str(j)[:160]}")
        json.dump(j, open(fn, "w"))
        return j
    raise AuthFail("429 retries संपले")


def fetch_option_candles(okey, ds, strike, side):
    """(दिवस, करार) च्या 1-मिनिट कॅन्डल्स; जुना backtest-कॅश (opt_/optL_) सुद्धा वापरतो"""
    is_exp = ds <= EXPIRED_EXPIRY
    old_tag = f"{'opt' if is_exp else 'optL'}_{ds}_{int(strike)}_{side}"
    got = _cache_load(old_tag)
    if got is not None:
        return got
    tag = f"optx_{ds}_{os.path.basename(okey)[-24:]}"
    got = _cache_load(tag)
    if got is not None:
        return got
    if is_exp:
        j = api_get(f"/expired-instruments/historical-candle/"
                    f"{requests.utils.quote(okey, safe='')}/1minute/{ds}/{ds}",
                    tag=tag)
    else:
        j = api_get(f"/historical-candle/"
                    f"{requests.utils.quote(okey, safe='')}/1minute/{ds}/{ds}",
                    tag=tag)
    _cache_save(tag, j)
    return S.parse_candles(j.get("data", {}).get("candles", []) or [])


# ---------------------------------------------------------------
# डेटा-लोड (जुने backtest-कॅश-टॅग सुद्धा ओळखतो)
# ---------------------------------------------------------------
def _load_or_fetch(tag, aliases, path, params=None):
    """आधी नवीन टॅग, मग जुने अलायस-कॅश, नाहीतर fetch (अपयशी → अलायस किंवा एरर)"""
    fn = os.path.join(CACHE, tag + ".json")
    if os.path.exists(fn):
        return json.load(open(fn))
    for al in aliases:
        afn = os.path.join(CACHE, al + ".json")
        if os.path.exists(afn):
            print(f"   (जुने कॅश '{al}' वापरतोय)")
            return json.load(open(afn))
    j = api_get(path, params=params, tag=tag)
    return j


def load_data(frm, to):
    print(f"▶ Index 1-min कॅन्डल्स {frm} → {to} (आधीचे 10 दिवससुद्धा — बायस/गॅपसाठी)...")
    back = (datetime.strptime(frm, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
    q = requests.utils.quote(IDX, safe="")
    j = _load_or_fetch(
        f"idx_1m_{back}_{to}", ["idx_1m_oct", "idx_1m_sep_oct"],
        f"/historical-candle/{q}/1minute/{to}/{back}")
    idx = S.parse_candles(j.get("data", {}).get("candles", []) or [])
    print(f"   {len(idx)} कॅन्डल्स")

    print("▶ Daily closes (गॅप-फिल्टर)...")
    j = _load_or_fetch(
        f"idx_1d_{back}_{to}", ["idx_1d_sep_oct", "idx_1d_oct"],
        f"/historical-candle/{q}/day/{to}/{back}")
    dc = {r[0][:10]: float(r[4]) for r in (j.get("data", {}).get("candles", []) or [])}

    print("▶ Expired contracts (expiry " + EXPIRED_EXPIRY + ")...")
    j = _load_or_fetch(
        f"expired_{EXPIRED_EXPIRY}", ["expired_oct27"],
        "/expired-instruments/option/contract",
        params={"instrument_key": IDX, "expiry_date": EXPIRED_EXPIRY})
    exp_map = {(float(x["strike_price"]), x["instrument_type"]): x["instrument_key"]
               for x in (j.get("data", []) or [])}
    print(f"   {len(exp_map)} करार")

    print("▶ लाइव्ह instrument master (expiry " + LIVE_EXPIRY + ")...")
    fn = os.path.join(CACHE, "fo_master.json.gz")
    if not os.path.exists(fn):
        if not TOKEN:
            raise SystemExit("❌ fo_master कॅशमध्ये नाही आणि टोकन नाही — VM वर चालवा.")
        r = requests.get("https://assets.upstox.com/market-quote/instruments/"
                         "exchange/complete.json.gz", timeout=120)
        open(fn, "wb").write(r.content)
    live_map = {}
    with gzip.open(fn, "rt", encoding="utf-8") as f:
        rows = json.load(f)
    if isinstance(rows, dict):
        rows = rows.get("data", []) or []
    for row in rows:
        sym = (row.get("trading_symbol") or row.get("tradingsymbol") or "")
        if "BANKNIFTY" not in sym:
            continue
        try:
            exp = datetime.fromtimestamp(row["expiry"] / 1000.0,
                                         tz=timezone.utc)
        except Exception:
            continue
        if exp.strftime("%Y-%m-%d") != LIVE_EXPIRY:
            continue
        if row.get("instrument_type") not in ("CE", "PE"):
            continue
        live_map[(float(row["strike_price"]), row["instrument_type"])] = \
            row["instrument_key"]
    print(f"   {len(live_map)} लाइव्ह करार")
    return idx, dc, exp_map, live_map


# ---------------------------------------------------------------
# OR + सिग्नल (प्रयोग-क्नॉब्ससह)
# ---------------------------------------------------------------
def or_range(cs, start, end):
    a, b = dtime(*map(int, start.split(":"))), dtime(*map(int, end.split(":")))
    win = [c for c in cs if a <= c["ts"].time() < b]
    if len(win) < 3:
        return None
    return {"high": max(c["h"] for c in win),
            "low": min(c["l"] for c in win), "n": len(win)}


def analyze_ex(cs, spot, now, prev_close, orb_start, orb_end,
               buffer_pct=0.0, bias_dir=0):
    orb = or_range(cs, orb_start, orb_end)
    if not orb:
        return None
    width = orb["high"] - orb["low"]
    width_pct = width / spot * 100.0
    if width_pct < C.MIN_OR_WIDTH_PCT:
        return {"blocked": f"OR रेंज खूप छोटी ({width_pct:.2f}%)"}
    if width_pct > C.MAX_OR_WIDTH_PCT:
        return {"blocked": f"OR रेंज खूप मोठी ({width_pct:.2f}%)"}
    if prev_close and prev_close > 0:
        gap = abs(cs[0]["o"] - prev_close) / prev_close * 100.0
        if gap > C.MAX_GAP_PCT:
            return {"blocked": f"गॅप {gap:.2f}%"}

    last = S.last_completed_5m(cs, now, orb_end)
    if not last:
        return None

    buf = spot * buffer_pct / 100.0
    CE = {"side": "CE", "or_high": orb["high"], "or_low": orb["low"],
          "breakout": last["c"], "candle_ts": last["ts"].isoformat()}
    PE = {"side": "PE", "or_high": orb["high"], "or_low": orb["low"],
          "breakout": last["c"], "candle_ts": last["ts"].isoformat()}

    if bias_dir > 0:                      # आदला दिवस वरचा → CE सोपे, PE कठीण
        if last["c"] < orb["low"] - width * 0.5:
            return PE
        if last["c"] > orb["high"] + buf:
            return CE
    elif bias_dir < 0:                    # आदला दिवस खालचा → PE सोपे, CE कठीण
        if last["c"] > orb["high"] + width * 0.5:
            return CE
        if last["c"] < orb["low"] - buf:
            return PE
    else:
        if last["c"] > orb["high"] + buf:
            return CE
        if last["c"] < orb["low"] - buf:
            return PE
    return None


# ---------------------------------------------------------------
# TP-लॅडर सिम्युलेशन (आजच्या लाइव्ह नियमांप्रमाणे)
# ---------------------------------------------------------------
LOT = C.LOT_SIZE
CAP = C.CAPITAL
SQ = dtime(*map(int, C.SQUARE_OFF.split(":")))
ENT_END = dtime(*map(int, C.ENTRY_END.split(":")))


def _mk_trade(ds, side, strike, entry, legs, reason, ets, xts):
    buy_val = entry * LOT
    chg = CHG.option_charges_ladder(buy_val, legs)["total"]
    gross = sum((p - entry) * q for (p, q) in legs)
    return {"date": ds, "side": side, "strike": strike, "entry": entry,
            "exit": legs[-1][0] if legs else entry, "gross": round(gross, 2),
            "charges": round(chg, 2), "pnl": round(gross - chg, 2),
            "reason": reason,
            "entry_ts": ets.strftime("%H:%M"), "exit_ts": xts.strftime("%H:%M")}


def run_day(cs, optmap_get, ds, prev_close, prev_mid,
            orb_start, orb_end, buffer_pct=0.0, rearm=False, bias_dir=0):
    """एक दिवस → (trades, blocked_note, fetch_fail_count)"""
    orb = or_range(cs, orb_start, orb_end)
    out, note, fails, skips = [], None, 0, 0
    if not orb:
        return out, note, fails, skips
    mid = (orb["high"] + orb["low"]) / 2.0

    end_t = dtime(*map(int, orb_end.split(":")))
    groups = {}
    for c in cs:
        if c["ts"].time() < end_t:
            continue
        k = c["ts"].replace(minute=(c["ts"].minute // 5) * 5, second=0, microsecond=0)
        g = groups.setdefault(k, {"ts": k, "o": c["o"], "h": c["h"],
                                  "l": c["l"], "c": c["c"]})
        g["h"] = max(g["h"], c["h"]); g["l"] = min(g["l"], c["l"]); g["c"] = c["c"]
    fivem = sorted(groups.values(), key=lambda g: g["ts"])

    day_pnl, halted, acted = 0.0, False, set()
    need_mid = None                    # EXP2: "CE"/"PE" = ती दिशा mid-क्रॉसशिवाय ब्लॉक
    last_exit_dt = None

    for g in fivem:
        now = g["ts"] + timedelta(minutes=5)
        if now.time() > ENT_END:
            break
        if len(out) >= C.MAX_TRADES_PER_DAY or halted:
            break
        if g["ts"] in acted:
            continue
        if last_exit_dt and now <= last_exit_dt:
            continue

        # EXP2: बंद ट्रेडनंतर त्याच दिशेला mid-क्रॉस हवा
        if rearm and need_mid:
            if need_mid == "CE" and g["c"] < mid:
                need_mid = None
            elif need_mid == "PE" and g["c"] > mid:
                need_mid = None
            else:
                continue

        sig = analyze_ex(cs, g["c"], now, prev_close, orb_start, orb_end,
                         buffer_pct=buffer_pct, bias_dir=bias_dir)
        if sig is None:
            continue
        if "blocked" in sig:
            if note is None:
                note = sig["blocked"]
            acted.add(g["ts"])
            continue
        acted.add(g["ts"])

        strike = round(g["c"] / 100.0) * 100
        okey = optmap_get((float(strike), sig["side"]))
        if not okey:
            skips += 1
            out.append({"date": ds, "side": sig["side"], "strike": strike,
                        "skip": "करार सापडला नाही"})
            continue
        try:
            ocs = fetch_option_candles(okey, ds, strike, sig["side"])
        except AuthFail as e:
            fails += 1
            out.append({"date": ds, "side": sig["side"], "strike": strike,
                        "skip": f"fetch-fail ({str(e)[:40]})"})
            continue
        if not ocs:
            skips += 1
            out.append({"date": ds, "side": sig["side"], "strike": strike,
                        "skip": "ऑप्शन कॅन्डल्स नाहीत"})
            continue
        mmap = {c["ts"]: c for c in ocs}
        raw, ets = None, None
        for off in (4, 3, 5, 2, 6):
            c = mmap.get(g["ts"] + timedelta(minutes=off))
            if c:
                raw, ets = c["c"], c["ts"]
                break
        if raw is None:
            skips += 1
            out.append({"date": ds, "side": sig["side"], "strike": strike,
                        "skip": "एंट्री किंमत नाही"})
            continue

        entry = round(raw * (1 + C.SLIPPAGE), 2)
        if entry * LOT > CAP * 0.90:
            skips += 1
            out.append({"date": ds, "side": sig["side"], "strike": strike,
                        "skip": f"भांडवल अपुरे (₹{entry*LOT:,.0f})"})
            continue

        # लॅडर-स्तर (लाइव्ह प्रमाणे)
        tp1 = round(entry * (1 + C.TP1_PCT / 100.0), 2)
        tp2 = round(entry * (1 + C.TARGET_PCT / 100.0), 2)
        tp3 = round(entry * (1 + C.TP3_PCT / 100.0), 2)
        sl = round(entry * (1 - C.SL_PCT / 100.0), 2)
        n1 = LOT // 3
        legs, left, leg_no = [], LOT, 0
        trade = None

        for om in ocs:
            if om["ts"] <= ets:
                continue
            if om["ts"].time() >= SQ:
                p = round(om["o"] * (1 - C.SLIPPAGE), 2)
                legs.append((p, left))
                trade = _mk_trade(ds, sig["side"], strike, entry, legs,
                                  "वेळ एग्झिट (15:05)", ets, om["ts"])
                last_exit_dt = om["ts"]
                break
            # त्याच मिनिटात SL+TP दोन्ही → SL आधी (निराशावादी)
            if om["l"] <= sl:
                p = round(sl * (1 - C.SLIPPAGE), 2)
                if left > 0:
                    legs.append((p, left))
                reason = "स्टॉप लॉस" if sl < entry else "ट्रेल SL 🔒"
                trade = _mk_trade(ds, sig["side"], strike, entry, legs,
                                  reason, ets, om["ts"])
                last_exit_dt = om["ts"]
                break
            if leg_no == 0 and om["h"] >= tp1:
                legs.append((round(tp1 * (1 - C.SLIPPAGE), 2), n1))
                left -= n1; leg_no = 1
                sl = entry                                   # BE-lock
            elif leg_no == 1 and om["h"] >= tp2:
                legs.append((round(tp2 * (1 - C.SLIPPAGE), 2), n1))
                left -= n1; leg_no = 2
                sl = round(entry * 1.10, 2)                  # नफा-लॉक
            elif leg_no == 2 and om["h"] >= tp3:
                legs.append((round(tp3 * (1 - C.SLIPPAGE), 2), left))
                left = 0
                trade = _mk_trade(ds, sig["side"], strike, entry, legs,
                                  "TP3 ✅", ets, om["ts"])
                last_exit_dt = om["ts"]
                break
        if trade is None and ocs:                            # अपवाद: डेटा अपुरा
            om = ocs[-1]
            p = round(om["c"] * (1 - C.SLIPPAGE), 2)
            legs.append((p, left))
            trade = _mk_trade(ds, sig["side"], strike, entry, legs,
                              "डेटा समाप्त", ets, om["ts"])
            last_exit_dt = om["ts"]

        if trade:
            out.append(trade)
            day_pnl += trade["pnl"]
            if day_pnl <= -C.MAX_DAILY_LOSS:
                halted = True
            if rearm:
                need_mid = "CE" if sig["side"] == "CE" else "PE"
        else:
            if rearm:
                need_mid = None                              # skip — गार्ड रीसेट
    return out, note, fails, skips


# ---------------------------------------------------------------
# मुख्य
# ---------------------------------------------------------------
def main():
    frm = sys.argv[1] if len(sys.argv) > 1 else "2026-10-01"
    to = sys.argv[2] if len(sys.argv) > 2 else \
        (_date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    idx, dc, exp_map, live_map = load_data(frm, to)
    days = {}
    for c in idx:
        days.setdefault(c["ts"].date(), []).append(c)
    all_days = sorted(d for d in days if len(days[d]) >= 100)

    def both_maps(key):
        return exp_map.get(key) or live_map.get(key)

    variants = [
        ("BASE  (जिवंत नियम)", dict(orb_start="09:15", orb_end="09:30")),
        ("EXP1  बफर+0.10%", dict(orb_start="09:15", orb_end="09:30",
                                  buffer_pct=0.10)),
        ("EXP2  मिडलाइन-रिआर्म", dict(orb_start="09:15", orb_end="09:30",
                                       rearm=True)),
        ("EXP3  डेली-बायस", dict(orb_start="09:15", orb_end="09:30",
                                  bias=True)),
        ("EXP4a OR 5 मिनिटे", dict(orb_start="09:15", orb_end="09:20")),
        ("EXP4b OR 30 मिनिटे", dict(orb_start="09:15", orb_end="09:45")),
    ]

    results, all_trades = [], []
    for name, kw in variants:
        bias = kw.pop("bias", False)
        trs, blocks, fails, skips = [], 0, 0, 0
        for d in all_days:
            ds = d.strftime("%Y-%m-%d")
            if not (frm <= ds <= to):
                continue
            cs = days[d]
            prev_close, prev_mid = None, None
            for k in range(1, 8):
                pk = (d - timedelta(days=k))
                pds = pk.strftime("%Y-%m-%d")
                pcs = days.get(pk)
                if pcs and len(pcs) >= 100:
                    if prev_close is None and pds in dc:
                        prev_close = dc[pds]
                    pm = or_range(pcs, "09:15", "09:30")
                    if pm:
                        prev_mid = (pm["high"] + pm["low"]) / 2.0
                    break
            bdir = 0
            if bias and prev_mid:
                todays = or_range(cs, kw["orb_start"], kw["orb_end"])
                if todays:
                    tm = (todays["high"] + todays["low"]) / 2.0
                    bdir = 1 if tm > prev_mid else (-1 if tm < prev_mid else 0)
            day_trades, note, f, sk = run_day(
                cs, both_maps, ds, prev_close, prev_mid,
                kw["orb_start"], kw["orb_end"],
                buffer_pct=kw.get("buffer_pct", 0.0),
                rearm=kw.get("rearm", False), bias_dir=bdir)
            fails += f
            skips += sk
            trs.extend(x for x in day_trades if "pnl" in x)
            all_trades.extend((name, x) for x in day_trades if "pnl" in x)
            if note:
                blocks += 1
        kw["bias"] = bias
        wins = sum(1 for t in trs if t["pnl"] > 0)
        net = round(sum(t["pnl"] for t in trs), 2)
        gross = round(sum(t["gross"] for t in trs), 2)
        chg = round(sum(t["charges"] for t in trs), 2)
        eq, peak, mdd = 0.0, 0.0, 0.0
        for t in trs:
            eq += t["pnl"]
            peak = max(peak, eq)
            mdd = min(mdd, eq - peak)
        results.append({"name": name, "n": len(trs), "wins": wins,
                        "net": net, "gross": gross, "charges": chg,
                        "avg": round(net / len(trs), 0) if trs else 0,
                        "mdd": round(mdd, 0), "fails": fails,
                        "skips": skips, "blocks": blocks})

    print("\n" + "=" * 78)
    print(f"🧪 शनिवारीचे प्रयोग — BANKNIFTY ORB, {frm} → {to} "
          f"({len(all_days)} व्यापार-दिवस)")
    print("=" * 78)
    print(f"{'व्हेरिएंट':24s} {'ट्रेड':>5s} {'जिंक':>5s} {'ग्रॉस':>10s} "
          f"{'खर्च':>7s} {'निव्वल':>10s} {'सरासरी':>8s} {'मॅक्स-DD':>9s} {'skip':>5s}")
    print("-" * 78)
    for r in results:
        flag = " ⚠️ अपूर्ण" if r["fails"] else ""
        print(f"{r['name']:24s} {r['n']:5d} {r['wins']:5d} {r['gross']:10,.0f} "
              f"{r['charges']:7,.0f} {r['net']:10,.0f} {r['avg']:8,.0f} "
              f"{r['mdd']:9,.0f} {r['skips']:5d}{flag}")
    print("-" * 78)
    if any(r["fails"] for r in results):
        print("⚠️ fetch-fail आढळले (टोकन/नेटवर्क) — VM वर नवीन टोकनाने पुन्हा "
              "चालवा; आणलेला डेटा कॅश होतो, त्यामुळे पुढची धाव जलद.\n")
    base = results[0]
    print("📌 अवलंबण्याची अट = निव्वल BASE पेक्षा जास्त + जिंक-रेट घसरलेला नाही "
          "+ मॅक्स-DD बिघडलेले नाही.")
    for r in results[1:]:
        d = r["net"] - base["net"]
        verdict = "ठरवा" if (r["fails"] or r["skips"] > base["skips"] + 3) \
            else ("चालू ठेवा ✅" if d > 0 else "नाकारा")
        print(f"   {r['name']}: निव्वल BASE पेक्षा {d:+,.0f} ₹ → {verdict}")

    csvp = os.path.join(REPO, "experiments_result.csv")
    with open(csvp, "w") as f:
        f.write("व्हेरिएंट,तारीख,एंट्री,एग्झिट,स्ट्राइक,SIDE,ग्रॉस,खर्च,निव्वल,कारण\n")
        for name, t in all_trades:
            f.write(f"{name},{t['date']},{t['entry_ts']},{t['exit_ts']},"
                    f"{t['strike']:.0f},{t['side']},{t['gross']},{t['charges']},"
                    f"{t['pnl']},\"{t['reason']}\"\n")
    print(f"\n✓ CSV: {csvp}")


if __name__ == "__main__":
    main()
