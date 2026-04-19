"""
Tests for python-engine/position_tracker.py — position state, trailing stops, Q8/Q10.
"""
import pytest
import pytest_asyncio
import math
import aiosqlite
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pandas as pd

from position_tracker import (
    init_positions_db,
    get_open_positions,
    update_daily_positions,
)
from engine import calc_zerodha_costs


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def _insert_position(db_path, **kwargs):
    """Insert a test position into the positions table."""
    defaults = {
        "ticker": "RELIANCE",
        "exchange": "NSE",
        "entry_date": "2025-10-01",
        "entry_price": 500.0,
        "shares": 10,
        "stop_loss_initial": 475.0,
        "trailing_stop_current": 475.0,
        "target_1": 537.5,
        "target_2": 575.0,
        "atr_14_at_entry": 16.67,
        "highest_close_since_entry": 500.0,
        "status": "OPEN",
        "source": "SYSTEM",
        "exit_price": None,
        "exit_date": None,
        "realised_pnl": None,
        "r_multiple": None,
    }
    defaults.update(kwargs)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO positions (ticker, exchange, entry_date, entry_price, shares,
                stop_loss_initial, trailing_stop_current, target_1, target_2,
                atr_14_at_entry, highest_close_since_entry, status, source,
                exit_price, exit_date, realised_pnl, r_multiple)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            defaults["ticker"], defaults["exchange"], defaults["entry_date"],
            defaults["entry_price"], defaults["shares"], defaults["stop_loss_initial"],
            defaults["trailing_stop_current"], defaults["target_1"], defaults["target_2"],
            defaults["atr_14_at_entry"], defaults["highest_close_since_entry"],
            defaults["status"], defaults["source"], defaults["exit_price"],
            defaults["exit_date"], defaults["realised_pnl"], defaults["r_multiple"]
        ))
        await db.commit()


@pytest_asyncio.fixture
async def pos_db(db_path):
    """Initialize positions table."""
    await init_positions_db(db_path)
    return db_path


def _mock_kite(today_close):
    """Create a mock kite_client that returns a DataFrame with one row."""
    kite = AsyncMock()
    df = pd.DataFrame({"close": [today_close]})
    kite.get_historical = AsyncMock(return_value=df)
    return kite


# ═══════════════════════════════════════════════════════════════
# POSITION TABLE BASICS
# ═══════════════════════════════════════════════════════════════


class TestPositionDB:

    @pytest.mark.asyncio
    async def test_init_creates_table(self, pos_db):
        async with aiosqlite.connect(pos_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='positions'"
            )
            row = await cursor.fetchone()
            assert row is not None

    @pytest.mark.asyncio
    async def test_get_open_positions_empty(self, pos_db):
        positions = await get_open_positions(pos_db)
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_open_positions_includes_open(self, pos_db):
        await _insert_position(pos_db, status="OPEN")
        positions = await get_open_positions(pos_db)
        assert len(positions) == 1

    @pytest.mark.asyncio
    async def test_get_open_positions_includes_closed_t1(self, pos_db):
        """CLOSED_T1 positions are still 'open' (managing remaining 50%)."""
        await _insert_position(pos_db, status="CLOSED_T1")
        positions = await get_open_positions(pos_db)
        assert len(positions) == 1

    @pytest.mark.asyncio
    async def test_get_open_excludes_fully_closed(self, pos_db):
        """Fully closed statuses should not appear in open positions."""
        await _insert_position(pos_db, ticker="A", status="CLOSED_T2")
        await _insert_position(pos_db, ticker="B", status="STOPPED_OUT")
        await _insert_position(pos_db, ticker="C", status="CLOSED_TIME")
        positions = await get_open_positions(pos_db)
        assert len(positions) == 0


# ═══════════════════════════════════════════════════════════════
# Q8: MOMENTUM POSITIONS EXEMPT FROM TRAILING STOP
# ═══════════════════════════════════════════════════════════════


class TestMomentumExemptQ8:

    @pytest.mark.asyncio
    async def test_momentum_skipped(self, pos_db):
        """[Q8] MOMENTUM positions must be skipped by update_daily_positions."""
        await _insert_position(pos_db, source="MOMENTUM", trailing_stop_current=475.0)
        kite = _mock_kite(510.0)
        record_cb = AsyncMock()

        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        # Kite should NOT be called for MOMENTUM positions
        kite.get_historical.assert_not_called()
        # Position should remain unchanged
        positions = await get_open_positions(pos_db)
        assert len(positions) == 1
        assert positions[0]["trailing_stop_current"] == 475.0

    @pytest.mark.asyncio
    async def test_system_position_gets_updated(self, pos_db):
        """SYSTEM positions DO get trailing stop updates."""
        await _insert_position(pos_db, source="SYSTEM", trailing_stop_current=475.0)
        kite = _mock_kite(520.0)  # new high
        record_cb = AsyncMock()

        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        # Kite should be called
        kite.get_historical.assert_called_once()
        # Trailing stop should be updated
        positions = await get_open_positions(pos_db)
        assert len(positions) == 1
        assert positions[0]["trailing_stop_current"] >= 475.0


# ═══════════════════════════════════════════════════════════════
# TRAILING STOP UPDATES
# ═══════════════════════════════════════════════════════════════


