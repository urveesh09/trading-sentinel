"""SN344: the minute-level reversal, including 2019 (PLAN.md frozen at 95287d3f before any number).

SN318's held break (a completed minute closing outside the 3 completed one-minute bars' range, the previous minute not,
the next minute also outside); the failure = a later minute, within 10 minutes of the break, closing back inside the
level; buy the OPPOSITE at-the-money option at the following minute (modelled ask, gl.Pos), hold 15 minutes with a Rs 3,000
stop (gl.walk); decisions 09:30-14:30; non-expiry sessions; one position at a time; one lot of 65; Zerodha charges +
Rs 205 (Rs 400). Control: 200 random-clock books with the same trades per session and sides.
Samples: DEV, TEST, 2019 Q3, 2019 Q4 (sn316's sealed 2019 copy). Pass: net > 0 at Rs 205 and Rs 400 in both 2019 quarters
and above the random median at Rs 205."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn316"))
import sn318 as B  # noqa: E402

gl = B.gl


def events(s):
    c, h, l = s["index"][3], s["index"][1], s["index"][2]
    out, prev = [], 0
    for m in range(3, 320):
        hi, lo = float(np.max(h[m - 3:m])), float(np.min(l[m - 3:m]))
        sg = 1 if c[m] > hi else (-1 if c[m] < lo else 0)
        fresh = sg != 0 and sg != prev
        prev = sg
        if not fresh or m < 15:
            continue
        lvl = hi if sg > 0 else lo
        if sg * (c[m + 1] - lvl) <= 0:
            continue
        k = next((k for k in range(m + 2, min(m + 11, 318)) if sg * (c[k] - lvl) < 0), None)
        if k is not None and k + 1 <= 317:
            out.append((k + 1, -sg))           # buy against the failed break
    return out


B.events = events                         # SN318's books, nulls and reports, on the reversal events


if __name__ == "__main__":
    out_path = HERE / "results-sn344.json"
    if out_path.exists():
        raise SystemExit("SN344 is run once")
    res = {}
    for name in ("DEV", "TEST"):
        smp = gl.sample(name)
        for st in (205.0, 400.0):
            res[f"{name} @{int(st)}"] = B.report(smp, smp.days, st, with_null=(st == 205.0))
            print("SN344", name, int(st), json.dumps(res[f"{name} @{int(st)}"]), flush=True)
    smp = B.n2019()
    quarters = {"2019Q3": [d for d in smp.days if d < "2019-10-01"], "2019Q4": [d for d in smp.days if d >= "2019-10-01"]}
    for q, days in quarters.items():
        for st in (205.0, 400.0):
            res[f"{q} @{int(st)}"] = B.report(smp, days, st, with_null=(st == 205.0))
            print("SN344", q, int(st), json.dumps(res[f"{q} @{int(st)}"]), flush=True)
    ok = all(res[f"{q} @205"]["net"] > 0 and res[f"{q} @400"]["net"] > 0 and res[f"{q} @205"]["net"] > res[f"{q} @205"]["random_median"]
             for q in quarters)
    res["verdict_2019"] = "PASS" if ok else "FAIL"
    print("SN344 verdict", res["verdict_2019"], flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
