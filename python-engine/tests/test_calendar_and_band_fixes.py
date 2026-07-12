"""
[ROADMAP-3.9 / 3.10 2026-07-12] Witnesses.

3.9  circuit band read from the quote's real lower/upper_circuit_limit
     fields, inference demoted to fallback.
3.10 holiday hygiene: static NSE list as the loud last-resort fallback
     (was a SILENT weekday-only fail-open, HIGH-010), is_market_open
     holiday-aware, and the operator-curated earnings/event no-trade
     window.
"""
from datetime import date, datetime

import httpx
import pytest

import event_calendar
import market_calendar
from config import settings
from penny_risk import PennyRiskEngine


# ===================================================================
# 3.9 -- band_pct_from_quote
# ===================================================================

class TestBandFromQuote:
    def test_real_limits_win_over_inference(self):
        """THE roadmap scenario: a quiet day (range would infer 5%) on a
        stock whose real band is 20% -- the quote fields must win."""
        band = PennyRiskEngine.band_pct_from_quote(
            quote={"lower_circuit_limit": 80.0, "upper_circuit_limit": 120.0},
            prev_close=100.0, day_high=101.0, day_low=99.5,
        )
        assert band == pytest.approx(0.20)

    def test_asymmetric_limits_take_wider_side(self):
        band = PennyRiskEngine.band_pct_from_quote(
            quote={"lower_circuit_limit": 95.0, "upper_circuit_limit": 110.0},
            prev_close=100.0, day_high=101.0, day_low=99.5,
        )
        assert band == pytest.approx(0.10)

    def test_missing_limits_fall_back_to_inference(self):
        band = PennyRiskEngine.band_pct_from_quote(
            quote={}, prev_close=100.0, day_high=101.0, day_low=99.5,
        )
        assert band == 0.05  # quiet-day inference

    def test_zero_limits_fall_back(self):
        """Some segments return 0.0 circuit fields -- junk, use inference."""
        band = PennyRiskEngine.band_pct_from_quote(
            quote={"lower_circuit_limit": 0.0, "upper_circuit_limit": 0.0},
            prev_close=100.0, day_high=112.0, day_low=99.0,
        )
        assert band == 0.10  # inferred from the 12% move

    def test_inverted_limits_fall_back(self):
        band = PennyRiskEngine.band_pct_from_quote(
            quote={"lower_circuit_limit": 120.0, "upper_circuit_limit": 80.0},
            prev_close=100.0, day_high=101.0, day_low=99.5,
        )
        assert band == 0.05

    def test_absurd_band_falls_back(self):
        """A 60% implied band is outside any NSE regime -> junk fields."""
        band = PennyRiskEngine.band_pct_from_quote(
            quote={"lower_circuit_limit": 40.0, "upper_circuit_limit": 160.0},
            prev_close=100.0, day_high=101.0, day_low=99.5,
        )
        assert band == 0.05


# ===================================================================
# 3.10 -- holiday fallback + is_market_open
# ===================================================================

class _FailingClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        raise httpx.RequestError("bot-blocked")


@pytest.fixture
def blocked_nse(monkeypatch):
    """Empty holiday cache + nseindia.com unreachable + alert recorder."""
    calls = []
    monkeypatch.setattr(market_calendar.httpx, "AsyncClient", _FailingClient)
    monkeypatch.setattr(
        market_calendar, "_alert_static_fallback", lambda reason: calls.append(reason)
    )
    return calls


class TestHolidayStaticFallback:
    @pytest.mark.asyncio
    async def test_holiday_blocked_when_fetch_fails(self, db_path, blocked_nse):
        # 2026-10-02 (Gandhi Jayanti) is a Friday.
        assert await market_calendar.is_trading_day(date(2026, 10, 2), db_path) is False

    @pytest.mark.asyncio
    async def test_normal_weekday_still_trades(self, db_path, blocked_nse):
        assert await market_calendar.is_trading_day(date(2026, 7, 10), db_path) is True

    @pytest.mark.asyncio
    async def test_fallback_pages_the_operator(self, db_path, blocked_nse):
        await market_calendar.is_trading_day(date(2026, 7, 10), db_path)
        assert len(blocked_nse) == 1

    @pytest.mark.asyncio
    async def test_populated_cache_needs_no_fallback(self, db_path, blocked_nse):
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "CREATE TABLE holidays (holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)"
            )
            await db.execute(
                "INSERT INTO holidays VALUES ('2026-07-10', CURRENT_TIMESTAMP)"
            )
            await db.commit()
        assert await market_calendar.is_trading_day(date(2026, 7, 10), db_path) is False
        assert blocked_nse == []  # cache answered; no fallback, no page

    def test_sync_fallback_uses_static_list(self, db_path):
        assert market_calendar.is_trading_day_sync(date(2026, 10, 2), db_path) is False
        assert market_calendar.is_trading_day_sync(date(2026, 7, 10), db_path) is True