class TestTrailingStop:

    @pytest.mark.asyncio
    async def test_trailing_stop_rises_with_price(self, pos_db):
        """New trail = highest_close - 1.5*ATR. Must only ratchet up."""
        await _insert_position(
            pos_db, entry_price=500.0, atr_14_at_entry=10.0,
            trailing_stop_current=485.0, highest_close_since_entry=500.0,
            target_1=530.0, target_2=560.0
        )
        # Today close = 520 → new highest = 520
        # new_trail = 520 - 1.5*10 = 505 > 485 → update to 505
        kite = _mock_kite(520.0)
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        positions = await get_open_positions(pos_db)
        assert positions[0]["trailing_stop_current"] == 505.0
        assert positions[0]["highest_close_since_entry"] == 520.0

    @pytest.mark.asyncio
    async def test_trailing_stop_never_drops(self, pos_db):
        """If price drops, trailing stop must not decrease."""
        await _insert_position(
            pos_db, entry_price=500.0, atr_14_at_entry=10.0,
            trailing_stop_current=505.0, highest_close_since_entry=520.0,
            target_1=530.0, target_2=560.0
        )
        # Today close = 510 → highest stays 520
        # new_trail = 520 - 15 = 505 = current → no change
        kite = _mock_kite(510.0)
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        positions = await get_open_positions(pos_db)
        assert positions[0]["trailing_stop_current"] >= 505.0


# ═══════════════════════════════════════════════════════════════
# STATUS TRANSITIONS
# ═══════════════════════════════════════════════════════════════


class TestStatusTransitions:

    @pytest.mark.asyncio
    async def test_stopped_out(self, pos_db):
        """Close <= trailing_stop → STOPPED_OUT."""
        await _insert_position(
            pos_db, entry_price=500.0, atr_14_at_entry=10.0,
            trailing_stop_current=490.0, highest_close_since_entry=500.0,
            target_1=530.0, target_2=560.0
        )
        kite = _mock_kite(489.0)  # below trailing stop
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        async with aiosqlite.connect(pos_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions")
            pos = dict(await cursor.fetchone())
        assert pos["status"] == "STOPPED_OUT"
        assert pos["exit_price"] is not None
        record_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_target_2_hit(self, pos_db):
        """Close >= target_2 → CLOSED_T2."""
        await _insert_position(
            pos_db, entry_price=500.0, atr_14_at_entry=10.0,
            trailing_stop_current=490.0, highest_close_since_entry=500.0,
            target_1=530.0, target_2=560.0
        )
        kite = _mock_kite(565.0)
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        async with aiosqlite.connect(pos_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions")
            pos = dict(await cursor.fetchone())
        assert pos["status"] == "CLOSED_T2"

    @pytest.mark.asyncio
    async def test_target_1_partial_close(self, pos_db):
        """Close >= target_1 and status OPEN → CLOSED_T1, shares halved."""
        await _insert_position(
            pos_db, entry_price=500.0, shares=10, atr_14_at_entry=10.0,
            trailing_stop_current=490.0, highest_close_since_entry=500.0,
            target_1=530.0, target_2=560.0, status="OPEN"
        )
        kite = _mock_kite(535.0)  # above T1 but below T2
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        async with aiosqlite.connect(pos_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions")
            pos = dict(await cursor.fetchone())
        assert pos["status"] == "CLOSED_T1"
        # 50% shares closed: floor(10 * 0.5) = 5 remaining
        assert pos["shares"] == 5
        # Trailing stop moved to breakeven (entry_price)
        assert pos["trailing_stop_current"] >= 500.0
        record_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_time_expiry_15_days(self, pos_db):
        """Position held >= 15 days → CLOSED_TIME."""
        entry_date = "2025-09-20"
        await _insert_position(
            pos_db, entry_date=entry_date, entry_price=500.0,
            atr_14_at_entry=10.0, trailing_stop_current=490.0,
            highest_close_since_entry=510.0,
            target_1=530.0, target_2=560.0
        )
        # 15 days later
        kite = _mock_kite(515.0)  # between entry and targets
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-05", record_cb)

        async with aiosqlite.connect(pos_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions")
            pos = dict(await cursor.fetchone())
        assert pos["status"] == "CLOSED_TIME"

    @pytest.mark.asyncio
    async def test_closed_t1_does_not_re_trigger_t1(self, pos_db):
        """CLOSED_T1 position should not re-trigger T1 partial close."""
        await _insert_position(
            pos_db, entry_price=500.0, shares=5, status="CLOSED_T1",
            atr_14_at_entry=10.0, trailing_stop_current=500.0,
            highest_close_since_entry=535.0,
            target_1=530.0, target_2=560.0
        )
        kite = _mock_kite(540.0)  # still above T1
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        positions = await get_open_positions(pos_db)
        # Should still be CLOSED_T1, not further reduced
        assert positions[0]["status"] == "CLOSED_T1"
        assert positions[0]["shares"] == 5
        record_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_pnl_recorded_on_close(self, pos_db):
        """Realised P&L and R-multiple should be computed on full close."""
        await _insert_position(
            pos_db, entry_price=500.0, shares=10, atr_14_at_entry=10.0,
            stop_loss_initial=475.0, trailing_stop_current=490.0,
            highest_close_since_entry=500.0,
            target_1=530.0, target_2=560.0
        )
        kite = _mock_kite(565.0)  # T2 hit
        record_cb = AsyncMock()
        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        async with aiosqlite.connect(pos_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM positions")
            pos = dict(await cursor.fetchone())
        assert pos["realised_pnl"] is not None
        assert pos["r_multiple"] is not None
        assert pos["realised_pnl"] > 0  # profitable trade

    @pytest.mark.asyncio
    async def test_empty_data_no_crash(self, pos_db):
        """If kite returns empty DataFrame, position should not change."""
        await _insert_position(pos_db)
        kite = AsyncMock()
        kite.get_historical = AsyncMock(return_value=pd.DataFrame())
        record_cb = AsyncMock()

        await update_daily_positions(pos_db, kite, "2025-10-10", record_cb)

        positions = await get_open_positions(pos_db)
        assert len(positions) == 1
        assert positions[0]["status"] == "OPEN"
