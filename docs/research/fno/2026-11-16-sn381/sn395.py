"""SN395: reserve sizing by block bootstrap (PLAN.md section 2, frozen at c6e99cee; details fixed here before any SN395
number).
Input: Gold v5 (deployed signals) on the 2022 - 2026 path from Rs 30k (SN392 / SN389 wiring), Rs 205 and Rs 400: each
session's net divided by that session's wallet; a month's return = the sum over its sessions (58 months).
Paths: 10,000 two-year (24-month) paths per stress, built from contiguous 3-month blocks drawn with replacement (seed
395). Each path: wallet W = Rs 30,000, spare P = Rs 30,000; each month net = return x W; P += net; Gold's growth (progress
since the last step >= W, x1.5, cap 3) funded from P when P - 0.5 W >= 20% of the new W, else deferred; month end:
  PROFIT_ONLY  withdraw everything above one wallet
  SALARY       withdraw Rs 15,750 in full
then if P < 20% of W the owner deposits the difference (outside cash).
Reported per policy and stress: outside cash P50 / P90 / P95 / max; the longest run of months paying nothing (P50 / P90);
the mean share of months paying >= Rs 15,750; the median total withdrawn. Monthly granularity: refills inside a month are
netted (disclosed); the daily ledger results are SN389's.
"""
from __future__ import annotations

import collections
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn389 as S  # noqa: E402

OUT = HERE / "results-sn395.json"
N_PATHS, MONTHS, BLOCK = 10000, 24, 3


def month_returns(stress):
    S.Q.install()
    S.setup()
    row, days, log = S.Q.run(stress)
    by = collections.OrderedDict()
    for d, w, n, _t, _l in days:
        by.setdefault(d[:7], 0.0)
        by[d[:7]] += n / w if w else 0.0
    return list(by.items())


def simulate(rets, policy, rng):
    W, P, prog, steps = 30000.0, 30000.0, 0.0, 0
    outside, paid = 0.0, []
    starts = list(range(0, len(rets) - BLOCK + 1))
    seq = []
    while len(seq) < MONTHS:
        b = rng.choice(starts)
        seq += rets[b:b + BLOCK]
    for r in seq[:MONTHS]:
        net = r * W
        P += net
        prog += net
        while prog >= W and steps < 3:
            dW = 0.5 * W
            if P - dW < 0.2 * 1.5 * W:
                break
            P -= dW
            prog -= W
            W *= 1.5
            steps += 1
        amt = max(0.0, P - W) if policy == "PROFIT_ONLY" else 15750.0
        P -= amt
        paid.append(amt)
        if P < 0.2 * W:
            outside += 0.2 * W - P
            P = 0.2 * W
    run = cur = 0
    for a in paid:
        cur = cur + 1 if a <= 0 else 0
        run = max(run, cur)
    return outside, run, sum(a >= 15750.0 for a in paid) / MONTHS, sum(paid)


def main():
    if OUT.exists():
        raise SystemExit("SN395 is run once")
    res = {}
    for st in (205.0, 400.0):
        mr = month_returns(st)
        rets = [r for _m, r in mr]
        res[f"months @{int(st)}"] = {"n": len(rets), "mean_monthly_return": round(float(np.mean(rets)), 4), "positive": sum(r > 0 for r in rets)}
        for pol in ("PROFIT_ONLY", "SALARY"):
            rng = random.Random(395)
            sims = [simulate(rets, pol, rng) for _ in range(N_PATHS)]
            o = np.array([s[0] for s in sims])
            dry = np.array([s[1] for s in sims])
            res[f"{pol} @{int(st)}"] = {"outside_p50": round(float(np.percentile(o, 50))), "outside_p90": round(float(np.percentile(o, 90))),
                                        "outside_p95": round(float(np.percentile(o, 95))), "outside_max": round(float(o.max())),
                                        "share_paths_no_outside": round(float((o <= 0).mean()), 3),
                                        "dry_p50": float(np.percentile(dry, 50)), "dry_p90": float(np.percentile(dry, 90)),
                                        "share_months_15750": round(float(np.mean([s[2] for s in sims])), 3),
                                        "median_withdrawn_24m": round(float(np.median([s[3] for s in sims])))}
            print(int(st), pol, json.dumps(res[f"{pol} @{int(st)}"]), flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
