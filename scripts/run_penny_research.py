"""Offline CLI for shipped classic Penny research replays.

``--strategy baseline`` (default) runs the Backtest Lab Penny minute evaluator
baseline. ``--strategy lifecycle`` runs the B2 exact classic Penny MIS lifecycle
over B1-validated bars (python-engine/penny_lifecycle_replay.py).

Collect-only is stdlib/read-only and safe to stream to a running container.
Replays use current Dev sources locally and never write to the source database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

MAX_ROWS = 100_000
LIFECYCLE_MAX_ROWS = 500_000
LIFECYCLE_MAX_TICKERS = 40


def collect(path: str, start: str, end: str, tickers: list[str], sample_count: int,
            strategy: str = "baseline") -> dict:
    if date.fromisoformat(end) < date.fromisoformat(start):
        raise ValueError("end precedes start")
    if strategy not in ("baseline", "lifecycle", "cnc"):
        raise ValueError("strategy must be baseline, lifecycle or cnc")
    if strategy == "cnc":
        return collect_cnc(path, start, end, tickers, sample_count)
    cap = LIFECYCLE_MAX_TICKERS if strategy == "lifecycle" else 20
    max_rows = LIFECYCLE_MAX_ROWS if strategy == "lifecycle" else MAX_ROWS
    if not 1 <= sample_count <= cap or len(tickers) > cap:
        raise ValueError(f"research sample bounded to {cap} tickers")
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
            if strategy == "lifecycle":
                rule = ("ALPHABETICAL_AT_LEAST_ONE_COMPLETE_375_BAR_MINUTE_SESSION_AND_PRIOR_20_DAILY_"
                        "COUNTS_AND_TIMESTAMPS_ONLY")
        if not chosen:
            raise ValueError("no eligible minute sample; no results fabricated")
        placeholders = ",".join("?" for _ in chosen)
        minute = db.execute(
            "SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache "
            f"WHERE ticker IN ({placeholders}) AND substr(datetime,1,10) BETWEEN ? AND ? ORDER BY ticker,datetime,interval",
            (*chosen, start, end),
        ).fetchmany(max_rows + 1)
        daily = db.execute(
            "SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
            f"WHERE ticker IN ({placeholders}) AND date<? ORDER BY ticker,date", (*chosen, end),
        ).fetchmany(max_rows + 1)
        if len(minute) > max_rows or len(daily) > max_rows:
            raise ValueError("bounded research input exceeded; no truncation")
    return {"requested_start": start, "requested_end": end, "tickers": chosen,
            "selection_rule": rule, "strategy": strategy, "intraday": minute, "daily": daily}


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


def collect_cnc(path: str, start: str, end: str, tickers: list[str], sample_count: int) -> dict:
    """[B2 CNC] 09:15-09:30 minute slices for entry days plus ~3 years of daily bars.

    Selection by counts/timestamps only: >= 250 daily rows before ``start`` and
    a 09:15 minute bar on at least one day in the window.
    """
    if not 1 <= sample_count <= LIFECYCLE_MAX_TICKERS or len(tickers) > LIFECYCLE_MAX_TICKERS:
        raise ValueError(f"research sample bounded to {LIFECYCLE_MAX_TICKERS} tickers")
    history_start = (date.fromisoformat(start) - timedelta(days=1100)).isoformat()
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        if tickers:
            chosen, rule = sorted(set(tickers)), "EXPLICIT_CLI_TICKERS"
        else:
            eligible = db.execute(
                "SELECT DISTINCT ticker FROM intraday_cache WHERE interval='minute' "
                "AND substr(datetime,1,10) BETWEEN ? AND ? AND substr(datetime,12,5)='09:15' "
                "ORDER BY ticker", (start, end)).fetchall()
            chosen = []
            for (ticker,) in eligible:
                if db.execute("SELECT count(*) FROM ohlcv_cache WHERE ticker=? AND date<?",
                              (ticker, start)).fetchone()[0] >= 250:
                    chosen.append(ticker)
                if len(chosen) == sample_count:
                    break
            rule = "ALPHABETICAL_0915_MINUTE_IN_WINDOW_AND_PRIOR_250_DAILY_COUNTS_ONLY"
        if not chosen:
            raise ValueError("no eligible CNC sample; no results fabricated")
        marks = ",".join("?" for _ in chosen)
        minute = db.execute(
            "SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache "
            f"WHERE ticker IN ({marks}) AND substr(datetime,1,10) BETWEEN ? AND ? "
            "AND substr(datetime,12,5) BETWEEN '09:15' AND '09:30' ORDER BY ticker,datetime,interval",
            (*chosen, start, end)).fetchmany(LIFECYCLE_MAX_ROWS + 1)
        daily = db.execute(
            "SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
            f"WHERE ticker IN ({marks}) AND date BETWEEN ? AND ? ORDER BY ticker,date",
            (*chosen, history_start, end)).fetchmany(LIFECYCLE_MAX_ROWS + 1)
        if len(minute) > LIFECYCLE_MAX_ROWS or len(daily) > LIFECYCLE_MAX_ROWS:
            raise ValueError("bounded research input exceeded; no truncation")
    return {"requested_start": start, "requested_end": end, "tickers": chosen,
            "selection_rule": rule, "strategy": "cnc", "intraday": minute, "daily": daily}


def replay_cnc(snapshot: dict, *, regime: str = "PR1_CALM") -> dict:
    """B1-validate the collected rows and run the exact CNC Connors paper lifecycle."""
    engine = Path(__file__).resolve().parents[1] / "python-engine"
    sys.path.insert(0, str(engine))
    from research_data_contracts import validate_daily_rows, validate_intraday_rows
    from research_penny_cnc_lifecycle import PennyCncConfig, run_penny_cnc_lifecycle
    start, end = snapshot["requested_start"], snapshot["requested_end"]
    intraday = validate_intraday_rows(snapshot["intraday"], interval="minute", start=start, end=end,
                                      tickers=snapshot["tickers"],
                                      source="sqlite:intraday_cache(read-only collector 09:15-09:30)")
    after_end = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    daily = validate_daily_rows(snapshot["daily"], tickers=snapshot["tickers"], before=after_end,
                                source="sqlite:ohlcv_cache(read-only collector)")
    result = run_penny_cnc_lifecycle(intraday, daily, PennyCncConfig(
        tickers=tuple(snapshot["tickers"]), regime=regime), start=start, end=end)
    sources = ("research_penny_cnc_lifecycle.py", "research_data_contracts.py",
               "penny_engine_connors.py", "penny_scanner.py", "position_tracker.py",
               "penny_executor.py", "penny_risk.py", "engine.py", "main.py", "config.py")
    return {"schema": "sentinel_penny_cnc_research_v1",
            "strategy_id": "penny_cnc_connors_lifecycle_1d",
            "sample": {k: v for k, v in snapshot.items() if k not in ("intraday", "daily")},
            "source_sha256": {name: hashlib.sha256((engine / name).read_bytes()).hexdigest()
                              for name in sources},
            "status": result["status"], "summary": result.get("summary"), "result": result,
            "can_place_orders": False, "can_qualify": False}


def replay_lifecycle(snapshot: dict, *, book: str = "PENNY_PAPER", regime: str = "PR1_CALM",
                     session_policy: str = "complete_only") -> dict:
    """B1-validate the collected rows and run the exact classic Penny MIS lifecycle."""
    engine = Path(__file__).resolve().parents[1] / "python-engine"
    sys.path.insert(0, str(engine))
    from penny_lifecycle_replay import PennyLifecycleConfig, run_penny_lifecycle
    from research_data_contracts import validate_daily_rows, validate_intraday_rows
    start, end = snapshot["requested_start"], snapshot["requested_end"]
    intraday = validate_intraday_rows(
        snapshot["intraday"], interval="minute", start=start, end=end, tickers=snapshot["tickers"],
        source="sqlite:intraday_cache(read-only collector)",
    )
    daily = validate_daily_rows(snapshot["daily"], tickers=snapshot["tickers"], before=end,
                                source="sqlite:ohlcv_cache(read-only collector)")
    config = PennyLifecycleConfig(tickers=tuple(snapshot["tickers"]), book=book, regime=regime,
                                  session_policy=session_policy)
    result = run_penny_lifecycle(intraday, daily, config, start=start, end=end)
    sources = ("penny_lifecycle_replay.py", "research_data_contracts.py", "penny_engine_breakout.py",
               "penny_scanner.py", "penny_executor.py", "penny_risk.py", "penny_shadow.py",
               "cost_schedules.py", "market_calendar.py", "config.py", "main.py")
    return {"schema": "sentinel_penny_lifecycle_research_v1",
            "strategy_id": "penny_breakout_mis_lifecycle_1m",
            "policy_scope": "CURRENT_DEV_CLASSIC_PENNY_MIS_LIFECYCLE_NOT_FULL_PORTFOLIO",
            "sample": {k: v for k, v in snapshot.items() if k not in ("intraday", "daily")},
            "source_sha256": {name: hashlib.sha256((engine / name).read_bytes()).hexdigest()
                              for name in sources},
            "status": result["status"], "summary": result["summary"], "result": result,
            "warnings": result["warnings"] + [
                "Coverage-selected sample is not a point-in-time Penny universe or portfolio return.",
                "Retrospective exploratory run; no prospective HOLDOUT, tuning or funding authority.",
            ],
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
    ap.add_argument("--strategy", choices=("baseline", "lifecycle", "cnc"), default="baseline")
    ap.add_argument("--book", choices=("PENNY_PAPER", "PENNY"), default="PENNY_PAPER")
    ap.add_argument("--regime", choices=("PR1_CALM", "PR2_ELEVATED", "PR3_HOT"), default="PR1_CALM")
    ap.add_argument("--session-policy", choices=("complete_only", "allow_gaps"), default="complete_only")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    symbols = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.container:
        command = ["docker", "exec", "-i", args.container, "python", "-", "--collect-only", "--db", args.db,
                   "--from", args.start, "--to", args.end, "--sample-count", str(args.sample_count),
                   "--strategy", args.strategy]
        if symbols:
            command.extend(["--tickers", ",".join(symbols)])
        completed = subprocess.run(command, input=Path(__file__).read_text(encoding="utf-8"),
                                   text=True, capture_output=True, check=True,
                                   timeout=300 if args.strategy in ("lifecycle", "cnc") else 60)
        snapshot = json.loads(completed.stdout)
    else:
        snapshot = collect(args.db, args.start, args.end, symbols, args.sample_count, args.strategy)
    if args.collect_only:
        print(json.dumps(snapshot, allow_nan=False))
        return
    try:
        if args.strategy == "lifecycle":
            report = replay_lifecycle(snapshot, book=args.book, regime=args.regime,
                                      session_policy=args.session_policy)
        elif args.strategy == "cnc":
            report = replay_cnc(snapshot, regime=args.regime)
        else:
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
    print(json.dumps({"output": str(target), "metrics": report.get("metrics"),
                      "summary": report.get("summary"), "state": report.get("state") or report.get("status"),
                      "sample": report.get("sample")}, default=str))


if __name__ == "__main__":
    main()
