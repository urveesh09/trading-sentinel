"""SN43 ITM depth by the money per lot; SN44 bootstrap of one year; SN45 without the best days; SN46 why 2023 loses."""
import json, random, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V3 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10}
V = {"SN Gold v3": dict(V3), "SN38 cascade up to 2": {**V3, "itm_cascade": 2}}
for lo, hi in ((17500, 20000), (17500, 1e12), (20000, 30000), (16000, 25000)):
    V[f"SN43 auto depth {lo}/{hi:.0f}"] = {**V3, "itm_auto": (lo, hi)}
if __name__ == "__main__":
    res = L.study("sn43", V, HERE)
    years = {y: L.B.Year(y) for y in L.YEARS}
    out = {}
    for wname, W, full in (("A 15k", 15000.0, 1), ("C 30k", 30000.0, 2)):
        ctx = L.Ctx(); days = []
        for y in L.YEARS:
            Y = years[y]; n11 = Y.sigs("N11")
            for S in Y.ordered():
                fl = full if full == 1 else 2
                vd = L.vday_of(S.day, V3)
                days.append((S.day, L.play_day(S, n11.get(S.day, []), V3, W, fl, ctx, vd)))
        # SN45: without the best days
        nets = sorted((x for _d, x in days), reverse=True)
        tot = sum(nets)
        # SN44: one-year paths drawn week by week from all four years
        weeks = defaultdict(float)
        for d, x in days:
            import datetime as dt
            iso = dt.date.fromisoformat(d).isocalendar(); weeks[(iso[0], iso[1])] += x
        wk = list(weeks.values()); rng = random.Random(7)
        sims = [sum(rng.choice(wk) for _ in range(50)) for _ in range(5000)]
        refills = []
        wk_ref = defaultdict(float)
        for d, x in days:
            iso = dt.date.fromisoformat(d).isocalendar(); wk_ref[(iso[0], iso[1])] += max(0.0, -x)
        pairs = [(weeks[k], wk_ref[k]) for k in weeks]
        sims2 = [sum(p[1] for p in (rng.choice(pairs) for _ in range(50))) for _ in range(5000)]
        out[wname] = {"four_year": round(tot), "without_best_5": round(tot - sum(nets[:5])), "without_best_10": round(tot - sum(nets[:10])),
                      "one_year_median": round(float(np.median(sims))), "one_year_p05": round(float(np.percentile(sims, 5))),
                      "one_year_p95": round(float(np.percentile(sims, 95))), "chance_year_loses": round(sum(s < 0 for s in sims) / len(sims), 3),
                      "refill_median": round(float(np.median(sims2))), "refill_p95": round(float(np.percentile(sims2, 95)))}
        print("SN44/45", wname, out[wname], flush=True)
        if wname == "A 15k":
            by = defaultdict(lambda: [0, 0.0])
            for day, j, e, n in ctx.closed:
                k = (day[:4], e); by[k][0] += 1; by[k][1] += n
            print("SN46 per strategy per year (trades, net per lot):", {f"{k[0]} {k[1]}": (v[0], round(v[1])) for k, v in sorted(by.items())}, flush=True)
            out["sn46"] = {f"{k[0]} {k[1]}": v for k, v in by.items()}
    (HERE / "results-sn44-46.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
