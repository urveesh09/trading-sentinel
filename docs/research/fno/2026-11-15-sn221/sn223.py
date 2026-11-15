"""SN223 - trend timing (PLAN.md): yesterday's ADX < 25 / < 20 and the 10-session efficiency ratio < 0.4 on WK-S, WK-G,
the k1 ATM straddle and the straddle kF stop 1.0, on the four seen samples; random-skip null (500 draws, the same
number of skipped weeks per sample as the filter) on the DEV net and on the four-sample min score."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import wk3  # noqa: E402

BASES = {"WK-S": ("STRANGLE 0.5", 3, "settle stop1"), "WK-G": ("STRANGLE 0.5", 3, "gate stop1"),
         "k1 straddle": ("STRADDLE", 1, "settle"), "straddle kF stop1": ("STRADDLE", "F", "settle stop1")}


def null(base, filt, draws=500, seed=223):
    rng = np.random.default_rng(seed)
    full = {n: grid.rows(n, base + ("none", "none")) for n in wk3.SEEN}
    kept = {n: len(grid.rows(n, base + ("none", filt))) for n in wk3.SEEN}
    dev, mins = [], []
    for _ in range(draws):
        sc = {}
        for n in wk3.SEEN:
            r = full[n]
            idx = rng.choice(len(r), size=kept[n], replace=False) if kept[n] < len(r) else np.arange(len(r))
            net = float(sum(r[i][3] for i in idx))
            sc[n] = net / wk3.sample(n).W
            if n == "DEV":
                dev.append(net)
        mins.append(min(sc.values()))
    return {"dev_net_p95": round(float(np.percentile(dev, 95))), "min_score_p95": round(float(np.percentile(mins, 95)), 1)}


if __name__ == "__main__":
    out_path = HERE / "results-sn223.json"
    if out_path.exists():
        raise SystemExit("SN223 is run once")
    T = grid.table()
    res = {}
    for lab, b in BASES.items():
        res[lab] = {}
        for f in wk3.FILTERS:
            v = b + ("none", f)
            row = T[v]
            res[lab][f] = {"rows": row, "min_score": min(row[n]["per_week"] for n in wk3.SEEN)}
            if f != "none":
                res[lab][f]["null"] = null(b, f)
            print("SN223", grid.line(v, row), json.dumps(res[lab][f].get("null", {})), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
