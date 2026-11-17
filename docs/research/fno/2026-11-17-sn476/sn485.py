"""SN485: one funded forward contest (PLAN.md SN485, frozen at bf895633; details fixed here before any forward number).

SN490 found no survivor, so by the plan the contest is Gold v5 alone (Production's paper book, sn_gold_positions / sn_gold_days)
against zero, on fresh sessions from 2026-11-18 (the first session after this script's commit).
Duration, set before looking: the prior is Gold's replay over every session it has been scored on, 2020-21 (SN482) + 2022 + 2023-26
(day nets, zeros included), ONE_15K and GOLD_30K at Rs 205 / 400. For each: mean and the block-bootstrap long-run SD (block 20,
10,000 draws, seed 485); n* = (1.645 * sigma_LR / |mean|)^2 replay sessions for a 90% CI to exclude zero at the prior mean, in
market sessions (x 246 / 194: Gold's replay has no expiry days) and calendar years. The contest length = n* of GOLD_30K @205 (the
book as it runs), with a floor of 120 market sessions.
The verdict (fw10.py, frozen with this slot, run once at that length): Gold's runtime paper day nets over the contest's market
sessions (zeros on days without a trade; net_stressed at Rs 205, and that minus Rs 195 a lot for Rs 400), circular block bootstrap
(block 20, 10,000 draws, seed 485): EDGE_CONFIRMED if the 90% CI of the mean lies above 0 at both stresses; EDGE_REJECTED if below 0
at Rs 205; else INCONCLUSIVE. Reported beside it: per lot (net / lots per trade), worst day, longest stretch without a new high,
refills (deposits), UNRESOLVED positions (counted, priced as a full loss in a bound).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn482_gold as K  # noqa: E402

A, goldx, g = K.A, K.goldx, K.g
OUT = HERE / "results-sn485.json"
YEAR = 194


def lr_sigma(x, seed=485, block=20, draws=10000):
    x = np.asarray(x, float)
    n = len(x)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n] % n
    return float(np.sqrt(n * np.var(x[idx].mean(axis=1))))


def main():
    if OUT.exists():
        raise SystemExit("SN485 is frozen once")
    goldx.install()
    for y in K.MINE:
        g.D.DATASETS[y] = K.DATASET[y]
    K.G._orig_load = K.load_year
    g._orig_stream = K.dispatch
    res = {"contestants": "Gold v5 alone (SN490: no survivor)", "start": "2026-11-18", "prior": {}}
    for lname, wallet in (("ONE_15K", goldx.ONE_15K), ("GOLD_30K", goldx.GOLD_30K)):
        for st in A.STRESSES:
            parts = {}
            for pname, years in (("2020-21", K.Y2021), ("2022", g.Y22), ("2023-2026", g.Y2326)):
                _s, days, _l = A.run(years, st, wallet)
                parts[pname] = np.asarray([n for _d, _w, n, _t, _l2 in days], float)
            x = np.concatenate(list(parts.values()))
            m, s = float(x.mean()), lr_sigma(x)
            n = (1.645 * s / abs(m)) ** 2 if abs(m) > 1e-9 else None
            res["prior"][f"{lname} @{int(st)}"] = {"sessions": len(x), "mean_per_replay_session": round(m, 1), "sigma_LR": round(s, 1),
                                                   "by_path_mean": {p: round(float(v.mean()), 1) for p, v in parts.items()},
                                                   "n_star_replay": round(n) if n else None, "n_star_market_sessions": round(n * 246 / YEAR) if n else None,
                                                   "n_star_years": round(n / YEAR, 1) if n else None}
    lead = res["prior"]["GOLD_30K @205"]["n_star_market_sessions"]
    res["contest_market_sessions"] = max(120, lead or 120)
    res["verdict_rule"] = {"EDGE_CONFIRMED": "90% CI of the mean day net above 0 at Rs 205 and Rs 400",
                           "EDGE_REJECTED": "90% CI below 0 at Rs 205", "else": "INCONCLUSIVE", "scorer": "fw10.py"}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
