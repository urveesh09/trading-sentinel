"""
[ROADMAP-2.4 2026-07-12] Scheduler loop-progress tick.

The job runs ON the APScheduler loop and writes
dirname(DB_PATH)/scheduler_tick.json every 60s; the agent container
reads it (ro mount) and pages when it goes stale during market hours.
A fresh file therefore proves "jobs are firing", which the
daemon-thread penny-liveness heartbeat deliberately cannot prove.
"""
import asyncio
import json
import time


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
