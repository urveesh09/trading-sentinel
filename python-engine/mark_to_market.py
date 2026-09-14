"""[WORKFLOW-F 2026-09-13] Open mark-to-market valuation (Phase 3).

Implements plan section 10.4 -- "Audit funding, expenses, partial
closes, rejected/cancelled orders and open mark-to-market
independently." The function is purely read-only: it computes
unrealised P&L on every open position (equity, F&O, and F&O
debit/credit structures) using a caller-supplied quote cache, and
returns an aggregate plus per-row breakdown with named freshness
buckets.

The reason this module exists at all: ``operator_status.py:257`` and
``penny_hourly_report.py:66`` consume an ``unrealised_pnl`` field
that no production code path produces. ``main.py:1599`` previously
read ``p.get("current_price", 0.0)`` from each penny position and
returned 0.0 because the ``positions`` table has no ``current_price``
column. The hourly report has been reporting "Rs +0" unrealised P&L
silently. F3 closes the producer side; the consumer-side wiring is
deferred to a follow-up commit that calls ``mark_open_positions``
from the orchestrator tick (which already has Kite open).

[DESIGN-INVARIANTS 2026-09-13]
  1. Pure function. No I/O, no network, no DB write.
  2. Caller supplies the quote cache -- the orchestrator owns the
     Kite call; this module only reads.
  3. Quotes older than ``MAX_QUOTE_AGE_SECONDS`` are rejected with
     QUOTE_STALE; they do not silently become 0.
  4. A missing token (no quote at all) is QUOTE_UNAVAILABLE, not 0.
  5. NaN/Inf in any numeric field raises ``ValueError`` (programmer
     error, not a runtime condition).
  6. Equity positions: ``pnl = (current_price - entry_price) * shares``.
     F&O positions: ``pnl = (current_premium - entry_premium) * qty
     * lot_size`` (premium multiplier). Multi-leg structures:
     ``pnl = sum(per_leg_mark) - net_premium_rs``.
  7. No UPDATE/DELETE on positions / fno_positions / fno_dr_positions.
     MTM is read-only; the audit doc explicitly disallows ledger
     mutation in this workflow.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


# Quote freshness budget: a mark older than this is stale, not 0.
# 5 minutes matches the penny scanner cron interval; anything older
# than that means the orchestrator has not refreshed and the operator
# should be told.
MAX_QUOTE_AGE_SECONDS = 300


class QuoteStatus(Enum):
    """How an open position's mark was sourced."""

    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class QuoteTick:
    """One cached quote observation.

    ``as_of`` is a timezone-aware datetime; the orchestrator that
    populates this cache converts to UTC once and stamps the tick.
    The mark-to-market check treats naive datetimes as ``UNAVAILABLE``
    because comparing a naive wall-clock to a tz-aware one would
    silently pass on systems where ``datetime.now()`` returns naive.
    """

    last_price: float
    as_of: datetime

    @classmethod
    def build(cls, last_price: float, as_of: datetime) -> "QuoteTick":
        """Construct with validation -- refuse NaN/Inf and naive datetimes."""
        if not math.isfinite(float(last_price)):
            raise ValueError(
                f"QuoteTick.last_price must be finite, got {last_price!r}"
            )
        if as_of is None:
            raise ValueError("QuoteTick.as_of must not be None")
        if as_of.tzinfo is None or as_of.tzinfo.utcoffset(as_of) is None:
            raise ValueError(
                "QuoteTick.as_of must be timezone-aware (got naive datetime)"
            )
        return cls(last_price=float(last_price), as_of=as_of)


@dataclass(frozen=True)
class PositionMark:
    """One row of the mark-to-market output."""

    subsystem: str          # "EQUITY" | "FNO" | "FNO_DR"
    source: str
    identity: str           # ticker / tradingsymbol / structure id
    entry_cost: float       # rupees invested at entry
    mark_price: float       # current LTP (0.0 if UNAVAILABLE)
    unrealised_pnl: float   # signed rupees; NaN/Inf blocked at input
    quote_status: QuoteStatus
    quote_age_seconds: Optional[int]  # None if UNAVAILABLE
    notes: str = ""

    def summary(self) -> str:
        sign = "+" if self.unrealised_pnl >= 0 else ""
        age = (
            f"{self.quote_age_seconds}s"
            if self.quote_age_seconds is not None
            else "n/a"
        )
        return (
            f"[{self.subsystem}/{self.source}/{self.identity}] "
            f"entry=Rs {self.entry_cost:.0f} mark=Rs {self.mark_price:.2f} "
            f"pnl={sign}Rs {self.unrealised_pnl:.0f} "
            f"quote={self.quote_status.value} age={age}"
        )


