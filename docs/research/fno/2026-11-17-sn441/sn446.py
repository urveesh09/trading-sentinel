"""SN446: an affordable strike under the full-loss bound (PLAN.md section 1, frozen at f56f5807; details fixed here before
any number). A policy comparison for the owner, kept apart from the ordinary stop-based book.

Gold v5 at Rs 30k, growth as deployed, no adds (in_atr None) in every arm. At each signal (common.gold_one's own sizing):
  NORMAL   Gold's strike as gold_one picks it (the ITM cascade, then L.affordable's one step out)
  SIGNAL   the signal's own strike (sg["strike"], the engine's ATM-like choice)
  OTM1     one step further out of the money than SIGNAL
Full-loss fit for a candidate at its model ask a (M.ask_of of the decision minute's close): the largest n <= Gold's lots with
  n x a x lot + M.charges(a, a, n x lot) + stress x n <= room,  room = the day room gold_one is given (loss + realized)
(the whole debit, the entry and a closing order's charges at the entry price, and the stress, all inside the room).
Arms:
  BOUND-NORMAL      SN434's BOUND exactly (sn434.bounded_walk: floor((room - buy fees) / (ask x lot)), Gold's strike) - parity
  BOUND-LADDER      NORMAL, then SIGNAL, then OTM1: the first (highest delta) where >= 1 lot fits; else skipped
  BOUND-LADDER-1    the same with one lot
  BOUND-SIGNAL      SIGNAL only;  BOUND-OTM1  OTM1 only
Paths 2022 and 2023-26, Rs 205 / 400. Reported: net, trades, skipped, the strike class used, mean net per lot by class,
worst month / day, refills, and the largest debit at risk (<= room by construction).
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
sys.path.insert(0, str(FNO / "2026-11-17-sn426"))
import gold  # noqa: E402
import sn434  # noqa: E402

OUT = HERE / "results-sn446.json"
gw = gold.T.Q.gw
Lb, Cm = gold.L, gold.C
M = Lb.M
STATE = {"mode": None, "one": False, "picks": [], "skipped": 0}


def fit(a, lots, room):
    n = lots
    while n >= 1 and n * a * M.LOT + M.charges(a, a, n * M.LOT) + Lb.STRESS * n > room:
        n -= 1
    return n


def bound_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    i = sg["i"]
    lots = Lb.size(S, sg, v, full_lots, ctx, vol_day)
    step = M.STEP if sg["opt"] == "CE" else -M.STEP
    # Gold's NORMAL strike, as common.gold_one picks it
    strike = sg["strike"]
    per_lot = wallet / max(1, lots)
    casc = 1 if per_lot < v["itm_auto"][0] else (2 if per_lot < v["itm_auto"][1] else 3)
    for dep in range(casc, 0, -1):
        k_itm = sg["strike"] - dep * step
        r_itm = Lb.quote(S, k_itm, sg["opt"], i)
        if r_itm is not None and M.ask_of(float(r_itm[0][3][i])) * M.LOT * lots <= wallet * v.get("itm_share", 1.0):
            strike = k_itm
            break
    got = Lb.affordable(S, i, strike, sg["opt"], wallet)
    normal = got[2] if got is not None else None
    order = {"LADDER": [("NORMAL", normal), ("SIGNAL", sg["strike"]), ("OTM1", sg["strike"] + step)],
             "SIGNAL": [("SIGNAL", sg["strike"])], "OTM1": [("OTM1", sg["strike"] + step)]}[STATE["mode"]]
    room = loss + realized
    cap = 1 if STATE["one"] else lots
    seen = set()
    for cls, k in order:
        if k is None or k in seen:
            continue
        seen.add(k)
        rec = Lb.quote(S, k, sg["opt"], i)
        if rec is None:
            continue
        a = M.ask_of(float(rec[0][3][i]))
        n = fit(a, min(cap, max(1, int(wallet // (a * M.LOT)))), room)
        if n < 1:
            continue
        d = 1 if sg["opt"] == "CE" else -1
        net, j, px = Lb.walk(S, rec, a, n, i, min(max(sg["j"], i + 1), M.EXIT_MIN), d, v, room, wallet)
        net += Lb.side_legs(S, i, j, d, k, v)
        STATE["picks"].append({"day": S.day, "i": i, "class": cls, "lots": n, "ask": a, "net": net,
                               "debit": n * a * M.LOT + M.charges(a, 0.0, n * M.LOT), "room": room})
        return net, j, n, a, px, k
    STATE["skipped"] += 1
    return None


def main():
    if OUT.exists():
        raise SystemExit("SN446 is run once")
    gold.install()
    orig_one, orig_walk = gw._ORIG["gold_one"], gold.L.walk
    sn434._walk = orig_walk
    res = {}
    for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
        for st in (205.0, 400.0):
            for arm in ("BOUND-NORMAL", "BOUND-LADDER", "BOUND-LADDER-1", "BOUND-SIGNAL", "BOUND-OTM1"):
                STATE.update(picks=[], skipped=0, one=arm == "BOUND-LADDER-1",
                             mode={"BOUND-LADDER": "LADDER", "BOUND-LADDER-1": "LADDER", "BOUND-SIGNAL": "SIGNAL", "BOUND-OTM1": "OTM1"}.get(arm))
                sn434.STATE.update(on=arm == "BOUND-NORMAL", skipped=[], cut=0)
                if arm == "BOUND-NORMAL":
                    gold.L.walk = sn434.bounded_walk
                else:
                    gw._ORIG["gold_one"] = bound_one
                try:
                    days, log, _ = gold.run(years, gold.DEPLOYED, st, in_atr=None)
                finally:
                    gw._ORIG["gold_one"] = orig_one
                    gold.L.walk = orig_walk
                    sn434.STATE["on"] = False
                s = gold.summary(days, log)
                if arm == "BOUND-NORMAL":
                    s["skipped"] = len(sn434.STATE["skipped"])
                    s["lots_cut"] = sn434.STATE["cut"]
                else:
                    pk = STATE["picks"]
                    s["skipped"] = STATE["skipped"]
                    s["class_used"] = dict(collections.Counter(x["class"] for x in pk))
                    s["per_lot_by_class"] = {c: round(sum(x["net"] for x in pk if x["class"] == c) / max(1, sum(x["lots"] for x in pk if x["class"] == c)))
                                             for c in ("NORMAL", "SIGNAL", "OTM1") if any(x["class"] == c for x in pk)}
                    s["largest_debit"] = round(max((x["debit"] for x in pk), default=0.0))
                    s["max_debit_over_room"] = round(max((x["debit"] / x["room"] for x in pk), default=0.0), 3)
                    s["mean_lots"] = round(sum(x["lots"] for x in pk) / max(1, len(pk)), 2)
                res[f"{arm} | {p} @{int(st)}"] = s
                print(arm, p, int(st), s["net"], s["trades"], s.get("skipped"), s.get("class_used"), s.get("per_lot_by_class"), s["worst_month"], flush=True)
    ref = json.loads((FNO / "2026-11-17-sn426" / "results-sn434.json").read_text(encoding="utf-8"))
    res["parity_vs_sn434"] = {k: [res[f"BOUND-NORMAL | {k}"]["net"], ref[f"BOUND | {k}"]["net"]] for k in ("2022 @205", "2022 @400", "2023-2026 @205", "2023-2026 @400")}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
