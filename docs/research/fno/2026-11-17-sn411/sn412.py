"""SN412: how much of the wage the day physically offered - a hindsight ceiling (PLAN.md section 1, frozen at e5cc95b7;
details fixed here before any number). Never portfolio P&L.

Data: the real-quote archive's sealed days (export 20261116T103002Z, Sep 10 - Nov 13, 2026), NIFTY's recorded universe
(about 11 strikes x 2 weekly expiries x CE / PE, one snapshot a minute; qa.py's loader, hash-checked), lot 65.
One lot of one contract: entry at a usable minute 09:16 - 14:59 at the walked one-lot ask (ask x lot + entry charges <=
Rs 15,000), exit at a later usable minute up to 15:10 at the walked one-lot bid (a contract expiring that day: entry and
exit by 13:30). net = (bid - ask) x 65 - Zerodha charges - stress (Rs 205 / 400).
  ceiling (no stop)    max over contracts and entry < exit
  ceiling (stop)       the same, with the exit before the first minute whose mark (bid at that minute) is <= -Rs 3,000
Per day: both ceilings, the best contract (side, expiry rank, strike vs the front future at entry), entry / exit clocks,
>= Rs 750 or not; minutes without a usable quote are holes (counted).
Fixed clocks 09:30 / 10:00 / 11:00 / 12:00 / 13:00 / 14:00: the best affordable contract entered at that minute, exit
within 60 minutes before its stop: the share of day x clock cells reaching Rs 750, and the share where every contract's
best exit is a loss (abstaining was best). Denominators: observed days, and Gold-empty days (Gold's DEPLOYED replay log,
2023-26 path, Rs 205; Sep 10 - Oct 28 only; later days have no Gold replay and are reported apart).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
sys.path.insert(0, str(FNO / "2026-11-14-sn201"))
import qa  # noqa: E402
import wk  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
qa.LOCAL = HERE / "_local" / "qa"
OUT = HERE / "results-sn412.json"
RUNS = FNO / "2026-11-17-sn396" / "_local" / "sn403-runs.json"
LOT, ROOM, STOP = 65, 15000.0, 3000.0
E_LO, E_HI, X_HI, EXP_HI = 1, 344, 355, 255
CLOCKS = {"09:30": 15, "10:00": 45, "11:00": 105, "12:00": 165, "13:00": 225, "14:00": 285}


def charges(b, s):
    return wk.charges(b, s, LOT, "NFO")


def walked(rec, side):
    n = qa.NM
    out = np.full(n, np.nan)
    for i in range(n):
        if not rec["usable"][i]:
            continue
        p, q = (rec["askp"][:, i], rec["askq"][:, i]) if side == "ask" else (rec["bidp"][:, i], rec["bidq"][:, i])
        w = qa.walk_cost(p, q, LOT)
        if w is not None:
            out[i] = w
    return out


def best_from(ask, bid, e, x_hi, stress, stop):
    """Best net exiting in (e, x_hi] from an entry at minute e; with stop, only before the first mark <= -STOP."""
    a = ask[e]
    seg = bid[e + 1: x_hi + 1]
    if not len(seg) or np.all(np.isnan(seg)):
        return None, None
    if stop:
        fee = charges(a, a) + stress
        marks = (seg - a) * LOT - fee
        hit = np.flatnonzero(np.nan_to_num(marks, nan=1e9) <= -STOP)
        if len(hit):
            seg = seg[: hit[0]]
            if not len(seg) or np.all(np.isnan(seg)):
                return None, None
    k = int(np.nanargmax(seg))
    b = float(seg[k])
    return (b - a) * LOT - charges(a, b) - stress, e + 1 + k


def main():
    if OUT.exists():
        raise SystemExit("SN412 is run once")
    man = qa.manifest()
    days = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    log = json.loads(RUNS.read_text(encoding="utf-8"))["2023-2026 DEPLOYED @205"]["log"]
    gold_days = {x["day"] for x in log}
    rows, cells = [], []
    for d in days:
        q = qa.load(d)
        fut = qa.front_fut(q, "NIFTY")
        cons = {k: v for k, v in q["opt"].items() if k[0] == "NIFTY" and k[1] >= d}
        exps = sorted({k[1] for k in cons})
        holes = 0
        best = {(st, sp): (None, None) for st in (205.0, 400.0) for sp in (False, True)}
        clock_best = {(c, st): None for c in CLOCKS for st in (205.0, 400.0)}
        for (_u, e_, k, typ), rec in cons.items():
            ask, bid = walked(rec, "ask"), walked(rec, "bid")
            holes += int(np.isnan(ask[E_LO:X_HI + 1]).sum())
            expiring = e_ == d
            e_hi, x_hi = (EXP_HI, EXP_HI) if expiring else (E_HI, X_HI)
            for e in range(E_LO, e_hi):
                a = ask[e]
                if np.isnan(a) or a * LOT + charges(a, 0.0) > ROOM:
                    continue
                for st in (205.0, 400.0):
                    for sp in (False, True):
                        net, x = best_from(ask, bid, e, x_hi, st, sp)
                        if net is not None and (best[(st, sp)][0] is None or net > best[(st, sp)][0]):
                            F = float(fut["ltp"][e]) if fut is not None and not np.isnan(fut["ltp"][e]) else None
                            best[(st, sp)] = (net, {"side": typ, "expiry_rank": exps.index(e_), "strike_minus_future": None if F is None else round(k - F, 1),
                                                    "entry_min": e, "exit_min": x, "ask": round(float(a), 2)})
            for c, e in CLOCKS.items():
                if e >= e_hi or np.isnan(ask[e]) or ask[e] * LOT + charges(ask[e], 0.0) > ROOM:
                    continue
                for st in (205.0, 400.0):
                    net, _x = best_from(ask, bid, e, min(x_hi, e + 60), st, True)
                    if net is not None and (clock_best[(c, st)] is None or net > clock_best[(c, st)]):
                        clock_best[(c, st)] = net
        g = "GOLD" if d in gold_days else ("EMPTY" if d <= "2026-10-28" else "NO_REPLAY")
        r = {"day": d, "gold": g, "contracts": len(cons), "holes": holes}
        for (st, sp), (net, info) in best.items():
            r[f"ceiling{'_stop' if sp else ''}@{int(st)}"] = None if net is None else round(net)
            if sp and st == 205.0:
                r["best_stop@205"] = info
        rows.append(r)
        for (c, st), net in clock_best.items():
            cells.append({"day": d, "gold": g, "clock": c, "stress": int(st), "best": net})
        print(d, g, r["ceiling@205"], r["ceiling_stop@205"], flush=True)

    def block(rs):
        out = {"days": len(rs)}
        for k in ("ceiling@205", "ceiling_stop@205", "ceiling@400", "ceiling_stop@400"):
            xs = [r[k] for r in rs if r[k] is not None]
            out[k] = {"median": round(float(np.median(xs))) if xs else None, "mean": round(float(np.mean(xs))) if xs else None,
                      "share_ge_750": round(float(np.mean([x >= 750 for x in xs])), 3) if xs else None,
                      "share_ge_1648": round(float(np.mean([x >= 1648 for x in xs])), 3) if xs else None}
        return out
    res = {"days": len(rows), "all": block(rows), "gold_empty": block([r for r in rows if r["gold"] == "EMPTY"]),
           "gold_days": block([r for r in rows if r["gold"] == "GOLD"]), "no_replay": block([r for r in rows if r["gold"] == "NO_REPLAY"])}
    for st in (205, 400):
        for c in CLOCKS:
            xs = [x["best"] for x in cells if x["clock"] == c and x["stress"] == st]
            ok = [v for v in xs if v is not None]
            res[f"clock {c} @{st}"] = {"cells": len(xs), "affordable": len(ok), "share_ge_750": round(float(np.mean([v >= 750 for v in ok])), 3) if ok else None,
                                       "share_best_is_loss": round(float(np.mean([v < 0 for v in ok])), 3) if ok else None,
                                       "median_best": round(float(np.median(ok))) if ok else None}
    res["best_contract_side_stop@205"] = {s: sum(1 for r in rows if (r.get("best_stop@205") or {}).get("side") == s) for s in ("CE", "PE")}
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
