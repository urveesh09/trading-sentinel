"""SN221-SN230 engine (PLAN.md), on SN201's wk.py and SN211's wk2.py (neither edited).

One weekly short-premium position per expiry (wk.trade's entry, fills, 15:15 lean marks and settlement, exactly), with
  * exits on the later 15:15 marks, in this order: stop (value <= -stop x credit), the SN217 expiry-day gate, pre;
  * entry day k in {1, 2, 3, "F", "M"}; "M" = the earliest session after which no calendar gap > 1 day remains;
  * trend filters (yesterday's 14-day Wilder ADX, the 10-session efficiency ratio) that only skip weeks;
  * a futures delta hedge (Black-Scholes deltas, sigma from the entry straddle), executed a minute after the trigger
    at the futures close +/- a half-spread, Zerodha futures charges, Rs 100 per lot per order (+Rs 100 before 09:20).
With no hedge the results equal wk.trade / wk2.simulate(gate) (SN222 parity). The unseen NIFTY 2020-21 exam stays
sealed (sample("EXAM") refuses) until SN228 sets UNSEAL_EXAM."""
from __future__ import annotations

import datetime as dt
import math
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-14-sn211"))
import wk2  # noqa: E402

wk = wk2.wk
LOCAL = HERE / "_local"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
EXAM_LEAN = LOCAL / "mirror-nifty-2021-lean.sqlite"
EXAM_FULL = LOCAL / "mirror-nifty-2021-full.sqlite"
FUT_MIRROR = {"EXAM": LOCAL / "fut-nifty-2021.sqlite", "N2122": LOCAL / "fut-nifty-2122.sqlite",
              "SENSEX": LOCAL / "fut-sensex.sqlite"}
EXAM_EXPIRY = ("2020-10-01", "2021-11-25")
EXAM_INDEX = ("2020-06-01", "2021-12-01")
UNSEAL_EXAM = False
SEEN = ("DEV", "TEST", "N2122", "SENSEX")

wk.STRUCTS.setdefault("IC 0.5/1.5", (0.5, 1.5))      # far wings (SN225): shorts +/-0.5 Q, wings 1.5 Q beyond
wk.STRUCTS.setdefault("IF 2.0", (0.0, 2.0))          # straddle with wings +/-2 Q
STRUCTURES = ("STRADDLE", "STRANGLE 0.25", "STRANGLE 0.5", "IC 0.5/1.5", "IF 2.0")
KS = (1, 2, 3, "F", "M")
EXITS = {"settle": ("settle", None, None), "settle stop1": ("settle", 1.0, None), "gate": ("settle", None, -0.25),
         "gate stop1": ("settle", 1.0, -0.25), "pre": ("pre", None, None), "pre stop1": ("pre", 1.0, None)}
HEDGES = {"none": None, "H1": {"band": 0.6, "every": 1, "lots": 1}, "H15": {"band": 0.6, "every": 15, "lots": 1},
          "H15x2": {"band": 0.6, "every": 15, "lots": 2}}
FILTERS = {"none": None, "ADX<25": ("adx", 25.0), "ADX<20": ("adx", 20.0), "ER<0.4": ("er", 0.4)}
NIGHT = 0.15                  # session units per night in the hedge's clock
FREEZE = 315                  # 14:30 on expiry day: no new hedge orders after it
HALF = {"NIFTY": 0.75, "SENSEX": 3.0}
FUT_STRESS = 100.0
OPEN_PEN = 100.0
TWAP = (345, 375)             # 15:00 .. 15:29


# ---- futures ---------------------------------------------------------------------------------------------------
def fut_charges(price, lots, side, mk):
    """Zerodha futures charges for one order (Nov 2026 schedule; NSE transaction rate used for BSE too)."""
    v = abs(price) * mk["lot"] * lots
    brk = min(20.0, 0.0003 * v)
    exch = 0.0000173 * v
    sebi = 1e-6 * v
    stt = 0.0002 * v if side == "sell" else 0.0
    stamp = 0.00002 * v if side == "buy" else 0.0
    return brk + stt + exch + sebi + stamp + 0.18 * (brk + exch + sebi)


