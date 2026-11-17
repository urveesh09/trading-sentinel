"""SN406 (own): the opening trade's parameter map on the HONEST clock (PLAN.md section 2, frozen at 00693405; details
fixed here before any SN406 number). Learning only.

AUCTION sessions (g != 0, 171), the auction side, one lot, the cash rule at the label quote, HONEST fills (decision at
hh:mm:00 = the close of the previous minute). Grid (720 cells x Rs 205 / 400):
  clock     09:16 / 09:17 / 09:18 / 09:20 / 09:25 / 09:30   (minute m = 1, 2, 3, 5, 10, 15; fill index m - 1)
  hold      15 / 30 / 60 / 90 minutes
  contract  ATM (0) / 1-ITM (1) / 2-ITM then 1 (2, 1)
  filter    ALL / CHEAP (fw9's frozen cutoff) / the causal 20th, 40th, 50th percentile of the HONEST 09:16 jump
            (sessions without a reading: traded only under ALL)
  stop      Rs 2,000 / Rs 3,000
Per cell: per-session net over all 171 sessions (skips 0), fills, per trade, by period. Reported: the full grid; fw9's
cell (09:16, 60, 2-then-1, CHEAP, 3,000) and its one-step neighbours (09:17; 30 / 90; 1-ITM; 40th percentile; 2,000);
the share of cells > 0 at Rs 400; the best cell at Rs 400 with the share of its one-step neighbours > 0; White's
reality check (non-studentized and studentized, stationary bootstrap 2,000 draws, mean block 5, seed 406) for the best
cell at Rs 400 against all 720.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

gl = op.gl
OUT = HERE / "results-sn406.json"
CLOCKS = {"09:16": 1, "09:17": 2, "09:18": 3, "09:20": 5, "09:25": 10, "09:30": 15}
HOLDS = (15, 30, 60, 90)
CONTRACTS = {"ATM": (0,), "ITM1": (1,), "ITM2>1": (2, 1)}
FILTERS = ("ALL", "CHEAP", "P20", "P40", "P50")
STOPS = (2000.0, 3000.0)
STRESSES = (205.0, 400.0)


def bootstrap(M, draws=2000, block=5, seed=406):
    n = M.shape[1]
    means = M.mean(1)
    se = M.std(1, ddof=1) / np.sqrt(n)
    se[se == 0] = np.inf
    rng = np.random.default_rng(seed)
    v_obs, t_obs = float(means.max()), float((means / se).max())
    hv = ht = 0
    for _ in range(draws):
        idx = np.empty(n, int)
        idx[0] = rng.integers(n)
        for t in range(1, n):
            idx[t] = rng.integers(n) if rng.random() < 1.0 / block else (idx[t - 1] + 1) % n
        mb = M[:, idx].mean(1) - means
        hv += float(mb.max()) >= v_obs
        ht += float((mb / se).max()) >= t_obs
    return {"p_white": round(hv / draws, 4), "p_studentized": round(ht / draws, 4), "t_best": round(t_obs, 2)}


def main():
    if OUT.exists():
        raise SystemExit("SN406 is run once")
    smp, _days, au = op.setup()
    jm = op.jumps(smp, "HONEST")
    lab = {"CHEAP": op.labels(jm, True), "P20": op.labels(jm, False, (1, 5), (4, 5)), "P40": op.labels(jm, False, (2, 5), (4, 5)),
           "P50": op.labels(jm, False, (1, 2), (4, 5))}
    sess = sorted(d for d, a in au.items() if a["g"] != 0)
    n = len(sess)
    cells = list(itertools.product(CLOCKS, HOLDS, CONTRACTS, FILTERS, STOPS))
    series = {st: {c: np.zeros(n) for c in cells} for st in STRESSES}
    fills = {c: 0 for c in cells}
    for si, d in enumerate(sess):
        s, a = smp.s[d], au[d]
        side = "CE" if a["g"] > 0 else "PE"
        ok_f = {"ALL": True, **{f: lab[f].get(d) == "CHEAP" for f in ("CHEAP", "P20", "P40", "P50")}}
        for (cn, m), (kn, deps) in itertools.product(CLOCKS.items(), CONTRACTS.items()):
            for st in STRESSES:
                pos, _dep, state, jf = op.leg(smp, s, side, m, "HONEST", st, deps)
                if pos is None:
                    continue
                vals = op.path(pos, s, jf, min(jf + max(HOLDS), op.gl.NM - 1))
                for h, f, stop in itertools.product(HOLDS, FILTERS, STOPS):
                    if not ok_f[f]:
                        continue
                    net, _why = op.net_from_path(vals, h, stop)
                    if net is None:
                        continue
                    c = (cn, h, kn, f, stop)
                    series[st][c][si] = net
                    if st == STRESSES[0]:
                        fills[c] += 1
    post = np.array([d >= op.SPLIT for d in sess])
    grid = {}
    for c in cells:
        key = " | ".join([c[0], f"{c[1]}m", c[2], c[3], f"stop{int(c[4])}"])
        g = {"fills": fills[c]}
        for st in STRESSES:
            x = series[st][c]
            g[f"per_session@{int(st)}"] = round(float(x.mean()), 1)
            g[f"per_trade@{int(st)}"] = round(float(x.sum() / fills[c]), 1) if fills[c] else None
            g[f"pre@{int(st)}"] = round(float(x[~post].mean()), 1)
            g[f"post@{int(st)}"] = round(float(x[post].mean()), 1)
        grid[key] = g
    keyof = lambda c: " | ".join([c[0], f"{c[1]}m", c[2], c[3], f"stop{int(c[4])}"])  # noqa: E731
    fw9 = ("09:16", 60, "ITM2>1", "CHEAP", 3000.0)
    neigh = [("09:17", 60, "ITM2>1", "CHEAP", 3000.0), ("09:16", 30, "ITM2>1", "CHEAP", 3000.0), ("09:16", 90, "ITM2>1", "CHEAP", 3000.0),
             ("09:16", 60, "ITM1", "CHEAP", 3000.0), ("09:16", 60, "ITM2>1", "P40", 3000.0), ("09:16", 60, "ITM2>1", "CHEAP", 2000.0)]
    res = {"sessions": n, "cells": len(cells), "fw9_cell": {keyof(fw9): grid[keyof(fw9)]}, "fw9_neighbours": {keyof(c): grid[keyof(c)] for c in neigh}}
    for st in STRESSES:
        vals = np.array([grid[keyof(c)][f"per_session@{int(st)}"] for c in cells])
        res[f"share_cells_positive@{int(st)}"] = round(float((vals > 0).mean()), 3)
        res[f"share_cells_positive_both_periods@{int(st)}"] = round(float(np.mean([grid[keyof(c)][f"pre@{int(st)}"] > 0 and grid[keyof(c)][f"post@{int(st)}"] > 0 for c in cells])), 3)
    best = max(cells, key=lambda c: grid[keyof(c)]["per_session@400"])
    cl, h, kn, f, stop = best
    ci, hi = list(CLOCKS).index(cl), HOLDS.index(h)
    nb = []
    for dc in (-1, 1):
        if 0 <= ci + dc < len(CLOCKS):
            nb.append((list(CLOCKS)[ci + dc], h, kn, f, stop))
        if 0 <= hi + dc < len(HOLDS):
            nb.append((cl, HOLDS[hi + dc], kn, f, stop))
    nb += [(cl, h, k2, f, stop) for k2 in CONTRACTS if k2 != kn] + [(cl, h, kn, f2, stop) for f2 in FILTERS if f2 != f] + [(cl, h, kn, f, s2) for s2 in STOPS if s2 != stop]
    res["best@400"] = {keyof(best): grid[keyof(best)], "neighbours_positive@400": f"{sum(grid[keyof(c)]['per_session@400'] > 0 for c in nb)} of {len(nb)}",
                       "neighbours": {keyof(c): grid[keyof(c)]["per_session@400"] for c in nb}}
    res["reality_check@400"] = bootstrap(np.array([series[400.0][c] for c in cells]))
    # compact views: per-session @400 by clock x hold for each contract x filter at the Rs 3,000 stop
    view = {}
    for kn, f in itertools.product(CONTRACTS, FILTERS):
        view[f"{kn} {f}"] = {cl: [grid[keyof((cl, h, kn, f, 3000.0))]["per_session@400"] for h in HOLDS] for cl in CLOCKS}
    res["view@400 stop3000 (rows clock, cols hold 15/30/60/90)"] = view
    view205 = {}
    for kn, f in itertools.product(CONTRACTS, FILTERS):
        view205[f"{kn} {f}"] = {cl: [grid[keyof((cl, h, kn, f, 3000.0))]["per_session@205"] for h in HOLDS] for cl in CLOCKS}
    res["view@205 stop3000"] = view205
    res["grid"] = grid
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("grid", "view@205 stop3000")}, indent=1))


if __name__ == "__main__":
    main()
