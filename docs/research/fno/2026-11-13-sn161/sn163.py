"""SN163 - the coin-flip wage trader, in full (PLAN.md). Development sessions. Random entry minute (09:30-14:30) and
side, ATM, max lots at Rs 15k (and one lot for the main cell), wage lock, day limit Rs 3,000 (20%). Grid: wage
{Rs 750, Rs 1,500} x stop per trade {Rs 750, Rs 1,500, Rs 3,000} x attempts {1, 2, 3}; 20 random replays each.
Wage-day share against net: the null every later candidate must beat."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

DRAWS = 20
WALLET = 15000.0


def replay(sessions, wage, stop, attempts, draw, max_lots=None, offset=0, stress=pw.STRESS):
    out = {}
    for S in sessions:
        net, trades = pw.play(S, pw.random_picker(pw.seed_of(S.day, draw), offset), WALLET, wage, stop, attempts,
                              day_limit=3000.0, max_lots=max_lots, stress=stress)
        if trades:
            out[S.day] = net
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn163.json"
    if out_path.exists():
        raise SystemExit("SN163 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    res = {}
    for wage, stop, att in itertools.product((750.0, 1500.0), (750.0, 1500.0, 3000.0), (1, 2, 3)):
        stats = [pw.wage_stats(replay(ss, wage, stop, att, k), days, WALLET, wage) for k in range(DRAWS)]
        key = f"wage {wage:.0f} stop {stop:.0f} attempts {att}"
        res[key] = {"wage_share": round(float(np.mean([s["wage_share"] for s in stats])), 4),
                    "red_share": round(float(np.mean([s["red_days"] / s["sessions"] for s in stats])), 4),
                    "net_mean": round(float(np.mean([s["net"] for s in stats]))),
                    "net_p5": round(float(np.percentile([s["net"] for s in stats], 5))),
                    "net_p95": round(float(np.percentile([s["net"] for s in stats], 95))),
                    "month_mean": round(float(np.mean([s["month"]["mean"] for s in stats]))),
                    "wage_days_per_month": round(float(np.mean([s["month"]["wage_days_mean"] for s in stats])), 1),
                    "by_year_net": {y: round(float(np.mean([s["by_year"][y]["net"] for s in stats]))) for y in pw.DEV_YEARS}}
        print(f"SN163 {key}: {json.dumps(res[key])}", flush=True)
    one = [pw.wage_stats(replay(ss, 1500.0, 1500.0, 1, k, max_lots=1), days, WALLET, 1500.0) for k in range(DRAWS)]
    res["one lot: wage 1500 stop 1500 attempts 1"] = {"wage_share": round(float(np.mean([s["wage_share"] for s in one])), 4),
                                                      "net_mean": round(float(np.mean([s["net"] for s in one])))}
    zero = [pw.wage_stats(replay(ss, 1500.0, 1500.0, 1, k, stress=0.0), days, WALLET, 1500.0) for k in range(DRAWS)]
    res["zero stress: wage 1500 stop 1500 attempts 1"] = {"wage_share": round(float(np.mean([s["wage_share"] for s in zero])), 4),
                                                          "net_mean": round(float(np.mean([s["net"] for s in zero])))}
    print("SN163 extra", json.dumps({k: res[k] for k in list(res)[-2:]}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
