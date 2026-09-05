#!/usr/bin/env python3
"""Deterministic, read-only Trading Sentinel runtime artifact audit.

This tool deliberately has no Docker, network, or application imports.  It
answers only from the saved files supplied on the command line and labels
missing evidence UNKNOWN instead of turning absence into a healthy zero.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
SCHEMA_VERSION = 1
_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "INFO": 3}
_PLAIN_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})")
_LEVEL = re.compile(r"\[(critical|error|warning|warn|info|debug|trace)\s*\]", re.I)
_LEVEL_ALIASES = {"warn": "warning"}
_PINO_LEVELS = {10: "trace", 20: "debug", 30: "info", 40: "warning",
                50: "error", 60: "critical"}


@dataclass(frozen=True)
class Evidence:
    path: str
    line: int
    timestamp: str | None


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class LogRecord:
    path: str
    line: int
    timestamp: datetime | None
    level: str | None
    message: str


def redact_text(value: object) -> str:
    """Remove credentials and operator identifiers from report text."""
    text = str(value)
    substitutions = (
        (r"(?i)\b(authorization)\s*[:=]\s*"
         r"(?!BLOCKED\b|AUTHORIZED\b|UNKNOWN\b|UNVERIFIED\b)[^\s,}]+",
         r"\1=<redacted>"),
        (r"(?i)\b(access[_-]?token|request[_-]?token|token|api[_-]?key|secret|password)"
         r"\s*[:=]\s*[^\s,}]+", r"\1=<redacted>"),
        (r"(?i)\b(chat[_-]?id)\s*[:=]\s*[-+]?\d+", r"\1=<redacted>"),
        (r"(?i)([?&](?:access_token|request_token|api_key|token)=)[^&\s]+",
         r"\1<redacted>"),
    )
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)

    # Public egress addresses are operational evidence, but need not be copied
    # into a shareable report.  Avoid replacing version-like dotted numbers.
    def _redact_ip(match: re.Match) -> str:
        candidate = match.group(0)
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return candidate
        return "<redacted-ip>"

    return re.sub(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", _redact_ip, text)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def parse_log(path: str | Path, target_date: str) -> list[LogRecord]:
    """Parse plain Python/agent logs and Pino JSON with normalized levels."""
    result: list[LogRecord] = []
    source = Path(path)
    contextual_date: str | None = None
    with source.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, 1):
            message = raw.rstrip("\r\n")
            timestamp = None
            level = None
            if message.lstrip().startswith("{"):
                try:
                    body = json.loads(message)
                except (TypeError, ValueError):
                    body = None
                if isinstance(body, dict):
                    timestamp = _parse_timestamp(str(body.get("time") or ""))
                    raw_level = body.get("level")
                    if isinstance(raw_level, int):
                        level = _PINO_LEVELS.get(raw_level)
                    elif raw_level is not None:
                        level = _LEVEL_ALIASES.get(str(raw_level).lower(),
                                                   str(raw_level).lower())
            else:
                match = _PLAIN_TS.match(message)
                if match:
                    timestamp = _parse_timestamp(f"{match.group(1)}T{match.group(2)}")
                level_match = _LEVEL.search(message)
                if level_match:
                    raw_level = level_match.group(1).lower()
                    level = _LEVEL_ALIASES.get(raw_level, raw_level)

            # Untimestamped lifecycle lines (for example Uvicorn's process-start
            # line) inherit the last timestamped line's day. This retains the
            # boot marker at 07:02 without importing an untimestamped marker
            # from a different day in a multi-day Docker log.
            if timestamp is not None:
                contextual_date = timestamp.date().isoformat()
                if contextual_date != target_date:
                    continue
            elif contextual_date is not None and contextual_date != target_date:
                continue
            result.append(LogRecord(str(source), line_no, timestamp, level, message))
    return result


def _evidence(record: LogRecord) -> Evidence:
    return Evidence(record.path, record.line,
                    record.timestamp.isoformat() if record.timestamp else None)


def _artifact_manifest(paths: Iterable[str | Path]) -> list[dict]:
    manifest = []
    for raw_path in paths:
        path = Path(raw_path)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
        manifest.append({
            "path": str(path), "bytes": stat.st_size, "sha256": digest.hexdigest(),
        })
    return manifest


def _job_name(raw: str) -> str:
    name = re.sub(r"^.*\.<locals>\.", "", raw.strip())
    return name


def _scheduler_skips(records: Sequence[LogRecord]) -> Counter:
    counts: Counter = Counter()
    patterns = (
        re.compile(r'Execution of job "(.+?) \(trigger:.*? skipped:', re.I),
        re.compile(r'Job "(.+?) \(trigger:.*? skipped', re.I),
    )
    for record in records:
        for pattern in patterns:
            match = pattern.search(record.message)
            if match:
                counts[_job_name(match.group(1))] += 1
                break
    return counts


def _gap_overlaps_market_hours(start: datetime, end: datetime) -> bool:
    """Return whether an IST interval intersects a weekday 09:15-15:30 session.

    A long gap is retained as raw evidence, but only a gap that actually
    overlaps a cash-market session is an operational freeze finding. This
    keeps overnight and pre-market intervals visible without mislabelling them
    as trading-hour availability failures.
    """
    if end <= start:
        return False
    start_ist = start.astimezone(IST)
    end_ist = end.astimezone(IST)
    current_day = start_ist.date()
    while current_day <= end_ist.date():
        if current_day.weekday() < 5:
            session_start = datetime.combine(current_day, time(9, 15), tzinfo=IST)
            session_end = datetime.combine(current_day, time(15, 30), tzinfo=IST)
            if start_ist < session_end and end_ist > session_start:
                return True
        current_day += timedelta(days=1)
    return False


def _liveness(records: Sequence[LogRecord], threshold_seconds: int) -> tuple[list[dict], list[Finding]]:
    epochs: list[dict] = []
    findings: list[Finding] = []
    epoch = 0
    last_tick: tuple[LogRecord, int, int] | None = None
    boot_pending = False
    for record in records:
        if re.search(r"Started server process|application startup complete", record.message, re.I):
            boot_pending = True
            continue
        match = re.search(r"penny_liveness_tick\s+count=(\d+)", record.message)
        if not match or record.timestamp is None:
            continue
        count = int(match.group(1))
        new_epoch = boot_pending or (last_tick is not None and count <= last_tick[1])
        if new_epoch:
            epoch += 1
            boot_pending = False
        if not epochs or epochs[-1]["epoch"] != epoch:
            epochs.append({
                "epoch": epoch, "first": record.timestamp.isoformat(),
                "last": record.timestamp.isoformat(), "ticks": 0,
                "restart_gap_seconds": None,
                "outside_market_gaps": [],
            })
            if last_tick is not None:
                restart_gap = (record.timestamp - last_tick[0].timestamp).total_seconds()
                epochs[-1]["restart_gap_seconds"] = int(restart_gap)
                if (restart_gap > threshold_seconds
                        and _gap_overlaps_market_hours(last_tick[0].timestamp, record.timestamp)):
                    findings.append(Finding(
                        "P1", "PROCESS_COVERAGE_GAP_ACROSS_BOOT",
                        f"process coverage gap of {int(restart_gap)}s crossed a boot boundary during market hours",
                        (_evidence(last_tick[0]), _evidence(record)),
                    ))
        else:
            gap = (record.timestamp - last_tick[0].timestamp).total_seconds() if last_tick else 0
            if gap > threshold_seconds:
                if _gap_overlaps_market_hours(last_tick[0].timestamp, record.timestamp):
                    findings.append(Finding(
                        "P0", "LIVENESS_GAP",
                        f"process liveness gap of {int(gap)}s overlapped market hours inside boot epoch {epoch}",
                        (_evidence(last_tick[0]), _evidence(record)),
                    ))
                else:
                    epochs[-1]["outside_market_gaps"].append({
                        "seconds": int(gap),
                        "from": last_tick[0].timestamp.isoformat(),
                        "to": record.timestamp.isoformat(),
                    })
        epochs[-1]["last"] = record.timestamp.isoformat()
        epochs[-1]["ticks"] += 1
        last_tick = (record, count, epoch)
    return epochs, findings


def _scheduler_progress(records: Sequence[LogRecord], threshold_seconds: int) -> tuple[dict, list[Finding]]:
    """Audit scheduler-loop progress independently from the process heartbeat."""
    ticks: list[tuple[LogRecord, int, str | None]] = []
    for record in records:
        match = re.search(r"scheduler_progress_tick\s+count=(\d+)", record.message)
        if match and record.timestamp is not None:
            boot_match = re.search(r"\bboot_id=([^\s]+)", record.message)
            ticks.append((record, int(match.group(1)),
                          boot_match.group(1) if boot_match else None))
    if not ticks:
        return {
            "status": "UNKNOWN", "ticks": 0, "last": None,
            "epochs": [], "outside_market_gaps": [],
        }, []

    findings: list[Finding] = []
    outside_market_gaps: list[dict] = []
    epochs: list[dict] = []
    last_record: LogRecord | None = None
    last_count: int | None = None
    last_boot_id: str | None = None
    for record, count, boot_id in ticks:
        # A boot id is authoritative when present. Older logs have no boot id,
        # so retain the monotonic counter reset as the conservative fallback.
        new_epoch = (
            last_record is None
            or (boot_id is not None and last_boot_id is not None and boot_id != last_boot_id)
            or (boot_id is None and last_boot_id is None and count <= last_count)
        )
        if new_epoch:
            restart_gap = ((record.timestamp - last_record.timestamp).total_seconds()
                           if last_record is not None else None)
            epochs.append({
                "boot_id": boot_id, "first": record.timestamp.isoformat(),
                "last": record.timestamp.isoformat(), "ticks": 0,
                "restart_gap_seconds": int(restart_gap)
                if restart_gap is not None else None,
            })
            if (restart_gap is not None and restart_gap > threshold_seconds
                    and _gap_overlaps_market_hours(last_record.timestamp, record.timestamp)):
                findings.append(Finding(
                    "P1", "SCHEDULER_COVERAGE_GAP_ACROSS_BOOT",
                    f"scheduler coverage gap of {int(restart_gap)}s crossed a boot boundary during market hours",
                    (_evidence(last_record), _evidence(record)),
                ))
        else:
            gap = (record.timestamp - last_record.timestamp).total_seconds()
            if gap > threshold_seconds:
                if _gap_overlaps_market_hours(last_record.timestamp, record.timestamp):
                    findings.append(Finding(
                        "P0", "SCHEDULER_PROGRESS_GAP",
                        f"scheduler progress gap of {int(gap)}s overlapped market hours",
                        (_evidence(last_record), _evidence(record)),
                    ))
                else:
                    outside_market_gaps.append({
                        "seconds": int(gap),
                        "from": last_record.timestamp.isoformat(),
                        "to": record.timestamp.isoformat(),
                    })
        epochs[-1]["last"] = record.timestamp.isoformat()
        epochs[-1]["ticks"] += 1
        last_record, last_count, last_boot_id = record, count, boot_id
    return {
        "status": "OBSERVED", "ticks": len(ticks),
        "last": asdict(_evidence(last_record)),
        "epochs": epochs,
        "outside_market_gaps": outside_market_gaps,
    }, findings


def _token_state(records: Sequence[LogRecord]) -> dict:
    state = "UNKNOWN"
    last: LogRecord | None = None
    for record in records:
        text = record.message.lower()
        next_state = None
        if "kite_token_restore_skipped" in text:
            next_state = "STALE"
        elif any(marker in text for marker in (
            "kite_token_set", "kite_token_injected", "kite_token_restored",
        )):
            next_state = "ARMED"
        elif any(marker in text for marker in (
            "token_exception", "kite_token_expired", "no_access_token",
        )):
            next_state = "MISSING_OR_EXPIRED"
        if next_state:
            state, last = next_state, record
    return {"status": state, "last_transition": asdict(_evidence(last)) if last else None}


def _order_authorization(records: Sequence[LogRecord]) -> tuple[dict, list[Finding]]:
    denied: list[LogRecord] = []
    for record in records:
        lower = record.message.lower()
        order_failure = (
            "kite_place_order_failed" in lower
            or "kite_order_authorization_denied" in lower
            or "order authorization rejected" in lower
        )
        permission = (
            re.search(r"status[=:]\s*(401|403)\b", lower) is not None
            and any(marker in lower for marker in (
                "static ip", "ip address", "not allowed to place orders",
                "permissionexception", "permission exception",
            ))
        ) or "kite_order_authorization_denied" in lower
        if order_failure and permission:
            denied.append(record)
    if not denied:
        return {"status": "UNKNOWN", "denials": 0, "last_transition": None}, []
    finding = Finding(
        "P0", "ORDER_AUTHORIZATION_BLOCKED",
        f"broker rejected {len(denied)} order request(s) for permission/static-IP reasons",
        tuple(_evidence(item) for item in denied[:5]),
    )
    return {
        "status": "BLOCKED", "denials": len(denied),
        "last_transition": asdict(_evidence(denied[-1])),
    }, [finding]


def _closure_contradictions(records: Sequence[LogRecord]) -> list[Finding]:
    no_order = [record for record in records
                if "penny_force_close_mis_exit" in record.message
                and re.search(r"order_id=(?:None|null)\b", record.message, re.I)]
    summaries: list[tuple[LogRecord, int]] = []
    for record in records:
        if "penny_force_close_mis_done" not in record.message:
            continue
        match = re.search(r"\bclosed=(\d+)\b", record.message)
        if match and int(match.group(1)) > 0:
            summaries.append((record, int(match.group(1))))
    if not no_order or not summaries:
        return []
    summary_record, claimed = summaries[-1]
    return [Finding(
        "P0", "UNCONFIRMED_EXIT_COUNTED_CLOSED",
        f"force-close summary claimed {claimed} closed position(s) while "
        f"{len(no_order)} exit attempt(s) had no broker order id",
        tuple([*(_evidence(item) for item in no_order[:5]), _evidence(summary_record)]),
    )]


def _pnl_evidence(db_snapshot: str | Path | None, target_date: str) -> dict:
    if db_snapshot is None:
        return {
            "status": "UNKNOWN", "realized_pnl": None,
            "reason": "no SQLite snapshot supplied",
        }
    path = Path(db_snapshot).resolve()
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        table = connection.execute("""
            SELECT 1 FROM sqlite_master WHERE type='table' AND name='bankroll_ledger'
        """).fetchone()
        if table is None:
            return {"status": "UNKNOWN", "realized_pnl": None,
                    "reason": "bankroll_ledger table absent"}
        rows = connection.execute(
            "SELECT timestamp,source,pnl FROM bankroll_ledger WHERE pnl IS NOT NULL"
        ).fetchall()
        totals: Counter = Counter()
        count = 0
        for row in rows:
            timestamp = _parse_timestamp(str(row["timestamp"] or ""))
            if timestamp is None or timestamp.date().isoformat() != target_date:
                continue
            pnl = float(row["pnl"])
            totals[str(row["source"] or "UNKNOWN")] += pnl
            count += 1
        return {
            "status": "OBSERVED_LEDGER", "realized_pnl": round(sum(totals.values()), 6),
            "events": count, "by_source": {key: round(value, 6)
                                              for key, value in sorted(totals.items())},
            "reason": "sum of dated bankroll_ledger rows in read-only snapshot",
        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return {"status": "UNKNOWN", "realized_pnl": None,
                "reason": redact_text(f"SQLite snapshot unreadable: {type(exc).__name__}")}
    finally:
        try:
            connection.close()
        except (NameError, sqlite3.Error):
            pass


def audit_runtime(
    *, python_log: str | Path, target_date: str,
    gateway_log: str | Path | None = None, agent_log: str | Path | None = None,
    db_snapshot: str | Path | None = None, liveness_gap_seconds: int = 300,
) -> dict:
    # Validate once so a typo cannot silently generate an empty clean report.
    datetime.strptime(target_date, "%Y-%m-%d")
    paths = [Path(python_log)]
    if gateway_log:
        paths.append(Path(gateway_log))
    if agent_log:
        paths.append(Path(agent_log))
    if db_snapshot:
        paths.append(Path(db_snapshot))
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    records: list[LogRecord] = []
    per_log: dict[str, int] = {}
    for path in paths:
        if db_snapshot and path.resolve() == Path(db_snapshot).resolve():
            continue
        parsed = parse_log(path, target_date)
        records.extend(parsed)
        per_log[str(path)] = len(parsed)

    level_counts = Counter(record.level for record in records if record.level)
    epochs, findings = _liveness(records, liveness_gap_seconds)
    scheduler_progress, scheduler_progress_findings = _scheduler_progress(
        records, liveness_gap_seconds
    )
    findings.extend(scheduler_progress_findings)
    token = _token_state(records)
    order_authorization, order_findings = _order_authorization(records)
    findings.extend(order_findings)
    findings.extend(_closure_contradictions(records))
    scheduler_skips = _scheduler_skips(records)
    findings.sort(key=lambda item: (_SEVERITY_ORDER[item.severity], item.code))

    report = {
        "schema_version": SCHEMA_VERSION,
        "target_date": target_date,
        "timestamp_policy": "plain timestamps=Asia/Kolkata; aware/JSON timestamps converted to Asia/Kolkata",
        "artifacts": _artifact_manifest(paths),
        "records_by_log": per_log,
        "levels": dict(sorted(level_counts.items())),
        "boot_epochs": epochs,
        "scheduler_progress": scheduler_progress,
        "token": token,
        "order_authorization": order_authorization,
        "scheduler_skips": dict(sorted(scheduler_skips.items())),
        "pnl": _pnl_evidence(db_snapshot, target_date),
        "findings": [
            {**asdict(item), "message": redact_text(item.message)} for item in findings
        ],
    }
    return report


def render_text(report: dict) -> str:
    lines = [
        f"Trading Sentinel offline runtime audit - {report['target_date']}",
        f"Evidence files: {len(report['artifacts'])}",
        "Levels: " + ", ".join(f"{key}={value}" for key, value in report["levels"].items()),
        f"Token final state: {report['token']['status']}",
        f"Order authorization: {report['order_authorization']['status']}",
        f"Scheduler progress: {report['scheduler_progress']['status']}",
        "Scheduler skips: " + (
            ", ".join(f"{key}={value}" for key, value in report["scheduler_skips"].items())
            or "none observed"
        ),
        f"Realized P&L evidence: {report['pnl']['status']}",
        "Findings:",
    ]
    if not report["findings"]:
        lines.append("  none")
    for finding in report["findings"]:
        lines.append(f"  {finding['severity']} {finding['code']}: {finding['message']}")
        for evidence in finding["evidence"]:
            lines.append(
                f"    {evidence['path']}:{evidence['line']}"
                + (f" ({evidence['timestamp']})" if evidence["timestamp"] else "")
            )
    return redact_text("\n".join(lines))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-log", required=True)
    parser.add_argument("--gateway-log")
    parser.add_argument("--agent-log")
    parser.add_argument("--db-snapshot")
    parser.add_argument("--date", required=True, dest="target_date")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--liveness-gap-seconds", type=int, default=300)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = audit_runtime(
        python_log=args.python_log, gateway_log=args.gateway_log,
        agent_log=args.agent_log, db_snapshot=args.db_snapshot,
        target_date=args.target_date,
        liveness_gap_seconds=args.liveness_gap_seconds,
    )
    if args.format == "json":
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
