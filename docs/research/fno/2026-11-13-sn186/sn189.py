"""SN189 - the variance seller on calm forecasts (PLAN.md). Gold's empty days (development) with SN171's HAR forecast /
implied < kappa (kappa in {0.75, 0.85, 0.95}; the fold's HAR is fitted without the scored year): sell the ATM iron fly
with +/-200 wings (1 lot, Rs 1.5 lakh wallet; Rs 100 per leg-lot) at 10:00; take +goal (Rs 1,000 / 1,500), stop -s
(Rs 3,000 / 4,500), else 15:10 (minute closes). LOYO over 12 variants; matched null: as many random empty days per
year with the same exits (pool = every empty day's fly). Robustness: Rs 200 per leg-lot, 1 minute late."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

pw, p3 = pe.pw, pe.p3
KAPPAS = (0.75, 0.85, 0.95)
EXITS = list(itertools.product((1000.0, 1500.0), (3000.0, 4500.0)))


def fly(S, goal, stop, stress=pe.MULTI_STRESS, late=0):
    i = p3.I1000 + late
    v = pe.iron_fly_vals(S, i, stress=stress)
    if v is None:
        return None
    return pe.settle(v, i, target=goal, stop=stop)[0]


if __name__ == "__main__":
    out_path = HERE / "results-sn189.json"
    if out_path.exists():
        raise SystemExit("SN189 is scored once")
    ss = pe.empty_sessions()
    days = [S.day for S in ss]
    allss = pw.dev_sessions()
    har = p3.HAR(allss)
    folds = {y: p3.rho_table(har, allss, lambda d, y=y: d[:4] != y) for y in pe.YEARS}
    raw = {(g, s): {S.day: fly(S, g, s) for S in ss} for g, s in EXITS}
    res = {"empty_days": len(ss), "loyo": {}}
    for y in pe.YEARS:
        vn = {}
        for k, (g, s) in itertools.product(KAPPAS, EXITS):
            vn[f"kappa {k} goal {g:.0f} stop {s:.0f}"] = {d: n for d, n in raw[(g, s)].items()
                                                          if n is not None and folds[y].get(d, 9.0) < k}
        ch, _t, _p = pe.loyo(vn)
        res["loyo"][y] = ch[y]
    total = sum(v["net"] for v in res["loyo"].values())
    pos = sum(v["net"] > 0 for v in res["loyo"].values())
    tots = []
    rng = np.random.default_rng(189)
    for _ in range(2000):
        t = 0.0
        for y in pe.YEARS:
            _k, _kv, _g, g, _s, s = res["loyo"][y]["variant"].split()
            pool = [n for d, n in raw[(float(g), float(s))].items() if n is not None and d[:4] == y]
            k_ = res["loyo"][y]["trades"]
            if pool and k_:
                t += float(np.sum(rng.choice(pool, min(k_, len(pool)), replace=False)))
        tots.append(t)
    res.update({"loyo_total": total, "years_positive": pos, "null_mean": round(float(np.mean(tots))),
                "null_p95": round(float(np.percentile(tots, 95)))})
    sess = {S.day: S for S in ss}
    robust = {"stress_200_per_leg": 0.0, "late_1": 0.0}
    held = []
    for y in pe.YEARS:
        _k, kap, _g, g, _s, s = res["loyo"][y]["variant"].split()
        for d, n in raw[(float(g), float(s))].items():
            if n is not None and d[:4] == y and folds[y].get(d, 9.0) < float(kap):
                held.append(n)
                robust["stress_200_per_leg"] += fly(sess[d], float(g), float(s), stress=200.0) or 0.0
                robust["late_1"] += fly(sess[d], float(g), float(s), late=1) or 0.0
    held.sort(reverse=True)
    res["robust_loyo"] = {k: round(v) for k, v in robust.items()} | {"without_best_5": round(sum(held[5:]))}
    rho_all = p3.rho_table(har, allss, lambda d: True)
    ins = {}
    for k, (g, s) in itertools.product(KAPPAS, EXITS):
        dn = {d: n for d, n in raw[(g, s)].items() if n is not None and rho_all.get(d, 9.0) < k}
        ins[f"kappa {k} goal {g:.0f} stop {s:.0f}"] = pe.goal_stats(dn, days, g)
    res["in_sample"] = ins
    res["all_empty_days_fly"] = {f"goal {g:.0f} stop {s:.0f}": pe.goal_stats({d: n for d, n in raw[(g, s)].items() if n is not None}, days, g)
                                 for g, s in EXITS}
    res["final_variant"] = max(ins, key=lambda k: ins[k]["net"])
    res["dev_pass"] = bool(total > 0 and pos >= 3 and total > res["null_p95"] and robust["stress_200_per_leg"] > 0
                           and robust["late_1"] > 0 and sum(held[5:]) > 0)
    print("SN189", json.dumps({k: v for k, v in res.items() if k not in ("in_sample",)}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
