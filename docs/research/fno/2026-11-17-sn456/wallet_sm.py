"""SN468: the shared-wallet state machine for Gold plus one companion (PLAN.md section 2, frozen at 83e1b444). Research ledger
only; it places nothing.

Events are processed in (time, kind order) with kind order: session end last, Gold intents before packets at the same
timestamp (Gold's priority), packets in arrival order; a packet's seq is processed once (duplicates ignored).
Companion order states: PENDING_ENTRY -> (PARTIAL) -> OPEN -> PENDING_EXIT -> (PARTIAL_EXIT) -> CLOSED; UNRESOLVED when the
session ends with units held (no forced sale at an invented bid); CANCELLED for an unfilled entry at the end.
A fill needs a FRESH packet (age <= MAX_AGE s) with a positive quantity on the touch: an entry at the ask (<= its limit), an
exit at the bid. Cash leaves at each entry fill (price x units + that fill's fee) and returns only at each exit fill (price x
units - that fill's fee): costs are booked once per fill and never recomputed.
Gold intent (amount): spends only free cash. If free cash is short and a companion holds units, the companion's exit is sent
(if not already) and the intent WAITS; it fills (DELAYED) at the first moment free cash covers it, or lapses (MISSED) GOLD_WAIT
seconds after it arrived or at the session end. It never spends proceeds that have not been received.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MAX_AGE, GOLD_WAIT = 2.0, 60.0


def fee(px, units):
    """A simple dated-cost stand-in for the fixtures: Rs 20 per fill plus 0.1% of the value (booked once per fill)."""
    return 20.0 + 0.001 * px * units


@dataclass
class Companion:
    qty: int
    limit: float
    state: str = "PENDING_ENTRY"
    held: int = 0
    paid: float = 0.0
    received: float = 0.0
    fills: list = field(default_factory=list)


@dataclass
class GoldIntent:
    t: float
    amount: float
    state: str = "WAITING"
    t_done: Optional[float] = None


class Ledger:
    def __init__(self, cash: float):
        self.cash = float(cash)
        self.comp: Optional[Companion] = None
        self.gold: list[GoldIntent] = []
        self.seen: set = set()
        self.fees_booked = 0
        self.log: list = []
        self.now = 0.0

    # ---- invariants -------------------------------------------------------------------------------------------------
    def check(self):
        assert self.cash >= -1e-9, self.cash
        if self.comp:
            assert 0 <= self.comp.held <= self.comp.qty
        assert self.fees_booked == sum(len(c) for c in ([self.comp.fills] if self.comp else []))

    # ---- companion ------------------------------------------------------------------------------------------------------
    def companion_buy(self, t, qty, limit):
        assert self.comp is None or self.comp.state in ("CLOSED", "CANCELLED")
        self.comp = Companion(qty=qty, limit=limit)
        self.fees_booked = 0
        self.log.append((t, "COMP_BUY", qty, limit))

    def companion_exit(self, t):
        c = self.comp
        if c and c.held > 0 and c.state in ("OPEN", "PARTIAL"):
            c.state = "PENDING_EXIT"
            self.log.append((t, "COMP_EXIT_SENT"))

    # ---- gold -------------------------------------------------------------------------------------------------------------
    def gold_intent(self, t, amount):
        g = GoldIntent(t=t, amount=float(amount))
        self.gold.append(g)
        self._try_gold(t)
        if g.state == "WAITING":
            self.companion_exit(t)
        return g

    def _try_gold(self, t):
        for g in self.gold:
            if g.state != "WAITING":
                continue
            if t - g.t > GOLD_WAIT:
                g.state, g.t_done = "MISSED", t
                continue
            if self.cash >= g.amount:
                self.cash -= g.amount
                g.state = "FILLED" if t == g.t else "DELAYED"
                g.t_done = t
                self.log.append((t, "GOLD_" + g.state, g.amount))

    # ---- packets ----------------------------------------------------------------------------------------------------------
    def packet(self, seq, t, age, bid, bq, ask, aq):
        if seq in self.seen:
            return
        self.seen.add(seq)
        self.now = t
        for g in self.gold:
            if g.state == "WAITING" and t - g.t > GOLD_WAIT:
                g.state, g.t_done = "MISSED", g.t + GOLD_WAIT
        c = self.comp
        fresh = age is not None and age <= MAX_AGE
        if c and fresh:
            if c.state in ("PENDING_ENTRY", "PARTIAL") and c.held < c.qty and ask and aq and aq > 0 and ask <= c.limit:
                u = min(aq, c.qty - c.held)
                cost = ask * u + fee(ask, u)
                if cost <= self.cash:
                    self.cash -= cost
                    c.held += u
                    c.paid += cost
                    c.fills.append(("BUY", t, ask, u))
                    self.fees_booked += 1
                    c.state = "OPEN" if c.held == c.qty else "PARTIAL"
            elif c.state in ("PENDING_EXIT", "PARTIAL_EXIT") and c.held > 0 and bid and bq and bq > 0:
                u = min(bq, c.held)
                got = bid * u - fee(bid, u)
                self.cash += got
                c.held -= u
                c.received += got
                c.fills.append(("SELL", t, bid, u))
                self.fees_booked += 1
                c.state = "CLOSED" if c.held == 0 else "PARTIAL_EXIT"
        self._try_gold(t)
        self.check()

    def session_end(self, t):
        c = self.comp
        if c:
            if c.held > 0:
                c.state = "UNRESOLVED"
            elif c.state in ("PENDING_ENTRY",):
                c.state = "CANCELLED"
        for g in self.gold:
            if g.state == "WAITING":
                g.state, g.t_done = "MISSED", t
        self.check()
