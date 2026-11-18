"""Causal precomputation of round 7's setups and gates (PLAN7.md). Every decision at bar i reads bars <= i of that
session (and, for EN73 / EN83's thresholds, only earlier sessions). check_causal in en_lab7 erases later bars and
later sessions and requires the same decisions.

  EN73  RIDGE73*: ridge (penalty 10, unpenalised intercept, standardised on training) for the 8-minute futures log
        return on 120 prior covered sessions (all sessions, not only expiries; nonoverlapping 8-minute afternoon
        windows, equal weight per session), the next 20 for grouped calibration residuals. The forecast distribution is
        mapped to the frozen E03 contract per side (choose4 in the matched envelope) at the bar's implied volatility:
        trade the stronger side when its calibration-day lower bound (mean - 1.645 sd / sqrt 20) of after-fee rupees > 0.
  EN75  SYNF75*: per-strike parity intervals K + C(bid) - P(ask) .. K + C(ask) - P(bid) at the 5 strikes nearest the
        future, both legs traded in the bar; the prior-20-minute median basis to the future removed; an up (down) bar
        has >= 3 strikes whose interval lies wholly above (below) the future +- half its quoted spread + the basis MAD;
        an event is the first bar of 3 successive such bars.
  EN78  BASIS78*: basis future - index; prior-60-minute median and MAD; an event is the first of 3 successive bars with
        the innovation beyond 3 MAD and 3 quoted future spreads (one per excursion, re-armed inside 1 MAD); the primary
        waits <= 3 bars for the cash to move toward the future while the future keeps >= half the innovation.
  EN83  OI83*: 15-bar OI change at the 5 strikes around the index, puts minus calls over their starting OI; a fresh
        crossing of the 80th percentile of |S| over the previous 20 covered expiries; put writing = up.
  EN76  N11_76 from n11x.py's output (pinned engine).  EN82 / EN84 gates from the same output."""
from __future__ import annotations
import json, math, sqlite3, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import en_lab7 as L7  # noqa: E402
import fut7  # noqa: E402

L6, L4, L3, E = L7.L6, L7.L4, L7.L3, L7.E
PRE7, META7, GATE7, N11 = L7.PRE7, L7.META7, L7.GATE7, L7.N11
und = L7.und
WIN = (780, 870)


def _blank(t):
    return np.zeros(t.n, np.int8)


def _ask(c):
    return L4.ask_of(float(c))


def _bid(c):
    return L4.bid_of(float(c))


# ---------------------------------------------------------------- EN75: synthetic forward
def syn75(t):
    sp = L4.spec_of(t); F = t.f[:, 3]; n = t.n; hf = L7.FUT_SPREAD[und(t)] / 2
    ks = sorted({float(k) for k in t.strikes}); col = {(float(k), int(kd)): j for j, (k, kd) in enumerate(zip(t.strikes, t.kinds))}
    base = np.full(n, np.nan); up = np.zeros(n, int); dn = np.zeros(n, int); up1 = np.zeros(n, bool); dn1 = np.zeros(n, bool)
    ivals = [None] * n
    for i in range(n):
        if not np.isfinite(F[i]):
            continue
        near = sorted(ks, key=lambda k: abs(k - F[i]))[:5]; rows = []
        for K in near:
            jc, jp = col.get((K, 1)), col.get((K, -1))
            if jc is None or jp is None:
                continue
            c, p = t.q[i, jc], t.q[i, jp]
            if not (np.isfinite(c).all() and np.isfinite(p).all() and c[4] > 0 and p[4] > 0):
                continue                                                   # a stale paired leg is missing
            rows.append((K, K + _bid(c[3]) - _ask(p[3]), K + _ask(c[3]) - _bid(p[3]), K + c[3] - p[3]))
        if len(rows) >= 3:
            base[i] = float(np.median([m - F[i] for _, _, _, m in rows])); ivals[i] = rows
    for i in range(20, n):
        if ivals[i] is None:
            continue
        w = base[i - 20:i]; w = w[np.isfinite(w)]
        if len(w) < 10:
            continue
        med = float(np.median(w)); mad = float(np.median(np.abs(w - med))); ref = F[i] + med; band = hf + mad
        up[i] = sum(lo - ref > band for _, lo, _, _ in ivals[i]); dn[i] = sum(hi - ref < -band for _, _, hi, _ in ivals[i])
        K0, lo0, hi0, _ = min(ivals[i], key=lambda r: abs(r[0] - F[i]))
        up1[i] = lo0 - ref > band; dn1[i] = hi0 - ref < -band
    out = {k: _blank(t) for k in ("SYNF75", "SYNF75_FUT", "SYNF75_LAG", "SYNF75_ONE")}; ev = []
    U = up >= 3; D = dn >= 3
    for i in range(3, n):
        for flag, d in ((U, 1), (D, -1)):
            if flag[i] and flag[i - 1] and flag[i - 2] and not flag[i - 3]:
                if U[i] and D[i]:
                    continue
                out["SYNF75"][i] = d
                if np.isfinite(F[[i, i - 3]]).all() and F[i] != F[i - 3]:
                    out["SYNF75_FUT"][i] = int(np.sign(F[i] - F[i - 3]))
                if i + 3 < n:
                    out["SYNF75_LAG"][i + 3] = d
                e = dict(i=i, m=int(t.minute[i]), d=d, n_up=int(up[i]), n_dn=int(dn[i]))
                for h in (1, 3, 8):
                    if i + h < n and np.isfinite([F[i], F[i + h], t.close[i], t.close[i + h], base[i]]).all():
                        e[f"dF{h}"] = round(d * (F[i + h] - F[i]), 2); e[f"dX{h}"] = round(d * (t.close[i + h] - t.close[i]), 2)
                        if np.isfinite(base[i + h]):
                            e[f"dB{h}"] = round(d * (base[i + h] - base[i]), 2)      # > 0: the options moved further; < 0: they came back
                ev.append(e)
        for flag, d in ((up1, 1), (dn1, -1)):
            if flag[i] and flag[i - 1] and flag[i - 2] and not flag[i - 3]:
                if not (up1[i] and dn1[i]):
                    out["SYNF75_ONE"][i] = d
    for k, v in out.items():
        PRE7[(k, und(t), t.day)] = v
    META7[("SYNF75", und(t), t.day)] = ev
    return ev


