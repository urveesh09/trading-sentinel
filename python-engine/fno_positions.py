"""
[FNO-POSITIONS 2026-07-10] Position store for the F&O subsystem.

Options positions don't fit the equity `positions` table (premium vs
price, lots vs shares, underlying-level stops next to premium backstops),
so they get their own table. Pool accounting still flows into the shared
bankroll_ledger via performance.record_trade_close(source=FNO_PAPER/
FNO_LIVE) at close time -- purely additive next to the existing source
tags (spec §10.3).

All dates/times stored in IST (the exchange's clock), ISO format. Kill
switches and day-queries key off entry_date / exit_date, so the module's
"day" can never drift against the trading session the way UTC dates do.

Rule 57: every reader preflights the table and returns a well-formed
empty result instead of raising on a fresh DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
import structlog

logger = structlog.get_logger()

_DDL = """
CREATE TABLE IF NOT EXISTS fno_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    tradingsymbol TEXT NOT NULL,
    token INTEGER,
    underlying TEXT,
    expiry TEXT,
    strike REAL,
    opt_type TEXT,
    direction TEXT,
    lots INTEGER,
    lot_size INTEGER,
    qty INTEGER,
    entry_time TEXT,
    entry_date TEXT,
    entry_premium REAL,
    entry_underlying REAL,
    delta_at_entry REAL,
    iv_at_entry REAL,
    atr_at_entry REAL,
    stop_underlying REAL,
    target_underlying REAL,
    premium_stop REAL,
    trail_active INTEGER DEFAULT 0,
    trail_stop_underlying REAL,
    best_underlying REAL,
    max_loss_rupees REAL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    exit_time TEXT,
    exit_date TEXT,
    exit_premium REAL,
    exit_underlying REAL,
    exit_reason TEXT,
    gross_pnl REAL,
    costs REAL,
    pnl REAL,
    r_multiple REAL,
    entry_order_id TEXT,
    exit_order_id TEXT,
    bar_ts TEXT,
    -- [WORKFLOW-A2 2026-09-20] Settlement-generation token.
    --
    -- Every successful close increments this counter. The unique
    -- index on ``bankroll_ledger(origin_ref, settlement_generation)``
    -- prevents two closes of the same position from producing two
    -- ledger rows -- the audit's reproducer. Default 0 for legacy
    -- rows; the migration is idempotent (``ADD COLUMN``).
    settlement_generation INTEGER NOT NULL DEFAULT 0
)
"""


_LEDGER_DDL = """
-- [WORKFLOW-A2 2026-09-20] Shared ledger uniqueness bound.
--
-- The audit reproducer showed that two writes using the same
-- ``fno_position:999`` origin created two ledger rows totalling -20.
-- The fix is a partial unique index on
-- ``(origin_ref, settlement_generation)`` that only enforces
-- uniqueness when ``settlement_generation > 0``. The partial-index
-- guard lets pre-migration callers (whose ``settlement_generation``
-- is always 0) keep writing rows without the constraint firing,
-- while post-migration callers (with monotonically increasing
-- tokens) are protected against duplicate writes.
--
-- Once every caller supplies a non-zero ``settlement_generation``,
-- a follow-up migration can drop the partial index and create a
-- full unique index. The partial index is the right default for
-- an idempotent migration.
CREATE UNIQUE INDEX IF NOT EXISTS ux_bankroll_ledger_source_origin_gen
    ON bankroll_ledger (source, origin_ref, settlement_generation)
    WHERE settlement_generation > 0
