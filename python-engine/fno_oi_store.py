"""
[PARTNER-TIPS 2026-07-18] Chain-OI snapshot persistence (WS3).

The analytics tick snapshots the wide option chain every ~5 minutes; this
module persists per-strike OI (+ the derived PCR/max-pain/ATM-IV row for
the future) so intraday OI-change and buildup reads have a baseline to
diff against. SQLite on settings.DB_PATH like every other fno_* store --
WAL mode already arbitrates the writers (storage-split evaluated and
rejected 2026-07-15).

Volume: 3 underlyings x ~63 rows x ~72 snaps/day ~= 14k rows/day.
Trivial, but the host disk sits at 86% -- purge_older_than is wired into
the EOD job and is NOT optional.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import aiosqlite
import structlog

from fno_chain import ChainSnapshot

logger = structlog.get_logger()

# Kite OI is delayed/garbage in the first minutes of the session; a
# baseline taken before this time poisons every diff of the day.
BASELINE_MIN_HHMM = "09:25"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fno_chain_oi (
  snap_ts    TEXT NOT NULL,
  underlying TEXT NOT NULL,
  expiry     TEXT NOT NULL,
  strike     REAL NOT NULL,
  opt_type   TEXT NOT NULL,
  oi         INTEGER NOT NULL DEFAULT 0,
  volume     INTEGER NOT NULL DEFAULT 0,
  ltp        REAL NOT NULL DEFAULT 0,
  iv         REAL,
  PRIMARY KEY (underlying, snap_ts, strike, opt_type)
);
CREATE TABLE IF NOT EXISTS fno_fut_snap (
  snap_ts    TEXT NOT NULL,
  underlying TEXT NOT NULL,
  fut_ltp    REAL NOT NULL DEFAULT 0,
  fut_oi     INTEGER NOT NULL DEFAULT 0,
  pcr        REAL,
  max_pain   REAL,
  atm_iv     REAL,
  PRIMARY KEY (underlying, snap_ts)
);
"""


async def init_oi_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def persist_snapshot(
    db_path: str,
    underlying: str,
    snap: ChainSnapshot,
    pcr: Optional[float],
    max_pain: Optional[float],
    atm_iv_val: Optional[float],
) -> None:
    """One wide snapshot -> chain rows + one futures summary row.
    INSERT OR REPLACE: a re-run tick for the same second overwrites
    instead of raising on the PK."""
    ts = snap.taken_at.strftime("%Y-%m-%d %H:%M:%S")
    chain_rows = [
        (
            ts, underlying, snap.expiry.isoformat(), float(strike), ot,
            q.oi, q.volume, q.ltp, None,
        )
        for (strike, ot), q in snap.quotes.items()
    ]
    fut_oi = snap.fut_quote.oi if snap.fut_quote else 0
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO fno_chain_oi "
            "(snap_ts, underlying, expiry, strike, opt_type, oi, volume, ltp, iv) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            chain_rows,
        )
        await db.execute(
            "INSERT OR REPLACE INTO fno_fut_snap "
            "(snap_ts, underlying, fut_ltp, fut_oi, pcr, max_pain, atm_iv) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, underlying, snap.forward, fut_oi, pcr, max_pain, atm_iv_val),
        )
        await db.commit()


async def open_baseline(
    db_path: str, underlying: str, day_iso: str,
) -> Dict[Tuple[float, str], int]:
    """Per-strike OI of the FIRST snapshot at/after 09:25 today -- the
    intraday OI-change baseline. Empty dict when none exists yet."""
    lo = f"{day_iso} {BASELINE_MIN_HHMM}:00"
    hi = f"{day_iso} 23:59:59"
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT snap_ts FROM fno_fut_snap WHERE underlying=? "
            "AND snap_ts>=? AND snap_ts<=? ORDER BY snap_ts ASC LIMIT 1",
            (underlying, lo, hi),
        )
        row = await cur.fetchone()
        if row is None:
            return {}
        base_ts = row[0]
        cur = await db.execute(
            "SELECT strike, opt_type, oi FROM fno_chain_oi "
            "WHERE underlying=? AND snap_ts=?",
            (underlying, base_ts),
        )
        rows = await cur.fetchall()
    return {(float(r[0]), r[1]): int(r[2]) for r in rows}


async def latest_fut_row(
    db_path: str, underlying: str, before_ts: Optional[str] = None,
) -> Optional[dict]:
    """Most recent futures summary row (optionally strictly before a
    timestamp -- the event detector diffs current vs previous)."""
    q = (
        "SELECT snap_ts, fut_ltp, fut_oi, pcr, max_pain, atm_iv "
        "FROM fno_fut_snap WHERE underlying=?"
    )
    params = [underlying]
    if before_ts is not None:
        q += " AND snap_ts<?"
        params.append(before_ts)
    q += " ORDER BY snap_ts DESC LIMIT 1"
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(q, params)
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "snap_ts": row[0], "fut_ltp": row[1], "fut_oi": row[2],
        "pcr": row[3], "max_pain": row[4], "atm_iv": row[5],
    }


async def first_fut_row_today(
    db_path: str, underlying: str, day_iso: str,
) -> Optional[dict]:
    """First >=09:25 futures row today (the open baseline for PCR-shift
    and buildup reads)."""
    lo = f"{day_iso} {BASELINE_MIN_HHMM}:00"
    hi = f"{day_iso} 23:59:59"
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT snap_ts, fut_ltp, fut_oi, pcr, max_pain, atm_iv "
            "FROM fno_fut_snap WHERE underlying=? AND snap_ts>=? AND snap_ts<=? "
            "ORDER BY snap_ts ASC LIMIT 1",
            (underlying, lo, hi),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "snap_ts": row[0], "fut_ltp": row[1], "fut_oi": row[2],
        "pcr": row[3], "max_pain": row[4], "atm_iv": row[5],
    }


async def strike_ltp_series(
    db_path: str, underlying: str, day_iso: str,
    expiry: str, strike: float, opt_type: str,
    from_ts: Optional[str] = None,
) -> list:
    """[PARTNER-ENRICH 2026-07-19] Today's (snap_ts, ltp) series for one
    contract, optionally from a start timestamp (the signal bar). Zero
    LTPs are dropped: a 0 print is a no-quote artifact, not a price.
    Feeds the EOD 'what did the suggested option's premium actually do'
    line (T2b)."""
    lo = from_ts or f"{day_iso} 00:00:00"
    hi = f"{day_iso} 23:59:59"
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT snap_ts, ltp FROM fno_chain_oi "
            "WHERE underlying=? AND expiry=? AND strike=? AND opt_type=? "
            "AND snap_ts>=? AND snap_ts<=? AND ltp>0 ORDER BY snap_ts ASC",
            (underlying, expiry, strike, opt_type, lo, hi),
        )
        rows = await cur.fetchall()
    return [(r[0], float(r[1])) for r in rows]


async def purge_older_than(db_path: str, days: int, now: Optional[datetime] = None) -> int:
    """Delete rows older than `days`. Returns rows removed (chain table)."""
    now = now or datetime.now()
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "DELETE FROM fno_chain_oi WHERE snap_ts<?", (cutoff,)
        )
        removed = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        await db.execute("DELETE FROM fno_fut_snap WHERE snap_ts<?", (cutoff,))
        await db.commit()
    if removed:
        logger.info("fno_oi_purged rows=%d cutoff=%s", removed, cutoff)
    return removed
