"""Phase P3 helpers (SN171-SN175): the HAR-RV forecast with leave-one-year-out fits, structure exits with a wage
target, an option trade with an index-condition exit, LOYO variant choice and the matched random-day null."""
from __future__ import annotations

import math

import numpy as np

import pw

C, pa, pb = pw.C, pw.pa, pw.pb
I1000 = 45
YEARS = pw.DEV_YEARS


def _park(h, l):
    return (math.log(h / l)) ** 2 / (4 * math.log(2)) if h > 0 and l > 0 and h > l else None


def har_row(S):
    """(x, y): x = [1, log RV yesterday, log RV week, log RV month, log morning RV x 375]; y = log rest-of-day RV x 375
    (minute log returns 10:00-15:10). Daily RVs are Parkinson estimates of the prior trading days (all index days)."""
    pdays = S.s.get("prev_days") or []
    pv = [_park(h, l) for (_o, h, l, _c) in pdays]
    pv = [v for v in pv if v]
    if len(pv) < 22:
        return None
    c = S.F["c"]
    rm = np.diff(np.log(c[: I1000 + 1]))
    rr = np.diff(np.log(c[I1000: pw.FLAT + 1]))
    vm, vr = float(np.mean(rm ** 2)), float(np.mean(rr ** 2))
    if vm <= 0 or vr <= 0:
        return None
    x = np.array([1.0, math.log(pv[-1]), math.log(np.mean(pv[-5:])), math.log(np.mean(pv[-22:])), math.log(vm * 375)])
    return x, math.log(vr * 375)


class HAR:
    def __init__(self, sessions):
        self.rows = {}
        for S in sessions:
            r = har_row(S)
            if r is not None:
                self.rows[S.day] = r

    def fit(self, keep):
        X = np.array([self.rows[d][0] for d in self.rows if keep(d)])
        y = np.array([self.rows[d][1] for d in self.rows if keep(d)])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        s2 = float(np.mean((y - X @ beta) ** 2))
        return beta, s2

    def sigma(self, day, beta, s2):
        """Forecast per-minute sigma of the rest of the day."""
        r = self.rows.get(day)
        if r is None:
            return None
        return math.sqrt(math.exp(float(r[0] @ beta) + 0.5 * s2) / 375.0)


def rho_table(har, sessions, fold_keep):
    """{day: forecast sigma / implied sigma at 10:00} with the HAR fitted on days where fold_keep(day) is True."""
    beta, s2 = har.fit(fold_keep)
    out = {}
    for S in sessions:
        fs = har.sigma(S.day, beta, s2)
        si = C.sigma_imp(S, I1000)
        if fs and si:
            out[S.day] = fs / si
    return out


def settle_target(vals, i, room, target=None, end=pw.FLAT, fallback=-410.0):
    last = None
    for j in range(i + 1, end + 1):
        v = vals[j]
        if v != v:
            continue
        last = v
        if v <= -room:
            return v, j
        if target is not None and v >= target:
            return v, j
    return (last if last is not None else fallback), end


def structure(S, i, kind, wallet, room, target=None, stress=205.0):
    """'strangle1' (1-OTM CE + PE) or 'straddle' (ATM) bought at minute i; None when it does not fit the wallet."""
    K = pw.atm(S, i)
    spec = [(K + pw.STEP, "CE"), (K - pw.STEP, "PE")] if kind == "strangle1" else [(K, "CE"), (K, "PE")]
    got = pb.struct_path(S, i, spec, leg_stress=stress)
    if got is None or got[1] > wallet:
        return None
    return settle_target(got[2], i, room, target, fallback=-2 * stress)[0]


def trade_until(S, i, opt, strike, wallet, target, stop, cond, end=pw.FLAT, stress=pw.STRESS, late=0):
    """pw.trade plus an index-condition exit: when cond(S, j) is True at minute j's close, sell at the bid close."""
    e = i + late
    rec = S.option(strike, opt)
    if rec is None or e >= end or not rec[6][e]:
        return None
    ask = pw.M.ask_of(float(rec[0][3][e]))
    n = pw.lots_for(ask, wallet)
    if n < 1:
        return None
    qty = n * pw.LOT
    tp = pw.price_for_net(ask, qty, n, target, stress, up=True)
    sp = pw.price_for_net(ask, qty, n, stop, stress, up=False)
    _a, bo, bh, bl, bc, bm, tr = rec
    for j in range(e + 1, end + 1):
        if tr[j] and sp >= pw.TICK and bl[j] <= sp:
            return {"net": pw.net_at(ask, min(sp, float(bo[j])), qty, n, stress), "j": j, "reason": "stop", "lots": n}
        if tr[j] and bh[j] >= tp:
            return {"net": pw.net_at(ask, tp, qty, n, stress), "j": j, "reason": "target", "lots": n}
        if cond(S, j) or j == end:
            b = float(bc[j]) if tr[j] else float(bm[j])
            return {"net": pw.net_at(ask, b, qty, n, stress), "j": j, "reason": "cond" if j < end else "time", "lots": n}
    return None


def loyo(variant_nets):
    """variant_nets: {variant: {day: net}} on development days. For each year, the variant best on the other years and
    its result on the year. Returns {year: {variant, net, trades}}, held-out sum, years positive."""
    out = {}
    for y in YEARS:
        best = max(variant_nets, key=lambda v: sum(n for d, n in variant_nets[v].items() if d[:4] != y))
        xs = {d: n for d, n in variant_nets[best].items() if d[:4] == y}
        out[y] = {"variant": best, "net": round(sum(xs.values())), "trades": len(xs)}
    total = sum(v["net"] for v in out.values())
    return out, total, sum(v["net"] > 0 for v in out.values())


def random_days_null(pool_by_year, counts_by_year, draws=2000, seed=171):
    """pool_by_year: {year: [nets of the same structure on every eligible day]}; held-out sum of random day draws."""
    rng = np.random.default_rng(seed)
    tots = []
    for _ in range(draws):
        s = 0.0
        for y, k in counts_by_year.items():
            p = pool_by_year.get(y, [])
            if k and p:
                s += float(np.sum(rng.choice(p, min(k, len(p)), replace=False)))
        tots.append(s)
    return round(float(np.mean(tots))), round(float(np.percentile(tots, 95)))