@dataclass(frozen=True)
class OpenMarkToMarket:
    """Aggregate mark-to-market result across all open positions."""

    marks: List[PositionMark] = field(default_factory=list)
    as_of: Optional[datetime] = None

    @property
    def total_unrealised_pnl(self) -> float:
        """Partial subtotal only; use complete_unrealised_pnl for accounting."""
        return sum(m.unrealised_pnl for m in self.marks)

    @property
    def complete_unrealised_pnl(self) -> Optional[float]:
        """Unknown if any position is unpriced, stale or unsupported."""
        if any(mark.quote_status != QuoteStatus.FRESH for mark in self.marks):
            return None
        return self.total_unrealised_pnl

    @property
    def count_by_status(self) -> Dict[QuoteStatus, int]:
        out: Dict[QuoteStatus, int] = {s: 0 for s in QuoteStatus}
        for m in self.marks:
            out[m.quote_status] += 1
        return out

    @property
    def count_by_subsystem(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for m in self.marks:
            out[m.subsystem] = out.get(m.subsystem, 0) + 1
        return out

    def filter_by_source(self, source: str) -> "OpenMarkToMarket":
        return OpenMarkToMarket(
            marks=[m for m in self.marks if m.source == source],
            as_of=self.as_of,
        )


# ---- equity MTM -----------------------------------------------------------------

def _validate_equity_row(row: Mapping[str, Any]) -> None:
    """Validate the equity-row shape the caller supplies.

    Equity rows come from ``positions`` (see ``position_tracker.py``).
    The relevant fields for MTM are ``ticker``, ``shares``, ``entry_price``,
    and ``source``. The function does NOT require ``status`` to be
    'OPEN' -- the caller's row filter has already handled that.
    """
    for required in ("ticker", "shares", "entry_price", "source"):
        if required not in row:
            raise ValueError(f"equity row missing required field {required!r}")
    # Numeric field validation. ``ticker`` and ``source`` are strings;
    # only ``shares`` (int) and ``entry_price`` (real) need a numeric
    # check.
    shares = row["shares"]
    if isinstance(shares, bool) or not isinstance(shares, int) or shares < 0:
        raise ValueError(
            f"equity row 'shares' must be a non-negative int, got {shares!r}"
        )
    entry_price = row["entry_price"]
    try:
        entry_price_f = float(entry_price)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"equity row 'entry_price' must be a real number, "
            f"got {entry_price!r}"
        ) from exc
    if not math.isfinite(entry_price_f):
        raise ValueError(
            f"equity row 'entry_price' must be finite, got {entry_price!r}"
        )
    # String fields are accepted as-is -- empty strings are rejected
    # at the mark step because they cannot match a quote.
    if not isinstance(row["ticker"], str) or not row["ticker"]:
        raise ValueError(
            f"equity row 'ticker' must be a non-empty string, "
            f"got {row['ticker']!r}"
        )
    if not isinstance(row["source"], str) or not row["source"]:
        raise ValueError(
            f"equity row 'source' must be a non-empty string, "
            f"got {row['source']!r}"
        )


def _mark_equity_row(
    row: Mapping[str, Any],
    quotes: Mapping[Any, QuoteTick],
    now_utc: datetime,
    freshness_seconds: int,
) -> PositionMark:
    """Mark a single equity row."""
    _validate_equity_row(row)
    ticker = str(row["ticker"])
    source = str(row["source"])
    shares = int(row["shares"])
    entry_price = float(row["entry_price"])
    entry_cost = entry_price * shares

    tick = quotes.get(ticker)
    if tick is None:
        return PositionMark(
            subsystem="EQUITY",
            source=source,
            identity=ticker,
            entry_cost=entry_cost,
            mark_price=0.0,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.UNAVAILABLE,
            quote_age_seconds=None,
            notes="no quote in cache for ticker",
        )

    age = (now_utc - tick.as_of).total_seconds()
    if age < 0 or age > freshness_seconds:
        return PositionMark(
            subsystem="EQUITY",
            source=source,
            identity=ticker,
            entry_cost=entry_cost,
            mark_price=tick.last_price,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.STALE,
            quote_age_seconds=int(age) if age >= 0 else None,
            notes=(
                f"quote age {int(age) if age >= 0 else 'negative'}s "
                f"exceeds freshness budget {freshness_seconds}s"
            ),
        )

    pnl = (tick.last_price - entry_price) * shares
    return PositionMark(
        subsystem="EQUITY",
        source=source,
        identity=ticker,
        entry_cost=entry_cost,
        mark_price=tick.last_price,
        unrealised_pnl=pnl,
        quote_status=QuoteStatus.FRESH,
        quote_age_seconds=int(age),
    )


