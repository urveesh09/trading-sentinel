"""SN227 - robust selection (PLAN.md, frozen rule) over every structure x k x exit x hedge x filter on the four seen samples.
score_s = net_s / weekly expiries in s (per option lot). Eligible: E1 net > 0 on all four; E2 DEV years positive >= 4 of 5;
E3 DEV worst month >= -34,163; E4 trades in >= 50% of DEV weeks; E5 winged: >= 80% of DEV weeks unclamped.
PICK = eligible with the largest min score (ties: larger summed net); RUNNERS = the next two; PLATEAU = the per-week
average of all eligible variants. Random-skip null (500 draws) for a filtered pick: it must beat the 95th percentile of
its unfiltered base's min score at the same skip counts, or the unfiltered base replaces it. Writes the frozen picks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import wk3  # noqa: E402

S = wk3.SEEN
E3 = -34163


def ms(r):
    return min(r[n]["per_week"] for n in S)


def eligible(v, r):
    why = []
    if not all(r[n]["net"] > 0 for n in S):
        why.append("E1")
    if r["DEV"]["years_positive"] < 4:
        why.append("E2")
    if r["DEV"]["worst_month"] < E3:
        why.append("E3")
    if r["DEV"]["trades"] < 0.5 * wk3.sample("DEV").W:
        why.append("E4")
    if v[0] in ("IC 0.5/1.5", "IF 2.0") and (r["DEV"]["trades"] == 0 or 1 - r["DEV"]["clamped"] / r["DEV"]["trades"] < 0.8):
        why.append("E5")
    return why


def null(v, draws=500, seed=227):
    base = v[:4] + ("none",)
    rng = np.random.default_rng(seed)
    full = {n: grid.rows(n, base) for n in S}
    kept = {n: len(grid.rows(n, v)) for n in S}
    L = grid.lots_of(v)
    out = []
    for _ in range(draws):
        sc = []
        for n in S:
            r = full[n]
            idx = rng.choice(len(r), size=kept[n], replace=False) if kept[n] < len(r) else np.arange(len(r))
            sc.append(float(sum(r[i][3] for i in idx)) / L / wk3.sample(n).W)
        out.append(min(sc))
    return round(float(np.percentile(out, 95)), 1)


def week_ledger(v):
    """{(sample, expiry): net per lot} for the plateau."""
    L = grid.lots_of(v)
    return {(n, r[1]): r[3] / L for n in S for r in grid.rows(n, v)}


if __name__ == "__main__":
    out_path = HERE / "results-sn227.json"
    if out_path.exists():
        raise SystemExit("SN227 is run once")
    T = grid.table()
    order = sorted(T, key=lambda v: (-ms(T[v]), -sum(T[v][n]["net"] for n in S), wk3.vname(v)))
    elig = [v for v in order if not eligible(v, T[v])]
    fails = {}
    for v in T:
        for w in eligible(v, T[v]):
            fails[w] = fails.get(w, 0) + 1
    res = {"variants": len(T), "positive_on_all_four": sum(all(T[v][n]["net"] > 0 for n in S) for v in T),
           "eligible": len(elig), "fail_counts": fails, "eligible_list": [wk3.vname(v) for v in elig]}
    print("SN227", json.dumps({k: res[k] for k in ("variants", "positive_on_all_four", "eligible", "fail_counts")}), flush=True)
    picks = {}
    if elig:
        chosen = []
        for v in elig:
            if len(chosen) == 3:
                break
            if any(wk3.vname(v) == wk3.vname(c) for c in chosen):
                continue
            item = {"variant": list(v), "name": wk3.vname(v), "min_score": ms(T[v]), "rows": T[v]}
            if v[4] != "none":
                p95 = null(v)
                item["null_min_score_p95"] = p95
                if ms(T[v]) <= p95:
                    b = v[:4] + ("none",)
                    item["replaced_by_unfiltered_base"] = {"variant": list(b), "name": wk3.vname(b), "min_score": ms(T[b]),
                                                           "eligible_failures": eligible(b, T[b]), "rows": T[b]}
            chosen.append(v)
            picks["PICK" if not picks else f"RUNNER {len(picks)}"] = item
        led = [week_ledger(v) for v in elig]
        plateau = {}
        for n in S:
            ws = [e for e, _d in wk3.sample(n).weeks]
            tot = sum(sum(l.get((n, e), 0.0) for l in led) / len(led) for e in ws)
            plateau[n] = {"net": round(tot), "per_week": round(tot / len(ws), 1)}
        res["plateau"] = {"members": len(elig), "by_sample": plateau}
    else:
        v = order[0]
        picks["LEAST BAD"] = {"variant": list(v), "name": wk3.vname(v), "min_score": ms(T[v]), "rows": T[v], "eligible_failures": eligible(v, T[v])}
    refs = {"WK-S": ("STRANGLE 0.5", 3, "settle stop1", "none", "none"), "WK-G": ("STRANGLE 0.5", 3, "gate stop1", "none", "none"),
            "k1 ATM straddle": ("STRADDLE", 1, "settle", "none", "none")}
    hedged_wks = max((("STRANGLE 0.5", 3, "settle stop1", h, "none") for h in ("H1", "H15", "H15x2")), key=lambda v: ms(T[v]))
    refs["best hedged WK-S"] = hedged_wks
    res["references"] = {k: {"variant": list(v), "name": wk3.vname(v), "min_score": ms(T[v]), "rows": T[v]} for k, v in refs.items()}
    res["references"]["breach 0.5 + gate"] = {"engine": "wk2", "base": "WK-S", "rule": {"breach": 0.5, "gate": -0.25}}
    res["picks"] = picks
    for k, it in picks.items():
        print("SN227", k, it["name"], "min/wk", it["min_score"], json.dumps({n: (it["rows"][n]["net"], it["rows"][n]["trades"], it["rows"][n]["worst_month"]) for n in S}),
              "null p95", it.get("null_min_score_p95"), "REPLACED" if "replaced_by_unfiltered_base" in it else "", flush=True)
        if "replaced_by_unfiltered_base" in it:
            b = it["replaced_by_unfiltered_base"]
            print("SN227   ->", b["name"], "min/wk", b["min_score"], "fails", b["eligible_failures"], flush=True)
    if "plateau" in res:
        print("SN227 PLATEAU", json.dumps(res["plateau"]), flush=True)
    for k, it in res["references"].items():
        if "rows" in it:
            print("SN227 ref", k, it["name"], "min/wk", it["min_score"], flush=True)
    unf = [v for v in elig if v[4] == "none"]                     # post-run addition (disclosed): information only
    res["best_eligible_unfiltered (information, not the frozen PICK)"] = ({"variant": list(unf[0]), "name": wk3.vname(unf[0]),
                                                                         "min_score": ms(T[unf[0]]), "rows": T[unf[0]]} if unf else None)
    res["eligible_rows"] = {wk3.vname(v): {"min_score": ms(T[v]), "nets": {n: T[v][n]["net"] for n in S}} for v in elig}
    print("SN227 best eligible unfiltered:", res["best_eligible_unfiltered (information, not the frozen PICK)"] and
          (res["best_eligible_unfiltered (information, not the frozen PICK)"]["name"], ms(T[unf[0]])), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")  # post-run fix: numpy ints
