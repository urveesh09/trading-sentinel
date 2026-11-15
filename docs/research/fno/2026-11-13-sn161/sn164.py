"""SN164 - cheaper contracts (PLAN.md). Development sessions. Wage Rs 1,500, stop Rs 1,500, one attempt, day limit
Rs 3,000, max lots at Rs 15k. Shapes: ATM, 1 / 2 / 3 / 4 strikes out of the money, and a debit spread (buy ATM, sell
2 strikes further; Rs 100 per leg-lot). Entries: random (20 replays) and the 15-minute range break (the 'momentum'
entry). Single legs also at Rs 100 per lot (cheap premiums have smaller real spreads, SN109). NIFTY futures: one lot
is ~Rs 16 lakh of index; its margin is far above Rs 15k, so no futures shape fits the wallet."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

DRAWS = 20
WALLET, WAGE, STOP = 15000.0, 1500.0, 1500.0


def spread_shape(S, i, opt, strike, wallet, tgt, st):
    return pw.spread_trade(S, i, 1 if opt == "CE" else -1, wallet, width=2, target=tgt, stop=st)


def run(ss, picker_for, offset, stress, shape=None):
    out, lots = {}, []
    for S in ss:
        net, trades = pw.play(S, picker_for(S), WALLET, WAGE, STOP, 1, day_limit=3000.0, stress=stress, shape=shape)
        if trades:
            out[S.day] = net
            lots.append(trades[0]["lots"])
    return out, lots


if __name__ == "__main__":
    out_path = HERE / "results-sn164.json"
    if out_path.exists():
        raise SystemExit("SN164 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    res = {}
    shapes = [(f"OTM {k}" if k else "ATM", k, None) for k in range(5)] + [("debit spread ATM/+2", 0, spread_shape)]
    for name, off, shape in shapes:
        for stress in ((pw.STRESS, 100.0) if shape is None else (pw.STRESS,)):
            tag = f"{name} @ {stress:.0f}/lot" if shape is None else f"{name} @ 100/leg-lot"
            rnd = []
            lots_all = []
            for k in range(DRAWS):
                dn, lots = run(ss, lambda S, k=k: pw.random_picker(pw.seed_of(S.day, k), off), off, stress, shape)
                rnd.append(pw.wage_stats(dn, days, WALLET, WAGE))
                lots_all += lots
            mom_dn, mom_lots = run(ss, lambda S: pw.range_break_picker(15, off), off, stress, shape)
            mom = pw.wage_stats(mom_dn, days, WALLET, WAGE)
            res[tag] = {"random": {"wage_share": round(float(np.mean([s["wage_share"] for s in rnd])), 4),
                                   "net_mean": round(float(np.mean([s["net"] for s in rnd]))),
                                   "net_p95": round(float(np.percentile([s["net"] for s in rnd], 95))),
                                   "trade_days": round(float(np.mean([s["trade_days"] for s in rnd]))),
                                   "mean_lots": round(float(np.mean(lots_all)), 2) if lots_all else None},
                        "range break": {"wage_share": mom["wage_share"], "net": mom["net"], "trade_days": mom["trade_days"],
                                        "by_year": {y: v["net"] for y, v in mom["by_year"].items()},
                                        "mean_lots": round(float(np.mean(mom_lots)), 2) if mom_lots else None}}
            print(f"SN164 {tag}: {json.dumps(res[tag])}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
