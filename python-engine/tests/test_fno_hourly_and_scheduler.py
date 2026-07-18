"""
[FNO-REPORT-TESTS 2026-07-10] Hourly report content rules (spec §9.2's
"healthy zero" vs "dead gate" distinction must be READABLE, not just
logged) + scheduler job registration.
"""
from datetime import datetime

import pytest
import pytz

from fno_hourly_report import build_hourly_report, is_in_report_window
from fno_signal_log import init_fno_signal_db, log_fno_signal

IST = pytz.timezone("Asia/Kolkata")
NOON = IST.localize(datetime(2026, 7, 10, 12, 0))


def test_report_window():
    assert is_in_report_window(IST.localize(datetime(2026, 7, 10, 10, 0)))
    assert is_in_report_window(IST.localize(datetime(2026, 7, 10, 15, 0)))
    assert not is_in_report_window(IST.localize(datetime(2026, 7, 10, 9, 0)))
    assert not is_in_report_window(IST.localize(datetime(2026, 7, 10, 16, 0)))


@pytest.mark.asyncio
async def test_report_flags_zero_evaluations_after_11(db_path):
    msg = await build_hourly_report(db_path, NOON, regime="REGIME_1_NORMAL")
    assert "WARNING: zero evaluations" in msg
    assert "FNO_PAPER" in msg


@pytest.mark.asyncio
async def test_report_explains_self_regulation(db_path):
    await init_fno_signal_db(db_path)
    for i in range(4):
        await log_fno_signal(
            db_path, scan_id=f"T-{i}", leg="FNO_PAPER", accepted=False,
            reject_reason="pool_below_min_viable",
            bar_ts=f"2026-07-10 10:{i:02d}:00",
        )
    msg = await build_hourly_report(db_path, NOON, regime="REGIME_1_NORMAL")
    assert "evaluations=4 accepts=0" in msg
    assert "pool_below_min_viable" in msg
    # §9.2: the healthy zero explains itself
    assert "correctly declining" in msg


@pytest.mark.asyncio
async def test_report_shows_positions(db_path):
    from fno_positions import init_fno_positions_db, insert_position
    await init_fno_positions_db(db_path)
    await insert_position(
        db_path, source="FNO_PAPER", tradingsymbol="NIFTY25000CE", token=1,
        underlying="NIFTY", expiry="2026-07-14", strike=25000.0, opt_type="CE",
        direction="LONG", lots=1, lot_size=75, qty=75,
        entry_time="2026-07-10T10:00:00+05:30", entry_date="2026-07-10",
        entry_premium=100.0, entry_underlying=25000.0, delta_at_entry=0.55,
        iv_at_entry=0.12, atr_at_entry=15.0, stop_underlying=24950.0,
        target_underlying=25075.0, premium_stop=75.0, trail_active=0,
        best_underlying=25000.0, max_loss_rupees=7500.0, status="OPEN",
        bar_ts="2026-07-10 09:55:00",
    )
    msg = await build_hourly_report(db_path, NOON, regime="REGIME_1_NORMAL")
    assert "open=1" in msg
    assert "NIFTY25000CE" in msg


def test_scheduler_jobs_registered():
    """register_fno_scheduler_jobs must add the four F&O jobs. Uses a
    recording stub -- no lifespan boot needed (same pattern the penny
    registration tests use)."""
    import main

    class _StubScheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger=None, **kw):
            self.jobs.append(kw.get("id"))

    stub = _StubScheduler()
    main.register_fno_scheduler_jobs(stub)
    # [BOOTSTRAP-2026-07-17] fno_instruments_refresh is no longer a
    # standalone cron -- the NFO snapshot is a daily_bootstrap task
    # (registered under register_penny_scheduler_jobs as
    # daily_bootstrap_0800 / daily_bootstrap_tick, re-run on login).
    for job_id in ("fno_tick", "fno_hourly_report", "fno_accept_watchdog"):
        assert job_id in stub.jobs, f"missing scheduler job: {job_id}"
    assert "fno_instruments_refresh" not in stub.jobs, (
        "fno_instruments_refresh cron reintroduced -- it must stay a "
        "daily_bootstrap task (token-gated, login-retried), not a "
        "token-blind 08:05 cron"
    )
