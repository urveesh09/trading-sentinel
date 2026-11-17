"""SN277 (walk-forward action-value learner, tau in {0, 300}) and SN278 (walk-forward two-stage classifier, delta in
{0.08, 0.12}) on SN276's pooled dataset (PLAN.md). Each slot's pick = the variant with the better worst fold. The
shuffled-label control is SN280's (it completes these verdicts)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ds  # noqa: E402
import wf  # noqa: E402

if __name__ == "__main__":
    out = HERE / "results-sn277-278.json"
    if out.exists():
        raise SystemExit("SN277-SN278 run once")
    rows = ds.load()
    res = {}
    for slot, fit, pol, params in (("SN277", wf.value_models, wf.policy_value, (0.0, 300.0)),
                                   ("SN278", wf.class_models, wf.policy_class, (0.08, 0.12))):
        res[slot] = {"variants": {}}
        for p in params:
            runs = wf.run(rows, fit, pol, p)
            st = wf.summary(runs)
            st["stress_400"] = wf.summary(runs, "400")["net"]
            st["late_1"] = wf.summary(runs, "late")["net"]
            res[slot]["variants"][str(p)] = st
            print(slot, p, json.dumps(st), flush=True)
        pick = max(res[slot]["variants"], key=lambda k: (res[slot]["variants"][k]["worst_fold"], res[slot]["variants"][k]["net"]))
        ps = res[slot]["variants"][pick]
        res[slot]["pick"] = pick
        res[slot]["gates_without_control"] = {"net>0": ps["net"] > 0, "folds>=6": ps["folds_positive"] >= 6,
                                              "both_indices>0": ps["by_index"]["NIFTY"] > 0 and ps["by_index"]["SENSEX"] > 0,
                                              "400>0": ps["stress_400"] > 0, "late>0": ps["late_1"] > 0}
        print(slot, "PICK", pick, json.dumps(res[slot]["gates_without_control"]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