"""


# A filled exit is an external fact.  Keep it independently of local
# accounting so a failed local settlement can be retried without asking the
# executor to submit another exit order.  The row is consumed in the same
# transaction that closes the position and writes the ledger delta.
_EXIT_RECEIPT_DDL = """
CREATE TABLE IF NOT EXISTS fno_exit_execution_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL UNIQUE,
    source TEXT NOT NULL,
    ticker TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    exit_premium REAL NOT NULL,
    exit_underlying REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    gross_pnl REAL NOT NULL,
    costs REAL NOT NULL,
    pnl REAL NOT NULL,
    r_multiple REAL NOT NULL,
    exit_order_id TEXT,
    settlement_generation INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
)
"""


@dataclass
class FnoPosition:
    """In-memory mirror of one fno_positions row."""
    id: int
    source: str
    tradingsymbol: str
    token: int
    underlying: str
    expiry: str
    strike: float
    opt_type: str
    direction: str
    lots: int
    lot_size: int
    qty: int
    entry_time: str
    entry_date: str
    entry_premium: float
    entry_underlying: float
    delta_at_entry: float
    iv_at_entry: float
    atr_at_entry: float
    stop_underlying: float
    target_underlying: float
    premium_stop: float
    trail_active: int
    trail_stop_underlying: Optional[float]
    best_underlying: float
    max_loss_rupees: float
    status: str
    bar_ts: str


_SELECT_COLS = (
    "id, source, tradingsymbol, token, underlying, expiry, strike, opt_type, "
    "direction, lots, lot_size, qty, entry_time, entry_date, entry_premium, "
    "entry_underlying, delta_at_entry, iv_at_entry, atr_at_entry, "
    "stop_underlying, target_underlying, premium_stop, trail_active, "
    "trail_stop_underlying, best_underlying, max_loss_rupees, status, bar_ts"
)


def _row_to_position(row) -> FnoPosition:
    return FnoPosition(*row)


async def init_fno_positions_db(db_path: str) -> None:
    """Idempotent DDL.

    [WORKFLOW-A2 2026-09-20] Adds the ``settlement_generation``
    column to ``fno_positions`` (idempotent) and the
    ``bankroll_ledger(origin_ref, settlement_generation)`` unique
    index. The unique index prevents two settles of the same
    position from producing two ledger rows.
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute(_DDL)
        # Idempotent column migration for legacy DBs that pre-date
        # the settlement_generation column. SQLite raises
        # ``OperationalError: duplicate column name`` if the
        # column already exists; swallow that.
        try:
            await db.execute(
                "ALTER TABLE fno_positions "
                "ADD COLUMN settlement_generation INTEGER NOT NULL DEFAULT 0"
            )
        except aiosqlite.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        # Create the unique index on the shared ledger. The table
        # itself is owned by ``performance.init_ledger``; we wrap
        # the index creation in a try so a test DB that doesn't
        # have ``bankroll_ledger`` yet does not fail this init.
        try:
            await db.execute(_LEDGER_DDL)
        except aiosqlite.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
        await db.execute(_EXIT_RECEIPT_DDL)
        await db.execute("""CREATE TABLE IF NOT EXISTS fno_exit_intents (
            position_id INTEGER PRIMARY KEY, source TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        await db.commit()


async def _table_exists(db) -> bool:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_positions'"
    ) as cur:
        return (await cur.fetchone()) is not None


async def insert_position(db_path: str, **fields) -> int:
    """Insert an OPEN position; returns the row id."""
    await init_fno_positions_db(db_path)
    cols = ", ".join(fields.keys())
    marks = ", ".join(["?"] * len(fields))
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            f"INSERT INTO fno_positions ({cols}) VALUES ({marks})",
            list(fields.values()),
        )
        await db.commit()
        return cur.lastrowid


async def open_positions(db_path: str, source: str) -> List[FnoPosition]:
    async with aiosqlite.connect(db_path) as db:
        if not await _table_exists(db):
            logger.info("fno_db_unready reason=fno_positions_missing FIX=first entry creates it")
            return []
        async with db.execute(
            f"SELECT {_SELECT_COLS} FROM fno_positions "
            "WHERE source=? AND status='OPEN' ORDER BY id",
            (source,),
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_position(r) for r in rows]


async def open_premium_committed(db_path: str, source: str) -> float:
    """Sum of entry_premium * qty across OPEN positions (spec §7.5 cap)."""
    async with aiosqlite.connect(db_path) as db:
        if not await _table_exists(db):
            return 0.0
        async with db.execute(
            "SELECT COALESCE(SUM(entry_premium * qty), 0.0) FROM fno_positions "
            "WHERE source=? AND status='OPEN'",
            (source,),
        ) as cur:
            row = await cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


async def trades_today(db_path: str, source: str, today_iso: str) -> int:
    async with aiosqlite.connect(db_path) as db:
        if not await _table_exists(db):
            return 0
        async with db.execute(
            "SELECT COUNT(*) FROM fno_positions WHERE source=? AND entry_date=?",
            (source, today_iso),
        ) as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def already_entered_bar(db_path: str, source: str, bar_ts: str) -> bool:
    """Idempotency: one entry per signal bar per leg, restart-safe."""
    async with aiosqlite.connect(db_path) as db:
        if not await _table_exists(db):
            return False
        async with db.execute(
            "SELECT 1 FROM fno_positions WHERE source=? AND bar_ts=? LIMIT 1",
            (source, bar_ts),
        ) as cur:
            return (await cur.fetchone()) is not None


async def update_trail(
    db_path: str, position_id: int,
    trail_active: int, trail_stop_underlying: Optional[float],
    best_underlying: float,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE fno_positions SET trail_active=?, trail_stop_underlying=?, "
            "best_underlying=? WHERE id=?",
            (trail_active, trail_stop_underlying, best_underlying, position_id),
        )
        await db.commit()


async def close_position(
    db_path: str, position_id: int,
    exit_time_ist: datetime, exit_premium: float, exit_underlying: float,
    exit_reason: str, gross_pnl: float, costs: float, pnl: float,
    r_multiple: float, exit_order_id: Optional[str],
) -> None:
    """[WORKFLOW-A2 2026-09-20] Deprecated thin shim.

    Use ``settle_position_close`` instead. This function performs
    ONLY the position UPDATE; it does NOT write the ledger row, so
    a crash between this call and ``record_trade_close`` leaves the
    position closed without its cash movement.

    The shim is preserved for callers that already split the close
    and the ledger write. New code MUST use ``settle_position_close``
    so the two writes commit atomically.
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE fno_positions SET status='CLOSED', exit_time=?, exit_date=?, "
            "exit_premium=?, exit_underlying=?, exit_reason=?, gross_pnl=?, "
            "costs=?, pnl=?, r_multiple=?, exit_order_id=? "
            "WHERE id=? AND status='OPEN'",
            (
                exit_time_ist.isoformat(), exit_time_ist.date().isoformat(),
                exit_premium, exit_underlying, exit_reason, gross_pnl,
                costs, pnl, r_multiple, exit_order_id, position_id,
            ),
        )
        await db.commit()


