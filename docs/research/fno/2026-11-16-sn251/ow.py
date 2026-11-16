"""One wallet (PLAN.md section 0): SN Gold v5 and a gap-day leg on the same money, SN110's contract generalised.

- The leg opens only when no Gold position is open; its premium leaves >= Rs 15,000 of the wallet free; its stop is 10% of
  the wallet, inside the shared 20% day room; a Gold signal while it is open sells it that minute, then Gold enters.
- A leg held overnight (opened after Gold's last exit, 15:15 or later) is booked on the session it closes, inside that
  session's room, and is closed before (or at) the first Gold signal of that session.
- Never admitted, the player is Gold v5 exactly (checked by SN252).
A leg object provides any of:
  intraday(smp, d, i_from, wallet, room, stop_at) -> (net, exit minute, reason) or None
  night_open(smp, d, wallet) -> carry dict {pos, exit_day, exit_i} or None   (entered at or after 15:15)
  night_close(smp, carry, d, room, stop_at) -> (net, exit minute, reason)
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import gl  # noqa: E402
import sn110  # noqa: E402

C = sn110.C
M = C.M
L = C.L
RESERVE = 15000.0
ROOM_SHARE = 0.10
DAYLOG: list = []          # (day, wallet, net, gold_trades, leg_net)
LEGLOG: list = []
STATE = {"leg": None, "smp": None, "carry": None}


def _smp():
    if STATE["smp"] is None:
        raw = gl._cache("devall", gl.build_dev)
        STATE["smp"] = gl.Sample("ACCOUNT", raw, "2023-01-01", gl.TEST_HI)
    return STATE["smp"]


def play_day(S, sigs, v, wallet, full_lots, ctx, vol_day):
    leg = STATE["leg"]
    loss = v.get("loss_share", 0.2) * wallet
    realized, free, ntr, gk, leg_net = 0.0, 0, 0, 0, 0.0
    gold = sorted(sigs, key=lambda x: x["i"])

    def next_gold(after):
        k = gk
        while k < len(gold) and (gold[k]["i"] < after or gold[k]["i"] >= M.EXIT_MIN or gold[k]["expiry"] != S.s["expiry"]):
            k += 1
        return k

    smp = _smp() if leg is not None else None
    # 1. an overnight leg carried into this session closes first
    car = STATE["carry"]
    if car is not None:
        STATE["carry"] = None
        if car["exit_day"] == S.day:
            k = next_gold(0)
            g_i = gold[k]["i"] if k < len(gold) else None
            room = min(ROOM_SHARE * wallet, loss + realized)
            net, j, why = leg.night_close(smp, car, S.day, room, g_i)
            realized += net
            leg_net += net
            LEGLOG.append({"day": S.day, "entry_day": car["pos"].day, "net": net, "why": why, "wallet": wallet})
            free = j + 1
        else:                                     # the planned next session is not this one (cannot happen by entry rule)
            LEGLOG.append({"day": S.day, "entry_day": car["pos"].day, "net": 0.0, "why": "orphan", "wallet": wallet})
    tried = False
    while True:
        gk = next_gold(free)
        g_i = gold[gk]["i"] if gk < len(gold) else None
        if leg is not None and not tried and hasattr(leg, "intraday") and loss + realized > loss * 0.05:
            tried = True
            room = min(ROOM_SHARE * wallet, loss + realized)
            got = leg.intraday(smp, S.day, free, wallet - RESERVE, room, g_i)
            if got is not None:
                net, j, why = got
                realized += net
                leg_net += net
                LEGLOG.append({"day": S.day, "net": net, "why": why, "wallet": wallet})
                free = j if why == "forced" else j + 1
                continue
        if g_i is None:
            break
        sg = gold[gk]
        gk += 1
        if ntr >= v.get("max_trades", 99):
            break
        res = C.gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
        if res is None:
            continue
        net, j, lots, ask, px, strike = res
        ntr += 1
        realized += net
        ctx.closed.append((S.day, j, sg["expert"], net / lots))
        free = j + 1
        if loss + realized < loss * 0.05:
            break
    # 2. an overnight leg may open after Gold's last exit
    if leg is not None and hasattr(leg, "night_open") and loss + realized > loss * 0.05:
        car = leg.night_open(smp, S.day, wallet - RESERVE)
        if car is not None:
            STATE["carry"] = car
    DAYLOG.append((S.day, wallet, realized, ntr, leg_net))
    return realized


def run_wallet(v, w, leg=None):
    """(panel row, DAYLOG copy, LEGLOG copy) for one wallet tuple, Gold v5 config v, and a leg (or None)."""
    L.play_day = play_day
    L.size = C.size_ext
    old = L.WALLETS
    L.WALLETS = (w,)
    DAYLOG.clear()
    LEGLOG.clear()
    STATE["leg"], STATE["carry"] = leg, None
    try:
        r = L.run(C.years(), None, v)
    finally:
        L.WALLETS = old
        STATE["leg"] = None
    return C.panel(r)[w[0]], list(DAYLOG), list(LEGLOG)


GOLD_30K = ("30k grow stop 3", 30000.0, "grow", 3)
