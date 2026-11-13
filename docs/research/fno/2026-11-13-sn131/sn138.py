"""SN138 - ensemble (PLAN.md): the average of SN132's and SN137's predictions as one policy; theta nested on the base
engine's validation, 1 lot, Rs 15k / Rs 3k."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402


def ensemble(data):
    pb, vb = run.cached_wf("base", data, run.TARGETS)
    pa_, _va = run.cached_wf("adaptive", data, run.TARGETS, weight_half_life=60, retrain="month")
    pe = {t: np.nanmean(np.vstack([pb[t], pa_[t]]), axis=0).astype(np.float32) for t in run.TARGETS}
    return pb, vb, pa_, pe


if __name__ == "__main__":
    out_path = HERE / "results-sn138.json"
    if out_path.exists():
        raise SystemExit("SN138 is scored once")
    data = sm.build()
    _pb, vb, _pa, pe = ensemble(data)
    res = {}
    for which in ("all days", "gold-free"):
        nets, trades, th = run.policy(data, pe, vb, which)
        py = sm.per_year(nets, trades)
        mask = run.submask(data, which) & (data["day"] >= "2024-01-01")
        rmean, r95 = sm.random_null(data, trades, mask)
        res[which] = {"per_year": py, "thetas": th, "random_mean": round(rmean), "random_95th": round(r95), "trade_list": trades}
        print(f"=== SN138 {which}: {py} | random 95th {round(r95)}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
