"""EN41-EN55 lab (PLAN5.md). Builds on the round-4 engine (../2026-11-17-expiry-en/en_lab4.py, immutable) through four
explicit dispatchers installed by install(): signals, setup_signals, choose4 and _decide. With no round-5 field set each
dispatcher calls the original, and check() proves run_day4 still reproduces results4 day by day. Straddles (EN51/52/54)
have their own two-leg day loop. Every decision reads the completed bar and earlier bars; fills are a later bar's.

New Rule fields (all off by default):
  setup3 'ORB' / 'ORB_NOW' / 'ORB_NOON'   EN44 opening-range acceptance + retest (and its two diagnostics)
  setup3 'ESCAPE' / 'ESCAPE_NOW'          EN45 failed escape back toward the frozen futures VWAP (and first-fade diag)
  setup3 'MODEL49' / 'M49_ICPT' / 'M49_TREND'  EN49 ridge entry model, walk-forward by session (and two diagnostics)
  ivgate         EN46 'drift' / 'zero': keep a signal only if a directional repricing pays the option's price
  resp_pick      EN47 one lot of the affordable strike with the best cost / response ratio
  exit_model     EN50 ridge continuation-value exits on E03.2's entries
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
import hashlib, json, math, random, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-expiry-en"))
import en_lab4 as L4  # noqa: E402
import en4_data as D4  # noqa: E402

L3, M, R, L, X, E = L4.L3, L4.M, L4.R, L4.L, L4.X, L4.E
YM = X.YEAR_MIN
SEED = 20261118
EXITSPEC = {}          # (und, day, decision_i, setup) -> dict(fstop=, ftarget=, fdir=) futures-based exits for new setups


@dataclass(frozen=True)
class Rule(L4.Rule):
    ivgate: str = ""
    resp_pick: bool = False
    exit_model: bool = False

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E032 = Rule(**asdict(L4.E032))
SYM = replace(E032, put_mult=1.)                              # equal-risk E03.2: Rs 1,250 parents, Rs 2,500 a day
NEW = dict(put_mult=1., chase=.04)                            # new setups: symmetric caps, 1.04 x decision-ask limit


def und(t):
    return getattr(t, "und", "NIFTY")


# ---------------------------------------------------------------- shared series
_CACHE = {}


def fvol(t):
    return L3.futvol(t)


def fvwap(t):
    """Futures session VWAP on each completed bar (typical price x futures volume, from 09:15), NaN until volume exists."""
    k = ("vwap", id(t))
    if k not in _CACHE:
        v = fvol(t); tp = (t.f[:, 1] + t.f[:, 2] + t.f[:, 3]) / 3; num = den = 0.; out = np.full(t.n, np.nan)
        for i in range(t.n):
            if np.isfinite(v[i]) and np.isfinite(tp[i]) and v[i] > 0:
                num += tp[i] * v[i]; den += v[i]
            if den > 0:
                out[i] = num / den
        _CACHE[k] = out
    return _CACHE[k]


def atr(t, i):
    a = t.features[10][i, 4]
    return float(a) if np.isfinite(a) and a > 0 else math.nan


def at(t, m):
    return int(np.searchsorted(t.minute, m))


def options_at(t, i):
    return bool(np.isfinite(t.q[i, :, 3]).any())


# ---------------------------------------------------------------- EN44: opening-range acceptance and retest
def orb_signals(t, mode):
    """mode 'ORB' (primary), 'ORB_NOW' (immediate breakout diag), 'ORB_NOON' (same retest rule anchored 12:00-12:30)."""
    key = ("orb", id(t), mode)
    if key in _CACHE:
        return _CACHE[key]
    dirs, sd, td = L3._blank(t); vw = fvwap(t)
    r0, r1, last = (556, 585, 690) if mode != "ORB_NOON" else (721, 750, 855)      # bar ends: range 09:15-09:45 (or 12:00-12:30)
    i0, i1, iend = at(t, r0), at(t, r1) + 1, at(t, last)
    w = slice(i0, i1)
    if i1 - i0 < 25 or not (np.isfinite(t.x[w]).all() and np.isfinite(t.f[w]).all()):
        _CACHE[key] = (dirs, sd, td); return _CACHE[key]
    H, Lo, FH, FL = float(np.max(t.x[w, 1])), float(np.min(t.x[w, 2])), float(np.max(t.f[w, 1])), float(np.min(t.f[w, 2]))
    done = set(); plan = None
    for i in range(i1, min(iend + 6, t.n - 1)):
        if not (np.isfinite(t.x[i]).all() and np.isfinite(t.f[i]).all()):
            continue
        A = atr(t, i); c, fc = t.close[i], t.f[i, 3]
        if not np.isfinite(A):
            continue
        if plan:
            d, k0, edge, fedge = plan
            if i - k0 > 5:
                plan = None
            elif abs(t.f[i, 2 if d > 0 else 1] - fedge) <= .25 * A and d * (fc - fedge) > 0 and d * (c - edge) > 0:
                if t.minute[i] < 900 and options_at(t, i) and L4._avail(t, i, d):
                    dirs[i] = d; sd[i] = np.inf
                    EXITSPEC[(und(t), t.day, i, mode)] = dict(fstop=fedge - d * .25 * A, fdir=d)
                plan = None; continue
        if i > iend or plan:
            continue
        for d, edge, fedge in ((1, H, FH), (-1, Lo, FL)):
            if d in done:
                continue
            if d * (c - edge) >= .10 * A and d * (fc - fedge) >= .10 * A and np.isfinite(vw[i]) and d * (fc - vw[i]) > 0:
                done.add(d)
                if mode == "ORB_NOW":
                    if options_at(t, i) and L4._avail(t, i, d):
                        dirs[i] = d; sd[i] = np.inf; EXITSPEC[(und(t), t.day, i, mode)] = dict(fstop=fedge - d * .25 * A, fdir=d)
                else:
                    plan = (d, i, edge, fedge)
                break
    _CACHE[key] = (dirs, sd, td)
    return _CACHE[key]


# ---------------------------------------------------------------- EN45: failed escape back toward the frozen futures VWAP
def escape_signals(t, mode):
    key = ("esc", id(t), mode)
    if key in _CACHE:
        return _CACHE[key]
    dirs, sd, td = L3._blank(t); vw = fvwap(t); fh, fl, fc = t.f[:, 1], t.f[:, 2], t.f[:, 3]
    used = set(); plan = None
    for i in range(16, t.n - 1):
        m = t.minute[i]
        if not 600 < m <= 870 or not np.isfinite(t.f[i]).all() or not np.isfinite(t.close[i - 1:i + 1]).all():
            continue
        A = atr(t, i)
        if not np.isfinite(A):
            continue
        if plan:
            d, k0, Hh, Ll, V, ext = plan
            if i - k0 > 2:
                plan = None
            elif Ll < fc[i] < Hh and d * (t.close[i] - t.close[i - 1]) > 0:
                if options_at(t, i) and L4._avail(t, i, d):
                    dirs[i] = d; sd[i] = np.inf
                    EXITSPEC[(und(t), t.day, i, mode)] = dict(fstop=ext - d * .10 * A, ftarget=V, fdir=d)
                plan = None
            continue
        w = slice(i - 15, i)
        if not np.isfinite(t.f[w]).all():
            continue
        Hh, Ll, V = float(np.max(fh[w])), float(np.min(fl[w])), vw[i]
        if not np.isfinite(V):
            continue
        for s, edge in ((1, Hh), (-1, Ll)):
            if s * (fc[i] - edge) >= .25 * A:
                d = -s; ext = float(fh[i] if s > 0 else fl[i])
                if (s, round(edge, 2)) in used or not (Ll < V < Hh and d * (V - fc[i]) >= .75 * A):
                    break
                used.add((s, round(edge, 2)))
                if mode == "ESCAPE_NOW":
                    if options_at(t, i) and L4._avail(t, i, d):
                        dirs[i] = d; sd[i] = np.inf; EXITSPEC[(und(t), t.day, i, mode)] = dict(fstop=ext - d * .10 * A, ftarget=V, fdir=d)
                else:
                    plan = (d, i, Hh, Ll, V, ext)
                break
    _CACHE[key] = (dirs, sd, td)
    return _CACHE[key]


# ---------------------------------------------------------------- ridge machinery (sufficient statistics, session blocks)
def ridge_stats(Xm, y):
    return dict(n=len(y), sx=Xm.sum(0), sxx=Xm.T @ Xm, sxy=Xm.T @ y, sy=float(y.sum()))


def ridge_fit(stats, w=None, lam=1.0):
    """Standardised ridge (mean squared error + lam * sum(beta^2), unpenalised intercept) from per-session statistics."""
    w = np.ones(len(stats)) if w is None else w
    N = sum(wi * s["n"] for wi, s in zip(w, stats))
    if N < 2:
        return None
    sx = sum(wi * s["sx"] for wi, s in zip(w, stats)); sxx = sum(wi * s["sxx"] for wi, s in zip(w, stats))
    sxy = sum(wi * s["sxy"] for wi, s in zip(w, stats)); sy = sum(wi * s["sy"] for wi, s in zip(w, stats))
    m = sx / N; ybar = sy / N; C = sxx / N - np.outer(m, m); sdv = np.sqrt(np.clip(np.diag(C), 1e-18, None))
    Cz = C / np.outer(sdv, sdv); cz = (sxy / N - m * ybar) / sdv
    bz = np.linalg.solve(Cz + lam * np.eye(len(m)), cz)
    return dict(m=m, s=sdv, b=bz, a=ybar)


def ridge_pred(fit, x):
    return float(fit["a"] + fit["b"] @ ((np.asarray(x) - fit["m"]) / fit["s"]))


def boot_fits(stats, n=200, seed=SEED):
    rng = np.random.default_rng(seed); k = len(stats); out = []
    for _ in range(n):
        w = np.bincount(rng.integers(0, k, k), minlength=k).astype(float)
        f = ridge_fit(stats, w)
        if f:
            out.append(f)
    return out


# ---------------------------------------------------------------- EN49: executable-net entry model
def feat49(t, i, d):
    A = atr(t, i); F, S = t.f[:, 3], t.close
    if i < 21 or not np.isfinite(A) or not np.isfinite(F[i - 20:i + 1]).all() or not np.isfinite(S[i - 5:i + 1]).all():
        return None
    r = np.diff(np.log(F[i - 20:i + 1])); v5, v20 = float(np.var(r[-5:])), float(np.var(r))
    if v20 <= 0:
        return None
    return [d * (F[i] - F[i - 1]) / A, d * (F[i] - F[i - 3]) / A, v5 / v20, d * ((F[i] - S[i]) - (F[i - 5] - S[i - 5])) / A, None,
            (930 - t.minute[i]) / 375]


GRID = tuple(range(585, 886, 5))
_ROWS = {}


def rows49(t):
    """Every 5-minute boundary 09:45-14:45 x side with a native one-lot contract inside Rs 1,250: features and label
    (3-minute exit bid - next-bar ask - fees, over the decision reserve). A missing exit is a conservative full loss."""
    if id(t) in _ROWS:
        return _ROWS[id(t)]
    sp = L4.spec_of(t); rule = replace(SYM, max_lots=1, chase=.04); out = []
    for m in GRID:
        i = at(t, m)
        if i >= t.n - 5 or t.minute[i] != m:
            continue
        for d in (1, -1):
            if not options_at(t, i) or not L4._avail(t, i, d):
                continue
            f = feat49(t, i, d)
            pick = L4.choose4(sp, t, i, d, rule, 1250., 30000.) if f else None
            if not pick:
                continue
            j, _, limit = pick; cl = float(t.q[i, j, 3]); f[4] = 2 * E.half(cl) / L4.ask_of(cl)
            res = L4.reserve(sp, limit, 1)
            f1, p1 = L4.executable(sp, t, i + 1, j, "BUY", "ordinary", 1)
            if not f1 or p1 is None or p1 > limit:
                continue
            f2, p2 = L4.executable(sp, t, i + 4, j, "SELL", "ordinary", 1)
            net = ((p2 - p1) * sp.lot - L4.fee(sp, p1, sp.lot, True) - L4.fee(sp, p2, sp.lot, False)) if f2 else \
                -(p1 * sp.lot + L4.fee(sp, p1, sp.lot, True) + sp.order)
            out.append(dict(i=i, d=d, x=f, y=net / res))
    _ROWS[id(t)] = out
    return out


MODELS = {}            # (und, mode) -> {day: [(i, d) decisions]}
DIAG49 = []            # (und, day, predicted mean, bootstrap 5th percentile, realised label) for every scored EN49 row


def model49_decisions(book, mode):
    """Walk-forward: before each session, fit on all earlier sessions of the same index (>= 40 sessions, >= 500 rows)."""
    stats = []; nrows = 0; dec = {}
    for t in book:
        rows = rows49(t); out = []
        if len(stats) >= 40 and nrows >= 500:
            if mode == "M49_TREND":
                pass
            else:
                fits = boot_fits(stats) if mode == "MODEL49" else None
                full = ridge_fit(stats) if mode == "MODEL49" else None
                icpt = sum(s["sy"] for s in stats) / max(1, sum(s["n"] for s in stats))
                by_i = {}
                for r in rows:
                    by_i.setdefault(r["i"], []).append(r)
                for i, rs in sorted(by_i.items()):
                    best = None
                    for r in rs:
                        if mode == "MODEL49":
                            mu = ridge_pred(full, r["x"]); p5 = float(np.percentile([ridge_pred(f, r["x"]) for f in fits], 5))
                            DIAG49.append((und(t), t.day, mu, p5, r["y"]))
                        else:
                            mu = p5 = icpt
                        if mu > 0 and p5 > 0 and (best is None or mu > best[0]):
                            best = (mu, r["d"])
                    if best:
                        out.append((i, best[1]))
        if mode == "M49_TREND":
            for m in GRID:
                i = at(t, m)
                if i < 4 or i >= t.n - 5 or t.minute[i] != m or not np.isfinite(t.f[i - 3:i + 1, 3]).all():
                    continue
                A = atr(t, i); mv = t.f[i, 3] - t.f[i - 3, 3]
                if np.isfinite(A) and abs(mv) >= .5 * A:
                    out.append((i, 1 if mv > 0 else -1))
        dec[t.day] = out
        if rows:
            Xm = np.array([r["x"] for r in rows], float); y = np.array([r["y"] for r in rows], float)
            stats.append(ridge_stats(Xm, y)); nrows += len(rows)
    return dec


def model_signals(t, mode):
    dirs, sd, td = L3._blank(t)
    for i, d in MODELS.get((und(t), mode), {}).get(t.day, []):
        if options_at(t, i) and L4._avail(t, i, d):
            dirs[i] = d; A = atr(t, i); sd[i] = 2 * A if np.isfinite(A) else np.inf
    return dirs, sd, td


# ---------------------------------------------------------------- EN46 / EN47: repricing with a local implied volatility
def forward(t, i):
    """Expiring-chain forward at the strike nearest the index: K + C - P from the same completed bar."""
    sp = L4.spec_of(t); c = float(t.close[i]); K = round(c / sp.step) * sp.step
    js = {int(t.kinds[j]): j for j in range(len(t.strikes)) if float(t.strikes[j]) == K}
    if len(js) < 2 or not np.isfinite([t.q[i, js[1], 3], t.q[i, js[-1], 3]]).all():
        return math.nan
    return K + float(t.q[i, js[1], 3]) - float(t.q[i, js[-1], 3])


def ivol(t, i, j, Fw):
    T = (930 - t.minute[i]) / YM; px = float(t.q[i, j, 3]); K = float(t.strikes[j]); call = t.kinds[j] == 1
    intrinsic = max(0., (Fw - K) if call else (K - Fw))
    if not np.isfinite(Fw) or T <= 0 or px <= intrinsic + .05:
        return math.nan
    return X.implied(px, Fw, K, T, call)


def price(Fw, K, T, v, call):
    if T <= 0:
        return max(0., (Fw - K) if call else (K - Fw))
    return X.bs(Fw, K, T, v, call)


def _z21():
    from statistics import NormalDist
    return [NormalDist().inv_cdf((k + .5) / 21) for k in range(21)]


Z21 = _z21()


def ivgate_ok(t, i, d, rule):
    """EN46: reprice the contract E03.2 would buy after 8 minutes over a backward-looking physical return forecast."""
    sp = L4.spec_of(t); pick = L4.choose4(sp, t, i, d, rule, 1250. * (rule.put_mult if d < 0 else 1.), 30000.)
    if not pick:
        return False, "no_contract"
    j = pick[0]; Fw = forward(t, i); iv = ivol(t, i, j, Fw)
    F = t.f[:, 3]
    if not np.isfinite(iv) or i < 21 or not np.isfinite(F[i - 20:i + 1]).all():
        return False, "no_iv"
    r = np.diff(np.log(F[i - 20:i + 1])); A = atr(t, i)
    mu = 0. if rule.ivgate == "zero" else .5 * float(np.mean(r[-5:])) * 8
    if np.isfinite(A):
        cap = 2 * A / F[i]; mu = max(-cap, min(cap, mu))
    sig = math.sqrt(max(float(np.var(r)) * 8, 1e-12))
    K = float(t.strikes[j]); call = t.kinds[j] == 1; T = (930 - t.minute[i]) / YM; Th = T - 8 / YM
    cl = float(t.q[i, j, 3]); ask = L4.ask_of(cl); hc = 2 * E.half(cl)
    fees = (L4.fee(sp, ask, sp.lot, True) + L4.fee(sp, ask, sp.lot, False)) / sp.lot
    nets = []
    for v in (iv, .9 * iv):
        ev = float(np.mean([price(Fw * math.exp(mu + sig * z), K, Th, v, call) for z in Z21]))
        nets.append(ev - ask - hc - fees)
    friction = 2 * E.half(cl) + fees
    ok = nets[0] > 0 and nets[1] > 0 and nets[0] > friction
    return ok, "pays" if ok else "refused"


def resp_pick(sp, t, i, d, rule, room):
    """EN47: ATM, first ITM and first three OTM strikes; one lot inside `room`; rank (spread + fees) / smaller predicted
    gain for a 0.50-ATR favourable move in 2 minutes (IV unchanged and -10%); buy the best only if gain > cost."""
    c = float(t.close[i]); s = sp.step; A = atr(t, i); Fw = forward(t, i)
    if not np.isfinite(A) or not np.isfinite(Fw):
        return None
    atm = round(c / s) * s; first = math.floor(c / s) * s + s if d > 0 else math.ceil(c / s) * s - s
    ks = [atm, atm - d * s] + [first + d * s * n for n in range(3)]
    T = (930 - t.minute[i]) / YM; T2 = T - 2 / YM; best = None
    for k in dict.fromkeys(ks):
        js = [j for j in range(len(t.strikes)) if t.kinds[j] == d and float(t.strikes[j]) == float(k)]
        if not js or not np.isfinite(t.q[i, js[0]]).all() or int(t.q[i, js[0], 4] * .2) // sp.lot < 1:
            continue
        j = js[0]; cl = float(t.q[i, j, 3]); ask = L4.ask_of(cl)
        limit = E.down(min(ask * (1 + rule.chase), (room - 2 * sp.order) / (sp.lot * (1 + sp.buy_rate))))
        if limit < ask or L4.reserve(sp, limit, 1) > room + .01:
            continue
        iv = ivol(t, i, j, Fw)
        if not np.isfinite(iv):
            continue
        now = price(Fw, k, T, iv, d > 0)
        g = min(price(Fw + d * .5 * A, k, T2, v, d > 0) - now for v in (iv, .9 * iv))
        cost = 2 * E.half(cl) + (L4.fee(sp, ask, sp.lot, True) + L4.fee(sp, ask, sp.lot, False)) / sp.lot
        if g <= cost:
            continue
        cand = (cost / g, L4.reserve(sp, limit, 1), abs(k - c), j, limit)
        if best is None or cand[:3] < best[:3]:
            best = cand
    return (best[3], 1, best[4]) if best else None


# ---------------------------------------------------------------- EN50: continuation-value exits
EXITM = {}             # (und, day) -> (full fit, bootstrap fits) trained on earlier sessions' E03.2 states


def feat50(t, i, pos, bid, peak):
    A = atr(t, i); F = t.f[:, 3]; d = pos["direction"]
    if not np.isfinite(A) or not np.isfinite(F[i - 3:i + 1]).all() or peak <= 0:
        return None
    return [d * (F[i] - F[i - 1]) / A, d * (F[i] - F[i - 3]) / A, bid / pos["first"], bid / peak, (i - pos["entry_i"]) / 15,
            (930 - t.minute[i]) / 375]


def states50(t, positions):
    """Hypothetical held states at ages 2-14 of each E03.2 entry, including after its real exit; label = the one-minute
    change in executable liquidation value net of the change in sell charges, over the entry price."""
    sp = L4.spec_of(t); out = []
    for p in positions:
        e, j = p["entry_i"], p["j"]; peak = p["first"]
        for a in range(1, 15):
            i = e + a
            if i + 2 >= t.n or t.minute[i] >= 913:
                break
            row = t.q[i, j]
            if not np.isfinite(row).all():
                continue
            bid = L4.bid_of(row[3]); peak = max(peak, bid)
            if a < 2:
                continue
            f = feat50(t, i, p, bid, peak)
            f1, s1 = L4.executable(sp, t, i + 1, j, "SELL", "ordinary", 1)
            f2, s2 = L4.executable(sp, t, i + 2, j, "SELL", "ordinary", 1)
            if f is None or not f1 or not f2:
                continue
            y = ((s2 - s1) - (L4.fee(sp, s2, sp.lot, False) - L4.fee(sp, s1, sp.lot, False)) / sp.lot) / p["first"]
            out.append((f, y))
    return out


def train_exits(book, rule):
    """Walk-forward exit models per index: before each session, fit on earlier sessions' states (>= 40 ticket
    expiries, >= 500 states)."""
    stats = []; nlab = 0
    for t in book:
        if len(stats) >= 40 and nlab >= 500:
            EXITM[(und(t), t.day)] = (ridge_fit(stats), boot_fits(stats))
        r = L4.run_day4(t, replace(rule, exit_model=False), "ordinary", details=True)
        st = states50(t, r["positions"])
        if st:
            Xm = np.array([f for f, _ in st], float); y = np.array([v for _, v in st], float)
            stats.append(ridge_stats(Xm, y)); nlab += len(st)


# ---------------------------------------------------------------- dispatchers
ORIG = {}


def install():
    if ORIG:
        return
    L4._patch()
    ORIG.update(signals=L4.signals, setup_signals=L4.setup_signals, choose4=L4.choose4, _decide=L4._decide)

    def setup_signals(t, rule):
        s = rule.setup3
        if s in ("ORB", "ORB_NOW", "ORB_NOON"):
            return orb_signals(t, s)
        if s in ("ESCAPE", "ESCAPE_NOW"):
            return escape_signals(t, s)
        if s in ("MODEL49", "M49_ICPT", "M49_TREND"):
            return model_signals(t, s)
        return ORIG["setup_signals"](t, rule)

    def signals(t, rule):
        dirs, sd, td = ORIG["signals"](t, rule)
        if getattr(rule, "ivgate", "") and not rule.setup3:
            dirs = dirs.copy()
            for i in np.flatnonzero(dirs):
                ok, why = ivgate_ok(t, int(i), int(dirs[i]), rule)
                GATE[(und(t), t.day, int(i), rule.ivgate)] = why
                if not ok:
                    dirs[i] = 0
        return dirs, sd, td

    def choose4(sp, t, i, d, rule, budget, cash):
        if getattr(rule, "resp_pick", False):
            return resp_pick(sp, t, i, d, rule, min(budget, cash))
        return ORIG["choose4"](sp, t, i, d, rule, budget, cash)

    def _decide(sp, t, i, pos, rule, bid, row):
        reason, qty = ORIG["_decide"](sp, t, i, pos, rule, bid, row)
        spec = EXITSPEC.get((und(t), t.day, pos["decision_i"], rule.setup3)) if rule.setup3 else None
        if reason is None and spec and not pos.get("runner") and np.isfinite(t.f[i, 3]):
            fc, d = t.f[i, 3], spec["fdir"]
            if d * (fc - spec["fstop"]) < 0:
                reason = "FSTOP"
            elif spec.get("ftarget") is not None and d * (fc - spec["ftarget"]) >= 0:
                reason = "FTARGET"
        if getattr(rule, "exit_model", False) and not pos.get("runner") and bid is not None and bid > 0:
            mdl = EXITM.get((und(t), t.day)); age = i - pos["entry_i"]
            pos["mpeak"] = max(pos.get("mpeak", pos["first"]), bid)
            if mdl and age >= 2 and reason in (None, "TIME"):
                f = feat50(t, i, pos, bid, pos["mpeak"])
                if f is not None:
                    full, boots = mdl; v = ridge_pred(full, f)
                    pos["neg"] = pos.get("neg", 0) + 1 if v <= 0 else 0
                    if reason is None and pos["neg"] >= 2:
                        reason = "MODEL_EXIT"
                    elif reason == "TIME" and age < 15 and float(np.percentile([ridge_pred(b, f) for b in boots], 5)) > 0:
                        reason = None; pos["extended"] = True
            if reason is None and age >= 15 and pos.get("extended"):
                reason = "TIME"
        return reason, qty

    L4.setup_signals = setup_signals; L4.signals = signals; L4.choose4 = choose4; L4._decide = _decide


GATE = {}


# ---------------------------------------------------------------- straddles (EN51 / EN52 / EN54)
@dataclass(frozen=True)
class Straddle:
    mode: str = "bracket"          # 'bracket' (EN51/EN54), 'legout' (EN52), 'hold' (diagnostic: no bracket)
    at: int = 780                  # decision bar end (13:00)
    target: float = .25
    stop: float = .25
    legout: float = 1.5
    cheap: float = 0.              # EN54: keep only if straddle / (ATR10 x sqrt(930 - minute)) <= cheap
    reserve: float = 5000.
    flat: int = 914
    runner_keep: float = .5
    hero: float = 9.

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


def straddle_day(t, s, scenario="ordinary", cash=30000., budget=5000., details=False):
    sp = L4.spec_of(t); i0 = at(t, s.at); empty = dict(day=t.day, net=0., trades=0, spent=0., fees=0., unresolved=0, rejected=0,
                                                         positions=[], marked_worst=0., calm=False, missed=[], refusal=None)
    if i0 >= t.n - 2 or t.minute[i0] != s.at or not np.isfinite(t.close[i0]):
        return dict(empty, refusal="no_bar")
    K = round(float(t.close[i0]) / sp.step) * sp.step
    js = {int(t.kinds[j]): j for j in range(len(t.strikes)) if float(t.strikes[j]) == K}
    if len(js) < 2 or not all(np.isfinite(t.q[i0, j]).all() for j in js.values()):
        return dict(empty, refusal="no_atm_pair")
    if s.cheap:
        A = atr(t, i0)
        ratio = (t.q[i0, js[1], 3] + t.q[i0, js[-1], 3]) / (A * math.sqrt(max(1, 930 - t.minute[i0]))) if np.isfinite(A) else math.inf
        if not ratio <= s.cheap:
            return dict(empty, refusal="not_cheap")
    legs = []; room = min(s.reserve, budget, cash)
    for d in (1, -1):
        j = js[d]; ask = L4.ask_of(t.q[i0, j, 3]); legs.append(dict(j=j, d=d, limit=E.down(ask * 1.04)))
    if sum(L4.reserve(sp, g["limit"], 1) for g in legs) > room + .01:
        return dict(empty, refusal="reserve")
    spent = sum(L4.reserve(sp, g["limit"], 1) for g in legs); got = []
    for g in legs:
        f, p = L4.executable(sp, t, i0 + 1, g["j"], "BUY", scenario, 1)
        if f and p is not None and p <= g["limit"]:
            fee0 = L4.fee(sp, p, sp.lot, True)
            got.append(dict(g, entry=p, open=1, net=-fee0, fees=fee0, peak=p, sells=[]))
    if not got:
        return dict(empty, rejected=1, refusal="unfilled", spent=round(spent, 2))
    cost = sum(g["entry"] * sp.lot + g["fees"] for g in got)
    pend = {}; runner = None if len(got) == 2 else got[0]; reason = None if len(got) == 2 else "ONE_LEG"
    if reason:
        pend[id(got[0])] = reason
    for i in range(i0 + 1, t.n):
        for g in got:                                                   # pending sells first
            if g["open"] and id(g) in pend:
                f, p = L4.executable(sp, t, i, g["j"], "SELL", scenario, 1)
                if f:
                    c = L4.fee(sp, p, sp.lot, False); g["net"] += (p - g["entry"]) * sp.lot - c; g["fees"] += c; g["open"] = 0
                    g["sells"].append(dict(i=i, reason=pend.pop(id(g)), price=p))
        if not any(g["open"] for g in got):
            break
        if i >= t.n - 1:
            break
        live = [g for g in got if g["open"] and id(g) not in pend]
        if not live:
            continue
        bids = {}
        for g in live:
            r = t.q[i, g["j"]]
            bids[id(g)] = L4.bid_of(r[3]) if np.isfinite(r).all() and r[4] * .2 >= sp.lot else None
        if t.minute[i] >= s.flat:
            for g in live:
                pend[id(g)] = "FLAT_TIME"
            continue
        if runner is not None:                                           # one leg left (EN52 after leg-out)
            b = bids.get(id(runner))
            if b:
                runner["peak"] = max(runner["peak"], b)
                stop = max(runner["entry"], runner["peak"] * s.runner_keep)
                if b <= stop:
                    pend[id(runner)] = "RUNNER_TRAIL"
                elif b >= runner["entry"] * (1 + s.hero):
                    pend[id(runner)] = "HERO_TARGET"
            continue
        if any(bids[id(g)] is None for g in live):
            continue
        V = sum(bids[id(g)] * sp.lot - L4.fee(sp, bids[id(g)], sp.lot, False) for g in live)
        if s.mode == "hold":
            continue
        if V <= (1 - s.stop) * cost:
            for g in live:
                pend[id(g)] = "STOP"
        elif s.mode == "bracket" and V >= (1 + s.target) * cost:
            for g in live:
                pend[id(g)] = "TARGET"
        elif s.mode == "legout":
            for g in live:
                if bids[id(g)] >= s.legout * g["entry"]:
                    other = [h for h in live if h is not g][0]; pend[id(other)] = "LEG_OUT"; runner = g; g["peak"] = bids[id(g)]
                    break
    unresolved = 0
    for g in got:
        if g["open"]:
            unresolved = 1; g["net"] -= g["entry"] * sp.lot
    net = round(sum(g["net"] for g in got), 2)
    assert net >= -spent - .05, (t.day, net, spent)
    pos = dict(day=t.day, decision_i=i0, entry_i=i0 + 1, direction=0, lots=len(got), entry=round(sum(g["entry"] for g in got), 2),
               first=round(sum(g["entry"] for g in got), 2), net=net, fees=round(sum(g["fees"] for g in got), 2), peak=0., origin="STRADDLE",
               symbol=f"{und(t)}-{K:g}", events=[dict(side="BUY", reason="", lots=1)] + [dict(side="SELL", reason=x["reason"], lots=1, price=x["price"], i=x["i"])
                                                                                       for g in got for x in g["sells"]], unresolved=bool(unresolved),
               exit_i=max([x["i"] for g in got for x in g["sells"]], default=t.n - 1))
    return dict(day=t.day, net=net, trades=1, spent=round(spent, 2), fees=pos["fees"], unresolved=unresolved, rejected=0,
                positions=[pos] if details else [], marked_worst=0., calm=False, missed=[], refusal=None)


# ---------------------------------------------------------------- books: fixed-cap expiries and the Rs 30,000 wallet
def day_budget(arm):
    return arm.reserve if isinstance(arm, Straddle) else (arm.day_budget or E.BUDGET * R.day_scale(arm)) * arm.size_k


def run_day(t, arm, scenario, cash, budget, details):
    if isinstance(arm, Straddle):
        return straddle_day(t, arm, scenario, cash, budget, details)
    return L4.run_day4(t, arm, scenario, cash, budget, details)


def run_fixed(book, arm, scenario="ordinary", details=False, cash=30000.):
    """Each expiry on its own: full day reserve, Rs 30,000 cash, no brakes (signal and lifecycle quality)."""
    days = [run_day(t, arm, scenario, cash, day_budget(arm), details) for t in book]
    return dict(days=days, summary=E.summary(days))


def run_wallet(book, arm, scenario="ordinary", start=30000., retain=.5, details=False):
    """One continuous wallet: brakes on the trading high-water (sweeps never reset them), 50% profit sweeps."""
    P = W = peakP = 0.; days = []; full = day_budget(arm)
    for t in book:
        cash = start + P - W; dd = peakP - P
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        row = run_day(t, arm, scenario, cash, min(full * scale, cash), details)
        P = round(P + row["net"], 2); peakP = max(peakP, P)
        sweep = round(max(0., retain * max(P, 0.) - W), 2) if retain else 0.
        W = round(W + sweep, 2)
        assert abs((start + P - W) + W - (start + P)) < 1e-6 and start + P - W >= -.01
        row.update(scale=scale, P=P, W=W, cash_after=round(start + P - W, 2), sweep=sweep); days.append(row)
    s = E.summary(days)
    return dict(days=days, summary=s, P=P, swept=W, wallet=round(start + P - W, 2), halted=sum(d["scale"] == 0. for d in days),
                first_halt=next((d["day"] for d in days if d["scale"] == 0.), None))


def retention_check():
    """The auditor's example: +2,000 -> 1,000 swept, wallet 31,000; then -1,000 -> wallet 30,000, no new sweep."""
    P = W = 0.; seq = []
    for net in (2000., -1000.):
        P += net; sweep = max(0., .5 * max(P, 0.) - W); W += sweep; seq.append((P, W, 30000 + P - W, sweep))
    assert seq == [(2000., 1000., 31000., 1000.), (1000., 1000., 30000., 0.)], seq
    return "RETENTION_OK"


