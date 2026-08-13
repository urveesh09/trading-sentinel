"""
[ROADMAP-2.4 2026-07-12] Scheduler loop-progress tick.

The job runs ON the APScheduler loop and writes
dirname(DB_PATH)/scheduler_tick.json every 60s; the agent container
reads it (ro mount) and pages when it goes stale during market hours.
A fresh file therefore proves "jobs are firing", which the
daemon-thread penny-liveness heartbeat deliberately cannot prove.
"""
import asyncio
import inspect
import json
import sqlite3
import time
from datetime import datetime

import pytest


def test_scheduler_tick_writes_fresh_atomic_file(tmp_path, monkeypatch):
    import main as main_module
    from config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))

    asyncio.run(main_module._scheduler_tick_job())

    tick_file = tmp_path / "scheduler_tick.json"
    assert tick_file.exists()
    payload = json.loads(tick_file.read_text())
    assert abs(time.time() - payload["ts_epoch"]) < 5.0
    assert "ist" in payload
    # Atomic replace: no torn temp file left for the agent to misread.
    assert not (tmp_path / "scheduler_tick.json.tmp").exists()


def test_scheduler_tick_overwrites_previous(tmp_path, monkeypatch):
    import main as main_module
    from config import settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    (tmp_path / "scheduler_tick.json").write_text(
        json.dumps({"ts_epoch": 1.0, "ist": "old"})
    )

    asyncio.run(main_module._scheduler_tick_job())

    payload = json.loads((tmp_path / "scheduler_tick.json").read_text())
    assert payload["ts_epoch"] > 1.0


def test_scheduler_tick_never_raises(tmp_path, monkeypatch):
    """A tick-write failure must not crash the job (it would be rescheduled
    anyway, but an exception storm would drown the logs)."""
    import main as main_module
    from config import settings

    # Point DB_PATH at a directory that doesn't exist.
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "nope" / "cache.db"))
    asyncio.run(main_module._scheduler_tick_job())  # must not raise


def test_lifespan_attests_scheduler_immediately_after_start():
    """Boot must leave deterministic proof without firing trading jobs."""
    import main as main_module

    source = inspect.getsource(main_module.lifespan)
    start_at = source.index("scheduler.start()")
    tick_at = source.index(
        "await _scheduler_tick_job(recover_previous=True)", start_at
    )
    attestation_at = source.index("scheduler_startup_attested", tick_at)
    yield_at = source.index("yield", attestation_at)

    assert start_at < tick_at < attestation_at < yield_at


async def _run_recovered_startup_tick(tmp_path, monkeypatch, now_ist, prior_ist=None):
    import ops_watchdogs
    from config import settings
    from ops_metrics import init_ops_metrics_db

    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(
        ops_watchdogs, "_scheduler_tick_state", {"prev_monotonic": None}
    )

    class _FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return now_ist

    monkeypatch.setattr(ops_watchdogs, "datetime", _FixedDatetime)
    monkeypatch.setattr(ops_watchdogs.time, "time", lambda: now_ist.timestamp())
    if prior_ist is not None:
        (tmp_path / "scheduler_tick.json").write_text(json.dumps({
            "ts_epoch": prior_ist.timestamp(),
            "ist": prior_ist.isoformat(),
        }))

    await init_ops_metrics_db(str(db_path))
    attestation = await ops_watchdogs._scheduler_tick_job(
        recover_previous=True
    )
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT max_gap_seconds, max_gap_market_seconds "
            "FROM ops_liveness_daily WHERE date_ist = ?",
            (now_ist.strftime("%Y-%m-%d"),),
        ).fetchone()
    return attestation, row


@pytest.mark.asyncio
async def test_startup_tick_recovers_midmarket_process_gap(tmp_path, monkeypatch):
    """A restart must not erase downtime from the 30-day clean-liveness gate."""
    from ops_watchdogs import IST

    prior = IST.localize(datetime(2026, 7, 8, 10, 45))
    now = IST.localize(datetime(2026, 7, 8, 11, 0))
    attestation, row = await _run_recovered_startup_tick(
        tmp_path, monkeypatch, now, prior
    )

    assert attestation == {
        "recovered_previous": True,
        "prior_gap_seconds": 900.0,
    }
    assert row == (900.0, 900.0)


@pytest.mark.asyncio
async def test_startup_tick_overnight_gap_does_not_poison_market_liveness(
    tmp_path, monkeypatch,
):
    from ops_watchdogs import IST

    prior = IST.localize(datetime(2026, 7, 8, 16, 0))
    now = IST.localize(datetime(2026, 7, 9, 8, 0))
    attestation, row = await _run_recovered_startup_tick(
        tmp_path, monkeypatch, now, prior
    )

    assert attestation["recovered_previous"] is True
    assert attestation["prior_gap_seconds"] == 16 * 3600.0
    assert row == (16 * 3600.0, 0.0)


@pytest.mark.asyncio
async def test_startup_tick_without_prior_file_starts_clean_baseline(
    tmp_path, monkeypatch,
):
    from ops_watchdogs import IST

    now = IST.localize(datetime(2026, 7, 8, 11, 0))
    attestation, row = await _run_recovered_startup_tick(
        tmp_path, monkeypatch, now
    )

    assert attestation == {
        "recovered_previous": False,
        "prior_gap_seconds": None,
    }
    assert row == (0.0, 0.0)
