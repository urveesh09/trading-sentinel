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
from datetime import datetime
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
    bar_ts TEXT
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
    """Idempotent DDL."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute(_DDL)
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
