"""Walk-forward machinery for SN277-SN280 (PLAN.md, fixed before any learner score). Folds: half-years 2022 H1 .. 2026 H2;
each fold's model is trained on every pooled session (NIFTY and SENSEX) dated before the fold starts."""
from __future__ import annotations

import numpy as np

import ds

FOLDS = [(f"{y}-01-01", f"{y}-07-01") if h == 1 else (f"{y}-07-01", f"{y + 1}-01-01") for y in range(2022, 2027) for h in (1, 2)]


def X(rows):
    return np.array([r["x"] for r in rows], dtype=float)


def lgb_reg(seed):
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=8, min_child_samples=40, subsample=0.8,
                             subsample_freq=1, colsample_bytree=0.8, random_state=seed, verbose=-1)


def lgb_clf(seed):
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=8, min_child_samples=40, subsample=0.8,
                              subsample_freq=1, colsample_bytree=0.8, random_state=seed, verbose=-1)


def folds(rows):
    for lo, hi in FOLDS:
        tr = [r for r in rows if r["day"] < lo]
        te = [r for r in rows if lo <= r["day"] < hi]
        if te:
            yield (lo, hi), tr, te


def value_models(tr, seed=277, shuffle_rng=None):
    out = {}
    for a in "SCP":
        y = np.array([r[f"{a}205"] for r in tr])
        if shuffle_rng is not None:
            y = shuffle_rng.permutation(y)
        m = lgb_reg(seed)
        m.fit(X(tr), y)
        out[a] = m
    return out


def policy_value(models, te, tau):
    P = {a: models[a].predict(X(te)) for a in "SCP"}
    acts = []
    for k in range(len(te)):
        a = max("SCP", key=lambda z: P[z][k])
        acts.append(a if P[a][k] > tau else "N")
    return acts


def class_models(tr, seed=278, shuffle_rng=None):
    yu = np.array([r["up"] for r in tr])
    yb = np.array([float(r["S205"] > 0) for r in tr])
    if shuffle_rng is not None:
        yu, yb = shuffle_rng.permutation(yu), shuffle_rng.permutation(yb)
    mu, mb = lgb_clf(seed), lgb_clf(seed + 1)
    mu.fit(X(tr), yu)
    mb.fit(X(tr), yb)
    thr = float(np.quantile(mb.predict_proba(X(tr))[:, 1], 0.85))
    return mu, mb, thr


def policy_class(models, te, delta):
    mu, mb, thr = models
    pu = mu.predict_proba(X(te))[:, 1]
    pb = mb.predict_proba(X(te))[:, 1]
    acts = []
    for u, b in zip(pu, pb):
        if abs(u - 0.5) >= delta:
            acts.append("C" if u > 0.5 else "P")
        elif b >= thr:
            acts.append("S")
        else:
            acts.append("N")
    return acts


def score(te_rows, acts, tag="205"):
    tr = []
    for r, a in zip(te_rows, acts):
        if a != "N":
            v = r[f"{a}{tag}"]
            if v is not None:
                tr.append({"day": r["day"], "exit_day": r["day"], "net": v, "inst": r["inst"], "a": a})
    return tr


def run(rows, fit, pol, param, tag="205", shuffle_seed=None):
    """[(fold, trades)] for one learner variant."""
    out = []
    rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
    for f, tr, te in folds(rows):
        models = fit(tr, shuffle_rng=rng)
        acts = pol(models, te, param)
        out.append((f, te, acts))
    return out


def summary(runs, tag="205"):
    fold_nets, allt = [], []
    for f, te, acts in runs:
        t = score(te, acts, tag)
        allt += t
        fold_nets.append(round(sum(x["net"] for x in t)))
    nets = np.array([x["net"] for x in allt]) if allt else np.zeros(0)
    by_inst = {i: round(sum(x["net"] for x in allt if x["inst"] == i)) for i in ("NIFTY", "SENSEX")}
    by_act = {a: {"n": sum(x["a"] == a for x in allt), "net": round(sum(x["net"] for x in allt if x["a"] == a))} for a in "SCP"}
    srt = np.sort(nets)[::-1]
    return {"net": round(float(nets.sum())), "trades": len(allt), "win_pct": round(100 * float((nets > 0).mean()), 1) if len(nets) else 0.0,
            "folds": fold_nets, "folds_positive": sum(x > 0 for x in fold_nets), "worst_fold": min(fold_nets) if fold_nets else 0,
            "by_index": by_inst, "by_action": by_act, "without_best10": round(float(srt[10:].sum())) if len(nets) else 0}
