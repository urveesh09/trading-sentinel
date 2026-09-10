"""Deterministic, conservative replay of the deployed intraday debit spread.

This is a research adapter, never an order simulator.  A replay can only use
quotes received by its decision clock and needs executable two-leg depth for a
full exchange lot on both entry and exit.  Missing data produces an explicit
non-fill or uncertainty result rather than an optimistic capped-loss outcome.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Iterable, Literal

import pytz

from partner_manual_advisory import INTRADAY_POLICY_VERSION


IST = pytz.timezone("Asia/Kolkata")
_EXCHANGES = {"NIFTY": "NFO", "SENSEX": "BFO"}


class ReplayInputError(ValueError):
    """Malformed research evidence; never silently repaired by replay."""


@dataclass(frozen=True)
class LegQuote:
    symbol: str
    side: Literal["BUY", "SELL"]
    exchange: str
    lot_size: int
    bid: float
    ask: float
    bid_depth: int
    ask_depth: int
    observed_at: datetime
    received_at: datetime


@dataclass(frozen=True)
class ReplayResult:
    state: str
    reason: str
    entry_debit_rs: float | None
    exit_credit_rs: float | None
    total_cost_rs: float | None
    net_pnl_rs: float | None
    entry_at: str
    exit_at: str | None
    evidence_sha256: str
    policy_version: str = INTRADAY_POLICY_VERSION
    research_only: bool = True
    can_place_orders: bool = False


def _stamp(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayInputError(f"{field} must be timezone-aware")
    return value.astimezone(IST)


def _finite(value: float, field: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ReplayInputError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ReplayInputError(f"{field} is invalid")
    return number


def _quote_payload(quote: LegQuote) -> dict:
    payload = asdict(quote)
    payload["observed_at"] = _stamp(quote.observed_at, "observed_at").isoformat()
    payload["received_at"] = _stamp(quote.received_at, "received_at").isoformat()
    return payload


def _digest(*, underlying: str, expiry: str, entry_at: datetime, exit_at: datetime | None,
            entry: Iterable[LegQuote], exit_: Iterable[LegQuote], fee_per_leg_rs: float) -> str:
    payload = {"policy_version": INTRADAY_POLICY_VERSION, "underlying": underlying,
               "expiry": expiry, "entry_at": entry_at.isoformat(),
               "exit_at": exit_at.isoformat() if exit_at else None,
               "entry": [_quote_payload(item) for item in entry],
               "exit": [_quote_payload(item) for item in exit_], "fee_per_leg_rs": fee_per_leg_rs}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_pair(underlying: str, quotes: list[LegQuote], *, decision_at: datetime,
                   max_age: timedelta, max_sync: timedelta, phase: str) -> tuple[str | None, list[LegQuote]]:
    if len(quotes) != 2:
        return f"{phase}_requires_exactly_two_legs", []
    expected_exchange = _EXCHANGES.get(underlying)
    if expected_exchange is None:
        raise ReplayInputError("only NIFTY and SENSEX are supported")
    sides = {quote.side for quote in quotes}
    if sides != {"BUY", "SELL"}:
        return f"{phase}_requires_one_buy_and_one_sell", []
    normalized = []
    for quote in quotes:
        if quote.exchange != expected_exchange:
            return f"{phase}_wrong_exchange", []
        if not quote.symbol or not isinstance(quote.lot_size, int) or quote.lot_size <= 0:
            return f"{phase}_contract_or_lot_invalid", []
        bid, ask = _finite(quote.bid, "bid", positive=True), _finite(quote.ask, "ask", positive=True)
        if bid > ask or quote.bid_depth < quote.lot_size or quote.ask_depth < quote.lot_size:
            return f"{phase}_book_not_executable_for_full_lot", []
        observed, received = _stamp(quote.observed_at, "observed_at"), _stamp(quote.received_at, "received_at")
        if observed > received or received > decision_at:
            return f"{phase}_future_packet_or_timestamp_order_invalid", []
        if decision_at - received > max_age or decision_at - observed > max_age:
            return f"{phase}_quote_stale", []
        normalized.append(quote)
    observed = [_stamp(quote.observed_at, "observed_at") for quote in normalized]
    if max(observed) - min(observed) > max_sync:
        return f"{phase}_legs_unsynchronised", []
    lots = {quote.lot_size for quote in normalized}
    if len(lots) != 1:
        return f"{phase}_leg_lot_mismatch", []
    return None, normalized


def replay_intraday_debit_spread(
    *, underlying: str, expiry: str, entry_at: datetime, entry_quotes: list[LegQuote],
    exit_at: datetime | None, exit_quotes: list[LegQuote], fee_per_leg_rs: float,
    entry_deadline_minute: int = 14 * 60 + 45, management_deadline_minute: int = 15 * 60 + 15,
    max_quote_age: timedelta = timedelta(seconds=30), max_leg_sync: timedelta = timedelta(seconds=5),
) -> ReplayResult:
    """Replay a one-lot debit spread with real bid/ask/depth requirements.

    The method has no parameter-searching and does not infer a fill from LTP,
    an expiry payoff, one leg, or a later packet. It produces a stable evidence
    hash for a frozen dataset/configuration combination.
    """
    entry_clock = _stamp(entry_at, "entry_at")
    exit_clock = _stamp(exit_at, "exit_at") if exit_at is not None else None
    if not expiry:
        raise ReplayInputError("expiry is required")
    if max_quote_age <= timedelta(0) or max_leg_sync <= timedelta(0):
        raise ReplayInputError("quote age and leg synchronisation bounds must be positive")
    fee = _finite(fee_per_leg_rs, "fee_per_leg_rs")
    if fee < 0:
        raise ReplayInputError("fee_per_leg_rs must be nonnegative")
    entry_minute = entry_clock.hour * 60 + entry_clock.minute
    digest = _digest(underlying=underlying, expiry=expiry, entry_at=entry_clock, exit_at=exit_clock,
                     entry=entry_quotes, exit_=exit_quotes, fee_per_leg_rs=fee)
    if entry_minute > entry_deadline_minute:
        return ReplayResult("REJECTED", "entry_after_intraday_deadline", None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat() if exit_clock else None, digest)
    entry_error, entry = _validate_pair(underlying, entry_quotes, decision_at=entry_clock,
                                        max_age=max_quote_age, max_sync=max_leg_sync, phase="entry")
    if entry_error:
        return ReplayResult("NO_FILL", entry_error, None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat() if exit_clock else None, digest)
    if exit_clock is None:
        return ReplayResult("UNRESOLVED", "exit_observation_missing", None, None, None, None,
                            entry_clock.isoformat(), None, digest)
    if exit_clock.date() != entry_clock.date() or exit_clock < entry_clock:
        return ReplayResult("REJECTED", "overnight_or_reverse_exit_rejected", None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat(), digest)
    if exit_clock.hour * 60 + exit_clock.minute > management_deadline_minute:
        return ReplayResult("REJECTED", "exit_after_intraday_management_deadline", None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat(), digest)
    exit_error, exit_pair = _validate_pair(underlying, exit_quotes, decision_at=exit_clock,
                                           max_age=max_quote_age, max_sync=max_leg_sync, phase="exit")
    if exit_error:
        return ReplayResult("UNRESOLVED", exit_error, None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat(), digest)
    if {(q.side, q.symbol, q.lot_size) for q in entry} != {(q.side, q.symbol, q.lot_size) for q in exit_pair}:
        return ReplayResult("UNRESOLVED", "exit_contract_identity_mismatch", None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat(), digest)
    lot = entry[0].lot_size
    entry_buy = next(item for item in entry if item.side == "BUY")
    entry_sell = next(item for item in entry if item.side == "SELL")
    exit_buy = next(item for item in exit_pair if item.side == "BUY")
    exit_sell = next(item for item in exit_pair if item.side == "SELL")
    debit = (float(entry_buy.ask) - float(entry_sell.bid)) * lot
    credit = (float(exit_buy.bid) - float(exit_sell.ask)) * lot
    if debit <= 0:
        return ReplayResult("NO_FILL", "entry_debit_nonpositive", None, None, None, None,
                            entry_clock.isoformat(), exit_clock.isoformat(), digest)
    costs = fee * 4  # entry and exit across both legs
    return ReplayResult("CLOSED", "two_leg_executable", round(debit, 4), round(credit, 4), round(costs, 4),
                        round(credit - debit - costs, 4), entry_clock.isoformat(), exit_clock.isoformat(), digest)
