"""SN414 follow-up (disclosed, Nov 17, after SN414's numbers): does any threshold choice make the bank residual persist?
The whole grid is published (no selection): |z| >= 1.5 / 2 / 2.5, breadth >= 60 / 70 / 80% of basket weight, |NIFTY 30
min| <= 0.10 / 0.15 / 0.25%, Gold flat, first trigger per session; outcome the basket's next 15 / 30 / 45 / 60 minutes in
the residual's direction (bp). Cash level only (no option is priced). Same data, beta and sigma as sn414.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn414 as S  # noqa: E402

OUT = HERE / "results-sn414b.json"
Z, BR, Q, H = (1.5, 2.0, 2.5), (0.6, 0.7, 0.8), (0.0010, 0.0015, 0.0025), (1, 2, 3, 4)


def main():
    if OUT.exists():
        raise SystemExit("SN414b is run once")
    bars = S.load_bars()
    days = sorted(bars)
    smp, _gd, _au = S.op.setup()
    busy = S.gold_log()

    def br(d, h0, h1):
        return sum(S.W[s] * (bars[d][s][h1] / bars[d][s][h0] - 1.0) for s in S.W if h0 in bars[d][s] and h1 in bars[d][s])

    def nc(d, hh):
        v = smp.s[d]["index"][3][S.bar_index(hh)]
        return None if np.isnan(v) else float(v)
    usable = [d for d in days if d in smp.s]
    pairs = {d: [(br(d, a, b), nc(d, b) / nc(d, a) - 1.0) for a, b in zip(S.BARS, S.BARS[1:]) if nc(d, a) and nc(d, b)] for d in usable}
    cand = []                                       # every (day, clock) reading with its forward paths
    for k, d in enumerate(usable):
        if k < 20:
            continue
        hist = [p for x in usable[k - 20:k] for p in pairs[x]]
        xb, xn = np.array([p[0] for p in hist]), np.array([p[1] for p in hist])
        beta = float((xn * xb).sum() / (xn * xn).sum())
        rs = []
        for x in usable[k - 20:k]:
            for c in S.CLOCKS:
                i1 = S.BARS.index(c) - 1
                a, b = S.BARS[i1 - 2], S.BARS[i1]
                if nc(x, a) and nc(x, b):
                    rs.append(br(x, a, b) - beta * (nc(x, b) / nc(x, a) - 1.0))
        sig = float(np.std(rs))
        for c in S.CLOCKS:
            i1 = S.BARS.index(c) - 1
            a, b = S.BARS[i1 - 2], S.BARS[i1]
            if not (nc(d, a) and nc(d, b)):
                continue
            rb, rn = br(d, a, b), nc(d, b) / nc(d, a) - 1.0
            resid = rb - beta * rn
            sgn = 1 if resid > 0 else -1
            m = int(c[:2]) * 60 + int(c[3:]) - 555
            fw = {h: 1e4 * br(d, b, S.BARS[i1 + h]) * sgn for h in H if i1 + h < len(S.BARS)}
            breadth = sum(S.W[s] for s in S.W if a in bars[d][s] and b in bars[d][s] and np.sign(bars[d][s][b] / bars[d][s][a] - 1.0) == sgn)
            cand.append({"day": d, "clock": c, "z": abs(resid / sig), "rn": abs(rn), "breadth": breadth,
                         "gold_on": any(i <= m - 1 < j for i, j in busy.get(d, [])), "fw": fw})
    grid = {}
    for z, bth, q in itertools.product(Z, BR, Q):
        seen, rows = set(), []
        for r in cand:
            if r["day"] in seen or r["gold_on"] or r["z"] < z or r["breadth"] < bth or r["rn"] > q:
                continue
            seen.add(r["day"])
            rows.append(r)
        cell = {"n": len(rows)}
        for h in H:
            xs = np.array([r["fw"][h] for r in rows if h in r["fw"]])
            cell[f"{15 * h}m"] = {"mean_bp": round(float(xs.mean()), 2) if len(xs) else None,
                                  "t": round(float(xs.mean() / (xs.std(ddof=1) / np.sqrt(len(xs)))), 2) if len(xs) > 2 and xs.std() > 0 else None}
        grid[f"z{z} breadth{bth} nifty{q}"] = cell
    ts = [c[f"{15 * h}m"]["t"] for c in grid.values() for h in H if c[f"{15 * h}m"]["t"] is not None]
    res = {"cells": len(grid), "share_cells_mean_positive_45m": round(float(np.mean([c["45m"]["mean_bp"] > 0 for c in grid.values() if c["45m"]["mean_bp"] is not None])), 3),
           "max_t": max(ts) if ts else None, "min_t": min(ts) if ts else None, "cells_t_over_2": sum(1 for t in ts if t > 2), "tests": len(ts), "grid": grid}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "grid"}, indent=1))
    for k, v in grid.items():
        print(k, v["n"], {h: (v[h]["mean_bp"], v[h]["t"]) for h in ("15m", "30m", "45m", "60m")})


if __name__ == "__main__":
    main()