class Fut:
    """Futures minute closes per day: {expiry: array(375)}; the contract is the first expiry >= the option expiry."""

    def __init__(self, sample):
        self.sample = sample
        self.dev = sample in ("DEV", "TEST")
        self.paths = list(wk.DEV_SOURCES.values()) if self.dev else [FUT_MIRROR[sample]]
        self.und = None if self.dev else ("SENSEX" if sample == "SENSEX" else "NIFTY")
        self.cache, self._cons = {}, {}

    def _con(self, p):
        if p not in self._cons:
            self._cons[p] = sqlite3.connect(f"file:{Path(p).as_posix()}?mode=ro", uri=True)
        return self._cons[p]

    def day(self, d):
        if d in self.cache:
            return self.cache[d]
        order = self.paths
        if self.dev and d[:4] in wk.DEV_SOURCES:
            first = wk.DEV_SOURCES[d[:4]]
            order = [first] + [p for p in self.paths if p != first]
        out = {}
        for p in order:
            if self.dev:
                rows = self._con(p).execute("SELECT expiry, datetime, close FROM candles WHERE kind='future' AND datetime >= ? "
                                            "AND datetime < ?", (d, d + "~")).fetchall()
            else:
                rows = self._con(p).execute("SELECT expiry, datetime, close FROM candles WHERE kind='future' AND underlying=? "
                                            "AND interval='1minute' AND datetime >= ? AND datetime < ?", (self.und, d, d + "~")).fetchall()
            for e, t, c in rows:
                m = wk._minute(t)
                if c is not None and 0 <= m < wk.NM:
                    out.setdefault(e[:10], np.full(wk.NM, np.nan))[m] = float(c)
            if out:
                break
        self.cache[d] = out
        return out

    def series(self, e_opt, d):
        day = self.day(d)
        ks = sorted(x for x in day if x >= e_opt)
        return day[ks[0]] if ks else None


# ---- samples ---------------------------------------------------------------------------------------------------
class Sample:
    def __init__(self, name, mk, data, weeks, fut, mins_source, feat_idx):
        self.name, self.mk, self.data, self.weeks, self.fut = name, mk, data, weeks, fut
        self.W = len(weeks)
        self._mins_source = mins_source
        self._mins = None
        self.feats = features(feat_idx)
        self.base = {}
        self.hpaths = {}

    @property
    def mins(self):
        if self._mins is None:
            if self._mins_source == "EXAM":
                m = wk2.Minutes("NIFTY")
                m.paths = [EXAM_FULL]
            else:
                m = wk2.Minutes(self._mins_source)
            self._mins = m
        return self._mins


def _cached(name, build):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"{name}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    data = build()
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(p)
    return data


def exam_weeks(data):
    out = []
    for e, days in wk.expiries(data):
        if not (EXAM_EXPIRY[0] <= e <= EXAM_EXPIRY[1]):
            continue
        if len(days) > 5:                                    # PLAN: 2021-07-08 carries the missing 07-01 week
            cut = (dt.date.fromisoformat(e) - dt.timedelta(days=7)).isoformat()
            days = [d for d in days if d > cut]
        out.append((e, days))
    return out


_S = {}


def sample(name):
    if name in _S:
        return _S[name]
    if name in ("DEV", "TEST"):
        D = wk.dev_data()
        N = wk.exam_data("NIFTY")
        s = Sample(name, wk.NIFTY, D, wk.split(wk.expiries(D), name.lower()), Fut(name), "dev", [D["idx"], N["idx"]])
    elif name == "N2122":
        N = wk.exam_data("NIFTY")
        s = Sample(name, wk.NIFTY, N, wk.expiries(N), Fut(name), "NIFTY", [N["idx"]])
    elif name == "SENSEX":
        X = wk.exam_data("SENSEX")
        s = Sample(name, wk.SENSEX, X, wk.expiries(X), Fut(name), "SENSEX", [X["idx"]])
    elif name == "EXAM":
        if not UNSEAL_EXAM:
            raise SystemExit("the NIFTY 2020-21 exam is sealed until SN228")
        E = _cached("wk3-exam-nifty-2021", lambda: wk.read_source(EXAM_LEAN, "NIFTY"))
        s = Sample(name, wk.NIFTY, E, exam_weeks(E), Fut(name), "EXAM", [E["idx"]])
    else:
        raise KeyError(name)
    _S[name] = s
    return s


