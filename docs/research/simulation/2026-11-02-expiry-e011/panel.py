"""September's conditional exit panel: what happens to a cheap ticket once it is bought.

September can't replay the book. preflight-sept.json shows why: none of its 11 breaks has a ticket in the files,
because the fixed strike is in the money or too dear by the afternoon. So this asks a narrower question. It buys a
ticket and compares only what each arm does afterwards. All arms own the same ticket at the same price, so the
difference is purely the exits. It can't say whether the book would have bought these tickets.

Two admission rules, each knowable at its tick, fixed after counting tickets and before seeing any ticket's later price:

  BREAK     a real confirmed break from the engine's box, on the proxy, where the fixed strike is out of the money in
            that direction and its ask is at most 3x C's band.
  MOMENTUM  the fixed strike's option, out of the money, 13:30 to 15:05, ask at most 2x C's band, above its own highest
            ask of the previous 10 minutes on two bars in a row, 15 minutes since this rule last bought this leg.

Each admission is its own ticket on its own full Rs 2,500 ceiling, with the engine's sizing, 10-lot cap and fees. They can
overlap and they are not a book, so the panel total is not money the book would have made. Dearer than C's band means a
lower multiple is likely, and every ticket here is a call on one of two days.

No failed-break exit in any arm: a momentum ticket has no box break behind it, and the panel treats both rules alike.
A thin bar refuses the fill and the exit stays pending, as in the engine.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import e011_lab as L
import sept as Z
from e011_lab import EP

LOOK = timedelta(minutes=10)
COOLDOWN = timedelta(minutes=15)
START, END = EP.BOX_END, EP.A_ENTRY_END
BREAK_BAND_X, MOMENTUM_BAND_X = 3.0, 2.0


def _in_band(spot: float, ask: float, multiple: float) -> bool:
    return spot * EP.C_PREMIUM_BAND[0] <= ask <= spot * EP.C_PREMIUM_BAND[1] * multiple


def break_admissions(S: Z.Sept) -> list[tuple[int, str, str]]:
    _, signals = L.signal_stream(S)
    out = []
    for i, direction in signals:
        kind = "CE" if direction == "UP" else "PE"
        symbol = next(n for n, k in S.kinds.items() if k == kind)
        q = S.quote(i, symbol)
        spot = S.spot[i]
        otm = S.strike > spot if kind == "CE" else S.strike < spot
        if otm and q.ask is not None and _in_band(spot, q.ask, BREAK_BAND_X) and q.spread_ok(EP.BC_MAX_SPREAD):
            out.append((i, symbol, "BREAK"))
    return out


def momentum_admissions(S: Z.Sept) -> list[tuple[int, str, str]]:
    out = []
    for symbol, kind in S.kinds.items():
        recent: list[tuple] = []
        last = None
        streak = 0
        for i in range(S.n):
            q = S.quote(i, symbol)
            if q is None or q.ask is None:
                continue
            now = S.now[i]
            floor = now - LOOK
            prior = [a for t, a in recent if t >= floor]
            above = bool(prior) and q.ask > max(prior)
            have_look = S.now[0] <= floor
            recent.append((now, q.ask))
            recent = [(t, a) for t, a in recent if t >= floor]
            streak = streak + 1 if above and have_look else 0
            if not START <= S.clock[i] < END:
                continue
            spot = S.spot[i]
            otm = S.strike > spot if kind == "CE" else S.strike < spot
            if streak >= EP.CONFIRM_TICKS and otm and _in_band(spot, q.ask, MOMENTUM_BAND_X) and q.spread_ok(EP.BC_MAX_SPREAD) \
                    and (last is None or now - last >= COOLDOWN):
                out.append((i, symbol, "MOMENTUM"))
                last = now
    return sorted(out)


def admissions(S: Z.Sept) -> list[tuple[int, str, str]]:
    """Every ticket on this day, from ordinary quotes, so every arm and scenario shares one list."""
    return sorted(break_admissions(S) + momentum_admissions(S))


def run_ticket(S: Z.Sept, i: int, symbol: str, ticket: L.Ticket, budget: float = 2500.0) -> list[dict]:
    """One admitted ticket under one arm's exits, at this scenario's fill."""
    contract = S.contract(symbol)
    quote = S.quote(i, symbol)
    lots, prices = EP.affordable_fill([(quote, contract.lot_size)], budget, EP.C_MAX_LOTS, S.schedule)
    if not lots:
        return []
    bare = replace(ticket, back=None)
    policy = bare.policy
    manager = L._bank_manager(bare)
    pos = L._open(S, i, "X", contract, prices[0], lots, policy)
    state = {"box": None}
    for k in range(i + 1, S.n):
        if pos["status"] != "OPEN":
            break
        L.manage_leg(S, k, pos, policy, None, state, manager)
    L.settle(S, [pos])
    return [pos]
