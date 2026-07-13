"""[ROADMAP-5.2 2026-07-13] Paper-vs-live honesty: the brokerage bypass.

PENNY_BROKERAGE_BYPASS zeroes every penny cost. On a Rs 2,500 bankroll,
Rs 20/order + STT + GST is not a rounding error -- it is most of the edge. Any
paper-vs-live comparison made while the flag is on is meaningless, and worse,
meaningless in the FLATTERING direction.

The roadmap asked only that reports assert the flag is off. Reading the code
turned up something sharper: penny_backtest.run_backtest set the flag on the
process-wide settings singleton and NEVER RESTORED IT (no try/finally), and its
`brokerage_bypass` parameter DEFAULTS TO TRUE. So a single in-process backtest
would zero brokerage for every subsequent LIVE penny trade, for the life of the
process, and the real ledger would drift away from the broker's while looking
like edge.

Three defences, three sets of tests below:
  1. penny_risk REFUSES the bypass when live trading is on (the interlock).
  2. penny_backtest restores the flag in a finally (the leak).
  3. edge_statistics withholds its verdict while the flag is set (the report).
"""
import pytest

from config import settings
from penny_risk import calc_penny_costs


@pytest.fixture(autouse=True)
def _restore_flags():
    """These tests mutate a process-wide singleton. Put it back, or they poison
    every test that runs after them -- which is precisely the bug under test."""
    live = settings.PENNY_LIVE_TRADING
    bypass = settings.PENNY_BROKERAGE_BYPASS
    yield
    settings.PENNY_LIVE_TRADING = live
    settings.PENNY_BROKERAGE_BYPASS = bypass


# ===================================================================
# 1. The interlock: live trading always pays real costs
# ===================================================================

def test_bypass_is_ignored_when_live_trading_is_on():
    """THE MONEY TEST. If the two flags contradict each other, charge the REAL
    costs. Under-reporting costs makes a losing strategy look profitable and
    corrupts the ledger it is measured against; over-reporting only makes it
    look worse than it is. Fail in the safe direction."""
    settings.PENNY_LIVE_TRADING = True
    settings.PENNY_BROKERAGE_BYPASS = True

    cost = calc_penny_costs(entry_price=10.0, exit_price=11.0, shares=100, is_intraday=True)

    assert cost > 0, (
        "PENNY_BROKERAGE_BYPASS zeroed costs on a LIVE trade. Every penny trade "
        "would book zero brokerage into the real ledger."
    )


def test_bypass_still_works_in_paper_mode():
    """The flag has a legitimate use -- measuring gross edge on a bankroll too
    small to survive costs. Do not break it; just confine it to paper."""
    settings.PENNY_LIVE_TRADING = False
    settings.PENNY_BROKERAGE_BYPASS = True

    assert calc_penny_costs(entry_price=10.0, exit_price=11.0, shares=100, is_intraday=True) == 0.0


def test_costs_are_charged_normally_when_the_flag_is_off():
    settings.PENNY_LIVE_TRADING = False
    settings.PENNY_BROKERAGE_BYPASS = False

    assert calc_penny_costs(entry_price=10.0, exit_price=11.0, shares=100, is_intraday=True) > 0


# ===================================================================
# 2. The leak: the flag must never escape a backtest
# ===================================================================

@pytest.mark.asyncio
async def test_backtest_restores_the_bypass_flag_even_when_it_raises():
    """The original code set the flag and never put it back. A backtest that
    THREW would leave the live process permanently cost-free -- the worst case,
    because nobody would think to check after a failure."""
    import penny_backtest

    settings.PENNY_LIVE_TRADING = False
    settings.PENNY_BROKERAGE_BYPASS = False

    with pytest.raises(ValueError):
        # kite=None raises immediately, before any work -- but AFTER the flag
        # would have been set by the old code path.
        await penny_backtest.run_backtest(
            from_date="2026-01-01",
            to_date="2026-01-02",
            universe_path="/nonexistent.json",
            kite=None,
            brokerage_bypass=True,
        )

    assert settings.PENNY_BROKERAGE_BYPASS is False, (
        "the backtest leaked PENNY_BROKERAGE_BYPASS into the live process"
    )


@pytest.mark.asyncio
async def test_backtest_restores_the_flag_on_the_normal_path(monkeypatch):
    """Same guarantee when the backtest completes rather than raising."""
    import penny_backtest

    settings.PENNY_LIVE_TRADING = False
    settings.PENNY_BROKERAGE_BYPASS = False

    seen = {}

    async def _fake_inner(**kw):
        # Inside the backtest the flag IS set -- that is the point of it.
        seen["inside"] = settings.PENNY_BROKERAGE_BYPASS
        return "done"

    monkeypatch.setattr(penny_backtest, "_run_backtest_inner", _fake_inner)

    out = await penny_backtest.run_backtest(
        from_date="2026-01-01", to_date="2026-01-02",
        universe_path="/x.json", kite=object(), brokerage_bypass=True,
    )

    assert out == "done"
    assert seen["inside"] is True            # active during the run
    assert settings.PENNY_BROKERAGE_BYPASS is False   # and restored after


# ===================================================================
# 3. The report: no verdict while costs are fictional
# ===================================================================

@pytest.mark.asyncio
async def test_edge_statistics_withholds_its_verdict_while_costs_are_bypassed(tmp_path):
    """A gross-P&L expectancy is not a slightly-optimistic number, it is a
    fictional one -- and it is exactly the number an operator would use to
    decide to scale up. Withhold the verdict rather than certify an edge earned
    by not paying brokerage."""
    import aiosqlite

    from analytics import edge_statistics, init_analytics_db

    db_path = str(tmp_path / "cache.db")
    await init_analytics_db(db_path)

    # A book that would otherwise look like a clear, reliable edge.
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO trade_outcomes (ticker, closed_at, realised_pnl, r_multiple) "
            "VALUES (?, ?, ?, ?)",
            [(f"T{i}", f"2026-07-{(i % 28) + 1:02d}T10:00:00+00:00", 200.0, 1.0)
             for i in range(40)]
            + [(f"L{i}", f"2026-07-{(i % 28) + 1:02d}T11:00:00+00:00", -50.0, -0.3)
               for i in range(10)],
        )
        await db.commit()

    settings.PENNY_BROKERAGE_BYPASS = True
    report = await edge_statistics(db_path, days=3650)

    assert report["brokerage_bypass_active"] is True
    assert report["costs_are_fictional"] is True
    assert report["verdict"] == "invalid_costs_bypassed"
    assert "PENNY_BROKERAGE_BYPASS is ON" in report["warning"]


@pytest.mark.asyncio
async def test_edge_statistics_reports_normally_when_costs_are_real(tmp_path):
    import aiosqlite

    from analytics import edge_statistics, init_analytics_db

    db_path = str(tmp_path / "cache.db")
    await init_analytics_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO trade_outcomes (ticker, closed_at, realised_pnl, r_multiple) "
            "VALUES (?, ?, ?, ?)",
            [(f"T{i}", f"2026-07-{(i % 28) + 1:02d}T10:00:00+00:00", 200.0, 1.0)
             for i in range(40)],
        )
        await db.commit()

    settings.PENNY_BROKERAGE_BYPASS = False
    report = await edge_statistics(db_path, days=3650)

    assert report["brokerage_bypass_active"] is False
    assert "costs_are_fictional" not in report
    assert report["verdict"] != "invalid_costs_bypassed"
