"""SN218 - the combined smart exit, WK-X (PLAN.md). Candidates: each family's development-best variant (SN213 breach,
SN214 loss and profit, SN215 speed, SN216 protect, SN217 calendar and gate) and every pair of one trigger (the breach /
loss / speed winners' rules) with one modifier (the protect / profit / calendar / gate winners' rules), each on both
bases (the gate only on settle).
Selection with the screen (pass rule 2 plus profit kept): worst week >= -27,891, worst month >= -35,872, total >= 80% of
WK-S's development total scaled to the years used, >= 4 of 5 years positive (3 of 4 inside LOYO).
LOYO: each held-out year scored with the candidate best on the other four among those passing the screen there (else
the best total). Pass rule 1 = LOYO >= Rs 2,50,818 with >= 4 of 5 held-out years positive.
WK-X = the best development total among candidates passing the screen on all five years (else the best total, marked
failing). Robustness: exits 2 minutes later, Rs 200 per leg-lot, a Rs 200 opening penalty, parameter neighbours."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fam  # noqa: E402

wk2, wk = fam.wk2, fam.wk
YEARS = wk.YEARS


def winners():
    out = {}
    r = lambda sn: json.loads((HERE / f"results-sn{sn}.json").read_text(encoding="utf-8"))  # noqa: E731
    for fname, part in (("breach", r("213")), ("loss", r("214")["loss"]), ("profit", r("214")["profit"]), ("speed", r("215")),
                        ("protect", r("216")), ("calendar", r("217")["calendar"]), ("gate", r("217")["gate"])):
        out[fname] = {"base": part["best"].split(" | ")[0], "rule": part["best_rule"]}
    return out


def ok_screen(trades, years):
    tr = [t for t in trades if t["entry"][:4] in years]
    if not tr:
        return False, 0.0
    mo = {}
    for t in tr:
        mo[t["exit_day"][:7]] = mo.get(t["exit_day"][:7], 0.0) + t["net"]
    by = {y: sum(t["net"] for t in tr if t["entry"][:4] == y) for y in years}
    tot = sum(by.values())
    base_scaled = 0.8 * sum(v for y, v in BASE_BY.items() if y in years)
    need_pos = len(years) - 1
    good = (min(t["net"] for t in tr) >= 0.7 * fam.WKS_WORST and min(mo.values()) >= 0.7 * fam.WKS_MONTH
            and tot >= base_scaled and sum(v > 0 for v in by.values()) >= need_pos)
    return good, tot


if __name__ == "__main__":
    out_path = HERE / "results-sn218.json"
    if out_path.exists():
        raise SystemExit("SN218 is run once")
    W = winners()
    D, Wk, M = fam.dev()
    base_book = wk2.book2(wk.NIFTY, D, M, Wk, wk2.WK_S, None)
    BASE_BY = {y: sum(t["net"] for t in base_book if t["entry"][:4] == y) for y in YEARS}
    cands = {}
    for fname, w in W.items():
        cands[f"{w['base']} | {fname}: {wk2.name(w['rule'])}"] = (w["base"], dict(w["rule"]))
    for trig in ("breach", "loss", "speed"):
        for mod in ("protect", "profit", "calendar", "gate"):
            rule = {**W[trig]["rule"], **W[mod]["rule"]}
            for b in (("settle",) if mod == "gate" else ("settle", "pre")):
                cands[f"{b} | {trig}+{mod}: {wk2.name(rule)}"] = (b, rule)
    books = {k: wk2.book2(wk.NIFTY, D, M, Wk, wk2.BASES[b], r) for k, (b, r) in cands.items()}
    rows = {k: wk2.summary(tr) for k, tr in books.items()}
    lo, held = {}, 0.0
    for y in YEARS:
        others = [x for x in YEARS if x != y]
        scr = {k: ok_screen(tr, others) for k, tr in books.items()}
        pool = [k for k in books if scr[k][0]] or list(books)
        pick = max(pool, key=lambda k: scr[k][1])
        lo[y] = {"pick": pick, "screened": bool(scr[pick][0]), "net": round(rows[pick]["by_year"][y])}
        held += lo[y]["net"]
    lo["sum"] = round(held)
    lo["years_positive"] = sum(lo[y]["net"] > 0 for y in YEARS)
    full = {k: ok_screen(tr, list(YEARS)) for k, tr in books.items()}
    passing = [k for k in books if full[k][0]]
    X = max(passing or list(books), key=lambda k: rows[k]["net"])
    res = {"winners": W, "candidates": len(cands), "base WK-S": wk2.summary(base_book), "rows": rows, "loyo": lo,
           "passing_screen": passing, "WK-X": X, "WK-X passes screen": X in passing,
           "pass": {"1 LOYO >= 2,50,818 and >= 4 of 5": bool(lo["sum"] >= 250818 and lo["years_positive"] >= 4),
                    "2 worst week / month 30% smaller": bool(rows[X]["worst"] >= 0.7 * fam.WKS_WORST and rows[X]["worst_month"] >= 0.7 * fam.WKS_MONTH)}}
    b, r = cands[X]
    rb = {}
    for tag, kw in (("exits 2 minutes later", {"delay": 2}), ("Rs 200 per leg-lot", {"stress": 200.0}), ("Rs 200 opening penalty", {"open_pen": 200.0})):
        rb[tag] = wk2.summary(wk2.book2(wk.NIFTY, D, M, Wk, wk2.BASES[b], r, **kw))
    for key, v in r.items():
        if key in fam.GRID and v is not True:
            g = fam.GRID[key]
            i = g.index(v)
            for j in (i - 1, i + 1):
                if 0 <= j < len(g):
                    r2 = {**r, key: g[j]}
                    rb[f"neighbour {key} {g[j]:g}"] = wk2.summary(wk2.book2(wk.NIFTY, D, M, Wk, wk2.BASES[b], r2))
    res["robustness"] = rb
    res["pass"]["3 > 0 at Rs 200 and 2 minutes later"] = bool(rb["Rs 200 per leg-lot"]["net"] > 0 and rb["exits 2 minutes later"]["net"] > 0)
    for k, x in rows.items():
        print(f"SN218 {k:60s} net {x['net']:>9} worst {x['worst']:>8} month {x['worst_month']:>8} cvar5 {x['cvar5']:>8} yrs+ {x['years_positive']} {'SCREEN' if k in passing else ''}", flush=True)
    print("SN218 base", json.dumps({x: res["base WK-S"][x] for x in ("net", "worst", "worst_month", "cvar5")}), flush=True)
    print("SN218 LOYO", json.dumps(lo), flush=True)
    print("SN218 WK-X", X, json.dumps(res["pass"]), flush=True)
    for k, x in rb.items():
        print(f"SN218 robust {k:32s} net {x['net']:>9} worst {x['worst']:>8} month {x['worst_month']:>8} {x['by_year']}", flush=True)
    (wk2.LOCAL / "sn218-wkx.pkl").write_bytes(pickle.dumps({"name": X, "base": b, "rule": r}))
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
