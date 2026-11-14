"""SN201-SN210 weekly-book engine (PLAN.md). One defined-risk short-premium position per weekly expiry, 1 lot,
entered at the 15:15 close of the k-th session before expiry, held to settlement / the pre-expiry 15:15 / a stop on a
15:15 mark. Reads only sealed copies: the NIFTY year datasets (development) and SN201's lean exam mirrors.

Conventions (all frozen in PLAN.md):
- prices are minute closes; an option's price at 15:15 is the 15:15 close, else its last close from 15:05;
- ATM = the strike whose call and put are closest in price; Q = that straddle;
- strike distances are multiples of Q rounded to the step (at least one step);
- sell at the model bid, buy at the model ask (house spread table; SENSEX on premium / 3.25 x 3.25);
- Zerodha charges per leg as a round trip (NFO or BFO schedule) + a slippage stress per leg-lot;
- settlement = intrinsic at the index's 15:00-15:29 average on expiry day, charged as a round trip (conservative);
- a leg with no print on a mark day is marked at intrinsic + 0.5 point (counted); a missing leg at entry skips."""
from __future__ import annotations

import math
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path.insert(0, str(ROOT / "python-engine"))
LOCAL = HERE / "_local"

DEV_SOURCES = {
    "2022": FNO / "2026-11-13-sn186/_local/dataset-nifty-2022/breeze.sqlite",
    "2023": ROOT / "docs/research/simulation/2026-11-01-fno-n08/_local/dataset-nifty-2023/breeze.sqlite",
    "2024": FNO / "2026-10-30-day-router/_local/dataset-nifty-2024/breeze.sqlite",
    "2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025/breeze.sqlite",
    "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty/breeze.sqlite",
}
EXAM_NIFTY = LOCAL / "mirror-nifty-exam.sqlite"
EXAM_SENSEX = LOCAL / "mirror-sensex-exam.sqlite"
DEV_FROM, TEST_FROM = "2022-04-01", "2026-08-20"
YEARS = ("2022", "2023", "2024", "2025", "2026")
NM = 375                      # 09:15 .. 15:29
I_ENTRY = 360                 # 15:15
LOOKBACK = 10                 # an option price may come from up to 10 minutes earlier
OPT_LO, OPT_HI = "14:55", "15:29"
TICK = 0.05
SCORE_STRESS = 100.0
SPREAD_P75 = ((50.0, 0.10), (100.0, 0.20), (150.0, 0.30), (200.0, 0.45), (300.0, 0.60), (450.0, 0.80))
SPREAD_ABOVE_PCT = 0.002

NIFTY = {"name": "NIFTY", "lot": 65, "step": 50, "exch": "NFO", "scale": 1.0}
SENSEX = {"name": "SENSEX", "lot": 20, "step": 100, "exch": "BFO", "scale": 3.25}

STRUCTS = {                   # name: (m, q) - short strikes at ATM -/+ m*Q, wings q*Q beyond them
    "IF 0.5": (0.0, 0.5), "IF 1.0": (0.0, 1.0),
    "IC 0.5/0.5": (0.5, 0.5), "IC 0.5/1.0": (0.5, 1.0), "IC 1.0/0.5": (1.0, 0.5), "IC 1.0/1.0": (1.0, 1.0),
}


# ---- money ---------------------------------------------------------------------------------------------------
_SNAP = {}


def charges(buy, sell, qty, exch):
    """Round-trip charges for one leg (buy price, sell price), Zerodha schedule of the exchange."""
    if exch not in _SNAP:
        from cost_schedules import options_cost_snapshot
        from fno_costs import calc_fno_costs_from_snapshot
        _SNAP[exch] = (options_cost_snapshot(exch), calc_fno_costs_from_snapshot)
    snap, calc = _SNAP[exch]
    return calc(max(0.0, buy), max(0.0, sell), qty, snap)


def _spread(mk, p):
    s = mk["scale"]
    x = p / s
    for below, sp in SPREAD_P75:
        if x < below:
            return sp * s
    return max(SPREAD_P75[-1][1], round(SPREAD_ABOVE_PCT * x / TICK) * TICK) * s


def bid(mk, p):
    return round(max(TICK, math.floor((p - _spread(mk, p) / 2) / TICK + 1e-9) * TICK), 2)


def ask(mk, p):
    b = bid(mk, p)
    return round(max(b + TICK, math.ceil((p + _spread(mk, p) / 2) / TICK - 1e-9) * TICK), 2)


# ---- data ----------------------------------------------------------------------------------------------------
def _minute(dt):
    return int(dt[11:13]) * 60 + int(dt[14:16]) - 555