# ---------------------------------------------------------------- EN78: basis repair
def basis78(t):
    X = t.close.astype(float); F = t.f[:, 3]; n = t.n; fv = L3.futvol(t); spr = L7.FUT_SPREAD[und(t)]
    b = F - X; e = np.full(n, np.nan); s = np.full(n, np.nan)
    for i in range(60, n):
        w = b[i - 60:i]; w = w[np.isfinite(w)]
        if len(w) < 40 or not np.isfinite(b[i]):
            continue
        m = float(np.median(w)); md = float(np.median(np.abs(w - m)))
        if md > 0:
            e[i] = b[i] - m; s[i] = md
    fresh = lambda i: und(t) != "SENSEX" or (np.isfinite(fv[i]) and fv[i] > 0)
    big = lambda i, sg: np.isfinite(e[i]) and sg * e[i] > max(3 * s[i], 3 * spr) and fresh(i)
    out = {k: _blank(t) for k in ("BASIS78", "BASIS78_FUT", "BASIS78_MR", "BASIS78_MOM")}; ev = []; armed = {1: True, -1: True}
    for i in range(62, n):
        for sg in (1, -1):
            if np.isfinite(e[i]) and abs(e[i]) < s[i]:
                armed[sg] = True
            if not armed[sg] or not (big(i, sg) and big(i - 1, sg) and big(i - 2, sg)):
                continue
            armed[sg] = False
            out["BASIS78_FUT"][i] = sg; out["BASIS78_MR"][i] = -sg
            x = dict(i=i, m=int(t.minute[i]), sg=sg, e=round(float(e[i]), 2), mad=round(float(s[i]), 2), entered=None)
            for j in range(i + 1, min(i + 4, n)):
                if np.isfinite([X[j], X[j - 1], F[j], F[i]]).all() and sg * (X[j] - X[j - 1]) > 0 and sg * (F[j] - F[i]) >= -.5 * abs(e[i]):
                    out["BASIS78"][j] = sg; x["entered"] = j
                    if j >= 3 and np.isfinite(F[[j, j - 3]]).all() and F[j] != F[j - 3]:
                        out["BASIS78_MOM"][j] = int(np.sign(F[j] - F[j - 3]))
                    break
            k = min(n - 1, i + 8)
            if np.isfinite([X[k], X[i], F[k], F[i]]).all():
                dX, dF = X[k] - X[i], F[k] - F[i]; rep = sg * (dX - dF)          # > 0: the gap closed
                x.update(dX8=round(float(dX), 2), dF8=round(float(dF), 2), repair8=round(float(rep), 2),
                         cash_share=round(float(sg * dX / rep), 3) if rep > 0 else None)
            ev.append(x)
    for k, v in out.items():
        PRE7[(k, und(t), t.day)] = v
    META7[("BASIS78", und(t), t.day)] = ev
    return ev


