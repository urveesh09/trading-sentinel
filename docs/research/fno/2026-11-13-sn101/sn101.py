"""SN101 - what SN95's straddle result is made of (PLAN.md): the 10:00 ledger, the 2 x 2 premium-ceiling x stop-room
attribution, R_today deciles, and a permutation test against non-signal days matched on days-to-expiry and premium."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402

C, M = pa.C, pa.M
CELLS = ((15000.0, 3000.0), (15000.0, 4000.0), (20000.0, 3000.0), (20000.0, 4000.0))


def ledger(adm):
    Ys = C.years()
    rows = []
    for y in C.YEARS:
        for S in Ys[y].ordered():
            got = pa.path(S, pa.I10)
            rt = C.r_today(S, pa.I10)
            key = (S.day, "10:00", "R_today", 0.2, "top")
            row = {"day": S.day, "year": y, "gold_free": C.gold_free(S.day), "r_today": rt, "flag": adm.get(key),
                   "dte": C.sessions_until(S.day, S.s["expiry"]), "priced": got is not None}
            if got is not None:
                asks, prem, vals = got
                c = S.F["c"]
                row.update({"premium": prem, "pure": pa.settle(vals, pa.I10)[0],
                            "mfe": float(np.nanmax(vals)) if np.any(~np.isnan(vals)) else None,
                            "disp": float(abs(c[pa.FLAT] - c[pa.I10])), "move_pts_vs_straddle": float(abs(c[pa.FLAT] - c[pa.I10]) / sum(asks))})
                for ceil, room in CELLS:
                    for ls in (205.0, 100.0):
                        v = vals if ls == 205.0 else pa.shift(vals, 205.0, ls)
                        net, j, why = pa.settle(v, pa.I10, room, fallback=-2 * ls)
                        row[f"{int(ceil)}/{int(room)}/{int(ls)}"] = net if prem <= ceil else None
                        if ls == 205.0:
                            row[f"exit {int(ceil)}/{int(room)}"] = why
            rows.append(row)
    return rows


def parity(rows, adm):
    """settle(path) must equal sn95.play for every SN95-L day (Rs 15k wallet, Rs 3k room, strict)."""
    Ys = C.years()
    n = 0
    for r in rows:
        if r["priced"] and r["flag"] and r["gold_free"]:
            S = Ys[r["year"]].sessions[r["day"]]
            got = pa.sn95.play(S, pa.I10, "buy", None, 1, 3000.0, 205.0, 15000.0)
            mine = r["15000/3000/205"]
            assert (got is None and mine is None) or abs(got[0] - mine) < 1e-6, (r["day"], got, mine)
            n += 1
    return n


def two_by_two(rows, sel):
    out = {}
    for ceil, room in CELLS:
        for ls in (205, 100):
            k = f"{int(ceil)}/{int(room)}/{ls}"
            out[k] = pa.year_table({r["day"]: (r[k] or 0.0) for r in rows if sel(r) and r["priced"]})
            out[k]["affordable"] = sum(1 for r in rows if sel(r) and r["priced"] and r[k] is not None)
    return out


def deciles(rows):
    xs = [r for r in rows if r["priced"] and r["r_today"] is not None]
    edges = np.quantile([r["r_today"] for r in xs], np.linspace(0, 1, 11))
    out = {}
    for d in range(10):
        g = [r for r in xs if edges[d] <= r["r_today"] <= edges[d + 1]]
        out[d + 1] = {"n": len(g), "mean_pure": round(float(np.mean([r["pure"] for r in g]))),
                      "mean_premium": round(float(np.mean([r["premium"] for r in g]))),
                      "mean_move_vs_straddle": round(float(np.mean([r["move_pts_vs_straddle"] for r in g])), 3),
                      "by_year": {y: round(float(np.mean([r["pure"] for r in g if r["year"] == y]))) if any(r["year"] == y for r in g) else None
                                  for y in C.YEARS}}
    top_beats = sum(1 for y in C.YEARS
                    if np.mean([r["pure"] for r in xs if r["year"] == y and r["r_today"] >= edges[8]]) >
                    np.mean([r["pure"] for r in xs if r["year"] == y and r["r_today"] < edges[5]]))
    return out, top_beats


def permutation(rows, gold_free_only, n=5000, seed=101):
    pop = [r for r in rows if r["priced"] and r["flag"] is not None and (r["gold_free"] or not gold_free_only)
           and r["15000/3000/205"] is not None]
    terc = np.quantile([r["premium"] for r in pop], [1 / 3, 2 / 3])
    cell = lambda r: (r["dte"], int(np.searchsorted(terc, r["premium"])))  # noqa: E731
    sig = [r for r in pop if r["flag"]]
    pool = collections.defaultdict(list)
    for r in pop:
        if not r["flag"]:
            pool[cell(r)].append(r["15000/3000/205"])
    by_dte = collections.defaultdict(list)
    for r in pop:
        if not r["flag"]:
            by_dte[r["dte"]].append(r["15000/3000/205"])
    rng = np.random.default_rng(seed)
    total = sum(r["15000/3000/205"] for r in sig)
    draws = []
    for _ in range(n):
        s = 0.0
        for r in sig:
            p = pool.get(cell(r)) or by_dte.get(r["dte"]) or [x for v in pool.values() for x in v]
            s += p[rng.integers(len(p))]
        draws.append(s)
    draws = np.array(draws)
    return {"signal_days": len(sig), "signal_total": round(total), "matched_mean": round(float(draws.mean())),
            "matched_95th": round(float(np.percentile(draws, 95))), "p_value": float((draws >= total).mean())}


if __name__ == "__main__":
    out_path = HERE / "results-sn101.json"
    if out_path.exists():
        raise SystemExit("SN101 is scored once")
    adm = pa.admission()
    rows = ledger(adm)
    print("parity with sn95.play on", parity(rows, adm), "SN95-L days", flush=True)
    res = {"cells_gold_free_signal": two_by_two(rows, lambda r: r["flag"] and r["gold_free"]),
           "cells_all_days_signal": two_by_two(rows, lambda r: bool(r["flag"]))}
    for name in ("cells_gold_free_signal", "cells_all_days_signal"):
        print(f"--- {name}")
        for k, v in res[name].items():
            print(f"   {k:16s} {[v[y]['net'] for y in C.YEARS]} total {v['total']:>8} without best 5 {v['without_best_5']:>8} trades "
                  f"{sum(v[y]['trades'] for y in C.YEARS)} affordable {v['affordable']}", flush=True)
    dec, top_beats = deciles(rows)
    res["deciles"], res["top2_beats_bottom5_years"] = dec, top_beats
    print("--- R_today deciles (pure hold, strict, all sessions)")
    for d, v in dec.items():
        print(f"   {d:2d}", v, flush=True)
    print("   top-2 deciles beat bottom-5 in", top_beats, "of 4 years")
    res["permutation_gold_free"] = permutation(rows, True)
    res["permutation_all_days"] = permutation(rows, False)
    print("PERMUTATION gold-free", res["permutation_gold_free"], flush=True)
    print("PERMUTATION all days", res["permutation_all_days"], flush=True)
    sig = [r for r in rows if r["flag"] and r["gold_free"] and r["priced"]]
    res["signal_days_expensive_share"] = {"over_15k": sum(r["premium"] > 15000 for r in sig), "n": len(sig),
                                          "over_15k_pure_mean": round(float(np.mean([r["pure"] for r in sig if r["premium"] > 15000] or [0]))),
                                          "under_15k_pure_mean": round(float(np.mean([r["pure"] for r in sig if r["premium"] <= 15000] or [0])))}
    res["exits_signal_15k_3k"] = collections.Counter(r.get("exit 15000/3000") for r in sig if r["premium"] <= 15000)
    print("signal days by premium", res["signal_days_expensive_share"], "exits", res["exits_signal_15k_3k"])
    res["DECISION_r_today_carries_information"] = res["permutation_gold_free"]["p_value"] < 0.05 and top_beats >= 3
    print("DECISION: R_today carries information:", res["DECISION_r_today_carries_information"], flush=True)
    res["ledger"] = rows
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
