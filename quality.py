"""
धोरण-गुणवत्ता दरवाजे (Strategy Quality Gates) — super-mind स्तर २.

तत्त्व: 'डेटा बोलतो, आपण ऐकतो.' प्रत्येक instrument चे खरे paper-निकाल
पाहून आपोआप निर्णय — जे रक्तवाहू आहेत त्यांना प्रोब/बेंच मोड, तोट्यानंतर
थंड-काळ, आणि सूचक-कुटुंबात एकच बाजू एकत्र जास्त नको. उद्देश:
जानेवारी 2027 real-trading पर्यंत प्रत्येक धोरण 'कमी तोटा + जास्त नफा'
आकारात पोहोचवणे — म्हणजे नुकसान थांबवणारे दरवाजे आतापासूनच कागदी वर.

3 दरवाजे (सर्व डेटा-आधारित, स्वतःहून लागू व स्वतःहून सुटले):

① गुणवत्ता-लॅडर — rolling शेवटचे ROLL_WINDOW बंद ट्रेड (फक्त खरे पेपर
   निकाल; swing/family वेगळ्या तक्त्यावर म्हणून या गणितात नाहीत):
       n≥6 आणि WR<25% → बेंच   (आजचा दिवस बंद — पुढच्या दिवशी पुन्हा मोजले)
       n≥3 आणि WR<40% → प्रोब  (आज फक्त 1 ट्रेड — डेटा-गोळी चालू राहते)
       अन्यथा → config मधला सामान्य max_trades
   बेंच = 'धोरण आता दुरुस्त करा' संकेत; पुढच्या दिवशी परत मोजले जाते,
   म्हणून कायमचा बंद नाही — दुरुस्ती झाली की आपोआप सुरू.

② तोटा-कूलडाउन — एखादा ट्रेड तोट्यात बंद झाल्यावर COOLDOWN_MIN मिनिटे
   त्याच सिम्बॉलची नवीन एंट्री नाही. कारण: तोट्यानंतरच्या सारख्याच
   परिस्थितीत लगेच पुन्हा एंट्री = दुहेरी तोटा (आजचा NIFTY/SENSEX प्रमाणे).

③ सूचक-एकता — BANKNIFTY/NIFTY/SENSEX/FINNIFTY हे एकाच दिशेने चालतात.
   कुटुंबातील एकाच बाजूला (CE किंवा PE) आज 2 ट्रेड उघडे किंवा तोट्यात
   बंद असतील → तिसरी एंट्री थांबवली. 11-Nov प्रमाणे: BN CE + NIFTY CE
   (SL) नंतर SENSEX/FINNIFTY CE आपोआप थांबले असते — क्लस्टर-तोटा नाही.

टीप: सर्व नोटीसी दिवसात एकदाच (telegram + events log) — स्पॅम नाही.
"""

import store
from config import ist_now

# ---------------- संरचना ----------------
INDEX_FAMILY = ("BANKNIFTY", "NIFTY", "SENSEX", "FINNIFTY")
INDEX_SAME_SIDE_CAP = 2        # कुटुंबात एकाच बाजूला कमाल उघडे/तोट्यात-बंद
ROLL_WINDOW = 10               # rolling गुणवत्ता-क्षितिज (शेवटचे N बंद ट्रेड)
BENCH_N, BENCH_WR = 6, 25.0    # n≥6 आणि WR<25 → बेंच
PROBE_N, PROBE_WR = 3, 40.0    # n≥3 आणि WR<40 → प्रोब (1 ट्रेड/दिवस)
COOLDOWN_DEFAULT_MIN = 30
COOLDOWN = {"COPPER": 45, "CRUDE": 45}   # MCX बेस-मेटल/ऊर्जा — जास्त थंड-काळ


def _cooldown_min(key):
    return COOLDOWN.get(key, COOLDOWN_DEFAULT_MIN)


def rolling_wr(key):
    """rolling शेवटचे ROLL_WINDOW बंद ट्रेड → (n, WR%) — ट्रेड नसतील तर (0, 100)"""
    rows = store.last_closed(key, ROLL_WINDOW)
    n = len(rows)
    if not n:
        return 0, 100.0
    wins = sum(1 for r in rows if (r["pnl"] or 0) > 0)
    return n, wins * 100.0 / n


