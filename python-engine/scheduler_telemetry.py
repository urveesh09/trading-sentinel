"""Bounded, read-only scheduler timing evidence.

APScheduler's own log lines are useful for a live operator but cannot answer
later whether a job was skipped, ran late, or simply returned because the
market was closed.  This module records what is actually known without
inventing scheduled/start times that an older invocation did not expose.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable

import aiosqlite


BOOT_ID = os.environ.get("TRADING_SENTINEL_BOOT_ID") or uuid.uuid4().hex
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduler_run_telemetry (
  run_id TEXT PRIMARY KEY,
  boot_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  scheduled_at TEXT,
  started_at TEXT,
  ended_at TEXT,
  elapsed_seconds REAL,
  result TEXT NOT NULL,
  reason TEXT,
  stage_durations_json TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduler_run_telemetry_job_time
  ON scheduler_run_telemetry(job_id, created_at DESC);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler telemetry timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


async def init_scheduler_telemetry(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def record_scheduler_event(
    db_path: str, *, job_id: str, event_kind: str, result: str,
    scheduled_at: datetime | None = None, started_at: datetime | None = None,
    ended_at: datetime | None = None, elapsed_seconds: float | None = None,
    reason: str | None = None, stage_durations: dict[str, Any] | None = None,
    retention: int = 5000,
) -> None:
    """Persist one bounded fact. Telemetry failure must never fail a job."""
    if not job_id or not event_kind or not result:
        raise ValueError("job_id, event_kind and result are required")
    if retention < 100:
        raise ValueError("retention must be at least 100")
    import json
    created_at = _utc_now()
    payload = json.dumps(stage_durations or {}, sort_keys=True, separators=(",", ":"))
    async with aiosqlite.connect(db_path, timeout=0.10) as db:
        await db.execute("PRAGMA busy_timeout=100")
        await db.executescript(_SCHEMA)
        await db.execute(
            "INSERT INTO scheduler_run_telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, BOOT_ID, job_id[:120], event_kind[:48], _iso(scheduled_at),
             _iso(started_at), _iso(ended_at), elapsed_seconds,
             result[:48], (reason or "")[:240], payload, _iso(created_at)),
        )
        # Keep a fixed forensic tail.  This is deliberately a bounded deletion
        # of telemetry only, never trading or research evidence.
        await db.execute(
            "DELETE FROM scheduler_run_telemetry WHERE run_id IN ("
            "SELECT run_id FROM scheduler_run_telemetry ORDER BY created_at DESC LIMIT -1 OFFSET ?) ",
            (retention,),
        )
        await db.commit()


async def start_scheduler_run(db_path: str, *, job_id: str, retention: int = 5000) -> str:
    """Durably mark a callback in-flight before awaiting business work.

    The marker is best-effort from the scheduler wrapper's perspective: a
    locked telemetry database must never prevent exit management or collection
    from running.  A process crash leaves an honest unfinished marker, which
    the report distinguishes from a current-process invocation.
    """
    if not job_id:
        raise ValueError("job_id is required")
    run_id = uuid.uuid4().hex
    now = _utc_now()
    async with aiosqlite.connect(db_path, timeout=0.10) as db:
        await db.execute("PRAGMA busy_timeout=100")
        await db.executescript(_SCHEMA)
        await db.execute(
            "INSERT INTO scheduler_run_telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, BOOT_ID, job_id[:120], "EXECUTION", None, _iso(now), None, None,
             "IN_FLIGHT", None, "{}", _iso(now)),
        )
        await db.execute(
            "DELETE FROM scheduler_run_telemetry WHERE run_id IN ("
            "SELECT run_id FROM scheduler_run_telemetry ORDER BY created_at DESC LIMIT -1 OFFSET ?)", (retention,),
        )
        await db.commit()
    return run_id


async def complete_scheduler_run(
    db_path: str, *, run_id: str, result: str, started_at: datetime, ended_at: datetime,
    elapsed_seconds: float, reason: str | None = None, stage_durations: dict[str, Any] | None = None,
    retention: int = 5000,
) -> bool:
    """Complete a pre-recorded run; returns false if its marker was absent."""
    import json
    payload = json.dumps(stage_durations or {}, sort_keys=True, separators=(",", ":"))
    async with aiosqlite.connect(db_path, timeout=0.10) as db:
        await db.execute("PRAGMA busy_timeout=100")
        await db.executescript(_SCHEMA)
        cursor = await db.execute(
            "UPDATE scheduler_run_telemetry SET ended_at=?,elapsed_seconds=?,result=?,reason=?,stage_durations_json=? "
            "WHERE run_id=? AND result='IN_FLIGHT'",
            (_iso(ended_at), elapsed_seconds, result[:48], (reason or "")[:240], payload, run_id),
        )
        await db.commit()
        return cursor.rowcount == 1


def instrument_async_job(
    db_path: str, job_id: str, callback: Callable[[], Awaitable[Any]], *, retention: int = 5000,
) -> Callable[[], Awaitable[Any]]:
    """Return a job wrapper that records execution without delaying the job.

    Recording happens after the business callback has completed and uses the
    writer's 100ms busy budget.  This avoids detached SQLite tasks surviving a
    shutdown while keeping an exit/lifecycle action independent of research
    queue waits. Scheduler misses/max-instance rejections are handled
    separately by ``attach_scheduler_listener``.
    """
    @wraps(callback)
    async def wrapped() -> Any:
        started = _utc_now()
        monotonic_started = time.monotonic()
        run_id: str | None = None
        try:
            run_id = await start_scheduler_run(db_path, job_id=job_id, retention=retention)
        except Exception:
            # Telemetry has a deliberately tiny lock budget and cannot become
            # a dependency of the business callback.
            pass
        result, outcome, reason, stages = None, "COMPLETED", None, None
        try:
            result = await callback()
            if isinstance(result, dict):
                stages = result.get("stage_durations_sec") if isinstance(result.get("stage_durations_sec"), dict) else None
                status = result.get("status") or result.get("state")
                if isinstance(status, str):
                    outcome = status[:48]
                if isinstance(result.get("reason"), str):
                    reason = result["reason"][:240]
            return result
        except asyncio.CancelledError:
            outcome, reason = "CANCELLED", "asyncio_cancelled"
            raise
        except Exception as exc:
            outcome, reason = "FAILED", type(exc).__name__
            raise
        finally:
            ended = _utc_now()
            elapsed = round(time.monotonic() - monotonic_started, 6)
            try:
                completed = run_id is not None and await complete_scheduler_run(
                    db_path, run_id=run_id, result=outcome, started_at=started, ended_at=ended,
                    elapsed_seconds=elapsed, reason=reason, stage_durations=stages, retention=retention,
                )
                if not completed:
                    await record_scheduler_event(db_path, job_id=job_id, event_kind="EXECUTION", result=outcome,
                                                 started_at=started, ended_at=ended, elapsed_seconds=elapsed,
                                                 reason=reason, stage_durations=stages, retention=retention)
            except Exception:
                # Observability must not recursively destabilise scheduled
                # work while a database is locked or storage is degraded.
                pass
    return wrapped


def telemetry_job(db_path: str, job_id: str, *, retention: int = 5000):
    """Decorator form preserves the scheduler's direct function registration."""
    def decorate(callback: Callable[[], Awaitable[Any]]) -> Callable[[], Awaitable[Any]]:
        return instrument_async_job(db_path, job_id, callback, retention=retention)
    return decorate


