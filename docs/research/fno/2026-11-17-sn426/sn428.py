"""SN428: which decision makes the hindsight money (PLAN.md section 1, frozen at 123301ac; details fixed here before any
number). Hindsight diagnostics, never strategy P&L.

Panel: SN412's 42 sealed archive days (NIFTY recorded universe, one snapshot a minute, walked one-lot prices, lot 65,
entry cost <= Rs 15,000). Day labels: EXPIRY (the front expiry is that day), GOLD (a Gold trade that day in the 2023-26
replay), EMPTY (neither, to Oct 28), NO_REPLAY (later). Clocks 10:00 / 11:00 / 13:00 (minute index 45 / 105 / 225).
BASE: a seeded side (random.Random(f"sn428-{day}-{clock}")), the 1-ITM strike on the front expiry (ATM from the front
future's last price at the clock), entered at the clock's snapshot at the walked ask, exited at the walked bid 60
minutes later or at the first snapshot whose mark <= -Rs 3,000 (an expiring contract by 13:30).
One decision in hindsight at a time:
  SIDE       the better of CE / PE (1-ITM each), fixed exit
  CONTRACT   the best affordable contract of the seeded side over every recorded strike and both expiries, fixed exit
  EXIT       seeded side, 1-ITM, the best walked bid before the stop within 60 minutes
  TIMING     seeded side, 1-ITM at each minute's own ATM, the best entry minute within +-30 minutes, fixed 60-minute exit
  SIDE+EXIT  both
  CEILING    SN412's full-day ceiling with the stop (the capture denominator)
Per clock and stress (Rs 205 / 400): priced cells, mean, median, share >= Rs 750, mean capture of the ceiling; by label.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import sn412 as C  # noqa: E402  (qa pointed at the sealed export; walked(), charges())

qa = C.qa
OUT = HERE / "results-sn428.json"
CLOCKS = {"10:00": 45, "11:00": 105, "13:00": 225}
LOT, ROOM, STOP = 65, 15000.0, 3000.0


def contracts(q, d):
    return {k: v for k, v in q["opt"].items() if k[0] == "NIFTY" and k[1] >= d}


def trade(ask, bid, e, x_end, stress, best_exit):
    a = ask[e]
    if np.isnan(a) or a * LOT + C.charges(a, 0.0) > ROOM:
        return None
    best, last = None, None
    for x in range(e + 1, x_end + 1):
        b = bid[x]
        if np.isnan(b):
            continue
        n = (b - a) * LOT - C.charges(a, b) - stress
        last = n
        if n <= -STOP:
            return n if not best_exit else (max(best, n) if best is not None else n)
        if best_exit:
            best = n if best is None else max(best, n)
    return best if best_exit else last


def main():
    if OUT.exists():
        raise SystemExit("SN428 is run once")
    man = qa.manifest()
    days = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    gold_days = {x["day"] for x in json.loads(C.RUNS.read_text(encoding="utf-8"))["2023-2026 DEPLOYED @205"]["log"]}
    ceiling = {r["day"]: r for r in json.loads((HERE.parent / "2026-11-17-sn411" / "results-sn412.json").read_text(encoding="utf-8"))["rows"]}
    cells = []
    for d in days:
        q = qa.load(d)
        cons = contracts(q, d)
        exps = sorted({k[1] for k in cons})
        if not exps:
            continue
        front = exps[0]
        label = "EXPIRY" if front == d else "GOLD" if d in gold_days else ("EMPTY" if d <= "2026-10-28" else "NO_REPLAY")
        fut = qa.front_fut(q, "NIFTY")
        walked = {k: (C.walked(v, "ask"), C.walked(v, "bid")) for k, v in cons.items()}
        expiring = front == d

        def leg(side, e, expiry=front, depth=1):
            F = fut["ltp"][e] if fut is not None else np.nan
            if np.isnan(F):
                return None
            atm = int(round(F / 50.0) * 50)
            k = atm + (-depth * 50 if side == "CE" else depth * 50)
            return walked.get(("NIFTY", expiry, k, side))
        for c, e in CLOCKS.items():
            if expiring and e >= 255:
                continue
            coin = random.Random(f"sn428-{d}-{c}").choice(("CE", "PE"))
            row = {"day": d, "clock": c, "label": label, "coin": coin}
            for st in (205.0, 400.0):
                x_end = min(e + 60, 255 if expiring else 355)
                lg = leg(coin, e)
                base = None if lg is None else trade(lg[0], lg[1], e, x_end, st, False)
                sides = [trade(*leg(s, e), e, x_end, st, False) for s in ("CE", "PE") if leg(s, e) is not None]
                sides = [v for v in sides if v is not None]
                conts = []
                for (u, ex, k, typ), (a, b) in walked.items():
                    if typ != coin:
                        continue
                    xe = min(e + 60, 255 if ex == d else 355)
                    v = trade(a, b, e, xe, st, False)
                    if v is not None:
                        conts.append(v)
                ex_best = None if lg is None else trade(lg[0], lg[1], e, x_end, st, True)
                tim = []
                for e2 in range(max(1, e - 30), e + 31):
                    lg2 = leg(coin, e2)
                    if lg2 is None:
                        continue
                    v = trade(lg2[0], lg2[1], e2, min(e2 + 60, 255 if expiring else 355), st, False)
                    if v is not None:
                        tim.append(v)
                se = [trade(*leg(s, e), e, x_end, st, True) for s in ("CE", "PE") if leg(s, e) is not None]
                se = [v for v in se if v is not None]
                row[f"@{int(st)}"] = {"BASE": base, "SIDE": max(sides) if sides else None, "CONTRACT": max(conts) if conts else None,
                                      "EXIT": ex_best, "TIMING": max(tim) if tim else None, "SIDE+EXIT": max(se) if se else None,
                                      "CEILING": (ceiling.get(d) or {}).get(f"ceiling_stop@{int(st)}")}
            cells.append(row)
    res = {"days": len(days), "cells": len(cells), "labels": {lab: len({r["day"] for r in cells if r["label"] == lab}) for lab in ("EXPIRY", "GOLD", "EMPTY", "NO_REPLAY")}}
    arms = ("BASE", "SIDE", "CONTRACT", "EXIT", "TIMING", "SIDE+EXIT", "CEILING")
    for st in (205, 400):
        for c in list(CLOCKS) + ["all"]:
            rs = [r for r in cells if c == "all" or r["clock"] == c]
            blk = {}
            for a in arms:
                xs = [r[f"@{st}"][a] for r in rs if r[f"@{st}"][a] is not None]
                cap = [r[f"@{st}"][a] / r[f"@{st}"]["CEILING"] for r in rs if r[f"@{st}"][a] is not None and r[f"@{st}"]["CEILING"]]
                blk[a] = {"priced": len(xs), "unpriced": len(rs) - len(xs), "mean": round(float(np.mean(xs))) if xs else None,
                          "median": round(float(np.median(xs))) if xs else None, "share_ge_750": round(float(np.mean([x >= 750 for x in xs])), 3) if xs else None,
                          "share_ge_750_of_all_cells": round(sum(x >= 750 for x in xs) / len(rs), 3) if rs else None,
                          "mean_capture_of_ceiling": round(float(np.mean(cap)), 3) if cap else None}
            res[f"{c} @{st}"] = blk
        for lab in ("EXPIRY", "GOLD", "EMPTY"):
            rs = [r for r in cells if r["label"] == lab]
            res[f"label {lab} @{st}"] = {a: (round(float(np.mean([r[f"@{st}"][a] for r in rs if r[f"@{st}"][a] is not None]))) if any(r[f"@{st}"][a] is not None for r in rs) else None) for a in arms}
    res["cells_rows"] = cells
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    for k, v in res.items():
        if "@" in k and not k.startswith("label"):
            print(k, {a: (v[a]["mean"], v[a]["share_ge_750"], v[a]["mean_capture_of_ceiling"]) for a in arms})
    for k, v in res.items():
        if k.startswith("label"):
            print(k, v)


if __name__ == "__main__":
    main()
