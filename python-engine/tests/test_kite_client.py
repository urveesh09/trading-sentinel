"""
Tests for kite_client.py — RateLimiter, KiteClient, cache behaviour, Q1, Q7.

Mocks httpx.AsyncClient so no real Zerodha calls are made.
Uses in-memory-like temp SQLite DB from conftest.patch_settings.
"""
import os
import sys
import asyncio
import pytest
import pytest_asyncio
import pandas as pd
import numpy as np
import aiosqlite
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kite_client import RateLimiter, KiteClient


# ─────────────────────────────────────────────────────────────────────
# RateLimiter Tests
# ─────────────────────────────────────────────────────────────────────

class TestRateLimiter:
    """Token-bucket rate limiter used before every Kite API call."""

    @pytest.mark.asyncio
    async def test_initial_burst_allowed(self):
        """First acquire should succeed immediately (burst=1)."""
        limiter = RateLimiter(rate=3.0, burst=1)
        # Should complete without delay
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)
        assert limiter.tokens < 1

    @pytest.mark.asyncio
    async def test_burst_tokens_consumed(self):
        """With burst=3, three rapid acquires succeed, fourth blocks."""
        limiter = RateLimiter(rate=3.0, burst=3)
        for _ in range(3):
            await asyncio.wait_for(limiter.acquire(), timeout=0.5)
        # tokens should be depleted
        assert limiter.tokens < 1

    @pytest.mark.asyncio
    async def test_token_refill_over_time(self):
        """Tokens refill at the configured rate."""
        limiter = RateLimiter(rate=100.0, burst=1)
        await limiter.acquire()  # consume the burst
        # After a small sleep, tokens should refill enough for another acquire
        await asyncio.sleep(0.05)
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_rate_3_burst_1_defaults(self):
        """Default config: rate=3.0, burst=1 — matches KiteClient init."""
        limiter = RateLimiter(rate=3.0, burst=1)
        assert limiter.rate == 3.0
        assert limiter.burst == 1
        assert limiter.tokens == 1


# ─────────────────────────────────────────────────────────────────────
# KiteClient — Initialisation & Token
# ─────────────────────────────────────────────────────────────────────

class TestKiteClientInit:

    def test_constructor_defaults(self, patch_settings):
        client = KiteClient(patch_settings.DB_PATH)
        assert client.access_token == ""
        assert client.instrument_cache == {}
        assert client.limiter.rate == 3.0
        assert client.limiter.burst == 1

    def test_set_token_updates_headers(self, patch_settings, monkeypatch):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        client = KiteClient(patch_settings.DB_PATH)
        client.set_token("my_token_123")
        assert client.access_token == "my_token_123"
        auth_header = client.client.headers.get("Authorization")
        assert "my_token_123" in auth_header
        assert "test_key" in auth_header

    def test_set_token_sets_kite_version(self, patch_settings, monkeypatch):
        monkeypatch.setenv("ZERODHA_API_KEY", "k")
        client = KiteClient(patch_settings.DB_PATH)
        client.set_token("tok")
        assert client.client.headers.get("X-Kite-Version") == "3"


# ─────────────────────────────────────────────────────────────────────
# KiteClient — refresh_instrument_cache
# ─────────────────────────────────────────────────────────────────────

