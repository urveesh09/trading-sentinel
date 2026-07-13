"""[ROADMAP-5.1 2026-07-13] Tests for the edge statistics.

The interesting tests here are not "does the arithmetic work". They are the
cases where the OLD numbers (win rate, average R) say the strategy is good and
the new ones say it is not -- because that is the entire reason for the module.
"""
import pytest

from edge_stats import (
    MIN_SAMPLE_FOR_RELIABLE,
    Trade,
    bootstrap_ci,
    edge_report,
    expectancy_r,
    expectancy_rupees,
    max_drawdown,
    profit_factor,
)


# ===================================================================
# The cases that motivate the module
# ===================================================================

def test_a_90pct_win_rate_can_still_be_a_losing_system():
    """THE HEADLINE CASE. Nine wins of Rs 100, one loss of Rs 2,000.

    win_rate = 0.90 -- which is all analytics.py would have told you.
    The system loses Rs 1,100 and profit factor is 0.45.
    """
    trades = [Trade(pnl=100.0, r=0.5)] * 9 + [Trade(pnl=-2000.0, r=-10.0)]

    report = edge_report(trades)

    assert report["win_rate"] == 0.9          # looks wonderful
    pf, undefined = profit_factor(trades)
    assert not undefined
    assert pf == pytest.approx(900 / 2000)    # 0.45 -- loses money
    assert pf < 1.0
    assert report["expectancy_rupees"] == pytest.approx(-110.0)
    assert report["verdict"] != "edge_demonstrated"


def test_profit_factor_with_no_losers_is_undefined_not_infinite():
    """A system that has not lost yet has not been TESTED yet. Reporting `inf`
    (or a big number) would rank an untested strategy top of the book."""
    trades = [Trade(pnl=100.0, r=1.0) for _ in range(5)]

    pf, undefined = profit_factor(trades)

    assert pf is None
    assert undefined is True

    report = edge_report(trades)
    assert report["profit_factor"] is None
    assert report["profit_factor_undefined"] is True


def test_a_good_looking_point_estimate_with_a_straddling_ci_is_not_an_edge():
    """The honesty rule. A tiny, noisy, positive-on-average sample must NOT be
    reported as a demonstrated edge -- the CI straddles zero."""
    trades = [
        Trade(pnl=500.0, r=2.0), Trade(pnl=-400.0, r=-1.0),
        Trade(pnl=600.0, r=2.2), Trade(pnl=-450.0, r=-1.0),
        Trade(pnl=300.0, r=1.1), Trade(pnl=-380.0, r=-1.0),
    ]
    report = edge_report(trades)

    assert report["expectancy_rupees"] > 0          # point estimate is positive
    lo, hi = report["expectancy_rupees_ci95"]
    assert lo < 0 < hi                              # ...but we cannot tell
    assert report["verdict"] == "not_demonstrated"
    assert report["reliable"] is False


def test_a_real_edge_over_a_large_sample_is_recognised():
    """The counterpart: given enough consistent trades, the CI clears zero and
    the module says so. A test suite that can only say 'no' is useless."""
    trades = ([Trade(pnl=200.0, r=1.0)] * 70) + ([Trade(pnl=-100.0, r=-0.5)] * 30)

    report = edge_report(trades)

    assert report["n"] == 100
    assert report["reliable"] is True
    lo, _ = report["expectancy_rupees_ci95"]
    assert lo > 0
    assert report["verdict"] == "edge_demonstrated"
    # The report rounds to 3dp for display; compare with that tolerance.
    assert report["profit_factor"] == pytest.approx((70 * 200) / (30 * 100), abs=1e-3)


def test_a_clearly_losing_system_is_called_negative_not_merely_unproven():
    trades = ([Trade(pnl=-150.0, r=-1.0)] * 60) + ([Trade(pnl=100.0, r=0.6)] * 20)
    report = edge_report(trades)
    assert report["verdict"] == "negative_edge"
    assert report["expectancy_rupees"] < 0


# ===================================================================
# Max drawdown
# ===================================================================

def test_max_drawdown_is_peak_to_trough_not_worst_trade():
    """+1000, -300, -400 => the worst TRADE is -400, but the operator sat
    through a 700 drawdown from the 1000 peak. Those are different numbers and
    only one of them tells you whether the strategy is survivable."""
    trades = [Trade(pnl=1000.0), Trade(pnl=-300.0), Trade(pnl=-400.0)]

    dd = max_drawdown(trades)

    assert dd["max_drawdown_rupees"] == 700.0
    assert dd["max_drawdown_pct_of_peak"] == pytest.approx(0.7)


def test_max_drawdown_recovers_and_keeps_the_worst():
    # up 1000, down to 200 (dd 800), back up to 1500, down to 1300 (dd 200).
    # The worst is the FIRST one; a "last drawdown" bug would report 200.
    trades = [Trade(pnl=1000.0), Trade(pnl=-800.0), Trade(pnl=1300.0), Trade(pnl=-200.0)]
    assert max_drawdown(trades)["max_drawdown_rupees"] == 800.0