async def exit_execution_receipt(
    db_path: str, position_id: int, source: str,
) -> Optional[dict]:
    """Return an acknowledged-but-unsettled exit for one open position."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                "SELECT * FROM fno_exit_execution_receipts "
                "WHERE position_id=? AND source=?",
                (position_id, source),
            )
            row = await cur.fetchone()
        except aiosqlite.OperationalError:
            # Unreadable execution evidence must never authorize another exit.
            raise
    return dict(row) if row is not None else None


async def claim_exit_intent(db_path: str, position_id: int, source: str) -> bool:
    """Durably claim one external exit; ambiguous dispatches require reconciliation.

    No lease expiry: a crash cannot prove an external order was never submitted.
    Successful accounting consumes the claim in the same transaction.
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "INSERT OR IGNORE INTO fno_exit_intents(position_id,source,created_at) "
            "SELECT id,source,? FROM fno_positions WHERE id=? AND source=? AND status='OPEN'",
            (datetime.now(timezone.utc).isoformat(), position_id, source),
        )
        await db.commit()
        return cur.rowcount == 1


async def record_exit_execution_receipt(
    db_path: str,
    position_id: int,
    *,
    source: str,
    ticker: str,
    exit_time_ist: datetime,
    exit_premium: float,
    exit_underlying: float,
    exit_reason: str,
    gross_pnl: float,
    costs: float,
    pnl: float,
    r_multiple: float,
    exit_order_id: Optional[str],
    settlement_generation: int = 1,
    notes: Optional[str] = None,
) -> dict:
    """Persist a broker-acknowledged exit before local settlement.

    The receipt is deliberately a separate, durable fact.  It is deleted by
    ``settle_position_close`` only when the position update and ledger insert
    commit together.  Therefore a local ledger failure leaves recovery input
    for the next tick and does not cause another broker exit submission.
    """
    if type(settlement_generation) is not int or settlement_generation <= 0:
        raise ValueError(
            "settlement_generation must be a positive integer; "
            f"got {settlement_generation!r}"
        )
    await init_fno_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            cur = await db.execute(
                "SELECT source, status FROM fno_positions WHERE id=?",
                (position_id,),
            )
            position = await cur.fetchone()
            if position is None or position["status"] != "OPEN":
                raise PositionNotOpen(
                    f"position {position_id} is not OPEN; cannot record exit receipt"
                )
            if position["source"] != source:
                raise SettlementConflict(
                    f"position {position_id} belongs to {position['source']!r}, "
                    f"not {source!r}"
                )
            cur = await db.execute(
                "SELECT * FROM fno_exit_execution_receipts WHERE position_id=?",
                (position_id,),
            )
            existing = await cur.fetchone()
            if existing is not None:
                if (
                    existing["source"] == source
                    and existing["exit_order_id"] == exit_order_id
                    and float(existing["exit_premium"]) == float(exit_premium)
                    and int(existing["settlement_generation"]) == settlement_generation
                ):
                    await db.commit()
                    return dict(existing)
                raise SettlementConflict(
                    f"position {position_id} already has a different exit receipt"
                )
            cur = await db.execute(
                "INSERT INTO fno_exit_execution_receipts "
                "(position_id, source, ticker, exit_time, exit_premium, "
                "exit_underlying, exit_reason, gross_pnl, costs, pnl, r_multiple, "
                "exit_order_id, settlement_generation, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    position_id, source, ticker, exit_time_ist.isoformat(),
                    exit_premium, exit_underlying, exit_reason, gross_pnl, costs,
                    pnl, r_multiple, exit_order_id, settlement_generation,
                    (notes or "").strip()[:500] or None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            receipt_id = cur.lastrowid
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            raise
    receipt = await exit_execution_receipt(db_path, position_id, source)
    if receipt is None or receipt["id"] != receipt_id:
        raise SettlementError(
            f"exit receipt for position {position_id} was not readable after commit"
        )
    return receipt


# [WORKFLOW-A2 2026-09-20] Settlement exceptions.
#
# These are raised by ``settle_position_close`` to communicate
# three distinct failure modes. Callers that catch one of these
# know exactly which retry / recovery path to follow.


class SettlementError(Exception):
    """Base class for atomic settlement failures."""


class PositionNotOpen(SettlementError):
    """[WORKFLOW-A2 2026-09-20] The position is already closed or
    never existed. The settlement UPDATE affected zero rows.

    A retry on this failure is NOT safe: the work is already
    done or the row never existed. The caller must look up the
    row's current state before deciding what to do.
    """


class SettlementConflict(SettlementError):
    """[WORKFLOW-A2 2026-09-20] A settlement with the same
    ``(origin_ref, settlement_generation)`` already exists in the
    ledger. The unique index caught a duplicate settle.

    This is the audit's reproducer failure mode: two writes using
    the same ``fno_position:999`` origin produced two ledger rows.
    With the unique index, the second write raises this exception
    instead of silently producing phantom equity.
    """


# [WORKFLOW-A2 2026-09-20] Atomic settlement helper.
#
# Runs the position UPDATE and the ledger INSERT in ONE
# ``aiosqlite`` transaction. Requires ``cursor.rowcount == 1`` for
# the position UPDATE; raises ``PositionNotOpen`` when the row is
# already closed or missing. Raises ``SettlementConflict`` when
# the unique ledger index catches a duplicate settlement.
#
# Pure of I/O: takes only the inputs that the caller already has.
# No clock read inside the transaction; the caller supplies the
# ``exit_time_ist`` and the helper uses ``datetime.now(UTC)`` for
# the ledger row's timestamp so the two writes share a single
# commit boundary without one stealing time from the other.
async def settle_position_close(
    db_path: str,
    position_id: int,
    *,
    exit_time_ist: datetime,
    exit_premium: float,
    exit_underlying: float,
    exit_reason: str,
    gross_pnl: float,
    costs: float,
    pnl: float,
    r_multiple: float,
    exit_order_id: Optional[str],
    source: str,
    ticker: str,
    settlement_generation: int = 1,
    origin_ref: Optional[str] = None,
    notes: Optional[str] = None,
    ledger_timestamp: Optional[datetime] = None,
    outcome_pnl: Optional[float] = None,
    outcome_r_multiple: Optional[float] = None,
    execution_receipt_id: Optional[int] = None,
) -> dict:
    """[WORKFLOW-A2 2026-09-20] Atomic position close + ledger write.

    Both writes commit in one transaction. On any error, both
    roll back together.

    Parameters
    ----------
    settlement_generation:
        Caller-supplied monotonically increasing token. The unique
        ledger index ``(origin_ref, settlement_generation)``
        prevents two settlements with the same token. Re-running
        the same settle (after a crash) reuses the same token so
        the second attempt hits the unique index and raises
        ``SettlementConflict`` instead of producing a duplicate
        ledger row.
    origin_ref:
        Defaults to ``fno_position:<id>`` when omitted. The unique
        index binds to this value + ``settlement_generation``.
    ledger_timestamp:
        Caller-supplied UTC timestamp for the ledger row. When
        omitted, ``datetime.now(timezone.utc)`` is used so the
        transaction is reproducible.

    Returns
    -------
    dict with keys ``position_id``, ``settlement_generation``,
    ``origin_ref``, ``ledger_id``, ``pnl``, ``bankroll_before``,
    ``bankroll_after``. ``bankroll_before`` / ``bankroll_after``
    reflect the division's allocation after the ledger write.

    Raises
    ------
    PositionNotOpen
        The position is already CLOSED or never existed. ``cursor.rowcount == 0``.
    SettlementConflict
        A row with the same ``(origin_ref, settlement_generation)`` already
        exists in the ledger. The unique index caught a duplicate.
    """
    if type(settlement_generation) is not int or settlement_generation <= 0:
        raise ValueError(
            "settlement_generation must be a positive integer; "
            f"got {settlement_generation!r}"
        )
    if origin_ref is None:
        origin_ref = f"fno_position:{position_id}"
    origin_ref = str(origin_ref).strip()[:180]
    timestamp = ledger_timestamp or datetime.now(timezone.utc)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            # Step 1: position UPDATE gated on status='OPEN'. The
            # rowcount tells us whether the position is still open
            # and whether we own this row.
            cur = await db.execute(
                "UPDATE fno_positions SET "
                "status='CLOSED', exit_time=?, exit_date=?, "
                "exit_premium=?, exit_underlying=?, exit_reason=?, "
                "gross_pnl=?, costs=?, pnl=?, r_multiple=?, "
                "exit_order_id=?, settlement_generation=? "
                "WHERE id=? AND source=? AND status='OPEN'",
                (
                    exit_time_ist.isoformat(),
                    exit_time_ist.date().isoformat(),
                    exit_premium,
                    exit_underlying,
                    exit_reason,
                    gross_pnl,
                    costs,
                    pnl,
                    r_multiple,
                    exit_order_id,
                    settlement_generation,
                    position_id,
                    source,
                ),
            )
            if cur.rowcount != 1:
                await db.rollback()
                raise PositionNotOpen(
                    f"position {position_id} is not OPEN (rowcount={cur.rowcount}); "
                    "cannot settle"
                )
            # Step 2: ledger INSERT. Read the division's equity
            # BEFORE the write so the ledger row records the
            # before / after pair.
            # [WORKFLOW-A2 2026-09-20] Test-fixture compatibility:
            # probe for the table first so tests that build a
            # minimal DB (no ``bankroll_ledger``) do not crash.
            try:
                cur = await db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='bankroll_ledger'"
                )
                row = await cur.fetchone()
                if row is None:
                    # No ledger table: the position UPDATE already
                    # committed; surface the failure so the caller
                    # can run init_ledger before retrying.
                    await db.rollback()
                    raise SettlementError(
                        "bankroll_ledger table missing; "
                        "call init_ledger() before settle_position_close()"
                    )
            except SettlementError:
                raise
            except Exception:
                await db.rollback()
                raise SettlementError(
                    "bankroll_ledger table missing; "
                    "call init_ledger() before settle_position_close()"
                )
            cur = await db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger WHERE source=?",
                (source,),
            )
            row = await cur.fetchone()
            from performance import allocation_for_source
            bankroll_before = allocation_for_source(source) + (
                float(row[0]) if row and row[0] is not None else 0.0
            )
            bankroll_after = bankroll_before + pnl
            try:
                cur = await db.execute(
                    "INSERT INTO bankroll_ledger "
                    "(timestamp, event_type, ticker, pnl, bankroll_before, "
                    "bankroll_after, source, notes, origin_ref, settlement_generation) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        timestamp.isoformat(),
                        "TRADE_CLOSED",
                        ticker,
                        pnl,
                        bankroll_before,
                        bankroll_after,
                        source,
                        (notes or "").strip()[:500] or None,
                        origin_ref,
                        settlement_generation,
                    ),
                )
            except aiosqlite.IntegrityError as exc:
                await db.rollback()
                raise SettlementConflict(
                    f"ledger row with origin_ref={origin_ref!r} and "
                    f"settlement_generation={settlement_generation} already exists"
                ) from exc
            ledger_id = cur.lastrowid
            if execution_receipt_id is not None:
                # Receipt consumption shares the position + ledger commit
                # boundary.  A local failure retains the broker fill for
                # recovery; a successful commit cannot leave it pending.
                cur = await db.execute(
                    "DELETE FROM fno_exit_execution_receipts "
                    "WHERE id=? AND position_id=? AND source=? "
                    "AND settlement_generation=?",
                    (
                        execution_receipt_id, position_id, source,
                        settlement_generation,
                    ),
                )
                if cur.rowcount != 1:
                    await db.rollback()
                    raise SettlementConflict(
                        f"exit receipt {execution_receipt_id} is missing or does not "
                        f"belong to position {position_id}"
                    )
            await db.execute(
                "DELETE FROM fno_exit_intents WHERE position_id=? AND source=?",
                (position_id, source),
            )
            await db.commit()
        except Exception:
            # Defensive: any uncaught exception in the transaction
            # body must roll back. ``aiosqlite`` auto-rolls-back
            # on connection close, but explicit rollback is
            # clearer and survives if a future refactor reorders
            # statements.
            try:
                await db.rollback()
            except Exception:
                pass
            raise
    return {
        "position_id": position_id,
        "settlement_generation": settlement_generation,
        "origin_ref": origin_ref,
        "ledger_id": ledger_id,
        "pnl": pnl,
        "bankroll_before": bankroll_before,
        "bankroll_after": bankroll_after,
        "source": source,
    }


