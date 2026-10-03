"""Durable, cross-runtime own-cash reservations for live *entry* orders.

The gateway and engine share ``/data/cache.db``.  Broker balances are a
snapshot, so the snapshot alone cannot safely admit two concurrent callers.
This module records the amount which the broker has not yet made visible as a
pending order or position.  It deliberately never releases an ambiguous order.
"""
from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ACTIVE = ("RESERVED", "DISPATCHED", "AMBIGUOUS", "PARTIAL")
OPEN_ORDER_STATUSES = frozenset({
    "OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "OPEN PENDING",
    "VALIDATION PENDING", "PUT ORDER REQ RECEIVED", "MODIFY PENDING",
    "MODIFY VALIDATION PENDING",
})


def estimate_entry_charges(notional: float) -> float:
    """Bound a cash-equity entry's statutory/broker debit, rounded upward.

    This is intentionally a worst-case *entry* estimate, not a claim of the
    broker's final contract note.  The 0.03% brokerage (capped at Rs20),
    exchange/SEBI charges, GST and the higher cash-delivery stamp duty basis
    are all reserved.  The separate 1% fill buffer protects the quoted limit.
    """
    if not isinstance(notional, (int, float)) or not math.isfinite(notional) or notional <= 0:
        raise ValueError("notional must be a positive finite number")
    brokerage = min(notional * 0.0003, 20.0)
    exchange_and_sebi = notional * (0.000035 + 0.000001)
    gst = 0.18 * (brokerage + exchange_and_sebi)
    stamp = notional * 0.00015
    return math.ceil((brokerage + exchange_and_sebi + gst + stamp) * 100) / 100


def required_reservation(notional: float) -> tuple[float, float, float]:
    """Return (total, charge_reserve, 1%-fill-buffer) for a bounded entry."""
    charges = estimate_entry_charges(notional)
    buffer = math.ceil(notional * 0.01 * 100) / 100
    return round(notional + charges + buffer, 2), charges, buffer


def _broker_represents(row: sqlite3.Row, orders: Iterable[dict]) -> bool:
    """True only if this current broker snapshot already commits the cash.

    A matching OPEN buy is included by F1-A's pending calculation. A matching
    COMPLETE buy is expected to be included by its broker position. A terminal
    rejected/cancelled order is *not* proof of zero fill and keeps the local
    hold until explicit reconciliation releases it.
    """
    for order in orders:
        if not isinstance(order, dict):
            continue
        same_id = row["broker_order_id"] and str(order.get("order_id") or "") == row["broker_order_id"]
        same_tag = row["broker_tag"] and str(order.get("tag") or "") == row["broker_tag"]
        if not (same_id or same_tag):
            continue
        status = str(order.get("status") or "").upper()
        side = str(order.get("transaction_type") or "").upper()
        if side == "BUY" and (status in OPEN_ORDER_STATUSES or status == "COMPLETE"):
            return True
    return False


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    amount: float
    charge_reserve: float
    fill_buffer: float
    available_after: float


class ReservationRefused(RuntimeError):
    pass


