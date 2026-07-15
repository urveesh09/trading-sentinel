"""
[DIVISION-BREAKDOWN 2026-07-15] Per-division P&L attribution.

Verifies that division_breakdown() attributes P&L to the correct division by
ledger `source`, rolls capital up per pool (swing + momentum share ONE Nifty
pool, counted once), and totals live vs paper separately — and that the
Telegram formatter renders it without error.
"""
import sqlite3
import pytest

import performance
from performance import (
    division_breakdown,
    format_division_breakdown,
    record_trade_close,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "cache.db")
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE bankroll_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, event_type TEXT, ticker TEXT, pnl REAL,
            bankroll_before REAL, bankroll_after REAL, source TEXT
        )
        """
    )
    con.commit()
    con.close()
    return path


def _div(data, key):
    return next(d for d in data["divisions"] if d["key"] == key)


@pytest.mark.asyncio
async def test_pnl_is_attributed_to_the_right_division(db):
    await record_trade_close(db, "AAA", -124.88, source="MOMENTUM")
    await record_trade_close(db, "BBB", 39.16, source="EDGE_LIVE")
    await record_trade_close(db, "CCC", 1732.60, source="EDGE_PAPER")

    data = await division_breakdown(db)

    assert _div(data, "momentum")["realised_pnl"] == pytest.approx(-124.88)
    assert _div(data, "penny_edge_live")["realised_pnl"] == pytest.approx(39.16)
    assert _div(data, "penny_edge_paper")["realised_pnl"] == pytest.approx(1732.60)
    # Swing saw no trades — a momentum loss must not bleed into it.
    assert _div(data, "swing")["realised_pnl"] == 0.0
    assert _div(data, "swing")["trades"] == 0
    assert _div(data, "momentum")["trades"] == 1


@pytest.mark.asyncio
async def test_swing_and_momentum_split_the_nifty_pool_50_50(db):
    # Swing and momentum are separate, non-overlapping halves of the ₹5,000
    # Nifty pool — ₹2,500 each at default MOMENTUM_POOL_PCT.
    await record_trade_close(db, "SW", 200.0, source="SYSTEM")
    await record_trade_close(db, "MO", -50.0, source="MOMENTUM")

    data = await division_breakdown(db)
    half = performance.settings.INITIAL_BANKROLL * performance.settings.MOMENTUM_POOL_PCT
    swing = _div(data, "swing")
    momentum = _div(data, "momentum")
    assert swing["allocated"] == pytest.approx(performance.settings.INITIAL_BANKROLL - half)
    assert momentum["allocated"] == pytest.approx(half)
    # Together they sum to the full Nifty pool — no double counting.
    assert swing["allocated"] + momentum["allocated"] == pytest.approx(performance.settings.INITIAL_BANKROLL)
    assert swing["realised_pnl"] == pytest.approx(200.0)
    assert momentum["realised_pnl"] == pytest.approx(-50.0)


@pytest.mark.asyncio
async def test_live_and_paper_totalled_separately(db):
    await record_trade_close(db, "L", 39.16, source="EDGE_LIVE")     # live
    await record_trade_close(db, "P", 1732.60, source="EDGE_PAPER")  # paper

    data = await division_breakdown(db)
    live = data["totals"]["live"]
    paper = data["totals"]["paper"]

    # Paper P&L must never land in the live total.
    assert live["realised_pnl"] == pytest.approx(39.16)
    assert paper["realised_pnl"] == pytest.approx(1732.60)
    # Live capital = Nifty 5000 + penny_breakout + edge_live 1000 (+ fno_live 0).
    assert live["capacity"] > 0
    assert paper["capacity"] >= 100000  # edge paper alone


@pytest.mark.asyncio
async def test_formatter_renders(db):
    await record_trade_close(db, "MO", -124.88, source="MOMENTUM")
    data = await division_breakdown(db)
    text = format_division_breakdown(data)
    assert "Bankroll by Division" in text
    assert "Intraday Momentum" in text
    assert "LIVE" in text and "PAPER" in text
