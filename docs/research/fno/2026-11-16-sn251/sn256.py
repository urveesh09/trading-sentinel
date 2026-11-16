"""SN256 - weekend and holiday long volatility (PLAN.md). SN224: sellers lose over weekend intervals on every sample;
a buyer may get the weekend's moves without paying the weekend's decay. On the last session before a weekend or holiday
(the next trading day is more than one calendar day later and is an SN session of the same weekly contract), buy the ATM
straddle or the 0.25-straddle strangle at 15:15 or 15:25 and sell it on the next session at 09:20, 09:45 or 15:10.
12 variants (the plan's 10:15 exit is dropped to keep the 12-variant cap; decided before any score). Rs 3,000 stop from
the entry minute; Rs 100 per lot per leg if it closes before 09:20. Null ("day"): the same trade entered on as many
random sessions that have a next session of the same contract (any night)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402


def gap_days(smp, d):
    nd = LG.next_session(smp, d)
    return None if nd is None else (dt.date.fromisoformat(nd) - dt.date.fromisoformat(d)).days


def make(width, i_entry, i_exit):
    def signal(smp, d):
        g = gap_days(smp, d)
        return True if (g is not None and g > 1) else None

    def trade(smp, d, side, stress=gl.STRESS, late=0):
        nd = LG.next_session(smp, d)
        if nd is None:
            return None
        lg = LG.straddle(smp, smp.s[d], i_entry, width)
        return LG.held(smp, d, lg, i_entry, [(d, gl.NM - 1), (nd, i_exit)], stress=stress, late=late)

    nm = f"{'straddle' if not width else 'strangle 0.25'} in {i_entry} out next {i_exit}"
    return {"name": nm, "signal": signal, "trade": trade, "null": "day", "eligible": lambda smp, d: gap_days(smp, d) is not None}


VARIANTS = [make(w, ie, ix) for w in (0.0, 0.25) for ie in (gl.I["15:15"], gl.I["15:25"]) for ix in (gl.I["09:20"], gl.I["09:45"], gl.I["15:10"])]

if __name__ == "__main__":
    out = HERE / "results-sn256.json"
    res = slot.evaluate("SN256", VARIANTS)
    slot.save(out, res)
