"""SN258 - multi-session swing, fewer and bigger trades (PLAN.md). Signal read at 15:15: (i) the 15:15 index beyond the
prior 10 daily highs / lows; (ii) a 3-session move (15:15 index minus the close 3 sessions back) beyond one daily
ATR(14). Position: the ATM option of the signal's side, bought at 15:15. Hold to 15:15 of the 1st or 2nd next session,
or of the last SN session before expiry (always within the same weekly contract; a planned session that does not exist
ends the hold at the last one that does; no next session = no trade). Stops: an adverse index move of one daily ATR on
15-minute marks, and the Rs 3,000 stop. 6 variants; null "side"."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402

IE = gl.I["15:15"]


def atr14(smp, d):
    bars = [smp.prev_bar(d, k) for k in range(1, 16)]
    if any(b is None for b in bars):
        return None
    trs = [max(b[1] - b[2], abs(b[1] - p[3]), abs(b[2] - p[3])) for b, p in zip(bars[:14], bars[1:15])]
    return float(np.mean(trs))


def sig_break(smp, d):
    bars = [smp.prev_bar(d, k) for k in range(1, 11)]
    if any(b is None for b in bars):
        return 0
    c = float(smp.s[d]["index"][3][IE])
    return 1 if c > max(b[1] for b in bars) else (-1 if c < min(b[2] for b in bars) else 0)


def sig_mom(smp, d):
    b3, a = smp.prev_bar(d, 3), atr14(smp, d)
    if b3 is None or not a:
        return 0
    m = float(smp.s[d]["index"][3][IE]) - b3[3]
    return 1 if m > a else (-1 if m < -a else 0)


def later_sessions(smp, d):
    out, x = [], d
    while True:
        nx = LG.next_session(smp, x)
        if nx is None:
            return out
        out.append(nx)
        x = nx


def make(sig_name, sig, hold):
    def trade(smp, d, side, stress=gl.STRESS, late=0):
        nxt = later_sessions(smp, d)
        if not nxt:
            return None
        nxt = nxt[: hold] if hold != "pre" else nxt
        plan = [(d, gl.NM - 1)] + [(x, gl.NM - 1) for x in nxt[:-1]] + [(nxt[-1], IE)]
        a = atr14(smp, d)
        lvl = float(smp.s[d]["index"][3][IE])

        def stop_for(dd):
            idx = smp.s[dd]["index"][3]
            return lambda j: j % 15 == 0 and ((side > 0 and idx[j] < lvl - a) or (side < 0 and idx[j] > lvl + a))
        return LG.held(smp, d, LG.side_legs(smp, smp.s[d], IE, side), IE, plan, stress=stress, late=late,
                       stop_index_by_day=stop_for if a else None)

    return {"name": f"{sig_name} hold {hold}", "signal": lambda smp, d: sig(smp, d), "trade": trade, "null": "side",
            "eligible": lambda smp, d: True}


VARIANTS = [make(n, f, h) for n, f in (("10-day breakout", sig_break), ("3-session move > ATR", sig_mom)) for h in (1, 2, "pre")]

if __name__ == "__main__":
    res = slot.evaluate("SN258", VARIANTS)
    slot.save(HERE / "results-sn258.json", res)
