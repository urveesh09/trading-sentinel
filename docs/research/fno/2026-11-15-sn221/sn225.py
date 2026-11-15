"""SN225 - far wings (PLAN.md): IC 0.5/1.5 and IF 2.0 x k x exits (no hedge, no filter) on the four seen samples; the
share of weeks whose wing had to be clamped inward (E5 needs >= 80% unclamped on DEV)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import wk3  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn225.json"
    if out_path.exists():
        raise SystemExit("SN225 is run once")
    T = grid.table()
    res = {}
    for st in ("IC 0.5/1.5", "IF 2.0"):
        for k in wk3.KS:
            for ex in wk3.EXITS:
                if k == 1 and ex not in ("settle", "settle stop1"):
                    continue
                v = (st, k, ex, "none", "none")
                row = T[v]
                unclamped = {n: round(1 - row[n]["clamped"] / row[n]["trades"], 3) if row[n]["trades"] else None for n in wk3.SEEN}
                res[wk3.vname(v)] = {"rows": row, "unclamped_share": unclamped, "min_score": min(row[n]["per_week"] for n in wk3.SEEN),
                                     "positive_samples": sum(row[n]["net"] > 0 for n in wk3.SEEN)}
                print("SN225", grid.line(v, row), "unclamped", json.dumps(unclamped), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
