"""
[TIER0-0.2 2026-07-14] Paper money must never enter a live pool.

What happened: `daily_post_market` called

    update_daily_positions(db, kite, today, lambda t, p: record_trade_close(db, t, p))

The lambda dropped the position's source, so record_trade_close fell back to its
default `source="SYSTEM"`. But update_daily_positions walks EVERY open position --
including EDGE_PAPER ones, which are sized off a ₹100,000 imaginary bankroll while
the real book is ₹5,000.

So the paper leg's P&L was booked into the live pool:

    EDGE_PAPER net  = +3,826.27      <- paper money, ₹100k bankroll
    EDGE_LIVE  net  =    +39.16
    MOMENTUM   net  =    -23.33
                      ----------
    ledger reported   ₹8,842.11      the account actually held ₹5,015.83

76% of the reported P&L was fiction, and every downstream number -- edge_stats,
win rate, expectancy, the A/B comparisons this roadmap depends on -- inherited it.

The repo already had the right primitive (`bankroll_for_source`) and a conformance
rule that sizing must never use the mixed `current_bankroll()`. It just had one
caller that silently mislabelled the source.
"""
import pytest

import performance
from performance import bankroll_for_source, record_trade_close


PAPER_SOURCES = ("EDGE_PAPER", "FNO_PAPER", "PENNY_PAPER")
LIVE_SOURCES = ("SYSTEM", "MOMENTUM", "PENNY", "EDGE_LIVE")


@pytest.fixture
def db(tmp_path, monkeypatch):
    import sqlite3
    path = str(tmp_path / "cache.db")
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE bankroll_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, event_type TEXT, ticker TEXT, pnl REAL,
            bankroll_before REAL, bankroll_after REAL, source TEXT
        )
    """)
    con.commit()
    con.close()
    return path


@pytest.mark.asyncio
async def test_paper_pnl_does_not_move_the_live_pool(db, monkeypatch):
    """The regression, stated directly."""
    monkeypatch.setattr("analytics.record_trade_outcome", None, raising=False)

    live_before = await bankroll_for_source(db, "SYSTEM")

    # The EDGE paper leg books a fat ₹100k-sized win.
    await record_trade_close(db, "MCLOUD", 1325.18, source="EDGE_PAPER")

    live_after = await bankroll_for_source(db, "SYSTEM")

    assert live_after == live_before, (
        "paper P&L moved the live SYSTEM pool -- this is the ₹3,826 of fiction "
        "that made a ₹5,016 account report ₹8,842"
    )

    # ...and it is still recorded, in its own pool.
    paper = await bankroll_for_source(db, "EDGE_PAPER")
    assert paper == pytest.approx(performance.settings.INITIAL_BANKROLL + 1325.18)


@pytest.mark.asyncio
async def test_each_pool_only_sees_its_own_trades(db):
    await record_trade_close(db, "AAA", 100.0, source="MOMENTUM")
    await record_trade_close(db, "BBB", 5000.0, source="EDGE_PAPER")
    await record_trade_close(db, "CCC", -10.0, source="EDGE_LIVE")

    base = performance.settings.INITIAL_BANKROLL
    assert await bankroll_for_source(db, "MOMENTUM") == pytest.approx(base + 100.0)
    assert await bankroll_for_source(db, "EDGE_LIVE") == pytest.approx(base - 10.0)
    assert await bankroll_for_source(db, "SYSTEM") == pytest.approx(base)


@pytest.mark.asyncio
async def test_no_paper_source_leaks_into_any_live_pool(db):
    """The conformance rule, over the full cross-product."""
    for src in PAPER_SOURCES:
        await record_trade_close(db, "PAPERCO", 9999.0, source=src)

    base = performance.settings.INITIAL_BANKROLL
    for live in LIVE_SOURCES:
        assert await bankroll_for_source(db, live) == pytest.approx(base), (
            f"paper P&L reached the live pool {live!r}"
        )


@pytest.mark.asyncio
async def test_update_daily_positions_passes_the_source_through():
    """
    The actual defect was the CALLBACK SIGNATURE. position_tracker calls
    record_pnl_cb(ticker, pnl, source); if a caller binds a 2-arg lambda, the
    source is lost and record_trade_close silently defaults to SYSTEM.

    Pin the arity so a future 2-arg lambda fails loudly here rather than quietly
    in the ledger.
    """
    import inspect
    from position_tracker import update_daily_positions

    src = inspect.getsource(update_daily_positions)
    assert "record_pnl_cb(ticker, realised_pnl, " in src, (
        "update_daily_positions must pass the position's source to the ledger "
        "callback -- dropping it books paper trades into the live book"
    )
