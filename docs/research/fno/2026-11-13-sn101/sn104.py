"""SN104 - does SN95-L's straddle give its profit back? (PLAN.md) Path description, then ONE frozen exit challenger
GB (arm at +Rs 1,000 net, exit at 50% of the peak) against hold and a fixed 13:00 exit, on identical entries."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402

C = pa.C
T1300 = 225


if __name__ == "__main__":
    out_path = HERE / "results-sn104.json"
    if out_path.exists():
        raise SystemExit("SN104 is scored once")
    adm = pa.admission()
    Ys = C.years()
    res = {}
    for dname, sel in (("gold-free (SN95-L)", lambda d: pa.sn95l(adm, d)),
                       ("all days", lambda d: adm.get((d, "10:00", "R_today", 0.2, "top"), False))):
        paths = []
        for y in C.YEARS:
            for S in Ys[y].ordered():
                if not sel(S.day):
                    continue
                got = pa.path(S, pa.I10)
                if got is None or got[1] > 15000.0:
                    continue
                paths.append((S.day, got[2]))
        desc = []
        rules = {"hold": {}, "GB": {}, "13:00": {}}
        for day, vals in paths:
            hold = pa.settle(vals, pa.I10, 3000.0)
            gb = pa.settle(vals, pa.I10, 3000.0, rule="gb")
            t13 = pa.settle(vals, pa.I10, 3000.0, t_exit=T1300)
            seg = vals[pa.I10 + 1: hold[1] + 1]
            ok = seg[~np.isnan(seg)]
            mfe = float(ok.max()) if len(ok) else 0.0
            desc.append({"day": day, "hold": round(hold[0]), "exit": hold[2], "mfe": round(mfe), "giveback": round(mfe - hold[0]),
                         "minutes_above_0": int((ok > 0).sum()), "minutes_above_1000": int((ok > 1000).sum()),
                         "gb": round(gb[0]), "gb_exit": gb[2], "t13": round(t13[0])})
            rules["hold"][day], rules["GB"][day], rules["13:00"][day] = hold[0], gb[0], t13[0]
        tabs = {k: pa.year_table(v) for k, v in rules.items()}
        n = len(desc)
        summary = {"trades": n, "mean_mfe": round(float(np.mean([d["mfe"] for d in desc]))) if n else 0,
                   "hindsight_bound_sum_mfe_unattainable": sum(max(0, d["mfe"]) for d in desc),
                   "share_ever_above_0": round(float(np.mean([d["minutes_above_0"] > 0 for d in desc])), 3) if n else 0,
                   "share_ever_above_1000": round(float(np.mean([d["minutes_above_1000"] > 0 for d in desc])), 3) if n else 0,
                   "mean_giveback_of_trades_that_reached_1000": round(float(np.mean([d["giveback"] for d in desc if d["minutes_above_1000"] > 0] or [0]))),
                   "stopped": sum(d["exit"] == "stop" for d in desc)}
        gbt, hd, t13 = tabs["GB"], tabs["hold"], tabs["13:00"]
        better_years = sum(gbt[y]["net"] >= hd[y]["net"] for y in C.YEARS)
        ok = gbt["total"] >= hd["total"] and better_years >= 3 and gbt["without_best_5"] > hd["without_best_5"] and gbt["total"] > t13["total"]
        res[dname] = {"summary": summary, "tables": tabs, "paths": desc,
                      "verdict": {"GB_total": gbt["total"], "hold_total": hd["total"], "t13_total": t13["total"],
                                  "GB_years_at_least_hold": better_years, "GB_without_best_5": gbt["without_best_5"],
                                  "hold_without_best_5": hd["without_best_5"], "PASS": ok}}
        print(f"=== SN104 {dname}", summary, flush=True)
        for k, t in tabs.items():
            print(f"   {k:6s} {[t[y]['net'] for y in C.YEARS]} total {t['total']:>8} w/o best5 {t['without_best_5']:>8}", flush=True)
        print("   VERDICT", res[dname]["verdict"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
