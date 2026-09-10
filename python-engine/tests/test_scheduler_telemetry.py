from datetime import datetime, timedelta, timezone

import asyncio
import sqlite3

import pytest

from scheduler_telemetry import instrument_async_job, record_scheduler_event, scheduler_timing_report


@pytest.mark.asyncio
async def test_timing_report_keeps_unknown_schedule_time_and_bounded_events(tmp_path):
    db_path = str(tmp_path / "cache.db")
    started = datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc)
    for index in range(101):
        await record_scheduler_event(
            db_path, job_id="research_quote_collection", event_kind="EXECUTION",
            result="COMPLETED", started_at=started + timedelta(seconds=index),
            ended_at=started + timedelta(seconds=index + 1), elapsed_seconds=float(index),
            retention=100,
        )
    report = await scheduler_timing_report(db_path, limit=500)
    events = report["events"]
    assert len(events) == 100
    assert events[0]["scheduled_at"] is None
    assert report["jobs"]["research_quote_collection"]["elapsed_seconds"] == {
        "p50": 51.0, "p95": 95.0, "max": 100.0,
    }


@pytest.mark.asyncio
async def test_instrumented_failure_preserves_job_exception_and_records_fact(tmp_path):
    db_path = str(tmp_path / "cache.db")

    async def fails():
        raise RuntimeError("provider unavailable")

    wrapped = instrument_async_job(db_path, "exit_lifecycle", fails)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await wrapped()
    # Completion telemetry is recorded after the failed callback and cannot
    # convert its exception into a successful scheduler result.
    report = await scheduler_timing_report(db_path)
    assert report["events"][0]["job_id"] == "exit_lifecycle"
    assert report["events"][0]["result"] == "FAILED"
    assert report["events"][0]["reason"] == "RuntimeError"


@pytest.mark.asyncio
async def test_instrumentation_exposes_inflight_callback_before_completion(tmp_path):
    db_path = str(tmp_path / "cache.db")
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow():
        entered.set()
        await release.wait()
        return {"status": "COMPLETED", "stage_durations_sec": {"provider": .01}}

    task = asyncio.create_task(instrument_async_job(db_path, "research_quote_collection", slow)())
    await entered.wait()
    live = await scheduler_timing_report(db_path)
    assert live["jobs"]["research_quote_collection"]["in_flight"] == 1
    assert live["inflight"][0]["inflight_state"] == "CURRENT_PROCESS"
    release.set(); await task
    finished = await scheduler_timing_report(db_path)
    assert finished["jobs"]["research_quote_collection"]["executed_runs"] == 1
    assert finished["inflight"] == []


@pytest.mark.asyncio
async def test_locked_telemetry_database_never_prevents_callback(tmp_path):
    db_path = str(tmp_path / "cache.db")
    # Materialise schema before taking a deliberate write lock.
    await record_scheduler_event(db_path, job_id="seed", event_kind="EXECUTION", result="COMPLETED")
    lock = sqlite3.connect(db_path); lock.execute("BEGIN EXCLUSIVE")
    try:
        async def callback():
            return "business-ran"
        assert await instrument_async_job(db_path, "exit_lifecycle", callback)() == "business-ran"
    finally:
        lock.rollback(); lock.close()


@pytest.mark.asyncio
async def test_independent_exit_wrapper_is_not_blocked_by_slow_bulk_wrapper(tmp_path):
    """Controlled isolation evidence: no shared in-process bulk queue exists."""
    db_path = str(tmp_path / "cache.db")
    entered, release = asyncio.Event(), asyncio.Event()

    async def bulk():
        entered.set()
        await release.wait()
        return {"status": "COMPLETED", "stage_durations_sec": {"provider": 60.0}}

    async def lifecycle():
        return {"status": "COMPLETED", "stage_durations_sec": {"management": .001}}

    bulk_task = asyncio.create_task(instrument_async_job(db_path, "research_quote_collection", bulk)())
    await entered.wait()
    assert await asyncio.wait_for(instrument_async_job(db_path, "partner_manual_advisory_lifecycle_tick", lifecycle)(), timeout=.25)
    release.set(); await bulk_task
    report = await scheduler_timing_report(db_path)
    assert report["jobs"]["research_quote_collection"]["executed_runs"] == 1
    assert report["jobs"]["partner_manual_advisory_lifecycle_tick"]["executed_runs"] == 1
