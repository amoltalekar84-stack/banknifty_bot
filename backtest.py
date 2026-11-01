"""
बॅकटेस्ट — ORB धोरण जुन्या BANKNIFTY डेटावर चालवून पाहा (सर्व खर्चांसह).

काय खरे आहे (real):
• खरे 5-मिनिट BANKNIFTY कॅन्डल (Upstox historical API)
• खरे नियम — strategy.py प्रमाणेच: OR रेंज, व्हॉलॅटिलिटी/गॅप फिल्टर,
  SL -20%, टार्गेट +40%, +25% वर breakeven ट्रेल, 15:05 स्क्वेअर-ऑफ,
  कमाल 2 ट्रेड/दिवस, दैनिक तोटा ₹2,500 halt
• खरे सर्व खर्च (charges.py) + 0.05% स्लिपेज

काय अंदाजे आहे (synthetic):
• ऑप्शन प्रीमियम Black-Scholes मॉडेलने (IV डीफॉल्ट 14%) — खऱ्या जुन्या
  ऑप्शन प्रीमियमचा डेटा फ्रीमध्ये मिळत नाही, म्हणून ATM स्ट्राइक + जवळची
  एक्सपायरी धरून किंमत काढली जाते. हे स्पष्टपणे निकालात लिहिले जाते.

वापर (VM वर):  python backtest.py 30
टोकन:          bot.db मधून आपोआप घेतला जातो — आधी बॉटला /settoken पाठवा.
Telegram:      /backtest 30
"""

import csv
import math
import os
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import config as C
import charges
import store
from strategy import parse_candles
from upstox_api import UpstoxError, get_hist_candles, get_hist_candles_v3

IST = ZoneInfo(C.TZ_NAME)
R_FREE = 0.065          # रिस्क-फ्री व्याज दर (Black-Scholes साठी)
STRIKE_STEP = 100       # BANKNIFTY स्ट्राइक अंतर = 100 अंक
MAX_DAYS = 90           # कमाल कालावधी


# ------------------------------------------------------------------
# Black-Scholes ऑप्शन प्राईसिंग
# ------------------------------------------------------------------
def _ncdf(x):
    """सामान्य वितरणाचे CDF"""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs_premium(S, K, T, sigma, is_call, r=R_FREE):
    """युरोपियन ऑप्शन प्रीमियम (T = वर्षांमध्ये, sigma = IV उदा. 0.14)"""
    if S <= 0 or K <= 0:
        return 0.0
    if sigma <= 0 or T <= 0:
        return round(max(S - K, 0.0) if is_call else max(K - S, 0.0), 2)
    T = max(T, 1e-6)
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sq
    d2 = d1 - sq
    disc = math.exp(-r * T)
    if is_call:
        p = S * _ncdf(d1) - K * disc * _ncdf(d2)
        return round(max(p, max(S - K * disc, 0.0)), 2)
    p = K * disc * _ncdf(-d2) - S * _ncdf(-d1)
    return round(max(p, max(K * disc - S, 0.0)), 2)


def next_expiry(d):
    """d पासून सर्वात जवळचा गुरुवार (BANKNIFTY weekly expiry)"""
    delta = (3 - d.weekday()) % 7          # Mon=0 ... Thu=3
    return d + timedelta(days=delta)


def _expiry_dt(d):
    """एक्सपायरी दिवशी 15:30 IST"""
    return datetime.combine(next_expiry(d), dtime(15, 30), tzinfo=IST)


def _T_years(expiry_dt, ts):
    secs = (expiry_dt - ts).total_seconds()
    return max(secs, 1.0) / (365.0 * 24 * 3600)


