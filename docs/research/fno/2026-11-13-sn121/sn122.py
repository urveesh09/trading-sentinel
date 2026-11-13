"""SN122 - do the partner's entries and exits carry skill? (real quotes; PLAN.md) For every priced trip: the option
mid's relative move 1 / 5 / 15 / 30 minutes after entry against 2,000 random entry minutes in the same contract that
day (09:20-15:00); the move after their exit; machine exits on their entries (fixed 10-minute hold, 20% premium
trail) as per-lot executable net against their own exit minute. Per-lot averages and shares only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

qa, M = pg.qa, pg.M
HZ = (1, 5, 15, 30)
STRESS = 205.0


def rel(rec, a, b):
    x, y = pg.qmid(rec, a), pg.qmid(rec, b)
    return None if x is None or y is None or x <= 0 else (y - x) / x


def per_lot(rec, m0, m1, lot):
    """Executable per-lot net: buy at the real ask at m0, sell at the real bid at m1."""
    a, b = pg.qask(rec, m0), pg.qbid(rec, m1)
    if a is None or b is None:
        return None
    return (b - a) * lot - M.charges(a, b, lot) - STRESS


if __name__ == "__main__":
    out_path = HERE / "results-sn122.json"
    if out_path.exists():
        raise SystemExit("SN122 is scored once")
    trips = pg.partner_trips()
    rng = np.random.default_rng(122)
    rows = []
    for t in trips:
        d = t["session_date"]
        q = qa.load(d)
        key = pg.symbol_map(d).get(t["tradingsymbol"])
        rec = q["opt"].get(key) if key else None
        if rec is None:
            continue
        m0, m1 = pg.ist_minute(t["first_at"]), pg.ist_minute(t["closed_at"])
        lot = q["lot"][key[0]]
        row = {"day": d, "m0": m0, "m1": m1, "hold_min": None if m1 is None else m1 - m0}
        for h in HZ:
            row[f"after_entry_{h}"] = rel(rec, m0, m0 + h)
            row[f"after_exit_{h}"] = None if m1 is None else rel(rec, m1, m1 + h)
        cands = [m for m in range(5, 346) if pg.qmid(rec, m) is not None]
        row["random_pool"] = {h: [x for x in (rel(rec, m, m + h) for m in cands) if x is not None] for h in HZ}
        row["their_exit"] = None if m1 is None else per_lot(rec, m0, m1, lot)
        row["hold_10"] = per_lot(rec, m0, min(m0 + 10, 370), lot)
        peak, jx = None, None
        for j in range(m0 + 1, 371):
            b = pg.qbid(rec, j)
            if b is None:
                continue
            peak = b if peak is None else max(peak, b)
            if b <= 0.8 * peak:
                jx = j
                break
        row["trail_20"] = per_lot(rec, m0, jx if jx is not None else 370, lot)
        rows.append(row)
    res = {"trips": len(trips), "priced_trips": len(rows), "entry": {}, "exit": {}}
    for h in HZ:
        v = [r[f"after_entry_{h}"] for r in rows if r[f"after_entry_{h}"] is not None]
        idx = [k for k, r in enumerate(rows) if r[f"after_entry_{h}"] is not None and r["random_pool"][h]]
        draws = []
        for _ in range(2000):
            draws.append(np.mean([rows[k]["random_pool"][h][rng.integers(len(rows[k]["random_pool"][h]))] for k in idx]))
        mean = float(np.mean(v))
        res["entry"][h] = {"n": len(v), "partner_mean_pct": round(100 * mean, 2), "random_mean_pct": round(100 * float(np.mean(draws)), 2),
                           "random_95th_pct": round(100 * float(np.percentile(draws, 95)), 2), "p_value": float(np.mean(np.array(draws) >= mean)),
                           "share_up": round(float(np.mean([x > 0 for x in v])), 3)}
        w = [r[f"after_exit_{h}"] for r in rows if r[f"after_exit_{h}"] is not None]
        res["exit"][h] = {"n": len(w), "mean_pct_after_their_exit": round(100 * float(np.mean(w)), 2),
                          "share_kept_rising": round(float(np.mean([x > 0 for x in w])), 3)}
    cmp = {}
    for k in ("their_exit", "hold_10", "trail_20"):
        v = [r[k] for r in rows if r[k] is not None and r["their_exit"] is not None and r["hold_10"] is not None and r["trail_20"] is not None]
        cmp[k] = {"n": len(v), "mean_per_lot": round(float(np.mean(v))), "share_green": round(float(np.mean([x > 0 for x in v])), 3)}
    res["exits_per_lot_same_trips"] = cmp
    res["median_hold_min"] = float(np.median([r["hold_min"] for r in rows if r["hold_min"] is not None]))
    print(json.dumps(res, indent=1), flush=True)
    for r in rows:
        r.pop("random_pool")
    res["rows_shape_only"] = [{k: r[k] for k in ("day", "m0", "m1", "hold_min")} for r in rows]
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
