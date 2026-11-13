"""SN127 - when is buying an option least bad? (description; PLAN.md) The ATM call and put bought at every 15-minute
clock 09:20-15:00 and sold 15 minutes later at the bid (strict): mean per lot of the pair's average, by clock; hot vs
cold days (SN95's 10:00 flag) for clocks >= 10:00; Gold-free vs ADX >= 30; by year."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

C, M, pa = pg.C, pg.M, pg.pa
CLOCKS = list(range(5, 346, 15))


def leg(S, K, o, i, j):
    rec = S.option(K, o)
    if rec is None or not rec[6][i]:
        return None
    ask = M.ask_of(float(rec[0][3][i]))
    m = pg.mark(S, K, o, j)
    if m is None:
        return None
    b = M.bid_of(m)
    return (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - 205.0


if __name__ == "__main__":
    out_path = HERE / "results-sn127.json"
    if out_path.exists():
        raise SystemExit("SN127 is scored once")
    adm = pa.admission()
    acc = collections.defaultdict(list)
    for S in pg.all_sessions():
        if C.adx(S.day) is None:
            continue
        hotday = adm.get((S.day, "10:00", "R_today", 0.2, "top"))
        regime = "gold-free" if C.gold_free(S.day) else "ADX>=30"
        for i in CLOCKS:
            K = int(round(S.F["c"][i] / M.STEP) * M.STEP)
            a, b = leg(S, K, "CE", i, i + 15), leg(S, K, "PE", i, i + 15)
            if a is None or b is None:
                continue
            v = (a + b) / 2
            clock = f"{9 + (i + 15) // 60:02d}:{(i + 15) % 60:02d}"
            acc[("all", clock)].append(v)
            acc[(regime, clock)].append(v)
            acc[(f"year {S.day[:4]}", clock)].append(v)
            if i >= pa.I10 and hotday is not None:
                acc[("hot" if hotday else "cold", clock)].append(v)
            acc[("best side (hindsight ceiling)", clock)].append(max(a, b))
    table = collections.defaultdict(dict)
    for (grp, clock), v in sorted(acc.items()):
        table[grp][clock] = {"n": len(v), "mean_per_lot": round(float(np.mean(v)))}
    for grp, t in table.items():
        print(f"{grp:32s}", " ".join(f"{c}:{x['mean_per_lot']:>5}" for c, x in t.items()), flush=True)
    out_path.write_text(json.dumps(table, indent=1), encoding="utf-8")
