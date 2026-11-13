"""Generic learn-then-trade helpers for SN135 (1-second) and SN136 (order-book quotes): fit on a training block, choose
theta on a later validation block with a model trained before it, then score a later test block once."""
from __future__ import annotations

import numpy as np

import sm

THETAS = sm.THETAS


def simulate(day, t, preds, labels, mask, theta, hz_of, gap, room=3000.0, stress_shift=0.0):
    """Rows must be sorted by (day, t). One position at a time; next decision after exit + gap (same units as t)."""
    keys = list(preds)
    P = np.vstack([preds[k] for k in keys])
    nets, trades = {}, []
    cur, realized, free = None, 0.0, -1
    for r in np.flatnonzero(mask):
        d = day[r]
        if d != cur:
            if cur is not None:
                nets[cur] = realized
            cur, realized, free = d, 0.0, -1
        if t[r] < free or realized <= -room:
            continue
        col = P[:, r]
        if np.all(np.isnan(col)):
            continue
        b = int(np.nanargmax(col))
        if col[b] <= theta:
            continue
        y = labels[keys[b]][r]
        if np.isnan(y):
            continue
        net = float(y) - stress_shift
        realized += net
        trades.append((str(d), int(t[r]), keys[b], net))
        free = t[r] + hz_of(keys[b]) + gap
    if cur is not None:
        nets[cur] = realized
    return nets, trades


def fit_predict(X, Y, train, test):
    out = {}
    for k, y in Y.items():
        m = sm._fit(X[train], y[train])
        out[k] = np.full(len(y), np.nan, dtype=np.float32)
        out[k][test] = m.predict(X[test]).astype(np.float32)
    return out


def learn(X, Y, day, t, inner, val, train, test, hz_of, gap, room=3000.0):
    pv = fit_predict(X, Y, inner, val)
    best, bv = None, -np.inf
    for th in THETAS:
        n, _ = simulate(day, t, pv, Y, val, th, hz_of, gap, room)
        v = sum(n.values())
        if v > bv:
            best, bv = th, v
    pt = fit_predict(X, Y, train, test)
    return pt, best, bv


def summary(nets, trades):
    vals = sorted((v for v in nets.values() if v), reverse=True)
    return {"days": len(nets), "days_traded": sum(1 for v in nets.values() if v), "trades": len(trades),
            "net": round(sum(vals)), "without_best_5_days": round(sum(vals[5:])), "won_days": sum(v > 0 for v in vals),
            "lost_days": sum(v < 0 for v in vals), "worst_day": round(min(vals)) if vals else 0}


def random_null(day, t, labels, mask, trades, n=200, seed=135):
    rng = np.random.default_rng(seed)
    keys = list(labels)
    per = {}
    for tr in trades:
        per[tr[0]] = per.get(tr[0], 0) + 1
    rows = {}
    for r in np.flatnonzero(mask):
        rows.setdefault(str(day[r]), []).append(r)
    tots = []
    for _ in range(n):
        s = 0.0
        for d, cnt in per.items():
            rr = rows.get(d, [])
            for r in (rng.choice(rr, min(cnt, len(rr)), replace=False) if rr else []):
                y = labels[keys[rng.integers(len(keys))]][r]
                s += 0.0 if np.isnan(y) else float(y)
        tots.append(s)
    return round(float(np.mean(tots))), round(float(np.percentile(tots, 95)))
