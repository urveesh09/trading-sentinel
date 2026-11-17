"""SN434: the opportunity cost of a hard loss bound (PLAN.md section 1, frozen at 123301ac; details fixed here before any
number). A policy comparison for the owner; no Gold change follows from this slot.

Arms (Gold v5 at Rs 30k, growth as deployed):
  DEPLOYED   as shipped (the 20% day room is a trigger: a stop, which can slip; adds allowed)
  NO_ADDS    scale-in off (in_atr None), to isolate the adds
  BOUND      scale-in off and, at entry, lots cut to floor((room - entry charges) / (ask x 65)) where room = the day room
             gw.walk is given (20% of the wallet + the day's realized net; one position at a time, so no other open
             debit); fewer than one lot -> the signal is skipped. Every admitted debit can be lost in full inside the room.
Paths 2022 and 2023-26, Rs 205 / 400. Reported: trades, skipped signals (by expert and by year), lots cut, net, worst
month, worst day, and the largest debit at risk (DEPLOYED: entry debit incl. adds; BOUND: <= room by construction).
"""
from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn434.json"
gw = gold.T.Q.gw
_walk = None
STATE = {"on": False, "skipped": [], "cut": 0}


def bounded_walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet):
    if not STATE["on"]:
        return _walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet)
    qty1 = gw.M.LOT
    fit = int(math.floor((room - gw.buy_fees(ask, qty1)) / (ask * qty1))) if ask > 0 else 0
    while fit >= 1 and fit * ask * qty1 + gw.buy_fees(ask, fit * qty1) > room:
        fit -= 1
    if fit < 1:
        sg = gw.CUR.get("sg") or {}
        STATE["skipped"].append({"day": S.day, "i": i, "expert": sg.get("expert"), "ask": float(ask), "room": float(room)})
        return 0.0, i, ask
    if fit < lots:
        STATE["cut"] += 1
        lots = fit
    return _walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet)


def main():
    global _walk
    if OUT.exists():
        raise SystemExit("SN434 is run once")
    gold.install()
    _walk = gold.L.walk
    gold.L.walk = bounded_walk
    res = {}
    for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
        for st in (205.0, 400.0):
            for arm, vx, on in (("DEPLOYED", {}, False), ("NO_ADDS", {"in_atr": None}, False), ("BOUND", {"in_atr": None}, True)):
                STATE.update(on=on, skipped=[], cut=0)
                days, log, _ = gold.run(years, gold.DEPLOYED, st, **vx)
                s = gold.summary(days, log)
                debits = []
                for x in log:
                    q = (x.get("lots0") or 1) * gw.M.LOT
                    debit = x["ask0"] * q + gw.buy_fees(x["ask0"], q)
                    adds = sum(a.get("added", 0) for a in x.get("adds", []) if isinstance(a, dict))
                    debits.append(debit + adds * x["ask0"] * gw.M.LOT)
                s.update(skipped=len(STATE["skipped"]), skipped_by_expert=dict(collections.Counter(z["expert"] for z in STATE["skipped"])),
                         skipped_by_year=dict(collections.Counter(z["day"][:4] for z in STATE["skipped"])), lots_cut=STATE["cut"],
                         largest_debit_at_risk=round(max(debits, default=0.0)), median_debit=round(sorted(debits)[len(debits) // 2]) if debits else 0)
                res[f"{arm} | {p} @{int(st)}"] = s
                print(arm, p, int(st), s["net"], s["trades"], s["skipped"], s["lots_cut"], s["worst_month"], s["largest_debit_at_risk"], flush=True)
    STATE["on"] = False
    gold.L.walk = _walk
    assert res["DEPLOYED | 2023-2026 @205"]["net"] in (850882, 850883)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