def attach_scheduler_listener(scheduler: Any, db_path: str, *, retention: int = 5000) -> None:
    """Persist APScheduler missed/max-instance facts when the loop is alive."""
    from apscheduler.events import EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED

    def listener(event: Any) -> None:
        code = getattr(event, "code", 0)
        if code == EVENT_JOB_MISSED:
            kind, result, reason = "SCHEDULER_REJECTED", "MISSED", "misfire_grace_exceeded"
        elif code == EVENT_JOB_MAX_INSTANCES:
            kind, result, reason = "SCHEDULER_REJECTED", "MAX_INSTANCES", "prior_invocation_in_flight"
        else:
            return
        scheduled = getattr(event, "scheduled_run_time", None)
        async def persist() -> None:
            try:
                await record_scheduler_event(
                    db_path, job_id=str(getattr(event, "job_id", "unknown")), event_kind=kind,
                    result=result, reason=reason, scheduled_at=scheduled, retention=retention,
                )
            except Exception:
                return
        try:
            asyncio.get_running_loop().create_task(persist())
        except RuntimeError:
            return
    scheduler.add_listener(listener, EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "max": None}
    values = sorted(values)
    def percentile(fraction: float) -> float:
        index = max(0, min(len(values) - 1, round((len(values) - 1) * fraction)))
        return round(values[index], 6)
    return {"p50": percentile(.50), "p95": percentile(.95), "max": round(values[-1], 6)}


async def scheduler_timing_report(db_path: str, *, limit: int = 500) -> dict[str, Any]:
    """Reproducible report; unavailable fields remain null rather than guessed."""
    if not 1 <= limit <= 5000:
        raise ValueError("limit must be within 1..5000")
    await init_scheduler_telemetry(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT job_id,event_kind,scheduled_at,started_at,ended_at,elapsed_seconds,result,reason,"
            "stage_durations_json,boot_id,created_at FROM scheduler_run_telemetry "
            "ORDER BY created_at DESC LIMIT ?", (limit,),
        )).fetchall()
    import json
    jobs: dict[str, dict[str, Any]] = {}
    events = []
    for row in reversed(rows):
        try:
            stages = json.loads(row[8]) if row[8] else {}
        except json.JSONDecodeError:
            stages = {}
        item = {"job_id": row[0], "event_kind": row[1], "scheduled_at": row[2],
                "started_at": row[3], "ended_at": row[4], "elapsed_seconds": row[5],
                "result": row[6], "reason": row[7] or None, "stage_durations": stages,
                "boot_id": row[9], "recorded_at": row[10]}
        events.append(item)
        bucket = jobs.setdefault(row[0], {"runs": 0, "executed_runs": 0, "rejected": 0, "in_flight": 0, "results": {}, "elapsed_samples": []})
        bucket["runs"] += 1  # retained compatibility: all scheduler facts
        if row[1] == "EXECUTION" and row[6] != "IN_FLIGHT":
            bucket["executed_runs"] += 1
        if row[1] == "EXECUTION" and row[6] == "IN_FLIGHT":
            bucket["in_flight"] += 1
        bucket["results"][row[6]] = bucket["results"].get(row[6], 0) + 1
        if row[1] == "SCHEDULER_REJECTED":
            bucket["rejected"] += 1
        if isinstance(row[5], (int, float)):
            bucket["elapsed_samples"].append(float(row[5]))
    for bucket in jobs.values():
        bucket["elapsed_seconds"] = _percentiles(bucket.pop("elapsed_samples"))
    inflight = [item | {"inflight_state": "CURRENT_PROCESS" if item["boot_id"] == BOOT_ID else "PREVIOUS_PROCESS_UNFINISHED"}
                for item in events if item["event_kind"] == "EXECUTION" and item["result"] == "IN_FLIGHT"]
    return {"boot_id": BOOT_ID, "events": events, "jobs": jobs, "inflight": inflight,
            "note": "scheduled_at is null for executions because APScheduler did not provide it to the callback; null is not a zero delay. In-flight markers survive crashes and are not inferred as successful runs."}