def quality_state(key):
    """डॅशबोर्ड/निदानासाठी — (मोड, n, WR%) ; मोड ∈ {'NORMAL','PROBE','BENCH'}"""
    n, wr = rolling_wr(key)
    if n >= BENCH_N and wr < BENCH_WR:
        return "BENCH", n, wr
    if n >= PROBE_N and wr < PROBE_WR:
        return "PROBE", n, wr
    return "NORMAL", n, wr


def effective_max_trades(date, S):
    """आजची प्रभावी ट्रेड-मर्यादा (गुणवत्ता-लॅडर लागू) — बेंच 0, प्रोब 1, अन्यथा config"""
    mode, _n, _wr = quality_state(S["key"])
    if mode == "BENCH":
        return 0
    if mode == "PROBE":
        return 1
    return S.get("max_trades", 2)


def _once_note(date, key, kind, msg):
    """दिवसात एकदाच सूचना — events log + telegram (import-cycle सुरक्षित)"""
    k = "qnote_{}_{}_{}".format(kind, date, key)
    if store.get_state(k) == "1":
        return
    store.set_state(k, "1")
    store.log_event("🛡️ " + msg)
    try:
        from telegram_bot import notify
        notify("🛡️ " + msg)
    except Exception:
        pass


def entry_block(date, S, now=None):
    """① बेंच + ② कूलडाउन दरवाजे → (चालू, कारण). engine च्या can_enter आधी."""
    key = S["key"]
    now = now or ist_now()

    # ① बेंच — रक्तवाहू धोरण आजचा दिवस बंद
    mode, n, wr = quality_state(key)
    if mode == "BENCH":
        msg = ("{} बेंचवर — शेवटचे {} बंद ट्रेड WR {:.0f}% (<{}%) "
               "म्हणून आज एंट्री नाही; धोरण-दुरुस्तीनंतर आपोआप सुरू".format(
                   S["label"], n, wr, BENCH_WR))
        _once_note(date, key, "bench", msg)
        return False, "गुणवत्ता-बेंच (शेवटचे {} ट्रेड WR {:.0f}%)".format(n, wr)

    # ② तोटा-कूलडाउन
    lk = "lastloss_" + date + "_" + key
    v = store.get_state(lk)
    if v:
        try:
            h, m = v.split(":")
            loss_min = int(h) * 60 + int(m)
            now_min = now.hour * 60 + now.minute
            cd = _cooldown_min(key)
            d = now_min - loss_min
            if 0 <= d < cd:
                msg = ("{} तोटा-कूलडाउन — {} मिनिटे उर्वरित "
                       "(तोट्यानंतरची पुन्हा-एंट्री थांबवली)".format(
                           S["label"], cd - d))
                _once_note(date, key, "cool", msg)
                return False, "तोटा-कूलडाउन ({} मि उर्वरित)".format(cd - d)
        except (ValueError, AttributeError):
            pass                      # वाईट state-किंमत — दरवाजा वगळा

    return True, ""


def index_gate(date, S, side):
    """③ सूचक-एकता दरवाजा — सिग्नल-बाजू मिळाल्यावर engine मध्ये होतो.
    कुटुंबात एकाच बाजूला आज 2 ट्रेड (उघडे किंवा तोट्यात बंद) → तिसरी थांबवली."""
    key = S["key"]
    if key not in INDEX_FAMILY:
        return True, ""
    same = 0
    for t in store.trades_today(date):
        if t.get("symbol") == key or (t.get("side") or "") != side:
            continue
        if t.get("symbol") not in INDEX_FAMILY:
            continue
        if t.get("status") == "OPEN":
            same += 1
        elif t.get("status") == "CLOSED" and (t.get("pnl") or 0) < 0:
            same += 1
    if same >= INDEX_SAME_SIDE_CAP:
        msg = ("सूचक-एकता: {} {} — कुटुंबात याच बाजूला आज {} ट्रेड "
               "उघडे/तोट्यात आहेत, म्हणून {} वी एंट्री थांबवली".format(
                   S["label"], side, same, same + 1))
        _once_note(date, key, "corr", msg)
        return False, "सूचक-एकता ({} बाजू आधीच {} वेळा)".format(side, same)
    return True, ""


def note_loss(date, S, pnl, now=None):
    """② साठी — तोट्यात बंद झालेला ट्रेड नोंदवा (risk.register_exit मधून)"""
    if pnl is None or pnl >= 0:
        return
    now = now or ist_now()
    store.set_state("lastloss_" + date + "_" + S["key"],
                    now.strftime("%H:%M"))
