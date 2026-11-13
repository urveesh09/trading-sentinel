"""SN145 - a learned extension for Gold's trades (PLAN.md; description, Rs 15k, 1-lot approximation): at each Gold v5
trade's N11 exit minute (2024-26, where phase D's walk-forward continuation predictions exist), hold on while any
horizon's predicted bid-to-bid change for the held side is positive; exit at the first minute none is, or 15:10.
Against v5's own exit on identical trades (entry ask, 1 lot, charges + Rs 205)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

sm, run = pe.sm, pe.run
C, M = sm.C, sm.M


def net1(ask, px):
    return (px - ask) * M.LOT - M.charges(ask, px, M.LOT) - sm.STRESS


if __name__ == "__main__":
    out_path = HERE / "results-sn145.json"
    if out_path.exists():
        raise SystemExit("SN145 is scored once")
    data = sm.build()
    gpred, _ = run.cached_wf("gross", data, run.GROSS)
    start = {}
    for k, d in enumerate(data["day"]):
        start.setdefault(d, k)
    C.RECORD[0] = True
    C.TRADES.clear()
    C.run(C.V5, wallets=(C.STD_WALLETS[0],))
    C.RECORD[0] = False
    sess = {S.day: S for y in C.YEARS for S in C.years()[y].ordered()}
    rows = []
    for t in C.TRADES:
        if t["day"] < "2024-01-01" or t["day"] not in start:
            continue
        S = sess[t["day"]]
        rec = S.option(t["strike"], t["opt"])
        side = t["opt"]
        j0 = min(max(t["j_n11"], t["i"] + 1), M.EXIT_MIN)
        jx = C.FLAT
        for j in range(j0, C.FLAT + 1):
            if j > sm.I1:
                jx = j
                break
            r = start[t["day"]] + (j - sm.I0)
            cont = [gpred[f"{side}{h}g"][r] for h in (5, 15, 30)]
            if all(not np.isnan(x) and x <= 0 for x in cont):
                jx = j
                break
        b = rec[4][jx] if rec[6][jx] else rec[5][jx]
        if np.isnan(b):
            continue
        rows.append({"day": t["day"], "v5": net1(t["ask"], t["px"]), "learned": net1(t["ask"], float(b)),
                     "v5_exit": t["j"], "learned_exit": jx, "n11_exit": j0})
    v5, le = sum(r["v5"] for r in rows), sum(r["learned"] for r in rows)
    by = {y: {"v5": round(sum(r["v5"] for r in rows if r["day"][:4] == y)), "learned": round(sum(r["learned"] for r in rows if r["day"][:4] == y))}
          for y in ("2024", "2025", "2026")}
    res = {"trades": len(rows), "v5_exit_total": round(v5), "learned_exit_total": round(le), "by_year": by,
           "learned_better_trades": sum(r["learned"] > r["v5"] for r in rows),
           "mean_extra_minutes_held": round(float(np.mean([r["learned_exit"] - r["v5_exit"] for r in rows])), 1) if rows else 0}
    print("SN145", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
