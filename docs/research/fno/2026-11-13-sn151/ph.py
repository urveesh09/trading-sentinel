"""Phase F helpers (SN151-SN160): straddle valuation from phase A (pa.path / pa.settle, parity with SN95 proven), causal
expanding quantiles, leave-one-year-out tables, random-admission controls and the common pass rule. Edits nothing."""
from __future__ import annotations

import bisect
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn111"))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import pa  # noqa: E402
import pb  # noqa: E402

C, M = pa.C, pa.M
YEARS = C.YEARS


def sessions():
    Ys = C.years()
    return [S for y in YEARS for S in Ys[y].ordered()]


def r_window(S, i, w):
    c = S.F["c"]
    r = np.diff(np.log(c[max(5, i - w): i + 1]))
    si = C.sigma_imp(S, i)
    if len(r) < 10 or not si:
        return None
    return float(np.std(r)) / si


class CausalQ:
    """Top-q thresholds from values added strictly earlier."""

    def __init__(self, min_n=60):
        self.v, self.min_n = [], min_n

    def thr(self, q):
        if len(self.v) < self.min_n:
            return None
        return float(np.quantile(self.v, 1 - q))

    def add(self, x):
        if x is not None:
            bisect.insort(self.v, x)


def straddle(S, i, stress=205.0, late=0, t_exit=None, room=3000.0, ceiling=15000.0):
    j = i + late
    got = pa.path(S, j, leg_stress=stress)
    if got is None or got[1] > ceiling:
        return None
    return pa.settle(got[2], j, room, t_exit=t_exit, fallback=-2 * stress)[0]


def table(nets):
    """{day: net} -> loyo-ready {year: {net, green, red, trades}}."""
    out = {}
    for y in YEARS:
        xs = [v for d, v in nets.items() if d[:4] == y]
        out[y] = {"net": round(sum(xs)), "green": sum(v > 0 for v in xs), "red": sum(v < 0 for v in xs), "trades": len(xs)}
    return out


def tot(t):
    return sum(t[y]["net"] for y in YEARS)


def random_control(counts, pool, n=2000, seed=151):
    """counts: {year: trades}; pool: {year: [nets of eligible random alternatives]}; totals of random draws."""
    rng = np.random.default_rng(seed)
    tots = []
    for _ in range(n):
        s = 0.0
        for y, k in counts.items():
            p = pool.get(y, [])
            if k and p:
                s += float(np.sum(rng.choice(p, min(k, len(p)), replace=False)))
        tots.append(s)
    return round(float(np.mean(tots))), round(float(np.percentile(tots, 95)))


def verdict(held_nets, held_years, r95, stress400, late1, min_years=3):
    xs = sorted((v for v in held_nets.values() if v), reverse=True)
    total = round(sum(xs))
    out = {"held_out": total, "years": held_years, "trades": len(xs), "without_best_5": round(sum(xs[5:])), "random_95th": r95,
           "stress_400_per_leg": stress400, "late_1min": late1}
    out["PASS"] = bool(total > 0 and sum(v > 0 for v in held_years) >= min_years and total > r95 and out["without_best_5"] > 0
                       and stress400 > 0 and late1 > 0)
    return out
