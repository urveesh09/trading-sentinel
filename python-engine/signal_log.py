"""
[MOMENTUM-LOG 2026-06-16] Append-only signal log for momentum scans.

Every momentum signal evaluation (accepted or rejected) is persisted to:
  1. CSV at settings.MOMENTUM_LOG_CSV_PATH (default /data/momentum_signals.csv)
  2. SQLite table `momentum_signals` in settings.DB_PATH

This is the data source for future backtests of new entry filters (MC7 RVOL,
MC8 RSI trim, ORB structure, etc.). Without it, every filter change is a guess.

Schema (stable contract -- do NOT rename columns, only add):
  scan_id        TEXT   -- uuid per scan (groups all rows from one scan call)
  scanned_at     TEXT   -- ISO8601 UTC timestamp
  ticker         TEXT
  accepted       INTEGER-- 1 if signal fired, 0 if rejected
  reject_reason  TEXT   -- empty when accepted=1
  regime         TEXT   -- e.g. REGIME_1_BULL / REGIME_2_ELEVATED / REGIME_3_CRISIS
  strategy_version TEXT
  bankroll       REAL
  momentum_pool  REAL
  close          REAL
  vwap           REAL
  prev_day_high  REAL
  stop_loss      REAL
  target_1       REAL
  shares         INTEGER
  cost_ratio     REAL
  net_ev         REAL
  volume_ratio   REAL
  rvol_ratio     REAL   -- MC7 (NULL if MC7 disabled)
  rsi_7          REAL   -- MC8 (NULL if MC8 disabled)
  intraday_high  REAL
  intraday_low   REAL
  minutes_from_open INTEGER -- last-bar minutes from 9:15 IST (NULL if no ts)
  raw            TEXT   -- full result dict as JSON for future-proofing

The CSV is the primary write target (operator-friendly, grep-friendly, easy to
backtest with pandas). The SQLite table is a structured mirror for API queries.
Both are gated by MOMENTUM_LOG_ENABLED -- set False to disable entirely.
"""
from __future__ import annotations

import csv
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import aiosqlite

from config import settings


