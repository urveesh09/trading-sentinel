"""SN475 (own): the forecast skill a Rs 30k option buyer needs (PLAN.md section 3, frozen at 83e1b444; details fixed here before
any number). A design tool: the synthetic forecast is built from the realised move by construction; it is never a strategy.

Dates: ledger10 dates where both sides are ENTERED at both stresses and SN456's y (10:00 -> 11:00 future, bp) exists.
f = rho z(y) + sqrt(1 - rho^2) eps (z over the sample; eps standard normal), rho in {0, .02, .05, .08, .10, .15, .20, .30, .50, 1};
200 noise seeds each (seed 475 + seed index). Trade sign(f): ALL dates (coverage 100%), and TOP30 (|f| >= its 70th percentile).
Per decision and per market session (denominator: every futures session 2023-01-01 .. 2026-10-28, expiry days included) at
Rs 205 and 400; the sign hit. Crossings (linear interpolation on the grid): the rho where per-decision net = 0, and where the
per-market-session net = Rs 154 (205) / Rs 498 (400). Against: the realised correlations of SN456's out-of-sample yA / yB with
y on the same dates, SN458's Kronos when its results exist (30-minute target, labelled), and SN193's LSTM (50-52% accuracy).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat456 as F  # noqa: E402
import ledger10  # noqa: E402

OUT = HERE / "results-sn475.json"
RHOS = (0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0)


def cross(xs, ys, target):
    for i in range(1, len(xs)):
        if (ys[i - 1] - target) * (ys[i] - target) <= 0 and ys[i] != ys[i - 1]:
            return round(xs[i - 1] + (target - ys[i - 1]) * (xs[i] - xs[i - 1]) / (ys[i] - ys[i - 1]), 4)
    return None


def main():
    if OUT.exists():
        raise SystemExit("SN475 is scored once")
    L = ledger10.build()
    cal, rows, _ = F.features()
    sessions = sum(1 for d in cal if ledger10.LO <= d <= ledger10.HI)
    ds = [d for d, r in sorted(L.items()) if all(r[s]["state"] == "ENTERED" and r[s]["state400"] == "ENTERED" for s in ("CE", "PE"))
          and rows.get(d, {}).get("y") is not None]
    y = np.array([rows[d]["y"] for d in ds])
    ce = {st: np.array([L[d]["CE"][f"net{st}"] for d in ds]) for st in (205, 400)}
    pe = {st: np.array([L[d]["PE"][f"net{st}"] for d in ds]) for st in (205, 400)}
    zy = (y - y.mean()) / y.std()
    res = {"dates": len(ds), "ledger_dates": len(L), "market_sessions": sessions,
           "states": {s: {k: sum(1 for r in L.values() if r[s]["state"] == k) for k in ("ENTERED", "UNRESOLVED", "NO_QUOTE_OR_UNAFFORDABLE")} for s in ("CE", "PE")},
           "coin_per_decision": {st: round(float(((ce[st] + pe[st]) / 2).mean()), 1) for st in (205, 400)}, "grid": {}}
    for rho in RHOS:
        g = {}
        for cov in ("ALL", "TOP30"):
            acc = {"hit": [], 205: [], 400: [], "s205": [], "s400": []}
            for k in range(200):
                eps = np.random.default_rng(475 + k).standard_normal(len(ds))
                f = rho * zy + np.sqrt(max(0.0, 1 - rho ** 2)) * eps
                take = np.ones(len(ds), bool) if cov == "ALL" else np.abs(f) >= np.percentile(np.abs(f), 70)
                acc["hit"].append(float(np.mean(np.sign(f[take]) == np.sign(y[take]))))
                for st in (205, 400):
                    n = np.where(f > 0, ce[st], pe[st])[take]
                    acc[st].append(float(n.mean()))
                    acc[f"s{st}"].append(float(n.sum() / sessions))
            g[cov] = {"hit": round(float(np.mean(acc["hit"])), 4), "per_decision_205": round(float(np.mean(acc[205])), 1),
                      "per_decision_400": round(float(np.mean(acc[400])), 1), "per_market_session_205": round(float(np.mean(acc["s205"])), 1),
                      "per_market_session_400": round(float(np.mean(acc["s400"])), 1)}
        res["grid"][str(rho)] = g
    xs = list(RHOS)
    res["crossings"] = {}
    for cov in ("ALL", "TOP30"):
        for st, tgt in ((205, 154.0), (400, 498.0)):
            pdv = [res["grid"][str(r)][cov][f"per_decision_{st}"] for r in xs]
            psv = [res["grid"][str(r)][cov][f"per_market_session_{st}"] for r in xs]
            res["crossings"][f"{cov}@{st}"] = {"rho_break_even": cross(xs, pdv, 0.0), "rho_for_target_per_session": cross(xs, psv, tgt)}
    # realised skill on the same dates
    fc = json.loads((HERE / "_local" / "sn456_forecasts.json").read_text(encoding="utf-8"))
    idx = {d: i for i, d in enumerate(fc["dates"])}
    com = [d for d in ds if d in idx]
    yy = np.array([fc["y"][idx[d]] for d in com])
    res["realised"] = {"SN456_dates": len(com),
                       "SN456_yA_corr": round(float(np.corrcoef([fc["ya"][idx[d]] for d in com], yy)[0, 1]), 4),
                       "SN456_yB_corr": round(float(np.corrcoef([fc["yb"][idx[d]] for d in com], yy)[0, 1]), 4),
                       "SN193_LSTM": "50-52% sign accuracy, near its base rate (SN186-SN200 README)"}
    k = HERE / "results-sn458.json"
    if k.exists():
        kk = json.loads(k.read_text(encoding="utf-8"))
        res["realised"]["SN458_kronos_corr_30min"] = kk.get("corr", {}).get("K")
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "grid"}, indent=1))
    for r in RHOS:
        print(r, res["grid"][str(r)])


if __name__ == "__main__":
    main()
