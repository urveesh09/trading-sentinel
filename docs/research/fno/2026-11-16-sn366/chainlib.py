"""Shared chain features for SN368 / SN372 / SN378 / SN379 from the real-quote archive (minute snapshots, usable quotes
only). Vectorised Black-76 (undiscounted, expiry 15:30), a normal CDF by Abramowitz-Stegun 7.1.26 (|error| < 1.5e-7),
bisection IV. One feature row per (day, minute 09:30 .. 14:30):
  fut      front NIFTY future mid
  for each tenor (front, next expiry >= day, the expiry day itself excluded as front):
    K0, syn  the ATM pair (strike nearest the future with both legs usable) and its synthetic forward K0 + C - P (mids)
    atm_iv   straddle IV at K0
    rr       IV at -25 delta (OTM puts) minus IV at +25 delta (OTM calls), interpolated in delta; nan unless both are
             bracketed by usable strikes
  flow     (front, strikes K0 - 100 .. K0 + 100) the minute's volume increment per contract signed by its last price
             against the previous snapshot's mid (Lee-Ready: above = buyer, below = seller, at = 0), in lots:
             call_buy - put_buy  (SN379)
Cached per day in _local/chain-<day>.pkl.
"""
from __future__ import annotations

import datetime as dt
import math
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import qa  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
LOCAL = HERE / "_local"
I0, I1 = 15, 315
LOT = 65
SQ2 = math.sqrt(2.0)


def ncdf(x):
    x = np.asarray(x, dtype=float)
    z = np.abs(x) / SQ2
    t = 1.0 / (1.0 + 0.3275911 * z)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-z * z)
    return 0.5 * (1.0 + np.sign(x) * y)


def b76(F, K, T, s, call):
    v = s * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * v * v) / v
    c = F * ncdf(d1) - K * ncdf(d1 - v)
    return np.where(call, c, c - F + K)


def iv(price, F, K, T, call, lo=0.01, hi=3.0, it=60):
    price, K, call = np.asarray(price, float), np.asarray(K, float), np.asarray(call, bool)
    a, b = np.full(price.shape, lo), np.full(price.shape, hi)
    ok = (b76(F, K, T, a, call) < price) & (price < b76(F, K, T, b, call))
    for _ in range(it):
        m = 0.5 * (a + b)
        up = b76(F, K, T, m, call) < price
        a, b = np.where(up, m, a), np.where(up, b, m)
    return np.where(ok, 0.5 * (a + b), np.nan)


def delta(F, K, T, s, call):
    v = s * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * v * v) / v
    return np.where(call, ncdf(d1), ncdf(d1) - 1.0)


def years_to(day, expiry, i):
    a = dt.datetime.fromisoformat(f"{day}T09:15:00") + dt.timedelta(minutes=i)
    return max(1e-6, (dt.datetime.fromisoformat(f"{expiry}T15:30:00") - a).total_seconds() / (365.0 * 86400.0))


def mid(rec, i):
    if rec is None or not rec["usable"][i]:
        return None
    return 0.5 * (rec["bid"][i] + rec["ask"][i])


