"""
[FNO-LOG 2026-07-10] Append-only signal log for the F&O subsystem (spec §9.2).

Every evaluation -- accepted or rejected, including "engine said no
signal" ticks where a bar was actually evaluated -- writes one row to:
  1. CSV at settings.FNO_SIGNAL_LOG_PATH (default /data/fno_signals.csv)
  2. SQLite table `fno_signals` in settings.DB_PATH

Ops rule 75: the CSV, not docker logs, is the ground truth for "is it
really doing nothing?". The zero-accept watchdog reads the SQLite table.

Schema is a stable contract -- never rename columns, only add.

Best-effort writes: failures here must NOT crash the scan tick.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
import structlog

logger = structlog.get_logger()

_COLUMNS = [
    "scan_id", "evaluated_at", "bar_ts", "leg", "underlying", "direction",
    "accepted", "reject_reason", "regime", "fut_price", "or_high", "or_low",
    "atr", "rvol", "ema_fast", "ema_slow", "tradingsymbol", "strike",
    "opt_type", "expiry", "premium", "iv", "delta", "spread_pct", "oi",
    "volume", "lots", "max_loss_rupees", "min_pool_required",
    # [POOL-AUDIT 2026-08-04] The pool the gate was actually evaluated against.
    # min_pool_required alone records the threshold but not what cleared it,
    # which made the 2026-08-03 F&O rows unfalsifiable -- see fno_orchestrator.
    "pool_at_eval",
]


async def init_fno_signal_db(db_path: str) -> None:
    """Create the fno_signals table if absent. Idempotent."""
    cols_sql = ", ".join(
        f"{c} {'INTEGER' if c in ('accepted', 'oi', 'volume', 'lots') else 'TEXT' if c in ('scan_id', 'evaluated_at', 'bar_ts', 'leg', 'underlying', 'direction', 'reject_reason', 'regime', 'tradingsymbol', 'opt_type', 'expiry') else 'REAL'}"
        for c in _COLUMNS
    )
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(f"CREATE TABLE IF NOT EXISTS fno_signals ({cols_sql})")
            # CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so a
            # column added to _COLUMNS after first deploy would never appear and
            # every INSERT would fail with "no such column". Backfill missing
            # columns explicitly -- the same discipline as position_tracker.
            async with db.execute("PRAGMA table_info(fno_signals)") as cur:
                existing = {r[1] for r in await cur.fetchall()}
            for col in _COLUMNS:
                if col not in existing:
                    await db.execute(f"ALTER TABLE fno_signals ADD COLUMN {col} REAL")
                    logger.info("fno_signal_db_column_added column=%s", col)
            await db.commit()
    except Exception as e:
        logger.error("fno_signal_db_init_failed db=%s error=%s", db_path, str(e))


async def log_fno_signal(
    db_path: str,
    scan_id: str,
    leg: str,
    accepted: bool,
    reject_reason: str = "",
    bar_ts: str = "",
    underlying: str = "NIFTY",
    direction: Optional[str] = None,
    regime: str = "",
    fut_price: Optional[float] = None,
    or_high: Optional[float] = None,
    or_low: Optional[float] = None,
    atr: Optional[float] = None,
    rvol: Optional[float] = None,
    ema_fast: Optional[float] = None,
    ema_slow: Optional[float] = None,
    tradingsymbol: str = "",
    strike: Optional[float] = None,
    opt_type: str = "",
    expiry: str = "",
    premium: Optional[float] = None,
    iv: Optional[float] = None,
    delta: Optional[float] = None,
    spread_pct: Optional[float] = None,
    oi: Optional[int] = None,
    volume: Optional[int] = None,
    lots: Optional[int] = None,
    max_loss_rupees: Optional[float] = None,
    min_pool_required: Optional[float] = None,
    pool_at_eval: Optional[float] = None,
) -> None:
    """Best-effort append of one evaluation row to CSV + SQLite."""
    from config import settings

    row = {
        "scan_id": scan_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "bar_ts": bar_ts,
        "leg": leg,
        "underlying": underlying,
        "direction": direction or "",
        "accepted": 1 if accepted else 0,
        "reject_reason": reject_reason or "",
        "regime": regime,
        "fut_price": fut_price,
        "or_high": or_high,
        "or_low": or_low,
        "atr": atr,
        "rvol": rvol,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "tradingsymbol": tradingsymbol,
        "strike": strike,
        "opt_type": opt_type,
        "expiry": expiry,
        "premium": premium,
        "iv": iv,
        "delta": delta,
        "spread_pct": spread_pct,
        "oi": oi,
        "volume": volume,
        "lots": lots,
        "max_loss_rupees": max_loss_rupees,
        "min_pool_required": min_pool_required,
        "pool_at_eval": pool_at_eval,
    }

    # 1. CSV append
    try:
        csv_path = settings.FNO_SIGNAL_LOG_PATH
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        new_file = not os.path.exists(csv_path)
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logger.error("fno_signal_csv_write_failed error=%s", str(e))

    # 2. SQLite insert
    try:
        await init_fno_signal_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                f"INSERT INTO fno_signals ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(['?'] * len(_COLUMNS))})",
                [row[c] for c in _COLUMNS],
            )
            await db.commit()
    except Exception as e:
        logger.error("fno_signal_db_write_failed db=%s error=%s", db_path, str(e))
