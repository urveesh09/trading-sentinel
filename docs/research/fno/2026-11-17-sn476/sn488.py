"""SN488 (own): Gold's uncertainty and the forward contest's length (PLAN.md SN488, frozen at bf895633; details fixed here first).

Series: Gold v5's day nets over every replay session (zeros included), 2022 path then 2023-26 path, Rs 205 / 400, on ONE_15K
(one lot: no compounding, the per-lot picture) and GOLD_30K (the growth wallet as Gold runs it).
Bootstrap: circular blocks of 20 sessions, 10,000 draws, seed 488, of the pooled 2022-26 series. A "year" = 194 replay sessions
(Gold's replay has no expiry days: 742 replay sessions in 2023-26 over 3.83 years). Reported per series: the year-net distribution
(mean, p5 / p50 / p95), P(year < 0), and over a full-length resample (932 sessions) the longest stretch without a new high and the
worst drawdown.
Contest length: for the paired daily difference of each candidate against Gold (SN478 FAST, SN480 failed add, SN489's frozen rule
EFF / OR20 adds off) and for Gold against zero, on GOLD_30K and ONE_15K at Rs 205 / 400, pooled 2022-26: mean per session, SD,
lag 1-5 autocorrelation, the block-bootstrap long-run variance sigma_LR^2 = n * Var(bootstrap mean), and the replay sessions needed
for a 90% CI to exclude zero at the observed mean, n* = (1.645 * sigma_LR / |mean|)^2, also in market sessions (x 246 / 194) and
years. A mean of zero -> n* infinite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn478  # noqa: E402
import sn480 as A  # noqa: E402

goldx, g = A.goldx, A.g
OUT = HERE / "results-sn488.json"
YEAR = 194
BLOCK, DRAWS, SEED = 20, 10000, 488


def resample(x, n_out, rng):
    n = len(x)
    nb = int(np.ceil(n_out / BLOCK))
    starts = rng.integers(0, n, size=(DRAWS, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(DRAWS, -1)[:, :n_out] % n
    return x[idx]


def drought_and_dd(paths):
    eq = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(np.maximum(eq, 0.0), axis=1)
    dd = (peak - eq).max(axis=1)
    longest = []
    for row, pk in zip(eq, peak):
        new = np.flatnonzero(row >= pk - 1e-9)
        gaps = np.diff(np.concatenate([[-1], new, [len(row)]]))
        longest.append(int(gaps.max()) - 1)
    return np.asarray(longest), dd


def series(days):
    return np.asarray([n for _d, _w, n, _t, _l in days], float)


def lr_var(x, rng):
    n = len(x)
    means = resample(x, n, rng).mean(axis=1)
    return n * float(np.var(means))


def nstar(x, rng):
    m, sd = float(np.mean(x)), float(np.std(x))
    s2 = lr_var(x, rng)
    ac = [round(float(np.corrcoef(x[:-k], x[k:])[0, 1]), 3) if sd > 0 else None for k in range(1, 6)]
    if abs(m) < 1e-9:
        return {"mean": 0.0, "sd": round(sd, 1), "autocorr_1_5": ac, "n_star_replay": None}
    n = (1.645 * np.sqrt(s2) / abs(m)) ** 2
    return {"mean": round(m, 2), "sd": round(sd, 1), "autocorr_1_5": ac, "sigma_LR": round(float(np.sqrt(s2)), 1), "n_star_replay": round(float(n)),
            "n_star_market_sessions": round(float(n) * 246 / YEAR), "n_star_years": round(float(n) / YEAR, 1)}


def main():
    if OUT.exists():
        raise SystemExit("SN488 is scored once")
    goldx.install()
    g._orig_stream = sn478.dispatch
    sn478._gold_one = g.C.gold_one
    g.C.gold_one = sn478.fast_gold_one
    rng = np.random.default_rng(SEED)
    res = {"gold": {}, "contest": {}}
    arms = {"SN480 failed add": dict(A.CHALLENGER), "SN489 adds only TPB / SHIPPED": {"no_add": frozenset({"EFF", "OR20"})}, "SN478 FAST": "fast"}
    for lname, wallet in (("ONE_15K", goldx.ONE_15K), ("GOLD_30K", goldx.GOLD_30K)):
        for st in A.STRESSES:
            base = {}
            for pname, years in A.PATHS:
                sn478.MODE["fast"] = False
                _s, days, _l = A.run(years, st, wallet)
                base[pname] = series(days)
            x = np.concatenate([base["2022"], base["2023-2026"]])
            yrs = resample(x, YEAR, rng).sum(axis=1)
            longest, dd = drought_and_dd(resample(x, len(x), rng))
            res["gold"][f"{lname} @{int(st)}"] = {"sessions": len(x), "per_session": round(float(x.mean()), 1),
                                                  "year_net": {"mean": round(float(yrs.mean())), "p5": round(float(np.quantile(yrs, 0.05))),
                                                               "p50": round(float(np.quantile(yrs, 0.5))), "p95": round(float(np.quantile(yrs, 0.95)))},
                                                  "P_year_below_0": round(float((yrs < 0).mean()), 3),
                                                  "longest_without_new_high": {"p50": int(np.quantile(longest, 0.5)), "p95": int(np.quantile(longest, 0.95))},
                                                  "worst_drawdown": {"p50": round(float(np.quantile(dd, 0.5))), "p95": round(float(np.quantile(dd, 0.95)))},
                                                  "gold_vs_zero": nstar(x, rng)}
            for name, vx in arms.items():
                parts = []
                for pname, years in A.PATHS:
                    if vx == "fast":
                        sn478.MODE["fast"] = True
                        _s, days, _l = A.run(years, st, wallet)
                        sn478.MODE["fast"] = False
                    else:
                        _s, days, _l = A.run(years, st, wallet, **vx)
                    parts.append(series(days) - base[pname])
                res["contest"][f"{name} | {lname} @{int(st)}"] = nstar(np.concatenate(parts), rng)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
