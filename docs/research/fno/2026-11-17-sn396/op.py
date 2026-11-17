"""The opening trade on three clocks (PLAN.md section 0, frozen at 00693405). Shared by SN396 / SN397 / SN399 / SN406 /
SN407 / SN410. Pure reading of gl's cached sessions and Breeze's read-only history; places nothing.

Clock for a decision at hh:mm:00 (minute index m = hh*60 + mm - 555; gl's index i is the bar starting 09:15 + i, its
close at the bar's last second):
  ORIGINAL  labels (ATM strike, straddle IV) and fill at m (SN382 / SN394: m = 1, the 09:16 bar's close, 09:16:59)
  HONEST    labels and fill at m - 1 (the bar that closed at hh:mm:00 - 1 s); exits at m - 1 + H
  LATE      labels at m - 1, fill at m (59 s latency); the order carries fw7a's limit (label ask + 2 ticks, never above
            the room price): a fill above it is MISSED; exits at m + H
Previous-session 15:00 reading: index 345 (ORIGINAL), 344 (HONEST / LATE).
"""
from __future__ import annotations

import bisect
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn381"))
sys.path.insert(0, str(FNO / "2026-11-16-sn366"))
import sn382 as R  # noqa: E402
import sn377 as V  # noqa: E402

gl, S, sn353b, sn361 = R.gl, R.S, R.sn353b, V.sn361
wk = gl.wk
ROOM, LOT, TICK = 15000.0, 65, 0.05
STOP = S.STOP
SPLIT = "2026-09-07"
CUT_LO, CUT_HI = 1.2684, 3.0684                 # fw9's frozen cutoffs (ORIGINAL clock, 644 historical jumps)
CLOCKS = {"ORIGINAL": (0, 0), "HONEST": (-1, -1), "LATE": (-1, 0)}     # offsets of (label, fill) from m
PREV = {"ORIGINAL": 345, "HONEST": 344, "LATE": 344}


def entry_cost(f):
    return f * LOT + wk.charges(f, 0.0, LOT, "NFO")


def room_price():
    lo, hi = 0.0, ROOM / LOT
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if entry_cost(mid) <= ROOM else (lo, mid)
    return lo


RP = room_price()


def setup():
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    return smp, days, au


def leg(smp, s, side, m, clock, stress, depths=(2, 1)):
    """(pos, depth, state, fill index). state FILLED / INADMISSIBLE / MISSED / NO_PRICE."""
    ol, of = CLOCKS[clock]
    il, jf = m + ol, m + of
    if il < 0:
        return None, None, "NO_PRICE", None
    atm = gl.atm(smp, s, il)
    sgn = -1 if side == "CE" else 1
    for dep in depths:
        k = atm + sgn * dep * 50
        p = gl.opx(s, k, side, il)
        if p is None:
            continue
        a_lab = wk.ask(smp.mk, p)
        if entry_cost(a_lab) > ROOM:
            continue
        pos = gl.Pos(smp, s, [(k, side, +1)], jf, lots=1, stress=stress)
        if not pos.ok:
            return None, dep, "NO_PRICE", jf
        if jf != il and pos.fills[0] > min(a_lab + 2 * TICK, RP) + 1e-9:
            return None, dep, "MISSED", jf
        return pos, dep, "FILLED", jf
    return None, None, "INADMISSIBLE", None


def path(pos, s, j0, j1):
    """Per-minute net values from j0 + 1 to j1 (None where unpriced)."""
    return [pos.value(s, j) for j in range(j0 + 1, j1 + 1)]


def net_from_path(vals, H, stop=STOP):
    """gl.walk on a precomputed path: stop at -stop, else the last priced value within H minutes."""
    last = None
    for v in vals[:H]:
        if v is None:
            continue
        last = v
        if stop is not None and v <= -stop:
            return v, "stop"
    return (None, "no price") if last is None else (last, "time")


def jumps(smp, clock):
    """{day: jump in vol points} for sessions whose previous session has the same expiry (SN377 / SN394's pairs)."""
    ol, _of = CLOCKS[clock]
    out = {}
    for a, d in zip(smp.days, smp.days[1:]):
        s, sp = smp.s[d], smp.s[a]
        if s["day"] == s["expiry"] or sp["expiry"] != s["expiry"]:
            continue
        io, ip = V.straddle_iv(smp, s, 1 + ol), V.straddle_iv(smp, sp, PREV[clock])
        if io is None or ip is None:
            continue
        out[d] = 100.0 * (io - ip)
    return out


def labels(jmp, fixed=True, q_lo=(1, 3), q_hi=(2, 3), min_hist=60):
    """CHEAP / MID / RICH: the frozen cutoffs (fixed=True) or the causal moving quantiles (>= min_hist earlier; q as
    integer fractions so the tercile index is SN394's len // 3 exactly)."""
    out, hist = {}, []
    for d in sorted(jmp):
        j = jmp[d]
        if fixed:
            out[d] = "CHEAP" if j < CUT_LO else "RICH" if j > CUT_HI else "MID"
        elif len(hist) >= min_hist:
            srt = sorted(hist)
            n = len(srt)
            lo, hi = srt[n * q_lo[0] // q_lo[1]], srt[min(n - 1, n * q_hi[0] // q_hi[1])]
            out[d] = "CHEAP" if j < lo else "RICH" if j > hi else "MID"
        hist.append(j)
    return out


def coin(d):
    return random.Random(f"sn376-{d}").choice(("CE", "PE"))


def per_session(xs):
    return round(float(np.mean(xs)), 1) if xs else None


def without_best(xs):
    return round(float((sum(xs) - max(xs)) / (len(xs) - 1)), 1) if len(xs) > 1 else None


def prev_session(cal, d):
    k = bisect.bisect_left(cal, d) - 1
    return cal[k] if k >= 0 else None
