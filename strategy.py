"""
धोरण: ORB (Opening Range Breakout) + व्हॉलॅटिलिटी/गॅप "AI फिल्टर"

नियम:
1. 09:15–09:30 मधली BANKNIFTY रेंज काढा (Opening Range = OR).
2. रेंज खूप छोटी (मंद बाजार) किंवा खूप मोठी (गोंधळ) → आज ट्रेड नाही.
3. आदल्या दिवसापासून गॅप 1% पेक्षा जास्त → ट्रेड नाही.
4. 5-मिनिट कॅन्डल OR च्या वर (high) बंद झाली → CE खरेदी सिग्नल.
   OR च्या खाली (low) बंद झाली → PE खरेदी सिग्नल.
"""

from datetime import datetime, time as dtime, timedelta

from config import MAX_GAP_PCT, MAX_OR_WIDTH_PCT, MIN_OR_WIDTH_PCT, ORB_END, ORB_START


def _t(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def parse_candles(candles):
    """Upstox कॅन्डल [ts, o, h, l, c, v, oi] → सोप्या dict यादी (कालक्रमाने)"""
    out = []
    for c in candles or []:
        try:
            out.append({
                "ts": datetime.fromisoformat(c[0]),
                "o": float(c[1]), "h": float(c[2]),
                "l": float(c[3]), "c": float(c[4]),
            })
        except (ValueError, TypeError, IndexError):
            continue
    out.sort(key=lambda x: x["ts"])
    return out


def opening_range(cs, orb_start=None, orb_end=None):
    """ORB रेंज (डीफॉल्ट 9:15–9:30; Copper साठी 9:15–9:45) → {high, low, n} किंवा None"""
    a, b = _t(orb_start or ORB_START), _t(orb_end or ORB_END)
    orc = [c for c in cs if a <= c["ts"].time() < b]
    if len(orc) < 12:          # पूर्ण 15 मिनिटे नाहीत → डेटा अपुरा (सुट्टी?)
        return None
    return {
        "high": max(c["h"] for c in orc),
        "low": min(c["l"] for c in orc),
        "n": len(orc),
    }


def last_completed_5m(cs, now, orb_end=None):
    """शेवटची पूर्ण झालेली 5-मिनिट कॅन्डल (ORB समाप्तीनंतरची)"""
    groups = {}
    orb_end_t = _t(orb_end or ORB_END)
    for c in cs:
        if c["ts"].time() < orb_end_t:
            continue
        k = c["ts"].replace(minute=(c["ts"].minute // 5) * 5,
                            second=0, microsecond=0)
        g = groups.setdefault(k, {"ts": k, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"]})
        g["h"] = max(g["h"], c["h"])
        g["l"] = min(g["l"], c["l"])
        g["c"] = c["c"]
    done = [g for g in groups.values() if g["ts"] + timedelta(minutes=5) <= now]
    done.sort(key=lambda g: g["ts"])
    return done[-1] if done else None


def analyze(cs, spot, now, prev_close=None,
            orb_start=None, orb_end=None):
    """
    मुख्य विश्लेषण → सिग्नल dict किंवा None.
    फिल्टर वगळल्यास → {"blocked": कारण}
    orb_start/orb_end — सिम्बॉल-विशिष्ट ORB वेळ (डीफॉल्ट BANKNIFTY 9:15–9:30)
    """
    if spot is None or spot <= 0 or not cs:
        return None

    orb = opening_range(cs, orb_start, orb_end)
    if not orb:
        return None

    # फिल्टर 1: रेंजची रुंदी (व्हॉलॅटिलिटी तपासणी)
    width_pct = (orb["high"] - orb["low"]) / spot * 100.0
    if width_pct < MIN_OR_WIDTH_PCT:
        return {"blocked": f"OR रेंज खूप छोटी ({width_pct:.2f}%) — मंद बाजार"}
    if width_pct > MAX_OR_WIDTH_PCT:
        return {"blocked": f"OR रेंज खूप मोठी ({width_pct:.2f}%) — गोंधळी बाजार"}

    # फिल्टर 2: गॅप तपासणी
    if prev_close and prev_close > 0:
        gap_pct = abs(cs[0]["o"] - prev_close) / prev_close * 100.0
        if gap_pct > MAX_GAP_PCT:
            return {"blocked": f"गॅप {gap_pct:.2f}% — धोकादायक उघड"}

    last = last_completed_5m(cs, now, orb_end)
    if not last:
        return None

    if last["c"] > orb["high"]:
        return {"side": "CE", "or_high": orb["high"], "or_low": orb["low"],
                "breakout": last["c"], "candle_ts": last["ts"].isoformat()}
    if last["c"] < orb["low"]:
        return {"side": "PE", "or_high": orb["high"], "or_low": orb["low"],
                "breakout": last["c"], "candle_ts": last["ts"].isoformat()}
    return None