def tenor_row(q, day, e, i, fut):
    strikes = sorted({k[2] for k in q["opt"] if k[0] == "NIFTY" and k[1] == e})
    if not strikes:
        return None
    near = sorted(strikes, key=lambda k: abs(k - fut))
    K0 = next((k for k in near if mid(q["opt"].get(("NIFTY", e, k, "CE")), i) is not None and mid(q["opt"].get(("NIFTY", e, k, "PE")), i) is not None), None)
    if K0 is None:
        return None
    c0, p0 = mid(q["opt"][("NIFTY", e, K0, "CE")], i), mid(q["opt"][("NIFTY", e, K0, "PE")], i)
    syn = K0 + c0 - p0
    T = years_to(day, e, i)
    # straddle IV: solve on the straddle price directly
    lo, hi = 0.01, 3.0
    for _ in range(60):
        m = 0.5 * (lo + hi)
        val = float(b76(syn, np.array([K0]), T, np.array([m]), np.array([True]))[0] + b76(syn, np.array([K0]), T, np.array([m]), np.array([False]))[0])
        lo, hi = (m, hi) if val < c0 + p0 else (lo, m)
    s_atm = 0.5 * (lo + hi) if 0.011 < lo < 2.99 else np.nan
    Ks, Ps, Cs = [], [], []
    for k in strikes:
        if k >= syn:
            m_ = mid(q["opt"].get(("NIFTY", e, k, "CE")), i)
            if m_ is not None:
                Ks.append(k), Ps.append(m_), Cs.append(True)
        if k <= syn:
            m_ = mid(q["opt"].get(("NIFTY", e, k, "PE")), i)
            if m_ is not None:
                Ks.append(k), Ps.append(m_), Cs.append(False)
    rr = np.nan
    if Ks:
        Ka, Pa, Ca = np.array(Ks, float), np.array(Ps, float), np.array(Cs, bool)
        sig = iv(Pa, syn, Ka, T, Ca)
        dl = delta(syn, Ka, T, np.where(np.isnan(sig), 0.2, sig), Ca)
        good = ~np.isnan(sig)
        cd, cs = dl[good & Ca], sig[good & Ca]
        pd_, ps = dl[good & ~Ca], sig[good & ~Ca]
        if len(cd) >= 2 and cd.min() <= 0.25 <= cd.max() and len(pd_) >= 2 and pd_.min() <= -0.25 <= pd_.max():
            oc, op = np.argsort(cd), np.argsort(pd_)
            rr = float(np.interp(-0.25, pd_[op], ps[op]) - np.interp(0.25, cd[oc], cs[oc]))
    return {"K0": K0, "syn": syn, "atm_iv": float(s_atm), "rr": rr}


def day_features(day):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"chain-{day}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    q = qa.load(day)
    exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] > day})
    fut_rec = qa.front_fut(q, "NIFTY")
    out = {"day": day, "front": exps[0] if exps else None, "next": exps[1] if len(exps) > 1 else None, "rows": {},
           "expiry_day": any(k[0] == "NIFTY" and k[1] == day for k in q["opt"])}
    if fut_rec is None or len(exps) < 2:
        p.write_bytes(pickle.dumps(out))
        return out
    for i in range(I0 - 30, I1 + 61):
        if i < 0 or i >= qa.NM:
            continue
        f = mid(fut_rec, i)
        if f is None:
            continue
        row = {"fut": f}
        if I0 - 30 <= i <= I1:
            for name, e in (("front", exps[0]), ("next", exps[1])):
                row[name] = tenor_row(q, day, e, i, f)
            fr = row["front"]
            if fr is not None and i >= 1:
                flow = 0.0
                for k in range(fr["K0"] - 100, fr["K0"] + 101, 50):
                    for o, sg in (("CE", 1.0), ("PE", -1.0)):
                        rec = q["opt"].get(("NIFTY", exps[0], k, o))
                        if rec is None or not rec["usable"][i] or not rec["usable"][i - 1]:
                            continue
                        dv = rec["vol"][i] - rec["vol"][i - 1]
                        pm = 0.5 * (rec["bid"][i - 1] + rec["ask"][i - 1])
                        if np.isnan(dv) or dv <= 0 or np.isnan(rec["ltp"][i]):
                            continue
                        side = 1.0 if rec["ltp"][i] > pm else -1.0 if rec["ltp"][i] < pm else 0.0
                        flow += sg * side * dv / LOT
                row["flow"] = flow
        out["rows"][i] = row
    p.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    return out


def option_trade(q, expiry, strike, side, i_entry, hold, stress, stop=3000.0):
    """Walked ask at i_entry, walked bid at a usable snapshot in the exit minute or the one before; stop on each minute."""
    rec = q["opt"].get(("NIFTY", expiry, strike, side))
    if rec is None or i_entry >= qa.NM or not rec["usable"][i_entry]:
        return None
    e = qa.walk_cost(rec["askp"][:, i_entry], rec["askq"][:, i_entry], LOT)
    if e is None:
        return None
    sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
    import gl  # noqa: E402
    last, xj = None, min(qa.NM - 1, i_entry + hold)
    for j in range(i_entry + 1, xj + 1):
        if not rec["usable"][j]:
            continue
        b = qa.walk_cost(rec["bidp"][:, j], rec["bidq"][:, j], LOT)
        if b is None:
            continue
        v = (b - e) * LOT - gl.wk.charges(e, b, LOT, "NFO") - stress
        if v <= -stop:
            return round(v, 2)
        if j >= xj - 1:
            last = round(v, 2)
    return last
