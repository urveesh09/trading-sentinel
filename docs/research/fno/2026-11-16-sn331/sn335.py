"""SN335: index rebalance pressure (PLAN.md frozen at 95287d3f). Event sessions: the last trading session of March and of
September, 2022-2026 (the NIFTY 50 semi-annual changes take effect after them), among the sample's non-expiry sessions.
Measured: the index's 14:00 -> 15:10 return before Gold's cutoff, its rank of |return| among all other sessions' same
window, and its sign. Close the study if the event days' mean rank of |return| is below 0.80 (not in the outer 20%)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
import gl  # noqa: E402

I0, I1 = 285, 355          # 14:00, 15:10

if __name__ == "__main__":
    out_path = HERE / "results-sn335.json"
    if out_path.exists():
        raise SystemExit("SN335 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    cal = smp.cal
    last = {}
    for d in cal:
        if d[5:7] in ("03", "09"):
            last[d[:7]] = max(last.get(d[:7], d), d)
    events = sorted(v for v in last.values() if gl.DEV_LO <= v < gl.TEST_HI)
    rets = {}
    for d in smp.days:
        c = smp.s[d]["index"][3]
        rets[d] = float((c[I1] - c[I0]) / c[I0] * 100)
    others = np.array([abs(v) for d, v in rets.items() if d not in events])
    rows = []
    for d in events:
        if d not in rets:
            rows.append({"day": d, "note": "an expiry session or no data: not in the sample"})
            continue
        rows.append({"day": d, "ret_pct": round(rets[d], 3), "abs_rank": round(float((others < abs(rets[d])).mean()), 3)})
    ranks = [r["abs_rank"] for r in rows if "abs_rank" in r]
    res = {"events": rows, "sessions_compared": len(others), "mean_abs_rank": round(float(np.mean(ranks)), 3) if ranks else None,
           "same_sign_share": round(float(np.mean([r["ret_pct"] > 0 for r in rows if "ret_pct" in r])), 3) if ranks else None}
    res["verdict"] = "CLOSED (no pressure before 15:10)" if not ranks or res["mean_abs_rank"] < 0.80 else "PRESSURE SEEN (forward watch only)"
    print(json.dumps(res, indent=1), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
