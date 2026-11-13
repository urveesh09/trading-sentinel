"""SN144 - the hot-day specialist (PLAN.md): a walk-forward model trained only on hot-day rows from 10:00 (SN95's causal
flag), actions CE / PE x 15 / 30 / 60 minutes or to the close, and the straddle to the close; theta nested; against
SN95-L's fixed 10:00 straddle on the same days. Pass: SN132's rule on hot days."""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

sm, run, pa = pe.sm, pe.run, pe.pa
ACTIONS = ["CE15", "CE30", "CE60", "CE999", "PE15", "PE30", "PE60", "PE999", "ST999"]


if __name__ == "__main__":
    out_path = HERE / "results-sn144.json"
    if out_path.exists():
        raise SystemExit("SN144 is scored once")
    data = sm.build()
    d2 = pe.with_labels(data, pe.close_labels(data))
    hot = pe.hot_rows(data)
    sub = {"X": d2["X"][hot], "day": d2["day"][hot], "minute": d2["minute"][hot], "Y": {k: d2["Y"][k][hot] for k in ACTIONS}}
    X, day = sub["X"], sub["day"]
    udays = np.unique(day)
    preds = {k: np.full(len(day), np.nan, dtype=np.float32) for k in ACTIONS}
    nets, trades, thetas = {}, [], {}
    for q0, q1 in zip(sm.QUARTERS, sm.QUARTERS[1:]):
        test = (day >= q0) & (day < q1)
        if not test.any():
            continue
        k0 = bisect.bisect_left(list(udays), q0)
        train = day < q0
        vdays = udays[max(0, k0 - 25): k0]                  # the last ~25 hot days before the quarter
        val = np.isin(day, vdays)
        inner = train & ~val
        # crash fix after the first run (README): too few hot training days before the quarter -> no trades there
        if len(np.unique(day[train])) < 50 or len(np.unique(day[inner])) < 20:
            thetas[q0] = None
            print(f"   SN144 {q0}: skipped, only {len(np.unique(day[train]))} hot training days", flush=True)
            continue
        vq = {}
        for k in ACTIONS:
            y = sub["Y"][k]
            vq[k] = (val, sm._fit(X[inner], y[inner]).predict(X[val]).astype(np.float32))
            preds[k][test] = sm._fit(X[train], y[train]).predict(X[test]).astype(np.float32)
        th, _v = sm.choose_theta(sub, vq, choices=ACTIONS)
        thetas[q0] = th
        n, tr = sm.simulate(sub, preds, test, th, choices=ACTIONS)
        nets.update(n)
        trades += tr
        print(f"   SN144 {q0}: hot days trained {len(np.unique(day[train]))}, theta {th}", flush=True)
    py = sm.per_year(nets, trades)
    # SN95-L's fixed straddle on the same hot days (Gold-free or not, Rs 15k ceiling, Rs 3k room, strict)
    C = sm.C
    sess = {S.day: S for y in C.YEARS for S in C.years()[y].ordered()}
    fixed = {}
    for d in np.unique(day[day >= "2024-01-01"]):
        got = pa.path(sess[d], pa.I10)
        fixed[d] = 0.0 if got is None or got[1] > 15000 else pa.settle(got[2], pa.I10, 3000.0)[0]
    pf = sm.per_year(fixed, [(d, 0, "ST", v, 0) for d, v in fixed.items() if v])
    rm, r95 = sm.random_null(sub, trades, day >= "2024-01-01", choices=ACTIONS)
    res = {"hot_days_scored": int(len(np.unique(day[day >= "2024-01-01"]))), "learned": py, "thetas": thetas,
           "fixed_sn95l_straddle_same_days": pf, "random_mean": round(rm), "random_95th": round(r95),
           "by_choice": {c: sum(1 for t in trades if t[2] == c) for c in ACTIONS}, "day_nets": nets}
    res["PASS_partial"] = bool(py["total"] > 0 and py["positive_years"] >= 2 and py["total"] > r95 and py["without_best_5_days"] > 0)
    print("SN144", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
