"""
[PENNY-LOG 2026-06-21] Append-only signal log for the penny subsystem.

Every penny scan outcome (accepted or rejected) is persisted to:
  1. CSV at settings.PENNY_LOG_CSV_PATH (default /data/penny_signals.csv)
  2. SQLite table `penny_signals` in settings.DB_PATH

Schema (stable contract -- do NOT rename columns, only add):
  scan_id          TEXT
  scanned_at       TEXT   -- ISO8601 UTC
  ticker           TEXT
  leg              TEXT   -- CNC / MIS
  accepted         INTEGER-- 1 if signal fired, 0 if rejected
  reject_reason    TEXT
  regime           TEXT
  close            REAL
  stop_loss        REAL
  target_1         REAL
  target_2         REAL
  rsi_2            REAL
  rsi_14           REAL
  volume_ratio     REAL
  shares           INTEGER

Best-effort writes: failures in this module must NOT crash the live scan.
The caller (scanner) wraps invocations in try/except + logger.error.

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

Public API:
  init_penny_signal_db(db_path)               -- idempotent
  log_penny_signal(db_path, scan_id, ticker,
                   leg, accepted, regime, close,
                   reject_reason=None, stop_loss=None, target_1=None,
                   target_2=None, rsi_2=None, rsi_14=None,
                   volume_ratio=None, shares=None)
"""
import asyncio
import csv
import logging
import os
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

_COLUMNS = [
    "scan_id", "scanned_at", "ticker", "leg", "accepted",
    "reject_reason", "regime", "close", "stop_loss", "target_1",
    "target_2", "rsi_2", "rsi_14", "volume_ratio", "breakout_level", "shares",
]


async def init_penny_signal_db(db_path: str) -> None:
    """Create the penny_signals table if absent. Idempotent."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS penny_signals (
                    scan_id         TEXT,
                    scanned_at      TEXT,
                    ticker          TEXT,
                    leg             TEXT,
                    accepted        INTEGER,
                    reject_reason   TEXT,
                    regime          TEXT,
                    close           REAL,
                    stop_loss       REAL,
                    target_1        REAL,
                    target_2        REAL,
                    rsi_2           REAL,
                    rsi_14          REAL,
                    volume_ratio    REAL,
                    breakout_level  REAL,
                    shares          INTEGER
                )
            """)
            await db.commit()
    except Exception as e:
        logger.error("penny_signal_db_init_failed db=%s error=%s", db_path, str(e))


async def log_penny_signal(
    db_path: str,
    scan_id: str,
    ticker: str,
    leg: str,
    accepted: bool,
    regime: str,
    close: float,
    reject_reason: str = None,
    stop_loss: float = None,
    target_1: float = None,
    target_2: float = None,
    rsi_2: float = None,
    rsi_14: float = None,
    volume_ratio: float = None,
    breakout_level: float = None,
    shares: int = None,
) -> None:
    """
    Best-effort: append a single signal outcome to CSV + SQLite.
    Failures are logged but NOT raised (so the scanner keeps running).
    """
    from config import settings
    row = {
        "scan_id": scan_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "leg": leg,
        "accepted": 1 if accepted else 0,
        "reject_reason": reject_reason or "",
        "regime": regime,
        "close": close,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "rsi_2": rsi_2,
        "rsi_14": rsi_14,
        "volume_ratio": volume_ratio,
        "breakout_level": breakout_level,
        "shares": shares,
    }

    # 1. CSV append
    try:
        csv_path = settings.PENNY_LOG_CSV_PATH
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        new_file = not os.path.exists(csv_path)
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logger.error("penny_signal_csv_write_failed error=%s", str(e))

    # 2. SQLite insert (best-effort)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                f"INSERT INTO penny_signals ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(['?'] * len(_COLUMNS))})",
                [row[c] for c in _COLUMNS],
            )
            await db.commit()
    except Exception as e:
        logger.error("penny_signal_db_write_failed db=%s error=%s", db_path, str(e))
