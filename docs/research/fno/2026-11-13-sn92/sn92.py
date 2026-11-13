"""SN92 - where the money goes (description, no pass/fail; PLAN.md).
1. Gold v5's trades at A (Rs 15k) and C (Rs 30k): by setup x book x side x year, with costs split into spread,
   charges and stress, and what the extension and scale-ins added.
2. The empty-day opportunity map: ATM call / put / straddle bought at 09:45, 10:30, 12:00, 13:30 and sold after
   15 / 30 / 60 / 120 minutes or at 15:10, on causal Gold-free days (split by the Gold-empty attribution label) and on
   ADX >= 30 days. The hindsight best side is a ceiling, never a strategy."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

M = C.M


def gold_trades():
    C.RECORD[0] = True
    C.TRADES.clear()
    r = C.run(C.V5, wallets=(C.STD_WALLETS[0], C.STD_WALLETS[2]))
    C.RECORD[0] = False
    return r, list(C.TRADES)


def decompose(trades, Ys):
    rows = []
    for t in trades:
        S = Ys[t["day"][:4]].sessions[t["day"]]
        rec = S.option(t["strike"], t["opt"])
        d = 1 if t["opt"] == "CE" else -1
        qty = t["lots"] * M.LOT
        mid_i = float(rec[0][3][t["i"]])
        spread = (t["ask"] - mid_i + M.spread_for(t["px"]) / 2) * qty
        charges = M.charges(t["ask"], t["px"], qty)
        stress = C.L.STRESS * t["lots"]
        simple = (t["px"] - t["ask"]) * qty - charges - stress
        jn = min(max(t["j_n11"], t["i"] + 1), M.EXIT_MIN)
        bn = rec[4][jn] if rec[6][jn] else rec[5][jn]
        at_n11 = (float(bn) - t["ask"]) * qty - M.charges(t["ask"], float(bn), qty) - stress if not np.isnan(bn) else simple
        rows.append({**t, "year": t["day"][:4], "spread": spread, "charges": charges, "stress": stress,
                     "gross_bidask": (t["px"] - t["ask"]) * qty, "scale_in_effect": t["net"] - simple,
                     "extended": t["j"] > jn, "ext_effect": (simple - at_n11) if t["j"] > jn else 0.0,
                     "index_pts": float((S.F["c"][t["j"]] - S.F["c"][t["i"]]) * d),
                     "gold_free_day": C.gold_free(t["day"])})
    return rows


def group(rows, keys):
    g = collections.defaultdict(list)
    for r in rows:
        g[tuple(r[k] for k in keys)].append(r)
    out = {}
    for k, rs in sorted(g.items()):
        nets = sorted((r["net"] for r in rs), reverse=True)
        lots = sum(r["lots"] for r in rs)
        out["|".join(map(str, k))] = {
            "trades": len(rs), "net": round(sum(nets)), "net_per_lot": round(sum(nets) / max(1, lots)),
            "win_pct": round(100 * np.mean([n > 0 for n in nets]), 1), "best5": round(sum(nets[:5])),
            "spread": round(sum(r["spread"] for r in rs)), "charges": round(sum(r["charges"] for r in rs)),
            "stress": round(sum(r["stress"] for r in rs)), "scale_in": round(sum(r["scale_in_effect"] for r in rs)),
            "extension": round(sum(r["ext_effect"] for r in rs)), "extended_trades": sum(r["extended"] for r in rs),
            "mean_index_pts": round(float(np.mean([r["index_pts"] for r in rs])), 1)}
    return out


CLOCKS = {"09:45": 30, "10:30": 75, "12:00": 165, "13:30": 255}
HORIZONS = (15, 30, 60, 120, "15:10")


def leg_net(S, strike, opt, i, j):
    rec = S.option(strike, opt)
    if rec is None or not rec[6][i]:
        return None
    ask = M.ask_of(float(rec[0][3][i]))
    bid = rec[4][j] if rec[6][j] else rec[5][j]
    if np.isnan(bid):
        return None
    bid = float(bid)
    return (bid - ask) * M.LOT - M.charges(ask, bid, M.LOT) - 205.0, ask, float(rec[4][i])


def opportunity_map(Ys):
    labels = {r["day"]: r for r in json.loads((C.FNO / "2026-11-13-sn76" / "_local" / "days.json").read_text(encoding="utf-8"))}
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for y in C.YEARS:
        for S in Ys[y].ordered():
            lab = labels.get(S.day)
            if lab is None:
                continue
            if C.gold_free(S.day):
                grp = "gold-free, Gold-empty" if not lab["trades"] else "gold-free, Gold traded"
            elif C.adx(S.day) is not None:
                grp = "ADX >= 30"
            else:
                continue
            c = S.F["c"]
            for cn, i in CLOCKS.items():
                K = int(round(c[i] / M.STEP) * M.STEP)
                for h in HORIZONS:
                    j = C.FLAT if h == "15:10" else min(i + h, C.FLAT)
                    a, b = leg_net(S, K, "CE", i, j), leg_net(S, K, "PE", i, j)
                    if a is None or b is None:
                        continue
                    hurdle = ((a[1] - a[2]) + (M.charges(a[1], a[1], M.LOT) + 205.0) / M.LOT) / 0.5
                    acc[(grp, cn)][h].append((a[0], b[0], abs(float(c[j] - c[i])), hurdle))
    out = {}
    for (grp, cn), byh in sorted(acc.items()):
        for h, xs in byh.items():
            arr = np.array(xs)
            best = np.maximum(arr[:, 0], arr[:, 1])
            out[f"{grp} | {cn} | {h}"] = {
                "n": len(arr), "call": round(float(arr[:, 0].mean())), "put": round(float(arr[:, 1].mean())),
                "straddle": round(float((arr[:, 0] + arr[:, 1]).mean())), "best_side_ceiling": round(float(best.mean())),
                "share_best_side_pays": round(float((best > 0).mean()), 3),
                "share_straddle_pays": round(float((arr[:, 0] + arr[:, 1] > 0).mean()), 3),
                "mean_abs_index_move": round(float(arr[:, 2].mean()), 1), "hurdle_pts": round(float(arr[:, 3].mean()), 1)}
    return out


if __name__ == "__main__":
    Ys = C.years()
    r, trades = gold_trades()
    tot = C.totals(r)
    assert tot["A 15k 1 lot"] == C.V5_TOTALS["A 15k 1 lot"] and tot["C 30k sized"] == C.V5_TOTALS["C 30k sized"], tot
    rows = decompose(trades, Ys)
    res = {}
    for wname, W in (("A", 15000.0), ("C", 30000.0)):
        rw = [x for x in rows if x["wallet"] == W]
        res[wname] = {"by_setup": group(rw, ("expert",)), "by_setup_side": group(rw, ("expert", "opt")),
                      "by_book": group(rw, ("book",)), "by_setup_year": group(rw, ("expert", "year")),
                      "by_side_regime": group(rw, ("opt", "gold_free_day")), "all": group(rw, ("wallet",))}
        print(f"--- Gold v5 trades at {wname}")
        for k in ("all", "by_setup", "by_setup_side", "by_book", "by_side_regime"):
            for kk, vv in res[wname][k].items():
                print(f"  {k:14s} {kk:22s}", vv, flush=True)
    res["opportunity_map"] = opportunity_map(Ys)
    for k, v in res["opportunity_map"].items():
        if k.split(" | ")[2] in ("30", "60", "15:10"):
            print(f"{k:44s}", v, flush=True)
    (HERE / "results-sn92.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