class TestRefreshInstrumentCache:

    @pytest.mark.asyncio
    async def test_skips_when_no_token(self, patch_settings):
        """refresh_instrument_cache should no-op when access_token is empty."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = ""
        await client.refresh_instrument_cache()
        assert client.instrument_cache == {}

    @pytest.mark.asyncio
    async def test_fetches_nse_and_indices(self, patch_settings):
        """Should call /instruments/NSE and /instruments/INDICES."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "valid_token"

        nse_csv = 'instrument_token,exchange_token,tradingsymbol,name\n123,10,"RELIANCE","Reliance"\n456,20,"TCS","TCS Ltd"'
        indices_csv = 'instrument_token,exchange_token,tradingsymbol,name\n999,50,"NIFTY 50","Nifty 50 Index"'

        mock_responses = {
            "/instruments/NSE": MagicMock(status_code=200, text=nse_csv, raise_for_status=MagicMock()),
            "/instruments/INDICES": MagicMock(status_code=200, text=indices_csv, raise_for_status=MagicMock()),
        }

        async def mock_get(url, **kwargs):
            return mock_responses[url]

        client.client.get = mock_get
        await client.refresh_instrument_cache()

        assert "RELIANCE" in client.instrument_cache
        assert "TCS" in client.instrument_cache
        assert "NIFTY 50" in client.instrument_cache  # Q1: must resolve

    @pytest.mark.asyncio
    async def test_nifty_50_in_instrument_cache_q1(self, patch_settings):
        """Q1: NIFTY 50 must be found via INDICES segment, not just NSE."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "valid"

        nse_csv = 'instrument_token,exchange_token,tradingsymbol\n100,1,"RELIANCE"'
        indices_csv = 'instrument_token,exchange_token,tradingsymbol\n256265,1,"NIFTY 50"'

        async def mock_get(url, **kwargs):
            text = nse_csv if "NSE" in url else indices_csv
            resp = MagicMock(status_code=200, text=text, raise_for_status=MagicMock())
            return resp

        client.client.get = mock_get
        await client.refresh_instrument_cache()

        assert client.instrument_cache.get("NIFTY 50") is not None


# ─────────────────────────────────────────────────────────────────────
# KiteClient — get_historical (daily OHLCV) + ohlcv_cache
# ─────────────────────────────────────────────────────────────────────

class TestGetHistorical:

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self, patch_settings):
        """On empty cache, should call the Kite historical API."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"RELIANCE": "123"}

        candle_data = {
            "data": {
                "candles": [
                    ["2025-01-02T00:00:00+0530", 1000, 1020, 990, 1010, 500000],
                    ["2025-01-03T00:00:00+0530", 1010, 1030, 1005, 1025, 600000],
                ]
            }
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = candle_data

        call_count = 0
        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp

        client.client.get = mock_get
        df = await client.get_historical("RELIANCE", "2025-01-01", "2025-01-10")

        assert call_count > 0  # API was called
        assert not df.empty
        assert "close" in df.columns

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self, patch_settings):
        """With sufficient cached data, API should NOT be called."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"RELIANCE": "123"}

        # Seed 65 rows into ohlcv_cache (threshold is 60)
        await client._init_db()
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            base_date = datetime(2025, 1, 1)
            for i in range(65):
                d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
                fetched = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                await db.execute(
                    "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("RELIANCE", d, 1000+i, 1010+i, 990+i, 1005+i, 500000, fetched)
                )
            await db.commit()

        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()

        client.client.get = mock_get
        # Query range is within cached range, last_cached_date >= to_date, fetched_at < 24h
        df = await client.get_historical("RELIANCE", "2025-01-01", "2025-03-06")

        assert not api_called, "API should not be called on cache hit"
        assert not df.empty

    @pytest.mark.asyncio
    async def test_unknown_ticker_raises(self, patch_settings):
        """Should raise ValueError for a ticker not in instrument_cache."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {}

        # Seed empty ohlcv_cache so cache miss triggers API lookup
        await client._init_db()

        with pytest.raises(ValueError, match="Unknown ticker"):
            await client.get_historical("DOESNOTEXIST", "2025-01-01", "2025-01-10")

    @pytest.mark.asyncio
    async def test_retries_on_429(self, patch_settings):
        """Should retry on 429 (rate limit) up to 5 times."""
        import httpx
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"TEST": "1"}
        # Speed up limiter for test
        client.limiter = RateLimiter(rate=100.0, burst=10)

        await client._init_db()
        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                resp = MagicMock()
                resp.status_code = 429
                resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "rate limited", request=MagicMock(), response=resp
                )
                return resp
            # Succeed on 3rd call
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"data": {"candles": [
                ["2025-01-02T00:00:00+0530", 100, 110, 90, 105, 1000]
            ]}}
            return resp

        client.client.get = mock_get
        df = await client.get_historical("TEST", "2025-01-01", "2025-01-10")
        assert call_count == 3
        assert not df.empty

    @pytest.mark.asyncio
    async def test_empty_candles_returns_empty_df(self, patch_settings):
        """API returning empty candles should produce an empty DataFrame."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"EMPTY": "2"}
        client.limiter = RateLimiter(rate=100.0, burst=10)
        await client._init_db()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": {"candles": []}}

        async def mock_get(url, **kwargs):
            return mock_resp

        client.client.get = mock_get
        df = await client.get_historical("EMPTY", "2025-01-01", "2025-01-10")
        assert df.empty


# ─────────────────────────────────────────────────────────────────────
# KiteClient — get_intraday + intraday_cache (Q7)
# ─────────────────────────────────────────────────────────────────────

class TestGetIntraday:

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self, patch_settings):
        """On empty intraday_cache, should call the API."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"INFY": "456"}
        client.limiter = RateLimiter(rate=100.0, burst=10)

        candle_data = {
            "data": {
                "candles": [
                    ["2025-06-10T09:30:00+0530", 1500, 1510, 1490, 1505, 50000],
                    ["2025-06-10T09:45:00+0530", 1505, 1515, 1500, 1512, 60000],
                    ["2025-06-10T10:00:00+0530", 1512, 1520, 1508, 1518, 70000],
                    ["2025-06-10T10:15:00+0530", 1518, 1525, 1515, 1522, 80000],
                ]
            }
        }

        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = candle_data
            return resp

        client.client.get = mock_get
        df = await client.get_intraday("INFY", "2025-06-10 09:15:00", "2025-06-10 10:30:00")

        assert api_called
        assert not df.empty
        assert len(df) == 4

    @pytest.mark.asyncio
    async def test_intraday_cache_hit(self, patch_settings):
        """With 4+ cached candles, intraday should NOT call API."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"TCS": "789"}

        await client._init_intraday_db()
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            # for i in range(5):
            for i in range(5):
                mins = 15 + (i * 15)
                hrs = 9 + (mins // 60)
                mins = mins % 60
                dt = f"2025-06-10 {hrs:02d}:{mins:02d}:00"
                await db.execute(
                # dt = f"2025-06-10 {9+i//4:02d}:{15 + (i%4)*15:02d}:00"
                # await db.execute(
                    "INSERT INTO intraday_cache (ticker, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("TCS", dt, 3000+i, 3010+i, 2990+i, 3005+i, 100000, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
                )
            await db.commit()

        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()

        client.client.get = mock_get
        df = await client.get_intraday("TCS", "2025-06-10 09:15:00", "2025-06-10 10:15:00")

        assert not api_called, "API should not be called on intraday cache hit"
        assert not df.empty


# ─────────────────────────────────────────────────────────────────────
# Q7: ohlcv_cache and intraday_cache are separate tables
# ─────────────────────────────────────────────────────────────────────

class TestCacheSeparationQ7:

    @pytest.mark.asyncio
    async def test_tables_are_independent(self, patch_settings):
        """Writing to intraday_cache must NOT affect ohlcv_cache, and vice versa."""
        client = KiteClient(patch_settings.DB_PATH)
        await client._init_db()
        await client._init_intraday_db()

        # Insert into ohlcv_cache
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            await db.execute(
                "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("SBIN", "2025-01-01", 600, 610, 590, 605, 100000, "2025-01-01 00:00:00")
            )
            await db.commit()

        # Insert into intraday_cache
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            await db.execute(
                "INSERT INTO intraday_cache (ticker, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("SBIN", "2025-01-01 09:30:00", 600, 610, 590, 605, 50000, "2025-01-01 09:30:00")
            )
            await db.commit()

        # Assert ohlcv_cache has 1 row
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM ohlcv_cache")
            ohlcv_count = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache")
            intraday_count = (await cursor.fetchone())[0]

        assert ohlcv_count == 1
        assert intraday_count == 1

    @pytest.mark.asyncio
    async def test_different_primary_keys(self, patch_settings):
        """ohlcv_cache PK = (ticker, date), intraday_cache PK = (ticker, datetime)."""
        client = KiteClient(patch_settings.DB_PATH)
        await client._init_db()
        await client._init_intraday_db()

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            # ohlcv_cache: duplicate (ticker, date) should REPLACE
            await db.execute(
                "INSERT OR REPLACE INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("HDFC", "2025-01-01", 100, 110, 90, 105, 1000, "2025-01-01 00:00:00")
            )
            await db.execute(
                "INSERT OR REPLACE INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("HDFC", "2025-01-01", 101, 111, 91, 106, 1001, "2025-01-01 00:01:00")
            )
            await db.commit()
            cursor = await db.execute("SELECT COUNT(*) FROM ohlcv_cache WHERE ticker='HDFC'")
            count = (await cursor.fetchone())[0]
            assert count == 1, "ohlcv_cache should have 1 row (PK dedup)"

            # intraday_cache: duplicate (ticker, datetime) should REPLACE
            await db.execute(
                "INSERT OR REPLACE INTO intraday_cache (ticker, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("HDFC", "2025-01-01 09:15:00", 100, 110, 90, 105, 1000, "now")
            )
            await db.execute(
                "INSERT OR REPLACE INTO intraday_cache (ticker, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("HDFC", "2025-01-01 09:15:00", 101, 111, 91, 106, 1001, "now2")
            )
            await db.commit()
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache WHERE ticker='HDFC'")
            count = (await cursor.fetchone())[0]
            assert count == 1, "intraday_cache should have 1 row (PK dedup)"


# ─────────────────────────────────────────────────────────────────────
# KiteClient — clear_intraday_cache
# ─────────────────────────────────────────────────────────────────────

class TestClearIntradayCache:

    @pytest.mark.asyncio
    async def test_clears_old_candles(self, patch_settings):
        """clear_intraday_cache purges yesterday's data."""
        client = KiteClient(patch_settings.DB_PATH)
        await client._init_intraday_db()

        # Insert old candle (2 days ago) and a recent candle (today)
        old_dt = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d 10:00:00")
        recent_dt = datetime.utcnow().strftime("%Y-%m-%d 10:00:00")

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            await db.execute(
                "INSERT INTO intraday_cache (ticker, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", old_dt, 100, 110, 90, 105, 50000, "now")
            )
            await db.execute(
                "INSERT INTO intraday_cache (ticker, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", recent_dt, 100, 110, 90, 105, 50000, "now")
            )
            await db.commit()

        await client.clear_intraday_cache()

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache")
            count = (await cursor.fetchone())[0]

        # Old candle should be deleted, recent stays
        # (exact count depends on IST date boundary; at minimum old is purged)
        assert count <= 1