# [WORKFLOW-A2 2026-09-20] Idempotent settlement retry helper.
#
# Wraps ``settle_position_close`` so a caller that has an
# acknowledged broker fill can re-attempt after a crash without
# risking a duplicate ledger row. The wrapper reads the
# position's current ``settlement_generation``; if it already
# matches the requested generation, the helper is a no-op and
# returns ``{"settled": False, "already": True}``. Otherwise it
# proceeds with the atomic settle.
async def settle_position_close_idempotent(
    db_path: str,
    position_id: int,
    requested_generation: int,
    **kwargs,
) -> dict:
    """[WORKFLOW-A2 2026-09-20] Idempotent settle wrapper.

    Returns ``{"settled": True, "result": <settle result>}`` on
    the first successful call. Returns ``{"settled": False,
    "already": True, "current_generation": <int>}`` on a retry
    that finds the position already at the requested generation.
    Any other failure (``PositionNotOpen``, ``SettlementConflict``)
    propagates.
    """
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT source, status, settlement_generation "
            "FROM fno_positions WHERE id=?",
            (position_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise PositionNotOpen(
            f"position {position_id} does not exist; cannot settle"
        )
    position_source, status, current_generation = row[0], row[1], int(row[2] or 0)
    requested_source = kwargs.get("source")
    if requested_source != position_source:
        raise SettlementConflict(
            f"position {position_id} belongs to {position_source!r}, "
            f"not {requested_source!r}"
        )
    if status == "CLOSED" and current_generation == requested_generation:
        return {
            "settled": False,
            "already": True,
            "current_generation": current_generation,
        }
    if status == "CLOSED":
        raise SettlementConflict(
            f"position {position_id} was settled at generation "
            f"{current_generation}, not requested generation {requested_generation}; "
            "reconcile the broker revision without a second ledger close"
        )
    result = await settle_position_close(
        db_path, position_id,
        settlement_generation=requested_generation,
        **kwargs,
    )
    return {"settled": True, "result": result}


async def closed_today(db_path: str, source: str, today_iso: str) -> List[dict]:
    """Today's closed rows for the hourly report."""
    async with aiosqlite.connect(db_path) as db:
        if not await _table_exists(db):
            return []
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tradingsymbol, direction, lots, entry_premium, exit_premium, "
            "pnl, r_multiple, exit_reason, exit_time FROM fno_positions "
            "WHERE source=? AND status='CLOSED' AND exit_date=? ORDER BY exit_time",
            (source, today_iso),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