# ------------------------------------------------------------------
# 5-मिनिट डेटा (v3 नाही मिळाला तर v2 1-minute आणून आपोआप जोडा)
# ------------------------------------------------------------------
def _to_5m(cs1):
    """1-मिनिट कॅन्डल → 5-मिनिट बार"""
    g = {}
    for c in cs1:
        k = c["ts"].replace(minute=(c["ts"].minute // 5) * 5,
                            second=0, microsecond=0)
        if k not in g:
            g[k] = {"ts": k, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"]}
        else:
            b = g[k]
            b["h"] = max(b["h"], c["h"])
            b["l"] = min(b["l"], c["l"])
            b["c"] = c["c"]
    return sorted(g.values(), key=lambda x: x["ts"])


def fetch_5m(token, d):
    """एक दिवसाचे 5-मिनिट बार → यादी (नाही मिळाले तर [])"""
    cs = []
    try:
        cs = parse_candles(get_hist_candles_v3(token, C.INDEX_KEY, "minutes", "5",
                                               d.isoformat(), d.isoformat()))
    except UpstoxError:
        cs = []
    if len(cs) >= 10:
        return cs
    try:                                     # fallback: 1-minute → 5-min
        cs1 = parse_candles(get_hist_candles(token, C.INDEX_KEY, "1minute",
                                             d.isoformat(), d.isoformat()))
    except UpstoxError:
        return cs
    if len(cs1) > len(cs):
        cs1_5 = _to_5m(cs1)
        if len(cs1_5) > len(cs):
            cs = cs1_5
    return cs


def opening_range_5m(cs):
    """09:15–09:30 रेंज (5-मिनिट बारमधून) → {high, low} किंवा None"""
    a, b = dtime(9, 15), dtime(9, 30)
    orc = [c for c in cs if a <= c["ts"].time() < b]
    if len(orc) < 3:                         # 3 पैकी 3 बार नाहीत → डेटा अपुरा
        return None
    return {"high": max(c["h"] for c in orc),
            "low": min(c["l"] for c in orc),
            "n": len(orc)}


# ------------------------------------------------------------------
# एक दिवसाचे सिम्युलेशन (engine.py च्या नियमांप्रमाणेच)
# ------------------------------------------------------------------
def simulate_day(cs, prev_close, expiry_dt, iv):
    """→ (trades[], blocked_reason किंवा None)"""
    orb = opening_range_5m(cs)
    if not orb:
        return [], "डेटा अपुरा"

    spot0 = cs[0]["o"]
    width = (orb["high"] - orb["low"]) / spot0 * 100.0
    if width < C.MIN_OR_WIDTH_PCT:
        return [], f"OR रेंज छोटी ({width:.2f}%)"
    if width > C.MAX_OR_WIDTH_PCT:
        return [], f"OR रेंज मोठी ({width:.2f}%)"
    if prev_close and prev_close > 0:
        gap = abs(spot0 - prev_close) / prev_close * 100.0
        if gap > C.MAX_GAP_PCT:
            return [], f"गॅप {gap:.2f}%"

    bars = [c for c in cs if c["ts"].time() >= dtime(9, 30)]
    trades = []
    day_pnl = 0.0
    pos = None
    end_t = dtime(*[int(x) for x in C.ENTRY_END.split(":")])
    sq_t = dtime(15, 5)

    for b in bars:
        ts = b["ts"]

        # ---------- उघडी पोझिशन असल्यास निरीक्षण ----------
        if pos:
            pl = bs_premium(b["l"], pos["K"], _T_years(expiry_dt, ts), iv, pos["CE"])
            ph = bs_premium(b["h"], pos["K"], _T_years(expiry_dt, ts), iv, pos["CE"])
            pc = bs_premium(b["c"], pos["K"], _T_years(expiry_dt, ts), iv, pos["CE"])

            # ट्रेल: +25% पोहोचला → SL खर्चाच्या ठिकाणी (breakeven)
            if pc >= pos["entry"] * (1 + C.TRAIL_START_PCT / 100.0) and pos["sl"] < pos["entry"]:
                pos["sl"] = pos["entry"]
                pos["trail"] = True

            reason = None
            exit_raw = None
            if ts.time() >= sq_t:
                reason, exit_raw = "वेळ एग्झिट (15:05)", pc
            elif pl <= pos["sl"]:
                reason = "ट्रेल SL 🔒" if pos["trail"] else "स्टॉप लॉस"
                exit_raw = pos["sl"]
            elif ph >= pos["target"]:
                reason, exit_raw = "टार्गेट पोहोचला ✅", pos["target"]

            if reason:
                exitp = round(exit_raw * (1 - C.SLIPPAGE), 2)
                gross = round((exitp - pos["entry"]) * C.LOT_SIZE, 2)
                chg = charges.option_charges(pos["entry"] * C.LOT_SIZE,
                                             exitp * C.LOT_SIZE)["total"]
                net = round(gross - chg, 2)
                trades.append({"date": pos["date"], "side": pos["side"],
                               "strike": pos["K"], "entry": pos["entry"],
                               "exit": exitp, "reason": reason,
                               "gross": gross, "charges": chg, "net": net,
                               "in_ts": pos["in_ts"].strftime("%H:%M"),
                               "out_ts": ts.strftime("%H:%M")})
                day_pnl += net
                pos = None
                if day_pnl <= -abs(C.MAX_DAILY_LOSS):
                    break                        # दैनिक तोटा halt
                continue                          # हीच कॅन्डल पुन्हा एंट्रीसाठी नाही

        # ---------- नवीन एंट्री ----------
        if (pos is None and len(trades) < C.MAX_TRADES_PER_DAY
                and ts.time() <= end_t):
            side = None
            if b["c"] > orb["high"]:
                side = "CE"
            elif b["c"] < orb["low"]:
                side = "PE"
            if side:
                K = round(b["c"] / STRIKE_STEP) * STRIKE_STEP
                raw = bs_premium(b["c"], K, _T_years(expiry_dt, ts), iv, side == "CE")
                if raw and raw > 1:               # अर्थपूर्ण प्रीमियम
                    entry = round(raw * (1 + C.SLIPPAGE), 2)
                    pos = {"date": ts.strftime("%Y-%m-%d"), "side": side,
                           "K": K, "CE": side == "CE", "entry": entry,
                           "sl": round(entry * (1 - C.SL_PCT / 100.0), 2),
                           "target": round(entry * (1 + C.TARGET_PCT / 100.0), 2),
                           "trail": False, "in_ts": ts}

    # ---------- डेटा अपूर्ण संपला → उघडी पोझिशन शेवटच्या किंमतीवर बंद ----------
    if pos and bars:
        lb = bars[-1]
        pc = bs_premium(lb["c"], pos["K"], _T_years(expiry_dt, lb["ts"]),
                        iv, pos["CE"])
        exitp = round(pc * (1 - C.SLIPPAGE), 2)
        gross = round((exitp - pos["entry"]) * C.LOT_SIZE, 2)
        chg = charges.option_charges(pos["entry"] * C.LOT_SIZE,
                                     exitp * C.LOT_SIZE)["total"]
        net = round(gross - chg, 2)
        trades.append({"date": pos["date"], "side": pos["side"],
                       "strike": pos["K"], "entry": pos["entry"], "exit": exitp,
                       "reason": "डेटा समाप्त (अपूर्ण दिवस)", "gross": gross,
                       "charges": chg, "net": net,
                       "in_ts": pos["in_ts"].strftime("%H:%M"),
                       "out_ts": lb["ts"].strftime("%H:%M")})

    return trades, None


# ------------------------------------------------------------------
# पूर्ण बॅकटेस्ट चालवा
# ------------------------------------------------------------------
def run(days=30, iv=0.14, token=None):
    """
    बॅकटेस्ट चालवा → (सारांश मजकूर, CSV फाईलचा पथ किंवा None)
    """
    store.init_db()
    token = token or store.get_state("upstox_token")
    if not token:
        return ("❌ टोकन नाही — आधी बॉटला /settoken पाठवा\n"
                "(बॅकटेस्टला Upstox चा खरा डेटा लागतो)."), None

    days = max(5, min(int(days), MAX_DAYS))
    end_d = datetime.now(IST).date()
    start_d = end_d - timedelta(days=days)

    # आदल्या दिवसाच्या बंद किंमती (गॅप फिल्टरसाठी) — एकच कॉल
    prev_map = {}
    try:
        rows = get_hist_candles(token, C.INDEX_KEY, "day",
                                (start_d - timedelta(days=12)).isoformat(),
                                (end_d - timedelta(days=1)).isoformat())
        for r in rows:
            try:
                prev_map[r[0][:10]] = float(r[4])
            except (ValueError, TypeError, IndexError):
                continue
    except UpstoxError:
        pass

    def _prev_close(d):
        cands = [k for k in prev_map if k < d.isoformat()]
        return prev_map[max(cands)] if cands else None

    all_trades, blocked, no_data = [], {}, 0
    d = start_d
    while d <= end_d:
        if d.weekday() < 5:                      # सोम–शुक्र
            cs = fetch_5m(token, d)
            if len(cs) < 10:
                no_data += 1                     # सुट्टी/डेटा नाही
            else:
                trades, why = simulate_day(cs, _prev_close(d), _expiry_dt(d), iv)
                if why and not trades:
                    blocked[why.split(" (")[0]] = blocked.get(why.split(" (")[0], 0) + 1
                all_trades.extend(trades)
            import time as tt
            tt.sleep(0.35)                       # API वेग मर्यादा सुरक्षा
        d += timedelta(days=1)

    if not all_trades and not blocked and no_data > 0:
        return ("⚠️ कोणताही डेटा मिळाला नाही.\n"
                "• टोकन वैध आहे का? (/status मध्ये बघा)\n"
                "• जुन्या तारखांसाठी Upstox कडे 5-मिनिट डेटा नसतो "
                "(साधारण शेवटचे ~1 महिना)."), None

    # ---------------- आकडेवारी ----------------
    n = len(all_trades)
    wins = [t for t in all_trades if t["net"] >= 0]
    losses = [t for t in all_trades if t["net"] < 0]
    gross_total = round(sum(t["gross"] for t in all_trades), 2)
    chg_total = round(sum(t["charges"] for t in all_trades), 2)
    net_total = round(sum(t["net"] for t in all_trades), 2)
    winrate = (len(wins) / n * 100.0) if n else 0.0
    avg = round(net_total / n, 0) if n else 0
    best = max((t["net"] for t in all_trades), default=0)
    worst = min((t["net"] for t in all_trades), default=0)
    cum, peak, mdd = 0.0, 0.0, 0.0
    for t in all_trades:
        cum += t["net"]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    days_traded = len({t["date"] for t in all_trades})

    capital = 50000.0
    try:
        capital = float(store.get_state("capital") or 50000.0)
    except (TypeError, ValueError):
        capital = 50000.0
    ret = net_total / capital * 100.0 if capital else 0.0

    # ---------------- CSV तयार करा ----------------
    csv_path = None
    try:
        csv_path = os.path.join(
            store.DATA_DIR,
            "backtest_" + datetime.now(IST).strftime("%Y%m%d_%H%M") + ".csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["तारीख", "बाजू", "स्ट्राइक", "एंट्री", "एग्झिट",
                        "कारण", "करपूर्व P&L", "खर्च", "निव्वळ P&L",
                        "एंट्री वेळ", "एग्झिट वेळ"])
            for t in all_trades:
                w.writerow([t["date"], t["side"], t["strike"], t["entry"],
                            t["exit"], t["reason"], t["gross"], t["charges"],
                            t["net"], t["in_ts"], t["out_ts"]])
    except OSError:
        csv_path = None

    # ---------------- सारांश मजकूर ----------------
    L = ["🧪 बॅकटेस्ट — ORB धोरण (सर्व खर्चांसह)",
         f"📅 कालावधी: {start_d.isoformat()} → {end_d.isoformat()}"
         f" | ट्रेड झालेले दिवस: {days_traded}",
         f"⚙️ प्रीमियम: Black-Scholes (IV {iv*100:.0f}%) | स्लिपेज 0.05%",
         "──────────────────",
         f"📊 एकूण ट्रेड: {n} | ✅ जिंके: {len(wins)} | ❌ हार: {len(losses)}"
         f" | विन रेट: {winrate:.0f}%",
         f"🧾 एकूण खर्च: ₹{chg_total:,.0f}"
         + (f" (सरासरी ₹{chg_total/n:,.0f}/ट्रेड)" if n else ""),
         f"💵 करपूर्व P&L: ₹{gross_total:,.0f}",
         f"📉 निव्वळ P&L (खर्च वजा): ₹{net_total:,.0f}",
         f"📊 सरासरी/ट्रेड: ₹{avg:,.0f} | सर्वोत्तम: ₹{best:,.0f} | "
         f"वाईटतम: ₹{worst:,.0f}",
         f"📉 कमाल ड्रॉडाऊन: ₹{mdd:,.0f}",
         f"💰 ₹{capital:,.0f} भांडवलावर परतावा: {ret:+.1f}% (या कालावधीत)"]
    if blocked:
        top = sorted(blocked.items(), key=lambda x: -x[1])[:4]
        L.append("🚫 वगळलेले दिवस: " + " | ".join(f"{k} ×{v}" for k, v in top))
    if no_data:
        L.append(f"ℹ️ डेटा नसलेले दिवस: {no_data} (सुट्ट्या/जुन्या तारखा)")

    # ट्रेड तपशील (जागा उरल्यास)
    detail = []
    for t in all_trades[-12:]:
        icon = "✅" if t["net"] >= 0 else "❌"
        dd = t["date"][5:]
        detail.append(f"{icon} {dd} | {t['strike']:.0f} {t['side']} "
                      f"₹{t['entry']:.0f}→₹{t['exit']:.0f} | "
                      f"निव्वळ ₹{t['net']:,.0f} ({t['reason']})")
    if detail:
        L.append("──────────────────")
        L.append("शेवटचे ट्रेड:")
        L.extend(detail)
    L.append("──────────────────")
    L.append("⚠️ नोंद: ऑप्शन प्रीमियम synthetic अंदाज आहे (खरा नाही); "
             "नियम, स्लिपेज व सर्व खर्च खरे आहेत. हे केवळ मार्गदर्शन आहे — "
             "नफ्याची हमी नाही.")
    if csv_path:
        L.append(f"📄 सविस्तर CSV: {csv_path}")

    txt = "\n".join(L)
    if len(txt) > 3900:                          # Telegram 4096 मर्यादा
        txt = txt[:3880] + "\n… (पूर्ण यादी CSV मध्ये)"
    return txt, csv_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ORB धोरण बॅकटेस्ट")
    ap.add_argument("days", nargs="?", default=30, type=int,
                    help="किती दिवस मागे जायचे (default 30)")
    ap.add_argument("--iv", default=0.14, type=float, help="इम्प्लाय्ड व्हॉलॅटिलिटी")
    a = ap.parse_args()
    _txt, _csv = run(days=a.days, iv=a.iv)
    print(_txt)
