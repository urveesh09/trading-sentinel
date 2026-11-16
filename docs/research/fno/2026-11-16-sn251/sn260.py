"""SN260 - big opening gaps, overnight shocks (PLAN.md). Gap = the 09:15 index open / the previous close - 1, at
|gap| >= 0.5% or >= 0.8%. Plays: (a) the ATM straddle 09:20 -> 15:10 (null "day"); (b) the gap's side 09:20 -> 11:00;
(c) the gap's side 09:20 -> 15:10; (d) the fade, the other side, 09:30 -> 15:10 (null "side" for b-d). Rs 3,000 stop.
8 variants."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402


def gap(smp, d):
    pb = smp.prev_bar(d)
    if pb is None:
        return None
    return float(smp.s[d]["index"][0][0]) / pb[3] - 1.0


def make(thr, play):
    def signal(smp, d):
        g = gap(smp, d)
        if g is None or abs(g) < thr:
            return None
        if play == "straddle":
            return True
        sd = 1 if g > 0 else -1
        return -sd if play == "fade" else sd

    def trade(smp, d, side, stress=gl.STRESS, late=0):
        s = smp.s[d]
        if play == "straddle":
            return LG.intraday(smp, d, LG.straddle(smp, s, gl.I["09:20"]), gl.I["09:20"], gl.FLAT, stress=stress, late=late)
        i = gl.I["09:30"] if play == "fade" else gl.I["09:20"]
        out = gl.I["11:00"] if play == "side to 11:00" else gl.FLAT
        return LG.intraday(smp, d, LG.side_legs(smp, s, i, side), i, out, stress=stress, late=late)

    return {"name": f"|gap| >= {thr * 100:.1f}%: {play}", "signal": signal, "trade": trade,
            "null": "day" if play == "straddle" else "side", "eligible": lambda smp, d: True}


VARIANTS = [make(t, p) for t in (0.005, 0.008) for p in ("straddle", "side to 11:00", "side to 15:10", "fade")]

if __name__ == "__main__":
    res = slot.evaluate("SN260", VARIANTS)
    slot.save(HERE / "results-sn260.json", res)
