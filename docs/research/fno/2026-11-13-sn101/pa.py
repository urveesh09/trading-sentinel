"""Phase A shared helpers (SN101-SN110). Imports the SN92 harness (Gold v5 parity proven) and SN95's straddle code;
neither is edited. A straddle is valued minute by minute once (`path`) and every exit rule reads that path
(`settle`), so the hold rule reproduces sn95.play exactly (asserted in smoke tests and at the start of each run)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn92"))
import common as C  # noqa: E402
import sn95  # noqa: E402

M = C.M
FLAT = C.FLAT
I10 = 45                      # 10:00
STRICT = 205.0


def path(S, i, leg_stress=STRICT, lots=1, end=FLAT):
    """(asks, premium rupees, per-minute net array) of a long ATM straddle bought at minute i, or None."""
    legs = sn95.legs(S, i, "buy")
    if legs is None:
        return None
    qty = lots * M.LOT
    vals = np.full(end + 1, np.nan)
    for j in range(i + 1, end + 1):
        tot = fees = 0.0
        ok = True
        for rec, _q, px in legs:
            x = sn95.bid_at(rec, j)
            if x is None:
                ok = False
                break
            tot += (x - px) * qty
            fees += M.charges(px, x, qty)
        if ok:
            vals[j] = tot - fees - leg_stress * lots * 2
    asks = [px for _r, _q, px in legs]
    return asks, sum(asks) * qty, vals


def settle(vals, i, room=None, rule="hold", end=FLAT, gb=(1000.0, 0.5), t_exit=None, stop_at=None, fallback=-2 * STRICT):
    """Exit a valued path. Returns (net, exit minute, reason)."""
    last, peak, armed = None, -math.inf, False
    for j in range(i + 1, end + 1):
        if stop_at is not None and j >= stop_at:
            v = vals[j] if not np.isnan(vals[j]) else last
            return (v if v is not None else fallback), j, "forced"
        v = vals[j]
        if np.isnan(v):
            continue
        last = v
        if room is not None and v <= -room:
            return v, j, "stop"
        if rule == "gb":
            peak = max(peak, v)
            if v >= gb[0]:
                armed = True
            if armed and v <= gb[1] * peak:
                return v, j, "giveback"
        if t_exit is not None and j >= t_exit:
            return v, j, "time"
    return (last if last is not None else fallback), end, "hold"


def shift(vals, from_stress, to_stress, lots=1):
    return vals + 2 * lots * (from_stress - to_stress)


def admission():
    """SN95's causal admission flags: {(day, clock, feature, q, top|bottom): bool}."""
    _rows, adm = sn95.features()
    return adm


def sn95l(adm, day):
    """SN95-L as frozen: Gold-free day and R_today at 10:00 in the causal top 20%."""
    return C.gold_free(day) and adm.get((day, "10:00", "R_today", 0.2, "top"), False)


def year_table(nets_by_day):
    """nets_by_day: {day: net or 0} -> per-year net / trades / won / lost and the without-best-5 total."""
    per = {}
    for y in C.YEARS:
        xs = [v for d, v in nets_by_day.items() if d[:4] == y and v is not None]
        traded = [v for v in xs if v != 0]
        per[y] = {"net": round(sum(xs)), "trades": len(traded), "won": sum(v > 0 for v in traded), "lost": sum(v < 0 for v in traded)}
    allv = sorted((v for v in nets_by_day.values() if v), reverse=True)
    per["total"] = round(sum(allv))
    per["without_best_5"] = round(sum(allv[5:]))
    per["positive_years"] = sum(per[y]["net"] > 0 for y in C.YEARS)
    return per


def bootstrap_ci(values_by_day: dict, stat, n=2000, seed=101):
    """Day-clustered bootstrap of stat(list of per-day arrays)."""
    rng = np.random.default_rng(seed)
    keys = sorted(values_by_day)
    out = []
    for _ in range(n):
        pick = rng.choice(len(keys), len(keys))
        out.append(stat([values_by_day[keys[k]] for k in pick]))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))