# ---- causal daily features ---------------------------------------------------------------------------------------
def daily_bars(idx_dicts):
    seen, bars = set(), []
    for idx in idx_dicts:                                     # the first dict wins a day both hold
        for d, a in idx.items():
            if d in seen:
                continue
            v = a[~np.isnan(a)]
            if len(v) < 200:
                continue
            seen.add(d)
            bars.append((d, float(v[0]), float(v.max()), float(v.min()), float(v[-1])))
    bars.sort()
    return bars


def _adx(bars, n=14):
    """Wilder ADX after each bar (None until 2n bars)."""
    out = [None] * len(bars)
    tr_s = pdm_s = mdm_s = None
    dx = []
    adx = None
    for i in range(1, len(bars)):
        _d, _o, h, l, _c = bars[i]
        _d1, _o1, h1, l1, c1 = bars[i - 1]
        tr = max(h - l, abs(h - c1), abs(l - c1))
        up, dn = h - h1, l1 - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        if i <= n:
            tr_s = (tr_s or 0.0) + tr
            pdm_s = (pdm_s or 0.0) + pdm
            mdm_s = (mdm_s or 0.0) + mdm
            if i < n:
                continue
        else:
            tr_s = tr_s - tr_s / n + tr
            pdm_s = pdm_s - pdm_s / n + pdm
            mdm_s = mdm_s - mdm_s / n + mdm
        pdi = 100.0 * pdm_s / tr_s if tr_s else 0.0
        mdi = 100.0 * mdm_s / tr_s if tr_s else 0.0
        x = 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        dx.append(x)
        if len(dx) == n:
            adx = sum(dx) / n
        elif len(dx) > n:
            adx = (adx * (n - 1) + x) / n
        out[i] = adx
    return out


def features(idx_dicts):
    """{day: {"adx": yesterday's ADX14, "closes": the 10 closes before the day}} for every day in the bars."""
    bars = daily_bars(idx_dicts)
    adx = _adx(bars)
    out = {}
    for i, b in enumerate(bars):
        out[b[0]] = {"adx": adx[i - 1] if i >= 1 else None,
                     "closes": [x[4] for x in bars[max(0, i - 10):i]] if i >= 10 else None}
    return out


def passes(smp, d0, flt):
    if flt is None:
        return True
    f = smp.feats.get(d0)
    if f is None:
        return False                                          # PLAN: a missing feature skips the week
    kind, thr = flt
    if kind == "adx":
        return f["adx"] is not None and f["adx"] < thr
    if f["closes"] is None:
        return False
    s = wk.idx_px(smp.data, d0)
    if s is None:
        return False
    c = f["closes"] + [s]
    path = sum(abs(c[i] - c[i - 1]) for i in range(1, len(c)))
    return path > 0 and abs(c[-1] - c[0]) / path < thr


# ---- entry day ---------------------------------------------------------------------------------------------------
def k_of(k, e, days):
    """An integer k (sessions before expiry) or None; "M" = earliest session with no calendar gap > 1 day to expiry."""
    if k != "M":
        return k
    seq = list(days) + [e]
    dd = [dt.date.fromisoformat(x) for x in seq]
    i = len(dd) - 1
    while i > 0 and (dd[i] - dd[i - 1]).days == 1:
        i -= 1
    if i == len(dd) - 1:
        return None
    return len(days) - i


def base_trade(smp, e, days, struct, k):
    key = (e, struct, k)
    if key not in smp.base:
        kk = k_of(k, e, days)
        t = None
        if kk is not None:
            t = wk.trade(smp.mk, smp.data, e, days, kk, struct, "settle", None)
            if t is not None and ("net" not in t or t["net"] is None):
                t = None
        smp.base[key] = t
    return smp.base[key]


# ---- the hedge ---------------------------------------------------------------------------------------------------
def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _delta(legs, S, T, sig):
    st = sig * math.sqrt(max(T, 1e-6))
    tot = 0.0
    for k, o, sgn in legs:
        d1 = (math.log(S / k) + 0.5 * st * st) / st
        n = _ncdf(d1)
        tot += sgn * (n if o == "CE" else n - 1.0)
    return tot


