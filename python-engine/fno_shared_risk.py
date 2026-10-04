"""Shared, fail-closed F&O paper-risk evidence and reservations.

This module is intentionally the only place that may combine the directional
``fno_positions`` and defined-risk ``fno_dr_positions`` books for an F&O
admission decision.  The books retain their own lifecycle/settlement writers;
this module does not invent a fill, close a position, or release exposure on a
timer.  In particular, an ``UNRESOLVED`` structure and an interrupted entry
reservation remain unavailable capital until an explicit, durable resolution.

F0-A/B provide the typed snapshot and atomic reservation primitive; the paper
position writers consume the reservation with their position insert.  F0-C
adds the common entry-policy receipt: exact source-scoped `TRADE_CLOSED` cash
from either book drives day/week/month, drawdown and consecutive-loss brakes.
Both paper admissions consult it and the reservation transaction checks it
again before consuming capacity.  Entry halts never suppress management or
exit/settlement work.

F0-D validates an open single-leg residual after a broker-verified partial
exit against its ordered recovery records, linked exact ledger cash, immutable
initial quantity/loss and pro-rata remaining catastrophe loss.  A discrepancy
does not guess a release: it makes the shared view unavailable for new entry.

F0-E also checks that the retained broker-evidence digest, immutable recovery
economics and ledger cash agree, while the quantity/loss entry baselines are
immutable after they are written. Cost schedules can change, so this read
validates the recorded atomic cost/P&L arithmetic rather than recalculating
with later settings.

F0-R1 keeps the fee reserve after a reservation is consumed. Each OPEN or
UNRESOLVED row contributes its structural loss plus the fee reserve frozen
at insert (single-leg ``risk_fee_reserve_rupees``; DR ``entry_cost_rs``).
A verified partial keeps the full frozen fee (fees rise with quantity), and
a terminal close hands the exposure over to exact ledger cash. A missing fee
reserve, or a single-leg loss below its paid premium at risk, fails closed.

F0-R2 separates the idempotent reservation receipt from the one-time right
to dispatch. ``claim_shared_fno_entry_dispatch`` re-reads the entry policy
and records exactly one DISPATCHING owner per reservation; only that owner
may call an executor. Outcomes are typed: capacity is released only for a
verified no-dispatch, explicit broker rejection or verified terminal zero
fill. Partial, unknown or unrecorded fills keep the whole reservation until
an operator reconciles them with evidence. A reservation-backed position can
only be inserted against a claim, and nothing expires on a timer.

F0-R3 reads one canonical, validated cash ledger for both the view and the
policy: TRADE_PARTIAL and TRADE_CLOSED are trade cash (counted once); cash
must be finite, timezone-aware, unique per origin/generation and not after
the observation instant (wall clock by default); day/week/month buckets are
bounded by the policy day; settled positions must have their exact cash;
and the consecutive-loss brake counts completed trades, not cash rows.

F0-R4 re-derives every open partial's receipt from its retained broker
packet with the same function the live verifier uses (never calling the
broker), binds it to the position's immutable entry premium and symbol, and
re-computes its charges from the frozen cost snapshot stored with it.

F0-R5 applies the books' existing occupancy limits (single-leg concurrency,
trades/day, open-premium cap and no-pyramid; one DR structure at a time)
inside the claim transaction, counting positions *and* in-flight claims, so
concurrent admissions can no longer each pass a stale pre-read.
Positive manual cash is never entry capacity; negative manual cash reduces
equity. Unknown event types fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Optional, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

import aiosqlite

from fno_exit_evidence import validate_retained_exit_receipt


_RESERVATION_DDL = """
CREATE TABLE IF NOT EXISTS fno_risk_reservations (
    reservation_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    book TEXT NOT NULL CHECK (book IN ('SINGLE_LEG', 'DEFINED_RISK')),
    state TEXT NOT NULL CHECK (state IN ('RESERVED', 'CONSUMED', 'RELEASED')),
    worst_case_cash_rs REAL NOT NULL CHECK (worst_case_cash_rs > 0),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    position_ref TEXT,
    resolution_reason TEXT
)
"""

_DISPATCH_DDL = """
CREATE TABLE IF NOT EXISTS fno_entry_dispatches (
    reservation_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    book TEXT NOT NULL CHECK (book IN ('SINGLE_LEG', 'DEFINED_RISK')),
    owner TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('DISPATCHING', 'FILLED', 'RELEASED', 'UNRESOLVED')),
    claimed_at TEXT NOT NULL,
    outcome TEXT,
    order_id TEXT,
    evidence_json TEXT,
    evidence_sha256 TEXT,
    operator TEXT,
    position_ref TEXT,
    resolved_at TEXT,
    tradingsymbol TEXT,
    planned_premium_rs REAL,
    entry_day TEXT
)
"""

# [F0-R5] Occupancy facts recorded by claims made before R5 added them.
_DISPATCH_R5_COLUMNS = (("tradingsymbol", "TEXT"), ("planned_premium_rs", "REAL"),
                        ("entry_day", "TEXT"))

# Terminal claims are evidence; a claim can never return to DISPATCHING or
# change identity, and no claim row may be deleted.
_DISPATCH_UPDATE_GUARD_DDL = """
CREATE TRIGGER IF NOT EXISTS fno_entry_dispatches_transition_guard
BEFORE UPDATE ON fno_entry_dispatches
FOR EACH ROW WHEN
    OLD.state IN ('FILLED', 'RELEASED')
    OR (NEW.state = 'DISPATCHING' AND OLD.state <> 'DISPATCHING')
    OR NEW.owner IS NOT OLD.owner
    OR NEW.reservation_key IS NOT OLD.reservation_key
    OR NEW.source IS NOT OLD.source
    OR NEW.book IS NOT OLD.book
    OR NEW.tradingsymbol IS NOT OLD.tradingsymbol
    OR NEW.planned_premium_rs IS NOT OLD.planned_premium_rs
    OR NEW.entry_day IS NOT OLD.entry_day
BEGIN
    SELECT RAISE(ABORT, 'fno entry dispatch evidence is immutable');
END
"""

_DISPATCH_NO_DELETE_DDL = """
CREATE TRIGGER IF NOT EXISTS fno_entry_dispatches_no_delete
BEFORE DELETE ON fno_entry_dispatches
BEGIN
    SELECT RAISE(ABORT, 'fno entry dispatch evidence is immutable');