# ---------------------------------------------------------------- EN83: OI flow (NIFTY)
SEALED = {"2023": HERE.parent / "2026-11-02-expiry-e02/_local/data.sqlite", "2024": HERE.parent / "2026-11-02-expiry-e02/_local/data.sqlite",
          "2025": HERE.parent / "2026-11-02-expiry-e02/_local/data.sqlite", "2026": HERE.parent / "2026-11-17-expiry-en/_local/exam2026.sqlite"}
_OI = {}


def oi_of(t):
    """OI per (bar, contract) from the same sealed export the tape was built from (NaN where missing)."""
    key = (und(t), t.day)
    if key in _OI:
        return _OI[key]
    p = SEALED[t.day[:4]]; c = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    cols = [r[1] for r in c.execute("PRAGMA table_info(candles)")]
    q = ("SELECT strike, opt, datetime, oi FROM candles WHERE kind='option' AND expiry=? AND datetime BETWEEN ? AND ?" if "underlying" not in cols else
         "SELECT strike, opt, datetime, oi FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND datetime BETWEEN ? AND ?")
    col = {(float(k), "CE" if kd == 1 else "PE"): j for j, (k, kd) in enumerate(zip(t.strikes, t.kinds))}
    oi = np.full((t.n, len(t.strikes)), np.nan)
    for K, o, dt, v in c.execute(q, (t.day, t.day + " 09:15:00", t.day + " 15:29:00")):
        j = col.get((float(K), o))
        kk = (int(dt[11:13]) - 9) * 60 + int(dt[14:16]) - 15
        if j is not None and 0 <= kk < t.n and v is not None and v > 0:
            oi[kk, j] = v
    c.close(); _OI[key] = oi
    return oi


def oi_score(t):
    sp = L4.spec_of(t); oi = oi_of(t); n = t.n; S = np.full(n, np.nan)
    col = {(float(k), int(kd)): j for j, (k, kd) in enumerate(zip(t.strikes, t.kinds))}
    for i in range(15, n):
        if not np.isfinite(t.close[i]):
            continue
        atm = round(float(t.close[i]) / sp.step) * sp.step; c0 = c1 = p0 = p1 = 0.; ok = 0
        for off in (-2, -1, 0, 1, 2):
            K = atm + off * sp.step; jc, jp = col.get((K, 1)), col.get((K, -1))
            if jc is None or jp is None or not np.isfinite([oi[i, jc], oi[i - 15, jc], oi[i, jp], oi[i - 15, jp]]).all():
                continue
            c0 += oi[i - 15, jc]; c1 += oi[i, jc]; p0 += oi[i - 15, jp]; p1 += oi[i, jp]; ok += 1
        if ok >= 3 and c0 + p0 > 0:
            S[i] = ((p1 - p0) - (c1 - c0)) / (c0 + p0)
    return S


def oi83(book):
    lo, hi = WIN; hist = []
    for t in book:
        S = oi_score(t); F = t.f[:, 3]
        win = [i for i in range(t.n) if lo <= t.minute[i] < hi]
        out = {k: _blank(t) for k in ("OI83", "OI83_PX", "OI83_INV")}; ev = []
        if len(hist) >= 20:
            pool = np.concatenate(hist[-20:]); pool = pool[np.isfinite(pool)]
            th = float(np.percentile(np.abs(pool), 80)) if len(pool) >= 200 else math.nan
            for i in win:
                if np.isfinite(th) and np.isfinite(S[i]) and np.isfinite(S[i - 1]) and abs(S[i]) > th >= abs(S[i - 1]):
                    d = int(np.sign(S[i])); out["OI83"][i] = d; out["OI83_INV"][i] = -d
                    if np.isfinite(F[[i, i - 15]]).all() and F[i] != F[i - 15]:
                        out["OI83_PX"][i] = int(np.sign(F[i] - F[i - 15]))
                    ev.append(dict(i=i, m=int(t.minute[i]), d=d, S=round(float(S[i]), 5), th=round(th, 5),
                                   agree_px=int(out["OI83_PX"][i] == d)))
        hist.append(np.array([S[i] for i in win]))
        for k, v in out.items():
            PRE7[(k, und(t), t.day)] = v
        META7[("OI83", und(t), t.day)] = ev


