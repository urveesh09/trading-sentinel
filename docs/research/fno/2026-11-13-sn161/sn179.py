"""SN179 - robustness of the wage day player (PLAN.md). Development sessions, Rs 15k and Rs 30k growing. Gold v5 at
Rs 400 per lot and with entries one minute late (the lab's own switches), the player without its best 5 days, and a
month bootstrap (12-month years drawn from the development months): chance of a losing month, of a month with >= 10 /
>= 15 wage days, the 5th percentile and median of a year, the chance of a losing year."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import p4  # noqa: E402
import pw  # noqa: E402
import sn176  # noqa: E402

L = pw.L

if __name__ == "__main__":
    out_path = HERE / "results-sn179.json"
    if out_path.exists():
        raise SystemExit("SN179 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    comps = p4.passing_companions()
    rho = p3.rho_table(p3.HAR(ss), ss, lambda d: True)
    w = sn176.watches(set(days))
    res = {}
    for key in ("Rs 15k", "Rs 30k growing (production)"):
        wallet = p4.WALLETS[key][1]
        base = p4.gold(key)
        old = L.STRESS
        L.STRESS = 400.0
        try:
            s400 = p4.gold(key)
        finally:
            L.STRESS = old
        late = p4.gold(key, v={**pw.C.V5, "late": 1})
        player = p4.day_player({**w, **base}, ss, comps, rho, wallet)
        xs = sorted(player.values(), reverse=True)
        res[key] = {"Gold v5 net": round(sum(base.values())), "Gold v5 at Rs 400/lot": round(sum(s400.values())),
                    "Gold v5 one minute late": round(sum(late.values())), "player net": round(sum(xs)),
                    "player without best 5 days": round(sum(xs[5:])),
                    "bootstrap": p4.bootstrap_months(p4.monthly(player, days, 0.10 * wallet))}
        print(f"SN179 {key}: {json.dumps(res[key])}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
