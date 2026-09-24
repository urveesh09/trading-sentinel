"""Read-only, evidence-first F&O daily audit report.

This module deliberately reports what the retained signal and ledger rows can
prove.  It does not recalculate a strategy, change a gate, or infer an order
from a row that stopped before admission.  In particular, repeated leg
evaluations for one underlying/direction/bar are grouped as one *decision
unit*, not marketed as several opportunities.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import aiosqlite

from config import settings
from performance import allocation_for_source

IST = ZoneInfo("Asia/Kolkata")
FNO_SOURCES = ("FNO_PAPER", "FNO_LIVE")


def _coerce_day(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


async def _connect_read_only(db_path: str) -> Optional[aiosqlite.Connection]:
    """Open an existing SQLite file read-only, never creating an audit target."""
    path = Path(db_path)
    if not path.is_file():
        return None
    return await aiosqlite.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ) as cursor:
        if await cursor.fetchone() is None:
            return set()
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        return {str(row[1]) for row in await cursor.fetchall()}


def _decode_audit_list(raw: Any) -> tuple[list[str], str]:
    """Decode an append-only list while labelling legacy/bad evidence honestly."""
    if raw is None:
        return [], "UNAVAILABLE_LEGACY_ROW"
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return [], "MALFORMED"
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [], "MALFORMED"
    return value, "PRESENT"


def _switch_policy(switch: str) -> dict[str, Any]:
    """Project the configured policy for a retained switch result.

    ``switch`` is already produced by ``kill_switch_status``.  The report
    retains it verbatim as observed evidence and separately reports the
    configuration threshold that defined the condition at report time.  It
    never claims an old row used a later configuration revision.
    """
    name = switch.split(maxsplit=1)[0]
    policy: dict[str, Any] = {"name": name, "observed": switch}
    if name == "daily_loss_halt":
        policy.update({
            "threshold_pct": float(settings.FNO_DAILY_KILL_PCT),
            "condition": "IST-day realized P&L <= -threshold_pct * evaluated pool",
        })
    elif name == "weekly_loss_halt":
        policy.update({
            "threshold_pct": float(settings.FNO_WEEKLY_KILL_PCT),
            "condition": "IST-week realized P&L <= -threshold_pct * evaluated pool",
        })
    elif name == "monthly_loss_halt":
        policy.update({
            "threshold_pct": float(settings.FNO_MONTHLY_KILL_PCT),
            "condition": "IST-month realized P&L <= -threshold_pct * evaluated pool",
        })
    elif name == "consecutive_loss_pause":
        policy.update({
            "maximum_consecutive_losses": int(settings.FNO_MAX_CONSECUTIVE_LOSSES),
            "condition": "trailing closed-position loss streak pauses entries through next calendar day",
        })
    elif name == "kill_switch_db_error":
        policy["condition"] = "database evidence unavailable; entry fails closed"
    else:
        policy["condition"] = "unrecognised retained switch evidence; inspect source row"
    return policy


def _empty_source(source: str) -> dict[str, Any]:
    return {
        "source": source,
        "mode": "paper" if source == "FNO_PAPER" else "live",
        "allocated_capital": round(float(allocation_for_source(source)), 2),
        "closed": {"event_count": 0, "realised_pnl": 0.0},
        "partial": {"event_count": 0, "realised_pnl": 0.0},
        "other_event_count": 0,
        "malformed_timestamp_count": 0,
        "costs": {
            "status": "UNAVAILABLE",
            "reason": "bankroll_ledger does not retain isolated F&O fee fields",
        },
    }


def _parse_aware_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


async def build_fno_daily_audit_report(db_path: str, day: date | str) -> dict[str, Any]:
    """Build a read-only daily report for one IST date.

    The output is JSON-safe and intentionally contains no expectancy score or
    qualification verdict.  Its close count is an outcome sample size; partial
    cash events are separate economic events, not additional completed trades.
    """
    report_day = _coerce_day(day)
    result: dict[str, Any] = {
        "schema_version": "fno_daily_audit_v1",
        "report_day_ist": report_day.isoformat(),
        "read_only": True,
        "signal_evidence": {
            "status": "UNAVAILABLE",
            "row_count": 0,
            "decision_unit_count": 0,
            "re_evaluation_count": 0,
            "reject_histogram": {},
            "kill_switch_blocks": [],
            "legacy_audit_fields": False,
        },
        "financial": {"status": "UNAVAILABLE", "by_source": {}},
        "expectancy": {
            "status": "NOT_ASSESSED",
            "reason": "A daily realised P&L or small close count does not establish expectancy.",
            "closed_outcome_sample_size": 0,
        },
        "errors": [],
    }
    db = await _connect_read_only(db_path)
    if db is None:
        result["errors"].append("database_unavailable_or_missing")
        return result

    try:
        signal_columns = await _table_columns(db, "fno_signals")
        if signal_columns:
            required = {"bar_ts", "underlying", "direction", "leg", "accepted", "reject_reason"}
            missing = sorted(required - signal_columns)
            if missing:
                result["signal_evidence"]["status"] = "UNAVAILABLE_SCHEMA"
                result["errors"].append("fno_signals_missing_columns:" + ",".join(missing))
            else:
                has_passed = "passed_gates_json" in signal_columns
                has_switches = "active_kill_switches_json" in signal_columns
                passed_expr = "passed_gates_json" if has_passed else "NULL"
                switches_expr = "active_kill_switches_json" if has_switches else "NULL"
                async with db.execute(
                    "SELECT bar_ts, underlying, direction, leg, accepted, reject_reason, "
                    f"{passed_expr} AS passed_gates_json, "
                    f"{switches_expr} AS active_kill_switches_json "
                    "FROM fno_signals WHERE bar_ts LIKE ? ORDER BY bar_ts, underlying, direction, leg",
                    (report_day.isoformat() + "%",),
                ) as cursor:
                    rows = await cursor.fetchall()

                units: dict[tuple[str, str, str], list[str]] = defaultdict(list)
                rejects: Counter[str] = Counter()
                blocks: list[dict[str, Any]] = []
                for bar_ts, underlying, direction, leg, accepted, reason, passed_raw, switches_raw in rows:
                    unit_key = (str(bar_ts or ""), str(underlying or ""), str(direction or ""))
                    units[unit_key].append(str(leg or ""))
                    if not bool(accepted) and reason:
                        rejects[str(reason)] += 1
                    if reason == "kill_switches_clear":
                        passed, passed_status = _decode_audit_list(passed_raw)
                        switches, switches_status = _decode_audit_list(switches_raw)
                        blocks.append({
                            "bar_ts": str(bar_ts or ""),
                            "underlying": str(underlying or ""),
                            "direction": str(direction or ""),
                            "leg": str(leg or ""),
                            "passed_gates": passed,
                            "passed_gates_status": passed_status,
                            "active_switches": [_switch_policy(item) for item in switches],
                            "active_switches_status": switches_status,
                        })
                result["signal_evidence"] = {
                    "status": "OK",
                    "row_count": len(rows),
                    "decision_unit_count": len(units),
                    "re_evaluation_count": max(0, len(rows) - len(units)),
                    "decision_units": [
                        {
                            "bar_ts": bar_ts,
                            "underlying": underlying,
                            "direction": direction,
                            "evaluation_count": len(legs),
                            "legs": legs,
                        }
                        for (bar_ts, underlying, direction), legs in sorted(units.items())
                    ],
                    "reject_histogram": dict(sorted(rejects.items())),
                    "kill_switch_blocks": blocks,
                    "legacy_audit_fields": not (has_passed and has_switches),
                }

        ledger_columns = await _table_columns(db, "bankroll_ledger")
        by_source = {source: _empty_source(source) for source in FNO_SOURCES}
        if ledger_columns:
            required = {"timestamp", "event_type", "pnl", "source"}
            missing = sorted(required - ledger_columns)
            if missing:
                result["financial"] = {"status": "UNAVAILABLE_SCHEMA", "by_source": by_source}
                result["errors"].append("bankroll_ledger_missing_columns:" + ",".join(missing))
            else:
                placeholders = ",".join("?" for _ in FNO_SOURCES)
                async with db.execute(
                    "SELECT timestamp, event_type, pnl, source FROM bankroll_ledger "
                    f"WHERE source IN ({placeholders})",
                    FNO_SOURCES,
                ) as cursor:
                    ledger_rows = await cursor.fetchall()
                for stamp, event_type, pnl, source in ledger_rows:
                    observed_at = _parse_aware_timestamp(stamp)
                    if observed_at is None:
                        by_source[str(source)]["malformed_timestamp_count"] += 1
                        continue
                    if observed_at.astimezone(IST).date() != report_day:
                        continue
                    entry = by_source[str(source)]
                    amount = float(pnl or 0.0)
                    if event_type == "TRADE_CLOSED":
                        entry["closed"]["event_count"] += 1
                        entry["closed"]["realised_pnl"] = round(
                            entry["closed"]["realised_pnl"] + amount, 2
                        )
                    elif event_type == "TRADE_PARTIAL":
                        entry["partial"]["event_count"] += 1
                        entry["partial"]["realised_pnl"] = round(
                            entry["partial"]["realised_pnl"] + amount, 2
                        )
                    else:
                        entry["other_event_count"] += 1
                result["financial"] = {"status": "OK", "by_source": by_source}
                result["expectancy"]["closed_outcome_sample_size"] = sum(
                    value["closed"]["event_count"] for value in by_source.values()
                )
    except aiosqlite.Error as exc:
        result["errors"].append(f"sqlite_error:{type(exc).__name__}")
    finally:
        await db.close()
    return result


def _main() -> None:
    """Render a report without modifying the supplied database."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Read-only F&O daily audit report")
    parser.add_argument("--db", required=True, help="Existing SQLite database path")
    parser.add_argument("--date", required=True, help="IST date, YYYY-MM-DD")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(build_fno_daily_audit_report(args.db, args.date)), indent=2, sort_keys=True))


if __name__ == "__main__":
    _main()