# ---------------------------------------------------------------- arms (PLAN5.md)
H = dict(start=586)                                           # new setups may enter from 09:46 where option bars exist
ARMS = {
    "E032_30k": E032,                                         # control 2: original tickets in the Rs 30,000 wallet
    "E032_sym": SYM,                                          # control 3: equal-risk E03.2 (Rs 1,250 parents, Rs 2,500 a day)
    "EN44": replace(E032, setup3="ORB", hold=8, **NEW, **H),
    "EN44_now_diag": replace(E032, setup3="ORB_NOW", hold=8, **NEW, **H),
    "EN44_noon_diag": replace(E032, setup3="ORB_NOON", hold=8, **NEW, **H),
    "EN45": replace(E032, setup3="ESCAPE", hold=5, **NEW, **H),
    "EN45_now_diag": replace(E032, setup3="ESCAPE_NOW", hold=5, **NEW, **H),
    "EN46": replace(SYM, ivgate="drift"),
    "EN46_zero_diag": replace(SYM, ivgate="zero"),
    "EN36_sym_diag": replace(SYM, cheap=.6924),
    "EN47": replace(SYM, resp_pick=True),
    "EN47_native1_diag": replace(SYM, max_lots=1),
    "EN49": replace(E032, setup3="MODEL49", hold=3, **NEW, **H),
    "EN49_icpt_diag": replace(E032, setup3="M49_ICPT", hold=3, **NEW, **H),
    "EN49_trend_diag": replace(E032, setup3="M49_TREND", hold=3, **NEW, **H),
    "EN50": replace(SYM, exit_model=True),
    "EN50_3min_diag": replace(SYM, hold=3),
    "EN29_sym_diag": replace(SYM, runner_stall=True),
    "EN51": Straddle("bracket"),
    "EN51_hold_diag": Straddle("hold"),
    "EN52": Straddle("legout"),
    "EN53": replace(E032, atm_itm=True, call_mult=2., put_mult=2.),
    "EN54": Straddle("bracket", cheap=.6924),
    "EN55": replace(E032, patient="cons", scout=True, runner_stall=True),
}
MODEL_MODES = ("MODEL49", "M49_ICPT", "M49_TREND")


