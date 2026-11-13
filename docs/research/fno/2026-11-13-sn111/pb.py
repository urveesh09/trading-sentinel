"""Phase B helpers (SN111-SN115): any fixed set of long option legs valued minute by minute (the phase A straddle
path generalised; parity with pa.path for the ATM straddle is asserted by the scorers)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import pa  # noqa: E402
import qa  # noqa: E402

C, M = pa.C, pa.M
FLAT, I10, STRICT = pa.FLAT, pa.I10, pa.STRICT


def atm(S, i):
    return int(round(S.F["c"][i] / M.STEP) * M.STEP)


def struct_path(S, i, spec, leg_stress=STRICT, end=FLAT):
    """spec: [(strike, 'CE'|'PE'), ...] bought at minute i's ask. Returns (asks, premium rupees, net path) or None."""
    legs = []
    for k, opt in spec:
        rec = S.option(k, opt)
        if rec is None or not rec[6][i]:
            return None
        legs.append((rec, M.ask_of(float(rec[0][3][i]))))
    vals = np.full(end + 1, np.nan)
    for j in range(i + 1, end + 1):
        tot = fees = 0.0
        ok = True
        for rec, px in legs:
            x = pa.sn95.bid_at(rec, j)
            if x is None:
                ok = False
                break
            tot += (x - px) * M.LOT
            fees += M.charges(px, x, M.LOT)
        if ok:
            vals[j] = tot - fees - leg_stress * len(legs)
    asks = [px for _r, px in legs]
    return asks, sum(asks) * M.LOT, vals


def net(got, i=I10, room=3000.0, ceiling=15000.0, n_legs=2):
    """Executable net of a valued structure under the room / ceiling rules (0 when skipped)."""
    if got is None or got[1] > ceiling:
        return 0.0
    return pa.settle(got[2], i, room, fallback=-STRICT * n_legs)[0]


def signal_days(adm, gold_free_only=True):
    """SN95-L's days (or all signal days): R_today in the causal top 20% at 10:00 and the straddle affordable at Rs 15k."""
    Ys = C.years()
    out = []
    for y in C.YEARS:
        for S in Ys[y].ordered():
            if not adm.get((S.day, "10:00", "R_today", 0.2, "top"), False):
                continue
            if gold_free_only and not C.gold_free(S.day):
                continue
            got = pa.path(S, I10)
            if got is not None and got[1] <= 15000.0:
                out.append(S)
    return out
