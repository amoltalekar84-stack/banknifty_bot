#!/usr/bin/env python3
"""
mcx_diag.py — MCX ORB निदान (underlying-स्तर) — STRATEGY_ROADMAP टप्पा-2 चे
पहिले हत्यार. उद्देश: COPPER 0/4 तोटे (आणि इतर MCX) — खरे कारण डेटावरून:

  ① brk_buffer_pct grid (0 / 0.05 / 0.10 / 0.15 / 0.20) — कोणता बफर
     नकली-ब्रेक गाळतो, कोणता खरा-ब्रेक गाळतो?
  ② SL/TP barrier-grid — ऑप्शन-प्रीमियमवरचे −20%/+40% underlying वर किती
     हवे? (अरुंद SL = लवकर तोटे; रुंद SL = पोहोचता येईल का?)
  ③ OR-रुंदी बँड — जिंक-दिवस व तोटा-दिवसांची OR रुंदी वेगळी आहे का?
     (SILVER/GOLD चा पैटर्न इतरांत लागू करण्यासाठी)
  ④ एंट्री-तास व बाजू — कोणता तास / कोणती बाजू रक्तवाहू आहे?

प्रामाणिकपणा (महत्त्वाचे): बॉट MCX **ऑप्शन्स** खरेदी करते; हे निदान
**फ्यूचर्स (underlying) कॅन्डल्सवर** होते. ऑप्शन-प्रीमियमचे −20% SL /
+40% TP अंदाजे underlying-हालचालीत अनुवादून barrier सिम्युलेशन होते
(डीफॉल्ट SL 0.8% / TP 1.6% = प्रीमियम-लीव्हरेज ~25× चा अंदाज; env
MCXDIAG_SL_UD / MCXDIAG_TP_UD ने बदलता येते). म्हणून हे **सापेक्ष
तुलना-साधन** आहे (बफर-अ vs बफर-ब कोणते बेहत्तर) — परम रुपये-हमी नाही.
TP1-breakeven-लॉक live प्रमाणेच आहे (TP1 = TP/2 वर SL→entry).

Live-नियम-अंमल: OR 09:15–09:45, एंट्री 09:45–12:00, 5m-क्लोज ब्रेक + बफर,
OR-रुंदी फिल्टर (0.15–2.0%), गॅप 1%, दिवसाला कमाल 2 ट्रेड, तोटा-कूलडाउन
(quality.py: COPPER/CRUDE 45 मि, बाकी 30 मि), quality-प्रोब आदर (प्रोब
मोडमधले सिम्बॉल दिवसाला फक्त 1), 23:05 स्क्वेअर-ऑफ, 0.05% स्लिपेज.
दैनिक ₹-हॉल्ट ऑप्शन-स्तरावर असल्याने underlying-स्तरावर अनुवाद होत नाही —
तो live मध्ये तरी अबाधित आहे (env MCXDIAG_PROBE=0 → प्रोब-आदर बंद).

डेटा: Upstox 1-मिनिट कॅन्डल्स (V3, जुना V2 fallback) — फक्त शेवटचे ~1 महिना
मिळते; प्रत्येक (कॉन्ट्रॅक्ट,दिवस) <repo>/bt_cache_mcx/ मध्ये कॅश (env
BT_CACHE_MCX). टोकन: env UPSTOX_TOKEN, नाहितर bot.db (store) मधून.

चालवा (VM):  python3 mcx_diag.py [दिवस]        # उदा. python3 mcx_diag.py 30
निकाल:       कन्सोल-अहवाल + mcx_diag_result.csv (gitignored)
"""
import csv
import os
import sys
import time
from datetime import datetime, time as dtime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C       # noqa: E402
import quality           # noqa: E402
import store             # noqa: E402
from strategy import parse_candles   # noqa: E402
from upstox_api import (get_hist_candles, get_hist_candles_v3)  # noqa: E402
from config import ist_now   # noqa: E402

REPO = os.path.dirname(os.path.abspath(__file__))
CACHE = os.getenv("BT_CACHE_MCX", os.path.join(REPO, "bt_cache_mcx"))
os.makedirs(CACHE, exist_ok=True)

SLIP = C.SLIPPAGE


def _fenv(k, d):
    try:
        return float(os.getenv(k) or d)
    except (TypeError, ValueError):
        return d


