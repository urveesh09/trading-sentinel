"""Transactional admission control for classic Penny entries.

The evaluator may run concurrently (or repeatedly on a later bar), so an
in-memory snapshot cannot enforce position limits.  This module serialises the
last pre-broker decision with ``BEGIN IMMEDIATE`` and leaves ambiguous broker
outcomes reserved until an operator/reconciler resolves them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

import aiosqlite


_SOURCES = {"PENNY", "PENNY_PAPER"}
_LEGS = {"CNC", "MIS"}
_ACTIVE = {"RESERVED", "UNRESOLVED"}
_FINAL = {"FULFILLED", "RELEASED"}


@dataclass(frozen=True)
class ReservationDecision:
    granted: bool
    reason: str
    total_occupied: int
    leg_occupied: int
    idempotent: bool = False


def _normalise(source: str, ticker: str, product_type: str) -> tuple[str, str, str]:
    source = str(source).strip().upper()
    ticker = str(ticker).strip().upper()
    product_type = str(product_type).strip().upper()
    if source not in _SOURCES:
        raise ValueError("source must be PENNY or PENNY_PAPER")
    if product_type not in _LEGS:
        raise ValueError("product_type must be CNC or MIS")
    if not ticker:
        raise ValueError("ticker must be non-empty")
    return source, ticker, product_type


async def init_penny_position_reservations(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS penny_position_reservations (
                attempt_id TEXT PRIMARY KEY,
                source TEXT NOT NULL CHECK(source IN ('PENNY','PENNY_PAPER')),
                ticker TEXT NOT NULL CHECK(
                    ticker=UPPER(TRIM(ticker)) AND LENGTH(ticker)>0
                ),
                product_type TEXT NOT NULL CHECK(product_type IN ('CNC','MIS')),
                state TEXT NOT NULL CHECK(
                    state IN ('RESERVED','UNRESOLVED','FULFILLED','RELEASED')
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolution_note TEXT
            )
        """)
        # This table starts clean, unlike positions which may contain legacy
        # duplicates.  A partial unique index therefore gives SQLite-level
        # protection without attempting to rewrite historical trade evidence.
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_penny_active_source_ticker
            ON penny_position_reservations(source,ticker)
            WHERE state IN ('RESERVED','UNRESOLVED')
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_penny_reservation_occupancy
            ON penny_position_reservations(source,state,product_type)
        """)
        await db.commit()


async def reserve_penny_position(
    db_path: str, *, attempt_id: str, source: str, ticker: str,
    product_type: str, max_total: int, max_leg: int,
) -> ReservationDecision:
    """Atomically reserve one source/ticker slot immediately before execution."""
    source, ticker, product_type = _normalise(source, ticker, product_type)
    attempt_id = str(attempt_id).strip()
    if not attempt_id:
        raise ValueError("attempt_id must be non-empty")
    if max_total < 1 or max_leg < 1:
        raise ValueError("position caps must be positive")
    await init_penny_position_reservations(db_path)

    async with aiosqlite.connect(db_path, timeout=30.0) as db:
        # RESERVED must be committed before the broker call. BEGIN IMMEDIATE
        # ensures every contender counts from the same serialised state.
        await db.execute("BEGIN IMMEDIATE")
        try:
            existing = await (await db.execute("""
                SELECT source,ticker,product_type,state
                FROM penny_position_reservations WHERE attempt_id=?
            """, (attempt_id,))).fetchone()
            if existing is not None:
                identity = (source, ticker, product_type)
                if tuple(existing[:3]) != identity:
                    raise ValueError("reservation idempotency collision")
                if existing[3] in _ACTIVE:
                    counts = await _occupancy_counts(db, source, product_type)
                    await db.commit()
                    # A process can die after the broker accepts the order but
                    # before ENTRY_SUBMITTED reaches the journal.  Therefore a
                    # pre-existing reservation is evidence of possible broker
                    # progress, never permission to submit the attempt again.
                    return ReservationDecision(
                        False, "attempt_already_reserved", *counts, True,
                    )
                counts = await _occupancy_counts(db, source, product_type)
                await db.commit()
                return ReservationDecision(
                    False, f"attempt_already_{str(existing[3]).lower()}", *counts, True,
                )

            duplicate = await (await db.execute("""
                SELECT 1 FROM positions
                WHERE source=? AND UPPER(ticker)=? AND exit_date IS NULL LIMIT 1
            """, (source, ticker))).fetchone()
            if duplicate is None:
                duplicate = await (await db.execute("""
                    SELECT 1 FROM penny_position_reservations
                    WHERE source=? AND ticker=?
                      AND state IN ('RESERVED','UNRESOLVED') LIMIT 1
                """, (source, ticker))).fetchone()
            total, leg_count = await _occupancy_counts(db, source, product_type)
            if duplicate is not None:
                await db.rollback()
                return ReservationDecision(False, "source_ticker_already_occupied", total, leg_count)
            if total >= max_total:
                await db.rollback()
                return ReservationDecision(False, f"max_total_reached:{total}/{max_total}", total, leg_count)
            if leg_count >= max_leg:
                await db.rollback()
                return ReservationDecision(
                    False, f"max_{product_type.lower()}_reached:{leg_count}/{max_leg}",
                    total, leg_count,
                )

            now = datetime.now(timezone.utc).isoformat()
            await db.execute("""
                INSERT INTO penny_position_reservations
                    (attempt_id,source,ticker,product_type,state,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)
            """, (attempt_id, source, ticker, product_type, "RESERVED", now, now))
            await db.commit()
            return ReservationDecision(True, "reserved", total + 1, leg_count + 1)
        except Exception:
            await db.rollback()
            raise


async def _occupancy_counts(db, source: str, product_type: str) -> tuple[int, int]:
    row = await (await db.execute("""
        SELECT
          (SELECT COUNT(*) FROM positions
             WHERE source=? AND exit_date IS NULL)
          +
          (SELECT COUNT(*) FROM penny_position_reservations
             WHERE source=? AND state IN ('RESERVED','UNRESOLVED')),
          (SELECT COUNT(*) FROM positions
             WHERE source=? AND exit_date IS NULL
               AND UPPER(COALESCE(product_type,'CNC'))=? )
          +
          (SELECT COUNT(*) FROM penny_position_reservations
             WHERE source=? AND state IN ('RESERVED','UNRESOLVED')
               AND product_type=? )
    """, (source, source, source, product_type, source, product_type))).fetchone()
    return int(row[0]), int(row[1])


async def set_penny_reservation_state(
    db_path: str, *, attempt_id: str, state: str, note: str | None = None,
) -> bool:
    """Resolve or quarantine a reservation; missing/final rows fail closed."""
    state = str(state).strip().upper()
    if state not in (_ACTIVE | _FINAL):
        raise ValueError("invalid reservation state")
    await init_penny_position_reservations(db_path)
    async with aiosqlite.connect(db_path, timeout=30.0) as db:
        before = db.total_changes
        await db.execute("""
            UPDATE penny_position_reservations
            SET state=?,updated_at=?,resolution_note=?
            WHERE attempt_id=? AND state IN ('RESERVED','UNRESOLVED')
        """, (state, datetime.now(timezone.utc).isoformat(),
              (note or "")[:500], attempt_id))
        changed = db.total_changes > before
        await db.commit()
    return changed


async def persist_reserved_penny_position(
    db_path: str, *, attempt_id: str, values: Mapping,
) -> int:
    """Insert the local position and fulfill its reservation in one commit."""
    required = {
        "ticker", "exchange", "entry_date", "entry_price", "shares",
        "stop_loss_initial", "trailing_stop_current", "target_1", "target_2",
        "atr_14_at_entry", "highest_close_since_entry", "status", "source",
        "product_type", "regime_at_entry", "sl_order_id",
    }
    missing = required - set(values)
    if missing:
        raise ValueError(f"missing position values: {','.join(sorted(missing))}")
    source, ticker, product_type = _normalise(
        values["source"], values["ticker"], values["product_type"],
    )
    await init_penny_position_reservations(db_path)
    async with aiosqlite.connect(db_path, timeout=30.0) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            reservation = await (await db.execute("""
                SELECT source,ticker,product_type,state
                FROM penny_position_reservations WHERE attempt_id=?
            """, (attempt_id,))).fetchone()
            if reservation is None or tuple(reservation[:3]) != (source, ticker, product_type):
                raise ValueError("position does not match a reservation")
            existing = await (await db.execute(
                "SELECT rowid FROM positions WHERE penny_attempt_id=?",
                (attempt_id,),
            )).fetchone()
            if existing is not None:
                if reservation[3] in _ACTIVE:
                    await db.execute("""
                        UPDATE penny_position_reservations
                        SET state='FULFILLED',updated_at=?,resolution_note='position_exists'
                        WHERE attempt_id=?
                    """, (datetime.now(timezone.utc).isoformat(), attempt_id))
                await db.commit()
                return int(existing[0])
            if reservation[3] not in _ACTIVE:
                raise ValueError(f"reservation is {reservation[3].lower()}")

            cursor = await db.execute("""
                INSERT INTO positions (
                    ticker,exchange,entry_date,entry_price,shares,
                    stop_loss_initial,trailing_stop_current,target_1,target_2,
                    atr_14_at_entry,highest_close_since_entry,status,source,
                    product_type,regime_at_entry,sl_order_id,penny_attempt_id,
                    atr_1min_post_t1,t1_fired,initial_capital_at_risk
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, values["exchange"], values["entry_date"], values["entry_price"],
                values["shares"], values["stop_loss_initial"],
                values["trailing_stop_current"], values["target_1"], values["target_2"],
                values["atr_14_at_entry"], values["highest_close_since_entry"],
                values["status"], source, product_type, values["regime_at_entry"],
                values["sl_order_id"], attempt_id, values.get("atr_1min_post_t1"),
                values.get("t1_fired", 0),
                max(
                    0.0,
                    (float(values["entry_price"]) - float(values["stop_loss_initial"]))
                    * int(values["shares"]),
                ),
            ))
            await db.execute("""
                UPDATE penny_position_reservations
                SET state='FULFILLED',updated_at=?,resolution_note='position_created'
                WHERE attempt_id=?
            """, (datetime.now(timezone.utc).isoformat(), attempt_id))
            await db.commit()
            return int(cursor.lastrowid)
        except Exception:
            await db.rollback()
            raise
