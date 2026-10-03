"""Offline CLI for the shipped Backtest Lab Penny minute baseline.

Collect-only is stdlib/read-only and safe to stream to a running container.
Replay uses current Dev sources on an isolated temporary research database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

MAX_ROWS = 100_000


def collect(path: str, start: str, end: str, tickers: list[str], sample_count: int) -> dict:
    if date.fromisoformat(end) < date.fromisoformat(start):
        raise ValueError("end precedes start")
    if not 1 <= sample_count <= 20 or len(tickers) > 20:
        raise ValueError("research sample bounded to 20 tickers")
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        if tickers:
            chosen = sorted(set(tickers))
            rule = "EXPLICIT_CLI_TICKERS"
        else:
            eligible = db.execute(
                "SELECT ticker FROM intraday_cache WHERE interval='minute' "
                "AND substr(datetime,1,10) BETWEEN ? AND ? "
                "GROUP BY ticker,substr(datetime,1,10) "
                "HAVING count(*)>=375 AND min(substr(datetime,12,5))='09:15' "
                "AND max(substr(datetime,12,5))='15:29' ORDER BY ticker", (start, end)
            ).fetchall()
            chosen = []
            for (ticker,) in eligible:
                if ticker not in chosen and db.execute(
                    "SELECT count(*) FROM ohlcv_cache WHERE ticker=? AND date<?", (ticker, start)
                ).fetchone()[0] >= 20:
                    chosen.append(ticker)
                if len(chosen) == sample_count:
                    break
            rule = "ALPHABETICAL_AVAILABLE_FULL_SESSION_AND_PRIOR_20_DAILY_NO_PNL_SELECTION"
        if not chosen:
            raise ValueError("no eligible minute sample; no results fabricated")
        placeholders = ",".join("?" for _ in chosen)
        minute = db.execute(
            "SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache "
            f"WHERE ticker IN ({placeholders}) AND substr(datetime,1,10) BETWEEN ? AND ? ORDER BY ticker,datetime,interval",
            (*chosen, start, end),
        ).fetchmany(MAX_ROWS + 1)
        daily = db.execute(
            "SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
            f"WHERE ticker IN ({placeholders}) AND date<? ORDER BY ticker,date", (*chosen, end),
        ).fetchmany(MAX_ROWS + 1)
        if len(minute) > MAX_ROWS or len(daily) > MAX_ROWS:
            raise ValueError("bounded research input exceeded; no truncation")
    return {"requested_start": start, "requested_end": end, "tickers": chosen,
            "selection_rule": rule, "intraday": minute, "daily": daily}


def replay(snapshot: dict) -> dict:
    engine = Path(__file__).resolve().parents[1] / "python-engine"
    sys.path.insert(0, str(engine))
    from backtest_lab import BacktestRequest, STRATEGY_REGISTRY
    adapter = STRATEGY_REGISTRY["penny_breakout_intraday_1m_replay"]
    config = adapter.snapshot_config({"tickers": snapshot["tickers"], "variants": ["PEN_BASE"],
                                      "minimum_daily_bars": 20})
    request = BacktestRequest(adapter.metadata.strategy_id, snapshot["requested_start"], snapshot["requested_end"],
                             config, adapter.snapshot_assumptions({}))
    with tempfile.TemporaryDirectory(prefix="sentinel-penny-research-") as temporary:
        db_path = Path(temporary) / "evidence.db"
        with closing(sqlite3.connect(db_path)) as db:
            db.execute("CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
            db.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
            db.executemany("INSERT INTO intraday_cache VALUES(?,?,?,?,?,?,?,?)", snapshot["intraday"])
            db.executemany("INSERT INTO ohlcv_cache VALUES(?,?,?,?,?,?,?)", snapshot["daily"])
            db.commit()
        prepared = adapter.prepare(str(db_path), request)
        result = adapter.execute(prepared, request)
        metrics, warnings = adapter.normalize(result, request)
    sources = ("penny_intraday_replay.py", "penny_engine_breakout.py", "penny_shadow.py", "penny_risk.py", "backtest_lab.py", "config.py")
    return {"schema": "sentinel_penny_baseline_diagnostic_v1", "strategy_id": request.strategy_id,
            "policy_scope": "CURRENT_DEV_EVALUATOR_NOT_COMPLETE_DEPLOYED_PORTFOLIO", "request": request.__dict__,
            "sample": {k: v for k, v in snapshot.items() if k not in ("intraday", "daily")},
            "dataset_fingerprint": prepared.fingerprint,
            "source_sha256": {name: hashlib.sha256((engine / name).read_bytes()).hexdigest() for name in sources},
            "metrics": metrics, "result": result,
            "warnings": warnings + ["Coverage-selected sample is not a point-in-time Penny universe or portfolio return.",
                                    "Replay defaults to PR1_CALM and one-share shadow exits, not all runtime gates, sizing or smart EOD.",
                                    "Retrospective exploratory run; no prospective HOLDOUT or funding authority.",
                                    "Minute-bar timestamps and simulated immediate entry are model assumptions, not historical fill evidence."],
            "can_place_orders": False, "can_qualify": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="/data/cache.db")
    ap.add_argument("--container")
    ap.add_argument("--from", dest="start", default="2026-08-11")
    ap.add_argument("--to", dest="end", default="2026-08-20")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--sample-count", type=int, default=5)
    ap.add_argument("--collect-only", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    symbols = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.container:
        command = ["docker", "exec", "-i", args.container, "python", "-", "--collect-only", "--db", args.db,
                   "--from", args.start, "--to", args.end, "--sample-count", str(args.sample_count)]
        if symbols:
            command.extend(["--tickers", ",".join(symbols)])
        completed = subprocess.run(command, input=Path(__file__).read_text(encoding="utf-8"),
                                   text=True, capture_output=True, check=True, timeout=60)
        snapshot = json.loads(completed.stdout)
    else:
        snapshot = collect(args.db, args.start, args.end, symbols, args.sample_count)
    if args.collect_only:
        print(json.dumps(snapshot, allow_nan=False))
        return
    try:
        report = replay(snapshot)
    except (ValueError, RuntimeError) as exc:
        report = {"state": "UNAVAILABLE", "reason": str(exc), "can_place_orders": False, "can_qualify": False,
                  "sample": {k: v for k, v in snapshot.items() if k not in ("intraday", "daily")}}
    if not args.output:
        print(json.dumps(report, indent=2, allow_nan=False, default=str))
        return
    target = args.output.resolve()
    if not target.is_relative_to(Path(__file__).resolve().parents[1] / "docs") or target.exists():
        raise ValueError("output must be a new file under Dev docs")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "metrics": report.get("metrics"), "state": report.get("state"),
                      "sample": report.get("sample")}))


if __name__ == "__main__":
    main()
