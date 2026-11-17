"""SN439 follow-up (disclosed, Nov 17, after SN439's numbers: 82 of 106 losing Gold trades were above entry first):
a breakeven lock on Gold's own trades. Learning only; no Gold change follows.

Rule LOCK-L: once Gold's chosen option closes a minute at or above entry x (1 + L), the trade's stop moves to the entry
price; if a later minute's low reaches it before Gold's own exit, the trade exits there at the entry price (net = minus
round-trip costs and stress). L = 10 / 20 / 30%. Implemented around gw.walk on Gold's own option record (bar closes for
the trigger, bar lows for the touch). Approximation (disclosed): trades that added lots before the touch keep Gold's own
result (the lock is applied to single-piece trades only). The day's later trades see the changed realized net (one path).
Paths 2022 and 2023-26, Rs 205 / 400; reported net, worst month, trades locked, losers turned to scratches, winners cut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn439b.json"
gw = gold.T.Q.gw
_walk = None
STATE = {"L": None, "locked": [], "ref": {}}


def lock_walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet):
    net, j, px = _walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet)
    L_ = STATE["L"]
    if L_ is None:
        return net, j, px
    log = gw.LOG[-1] if gw.LOG else {}
    if any(isinstance(a, dict) and a.get("added") for a in log.get("adds", [])):
        return net, j, px
    a, bo, bh, bl, bc, bm, tr = rec
    trig = None
    for k in range(i + 1, j + 1):
        b = bc[k] if tr[k] else bm[k]
        if not np.isnan(b) and b >= ask * (1 + L_):
            trig = k
            break
    if trig is None:
        return net, j, px
    for k in range(trig + 1, j + 1):
        if tr[k] and bl[k] <= ask:
            qty = lots * gw.M.LOT
            new = -gold.L.cost(ask, ask, qty, lots)
            STATE["locked"].append({"day": S.day, "i": i, "old": float(net), "new": float(new)})
            log.update(net=new, j=k, px=float(ask), reason="lock")
            return new, k, float(ask)
    return net, j, px


def main():
    global _walk
    if OUT.exists():
        raise SystemExit("SN439b is run once")
    gold.install()
    _walk = gold.L.walk
    gold.L.walk = lock_walk
    res = {}
    try:
        for L_ in (None, 0.10, 0.20, 0.30):
            for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
                for st in (205.0, 400.0):
                    STATE.update(L=L_, locked=[])
                    days, log, _ = gold.run(years, gold.DEPLOYED, st)
                    s = gold.summary(days, log)
                    lk = STATE["locked"]
                    s.update(locked=len(lk), losers_scratched=sum(1 for x in lk if x["old"] < 0), loss_avoided=round(sum(x["new"] - x["old"] for x in lk if x["old"] < 0)),
                             winners_cut=sum(1 for x in lk if x["old"] > 0), winner_give_up=round(sum(x["old"] - x["new"] for x in lk if x["old"] > 0)))
                    name = "BASE" if L_ is None else f"LOCK-{int(L_ * 100)}%"
                    res[f"{name} | {p} @{int(st)}"] = s
                    print(name, p, int(st), s["net"], s["worst_month"], s["locked"], s["loss_avoided"], s["winner_give_up"], flush=True)
    finally:
        gold.L.walk = _walk
    assert res["BASE | 2023-2026 @205"]["net"] in (850882, 850883)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
