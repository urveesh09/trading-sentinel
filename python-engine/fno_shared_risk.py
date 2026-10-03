"""Shared, fail-closed F&O paper-risk evidence and reservations.

This module is intentionally the only place that may combine the directional
``fno_positions`` and defined-risk ``fno_dr_positions`` books for an F&O
admission decision.  The books retain their own lifecycle/settlement writers;
this module does not invent a fill, close a position, or release exposure on a
timer.  In particular, an ``UNRESOLVED`` structure and an interrupted entry
reservation remain unavailable capital until an explicit, durable resolution.

The first F0 slice exposes a typed snapshot and an atomic reservation primitive
without changing an existing entry path.  Wiring either book to reserve and
consume an admission is a separate change: it must make its position insert
and reservation transition one idempotent transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Optional

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


async def _read_view(
    db: aiosqlite.Connection, source: str, pool_rs: float,
) -> SharedFnoRiskView:
    """Read one consistent view; caller owns the transaction boundary."""
    required = ("bankroll_ledger", "fno_positions", "fno_dr_positions", "fno_risk_reservations")
    missing = [name for name in required if not await _table_exists(db, name)]
    if missing:
        return _unavailable(source, pool_rs, "missing_required_table:" + ",".join(missing))

    ledger = await (await db.execute(
        "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger "
        "WHERE source=? AND event_type='TRADE_CLOSED'", (source,)
    )).fetchone()
    # P&L may legitimately be negative, so validate it separately.
    try:
        realised_pnl = float(ledger[0] if ledger else 0.0)
    except (TypeError, ValueError):
        realised_pnl = float("nan")
    if not math.isfinite(realised_pnl):
        return _unavailable(source, pool_rs, "nonfinite_realised_pnl")

    single = await (await db.execute(
        "SELECT max_loss_rupees FROM fno_positions "
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
    for label, rows in (("single_leg", single), ("defined_risk", defined), ("reservation", reserved)):
        for row in rows:
            amount = _finite_non_negative(row[0])
            if amount is None:
                return _unavailable(source, pool_rs, f"invalid_{label}_worst_case_cash")
            amounts.append(amount)

    single_total = sum(_finite_non_negative(row[0]) or 0.0 for row in single)
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
    "SharedFnoAdmission", "SharedFnoRiskView", "init_shared_fno_risk_db",
    "consume_shared_fno_risk_reservation_in_transaction",
    "reserve_shared_fno_risk", "resolve_shared_fno_risk_reservation",
    "shared_fno_risk_view",
]