# ---- F&O MTM --------------------------------------------------------------------

def _validate_fno_row(row: Mapping[str, Any]) -> None:
    """Validate the F&O-row shape.

    F&O rows come from ``fno_positions`` via
    ``fno_positions.open_positions()``. The relevant fields for MTM
    are ``tradingsymbol`` (or ``token``), ``qty``, ``lot_size``,
    ``entry_premium``, ``source``. The function refuses ``qty=0``
    (a fully-exited F&O position should never be in the open list,
    but if a stale row leaks through we mark it explicitly).
    """
    for required in (
        "tradingsymbol", "qty", "lot_size", "entry_premium", "source",
    ):
        if required not in row:
            raise ValueError(f"fno row missing required field {required!r}")
    if not isinstance(row["tradingsymbol"], str) or not row["tradingsymbol"]:
        raise ValueError(
            f"fno row 'tradingsymbol' must be a non-empty string, "
            f"got {row['tradingsymbol']!r}"
        )
    if not isinstance(row["source"], str) or not row["source"]:
        raise ValueError(
            f"fno row 'source' must be a non-empty string, "
            f"got {row['source']!r}"
        )
    qty = row["qty"]
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
        raise ValueError(
            f"fno row 'qty' must be a non-negative int, got {qty!r}"
        )
    lot_size = row["lot_size"]
    if (
        isinstance(lot_size, bool)
        or not isinstance(lot_size, int)
        or lot_size <= 0
    ):
        raise ValueError(
            f"fno row 'lot_size' must be a positive int, "
            f"got {lot_size!r}"
        )
    try:
        entry_premium = float(row["entry_premium"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"fno row 'entry_premium' must be a real number, "
            f"got {row['entry_premium']!r}"
        ) from exc
    if not math.isfinite(entry_premium):
        raise ValueError(
            f"fno row 'entry_premium' must be finite, got {entry_premium!r}"
        )


def _mark_fno_row(
    row: Mapping[str, Any],
    quotes: Mapping[Any, QuoteTick],
    now_utc: datetime,
    freshness_seconds: int,
) -> PositionMark:
    """Mark a single F&O row using the premium multiplier.

    ``fno_positions.qty`` is already the number of option contracts:
    its writer persists ``lots * lot_size``.  ``lot_size`` remains
    position metadata and must not be applied again.

    P&L formula:
        pnl = (current_premium - entry_premium) * qty
    """
    _validate_fno_row(row)
    tradingsymbol = str(row["tradingsymbol"])
    source = str(row["source"])
    qty = int(row["qty"])
    lot_size = int(row["lot_size"])
    entry_premium = float(row["entry_premium"])
    entry_cost = entry_premium * qty

    tick = quotes.get(tradingsymbol)
    if tick is None and "token" in row and row["token"]:
        try:
            tick = quotes.get(int(row["token"]))
        except (TypeError, ValueError):
            tick = None

    if tick is None:
        return PositionMark(
            subsystem="FNO",
            source=source,
            identity=tradingsymbol,
            entry_cost=entry_cost,
            mark_price=0.0,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.UNAVAILABLE,
            quote_age_seconds=None,
            notes="no quote in cache for tradingsymbol or token",
        )

    age = (now_utc - tick.as_of).total_seconds()
    if age < 0 or age > freshness_seconds:
        return PositionMark(
            subsystem="FNO",
            source=source,
            identity=tradingsymbol,
            entry_cost=entry_cost,
            mark_price=tick.last_price,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.STALE,
            quote_age_seconds=int(age) if age >= 0 else None,
            notes=(
                f"quote age {int(age) if age >= 0 else 'negative'}s "
                f"exceeds freshness budget {freshness_seconds}s"
            ),
        )

    pnl = (tick.last_price - entry_premium) * qty
    return PositionMark(
        subsystem="FNO",
        source=source,
        identity=tradingsymbol,
        entry_cost=entry_cost,
        mark_price=tick.last_price,
        unrealised_pnl=pnl,
        quote_status=QuoteStatus.FRESH,
        quote_age_seconds=int(age),
    )


# ---- F&O debit/credit MTM -------------------------------------------------------

def _validate_fno_dr_row(row: Mapping[str, Any]) -> None:
    """Validate the F&O debit/credit row.

    Rows come from ``fno_dr_book.open_structures``. For MTM the
    relevant fields are ``id`` (or ``kind`` for human-readable
    identity), ``legs_json`` (parsed JSON list of leg dicts),
    ``net_premium_rs``, ``source``. Each leg dict must carry
    ``tradingsymbol`` (or ``token``), ``qty``, ``entry_premium``,
    ``direction``.
    """
    for required in ("legs_json", "net_premium_rs", "source"):
        if required not in row:
            raise ValueError(f"fno_dr row missing required field {required!r}")
    if not isinstance(row["source"], str) or not row["source"]:
        raise ValueError(
            f"fno_dr row 'source' must be a non-empty string, "
            f"got {row['source']!r}"
        )
    try:
        net_premium = float(row["net_premium_rs"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"fno_dr row 'net_premium_rs' must be a real number, "
            f"got {row['net_premium_rs']!r}"
        ) from exc
    if not math.isfinite(net_premium):
        raise ValueError(
            f"fno_dr row 'net_premium_rs' must be finite, "
            f"got {net_premium!r}"
        )


def _mark_fno_dr_row(
    row: Mapping[str, Any],
    quotes: Mapping[Any, QuoteTick],
    now_utc: datetime,
    freshness_seconds: int,
) -> PositionMark:
    """Mark a multi-leg F&O structure.

    Each leg is marked against the quote cache individually. The
    structure's P&L is the sum of leg marks minus the
    ``net_premium_rs`` paid at entry. If ANY leg's quote is stale or
    unavailable, the structure is conservatively marked UNKNOWN
    (one bad leg makes the whole mark unsound) and the row is
    returned with ``quote_status`` reflecting the *worst* leg.

    This conservative behaviour is the explicit senior-dev
    choice: marking a 4-leg structure as FRESH when one leg is
    STALE would be the same kind of silent-zero bug F3 is closing.
    """
    import json as _json  # local import keeps the public surface tight
    _validate_fno_dr_row(row)
    source = str(row["source"])
    structure_id = str(row.get("id", row.get("kind", "fno_dr")))
    try:
        legs = _json.loads(str(row["legs_json"]))
    except (TypeError, ValueError):
        return PositionMark(
            subsystem="FNO_DR",
            source=source,
            identity=structure_id,
            entry_cost=float(row["net_premium_rs"]),
            mark_price=0.0,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.UNAVAILABLE,
            quote_age_seconds=None,
            notes="legs_json unparseable",
        )
    if not isinstance(legs, list) or not legs:
        return PositionMark(
            subsystem="FNO_DR",
            source=source,
            identity=structure_id,
            entry_cost=float(row["net_premium_rs"]),
            mark_price=0.0,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.UNAVAILABLE,
            quote_age_seconds=None,
            notes="legs_json empty or not a list",
        )

    # The owning fno_dr_book persists only opt_type/strike/quantity/premium.
    # That cannot identify a broker instrument later, so never manufacture a
    # symbol from it: distinguish this unsupported row from a missing quote.
    if any(
        not isinstance(leg, dict)
        or (not leg.get("tradingsymbol") and not leg.get("token"))
        for leg in legs
    ):
        return PositionMark(
            subsystem="FNO_DR",
            source=source,
            identity=structure_id,
            entry_cost=float(row["net_premium_rs"]),
            mark_price=0.0,
            unrealised_pnl=0.0,
            quote_status=QuoteStatus.UNSUPPORTED,
            quote_age_seconds=None,
            notes="stored legs lack immutable tradingsymbol or token",
        )

    net_premium = float(row["net_premium_rs"])
    leg_pnl = 0.0
    worst_status = QuoteStatus.FRESH
    worst_age: Optional[int] = 0
    notes: List[str] = []
    for leg in legs:
        if not isinstance(leg, dict):
            notes.append("non-dict leg skipped")
            worst_status = QuoteStatus.UNAVAILABLE
            continue
        sym = leg.get("tradingsymbol")
        token = leg.get("token")
        try:
            qty = int(leg.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        try:
            lot_size = int(leg.get("lot_size", 1)) or 1
        except (TypeError, ValueError):
            lot_size = 1
        try:
            entry_premium = float(leg.get("entry_premium", 0.0))
            direction = float(leg.get("direction", 1.0)) or 1.0
        except (TypeError, ValueError):
            entry_premium = 0.0
            direction = 1.0

        tick = None
        if sym:
            tick = quotes.get(sym)
        if tick is None and token:
            try:
                tick = quotes.get(int(token))
            except (TypeError, ValueError):
                tick = None

        if tick is None:
            worst_status = QuoteStatus.UNAVAILABLE
            notes.append(f"leg {sym or token}: quote unavailable")
            continue
        age = (now_utc - tick.as_of).total_seconds()
        if age < 0 or age > freshness_seconds:
            worst_status = QuoteStatus.STALE
            if worst_age is None or age > worst_age:
                worst_age = int(age) if age >= 0 else None
            notes.append(f"leg {sym or token}: quote stale ({int(age)}s)")
            continue
        leg_pnl += (tick.last_price - entry_premium) * qty * lot_size * direction
        if worst_age is None or int(age) > worst_age:
            worst_age = int(age)

    if worst_status != QuoteStatus.FRESH:
        return PositionMark(
            subsystem="FNO_DR",
            source=source,
            identity=structure_id,
            entry_cost=net_premium,
            mark_price=0.0,
            unrealised_pnl=0.0,
            quote_status=worst_status,
            quote_age_seconds=worst_age,
            notes="; ".join(notes) if notes else "no legs marked",
        )

    return PositionMark(
        subsystem="FNO_DR",
        source=source,
        identity=structure_id,
        entry_cost=net_premium,
        mark_price=0.0,
        unrealised_pnl=leg_pnl - net_premium,
        quote_status=QuoteStatus.FRESH,
        quote_age_seconds=worst_age or 0,
    )


# ---- public surface -------------------------------------------------------------

def mark_open_positions(
    *,
    equity_rows: Sequence[Mapping[str, Any]],
    fno_rows: Sequence[Mapping[str, Any]],
    fno_dr_rows: Sequence[Mapping[str, Any]],
    quotes: Mapping[Any, QuoteTick],
    now_utc: Optional[datetime] = None,
    freshness_seconds: int = MAX_QUOTE_AGE_SECONDS,
) -> OpenMarkToMarket:
    """Compute mark-to-market across all open positions.

    Each subsystem is marked independently; an UNAVAILABLE row in one
    subsystem does not affect the others. The aggregate is the sum of
    per-row marks. Missing rows contribute zero to that legacy partial
    subtotal, which is NOT a conservative loss estimate. Accounting/report
    callers must use complete_unrealised_pnl, which is unknown unless all
    marks are fresh, and inspect quote_status for the missing positions.
    """
    if freshness_seconds < 0:
        raise ValueError(
            f"freshness_seconds must be non-negative, got {freshness_seconds}"
        )
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None or now_utc.tzinfo.utcoffset(now_utc) is None:
        raise ValueError(
            f"now_utc must be timezone-aware, got {now_utc!r}"
        )

    marks: List[PositionMark] = []
    for row in equity_rows:
        marks.append(
            _mark_equity_row(row, quotes, now_utc, freshness_seconds)
        )
    for row in fno_rows:
        marks.append(
            _mark_fno_row(row, quotes, now_utc, freshness_seconds)
        )
    for row in fno_dr_rows:
        marks.append(
            _mark_fno_dr_row(row, quotes, now_utc, freshness_seconds)
        )
    return OpenMarkToMarket(marks=marks, as_of=now_utc)


__all__ = [
    "MAX_QUOTE_AGE_SECONDS",
    "OpenMarkToMarket",
    "PositionMark",
    "QuoteStatus",
    "QuoteTick",
    "mark_open_positions",
]