# ---------------- निदान-गतीके ----------------
SL_UD = _fenv("MCXDIAG_SL_UD", 0.8)     # underlying-स्तरावर SL %
TP_UD = _fenv("MCXDIAG_TP_UD", 1.6)     # underlying-स्तरावर TP %
BUFFERS = (0.0, 0.05, 0.10, 0.15, 0.20)
BARRIER_SL = (0.6, 0.8, 1.0, 1.3, 1.6)
BARRIER_TP = (1.2, 1.6, 2.0, 2.4, 3.0)
PROBE_RESPECT = os.getenv("MCXDIAG_PROBE", "1") != "0"
MAX_DAYS = 45


# ---------------- डेटा ----------------
def get_token():
    tok = os.getenv("UPSTOX_TOKEN", "").strip()
    if tok:
        return tok
    try:
        return (store.get_state("upstox_token") or "").strip() or None
    except Exception:
        return None


def instr_key(S):
    """MCX फ्यूचर्स main-series की (engine प्रमाणेच) → None = आज नाही"""
    import engine
    try:
        dkey, _snap = engine._data_key(S, ist_now())
    except Exception:
        return None
    return dkey


def fetch_1m(token, key, ds):
    """एक दिवसाचे 1-मिनिट कॅन्डल (कॅशसह) → यादी किंवा []"""
    safe = "".join(ch if ch.isalnum() else "_" for ch in key)[-40:]
    fn = os.path.join(CACHE, "mcxd_{}_{}.json".format(safe, ds))
    if os.path.exists(fn):
        try:
            import json
            j = json.load(open(fn))
            return parse_candles(j.get("data", {}).get("candles", []) or [])
        except (ValueError, OSError):
            pass
    if not token:
        return []
    import json
    try:
        cs = parse_candles(get_hist_candles_v3(token, key, "minutes", "1",
                                               ds, ds))
        if len(cs) >= 20:
            _save_json(fn, {"data": {"candles":
                             [[c["ts"].isoformat(), c["o"], c["h"], c["l"],
                               c["c"]] for c in cs]}})
            return cs
        rows = get_hist_candles(token, key, "1minute", ds, ds)
        cs = parse_candles(rows or [])
        if cs:
            _save_json(fn, {"data": {"candles":
                             [[c["ts"].isoformat(), c["o"], c["h"], c["l"],
                               c["c"]] for c in cs]}})
        return cs
    except Exception:
        return []


def _save_json(fn, j):
    try:
        import json
        json.dump(j, open(fn, "w"))
    except OSError:
        pass


def day_closes(token, key, back, to):
    """दिवस-बंद किंमती {तारीख: close} — गॅप-फिल्टरसाठी"""
    try:
        rows = get_hist_candles(token, key, "day", to, back)
    except Exception:
        return {}
    out = {}
    for r in rows or []:
        try:
            out[r[0][:10]] = float(r[4])
        except (ValueError, TypeError, IndexError):
            continue
    return out


