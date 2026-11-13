"""SN134 - learning on top of a simple event (PLAN.md): every fresh 3-minute move >= 1.5 ATR x sqrt 3 (feature r3,
fresh against the previous minute) on any day; a walk-forward model trained on event rows only predicts the
15-minute net in the move's direction; take the event when the prediction > theta (nested). Against all events and
random events at the same count."""
from __future__ import annotations

import bisect
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sm  # noqa: E402

THR = 1.5 * math.sqrt(3)


def events(data):
    X, day = data["X"], data["day"]
    r3 = X[:, sm.FEATURES.index("r3")]
    ev, side = [], []
    for k in range(1, len(day)):
        if day[k] != day[k - 1] or np.isnan(r3[k]) or np.isnan(r3[k - 1]):
            continue
        if abs(r3[k]) >= THR and abs(r3[k - 1]) < THR:
            ev.append(k)
            side.append(1 if r3[k] > 0 else -1)
    return np.array(ev), np.array(side)


def take(data, rows, sides, keep, room=3000.0):
    """One position at a time, 15-minute hold, day room."""
    day, minute = data["day"], data["minute"]
    nets, trades, free, cur, realized = {}, [], -1, None, 0.0
    for r, s, k in zip(rows, sides, keep):
        d = day[r]
        if d != cur:
            if cur is not None:
                nets[cur] = realized
            cur, realized, free = d, 0.0, -1
        if not k or minute[r] < free or realized <= -room:
            continue
        y = data["Y"]["CE15" if s > 0 else "PE15"][r]
        if np.isnan(y):
            continue
        realized += float(y)
        trades.append((d, int(minute[r]), "CE15" if s > 0 else "PE15", float(y), 0.0))
        free = minute[r] + 16
    if cur is not None:
        nets[cur] = realized
    return nets, trades


if __name__ == "__main__":
    out_path = HERE / "results-sn134.json"
    if out_path.exists():
        raise SystemExit("SN134 is scored once")
    data = sm.build()
    rows, sides = events(data)
    day = data["day"][rows]
    Xe = np.column_stack([data["X"][rows], sides.astype(np.float32)])
    ye = np.where(sides > 0, data["Y"]["CE15"][rows], data["Y"]["PE15"][rows])
    pred = np.full(len(rows), np.nan)
    udays = np.unique(data["day"])
    thetas = {}
    for q0, q1 in zip(sm.QUARTERS, sm.QUARTERS[1:]):
        test = (day >= q0) & (day < q1)
        if not test.any():
            continue
        k0 = bisect.bisect_left(list(udays), q0)
        train = day < udays[max(0, k0 - 1)]
        inner, vm = day < udays[max(0, k0 - 126)], (day >= udays[max(0, k0 - 126)]) & train
        mi = sm._fit(Xe[inner], ye[inner])
        pv = mi.predict(Xe[vm])
        best, bv = None, -np.inf
        for th in sm.THETAS:
            v = float(np.nansum(ye[vm][pv > th]))
            if v > bv:
                best, bv = th, v
        thetas[q0] = best
        mt = sm._fit(Xe[train], ye[train])
        pred[test] = mt.predict(Xe[test])
        print(f"   SN134 {q0}: events trained {int(train.sum())}, theta {best}", flush=True)
    scored = day >= "2024-01-01"
    thr = np.array([thetas.get(next((q for q in sm.QUARTERS[::-1] if q <= d), None), 0.0) for d in day])
    keep = scored & ~np.isnan(pred) & (pred > thr)
    n_all, t_all = take(data, rows[scored], sides[scored], np.ones(scored.sum(), bool))
    n_ml, t_ml = take(data, rows, sides, keep)
    rng = np.random.default_rng(134)
    rnd = []
    share = keep.sum() / max(1, scored.sum())
    for _ in range(200):
        kr = scored & (rng.random(len(rows)) < share)
        n_r, _t = take(data, rows, sides, kr)
        rnd.append(sum(n_r.values()))
    res = {"events_scored": int(scored.sum()), "taken": int(keep.sum()), "thetas": thetas,
           "all_events": sm.per_year(n_all, t_all), "learned": sm.per_year(n_ml, t_ml),
           "random_mean": round(float(np.mean(rnd))), "random_95th": round(float(np.percentile(rnd, 95)))}
    py = res["learned"]
    res["PASS_partial"] = bool(py["total"] > 0 and py["positive_years"] >= 2 and py["total"] > res["random_95th"] and py["without_best_5_days"] > 0)
    print("SN134", json.dumps({k: v for k, v in res.items() if k != "thetas"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
