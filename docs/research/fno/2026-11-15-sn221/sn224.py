"""SN224 - exposure (PLAN.md): entry day k in {1, 2, 3, F, M} x straddle / strangles x settle / settle stop 1 / gate /
gate stop 1 (no hedge, no filter) on the four seen samples, and the weekend-gap anatomy: for every held unhedged
position (structure x k, settle, no stop), the 15:15-to-15:15 mark changes summed over intervals that span a weekend
or holiday vs ordinary weekday intervals and the expiry-day leg (last 15:15 mark -> settlement)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import wk3  # noqa: E402

STRS = ("STRADDLE", "STRANGLE 0.25", "STRANGLE 0.5")
EXS = ("settle", "settle stop1", "gate", "gate stop1")


def anatomy(name, struct, k):
    s = wk3.sample(name)
    out = {"weekend": 0.0, "weekend_n": 0, "weekday": 0.0, "weekday_n": 0, "expiry_day": 0.0, "entry_costs": 0.0}
    for e, days in s.weeks:
        t = wk3.base_trade(s, e, days, struct, k)
        if t is None:
            continue
        ms = sorted(t["marks"].items())
        out["entry_costs"] += ms[0][1]
        for (d1, v1), (d2, v2) in zip(ms, ms[1:]):
            if d2 == e:
                out["expiry_day"] += v2 - v1
                continue
            gap = (dt.date.fromisoformat(d2) - dt.date.fromisoformat(d1)).days
            key = "weekend" if gap > 1 else "weekday"
            out[key] += v2 - v1
            out[key + "_n"] += 1
    return {k_: round(v) if isinstance(v, float) else v for k_, v in out.items()}


if __name__ == "__main__":
    out_path = HERE / "results-sn224.json"
    if out_path.exists():
        raise SystemExit("SN224 is run once")
    T = grid.table()
    res = {"grid": {}, "anatomy": {}}
    for st in STRS:
        for k in wk3.KS:
            for ex in EXS:
                if k == 1 and ex.startswith("gate"):
                    continue
                v = (st, k, ex, "none", "none")
                res["grid"][wk3.vname(v)] = {"rows": T[v], "min_score": min(T[v][n]["per_week"] for n in wk3.SEEN),
                                             "positive_samples": sum(T[v][n]["net"] > 0 for n in wk3.SEEN)}
                print("SN224", grid.line(v, T[v]), "pos", res["grid"][wk3.vname(v)]["positive_samples"], flush=True)
    for st in STRS:
        for k in wk3.KS:
            res["anatomy"][f"{st} k{k}"] = {n: anatomy(n, st, k) for n in wk3.SEEN}
            print("SN224 anatomy", st, f"k{k}", json.dumps(res["anatomy"][f"{st} k{k}"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
