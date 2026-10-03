"""Evidence-labelled shared-cash portfolio reconciliation for P3 research.

It consumes already archived lifecycle trades.  The routine does not invent an
entry that a source lifecycle did not expose and retains unresolved exposure;
callers must therefore label the output PARTIAL unless every upstream runtime
context and fill event is archived.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PortfolioResult:
    initial_cash: float
    final_cash: float
    locked_cash: float
    realized_pnl: float
    admitted: int
    cash_rejected: int
    unresolved: int
    events: list[dict]


def _stamp(trade: dict) -> str | None:
    return trade.get("entry_time_utc") or trade.get("entry_date")


def reconcile_shared_cash(trade_streams: Iterable[tuple[str, Iterable[dict]]], *, initial_cash: float) -> PortfolioResult:
    """Apply full-notional shared admission then realised lifecycle settlement.

    Ordering is timestamp, strategy label and ticker. This deterministic tie
    rule replaces neither an unarchived scheduler race nor broker priority, so
    it is returned as evidence rather than hidden as a live-parity assertion.
    """
    if not isinstance(initial_cash, (int, float)) or initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    timeline = []
    serial = 0
    for strategy, trades in trade_streams:
        for trade in trades:
            stamp = _stamp(trade)
            price = trade.get("entry_fill_price", trade.get("entry_price"))
            shares = trade.get("initial_shares", trade.get("shares"))
            if not stamp or not isinstance(price, (int, float)) or not isinstance(shares, int) or price <= 0 or shares <= 0:
                continue
            serial += 1
            key = f"{strategy}:{trade.get('ticker')}:{serial}"
            item = (str(strategy), str(trade.get("ticker") or ""), trade, float(price) * shares, key)
            # Exit timestamps from MIS are exact. CNC has only a date, so put
            # it at the end of that session rather than falsely freeing cash
            # before the 15:45 tracker event.
            exit_at = trade.get("exit_fill_ts") or trade.get("exit_date")
            if isinstance(exit_at, str) and len(exit_at) == 10:
                exit_at += "T23:59:59+05:30"
            timeline.append((str(stamp), 1, str(strategy), str(trade.get("ticker") or ""), "ENTRY", item))
            if exit_at and isinstance(trade.get("net_pnl"), (int, float)):
                timeline.append((str(exit_at), 0, str(strategy), str(trade.get("ticker") or ""), "SETTLE", item))
    # Known exits at an identical clock run before fresh entries; this is an
    # explicit declared policy, not a claim about an unarchived scheduler tie.
    timeline.sort(key=lambda item: item[:4])
    cash, locked, pnl = float(initial_cash), 0.0, 0.0
    events = []
    admitted = rejected = unresolved = 0
    admitted_keys = set()
    for stamp, _, strategy, ticker, kind, item in timeline:
        _, _, trade, cost, key = item
        if kind == "ENTRY":
            if cost > cash + 1e-9:
                rejected += 1
                events.append({"event": "CASH_REJECTED", "at": stamp, "strategy": strategy,
                               "ticker": ticker, "required": round(cost, 4), "cash": round(cash, 4)})
                continue
            cash -= cost
            locked += cost
            admitted += 1
            admitted_keys.add(key)
            if not isinstance(trade.get("net_pnl"), (int, float)):
                unresolved += 1
                events.append({"event": "UNRESOLVED_LOCKED", "at": stamp, "strategy": strategy,
                               "ticker": ticker, "locked": round(cost, 4), "source_status": str(trade.get("status") or "")})
            continue
        if key not in admitted_keys:
            continue
        net = float(trade["net_pnl"])
        cash += cost + net
        locked -= cost
        pnl += net
        events.append({"event": "SETTLED", "at": stamp, "strategy": strategy,
                       "ticker": ticker, "net_pnl": round(net, 4)})
    return PortfolioResult(round(float(initial_cash), 4), round(cash, 4), round(locked, 4),
                           round(pnl, 4), admitted, rejected, unresolved, events)