def read_source(path, und):
    """{'idx': {day: array(375) closes}, 'opt': {expiry: {day: {(strike, opt): {minute: close}}}}} from one sqlite."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute("PRAGMA table_info(candles)")]
    w, a = ("", ())
    if "underlying" in cols:
        w, a = " AND underlying=?", (und,)
    if "interval" in cols:
        w += " AND interval='1minute'"
    idx = {}
    for dt, c in con.execute(f"SELECT datetime, close FROM candles WHERE kind='index'{w}", a):
        m = _minute(dt)
        if 0 <= m < NM and c is not None:
            idx.setdefault(dt[:10], np.full(NM, np.nan))[m] = float(c)
    opt = {}
    q = (f"SELECT expiry, strike, opt, datetime, close FROM candles WHERE kind='option'{w} "
         f"AND substr(datetime,12,5) BETWEEN ? AND ?")
    for e, k, o, dt, c in con.execute(q, a + (OPT_LO, OPT_HI)):
        if c is None:
            continue
        e = e[:10]
        d = dt[:10]
        if d >= e:
            continue
        opt.setdefault(e, {}).setdefault(d, {}).setdefault((int(round(float(k))), o), {})[_minute(dt)] = float(c)
    con.close()
    return {"idx": idx, "opt": opt}


def _cached(name, build):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"wk-{name}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    data = build()
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(p)
    return data


def dev_data():
    """NIFTY development (Apr 2022 - Oct 2026; TEST kept apart by the caller). Each day's index and each expiry's
    options come from the dataset of their own year when it has them."""
    def build():
        parts = {y: read_source(p, "NIFTY") for y, p in DEV_SOURCES.items()}
        idx, opt = {}, {}
        for y, part in parts.items():
            for d, a in part["idx"].items():
                if d[:4] == y or d not in idx:
                    idx[d] = a
            for e, rows in part["opt"].items():
                if e[:4] == y or e not in opt:
                    opt[e] = rows
        return {"idx": idx, "opt": opt}
    return _cached("dev-nifty", build)


def exam_data(which):
    path, und = (EXAM_NIFTY, "NIFTY") if which == "NIFTY" else (EXAM_SENSEX, "SENSEX")
    if not path.exists():
        raise SystemExit(f"{path.name} missing: SN201 seals it")
    return _cached(f"exam-{which.lower()}", lambda: read_source(path, und))


# ---- prices --------------------------------------------------------------------------------------------------
def opt_px(data, e, d, k, o, i=I_ENTRY):
    rec = data["opt"].get(e, {}).get(d, {}).get((k, o))
    if not rec:
        return None
    for j in range(i, i - LOOKBACK - 1, -1):
        if j in rec:
            return rec[j]
    return None


def idx_px(data, d, i=I_ENTRY):
    a = data["idx"].get(d)
    if a is None:
        return None
    for j in range(i, max(-1, i - LOOKBACK - 1), -1):
        if a[j] == a[j]:
            return float(a[j])
    return None


def settle_px(data, e):
    a = data["idx"].get(e)
    if a is None:
        return None
    w = a[345:375]
    w = w[~np.isnan(w)]
    return float(w.mean()) if len(w) >= 20 else None


def atm_of(data, e, d, i=I_ENTRY):
    """(K0, Q, CE, PE): the strike where call and put are closest; ties to the nearer to the index."""
    day = data["opt"].get(e, {}).get(d, {})
    ks = sorted({k for (k, o) in day if o == "CE"} & {k for (k, o) in day if o == "PE"})
    s = idx_px(data, d, i)
    best = None
    for k in ks:
        c, p = opt_px(data, e, d, k, "CE", i), opt_px(data, e, d, k, "PE", i)
        if c is None or p is None:
            continue
        key = (abs(c - p), abs(k - s) if s else 0.0)
        if best is None or key < best[0]:
            best = (key, k, c + p, c, p)
    return None if best is None else best[1:]


def expiries(data, lo=None, hi=None):
    """Weekly expiries with options before expiry and a settlement price; [(expiry, [sessions before it])]."""
    out = []
    for e in sorted(data["opt"]):
        days = sorted(d for d in data["opt"][e] if d < e)
        if not days or settle_px(data, e) is None:
            continue
        if lo and days[0] < lo and days[-1] < lo:
            continue
        if hi and e > hi:
            continue
        out.append((e, days))
    return out


def dist(mk, x):
    st = mk["step"]
    return max(st, int(round(x / st)) * st)


def legs_for(mk, K0, Q, struct):
    if struct == "STRADDLE":                   # description only (SN202): no wings, unlimited risk
        return [(K0, "CE", -1), (K0, "PE", -1)], None
    m, q = STRUCTS[struct]
    up = K0 + (dist(mk, m * Q) if m > 0 else 0)
    dn = K0 - (dist(mk, m * Q) if m > 0 else 0)
    w = dist(mk, q * Q)
    return [(up, "CE", -1), (dn, "PE", -1), (up + w, "CE", 1), (dn - w, "PE", 1)], w


# ---- the trade -----------------------------------------------------------------------------------------------
def _value(mk, legs, fills0, raws, stress):
    """Net rupees if closed at these raw prices (shorts bought at the ask, wings sold at the bid)."""
    lot, ex = mk["lot"], mk["exch"]
    tot = 0.0
    for (k, o, sgn), f0, r in zip(legs, fills0, raws):
        if sgn < 0:
            fx = ask(mk, r)
            tot += (f0 - fx) * lot - charges(fx, f0, lot, ex)
        else:
            fx = bid(mk, r)
            tot += (fx - f0) * lot - charges(f0, fx, lot, ex)
    return tot - stress * len(legs)


def _settle_value(mk, legs, fills0, S_T, stress):
    lot, ex = mk["lot"], mk["exch"]
    tot = 0.0
    for (k, o, sgn), f0 in zip(legs, fills0):
        iv = max(0.0, S_T - k) if o == "CE" else max(0.0, k - S_T)
        if sgn < 0:
            tot += (f0 - iv) * lot - charges(iv, f0, lot, ex)
        else:
            tot += (iv - f0) * lot - charges(f0, iv, lot, ex)
    return tot - stress * len(legs)


def trade(mk, data, e, days, k, struct, exit_="settle", stop=None, stress=SCORE_STRESS, i_entry=I_ENTRY):
    """One weekly position. Returns a dict (net, marks by day, credit, max loss, flags) or None when it cannot be
    entered (fewer than k sessions, a missing leg, no ATM). k = "F" enters on the week's first session."""
    if k == "F":
        k = len(days)
    if len(days) < k:
        return None
    d0 = days[-k]
    a = atm_of(data, e, d0, i_entry)
    if a is None:
        return None
    K0, Q, _c, _p = a
    legs, w = legs_for(mk, K0, Q, struct)
    clamped = 0
    if w is not None:                          # a wing beyond the downloaded strikes moves inward to the farthest
        short = {o: kk for kk, o, sg in legs if sg < 0}            # priced strike, at least one step past the short
        for n, (kk, o, sg) in enumerate(legs):
            if sg < 0:
                continue
            step = -mk["step"] if o == "CE" else mk["step"]
            while opt_px(data, e, d0, kk, o, i_entry) is None and abs(kk + step - short[o]) >= mk["step"]:
                kk += step
                clamped = 1
            legs[n] = (kk, o, sg)
        w = max(abs(legs[2][0] - legs[0][0]), abs(legs[3][0] - legs[1][0]))
    raws0 = [opt_px(data, e, d0, kk, o, i_entry) for kk, o, _s in legs]
    if any(r is None for r in raws0):
        return {"skip": "entry leg missing", "entry": d0, "expiry": e}
    fills0 = [bid(mk, r) if s < 0 else ask(mk, r) for (kk, o, s), r in zip(legs, raws0)]
    credit = sum(f if s < 0 else -f for (kk, o, s), f in zip(legs, fills0))
    lot = mk["lot"]
    res = {"entry": d0, "expiry": e, "k": k, "struct": struct, "K0": K0, "Q": Q, "S0": idx_px(data, d0, i_entry),
           "legs": legs, "credit_pts": round(credit, 2), "wing": w,
           "max_loss": None if w is None else round((w - credit) * lot, 0),
           "estimated_marks": 0, "wing_clamped": clamped, "marks": {}}
    res["marks"][d0] = _value(mk, legs, fills0, raws0, stress)
    later = [d for d in days if d > d0]
    for d in later:
        s = idx_px(data, d)
        raws = []
        for kk, o, _s in legs:
            r = opt_px(data, e, d, kk, o)
            if r is None:
                if s is None:
                    raws = None
                    break
                r = (max(0.0, s - kk) if o == "CE" else max(0.0, kk - s)) + 0.5
                res["estimated_marks"] += 1
            raws.append(r)
        if raws is None:
            continue
        v = _value(mk, legs, fills0, raws, stress)
        res["marks"][d] = v
        if stop is not None and v <= -stop * credit * lot:
            res.update(net=v, exit_day=d, reason="stop")
            return res
        if exit_ == "pre" and d == days[-1]:
            res.update(net=v, exit_day=d, reason="pre")
            return res
    if exit_ == "pre":
        return None if k == 1 else res | {"net": res["marks"].get(days[-1]), "exit_day": days[-1], "reason": "pre"}
    S_T = settle_px(data, e)
    v = _settle_value(mk, legs, fills0, S_T, stress)
    res["marks"][e] = v
    res.update(net=v, exit_day=e, reason="settle", S_T=S_T)
    return res


