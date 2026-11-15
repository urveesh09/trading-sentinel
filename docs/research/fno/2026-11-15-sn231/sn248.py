"""SN248 - the pre-registered crash test (CRASH_TEST_2020.md). Run ONCE, only after the downloading agent reports every NIFTY
2020 target through Sep 2020 finished:  python sn248.py --data-complete
It mirrors (read-only) NIFTY index 1-minute Dec 2019 - Sep 2020, futures, and option rows 14:55-15:29 of the weekly expiries
Jan 2 - Sep 24 2020 into _local, checks coverage (counts only), then scores the frozen legs once."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import led  # noqa: E402
import wk4  # noqa: E402

wk3, wk = led.wk3, led.wk
LOCAL = HERE / "_local"
LEAN, FUT = LOCAL / "mirror-nifty-2020-lean.sqlite", LOCAL / "fut-nifty-2020.sqlite"
EXPIRY = ("2020-01-02", "2020-09-24")
INDEX = ("2019-12-01", "2020-10-01")
LEGS = {"Gold v7 leg: WK-H band 0.8": {"band": 0.8}, "Gold v6 leg: WK-H band 0.6": {}, "WK-H band 0.7": {"band": 0.7},
        "info: band 0.8 + synthetic hedge": {"band": 0.8, "instrument": "synth"}, "info: band 0.8 + flatten at 14:30": {"band": 0.8, "flatten_j": 315}}
INS = "INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"


def months(lo, hi):
    y, m = int(lo[:4]), int(lo[5:7])
    while f"{y:04d}-{m:02d}-01" < hi:
        nxt = (y + (m == 12), 1 if m == 12 else m + 1)
        yield f"{y:04d}-{m:02d}-01", min(hi, f"{nxt[0]:04d}-{nxt[1]:02d}-01")
        y, m = nxt


def mirror():
    sys.path.insert(0, str(wk.HERE))           # SN201's folder (CANDLES schema)
    import sn201
    src = sqlite3.connect(f"file:{wk3.SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    for path, fill in ((LEAN, "lean"), (FUT, "fut")):
        if path.exists():
            continue
        part = path.with_name(path.name + ".part")
        part.unlink(missing_ok=True)
        dst = sqlite3.connect(part)
        dst.execute(sn201.CANDLES)
        if fill == "lean":
            for a, b in months(*INDEX):
                dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND interval='1minute' "
                                                 "AND datetime >= ? AND datetime < ?", (a, b)).fetchall())
                time.sleep(0.02)
            for (e,) in src.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry >= ? AND expiry <= ?", EXPIRY).fetchall():
                dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND interval='1minute' "
                                                 "AND substr(datetime,12,5) BETWEEN ? AND ?", (e, wk.OPT_LO, wk.OPT_HI)).fetchall())
                time.sleep(0.02)
        else:
            for a, b in months(*INDEX):
                dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='future' AND underlying='NIFTY' AND interval='1minute' "
                                                 "AND datetime >= ? AND datetime < ?", (a, b)).fetchall())
                time.sleep(0.02)
        dst.commit()
        dst.close()
        os.replace(part, path)
    src.close()


def coverage():
    con = sqlite3.connect(f"file:{LEAN.as_posix()}?mode=ro", uri=True)
    per = con.execute("SELECT substr(expiry,1,10), COUNT(DISTINCT substr(datetime,1,10)), MIN(n) FROM (SELECT expiry, datetime, COUNT(*) n FROM candles "
                      "WHERE kind='option' AND substr(datetime,12,5)='15:15' AND substr(datetime,1,10) < substr(expiry,1,10) GROUP BY expiry, datetime) GROUP BY 1").fetchall()
    idx = con.execute("SELECT COUNT(DISTINCT substr(datetime,1,10)) FROM candles WHERE kind='index'").fetchone()[0]
    con.close()
    return {"expiries": len(per), "expiries_with_3plus_sessions": sum(1 for _e, s, _n in per if s >= 3), "index_sessions": idx,
            "min_series_at_1515": min((n for _e, _s, n in per), default=0)}


def crash_sample():
    data = wk.read_source(LEAN, "NIFTY")
    weeks = []
    for e, days in wk.expiries(data):
        if not (EXPIRY[0] <= e <= EXPIRY[1]):
            continue
        if len(days) > 5:
            cut = (dt.date.fromisoformat(e) - dt.timedelta(days=7)).isoformat()
            days = [d for d in days if d > cut]
        weeks.append((e, days))
    wk3.FUT_MIRROR["CRASH"] = FUT
    return wk3.Sample("CRASH", wk.NIFTY, data, weeks, wk3.Fut("CRASH"), "NIFTY", [data["idx"]])


if __name__ == "__main__":
    out_path = HERE / "results-sn248.json"
    if out_path.exists():
        raise SystemExit("SN248 is scored once")
    if "--data-complete" not in sys.argv:
        raise SystemExit("SN248 waits for the NIFTY Jan-Sep 2020 download to finish (CRASH_TEST_2020.md); then: python sn248.py --data-complete")
    mirror()
    cov = coverage()
    print("SN248 coverage (counts only)", json.dumps(cov), flush=True)
    s = crash_sample()
    res = {"coverage": cov, "weeks": s.W, "legs": {}}
    for lab, hp in LEGS.items():
        tr = wk4.book4(s, "STRADDLE", "M", "settle", hp)
        st = led.wk_month_stats(tr, 2)
        mar = round(sum(t["net"] for t in tr if t["exit_day"][:7] == "2020-03") / 2)
        res["legs"][lab] = {**st, "march_2020": mar, "trades": len(tr)}
        print("SN248", lab, json.dumps(res["legs"][lab]), flush=True)
    for lab, v in (("ref: unhedged straddle kM", ("STRADDLE", "M", "settle", "none", "none")), ("ref: WK-S", ("STRANGLE 0.5", 3, "settle stop1", "none", "none"))):
        tr = wk3.book3(s, *v)
        res["legs"][lab] = {**led.wk_month_stats(tr, 1), "march_2020": round(sum(t["net"] for t in tr if t["exit_day"][:7] == "2020-03"))}
        print("SN248", lab, json.dumps(res["legs"][lab]), flush=True)
    g7 = res["legs"]["Gold v7 leg: WK-H band 0.8"]
    res["pass"] = {"C1_net_positive": g7["net"] > 0, "C2_worst_month_ok": g7["worst_month"] >= -34163, "C3_march_2020": g7["march_2020"],
                   "crash_brake_recommended": g7["march_2020"] < -50000}
    print("SN248 PASS", json.dumps(res["pass"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
