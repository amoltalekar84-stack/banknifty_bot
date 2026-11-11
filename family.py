"""
👨‍👩‍👧 Low Capital Family — कमी-भांडवल शोध-कुटुंब (All Rounder चा 4था विभाग).
(ORB इंजिन + Swing अबाधित — स्वतंत्र थ्रेड, स्वतंत्र family_trades टेबल,
 स्वतंत्र वर्चुअल भांडवले; एकूण ₹15,000 — मुख्य भांडवलाला स्पर्श नाही)

मोटो (मालकाचा शब्द): "स्वस्त प्रीमियमचा स्ट्राइक शोधा, कमी भांडवल लावा,
पण जिंकणाऱ्या ट्रेडमध्ये खर्चानंतरचा निव्वल P&L हमीभर पॉझिटिव्ह असावा."

कुटुंबाचे 4 सदस्य — सारखाच मोटो, वेगळी स्ट्राइक-शोध पद्धत:
  F1 🪙 Sasta King   — chain मधला absolute सर्वात स्वस्त (दूर OTM)
  F2 🎯 Delta Filter — सर्वात स्वस्त ज्याचा |delta| ≥ 0.30 (sweet spot;
                        ग्रीक्स नसतील तर ATM±1 fallback)
  F3 📏 Distance Rule— ATM पासून नेमका 2 रा स्ट्राइक OTM
  F4 ⚙️ MCX Mini     — GOLDM mini-ऑप्शन्स: ATM±4 मधला सर्वात स्वस्त

🔒 Net Profit Gate (प्रत्येक एंट्रीआधी, गणित अचूक):
  • टार्गेट (+55%) वर निव्वल = (target−entry)×qty − सर्व खर्च ≥ ₹150
    (खर्च = ₹20×2 ब्रोकरेज + STT/CTT + एक्सचेंज + GST + स्टॅम्प — charges.py)
  • breakeven move ≤ 25% (बायनरी-सर्च: निव्वल-शून्य एग्झिट किंमत)
  • प्रीमियम ≥ ₹8 (मृत/अप्रवाही कोट टाळा) • गुंतवणूक ≤ 90% सदस्य-भांडवल

एकूण नियम: ORB सिग्नल (मुख्य इंजिनप्रमाणेच) दिशा ठरवतो; F1–F3 = BANKNIFTY
वीकली चेन (एकच चेन-कॉल शेअर), F4 = GOLDM फ्यूचर्स ORB (9:15–9:45).
एग्झिट: SL −35% | टार्गेट +55% (पूर्ण बुकिंग) | वेळ-एग्झिट (BN 15:05 / MCX 23:05)
| KILL. प्रति सदस्य: दिवसाला ≤ 2 ट्रेड, बरोबर 1 स्थिती, दैनिक तोटा-कवाड.
"""

import os
import threading
import time
import traceback
from datetime import time as dtime

import cards
import charges
import store
from config import SLIPPAGE, ist_now
from instruments import mcx_snapshot
from strategy import analyze, parse_candles
from upstox_api import (UpstoxError, chain_lot, get_ltp, get_market_status,
                        get_option_chain, get_today_candles)

_started = False
_lock = threading.Lock()

BN_INDEX_KEY = "NSE_INDEX|Nifty Bank"

# ------------------------------------------------------------------
# सदस्य — प्रत्येकी स्वतंत्र वर्चुअल भांडवल (env ने बदलता येते)
# ------------------------------------------------------------------
MEMBERS = [
    {"key": "F1", "name": "🪙 Sasta King", "seg": "NSE",
     "filter": "cheapest", "style": "chain-madhla sarvasta sasta (door OTM)",
     "capital": float(os.getenv("FAM_CAPITAL_F1", "2000")),
     "max_daily_loss": float(os.getenv("FAM_LOSSCAP_F1", "1000"))},
    {"key": "F2", "name": "🎯 Delta Filter", "seg": "NSE",
     "filter": "delta", "style": "sasta pan |delta|>=0.30 (sweet spot)",
     "capital": float(os.getenv("FAM_CAPITAL_F2", "4000")),
     "max_daily_loss": float(os.getenv("FAM_LOSSCAP_F2", "2000"))},
    {"key": "F3", "name": "📏 Distance Rule", "seg": "NSE",
     "filter": "distance", "style": "ATM pasun nakt 2ra strike OTM",
     "capital": float(os.getenv("FAM_CAPITAL_F3", "6000")),
     "max_daily_loss": float(os.getenv("FAM_LOSSCAP_F3", "3000"))},
    {"key": "F4", "name": "⚙️ MCX Mini", "seg": "MCX",
     "filter": "mcx", "style": "GOLDM mini-options ATM±4 sarvasta sasta",
     "capital": float(os.getenv("FAM_CAPITAL_F4", "3000")),
     "max_daily_loss": float(os.getenv("FAM_LOSSCAP_F4", "1500"))},
]
_BY_KEY = {m["key"]: m for m in MEMBERS}
BN_MEMBERS = ("F1", "F2", "F3")

