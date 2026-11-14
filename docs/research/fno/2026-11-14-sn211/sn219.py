"""SN219 - the Gold v6 candidate and the second look (PLAN.md). Frozen before it runs; run once.
SN218 selected WK-X = "settle | loss 2.0" by its frozen rule (no candidate passed the screen, so the best total; it
fires 3 times in 223 weeks, i.e. almost WK-S itself) and failed pass rules 1-2. Declared here, before the second look,
from development results only: the candidate that best meets the owner's goal (profit kept, big losses cut) is the
SN217 expiry-day gate -0.25 (97% of WK-S's profit, worst month -37%, worst week -18%, CVaR -26%, 5 of 5 years).
Candidates: A WK-S; B WK-X (SN218 as frozen); C WK-S + gate -0.25 ("WK-G"); D breach 0.5 + gate -0.25 (SN218's best
worst-month pair keeping >= 65% of the profit); E the pre base (never holds through expiry day), a reference.
1. Development 2023 - Aug 2026: Gold v5 Rs 30k growing + each candidate's daily marks (SN207's summary).
2. Second look, once: TEST, NIFTY Dec 2021 - Mar 2022, SENSEX Oct 2024 - Apr 2026 - per candidate ledgers (SN209's).
Pass rule 4: the three combined > 0 and better than WK-S on each."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk2  # noqa: E402

wk = wk2.wk
sys.path.insert(0, str(wk.HERE))
import sn207  # noqa: E402
import sn209  # noqa: E402

X = pickle.loads((wk2.LOCAL / "sn218-wkx.pkl").read_bytes())
CANDS = {"A WK-S": ("settle", None), f"B WK-X {X['name']}": (X["base"], X["rule"]), "C WK-G (WK-S + gate -0.25)": ("settle", {"gate": -0.25}),
         "D breach 0.5 + gate -0.25": ("settle", {"breach": 0.5, "gate": -0.25}), "E pre base": ("pre", None)}


def run(mk, data, mins, weeks):
    return {k: wk2.book2(mk, data, mins, weeks, wk2.BASES[b], r) for k, (b, r) in CANDS.items()}


if __name__ == "__main__":
    out_path = HERE / "results-sn219.json"
    if out_path.exists():
        raise SystemExit("SN219 is scored once")
    import p4
    D = wk.dev_data()
    W = wk.expiries(D)
    mins = wk2.Minutes("dev")
    res = {"candidates": {k: {"base": b, "rule": r} for k, (b, r) in CANDS.items()}}
    dev = run(wk.NIFTY, D, mins, wk.split(W, "dev"))
    days = sorted(d for d in D["idx"] if sn207.LO <= d < sn207.HI)
    gold = p4.gold("Rs 30k growing (production)")
    res["development"] = {"Gold alone": sn207.summary(gold, days)}
    for k, tr in dev.items():
        m = sn207.marks(tr)
        res["development"][k] = {"alone": sn207.summary(m, days), "Gold +": sn207.summary({d: gold.get(d, 0.0) + m.get(d, 0.0) for d in days}, days),
                                 "weeks": wk2.summary(tr)}
        print(f"SN219 dev {k}:", json.dumps({"alone": {x: res['development'][k]['alone'][x] for x in ('net', 'green_days', 'worst_week', 'worst_month')},
                                             "Gold +": {x: res['development'][k]['Gold +'][x] for x in ('net', 'green_days', 'worst_day', 'worst_week', 'worst_month', 'by_year')}}), flush=True)
    looks = {"TEST": (wk.NIFTY, D, mins, wk.split(W, "test"))}
    for und, mk in (("NIFTY", wk.NIFTY), ("SENSEX", wk.SENSEX)):
        E = wk.exam_data(und)
        looks[f"{und} exam"] = (mk, E, wk2.Minutes(und), wk.expiries(E))
    totals = {k: 0.0 for k in CANDS}
    for name, (mk, data, mm, weeks) in looks.items():
        books = run(mk, data, mm, weeks)
        res[name] = {}
        for k, tr in books.items():
            res[name][k] = sn209.ledger(tr) if tr else {"weeks": 0, "net": 0}
            totals[k] += res[name][k]["net"]
        print(f"SN219 {name}:", json.dumps({k: {x: v.get(x) for x in ("weeks", "net", "win_pct", "worst", "worst_month")} for k, v in res[name].items()}), flush=True)
    res["second look total"] = {k: round(v) for k, v in totals.items()}
    a = "A WK-S"
    res["pass 4"] = {k: bool(totals[k] > 0 and all(res[n][k]["net"] > res[n][a]["net"] for n in looks)) for k in CANDS if k != a}
    print("SN219 second-look totals:", json.dumps(res["second look total"]), "pass 4:", json.dumps(res["pass 4"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