class _FakeDT:
    """datetime stand-in so is_market_open sees a chosen 'now'."""
    fixed = None

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


class TestIsMarketOpenHolidayAware:
    def _set_now(self, monkeypatch, y, mo, d, h, mi):
        _FakeDT.fixed = market_calendar.IST.localize(datetime(y, mo, d, h, mi))
        monkeypatch.setattr(market_calendar, "datetime", _FakeDT)

    def test_closed_on_nse_holiday(self, monkeypatch):
        self._set_now(monkeypatch, 2026, 10, 2, 11, 0)  # Friday, holiday
        assert market_calendar.is_market_open() is False

    def test_open_on_normal_weekday(self, monkeypatch):
        self._set_now(monkeypatch, 2026, 7, 10, 11, 0)
        assert market_calendar.is_market_open() is True

    def test_closed_on_weekend(self, monkeypatch):
        self._set_now(monkeypatch, 2026, 7, 11, 11, 0)  # Saturday
        assert market_calendar.is_market_open() is False


# ===================================================================
# 3.10 -- event calendar
# ===================================================================

@pytest.fixture
def event_csv(tmp_path, monkeypatch):
    p = tmp_path / "event_calendar.csv"
    p.write_text(
        "ticker,event_date,event_type\n"
        "SUZLON,2026-07-25,RESULTS\n"
        "IDEA,2026-07-28,AGM\n"
        "BADROW\n"
        "BADDATE,not-a-date,RESULTS\n"
    )
    # Fresh TTL cache per test.
    monkeypatch.setitem(event_calendar._cache, "loaded_monotonic", None)
    monkeypatch.setitem(event_calendar._cache, "path", None)
    return str(p)


class TestEventCalendar:
    def test_blocked_inside_window(self, event_csv):
        # Default window: 2 days before through the event day itself.
        for d in (date(2026, 7, 23), date(2026, 7, 24), date(2026, 7, 25)):
            blocked, reason = event_calendar.event_block("SUZLON", d, event_csv)
            assert blocked is True
            assert "RESULTS" in reason and "2026-07-25" in reason

    def test_allowed_outside_window(self, event_csv):
        for d in (date(2026, 7, 22), date(2026, 7, 26)):
            assert event_calendar.event_block("SUZLON", d, event_csv) == (False, "")

    def test_unknown_ticker_allowed(self, event_csv):
        assert event_calendar.event_block("RELIANCE", date(2026, 7, 25), event_csv) \
            == (False, "")

    def test_missing_csv_allows_everything(self, tmp_path, monkeypatch):
        monkeypatch.setitem(event_calendar._cache, "loaded_monotonic", None)
        assert event_calendar.event_block(
            "SUZLON", date(2026, 7, 25), str(tmp_path / "nope.csv")
        ) == (False, "")

    def test_malformed_rows_do_not_poison_good_ones(self, event_csv):
        blocked, _ = event_calendar.event_block("IDEA", date(2026, 7, 28), event_csv)
        assert blocked is True

    def test_master_toggle_off_allows(self, event_csv, monkeypatch):
        monkeypatch.setattr(settings, "PENNY_USE_EVENT_FILTER", False)
        assert event_calendar.event_block(
            "SUZLON", date(2026, 7, 25), event_csv
        ) == (False, "")

    def test_case_insensitive_ticker(self, event_csv):
        blocked, _ = event_calendar.event_block("suzlon", date(2026, 7, 25), event_csv)
        assert blocked is True
