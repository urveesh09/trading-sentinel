"""SN132 - the smart entry policy (PLAN.md): the walk-forward predictions as one policy, 1 lot, Rs 15k / Rs 3k room,
all days (primary) and Gold-free days; random-policy control. Robustness and the shuffled control are in SN140."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn132.json"
    if out_path.exists():
        raise SystemExit("SN132 is scored once")
    data = sm.build()
    pred, val = run.cached_wf("base", data, run.TARGETS)
    res = {}
    for which in ("all days", "gold-free"):
        nets, trades, th = run.policy(data, pred, val, which)
        py = sm.per_year(nets, trades)
        mask = run.submask(data, which) & (data["day"] >= "2024-01-01")
        rmean, r95 = sm.random_null(data, trades, mask)
        res[which] = {"per_year": py, "thetas": th, "random_mean": round(rmean), "random_95th": round(r95), "trades": len(trades),
                      "by_choice": {c: sum(1 for t in trades if t[2] == c) for c in run.TARGETS}, "trade_list": trades}
        print(f"=== SN132 {which}: {py} | thetas {th} | random mean {round(rmean)} 95th {round(r95)} | choices {res[which]['by_choice']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
