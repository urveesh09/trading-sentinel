"""SN263 - confirmed gap-day afternoons (PLAN.md). On a low-ADX session (yesterday's daily ADX < 30: Gold can then only
take TPB puts, and only before 14:00, so from 14:00 the session is a certain gap day when Gold holds nothing), at 14:00:
(a) an ATM option on the side of the 13:00 -> 14:00 index move (null "side"); (b) the ATM straddle (null "day": the
straddle at 14:00 on as many random sessions of any ADX). Exit 15:10 or 15:25. Rs 3,000 stop. On the exams (no Gold),
every low-ADX session is used. 4 variants."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402

I14, I13 = gl.I["14:00"], gl.I["13:00"]


def low_adx(smp, d):
    a = smp.adx(d)
    return a is not None and a < 30


def make(play, out):
    def signal(smp, d):
        if not low_adx(smp, d):
            return None
        if play == "straddle":
            return True
        ix = smp.s[d]["index"][3]
        m = float(ix[I14]) - float(ix[I13])
        return 0 if m == 0 else (1 if m > 0 else -1)

    def trade(smp, d, side, stress=gl.STRESS, late=0):
        s = smp.s[d]
        lg = LG.straddle(smp, s, I14) if play == "straddle" else LG.side_legs(smp, s, I14, side)
        return LG.intraday(smp, d, lg, I14, out, stress=stress, late=late)

    return {"name": f"low ADX 14:00 {play} to {out}", "signal": signal, "trade": trade,
            "null": "day" if play == "straddle" else "side", "eligible": lambda smp, d: True}


VARIANTS = [make(p, o) for p in ("13:00-14:00 side", "straddle") for o in (gl.FLAT, gl.I["15:25"])]

if __name__ == "__main__":
    res = slot.evaluate("SN263", VARIANTS)
    slot.save(HERE / "results-sn263.json", res)
