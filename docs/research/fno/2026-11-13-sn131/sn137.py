"""SN137 - adaptive learning (PLAN.md): retrained every month, recent sessions weighted more (half-life 60 sessions);
theta reused from SN132's quarter. 1 lot, Rs 15k / Rs 3k."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn137.json"
    if out_path.exists():
        raise SystemExit("SN137 is scored once")
    data = sm.build()
    pred, _val = run.cached_wf("adaptive", data, run.TARGETS, weight_half_life=60, retrain="month")
    r132 = json.loads((HERE / "results-sn132.json").read_text(encoding="utf-8"))
    res = {}
    for which in ("all days", "gold-free"):
        nets, trades, th = run.policy(data, pred, None, which, thetas=r132[which]["thetas"])
        py = sm.per_year(nets, trades)
        mask = run.submask(data, which) & (data["day"] >= "2024-01-01")
        rmean, r95 = sm.random_null(data, trades, mask)
        res[which] = {"per_year": py, "random_mean": round(rmean), "random_95th": round(r95), "trade_list": trades}
        print(f"=== SN137 {which}: {py} | random 95th {round(r95)}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
