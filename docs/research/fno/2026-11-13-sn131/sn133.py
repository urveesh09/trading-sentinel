"""SN133 - the learned exit (PLAN.md): gross continuation models (CE/PE x 5/15/30, walk-forward). For SN132's entries:
hold while any horizon predicts a positive bid-to-bid change from here; exit at the first minute where none does;
cap at twice the chosen horizon or 15:10. Against SN132's fixed horizons on identical entries."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402

C, M = sm.C, sm.M


def learned_exit(data, gpred, start, trade, sessions):
    d, m, lab, fixed_net, _p = trade
    side, hz = lab[:2], int(lab[2:])
    S = sessions[d]
    K = int(round(S.F["c"][m] / M.STEP) * M.STEP)
    rec = S.option(K, side)
    ask = M.ask_of(float(rec[0][3][m]))
    cap = min(m + 2 * hz, C.FLAT)
    base = start[d]
    j = cap
    for t in range(m + 1, cap + 1):
        if t > sm.I1:
            j = t
            break
        r = base + (t - sm.I0)
        cont = [gpred[f"{side}{h}g"][r] for h in (5, 15, 30)]
        if all(not np.isnan(x) and x < 0 for x in cont):
            j = t
            break
    b = rec[4][j] if rec[6][j] else rec[5][j]
    if np.isnan(b):
        return fixed_net
    b = float(b)
    return (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - sm.STRESS


if __name__ == "__main__":
    out_path = HERE / "results-sn133.json"
    if out_path.exists():
        raise SystemExit("SN133 is scored once")
    data = sm.build()
    gpred, _gval = run.cached_wf("gross", data, run.GROSS)
    r132 = json.loads((HERE / "results-sn132.json").read_text(encoding="utf-8"))
    C.years()
    sessions = {S.day: S for y in C.YEARS for S in C.years()[y].ordered()}
    start = {}
    for k, d in enumerate(data["day"]):
        start.setdefault(d, k)
    res = {}
    for which in ("all days", "gold-free"):
        trades = r132[which]["trade_list"]
        fixed, learned = {}, {}
        for t in trades:
            d = t[0]
            fixed[d] = fixed.get(d, 0.0) + t[3]
            learned[d] = learned.get(d, 0.0) + learned_exit(data, gpred, start, t, sessions)
        tf = [tuple(t) for t in trades]
        pf, pl = sm.per_year(fixed, tf), sm.per_year(learned, tf)
        better = sum(pl[y]["net"] > pf[y]["net"] for y in ("2024", "2025", "2026"))
        res[which] = {"fixed": pf, "learned_exit": pl, "years_better": better, "PREFERRED": bool(pl["total"] > pf["total"] and better >= 2)}
        print(f"=== SN133 {which}: fixed {pf['total']} {[pf[y]['net'] for y in ('2024','2025','2026')]} | learned exit {pl['total']} "
              f"{[pl[y]['net'] for y in ('2024','2025','2026')]} | preferred {res[which]['PREFERRED']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
