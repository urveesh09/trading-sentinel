"""SN197 - the empty-day leg ledger (PLAN.md). Development sessions. No SN187-SN194 pick passed development, so the
leg is the existing forward watches on Gold's empty days, one a day in this order: SN95-L (10:00 straddle on causal hot
days, Rs 15k), SN126-L (held-out hot-day bursts), SN171 (HAR forecast / implied >= 1.1: 1-OTM strangle at Rs 15k, ATM
straddle at Rs 30k+). Gold v5 first (Rs 15k and Rs 30k growing). The leg alone and Gold + leg: days at a fixed
Rs 1,000 / Rs 1,500 goal, red days, worst day and month, per year."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

pw, p3, pa, pb, C, p4 = pe.pw, pe.p3, pe.pa, pe.pb, pe.C, pe.p4


def leg_nets(sessions, wallet, rho, adm, s126):
    out = {}
    for S in sessions:
        n = None
        if adm.get((S.day, "10:00", "R_today", 0.2, "top"), False):
            got = pa.path(S, pa.I10)
            if got is not None and got[1] <= 15000.0:
                n = pb.net(got)
        if not n and S.day in s126:
            n = s126[S.day]
        if not n and rho.get(S.day, 0) >= 1.1:
            if wallet >= 30000.0:
                n = p3.structure(S, p3.I1000, "straddle", 30000.0, 6000.0)
            else:
                n = p3.structure(S, p3.I1000, "strangle1", 15000.0, 3000.0)
        if n:
            out[S.day] = n
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn197.json"
    if out_path.exists():
        raise SystemExit("SN197 is scored once")
    devS = pw.dev_sessions()
    days = [S.day for S in devS]
    empty = pe.empty_sessions()
    adm = pa.admission()
    r126 = json.loads((C.FNO / "2026-11-13-sn121" / "results-sn126.json").read_text(encoding="utf-8"))
    s126 = {d: v for d, v in r126["heldout_day_nets"].items() if v}
    rho = p3.rho_table(p3.HAR(devS), devS, lambda d: True)
    res = {"empty_days": len(empty)}
    for key, wallet in (("Rs 15k", 15000.0), ("Rs 30k growing (production)", 30000.0)):
        leg = leg_nets(empty, wallet, rho, adm, s126)
        gold = p4.gold(key)
        both = {**leg, **gold}
        res[key] = {}
        for goal in (1000.0, 1500.0):
            res[key][f"leg alone, goal {goal:.0f}"] = pe.goal_stats(leg, days, goal)
            res[key][f"Gold + leg, goal {goal:.0f}"] = pe.goal_stats(both, days, goal)
            res[key][f"Gold alone, goal {goal:.0f}"] = pe.goal_stats(gold, days, goal)
        print(f"SN197 {key}: " + json.dumps({k: {x: v[x] for x in ("net", "trade_days", "goal_days", "goal_days_per_month", "red_days", "month_worst")}
                                             for k, v in res[key].items()}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
