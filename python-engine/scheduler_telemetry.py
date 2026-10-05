"""Bounded, read-only scheduler timing evidence.

APScheduler's own log lines are useful for a live operator but cannot answer
later whether a job was skipped, ran late, or simply returned because the
market was closed.  This module records what is actually known without
inventing scheduled/start times that an older invocation did not expose.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable

import aiosqlite
from zoneinfo import ZoneInfo


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
CREATE TABLE IF NOT EXISTS scheduler_daily_summaries (
  session_date TEXT NOT NULL,
  job_id TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  runs INTEGER NOT NULL,
  result_counts_json TEXT NOT NULL,
  stage_stats_json TEXT NOT NULL,
  first_recorded_at TEXT NOT NULL,
  last_recorded_at TEXT NOT NULL,
  PRIMARY KEY (session_date, job_id, event_kind)
);
"""
IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)

# [TELEMETRY-FINAL 2026-10-05] Production audit: 18 current-boot rows stayed
# IN_FLIGHT although their jobs completed (F&O logs show outcome=ok); the final
# write failed silently inside a 100 ms busy budget. The completion write now
# retries with a growing budget, logs a failure, and keeps the final fact in
# memory so a later successful write can replay it. The report separates an
# active run from a stale marker and from a failed completion write.
COMPLETION_BUSY_BUDGETS_MS = (100, 250, 500)
PENDING_COMPLETION_LIMIT = 200
_ACTIVE_RUNS: set[str] = set()
_PENDING_COMPLETIONS: dict[str, dict[str, Any]] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler telemetry timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _session_date(value: datetime) -> str:
    """Use the market session date, not host/UTC midnight, for retention."""
    return value.astimezone(IST).date().isoformat()


# [S3 R4 2026-10-02] Durable elapsed distributions.  Fixed upper bounds in
# seconds; the last bucket is open-ended.  Counts survive raw-tail eviction.
ELAPSED_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0, 300.0)
_MARKET_OPEN_MIN, _MARKET_CLOSE_MIN = 9 * 60 + 15, 15 * 60 + 30


def _market_segment(value: datetime) -> str:
    """NSE continuous-session hours (IST, weekdays) versus everything else."""
    local = value.astimezone(IST)
    minute = local.hour * 60 + local.minute
    if local.weekday() < 5 and _MARKET_OPEN_MIN <= minute < _MARKET_CLOSE_MIN:
        return "market_hours"
    return "off_hours"


def _fold_elapsed(histograms: dict, segment: str, elapsed: float) -> None:
    hist = histograms.setdefault(segment, {"count": 0, "sum": 0.0, "max": 0.0,
                                           "buckets": [0] * (len(ELAPSED_BUCKETS) + 1)})
    if len(hist.get("buckets", [])) != len(ELAPSED_BUCKETS) + 1:
        hist["buckets"] = [0] * (len(ELAPSED_BUCKETS) + 1)
    index = next((i for i, bound in enumerate(ELAPSED_BUCKETS) if elapsed <= bound), len(ELAPSED_BUCKETS))
    hist["buckets"][index] += 1
    hist["count"] = int(hist["count"]) + 1
    hist["sum"] = round(float(hist["sum"]) + elapsed, 6)
    hist["max"] = max(float(hist["max"]), elapsed)


def elapsed_quantile_upper_bound(hist: dict, quantile: float) -> float | None:
    """Bucket upper bound containing the quantile (None if open-ended/empty)."""
    count = int(hist.get("count", 0))
    if count <= 0:
        return None
    target = math.ceil(quantile * count)
    running = 0
    for index, bucket in enumerate(hist.get("buckets", [])):
        running += int(bucket)
        if running >= target:
            return ELAPSED_BUCKETS[index] if index < len(ELAPSED_BUCKETS) else None
    return None


async def _ensure_summary_columns(db) -> None:
    columns = {row[1] for row in await (await db.execute(
        "PRAGMA table_info(scheduler_daily_summaries)")).fetchall()}
    if "elapsed_hist_json" not in columns:
        await db.execute(
            "ALTER TABLE scheduler_daily_summaries ADD COLUMN elapsed_hist_json TEXT NOT NULL DEFAULT '{}'")


