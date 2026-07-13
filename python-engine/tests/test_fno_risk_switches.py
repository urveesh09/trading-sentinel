"""
[FNO-SWITCHES-TESTS 2026-07-10] Kill switches (spec §7.6) and the
go-live gate (spec §11). Switch state is derived from fno_positions
rows, never from in-memory counters, so a container restart cannot
forget a halt.
"""
from datetime import date

import pytest

from config import settings
from fno_positions import close_position, init_fno_positions_db, insert_position
from fno_risk import fno_go_live_check, kill_switch_status

TODAY = date(2026, 7, 10)
POOL = 100000.0


async def _closed_trade(db_path, pnl: float, exit_date: str, source="FNO_PAPER"):
    """Insert one already-CLOSED row with the given pnl/exit_date."""
    import aiosqlite
    await init_fno_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO fno_positions (source, tradingsymbol, status, pnl, "
            "exit_date, exit_time, entry_date) VALUES (?, 'NIFTYTEST', 'CLOSED', ?, ?, ?, ?)",
            (source, pnl, exit_date, exit_date + "T14:00:00+05:30", exit_date),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_missing_table_means_clear(db_path):
    assert await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY) == []


@pytest.mark.asyncio
async def test_no_losses_means_clear(db_path):
    await _closed_trade(db_path, +500.0, "2026-07-10")
    assert await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY) == []


@pytest.mark.asyncio
async def test_daily_kill_fires_at_6_pct(db_path):
    await _closed_trade(db_path, -6001.0, "2026-07-10")
    active = await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY)
    assert any(a.startswith("daily_loss_halt") for a in active)


@pytest.mark.asyncio
async def test_weekly_kill_fires_without_daily(db_path):
    """Options bleed slowly enough to walk under a daily limit every day
    (spec §7.6): -4k/day x 4 days trips weekly (12%) but never daily (6%)."""
    for d in ("2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"):
        await _closed_trade(db_path, -4000.0, d)
    active = await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY)
    assert any(a.startswith("weekly_loss_halt") for a in active)
    assert not any(a.startswith("daily_loss_halt") for a in active)


@pytest.mark.asyncio
async def test_monthly_kill_fires_across_weeks(db_path):
    # -3.5k on 6 days spread over the month: 21% monthly, never daily
    for d in ("2026-07-01", "2026-07-02", "2026-07-03",
              "2026-07-06", "2026-07-07", "2026-07-08"):
        await _closed_trade(db_path, -3500.0, d)
    active = await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY)
    assert any(a.startswith("monthly_loss_halt") for a in active)


@pytest.mark.asyncio
async def test_consecutive_losses_pause_then_resume(db_path):
    for i in range(settings.FNO_MAX_CONSECUTIVE_LOSSES):
        await _closed_trade(db_path, -100.0, "2026-07-09")
    active = await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY)
    assert any(a.startswith("consecutive_loss_pause") for a in active)
    # Two days later the pause has lapsed (small losses don't trip the
    # pct switches: 600 rupees total).
    later = date(2026, 7, 12)
    active2 = await kill_switch_status(db_path, "FNO_PAPER", POOL, later)
    assert not any(a.startswith("consecutive_loss_pause") for a in active2)


@pytest.mark.asyncio
async def test_streak_broken_by_win_is_clear(db_path):
    for i in range(4):
        await _closed_trade(db_path, -100.0, "2026-07-09")
    await _closed_trade(db_path, +50.0, "2026-07-09")
    await _closed_trade(db_path, -100.0, "2026-07-09")
    active = await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY)
    assert not any(a.startswith("consecutive_loss_pause") for a in active)


@pytest.mark.asyncio
async def test_sources_do_not_cross_contaminate(db_path):
    await _closed_trade(db_path, -7000.0, "2026-07-10", source="FNO_LIVE")
    assert await kill_switch_status(db_path, "FNO_PAPER", POOL, TODAY) == []


# ---------------------------------------------------------------------------
# go-live gate: promotion is a function, not a judgment call (spec §11)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_go_live_refuses_fresh_system(db_path):
    unmet = await fno_go_live_check(db_path)
    # Every condition unmet on a fresh system -- the live leg cannot arm.
    assert unmet
    joined = " ".join(unmet)
    assert "atm_premium_unknown" in joined
    assert "sl_mechanism_not_broker_verified" in joined
    assert "liveness_30d_not_attested" in joined
    assert "max_loss_branch_coverage_not_attested" in joined