def hedge_path(smp, t, e, days, hp):
    """The hedge's value at each later 15:15 (as if closed then) and at settlement (closed at the futures 15:00-15:29
    mean), with order counts; it depends only on the index, the futures and the position's strikes."""
    mk, lot = smp.mk, smp.mk["lot"]
    L, band, every = hp["lots"], hp["band"], hp["every"]
    half = HALF[mk["name"]]
    d0 = t["entry"]
    hold = [d for d in days if d >= d0] + [e]
    n_after = {d: sum(1 for x in days if d < x) for d in hold}       # sessions strictly after d, before expiry

    def T_of(d, j):
        if d == e:
            return max(1e-4, (360 - j) / 375.0)
        return (375 - j) / 375.0 + n_after[d] + 360 / 375.0 + NIGHT * (n_after[d] + 1)

    S0 = t["S0"] or wk.idx_px(smp.data, d0) or float(t["K0"])   # post-freeze fix (disclosed): no index print at entry
    T0 = T_of(d0, wk.I_ENTRY)
    sig = t["Q"] / (0.7979 * S0 * math.sqrt(T0))
    legs = t["legs"]
    h, cash, costs, orders, fallback = 0, 0.0, 0.0, 0, 0
    basis = None
    pending = None
    marks, out = {}, {"orders": 0, "costs": 0.0, "fallback": 0}

    def px_at(F, S, j):
        nonlocal basis
        f = F[j] if F is not None and F[j] == F[j] else None
        if f is not None and S is not None:
            basis = f - S
        if f is not None:
            return f, False
        if S is not None and basis is not None:
            return S + basis, True
        return None, False

    def close_value(f):
        if h == 0:
            return cash
        if h > 0:
            p = f - half
            return cash + h * lot * p - fut_charges(p, h, "sell", mk) - FUT_STRESS * h
        p = f + half
        return cash + h * lot * p - fut_charges(p, -h, "buy", mk) - FUT_STRESS * (-h)

    for d in hold:
        a = smp.data["idx"].get(d)
        F = smp.fut.series(e, d)
        j0 = wk.I_ENTRY + 1 if d == d0 else 0
        last_f = None
        for j in range(j0, wk.NM):
            S = float(a[j]) if a is not None and a[j] == a[j] else None
            f, fb = px_at(F, S, j)
            if f is not None:
                last_f = f
            if pending is not None and f is not None:
                q = pending
                side = "buy" if q > 0 else "sell"
                p = f + half if q > 0 else f - half
                c = fut_charges(p, abs(q), side, mk) + FUT_STRESS * abs(q) + (OPEN_PEN * abs(q) if j < wk2.OPEN_MIN else 0.0)
                cash -= q * lot * p
                cash -= c
                costs += c
                orders += 1
                fallback += int(fb)
                h += q
                pending = None
            if d != d0 and d != e and j == wk.I_ENTRY:
                marks[d] = close_value(last_f) if last_f is not None else None
            if d == e and j >= FREEZE:
                continue
            if S is not None and pending is None and (j % every == 0 or every == 1):
                net = L * _delta(legs, S, T_of(d, j), sig) + h
                if abs(net) > band:
                    target = -int(round(L * _delta(legs, S, T_of(d, j), sig)))
                    if target != h:
                        pending = target - h
        if d == e:
            w = []
            for j in range(*TWAP):
                S = float(a[j]) if a is not None and a[j] == a[j] else None
                f = F[j] if F is not None and F[j] == F[j] else (S + basis if S is not None and basis is not None else None)
                if f is not None:
                    w.append(f)
            out["settle"] = close_value(sum(w) / len(w)) if w else (close_value(last_f) if last_f is not None else cash)
    out.update(marks=marks, orders=orders, costs=round(costs, 2), fallback=fallback, end_lots=h)
    return out


