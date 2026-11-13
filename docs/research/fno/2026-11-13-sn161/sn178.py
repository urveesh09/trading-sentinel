"""SN178 - sweep vs compound (PLAN.md). Development sessions. Gold v5 from Rs 30k: compounding (growing, stop 3,
the production rule) against a fixed Rs 30k wallet whose profits are taken out each month (losses refilled from
outside, as SN Gold's ledger). For each: total earned, what a monthly withdrawal would look like (median, worst, share
of months with something to take), the wallet at the end. Same for Rs 15k (one lot fixed vs growing)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p4  # noqa: E402
import pw  # noqa: E402

p4.WALLETS["Rs 15k growing"] = ("G3 (Gold)", 15000.0, "grow", 3)

if __name__ == "__main__":
    out_path = HERE / "results-sn178.json"
    if out_path.exists():
        raise SystemExit("SN178 is scored once")
    days = [S.day for S in pw.dev_sessions()]
    res = {}
    for name, key in (("Rs 30k fixed, monthly sweep", "Rs 30k fixed"), ("Rs 30k compounding (production)", "Rs 30k growing (production)"),
                      ("Rs 15k fixed, monthly sweep", "Rs 15k"), ("Rs 15k compounding", "Rs 15k growing")):
        g = p4.gold(key)
        m = p4.monthly(g, days, 0.0)
        nets = np.array([v["net"] for v in m.values()])
        res[name] = {"total": round(float(nets.sum())), "month_median": round(float(np.median(nets))), "month_worst": round(float(nets.min())),
                     "months_positive": round(float((nets > 0).mean()), 3), "month_mean": round(float(nets.mean())),
                     "refilled": round(-float(sum(v for v in g.values() if v < 0)))}
        print(f"SN178 {name}: {json.dumps(res[name])}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