def daily_changes(t):
    """{day: change in the position's value}: the entry day carries the entry costs, the exit day the last change."""
    out, prev = {}, 0.0
    for d in sorted(t["marks"]):
        if d > t["exit_day"]:
            break
        out[d] = t["marks"][d] - prev
        prev = t["marks"][d]
    return out


# ---- variants and scoring ------------------------------------------------------------------------------------
def variants():
    out = []
    for s in STRUCTS:                          # k = 1, 2, 3 sessions before expiry, or "F" = the week's first session
        for k in (1, 2, 3, "F"):
            out.append((s, k, "settle", None))
            if k >= 2:
                out.append((s, k, "settle", 1.0))
                out.append((s, k, "pre", None))
                out.append((s, k, "pre", 1.0))
    return out


def vname(v):
    s, k, ex, st = v
    return f"{s} k{k} {ex}" + (f" stop{st:g}" if st else "")


def book(mk, data, weeks, v, stress=SCORE_STRESS, i_entry=I_ENTRY):
    s, k, ex, st = v
    out = []
    for e, days in weeks:
        t = trade(mk, data, e, days, k, s, ex, st, stress, i_entry)
        if t and "net" in t and t["net"] is not None:
            out.append(t)
    return out


def split(weeks, part):
    """Weeks by entry period: 'dev' (Apr 2022 - Aug 19 2026) or 'test' (entries from Aug 20 2026)."""
    if part == "dev":
        return [(e, ds) for e, ds in weeks if ds[0] >= DEV_FROM and e < TEST_FROM]
    return [(e, ds) for e, ds in weeks if ds[0] >= TEST_FROM]       # the week spanning Aug 20 is in neither


