"""SN226 - the futures delta hedge (PLAN.md): H1 / H15 / H15x2 (per option lot) vs no hedge, x straddle / strangles x k x
exits, on the four seen samples; futures orders and hedge costs paid; how many variants the hedge lifts on the min score."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import wk3  # noqa: E402

STRS = ("STRADDLE", "STRANGLE 0.25", "STRANGLE 0.5")


def ms(row):
    return min(row[n]["per_week"] for n in wk3.SEEN)


if __name__ == "__main__":
    out_path = HERE / "results-sn226.json"
    if out_path.exists():
        raise SystemExit("SN226 is run once")
    T = grid.table()
    res = {"rows": {}, "lift": {}}
    for st in STRS:
        for k in wk3.KS:
            for ex in wk3.EXITS:
                if k == 1 and ex not in ("settle", "settle stop1"):
                    continue
                for h in wk3.HEDGES:
                    v = (st, k, ex, h, "none")
                    row = T[v]
                    res["rows"][wk3.vname(v)] = {"rows": row, "min_score": ms(row), "positive_samples": sum(row[n]["net"] > 0 for n in wk3.SEEN)}
                    extra = "" if h == "none" else " orders/wk DEV %.1f costs DEV %d" % (row["DEV"]["orders"] / max(1, row["DEV"]["trades"]), row["DEV"]["hedge_costs"])
                    print("SN226", grid.line(v, row), "pos", res["rows"][wk3.vname(v)]["positive_samples"], extra, flush=True)
    for h in ("H1", "H15", "H15x2"):
        better = tot = 0
        for st in STRS:
            for k in wk3.KS:
                for ex in wk3.EXITS:
                    if k == 1 and ex not in ("settle", "settle stop1"):
                        continue
                    a, b = T[(st, k, ex, "none", "none")], T[(st, k, ex, h, "none")]
                    tot += 1
                    better += int(ms(b) > ms(a))
        res["lift"][h] = {"variants": tot, "min_score_better": better}
        print("SN226 lift", h, json.dumps(res["lift"][h]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")  # post-run fix: numpy ints
