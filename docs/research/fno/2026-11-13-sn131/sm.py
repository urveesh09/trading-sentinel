"""The Smart Sentinel research engine (SN131-SN140): learned decisions instead of hand-written rules.

At every minute 09:30-14:45 of every sealed session (2023 - Oct 28 2026) it records ~45 causal features and, for the
ATM call and the ATM put, the executable net of buying now and selling 5 / 15 / 30 / 60 minutes later (ask in, bid
out, Zerodha charges, Rs 205 stress) plus the gross bid-to-bid change (for the learned exit). LightGBM models
(fixed parameters, frozen here) are retrained every quarter on everything before it (walk-forward, a one-session
purge); the decision threshold is chosen inside the training window on its last two quarters. Scored quarters:
2024 Q1 - 2026 Q4 (2023 only ever trains). Runs in the research venv C:\\Users\\Urveesh\\sentinel-ml-venv."""
from __future__ import annotations

import bisect
import math
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import pa  # noqa: E402

C, M, L = pa.C, pa.M, pa.C.L
HZ = (5, 15, 30, 60)
SIDES = ("CE", "PE")
I0, I1 = 15, 330
STRESS = 205.0
PARAMS = {"objective": "regression", "learning_rate": 0.03, "num_leaves": 31, "min_data_in_leaf": 400,
          "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 10.0, "verbose": -1,
          "num_threads": 4, "seed": 131, "deterministic": True, "force_col_wise": True}
ROUNDS = 400
THETAS = (0.0, 100.0, 200.0, 300.0, 500.0, 800.0)
FEATURES = ("r1", "r2", "r3", "r5", "r10", "r15", "r30", "r60", "ret_open", "gap", "range_pos", "dist_hi", "dist_lo",
            "or_hi", "or_lo", "vwap_d", "ema9_slope", "ema21_50", "atr_rel", "rv15_ratio", "rv_open", "r_today",
            "ce_prem", "pe_prem", "skew", "fv5", "rel_vol", "basis_chg", "cev5", "pev5", "minute", "dte", "weekday",
            "adx", "vix_ratio", "atr_prev", "prev_ret", "prev_range", "gold_free", "iv_chg30", "hi_new", "lo_new",
            "up_share15", "max_bar15")


def _lastprint(tr):
    out = np.full(len(tr), -10 ** 6)
    last = -10 ** 6
    for k in range(len(tr)):
        if tr[k]:
            last = k
        out[k] = last
    return out


