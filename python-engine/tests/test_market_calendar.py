"""
Tests for python-engine/market_calendar.py - trading days, holidays, weekends.
"""
import pytest
import pytest_asyncio
import aiosqlite
from datetime import date
from market_calendar import is_trading_day, next_trading_day, prev_trading_day


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def cal_db(db_path):
    """Seed holiday table with known holidays."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS holidays "
            "(holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)"
        )
        # Known NSE holidays for testing (Republic Day, Independence Day, Diwali-ish)
        holidays = [
            "2026-01-26",  # Republic Day (Monday)
            "2026-08-15",  # Independence Day (Saturday - weekend anyway)
            "2026-10-02",  # Gandhi Jayanti (Friday)
            "2026-11-04",  # Diwali (Wednesday)
        ]
        for h in holidays:
            await db.execute(
                "INSERT OR IGNORE INTO holidays (holiday_date, fetched_at) "
                "VALUES (?, CURRENT_TIMESTAMP)",
                (h,)
            )
        await db.commit()
    return db_path


# ═══════════════════════════════════════════════════════════════
# WEEKENDS
# ═══════════════════════════════════════════════════════════════


class TestWeekends:

    @pytest.mark.asyncio
    async def test_saturday_not_trading(self, cal_db):
        # 2026-01-03 is a Saturday
        assert await is_trading_day(date(2026, 1, 3), cal_db) is False

    @pytest.mark.asyncio
    async def test_sunday_not_trading(self, cal_db):
        # 2026-01-04 is a Sunday
        assert await is_trading_day(date(2026, 1, 4), cal_db) is False


# ═══════════════════════════════════════════════════════════════
# HOLIDAYS
# ═══════════════════════════════════════════════════════════════


class TestHolidays:

    @pytest.mark.asyncio
    async def test_republic_day_holiday(self, cal_db):
        """Jan 26, 2026 (Monday) is a known NSE holiday."""
        assert await is_trading_day(date(2026, 1, 26), cal_db) is False

    @pytest.mark.asyncio
    async def test_gandhi_jayanti_holiday(self, cal_db):
        """Oct 2, 2026 (Friday) is a known NSE holiday."""
        assert await is_trading_day(date(2026, 10, 2), cal_db) is False

    @pytest.mark.asyncio
    async def test_diwali_holiday(self, cal_db):
        """Nov 4, 2026 (Wednesday) is a known NSE holiday."""
        assert await is_trading_day(date(2026, 11, 4), cal_db) is False


# ═══════════════════════════════════════════════════════════════
# NORMAL TRADING DAYS
# ═══════════════════════════════════════════════════════════════


class TestTradingDays:

    @pytest.mark.asyncio
    async def test_normal_wednesday(self, cal_db):
        """A Wednesday not in holiday list should be a trading day."""
        # 2026-01-07 is a Wednesday, not a holiday
        assert await is_trading_day(date(2026, 1, 7), cal_db) is True

    @pytest.mark.asyncio
    async def test_normal_friday(self, cal_db):
        """A Friday not in holiday list should be a trading day."""
        # 2026-01-09 is a Friday
        assert await is_trading_day(date(2026, 1, 9), cal_db) is True


# ═══════════════════════════════════════════════════════════════
# NEXT / PREV TRADING DAY
# ═══════════════════════════════════════════════════════════════


class TestNextPrevTradingDay:

    @pytest.mark.asyncio
    async def test_next_from_friday_is_monday(self, cal_db):
        """Next trading day after a Friday should be Monday (skipping weekend)."""
        # 2026-01-09 is Friday
        nxt = await next_trading_day(date(2026, 1, 9), cal_db)
        assert nxt == date(2026, 1, 12)  # Monday

    @pytest.mark.asyncio
    async def test_next_skips_holiday(self, cal_db):
        """Next trading day should skip holidays."""
        # 2026-01-25 is Sunday → Monday Jan 26 is Republic Day
        # Next trading day from Jan 25 should be Jan 27 (Tuesday)
        nxt = await next_trading_day(date(2026, 1, 25), cal_db)
        assert nxt == date(2026, 1, 27)

    @pytest.mark.asyncio
    async def test_prev_from_monday_is_friday(self, cal_db):
        """Prev trading day before a Monday should be Friday."""
        # 2026-01-12 is Monday
        prv = await prev_trading_day(date(2026, 1, 12), cal_db)
        assert prv == date(2026, 1, 9)  # Friday

    @pytest.mark.asyncio
    async def test_prev_skips_holiday(self, cal_db):
        """Prev trading day should skip holidays."""
        # 2026-01-27 is Tuesday, Jan 26 is holiday
        prv = await prev_trading_day(date(2026, 1, 27), cal_db)
        assert prv == date(2026, 1, 23)  # Friday before