def to_5m(cs):
    """1-मिनिट → 5-मिनिट बार (backtest प्रमाणेच)"""
    g = {}
    for c in cs:
        k = c["ts"].replace(minute=(c["ts"].minute // 5) * 5,
                            second=0, microsecond=0)
        b = g.get(k)
        if b is None:
            g[k] = {"ts": k, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"]}
        else:
            b["h"] = max(b["h"], c["h"])
            b["l"] = min(b["l"], c["l"])
            b["c"] = c["c"]
    return [g[k] for k in sorted(g)]


# ---------------- एक दिवसाचे सिम्युलेशन ----------------
def _t(s):
    return dtime(*[int(x) for x in s.split(":")])


def sim_day(cs1, ctx):
    """एक दिवस → (trades[], blocked_note किंवा None). ctx = dict:
    S, ds, prev_close, buf, sl_ud, tp_ud, cap, cd_min"""
    S = ctx["S"]
    buf, sl_ud, tp_ud = ctx["buf"], ctx["sl_ud"], ctx["tp_ud"]
    cap, cd_min = ctx["cap"], ctx["cd_min"]
    orb_s, orb_e = _t(S["orb_start"]), _t(S["orb_end"])
    ent_s, ent_e = _t(S["entry_start"]), _t(S["entry_end"])
    sq_t = _t(S["square_off"])

    cs = sorted(cs1, key=lambda c: c["ts"])
    five = to_5m(cs)
    if len(five) < 8:
        return [], "डेटा अपुरा"

    orbars = [b for b in five if orb_s <= b["ts"].time() < orb_e]
    if len(orbars) < 3:
        return [], "OR डेटा अपुरा"
    or_high = max(b["h"] for b in orbars)
    or_low = min(b["l"] for b in orbars)

    spot0 = five[0]["o"]
    width_pct = (or_high - or_low) / spot0 * 100.0
    if width_pct < C.MIN_OR_WIDTH_PCT:
        return [], "OR रेंज छोटी ({:.2f}%)".format(width_pct)
    if width_pct > C.MAX_OR_WIDTH_PCT:
        return [], "OR रेंज मोठी ({:.2f}%)".format(width_pct)
    if ctx.get("prev_close") and ctx["prev_close"] > 0:
        gap = abs(spot0 - ctx["prev_close"]) / ctx["prev_close"] * 100.0
        if gap > C.MAX_GAP_PCT:
            return [], "गॅप {:.2f}%".format(gap)

    mmap = {c["ts"]: c for c in cs}
    times = sorted(mmap)
    trades, acted = [], set()
    last_exit_dt = None
    last_loss_dt = None

    for b in five:
        comp = b["ts"] + timedelta(minutes=5)
        if comp.time() > ent_e:
            break
        if comp.time() < ent_s:
            continue
        if last_exit_dt and comp <= last_exit_dt:
            continue
        if b["ts"] in acted:
            continue
        if len(trades) >= cap:
            break

        # तोटा-कूलडाउन (quality.py प्रमाणेच: 0 <= d < cd)
        if last_loss_dt is not None and cd_min > 0:
            d = (comp - last_loss_dt).total_seconds() / 60.0
            if 0 <= d < cd_min:
                acted.add(b["ts"])
                continue

        c = b["c"]
        bufp = (c * buf / 100.0) if (buf and c) else 0.0
        if c > or_high + bufp:
            side, dirn = "CE", 1
        elif c < or_low - bufp:
            side, dirn = "PE", -1
        else:
            continue

        # एंट्री = सिग्नल-कॅन्डल संपल्यावरच्या मिनिटाची open (± 1 मि)
        ets, entry = None, None
        for off in (0, 1, 2):
            cand = comp + timedelta(minutes=off)
            m = mmap.get(cand)
            if m:
                ets, entry = m["ts"], m["o"] * (1 + SLIP)
                break
        if entry is None:
            acted.add(b["ts"])
            continue
        acted.add(b["ts"])

        if dirn > 0:
            sl = entry * (1 - sl_ud / 100.0)      # CE: SL खाली
            tp = entry * (1 + tp_ud / 100.0)
            tp1 = entry * (1 + tp_ud / 200.0)     # live: TP1 = TP चा अर्धा %
        else:
            sl = entry * (1 + sl_ud / 100.0)      # PE: SL वर
            tp = entry * (1 - tp_ud / 100.0)
            tp1 = entry * (1 - tp_ud / 200.0)
        locked = False
        exitp, xts, reason = None, None, None

        for ts in times:
            if ts <= ets:
                continue
            m = mmap[ts]
            if m["ts"].time() >= sq_t:
                exitp = m["o"] * (1 - SLIP) if dirn > 0 \
                    else m["o"] * (1 + SLIP)
                xts, reason = ts, "वेळ एग्झिट"
                break
            lo_x = m["l"] if dirn > 0 else m["h"]
            hi_x = m["h"] if dirn > 0 else m["l"]
            # SL आधी (निराशावादी — त्याच मिनिटात TP असले तरी)
            if (lo_x - sl) * dirn <= 0:
                exitp = sl * (1 - SLIP) if dirn > 0 else sl * (1 + SLIP)
                xts = ts
                reason = "ट्रेल SL 🔒" if locked else "स्टॉप लॉस"
                break
            if (hi_x - tp) * dirn >= 0:
                exitp = tp * (1 - SLIP) if dirn > 0 else tp * (1 + SLIP)
                xts, reason = ts, "TP पूर्ण"
                break
            if not locked and (hi_x - tp1) * dirn >= 0:
                locked = True
                sl = entry
        if exitp is None and cs:
            m = cs[-1]
            exitp = m["c"] * (1 - SLIP) if dirn > 0 else m["c"] * (1 + SLIP)
            xts, reason = m["ts"], "डेटा समाप्त"

        r0 = entry * sl_ud / 100.0
        r = dirn * (exitp - entry) / r0
        trades.append({"date": ctx["ds"], "side": side,
                       "entry_ts": ets.strftime("%H:%M"),
                       "exit_ts": xts.strftime("%H:%M"),
                       "entry": round(entry, 2), "exit": round(exitp, 2),
                       "reason": reason, "R": round(r, 3),
                       "u_pnl": round(dirn * (exitp - entry) * S["lot"], 0),
                       "lot": S["lot"]})
        last_exit_dt = xts
        if r < -1e-9:
            last_loss_dt = xts
    return trades, None


# ---------------- आकडे ----------------
def summarize(trades):
    n = len(trades)
    wins = [t for t in trades if t["R"] > 0]
    losses = [t for t in trades if t["R"] < 0]
    gw = sum(t["R"] for t in wins)
    gl = abs(sum(t["R"] for t in losses))
    cum = peak = mdd = 0.0
    for t in trades:
        cum += t["R"]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return {"n": n, "wins": len(wins), "losses": len(losses),
            "wr": (len(wins) * 100.0 / n) if n else 0.0,
            "net": round(sum(t["R"] for t in trades), 2),
            "pf": round(gw / gl, 2) if gl > 0 else (9.99 if gw > 0 else 0.0),
            "avg_w": round(gw / len(wins), 2) if wins else 0.0,
            "avg_l": round(gl / len(losses), 2) if losses else 0.0,
            "mdd": round(mdd, 2)}


def or_widths(cs_by_day, S):
    """प्रत्येक दिवसाची OR-रुंदी % → यादी (वाढत्या क्रमाने)"""
    out = []
    orb_s, orb_e = _t(S["orb_start"]), _t(S["orb_end"])
    for ds, cs1 in sorted(cs_by_day.items()):
        five = to_5m(cs1)
        orbars = [b for b in five if orb_s <= b["ts"].time() < orb_e]
        if len(orbars) < 3:
            continue
        hi = max(b["h"] for b in orbars)
        lo = min(b["l"] for b in orbars)
        if five:
            out.append((hi - lo) / five[0]["o"] * 100.0)
    return sorted(out)


def hour_bucket(hhmm):
    h, m = hhmm.split(":")
    mins = int(h) * 60 + int(m)
    if mins < 10 * 60 + 15:
        return "09:45–10:15"
    if mins < 11 * 60:
        return "10:15–11:00"
    return "11:00–12:00"


def entry_quality(ctx_by_day, S, buf, sl_ud, tp_ud, cap, cd_min):
    """सर्व दिवस एकत्र सिम्युलेट → trades यादी"""
    out = []
    for ds in sorted(ctx_by_day):
        ctx = dict(ctx_by_day[ds])
        ctx.update({"buf": buf, "sl_ud": sl_ud, "tp_ud": tp_ud,
                    "cap": cap, "cd_min": cd_min})
        trs, _why = sim_day(ctx_by_day[ds]["cs1"], ctx)
        out.extend(trs)
    return out


def recommend(rows, base):
    """buffer-grid rows मधून शिफारस — n लहान असेल तर निष्कर्ष नाही"""
    best, bn = None, 8
    for r in rows:
        if abs(r["buf"] - 0.0) < 1e-9:
            continue
        if r["n"] < bn:
            continue
        if r["net"] > base["net"] and r["pf"] > base["pf"]:
            if best is None or r["net"] > best["net"]:
                best = r
    return best


# ---------------- अहवाल ----------------
def _row_line(r):
    return ("  बफर {:>4.2f}%  n={:<3d} जिंक={:<3d} WR={:>5.1f}% "
            "netR={:>7.2f} PF={:>5.2f} avgW={:>5.2f} avgL={:>5.2f} "
            "maxDD={:>6.2f}R".format(r["buf"], r["n"], r["wins"], r["wr"],
                                     r["net"], r["pf"], r["avg_w"],
                                     r["avg_l"], r["mdd"]))


def effective_cap(S, respect=True):
    """आजची सिम्युलेशन-कॅप → (कॅप, मोड). प्रोब=1, बेंच=0, नाहितर config"""
    cap = S.get("max_trades", 2)
    if not respect:
        return cap, "NORMAL"
    try:
        mode, _n, _wr = quality.quality_state(S["key"])
    except Exception:
        return cap, "NORMAL"
    if mode == "PROBE":
        return 1, mode
    if mode == "BENCH":
        return 0, mode
    return cap, mode


def diag_symbol(S, token, days, csv_rows):
    """एक सिम्बॉल → अहवाल-ओळी (यादी)"""
    L = []
    key = S["key"]
    dk = instr_key(S)
    if not dk:
        return ["\n== {} — कॉन्ट्रॅक्ट नाही, वगळले ==".format(S["label"])], []
    end = ist_now().date()
    start = end - timedelta(days=int(days))
    back = start - timedelta(days=10)
    prev_map = day_closes(token, dk, back.isoformat(),
                          (end - timedelta(days=1)).isoformat())
    cs_by_day, no_data = {}, 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            ds = d.isoformat()
            cs1 = fetch_1m(token, dk, ds)
            if len(cs1) >= 20:
                cs_by_day[ds] = cs1
            else:
                no_data += 1
            time.sleep(0.25)
        d += timedelta(days=1)

    cd_min = quality._cooldown_min(key)
    cap, mode = effective_cap(S, PROBE_RESPECT)

    ctx_by_day = {}
    for ds, cs1 in cs_by_day.items():
        pc = None
        cands = [k for k in prev_map if k < ds]
        if cands:
            pc = prev_map[max(cands)]
        ctx_by_day[ds] = {"cs1": cs1, "ds": ds, "prev_close": pc, "S": S}

    L.append("\n== {} ({} | {} दिवस डेटा, {} नाही | कूलडाउन {} मि | "
             "कॅप {} [{}]) ==".format(S["label"], dk, len(cs_by_day),
                                      no_data, cd_min, cap, mode))

    # ① buffer-grid (डीफॉल्ट barriers)
    rows = []
    for buf in BUFFERS:
        trs = entry_quality(ctx_by_day, S, buf, SL_UD, TP_UD, cap, cd_min)
        st = summarize(trs)
        st["buf"] = buf
        rows.append(st)
        for t in trs:
            csv_rows.append(dict(t, symbol=key, grid="buf{:.2f}".format(buf)))
    base = rows[0]
    L.append("① बफर-ग्रिड (SL {:.2f}% / TP {:.2f}%):".format(SL_UD, TP_UD))
    for r in rows:
        L.append(_row_line(r))
    rec = recommend(rows, base)
    if rec:
        L.append("  👉 शिफारस: brk_buffer_pct = {:.2f} (netR {} vs बफर-0 "
                 "{}; PF {} vs {})".format(rec["buf"], rec["net"], base["net"],
                                           rec["pf"], base["pf"]))
    else:
        L.append("  👉 शिफारस: 0.0 — बदलायला पुरेसा डेटा नाही (किमान 8 सिग्नल)")

    # ② barrier-grid (बफर 0)
    L.append("② SL/TP-ग्रिड (बफर 0) — फक्त PF वाढणाऱ्या पंक्ती:")
    brows = []
    for sl_ud in BARRIER_SL:
        for tp_ud in BARRIER_TP:
            trs = entry_quality(ctx_by_day, S, 0.0, sl_ud, tp_ud, cap, cd_min)
            st = summarize(trs)
            st["sl_ud"], st["tp_ud"] = sl_ud, tp_ud
            brows.append(st)
            for t in trs:
                csv_rows.append(dict(t, symbol=key,
                                     grid="SL{:.1f}/TP{:.1f}".format(sl_ud,
                                                                     tp_ud)))
    d0 = (SL_UD, TP_UD, summarize(entry_quality(ctx_by_day, S, 0.0,
                                                SL_UD, TP_UD, cap, cd_min)))
    shown = 0
    for st in sorted(brows, key=lambda x: (-x["pf"], -x["net"])):
        if shown >= 5:
            break
        if (st["sl_ud"], st["tp_ud"]) == (d0[0], d0[1]):
            continue
        if st["pf"] > d0[2]["pf"] and st["n"] >= 8:
            L.append("  SL {:.1f}% / TP {:.1f}% → n={} WR={:.0f}% "
                     "netR={:+.2f} PF={:.2f}".format(
                         st["sl_ud"], st["tp_ud"], st["n"], st["wr"],
                         st["net"], st["pf"]))
            shown += 1
    if not shown:
        L.append("  (डीफॉल्ट SL {:.1f}/TP {:.1f} पेक्षा बेहत्तर काही नाही — "
                 "किंवा n लहान)".format(SL_UD, TP_UD))

    # ③ OR-रुंदी बँड
    ws = or_widths(cs_by_day, S)
    if ws:
        k = len(ws)
        p25, p50, p75 = ws[k // 4], ws[k // 2], ws[(3 * k) // 4]
        trs0 = entry_quality(ctx_by_day, S, 0.0, SL_UD, TP_UD, cap, cd_min)
        wmap = {}
        orb_s, orb_e = _t(S["orb_start"]), _t(S["orb_end"])
        for ds, cs1 in cs_by_day.items():
            five = to_5m(cs1)
            orbars = [b for b in five if orb_s <= b["ts"].time() < orb_e]
            if len(orbars) >= 3 and five:
                wmap[ds] = (max(b["h"] for b in orbars)
                            - min(b["l"] for b in orbars)) / five[0]["o"] * 100
        wwin = [wmap[t["date"]] for t in trs0 if t["R"] > 0 and t["date"] in wmap]
        wloss = [wmap[t["date"]] for t in trs0 if t["R"] < 0
                 and t["date"] in wmap]
        mwin = sum(wwin) / len(wwin) if wwin else 0.0
        mloss = sum(wloss) / len(wloss) if wloss else 0.0
        L.append("③ OR-रुंदी: p25={:.2f}% p50={:.2f}% p75={:.2f}% | "
                 "जिंक-सरास {:.2f}% vs तोटा-सरास {:.2f}% {}".format(
                     p25, p50, p75, mwin, mloss,
                     "(जिंक-दिवस रुंद!" if mwin > mloss * 1.25 else
                     "(तोटा-दिवस रुंद!" if mloss > mwin * 1.25 else "सारखी"))

    # ④ तास/बाजू
    trs0 = entry_quality(ctx_by_day, S, 0.0, SL_UD, TP_UD, cap, cd_min)
    buckets, sides = {}, {"CE": [], "PE": []}
    for t in trs0:
        buckets.setdefault(hour_bucket(t["entry_ts"]), []).append(t)
        sides[t["side"]].append(t)
    L.append("④ तास/बाजू (बफर 0):")
    for bk in sorted(buckets):
        st = summarize(buckets[bk])
        L.append("  {} → n={} WR={:.0f}% netR={:+.2f}".format(
            bk, st["n"], st["wr"], st["net"]))
    for sd in ("CE", "PE"):
        st = summarize(sides[sd])
        if st["n"]:
            L.append("  {} → n={} WR={:.0f}% netR={:+.2f} PF={:.2f}".format(
                sd, st["n"], st["wr"], st["net"], st["pf"]))

    # शेवटचे ट्रेड (निदानासाठी)
    if trs0:
        L.append("  शेवटचे ट्रेड (बफर 0):")
        for t in trs0[-8:]:
            ic = "✅" if t["R"] > 0 else ("❌" if t["R"] < 0 else "⚪")
            L.append("  {} {} {} {}→{} R={:+.2f} ({})".format(
                ic, t["date"][5:], t["side"], t["entry_ts"], t["exit_ts"],
                t["R"], t["reason"]))
    return L, csv_rows


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    days = max(5, min(days, MAX_DAYS))
    token = get_token()
    csv_rows = []
    out = ["🧪 MCX ORB निदान — underlying-स्तर (mcx_diag)",
           "कालावधी: शेवटचे {} दिवस | SL {:.2f}% / TP {:.2f}% (env बदलता येते) "
           "| बफर-ग्रिड {} | प्रोब-आदर={}".format(
               days, SL_UD, TP_UD, ",".join("{:.2f}".format(b)
                                            for b in BUFFERS),
               PROBE_RESPECT),
           "⚠️ नोंद: हे सापेक्ष तुलना-साधन (बफर/SL/TP कोणते बेहत्तर) — "
           "ऑप्शन-प्रीमियम अंदाजे underlying-हालचालीत; परम रुपये-हमी नाही."]

    mcx = [S for S in C.SYMBOLS if S.get("mcx")]
    for S in mcx:
        try:
            L, csv_rows = diag_symbol(S, token, days, csv_rows)
        except Exception as e:
            L = ["\n== {} — त्रुटी: {!r} ==".format(S["label"], e)]
        out.extend(L)

    print("\n".join(out))
    if csv_rows:
        p = os.path.join(REPO, "mcx_diag_result.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["सिम्बॉल", "ग्रिड", "तारीख", "बाजू", "एंट्री",
                        "एग्झिट", "एंट्री-वेळ", "एग्झिट-वेळ", "R",
                        "underlying-₹", "कारण"])
            for t in csv_rows:
                w.writerow([t.get("symbol"), t.get("grid"), t["date"],
                            t["side"], t["entry"], t["exit"], t["entry_ts"],
                            t["exit_ts"], t["R"], t["u_pnl"], t["reason"]])
        print("\n✓ CSV: {} ({} ओळी)".format(p, len(csv_rows)))
    else:
        print("\n⚠️ एकही ट्रेड नाही — टोकन/डेटा तपासा (candlecheck प्रमाणे)")


if __name__ == "__main__":
    main()
