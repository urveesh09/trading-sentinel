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