@pytest.mark.asyncio
async def test_kill_switch_db_error_fails_closed(tmp_path):
    """An unreadable ledger means NO entries, not free entries."""
    bad_path = str(tmp_path)   # a directory, not a DB file
    active = await kill_switch_status(bad_path, "FNO_PAPER", POOL, TODAY)
    assert active and active[0].startswith("kill_switch_db_error")


@pytest.mark.asyncio
async def test_go_live_arms_only_when_every_condition_holds(db_path, patch_settings, monkeypatch):
    """The promotion function returns [] iff ALL six §11 conditions are
    met -- covering the success path so nobody can break it silently."""
    monkeypatch.setattr(patch_settings, "FNO_LIVE_BANKROLL", 100000.0)
    monkeypatch.setattr(patch_settings, "FNO_LIVENESS_30D_CLEAN", True)
    # 60 profitable-enough closed paper trades over 60 distinct days
    from datetime import timedelta
    start = date(2026, 4, 1)
    for i in range(60):
        d = (start + timedelta(days=i)).isoformat()
        await _closed_trade(db_path, +200.0 if i % 3 else -100.0, d)
    unmet = await fno_go_live_check(
        db_path, current_atm_premium=100.0, lot_size=75,
        sl_mechanism_verified=True, max_loss_branch_cov_ok=True,
    )
    assert unmet == [], f"expected clean go-live, got: {unmet}"


@pytest.mark.asyncio
async def test_go_live_blocks_on_thin_history(db_path, patch_settings, monkeypatch):
    """40 days AND 60 trades are BOTH required (spec §11 condition 2)."""
    monkeypatch.setattr(patch_settings, "FNO_LIVE_BANKROLL", 100000.0)
    from datetime import timedelta
    start = date(2026, 7, 1)
    for i in range(10):   # 10 trades over 5 days: both sub-conditions unmet
        d = (start + timedelta(days=i % 5)).isoformat()
        await _closed_trade(db_path, +200.0, d)
    unmet = await fno_go_live_check(
        db_path, current_atm_premium=100.0, lot_size=75,
        sl_mechanism_verified=True, max_loss_branch_cov_ok=True,
    )
    joined = " ".join(unmet)
    assert "paper_days=5<40" in joined
    assert "paper_trades=10<60" in joined


@pytest.mark.asyncio
async def test_go_live_blocks_on_thin_profit_factor(db_path, patch_settings, monkeypatch):
    monkeypatch.setattr(patch_settings, "FNO_LIVE_BANKROLL", 100000.0)
    monkeypatch.setattr(patch_settings, "FNO_LIVENESS_30D_CLEAN", True)
    from datetime import timedelta
    start = date(2026, 4, 1)
    for i in range(60):
        d = (start + timedelta(days=i)).isoformat()
        await _closed_trade(db_path, -50.0, d)   # pf = 0
    unmet = await fno_go_live_check(
        db_path, current_atm_premium=100.0, lot_size=75,
        sl_mechanism_verified=True, max_loss_branch_cov_ok=True,
    )
    assert any(u.startswith("profit_factor") for u in unmet)


@pytest.mark.asyncio
async def test_go_live_pool_check_uses_min_viable(db_path, patch_settings):
    # Live pool is Rs 0 in P1 -> pool_below_min_viable must be unmet.
    unmet = await fno_go_live_check(
        db_path, current_atm_premium=100.0, lot_size=75,
        sl_mechanism_verified=True, max_loss_branch_cov_ok=True,
    )
    assert any(u.startswith("pool_below_min_viable") for u in unmet)


# ---------------------------------------------------------------------------
# fno_bankroll: pool isolation in the shared ledger (spec §10.3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fno_bankroll_isolated_per_source(db_path, patch_settings):
    from performance import fno_bankroll, init_ledger, record_trade_close
    await init_ledger(db_path)
    await record_trade_close(db_path, "NIFTYTEST", -1500.0, source="FNO_PAPER")
    await record_trade_close(db_path, "SOMESTOCK", +9999.0, source="PENNY")
    paper = await fno_bankroll(db_path, "FNO_PAPER")
    assert paper == pytest.approx(settings.FNO_PAPER_BANKROLL - 1500.0)
    # penny pnl is invisible to the fno pool, and vice versa
    live = await fno_bankroll(db_path, "FNO_LIVE")
    assert live == pytest.approx(settings.FNO_LIVE_BANKROLL)
