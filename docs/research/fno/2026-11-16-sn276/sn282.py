"""SN282 - SN126-L, the last frozen watch never exam-run (PLAN.md): hot days (proxy-empty: yesterday's daily ADX < 30,
and R_today at 10:00 >= SN95's DEV threshold 1.332, SN196's convention), 10:00-15:00 a fresh 3-minute move >= 2.5 x the
1-minute ATR x sqrt 3, the ATM option in its direction, a 2-ATR index stop or 15 minutes, 25% backstop, at most 5 trades a
day, Rs 15,000 wallet, Rs 3,000 room. The ORIGINAL code (sn126.burst + common.comp_one) runs on NIFTY samples (2022 from
DEV, TEST, EXAM-N); comp_one is NIFTY-only, so EXAM-S is recorded as not ported. 2023-26 is in-sample and reported for
reference with the same fixed-threshold admission."""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
sys.path.insert(0, str(FNO / "2026-11-13-sn121"))
import gl  # noqa: E402
import sn126  # noqa: E402

C = sn126.C
M = C.M
EX = {"stop_k": 2.0, "time": 15, "backstop": 0.25}
THR = 1.332


def day_net(S, f, stress=None, delay=0):
    sig, _x = f(S)
    realized, cnt, free = 0.0, 0, 0
    ex = dict(EX, delay=delay)
    for i in np.flatnonzero(sig):
        if cnt >= 5 or i > 345 or i < free:
            continue
        got = C.comp_one(S, int(i), int(sig[i]), ex, 15000.0, 1, 3000.0 + realized, stress=stress)
        if got is None:
            continue
        realized += got[0]
        cnt += 1
        free = got[1] + 1
        if 3000.0 + realized < 150.0:
            break
    return realized, cnt


if __name__ == "__main__":
    out = HERE / "results-sn282.json"
    if out.exists():
        raise SystemExit("SN282 is run once")
    C.years()
    f = sn126.burst(2.5)
    res = {"not_ported": "EXAM-S (comp_one is NIFTY-only)"}
    gl.SEALED["EXAMN"] = True
    for name, lo, hi in (("2022 (DEV)", "2022-04-01", "2023-01-01"), ("2023-26 (in-sample)", "2023-01-01", gl.TEST_LO),
                         ("TEST", gl.TEST_LO, gl.TEST_HI), ("EXAM-N", "2020-01-01", "2022-04-01")):
        smp = gl.sample("EXAMN") if name == "EXAM-N" else gl.sample("DEV" if lo < gl.TEST_LO else "TEST")
        for d in smp.cal:
            if d not in C._CAL:
                bisect.insort(C._CAL, d)
        days, tot, t400, tlate, trades, by = [], 0.0, 0.0, 0.0, 0, {}
        for d in smp.days:
            if not (lo <= d < hi):
                continue
            a = smp.adx(d)
            if a is None or a >= 30:
                continue
            S = M.Session(smp.s[d])
            r = C.r_today(S, 45)
            if r is None or r < THR:
                continue
            n, k = day_net(S, f)
            if k == 0:
                continue
            days.append(d)
            tot += n
            trades += k
            by[d[:4]] = by.get(d[:4], 0) + round(n)
            t400 += day_net(S, f, stress=400.0)[0]
            tlate += day_net(S, f, delay=1)[0]
        res[name] = {"hot_days_traded": len(days), "trades": trades, "net": round(tot), "stress_400": round(t400), "late_1": round(tlate), "by_year": by}
        print("SN282", name, json.dumps(res[name]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
