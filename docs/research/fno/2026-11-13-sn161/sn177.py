"""SN177 - the salary account (PLAN.md). Development sessions 2023-01 .. 2026-08-19. One cash account trades Gold v5
at a fixed wallet (Rs 15k one lot, or Rs 30k fixed) plus the forward watches on Gold's empty days; every trading loss
is paid from the account (the refill) and a fixed wage is paid each session (Rs 750 / 1,000 / 1,500) while the
account stays at or above the trading wallet. The smallest starting capital that never misses a wage, and for starts of
Rs 15k / 30k / 50k / 1 lakh / 2 lakh / 3 lakh: wage paid a month, short days and months, the lowest balance.
Sessions are the lab's non-expiry days (about 4 a week), so a calendar month pays about 16-17 wages here."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p4  # noqa: E402
import pw  # noqa: E402
import sn176  # noqa: E402

STARTS = (15000.0, 30000.0, 50000.0, 100000.0, 200000.0, 300000.0)
WAGES = (750.0, 1000.0, 1500.0)

if __name__ == "__main__":
    out_path = HERE / "results-sn177.json"
    if out_path.exists():
        raise SystemExit("SN177 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    w = sn176.watches(set(days))
    res = {}
    for key in ("Rs 15k", "Rs 30k fixed"):
        wallet = p4.WALLETS[key][1]
        g = p4.gold(key)
        for name, dn in (("Gold v5", g), ("Gold v5 + forward watches", {**w, **g})):
            row = {"trading_net": round(sum(dn.values()))}
            for wage in WAGES:
                row[f"wage {wage:.0f}"] = {"min_start_never_short": p4.min_start(dn, days, wallet, wage),
                                           "by_start": {f"{s:,.0f}": p4.salary(dn, days, s, wallet, wage) for s in STARTS if s >= wallet}}
            res[f"{key} | {name}"] = row
            print(f"SN177 {key} | {name}: net {row['trading_net']:,} | min start never short: " +
                  ", ".join(f"wage {wg:.0f} -> {row[f'wage {wg:.0f}']['min_start_never_short']}" for wg in WAGES), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
