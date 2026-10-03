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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from typing import Optional
from zoneinfo import ZoneInfo

import aiosqlite


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


@dataclass(frozen=True)
class SharedFnoAdmission:
    """Result of attempting to reserve worst-case cash for one new entry."""

    allowed: bool
    reason: str
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


async def _validate_open_partial_exit_evidence(
    db: aiosqlite.Connection, *, source: str, open_positions: list[tuple],
) -> str:
    """Bind residual single-leg risk to durable partial-exit evidence.

    A recovery records the broker-confirmed filled/residual quantities and its
    exact ledger row in the same transaction as the position reduction.  Only
    an open position with such evidence needs this validation; untouched
    positions retain their existing structural-loss contract.  This read never
    changes recovery state or grants capacity.
    """
    positions = {int(row[0]): row for row in open_positions}
    if not positions:
        return ""
    marks = ",".join("?" for _ in positions)
    recoveries = await (await db.execute(
        "SELECT id,position_id,filled_qty,remaining_qty,settlement_generation,ledger_id "
        "FROM fno_exit_recoveries WHERE source=? AND position_id IN (" + marks + ") "
        "ORDER BY position_id,id",
        (source, *positions),
    )).fetchall()
    by_position: dict[int, list[tuple]] = {}
    for recovery in recoveries:
        position_id = _whole_non_negative(recovery[1])
        if position_id is None or position_id not in positions:
            return "invalid_partial_recovery_evidence"
        by_position.setdefault(position_id, []).append(recovery)

    for position_id, rows in by_position.items():
        _id, current_loss, current_qty, initial_qty, initial_loss = positions[position_id]
        qty = _whole_non_negative(current_qty)
        original_qty = _whole_non_negative(initial_qty)
        original_loss = _finite_non_negative(initial_loss)
        current = _finite_non_negative(current_loss)
        if qty is None or qty <= 0 or original_qty is None or original_qty <= 0 \
                or qty > original_qty or original_loss is None or current is None:
            return "invalid_partial_recovery_evidence"
        expected_remaining = original_qty
        expected_generation = 0
        for recovery in rows:
            _recovery_id, _position_id, filled_raw, remaining_raw, generation_raw, ledger_id = recovery
            filled = _whole_non_negative(filled_raw)
            remaining = _whole_non_negative(remaining_raw)
            generation = _whole_non_negative(generation_raw)
            if filled is None or remaining is None or generation is None \
                    or filled + remaining != expected_remaining:
                return "invalid_partial_recovery_evidence"
            if filled:
                expected_generation += 1
                if generation != expected_generation or ledger_id is None:
                    return "invalid_partial_recovery_evidence"
                ledger = await (await db.execute(
                    "SELECT source,event_type,origin_ref,settlement_generation,pnl "
                    "FROM bankroll_ledger WHERE id=?", (ledger_id,)
                )).fetchone()
                if (ledger is None or ledger[0] != source or ledger[1] != "TRADE_CLOSED"
                        or ledger[2] != f"fno_position:{position_id}"
                        or _whole_non_negative(ledger[3]) != generation
                        or not isinstance(ledger[4], (int, float))
                        or isinstance(ledger[4], bool)
                        or not math.isfinite(float(ledger[4]))):
                    return "invalid_partial_recovery_evidence"
            elif generation != expected_generation or ledger_id is not None:
                return "invalid_partial_recovery_evidence"
            expected_remaining = remaining
        expected_loss = original_loss * expected_remaining / original_qty
        if (expected_remaining != qty or not math.isclose(
                current, expected_loss, rel_tol=0.0, abs_tol=0.01)):
            return "invalid_partial_recovery_evidence"
    return ""


