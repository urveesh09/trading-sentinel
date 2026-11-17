"""SN487 (own): where Gold's money comes from; SN489 (own): adds by expert, chosen honestly (PLAN.md SN487 / SN489, frozen at
bf895633; details fixed here before any number). Gold v5 on GOLD_30K, paths 2022 and 2023-26, Rs 205 / 400.

SN487, from Gold's trade log (goldx): per trade first-lot piece net, added pieces' net, the extension's contribution (net minus
the counterfactual sale of the pieces held at N11's exit, at N11's exit bid), charges (fees minus stress) and stress (Rs/lot x lots);
sums by year, expert, side; add count and add win rate (added pieces' net > 0); the top-5 days' parts.
SN489: experts = the expert names in Gold's DEPLOYED stream. For each expert E, Gold with E's adds off (goldx no_add={E}),
paired by year with Gold. Leave-one-year-out over 2022-2026: for held-out year Y, an expert keeps its adds when the sum of its
add contribution (Gold minus Gold-without-E's-adds) over the other four years at Rs 400 is > 0; the rule (adds off for the others)
is run on Y's path and Y's paired difference taken; the honest estimate = the sum over Y, at Rs 205 and Rs 400 (the rule chosen
at Rs 400 is applied at both). If both sums > 0, the rule chosen on all five years is frozen for SN490; else SN489 ends.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn480 as A  # noqa: E402

goldx, g = A.goldx, A.g
OUT7 = HERE / "results-sn487.json"
OUT9 = HERE / "results-sn489.json"
YEARS5 = ("2022", "2023", "2024", "2025", "2026")


def path_of(y):
    return g.Y22 if y == "2022" else g.Y2326


def decompose(log, stress):
    agg = collections.defaultdict(lambda: collections.defaultdict(float))
    for t in log:
        lots = sum(p[1] for p in t["pieces"])
        first = t["pieces"][0][2] if t["pieces"] else 0.0
        adds = sum(p[2] for p in t["pieces"][1:])
        ext = t.get("ext_contrib", 0.0) if t.get("ext") else 0.0
        stress_rs = stress * lots
        charges = t["fees"] - stress_rs
        for key in ("all", f"year {t['day'][:4]}", f"expert {t.get('expert')}", f"side {t.get('opt')}"):
            a = agg[key]
            a["trades"] += 1
            a["net"] += t["net"]
            a["first_lot_pieces"] += first
            a["added_pieces"] += adds
            a["extension_contribution"] += ext
            a["charges"] += charges
            a["stress"] += stress_rs
            a["adds"] += 1 if len(t["pieces"]) > 1 else 0
            a["adds_won"] += 1 if len(t["pieces"]) > 1 and adds > 0 else 0
            a["extended"] += 1 if t.get("ext") else 0
    return {k: {x: round(v, 0) for x, v in d.items()} for k, d in sorted(agg.items())}


def top5(days, log):
    best = sorted(days, key=lambda r: -r[2])[:5]
    out = []
    for d, _w, n, _t, _l in best:
        ts = [t for t in log if t["day"] == d]
        out.append({"day": d, "net": round(n), "trades": [{"i": t["i"], "expert": t.get("expert"), "opt": t.get("opt"), "lots0": t["lots0"],
                                                           "first": round(t["pieces"][0][2]) if t["pieces"] else 0,
                                                           "adds": round(sum(p[2] for p in t["pieces"][1:])), "ext": round(t.get("ext_contrib", 0.0)) if t.get("ext") else 0,
                                                           "reason": t["reason"]} for t in ts]})
    return out


def by_year(days):
    out = collections.defaultdict(float)
    for d, _w, n, _t, _l in days:
        out[d[:4]] += n
    return out


def main():
    if OUT7.exists() or OUT9.exists():
        raise SystemExit("SN487 / SN489 are scored once")
    goldx.install()
    R7, base = {}, {}
    for pname, years in A.PATHS:
        for st in A.STRESSES:
            s, days, log = A.run(years, st, goldx.GOLD_30K)
            base[(pname, st)] = (s, days, log)
            R7[f"{pname} @{int(st)}"] = {"summary": s, "parts": decompose(log, st), "top5": top5(days, log)}
    OUT7.write_text(json.dumps(R7, indent=1), encoding="utf-8")
    experts = sorted({t.get("expert") for (_p, _s), (_x, _d, log) in base.items() for t in log if t.get("expert")})
    contrib = {}          # (expert, stress) -> {year: Gold - Gold without E's adds}
    for e in experts:
        for st in A.STRESSES:
            yy = {}
            for pname, years in A.PATHS:
                _s, days, _log = A.run(years, st, goldx.GOLD_30K, no_add=frozenset({e}))
                b = by_year(base[(pname, st)][1])
                o = by_year(days)
                for y in b:
                    yy[y] = b[y] - o[y]
            contrib[(e, st)] = yy
    loyo, honest = {}, {205.0: 0.0, 400.0: 0.0}
    for Y in YEARS5:
        keep = [e for e in experts if sum(v for y, v in contrib[(e, 400.0)].items() if y != Y) > 0]
        off = frozenset(e for e in experts if e not in keep)
        row = {"keep_adds": keep, "adds_off": sorted(off)}
        for st in A.STRESSES:
            pname = "2022" if Y == "2022" else "2023-2026"
            b = by_year(base[(pname, st)][1])
            if off:
                _s, days, _log = A.run(path_of(Y), st, goldx.GOLD_30K, no_add=off)
                o = by_year(days)
            else:
                o = b
            row[f"@{int(st)}"] = round(o[Y] - b[Y])
            honest[st] += o[Y] - b[Y]
        loyo[Y] = row
    final_keep = [e for e in experts if sum(contrib[(e, 400.0)].values()) > 0]
    qualified = honest[205.0] > 0 and honest[400.0] > 0
    R9 = {"experts": experts, "add_contribution_by_year": {f"{e} @{int(st)}": {y: round(v) for y, v in sorted(c.items())} for (e, st), c in contrib.items()},
          "loyo": loyo, "honest_estimate": {f"@{int(k)}": round(v) for k, v in honest.items()}, "qualified_for_SN490": qualified,
          "frozen_rule": {"keep_adds": final_keep, "adds_off": sorted(set(experts) - set(final_keep))} if qualified else None}
    OUT9.write_text(json.dumps(R9, indent=1), encoding="utf-8")
    for k, v in R7.items():
        a = v["parts"]["all"]
        print(k, {x: a[x] for x in ("trades", "net", "first_lot_pieces", "added_pieces", "extension_contribution", "charges", "stress", "adds", "adds_won", "extended")})
    print(json.dumps({k: v for k, v in R9.items() if k != "add_contribution_by_year"}, indent=1))
    for k, v in R9["add_contribution_by_year"].items():
        print(k, v)


if __name__ == "__main__":
    main()
