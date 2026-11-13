"""SN143 - holding to the close as a learned action (PLAN.md): CE999 / PE999 (buy now, sell at 15:10) walk-forward,
added to phase D's 8 actions; a close trade ends the day's trading. Policy and pass rule as SN132."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

sm, run = pe.sm, pe.run
CLOSE = ["CE999", "PE999"]

if __name__ == "__main__":
    out_path = HERE / "results-sn143.json"
    if out_path.exists():
        raise SystemExit("SN143 is scored once")
    data = sm.build()
    d2 = pe.with_labels(data, {k: v for k, v in pe.close_labels(data).items() if k in CLOSE})
    pb, vb = run.cached_wf("base", data, run.TARGETS)
    pc, vc = run.cached_wf("close", d2, CLOSE)
    preds = {**pb, **pc}
    val = {q: {**vb[q], **vc.get(q, {})} for q in vb}
    res = {}
    for which in ("all days", "gold-free"):
        nets, trades, th = run.policy(d2, preds, val, which)
        py = sm.per_year(nets, trades)
        mask = run.submask(d2, which) & (d2["day"] >= "2024-01-01")
        rmean, r95 = sm.random_null(d2, trades, mask, choices=run.TARGETS + CLOSE)
        res[which] = {"per_year": py, "thetas": th, "random_mean": round(rmean), "random_95th": round(r95),
                      "by_choice": {c: sum(1 for t in trades if t[2] == c) for c in run.TARGETS + CLOSE}, "day_nets": nets}
        res[which]["PASS_partial"] = bool(py["total"] > 0 and py["positive_years"] >= 2 and py["total"] > r95 and py["without_best_5_days"] > 0)
        print(f"=== SN143 {which}: {py} | random 95th {round(r95)} | choices {res[which]['by_choice']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
