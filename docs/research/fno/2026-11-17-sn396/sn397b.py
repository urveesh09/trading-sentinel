"""SN397 follow-up (disclosed, Nov 17, after SN397's numbers): the pre-registered White check is non-studentized, so the
widest rules (every session traded) dominate its maximum. Hansen's studentized version (max t over the family, the
same stationary bootstrap: 2,000 draws, mean block 5, seed 397) asks the same question with each rule scaled by its own
standard error. Same 24 rules and series as SN397, both clocks, Rs 400. Diagnostic only; it cannot rescue a rule.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402
import sn396  # noqa: E402
import sn397  # noqa: E402

OUT = HERE / "results-sn397b.json"


def studentized(series, draws=2000, block=5, seed=397):
    names = list(series)
    M = np.array([series[k] for k in names])
    n = M.shape[1]
    means = M.mean(1)
    se = M.std(1, ddof=1) / np.sqrt(n)
    se[se == 0] = np.inf
    T = means / se
    Tobs = float(T.max())
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(draws):
        idx = np.empty(n, int)
        idx[0] = rng.integers(n)
        for t in range(1, n):
            idx[t] = rng.integers(n) if rng.random() < 1.0 / block else (idx[t - 1] + 1) % n
        Tb = float(((M[:, idx].mean(1) - means) / se).max())
        hits += Tb >= Tobs
    return {"best": names[int(T.argmax())], "t_best": round(Tobs, 2), "p_studentized": round(hits / draws, 4),
            "t": {k: round(float(x), 2) for k, x in zip(names, T)}}


def main():
    if OUT.exists():
        raise SystemExit("SN397b is run once")
    smp, _days, au = op.setup()
    res = {}
    for clock in ("ORIGINAL", "HONEST"):
        rows = sn396.score(smp, au, clock)
        res[clock] = studentized(sn397.family(smp, au, rows, op.jumps(smp, clock)))
        print(clock, json.dumps({k: res[clock][k] for k in ("best", "t_best", "p_studentized")}), flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