# ---- the variant -------------------------------------------------------------------------------------------------
def trade3(smp, e, days, struct, k, exit_name, hedge_name="none", flt_name="none"):
    exit_, stop, gate = EXITS[exit_name]
    hp = HEDGES[hedge_name]
    flt = FILTERS[flt_name]
    t = base_trade(smp, e, days, struct, k)
    if t is None:
        return None
    if not passes(smp, t["entry"], flt):
        return {"skip": "filter", "entry": t["entry"], "expiry": e}
    if exit_ == "pre" and t["k"] == 1:
        return None
    L = hp["lots"] if hp else 1
    H = None
    if hp:
        key = (e, struct, k, hedge_name)
        if key not in smp.hpaths:
            smp.hpaths[key] = hedge_path(smp, t, e, days, hp)
        H = smp.hpaths[key]
    lot = smp.mk["lot"]
    credit_rs = t["credit_pts"] * lot * L
    legs = t["legs"]
    Kc, Kp, Q = legs[0][0], legs[1][0], t["Q"]
    d0 = t["entry"]
    marks = {d0: L * t["marks"][d0]}

    def done(v, d, why):
        marks[d] = v
        return {"entry": d0, "expiry": e, "exit_day": d, "reason": why, "net": v, "credit_pts": t["credit_pts"], "Q": Q,
                "k": t["k"], "lots": L, "marks": marks, "wing_clamped": t["wing_clamped"],
                "orders": H["orders"] if H else 0, "hedge_costs": H["costs"] if H else 0.0}

    for d in [x for x in days if x > d0]:
        if d not in t["marks"]:
            if exit_ == "pre" and d == days[-1]:
                return None
            continue
        hv = 0.0
        if H:
            hv = H["marks"].get(d)
            if hv is None:
                hv = 0.0
        v = L * t["marks"][d] + hv
        marks[d] = v
        if stop is not None and v <= -stop * credit_rs:
            return done(v, d, "stop")
        if gate is not None and exit_ == "settle" and d == days[-1]:
            sg = wk.idx_px(smp.data, d)
            if sg is not None and min(Kc - sg, sg - Kp) < gate * Q:
                return done(v, d, "gate")
        if exit_ == "pre" and d == days[-1]:
            return done(v, d, "pre")
    if exit_ == "pre":
        return None
    return done(L * t["marks"][e] + (H["settle"] if H else 0.0), e, "settle")


def book3(smp, struct, k, exit_name, hedge_name="none", flt_name="none"):
    out = []
    for e, days in smp.weeks:
        r = trade3(smp, e, days, struct, k, exit_name, hedge_name, flt_name)
        if r and "net" in r and r["net"] is not None:
            out.append(r)
    return out


def variants():
    """Every structure x k x exit x hedge x filter of the PLAN (k = 1 has no gate / pre)."""
    out = []
    for s in STRUCTURES:
        for k in KS:
            for ex in EXITS:
                if k == 1 and ex not in ("settle", "settle stop1"):
                    continue
                for h in HEDGES:
                    for f in FILTERS:
                        out.append((s, k, ex, h, f))
    return out


def vname(v):
    s, k, ex, h, f = v
    return f"{s} k{k} {ex}" + ("" if h == "none" else f" {h}") + ("" if f == "none" else f" {f}")


def summary(trades, W, lots=1):
    x = np.array([t["net"] for t in trades], dtype=float) / lots
    mo = {}
    for t in trades:
        mo[t["exit_day"][:7]] = mo.get(t["exit_day"][:7], 0.0) + t["net"] / lots
    by = {}
    for t in trades:
        by[t["entry"][:4]] = by.get(t["entry"][:4], 0.0) + t["net"] / lots
    xs = np.sort(x)
    return {"weeks": W, "trades": len(x), "net": round(float(x.sum())) if len(x) else 0,
            "per_week": round(float(x.sum()) / W, 1) if W else 0.0,
            "win_pct": round(float((x > 0).mean() * 100), 1) if len(x) else 0.0,
            "worst": round(float(x.min())) if len(x) else 0, "worst_month": round(min(mo.values())) if mo else 0,
            "months_positive": f"{sum(v > 0 for v in mo.values())} of {len(mo)}",
            "cvar5": round(float(xs[:max(1, len(xs) // 20)].mean())) if len(xs) else 0,
            "by_year": {y: round(v) for y, v in sorted(by.items())},
            "years_positive": sum(v > 0 for v in by.values()),
            "clamped": sum(t.get("wing_clamped", 0) for t in trades),
            "orders": sum(t.get("orders", 0) for t in trades),
            "hedge_costs": round(sum(t.get("hedge_costs", 0.0) for t in trades))}