# ------------------------------------------------------------------
# पॅरामीटर्स (env ने बदलता येतात)
# ------------------------------------------------------------------
ENABLED = os.getenv("ENABLE_FAMILY", "YES").strip().upper() != "NO"
TARGET_PCT = float(os.getenv("FAM_TARGET_PCT", "55"))     # +55% → पूर्ण बुकिंग
SL_PCT = float(os.getenv("FAM_SL_PCT", "35"))             # SL = −35%
NET_MIN = float(os.getenv("FAM_NET_MIN", "150"))          # टार्गेटवर किमान निव्वल ₹
BE_MOVE_MAX = float(os.getenv("FAM_BE_MOVE_MAX", "25"))   # breakeven move ≤ %
PREMIUM_MIN = float(os.getenv("FAM_PREMIUM_MIN", "8"))    # मृत कोट टाळा
DELTA_MIN = float(os.getenv("FAM_DELTA_MIN", "0.30"))
DIST_OTM = int(os.getenv("FAM_DIST_OTM", "2"))
MAX_TRADES = int(os.getenv("FAM_MAX_TRADES", "2"))        # प्रति सदस्य/दिवस
ENTRY_START = os.getenv("FAM_ENTRY_START", "09:35")
ENTRY_END = os.getenv("FAM_ENTRY_END", "12:00")
BN_SQ_OFF = os.getenv("FAM_BN_SQ_OFF", "15:05")
MCX_SQ_OFF = os.getenv("FAM_MCX_SQ_OFF", "23:05")
F4_COMMODITY = "GOLDM"
F4_TS_PATTERN = r"^GOLDM\d"            # फक्त main mini series (GOLD/GOLDP वगळले)
F4_LOT_FALLBACK = 10                   # GOLDM ऑप्शन लॉट (फाईल देईल तर तोच)