async def _record_daily_summary(
    db, *, job_id: str, event_kind: str, result: str,
    occurred_at: datetime, stage_durations: dict[str, Any] | None,
    elapsed_seconds: float | None = None,
) -> None:
    """Fold one final scheduler fact into durable, bounded daily evidence."""
    import json
    await _ensure_summary_columns(db)
    session_date = _session_date(occurred_at)
    row = await (await db.execute(
        "SELECT runs,result_counts_json,stage_stats_json,first_recorded_at,elapsed_hist_json "
        "FROM scheduler_daily_summaries WHERE session_date=? AND job_id=? AND event_kind=?",
        (session_date, job_id[:120], event_kind[:48]),
    )).fetchone()
    if row:
        runs, result_counts, stage_stats, first, hist_json = row
        try:
            results = json.loads(result_counts)
            stages = json.loads(stage_stats)
        except json.JSONDecodeError:
            results, stages = {}, {}
        try:
            histograms = json.loads(hist_json or "{}")
        except json.JSONDecodeError:
            histograms = {}
    else:
        runs, results, stages, first, histograms = 0, {}, {}, _iso(occurred_at), {}
    if (isinstance(elapsed_seconds, (int, float)) and not isinstance(elapsed_seconds, bool)
            and math.isfinite(float(elapsed_seconds)) and float(elapsed_seconds) >= 0):
        _fold_elapsed(histograms, _market_segment(occurred_at), float(elapsed_seconds))
    results[result[:48]] = int(results.get(result[:48], 0)) + 1
    for name, value in (stage_durations or {}).items():
        if not isinstance(name, str) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(float(value)) or float(value) < 0:
            continue
        stat = stages.setdefault(name[:120], {"count": 0, "total": 0.0, "max": 0.0})
        stat["count"] = int(stat.get("count", 0)) + 1
        stat["total"] = round(float(stat.get("total", 0.0)) + float(value), 6)
        stat["max"] = max(float(stat.get("max", 0.0)), float(value))
    await db.execute(
        "INSERT OR REPLACE INTO scheduler_daily_summaries "
        "(session_date,job_id,event_kind,runs,result_counts_json,stage_stats_json,first_recorded_at,last_recorded_at,"
        "elapsed_hist_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (session_date, job_id[:120], event_kind[:48], int(runs) + 1,
         json.dumps(results, sort_keys=True, separators=(",", ":")),
         json.dumps(stages, sort_keys=True, separators=(",", ":")),
         first, _iso(occurred_at),
         json.dumps(histograms, sort_keys=True, separators=(",", ":"))),
    )


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
        if result != "IN_FLIGHT":
            await _record_daily_summary(
                db, job_id=job_id, event_kind=event_kind, result=result,
                occurred_at=ended_at or started_at or created_at,
                stage_durations=stage_durations, elapsed_seconds=elapsed_seconds,
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
    retention: int = 5000, busy_ms: int = 100,
) -> bool:
    """Complete a pre-recorded run; returns false if its marker was absent."""
    import json
    payload = json.dumps(stage_durations or {}, sort_keys=True, separators=(",", ":"))
    async with aiosqlite.connect(db_path, timeout=busy_ms / 1000) as db:
        await db.execute(f"PRAGMA busy_timeout={int(busy_ms)}")
        await db.executescript(_SCHEMA)
        existing = await (await db.execute(
            "SELECT job_id,event_kind FROM scheduler_run_telemetry WHERE run_id=? AND result='IN_FLIGHT'",
            (run_id,),
        )).fetchone()
        cursor = await db.execute(
            "UPDATE scheduler_run_telemetry SET ended_at=?,elapsed_seconds=?,result=?,reason=?,stage_durations_json=? "
            "WHERE run_id=? AND result='IN_FLIGHT'",
            (_iso(ended_at), elapsed_seconds, result[:48], (reason or "")[:240], payload, run_id),
        )
        if cursor.rowcount == 1 and existing is not None:
            await _record_daily_summary(
                db, job_id=existing[0], event_kind=existing[1], result=result,
                occurred_at=ended_at, stage_durations=stage_durations,
                elapsed_seconds=elapsed_seconds,
            )
        await db.commit()
        return cursor.rowcount == 1


