"""SN279 - a transparent vote over seven frozen signals, no fitting (PLAN.md): buy the 10:00 straddle (to 15:10, Rs 3,000
stop) when >= k of: R_today >= 1.332; OR30 in the causal top 20% of the same index's earlier sessions; |gap| >= 0.5%;
pre-holiday; yesterday's range in the causal top 20%; yesterday's close beyond the prior 10 days' high / low; an RBI day.
k in {2, 3}. Per sample (DEV, TEST, EXAM-N, EXAM-S); null = as many random sessions of the same sample, 200 draws."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ds  # noqa: E402

F = {f: k for k, f in enumerate(ds.FEATURES)}


def votes(rows):
    """{day+sample: votes}, causal quantiles within each index over earlier sessions (all samples pooled by date)."""
    out = {}
    hist = {"NIFTY": {"or30": [], "y_range": []}, "SENSEX": {"or30": [], "y_range": []}}
    for r in sorted(rows, key=lambda r: r["day"]):
        x, h = r["x"], hist[r["inst"]]
        v = 0
        v += x[F["r_today"]] >= 1.332
        v += len(h["or30"]) >= 60 and x[F["or30"]] >= np.quantile(h["or30"], 0.8)
        v += x[F["abs_gap"]] >= 0.005
        v += x[F["pre_holiday"]] > 0
        v += len(h["y_range"]) >= 60 and x[F["y_range"]] >= np.quantile(h["y_range"], 0.8)
        v += x[F["breakout10"]] != 0
        v += x[F["rbi"]] > 0
        out[(r["sample"], r["day"])] = int(v)
        h["or30"].append(x[F["or30"]])
        h["y_range"].append(x[F["y_range"]])
    return out


if __name__ == "__main__":
    out = HERE / "results-sn279.json"
    if out.exists():
        raise SystemExit("SN279 is run once")
    rows = ds.load()
    V = votes(rows)
    rng = np.random.default_rng(279)
    res = {"variants": {}}
    for k in (2, 3):
        row = {}
        for n in ds.SAMPLES:
            rs = [r for r in rows if r["sample"] == n]
            sel = [r for r in rs if V[(n, r["day"])] >= k]
            net = sum(r["S205"] for r in sel)
            pool = np.array([r["S205"] for r in rs])
            null = [float(rng.choice(pool, len(sel), replace=False).sum()) for _ in range(200)] if sel else [0.0]
            by = {}
            for r in sel:
                by[r["day"][:4]] = by.get(r["day"][:4], 0) + round(r["S205"])
            row[n] = {"trades": len(sel), "net": round(net), "win_pct": round(100 * float(np.mean([r["S205"] > 0 for r in sel])), 1) if sel else 0.0,
                      "null_p95": round(float(np.percentile(null, 95))), "null_mean": round(float(np.mean(null))),
                      "stress_400": round(sum(r["S400"] for r in sel)), "late_1": round(sum(r["Slate"] for r in sel if r["Slate"] is not None)),
                      "by_year": by}
            print("SN279", f"k={k}", n, json.dumps(row[n]), flush=True)
        pooled = sum(row[n]["net"] for n in ds.SAMPLES if n != "EXAMN") + sum(
            r["S205"] for r in rows if r["sample"] == "EXAMN" and r["day"] >= "2022-01-01" and V[("EXAMN", r["day"])] >= k)
        row["pooled_from_2022"] = round(pooled)
        row["PASS"] = bool(all(row[n]["net"] > 0 for n in ds.SAMPLES) and row["DEV"]["net"] > row["DEV"]["null_p95"]
                           and row["DEV"]["stress_400"] > 0 and row["DEV"]["late_1"] > 0)
        res["variants"][f"k={k}"] = row
        print("SN279", f"k={k}", "pooled from 2022", row["pooled_from_2022"], "PASS", row["PASS"], flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