class AccountCashReservations:
    """Tiny SQLite protocol shared with ``node-gateway``.

    The schema intentionally uses only SQLite primitives supported by Python's
    sqlite3 and better-sqlite3. ``BEGIN IMMEDIATE`` serializes the read/sum/
    insert decision across the two processes.
    """
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))
        self._memory_connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:", timeout=30.0, isolation_level=None)
                self._memory_connection.row_factory = sqlite3.Row
                self._memory_connection.execute("PRAGMA busy_timeout = 30000")
                self._ensure_schema(self._memory_connection)
            return self._memory_connection
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        self._ensure_schema(conn)
        return conn

    def _close(self, conn: sqlite3.Connection) -> None:
        if conn is not self._memory_connection:
            conn.close()

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_cash_reservations (
              reservation_id TEXT PRIMARY KEY,
              account_id TEXT NOT NULL,
              book TEXT NOT NULL,
              broker_tag TEXT NOT NULL,
              broker_order_id TEXT,
              amount REAL NOT NULL CHECK(amount > 0),
              charge_reserve REAL NOT NULL CHECK(charge_reserve >= 0),
              fill_buffer REAL NOT NULL CHECK(fill_buffer >= 0),
              state TEXT NOT NULL CHECK(state IN
                ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL','RELEASED')),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              release_reason TEXT
            )
        """)
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_account_cash_active
            ON account_cash_reservations(account_id, state)""")

    def reserve(self, *, reservation_id: str, account_id: str, book: str,
                broker_tag: str, notional: float, own_uncommitted_cash: float,
                broker_orders: Iterable[dict]) -> Reservation:
        if not all(isinstance(v, str) and v for v in (reservation_id, account_id, book, broker_tag)):
            raise ReservationRefused("ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: invalid reservation identity")
        if not isinstance(own_uncommitted_cash, (int, float)) or not math.isfinite(own_uncommitted_cash):
            raise ReservationRefused("ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: invalid own-cash snapshot")
        broker_orders = list(broker_orders) if isinstance(broker_orders, (list, tuple)) else None
        if broker_orders is None:
            raise ReservationRefused("ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: broker order snapshot unavailable")
        amount, charges, buffer = required_reservation(float(notional))
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM account_cash_reservations WHERE reservation_id=?",
                                    (reservation_id,)).fetchone()
            if existing is not None:
                if existing["state"] == "RELEASED":
                    raise ReservationRefused("ACCOUNT_RESERVATION_REUSED: released id cannot be dispatched again")
                conn.execute("COMMIT")
                return Reservation(reservation_id, float(existing["amount"]),
                                   float(existing["charge_reserve"]), float(existing["fill_buffer"]),
                                   float(own_uncommitted_cash))
            held = 0.0
            for row in conn.execute("SELECT * FROM account_cash_reservations WHERE account_id=? "
                                    "AND state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL')", (account_id,)):
                if not _broker_represents(row, broker_orders):
                    held += float(row["amount"])
            available_after = float(own_uncommitted_cash) - held - amount
            if available_after < -0.00001:
                conn.execute("ROLLBACK")
                raise ReservationRefused(
                    f"ACCOUNT_OWN_CASH_INSUFFICIENT: required {amount:.2f}, "
                    f"uncommitted {own_uncommitted_cash:.2f}, local holds {held:.2f}"
                )
            conn.execute("""INSERT INTO account_cash_reservations
              (reservation_id,account_id,book,broker_tag,amount,charge_reserve,fill_buffer,state,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,'RESERVED',?,?)""",
                         (reservation_id, account_id, book, broker_tag, amount, charges, buffer, now, now))
            conn.execute("COMMIT")
            return Reservation(reservation_id, amount, charges, buffer, max(0.0, available_after))
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def mark_dispatch(self, reservation_id: str, *, broker_order_id: str | None,
                      ambiguous: bool) -> None:
        state = "AMBIGUOUS" if ambiguous else "DISPATCHED"
        conn = self._connect()
        try:
            result = conn.execute("""UPDATE account_cash_reservations
                SET broker_order_id=COALESCE(?, broker_order_id), state=?, updated_at=?
                WHERE reservation_id=? AND state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL')""",
                                  (broker_order_id, state, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), reservation_id))
            if result.rowcount != 1:
                raise ReservationRefused("ACCOUNT_RESERVATION_MISSING: dispatch state was not retained")
        finally:
            self._close(conn)

    def release_zero_fill(self, reservation_id: str, *, broker_order_id: str,
                          terminal_status: str, filled_quantity: float) -> bool:
        """Release only a matching terminal zero-fill broker proof."""
        terminal = str(terminal_status or "").upper()
        if terminal not in {"CANCELLED", "REJECTED"} or float(filled_quantity) != 0 or not broker_order_id:
            return False
        conn = self._connect()
        try:
            result = conn.execute("""UPDATE account_cash_reservations
                SET state='RELEASED', release_reason=?, updated_at=?
                WHERE reservation_id=? AND broker_order_id=?
                  AND state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL')""",
                                  (f"verified_{terminal.lower()}_zero_fill",
                                   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   reservation_id, broker_order_id))
            return result.rowcount == 1
        finally:
            self._close(conn)

    def release_not_sent(self, reservation_id: str, reason: str) -> bool:
        """Release only when the caller has proof that no request left it."""
        conn = self._connect()
        try:
            result = conn.execute("""UPDATE account_cash_reservations
                SET state='RELEASED', release_reason=?, updated_at=?
                WHERE reservation_id=? AND state='RESERVED'""",
                                  (str(reason)[:100], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   reservation_id))
            return result.rowcount == 1
        finally:
            self._close(conn)
