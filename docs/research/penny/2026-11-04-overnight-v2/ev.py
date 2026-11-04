"""EV trader: walk-forward ridge model of the next overnight return, cost-aware selection.

Features are causal (known at the decision close). Labels are the next open /
close - 1, clipped to +/-15%. The model is refit every REFIT sessions on an
expanding window that never starts before ``train_from`` (so the sealed exam's
labels are never used to score development, and vice versa).

``ev_days`` returns copies of the panel's Day objects whose candidate list is the
whole unlocked band (pool="all") or the shipped EDGE candidates only
(pool="edge"), ranked by predicted gross overnight return.
"""
from __future__ import annotations

import math
import pickle
from copy import copy
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import lab  # noqa: E402

FEATURES = ("ret", "ret2", "clv", "clv_ret", "from_high", "ltv", "ltv20", "lprice", "lrvol", "night_mean",
            "day_mean", "ph_rate", "atrp", "gap", "oc", "ret5", "near_hi20", "prev_ret", "mo", "bounce", "big")


def vec(f: dict) -> list[float]:
    r = max(-.2, min(.2, f["ret"]))
    return [r, r * r, f["clv"], f["clv"] * r, f["from_high"], math.log10(max(f["tv"], 1.0)),
            math.log10(max(f["tv20"], 1.0)), math.log(f["price"]), math.log1p(max(f["rvol"], 0.0)),
            f["night_mean"], f["day_mean"], f["ph_rate"], min(f["atrp"], .3), max(-.2, min(.2, f["gap"])),
            max(-.2, min(.2, f["oc"])), max(-.5, min(1.0, f["ret5"])), f["near_hi20"],
            max(-.2, min(.2, f["prev_ret"])), float(f["ret"] >= .05 and f["rvol"] >= 1), f["bounce"],
            float(f["ret"] >= .12)]


def locked(f: dict) -> bool:
    return f["from_high"] >= -0.001 and f["ret"] >= 0.019


@dataclass
class Model:
    mu: np.ndarray
    sd: np.ndarray
    w: np.ndarray
    b: float

    def predict(self, X: np.ndarray) -> np.ndarray:
        return ((X - self.mu) / self.sd) @ self.w + self.b


def fit(X: np.ndarray, y: np.ndarray, lam: float = 50.0) -> Model:
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1.0
    Z = (X - mu) / sd
    b = float(y.mean())
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ (y - b))
    return Model(mu, sd, w, b)


def table(src: str, min_tv: float = 5e5):
    """-> (keys [(ticker, date)], X, y) for unlocked non-SME band rows with tv >= min_tv."""
    rows = pickle.load(open(HERE / f"_local/allrows-{src}.pkl", "rb"))
    keys, X, y = [], [], []
    for t, d, f, on, _nday, _ph in rows:
        if locked(f) or f["tv"] < min_tv:
            continue
        keys.append((t, d))
        X.append(vec(f))
        y.append(max(-.15, min(.15, on)))
    return keys, np.asarray(X, float), np.asarray(y, float)


def walk_forward(src: str, *, train_from: str, predict_from: str, predict_to: str, refit: int = 21,
                 min_sessions: int = 120, window: int | None = None, lam: float = 50.0, frozen: Model | None = None):
    """-> dict (ticker, date) -> predicted gross overnight, plus the list of fitted models."""
    keys, X, y = table(src)
    dates = np.array([d for _, d in keys])
    sessions = sorted({d for d in dates if d >= train_from})
    pred, models = {}, []
    targets = [d for d in sessions if predict_from <= d <= predict_to]
    k = 0
    while k < len(targets):
        block = targets[k:k + refit]
        if frozen is not None:
            m = frozen
        else:
            first = block[0]
            past = [d for d in sessions if d < first]
            if len(past) < min_sessions:
                k += refit
                continue
            lo = past[-window] if window else train_from
            mask = (dates >= lo) & (dates < first)
            m = fit(X[mask], y[mask], lam)
            models.append({"first": first, "train_rows": int(mask.sum()), "w": m.w.tolist(), "b": m.b})
        sel = (dates >= block[0]) & (dates <= block[-1])
        p = m.predict(X[sel])
        for (t, d), v in zip([keys[i] for i in np.flatnonzero(sel)], p):
            pred[(t, d)] = float(v)
        k += refit
    return pred, models


def ev_days(days: list, pred: dict, pool: str = "all") -> list:
    """Copies of Day with cands replaced by model-ranked rows (shipped fields kept for EDGE rows)."""
    out = []
    for d in days:
        nd = copy(d)
        if pool == "edge":
            cs = [c for c in d.cands if (c.ticker, d.date) in pred]
            nd.cands = sorted((lab.replace(c, adj=pred[(c.ticker, d.date)]) for c in cs), key=lambda c: -c.adj)
        else:
            cs = []
            edge = {c.ticker: c for c in d.cands}
            for t, b in d.bar.items():
                p = pred.get((t, d.date))
                if p is None:
                    continue
                if t in edge:
                    cs.append(lab.replace(edge[t], adj=p))
                else:
                    cs.append(lab.Cand(t, "EV", "EV", p, p, b["close"], b["close"] * .9, b["close"] * 1.1, {}))
            nd.cands = sorted(cs, key=lambda c: -c.adj)
        out.append(nd)
    return out
