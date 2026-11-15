"""SN203 - the frozen grid, chosen held out (PLAN.md). 78 variants (6 structures x k in {1, 2, 3, F} x exit {settle,
pre} x stop {none, 1x credit}) on the development weeks at Rs 100 per leg-lot; eligible = entered in >= 80% of the
weeks it could trade. LOYO over 2022-2026, eligible variants (each held-out year
scored with the variant best on the other four). WK-A = the best development total; the runner-up is kept. For WK-A:
the pass checks (LOYO, Rs 200, without the best 5, the week-resampled 5th percentile), costs Rs 0 / 50 / 100 / 200, its
grid neighbours (plateau), max loss per lot."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn203.json"
    if out_path.exists():
        raise SystemExit("SN203 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    table, books, cover = {}, {}, {}
    for v in wk.variants():
        tr = wk.book(wk.NIFTY, D, weeks, v)
        books[v] = tr
        possible = sum(len(ds) >= (1 if v[1] == "F" else v[1]) for _e, ds in weeks)
        cover[wk.vname(v)] = round(len(tr) / possible, 3)
        table[wk.vname(v)] = wk.stats(tr)["by_year"]
    elig = [v for v in wk.variants() if cover[wk.vname(v)] >= 0.8]          # PLAN: entered in >= 80% of its weeks
    lo = wk.loyo({wk.vname(v): table[wk.vname(v)] for v in elig})
    ranked = sorted(elig, key=lambda v: -sum(table[wk.vname(v)].values()))
    A, B = ranked[0], ranked[1]
    res = {"dev_weeks": len(weeks), "variants": len(table), "eligible": len(elig), "coverage": cover, "loyo": lo,
           "top10": [{"variant": wk.vname(v), "net": sum(table[wk.vname(v)].values()), "by_year": table[wk.vname(v)]} for v in ranked[:10]],
           "bottom3": [{"variant": wk.vname(v), "net": sum(table[wk.vname(v)].values())} for v in ranked[-3:]],
           "positive_variants": sum(sum(t.values()) > 0 for t in table.values()),
           "positive_eligible": sum(sum(table[wk.vname(v)].values()) > 0 for v in elig), "all": table}
    for tag, v in (("WK-A", A), ("runner-up", B)):
        st = wk.stats(books[v])
        st["variant"] = wk.vname(v)
        st["boot_p5"] = wk.boot_p5(books[v])
        st["by_stress"] = {str(s): round(sum(t["net"] for t in wk.book(wk.NIFTY, D, weeks, v, stress=s))) for s in (0.0, 50.0, 100.0, 200.0)}
        st["stops"] = sum(t["reason"] == "stop" for t in books[v])
        st["estimated_marks"] = sum(t["estimated_marks"] for t in books[v])
        st["skipped_entries"] = sum(1 for e, ds in weeks if (lambda t: t and "skip" in t)(wk.trade(wk.NIFTY, D, e, ds, v[1], v[0], v[2], v[3])))
        res[tag] = st
        print(f"SN203 {tag}:", json.dumps(st), flush=True)
    s, k, ex, stp = A
    nb = [v for v in elig if v != A and ((v[0] == s and v[2:] == A[2:]) or (v[1] == k and v[2:] == A[2:]))]
    res["WK-A neighbours"] = {wk.vname(v): sum(table[wk.vname(v)].values()) for v in nb}
    a = res["WK-A"]
    res["pass"] = {"1 LOYO > 0 and >= 4 of 5 years": bool(lo["sum"] > 0 and lo["years_positive"] >= 4),
                   "2a > 0 at Rs 200": bool(a["by_stress"]["200.0"] > 0), "2b > 0 without the best 5": bool(a["without_best_5"] > 0),
                   "3 week-resampled p5 > 0": bool(a["boot_p5"] > 0)}
    print("SN203 LOYO:", json.dumps(lo), flush=True)
    print("SN203 pass:", json.dumps(res["pass"]), "neighbours:", json.dumps(res["WK-A neighbours"]), flush=True)
    (wk.LOCAL / "sn203-picks.pkl").write_bytes(pickle.dumps({"WK-A": A, "runner-up": B}))
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
