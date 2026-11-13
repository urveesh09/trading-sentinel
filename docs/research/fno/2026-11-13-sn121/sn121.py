"""SN121 - the partner's day paths (description; PLAN.md). Minute by minute: realised P&L of closed trips plus open
trips marked at the archived BID (what selling would fetch). Peak timing, the share of the peak given back, trips
after the peak; lock counterfactuals on their own sequence. Output is shapes, shares and ratios only - no partner
rupee totals (standing privacy rule)."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

qa = pg.qa
LOCKS = {"lock at +10%": ("lock", 0.10), "lock at +20%": ("lock", 0.20),
         "stop after a 30% giveback of a >= +5% peak": ("giveback", 0.30), "stop after a 50% giveback of a >= +5% peak": ("giveback", 0.50)}


def day_path(day, trips):
    q = qa.load(day)
    smap = pg.symbol_map(day)
    n = qa.NM
    realised = np.zeros(n)
    open_val = np.zeros(n)
    priced = unpriced = 0
    for t in trips:
        cm = pg.ist_minute(t["closed_at"])
        a, b = max(0, pg.ist_minute(t["first_at"])), (min(n - 1, cm) if cm is not None else 374)
        if cm is not None and t["realised"] is not None:
            realised[b:] += t["realised"]
        key = smap.get(t["tradingsymbol"])
        rec = q["opt"].get(key) if key else None
        last = None
        for m in range(a, b):
            x = pg.qbid(rec, m)
            if x is not None:
                last = x
            if last is not None:
                open_val[m] += (last - t["entry"]) * t["bought"]
        priced += rec is not None
        unpriced += rec is None
    return realised + open_val, priced, unpriced


def apply_lock(path, kind, x):
    peak = -np.inf
    for m, v in enumerate(path):
        peak = max(peak, v)
        if kind == "lock" and v >= x * pg.NOTIONAL:
            return v
        if kind == "giveback" and peak >= 0.05 * pg.NOTIONAL and v <= peak * (1 - x):
            return v
    return path[-1]


if __name__ == "__main__":
    out_path = HERE / "results-sn121.json"
    if out_path.exists():
        raise SystemExit("SN121 is scored once")
    trips = pg.partner_trips()
    by_day = collections.defaultdict(list)
    for t in trips:
        by_day[t["session_date"]].append(t)
    days, finals, locks = [], {}, {k: {} for k in LOCKS}
    for d in sorted(by_day):
        path, pr, up = day_path(d, by_day[d])
        pk = int(np.argmax(path))
        peak, final = float(path[pk]), float(path[-1])
        closes = sorted(pg.ist_minute(t["closed_at"]) for t in by_day[d] if t["closed_at"])
        days.append({"day": d, "trips": len(by_day[d]), "trips_priced_share": round(pr / max(1, pr + up), 2),
                     "peak_clock": f"{9 + (pk + 15) // 60:02d}:{(pk + 15) % 60:02d}",
                     "peak_positive": peak > 0, "peak_at_least_10pct": peak >= 0.10 * pg.NOTIONAL,
                     "peak_at_least_20pct": peak >= 0.20 * pg.NOTIONAL,
                     "share_of_peak_given_back": round((peak - final) / peak, 2) if peak > 0 else None,
                     "trips_after_peak": sum(c > pk for c in closes), "ended_green": final > 0})
        finals[d] = final
        for k, (kind, x) in LOCKS.items():
            locks[k][d] = apply_lock(path, kind, x)
    actual = sum(finals.values())
    lock_res = {}
    for k, v in locks.items():
        ch = sum(v.values()) - actual
        lock_res[k] = {"days_improved": sum(v[d] > finals[d] + 1 for d in v), "days_worse": sum(v[d] < finals[d] - 1 for d in v),
                       "days_green_after": sum(x > 0 for x in v.values()),
                       "change_relative_to_actual_result": round(ch / abs(actual), 2) if actual else None,
                       "change_sign": "better" if ch > 0 else "worse" if ch < 0 else "same"}
    res = {"sessions": len(days), "trips": len(trips), "days": days, "locks": lock_res,
           "summary": {"days_with_a_positive_peak": sum(d["peak_positive"] for d in days),
                       "days_peak_at_least_10pct_of_25k": sum(d["peak_at_least_10pct"] for d in days),
                       "days_peak_at_least_20pct_of_25k": sum(d["peak_at_least_20pct"] for d in days),
                       "days_ended_green": sum(d["ended_green"] for d in days),
                       "median_share_of_peak_given_back": float(np.median([d["share_of_peak_given_back"] for d in days if d["share_of_peak_given_back"] is not None] or [0])),
                       "median_trips_after_peak": float(np.median([d["trips_after_peak"] for d in days])),
                       "median_trips_per_day": float(np.median([d["trips"] for d in days]))}}
    print(json.dumps(res["summary"], indent=1))
    for d in days:
        print("  ", d)
    for k, v in lock_res.items():
        print(f"  {k:46s}", v)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
