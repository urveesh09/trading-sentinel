"""SN142 - the cost curve (PLAN.md): SN132's walk-forward predictions re-simulated at stress Rs 0 / 50 / 100 / 150 / 205
per lot (labels and predictions both shifted by the cost change; theta re-chosen nested under each cost)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

sm, run = pe.sm, pe.run

if __name__ == "__main__":
    out_path = HERE / "results-sn142.json"
    if out_path.exists():
        raise SystemExit("SN142 is scored once")
    data = sm.build()
    pred, val = run.cached_wf("base", data, run.TARGETS)
    res = {}
    for s in (0.0, 50.0, 100.0, 150.0, 205.0):
        up = 205.0 - s
        d2 = pe.with_labels(data, {t: (data["Y"][t] + up).astype(np.float32) for t in run.TARGETS})
        p2 = {t: (pred[t] + up).astype(np.float32) for t in run.TARGETS}
        v2 = {q: {t: (vm, (p + up).astype(np.float32)) for t, (vm, p) in vq.items()} for q, vq in val.items()}
        nets, trades, th = run.policy(d2, p2, v2, "all days")
        py = sm.per_year(nets, trades)
        res[f"stress {int(s)}"] = {"per_year": py, "thetas": th}
        print(f"=== SN142 stress Rs {int(s)}: total {py['total']} by year {[py[y]['net'] for y in ('2024', '2025', '2026')]} "
              f"trades {len(trades)} w/o best 5 {py['without_best_5_days']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
