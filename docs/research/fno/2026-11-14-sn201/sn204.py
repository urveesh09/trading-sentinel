"""SN204 - the unprotected weekly seller, WK-S (PLAN.md amendment). 38 variants (STRADDLE / STRANGLE 0.5 x k x exit
x stop at a 15:15 mark) on the development weeks at Rs 100 per leg-lot; eligible = entered in >= 80% of the weeks it
could trade; LOYO over 2022-2026; WK-S = the best eligible total, the runner-up kept. For both: pass checks 1-3 and 6,
costs, worst weeks, worst month per year, drawdown, tail scenarios at today's level, and WK-S's daily marks on Gold's
empty days vs Gold days (2023 - Aug 2026)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk  # noqa: E402

GOLD_DAYS = wk.FNO / "2026-11-13-sn186/_local/gold-days.json"
WALLET = 250000.0


def months(trades):
    m = {}
    for t in trades:
        m[t["exit_day"][:7]] = m.get(t["exit_day"][:7], 0.0) + t["net"]
    return m


def drawdown(trades):
    eq = np.cumsum([t["net"] for t in sorted(trades, key=lambda t: t["exit_day"])])
    return round(float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))) if len(eq) else 0


def scenarios(trades, struct):
    recent = [t for t in trades if t["entry"] >= "2025-01-01"]
    S = float(np.median([t["S0"] for t in recent]))
    Q = float(np.median([t["Q"] for t in recent]))
    credit = float(np.median([t["credit_pts"] for t in recent]))
    d = 0.0 if struct == "STRADDLE" else wk.dist(wk.NIFTY, 0.5 * Q)
    out = {"index": round(S), "Q_points": round(Q, 1), "credit_points": round(credit, 1)}
    for mv in (0.03, 0.05, 0.08, 0.13):
        pay = max(0.0, mv * S - d)
        out[f"{int(mv * 100)}% move"] = round((credit - pay) * wk.NIFTY["lot"])
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn204.json"
    if out_path.exists():
        raise SystemExit("SN204 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    table, books, cover = {}, {}, {}
    for v in wk.naked_variants():
        tr = wk.book(wk.NIFTY, D, weeks, v)
        books[v] = tr
        possible = sum(len(ds) >= (1 if v[1] == "F" else v[1]) for _e, ds in weeks)
        cover[wk.vname(v)] = round(len(tr) / possible, 3)
        table[wk.vname(v)] = wk.stats(tr)["by_year"]
    elig = [v for v in wk.naked_variants() if cover[wk.vname(v)] >= 0.8]
    lo = wk.loyo({wk.vname(v): table[wk.vname(v)] for v in elig})
    ranked = sorted(elig, key=lambda v: -sum(table[wk.vname(v)].values()))
    A, B = ranked[0], ranked[1]
    res = {"dev_weeks": len(weeks), "variants": len(table), "eligible": len(elig), "coverage": cover, "loyo": lo,
           "ranked": [{"variant": wk.vname(v), "net": sum(table[wk.vname(v)].values()), "by_year": table[wk.vname(v)]} for v in ranked],
           "positive_eligible": sum(sum(table[wk.vname(v)].values()) > 0 for v in elig)}
    for tag, v in (("WK-S", A), ("runner-up", B)):
        tr = books[v]
        st = wk.stats(tr)
        mo = months(tr)
        st.update(variant=wk.vname(v), boot_p5=wk.boot_p5(tr), stops=sum(t["reason"] == "stop" for t in tr),
                  estimated_marks=sum(t["estimated_marks"] for t in tr), drawdown=drawdown(tr),
                  by_stress={str(s): round(sum(t["net"] for t in wk.book(wk.NIFTY, D, weeks, v, stress=s))) for s in (0.0, 50.0, 100.0, 200.0)},
                  worst_10=[{"entry": t["entry"], "expiry": t["expiry"], "net": round(t["net"]), "move_pct": round(100 * (t["S_T"] / t["S0"] - 1), 2) if "S_T" in t else None,
                             "reason": t["reason"]} for t in sorted(tr, key=lambda t: t["net"])[:10]],
                  worst_month_by_year={y: round(min([n for m, n in mo.items() if m[:4] == y] or [0])) for y in wk.YEARS},
                  months_positive=f"{sum(n > 0 for n in mo.values())} of {len(mo)}", worst_month=round(min(mo.values())),
                  yearly_return_on_wallet_pct={y: round(100 * n / WALLET, 1) for y, n in st["by_year"].items()},
                  scenarios=scenarios(tr, v[0]))
        res[tag] = st
        print(f"SN204 {tag}:", json.dumps(st), flush=True)
    a = res["WK-S"]
    res["pass"] = {"1 LOYO > 0 and >= 4 of 5 years": bool(lo["sum"] > 0 and lo["years_positive"] >= 4),
                   "2a > 0 at Rs 200": bool(a["by_stress"]["200.0"] > 0), "2b > 0 without the best 5": bool(a["without_best_5"] > 0),
                   "3 week-resampled p5 > 0": bool(a["boot_p5"] > 0), "6 worst month > -Rs 50,000": bool(a["worst_month"] > -50000)}
    gold = set(json.loads(GOLD_DAYS.read_text(encoding="utf-8")))
    ch = {}
    for t in books[A]:
        if t["entry"] >= "2023-01-01":
            for d, x in wk.daily_changes(t).items():
                ch[d] = ch.get(d, 0.0) + x
    split = {}
    for name, keep in (("Gold days", lambda d: d in gold), ("Gold's empty days", lambda d: d not in gold)):
        x = np.array([y for d, y in ch.items() if keep(d)])
        split[name] = {"days": len(x), "mean": round(float(x.mean())), "median": round(float(np.median(x))),
                       "green_pct": round(float((x > 0).mean() * 100), 1), "sum": round(float(x.sum()))}
    res["WK-S daily marks, 2023 - Aug 2026"] = split
    print("SN204 LOYO:", json.dumps(lo), flush=True)
    print("SN204 pass:", json.dumps(res["pass"]), "daily:", json.dumps(split), flush=True)
    (wk.LOCAL / "sn204-picks.pkl").write_bytes(pickle.dumps({"WK-S": A, "runner-up": B}))
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