# ---------------------------------------------------------------- EN73: ridge on all-session futures
FEATS = ("r1", "r3", "r8", "r20", "rv30", "tav", "vwap", "orpos", "prev", "tod")
MODEL73 = {}       # (und, day, kind) -> dict(beta, mu, sd, b0, resid [[...] per calib day], scores)


def _sess(und_, d):
    s = fut7.store(und_); i = s["pos"][d]
    return s["F"][i], s["X"][i]


def _prevret(und_, d):
    s = fut7.store(und_); i = s["pos"][d]; cl = []
    for j in range(i - 1, -1, -1):
        x = s["X"][j][:, 3]; x = x[np.isfinite(x)]
        if len(x) >= 300:
            cl.append(float(x[-1]))
            if len(cl) == 2:
                return math.log(cl[0] / cl[1])
    return math.nan


_VB = {}


def _volbase(und_, d, k):
    """Median over the 10 prior covered sessions of the futures volume in bars k-7..k (time-of-day baseline)."""
    key = (und_, d, k)
    if key not in _VB:
        prev = fut7.prior_sessions(und_, d, 10) or []; vs = []
        for p in prev:
            F, _ = _sess(und_, p); w = F[k - 7:k + 1, 4]
            if np.isfinite(w).sum() >= 6:
                vs.append(float(np.nansum(w)))
        _VB[key] = float(np.median(vs)) if len(vs) >= 5 else math.nan
    return _VB[key]


def feats(und_, d, F, X, k):
    c = F[:, 3]
    if k < 30 or not np.isfinite(c[k - 30:k + 1]).all() or np.isfinite(F[:k + 1, 3]).mean() < .9:
        return None
    lr = np.diff(np.log(c[k - 30:k + 1])); r = lambda h: math.log(c[k] / c[k - h])
    ok = np.isfinite(F[:k + 1, 3]) & np.isfinite(F[:k + 1, 4]); v = np.where(ok, F[:k + 1, 4], 0.)
    tp = np.where(ok, (F[:k + 1, 1] + F[:k + 1, 2] + F[:k + 1, 3]) / 3, 0.)
    vwap = float((tp * v).sum() / v.sum()) if v.sum() > 0 else float(np.nanmean((F[:k + 1, 1] + F[:k + 1, 2] + F[:k + 1, 3]) / 3))
    orh, orl = float(np.nanmax(F[:30, 1])), float(np.nanmin(F[:30, 2]))
    vb = _volbase(und_, d, k); tav = float(np.nansum(F[k - 7:k + 1, 4])) / vb if np.isfinite(vb) and vb > 0 else math.nan
    out = (r(1), r(3), r(8), r(20), float(np.std(lr)), math.log(max(tav, 1e-3)) if np.isfinite(tav) else math.nan, math.log(c[k] / vwap),
           (c[k] - (orh + orl) / 2) / (orh - orl) if orh > orl else math.nan, _prevret(und_, d), (556 + k - 780) / 120.)
    return out if all(np.isfinite(out)) else None


_ROWS = {}


def rows73(und_, d):
    """Nonoverlapping 8-minute afternoon windows (decisions at bar ends 12:00, 12:08, ... 14:48): (x, y)."""
    if (und_, d) not in _ROWS:
        F, X = _sess(und_, d); xs, ys = [], []
        for m in range(720, 893, 8):
            k = m - 556
            if k + 8 >= 375 or not np.isfinite(F[[k, k + 8], 3]).all():
                continue
            x = feats(und_, d, F, X, k)
            if x is not None:
                xs.append(x); ys.append(math.log(F[k + 8, 3] / F[k, 3]))
        _ROWS[(und_, d)] = (np.array(xs).reshape(-1, len(FEATS)), np.array(ys))
    return _ROWS[(und_, d)]


