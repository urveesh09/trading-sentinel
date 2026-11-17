"""SN280 - controls and robustness for the best of SN277-SN279 by pooled out-of-sample net (PLAN.md). The best was
SN279 k=3 (pooled from 2022: -974; SN277 tau 0: -128,556; SN278 delta 0.12: -134,370). The vote has no fitted labels,
so the shuffled-label control does not apply; its controls: as many random sessions per sample (pooled from 2022, 200
draws), Rs 400, one minute late, without the best 10 days."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ds  # noqa: E402
import sn279  # noqa: E402

if __name__ == "__main__":
    out = HERE / "results-sn280.json"
    if out.exists():
        raise SystemExit("SN280 is run once")
    rows = [r for r in ds.load() if r["day"] >= "2022-01-01"]
    V = sn279.votes(ds.load())
    sel = [r for r in rows if V[(r["sample"], r["day"])] >= 3]
    rng = np.random.default_rng(280)
    null = []
    for _ in range(200):
        tot = 0.0
        for n in ds.SAMPLES:
            pool = [r["S205"] for r in rows if r["sample"] == n]
            k = sum(r["sample"] == n for r in sel)
            if k:
                tot += float(rng.choice(pool, k, replace=False).sum())
        null.append(tot)
    nets = np.sort([r["S205"] for r in sel])[::-1]
    res = {"pick": "SN279 k=3", "trades": len(sel), "net": round(float(nets.sum())), "null_mean": round(float(np.mean(null))),
           "null_p95": round(float(np.percentile(null, 95))), "stress_400": round(sum(r["S400"] for r in sel)),
           "late_1": round(sum(r["Slate"] for r in sel if r["Slate"] is not None)), "without_best10": round(float(nets[10:].sum())),
           "by_index": {i: round(sum(r["S205"] for r in sel if r["inst"] == i)) for i in ("NIFTY", "SENSEX")}}
    res["PASS"] = bool(res["net"] > 0 and res["net"] > res["null_p95"] and res["stress_400"] > 0 and res["late_1"] > 0)
    print("SN280", json.dumps(res), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
