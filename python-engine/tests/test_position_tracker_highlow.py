"""
[POS-TRACKER-HIGHLOW-TEST 2026-07-01] Regression test for the
high/low fix in update_daily_positions.
"""
import asyncio
import os
import sys
import pytest
import pandas as pd
from unittest.mock import AsyncMock

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import aiosqlite

from config import settings
from position_tracker import init_positions_db, update_daily_positions


def _mock_kite_with_ohlc(open_, high, low, close):
    kite = AsyncMock()
    df = pd.DataFrame({
        "open":  [open_],
        "high":  [high],
        "low":   [low],
        "close": [close],
        "volume": [10000],
    })
    kite.get_historical = AsyncMock(return_value=df)
    return kite


async def _seed_one_position(
    db_path, entry_price, shares, target_1, target_2,
    stop_loss, trailing_stop, highest_close,
):
    await init_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO positions (
                ticker, exchange, entry_date, entry_price, shares,
                stop_loss_initial, trailing_stop_current,
                target_1, target_2, atr_14_at_entry,
                highest_close_since_entry, status, source,
                product_type, regime_at_entry,
                atr_1min_post_t1, t1_fired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEST", "NSE", "2025-10-01T09:30:00",
             entry_price, shares, stop_loss, trailing_stop,
             target_1, target_2, 10.0, highest_close,
             "OPEN", "EDGE_PAPER", "CNC", "REGIME_1_NORMAL",
             0.0, 0),
        )
        await db.commit()


async def _get_status_shares(db_path):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT status, shares FROM positions")
        row = await cur.fetchone()
        return row["status"], row["shares"]


@pytest.mark.asyncio
async def test_tp_hit_detected_via_high_even_when_close_below_target(tmp_path):
    """[HIGHLOW-1]"""
    db_path = str(tmp_path / "t1.db")
    await _seed_one_position(
        db_path, entry_price=100.0, shares=10,
        target_1=100.0, target_2=110.0,
        stop_loss=95.0, trailing_stop=96.0, highest_close=99.0,
    )
    kite = _mock_kite_with_ohlc(open_=99.0, high=101.0, low=98.5, close=98.0)
    record_cb = AsyncMock()
    await update_daily_positions(db_path, kite, "2025-10-10", record_cb)
    status, shares = await _get_status_shares(db_path)
    assert status == "CLOSED_T1"
    assert shares == 5


@pytest.mark.asyncio
async def test_sl_hit_detected_via_low_even_when_close_above_stop(tmp_path):
    """[HIGHLOW-2]"""
    db_path = str(tmp_path / "sl.db")
    await _seed_one_position(
        db_path, entry_price=100.0, shares=10,
        target_1=110.0, target_2=120.0,
        stop_loss=95.0, trailing_stop=96.0, highest_close=100.0,
    )
    kite = _mock_kite_with_ohlc(open_=99.0, high=100.0, low=95.5, close=98.0)
    record_cb = AsyncMock()
    await update_daily_positions(db_path, kite, "2025-10-10", record_cb)
    status, shares = await _get_status_shares(db_path)
    assert status == "STOPPED_OUT"


@pytest.mark.asyncio
async def test_no_touch_keeps_position_open(tmp_path):
    """[HIGHLOW-3]"""
    db_path = str(tmp_path / "hold.db")
    await _seed_one_position(
        db_path, entry_price=100.0, shares=10,
        target_1=110.0, target_2=120.0,
        stop_loss=95.0, trailing_stop=96.0, highest_close=99.0,
    )
    kite = _mock_kite_with_ohlc(open_=99.0, high=99.5, low=98.5, close=99.0)
    record_cb = AsyncMock()
    await update_daily_positions(db_path, kite, "2025-10-10", record_cb)
    status, shares = await _get_status_shares(db_path)
    assert status == "OPEN"
    assert shares == 10


@pytest.mark.asyncio
async def test_position_tracker_handles_close_only_dataframe(tmp_path):
    """[HIGHLOW-4]"""
    db_path = str(tmp_path / "tolerant.db")
    await _seed_one_position(
        db_path, entry_price=100.0, shares=10,
        target_1=110.0, target_2=120.0,
        stop_loss=95.0, trailing_stop=96.0, highest_close=99.0,
    )
    kite = AsyncMock()
    df = pd.DataFrame({"close": [99.0]})
    kite.get_historical = AsyncMock(return_value=df)
    record_cb = AsyncMock()
    await update_daily_positions(db_path, kite, "2025-10-10", record_cb)
    status, shares = await _get_status_shares(db_path)
    assert status == "OPEN"


async def _get_exit(db_path):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status, exit_price, realised_pnl FROM positions")
        row = await cur.fetchone()
        return row["status"], row["exit_price"], row["realised_pnl"]


@pytest.mark.asyncio
async def test_gap_through_stop_fills_at_the_open_not_at_the_stop(tmp_path):
    """[GAP-THROUGH 2026-07-31] The 2026-07-30 SIGMA exit.

    The stock gapped below its stop and never traded at the stop price again.
    Booking the exit AT the stop invents a fill the market never offered and
    flatters the P&L -- SIGMA was booked out at 50.304 on a day that opened
    48.00 and closed 47.30. The fill must be clamped to the open."""
    db_path = str(tmp_path / "gap.db")
    await _seed_one_position(
        db_path, entry_price=52.40, shares=100,
        target_1=55.02, target_2=60.0,
        stop_loss=50.304, trailing_stop=50.304, highest_close=52.40,
    )
    # Opens 4.6% below the stop; low 47.20; closes 47.30 -- exactly SIGMA.
    kite = _mock_kite_with_ohlc(open_=48.00, high=52.58, low=47.20, close=47.30)
    record_cb = AsyncMock()
    await update_daily_positions(db_path, kite, "2026-07-30", record_cb)
    status, exit_price, _pnl = await _get_exit(db_path)
    assert status == "STOPPED_OUT"
    # Must NOT be the untouched 50.304.
    assert exit_price == pytest.approx(48.00)


@pytest.mark.asyncio
async def test_normal_stop_touch_still_fills_at_the_stop(tmp_path):
    """The clamp must not penalise an ordinary intraday stop touch: when the
    bar opens ABOVE the stop and only wicks down to it, the stop is where the
    order fills."""
    db_path = str(tmp_path / "touch.db")
    await _seed_one_position(
        db_path, entry_price=100.0, shares=10,
        target_1=110.0, target_2=120.0,
        stop_loss=95.0, trailing_stop=96.0, highest_close=100.0,
    )
    kite = _mock_kite_with_ohlc(open_=99.0, high=100.0, low=95.5, close=98.0)
    record_cb = AsyncMock()
    await update_daily_positions(db_path, kite, "2025-10-10", record_cb)
    status, exit_price, _pnl = await _get_exit(db_path)
    assert status == "STOPPED_OUT"
    assert exit_price == pytest.approx(96.0)