def books():
    T = M.tapes(); Xt = D4.tapes()
    return {"NIFTY": T[2023] + T[2024] + T[2025] + Xt["N-X1"] + Xt["N-X2"], "SENSEX": Xt["S-X1"] + Xt["S-X2"]}


def prepare(B, quiet=True):
    """Walk-forward models before any book is run: EN49's entry models and EN50's exit models, per index."""
    for name, book in B.items():
        for mode in MODEL_MODES:
            MODELS[(name, mode)] = model49_decisions(book, mode)
        train_exits(book, SYM)
        if not quiet:
            print("prepared", name, flush=True)


# ---------------------------------------------------------------- checks (counts only, no rupees)
def _straddle_synth():
    t = L4._synthetic_tape(np.full(375, 50.), index_step=0.)
    D = D4._D(); n = 375; i0 = at(t, 780)
    q = np.full((n, 2, 5), np.nan)
    for k in (0, 1):
        q[:, k, 0] = q[:, k, 3] = 30.; q[:, k, 1] = 30.02; q[:, k, 2] = 29.98; q[:, k, 4] = 1e6
    c0 = round(float(t.close[i0]) / 50) * 50

    def tape(qq):
        return D.Tape(t.day, t.x, t.f, qq, np.array([c0, c0]), np.array([1, -1]), ["C", "P"], t.now, t.minute, 0)
    up_ = q.copy(); up_[i0 + 3:, 0, :4] = 50.                       # the call jumps: straddle ~80 of ~60 -> TARGET
    r = straddle_day(tape(up_), ARMS["EN51"], details=True)
    sells = sorted((e["reason"], e["i"]) for e in r["positions"][0]["events"] if e["side"] == "SELL")
    assert [x for x, _ in sells] == ["TARGET", "TARGET"] and all(i == i0 + 4 for _, i in sells), sells
    lo = q.copy(); lo[i0 + 3:, :, :4] = 21.                           # both legs fade to ~42 of ~60 -> STOP
    r = straddle_day(tape(lo), ARMS["EN51"], details=True)
    assert {e["reason"] for e in r["positions"][0]["events"] if e["side"] == "SELL"} == {"STOP"}
    lg = q.copy(); lg[i0 + 3:, 0, :4] = 50.; lg[i0 + 3:, 1, :4] = 25.; lg[i0 + 8:, 0, :4] = 75.; lg[i0 + 12:, 0, :4] = 33.
    r = straddle_day(tape(lg), ARMS["EN52"], details=True)
    rs = {e["reason"]: e["i"] for e in r["positions"][0]["events"] if e["side"] == "SELL"}
    assert rs.get("LEG_OUT") == i0 + 4 and rs.get("RUNNER_TRAIL") == i0 + 13, rs
    assert straddle_day(tape(up_), replace(ARMS["EN54"], cheap=1e-6))["refusal"] == "not_cheap"
    return "STRADDLE_SYNTHETIC_OK"


