"""[B0] Stdlib-only, read-only collector for backtest snapshots.

Safe to stream into a running container (``python - ...``): it imports only
the standard library, opens SQLite with ``mode=ro`` inside one read
transaction, never creates a database and bounds its output.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import sys

MAX_ROWS = 2_000_000
MAX_TICKERS = 200


def collect(db_path: str, start: str, end: str, tickers: list, history_days: int = 1100) -> dict:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError("end precedes start")
    chosen = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not 1 <= len(chosen) <= MAX_TICKERS:
        raise ValueError(f"between 1 and {MAX_TICKERS} explicit tickers are required")
    if not 0 <= history_days <= 4000:
        raise ValueError("history_days must be within 0..4000")
    path = Path(db_path)
    if not path.is_file():
        raise ValueError(f"database not found: {db_path}")
    marks = ",".join("?" for _ in chosen)
    history_start = (first - timedelta(days=history_days)).isoformat()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        intraday = db.execute(
            "SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache "
            f"WHERE ticker IN ({marks}) AND substr(datetime,1,10) BETWEEN ? AND ? "
            "ORDER BY ticker,interval,datetime", (*chosen, start, end)).fetchmany(MAX_ROWS + 1)
        daily = db.execute(
            "SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
            f"WHERE ticker IN ({marks}) AND date BETWEEN ? AND ? ORDER BY ticker,date",
            (*chosen, history_start, end)).fetchmany(MAX_ROWS + 1)
    if len(intraday) > MAX_ROWS or len(daily) > MAX_ROWS:
        raise ValueError("bounded snapshot exceeded; nothing truncated or written")
    return {"request": {"start": start, "end": end, "tickers": chosen, "history_days": history_days,
                        "history_start": history_start},
            "intraday": intraday, "daily": daily}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--history-days", type=int, default=1100)
    args = ap.parse_args()
    out = collect(args.db, args.start, args.end, args.tickers.split(","), args.history_days)
    json.dump(out, sys.stdout, allow_nan=False)


if __name__ == "__main__":
    main()
