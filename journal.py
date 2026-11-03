#!/usr/bin/env python3
"""जर्नल-दर्शक (VM वर sqlite3 CLI नसताना):
    ./venv/bin/python journal.py [पासून-तारीख YYYY-MM-DD] [मर्यादा]
उदा: ./venv/bin/python journal.py 2026-11-02 100
प्रति-दिवस ट्रेड-सारांश + oi-कचरा वगळून घटना (IST) दाखवतो."""
import calendar
import os
import sys
import time
import sqlite3

# सेवेशी तीच DB — DATA_DIR unset असताना <repo>/data (deploy.sh प्रमाणे)
if not os.getenv("DATA_DIR"):
    _dd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if os.path.isdir(_dd):
        os.environ["DATA_DIR"] = _dd

import store  # noqa: E402  (DATA_DIR सेट झाल्यावरच इंपोर्ट)


def _ist(ts):
    return time.strftime("%d-%b %H:%M:%S", time.gmtime(ts + 19800))


def main():
    today = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 19800))
    since = sys.argv[1] if len(sys.argv) > 1 else today
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    con = sqlite3.connect(store.DB_PATH)

    print("=== ट्रेड-सारांश (शेवटचे 7 दिवस) ===")
    q = ("SELECT date, COUNT(*), IFNULL(SUM(status='CLOSED'),0), "
         "IFNULL(SUM(pnl>0),0), IFNULL(ROUND(SUM(pnl),0),0) "
         "FROM trades GROUP BY date ORDER BY date DESC LIMIT 7")
    rows = con.execute(q).fetchall()
    if not rows:
        print("  (अजून एकही ट्रेड नाही)")
    for r in rows:
        print("  %s | ट्रेड %d | बंद %s | जिंकले %s | P&L ₹%s" % r)

    print()
    print("=== घटना (पासून %s, oi-कचरा वगळला) ===" % since)
    cut = calendar.timegm(time.strptime(since, "%Y-%m-%d")) - 19800
    q2 = ("SELECT ts,msg FROM events WHERE ts > ? AND msg NOT LIKE 'oi:%' "
          "ORDER BY id ASC LIMIT ?")
    n = 0
    for ts, msg in con.execute(q2, (cut, limit)):
        print("  %s | %s" % (_ist(ts), str(msg)[:180]))
        n += 1
    if n == 0:
        print("  (या तारखेपासून काही घटना नाहीत)")


if __name__ == "__main__":
    store.init_db()
    main()
