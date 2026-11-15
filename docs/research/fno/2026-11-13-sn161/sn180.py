"""SN180 - the starting price grid (PLAN.md). Development sessions. The wage day player (SN176's ledger) for Rs 15k,
Rs 30k fixed, Rs 30k growing, Rs 50k growing and Rs 1 lakh growing: net, wage days a month (wage = 10% of the start),
the worst month, refills; and SN177's salary account for a Rs 1,500 wage paid from that player's ledger at a fixed
wallet: the smallest start that never misses."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import p4  # noqa: E402
import pw  # noqa: E402
import sn176  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn180.json"
    if out_path.exists():
        raise SystemExit("SN180 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    comps = p4.passing_companions()
    rho = p3.rho_table(p3.HAR(ss), ss, lambda d: True)
    w = sn176.watches(set(days))
    res = {}
    for key, (_n, wallet, mode, _cap) in p4.WALLETS.items():
        player = p4.day_player({**w, **p4.gold(key)}, ss, comps, rho, wallet)
        s = pw.wage_stats(player, days, wallet)
        row = {"net": s["net"], "wage_days_per_month": s["month"]["wage_days_mean"], "month_median": s["month"]["median"],
               "month_worst": s["month"]["worst"], "refilled": round(-sum(v for v in player.values() if v < 0)),
               "net_pct_of_start": round(s["net"] / wallet * 100, 1)}
        if mode == "one" or _cap == 0:
            row["salary 1500: min start never short"] = p4.min_start(player, days, wallet, 1500.0)
        res[key] = row
        print(f"SN180 {key}: {json.dumps(row)}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