def ridge(sessions, lam=10., icpt_only=False):
    X, y, w = [], [], []
    for d in sessions:
        a, b = rows73(*d)
        if len(b):
            X.append(a); y.append(b); w.append(np.full(len(b), 1. / len(b)))
    if len(X) < .75 * len(sessions):
        return None
    X, y, w = np.vstack(X), np.concatenate(y), np.concatenate(w)
    mu = (w[:, None] * X).sum(0) / w.sum(); sd = np.sqrt((w[:, None] * (X - mu) ** 2).sum(0) / w.sum()); sd[sd == 0] = 1.
    Z = (X - mu) / sd; b0 = float((w * y).sum() / w.sum())
    if icpt_only:
        beta = np.zeros(X.shape[1])
    else:
        A = Z.T @ (w[:, None] * Z) + lam * np.eye(X.shape[1]); beta = np.linalg.solve(A, Z.T @ (w * (y - b0)))
    return dict(mu=mu, sd=sd, b0=b0, beta=beta)


def predict(mdl, x):
    return mdl["b0"] + float(((np.asarray(x) - mdl["mu"]) / mdl["sd"]) @ mdl["beta"])


def fit73(und_, day, kind, expiry_days):
    """kind: 'ridge' | 'icpt' (all sessions) | 'exp' (expiry sessions only). None = abstain (too little history)."""
    key = (und_, day, kind)
    if key in MODEL73:
        return MODEL73[key]
    if kind == "exp":
        prior = [d for d in expiry_days if d < day and fut7.covered(und_, d)]
        if len(prior) < 40:
            MODEL73[key] = None; return None
        train, cal = prior[:-20][-120:], prior[-20:]
    else:
        prior = fut7.prior_sessions(und_, day, 140)
        if prior is None:
            MODEL73[key] = None; return None
        train, cal = prior[:120], prior[120:]
    mdl = ridge([(und_, d) for d in train], icpt_only=(kind == "icpt"))
    if mdl is None:
        MODEL73[key] = None; return None
    res = []
    for d in cal:
        a, b = rows73(und_, d)
        if len(b):
            res.append(np.array([y - predict(mdl, x) for x, y in zip(a, b)]))
    if len(res) < 15:
        MODEL73[key] = None; return None
    mdl.update(resid=res, train=(train[0], train[-1]), cal=(cal[0], cal[-1]))
    MODEL73[key] = mdl
    return mdl


_IVS = {}


def iv_shift(book, idx):
    """Median 8-minute relative change of the ATM call's implied volatility on the 20 covered expiries before book[idx]."""
    ch = []
    for t in book[max(0, idx - 20):idx]:
        for m in (780, 800, 820, 840, 860):
            i = L7.at(t, m)
            if i + 8 >= t.n:
                continue
            got = []
            for ii in (i, i + 8):
                Fw = L7.forward(t, ii); sp = L4.spec_of(t)
                if not np.isfinite(Fw):
                    break
                K = round(float(t.close[i]) / sp.step) * sp.step
                j = next((j for j in range(len(t.strikes)) if float(t.strikes[j]) == K and t.kinds[j] == 1), None)
                v = L7.ivol(t, ii, j, Fw) if j is not None and np.isfinite(t.q[ii, j, 3]) else math.nan
                got.append(v)
            if len(got) == 2 and np.isfinite(got).all() and got[0] > 0:
                ch.append(got[1] / got[0] - 1)
    return float(np.median(ch)) if len(ch) >= 30 else 0.


def value73(t, i, d, mdl, rule, zero=False, ivs=0.):
    """Lower bound (Rs, after fees) and the mean predicted sale value for side d at bar i, or None if infeasible."""
    sp = L4.spec_of(t); pick = L4.choose4(sp, t, i, d, rule, 2500., 30000.)
    if not pick:
        return None
    j, lots, limit = pick; Fw = L7.forward(t, i)
    if not np.isfinite(Fw):
        return None
    iv = L7.ivol(t, i, j, Fw)
    if not np.isfinite(iv):
        return None
    x = feats(und(t), t.day, *_sess(und(t), t.day), i)
    if x is None:
        return None
    mu = 0. if zero else predict(mdl, x)
    T1 = max(0., (930 - float(t.minute[i]) - 8) / L7.YM); K = float(t.strikes[j]); call = t.kinds[j] == 1
    units = lots * sp.lot; ask = _ask(t.q[i, j, 3]); g = []; vs = []
    allres = np.concatenate(mdl["resid"]); shift = -float(allres.mean()) if zero else 0.
    for r in mdl["resid"]:
        V = L7.bsv(Fw * np.exp(mu + r + shift), K, T1, iv * (1 + ivs), call)
        vb = V - E.half(float(V.mean()))
        sale = float(np.maximum(vb, 0.).mean())
        g.append((sale - ask) * units - L4.fee(sp, ask, units, True) - L4.fee(sp, max(sale, .05), units, False)); vs.append(float(V.mean()))
    g = np.array(g); lb = float(g.mean() - 1.645 * g.std(ddof=1) / math.sqrt(len(g)))
    return dict(lb=lb, mean=float(g.mean()), j=int(j), lots=int(lots), V=float(np.mean(vs)), mu=mu)