def test_drawdown_pct_is_none_while_the_peak_is_underwater():
    """You cannot draw down 30% of nothing. Losing from trade one gives an
    absolute drawdown but no meaningful percentage -- report None, not a
    divide-by-zero or a fabricated 100%."""
    trades = [Trade(pnl=-500.0), Trade(pnl=-200.0)]
    dd = max_drawdown(trades)
    assert dd["max_drawdown_rupees"] == 700.0
    assert dd["max_drawdown_pct_of_peak"] is None


def test_drawdown_is_flagged_as_closed_trade_basis():
    """It is a LOWER BOUND -- open positions swinging against you never appear.
    The flag exists so a caller cannot quietly present it as the real thing."""
    assert max_drawdown([Trade(pnl=1.0)])["closed_trade_basis"] is True


# ===================================================================
# Bootstrap
# ===================================================================

def test_bootstrap_is_deterministic():
    """A confidence interval that moves between runs is one nobody will trust
    -- and worse, one that can be re-rolled until it says what you want."""
    trades = [Trade(pnl=float(x), r=x / 100) for x in (100, -50, 200, -80, 150, -60)]
    a = bootstrap_ci(trades, expectancy_rupees)
    b = bootstrap_ci(trades, expectancy_rupees)
    assert a == b


def test_bootstrap_ci_brackets_the_point_estimate():
    trades = ([Trade(pnl=200.0)] * 60) + ([Trade(pnl=-100.0)] * 40)
    lo, hi = bootstrap_ci(trades, expectancy_rupees)
    assert lo <= expectancy_rupees(trades) <= hi


def test_bootstrap_returns_none_when_the_statistic_is_mostly_undefined():
    """Profit factor on a book with a single loser: most resamples contain no
    loser at all, so the statistic is undefined for them. Reporting an interval
    built from the minority that happened to include the loser would be worse
    than reporting nothing."""
    trades = [Trade(pnl=100.0)] * 20 + [Trade(pnl=-50.0)]
    ci = bootstrap_ci(trades, lambda ts: profit_factor(ts)[0])
    assert ci is None


def test_bootstrap_needs_at_least_two_trades():
    assert bootstrap_ci([Trade(pnl=100.0)], expectancy_rupees) is None


# ===================================================================
# Expectancy plumbing
# ===================================================================

def test_expectancy_r_ignores_rows_with_no_r_multiple():
    """Older trade_outcomes rows predate r_multiple and store NULL. They must
    not be silently counted as 0.0 R -- that would drag expectancy toward zero
    and make a real edge look like noise."""
    trades = [Trade(pnl=1.0, r=2.0), Trade(pnl=1.0, r=None), Trade(pnl=1.0, r=4.0)]
    assert expectancy_r(trades) == pytest.approx(3.0)   # not 2.0
    assert expectancy_rupees(trades) == pytest.approx(1.0)  # rupees uses all rows


def test_empty_input_is_no_data_not_zero():
    r = edge_report([])
    assert r["n"] == 0
    assert r["verdict"] == "no_data"
    assert r["reliable"] is False


def test_reliable_flag_tracks_the_sample_floor():
    small = edge_report([Trade(pnl=10.0, r=0.1)] * (MIN_SAMPLE_FOR_RELIABLE - 1))
    big = edge_report([Trade(pnl=10.0, r=0.1)] * MIN_SAMPLE_FOR_RELIABLE)
    assert small["reliable"] is False
    assert big["reliable"] is True


# ===================================================================
# The DB adapter (analytics.edge_statistics)
# ===================================================================

import aiosqlite
import pytest_asyncio  # noqa: F401


@pytest.mark.asyncio
async def test_edge_statistics_reads_trade_outcomes_in_close_order(tmp_path):
    """max_drawdown walks the equity curve in CLOSE ORDER and refuses to sort
    for itself. If the adapter's ORDER BY ever goes missing, the drawdown
    becomes a plausible, wrong number -- so pin it with rows inserted OUT of
    order whose correct drawdown depends on the ordering."""
    from analytics import edge_statistics, init_analytics_db

    db_path = str(tmp_path / "cache.db")
    await init_analytics_db(db_path)

    # Inserted deliberately out of chronological order.
    # True close order: +1000, -800, +1300, -200  -> worst drawdown = 800.
    rows = [
        ("C", "2026-07-03T10:00:00+00:00", 1300.0, 2.0),
        ("A", "2026-07-01T10:00:00+00:00", 1000.0, 1.5),
        ("D", "2026-07-04T10:00:00+00:00", -200.0, -0.4),
        ("B", "2026-07-02T10:00:00+00:00", -800.0, -1.0),
    ]
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO trade_outcomes (ticker, closed_at, realised_pnl, r_multiple) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        await db.commit()

    report = await edge_statistics(db_path, days=3650)

    assert report["n"] == 4
    # 800, not 200 (which is what you get if the rows arrive unsorted).
    assert report["max_drawdown_rupees"] == 800.0
    assert report["expectancy_rupees"] == pytest.approx((1000 - 800 + 1300 - 200) / 4)
    assert report["reliable"] is False  # only 4 trades -- say so


@pytest.mark.asyncio
async def test_edge_statistics_on_an_empty_table_says_no_data(tmp_path):
    from analytics import edge_statistics, init_analytics_db

    db_path = str(tmp_path / "cache.db")
    await init_analytics_db(db_path)

    report = await edge_statistics(db_path, days=90)
    assert report["n"] == 0
    assert report["verdict"] == "no_data"