def _ridge_check():
    rng = np.random.default_rng(1); Xa = rng.normal(size=(300, 6)) * [1, 2, 3, .5, 4, 1] + 3; y = Xa @ [1, -2, 0, 3, .5, 0] + rng.normal(size=300)
    st = [ridge_stats(Xa[k:k + 100], y[k:k + 100]) for k in (0, 100, 200)]; f = ridge_fit(st)
    m, s = Xa.mean(0), Xa.std(0); Z = (Xa - m) / s
    b = np.linalg.solve(Z.T @ Z / 300 + np.eye(6), Z.T @ (y - y.mean()) / 300)
    assert np.allclose(f["b"], b) and abs(f["a"] - y.mean()) < 1e-9
    f2 = ridge_fit(st, np.array([2., 0., 1.]))
    Xw = np.vstack([Xa[:100], Xa[:100], Xa[200:]]); yw = np.concatenate([y[:100], y[:100], y[200:]])
    m, s = Xw.mean(0), Xw.std(0); Z = (Xw - m) / s
    assert np.allclose(f2["b"], np.linalg.solve(Z.T @ Z / 300 + np.eye(6), Z.T @ (yw - yw.mean()) / 300))
    return "RIDGE_OK"


def _truncated(t, i):
    u = D4._D().Tape(t.day, t.x.copy(), t.f.copy(), t.q.copy(), t.strikes, t.kinds, t.symbols, t.now, t.minute, t.invalid)
    u.x[i + 1:] = np.nan; u.f[i + 1:] = np.nan; u.q[i + 1:] = np.nan
    if hasattr(t, "und"):
        u.und = t.und
    KEEP.append(u)                                            # caches key on id(): keep every copy alive (no id reuse)
    return u


