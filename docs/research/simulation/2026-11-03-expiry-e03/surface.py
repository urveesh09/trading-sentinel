"""Ticket surface: every eligible cheap OTM ticket every five minutes, with causal readings.

Diagnosis on seen 2024/2025 only. Each ticket is bought at the next bar's open plus the half
spread. Outcomes are simple fixed exits judged on later closes minus the half spread:
HOLD (sell at the 15:28 close) and TARGET k (sell at the first close worth k times entry,
else at 15:28), each with and without a 50% premium stop. The readings at the decision
close use only that bar and earlier bars.
"""
from __future__ import annotations
import csv, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e02"))
import data as D          # noqa: E402
import e02_lab as E       # noqa: E402

YEAR_MIN = 375 * 252


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, v, call):
    if T <= 0 or v <= 0:
        return max(0.0, S - K) if call else max(0.0, K - S)
    sd = v * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return S * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - S * ncdf(-d1)


def implied(price, S, K, T, call):
    lo, hi = 1e-3, 5.0
    if bs(S, K, T, hi, call) < price:
        return np.nan
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(S, K, T, mid, call) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def rv(c, i, n):
    w = c[max(0, i - n):i + 1]
    if len(w) < n or not np.isfinite(w).all():
        return np.nan
    return float(np.std(np.diff(np.log(w))) * math.sqrt(YEAR_MIN))


def eff(c, i, n):
    w = c[i - n:i + 1]
    if i < n or not np.isfinite(w).all():
        return np.nan
    path = np.abs(np.diff(w)).sum()
    return float((w[-1] - w[0]) / path) if path else 0.0


def outcomes(t, j, i, flat):
    o = t.q[i + 1, j, 0]
    if not np.isfinite(o):
        return None
    entry = E.up(o + E.half(o))
    path = []
    for k in range(i + 1, flat + 1):
        x = t.q[k, j, 3]
        path.append(E.down(x - E.half(x)) if np.isfinite(x) else np.nan)
    path = np.array(path)
    last = path[np.isfinite(path)]
    end = float(last[-1]) if len(last) else 0.0
    res = dict(entry=entry, best=float(np.nanmax(path)) / entry if len(last) else 0.0)
    for stop in (None, 0.5):
        tag = "" if stop is None else "_s50"
        for k in (None, 3, 5, 10):
            sale = end
            for x in path:
                if not np.isfinite(x):
                    continue
                if stop is not None and x <= entry * (1 - stop):
                    sale = x
                    break
                if k is not None and x >= entry * k:
                    sale = x
                    break
            res[("hold" if k is None else f"t{k}") + tag] = sale / entry
    return res


FIELDS = ["year", "day", "minute", "kind", "dist", "entry", "best", "rv30", "rv60", "rv120", "rv_am", "eff10", "eff30",
          "move13", "move_day", "reach", "iv", "ivrv", "atm_iv"]
EXITS = ["hold", "t3", "t5", "t10", "hold_s50", "t3_s50", "t5_s50", "t10_s50"]


def main():
    out = (HERE / "_local")
    out.mkdir(exist_ok=True)
    with open(out / "surface.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS + EXITS)
        for year in (2024, 2025):
            for t in D.load_year(year, exam=year == 2024):
                c = t.close
                flat = int(np.searchsorted(t.minute, 928))
                start = int(np.searchsorted(t.minute, 780))
                open_i = int(np.flatnonzero(np.isfinite(c))[0])
                for i in range(start, int(np.searchsorted(t.minute, 885)) + 1, 5):
                    S = c[i]
                    if not np.isfinite(S):
                        continue
                    T = (930 - t.minute[i]) / YEAR_MIN
                    r30, r60, r120 = rv(c, i, 30), rv(c, i, 60), rv(c, i, 120)
                    ram = rv(c, start, start - open_i - 1) if start - open_i > 30 else np.nan
                    atr = t.features[10][i, 4]
                    atm = round(S / 50) * 50
                    ivs = []
                    for j in range(len(t.strikes)):
                        if t.strikes[j] == atm and np.isfinite(t.q[i, j, 3]):
                            ivs.append(implied(float(t.q[i, j, 3]), S, float(atm), T, t.kinds[j] == 1))
                    atm_iv = float(np.nanmean(ivs)) if ivs and np.isfinite(ivs).any() else np.nan
                    for j in range(len(t.strikes)):
                        d = int(t.kinds[j])
                        dist = d * (t.strikes[j] - S)
                        ask = t.q[i, j, 3]
                        if dist <= 0 or dist > 200 or not np.isfinite(ask) or not 1.0 <= ask <= 20.0:
                            continue
                        res = outcomes(t, j, i, flat)
                        if res is None:
                            continue
                        iv = implied(float(ask), S, float(t.strikes[j]), T, d == 1)
                        reach = dist / (atr * math.sqrt(930 - t.minute[i])) if np.isfinite(atr) and atr > 0 else np.nan
                        w.writerow([year, t.day, int(t.minute[i]), d, round(float(dist), 1), res["entry"], round(res["best"], 3),
                                    r30, r60, r120, ram, d * eff(c, i, 10), d * eff(c, i, 30),
                                    d * (S - c[start]), d * (S - c[open_i]), reach, iv, iv / r60 if r60 else np.nan, atm_iv]
                                   + [round(res[x], 4) for x in EXITS])
                print(year, t.day, flush=True)


if __name__ == "__main__":
    main()
