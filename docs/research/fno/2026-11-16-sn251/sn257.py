"""SN257 - weekday overnight longs (PLAN.md). Entry 15:20 on a session whose next trading day is the next calendar day
and an SN session of the same weekly contract (not an expiry day); exit 09:20 or 09:45 on that session.
Positions: the ATM straddle (every night: no selection, G2 n/a); an ATM call and an ITM call (one strike in) every night
(null "side": a random call or put); the same two calls only after a down day (15:20 index below the previous close;
null "side"). 10 variants. Rs 3,000 stop from the entry minute; Rs 100 per lot per leg if it closes before 09:20.
Description (after the pick): the index's close-to-open drift on weekday nights per year, DEV and both exams."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402

IE = gl.I["15:20"]


def weeknight(smp, d):
    nd = LG.next_session(smp, d)
    if nd is None or (dt.date.fromisoformat(nd) - dt.date.fromisoformat(d)).days != 1:
        return None
    return nd


def down_day(smp, d):
    pb = smp.prev_bar(d)
    return pb is not None and float(smp.s[d]["index"][3][IE]) < pb[3]


def make(kind, i_exit, after_down=False):
    def signal(smp, d):
        if weeknight(smp, d) is None:
            return None
        if after_down and not down_day(smp, d):
            return None
        return True if kind == "straddle" else 1

    def trade(smp, d, side, stress=gl.STRESS, late=0):
        nd = weeknight(smp, d)
        if nd is None:
            return None
        s = smp.s[d]
        if kind == "straddle":
            lg = LG.straddle(smp, s, IE)
        else:
            lg = LG.side_legs(smp, s, IE, side, off=1 if kind == "itm" else 0)
        return LG.held(smp, d, lg, IE, [(d, gl.NM - 1), (nd, i_exit)], stress=stress, late=late)

    nm = f"{kind}{' after a down day' if after_down else ''} 15:20 -> next {i_exit}"
    return {"name": nm, "signal": signal, "trade": trade, "null": "none" if kind == "straddle" else "side",
            "eligible": lambda smp, d: weeknight(smp, d) is not None}


VARIANTS = ([make("straddle", ix) for ix in (gl.I["09:20"], gl.I["09:45"])] +
            [make(k, ix, ad) for k in ("atm", "itm") for ad in (False, True) for ix in (gl.I["09:20"], gl.I["09:45"])])


def drift(smp):
    by = {}
    for d in smp.cal:
        nd = smp.next_day(d)
        if nd is None or (dt.date.fromisoformat(nd) - dt.date.fromisoformat(d)).days != 1:
            continue
        r = smp.daily[nd][0] / smp.daily[d][3] - 1.0
        by.setdefault(d[:4], []).append(r)
    return {y: {"nights": len(v), "mean_pct": round(100 * float(np.mean(v)), 4), "t": round(float(np.mean(v) / (np.std(v) / np.sqrt(len(v)))), 2)}
            for y, v in sorted(by.items())}


if __name__ == "__main__":
    out = HERE / "results-sn257.json"
    res = slot.evaluate("SN257", VARIANTS)
    res["drift"] = {"DEV": drift(gl.sample("DEV"))}
    for n in ("EXAMN", "EXAMS"):
        gl.SEALED[n] = True
        res["drift"][n] = drift(gl.sample(n))
        gl.SEALED[n] = False
    print("SN257 drift", json.dumps(res["drift"]), flush=True)
    slot.save(out, res)
