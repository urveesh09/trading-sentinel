"""EN116 causal diagonal-Gaussian HMM (IMPL10.md section 4.6). Own implementation (no external HMM package): deterministic
initialisation, scaled forward-backward, equal-day weights, variance floor. Fits read only earlier covered sessions; the
day filter resets to the fitted initial distribution and updates on completed observations only (no smoothing).
"""
import hashlib, json, math
import numpy as np
import round10  # noqa: F401
import features10 as FX

VAR_FLOOR = 1e-3
MIN_OBS = 80                       # covered HMM session: >= 80 of the 90 window observations valid
ITERS, TOL = 100, 1e-7


def standardizer(seqs):
    x = np.concatenate([s[np.isfinite(s).all(1)] for s in seqs])
    mu = x.mean(0); sd = x.std(0)
    sd[sd <= 1e-12] = 1.
    return mu, sd


def transform(X, mu, sd):
    Z = (X - mu) / sd
    return np.clip(Z, -4, 4)


def loglik_rows(Z, mu, var):
    """(T, K) log emission densities; rows with a missing value get 0 (likelihood 1: no update)."""
    ok = np.isfinite(Z).all(1)
    out = np.zeros((len(Z), len(mu)))
    if ok.any():
        z = Z[ok][:, None, :]
        out[ok] = -.5 * (np.log(2 * np.pi * var)[None] + (z - mu[None]) ** 2 / var[None]).sum(2)
    return out, ok


def forward_backward(logb, pi, A):
    """Batched scaled forward-backward. logb: (S, T, K). Returns gamma (S, T, K), per-sequence xi sums (S, K, K), loglik (S)."""
    m = logb.max(2, keepdims=True); b = np.exp(logb - m)
    S, T, K = logb.shape
    al = np.zeros((S, T, K)); c = np.zeros((S, T))
    a = pi[None] * b[:, 0]; c[:, 0] = a.sum(1); al[:, 0] = a / c[:, 0, None]
    for t in range(1, T):
        a = (al[:, t - 1] @ A) * b[:, t]; c[:, t] = a.sum(1); al[:, t] = a / c[:, t, None]
    be = np.ones((S, T, K))
    for t in range(T - 2, -1, -1):
        be[:, t] = ((b[:, t + 1] * be[:, t + 1]) @ A.T) / c[:, t + 1, None]
    g = al * be; g /= g.sum(2, keepdims=True)
    X = al[:, :-1, :, None] * A[None, None] * (b[:, 1:] * be[:, 1:])[:, :, None, :]
    X /= X.sum((2, 3), keepdims=True)
    return g, X.sum(1), np.log(c).sum(1) + m[..., 0].sum(1)


def fit(seqs, K):
    """seqs: list of (T, 3) raw observation arrays (one per covered session, equal T). Returns a model dict or None (degenerate)."""
    mu0, sd0 = standardizer(seqs)
    Z = np.stack([transform(x, mu0, sd0) for x in seqs])                 # (S, T, D)
    S_, T, D = Z.shape
    ok = np.isfinite(Z).all(2)                                           # (S, T)
    Z0 = np.where(ok[..., None], Z, 0.)
    pooled = Z[ok]
    order = np.argsort(pooled[:, 0], kind="stable"); groups = np.array_split(order, K)
    mu = np.array([pooled[g].mean(0) for g in groups]); var = np.maximum(np.array([pooled[g].var(0) for g in groups]), VAR_FLOOR)
    A = np.full((K, K), .1 / max(K - 1, 1)); np.fill_diagonal(A, .9); pi = np.full(K, 1. / K)
    w = 1. / np.maximum(1, ok.sum(1))                                    # equal-day weights
    prev = -np.inf
    for it in range(ITERS):
        logb = -.5 * (np.log(2 * np.pi * var)[None, None] + (Z0[:, :, None, :] - mu[None, None]) ** 2 / var[None, None]).sum(3)
        logb = np.where(ok[..., None], logb, 0.)
        g, xi, l = forward_backward(logb, pi, A)
        ll = float((w * l).sum())
        Npi = g[:, 0].sum(0); Nxi = (w[:, None, None] * xi).sum(0)
        gz = g * ok[..., None] * w[:, None, None]
        G = gz.sum((0, 1)); S1 = np.einsum("stk,std->kd", gz, Z0); S2 = np.einsum("stk,std->kd", gz, Z0 ** 2)
        pi = Npi / Npi.sum(); A = Nxi / Nxi.sum(1, keepdims=True)
        mu = S1 / G[:, None]; var = np.maximum(S2 / G[:, None] - mu ** 2, VAR_FLOOR)
        if abs(ll - prev) < TOL * max(1., abs(ll)):
            break
        prev = ll
    share = G / G.sum()
    if not (np.isfinite(mu).all() and np.isfinite(var).all() and np.isfinite(A).all()) or share.min() < .02:
        return None
    erc = mu[:, 0]; med = float(np.median(erc))
    high = tuple(int(k) for k in range(K) if erc[k] >= med - 1e-12)
    m = dict(K=K, mu=mu.round(10).tolist(), var=var.round(10).tolist(), A=A.round(10).tolist(), pi=pi.round(10).tolist(),
             std_mu=mu0.round(10).tolist(), std_sd=sd0.round(10).tolist(), high=list(high), iters=it + 1, share=share.round(6).tolist())
    m["hash"] = hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()[:16]
    return m