async def scheduler_daily_summary_report(
    db_path: str, *, session_date: str | None = None,
) -> dict[str, Any]:
    """Read durable market-session rollups without relying on raw retention."""
    await init_scheduler_telemetry(db_path)
    selected = session_date or _session_date(_utc_now())
    if len(selected) != 10:
        raise ValueError("session_date must be ISO YYYY-MM-DD")
    async with aiosqlite.connect(db_path) as db:
        await _ensure_summary_columns(db)
        await db.commit()
        rows = await (await db.execute(
            "SELECT job_id,event_kind,runs,result_counts_json,stage_stats_json,first_recorded_at,last_recorded_at,"
            "elapsed_hist_json FROM scheduler_daily_summaries WHERE session_date=? ORDER BY job_id,event_kind",
            (selected,),
        )).fetchall()
    import json
    summaries = []
    for row in rows:
        try:
            results, stages = json.loads(row[3]), json.loads(row[4])
        except json.JSONDecodeError:
            results, stages = {}, {}
        try:
            histograms = json.loads(row[7] or "{}")
        except json.JSONDecodeError:
            histograms = {}
        elapsed = {}
        for segment, hist in sorted(histograms.items()):
            count = int(hist.get("count", 0))
            elapsed[segment] = {
                "count": count, "max": hist.get("max"),
                "mean": round(float(hist["sum"]) / count, 6) if count else None,
                "p50_upper_bound": elapsed_quantile_upper_bound(hist, 0.50),
                "p95_upper_bound": elapsed_quantile_upper_bound(hist, 0.95),
                "bucket_upper_bounds": list(ELAPSED_BUCKETS) + ["inf"],
                "buckets": hist.get("buckets"),
            }
        summaries.append({
            "job_id": row[0], "event_kind": row[1], "runs": row[2],
            "results": results, "stage_stats": stages,
            "elapsed_distribution": elapsed,
            "first_recorded_at": row[5], "last_recorded_at": row[6],
        })
    return {
        "session_date": selected, "summaries": summaries,
        "note": "Daily summaries contain final scheduler facts only; unfinished crash markers remain visible in the raw telemetry report until separately reconciled.",
    }


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
            _ACTIVE_RUNS.add(run_id)
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
            final = {"job_id": job_id, "result": outcome, "started_at": started, "ended_at": ended,
                     "elapsed_seconds": elapsed, "reason": reason, "stage_durations": stages}
            # Observability must not destabilise scheduled work: a failed
            # final write is logged and parked, never raised.
            if await _write_final(db_path, run_id, final, retention):
                await _replay_pending(db_path, retention)
            else:
                _park_completion(run_id, final)
            if run_id is not None:
                _ACTIVE_RUNS.discard(run_id)
    return wrapped


async def _write_final(db_path: str, run_id: str | None, final: dict[str, Any], retention: int) -> bool:
    """Persist one final fact with bounded retries; True when it is durable."""
    error: str | None = None
    for budget in COMPLETION_BUSY_BUDGETS_MS:
        try:
            completed = run_id is not None and await complete_scheduler_run(
                db_path, run_id=run_id, result=final["result"], started_at=final["started_at"],
                ended_at=final["ended_at"], elapsed_seconds=final["elapsed_seconds"],
                reason=final["reason"], stage_durations=final["stage_durations"],
                retention=retention, busy_ms=budget,
            )
            if not completed:
                await record_scheduler_event(
                    db_path, job_id=final["job_id"], event_kind="EXECUTION", result=final["result"],
                    started_at=final["started_at"], ended_at=final["ended_at"],
                    elapsed_seconds=final["elapsed_seconds"], reason=final["reason"],
                    stage_durations=final["stage_durations"], retention=retention,
                )
            return True
        except Exception as exc:  # noqa: BLE001 - telemetry is best-effort
            error = f"{type(exc).__name__}: {exc}"[:240]
    logger.warning("scheduler_telemetry_completion_write_failed job_id=%s run_id=%s result=%s error=%s",
                   final["job_id"], run_id, final["result"], error)
    final["write_error"] = error
    return False


