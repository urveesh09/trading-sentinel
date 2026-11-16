"""Shared trade helpers for SN255-SN263 (standalone, one lot). Conventions (PLAN.md section 2, fixed here before any
Block C score): one lot; the leg's own exits; a Rs 3,000 stop (10% of Rs 30,000) on minute closes; an overnight position
is checked from the next session's 09:15 close (a gap fills wherever it opens) and pays Rs 100 per lot per leg extra if
it closes before 09:20 (wk2's opening penalty); no premium ceiling in the per-lot tables (the premium is recorded)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402

ROOM = 3000.0
OPEN_PEN = 100.0


def side_legs(smp, s, i, side, off=0):
    """One ATM (off = +1 one strike in the money) call (side > 0) or put (side < 0)."""
    K = gl.atm(smp, s, i)
    st = smp.mk["step"]
    if side > 0:
        return [(K - off * st, "CE", 1)]
    return [(K + off * st, "PE", 1)]


def straddle(smp, s, i, width=0.0):
    K = gl.atm(smp, s, i)
    if not width:
        return [(K, "CE", 1), (K, "PE", 1)]
    st = smp.mk["step"]
    ce, pe = gl.opx(s, K, "CE", i), gl.opx(s, K, "PE", i)
    if ce is None or pe is None:
        return None
    d = max(st, int(round(width * (ce + pe) / st)) * st)
    return [(K + d, "CE", 1), (K - d, "PE", 1)]


def intraday(smp, d, legs, i_entry, i_exit, room=ROOM, tgt=None, stress=gl.STRESS, late=0, stop_index=None):
    s = smp.s[d]
    if legs is None:
        return None
    i = i_entry + late
    p = gl.Pos(smp, s, legs, i, 1, stress)
    if not p.ok:
        return None
    net, j, why = gl.walk(p, s, i, i_exit, room=room, tgt=tgt, stop_index=stop_index)
    if net is None:
        return None
    return {"day": d, "exit_day": d, "net": net, "why": why, "premium": p.premium, "i": i, "j": j}


def next_session(smp, d):
    """The next trading day if it is an SN session of the same weekly contract, else None."""
    nd = smp.next_day(d)
    if nd is None or nd not in smp.s or smp.s[nd]["expiry"] != smp.s[d]["expiry"]:
        return None
    return nd


def held(smp, d, legs, i_entry, plan, room=ROOM, stress=gl.STRESS, late=0, stop_index_by_day=None):
    """Open at i_entry on d; plan = [(day, last minute to hold to on that day)], in order; the position is valued on each
    planned session from its 09:15 close (or after the entry minute on d itself) and closed at the plan's last minute,
    at the room stop, or at the last mark if a planned session has no price."""
    s = smp.s[d]
    if legs is None:
        return None
    i = i_entry + late
    p = gl.Pos(smp, s, legs, i, 1, stress)
    if not p.ok:
        return None
    last = None
    for n, (dd, jmax) in enumerate(plan):
        ss = smp.s[dd]
        j0 = i if dd == d else -1
        sidx = stop_index_by_day(dd) if stop_index_by_day else None
        for j in range(j0 + 1, jmax + 1):
            v = p.value(ss, j)
            if v is None:
                continue
            pen = OPEN_PEN * len(p.legs) if (dd != d and j < 5) else 0.0
            v -= pen
            last = (v, dd, j)
            if room is not None and v <= -room:
                return {"day": d, "exit_day": dd, "net": v, "why": "stop", "premium": p.premium, "i": i, "j": j}
            if sidx is not None and sidx(j):
                return {"day": d, "exit_day": dd, "net": v, "why": "index stop", "premium": p.premium, "i": i, "j": j}
    if last is None:
        return None
    return {"day": d, "exit_day": last[1], "net": last[0], "why": "time", "premium": p.premium, "i": i, "j": last[2]}


def board(smp_names, rule, **kw):
    out = {}
    for n in smp_names:
        smp = gl.sample(n)
        tr = gl.book(smp, rule, **kw)
        st = gl.stats(tr)
        st["premium_le_15k_share"] = round(float(np.mean([t["premium"] <= 15000.0 for t in tr])), 3) if tr else None
        out[n] = (st, tr)
    return out