async def _read_view(
    db: aiosqlite.Connection, source: str, pool_rs: float,
) -> SharedFnoRiskView:
    """Read one consistent view; caller owns the transaction boundary."""
    required = (
        "bankroll_ledger", "fno_positions", "fno_dr_positions",
        "fno_exit_recoveries", "fno_risk_reservations",
    )
    missing = [name for name in required if not await _table_exists(db, name)]
    if missing:
        return _unavailable(source, pool_rs, "missing_required_table:" + ",".join(missing))

    ledger_rows = await (await db.execute(
        "SELECT pnl FROM bankroll_ledger "
        "WHERE source=? AND event_type='TRADE_CLOSED'", (source,)
    )).fetchall()
    # Validate individual rows instead of trusting SQLite's aggregate: an
    # invalid positive/negative pair must not cancel into apparent capacity.
    realised_pnl = 0.0
    for row in ledger_rows:
        try:
            pnl = float(row[0])
        except (TypeError, ValueError):
            pnl = float("nan")
        if not math.isfinite(pnl):
            return _unavailable(source, pool_rs, "nonfinite_realised_pnl")
        realised_pnl += pnl
    if not math.isfinite(realised_pnl):
        return _unavailable(source, pool_rs, "nonfinite_realised_pnl")

    single = await (await db.execute(
        "SELECT id,max_loss_rupees,qty,initial_qty,initial_max_loss_rupees "
        "FROM fno_positions "
        "WHERE source=? AND status IN ('OPEN', 'UNRESOLVED')", (source,)
    )).fetchall()
    defined = await (await db.execute(
        "SELECT max_loss_rs FROM fno_dr_positions "
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

    single_total = sum(_finite_non_negative(row[1]) or 0.0 for row in single)
    defined_total = sum(_finite_non_negative(row[0]) or 0.0 for row in defined)
    reserved_total = sum(_finite_non_negative(row[0]) or 0.0 for row in reserved)
    equity = pool_rs + realised_pnl
    if not math.isfinite(equity):
        return _unavailable(source, pool_rs, "nonfinite_equity")
    available = equity - single_total - defined_total - reserved_total
    return SharedFnoRiskView(
        source=source,
        pool_rs=pool_rs,
        realised_pnl_rs=realised_pnl,
        equity_rs=equity,
        open_worst_case_cash_rs=single_total + defined_total,
        reserved_worst_case_cash_rs=reserved_total,
        available_worst_case_cash_rs=max(0.0, available),
        single_leg_open_count=len(single),
        defined_risk_open_count=len(defined),
        reservation_count=len(reserved),
        available=True,
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
) -> SharedFnoEntryPolicyDecision:
    """Evaluate policy under the caller's transaction boundary.

    Every F&O terminal/partial cash event shares the same source ledger, so
    this intentionally has no origin-prefix filter.  Position rows are not a
    fallback: a ledger timestamp/P&L ambiguity fails the new entry closed.
    """
    if _invalid_policy(policy):
        return _policy_unavailable(source, pool_rs, "invalid_shared_risk_policy")
    view = await _read_view(db, source, pool_rs)
    if not view.available:
        return SharedFnoEntryPolicyDecision(
            allowed=False, reason=view.reason or "risk_view_unavailable",
            active_halts=(view.reason or "risk_view_unavailable",),
            day_pnl_rs=None, week_pnl_rs=None, month_pnl_rs=None, view=view,
        )

    rows = await (await db.execute(
        "SELECT id,timestamp,pnl FROM bankroll_ledger "
        "WHERE source=? AND event_type='TRADE_CLOSED' ORDER BY id DESC",
        (source,),
    )).fetchall()
    iso_year, iso_week, _ = today_ist.isocalendar()
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    month_start = today_ist.replace(day=1)
    day_pnl = week_pnl = month_pnl = 0.0
    consecutive_losses = 0
    latest_loss_day: Optional[date] = None
    streak_active = True
    for row in rows:
        try:
            stamp = datetime.fromisoformat(str(row[1]))
            pnl = float(row[2])
        except (TypeError, ValueError):
            return _policy_unavailable(source, pool_rs, "invalid_terminal_cash_event")
        if stamp.tzinfo is None or not math.isfinite(pnl):
            return _policy_unavailable(source, pool_rs, "invalid_terminal_cash_event")
        event_day = stamp.astimezone(_IST).date()
        if event_day >= today_ist:
            day_pnl += pnl
        if event_day >= week_start:
            week_pnl += pnl
        if event_day >= month_start:
            month_pnl += pnl
        if streak_active and pnl < 0:
            consecutive_losses += 1
            if latest_loss_day is None:
                latest_loss_day = event_day
        else:
            streak_active = False

    halts: list[str] = []
    if day_pnl <= -policy.daily_loss_pct * pool_rs:
        halts.append(f"daily_loss_halt pnl={day_pnl:.0f}")
    if week_pnl <= -policy.weekly_loss_pct * pool_rs:
        halts.append(f"weekly_loss_halt pnl={week_pnl:.0f}")
    if month_pnl <= -policy.monthly_loss_pct * pool_rs:
        halts.append(f"monthly_loss_halt pnl={month_pnl:.0f}")
    if view.equity_rs <= 0:
        halts.append(f"drawdown_halt equity={view.equity_rs:.0f}")
    elif view.equity_rs < pool_rs * (1.0 - policy.drawdown_pct):
        halts.append(f"drawdown_halt equity={view.equity_rs:.0f}")
    if (consecutive_losses >= policy.max_consecutive_losses and latest_loss_day is not None
            and today_ist <= latest_loss_day + timedelta(days=1)):
        halts.append(
            f"consecutive_loss_pause streak={consecutive_losses} last={latest_loss_day}"
        )
    return SharedFnoEntryPolicyDecision(
        allowed=not halts, reason="" if not halts else halts[0],
        active_halts=tuple(halts), day_pnl_rs=day_pnl, week_pnl_rs=week_pnl,
        month_pnl_rs=month_pnl, view=view,
    )


async def shared_fno_entry_policy(
    db_path: str, *, source: str, pool_rs: float, today_ist: date,
    policy: Optional[SharedFnoRiskPolicy] = None,
) -> SharedFnoEntryPolicyDecision:
    """Read the common F&O entry policy; malformed evidence denies entry."""
    pool = _finite_non_negative(pool_rs)
    active_policy = policy or policy_from_settings()
    if pool is None or not isinstance(today_ist, date):
        return _policy_unavailable(source, pool or 0.0, "invalid_policy_request")
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA query_only=ON")
            await db.execute("BEGIN")
            decision = await _read_entry_policy(
                db, source=source, pool_rs=pool, today_ist=today_ist,
                policy=active_policy,
            )
            await db.rollback()
            return decision
    except Exception as exc:
        return _policy_unavailable(
            source, pool, f"shared_policy_db_error:{type(exc).__name__}",
        )


async def shared_fno_risk_view(
    db_path: str, source: str, pool_rs: float,
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
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA query_only=ON")
            await db.execute("BEGIN")
            view = await _read_view(db, source, pool)
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
                view = await _read_view(db, source, pool)
                await db.rollback()
                return SharedFnoAdmission(same and view.available,
                                          "already_reserved" if same else "reservation_key_conflict", view)
            if entry_day_ist is not None:
                decision = await _read_entry_policy(
                    db, source=source, pool_rs=pool, today_ist=entry_day_ist,
                    policy=active_policy,
                )
                if not decision.allowed:
                    await db.rollback()
                    return SharedFnoAdmission(False, decision.reason, decision.view)
            view = await _read_view(db, source, pool)
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
                post = await _read_view(after, source, pool)
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
    updated = await db.execute(
        "UPDATE fno_risk_reservations SET state='CONSUMED', resolved_at=?, position_ref=? "
        "WHERE reservation_key=? AND source=? AND book=? AND state='RESERVED'",
        (resolved_at.astimezone(timezone.utc).isoformat(), position_ref,
         reservation_key, source, book),
    )
    return updated.rowcount == 1


__all__ = [
    "SharedFnoAdmission", "SharedFnoEntryPolicyDecision", "SharedFnoRiskPolicy",
    "SharedFnoRiskView", "init_shared_fno_risk_db", "policy_from_settings",
    "consume_shared_fno_risk_reservation_in_transaction",
    "reserve_shared_fno_risk", "resolve_shared_fno_risk_reservation",
    "shared_fno_entry_policy", "shared_fno_risk_view",
]