def _park_completion(run_id: str | None, final: dict[str, Any]) -> None:
    final["run_id"] = run_id
    _PENDING_COMPLETIONS[run_id or f"unmarked:{uuid.uuid4().hex}"] = final
    while len(_PENDING_COMPLETIONS) > PENDING_COMPLETION_LIMIT:
        _PENDING_COMPLETIONS.pop(next(iter(_PENDING_COMPLETIONS)))


async def _replay_pending(db_path: str, retention: int) -> None:
    """After a durable write, retry parked final facts, oldest first."""
    for key in list(_PENDING_COMPLETIONS)[:20]:
        final = _PENDING_COMPLETIONS.get(key)
        if final is None:
            continue
        if not await _write_final(db_path, final.get("run_id"), final, retention):
            return
        _PENDING_COMPLETIONS.pop(key, None)
        logger.info("scheduler_telemetry_completion_replayed job_id=%s run_id=%s",
                    final["job_id"], final.get("run_id"))


def pending_completion_writes() -> list[dict[str, Any]]:
    """Final facts this process has not persisted yet (bounded, oldest first)."""
    return [{"run_id": f.get("run_id"), "job_id": f["job_id"], "result": f["result"],
             "ended_at": _iso(f["ended_at"]), "elapsed_seconds": f["elapsed_seconds"],
             "write_error": f.get("write_error")} for f in _PENDING_COMPLETIONS.values()]


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


# [WORKFLOW-H H2 2026-09-13] Priority-tier mapping. Plan §12 mandates:
# "Prioritize order exits and public advice management, then candidate
# scans, then research." The four tiers in priority order are:
#
#   exit       -- order exits, force-closes, EOD digest, force-close MIS.
#                A latency here means a real position is unprotected.
#   advice     -- daily attribution, hourly reports, premarket
#                summaries, watchdog jobs. These produce operator
#                visibility; a missed run hides information but
#                does not by itself leave a position unprotected.
#   scan       -- penny scans, connors scan, FNO tick, regime
#                compute. These are the candidate-discovery loops;
#                latency here means fewer candidates, not more risk.
#   research   -- proactive shadow, research quote collection,
#                archive jobs. Offline; latency here is invisible
#                to the operator for the duration of the run.
#
# Anything not in the map lands in the ``other`` tier. A future agent
# who adds a job that doesn't fit the taxonomy must add it here, NOT
# silently drop it into ``other``. The taxonomy comment is the
# authoritative reference; the table below is the implementation.
JOB_TIER_MAP: dict[str, str] = {
    # exit -- order exits / force closes / EOD digest
    "penny_edge_exit": "exit",
    "penny_force_close_mis": "exit",
    "penny_eod_check": "exit",
    "penny_eod_digest": "exit",
    "fno_hourly_report": "exit",
    # advice -- operator-facing reports / watchdogs
    "penny_daily_attribution": "advice",
    "penny_hourly_report": "advice",
    "penny_premarket_report": "advice",
    "penny_heatmap": "advice",
    "penny_accept_watchdog": "advice",
    "fno_accept_watchdog": "advice",
    "partner_morning_brief": "advice",
    "partner_eod_wrap": "advice",
    "partner_hedge_morning_summary": "advice",
    "partner_hedge_eod_summary": "advice",
    "partner_analytics_tick": "advice",
    # scan -- candidate-discovery loops
    "penny_scan_interval": "scan",
    "penny_connors_scan": "scan",
    "penny_edge_scan": "scan",
    "penny_regime_compute": "scan",
    "penny_regime_refresh": "scan",
    "fno_tick": "scan",
    "partner_scan_tick": "scan",
    "partner_manual_advisory_tick": "scan",
    "partner_manual_advisory_lifecycle_tick": "scan",
    "partner_hedge_tick": "scan",
    "partner_hedge_delivery_recovery": "scan",
    "partner_hedge_phase2_tick": "scan",
    "partner_hedge_phase3_tick": "scan",
    # research -- offline / non-time-critical
    "proactive_shadow_workflow": "research",
    "research_quote_collection": "research",
    "partner_rv_refresh": "research",
    "partner_input_refresh": "research",
    # system / meta -- bootstrap, login, circuit-breaker enforcement
    # (not user-facing; the cron itself is the operator signal that
    # the system is alive). Treated as a fifth tier for honest
    # accounting rather than folded into one of the four above.
    "premarket_login_nudge": "system",
    "daily_bootstrap_tick": "system",
    "circuit_breaker_enforce": "system",
}

