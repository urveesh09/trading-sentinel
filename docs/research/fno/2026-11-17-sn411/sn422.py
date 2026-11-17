"""SN422 (own): why Gold's sessions are empty (PLAN.md section 2, frozen at e5cc95b7; details fixed here before any
number). DEPLOYED 2022-26 at Rs 205 (gold.run). Learning only.

Calendar: every NIFTY session in Breeze's daily bars, Jan 3, 2022 - Oct 28, 2026. Gold's day list (its sessions) is the
eligible set; calendar sessions outside it are classed NOT_IN_GOLD (expected: NIFTY expiry days and data gaps), by
weekday. Each Gold session without a Gold trade:
  NO_SIGNAL         no N11 / R0.85 signal that day
  STAND_ASIDE       no N11 / R0.85 signal, but NO_STAND or N10 had one (the stand-aside held it back)
  SIGNAL_NOT_TAKEN  an N11 / R0.85 signal existed and Gold did not enter: LATE (every signal at or after Gold's last
                    entry minute), EXPIRY (every signal on another expiry than the session's), OTHER (day stop, price, ...)
Reported per year; the Gold net those STAND_ASIDE days had in the NO_STAND + R0.85 arm; and the per-session figure of
SN405 recomputed on calendar sessions (Gold-ineligible days count as 0).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold  # noqa: E402

OUT = HERE / "results-sn422.json"
HIST = Path(r"C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite")


def main():
    if OUT.exists():
        raise SystemExit("SN422 is run once")
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True)
    cal = sorted({r[0][:10] for r in con.execute("SELECT datetime FROM candles WHERE underlying='NIFTY' AND kind='daily' AND interval='1day' AND datetime>=? AND datetime<=?",
                                                    ("2022-01-01", "2026-10-28 23:59"))})
    days, log, _ = gold.run(gold.Y2226, gold.DEPLOYED, 205.0)
    nd, nlog, _ = gold.run(gold.Y2226, gold.NO_STAND_R, 205.0)
    gnet = {d: n for d, _w, n, *_ in days}
    ntr = {d: t for d, _w, _n, t, _l in days}
    nsn = {d: n for d, _w, n, *_ in nd}
    sig = collections.defaultdict(list)
    alt = collections.defaultdict(list)
    for y in gold.Y2226:
        for b in gold.DEPLOYED:
            for s in gold.P.stream(y, b):
                sig[s["day"]].append(s)
        for b in ("NO_STAND", "N10"):
            for s in gold.P.stream(y, b):
                alt[s["day"]].append(s)
    exit_min = gold.L.M.EXIT_MIN
    sessions = {}
    expiry_of = {}
    for y in gold.Y2226:
        for S in gold.C.years()[y].ordered():
            expiry_of[S.day] = S.s["expiry"]
    cls = {}
    for d in gnet:
        if ntr.get(d, 0) > 0:
            cls[d] = "GOLD"
            continue
        ss = sig.get(d, [])
        if not ss:
            cls[d] = "STAND_ASIDE" if alt.get(d) else "NO_SIGNAL"
        elif all(s["i"] >= exit_min for s in ss):
            cls[d] = "SIGNAL_NOT_TAKEN:LATE"
        elif all(s["expiry"] != expiry_of.get(d) for s in ss):
            cls[d] = "SIGNAL_NOT_TAKEN:EXPIRY"
        else:
            cls[d] = "SIGNAL_NOT_TAKEN:OTHER"
    outside = [d for d in cal if d not in gnet]
    wd = collections.Counter(dt.date.fromisoformat(d).strftime("%a") for d in outside)
    res = {"calendar_sessions": len(cal), "gold_sessions": len(gnet), "not_in_gold": len(outside), "not_in_gold_by_weekday": dict(wd),
           "classes": dict(collections.Counter(cls.values())),
           "by_year": {y: dict(collections.Counter(c for d, c in cls.items() if d[:4] == y)) for y in gold.Y2226},
           "stand_aside_days_net_in_NO_STAND": round(sum(nsn.get(d, 0.0) for d, c in cls.items() if c == "STAND_ASIDE")),
           "stand_aside_days_winners_in_NO_STAND": sum(1 for d, c in cls.items() if c == "STAND_ASIDE" and nsn.get(d, 0.0) > 0)}
    tot = sum(gnet.values())
    res["per_gold_session"] = round(tot / len(gnet), 1)
    res["per_calendar_session"] = round(tot / len(cal), 1)
    res["empty_share_of_calendar"] = round(1 - sum(1 for c in cls.values() if c == "GOLD") / len(cal), 3)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
