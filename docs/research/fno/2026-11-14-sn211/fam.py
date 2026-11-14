"""SN213-SN218 shared (PLAN.md): run a family of smart rules on the development weeks on both bases, score each
variant (net, per year, worst week, worst month, CVaR 5%, how often it fired) and choose by LOYO."""
from __future__ import annotations

import json

import wk2

wk = wk2.wk
GRID = {"breach": [-0.25, 0.0, 0.25, 0.5], "loss": [0.5, 1.0, 1.5, 2.0], "profit": [0.5, 0.7], "speed": [0.3, 0.5, 0.7],
        "protect": [0.0, 0.25], "gate": [-0.25, 0.0, 0.25, 0.5]}
WKS_NET, WKS_WORST, WKS_MONTH = 313523, -39844, -51245
_C = {}


def dev():
    if not _C:
        D = wk.dev_data()
        _C.update(D=D, W=wk.split(wk.expiries(D), "dev"), M=wk2.Minutes("dev"))
    return _C["D"], _C["W"], _C["M"]


def run(rules, bases=("settle", "pre"), **kw):
    D, W, M = dev()
    books = {}
    for b in bases:
        books[f"{b} | none"] = wk2.book2(wk.NIFTY, D, M, W, wk2.BASES[b], None)
        for nm, r in rules.items():
            books[f"{b} | {nm}"] = wk2.book2(wk.NIFTY, D, M, W, wk2.BASES[b], r, **kw)
    return books


def screen(row):
    """Pass rules 1 (on the variant's own total here; SN218 applies LOYO) and 2."""
    return {"keeps_80pct_profit": row["net"] >= 0.8 * WKS_NET, "years_4_of_5": row["years_positive"] >= 4,
            "worst_week_30pct_smaller": row["worst"] >= 0.7 * WKS_WORST, "worst_month_30pct_smaller": row["worst_month"] >= 0.7 * WKS_MONTH}


def score(books, rules):
    rows = {k: wk2.summary(tr) for k, tr in books.items()}
    for k, r in rows.items():
        r["screen"] = screen(r)
    cand = {k: v["by_year"] for k, v in rows.items() if not k.endswith("| none")}
    lo = wk.loyo(cand)
    best = max(cand, key=lambda k: sum(cand[k].values()))
    return {"rows": rows, "loyo": lo, "best": best, "best_rule": rules[best.split(" | ", 1)[1]],
            "rules": {n: r for n, r in rules.items()}}


def show(tag, res):
    for k, r in res["rows"].items():
        print(f"{tag} {k:34s} net {r['net']:>9} worst {r['worst']:>8} month {r['worst_month']:>8} cvar5 {r['cvar5']:>8} "
              f"yrs+ {r['years_positive']} fired {r['fired']:>3} hedges {r['hedges']:>3} {r['by_year']}", flush=True)
    print(f"{tag} LOYO", json.dumps(res["loyo"]), "best", res["best"], flush=True)