# The five tiers, in priority order (system last). A future tier
# addition MUST extend this tuple AND the JOB_TIER_MAP comment.
TIER_ORDER: tuple[str, ...] = ("exit", "advice", "scan", "research", "system")


def _tier_for(job_id: str) -> str:
    """Return the priority tier for a job_id. Unrecognised ids land
    in ``other`` so the roll-up never silently drops a job.
    """
    return JOB_TIER_MAP.get(job_id, "other")


def _aggregate_by_tier(jobs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-job aggregates into per-tier aggregates.

    For each tier:
      * elapsed_seconds -- p50/p95/max across ALL elapsed samples
        of jobs in this tier (NOT the median of per-job medians).
        The operator wants "the slowest stage across this priority
        bucket", not "the average of medians" which can hide a tail.
      * runs / executed_runs / rejected / in_flight -- sums.
      * results -- merged status counts.
      * stage_durations -- per-stage aggregation across all jobs in
        the tier. The slowest stage across the tier is the most
        actionable single signal for capacity work.

    A tier with zero jobs returns ``None`` (not ``0``) for all
    numeric fields, per §12 acceptance: *"UI fixture covers
    unavailable and zero distinctly."* A future dashboard must
    be able to distinguish "no data" from "instant" without a
    second probe.
    """
    by_tier: dict[str, dict[str, Any]] = {}
    for tier in TIER_ORDER + ("other",):
        # Collect samples and stages from every job in this tier.
        elapsed_samples: list[float] = []
        merged_results: dict[str, int] = {}
        total_runs = 0
        total_executed = 0
        total_rejected = 0
        total_in_flight = 0
        merged_stages: dict[str, list[float]] = {}
        jobs_in_tier: list[str] = []
        for job_id, bucket in jobs.items():
            if _tier_for(job_id) != tier:
                continue
            jobs_in_tier.append(job_id)
            total_runs += int(bucket.get("runs", 0))
            total_executed += int(bucket.get("executed_runs", 0))
            total_rejected += int(bucket.get("rejected", 0))
            total_in_flight += int(bucket.get("in_flight", 0))
            for status, count in (bucket.get("results") or {}).items():
                merged_results[status] = merged_results.get(status, 0) + int(count)
            # [WORKFLOW-H H2 2026-09-13] Merge raw elapsed samples
            # AND raw stage samples from every job in the tier. The
            # per-tier p50/p95/max must be computed from the union
            # of samples (not from the per-job percentiles, which
            # cannot be inverse-distributed).
            for sample in (bucket.get("elapsed_samples") or []):
                if isinstance(sample, (int, float)) and math.isfinite(float(sample)):
                    elapsed_samples.append(float(sample))
            stages = bucket.get("stage_durations_samples") or {}
            for stage_name, samples in stages.items():
                merged_stages.setdefault(stage_name, []).extend(
                    float(s) for s in samples
                    if isinstance(s, (int, float)) and math.isfinite(float(s))
                )
        if not jobs_in_tier:
            by_tier[tier] = {
                "tier": tier,
                "job_count": 0,
                "jobs": [],
                "runs": 0,
                "executed_runs": 0,
                "rejected": 0,
                "in_flight": 0,
                "results": {},
                "elapsed_seconds": {"p50": None, "p95": None, "max": None},
                "stage_durations": {},
                "note": (
                    "no jobs in this tier; UI must render this as "
                    "'unavailable' rather than '0ms' or 'instant'."
                ),
            }
            continue
        # We have data; merge stages into a per-stage percentile.
        merged_stage_percentiles: dict[str, dict[str, float | None]] = {}
        for stage_name, samples in merged_stages.items():
            merged_stage_percentiles[stage_name] = _percentiles(samples)
        by_tier[tier] = {
            "tier": tier,
            "job_count": len(jobs_in_tier),
            "jobs": sorted(jobs_in_tier),
            "runs": total_runs,
            "executed_runs": total_executed,
            "rejected": total_rejected,
            "in_flight": total_in_flight,
            "results": merged_results,
            "elapsed_seconds": _percentiles(elapsed_samples),
            "stage_durations": merged_stage_percentiles,
        }
    return by_tier


def _inflight_state(item: dict[str, Any]) -> str:
    """CURRENT_PROCESS only while this process is still awaiting the callback."""
    if item["boot_id"] != BOOT_ID:
        return "PREVIOUS_PROCESS_UNFINISHED"
    if item.get("run_id") in _ACTIVE_RUNS:
        return "CURRENT_PROCESS"
    if item.get("run_id") in _PENDING_COMPLETIONS:
        return "COMPLETION_WRITE_FAILED"
    return "CURRENT_PROCESS_STALE"


async def scheduler_timing_report(db_path: str, *, limit: int = 500) -> dict[str, Any]:
    """Reproducible report; unavailable fields remain null rather than guessed."""
    if not 1 <= limit <= 5000:
        raise ValueError("limit must be within 1..5000")
    await init_scheduler_telemetry(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT job_id,event_kind,scheduled_at,started_at,ended_at,elapsed_seconds,result,reason,"
            "stage_durations_json,boot_id,created_at,run_id FROM scheduler_run_telemetry "
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
                "boot_id": row[9], "recorded_at": row[10], "run_id": row[11]}
        events.append(item)
        bucket = jobs.setdefault(row[0], {
            "runs": 0, "executed_runs": 0, "rejected": 0, "in_flight": 0,
            "results": {}, "elapsed_samples": [],
            # [WORKFLOW-H H2 2026-09-13] Stage-durations raw samples
            # kept on the bucket until AFTER the per-tier roll-up.
            # Per-stage p50/p95/max across the tier (NOT per-job)
            # is the most actionable signal for capacity work; we
            # therefore keep the raw per-stage samples until the
            # tier roll-up consumes them.
            "stage_durations_samples": {},
        })
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
        # Accumulate stage samples. Each stage is a string -> float.
        for stage_name, duration in (stages or {}).items():
            if not isinstance(stage_name, str) or not isinstance(
                duration, (int, float)
            ):
                continue
            if not math.isfinite(float(duration)):
                continue
            bucket["stage_durations_samples"].setdefault(
                stage_name, []
            ).append(float(duration))
    # [WORKFLOW-H H2 2026-09-13] Per-tier roll-up is computed
    # BEFORE the per-job _percentiles pop so the roll-up has access
    # to the raw samples. After the roll-up, the per-job
    # ``elapsed_samples`` and ``stage_durations_samples`` lists
    # are popped (the existing contract) and replaced with their
    # p50/p95/max shape.
    by_tier = _aggregate_by_tier(jobs)
    for bucket in jobs.values():
        bucket["elapsed_seconds"] = _percentiles(bucket.pop("elapsed_samples"))
        bucket.pop("stage_durations_samples", None)
    inflight = [item | {"inflight_state": _inflight_state(item)}
                for item in events if item["event_kind"] == "EXECUTION" and item["result"] == "IN_FLIGHT"]
    return {"boot_id": BOOT_ID, "events": events, "jobs": jobs, "inflight": inflight,
            "pending_completion_writes": pending_completion_writes(),
            "by_tier": by_tier,
            "note": "scheduled_at is null for executions because APScheduler did not provide it to the callback; null is not a zero delay. In-flight markers survive crashes and are not inferred as successful runs. inflight_state CURRENT_PROCESS means the callback is still running; COMPLETION_WRITE_FAILED means it finished but its final write is parked in pending_completion_writes; CURRENT_PROCESS_STALE means neither is known. by_tier groups jobs by priority tier per plan §12 (exit, advice, scan, research, system); unrecognised job_ids land in 'other'. A tier with zero jobs returns None -- not 0 -- for all numeric fields, so the UI can distinguish 'unavailable' from 'instant'."}
