"""SN202 - is there a weekly premium? (PLAN.md; development description only). Sell the ATM straddle and each WK
structure at k = 1, 2, 3, F at 15:15 and hold to settlement. Per year: the settlement payout / Q (below 1 means the
seller is paid), gross (no spread, charges or stress) and net (Rs 100 per leg-lot), win rate, worst week; the long
straddle as the mirror. The IF 1.0 k F daily marks on Gold's empty days vs Gold days (2023 - Aug 2026)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk  # noqa: E402

GOLD_DAYS = wk.FNO / "2026-11-13-sn186/_local/gold-days.json"

if __name__ == "__main__":
    out_path = HERE / "results-sn202.json"
    if out_path.exists():
        raise SystemExit("SN202 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    res = {"dev_weeks": len(weeks), "straddle": {}, "structures": {}}
    for k in (1, 2, 3, "F"):
        rows = []
        for e, days in weeks:
            t = wk.trade(wk.NIFTY, D, e, days, k, "STRADDLE", "settle", None, wk.SCORE_STRESS)
            if not t or "net" not in t:
                continue
            payout = abs(t["S_T"] - t["K0"])
            gross = (t["Q"] - payout) * wk.NIFTY["lot"]
            rows.append({"y": t["entry"][:4], "ratio": payout / t["Q"], "gross": gross, "net": t["net"],
                         "long_net": -gross - (gross - t["net"])})   # the buyer pays the same frictions (gross - net)
        by = {}
        for y in wk.YEARS + ("all",):
            r = [x for x in rows if y == "all" or x["y"] == y]
            if not r:
                continue
            g = np.array([x["gross"] for x in r])
            n = np.array([x["net"] for x in r])
            by[y] = {"weeks": len(r), "payout_over_Q_mean": round(float(np.mean([x["ratio"] for x in r])), 3),
                     "payout_over_Q_median": round(float(np.median([x["ratio"] for x in r])), 3),
                     "gross_sum": round(float(g.sum())), "net_sum": round(float(n.sum())), "net_mean": round(float(n.mean())),
                     "win_pct": round(float((n > 0).mean() * 100), 1), "worst_week": round(float(n.min())),
                     "long_straddle_net_sum": round(float(sum(x["long_net"] for x in r)))}
        res["straddle"][f"k{k}"] = by
        print(f"SN202 straddle k{k}:", json.dumps(by.get("all")), flush=True)
    for s in wk.STRUCTS:
        for k in (1, 2, 3, "F"):
            tr = wk.book(wk.NIFTY, D, weeks, (s, k, "settle", None))
            st = wk.stats(tr)
            gross0 = wk.book(wk.NIFTY, D, weeks, (s, k, "settle", None), stress=0.0)
            st["net_at_stress_0"] = round(sum(t["net"] for t in gross0))
            res["structures"][f"{s} k{k}"] = st
            print(f"SN202 {s} k{k}:", json.dumps({x: st[x] for x in ("weeks", "net", "win_pct", "worst", "by_year", "net_at_stress_0")}), flush=True)
    gold = set(json.loads(GOLD_DAYS.read_text(encoding="utf-8")))
    tr = [t for t in wk.book(wk.NIFTY, D, weeks, ("IF 1.0", "F", "settle", None)) if t["entry"] >= "2023-01-01"]
    ch = {}
    for t in tr:
        for d, v in wk.daily_changes(t).items():
            ch[d] = ch.get(d, 0.0) + v
    split = {}
    for name, keep in (("Gold days", lambda d: d in gold), ("Gold's empty days", lambda d: d not in gold)):
        v = np.array([x for d, x in ch.items() if keep(d)])
        split[name] = {"days": len(v), "mean": round(float(v.mean())), "median": round(float(np.median(v))),
                       "green_pct": round(float((v > 0).mean() * 100), 1), "sum": round(float(v.sum()))}
    res["IF 1.0 kF daily marks, 2023 - Aug 2026"] = split
    print("SN202 daily marks:", json.dumps(split), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
