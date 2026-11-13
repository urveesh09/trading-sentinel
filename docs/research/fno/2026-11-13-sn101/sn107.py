"""SN107 - RBI decision days (description; PLAN.md). Against 5 matched non-event days each (same days-to-expiry,
nearest earlier sessions): implied sigma change 09:45 -> 10:30, a straddle bought 10:30 held to 15:10 (strict), and an
ATM option bought 10:30 in the direction of 10:00-10:30 (3-ATR trail, 25% backstop). No consensus archive exists, so
this is price reaction only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402

C, M = pa.C, pa.M
I1030 = 75
RBI = [r["date"] for r in json.loads((M.ROOT / "docs/research/simulation/2026-11-05-fno-n12/round31-calendar.json").read_text(encoding="utf-8"))]
EX = {"stop_k": 3.0, "trail_k": 3.0, "backstop": 0.25}


def measure(S):
    a, b = C.sigma_imp(S, 30), C.sigma_imp(S, I1030)
    got = pa.path(S, I1030)
    strad = None if got is None or got[1] > 15000 else pa.settle(got[2], I1030, 3000.0)[0]
    c = S.F["c"]
    d = 1 if c[I1030] >= c[pa.I10] else -1
    dr = C.comp_one(S, I1030, d, EX, 15000.0, 1, 3000.0)
    return {"iv_change": None if a is None or b is None else b / a - 1, "straddle": strad,
            "directional": None if dr is None else dr[0], "move_1000_1030_pts": float(c[I1030] - c[pa.I10]),
            "abs_move_1030_1510_pts": float(abs(c[pa.FLAT] - c[I1030]))}


if __name__ == "__main__":
    out_path = HERE / "results-sn107.json"
    if out_path.exists():
        raise SystemExit("SN107 is scored once")
    Ys = C.years()
    allS = [S for y in C.YEARS for S in Ys[y].ordered()]
    by_day = {S.day: S for S in allS}
    ev, ctl = [], []
    for d in RBI:
        S = by_day.get(d)
        if S is None:
            continue
        dte = C.sessions_until(d, S.s["expiry"])
        earlier = [x for x in allS if x.day < d and x.day not in RBI and C.sessions_until(x.day, x.s["expiry"]) == dte][-5:]
        ev.append({"day": d, **measure(S)})
        ctl.extend({"day": x.day, "for": d, **measure(x)} for x in earlier)

    def mean(xs, k):
        v = [x[k] for x in xs if x[k] is not None]
        return (round(float(np.mean(v)), 4) if v else None, len(v))
    res = {"events": len(ev), "controls": len(ctl)}
    for k in ("iv_change", "straddle", "directional", "abs_move_1030_1510_pts"):
        res[k] = {"rbi_mean_n": mean(ev, k), "matched_mean_n": mean(ctl, k),
                  "rbi_sum": round(sum(x[k] for x in ev if x[k] is not None), 2)}
        vals = {x["day"]: [x[k]] for x in ev if x[k] is not None}
        if len(vals) >= 5:
            res[k]["rbi_mean_95ci"] = pa.bootstrap_ci(vals, lambda xs: float(np.mean([v[0] for v in xs])))
    print(json.dumps(res, indent=1), flush=True)
    for x in ev:
        print("  ", x)
    out_path.write_text(json.dumps({**res, "event_rows": ev, "control_rows": ctl}, indent=1, default=float), encoding="utf-8")