def filter_batch(m, Xs):
    """Filtered state probabilities (S, T, K) and validity (S, T) for equal-length sessions; reset to pi each session."""
    mu, var, A, pi = (np.array(m[k]) for k in ("mu", "var", "A", "pi"))
    Z = np.stack([transform(x, np.array(m["std_mu"]), np.array(m["std_sd"])) for x in Xs])
    ok = np.isfinite(Z).all(2); Z0 = np.where(ok[..., None], Z, 0.)
    logb = -.5 * (np.log(2 * np.pi * var)[None, None] + (Z0[:, :, None, :] - mu[None, None]) ** 2 / var[None, None]).sum(3)
    S_, T, K = logb.shape; out = np.zeros((S_, T, K)); a = np.repeat(pi[None], S_, 0)
    for t in range(T):
        pred = np.repeat(pi[None], S_, 0) if t == 0 else a @ A
        x = pred * np.exp(logb[:, t] - logb[:, t].max(1, keepdims=True)); x /= x.sum(1, keepdims=True)
        a = np.where(ok[:, t, None], x, pred); out[:, t] = a
    return out, ok


def filter_day(m, X):
    p, ok = filter_batch(m, [X])
    return p[0], ok[0]


def activate(p, ok, mode):
    act = np.zeros(len(p), bool); on = False
    for t in range(len(p)):
        if ok[t]:
            if not on:
                on = p[t] >= .6 and (mode == "IMMEDIATE" or (t >= 1 and ok[t - 1] and p[t - 1] >= .6))
            elif p[t] < .4:
                on = False
        act[t] = on
    return act


def window_obs(t):
    return t.obs10[FX.window(t)]


def states116(book, K, refit, seed=20261118):
    """Causal per-session filtered pTrend for one (K, refit) fit sequence, plus the random-mapping and fit receipts."""
    cov_days = []; model = None; since = 0; rng = np.random.default_rng(seed + 10 * K + refit); out = []
    for k, t in enumerate(book):
        X = window_obs(t)
        rec = dict(day=t.day, model=None, fallback="WARMUP")
        if len(cov_days) >= 40 and (model is None or since >= refit):
            seqs = [window_obs(book[c]) for c in cov_days[-40:]]
            m = fit(seqs, K)
            since = 0
            if m is not None:
                rnd = sorted(rng.choice(K, size=len(m["high"]), replace=False).tolist())
                m["random_high"] = [int(x) for x in rnd]
                Xs = [window_obs(book[c]) for c in cov_days[-40:]]
                pp, oo = filter_batch(m, Xs)
                m["_train"] = [(pp[n][:, m["high"]].sum(1), oo[n], Xs[n][:, 0]) for n in range(len(Xs))]
            model = m if m is not None else ("DEGENERATE", model)
        cur = model if isinstance(model, dict) else None
        if cur is not None:
            p, ok = filter_day(cur, X)
            rec = dict(day=t.day, model=cur["hash"], fallback=None, pT=p[:, cur["high"]].sum(1), pR=p[:, cur["random_high"]].sum(1), ok=ok,
                       train=cur["_train"])
        elif isinstance(model, tuple):
            rec["fallback"] = "DEGENERATE"
        out.append(rec)
        if int(np.isfinite(X).all(1).sum()) >= MIN_OBS:
            cov_days.append(k); since += 1
    return out