def _t(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _capital(M):
    try:
        return float(store.get_state("fam_capital_" + M["key"]) or M["capital"])
    except (TypeError, ValueError):
        return M["capital"]


def _label(M):
    return M["name"] + " (" + M["key"] + ")"


# ------------------------------------------------------------------
# 🔒 Net Profit Gate — गणित (PAPER खर्च-मॉडेलशी तंतोतंत जुळणारे)
# ------------------------------------------------------------------
def _charges_for(entry, exit_, qty, mcx):
    """एक बाय + एक सेल = पूर्ण राउंड-ट्रिप खर्च (MCX असल्यास CTT/मॉडेल)"""
    if mcx:
        return charges.mcx_option_charges_ladder(
            entry * qty, [(exit_, qty)])["total"]
    return charges.option_charges_ladder(entry * qty, [(exit_, qty)])["total"]


def net_at_exit(entry, exit_, qty, mcx=False):
    """या एग्झिट-किंमतीवर निव्वल P&L (सर्व खर्च वजा)"""
    return round((exit_ - entry) * qty - _charges_for(entry, exit_, qty, mcx), 2)


def breakeven_exit(entry, qty, mcx=False):
    """निव्वल-शून्य एग्झिट किंमत (बायनरी-सर्च; खर्च किंमतीवर अवलंबून म्हणून सर्च)"""
    lo, hi = entry, entry * 3.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if net_at_exit(entry, mid, qty, mcx) < 0:
            lo = mid
        else:
            hi = mid
    return hi


def gate_check(entry, qty, mcx=False):
    """🔒 Net Profit Gate → (पास, टिप, be_move_pct).
    नियम: टार्गेटवर निव्वल ≥ NET_MIN • breakeven move ≤ BE_MOVE_MAX"""
    target = entry * (1 + TARGET_PCT / 100.0)
    net_t = net_at_exit(entry, target, qty, mcx)
    if net_t < NET_MIN:
        return False, ("गेट अडला: टार्गेटवर निव्वल फक्त ₹{:.0f} (<₹{:.0f})"
                       .format(net_t, NET_MIN)), None
    be = breakeven_exit(entry, qty, mcx)
    be_pct = (be / entry - 1.0) * 100.0
    if be_pct > BE_MOVE_MAX:
        return False, ("गेट अडला: breakeven move +{:.1f}% (>{:.0f}%)"
                       .format(be_pct, BE_MOVE_MAX)), round(be_pct, 1)
    note = ("गेट पास: टार्गेटवर निव्वल ₹{:.0f} (>=₹{:.0f}) • "
            "breakeven +{:.1f}%".format(net_t, NET_MIN, be_pct))
    return True, note, round(be_pct, 1)


# ------------------------------------------------------------------
# चेन-ओळी → सदस्यांचे स्ट्राइक-शोध
# ------------------------------------------------------------------
def side_rows(chain, side):
    """जवळच्या expiry-च्या चेनमधून या बाजूच्या ऑप्शन-ओळी → क्रमवार स्ट्राइक.
    प्रत्येकी: {strike, ltp, delta, key, expiry} — डेटा नसलेल्या वगळल्या.
    🐛 दुरुस्ती: expiry आता प्रत्येक ओळीबरोबर येते (आधी गाळलं होतं,
    त्यामुळे _member_enter मध्ये KeyError('expiry') होऊन F1–F3 आज
    संपूर्ण दिवस एंट्री करू शकले नव्हते)."""
    out = []
    for r in chain or []:
        node = r.get("call_options") if side == "CE" else r.get("put_options")
        if not node:
            continue
        key = node.get("instrument_key")
        if not key:
            continue
        ltp = (node.get("market_data") or {}).get("ltp")
        try:
            ltp = float(ltp) if ltp not in (None, 0, "0") else None
        except (TypeError, ValueError):
            ltp = None
        if not ltp or ltp <= 0:
            continue
        g = node.get("option_greeks") or {}
        try:
            delta = float(g.get("delta")) if g.get("delta") is not None else None
        except (TypeError, ValueError):
            delta = None
        try:
            strike = float(r.get("strike_price") or 0)
        except (TypeError, ValueError):
            continue
        out.append({"strike": strike, "ltp": ltp, "delta": delta, "key": key,
                    "expiry": str(r.get("expiry") or r.get("expiry_date") or "")})
    out.sort(key=lambda x: x["strike"])
    return out


def _opt_of(M, row, qty):
    """सामान्य ऑप्शन-dict; गुंतवणूक-गार्ड पास झाला तरच"""
    if not row:
        return None
    entry = round(float(row["ltp"]) * (1 + SLIPPAGE), 2)
    if entry * qty > _capital(M) * 0.90:
        return None
    return {"key": row["key"], "strike": float(row["strike"]),
            "ltp": float(row["ltp"]), "lot": int(qty),
            "expiry": row.get("expiry") or ""}


def pick_cheapest(M, rows, qty):
    """F1 — सर्वात स्वस्त प्रीमियम (किमान PREMIUM_MIN; मृत कोट नाही)"""
    ok_rows = [r for r in rows if r["ltp"] >= PREMIUM_MIN]
    ok_rows.sort(key=lambda r: r["ltp"])
    return _opt_of(M, ok_rows[0] if ok_rows else None, qty)


def pick_delta(M, rows, spot, side, qty):
    """F2 — |delta| ≥ DELTA_MIN मधला सर्वात स्वस्त; ग्रीक्स नाहीत → ATM±1"""
    with_d = [r for r in rows if r["delta"] is not None and
              abs(r["delta"]) >= DELTA_MIN]
    if with_d:
        with_d.sort(key=lambda r: r["ltp"])
        return _opt_of(M, with_d[0], qty)
    # fallback: ATM च्या 1 पाऊल बाजूला (CE: वर, PE: खाली)
    near = sorted(rows, key=lambda r: abs(r["strike"] - spot))
    if not near:
        return None
    atm = near[0]["strike"]
    if side == "CE":
        ups = sorted([r for r in rows if r["strike"] > atm],
                     key=lambda r: r["strike"])
        return _opt_of(M, ups[0] if ups else None, qty)
    dns = sorted([r for r in rows if r["strike"] < atm],
                 key=lambda r: -r["strike"])
    return _opt_of(M, dns[0] if dns else None, qty)


def pick_distance(M, rows, spot, side, qty):
    """F3 — ATM पासून नेमका DIST_OTM रा स्ट्राइक OTM"""
    if not rows:
        return None
    atm = min(rows, key=lambda r: abs(r["strike"] - spot))["strike"]
    if side == "CE":
        ups = sorted([r for r in rows if r["strike"] > atm],
                     key=lambda r: r["strike"])
        want = ups[DIST_OTM - 1] if len(ups) >= DIST_OTM else None
    else:
        dns = sorted([r for r in rows if r["strike"] < atm],
                     key=lambda r: -r["strike"])
        want = dns[DIST_OTM - 1] if len(dns) >= DIST_OTM else None
    return _opt_of(M, want, qty)


def pick_mcx_mini(M, snap, token, spot, side, qty):
    """F4 — GOLDM स्नॅपशॉट: ATM±4 स्ट्राइक, सर्वात स्वस्त जो गेट पास करतो"""
    ks = sorted(snap.get("strikes", {}).keys(),
                key=lambda k: abs(float(k) - float(spot)))[:4]
    cands = []
    for k in ks:
        node = (snap["strikes"].get(str(k)) or snap["strikes"].get(int(k))
                or snap["strikes"].get(k))
        if not node:
            continue
        key = node.get(side)
        if not key:
            continue
        try:
            ltp = get_ltp(key, token)
        except UpstoxError:
            raise
        except Exception:
            ltp = None
        if not ltp or float(ltp) <= 0:
            continue
        cands.append({"strike": float(k), "ltp": float(ltp),
                      "delta": None, "key": key})
    cands.sort(key=lambda r: r["ltp"])
    return _opt_of(M, cands[0] if cands else None, qty)


# ------------------------------------------------------------------
# एंट्री
# ------------------------------------------------------------------
def _skip_once(date, member, reason):
    """एकाच कारण दिवसात एकदाच जर्नल/Telegram वर (आवाज-नियंत्रण)"""
    rk = "".join(ch for ch in str(reason)[:30] if ch.isalnum())
    k = "fam_skip_" + date + "_" + member + "_" + rk
    if store.get_state(k) == "1":
        return
    store.set_state(k, "1")
    store.log_event("👨‍👩‍👧 " + member + ": " + reason)


def _can_enter(M, date):
    """प्रति-सदस्य गार्ड्स: halt • बरोबर 1 स्थिती • दिवसाला ≤ MAX_TRADES"""
    if store.get_state("fam_halt_" + date + "_" + M["key"]) == "1":
        return False
    if store.family_open(M["key"]):
        return False
    closed = [t for t in store.family_today(date, M["key"])
              if t["status"] == "CLOSED"]
    return len(closed) < MAX_TRADES


def _member_enter(M, sig, spot, opt, now):
    """गेट + एंट्री + कार्ड → (tid, note) किंवा (None, कारण)"""
    from telegram_bot import notify
    date = now.strftime("%Y-%m-%d")
    qty = int(opt["lot"])
    entry = round(opt["ltp"] * (1 + SLIPPAGE), 2)
    ok, note, be_pct = gate_check(entry, qty, M["seg"] == "MCX")
    if not ok:
        return None, note
    sl = round(entry * (1 - SL_PCT / 100.0), 2)
    target = round(entry * (1 + TARGET_PCT / 100.0), 2)
    gate_note = note + " • प्रीमियम ₹{:.2f}".format(entry)
    exp = opt.get("expiry") or ""          # 🛡️ KeyError-प्रतिकारक
    tid = store.family_insert(
        date, M["key"], sig["side"], opt["key"], opt["strike"], exp,
        qty, entry, sl, target, round(entry * qty, 2), be_pct, gate_note,
        round(float(spot), 2), sig.get("side", ""),
        now.strftime("%H:%M:%S"))
    store.log_event("👨‍👩‍👧 Family ENTRY {} {} {:.0f}{} exp={} qty={} @₹{:.2f} "
                    "| {}".format(M["key"], sig["side"], opt["strike"],
                                  sig["side"], exp, qty, entry,
                                  note))
    chg = _charges_for(entry, target, qty, M["seg"] == "MCX")
    sl_cost = _charges_for(entry, sl, qty, M["seg"] == "MCX")
    net_t = net_at_exit(entry, target, qty, M["seg"] == "MCX")
    notify(
        "👨‍👩‍👧 <b>FAMILY ENTRY — {}</b> (PAPER)\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "• {:.0f} {} — expiry {}\n"
        "• प्रीमियम <b>₹{:.2f}</b> × {} = ₹{:,.0f} गुंतवणूक\n"
        "• स्पॉट ₹{:,.2f} • ORB {} सिग्नल (मुख्य इंजिनप्रमाणेच)\n"
        "• 🛑 SL ₹{:.2f} (−{:.0f}%) → कमाल तोटा −₹{:,.0f}\n"
        "• 🎯 टार्गेट ₹{:.2f} (+{:.0f}%) → निव्वल +₹{:,.0f} (खर्च ₹{:,.0f} वजा)\n"
        "• 🔓 breakeven +{:.1f}% — त्याआधी एग्झिट = तोटा\n"
        "• 💵 स्लीव्ह ₹{:,.0f} ({} पद्धत)".format(
            M["name"], opt["strike"], sig["side"], exp, entry, qty,
            entry * qty, spot, sig["side"], sl, SL_PCT,
            round((entry - sl) * qty + sl_cost),
            target, TARGET_PCT, net_t, chg, be_pct, _capital(M), M["style"]),
        html=True)
    return tid, note


def _bn_signal(token, now):
    """BANKNIFTY ORB सिग्नल (मुख्य इंजिनशी तंतोतंत तसेच) → (sig, spot)"""
    date = now.strftime("%Y-%m-%d")
    cs = parse_candles(get_today_candles(token, BN_INDEX_KEY, date))
    if len(cs) < 16:
        return None, None
    spot = get_ltp(BN_INDEX_KEY, token)
    if not spot or spot <= 0:
        return None, None
    sig = analyze(cs, spot, now, None,
                  orb_start="09:15", orb_end="09:30")
    return sig, spot


def _try_enter_bn(token, now):
    """F1–F3 — एकच कॅन्डल+चेन वापरून तिन्ही सदस्य स्वतंत्र निर्णय घेतात"""
    date = now.strftime("%Y-%m-%d")
    waiting = []
    for mk in BN_MEMBERS:
        M = _BY_KEY[mk]
        if not _can_enter(M, date):
            continue
        waiting.append(mk)
    if not waiting:
        return
    sig, spot = _bn_signal(token, now)
    if not sig or "blocked" in sig:
        return
    ts = sig["candle_ts"]
    waiting = [mk for mk in waiting
               if store.get_state("fam_acted_" + date + "_" + mk) != ts]
    if not waiting:
        return
    for mk in waiting:                     # या कॅन्डलवर एकदाच प्रयत्न
        store.set_state("fam_acted_" + date + "_" + mk, ts)
    try:
        chain = get_option_chain(token, BN_INDEX_KEY)
    except UpstoxError:
        raise
    except Exception as e:
        _skip_once(date, "F1-F3", "चेन नाही: " + repr(e)[:80])
        return
    lot = chain_lot(BN_INDEX_KEY) or 30
    for mk in waiting:
        M = _BY_KEY[mk]
        try:
            rows = side_rows(chain, sig["side"])
            if M["filter"] == "cheapest":
                opt = pick_cheapest(M, rows, lot)
            elif M["filter"] == "delta":
                opt = pick_delta(M, rows, spot, sig["side"], lot)
            else:
                opt = pick_distance(M, rows, spot, sig["side"], lot)
            if not opt:
                _skip_once(date, mk, M["name"] +
                           ": योग्य स्वस्त स्ट्राइक नाही (गुंतवणूक-गार्ड/प्रीमियम)")
                continue
            _member_enter(M, sig, spot, opt, now)
        except UpstoxError:
            raise
        except Exception as e:
            store.log_event("family enter[" + mk + "]: " + repr(e)[:150])


def _f4_signal(token, now):
    """GOLDM फ्यूचर्स ORB (MCX नियम 9:15–9:45) → (sig, spot, snap)"""
    date = now.strftime("%Y-%m-%d")
    snap = mcx_snapshot(F4_COMMODITY, ts_pattern=F4_TS_PATTERN)
    if not snap:
        return None, None, None
    cs = parse_candles(get_today_candles(token, snap["fut"]["key"], date))
    if len(cs) < 31:
        return None, None, snap
    spot = get_ltp(snap["fut"]["key"], token)
    if not spot or spot <= 0:
        return None, None, snap
    sig = analyze(cs, spot, now, None,
                  orb_start="09:15", orb_end="09:45")
    return sig, spot, snap


def _try_enter_f4(token, now):
    """F4 — GOLDM mini-ऑप्शन (MCX)"""
    date = now.strftime("%Y-%m-%d")
    M = _BY_KEY["F4"]
    if not _can_enter(M, date):
        return
    try:
        st = get_market_status(token, "MCX")
        if st == "NORMAL_CLOSE":
            return
    except Exception:
        pass
    sig, spot, snap = _f4_signal(token, now)
    if not sig or "blocked" in sig or not snap:
        return
    acted = "fam_acted_" + date + "_F4"
    if store.get_state(acted) == sig["candle_ts"]:
        return
    store.set_state(acted, sig["candle_ts"])
    try:
        qty = int(snap.get("opt_lot") or F4_LOT_FALLBACK)
        opt = pick_mcx_mini(M, snap, token, spot, sig["side"], qty)
        if not opt:
            _skip_once(date, "F4", M["name"] +
                       ": योग्य स्वस्त GOLDM स्ट्राइक नाही (गुंतवणूक-गार्ड)")
            return
        opt["expiry"] = snap["opt_expiry"]
        _member_enter(M, sig, spot, opt, now)
    except UpstoxError:
        raise
    except Exception as e:
        store.log_event("family enter[F4]: " + repr(e)[:150])


# ------------------------------------------------------------------
# एग्झिट + निरीक्षण
# ------------------------------------------------------------------
def _exit_position(p, ltp, reason, now):
    from telegram_bot import notify
    M = _BY_KEY.get(p["member"])
    if not M:
        return 0.0
    date = now.strftime("%Y-%m-%d")
    entry = float(p["entry"])
    qty = int(p["qty"])
    exitp = round(float(ltp) * (1 - SLIPPAGE), 2)
    chg = _charges_for(entry, exitp, qty, M["seg"] == "MCX")
    pnl = round((exitp - entry) * qty - chg, 2)
    when = now.strftime("%Y-%m-%d %H:%M:%S")
    store.family_close(p["id"], exitp, pnl, chg, reason, when)
    day = round(sum((t["pnl"] or 0) for t in store.family_today(date, M["key"])
                    if t["status"] == "CLOSED"), 2)
    halted = False
    if day <= -abs(M["max_daily_loss"]):
        store.set_state("fam_halt_" + date + "_" + M["key"], "1")
        halted = True
    store.log_event("👨‍👩‍👧 Family EXIT {} {} {:.0f}{} {}: ₹{:,}".format(
        M["key"], p["side"], p["strike"], p["side"], reason, pnl))
    legs = [{"label": reason, "price": exitp, "qty": qty}]
    in_ts = p.get("opened") or "—"
    notify(cards.exit_card("PAPER", p["side"], p["strike"], reason, entry,
                           exitp, chg, pnl, legs, day,
                           store.family_member_total(M["key"]), halted,
                           M["max_daily_loss"], in_ts,
                           now.strftime("%H:%M"), _label(M)), html=True)
    if halted:
        notify("🛑 {} ची दैनिक तोटा-मर्यादा (₹{:,.0f}) भितली — आज पुढचे ट्रेड नाहीत."
               .format(M["name"], M["max_daily_loss"]))
    return pnl


def _monitor(token, now):
    """उघड्या स्थितींचे निरीक्षण — SL / टार्गेट / वेळ (दर 30 सेकंदांनी)"""
    date = now.strftime("%Y-%m-%d")
    for p in store.family_open():
        M = _BY_KEY.get(p["member"])
        if not M:
            continue
        try:
            sq = _t(MCX_SQ_OFF if M["seg"] == "MCX" else BN_SQ_OFF)
            if now.time() >= sq:
                ltp = get_ltp(p["option_key"], token) or p["last_ltp"] \
                    or p["entry"]
                _exit_position(p, ltp, "वेळ एग्झिट (" +
                               (MCX_SQ_OFF if M["seg"] == "MCX"
                                else BN_SQ_OFF) + ")", now)
                continue
            ltp = get_ltp(p["option_key"], token)
            if not ltp or ltp <= 0:
                continue
            store.family_set_ltp(p["id"], round(ltp, 2))
            if ltp <= float(p["sl"]):
                _exit_position(p, ltp,
                               "स्टॉप लॉस −{:.0f}% 🛑".format(SL_PCT), now)
                continue
            if ltp >= float(p["target"]):
                _exit_position(p, ltp,
                               "टार्गेट +{:.0f}% ✅".format(TARGET_PCT), now)
        except UpstoxError:
            raise
        except Exception as e:
            store.log_event("family monitor[" + p["member"] + "]: "
                            + str(e)[:120])


def _kill_all(token, now):
    """KILL — सर्व family स्थिती तात्काळ बंद (दिवसात एकदाच)"""
    date = now.strftime("%Y-%m-%d")
    if store.get_state("fam_killdone_" + date) == "1":
        return
    store.set_state("fam_killdone_" + date, "1")
    for p in store.family_open():
        try:
            ltp = get_ltp(p["option_key"], token)
            if ltp and ltp > 0:
                _exit_position(p, ltp, "KILL स्विच 🚨", now)
        except Exception:
            pass


# ------------------------------------------------------------------
# मुख्य लूप (स्वतंत्र थ्रेड)
# ------------------------------------------------------------------
def _loop():
    tot = sum(_capital(M) for M in MEMBERS)
    store.log_event("👨‍👩‍👧 Family सुरू — 4 सदस्य (F1 Sasta/F2 Delta/F3 Distance/"
                    "F4 MCX-Mini), एकूण वर्चुअल ₹{:,.0f}, मोटो: स्वस्त स्ट्राइक + "
                    "निव्वल-नफा गेट (≥₹{:.0f}, breakeven ≤{:.0f}%)".format(
                        tot, NET_MIN, BE_MOVE_MAX))
    tick = 0
    while True:
        try:
            now = ist_now()
            if now.weekday() >= 5 or not ENABLED:
                time.sleep(60)
                continue
            token = store.get_state("upstox_token")
            if not token:
                time.sleep(60)
                continue
            if store.get_state("killed") == "1":
                _kill_all(token, now)
                time.sleep(30)
                continue
            if store.family_open():
                _monitor(token, now)
            # एंट्री-प्रयत्न — दर 60 सेकंदांनी (30-सेकंद लूपाचा दुसरा टिक)
            if tick % 2 == 0 and store.get_state("paused") != "1":
                n = now.time()
                if _t(ENTRY_START) <= n <= _t(ENTRY_END):
                    try:
                        st = get_market_status(token, "NSE")
                        if st != "NORMAL_CLOSE":
                            _try_enter_bn(token, now)
                    except Exception:
                        _try_enter_bn(token, now)
                if _t("09:45") <= n <= _t("12:00"):
                    _try_enter_f4(token, now)
            tick += 1
            time.sleep(30)
        except UpstoxError as e:
            if "TOKEN_INVALID" in str(e):
                time.sleep(90)             # मुख्य इंजिन टोकन हाताळते
            else:
                try:
                    store.log_event("family loop: " + str(e)[:150])
                except Exception:
                    pass
                time.sleep(60)
        except Exception as e:
            try:
                store.log_event("family loop err: " + repr(e)
                                + traceback.format_exc()[:200])
            except Exception:
                pass
            time.sleep(60)


def start_family():
    """family थ्रेड सुरू करा (engine.start_engine मधून; एकदाच)"""
    global _started
    if not ENABLED:
        return
    with _lock:
        if _started:
            return
        _started = True
    store.init_db()
    threading.Thread(target=_loop, daemon=True, name="family").start()


# ------------------------------------------------------------------
# दृश्य-मार्ग: डॅशबोर्ड + /api/eval + Telegram
# ------------------------------------------------------------------
def member_stats(date, M):
    """एका सदस्याचे आज + MTD आकडे (scoreboard साठी)"""
    today = store.family_today(date, M["key"])
    t_closed = [t for t in today if t["status"] == "CLOSED"]
    mts = [t for t in store.family_month(date[:7], M["key"])
           if t["status"] == "CLOSED"]
    w = sum(1 for t in mts if (t["pnl"] or 0) >= 0)

    def _avg_be(rows):
        bes = [float(r["be_move_pct"]) for r in rows
               if r.get("be_move_pct") is not None]
        return round(sum(bes) / len(bes), 1) if bes else None

    return {
        "key": M["key"], "name": M["name"], "style": M["style"],
        "seg": M["seg"], "capital": _capital(M),
        "max_daily_loss": M["max_daily_loss"],
        "today_trades": len(today),
        "today_pnl": round(sum((t["pnl"] or 0) for t in t_closed), 2),
        "mtd_trades": len(mts),
        "mtd_wins": w,
        "mtd_losses": len(mts) - w,
        "mtd_pnl": round(sum((t["pnl"] or 0) for t in mts), 2),
        "mtd_charges": round(sum((t["charges"] or 0) for t in mts), 2),
        "win_rate": round(100.0 * w / len(mts), 1) if mts else None,
        "avg_be_move": _avg_be(mts),
        "total_pnl": store.family_member_total(M["key"]),
        "halted": store.get_state("fam_halt_" + date + "_" + M["key"]) == "1",
        "open": [t for t in today if t["status"] == "OPEN"],
    }


def eval_block(date):
    """/api/eval चा 'family' ब्लॉक"""
    stats = [member_stats(date, M) for M in MEMBERS]
    best = None
    played = [s for s in stats if s["mtd_trades"]]
    if played:
        best = max(played, key=lambda s: s["mtd_pnl"])["key"]
    opens = []
    for p in store.family_open():
        ltp = p.get("last_ltp")
        mtm = round((float(ltp) - float(p["entry"])) * int(p["qty"]), 2) \
            if ltp else None
        opens.append({"id": p["id"], "member": p["member"],
                      "side": p["side"], "strike": p["strike"],
                      "expiry": p["expiry"], "qty": p["qty"],
                      "entry": p["entry"], "sl": p["sl"],
                      "target": p["target"], "be_move_pct": p["be_move_pct"],
                      "gate_note": p["gate_note"], "last_ltp": ltp,
                      "mtm": mtm})
    closed_today = [t for t in store.family_today(date)
                    if t["status"] == "CLOSED"]
    return {
        "enabled": ENABLED,
        "moto": "स्वस्त प्रीमियम + कमी भांडवल + जिंकीत ट्रेडमध्ये निव्वल-हमी",
        "rules": {"target_pct": TARGET_PCT, "sl_pct": SL_PCT,
                  "net_min": NET_MIN, "be_move_max_pct": BE_MOVE_MAX,
                  "premium_min": PREMIUM_MIN, "max_trades_per_day": MAX_TRADES,
                  "entry_window": ENTRY_START + "–" + ENTRY_END,
                  "bn_square_off": BN_SQ_OFF, "mcx_square_off": MCX_SQ_OFF},
        "members": stats,
        "best_finder_week": best,
        "positions": opens,
        "today": {"entries": len(store.family_today(date)),
                  "closed": len(closed_today),
                  "pnl_net": round(sum((t["pnl"] or 0) for t in closed_today),
                                   2)},
        "month": {
            "trades": len(store.family_month(date[:7])),
            "pnl_net": round(sum((t["pnl"] or 0) for t in
                                 store.family_month(date[:7])
                                 if t["status"] == "CLOSED"), 2),
        },
        "total_pnl": store.family_total_pnl(),
    }


def tele_text(date=None):
    """/family — Telegram scoreboard"""
    n = ist_now()
    date = date or n.strftime("%Y-%m-%d")
    b = eval_block(date)
    lines = ["👨‍👩‍👧 <b>Low Capital Family</b> ({})".format(date),
             "मोटो: स्वस्त स्ट्राइक + कमी भांडवल + निव्वल-नफा गेट "
             "(≥₹{:.0f}, breakeven ≤{:.0f}%)".format(NET_MIN, BE_MOVE_MAX)]
    for s in b["members"]:
        halt = " 🛑हॉल्ट" if s["halted"] else ""
        wr = "• WR {}%".format(s["win_rate"]) if s["win_rate"] is not None else ""
        be = ("• BE +{}%".format(s["avg_be_move"])
              if s["avg_be_move"] is not None else "")
        lines.append(
            "\n{} — {}{}\n"
            "  आज ₹{:,} | MTD ₹{:,} ({}W/{}L){} {}\n"
            "  भांडवल ₹{:,.0f} • सुरुवातीपासून ₹{:,.0f}".format(
                s["name"], s["style"], halt, s["today_pnl"], s["mtd_pnl"],
                s["mtd_wins"], s["mtd_losses"], wr, be, s["capital"],
                s["total_pnl"]))
    for p in b["positions"]:
        lines.append("\n◉ उघडी: [{}] {} {:.0f} @ ₹{:.2f} × {} | "
                     "SL ₹{:.2f} | टार्गेट ₹{:.2f} | {}".format(
                         p["member"], p["side"], p["strike"], p["entry"],
                         p["qty"], p["sl"], p["target"],
                         (p.get("gate_note") or "")[:60]))
    if b["best_finder_week"]:
        nm = _BY_KEY[b["best_finder_week"]]["name"] \
            if b["best_finder_week"] in _BY_KEY else b["best_finder_week"]
        lines.append("\n🏅 Best Strike Finder (MTD): " + nm)
    lines.append("\nएकूण सुरुवातीपासून: ₹{:,.0f}".format(b["total_pnl"]))
    return "\n".join(lines)


def eod_lines(date):
    """EOD अहवालासाठी family-ओळी"""
    if not ENABLED:
        return []
    b = eval_block(date)
    out = ["\n👨‍👩‍👧 <b>FAMILY</b> — उघडे {} | आज ₹{:,.0f} | "
           "MTD ₹{:,.0f} | सुरुवातीपासून ₹{:,.0f}".format(
               len(b["positions"]), b["today"]["pnl_net"],
               b["month"]["pnl_net"], b["total_pnl"])]
    for s in b["members"]:
        if s["today_trades"] or s["mtd_trades"]:
            out.append("   ◉ {} — आज {} ट्रेड ₹{:,.0f} | MTD {}W/{}L ₹{:,.0f}"
                       .format(s["name"], s["today_trades"], s["today_pnl"],
                               s["mtd_wins"], s["mtd_losses"], s["mtd_pnl"]))
    return out
