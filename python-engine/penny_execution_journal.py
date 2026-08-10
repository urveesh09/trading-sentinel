"""Append-only, source-isolated execution lifecycle evidence for classic Penny."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Mapping

import aiosqlite

EVENT_SEQUENCE = {
    "CANDIDATE_ACCEPTED": 10,
    "VALIDATION_REJECTED": 20,
    "ENTRY_SUBMITTED": 30,
    "ENTRY_FILLED": 40,
    "ENTRY_REJECTED": 41,
    "ENTRY_TIMEOUT": 42,
    "SL_PLACED": 50,
    "SL_FAILED": 51,
    "UNWIND_SUBMITTED": 60,
    "UNWIND_CONFIRMED": 61,
    "UNPROTECTED": 62,
    "UNRESOLVED_RECONCILIATION": 89,
    "EXECUTION_RESULT": 80,
    "POSITION_CREATED": 90,
    "POSITION_PERSIST_FAILED": 91,
}
_SOURCES = {"PENNY", "PENNY_PAPER"}
_MODES = {"live", "paper"}
_SENSITIVE = ("token", "secret", "password", "authorization", "api_key")


def attempt_identity(candidate_identity: str, ticker: str, leg: str, source: str) -> tuple[str, str]:
    candidate = f"{candidate_identity}|{str(ticker).strip().upper()}|{str(leg).strip().upper()}"
    digest = hashlib.sha256(f"{candidate}|{source}".encode("utf-8")).hexdigest()
    return f"pen-{digest[:24]}", candidate


def _clean_payload(value, path: str = "payload"):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains non-finite number")
        return value
    if isinstance(value, Mapping):
        cleaned = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if any(marker in key.lower() for marker in _SENSITIVE):
                raise ValueError(f"{path} contains sensitive key {key!r}")
            cleaned[key] = _clean_payload(item, f"{path}.{key}")
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_clean_payload(item, f"{path}[]") for item in value]
    raise ValueError(f"{path} contains unsupported {type(value).__name__}")


async def init_penny_execution_journal(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS penny_execution_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_ts TEXT NOT NULL,
                scan_id TEXT NOT NULL,
                candidate_key TEXT NOT NULL,
                ticker TEXT NOT NULL,
                leg TEXT NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('PENNY','PENNY_PAPER')),
                mode TEXT NOT NULL CHECK(mode IN ('live','paper')),
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(attempt_id,sequence)
            )
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS penny_execution_events_no_update
            BEFORE UPDATE ON penny_execution_events
            BEGIN SELECT RAISE(ABORT, 'execution events are immutable'); END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS penny_execution_events_no_delete
            BEFORE DELETE ON penny_execution_events
            BEGIN SELECT RAISE(ABORT, 'execution events are immutable'); END
        """)
        await db.commit()


async def append_execution_event(
    db_path: str, *, attempt_id: str, scan_id: str, candidate_key: str,
    ticker: str, leg: str, source: str, mode: str, event_type: str,
    payload: Mapping | None = None, event_ts: str | None = None,
) -> bool:
    if event_type not in EVENT_SEQUENCE:
        raise ValueError(f"unsupported Penny execution event: {event_type}")
    if source not in _SOURCES or mode not in _MODES:
        raise ValueError("invalid Penny source or mode")
    if (source == "PENNY_PAPER") != (mode == "paper"):
        raise ValueError("Penny source/mode mismatch")
    ticker = str(ticker).strip().upper()
    if not all(str(item).strip() for item in (attempt_id, scan_id, candidate_key, ticker, leg)):
        raise ValueError("execution identity fields must be non-empty")
    body = json.dumps(_clean_payload(payload or {}), sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    if len(body) > 8192:
        raise ValueError("execution payload exceeds 8192 bytes")
    timestamp = event_ts or datetime.now(timezone.utc).isoformat()
    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise ValueError("event_ts must be timezone-aware")
    await init_penny_execution_journal(db_path)
    sequence = EVENT_SEQUENCE[event_type]
    async with aiosqlite.connect(db_path) as db:
        before = db.total_changes
        await db.execute("""
            INSERT OR IGNORE INTO penny_execution_events
                (attempt_id,sequence,event_ts,scan_id,candidate_key,ticker,leg,
                 source,mode,event_type,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (attempt_id, sequence, timestamp, scan_id, candidate_key, ticker,
              str(leg).upper(), source, mode, event_type, body))
        inserted = db.total_changes > before
        if not inserted:
            row = await (await db.execute("""
                SELECT event_type,payload_json,candidate_key,ticker,leg,source,mode
                FROM penny_execution_events WHERE attempt_id=? AND sequence=?
            """, (attempt_id, sequence))).fetchone()
            expected = (event_type, body, candidate_key, ticker,
                        str(leg).upper(), source, mode)
            if row != expected:
                raise ValueError("idempotency collision for Penny execution event")
        await db.commit()
    return inserted


async def execution_funnel(db_path: str, *, source: str) -> dict:
    if source not in _SOURCES:
        raise ValueError("source must be PENNY or PENNY_PAPER")
    await init_penny_execution_journal(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("""
            SELECT event_type,COUNT(*),COUNT(DISTINCT attempt_id)
            FROM penny_execution_events WHERE source=? GROUP BY event_type
        """, (source,))).fetchall()
    counts = {event: int(count) for event, count, _attempts in rows}
    attempts = max((int(value) for _event, _count, value in rows), default=0)
    return {
        "source": source, "mode": "paper" if source == "PENNY_PAPER" else "live",
        "attempts": attempts, "events": counts,
        "evaluator_accepts": counts.get("CANDIDATE_ACCEPTED", 0),
        "fills": counts.get("ENTRY_FILLED", 0),
        "protected": counts.get("SL_PLACED", 0),
        "positions": counts.get("POSITION_CREATED", 0),
        "failures": sum(counts.get(name, 0) for name in (
            "VALIDATION_REJECTED", "ENTRY_REJECTED", "ENTRY_TIMEOUT",
            "SL_FAILED", "UNPROTECTED", "UNRESOLVED_RECONCILIATION",
            "POSITION_PERSIST_FAILED",
        )),
    }


async def attempt_has_event(db_path: str, attempt_id: str, event_type: str) -> bool:
    if event_type not in EVENT_SEQUENCE:
        raise ValueError("unsupported Penny execution event")
    await init_penny_execution_journal(db_path)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT 1 FROM penny_execution_events WHERE attempt_id=? AND event_type=?",
            (attempt_id, event_type),
        )).fetchone()
    return row is not None


async def attempt_event_types(db_path: str, attempt_id: str) -> tuple[str, ...]:
    """Return immutable lifecycle state in sequence order for restart safety."""
    await init_penny_execution_journal(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("""
            SELECT event_type FROM penny_execution_events
            WHERE attempt_id=? ORDER BY sequence,id
        """, (attempt_id,))).fetchall()
    return tuple(row[0] for row in rows)


async def attempt_event_payload(
    db_path: str, attempt_id: str, event_type: str,
) -> dict | None:
    if event_type not in EVENT_SEQUENCE:
        raise ValueError("unsupported Penny execution event")
    await init_penny_execution_journal(db_path)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("""
            SELECT payload_json FROM penny_execution_events
            WHERE attempt_id=? AND event_type=?
        """, (attempt_id, event_type))).fetchone()
    return json.loads(row[0]) if row else None