def ridge73(book):
    rule = L7.E03_ENV; u = und(book[0]); exp_days = [t.day for t in book]; scores = []
    for idx, t in enumerate(book):
        outs = {k: _blank(t) for k in ("RIDGE73", "RIDGE73_ZERO", "RIDGE73_ICPT", "RIDGE73_EXP", "RIDGE73_IVS")}; ev = []
        models = {"RIDGE73": fit73(u, t.day, "ridge", exp_days), "RIDGE73_ICPT": fit73(u, t.day, "icpt", exp_days),
                  "RIDGE73_EXP": fit73(u, t.day, "exp", exp_days)}
        models["RIDGE73_ZERO"] = models["RIDGE73"]; models["RIDGE73_IVS"] = models["RIDGE73"]
        ivs = iv_shift(book, idx) if models["RIDGE73"] is not None else 0.
        if fut7.covered(u, t.day) and models["RIDGE73"] is not None:
            a, b = rows73(u, t.day)                            # genuinely forward: this expiry never trained or calibrated
            for x, y in zip(a, b):
                scores.append(dict(day=t.day, y=float(y), ridge=predict(models["RIDGE73"], x), icpt=predict(models["RIDGE73_ICPT"], x),
                                   exp=predict(models["RIDGE73_EXP"], x) if models["RIDGE73_EXP"] else None))
            for i in range(t.n):
                if not (WIN[0] <= t.minute[i] < WIN[1]) or i + 9 >= t.n:
                    continue
                for name, mdl in models.items():
                    if mdl is None:
                        continue
                    best = None
                    for d in (1, -1):
                        v = value73(t, i, d, mdl, rule, zero=(name == "RIDGE73_ZERO"), ivs=ivs if name == "RIDGE73_IVS" else 0.)
                        if v and v["lb"] > 0 and (best is None or v["lb"] > best[1]["lb"]):
                            best = (d, v)
                        if name == "RIDGE73" and v:
                            act = t.q[i + 9, v["j"], 3]
                            ev.append(dict(i=i, d=d, lb=round(v["lb"], 2), V=round(v["V"], 2), actual=float(act) if np.isfinite(act) else None,
                                           mu=v["mu"]))
                    if best:
                        outs[name][i] = best[0]
        for k, v in outs.items():
            PRE7[(k, u, t.day)] = v
        META7[("RIDGE73", u, t.day)] = ev
    META7[("RIDGE73_scores", u)] = scores


# ---------------------------------------------------------------- EN76 / EN82 / EN84 from the isolated N11 process
def n11(path, B):
    got = json.loads(Path(path).read_text())
    for r in got["days"]:
        N11[(r["und"], r["day"])] = r
        if r.get("missing"):
            continue
        if r["und"] == "NIFTY":
            GATE7[("ADX", r["day"])] = r["adx"]
        GATE7[("RVOL", r["day"])] = {s["m"]: (s["rvol"] if s.get("rvol") is not None else math.nan) for s in r["signals"]}
    for bk, book in B.items():
        for t in book:
            r = N11.get((bk, t.day)); out = _blank(t); ev = []
            if r and not r.get("missing"):
                pos = {int(m): i for i, m in enumerate(t.minute)}
                for s in r["signals"]:
                    if s["d"] and s["m"] in pos:
                        out[pos[s["m"]]] = s["d"]; ev.append(dict(m=s["m"], d=s["d"], strategy=s["strategy"]))
            PRE7[("N11_76", bk, t.day)] = out; META7[("N11_76", bk, t.day)] = ev
    return dict(pinned_commit=got["pinned_commit"], pinned_tree_sha256=got["pinned_tree_sha256"], settings=got["settings"], regime=got["regime"])


def prepare(B, n11_path=HERE / "n11-signals.json", quiet=True):
    info = n11(n11_path, B) if Path(n11_path).exists() else None
    for bk, book in B.items():
        for t in book:
            syn75(t); basis78(t)
        if bk == "NIFTY":
            oi83(book)
        ridge73(book)
        if not quiet:
            print("prepared", bk, flush=True)
    return info
