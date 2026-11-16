"""SN261 - the weekly straddle bought when it is cheap, WK-H's mirror (PLAN.md). Entry day = WK-H's: the first session
after the last weekend or holiday before expiry (no calendar gap > 1 day from it to expiry), at 15:15. Buy the ATM
straddle when its price (points) < m x the mean absolute daily close change of the last 5 sessions x sqrt(sessions to
expiry), m in {0.8, 1.0}. Exit: (x1) the next session's 15:15; (x2) 09:20 two sessions later. Both exit sessions must be
SN sessions of the same contract (expiry-day minutes do not exist), else no trade. Rs 3,000 stop. Null "day": the same
trade on as many random WK-H entry days (random weeks). 4 variants."""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402

IE = gl.I["15:15"]


def is_m_day(smp, d):
    e = smp.s[d]["expiry"]
    k = smp.cal.index(d)
    if k == 0:
        return False
    prev = smp.cal[k - 1]
    if (dt.date.fromisoformat(d) - dt.date.fromisoformat(prev)).days <= 1:
        return False                                  # d must follow a weekend / holiday
    x = d
    while x < e:                                      # and no gap > 1 day from d to expiry
        nx = smp.next_day(x)
        if nx is None or (dt.date.fromisoformat(nx) - dt.date.fromisoformat(x)).days > 1:
            return False
        x = nx
    return d < e


def cheap(smp, d, m):
    s = smp.s[d]
    K = gl.atm(smp, s, IE)
    ce, pe = gl.opx(s, K, "CE", IE), gl.opx(s, K, "PE", IE)
    bars = [smp.prev_bar(d, k) for k in range(0, 6)]
    if ce is None or pe is None or any(b is None for b in bars[1:]):
        return False
    closes = [float(s["index"][3][IE])] + [b[3] for b in bars[1:]]
    mv = float(np.mean(np.abs(np.diff(closes))))
    n = smp.sessions_until(d, s["expiry"])
    return (ce + pe) < m * mv * math.sqrt(max(n, 1))


def make(m, x):
    def trade(smp, d, side, stress=gl.STRESS, late=0):
        n1 = LG.next_session(smp, d)
        if n1 is None:
            return None
        if x == "x1":
            plan = [(d, gl.NM - 1), (n1, IE)]
        else:
            n2 = LG.next_session(smp, n1)
            if n2 is None:
                return None
            plan = [(d, gl.NM - 1), (n1, gl.NM - 1), (n2, gl.I["09:20"])]
        return LG.held(smp, d, LG.straddle(smp, smp.s[d], IE), IE, plan, stress=stress, late=late)

    return {"name": f"cheap < {m} x recent move, exit {x}", "signal": lambda smp, d: True if (is_m_day(smp, d) and cheap(smp, d, m)) else None,
            "trade": trade, "null": "day", "eligible": is_m_day}


VARIANTS = [make(m, x) for m in (0.8, 1.0) for x in ("x1", "x2")]

if __name__ == "__main__":
    res = slot.evaluate("SN261", VARIANTS)
    slot.save(HERE / "results-sn261.json", res)