END
"""

# Executor/broker outcomes that prove no exposure was created.
DISPATCH_RELEASE_OUTCOMES = frozenset({"no_dispatch", "rejected", "zero_fill_verified"})
# Outcomes that may hide a fill: the whole reservation is retained.
DISPATCH_RETAIN_OUTCOMES = frozenset({"partial", "unknown", "filled_unrecorded"})
RECONCILE_OUTCOMES = frozenset({"zero_fill_verified", "no_order_verified"})
_MAX_EVIDENCE_BYTES = 65536

_IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class SharedFnoRiskPolicy:
    """Explicit entry-brake policy shared by both F&O paper books.

    These defaults deliberately reproduce the already-shipped directional
    brakes; F0-C changes their evidence scope, not their level.  The caller
    may pass a frozen policy receipt when it needs to bind a decision to
    non-default settings.
    """

    daily_loss_pct: float = 0.06
    weekly_loss_pct: float = 0.12
    monthly_loss_pct: float = 0.20
    drawdown_pct: float = 0.25
    max_consecutive_losses: int = 6


@dataclass(frozen=True)
class SharedFnoEntryPolicyDecision:
    """One source-scoped, fail-closed entry-policy receipt.

    ``active_halts`` is deliberately only an entry admission result.  It has
    no bearing on position management or exit/settlement authority.
    """

    allowed: bool
    reason: str
    active_halts: tuple[str, ...]
    day_pnl_rs: Optional[float]
    week_pnl_rs: Optional[float]
    month_pnl_rs: Optional[float]
    view: SharedFnoRiskView
    # [F0-R3] Completed-trade loss streak, observation instant and legacy
    # cash rows that carry no trade identity (each counted as one trade).
    completed_loss_streak: Optional[int] = None
    observed_at: Optional[str] = None
    legacy_unlinked_cash_events: int = 0


@dataclass(frozen=True)
class SharedFnoRiskView:
    """A source-scoped F&O capital view built from durable evidence only.

    ``available`` is false rather than zero when source tables are absent,
    malformed, or contain non-finite economic values.  Treating such a state
    as a zero-exposure book would turn missing evidence into buying capacity.
    """

    source: str
    pool_rs: float
    realised_pnl_rs: float
    equity_rs: float
    open_worst_case_cash_rs: float
    reserved_worst_case_cash_rs: float
    available_worst_case_cash_rs: Optional[float]
    single_leg_open_count: int
    defined_risk_open_count: int
    reservation_count: int
    available: bool
    reason: str = ""
    # [F0-R1] Fee portion already included in ``open_worst_case_cash_rs``.
    open_fee_reserve_rs: float = 0.0
    # [F0-R2] Claims still DISPATCHING or UNRESOLVED (their reservations are
    # retained in ``reserved_worst_case_cash_rs``).
    unresolved_entry_dispatch_count: int = 0
    # [F0-R3] Positive manual cash excluded from equity (never capacity) and
    # closed rows that predate exact settlement lineage.
    excluded_positive_manual_cash_rs: float = 0.0
    legacy_unlinked_closed_positions: int = 0


@dataclass(frozen=True)
class SharedFnoAdmission:
    """Result of attempting to reserve worst-case cash for one new entry.

    ``allowed`` means the reservation exists; it is *not* permission to
    dispatch an order. Only a granted ``SharedFnoDispatchClaim`` is.
    """

    allowed: bool
    reason: str
    view: SharedFnoRiskView


@dataclass(frozen=True)
class EntryOccupancy:
    """The book's *existing* occupancy limits, re-applied inside the claim.

    Single-leg: ``max_open`` (FNO_MAX_CONCURRENT), ``max_trades_per_day``,
    ``max_open_premium_rs`` (FNO_MAX_OPEN_PREMIUM_PCT x pool) and
    ``no_pyramid`` for ``tradingsymbol``. Defined-risk: ``max_open`` (one
    structure at a time). ``None`` limits are not applied.
    """

    entry_day: date
    max_open: int
    tradingsymbol: Optional[str] = None
    planned_premium_rs: float = 0.0
    max_trades_per_day: Optional[int] = None
    max_open_premium_rs: Optional[float] = None
    no_pyramid: bool = False


@dataclass(frozen=True)
class SharedFnoDispatchClaim:
    """The one-time right to dispatch the entry bound to a reservation."""

    granted: bool
    reason: str
    owner: Optional[str]
    view: SharedFnoRiskView


def _finite_non_negative(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _unavailable(source: str, pool_rs: float, reason: str) -> SharedFnoRiskView:
    return SharedFnoRiskView(
        source=source,
        pool_rs=pool_rs,
        realised_pnl_rs=0.0,
        equity_rs=0.0,
        open_worst_case_cash_rs=0.0,
        reserved_worst_case_cash_rs=0.0,
        available_worst_case_cash_rs=None,
        single_leg_open_count=0,
        defined_risk_open_count=0,
        reservation_count=0,
        available=False,
        reason=reason,
    )


async def init_shared_fno_risk_db(db_path: str) -> None:
    """Install the additive reservation table without touching positions.

    This is deliberately separate from reads.  Reporting a risk view must not
    create a database or repair a missing production schema as a side effect.
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_RESERVATION_DDL)
        await db.execute(_DISPATCH_DDL)
        columns = {row[1] for row in await (await db.execute(
            "PRAGMA table_info(fno_entry_dispatches)")).fetchall()}
        for column, datatype in _DISPATCH_R5_COLUMNS:
            if column not in columns:
                await db.execute(f"ALTER TABLE fno_entry_dispatches ADD COLUMN {column} {datatype}")
        await db.execute(_DISPATCH_UPDATE_GUARD_DDL)
        await db.execute(_DISPATCH_NO_DELETE_DDL)
        await db.commit()


async def _table_exists(db: aiosqlite.Connection, name: str) -> bool:
    row = await (await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )).fetchone()
    return row is not None


def _whole_non_negative(value: object) -> Optional[int]:
    """Accept SQLite's integer quantities, never silently coerce fractions."""
    if type(value) is not int or value < 0:
        return None
    return value