def stats(trades, years=YEARS):
    x = np.array([t["net"] for t in trades]) if trades else np.zeros(0)
    by = {y: round(float(sum(t["net"] for t in trades if t["entry"][:4] == y))) for y in years}
    xs = np.sort(x)[::-1]
    return {"weeks": len(x), "net": round(float(x.sum())), "mean": round(float(x.mean())) if len(x) else 0,
            "win_pct": round(float((x > 0).mean() * 100), 1) if len(x) else 0.0,
            "worst": round(float(x.min())) if len(x) else 0, "best": round(float(x.max())) if len(x) else 0,
            "without_best_5": round(float(xs[5:].sum())), "without_best_10": round(float(xs[10:].sum())),
            "by_year": by, "years_positive": int(sum(v > 0 for y, v in by.items() if any(t["entry"][:4] == y for t in trades))),
            "max_loss_median": round(float(np.median([t["max_loss"] for t in trades]))) if trades and trades[0]["max_loss"] is not None else None,
            "max_loss_max": round(float(max(t["max_loss"] for t in trades))) if trades and trades[0]["max_loss"] is not None else None}


def boot_p5(trades, draws=2000, seed=201):
    x = np.array([t["net"] for t in trades])
    if not len(x):
        return 0
    rng = np.random.default_rng(seed)
    return round(float(np.percentile([rng.choice(x, len(x)).sum() for _ in range(draws)], 5)))


def loyo(table):
    """table: {variant: {year: net}} -> per held-out year the variant best on the other years, and the sum."""
    out, tot = {}, 0.0
    for y in YEARS:
        pick = max(table, key=lambda v: sum(n for yy, n in table[v].items() if yy != y))
        out[y] = {"pick": pick, "net": table[pick].get(y, 0)}
        tot += table[pick].get(y, 0)
    out["sum"] = round(tot)
    out["years_positive"] = sum(out[y]["net"] > 0 for y in YEARS)
    return out


# ---- daily index series (for HAR / ML) -----------------------------------------------------------------------
def daily_series(data):
    """Sorted days with close (last print to 15:29), open, high, low, realised variance (5-minute squared log returns
    plus the squared overnight log return)."""
    days = sorted(data["idx"])
    out = {"day": [], "open": [], "high": [], "low": [], "close": [], "rv": [], "c1515": []}
    prev_close = None
    for d in days:
        a = data["idx"][d]
        v = a[~np.isnan(a)]
        if len(v) < 200:
            continue
        five = a[::5]
        five = five[~np.isnan(five)]
        r = np.diff(np.log(five))
        rv = float(np.sum(r * r))
        if prev_close is not None:
            rv += float(np.log(v[0] / prev_close)) ** 2
        out["day"].append(d)
        out["open"].append(float(v[0]))
        out["high"].append(float(v.max()))
        out["low"].append(float(v.min()))
        out["close"].append(float(v[-1]))
        out["rv"].append(rv)
        out["c1515"].append(idx_px(data, d) or float(v[-1]))
        prev_close = float(v[-1])
    return {k: (np.array(x) if k != "day" else x) for k, x in out.items()}
