"""SN190 - the volatility-regime leg (PLAN.md). Gold's empty days (development). Per held-out year (HAR fitted without
it): forecast / implied >= 1.1 -> SN171's ATM straddle at 10:00 held to 15:10 inside Rs 6,000 (Rs 30k); below SN189's
fold choice of kappa -> SN189's fold-chosen iron fly; otherwise no trade. The held-out ledger per year, the null (as
many random empty days per year, each traded with the regime's structure drawn at random) and robustness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import sn189  # noqa: E402

pw, p3 = pe.pw, pe.p3


def straddle(S, stress=205.0, late=0):
    return p3.structure(S, p3.I1000 + late, "straddle", 30000.0, 6000.0, None, stress)


if __name__ == "__main__":
    out_path = HERE / "results-sn190.json"
    if out_path.exists():
        raise SystemExit("SN190 is scored once")
    r189 = json.loads((HERE / "results-sn189.json").read_text(encoding="utf-8"))
    ss = pe.empty_sessions()
    days = [S.day for S in ss]
    allss = pw.dev_sessions()
    har = p3.HAR(allss)
    folds = {y: p3.rho_table(har, allss, lambda d, y=y: d[:4] != y) for y in pe.YEARS}
    res = {"by_year": {}}
    ledger, hi_n, lo_n = {}, {}, {}
    for y in pe.YEARS:
        _k, kap, _g, g, _s, s = r189["loyo"][y]["variant"].split()
        hi_n[y] = lo_n[y] = 0
        for S in ss:
            if S.day[:4] != y:
                continue
            r = folds[y].get(S.day)
            if r is None:
                continue
            n = None
            if r >= 1.1:
                n = straddle(S)
                hi_n[y] += n is not None
            elif r < float(kap):
                n = sn189.fly(S, float(g), float(s))
                lo_n[y] += n is not None
            if n is not None:
                ledger[S.day] = n
        res["by_year"][y] = {"net": round(sum(v for d, v in ledger.items() if d[:4] == y)), "straddles": hi_n[y], "flies": lo_n[y]}
    total = sum(v["net"] for v in res["by_year"].values())
    pos = sum(v["net"] > 0 for v in res["by_year"].values())
    rng = np.random.default_rng(190)
    pool_st = {y: [n for n in (straddle(S) for S in ss if S.day[:4] == y) if n is not None] for y in pe.YEARS}
    pool_fl = {y: [n for n in (sn189.fly(S, float(r189["loyo"][y]["variant"].split()[3]), float(r189["loyo"][y]["variant"].split()[5]))
                               for S in ss if S.day[:4] == y) if n is not None] for y in pe.YEARS}
    tots = []
    for _ in range(2000):
        t = 0.0
        for y in pe.YEARS:
            if hi_n[y] and pool_st[y]:
                t += float(np.sum(rng.choice(pool_st[y], min(hi_n[y], len(pool_st[y])), replace=False)))
            if lo_n[y] and pool_fl[y]:
                t += float(np.sum(rng.choice(pool_fl[y], min(lo_n[y], len(pool_fl[y])), replace=False)))
        tots.append(t)
    xs = sorted(ledger.values(), reverse=True)
    res.update({"total": total, "years_positive": pos, "null_mean": round(float(np.mean(tots))),
                "null_p95": round(float(np.percentile(tots, 95))), "without_best_5": round(sum(xs[5:])),
                "goal_stats_1000": pe.goal_stats(ledger, days, 1000.0)})
    res["dev_pass"] = bool(total > 0 and pos >= 3 and total > res["null_p95"] and sum(xs[5:]) > 0)
    print("SN190", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