def _finite_number(value: object) -> Optional[float]:
    """Accept finite scalar evidence, including a realised loss."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _recovery_evidence_is_intact(digest: object, raw: object) -> bool:
    """Check the bounded broker snapshot before trusting its recovery receipt."""
    if not isinstance(digest, str) or len(digest) != 64 or not isinstance(raw, str):
        return False
    encoded = raw.encode("utf-8")
    if len(encoded) > 65536:
        return False
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and hashlib.sha256(encoded).hexdigest() == digest


async def _validate_open_partial_exit_evidence(
    db: aiosqlite.Connection, *, source: str, open_positions: list[tuple],
) -> str:
    """Bind residual single-leg risk to durable partial-exit evidence.

    A recovery records the broker-confirmed filled/residual quantities and its
    exact ledger row in the same transaction as the position reduction. This
    read also verifies receipt hash/economics before it releases any residual
    capacity. It never changes recovery state or grants capacity on ambiguity.
    """
    positions = {int(row[0]): row for row in open_positions}
    if not positions:
        return ""
    marks = ",".join("?" for _ in positions)
    recoveries = await (await db.execute(
        "SELECT id,position_id,filled_qty,remaining_qty,entry_premium,fill_price,gross_pnl,costs,pnl,"
        "settlement_generation,ledger_id,broker_evidence_sha256,broker_evidence_json,"
        "account_id,order_id,intent_created_at,terminal_status,cost_snapshot_json "
        "FROM fno_exit_recoveries WHERE source=? AND position_id IN (" + marks + ") "
        "ORDER BY position_id,id",
        (source, *positions),
    )).fetchall()
    # [F0-R4] Entry identity/economics that every receipt must agree with.
    identity = {int(row[0]): (row[1], row[2]) for row in await (await db.execute(
        "SELECT id,tradingsymbol,entry_premium FROM fno_positions WHERE source=? AND id IN ("
        + marks + ")", (source, *positions),
    )).fetchall()}
    by_position: dict[int, list[tuple]] = {}
    for recovery in recoveries:
        position_id = _whole_non_negative(recovery[1])
        if position_id is None or position_id not in positions:
            return "invalid_partial_recovery_evidence"
        by_position.setdefault(position_id, []).append(recovery)

    for position_id, position in positions.items():
        _id, current_loss, current_qty, initial_qty, initial_loss, current_generation = position
        qty = _whole_non_negative(current_qty)
        original_qty = _whole_non_negative(initial_qty)
        original_loss = _finite_non_negative(initial_loss)
        current = _finite_non_negative(current_loss)
        position_generation = _whole_non_negative(current_generation)
        rows = by_position.get(position_id, [])
        if not rows:
            # A legacy/untouched row may not have the newer baselines. If it
            # does, it must still describe a wholly open generation; otherwise
            # a deleted partial receipt could masquerade as fresh exposure.
            populated = (qty is not None and original_qty is not None
                         and original_loss is not None and current is not None
                         and position_generation is not None)
            if populated and (qty != original_qty or position_generation != 0 or not math.isclose(
                    current, original_loss, rel_tol=0.0, abs_tol=0.01)):
                return "invalid_partial_recovery_evidence"
            continue
        if qty is None or qty <= 0 or original_qty is None or original_qty <= 0 \
                or qty > original_qty or original_loss is None or current is None \
                or position_generation is None:
            return "invalid_partial_recovery_evidence"
        expected_remaining = original_qty
        expected_generation = 0
        symbol, position_entry = identity.get(position_id, (None, None))
        position_trade_ids: set[str] = set()
        for recovery in rows:
            (_recovery_id, _position_id, filled_raw, remaining_raw, entry_raw, fill_raw,
             gross_raw, costs_raw, pnl_raw, generation_raw, ledger_id,
             evidence_digest, evidence_json, account_id, order_id, intent_created_at,
             terminal_status, cost_snapshot_json) = recovery
            filled = _whole_non_negative(filled_raw)
            remaining = _whole_non_negative(remaining_raw)
            generation = _whole_non_negative(generation_raw)
            if filled is None or remaining is None or generation is None \
                    or filled + remaining != expected_remaining \
                    or not _recovery_evidence_is_intact(evidence_digest, evidence_json):
                return "invalid_partial_recovery_evidence"
            # F0-R4: re-derive the receipt from its retained broker packet and
            # bind it to the position's entry economics and frozen charges.
            reason, trade_ids = validate_retained_exit_receipt(
                {"broker_evidence_json": evidence_json, "broker_evidence_sha256": evidence_digest,
                 "account_id": account_id, "order_id": order_id,
                 "intent_created_at": intent_created_at, "terminal_status": terminal_status,
                 "filled_qty": filled, "remaining_qty": remaining, "entry_premium": entry_raw,
                 "fill_price": fill_raw, "costs": costs_raw,
                 "cost_snapshot_json": cost_snapshot_json},
                source=source, tradingsymbol=str(symbol or ""), position_entry_premium=position_entry,
            )
            if reason:
                return reason
            if position_trade_ids & set(trade_ids):
                return "recovery_payload_mismatch"
            position_trade_ids |= set(trade_ids)
            if filled:
                expected_generation += 1
                entry = _finite_number(entry_raw)
                fill = _finite_number(fill_raw)
                gross = _finite_number(gross_raw)
                costs = _finite_non_negative(costs_raw)
                recorded_pnl = _finite_number(pnl_raw)
                if (generation != expected_generation or ledger_id is None
                        or entry is None or entry <= 0 or fill is None or fill <= 0 or gross is None
                        or costs is None or recorded_pnl is None
                        or not math.isclose(gross, (fill - entry) * filled,
                                            rel_tol=0.0, abs_tol=0.01)
                        or not math.isclose(recorded_pnl, gross - costs,
                                            rel_tol=0.0, abs_tol=0.01)):
                    return "invalid_partial_recovery_evidence"
                ledger = await (await db.execute(
                    "SELECT source,event_type,origin_ref,settlement_generation,pnl "
                    "FROM bankroll_ledger WHERE id=?", (ledger_id,)
                )).fetchone()
                if (ledger is None or ledger[0] != source or ledger[1] != "TRADE_CLOSED"
                        or ledger[2] != f"fno_position:{position_id}"
                        or _whole_non_negative(ledger[3]) != generation
                        or _finite_number(ledger[4]) is None
                        or not math.isclose(float(ledger[4]), recorded_pnl,
                                            rel_tol=0.0, abs_tol=0.01)):
                    return "invalid_partial_recovery_evidence"
            elif (generation != expected_generation or ledger_id is not None
                  or any(value is not None for value in (fill_raw, gross_raw, costs_raw, pnl_raw))
                  or (entry_raw is not None and (
                      _finite_number(entry_raw) is None or float(entry_raw) <= 0))):
                # The real recovery writer retains entry premium as context
                # even when a terminal order filled nothing. It is not cash
                # or a release: quantities/generation remain unchanged.
                return "invalid_partial_recovery_evidence"
            expected_remaining = remaining
        expected_loss = original_loss * expected_remaining / original_qty
        if (expected_remaining != qty or position_generation != expected_generation
                or not math.isclose(
                current, expected_loss, rel_tol=0.0, abs_tol=0.01)):
            return "invalid_partial_recovery_evidence"
    return ""


_TRADE_CASH_TYPES = frozenset({"TRADE_PARTIAL", "TRADE_CLOSED"})
_ZERO_CASH_TYPES = frozenset({"INITIAL", "TRADE_OPENED"})
_MANUAL_CASH_TYPES = frozenset({"MANUAL_DEPOSIT", "MANUAL_WITHDRAWAL", "MANUAL_ADJUSTMENT"})


@dataclass(frozen=True)
class _CashEvent:
    id: int
    at: datetime
    event_type: str
    pnl: float
    origin_ref: Optional[str]
    generation: Optional[int]


@dataclass(frozen=True)
class _CashLedger:
    trade_events: tuple
    trade_cash_rs: float
    negative_manual_cash_rs: float
    positive_manual_cash_rs: float
    legacy_unlinked_events: int      # no origin, or generation 0 (pre-exact lineage)


def _observation_instant(observed_at: Optional[datetime]) -> Optional[datetime]:
    instant = observed_at or datetime.now(timezone.utc)
    if not isinstance(instant, datetime) or instant.tzinfo is None:
        return None
    return instant.astimezone(timezone.utc)


async def _read_cash_ledger(
    db: aiosqlite.Connection, source: str, observed_at: datetime,
):
    """Validated canonical cash for ``source``; a reason string on failure."""
    rows = await (await db.execute(
        "SELECT id,timestamp,event_type,pnl,origin_ref,settlement_generation "
        "FROM bankroll_ledger WHERE source=?", (source,)
    )).fetchall()
    trade: list[_CashEvent] = []
    seen: set = set()
    trade_total = negative_manual = positive_manual = 0.0
    legacy = 0
    for event_id, stamp_raw, event_type, pnl_raw, origin, generation in rows:
        try:
            pnl = float(pnl_raw)
        except (TypeError, ValueError):
            pnl = float("nan")
        if not math.isfinite(pnl):
            return "nonfinite_realised_pnl"
        if event_type in _ZERO_CASH_TYPES:
            if pnl != 0.0:
                return "unclassified_cash_event"
            continue
        if event_type not in _TRADE_CASH_TYPES and event_type not in _MANUAL_CASH_TYPES:
            return "unclassified_cash_event"
        try:
            at = datetime.fromisoformat(str(stamp_raw))
        except (TypeError, ValueError):
            return "invalid_cash_event"
        if at.tzinfo is None:
            return "invalid_cash_event"
        if at.astimezone(timezone.utc) > observed_at:
            return "future_cash_event"
        if event_type in _MANUAL_CASH_TYPES:
            if pnl < 0:
                negative_manual += pnl
            else:
                positive_manual += pnl
            continue
        if origin is not None and type(generation) is int and generation >= 1:
            # Exact settlements are unique per origin/generation (the ledger
            # index only covers generation > 0; generation 0 is legacy).
            key = (origin, generation)
            if key in seen:
                return "duplicate_cash_event"
            seen.add(key)
        else:
            legacy += 1
        trade_total += pnl
        trade.append(_CashEvent(int(event_id), at, event_type, pnl, origin,
                                generation if type(generation) is int else None))
    if not all(math.isfinite(x) for x in (trade_total, negative_manual, positive_manual)):
        return "nonfinite_realised_pnl"
    return _CashLedger(tuple(trade), trade_total, negative_manual, positive_manual, legacy)


async def _settlement_cash_gap(db: aiosqlite.Connection, source: str, ledger: _CashLedger):
    """(reason, legacy_count): settled rows must carry their exact cash."""
    by_origin: dict[str, list] = {}
    for event in ledger.trade_events:
        if event.origin_ref is not None and event.generation is not None and event.generation >= 1:
            by_origin.setdefault(event.origin_ref, []).append(event.generation)
    legacy = 0
    single = await (await db.execute(
        "SELECT id,settlement_generation FROM fno_positions WHERE source=? AND status='CLOSED'",
        (source,),
    )).fetchall()
    for position_id, generation in single:
        if type(generation) is not int or generation < 1:
            legacy += 1
            continue
        if sorted(by_origin.get(f"fno_position:{position_id}", [])) != list(range(1, generation + 1)):
            return "missing_settlement_cash", legacy
    dr_columns = {row[1] for row in await (await db.execute(
        "PRAGMA table_info(fno_dr_positions)")).fetchall()}
    state_column = "settlement_state" if "settlement_state" in dr_columns else "NULL"
    defined = await (await db.execute(
        f"SELECT id,{state_column} FROM fno_dr_positions WHERE source=? AND status='CLOSED'",
        (source,),
    )).fetchall()
    for structure_id, state in defined:
        if state != "SETTLED":
            legacy += 1
            continue
        if by_origin.get(f"fno_dr_structure:{structure_id}") != [1]:
            return "missing_settlement_cash", legacy
    return "", legacy


async def _completed_trades(
    db: aiosqlite.Connection, source: str, ledger: _CashLedger,
) -> list[tuple[datetime, int, float]]:
    """(completion time, last id, net cash) per completed trade, newest first."""
    single = {f"fno_position:{row[0]}": row[1] for row in await (await db.execute(
        "SELECT id,status FROM fno_positions WHERE source=?", (source,))).fetchall()}
    defined = {f"fno_dr_structure:{row[0]}": row[1] for row in await (await db.execute(
        "SELECT id,status FROM fno_dr_positions WHERE source=?", (source,))).fetchall()}
    groups: dict[str, list[_CashEvent]] = {}
    trades: list[tuple[datetime, int, float]] = []
    for event in ledger.trade_events:
        if event.origin_ref is None:
            trades.append((event.at, event.id, event.pnl))     # legacy: one row, one trade
        else:
            groups.setdefault(event.origin_ref, []).append(event)
    for origin, events in groups.items():
        status = single.get(origin, defined.get(origin))
        if status is not None and status != "CLOSED":
            continue                                          # still open: not a completed trade
        trades.append((max(e.at for e in events), max(e.id for e in events),
                       sum(e.pnl for e in events)))
    trades.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return trades


async def _read_view(
    db: aiosqlite.Connection, source: str, pool_rs: float,
    observed_at: Optional[datetime] = None,
) -> SharedFnoRiskView:
    """Read one consistent view; caller owns the transaction boundary."""
    instant = _observation_instant(observed_at)
    if instant is None:
        return _unavailable(source, pool_rs, "invalid_observation_clock")
    required = (
        "bankroll_ledger", "fno_positions", "fno_dr_positions",
        "fno_exit_recoveries", "fno_risk_reservations", "fno_entry_dispatches",
    )
    missing = [name for name in required if not await _table_exists(db, name)]
    if missing:
        return _unavailable(source, pool_rs, "missing_required_table:" + ",".join(missing))

    # Validate individual rows instead of trusting SQLite's aggregate: an
    # invalid positive/negative pair must not cancel into apparent capacity.
    ledger = await _read_cash_ledger(db, source, instant)
    if isinstance(ledger, str):
        return _unavailable(source, pool_rs, ledger)
    gap, legacy_closed = await _settlement_cash_gap(db, source, ledger)
    if gap:
        return _unavailable(source, pool_rs, gap)
    # Positive manual cash is never entry capacity (no top-ups without an
    # explicit owner policy); negative manual cash is real and reduces equity.
    realised_pnl = ledger.trade_cash_rs + ledger.negative_manual_cash_rs

    single_columns = {row[1] for row in await (await db.execute(
        "PRAGMA table_info(fno_positions)")).fetchall()}
    if "risk_fee_reserve_rupees" not in single_columns:
        return _unavailable(source, pool_rs, "single_leg_fee_reserve_unbound")
    single_rows = await (await db.execute(
        "SELECT id,max_loss_rupees,qty,initial_qty,initial_max_loss_rupees,settlement_generation,"
        "entry_premium,risk_fee_reserve_rupees "
        "FROM fno_positions "
        "WHERE source=? AND status IN ('OPEN', 'UNRESOLVED')", (source,)
    )).fetchall()
    single = [row[:6] for row in single_rows]
    defined = await (await db.execute(
        "SELECT max_loss_rs,entry_cost_rs FROM fno_dr_positions "
        "WHERE source=? AND status IN ('OPEN', 'UNRESOLVED')", (source,)
    )).fetchall()
    reserved = await (await db.execute(
        "SELECT worst_case_cash_rs FROM fno_risk_reservations "
        "WHERE source=? AND state='RESERVED'", (source,)
    )).fetchall()

    amounts: list[float] = []
    for label, rows, amount_index in (
        ("single_leg", single, 1),
        ("defined_risk", defined, 0),
        ("reservation", reserved, 0),
    ):
        for row in rows:
            amount = _finite_non_negative(row[amount_index])
            if amount is None:
                return _unavailable(source, pool_rs, f"invalid_{label}_worst_case_cash")
            amounts.append(amount)

    partial_evidence_reason = await _validate_open_partial_exit_evidence(
        db, source=source, open_positions=single,
    )
    if partial_evidence_reason:
        return _unavailable(source, pool_rs, partial_evidence_reason)

    # F0-R1: the fee reserve frozen at entry stays in exposure until the
    # terminal close; unavailable economics are never zero fees.
    fee_total = 0.0
    for row in single_rows:
        fee = _finite_non_negative(row[7])
        if fee is None:
            return _unavailable(source, pool_rs, "single_leg_fee_reserve_unbound")
        entry = _finite_non_negative(row[6])
        qty = _whole_non_negative(row[2])
        loss = _finite_non_negative(row[1])
        if entry is None or entry <= 0 or qty is None or loss is None \
                or loss + 0.01 < entry * qty:
            return _unavailable(source, pool_rs, "structural_loss_below_premium_at_risk")
        fee_total += fee
    for row in defined:
        fee = _finite_non_negative(row[1])
        if fee is None:
            return _unavailable(source, pool_rs, "defined_risk_fee_reserve_unbound")
        fee_total += fee

    single_total = sum(_finite_non_negative(row[1]) or 0.0 for row in single)
    defined_total = sum(_finite_non_negative(row[0]) or 0.0 for row in defined)
    reserved_total = sum(_finite_non_negative(row[0]) or 0.0 for row in reserved)
    unresolved_claims = (await (await db.execute(
        "SELECT COUNT(*) FROM fno_entry_dispatches "
        "WHERE source=? AND state IN ('DISPATCHING', 'UNRESOLVED')", (source,)
    )).fetchone())[0]
    equity = pool_rs + realised_pnl
    if not math.isfinite(equity):
        return _unavailable(source, pool_rs, "nonfinite_equity")
    available = equity - single_total - defined_total - fee_total - reserved_total
    return SharedFnoRiskView(
        source=source,
        pool_rs=pool_rs,
        realised_pnl_rs=realised_pnl,
        equity_rs=equity,
        open_worst_case_cash_rs=single_total + defined_total + fee_total,
        reserved_worst_case_cash_rs=reserved_total,
        available_worst_case_cash_rs=max(0.0, available),
        single_leg_open_count=len(single),
        defined_risk_open_count=len(defined),
        reservation_count=len(reserved),
        available=True,
        open_fee_reserve_rs=fee_total,
        unresolved_entry_dispatch_count=int(unresolved_claims),
        excluded_positive_manual_cash_rs=ledger.positive_manual_cash_rs,
        legacy_unlinked_closed_positions=legacy_closed,
    )


def _invalid_policy(policy: SharedFnoRiskPolicy) -> bool:
    percentages = (
        policy.daily_loss_pct, policy.weekly_loss_pct,
        policy.monthly_loss_pct, policy.drawdown_pct,
    )
    return (
        any(not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value)) or not 0 < float(value) <= 1
            for value in percentages)
        or type(policy.max_consecutive_losses) is not int
        or policy.max_consecutive_losses <= 0
    )


def policy_from_settings() -> SharedFnoRiskPolicy:
    """Freeze the existing configured brakes into an explicit receipt."""
    from config import settings
    return SharedFnoRiskPolicy(
        daily_loss_pct=float(settings.FNO_DAILY_KILL_PCT),
        weekly_loss_pct=float(settings.FNO_WEEKLY_KILL_PCT),
        monthly_loss_pct=float(settings.FNO_MONTHLY_KILL_PCT),
        drawdown_pct=0.25,  # existing directional FNO_MAX_DRAWDOWN_PCT policy
        max_consecutive_losses=int(settings.FNO_MAX_CONSECUTIVE_LOSSES),
    )


def _policy_unavailable(
    source: str, pool_rs: float, reason: str,
) -> SharedFnoEntryPolicyDecision:
    view = _unavailable(source, pool_rs, reason)
    return SharedFnoEntryPolicyDecision(
        allowed=False, reason=reason, active_halts=(reason,),
        day_pnl_rs=None, week_pnl_rs=None, month_pnl_rs=None, view=view,
    )


async def _read_entry_policy(
    db: aiosqlite.Connection, *, source: str, pool_rs: float,
    today_ist: date, policy: SharedFnoRiskPolicy,
    observed_at: Optional[datetime] = None,
) -> SharedFnoEntryPolicyDecision:
    """Evaluate policy under the caller's transaction boundary.

    Every F&O terminal/partial cash event shares the same source ledger, so
    this intentionally has no origin-prefix filter.  Position rows are not a
    fallback: a ledger timestamp/P&L ambiguity fails the new entry closed.
    """
    if _invalid_policy(policy):
        return _policy_unavailable(source, pool_rs, "invalid_shared_risk_policy")
    instant = _observation_instant(observed_at)
    if instant is None:
        return _policy_unavailable(source, pool_rs, "invalid_observation_clock")
    view = await _read_view(db, source, pool_rs, instant)
    if not view.available:
        return SharedFnoEntryPolicyDecision(
            allowed=False, reason=view.reason or "risk_view_unavailable",
            active_halts=(view.reason or "risk_view_unavailable",),
            day_pnl_rs=None, week_pnl_rs=None, month_pnl_rs=None, view=view,
        )

    ledger = await _read_cash_ledger(db, source, instant)
    if isinstance(ledger, str):          # the view validated it; defensive only
        return _policy_unavailable(source, pool_rs, ledger)
    completed = [(at, net) for at, _last_id, net in await _completed_trades(db, source, ledger)]
    halts = entry_halts(
        trade_cash=[(event.at, event.pnl) for event in ledger.trade_events],
        completed_newest_first=completed, today_ist=today_ist, pool_rs=pool_rs,
        equity_rs=view.equity_rs, policy=policy,
    )
    return SharedFnoEntryPolicyDecision(
        allowed=not halts.active, reason="" if not halts.active else halts.active[0],
        active_halts=halts.active, day_pnl_rs=halts.day_pnl_rs, week_pnl_rs=halts.week_pnl_rs,
        month_pnl_rs=halts.month_pnl_rs, view=view,
        completed_loss_streak=halts.loss_streak, observed_at=instant.isoformat(),
        legacy_unlinked_cash_events=ledger.legacy_unlinked_events,
    )


@dataclass(frozen=True)
class EntryHalts:
    """Pure result of the shared entry brakes for one IST policy day."""
    active: tuple[str, ...]
    day_pnl_rs: float
    week_pnl_rs: float
    month_pnl_rs: float
    loss_streak: int


def entry_halts(
    *, trade_cash: Sequence[tuple[datetime, float]],
    completed_newest_first: Sequence[tuple[datetime, float]],
    today_ist: date, pool_rs: float, equity_rs: float, policy: SharedFnoRiskPolicy,
) -> EntryHalts:
    """Daily/weekly/monthly loss, drawdown and loss-streak brakes.

    ``trade_cash`` holds every settled cash event (aware instant, net rupees);
    ``completed_newest_first`` holds completed trades' (aware completion
    instant, net rupees), newest first. Events after the policy day are
    ignored (never a credit). Shared by the live entry policy and the
    research replay so both brake identically.
    """
    iso_year, iso_week, _ = today_ist.isocalendar()
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    month_start = today_ist.replace(day=1)
    day_pnl = week_pnl = month_pnl = 0.0
    for at, pnl in trade_cash:
        event_day = at.astimezone(_IST).date()
        if event_day > today_ist:
            continue                      # after the policy day (replay); never a credit
        if event_day == today_ist:
            day_pnl += pnl
        if event_day >= week_start:
            week_pnl += pnl
        if event_day >= month_start:
            month_pnl += pnl
    consecutive_losses = 0
    latest_loss_day: Optional[date] = None
    for completed_at, net in completed_newest_first:
        if completed_at.astimezone(_IST).date() > today_ist:
            continue
        if net >= 0:
            break
        consecutive_losses += 1
        if latest_loss_day is None:
            latest_loss_day = completed_at.astimezone(_IST).date()

    halts: list[str] = []
    if day_pnl <= -policy.daily_loss_pct * pool_rs:
        halts.append(f"daily_loss_halt pnl={day_pnl:.0f}")
    if week_pnl <= -policy.weekly_loss_pct * pool_rs:
        halts.append(f"weekly_loss_halt pnl={week_pnl:.0f}")
    if month_pnl <= -policy.monthly_loss_pct * pool_rs:
        halts.append(f"monthly_loss_halt pnl={month_pnl:.0f}")
    if equity_rs <= 0:
        halts.append(f"drawdown_halt equity={equity_rs:.0f}")
    elif equity_rs < pool_rs * (1.0 - policy.drawdown_pct):
        halts.append(f"drawdown_halt equity={equity_rs:.0f}")
    if (consecutive_losses >= policy.max_consecutive_losses and latest_loss_day is not None
            and today_ist <= latest_loss_day + timedelta(days=1)):
        halts.append(
            f"consecutive_loss_pause streak={consecutive_losses} last={latest_loss_day}"
        )
    return EntryHalts(tuple(halts), day_pnl, week_pnl, month_pnl, consecutive_losses)


async def shared_fno_entry_policy(
    db_path: str, *, source: str, pool_rs: float, today_ist: date,
    policy: Optional[SharedFnoRiskPolicy] = None,
    observed_at: Optional[datetime] = None,
) -> SharedFnoEntryPolicyDecision:
    """Read the common F&O entry policy; malformed evidence denies entry."""
    pool = _finite_non_negative(pool_rs)
    active_policy = policy or policy_from_settings()
    if pool is None or not isinstance(today_ist, date):
        return _policy_unavailable(source, pool or 0.0, "invalid_policy_request")
    try:
        async with aiosqlite.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as db:
            await db.execute("PRAGMA query_only=ON")
            await db.execute("BEGIN")
            decision = await _read_entry_policy(
                db, source=source, pool_rs=pool, today_ist=today_ist,
                policy=active_policy, observed_at=observed_at,
            )
            await db.rollback()
            return decision
    except Exception as exc:
        return _policy_unavailable(
            source, pool, f"shared_policy_db_error:{type(exc).__name__}",
        )


async def shared_fno_risk_view(
    db_path: str, source: str, pool_rs: float,
    observed_at: Optional[datetime] = None,
) -> SharedFnoRiskView:
    """Return a read-only, consistent shared F&O risk view.

    ``pool_rs`` is an explicit caller-owned policy value.  It is not inferred
    from global settings, so paper and live callers cannot accidentally share
    a pool merely because a configuration default changed.
    """
    pool = _finite_non_negative(pool_rs)
    if pool is None:
        return _unavailable(source, 0.0, "invalid_pool")
    try:
        async with aiosqlite.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as db:
            await db.execute("PRAGMA query_only=ON")
            await db.execute("BEGIN")
            view = await _read_view(db, source, pool, observed_at)
            await db.rollback()
            return view
    except Exception as exc:
        return _unavailable(source, pool, f"risk_view_db_error:{type(exc).__name__}")


async def reserve_shared_fno_risk(
    db_path: str,
    *,
    source: str,
    pool_rs: float,
    reservation_key: str,
    book: str,
    worst_case_cash_rs: float,
    created_at: Optional[datetime] = None,
    entry_day_ist: Optional[date] = None,
    policy: Optional[SharedFnoRiskPolicy] = None,
    observed_at: Optional[datetime] = None,
) -> SharedFnoAdmission:
    """Atomically reserve capacity for an entry, failing closed on ambiguity.

    Repeating the same key is idempotent only when it describes the exact same
    still-reserved admission.  A consumed/released or mismatched key is never
    silently revived.  Reservations have no automatic expiry because an
    interrupted broker call is an external-state uncertainty, not free cash.
    """
    pool = _finite_non_negative(pool_rs)
    needed = _finite_non_negative(worst_case_cash_rs)
    if pool is None or needed is None or needed <= 0 or book not in {"SINGLE_LEG", "DEFINED_RISK"} or not reservation_key:
        view = _unavailable(source, pool or 0.0, "invalid_reservation_request")
        return SharedFnoAdmission(False, "invalid_reservation_request", view)
    stamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    active_policy = policy or policy_from_settings()
    try:
        await init_shared_fno_risk_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            existing = await (await db.execute(
                "SELECT source, book, state, worst_case_cash_rs FROM fno_risk_reservations WHERE reservation_key=?",
                (reservation_key,),
            )).fetchone()
            if existing is not None:
                same = (existing[0] == source and existing[1] == book
                        and existing[2] == "RESERVED" and float(existing[3]) == needed)
                view = await _read_view(db, source, pool, observed_at)
                await db.rollback()
                return SharedFnoAdmission(same and view.available,
                                          "already_reserved" if same else "reservation_key_conflict", view)
            if entry_day_ist is not None:
                decision = await _read_entry_policy(
                    db, source=source, pool_rs=pool, today_ist=entry_day_ist,
                    policy=active_policy, observed_at=observed_at,
                )
                if not decision.allowed:
                    await db.rollback()
                    return SharedFnoAdmission(False, decision.reason, decision.view)
            view = await _read_view(db, source, pool, observed_at)
            available = view.available_worst_case_cash_rs
            if not view.available or available is None:
                await db.rollback()
                return SharedFnoAdmission(False, view.reason or "risk_view_unavailable", view)
            if needed > available:
                await db.rollback()
                return SharedFnoAdmission(False, "shared_worst_case_cash_exhausted", view)
            await db.execute(
                "INSERT INTO fno_risk_reservations "
                "(reservation_key,source,book,state,worst_case_cash_rs,created_at) VALUES (?,?,?,'RESERVED',?,?)",
                (reservation_key, source, book, needed, stamp),
            )
            await db.commit()
            # Return the post-reservation view, not the pre-check that granted it.
            async with aiosqlite.connect(db_path) as after:
                await after.execute("BEGIN")
                post = await _read_view(after, source, pool, observed_at)
                await after.rollback()
            return SharedFnoAdmission(True, "reserved", post)
    except Exception as exc:
        view = _unavailable(source, pool, f"reservation_db_error:{type(exc).__name__}")
        return SharedFnoAdmission(False, view.reason, view)


async def resolve_shared_fno_risk_reservation(
    db_path: str,
    *,
    reservation_key: str,
    state: str,
    position_ref: Optional[str] = None,
    resolution_reason: Optional[str] = None,
    resolved_at: Optional[datetime] = None,
) -> bool:
    """Durably consume or release a reservation exactly once.

    A consumed reservation names the created position; a released reservation
    names the failed-before-entry reason.  Both requirements prevent an
    operator or a retry from making capacity disappear without an audit trail.
    The function never changes a non-reserved row, so a duplicate completion
    cannot overwrite an earlier external-state resolution.
    """
    if state not in {"CONSUMED", "RELEASED"} or not reservation_key:
        return False
    if state == "CONSUMED" and not position_ref:
        return False
    if state == "RELEASED" and not resolution_reason:
        return False
    stamp = (resolved_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    try:
        await init_shared_fno_risk_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            # F0-R2: once an entry is claimed for dispatch, only the typed,
            # evidence-backed dispatch resolution (or a position insert) may
            # resolve its reservation.
            claimed = await (await db.execute(
                "SELECT 1 FROM fno_entry_dispatches WHERE reservation_key=?", (reservation_key,)
            )).fetchone()
            if claimed is not None:
                await db.rollback()
                return False
            updated = await db.execute(
                "UPDATE fno_risk_reservations SET state=?, resolved_at=?, position_ref=?, resolution_reason=? "
                "WHERE reservation_key=? AND state='RESERVED'",
                (state, stamp, position_ref, resolution_reason, reservation_key),
            )
            if updated.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
    except Exception:
        return False


async def consume_shared_fno_risk_reservation_in_transaction(
    db: aiosqlite.Connection, *, reservation_key: str, source: str,
    book: str, position_ref: str, resolved_at: datetime,
) -> bool:
    """Consume one reservation using the caller's already-open transaction.

    Position stores use this narrow primitive so a position row and its
    reservation transition commit together.  It intentionally performs no
    schema setup and never commits/rolls back the caller's transaction.
    """
    if not position_ref or book not in {"SINGLE_LEG", "DEFINED_RISK"}:
        return False
    stamp = resolved_at.astimezone(timezone.utc).isoformat()
    try:
        updated = await db.execute(
            "UPDATE fno_risk_reservations SET state='CONSUMED', resolved_at=?, position_ref=? "
            "WHERE reservation_key=? AND source=? AND book=? AND state='RESERVED'",
            (stamp, position_ref, reservation_key, source, book),
        )
        if updated.rowcount != 1:
            return False
        # F0-R2: a reservation-backed position requires its one dispatch
        # claim; the claim becomes FILLED in the same transaction.
        claim = await db.execute(
            "UPDATE fno_entry_dispatches SET state='FILLED', position_ref=?, resolved_at=?, "
            "outcome=COALESCE(outcome, 'filled') "
            "WHERE reservation_key=? AND source=? AND book=? "
            "AND state IN ('DISPATCHING', 'UNRESOLVED')",
            (position_ref, stamp, reservation_key, source, book),
        )
    except aiosqlite.OperationalError:
        return False
    return claim.rowcount == 1


def _encode_evidence(evidence: object) -> Optional[tuple[str, str]]:
    if not isinstance(evidence, dict):
        return None
    try:
        raw = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                         default=str, allow_nan=False)
    except (TypeError, ValueError):
        return None
    encoded = raw.encode("utf-8")
    if len(encoded) > _MAX_EVIDENCE_BYTES:
        return None
    return raw, hashlib.sha256(encoded).hexdigest()


def _zero_fill_evidence_ok(evidence: dict) -> bool:
    filled = evidence.get("filled_quantity")
    return (bool(evidence.get("order_id"))
            and evidence.get("final_status") in {"CANCELLED", "REJECTED"}
            and type(filled) is int and filled == 0)


def dispatch_release_evidence_ok(outcome: str, evidence: object) -> bool:
    """True only when ``evidence`` proves the outcome created no exposure."""
    if not isinstance(evidence, dict):
        return False
    if outcome == "no_dispatch":
        return evidence.get("dispatch_certainty") == "NOT_SENT"
    if outcome == "rejected":
        return (evidence.get("dispatch_certainty") == "BROKER_REJECTED"
                and not evidence.get("order_id"))
    if outcome == "zero_fill_verified":
        return _zero_fill_evidence_ok(evidence)
    return False


def _reconcile_evidence_ok(outcome: str, evidence: object) -> bool:
    if not isinstance(evidence, dict):
        return False
    if outcome == "zero_fill_verified":
        return _zero_fill_evidence_ok(evidence)
    if outcome == "no_order_verified":
        checked = evidence.get("checked_at")
        try:
            aware = datetime.fromisoformat(str(checked)).tzinfo is not None
        except ValueError:
            aware = False
        return (isinstance(evidence.get("account_id"), str) and bool(evidence["account_id"])
                and aware and evidence.get("matching_orders") == [])
    return False


async def _occupancy_denial(
    db: aiosqlite.Connection, *, source: str, book: str, reservation_key: str,
    occupancy: EntryOccupancy,
) -> str:
    """First existing-limit violation, counting positions plus in-flight claims."""
    inflight = await (await db.execute(
        "SELECT tradingsymbol, planned_premium_rs, entry_day FROM fno_entry_dispatches "
        "WHERE source=? AND book=? AND state IN ('DISPATCHING', 'UNRESOLVED') "
        "AND reservation_key<>?", (source, book, reservation_key),
    )).fetchall()
    if book == "DEFINED_RISK":
        open_rows = (await (await db.execute(
            "SELECT COUNT(*) FROM fno_dr_positions WHERE source=? AND status IN ('OPEN','UNRESOLVED')",
            (source,))).fetchone())[0]
        if open_rows + len(inflight) >= occupancy.max_open:
            return "dr_structure_occupied"
        return ""
    positions = await (await db.execute(
        "SELECT tradingsymbol, entry_premium, qty FROM fno_positions "
        "WHERE source=? AND status IN ('OPEN','UNRESOLVED')", (source,),
    )).fetchall()
    if len(positions) + len(inflight) >= occupancy.max_open:
        return "concurrency"
    if occupancy.no_pyramid and occupancy.tradingsymbol and (
            any(row[0] == occupancy.tradingsymbol for row in positions)
            or any(row[0] == occupancy.tradingsymbol for row in inflight)):
        return "already_holding_this_contract"
    if occupancy.max_trades_per_day is not None:
        day = occupancy.entry_day.isoformat()
        entered = (await (await db.execute(
            "SELECT COUNT(*) FROM fno_positions WHERE source=? AND entry_date=?",
            (source, day))).fetchone())[0]
        if entered + sum(1 for row in inflight if row[2] == day) >= occupancy.max_trades_per_day:
            return "trades_per_day"
    if occupancy.max_open_premium_rs is not None:
        committed = 0.0
        for _symbol, entry, qty in positions:
            value = _finite_non_negative(entry)
            if value is None or type(qty) is not int:
                return "open_premium_unknown"
            committed += value * qty
        for _symbol, planned, _day in inflight:
            value = _finite_non_negative(planned)
            if value is None:
                return "inflight_premium_unknown"
            committed += value
        if committed + occupancy.planned_premium_rs > occupancy.max_open_premium_rs + 1e-9:
            return "open_premium_cap"
    return ""


async def claim_shared_fno_entry_dispatch(
    db_path: str,
    *,
    reservation_key: str,
    source: str,
    book: str,
    pool_rs: float,
    entry_day_ist: Optional[date],
    policy: Optional[SharedFnoRiskPolicy] = None,
    claimed_at: Optional[datetime] = None,
    observed_at: Optional[datetime] = None,
    occupancy: Optional[EntryOccupancy] = None,
) -> SharedFnoDispatchClaim:
    """Grant the single right to dispatch a reserved entry, or refuse.

    Under one ``BEGIN IMMEDIATE`` transaction: the reservation must still be
    RESERVED with the same source/book, no claim may exist, and the current
    entry policy (when ``entry_day_ist`` is given, the same scope admission
    used) must still allow entry. A policy denial releases the never-sent
    reservation as ``policy_denied_before_dispatch``. An existing claim in
    any state - including an orphaned DISPATCHING claim after a restart - is
    never granted again.
    """
    pool = _finite_non_negative(pool_rs)
    if (pool is None or not reservation_key or book not in {"SINGLE_LEG", "DEFINED_RISK"}
            or (entry_day_ist is not None and not isinstance(entry_day_ist, date))):
        view = _unavailable(source, pool or 0.0, "invalid_dispatch_claim_request")
        return SharedFnoDispatchClaim(False, "invalid_dispatch_claim_request", None, view)
    stamp = (claimed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    try:
        await init_shared_fno_risk_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            reservation = await (await db.execute(
                "SELECT source,book,state FROM fno_risk_reservations WHERE reservation_key=?",
                (reservation_key,),
            )).fetchone()
            existing = await (await db.execute(
                "SELECT state FROM fno_entry_dispatches WHERE reservation_key=?",
                (reservation_key,),
            )).fetchone()
            if reservation is None or reservation[0] != source or reservation[1] != book:
                view = await _read_view(db, source, pool, observed_at)
                await db.rollback()
                return SharedFnoDispatchClaim(False, "reservation_not_found_or_mismatched", None, view)
            if existing is not None:
                view = await _read_view(db, source, pool, observed_at)
                await db.rollback()
                return SharedFnoDispatchClaim(False, f"dispatch_already_claimed:{existing[0]}", None, view)
            if reservation[2] != "RESERVED":
                view = await _read_view(db, source, pool, observed_at)
                await db.rollback()
                return SharedFnoDispatchClaim(False, f"reservation_not_reserved:{reservation[2]}", None, view)
            if entry_day_ist is not None:
                decision = await _read_entry_policy(
                    db, source=source, pool_rs=pool, today_ist=entry_day_ist,
                    policy=policy or policy_from_settings(), observed_at=observed_at,
                )
                if not decision.allowed:
                    await db.execute(
                        "UPDATE fno_risk_reservations SET state='RELEASED', resolved_at=?, "
                        "resolution_reason=? WHERE reservation_key=? AND state='RESERVED'",
                        (stamp, f"policy_denied_before_dispatch:{decision.reason}"[:200],
                         reservation_key),
                    )
                    await db.commit()
                    return SharedFnoDispatchClaim(False, decision.reason, None, decision.view)
                view = decision.view
            else:
                view = await _read_view(db, source, pool, observed_at)
                if not view.available:
                    await db.rollback()
                    return SharedFnoDispatchClaim(False, view.reason or "risk_view_unavailable", None, view)
            if occupancy is not None:
                denial = await _occupancy_denial(
                    db, source=source, book=book, reservation_key=reservation_key,
                    occupancy=occupancy,
                )
                if denial:
                    # Nothing was dispatched: release the reservation auditably.
                    await db.execute(
                        "UPDATE fno_risk_reservations SET state='RELEASED', resolved_at=?, "
                        "resolution_reason=? WHERE reservation_key=? AND state='RESERVED'",
                        (stamp, f"occupancy_denied_before_dispatch:{denial}", reservation_key),
                    )
                    await db.commit()
                    return SharedFnoDispatchClaim(False, denial, None, view)
            owner = uuid4().hex
            await db.execute(
                "INSERT INTO fno_entry_dispatches "
                "(reservation_key,source,book,owner,state,claimed_at,tradingsymbol,"
                "planned_premium_rs,entry_day) VALUES (?,?,?,?,'DISPATCHING',?,?,?,?)",
                (reservation_key, source, book, owner, stamp,
                 occupancy.tradingsymbol if occupancy else None,
                 float(occupancy.planned_premium_rs) if occupancy else None,
                 occupancy.entry_day.isoformat() if occupancy else None),
            )
            await db.commit()
            return SharedFnoDispatchClaim(True, "claimed", owner, view)
    except Exception as exc:
        view = _unavailable(source, pool, f"dispatch_claim_db_error:{type(exc).__name__}")
        return SharedFnoDispatchClaim(False, view.reason, None, view)


async def resolve_shared_fno_entry_dispatch(
    db_path: str,
    *,
    reservation_key: str,
    owner: str,
    outcome: str,
    evidence: dict,
    resolved_at: Optional[datetime] = None,
) -> Optional[str]:
    """Record the owner's dispatch outcome once; return the applied outcome.

    A release outcome whose evidence does not prove zero exposure is applied
    as ``unknown`` (retained), never as a release. Returns ``None`` when the
    claim is not this owner's DISPATCHING claim or the write fails.
    """
    if outcome not in DISPATCH_RELEASE_OUTCOMES | DISPATCH_RETAIN_OUTCOMES or not owner:
        return None
    applied = outcome
    if outcome in DISPATCH_RELEASE_OUTCOMES and not dispatch_release_evidence_ok(outcome, evidence):
        applied = "unknown"
    encoded = _encode_evidence(evidence) or _encode_evidence(
        {"evidence_unserialisable": True, "requested_outcome": outcome})
    raw, digest = encoded
    order_id = evidence.get("order_id") if isinstance(evidence, dict) else None
    stamp = (resolved_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            claim = await (await db.execute(
                "SELECT 1 FROM fno_entry_dispatches WHERE reservation_key=? AND owner=? "
                "AND state='DISPATCHING'", (reservation_key, owner),
            )).fetchone()
            if claim is None:
                await db.rollback()
                return None
            state = "RELEASED" if applied in DISPATCH_RELEASE_OUTCOMES else "UNRESOLVED"
            await db.execute(
                "UPDATE fno_entry_dispatches SET state=?, outcome=?, order_id=?, evidence_json=?, "
                "evidence_sha256=?, resolved_at=? WHERE reservation_key=? AND owner=? "
                "AND state='DISPATCHING'",
                (state, applied, None if order_id is None else str(order_id), raw, digest,
                 stamp, reservation_key, owner),
            )
            if state == "RELEASED":
                released = await db.execute(
                    "UPDATE fno_risk_reservations SET state='RELEASED', resolved_at=?, "
                    "resolution_reason=? WHERE reservation_key=? AND state='RESERVED'",
                    (stamp, f"entry_{applied}", reservation_key),
                )
                if released.rowcount != 1:
                    await db.rollback()
                    return None
            await db.commit()
            return applied
    except Exception:
        return None


async def reconcile_shared_fno_entry_dispatch(
    db_path: str,
    *,
    reservation_key: str,
    operator: str,
    outcome: str,
    evidence: dict,
    resolved_at: Optional[datetime] = None,
) -> bool:
    """Operator release of an orphaned/unresolved claim with verified evidence.

    Allowed only for ``zero_fill_verified`` (order id, terminal status, zero
    filled quantity) or ``no_order_verified`` (account id, aware check time,
    empty matching-order list when no order id is known). Zero-fill evidence
    must match any recorded order id. A discovered fill is recorded instead by
    inserting the position through the normal reservation-consuming writer.
    """
    if outcome not in RECONCILE_OUTCOMES or not str(operator or "").strip() \
            or not _reconcile_evidence_ok(outcome, evidence):
        return False
    encoded = _encode_evidence(evidence)
    if encoded is None:
        return False
    raw, digest = encoded
    stamp = (resolved_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            claim = await (await db.execute(
                "SELECT order_id FROM fno_entry_dispatches WHERE reservation_key=? "
                "AND state IN ('DISPATCHING', 'UNRESOLVED')", (reservation_key,),
            )).fetchone()
            if claim is None or (claim[0] is not None and (
                    outcome != "zero_fill_verified"
                    or str(evidence.get("order_id")) != str(claim[0]))):
                await db.rollback()
                return False
            updated = await db.execute(
                "UPDATE fno_entry_dispatches SET state='RELEASED', outcome=?, operator=?, "
                "order_id=COALESCE(order_id, ?), evidence_json=?, evidence_sha256=?, resolved_at=? "
                "WHERE reservation_key=? AND state IN ('DISPATCHING', 'UNRESOLVED')",
                (outcome, str(operator).strip()[:80], evidence.get("order_id"), raw, digest,
                 stamp, reservation_key),
            )
            if updated.rowcount != 1:
                await db.rollback()
                return False
            released = await db.execute(
                "UPDATE fno_risk_reservations SET state='RELEASED', resolved_at=?, "
                "resolution_reason=? WHERE reservation_key=? AND state='RESERVED'",
                (stamp, f"operator_reconciled:{outcome}", reservation_key),
            )
            if released.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
    except Exception:
        return False


__all__ = [
    "EntryOccupancy", "SharedFnoAdmission", "SharedFnoDispatchClaim", "SharedFnoEntryPolicyDecision",
    "SharedFnoRiskPolicy", "SharedFnoRiskView", "init_shared_fno_risk_db", "policy_from_settings",
    "DISPATCH_RELEASE_OUTCOMES", "DISPATCH_RETAIN_OUTCOMES", "RECONCILE_OUTCOMES",
    "claim_shared_fno_entry_dispatch", "dispatch_release_evidence_ok",
    "reconcile_shared_fno_entry_dispatch", "resolve_shared_fno_entry_dispatch",
    "consume_shared_fno_risk_reservation_in_transaction",
    "reserve_shared_fno_risk", "resolve_shared_fno_risk_reservation",
    "shared_fno_entry_policy", "shared_fno_risk_view",
]
