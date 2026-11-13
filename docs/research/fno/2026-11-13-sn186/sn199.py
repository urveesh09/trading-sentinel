"""SN199 - the leg's wallet and growth (PLAN.md). Development sessions, Gold's empty days. The SN197 leg's
per-lot day nets (SN95-L and SN171 at one lot of each leg) scaled to a leg wallet: lots = floor(W / per-lot wallet)
(Rs 15k per straddle / strangle lot), W in {Rs 15k, 30k, 50k, 1.5 lakh}; fixed or growing (+50% after the leg's profit
equals its wallet, at most 3 steps); losing days refilled. Net, refills, worst day and month, days at a fixed
Rs 1,000 / 1,500 goal."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import sn197  # noqa: E402

pw, p3, pa, C = pe.pw, pe.p3, pe.pa, pe.C

if __name__ == "__main__":
    out_path = HERE / "results-sn199.json"
    if out_path.exists():
        raise SystemExit("SN199 is scored once")
    devS = pw.dev_sessions()
    days = [S.day for S in devS]
    empty = pe.empty_sessions()
    r126 = json.loads((C.FNO / "2026-11-13-sn121" / "results-sn126.json").read_text(encoding="utf-8"))
    s126 = {d: v for d, v in r126["heldout_day_nets"].items() if v}
    rho = p3.rho_table(p3.HAR(devS), devS, lambda d: True)
    per_lot = sn197.leg_nets(empty, 15000.0, rho, pa.admission(), s126)
    res = {"per_lot_trades": len(per_lot), "per_lot_net": round(sum(per_lot.values()))}
    for W0 in (15000.0, 30000.0, 50000.0, 150000.0):
        for grow in (False, True):
            W, steps, earned, ledger = W0, 0, 0.0, {}
            for d in days:
                if d not in per_lot:
                    continue
                lots = max(1, int(W // 15000))
                n = per_lot[d] * lots
                ledger[d] = n
                earned += n
                if grow and steps < 3 and earned >= W:
                    W, earned, steps = W * 1.5, 0.0, steps + 1
            key = f"Rs {W0:,.0f} {'growing' if grow else 'fixed'}"
            res[key] = {**{k: v for k, v in pe.goal_stats(ledger, days, 1000.0).items() if k in ("net", "trade_days", "red_days", "worst_day", "month_worst", "by_year")},
                        "refilled": round(-sum(v for v in ledger.values() if v < 0)), "final_wallet": W}
            res[key]["goal_days_1000"] = pe.goal_stats(ledger, days, 1000.0)["goal_days"]
            res[key]["goal_days_1500"] = pe.goal_stats(ledger, days, 1500.0)["goal_days"]
            print(f"SN199 {key}: {json.dumps(res[key])}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
