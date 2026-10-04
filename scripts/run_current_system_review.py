"""Inert retrospective review: Production reads, current Dev replay, local artifacts.

No runtime caller, broker/provider calls, parameter search or qualification.
Run collect first, then independent --job commands, then fno/archive analysis.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "python-engine"
sys.path.insert(0, str(ENGINE))
from backtest_cli import _atomic_json_new, policy_manifest, verify_snapshot, write_snapshot

DEFAULT_OUT = ROOT / "docs/research/2026-10-03-current-system"
START, END = "2026-07-01", "2026-09-30"
FSTART, FEND = "2026-09-17", "2026-10-01"

# Only this standard-library collector is streamed into Production. It opens
# one read transaction; its stdout is captured into a Dev file, never printed.
COLLECTOR = r'''
import json,sqlite3
from pathlib import Path
from datetime import datetime,timezone
penny=json.loads(Path('/data/penny_static.json').read_text())
stocks=json.loads(Path('/app/data/nifty500.json').read_text())
symbols=lambda d: sorted({str(t['symbol']).upper() for t in d['tickers']})
pnames,snames=symbols(penny),symbols(stocks)
names=sorted(set(pnames+snames+['NIFTY 50','NIFTY BANK','NIFTYBEES']))
assert 1<=len(names)<=1000
marks=','.join('?' for _ in names)
c=sqlite3.connect('file:/data/cache.db?mode=ro',uri=True); c.row_factory=sqlite3.Row
c.execute('BEGIN')
out={'collected_at_utc':datetime.now(timezone.utc).isoformat(),
 'penny_universe':penny,'stock_universe':stocks,'tables':{},'operational':{},
 'request':{'start':'2026-07-01','end':'2026-09-30','tickers':names,
 'history_start':'2023-08-07','history_days':1059}}
def bounded(query,args=(),limit=2000000):
 rows=c.execute(query,args).fetchmany(limit+1)
 if len(rows)>limit: raise ValueError('bounded collection exceeded; no truncation')
 return [list(r) for r in rows]
out['intraday']=bounded('SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache WHERE ticker IN ('+marks+") AND substr(datetime,1,10) BETWEEN '2026-07-01' AND '2026-09-30' ORDER BY ticker,interval,datetime",names)
out['daily']=bounded('SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache WHERE ticker IN ('+marks+") AND date BETWEEN '2023-08-07' AND '2026-10-01' ORDER BY ticker,date",names)
for table in ('fno_positions','fno_dr_positions','bankroll_ledger','positions'):
 ddl=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
 if ddl is not None:
  rows=bounded('SELECT * FROM '+table,limit=100000)
  columns=[r[1] for r in c.execute('PRAGMA table_info('+table+')')]
  out['tables'][table]={'ddl':ddl[0],'columns':columns,'rows':rows}
for table,stamp,category,first,last in (
 ('penny_signals','scanned_at','leg','2026-07-01','2026-09-30'),
 ('momentum_signals','scanned_at','strategy_version','2026-07-01','2026-09-30'),
 ('fno_signals','evaluated_at','leg','2026-09-17','2026-10-01')):
 # SQLite converts aware UTC/IST stamps to local IST before date selection.
 where=" WHERE date("+stamp+",'+5 hours','+30 minutes') BETWEEN ? AND ?"
 query='SELECT substr(date('+stamp+",'+5 hours','+30 minutes'),1,7) month,"+category+' category,accepted,COALESCE(reject_reason,\'\') reason,COUNT(*) n,COUNT(DISTINCT ticker) tickers FROM '+table+where+' GROUP BY month,category,accepted,reason' if table!='fno_signals' else 'SELECT '+category+' category,accepted,COALESCE(reject_reason,\'\') reason,COUNT(*) n FROM '+table+where+' GROUP BY category,accepted,reason'
 cur=c.execute(query,(first,last));cols=[d[0] for d in cur.description]
 out['operational'][table]=[dict(zip(cols,r)) for r in cur]
out['operational']['penny_execution_events']=[dict(r) for r in c.execute("SELECT event_type,source,COUNT(*) n FROM penny_execution_events WHERE date(event_ts,'+5 hours','+30 minutes') BETWEEN '2026-07-01' AND '2026-09-30' GROUP BY event_type,source")]
out['operational']['penny_accepted']=[dict(r) for r in c.execute("SELECT scanned_at,ticker,leg,regime FROM penny_signals WHERE accepted=1 AND date(scanned_at,'+5 hours','+30 minutes') BETWEEN '2026-07-01' AND '2026-09-30' ORDER BY scanned_at")]
out['token_coverage']=[dict(r) for r in c.execute('SELECT instrument_token,interval,COUNT(*) n,MIN(datetime) first,MAX(datetime) last FROM intraday_cache_by_token GROUP BY instrument_token,interval')]
c.close()
json.dump(out,__import__('sys').stdout,allow_nan=False,separators=(',',':'),
 default=lambda value: {'__sqlite_blob_hex__':value.hex()} if isinstance(value,bytes) else (_ for _ in ()).throw(TypeError(type(value).__name__)))
'''


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def decode_sqlite_blob(value: dict):
    """Preserve malformed/legacy SQLite BLOB values; never coerce them to money."""
    if set(value) == {"__sqlite_blob_hex__"}:
        return bytes.fromhex(value["__sqlite_blob_hex__"])
    return value


def offline_collector(copied: Path) -> str:
    source = COLLECTOR.replace("Path('/data/penny_static.json')", f"Path({str(copied / 'penny_static.json')!r})")
    source = source.replace("Path('/app/data/nifty500.json')", f"Path({str(copied / 'nifty500.json')!r})")
    return source.replace("'file:/data/cache.db?mode=ro'", repr((copied / "cache.db").as_uri() + "?mode=ro"))


def local(out: Path) -> Path:
    folder = out / "_local"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def collect(out: Path, container: str) -> None:
    folder = local(out)
    raw = folder / "production-collection.json"
    running = subprocess.check_output(["docker", "inspect", "--format", "{{.State.Running}}", container], text=True).strip()
    source = COLLECTOR
    command = ["docker", "exec", "-i", container, "python", "-B", "-"]
    collection_mode = "Production mode=ro transaction"
    if running == "false":
        # A stopped engine cannot execute a collector. Copy its stable DB+WAL
        # and universe inputs, then perform the same read-only transaction in
        # Dev. Never restart it or treat a live main-file copy as consistent.
        copied = folder / "stopped-production"
        existing_copy = copied.exists()
        if existing_copy:
            receipt = json.loads((out / "stopped-source-manifest.json").read_text())
            for item in receipt["files"]:
                assert sha(copied / item["file"]) == item["sha256"], "frozen stopped copy changed"
        else:
          copied.mkdir(exist_ok=False)
          for name, remote in (("cache.db", "/data/cache.db"),
                             ("penny_static.json", "/data/penny_static.json"),
                             ("nifty500.json", "/app/data/nifty500.json")):
            subprocess.run(["docker", "cp", f"{container}:{remote}", str(copied / name)], check=True)
          for suffix in ("-wal", "-shm"):
            attempt = subprocess.run(["docker", "cp", f"{container}:/data/cache.db{suffix}", str(copied / f"cache.db{suffix}")], capture_output=True)
            if attempt.returncode and b"Could not find" not in attempt.stderr and b"No such" not in attempt.stderr:
                raise RuntimeError(attempt.stderr.decode(errors="replace"))
        if subprocess.check_output(["docker", "inspect", "--format", "{{.State.Running}}", container], text=True).strip() != "false":
            raise RuntimeError("engine resumed during stopped copy; no consistency claim")
        if not existing_copy:
            _atomic_json_new(str(out / "stopped-source-manifest.json"), {"container_was_stopped": True,
                "files": [{"file": p.name, "bytes": p.stat().st_size, "sha256": sha(p)}
                          for p in sorted(copied.iterdir()) if not p.name.endswith("-shm")]})
        source = offline_collector(copied)
        command = [sys.executable, "-B", "-"]
        collection_mode = "Stopped Production DB+WAL copied to Dev; local mode=ro transaction"
    with raw.open("xb") as handle:
        subprocess.run(command, input=source.encode(), stdout=handle, check=True)
    data = json.loads(raw.read_text(encoding="utf-8"), object_hook=decode_sqlite_blob)
    snapshot = write_snapshot(data, str(folder / "q3.sqlite"), source=collection_mode + "; current static universe")
    evidence = folder / "evidence.db"
    with sqlite3.connect(evidence) as db:
        for table, value in data["tables"].items():
            db.execute(value["ddl"])
            count = len(value["columns"])
            db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(count))})", value["rows"])
    for name in ("penny_universe", "stock_universe", "token_coverage"):
        _atomic_json_new(str(out / f"{name}.json"), data[name])
    op_raw = folder / "operational-raw.json"
    _atomic_json_new(str(op_raw), data["operational"])
    _atomic_json_new(str(out / "operational.json"), compact_operations(data["operational"], sha(op_raw)))
    _atomic_json_new(str(out / "collection-manifest.json"), {
        "collected_at_utc": data["collected_at_utc"], "input_sha256": sha(raw),
        "snapshot": snapshot, "evidence_sha256": sha(evidence),
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "quarter": [START, END], "fno_window": [FSTART, FEND],
        "membership_scope": "current static universe; historical membership unavailable", "collection_mode": collection_mode,
        "can_place_orders": False, "qualification": "NOT_ASSESSED",
    })
    print(json.dumps({"stage": "collected", "rows": snapshot["row_counts"], "raw_bytes": raw.stat().st_size}), flush=True)


def compact_operations(operations: dict, raw_sha256: str) -> dict:
    compact = {}
    for table, rows in operations.items():
        if table.endswith("signals"):
            counts = Counter()
            for row in rows:
                # Numeric values make otherwise identical rejection messages
                # unique. Summarize templates without changing count or verdict.
                reason = re.sub(r"-?\d+(?:\.\d+)?", "#", row["reason"])
                counts[(row.get("month"), row["category"], row["accepted"], reason)] += row["n"]
            compact[table] = [{"month": month, "category": category, "accepted": accepted,
                               "reason_template": reason, "n": n}
                              for (month, category, accepted, reason), n in sorted(counts.items())]
        else:
            compact[table] = rows
    compact["raw_sha256"] = raw_sha256
    compact["aggregation"] = "Numeric rejection values replaced by #; counts preserved; distinct-ticker counts are not summed."
    return compact


def coverage(out: Path) -> None:
    from research_data_contracts import load_daily_dataset, load_intraday_dataset, default_calendar
    from datetime import timedelta
    folder = local(out)
    db_path = str(folder / "q3.sqlite")
    penny, stocks = symbols(out, "penny"), symbols(out, "stock")
    quality = {"quarter": [START, END], "intraday": {}, "daily": {}}
    calendar = default_calendar()
    requested = []
    day = date.fromisoformat(START)
    while day <= date.fromisoformat(END):
        if calendar.is_trading_day(day): requested.append(day.isoformat())
        day += timedelta(days=1)
    quality["calendar"] = calendar.describe()
    quality["requested_sessions"] = len(requested)
    for family, names, interval in (("penny", penny, "minute"), ("momentum", stocks, "15minute")):
        data = load_intraday_dataset(db_path, interval=interval, start=START, end=END, tickers=names)
        months = {}
        sessions = {}
        for item in data.coverage:
            month = item["trading_date"][:7]
            counts = months.setdefault(month, Counter())
            counts[item["status"]] += 1
            sessions.setdefault(item["trading_date"], Counter())[item["status"]] += 1
        quality["intraday"][family] = {"manifest": data.manifest, "by_month": months, "by_session": sessions,
                                     "requested_names": len(names), "rows": sum(len(v) for v in data.bars.values())}
    daily = load_daily_dataset(db_path, tickers=stocks + ["NIFTY 50", "NIFTY BANK"], before="2026-10-01")
    quality["daily"] = {"manifest": daily.manifest, "index_warmup": {}}
    for stamp in ("2026-07-01", "2026-08-11", "2026-09-30"):
        cutoff = date.fromisoformat(stamp)
        n = {b.day for b in daily.known_before("NIFTY 50", cutoff)}
        b = {b.day for b in daily.known_before("NIFTY BANK", cutoff)}
        quality["daily"]["index_warmup"][stamp] = {"nifty_prior_rows": len(n), "banknifty_prior_rows": len(b),
                                                   "aligned_prior_rows": len(n & b), "aligned_atr_baseline_required": 214}
    _atomic_json_new(str(out / "coverage.json"), quality)
    print(json.dumps({"stage": "coverage", "sessions": len(requested), "penny": quality["intraday"]["penny"]["by_month"],
                      "momentum": quality["intraday"]["momentum"]["by_month"], "indices": quality["daily"]["index_warmup"]}), flush=True)


def symbols(out: Path, family: str) -> list[str]:
    data = json.loads((out / f"{family}_universe.json").read_text())
    return sorted({str(t["symbol"]).upper() for t in data["tickers"]})


def job_spec(out: Path, job: str) -> tuple[str, dict]:
    job = job.removesuffix("-final")
    penny, stocks = symbols(out, "penny"), symbols(out, "stock")
    specs = {
        "penny-mis": ("penny_breakout_mis_lifecycle_1m", {"tickers": penny}),
        "penny-mis-gaps": ("penny_breakout_mis_lifecycle_1m", {"tickers": penny, "session_policy": "allow_gaps"}),
        "penny-cnc": ("penny_cnc_connors_lifecycle_1d", {"tickers": penny}),
        "penny-joint": ("penny_joint_lifecycle_portfolio", {"mis_tickers": penny, "cnc_tickers": penny}),
        "penny-joint-gaps": ("penny_joint_lifecycle_portfolio", {"mis_tickers": penny, "cnc_tickers": penny, "session_policy": "allow_gaps"}),
        "swing": ("swing_regime_daily_evaluator", {"tickers": stocks}),
        "edge": ("penny_edge_daily_evaluator", {"tickers": penny}),
        "edge-retry": ("penny_edge_daily_evaluator", {"tickers": penny}),
        "momentum": ("momentum_intraday_15m_replay", {"tickers": stocks}),
        "momentum-covered": ("momentum_intraday_15m_replay", {"tickers": stocks}),
        "range": ("range_reversion_daily_evaluator", {"tickers": stocks}),
        "fno-full": ("fno_momentum_5m", {}),
    }
    return specs[job]


def run_job(out: Path, job: str) -> None:
    from backtest_lab import BacktestRequest, BacktestUnavailable, STRATEGY_REGISTRY
    folder = local(out)
    strategy, supplied = job_spec(out, job)
    adapter = STRATEGY_REGISTRY[strategy]
    config, assumptions = adapter.snapshot_config(supplied), adapter.snapshot_assumptions({})
    start, end = (FSTART, FEND) if job.removesuffix("-final") == "fno-full" else (START, END)
    if job.removesuffix("-final") == "momentum-covered":
        start = "2026-08-11"
    snapshot = verify_snapshot(str(folder / "q3.sqlite"))
    request = BacktestRequest(strategy, start, end, config, assumptions)
    report = {"schema": "sentinel_retrospective_module_review_v1", "job": job,
              "strategy_id": strategy, "scope": adapter.metadata.scope,
              "request": {"from": start, "to": end, "config": config, "assumptions": assumptions},
              "policy": policy_manifest(strategy, adapter), "snapshot": snapshot,
              "limitations": list(adapter.metadata.limitations),
              "qualification": "NOT_ASSESSED", "can_place_orders": False}
    _atomic_json_new(str(out / f"{job}-freeze.json"), report)
    print(f"{job}: frozen; preparing", flush=True)
    try:
        prepared = adapter.prepare(str(folder / "q3.sqlite"), request)
        print(f"{job}: prepared {prepared.row_count} rows; replaying", flush=True)
        result = adapter.execute(prepared, request)
        metrics, warnings = adapter.normalize(result, request)
        report.update(state="SUCCEEDED", dataset_fingerprint=prepared.fingerprint,
                      dataset=prepared.details, result=result, metrics=metrics, warnings=warnings)
    except BacktestUnavailable as exc:
        report.update(state="UNAVAILABLE", reason=str(exc), metrics=None)
    except Exception as exc:
        report.update(state="FAILED", reason=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(), metrics=None)
    verify_snapshot(str(folder / "q3.sqlite"))
    path = folder / f"{job}-report.json"
    _atomic_json_new(str(path), report)
    _atomic_json_new(str(out / f"{job}-receipt.json"), {
        "job": job, "scope": report["scope"], "state": report["state"],
        "reason": report.get("reason"), "result_status": report.get("result", {}).get("status"),
        "metrics": report.get("metrics"), "report_sha256": sha(path), "report": str(path.resolve()),
        "dataset_fingerprint": report.get("dataset_fingerprint"),
    })
    print(json.dumps({"job": job, "state": report["state"], "reason": report.get("reason"), "metrics": report.get("metrics")}, default=str), flush=True)


def copy_archives(out: Path, container: str) -> None:
    folder = local(out) / "archive" / "quotes"
    folder.mkdir(parents=True, exist_ok=True)
    days = ("2026-09-17", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24",
            "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01")
    files = []
    for day in days:
        target = folder / day
        if target.exists():
            raise ValueError(f"archive already exists: {target}")
        subprocess.run(["docker", "cp", f"{container}:/data/research/quotes/{day}", str(target)], check=True)
        for path in sorted(target.iterdir()):
            files.append({"file": str(path.relative_to(folder.parent)), "bytes": path.stat().st_size, "sha256": sha(path)})
        print(f"copied read-only quote evidence: {day}", flush=True)
    _atomic_json_new(str(out / "archive-manifest.json"), {"files": files, "days": list(days), "atomic_with_sqlite": False})


def fno_review(out: Path, *, post_entry: bool = False) -> None:
    import fno_exit_experiment as single
    import fno_dr_exit_experiment as dr
    from intraday_spread_archive_adapter import read_archived_quote_events
    sys.path.insert(0, str(ROOT / "scripts"))
    from assess_fno_profitability import collect as cash_collect, assess
    folder = local(out)
    prefix = "fno-post-entry" if post_entry else "fno"
    db_path, archive = folder / "evidence.db", folder / "archive"
    cash = assess(cash_collect(str(db_path), str(archive)), start=date.fromisoformat(FSTART), end=date.fromisoformat(FEND))
    if not post_entry:
        _atomic_json_new(str(out / "fno-recorded-cash.json"), cash)
    manifest = single.freeze_manifest(experiment_id="oct3-current-exit-review", candidate_policy=single.PARTIAL_POLICY)
    _atomic_json_new(str(out / f"{prefix}-single-exit-freeze.json"), manifest)
    dr_manifest = dr.freeze_manifest(experiment_id="oct3-current-dr-exit-review")
    _atomic_json_new(str(out / f"{prefix}-dr-exit-freeze.json"), dr_manifest)
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        srows = [dict(r) for r in db.execute("SELECT * FROM fno_positions WHERE entry_date BETWEEN ? AND ? ORDER BY entry_time", (FSTART, FEND))]
        drows = [dict(r) for r in db.execute("SELECT * FROM fno_dr_positions WHERE substr(opened_at,1,10) BETWEEN ? AND ? ORDER BY opened_at", (FSTART, FEND))]
        ledgers = [dict(r) for r in db.execute("SELECT * FROM bankroll_ledger")]
    single_attempts, dr_items, unavailable, inventory = [], [], [], []
    for day in sorted({r["entry_date"] for r in srows} | {r["opened_at"][:10] for r in drows}):
        print(f"F&O exit review: {day}", flush=True)
        events = read_archived_quote_events(archive, days=[day])
        contracts = {str((e.get("contract") or {}).get("instrument_token")): (e.get("contract") or {}) for e in events}
        futures = [c for c in contracts.values() if c.get("instrument_type") == "FUT" and c.get("underlying") == "NIFTY"]
        inventory.append({"day": day, "events": len(events), "futures": futures,
                          "option_tokens": sum(c.get("instrument_type") in ("CE", "PE") for c in contracts.values())})
        for row in (r for r in srows if r["entry_date"] == day):
            attempt = {"position_id": row["id"], "entry_day": day, "tradingsymbol": row["tradingsymbol"]}
            try:
                if len(futures) != 1:
                    raise single.FnoExitStudyError("futures identity unavailable or ambiguous in retained journal")
                entry = single.entry_from_position_row(str(db_path), row["id"])
                entry_at = datetime.fromisoformat(entry["entry_time"])
                selected_events = [e for e in events if datetime.fromisoformat(e["received_at_utc"].replace("Z", "+00:00")) > entry_at] if post_entry else events
                packet = single.build_packet_from_archive_events(selected_events, entry=entry,
                    future_token=int(futures[0]["instrument_token"]), study_id=f"oct3-{row['id']}")
                packet_path = folder / f"{prefix}-position-{row['id']}-packet.json"
                _atomic_json_new(str(packet_path), packet)
                result = single.build_fno_exit_experiment(packet_path, manifest)
                _atomic_json_new(str(folder / f"{prefix}-position-{row['id']}-exit.json"), result)
                attempt.update(state="ATTEMPTED", observations=len(packet["observations"]),
                               excluded=packet.get("provenance", {}).get("excluded", {}), pairs=result["pairs"])
            except Exception as exc:
                attempt.update(state="UNAVAILABLE", reason=f"{type(exc).__name__}: {exc}")
            single_attempts.append(attempt)
        for row in (r for r in drows if r["opened_at"][:10] == day):
            try:
                envelope = dr.entry_envelope(row)
                matched = [r for r in ledgers if r.get("origin_ref") == f"fno_dr_structure:{row['id']}" and r.get("source") == row["source"]]
                settlement = {"status": row["status"], "settlement_state": row.get("settlement_state"),
                              "exit_reason": row["exit_reason"], "position_net_pnl": row["pnl"],
                              "ledger_net_pnl": sum(r["pnl"] for r in matched) if matched else None}
                entry = dr.verify_entry(envelope, settlement)
                observations, excluded = dr.observations_from_archive(events, entry, max_age_seconds=int(dr_manifest["max_gap_seconds"]))
                dr_items.append((entry, observations, excluded))
            except Exception as exc:
                unavailable.append({"position_id": row["id"], "entry_day": day, "reason": f"{type(exc).__name__}: {exc}"})
    _atomic_json_new(str(out / f"{prefix}-exit-attempts.json"), {"scope": "RECORDED_ENTRY_EXIT_ONLY", "single_leg": single_attempts,
        "defined_risk": dr.build_report(dr_items, dr_manifest, unavailable=unavailable), "quote_inventory": inventory,
        "full_strategy_available": False, "qualification": "NOT_ASSESSED"})
    print(f"F&O attempts archived: {len(single_attempts)} single-leg, {len(drows)} defined-risk", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("collect", "job", "archives", "fno", "coverage"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--container", default="python-engine")
    parser.add_argument("--job")
    parser.add_argument("--post-entry", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.stage == "collect": collect(args.out, args.container)
    elif args.stage == "job": run_job(args.out, args.job)
    elif args.stage == "archives": copy_archives(args.out, args.container)
    elif args.stage == "coverage": coverage(args.out)
    else: fno_review(args.out, post_entry=args.post_entry)


if __name__ == "__main__":
    main()