def session_rows(S):
    F = S.F
    c, o, h, l, atr, vwap = F["c"], F["o"], F["h"], F["l"], F["atr"], F["vwap"]
    fut = S.s["future"]
    fc, fv = fut[3], np.nan_to_num(fut[4])
    n = len(c)
    hi = np.maximum.accumulate(h)
    lo = np.minimum.accumulate(l)
    lr = np.concatenate([[0.0], np.diff(np.log(c))])
    a_prev = L.VOLT.get(S.day, (None, None))[0]
    vix_last, vix_med = C.vix_prev(S.day)
    prev = S.s.get("prev")
    pd_ = S.s.get("prev_days") or []
    prev_ret = (prev[3] / pd_[-2][3] - 1) * 100 if prev and len(pd_) >= 2 else np.nan
    prev_range = (prev[1] - prev[2]) / prev[3] * 100 if prev else np.nan
    dte = C.sessions_until(S.day, S.s["expiry"])
    ntau = C.sessions_until(S.day, S.s["expiry"])
    wd = int(np.datetime64(S.day, "D").astype("datetime64[D]").view("int64") + 3) % 7   # Monday = 0
    gf = 1.0 if C.gold_free(S.day) else 0.0
    adx = C.adx(S.day)
    rel = C.REL.get(S.day)
    # ATM option marks per minute (fresh within 5 minutes) for premium / implied features
    strikes = np.round(c / M.STEP) * M.STEP
    ce_m, pe_m, sig_imp = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    cache = {}
    for i in range(n):
        K = int(strikes[i])
        for opt, arr in (("CE", ce_m), ("PE", pe_m)):
            key = (K, opt)
            if key not in cache:
                rec = S.option(K, opt)
                cache[key] = None if rec is None else (rec, _lastprint(rec[6]))
            got = cache[key]
            if got is not None and i - got[1][i] <= 5:
                arr[i] = float(got[0][0][3][got[1][i]])
        if not np.isnan(ce_m[i]) and not np.isnan(pe_m[i]) and fc[i] > 0:
            tau = (375 - (i + 1)) + 375.0 * ntau + C.OVERNIGHT_MIN * ntau
            if tau > 0:
                sig_imp[i] = (ce_m[i] + pe_m[i]) / (0.7979 * fc[i] * math.sqrt(tau))
    rows, labels = [], []
    for i in range(I0, I1 + 1):
        a = atr[i] if atr[i] > 0 else 1.0
        rk = {f"r{k}": (c[i] - c[i - k]) / a for k in (1, 2, 3, 5, 10, 15, 30, 60) if i - k >= 0}
        r_since = lr[6: i + 1]
        rv_open = float(np.std(r_since)) if len(r_since) > 5 else np.nan
        rv15 = float(np.std(lr[i - 14: i + 1]))
        bar15 = np.abs(np.diff(c[i - 15: i + 1]))
        x = {**{f"r{k}": np.nan for k in (1, 2, 3, 5, 10, 15, 30, 60)}, **rk,
             "ret_open": (c[i] / o[0] - 1) * 100, "gap": F["gap"] * 100,
             "range_pos": (c[i] - lo[i]) / (hi[i] - lo[i]) if hi[i] > lo[i] else 0.5,
             "dist_hi": (hi[i] - c[i]) / a, "dist_lo": (c[i] - lo[i]) / a,
             "or_hi": (c[i] - F["orh30"][i]) / a if i >= 30 else np.nan, "or_lo": (c[i] - F["orl30"][i]) / a if i >= 30 else np.nan,
             "vwap_d": (c[i] - vwap[i]) / a, "ema9_slope": (F["ema9"][i] - F["ema9"][i - 5]) / a,
             "ema21_50": (F["ema21"][i] - F["ema50"][i]) / a,
             "atr_rel": a / (a_prev * c[i] / math.sqrt(375)) if a_prev else np.nan,
             "rv15_ratio": rv15 / rv_open if rv_open and rv_open > 0 else np.nan,
             "rv_open": rv_open * 1e4 if rv_open == rv_open else np.nan,
             "r_today": rv_open / sig_imp[i] if (rv_open == rv_open and sig_imp[i] == sig_imp[i] and sig_imp[i] > 0) else np.nan,
             "ce_prem": ce_m[i] / c[i] * 1e4 if ce_m[i] == ce_m[i] else np.nan,
             "pe_prem": pe_m[i] / c[i] * 1e4 if pe_m[i] == pe_m[i] else np.nan,
             "skew": (ce_m[i] - pe_m[i]) / (ce_m[i] + pe_m[i]) if (ce_m[i] == ce_m[i] and pe_m[i] == pe_m[i]) else np.nan,
             "fv5": fv[i - 4: i + 1].sum() / max(1.0, fv[: i + 1].mean() * 5),
             "rel_vol": rel[i] if rel is not None else np.nan,
             "basis_chg": ((fc[i] - c[i]) - (fc[i - 15] - c[i - 15])) / a,
             "cev5": np.nan, "pev5": np.nan, "minute": float(i), "dte": float(dte), "weekday": float(wd),
             "adx": adx if adx is not None else np.nan, "vix_ratio": vix_last / vix_med if vix_last else np.nan,
             "atr_prev": a_prev * 100 if a_prev else np.nan, "prev_ret": prev_ret, "prev_range": prev_range, "gold_free": gf,
             "iv_chg30": sig_imp[i] / sig_imp[i - 30] - 1 if (i >= 30 and sig_imp[i] == sig_imp[i] and sig_imp[i - 30] == sig_imp[i - 30]) else np.nan,
             "hi_new": float(h[i] >= hi[i - 1]), "lo_new": float(l[i] <= lo[i - 1]),
             "up_share15": float(np.mean(np.diff(c[i - 15: i + 1]) > 0)), "max_bar15": float(bar15.max() / a)}
        K = int(strikes[i])
        y = {}
        for opt in SIDES:
            got = cache.get((K, opt))
            rec = None if got is None else got[0]
            ok = rec is not None and rec[6][i]
            vol = rec[0][4] if rec is not None else None
            if vol is not None:
                v5 = np.nansum(vol[i - 4: i + 1]) / max(1.0, np.nanmean(vol[: i + 1]) * 5) if np.any(~np.isnan(vol[: i + 1])) else np.nan
                x["cev5" if opt == "CE" else "pev5"] = float(v5)
            if not ok:
                for hz in HZ:
                    y[f"{opt}{hz}"] = np.nan
                    y[f"{opt}{hz}g"] = np.nan
                continue
            ask = M.ask_of(float(rec[0][3][i]))
            bid0 = float(rec[4][i])
            lp = got[1]
            for hz in HZ:
                j = min(i + hz, C.FLAT)
                if j - lp[j] > 5:
                    y[f"{opt}{hz}"] = y[f"{opt}{hz}g"] = np.nan
                    continue
                b = float(rec[4][j] if rec[6][j] else rec[5][j])
                y[f"{opt}{hz}"] = (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - STRESS
                y[f"{opt}{hz}g"] = (b - bid0) * M.LOT
        rows.append([x[f] for f in FEATURES])
        labels.append(y)
    return np.array(rows, dtype=np.float32), labels


def build(force=False):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / "dataset.pkl"
    if p.exists() and not force:
        return pickle.loads(p.read_bytes())
    C.years()
    X, days, minutes, Y = [], [], [], {f"{o}{h}{g}": [] for o in SIDES for h in HZ for g in ("", "g")}
    for S in [S for y in C.YEARS for S in C.years()[y].ordered()]:
        xs, ys = session_rows(S)
        X.append(xs)
        days += [S.day] * len(xs)
        minutes += list(range(I0, I1 + 1))
        for k in Y:
            Y[k] += [r[k] for r in ys]
    data = {"X": np.vstack(X), "day": np.array(days), "minute": np.array(minutes, dtype=np.int16),
            "Y": {k: np.array(v, dtype=np.float32) for k, v in Y.items()}, "features": FEATURES}
    p.write_bytes(pickle.dumps(data))
    return data


QUARTERS = [f"{y}-{m:02d}-01" for y in ("2024", "2025", "2026") for m in (1, 4, 7, 10)] + ["2027-01-01"]


def _fit(X, y, w=None):
    import lightgbm as lgb
    ok = ~np.isnan(y)
    ds = lgb.Dataset(X[ok], y[ok], weight=None if w is None else w[ok], free_raw_data=True)
    return lgb.train(PARAMS, ds, num_boost_round=ROUNDS)


def walk_forward(data, targets, weight_half_life=None, retrain="quarter", shuffle=False, seed=0):
    """Out-of-sample predictions for every row of 2024 Q1 onward: {target: array (NaN before 2024)} plus the
    nested validation predictions used to choose the threshold: {quarter: {target: (mask, pred)}}."""
    X, day = data["X"], data["day"]
    pred = {t: np.full(len(day), np.nan, dtype=np.float32) for t in targets}
    val = {}
    starts = QUARTERS if retrain == "quarter" else [f"{y}-{m:02d}-01" for y in ("2024", "2025", "2026") for m in range(1, 13)] + ["2027-01-01"]
    udays = np.unique(day)
    rng = np.random.default_rng(seed)
    for q0, q1 in zip(starts, starts[1:]):
        test = (day >= q0) & (day < q1)
        if not test.any():
            continue
        k0 = bisect.bisect_left(list(udays), q0)
        purge = udays[max(0, k0 - 1)]                     # one-session purge before the test quarter
        train = day < purge
        vstart = udays[max(0, k0 - 1 - 125)]              # the last ~two quarters of the training window
        inner, vmask = day < udays[max(0, k0 - 126)], (day >= vstart) & (day < purge)
        w = None
        if weight_half_life:
            pos = np.searchsorted(udays, day)
            w = np.power(0.5, (k0 - pos) / weight_half_life).astype(np.float32)
        val[q0] = {}
        for t in targets:
            y = data["Y"][t].copy()
            if shuffle:
                for d in np.unique(day[train]):
                    m = np.flatnonzero(day == d)
                    y[m] = y[rng.permutation(m)]
            mi = _fit(X[inner], y[inner], None if w is None else w[inner])
            val[q0][t] = (vmask, mi.predict(X[vmask]).astype(np.float32))
            mt = _fit(X[train], y[train], None if w is None else w[train])
            pred[t][test] = mt.predict(X[test]).astype(np.float32)
        print(f"   walk-forward {q0}: trained on {int(train.sum())} rows, scored {int(test.sum())}", flush=True)
    return pred, val


def simulate(data, preds, mask, theta, room=3000.0, choices=None, stress_shift=0.0, late=False, lots=None):
    """One position at a time. At a flat minute choose the (side, horizon) with the highest prediction; trade when it
    exceeds theta; the realised net is that row's executable label (minus a stress shift); the next decision comes
    after the exit minute. Day limit `room` (no new trade once the day's loss reaches it). Returns {day: net}, trades."""
    day, minute, Y = data["day"], data["minute"], data["Y"]
    choices = choices or [f"{o}{h}" for o in SIDES for h in HZ]
    P = np.vstack([preds[c] for c in choices])
    out, trades = {}, []
    idx = np.flatnonzero(mask)
    if not len(idx):
        return out, trades
    k = 0
    while k < len(idx):
        r = idx[k]
        d = day[r]
        realized, free = 0.0, -1
        while k < len(idx) and day[idx[k]] == d:
            r = idx[k]
            m = minute[r]
            if m < free or realized <= -room:
                k += 1
                continue
            col = P[:, r]
            if np.all(np.isnan(col)):
                k += 1
                continue
            best = int(np.nanargmax(col))
            if col[best] > theta:
                lab = choices[best]
                rr = r + 1 if late else r
                if rr < len(day) and day[rr] == d:
                    y = Y[lab][rr]
                    if not np.isnan(y):
                        n_l = 1 if lots is None else lots(col[best], theta)
                        net = (float(y) - stress_shift) * n_l
                        realized += net
                        hz = int(lab[2:])
                        trades.append((d, int(m), lab, net, float(col[best])))
                        free = m + hz + 1
            k += 1
        out[d] = realized
    return out, trades


def choose_theta(data, val_q, room=3000.0, choices=None):
    best_t, best_v = None, -np.inf
    for t in THETAS:
        mask = next(iter(val_q.values()))[0]
        preds = {}
        for c, (vm, p) in val_q.items():
            arr = np.full(len(data["day"]), np.nan, dtype=np.float32)
            arr[vm] = p
            preds[c] = arr
        nets, _tr = simulate(data, preds, mask, t, room, choices)
        v = sum(nets.values())
        if v > best_v:
            best_t, best_v = t, v
    return best_t, best_v


def per_year(nets, trades):
    out = {}
    for y in ("2024", "2025", "2026"):
        xs = [v for d, v in nets.items() if d[:4] == y]
        tr = [t for t in trades if t[0][:4] == y]
        out[y] = {"net": round(sum(xs)), "trades": len(tr), "days_traded": sum(1 for v in xs if v != 0),
                  "won_days": sum(1 for v in xs if v > 0), "lost_days": sum(1 for v in xs if v < 0)}
    allv = sorted((v for v in nets.values() if v), reverse=True)
    out["total"] = round(sum(allv))
    out["without_best_5_days"] = round(sum(allv[5:]))
    out["worst_day"] = round(min(allv)) if allv else 0
    out["positive_years"] = sum(out[y]["net"] > 0 for y in ("2024", "2025", "2026"))
    return out


def random_null(data, trades, mask, n=200, seed=131, choices=None):
    """The same number of trades per day at random flat minutes, random side and horizon (labels as realised)."""
    rng = np.random.default_rng(seed)
    choices = choices or [f"{o}{h}" for o in SIDES for h in HZ]
    day, minute, Y = data["day"], data["minute"], data["Y"]
    per_day = {}
    for t in trades:
        per_day[t[0]] = per_day.get(t[0], 0) + 1
    rows_by_day = {}
    for r in np.flatnonzero(mask):
        rows_by_day.setdefault(day[r], []).append(r)
    tots = []
    for _ in range(n):
        s = 0.0
        for d, cnt in per_day.items():
            rows = rows_by_day.get(d, [])
            if not rows:
                continue
            for r in rng.choice(rows, min(cnt, len(rows)), replace=False):
                y = Y[choices[rng.integers(len(choices))]][r]
                s += 0.0 if np.isnan(y) else float(y)
        tots.append(s)
    return float(np.mean(tots)), float(np.percentile(tots, 95))
