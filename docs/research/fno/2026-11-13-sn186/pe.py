"""SN186-SN200 shared helpers (PLAN.md). Built on SN161's toolkit (pw: fills, charges, wage lock; p3: HAR forecast,
LOYO; p4: Gold v5 day nets). Adds: Gold's empty days, two-leg and iron-fly minute valuations, a fixed-goal day and the
empty-day null."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn161"))
import pw  # noqa: E402
import p3  # noqa: E402
import p4  # noqa: E402

C, M, pa, pb = pw.C, pw.M, pw.pa, pw.pb
LOCAL = HERE / "_local"
YEARS = pw.DEV_YEARS
LEG_STRESS = 205.0            # per leg for straddles / strangles (as SN95 / SN171 strict)
MULTI_STRESS = 100.0          # per leg-lot for the four-leg fly (house multi-leg)


def gold_trade_days():
    """Every session (development and TEST) on which Gold v5 at Rs 15k traded (cached)."""
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / "gold-days.json"
    if p.exists():
        return set(json.loads(p.read_text(encoding="utf-8")))
    days = sorted(p4.gold("Rs 15k", keep=lambda d: True))
    p.write_text(json.dumps(days), encoding="utf-8")
    return set(days)


def empty_sessions(test=False):
    g = gold_trade_days()
    ss = pw.test_sessions() if test else pw.dev_sessions()
    return [S for S in ss if S.day not in g]


def leg_vals(S, i, strike, opt, stress=LEG_STRESS, end=pw.FLAT, lots=1):
    """Per-minute net of one long leg bought at minute i (bid close / carried bid mark), or None."""
    got = pb.struct_path(S, i, [(strike, opt)], leg_stress=stress, end=end)
    if got is None:
        return None
    vals = got[2]
    return vals * lots if lots != 1 else vals


def settle(vals, i, target=None, stop=None, end=pw.FLAT):
    """(net, exit minute, reason) on a minute-close path: stop first, then target, else the last value at end."""
    last = None
    for j in range(i + 1, end + 1):
        v = vals[j]
        if v != v:
            continue
        last = (v, j)
        if stop is not None and v <= -abs(stop):
            return v, j, "stop"
        if target is not None and v >= target:
            return v, j, "target"
    return (last[0], last[1], "time") if last else (None, end, "none")


def iron_fly_vals(S, i, wing=200, stress=MULTI_STRESS, end=pw.FLAT):
    """Short ATM CE + PE, long CE +wing / PE -wing, 1 lot at minute i. Per-minute net to close (shorts bought at the
    ask, wings sold at the bid; marks carry the last print). None when any leg has no print at i."""
    K = pw.atm(S, i)
    legs = [(K, "CE", -1), (K, "PE", -1), (K + wing, "CE", 1), (K - wing, "PE", 1)]
    recs = []
    for k, o, sgn in legs:
        r = S.option(k, o)
        if r is None or not r[6][i]:
            return None
        recs.append((r, sgn))
    entry = []
    for r, sgn in recs:
        raw = float(r[0][3][i])
        entry.append(M.bid_of(raw) if sgn < 0 else M.ask_of(raw))       # sell shorts at the bid, buy wings at the ask
    vals = np.full(end + 1, np.nan)
    last_raw = [float(r[0][3][i]) for r, _s in recs]
    for j in range(i + 1, end + 1):
        tot, fees = 0.0, 0.0
        for q, (r, sgn) in enumerate(recs):
            if r[6][j]:
                last_raw[q] = float(r[0][3][j])
            px = M.ask_of(last_raw[q]) if sgn < 0 else M.bid_of(last_raw[q])   # close: buy shorts back, sell wings
            tot += (entry[q] - px) * M.LOT if sgn < 0 else (px - entry[q]) * M.LOT
            fees += M.charges(min(entry[q], px), max(entry[q], px), M.LOT)
        vals[j] = tot - fees - stress * 4
    return vals


def goal_stats(day_nets, days, goal):
    """Fixed-goal statistics: days at or above the goal, red days, net, per year, monthly."""
    x = np.array([float(day_nets.get(d, 0.0)) for d in days])
    months = {}
    for d, v in zip(days, x):
        months.setdefault(d[:7], []).append(v)
    ms = np.array([sum(v) for v in months.values()]) if months else np.array([0.0])
    by_year = {y: round(float(x[[d[:4] == y for d in days]].sum())) for y in YEARS if any(d[:4] == y for d in days)}
    xs = sorted([v for d, v in day_nets.items() if d in set(days)], reverse=True)
    return {"sessions": len(days), "trade_days": int(sum(d in day_nets for d in days)), "goal_days": int((x >= goal - 1e-6).sum()),
            "red_days": int((x < 0).sum()), "net": round(float(x.sum())), "worst_day": round(float(x.min())) if len(x) else 0,
            "month_median": round(float(np.median(ms))), "month_worst": round(float(ms.min())),
            "goal_days_per_month": round(float((x >= goal - 1e-6).sum()) / max(1, len(months)), 2),
            "without_best_5": round(sum(xs[5:])), "by_year": by_year}


def loyo(variant_nets):
    return p3.loyo(variant_nets)


def null_days(pool_by_year, counts_by_year, draws=2000, seed=186):
    return p3.random_days_null(pool_by_year, counts_by_year, draws, seed)