# -------------------------------------------------------------------
# Schema
# -------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    scan_id          TEXT    NOT NULL,
    scanned_at       TEXT    NOT NULL,
    ticker           TEXT    NOT NULL,
    accepted         INTEGER NOT NULL,
    reject_reason    TEXT,
    regime           TEXT,
    strategy_version TEXT,
    bankroll         REAL,
    momentum_pool    REAL,
    close            REAL,
    vwap             REAL,
    prev_day_high    REAL,
    stop_loss        REAL,
    target_1         REAL,
    shares           INTEGER,
    cost_ratio       REAL,
    net_ev           REAL,
    volume_ratio     REAL,
    rvol_ratio       REAL,
    rsi_7            REAL,
    intraday_high    REAL,
    intraday_low     REAL,
    minutes_from_open INTEGER,
    raw              TEXT,
    PRIMARY KEY (scan_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_{table}_scanned_at ON {table}(scanned_at);
CREATE INDEX IF NOT EXISTS idx_{table}_reject_reason ON {table}(reject_reason);
CREATE INDEX IF NOT EXISTS idx_{table}_ticker ON {table}(ticker);
"""

# Column order must match _row_from_dict
_COLUMNS = [
    "scan_id", "scanned_at", "ticker", "accepted", "reject_reason", "regime",
    "strategy_version", "bankroll", "momentum_pool", "close", "vwap",
    "prev_day_high", "stop_loss", "target_1", "shares", "cost_ratio", "net_ev",
    "volume_ratio", "rvol_ratio", "rsi_7", "intraday_high", "intraday_low",
    "minutes_from_open", "raw",
]


async def init_momentum_log_db(db_path: str) -> None:
    """Idempotent table + index creation. Safe to call from main()."""
    if not settings.MOMENTUM_LOG_ENABLED:
        return
    table = settings.MOMENTUM_LOG_DB_TABLE
    async with aiosqlite.connect(db_path) as db:
        for stmt in CREATE_TABLE_SQL.format(table=table).split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        await db.commit()


def _row_from_dict(
    scan_id: str,
    scanned_at: str,
    ticker: str,
    accepted: bool,
    result: dict,
    regime: Optional[str] = None,
    bankroll: Optional[float] = None,
    momentum_pool: Optional[float] = None,
) -> dict:
    """Extract a log row from a momentum result/reject dict.

    result may be a dict (rejected) or the same dict (accepted); we just read
    fields defensively and write whatever is present.
    """
    def _get(k: str) -> Any:
        return result.get(k) if isinstance(result, dict) else getattr(result, k, None)

    close_val = _get("close") or _get("entry_price")
    return {
        "scan_id":          scan_id,
        "scanned_at":       scanned_at,
        "ticker":           ticker,
        "accepted":         1 if accepted else 0,
        "reject_reason":    "" if accepted else (_get("reject_reason") or ""),
        "regime":           regime or _get("regime") or "",
        "strategy_version": _get("strategy_version") or settings.STRATEGY_VERSION,
        "bankroll":         bankroll,
        "momentum_pool":    momentum_pool,
        "close":            close_val,
        "vwap":             _get("vwap"),
        "prev_day_high":    _get("prev_day_high"),
        "stop_loss":        _get("stop_loss"),
        "target_1":         _get("target_1") or _get("target"),
        "shares":           _get("shares"),
        "cost_ratio":       _get("cost_ratio"),
        "net_ev":           _get("net_ev"),
        "volume_ratio":     _get("volume_ratio"),
        "rvol_ratio":       _get("rvol_ratio"),
        "rsi_7":            _get("rsi_7"),
        "intraday_high":    _get("intraday_high"),
        "intraday_low":     _get("intraday_low"),
        "minutes_from_open": _get("minutes_from_open"),
        "raw":              json.dumps(result, default=str) if result else None,
    }


def _ensure_csv_header(csv_path: str) -> None:
    """Create the CSV with header if it doesn't exist yet. Idempotent."""
    if os.path.exists(csv_path):
        return
    parent = os.path.dirname(csv_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()


async def log_momentum_batch(
    db_path: str,
    rows: Iterable[dict],
) -> Optional[str]:
    """Persist a batch of momentum signal rows to CSV + SQLite.

    Returns the scan_id used, or None if logging is disabled / rows empty.
    Each row must be produced by _row_from_dict (caller responsibility).
    """
    if not settings.MOMENTUM_LOG_ENABLED:
        return None
    rows_list = list(rows)
    if not rows_list:
        return None

    scan_id = rows_list[0]["scan_id"]

    # -- CSV write (append mode) --
    csv_path = settings.MOMENTUM_LOG_CSV_PATH
    try:
        _ensure_csv_header(csv_path)
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS, extrasaction="ignore")
            for row in rows_list:
                writer.writerow(row)
    except OSError as e:
        # Don't crash a live scan because the log disk is full / read-only
        # -- but make it visible in the next log line.
        import structlog
        log = structlog.get_logger()
        log.error("momentum_log_csv_write_failed", path=csv_path, error=str(e))

    # -- SQLite write (bulk insert) --
    table = settings.MOMENTUM_LOG_DB_TABLE
    try:
        placeholders = ",".join(["?"] * len(_COLUMNS))
        insert_sql = (
            f"INSERT OR REPLACE INTO {table} ({','.join(_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        values = [tuple(r.get(c) for c in _COLUMNS) for r in rows_list]
        async with aiosqlite.connect(db_path) as db:
            await db.executemany(insert_sql, values)
            await db.commit()
    except Exception as e:
        import structlog
        log = structlog.get_logger()
        log.error("momentum_log_sqlite_write_failed", table=table, error=str(e))

    return scan_id


def make_scan_id() -> str:
    """UUID4 for grouping all rows from one scan call."""
    return str(uuid.uuid4())


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_row(
    ticker: str,
    accepted: bool,
    result: dict,
    scan_id: str,
    scanned_at: str,
    regime: Optional[str] = None,
    bankroll: Optional[float] = None,
    momentum_pool: Optional[float] = None,
) -> dict:
    """Public helper so callers don't need to know the private one."""
    return _row_from_dict(
        scan_id=scan_id,
        scanned_at=scanned_at,
        ticker=ticker,
        accepted=accepted,
        result=result,
        regime=regime,
        bankroll=bankroll,
        momentum_pool=momentum_pool,
    )
