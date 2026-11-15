"""Phase P2 helpers (SN167-SN170): the feature matrix (SN131's 44 causal features + 5 for the wage), walk-forward
LightGBM classifiers inside DEVELOPMENT, the wage policy simulator on SN166's barrier labels and its matched null.
Runs in the research venv (LightGBM 4.5.0). TEST rows are never scored here: final models write TEST predictions to
_local for SN181."""
from __future__ import annotations

import bisect
import math
import pickle

import numpy as np

import pw
import sn166

LOCAL = sn166.LOCAL
PARAMS = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 31, "min_data_in_leaf": 400,
          "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 10.0, "verbose": -1,
          "num_threads": 4, "seed": 167, "deterministic": True, "force_col_wise": True}
ROUNDS = 300
THETAS = (0.40, 0.45, 0.50, 0.55, 0.60)
BLOCKS = [f"{y}-{m:02d}-01" for y in ("2024", "2025", "2026") for m in (1, 4, 7, 10)]
BLOCKS = [b for b in BLOCKS if b < pw.TEST_FROM] + [pw.TEST_FROM]
EXTRA = ("left", "or30_width", "rv_fc_ratio", "ask_a", "lots_a")
NK = sn166.I1 - sn166.I0 + 1


def load():
    """d131, bar, s_idx, k_idx and the common feature block (44 + left, or30_width, rv_fc_ratio)."""
    d131, bar, s_idx, k_idx = sn166.aligned()
    X, F = d131["X"], list(d131["features"])
    left = (pw.FLAT - d131["minute"].astype(np.float32))
    or30 = X[:, F.index("or_lo")] - X[:, F.index("or_hi")]                 # (OR30 high - low) / ATR, NaN before 09:45
    rt = X[:, F.index("r_today")]
    rv_open = X[:, F.index("rv_open")] / 1e4
    sig = np.where(rt > 0, rv_open / rt, np.nan)
    r_atr = (X[:, F.index("atr_prev")] / 100.0) / (1.6 * math.sqrt(375.0)) / sig
    rv_fc = 0.5 * rt + 0.5 * r_atr
    base = np.hstack([X, np.stack([left, or30, rv_fc], axis=1).astype(np.float32)])
    return d131, bar, s_idx, k_idx, base, F + ["left", "or30_width", "rv_fc_ratio"]


def action_matrix(base, bar, s_idx, k_idx, a):
    ask = bar["ask"][s_idx, a, k_idx]
    lots = bar["lots"][s_idx, a, k_idx].astype(np.float32)
    return np.hstack([base, np.stack([ask, lots], axis=1)]).astype(np.float32)


def fit(X, y, params=None, rounds=ROUNDS):
    import lightgbm as lgb
    p = dict(PARAMS, **(params or {}))
    return lgb.train(p, lgb.Dataset(X, y.astype(np.float32), free_raw_data=True), num_boost_round=rounds)


def walk_forward(Xa, y, ok, days, params=None, rounds=ROUNDS):
    """Out-of-sample P for DEVELOPMENT rows from 2024-01-01: each block predicted by a model trained on every valid
    row before the session preceding the block (one-session purge)."""
    pred = np.full(len(days), np.nan, dtype=np.float32)
    udays = sorted(set(days))
    for q0, q1 in zip(BLOCKS, BLOCKS[1:]):
        test = (days >= q0) & (days < q1) & ok
        if not test.any():
            continue
        k0 = bisect.bisect_left(udays, q0)
        purge = udays[max(0, k0 - 1)]
        train = ok & (days < purge)
        m = fit(Xa[train], y[train], params, rounds)
        pred[test] = m.predict(Xa[test]).astype(np.float32)
    return pred


def final_test_pred(Xa, y, ok, days, params=None, rounds=ROUNDS):
    """The final model: every valid DEVELOPMENT row but the last session; predictions for TEST rows only."""
    udev = sorted(set(days[days < pw.TEST_FROM]))
    train = ok & (days < udev[-1])
    test = (days >= pw.TEST_FROM) & ok
    m = fit(Xa[train], y[train], params, rounds)
    pred = np.full(len(days), np.nan, dtype=np.float32)
    pred[test] = m.predict(Xa[test]).astype(np.float32)
    return pred, m


