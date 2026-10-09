"""[FAST-EXIT 2026-10-04] Fast single-leg management loop and bar-close trigger."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import fno_orchestrator


def _registered(monkeypatch, **flags):
    import main
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from config import settings
    for name, value in flags.items():
        monkeypatch.setattr(settings, name, value)
    probe = AsyncIOScheduler(timezone=main.IST)
    main.register_fno_scheduler_jobs(probe)
    return {job.id: job for job in probe.get_jobs()}


def test_speedups_register_only_when_enabled(monkeypatch):
    from config import settings
    # Fast exit ships ON since the Oct 9 audit (profit-lock floor missed by a
    # 90 s sample); the bar-close entry trigger stays OFF.
    assert settings.FNO_FAST_EXIT_ENABLED is True and settings.FNO_BAR_CLOSE_TRIGGER_ENABLED is False
    off = _registered(monkeypatch, FNO_FAST_EXIT_ENABLED=False)
    assert "fno_tick" in off and "fno_fast_exit" not in off and "fno_bar_close_tick" not in off
    on = _registered(monkeypatch, FNO_FAST_EXIT_ENABLED=True, FNO_BAR_CLOSE_TRIGGER_ENABLED=True)
    assert on["fno_fast_exit"].trigger.interval.total_seconds() == settings.FNO_FAST_EXIT_INTERVAL_SEC
    trigger = str(on["fno_bar_close_tick"].trigger)
    assert "minute='*/5'" in trigger and f"second='{settings.FNO_BAR_CLOSE_DELAY_SEC}'" in trigger
    # The bar-close trigger reuses the regular tick (same lock, same telemetry).
    assert on["fno_bar_close_tick"].func is on["fno_tick"].func


@pytest.mark.asyncio
async def test_fast_exit_and_tick_share_one_lock(monkeypatch):
    import main
    import scheduler_setup

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return main.IST.localize(datetime(2026, 9, 14, 11, 0))

    monkeypatch.setattr(scheduler_setup, "datetime", Clock)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "kite", MagicMock(access_token="test"))
    jobs = _registered(monkeypatch, FNO_FAST_EXIT_ENABLED=True)
    seen = []

    async def slow_tick(*args, **kwargs):
        seen.append("tick")
        await jobs["fno_fast_exit"].func()          # attempted while the tick holds the lock
        return {}

    fast = AsyncMock(return_value={"exits": []})
    monkeypatch.setattr(fno_orchestrator, "run_fno_tick", slow_tick)
    monkeypatch.setattr(fno_orchestrator, "run_fno_fast_exit", fast)
    await jobs["fno_tick"].func()
    assert seen == ["tick"] and fast.await_count == 0      # skipped, never concurrent
    await jobs["fno_fast_exit"].func()
    assert fast.await_count == 1                           # runs once the lock is free


@pytest.mark.asyncio
async def test_fast_exit_is_a_no_op_without_open_positions(monkeypatch):
    monkeypatch.setattr(fno_orchestrator.fpos, "open_positions", AsyncMock(return_value=[]))
    manage = AsyncMock()
    monkeypatch.setattr(fno_orchestrator, "_manage_single_leg_books", manage)
    summary = await fno_orchestrator.run_fno_fast_exit(MagicMock(), db_path="unused.db",
                                                       now_ist=fno_orchestrator.IST.localize(datetime(2026, 9, 14, 11)))
    assert summary["note"] == "no_open_positions" and manage.await_count == 0


@pytest.mark.asyncio
async def test_fast_exit_uses_the_shared_management_path(monkeypatch):
    monkeypatch.setattr(fno_orchestrator.fpos, "open_positions", AsyncMock(return_value=[object()]))
    instruments = MagicMock()
    instruments.ready.return_value = True
    instruments.front_future.return_value = MagicMock(token=9001)
    monkeypatch.setattr(fno_orchestrator, "get_fno_instruments", lambda: instruments)
    manage = AsyncMock(return_value=(25_000.0, None))
    monkeypatch.setattr(fno_orchestrator, "_manage_single_leg_books", manage)
    now = fno_orchestrator.IST.localize(datetime(2026, 9, 14, 11))
    summary = await fno_orchestrator.run_fno_fast_exit(MagicMock(), db_path="unused.db", now_ist=now)
    assert summary["note"] == "managed" and manage.await_count == 1
    kwargs = manage.await_args.kwargs
    assert kwargs["now_ist"] == now and kwargs["supplied_now_ist"] == now and kwargs["action_clock"] is None