KEEP = []


def check():
    install()
    R4 = json.loads((HERE.parent / "2026-11-17-expiry-en/results4.json").read_text())
    T = M.tapes(); Xt = D4.tapes()
    bk = {"2023": T[2023], "2024": T[2024], "2025": T[2025], "N-X1": Xt["N-X1"], "S-X1": Xt["S-X1"]}
    # 1. dispatchers inert with every round-5 field off: results4 reproduces on every book and fill level
    for name, rule in (("E032", L4.E032), ("EN40", L4.ARMS["EN40"]), ("EN35_diag", L4.ARMS["EN35_diag"]), ("EN32", L4.ARMS["EN32"]),
                       ("EN28", L4.ARMS["EN28"]), ("EN36", L4.rule_for("EN36"))):
        ref = R4[name] if name == "E032" else R4[name]["summary"]
        for b, ts in bk.items():
            for sc in ("ordinary", "adverse", "catastrophe"):
                s = L4.run4(ts, Rule(**asdict(rule)), sc)["summary"]
                assert abs(s["net"] - ref[f"{b}|{sc}"]["net"]) < .006 and s["trades"] == ref[f"{b}|{sc}"]["trades"], (name, b, sc)
    print("CHECK_OK en_lab5: dispatchers inert; results4 reproduced for E032, EN40, EN35_diag, EN32, EN28, EN36 (5 books x 3 fills)")
    print(_ridge_check(), retention_check(), _straddle_synth())
    # 2. no future leakage: signals, features and contract picks unchanged with every later bar erased
    B = books(); n = 0
    for name, book in B.items():
        for t in book[::7]:
            for mode in ("ORB", "ORB_NOW", "ORB_NOON", "ESCAPE", "ESCAPE_NOW"):
                fn = orb_signals if "ORB" in mode else escape_signals
                d0 = fn(t, mode)[0].copy()
                for i in np.flatnonzero(d0)[:2]:
                    u = _truncated(t, int(i))
                    assert fn(u, mode)[0][i] == d0[i], (t.day, mode, int(i)); n += 1
            for r in rows49(t)[:4]:
                u = _truncated(t, r["i"]); f = feat49(u, r["i"], r["d"])
                assert f is not None and np.allclose(f[:4] + f[5:], r["x"][:4] + r["x"][5:]), (t.day, r["i"]); n += 1
            d0 = L4.signals(t, SYM)[0]
            for i in np.flatnonzero(d0)[:2]:
                u = _truncated(t, int(i)); rule = replace(SYM, ivgate="drift")
                assert ivgate_ok(u, int(i), int(d0[i]), rule) == ivgate_ok(t, int(i), int(d0[i]), rule)
                assert resp_pick(L4.spec_of(t), u, int(i), int(d0[i]), SYM, 1250.) == resp_pick(L4.spec_of(t), t, int(i), int(d0[i]), SYM, 1250.)
                n += 1
    print("TRUNCATION_OK", n, "decisions unchanged with every later bar erased")
    # 3. counts only
    EXITSPEC.clear(); _CACHE.clear()
    prepare(B)
    cnt = {}
    for name, book in B.items():
        c = {arm: int(sum(np.count_nonzero(L4.setup_signals(t, ARMS[arm])[0]) for t in book))
             for arm in ("EN44", "EN44_now_diag", "EN44_noon_diag", "EN45", "EN45_now_diag", "EN49", "EN49_icpt_diag", "EN49_trend_diag")}
        c["EN49_sessions_after_warmup"] = max(0, len(book) - 40)
        c["EN50_sessions_with_model"] = sum(1 for t in book if (name, t.day) in EXITM)
        c["sessions_without_morning_options"] = int(sum(1 for t in book if not options_at(t, at(t, 600))))
        for t in book:
            L4.signals(t, ARMS["EN46"])
        g = {}
        for k, v in GATE.items():
            if k[0] == name and k[3] == "drift":
                g[v] = g.get(v, 0) + 1
        c["EN46_gate"] = g
        ref = {}
        for t in book:
            r = straddle_day(t, ARMS["EN51"])
            ref[r["refusal"] or "entered"] = ref.get(r["refusal"] or "entered", 0) + 1
        c["EN51_entries"] = ref
        for arm in ARMS:
            run_fixed(book[:8], ARMS[arm])
        cnt[name] = c
    print("COUNTS", json.dumps(cnt))


if __name__ == "__main__":
    check()
