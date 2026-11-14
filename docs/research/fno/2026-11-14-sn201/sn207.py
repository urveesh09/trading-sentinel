"""SN207 - Gold + the weekly seller in one account (PLAN.md SN206 rule, applied to WK-S by the amendment).
Development 2023-01-02 .. 2026-08-19: Gold v5 Rs 30k growing (production) day nets (SN161 p4, development days) plus
WK-S's daily marks (1 lot; Rs 2.5 lakh wallet), and the SN205 / SN206 filtered book when that filter passed. Per day:
green / red / flat for each and combined; WK-S on Gold's empty days; correlation; worst day / week / month; per year."""
from __future__ import annotations

import datetime as _dt
import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk  # noqa: E402

sys.path.insert(0, str(wk.FNO / "2026-11-13-sn161"))
LO, HI = "2023-01-02", wk.TEST_FROM


def marks(trades):
    ch = {}
    for t in trades:
        for d, x in wk.daily_changes(t).items():
            if LO <= d < HI:
                ch[d] = ch.get(d, 0.0) + x
    return ch


def summary(x_by_day, days):
    x = np.array([x_by_day.get(d, 0.0) for d in days])
    wk_ = {}
    mo = {}
    for d, v in zip(days, x):
        iso = _dt.date.fromisoformat(d).isocalendar()
        wk_[(iso[0], iso[1])] = wk_.get((iso[0], iso[1]), 0.0) + v
        mo[d[:7]] = mo.get(d[:7], 0.0) + v
    by = {y: round(float(x[[d[:4] == y for d in days]].sum())) for y in ("2023", "2024", "2025", "2026")}
    return {"net": round(float(x.sum())), "green_days": int((x > 0).sum()), "red_days": int((x < 0).sum()), "flat_days": int((x == 0).sum()),
            "days_at_least_500": int((x >= 500).sum()), "worst_day": round(float(x.min())), "worst_week": round(min(wk_.values())),
            "worst_month": round(min(mo.values())), "months_positive": f"{sum(v > 0 for v in mo.values())} of {len(mo)}",
            "weeks_positive": f"{sum(v > 0 for v in wk_.values())} of {len(wk_)}", "by_year": by}


if __name__ == "__main__":
    out_path = HERE / "results-sn207.json"
    if out_path.exists():
        raise SystemExit("SN207 is run once")
    import p4
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    A = pickle.loads((wk.LOCAL / "sn204-picks.pkl").read_bytes())["WK-S"]
    tr = wk.book(wk.NIFTY, D, weeks, A)
    days = sorted(d for d in D["idx"] if LO <= d < HI)
    gold = p4.gold("Rs 30k growing (production)")
    gold_days = set(json.loads((wk.FNO / "2026-11-13-sn186/_local/gold-days.json").read_text(encoding="utf-8")))
    books = {"WK-S": marks(tr)}
    for sn, key in (("205", "rule_A"), ("206", "lgb"), ("206", "lstm"), ("206", "avg")):
        r = json.loads((HERE / f"results-sn{sn}.json").read_text(encoding="utf-8"))
        if r.get(key, {}).get("PASS"):
            dec = pickle.loads((wk.LOCAL / f"sn{sn}-decisions.pkl").read_bytes())
            dec = dec if sn == "205" else dec[key]
            books[f"WK-S + SN{sn} {key}"] = marks([t for t in tr if dec.get(t["expiry"], True)])
    res = {"variant": wk.vname(A), "days": len(days), "Gold alone": summary(gold, days), "WK-S alone": summary(books["WK-S"], days)}
    both = {d: gold.get(d, 0.0) + books["WK-S"].get(d, 0.0) for d in days}
    res["Gold + WK-S"] = summary(both, days)
    g = np.array([gold.get(d, 0.0) for d in days])
    w = np.array([books["WK-S"].get(d, 0.0) for d in days])
    res["correlation_all_days"] = round(float(np.corrcoef(g, w)[0, 1]), 3)
    on = g != 0
    res["correlation_gold_trade_days"] = round(float(np.corrcoef(g[on], w[on])[0, 1]), 3)
    res["WK-S on Gold trade days"] = {"days": int(on.sum()), "mean": round(float(w[on].mean())), "green_pct": round(100 * float((w[on] > 0).mean()), 1)}
    off = np.array([d not in gold_days for d in days])
    res["WK-S on Gold's empty days"] = {"days": int(off.sum()), "mean": round(float(w[off].mean())), "median": round(float(np.median(w[off]))),
                                        "green_pct": round(100 * float((w[off] > 0).mean()), 1), "sum": round(float(w[off].sum()))}
    res["wallets"] = {"Gold": 30000, "WK-S": 250000}
    res["filters_passed"] = [k for k in books if k != "WK-S"]
    for name in res["filters_passed"]:
        res[name] = summary(books[name], days)
        res[f"Gold + {name}"] = summary({d: gold.get(d, 0.0) + books[name].get(d, 0.0) for d in days}, days)
    print("SN207", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
