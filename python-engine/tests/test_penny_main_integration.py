"""
[PENNY-MAIN 2026-06-21] Integration tests for penny subsystem wiring in
python-engine/main.py.

Verifies:
  - main.py imports cleanly with the new penny globals + scheduler jobs
  - The 7 penny scheduler jobs are registered with the expected IDs
  - The two penny scanner entry points are callable coroutines
  - The paper-mode default keeps live trading OFF

These tests import main.py once and exercise the public symbols. They do
not run the scheduler itself (no fastapi app start, no async lifespan).
"""
import asyncio
import importlib
import sys
from pathlib import Path

import pytest


def _import_main():
    """Import main.py fresh; reset sys.modules cache so the module reloads
    cleanly even if a previous test in this session imported it."""
    for k in [k for k in sys.modules if k == "main"]:
        del sys.modules[k]
    return importlib.import_module("main")


def _fresh_scheduler_with_penny_jobs():
    """Build a clean AsyncIOScheduler + register the penny jobs on it.

    main.scheduler is a module-level singleton. We verify job
    registration in isolation by building a fresh scheduler per test
    and calling the extracted register_penny_scheduler_jobs() function.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sched = AsyncIOScheduler(timezone="Asia/Kolkata")
    main = _import_main()
    main.register_penny_scheduler_jobs(sched)
    return sched


def test_penny_main_imports_cleanly():
    """main.py must import without errors after penny globals + jobs added."""
    main = _import_main()
    assert main is not None
    # The penny globals must exist
    assert hasattr(main, "_penny_universe"), "_penny_universe missing"
    assert hasattr(main, "_penny_regime_engine"), "_penny_regime_engine missing"
    assert hasattr(main, "_penny_scanner"), "_penny_scanner missing"
    # Lazy-init helpers
    assert callable(main._get_penny_universe)
    assert callable(main._get_penny_scanner)
    # Path constants
    assert isinstance(main.PENNY_UNIVERSE_JSON_PATH, str)
    assert isinstance(main.PENNY_CORP_DATA_JSON_PATH, str)


def test_run_penny_scanner_once_is_callable():
    """The MIS-leg entry point must be exposed as a callable async function."""
    main = _import_main()
    assert callable(main.run_penny_scanner_once), (
        "run_penny_scanner_once missing or not callable"
    )
    # It must be a coroutine function (async def)
    assert asyncio.iscoroutinefunction(main.run_penny_scanner_once)


def test_run_penny_connors_scan_is_callable():
    """The CNC-leg entry point must be exposed as a callable async function."""
    main = _import_main()
    assert callable(main.run_penny_connors_scan), (
        "run_penny_connors_scan missing or not callable"
    )
    assert asyncio.iscoroutinefunction(main.run_penny_connors_scan)


def test_penny_universe_refresh_is_scheduled():
    """[BOOTSTRAP-2026-07-17] The 08:00 slot is now the token-aware
    daily_bootstrap entry (which runs the universe refresh underneath),
    plus a 10-min safety tick for post-login catch-up."""
    sched = _fresh_scheduler_with_penny_jobs()
    job_ids = [j.id for j in sched.get_jobs()]
    assert "daily_bootstrap_0800" in job_ids, (
        f"daily_bootstrap_0800 missing; got jobs={job_ids}"
    )
    assert "daily_bootstrap_tick" in job_ids, (
        f"daily_bootstrap_tick missing; got jobs={job_ids}"
    )
    job = next(j for j in sched.get_jobs() if j.id == "daily_bootstrap_0800")
    # Cron trigger; hour 8 IST
    assert job.trigger is not None


def test_penny_regime_compute_is_scheduled():
    """The penny_regime_compute cron job (09:20 IST) must be registered."""
    main = _import_main()
    sched = _fresh_scheduler_with_penny_jobs()
    job_ids = [j.id for j in sched.get_jobs()]
    assert "penny_regime_compute" in job_ids, (
        f"penny_regime_compute missing; got jobs={job_ids}"
    )


def test_penny_scanner_polling_is_scheduled():
    """The penny_scan_interval 30s polling job must be registered."""
    main = _import_main()
    sched = _fresh_scheduler_with_penny_jobs()
    job_ids = [j.id for j in sched.get_jobs()]
    assert "penny_scan_interval" in job_ids, (
        f"penny_scan_interval missing; got jobs={job_ids}"
    )


def test_penny_hourly_report_is_scheduled():
    """The penny_hourly_report cron job (top of every hour) must be registered."""
    main = _import_main()
    sched = _fresh_scheduler_with_penny_jobs()
    job_ids = [j.id for j in sched.get_jobs()]
    assert "penny_hourly_report" in job_ids, (
        f"penny_hourly_report missing; got jobs={job_ids}"
    )


def test_paper_mode_default_blocks_live_orders():
    """A missing environment override must leave Penny in paper mode."""
    from config import Settings, settings
    defaults = Settings(_env_file=None)
    assert defaults.PENNY_LIVE_TRADING is False
    assert settings.PENNY_PAPER_BANKROLL > 0
    assert settings.PENNY_LIVE_BANKROLL > 0
    # Per-stock cap matches docs
    assert settings.PENNY_PER_STOCK_CAP == 500.0
    # Daily kill-switch at 20%
    assert settings.PENNY_DAILY_KILL_SWITCH_PCT == 0.20


def test_scanner_mode_requires_explicit_live_opt_in(monkeypatch):
    """The master switch is inverted exactly once at scanner construction."""
    from types import SimpleNamespace
    from config import settings

    main = _import_main()
    built = []

    def fake_scanner(**kwargs):
        built.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(main, "PennyScanner", fake_scanner)
    monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)
    main._penny_scanner = None
    assert main._get_penny_scanner().paper_mode is True

    monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", True)
    main._penny_scanner = None
    assert main._get_penny_scanner().paper_mode is False
    assert [item["paper_mode"] for item in built] == [True, False]
    main._penny_scanner = None
