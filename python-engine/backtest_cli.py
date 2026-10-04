"""[B0 2026-10-03] One offline entry point for shipped-strategy backtests.

    python backtest_cli.py catalogue
    python backtest_cli.py snapshot --db PATH | --container NAME --from D --to D --tickers A,B --out NEW.sqlite
    python backtest_cli.py coverage --snapshot S --strategy ID
    python backtest_cli.py run --snapshot S --strategy ID --from D --to D [--config JSON] --out NEW.json
    python backtest_cli.py compare A.json B.json
    python backtest_cli.py report R.json

Only registered Backtest Lab adapters can run (no arbitrary code or
callbacks); only their documented default assumptions are accepted. Every run
binds the code release, a secret-free settings hash and the frozen snapshot
hash. Nothing here calls the broker, places orders or uses Production routes.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import os

ENGINE_DIR = Path(__file__).resolve().parent
REPO_DIR = ENGINE_DIR.parent
COLLECTOR = REPO_DIR / "scripts" / "backtest_snapshot_collector.py"
SECRET_PATTERNS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "CHAT", "URL", "ACCOUNT", "WEBHOOK")
_SNAPSHOT_DDL = (
    "CREATE TABLE intraday_cache (ticker TEXT, interval TEXT, datetime TEXT, open REAL, high REAL,"
    " low REAL, close REAL, volume REAL, fetched_at TEXT, PRIMARY KEY(ticker, interval, datetime))",
    "CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,"
    " volume REAL, fetched_at TEXT, PRIMARY KEY(ticker, date))",
    "CREATE TABLE snapshot_manifest (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)


class CliError(RuntimeError):
    pass


def _new_file(path: str) -> Path:
    target = Path(path).resolve()
    if target.exists():
        raise CliError(f"refusing to overwrite existing file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _publish_new_file(temp_path: Path, target: Path) -> None:
    """Publish a completed artifact exactly once without an exists/write race."""
    try:
        # Hard-link creation is exclusive: unlike exists()+replace(), a rival
        # writer cannot be overwritten between the check and publication.
        os.link(temp_path, target)
    except FileExistsError as exc:
        raise CliError(f"refusing to overwrite existing file: {target}") from exc
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_json_new(path: str, payload: dict) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str, allow_nan=False)
            handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        _publish_new_file(temp_path, target)
        return target
    except Exception:
        try: temp_path.unlink()
        except FileNotFoundError: pass
        raise


def _rows_sha256(db: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for table, order in (("intraday_cache", "ticker,interval,datetime"), ("ohlcv_cache", "ticker,date")):
        digest.update(table.encode())
        cols = "ticker,interval,datetime,open,high,low,close,volume" if table == "intraday_cache" \
            else "ticker,date,open,high,low,close,volume"
        for row in db.execute(f"SELECT {cols} FROM {table} ORDER BY {order}"):
            digest.update(json.dumps(row, separators=(",", ":")).encode())
            digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


# ---- snapshot ------------------------------------------------------------------

def write_snapshot(collected: dict, out: str, *, source: str) -> dict:
    target = Path(out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
      with closing(sqlite3.connect(temporary)) as db:
        for ddl in _SNAPSHOT_DDL:
            db.execute(ddl)
        db.executemany("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,'snapshot')",
                       [tuple(r) for r in collected["intraday"]])
        db.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,'snapshot')",
                       [tuple(r) for r in collected["daily"]])
        manifest = {
            "schema": "sentinel_backtest_snapshot_v1", "source": source,
            "created_at": datetime.now(timezone.utc).isoformat(), "request": collected["request"],
            "row_counts": {"intraday": len(collected["intraday"]), "daily": len(collected["daily"])},
            "rows_sha256": _rows_sha256(db),
        }
        db.execute("INSERT INTO snapshot_manifest VALUES ('manifest', ?)",
                   (json.dumps(manifest, sort_keys=True),))
        db.commit()
      _publish_new_file(temporary, target)
      return manifest
    except Exception:
      try: temporary.unlink()
      except FileNotFoundError: pass
      raise


def snapshot(args) -> dict:
    tickers = [t for t in args.tickers.split(",") if t.strip()]
    if args.container:
        command = ["docker", "exec", "-i", args.container, "python", "-", "--db", args.db,
                   "--from", args.start, "--to", args.end, "--tickers", ",".join(tickers),
                   "--history-days", str(args.history_days)]
        done = subprocess.run(command, input=COLLECTOR.read_text(encoding="utf-8"), text=True,
                              capture_output=True, check=True, timeout=600)
        collected = json.loads(done.stdout)
        source = f"container:{args.container}:{args.db} (read-only stdlib collector)"
    else:
        sys.path.insert(0, str(COLLECTOR.parent))
        from backtest_snapshot_collector import collect
        collected = collect(args.db, args.start, args.end, tickers, args.history_days)
        source = f"sqlite:{Path(args.db).resolve()} (mode=ro)"
    return write_snapshot(collected, args.out, source=source)


def verify_snapshot(path: str) -> dict:
    snap = Path(path)
    if not snap.is_file():
        raise CliError(f"snapshot not found: {path}")
    with closing(sqlite3.connect(snap.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT value FROM snapshot_manifest WHERE key='manifest'").fetchone()
        if row is None:
            raise CliError("snapshot has no manifest")
        manifest = json.loads(row[0])
        actual = _rows_sha256(db)
    if actual != manifest.get("rows_sha256"):
        raise CliError(f"snapshot rows changed since it was frozen ({actual} != {manifest.get('rows_sha256')})")
    return manifest


# ---- policy manifest -------------------------------------------------------------

def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO_DIR, capture_output=True, text=True,
                              check=True, timeout=30).stdout.strip()
    except Exception:
        return None


def policy_manifest(strategy_id: str, adapter) -> dict:
    from backtest_catalogue import family_prefixes
    from config import settings
    modules = {"backtest_lab", "research_data_contracts", "config"}
    modules |= {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", adapter.metadata.engine)
                if (ENGINE_DIR / f"{token}.py").is_file()}
    # Bind recursively imported local source too: a changed cost/exit/helper
    # module invalidates reproducibility even if the adapter's engine string
    # did not name it directly.
    pending = list(modules)
    while pending:
        module = pending.pop()
        path = ENGINE_DIR / f"{module}.py"
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import): names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module: names = [node.module.split(".")[0]]
            for name in names:
                if name not in modules and (ENGINE_DIR / f"{name}.py").is_file():
                    modules.add(name); pending.append(name)
    dumped = settings.model_dump()
    safe = {k: v for k, v in dumped.items() if not any(p in k.upper() for p in SECRET_PATTERNS)}
    prefixes = tuple(family_prefixes(strategy_id))
    status = _git("status", "--porcelain")
    return {
        "git_commit": _git("rev-parse", "HEAD"), "git_dirty": None if status is None else bool(status),
        "engine_sha256": {m: hashlib.sha256((ENGINE_DIR / f"{m}.py").read_bytes()).hexdigest()
                          for m in sorted(modules)},
        "settings_sha256": "sha256:" + hashlib.sha256(json.dumps(
            safe, sort_keys=True, default=str).encode()).hexdigest(),
        "family_settings": {k: v for k, v in sorted(safe.items()) if k.startswith(prefixes)},
        "secret_keys_excluded": True,
    }


# ---- run / coverage / compare / report -----------------------------------------------

def _adapter(strategy_id: str):
    from backtest_lab import STRATEGY_REGISTRY
    if strategy_id not in STRATEGY_REGISTRY:
        raise CliError(f"unknown strategy_id {strategy_id!r}; see `catalogue`")
    return STRATEGY_REGISTRY[strategy_id]


def run(args) -> dict:
    from backtest_lab import BacktestRequest, BacktestUnavailable
    from backtest_reporting import validate_holdout
    from backtest_qualification import QualificationError, validate_run, record_evaluation, canonical_sha256
    adapter = _adapter(args.strategy)
    snap = verify_snapshot(args.snapshot)
    supplied = json.loads(args.config) if args.config else {}
    if not isinstance(supplied, dict):
        raise CliError("--config must be a JSON object")
    config = adapter.snapshot_config(supplied)
    assumptions = adapter.snapshot_assumptions({})
    request = BacktestRequest(args.strategy, args.start, args.end, config, assumptions)
    policy = policy_manifest(args.strategy, adapter)
    qualification = None
    try:
        if args.qualification_id and (args.holdout_from or args.holdout_to):
            raise CliError("a prospective qualification run cannot also use a date-only holdout declaration")
        holdout = validate_holdout(args.start, args.end, args.holdout_from, args.holdout_to)
        if args.qualification_id:
            if not args.qualification_registry:
                raise CliError("--qualification-id requires --qualification-registry")
            qualification = validate_run(
                registry=args.qualification_registry, qualification_id=args.qualification_id,
                strategy_id=args.strategy, window=(args.start, args.end),
                snapshot_sha256=snap["rows_sha256"], policy=policy, request_config=config,
            )
    except (ValueError, QualificationError) as exc:
        raise CliError(str(exc)) from exc
    report = {
        "schema": "sentinel_backtest_report_v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": args.strategy, "scope": adapter.metadata.scope,
        "request": {"from": args.start, "to": args.end, "config": config, "assumptions": assumptions},
        "snapshot": {"path": str(Path(args.snapshot).resolve()), "rows_sha256": snap["rows_sha256"],
                     "request": snap["request"], "source": snap["source"]},
        "policy": policy,
        "holdout": holdout,
        "qualification": qualification,
        "can_place_orders": False, "can_qualify": False,
    }
    with tempfile.TemporaryDirectory(prefix="sentinel-backtest-") as tmp:
        working = Path(tmp) / "snapshot.sqlite"
        shutil.copyfile(args.snapshot, working)          # the frozen snapshot is never opened read-write
        try:
            prepared = adapter.prepare(str(working), request)
            result = adapter.execute(prepared, request)
            metrics, warnings = adapter.normalize(result, request)
            report.update(state="SUCCEEDED", dataset_fingerprint=prepared.fingerprint,
                          metrics=metrics, warnings=warnings, result=result)
        except BacktestUnavailable as exc:
            report.update(state="UNAVAILABLE", reason=str(exc), metrics=None, warnings=[str(exc)])
    verify_snapshot(args.snapshot)
    target = _atomic_json_new(args.out, report)
    if qualification:
        try:
            record_evaluation(registry=args.qualification_registry,
                              qualification_id=args.qualification_id,
                              report_sha256=canonical_sha256(report))
        except QualificationError as exc:
            # The report exists, so suppressing failed evidence logging would
            # be less truthful than reporting a hard run failure to the caller.
            raise CliError(f"report written but qualification evaluation was not recorded: {exc}") from exc
    return {"output": str(target), "state": report["state"], "scope": report["scope"],
            "metrics": report.get("metrics")}


def freeze_holdout(args) -> dict:
    from backtest_qualification import QualificationError, freeze
    adapter = _adapter(args.strategy)
    if adapter.metadata.scope != "FULL_PORTFOLIO":
        raise CliError(
            f"{args.strategy} has {adapter.metadata.scope} fidelity; a prospective qualification "
            "requires a FULL_PORTFOLIO adapter with archived admission/context evidence"
        )
    snap = verify_snapshot(args.snapshot)
    supplied = json.loads(args.config) if args.config else {}
    if not isinstance(supplied, dict):
        raise CliError("--config must be a JSON object")
    config = adapter.snapshot_config(supplied)
    try:
        record = freeze(
            registry=args.registry, strategy_id=args.strategy,
            development_window=(args.start, args.end), holdout_window=(args.holdout_from, args.holdout_to),
            snapshot_sha256=snap["rows_sha256"], policy=policy_manifest(args.strategy, adapter),
            request_config=config,
        )
    except (ValueError, QualificationError) as exc:
        raise CliError(str(exc)) from exc
    return {"qualification_id": record["qualification_id"], "status": record["status"],
            "registry": str(Path(args.registry).resolve()), "holdout_window": record["holdout_window"]}


def coverage(args) -> dict:
    from research_data_contracts import load_daily_dataset, load_intraday_dataset
    adapter = _adapter(args.strategy)
    snap = verify_snapshot(args.snapshot)
    request = snap["request"]
    timeframe = adapter.metadata.timeframe
    interval = "minute" if timeframe.startswith("1 minute") or "minutes" in timeframe \
        else "15minute" if timeframe.startswith("15 minute") else None
    out = {"strategy_id": args.strategy, "scope": adapter.metadata.scope, "snapshot": snap["rows_sha256"]}
    if interval:
        intraday = load_intraday_dataset(args.snapshot, interval=interval, start=request["start"],
                                         end=request["end"], tickers=request["tickers"])
        out["intraday"] = {"interval": interval, "status_counts": intraday.manifest["status_counts"],
                           "row_counts": intraday.manifest["row_counts"]}
    daily = load_daily_dataset(args.snapshot, tickers=request["tickers"], before=request["end"])
    out["daily"] = {k: daily.manifest[k] for k in ("accepted_rows", "invalid", "zero_volume_days",
                                                   "suspected_corporate_actions", "off_calendar_dates")}
    return out


def _load_report(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "sentinel_backtest_report_v1":
        raise CliError(f"not a backtest report: {path}")
    return data


def compare(args) -> dict:
    a, b = _load_report(args.a), _load_report(args.b)
    if a["snapshot"]["rows_sha256"] != b["snapshot"]["rows_sha256"]:
        raise CliError("not comparable: different snapshots")
    if (a["request"]["from"], a["request"]["to"]) != (b["request"]["from"], b["request"]["to"]):
        raise CliError("not comparable: different windows")
    if a.get("scope") != b.get("scope"):
        raise CliError("not comparable: different fidelity scopes")
    if a.get("holdout") != b.get("holdout"):
        raise CliError("not comparable: different holdout declarations")
    keys = sorted(set(a.get("metrics") or {}) | set(b.get("metrics") or {}))
    diff = {}
    for key in keys:
        va, vb = (a.get("metrics") or {}).get(key), (b.get("metrics") or {}).get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
            diff[key] = {"a": va, "b": vb, "b_minus_a": vb - va}
        elif va != vb and not isinstance(va, (dict, list)):
            diff[key] = {"a": va, "b": vb}
    return {"a": {"strategy_id": a["strategy_id"], "scope": a["scope"], "state": a["state"]},
            "b": {"strategy_id": b["strategy_id"], "scope": b["scope"], "state": b["state"]},
            "snapshot": a["snapshot"]["rows_sha256"], "window": [a["request"]["from"], a["request"]["to"]], "holdout": a.get("holdout"),
            "metric_differences": diff}


def report(args) -> dict:
    from backtest_reporting import report_holdout, standard_metrics
    data = _load_report(args.report)
    return {"strategy_id": data["strategy_id"], "scope": data["scope"], "state": data["state"],
            "window": [data["request"]["from"], data["request"]["to"]],
            "metrics": data.get("metrics"), "warnings": data.get("warnings"),
            "git_commit": data["policy"]["git_commit"], "git_dirty": data["policy"]["git_dirty"],
            "snapshot": data["snapshot"]["rows_sha256"], "holdout": report_holdout(data.get("holdout")),
            "standard_metrics": standard_metrics(data)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalogue")
    p = sub.add_parser("snapshot")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db")
    src.add_argument("--container")
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)
    p.add_argument("--tickers", required=True)
    p.add_argument("--history-days", type=int, default=1100)
    p.add_argument("--out", required=True)
    p = sub.add_parser("coverage")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--strategy", required=True)
    p = sub.add_parser("run")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--strategy", required=True)
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)
    p.add_argument("--config")
    p.add_argument("--holdout-from")
    p.add_argument("--holdout-to")
    p.add_argument("--qualification-registry")
    p.add_argument("--qualification-id")
    p.add_argument("--out", required=True)
    p = sub.add_parser("freeze-holdout")
    p.add_argument("--registry", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--strategy", required=True)
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)
    p.add_argument("--holdout-from", required=True)
    p.add_argument("--holdout-to", required=True)
    p.add_argument("--config")
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("report")
    p.add_argument("report")
    args = parser.parse_args(argv)
    if args.command == "snapshot" and args.container and not args.db:
        args.db = "/data/cache.db"
    try:
        if args.command == "catalogue":
            from backtest_catalogue import catalogue, validate_catalogue
            problems = validate_catalogue()
            out = {"strategies": catalogue(), "problems": problems}
        else:
            out = {"snapshot": snapshot, "coverage": coverage, "run": run, "freeze-holdout": freeze_holdout,
                   "compare": compare, "report": report}[args.command](args)
    except (CliError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
