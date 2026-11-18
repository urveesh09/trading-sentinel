"""Round-10 causal features (IMPL10.md section 3). Every per-session value reads only that session's completed bars up to the
decision minute and strictly earlier sessions' window minutes. Histories are updated only after a session is finished.
"""
import math
import numpy as np
import round10  # noqa: F401
from data8 import L7, basket as basket8
import signals9 as S9
import families9 as F9
import lab9
L4 = L7.L4
E = L7.E
WIN = (780, 870)
FAST_L = (1, 3, 5)
FAST_P = (80, 90)


def window(t, end=870):
    return (t.minute >= WIN[0]) & (t.minute < end)


def covered(t, x, frac=.95):
    v = x[window(t)]
    return len(v) > 0 and float(np.mean(np.isfinite(v))) >= frac


# ------------------------------------------------------------------ EN113 fast OI series (round-8 accumulation, lag L)
def fast_series(t, L):
    out = np.full(t.n, np.nan)
    if not t.oi_source8["available"]:
        return out
    for i in range(L, t.n):
        out[i] = S9.ref_score(t, i, L)
    return out


# ------------------------------------------------------------------ EN112 extension and acceleration
def accel(t, i, d):
    F = t.f[:, 3]
    if i < 15 or not np.isfinite([F[i], F[i - 3], F[i - 15]]).all():
        return None
    return bool(d * (F[i] - F[i - 3]) / 3 >= d * (F[i] - F[i - 15]) / 15)


def rank_of(x, ref):
    ref = np.asarray(ref, float)
    return float(np.mean(ref <= x + 1e-12))


# ------------------------------------------------------------------ minute features for EN116/EN118/EN120
def rv_ratio(t, i):
    F = t.f[:, 3]
    if i < 30:
        return math.nan
    w = F[i - 30:i + 1]
    if not np.isfinite(w).all():
        return math.nan
    d = np.diff(w); v30 = float(np.mean(d ** 2)); v5 = float(np.mean(d[-5:] ** 2))
    return math.sqrt(v5 / v30) if v30 > 0 else math.nan


def move5(t, i):
    F = t.f[:, 3]; A = t.features[10][i, 4]
    if i < 5 or not np.isfinite([F[i], F[i - 5], A]).all() or A <= 0:
        return math.nan
    return float(F[i] - F[i - 5]) / float(A)


def minute_obs(t):
    """(n, 3) array: ER10, signed 5-minute futures move / ATR10, RV5/RV30 at each bar (nan where unavailable)."""
    out = np.full((t.n, 3), np.nan)
    for i in range(30, t.n):
        out[i] = (S9.er10(t, i), move5(t, i), rv_ratio(t, i))
    return out


def nominal_friction(t, i, d):
    """One-lot friction/reserve of the nearest affordable contract at the nominal Rs 2,500 room (nan if none)."""
    sp = L4.spec_of(t)
    cs = lab9.candidates(sp, t, int(i), d, L7.E03_ENV, 2500., 30000.)
    if not cs:
        return math.nan
    c = min(cs, key=lambda c: (c["dist"], c["K"], c["j"]))
    return float(c["fric"])


# ------------------------------------------------------------------ EN117 range rejections
def range_events(t, buffer):
    """First confirmed failed escape per side per day (13:00-14:29), five-minute separation, frozen bands.
    Bands: q10/q90 of the 30 futures closes before the two event bars; ER30 < 0.25 over the same closes; width > 0."""
    F = t.f[:, 3]; out = []; seen = set(); last = -99
    win = window(t)
    for i in np.flatnonzero(win):
        i = int(i)
        if i < 32:
            continue
        w = F[i - 31:i - 1]
        A = t.features[10][i, 4]
        if not (np.isfinite(w).all() and np.isfinite(F[i]) and np.isfinite(F[i - 1]) and np.isfinite(A) and A > 0):
            continue
        lo, hi = float(np.percentile(w, 10)), float(np.percentile(w, 90))
        den = float(np.abs(np.diff(w)).sum())
        er30 = abs(float(w[-1] - w[0])) / den if den > 0 else math.nan
        if not (hi > lo and np.isfinite(er30) and er30 < .25):
            continue
        d = 0
        if F[i - 1] < lo - buffer * A and lo <= F[i] <= hi:
            d = 1
        elif F[i - 1] > hi + buffer * A and lo <= F[i] <= hi:
            d = -1
        if not d or d in seen or i - last < 5:
            continue
        seen.add(d); last = i
        out.append(dict(i=i, d=d, lo=lo, hi=hi, q25=float(np.percentile(w, 25)), q75=float(np.percentile(w, 75)),
                        A=float(A), F=float(F[i]), er30=er30))
    return out


