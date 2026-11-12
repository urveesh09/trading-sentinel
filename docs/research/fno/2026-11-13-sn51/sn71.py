"""SN71 v5 one-year risk (weeks redrawn) and the real account (no refill) from each quarter; SN72 best-day dependence."""
import datetime as dt, json, random, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab as L
V4 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": 0.10, "itm_auto": (17500, 20000)}
V5 = {**V4, "books": ("N11", "R0.85"), "in_x": None, "in_atr": 1.0, "in_full": True}
if __name__ == "__main__":
    L.VOLT.update(L.vol_table())
    years = {y: L.B.Year(y) for y in L.YEARS}
    out = {}
    for wname, W, full in (("A 15k", 15000.0, 1), ("B 20k", 20000.0, 1), ("C 30k", 30000.0, 2)):
        ctx = L.Ctx(); days = []
        for y in L.YEARS:
            Y = years[y]
            for S in Y.ordered():
                vd = L.vday_of(S.day, V5) if full == 2 else False
                days.append((S.day, L.play_day(S, L.sig_of(Y, S.day, V5), V5, W, full, ctx, vd)))
        nets = sorted((x for _d, x in days), reverse=True)
        wk, wr = defaultdict(float), defaultdict(float)
        for d, x in days:
            k = dt.date.fromisoformat(d).isocalendar()[:2]; wk[k] += x; wr[k] += max(0.0, -x)
        keys = list(wk); rng = random.Random(11)
        sims = [[rng.choice(keys) for _ in range(50)] for _ in range(5000)]
        prof = [sum(wk[k] for k in s) for s in sims]; refl = [sum(wr[k] for k in s) for s in sims]
        out[wname] = {"four_year": round(sum(nets)), "without_best_5": round(sum(nets) - sum(nets[:5])), "without_best_10": round(sum(nets) - sum(nets[:10])),
                      "year_median": round(float(np.median(prof))), "year_p05": round(float(np.percentile(prof, 5))), "year_p95": round(float(np.percentile(prof, 95))),
                      "losing_year_chance": round(sum(p < 0 for p in prof) / len(prof), 3), "refill_median": round(float(np.median(refl))), "refill_p95": round(float(np.percentile(refl, 95)))}
        print("SN71/72", wname, out[wname], flush=True)
    starts = [f"{y}-{m}-01" for y in ("2023", "2024", "2025", "2026") for m in ("01", "04", "07", "10")][:-1]
    rows = []
    for W0 in (15000.0, 20000.0, 30000.0):
        L.WALLETS = ((f"real {int(W0/1000)}k", W0, "float", None),)
        ends = []
        for st in starts:
            r = L.run(years, None, {**V5, "from_day": st, "float_cap": 50625.0})
            ends.append(r[f"real {int(W0/1000)}k"]["final_equity"]["net"])
        dead = sum(e < 7500 for e in ends)
        rows.append({"start_wallet": W0, "ends": ends, "dead": dead})
        print(f"SN71 real account (no refill) from Rs {int(W0)}: ends by start quarter {ends} | dead {dead} of {len(ends)}", flush=True)
    out["real_accounts"] = rows
    (HERE / "results-sn71-72.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
