from datetime import datetime, timedelta, timezone

import asyncio
import sqlite3

import pytest

from scheduler_telemetry import (
    instrument_async_job, record_scheduler_event, scheduler_daily_summary_report,
    scheduler_timing_report,
)


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


@pytest.mark.asyncio
async def test_daily_summary_survives_raw_tail_retention_and_keeps_stage_outcomes(tmp_path):
    db_path = str(tmp_path / "cache.db")
    ended = datetime(2026, 10, 2, 10, 30, tzinfo=timezone.utc)
    for index in range(101):
        await record_scheduler_event(
            db_path, job_id="fno_tick", event_kind="EXECUTION", result="COMPLETED",
            ended_at=ended + timedelta(seconds=index), elapsed_seconds=.1,
            stage_durations={"provider": .2 + index}, retention=100,
        )
    daily = await scheduler_daily_summary_report(db_path, session_date="2026-10-02")
    assert daily["summaries"] == [{
        "job_id": "fno_tick", "event_kind": "EXECUTION", "runs": 101,
        "results": {"COMPLETED": 101},
        "stage_stats": {"provider": {"count": 101, "total": 5070.2, "max": 100.2}},
        # [S3 R4] Durable elapsed distribution; 16:00 IST is off-hours.
        "elapsed_distribution": {"off_hours": {
            "count": 101, "max": 0.1, "mean": 0.1, "p50_upper_bound": 0.1, "p95_upper_bound": 0.1,
            "bucket_upper_bounds": [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0,
                                    120.0, 180.0, 300.0, "inf"],
            "buckets": [101] + [0] * 15,
        }},
        "first_recorded_at": ended.isoformat(),
        "last_recorded_at": (ended + timedelta(seconds=100)).isoformat(),
    }]
    assert len((await scheduler_timing_report(db_path))["events"]) == 100


@pytest.mark.asyncio
async def test_inflight_marker_is_not_counted_as_completed_daily_evidence(tmp_path):
    db_path = str(tmp_path / "cache.db")
    entered, release = asyncio.Event(), asyncio.Event()

    async def callback():
        entered.set()
        await release.wait()
        return {"status": "COMPLETED", "stage_durations_sec": {"management": .01}}

    task = asyncio.create_task(instrument_async_job(db_path, "fno_tick", callback)())
    await entered.wait()
    assert (await scheduler_daily_summary_report(db_path))["summaries"] == []
    release.set()
    await task
    daily = await scheduler_daily_summary_report(db_path)
    assert daily["summaries"][0]["results"] == {"COMPLETED": 1}
    assert daily["summaries"][0]["stage_stats"]["management"]["count"] == 1


# [S3 R4 2026-10-02] Durable market-hours elapsed distributions.
@pytest.mark.asyncio
async def test_elapsed_distribution_is_segmented_by_market_hours_with_p95_bound(tmp_path):
    from datetime import timezone as _tz
    from scheduler_telemetry import record_scheduler_event, scheduler_daily_summary_report
    db_path = str(tmp_path / "telemetry.db")
    market = datetime(2026, 10, 1, 5, 0, tzinfo=_tz.utc)      # 10:30 IST Thursday
    evening = datetime(2026, 10, 1, 12, 0, tzinfo=_tz.utc)    # 17:30 IST
    for index in range(20):
        elapsed = 100.0 if index >= 18 else 0.4
        await record_scheduler_event(db_path, job_id="research", event_kind="EXECUTION", result="COMPLETED",
                                     ended_at=market + timedelta(seconds=index), elapsed_seconds=elapsed)
    await record_scheduler_event(db_path, job_id="research", event_kind="EXECUTION", result="COMPLETED",
                                 ended_at=evening, elapsed_seconds=1.5)
    report = await scheduler_daily_summary_report(db_path, session_date="2026-10-01")
    dist = report["summaries"][0]["elapsed_distribution"]
    assert dist["market_hours"]["count"] == 20 and dist["off_hours"]["count"] == 1
    assert dist["market_hours"]["p50_upper_bound"] == 0.5
    assert dist["market_hours"]["p95_upper_bound"] == 120.0
    assert dist["market_hours"]["max"] == 100.0


@pytest.mark.asyncio
async def test_legacy_summary_table_gains_the_histogram_column(tmp_path):
    import aiosqlite
    from datetime import timezone as _tz
    from scheduler_telemetry import record_scheduler_event, scheduler_daily_summary_report
    db_path = str(tmp_path / "legacy.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE scheduler_daily_summaries (session_date TEXT NOT NULL, job_id TEXT NOT NULL,"
                         " event_kind TEXT NOT NULL, runs INTEGER NOT NULL, result_counts_json TEXT NOT NULL,"
                         " stage_stats_json TEXT NOT NULL, first_recorded_at TEXT NOT NULL,"
                         " last_recorded_at TEXT NOT NULL, PRIMARY KEY (session_date, job_id, event_kind))")
        await db.execute("INSERT INTO scheduler_daily_summaries VALUES ('2026-10-01','old','EXECUTION',3,"
                         "'{\"COMPLETED\":3}','{}','2026-10-01T04:00:00+00:00','2026-10-01T04:10:00+00:00')")
        await db.commit()
    await record_scheduler_event(db_path, job_id="old", event_kind="EXECUTION", result="COMPLETED",
                                 ended_at=datetime(2026, 10, 1, 4, 20, tzinfo=_tz.utc), elapsed_seconds=2.0)
    summary = (await scheduler_daily_summary_report(db_path, session_date="2026-10-01"))["summaries"][0]
    assert summary["runs"] == 4 and summary["results"] == {"COMPLETED": 4}
    assert summary["elapsed_distribution"]["market_hours"]["count"] == 1
