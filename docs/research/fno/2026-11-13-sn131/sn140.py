"""SN140 - honesty checks for each of SN132 / SN137 / SN138 (PLAN.md): Rs 400 stress, entries 1 minute late, by
quarter; the shuffled-label control (SN132's engine); the count of everything tried."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402
import sn138  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn140.json"
    if out_path.exists():
        raise SystemExit("SN140 is scored once")
    data = sm.build()
    pb, vb, pa_, pe = sn138.ensemble(data)
    r132 = json.loads((HERE / "results-sn132.json").read_text(encoding="utf-8"))
    engines = {"SN132 base": (pb, vb, None), "SN137 adaptive": (pa_, None, r132["all days"]["thetas"]), "SN138 ensemble": (pe, vb, None)}
    res = {"engines": {}}
    for name, (p, v, th) in engines.items():
        base, tb, chosen = run.policy(data, p, v, "all days", thetas=th)
        s400, t4, _ = run.policy(data, p, v, "all days", thetas=chosen, stress_shift=195.0)
        late, tl, _ = run.policy(data, p, v, "all days", thetas=chosen, late=True)
        byq = {q0: round(sum(x for d, x in base.items() if q0 <= d < q1)) for q0, q1 in zip(sm.QUARTERS, sm.QUARTERS[1:])}
        res["engines"][name] = {"base": sm.per_year(base, tb)["total"], "stress_400": sm.per_year(s400, t4)["total"],
                                "late_1min": sm.per_year(late, tl)["total"], "by_quarter": byq,
                                "positive_quarters": sum(x > 0 for x in byq.values())}
        print(f"=== SN140 {name}: {res['engines'][name]}", flush=True)
    ps, vs = run.cached_wf("shuffled", data, run.TARGETS, shuffle=True, seed=140)
    sh, ts, _ = run.policy(data, ps, vs, "all days")
    res["shuffled_label_control"] = sm.per_year(sh, ts)
    print("shuffled-label control", res["shuffled_label_control"], flush=True)
    res["trials_note"] = ("SN131-SN140: 1 feature set, 1 model family with fixed parameters, 8 targets, 6 thresholds chosen "
                          "nested, 3 engines (base / adaptive / ensemble), 2 day sets, 1 sizing rule, 1 exit model, 1 event "
                          "model, 1 second-level and 1 order-book model.")
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