def range_levels(ev, target, stop_buffer):
    d = ev["d"]
    tgt = (ev["lo"] + ev["hi"]) / 2 if target == "MIDPOINT" else (ev["q75"] if d > 0 else ev["q25"])
    struct = ev["lo"] - stop_buffer * ev["A"] if d > 0 else ev["hi"] + stop_buffer * ev["A"]
    return (d, float(tgt), float(struct))


# ------------------------------------------------------------------ preparation
def prepare10(book):
    """Attach round-10 causal per-session inputs. Requires prepare9 (t.e03, t.S9, t.q9) to have run."""
    fast_hist = {L: {p: S9.Threshold(20, p) for p in FAST_P} for L in FAST_L}
    ext_hist = []                      # per covered session: list of (d, X) for E03 signal minutes in the window
    v_hist = []                        # per covered session: window minute v values (EN114 vol-ratio control)
    er_hist = []                       # per covered session: window ER10 values (EN120 routing rank)
    receipts = []
    for t in book:
        t.q10 = {}; t.state10 = {}; t.logs10 = {}
        # EN113 thresholds (prior 20 covered, current-ATM basket)
        t.S10 = {}
        for L in FAST_L:
            s = t.S9[F9.skey(F9.STD(5))] if L == 5 else fast_series(t, L)
            t.S10[L] = s
            for p in FAST_P:
                t.q10[f"L{L}|p{p}"] = fast_hist[L][p].value()
        for L in FAST_L:
            for p in FAST_P:
                fast_hist[L][p].update(t, t.S10[L])
        # EN112 extension rank / acceleration at E03 signal minutes
        win = window(t)
        evs = [int(i) for i in np.flatnonzero((t.e03 != 0) & win)]
        t.ext10 = {}
        prior = [x for day in ext_hist[-40:] for x in day]
        prior_all = [x for day in ext_hist for x in day]
        today = []
        for i in evs:
            d = int(t.e03[i]); X = S9.extension(t, i, d)
            same40 = [x for dd, x in prior if dd == d]
            same_all = [x for dd, x in prior_all if dd == d]
            t.ext10[i] = dict(d=d, X=None if not np.isfinite(X) else float(X), accel=accel(t, i, d),
                              rank40=rank_of(X, same40) if np.isfinite(X) and len(same40) >= 20 else None, n40=len(same40),
                              rank_all=rank_of(X, same_all) if np.isfinite(X) and len(same_all) >= 20 else None, n_all=len(same_all))
            if np.isfinite(X):
                today.append((d, float(X)))
        A = t.features[10][:, 4]; Fc = t.f[:, 3]
        cov_fut = covered(t, Fc) and covered(t, A)
        # EN114 vol-ratio reference (prior 40 covered)
        t.vref10 = float(np.median(np.concatenate(v_hist[-40:]))) if len(v_hist) >= 40 else math.nan
        vv = np.array([lab_v0(t, int(i)) for i in np.flatnonzero(win)])
        # EN116/EN118/EN120 minute observations
        t.obs10 = minute_obs(t)
        t.er_rank_ref10 = np.concatenate(er_hist[-40:]) if len(er_hist) >= 40 else None
        if cov_fut:
            ext_hist.append(today)
            v_hist.append(vv[np.isfinite(vv)])
            e = t.obs10[win, 0]; er_hist.append(e[np.isfinite(e)])
        receipts.append(dict(day=t.day, covered_futures=bool(cov_fut), e03_events=len(evs),
                             q_fast={k: (None if not np.isfinite(v) else v) for k, v in t.q10.items()}))
    return receipts


def lab_v0(t, k):
    F = t.f[:, 3]
    if k < 30:
        return math.nan
    w = F[k - 30:k + 1]
    if not np.isfinite(w).all():
        return math.nan
    v = float(np.mean(np.diff(w) ** 2))
    return v if v > 0 else math.nan


def er_rank(t, i):
    ref = t.er_rank_ref10; x = t.obs10[i, 0]
    if ref is None or len(ref) < 200 or not np.isfinite(x):
        return math.nan
    return rank_of(x, ref)
