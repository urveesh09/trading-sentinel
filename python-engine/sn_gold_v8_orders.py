"""[SN338 2026-11-16] Gold V8's order lifecycle for one position, as a pure state machine (no broker, no I/O). The future
real-money module will drive it from Kite order updates; this file fixes the rules first, with tests for the cases where
the broker or the market misbehaves (docs/research/fno/2026-11-16-sn331/PLAN.md, SN338; GOLD_V8.md section 2).

The rules:
  * the units sold (filled SELLs) never exceed the units bought (filled BUYs): a SELL order is only ever sized to what is
    held and not already being sold;
  * one protective stop (SL) at a time, sized to the holding; an add first cancels the old stop, and the new stop for the
    whole holding is placed only after the add's fill is known;
  * an exit first asks to cancel the stop and sends its SELL only once the stop's cancel or its fill is confirmed, so a
    stop that fills during the cancel shrinks the exit (to zero if it sold everything);
  * a stop that triggers but does not fill (the price gapped through its limit) is cancelled and replaced by a MARKET sell
    of what is still held;
  * a fill that arrives after a cancel was confirmed (an exchange race) is still booked, and the holding is reconciled; a
    holding that would go negative is flagged OVERSOLD (it must never happen; the module then stops new entries).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

LIVE = ("OPEN", "TRIGGER_PENDING", "TRIGGERED", "CANCEL_REQUESTED")


@dataclass
class Order:
    oid: int
    kind: str                  # ENTRY / ADD / STOP / EXIT
    side: str                  # BUY / SELL
    qty: int
    order_type: str            # LIMIT / SL / MARKET
    limit: Optional[float] = None
    trigger: Optional[float] = None
    filled: int = 0
    status: str = "OPEN"       # OPEN / TRIGGER_PENDING / TRIGGERED / CANCEL_REQUESTED / COMPLETE / CANCELLED / REJECTED
    late_fill: bool = False


@dataclass
class Book:
    lot_size: int
    held: int = 0
    orders: Dict[int, Order] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    pending_exit: Optional[str] = None       # the exit's order type, waiting for the stop's cancel
    _next: int = 1

    # ---- what is in flight ------------------------------------------------------------------------------------------
    def live(self, kind=None, side=None):
        return [o for o in self.orders.values() if o.status in LIVE and (kind is None or o.kind == kind) and (side is None or o.side == side)]

    def selling(self) -> int:
        return sum(o.qty - o.filled for o in self.live(side="SELL"))

    def stop(self) -> Optional[Order]:
        s = self.live(kind="STOP")
        return s[0] if s else None

    # ---- actions ----------------------------------------------------------------------------------------------------
    def _place(self, kind, side, qty, order_type, limit=None, trigger=None) -> Optional[Order]:
        if qty <= 0:
            return None
        if side == "SELL" and qty > self.held - self.selling():
            raise ValueError(f"SELL {qty} > held {self.held} - selling {self.selling()}")
        o = Order(self._next, kind, side, qty, order_type, limit, trigger,
                  status="TRIGGER_PENDING" if order_type == "SL" else "OPEN")
        self.orders[o.oid] = o
        self._next += 1
        self.log.append(f"place {kind} {side} {qty} {order_type}")
        return o

    def buy(self, kind: str, qty: int, limit: float) -> Optional[Order]:
        if kind == "ADD" and self.stop() is not None:
            self.cancel(self.stop().oid)          # the old stop goes first; the new one follows the add's fill
        return self._place(kind, "BUY", qty, "LIMIT", limit=limit)

    def protect(self, trigger: float, limit: float) -> Optional[Order]:
        """Place the stop for the whole holding (none while another stop is live or nothing is held)."""
        if self.stop() is not None or self.held - self.selling() <= 0:
            return None
        return self._place("STOP", "SELL", self.held - self.selling(), "SL", limit=limit, trigger=trigger)

    def cancel(self, oid: int) -> None:
        o = self.orders[oid]
        if o.status in LIVE:
            o.status = "CANCEL_REQUESTED"
            self.log.append(f"cancel {o.kind} {oid}")

    def exit(self, order_type: str = "LIMIT_THEN_MARKET") -> Optional[Order]:
        """Leave the position: cancel the stop first; the SELL goes once that is confirmed (see on_cancelled / on_fill)."""
        s = self.stop()
        if s is not None:
            self.cancel(s.oid)
            self.pending_exit = order_type
            return None
        return self._send_exit(order_type)

    def _send_exit(self, order_type: str) -> Optional[Order]:
        self.pending_exit = None
        qty = self.held - self.selling()
        return self._place("EXIT", "SELL", qty, "MARKET" if order_type == "MARKET" else "LIMIT") if qty > 0 else None

    # ---- broker events ------------------------------------------------------------------------------------------------
    def on_fill(self, oid: int, qty: int) -> None:
        o = self.orders[oid]
        if qty <= 0 or o.filled + qty > o.qty:
            raise ValueError("fill beyond the order")
        if o.status == "CANCELLED":
            o.late_fill = True
            self.flags.append(f"late fill on {o.kind} {oid}")
        o.filled += qty
        self.held += qty if o.side == "BUY" else -qty
        if self.held < 0:
            self.flags.append("OVERSOLD")
        if o.filled == o.qty:
            o.status = "COMPLETE"
        self.log.append(f"fill {o.kind} {o.side} {qty} -> held {self.held}")
        if o.side == "BUY" and o.status == "COMPLETE" and self.pending_exit is None:
            pass                                   # the caller places the stop for the new holding (protect)
        if o.kind == "STOP" and self.pending_exit is not None and o.status == "COMPLETE":
            self._send_exit(self.pending_exit)      # the stop sold it all during the cancel: nothing (or the rest) to sell

    def on_cancelled(self, oid: int) -> None:
        o = self.orders[oid]
        if o.status != "COMPLETE":
            o.status = "CANCELLED"
            self.log.append(f"cancelled {o.kind} {oid} (filled {o.filled})")
        if o.kind == "STOP" and self.pending_exit is not None:
            self._send_exit(self.pending_exit)

    def on_triggered_unfilled(self, oid: int) -> None:
        """The stop triggered but the price went through its limit: cancel it and sell what is held at MARKET."""
        o = self.orders[oid]
        o.status = "TRIGGERED"
        self.cancel(oid)
        self.pending_exit = "MARKET"

    def on_rejected(self, oid: int) -> None:
        self.orders[oid].status = "REJECTED"
        self.flags.append(f"rejected {self.orders[oid].kind} {oid}")