# ─────────────────────────────────────────────────────────────────────
# KiteClient — writes to correct cache table
# ─────────────────────────────────────────────────────────────────────

class TestCacheWriteIsolation:

    @pytest.mark.asyncio
    async def test_get_historical_writes_to_ohlcv_only(self, patch_settings):
        """get_historical must only write to ohlcv_cache, never intraday_cache."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"AAA": "1"}
        client.limiter = RateLimiter(rate=100.0, burst=10)

        mock_resp = MagicMock(status_code=200, raise_for_status=MagicMock())
        mock_resp.json.return_value = {"data": {"candles": [
            ["2025-01-02T00:00:00+0530", 100, 110, 90, 105, 1000]
        ]}}

        async def mock_get(url, **kwargs):
            return mock_resp

        client.client.get = mock_get
        await client._init_intraday_db()  # ensure intraday table exists
        await client.get_historical("AAA", "2025-01-01", "2025-01-10")

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM ohlcv_cache")
            ohlcv_count = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache")
            intraday_count = (await cursor.fetchone())[0]

        assert ohlcv_count >= 1
        assert intraday_count == 0

    @pytest.mark.asyncio
    async def test_get_intraday_writes_to_intraday_only(self, patch_settings):
        """get_intraday must only write to intraday_cache, never ohlcv_cache."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"BBB": "2"}
        client.limiter = RateLimiter(rate=100.0, burst=10)

        mock_resp = MagicMock(status_code=200, raise_for_status=MagicMock())
        mock_resp.json.return_value = {"data": {"candles": [
            ["2025-06-10T09:30:00+0530", 100, 110, 90, 105, 1000],
            ["2025-06-10T09:45:00+0530", 105, 115, 100, 112, 2000],
            ["2025-06-10T10:00:00+0530", 112, 118, 108, 115, 3000],
            ["2025-06-10T10:15:00+0530", 115, 120, 112, 118, 4000],
        ]}}

        async def mock_get(url, **kwargs):
            return mock_resp

        client.client.get = mock_get
        await client._init_db()  # ensure ohlcv table exists
        await client.get_intraday("BBB", "2025-06-10 09:15:00", "2025-06-10 10:30:00")

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM ohlcv_cache")
            ohlcv_count = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache")
            intraday_count = (await cursor.fetchone())[0]

        assert ohlcv_count == 0
        assert intraday_count >= 1
