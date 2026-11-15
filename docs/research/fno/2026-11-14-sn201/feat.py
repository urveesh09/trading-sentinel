"""SN205 / SN206 / SN209 shared (PLAN.md): HAR forecasts with monthly walk-forward refits, entry features for the
risk models and the 20-session sequences for the LSTM. Every value at an entry uses only days before it, plus the
entry day up to 15:15."""
from __future__ import annotations

import datetime as _dt
import math

import numpy as np

import wk


class Daily:
    def __init__(self, data):
        s = wk.daily_series(data)
        self.data = data
        self.day = s["day"]
        self.pos = {d: i for i, d in enumerate(self.day)}
        self.rv, self.close, self.open, self.high, self.low = s["rv"], s["close"], s["open"], s["high"], s["low"]
        n = len(self.rv)
        cs = np.concatenate([[0.0], np.cumsum(self.rv)])
        lo5 = np.maximum(0, np.arange(n) - 4)
        lo22 = np.maximum(0, np.arange(n) - 21)
        self.rw = (cs[1:] - cs[lo5]) / (np.arange(n) + 1 - lo5)
        self.rm = (cs[1:] - cs[lo22]) / (np.arange(n) + 1 - lo22)
        self._beta = {}

    def prev(self, d):
        """Index of the last full day before d (or None)."""
        i = self.pos.get(d)
        if i is None:
            import bisect
            i = bisect.bisect_left(self.day, d)
        return i - 1 if i - 1 >= 21 else None

    def fit(self, upto):
        """HAR beta on rows t (21 <= t, t + 1 < upto): RV[t+1] ~ 1 + RV[t] + RV_week[t] + RV_month[t]."""
        rows = np.arange(21, upto - 1)
        if len(rows) < 60:
            return None
        X = np.c_[np.ones(len(rows)), self.rv[rows], self.rw[rows], self.rm[rows]]
        return np.linalg.lstsq(X, self.rv[rows + 1], rcond=None)[0]

    def beta_for(self, d):
        """Monthly walk-forward: the fit on every day before the first session of d's month."""
        m = d[:7]
        if m not in self._beta:
            first = next((i for i, x in enumerate(self.day) if x[:7] >= m), len(self.day))
            self._beta[m] = self.fit(first)
        return self._beta[m]

    def forecast(self, beta, t):
        f = float(beta @ np.array([1.0, self.rv[t], self.rw[t], self.rm[t]]))
        return max(f, 0.25 * float(self.rm[t]))

    def rho(self, t_entry, beta=None):
        """Forecast holding sd / implied holding sd (Q / 0.8 S) for a trade dict; None without history or a fit."""
        t = self.prev(t_entry["entry"])
        b = self.beta_for(t_entry["entry"]) if beta is None else beta
        if t is None or b is None or not t_entry.get("S0"):
            return None
        h = t_entry["k"]
        f = h * self.forecast(b, t)
        implied = t_entry["Q"] / (0.8 * t_entry["S0"])
        return math.sqrt(f) / implied


FEATURES = ("qs", "rho", "lrd", "lrw", "lrm", "lrv_today", "r5", "r20", "otd", "rng", "dist20", "skew", "cq", "k", "wd")


def features(dl, t, beta=None):
    """Entry features for one trade dict (None when history is short)."""
    i = dl.prev(t["entry"])
    if i is None or i < 21 or t.get("S0") is None or t["entry"] not in dl.data["idx"]:
        return None                    # post-freeze fix (SN206 crashed before any number): no index that day
    a = dl.data["idx"][t["entry"]]
    upto = a[:wk.I_ENTRY + 1]
    v = upto[~np.isnan(upto)]
    if len(v) < 100:
        return None
    five = upto[::5]
    five = five[~np.isnan(five)]
    r = np.diff(np.log(five))
    rv_today = float(np.sum(r * r)) + float(np.log(v[0] / dl.close[i])) ** 2
    e, d0, legs = t["expiry"], t["entry"], t["legs"]
    pc = wk.opt_px(dl.data, e, d0, legs[1][0], "PE")
    cc = wk.opt_px(dl.data, e, d0, legs[0][0], "CE")
    rho = dl.rho(t, beta)
    S = t["S0"]
    return {"qs": t["Q"] / S, "rho": rho if rho is not None else np.nan,
            "lrd": math.log(dl.rv[i] + 1e-12), "lrw": math.log(dl.rw[i] + 1e-12), "lrm": math.log(dl.rm[i] + 1e-12),
            "lrv_today": math.log(rv_today + 1e-12),
            "r5": math.log(dl.close[i] / dl.close[i - 5]), "r20": math.log(dl.close[i] / dl.close[i - 20]),
            "otd": math.log(S / v[0]), "rng": (float(v.max()) - float(v.min())) / S,
            "dist20": S / float(np.mean(dl.close[i - 19:i + 1])) - 1.0,
            "skew": ((pc or 0.0) - (cc or 0.0)) / t["Q"], "cq": t["credit_pts"] / t["Q"], "k": float(t["k"]),
            "wd": float(_dt.date.fromisoformat(d0).weekday())}


def sequence(dl, t, n=20):
    """The last n full sessions before the entry: [log RV, return, range / close, gap], plus k / 4 as a channel."""
    i = dl.prev(t["entry"])
    if i is None or i < n + 1:
        return None
    rows = []
    for j in range(i - n + 1, i + 1):
        rows.append([math.log(dl.rv[j] + 1e-12), math.log(dl.close[j] / dl.close[j - 1]),
                     (dl.high[j] - dl.low[j]) / dl.close[j], math.log(dl.open[j] / dl.close[j - 1]), t["k"] / 4.0])
    return np.array(rows, dtype=np.float32)


def quarter(d):
    return f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"