def to_grid(pred_rows, s_idx, k_idx, n_sess):
    g = np.full((n_sess, NK), np.nan, dtype=np.float32)
    g[s_idx, k_idx] = pred_rows
    return g


def policy(P, bar, sessions_scored, theta, max_trades=2, k_last=300):
    """P: (n_sess, 4, NK) probabilities. At each flat minute (09:30-14:30) take the action with the highest P if
    >= theta; its SN166 barrier outcome is the trade; stop the day after a target (the wage) or a 15:10 exit, or after
    ``max_trades``. Returns {day: net}, trades taken."""
    out, ntr = {}, 0
    for s in sessions_scored:
        k, trades, net = 0, 0, 0.0
        while k <= k_last and trades < max_trades:
            p = P[s, :, k]
            nets = bar["net"][s, :, k]
            ok = ~np.isnan(p) & ~np.isnan(nets)
            if ok.any():
                a = int(np.argmax(np.where(ok, p, -np.inf)))
                if p[a] >= theta:
                    net += float(nets[a])
                    trades += 1
                    j = int(bar["j"][s, a, k])
                    if bar["label"][s, a, k] == 1 or j >= pw.FLAT:
                        break
                    k = j + 1 - sn166.I0
                    continue
            k += 1
        if trades:
            out[bar["days"][s]] = net
            ntr += trades
    return out, ntr


def matched_null(bar, taken: dict, draws=200, seed=167, k_last=300):
    """For each day the policy traded: random minutes and actions with the same sequencing, as many trades as the policy
    took that day (or until a target / 15:10). Returns per-draw {day: net} dicts."""
    rng = np.random.default_rng(seed)
    pos = {d: s for s, d in enumerate(bar["days"])}
    out = []
    for _ in range(draws):
        dn = {}
        for day, n_tr in taken.items():
            s = pos[day]
            k, trades, net = 0, 0, 0.0
            while trades < n_tr and k <= k_last:
                k = int(rng.integers(k, k_last + 1))
                nets = bar["net"][s, :, k]
                ok = np.flatnonzero(~np.isnan(nets))
                if not len(ok):
                    k += 1
                    continue
                a = int(rng.choice(ok))
                net += float(nets[a])
                trades += 1
                j = int(bar["j"][s, a, k])
                if bar["label"][s, a, k] == 1 or j >= pw.FLAT:
                    break
                k = j + 1 - sn166.I0
            if trades:
                dn[day] = net
        out.append(dn)
    return out


def trades_per_day(P, bar, sessions_scored, theta, max_trades=2, k_last=300):
    """{day: number of trades} of the policy (for the matched null)."""
    out = {}
    for s in sessions_scored:
        k, trades = 0, 0
        while k <= k_last and trades < max_trades:
            p = P[s, :, k]
            nets = bar["net"][s, :, k]
            ok = ~np.isnan(p) & ~np.isnan(nets)
            if ok.any():
                a = int(np.argmax(np.where(ok, p, -np.inf)))
                if p[a] >= theta:
                    trades += 1
                    j = int(bar["j"][s, a, k])
                    if bar["label"][s, a, k] == 1 or j >= pw.FLAT:
                        break
                    k = j + 1 - sn166.I0
                    continue
            k += 1
        if trades:
            out[bar["days"][s]] = trades
    return out


def summary(dn, days, wallet=15000.0, wage=1500.0):
    s = pw.wage_stats(dn, days, wallet, wage)
    return {"net": s["net"], "wage_share": s["wage_share"], "trade_days": s["trade_days"], "red_days": s["red_days"],
            "month_mean": s["month"]["mean"], "by_year": {y: v["net"] for y, v in s["by_year"].items()}}


def null_summary(null_dns, days, wallet=15000.0, wage=1500.0):
    st = [pw.wage_stats(dn, days, wallet, wage) for dn in null_dns]
    nets = [s["net"] for s in st]
    return {"net_mean": round(float(np.mean(nets))), "net_p95": round(float(np.percentile(nets, 95))),
            "wage_share_mean": round(float(np.mean([s["wage_share"] for s in st])), 4)}


def save(name, obj):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / name
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(obj))
    tmp.replace(p)
