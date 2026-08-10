"""
Tests for kite_client.py - RateLimiter, KiteClient, cache behaviour, Q1, Q7.

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


# ---------------------------------------------------------------------
# RateLimiter Tests
# ---------------------------------------------------------------------

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
        """Default config: rate=3.0, burst=1 - matches KiteClient init."""
        limiter = RateLimiter(rate=3.0, burst=1)
        assert limiter.rate == 3.0
        assert limiter.burst == 1
        assert limiter.tokens == 1


# ---------------------------------------------------------------------
# KiteClient - Initialisation & Token
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# KiteClient - refresh_instrument_cache
# ---------------------------------------------------------------------

class TestRefreshInstrumentCache:

    @pytest.mark.asyncio
    async def test_skips_when_no_token(self, patch_settings):
        """refresh_instrument_cache should no-op when access_token is empty."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = ""
        await client.refresh_instrument_cache()
        assert client.instrument_cache == {}

    @pytest.mark.asyncio
    async def test_fetches_nse_only(self, patch_settings):
        """Should call /instruments/NSE only -- INDICES segment returns 403 on this plan."""
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "valid_token"

        nse_csv = 'instrument_token,exchange_token,tradingsymbol,name\n123,10,"RELIANCE","Reliance"\n456,20,"TCS","TCS Ltd"'

        mock_responses = {
            "/instruments/NSE": MagicMock(status_code=200, text=nse_csv, raise_for_status=MagicMock()),
        }

        async def mock_get(url, **kwargs):
            return mock_responses[url]

        client.client.get = mock_get
        await client.refresh_instrument_cache()

        assert "RELIANCE" in client.instrument_cache
        assert "TCS" in client.instrument_cache

    @pytest.mark.asyncio
    async def test_instrument_cache_values_are_int(self, patch_settings):
        """[INSTRUMENT-CACHE-INT 2026-07-03] The values stored in
        instrument_cache must be int, NOT str. The /quote HTTP response
        is keyed by int (`{int(k): v for k, v in data.items()}` in
        `KiteClient.get_quote`), so any consumer that does
        `kite.instrument_cache.get(symbol)` and then passes the result
        to a quote-fetching dict lookup needs an int. Pre-fix this
        stored `parts[0]` (a string from the raw CSV cell), causing
        every penny ticker to silently log `quote_unavailable` even
        when the cache was full.
        """
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "valid_token"

        # Real CSV shape: instrument_token is the FIRST column and is a
        # plain decimal integer with no quotes around it. Real-world
        # Kite /instruments/NSE returns values like 738561, 2953217, etc.
        nse_csv = (
            'instrument_token,exchange_token,tradingsymbol,name,last_price,'
            'tick_size,lot_size,instrument_type,segment,exchange\n'
            '738561,10,"RELIANCE","Reliance Industries",2500.0,0.05,1,EQ,NSE,NSE\n'
            '2953217,20,"TCS","Tata Consultancy",3450.5,0.05,1,EQ,NSE,NSE\n'
        )

        async def mock_get(url, **kwargs):
            return MagicMock(
                status_code=200, text=nse_csv, raise_for_status=MagicMock(),
            )

        client.client.get = mock_get
        await client.refresh_instrument_cache()

        # The full-row CSV from Kite has the token at index 0 (not 2)
        # -- this test deliberately uses the OTHER positional indexing
        # of `tradingsymbol` (parts[2]) for symbol extraction. The
        # assertion below verifies the cached VALUE type is `int`.
        # If symbol extraction at parts[2] is wrong for this fixture,
        # the cache will be empty and the assertion will say so.
        assert len(client.instrument_cache) >= 1, (
            "Cache should populate from CSV rows when tradingsymbol is at parts[2]; "
            "if this is 0, the column-order assumption has changed."
        )
        for symbol, token in client.instrument_cache.items():
            assert isinstance(token, int), (
                f"instrument_cache[{symbol!r}] = {token!r} (type {type(token).__name__}); "
                f"expected int. Storing str breaks the dict-key alignment "
                f"with /quote's int-keyed response and silently returns "
                f"None on every lookup. [INSTRUMENT-CACHE-INT 2026-07-03]"
            )

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="INDICES segment 403s on current Kite plan -- NIFTY 50 cannot be resolved via instrument_cache. Gap documented in GEMINI.md.")
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


# ---------------------------------------------------------------------
# KiteClient - get_historical (daily OHLCV) + ohlcv_cache
# ---------------------------------------------------------------------

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
    async def test_short_window_hits_cache(self, patch_settings):
        """[DAILY-CACHE-COVERAGE 2026-07-15] A momentum-style 30-day window
        (~22 trading rows) must be a cache HIT. The old `len(rows) >= 60` floor
        made it a permanent MISS -> ~500 redundant Kite calls per scan.
        """
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"RELIANCE": "123"}

        # Seed ~22 recent trading rows ending on to_date (as momentum's window has).
        await client._init_db()
        to_date = datetime(2025, 3, 6)
        from_date = to_date - timedelta(days=30)
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            d = from_date
            while d <= to_date:
                if d.weekday() < 5:  # weekdays only, ~22 rows
                    fetched = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    await db.execute(
                        "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                        ("RELIANCE", d.strftime("%Y-%m-%d"), 1000, 1010, 990, 1005, 500000, fetched)
                    )
                d += timedelta(days=1)
            await db.commit()

        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()
        client.client.get = mock_get

        df = await client.get_historical(
            "RELIANCE", from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d")
        )
        assert not api_called, "short-window momentum fetch should hit the cache, not the API"
        assert not df.empty

    @pytest.mark.asyncio
    async def test_long_window_refuses_truncated_cache(self, patch_settings):
        """A long (swing) window must NOT be served a momentum-truncated cache:
        ~22 rows cannot satisfy a ~250-day request, so it re-fetches.
        """
        client = KiteClient(patch_settings.DB_PATH)
        client.access_token = "tok"
        client.instrument_cache = {"RELIANCE": "123"}

        await client._init_db()
        to_date = datetime(2025, 3, 6)
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            for i in range(22):  # only 22 rows cached
                d = (to_date - timedelta(days=i)).strftime("%Y-%m-%d")
                fetched = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                await db.execute(
                    "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("RELIANCE", d, 1000, 1010, 990, 1005, 500000, fetched)
                )
            await db.commit()

        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            raise ValueError("stop after confirming API was hit")
        client.client.get = mock_get

        # ~250-day window needs ~178 trading rows; a 22-row cache must miss.
        from_date = (to_date - timedelta(days=250)).strftime("%Y-%m-%d")
        try:
            await client.get_historical("RELIANCE", from_date, to_date.strftime("%Y-%m-%d"))
        except ValueError:
            pass
        assert api_called, "long-window swing fetch must re-fetch, not serve a truncated cache"

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


# ---------------------------------------------------------------------
# KiteClient - get_intraday + intraday_cache (Q7)
# ---------------------------------------------------------------------

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
                    "INSERT INTO intraday_cache (ticker, interval, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    ("TCS", "15minute", dt, 3000+i, 3010+i, 2990+i, 3005+i, 100000, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
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


# ---------------------------------------------------------------------
# Q7: ohlcv_cache and intraday_cache are separate tables
# ---------------------------------------------------------------------

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
        """Intraday identity includes interval, so resolutions can coexist."""
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

            # Same interval + timestamp replaces, while another interval at the
            # same timestamp is an independent candle.
            await db.execute(
                "INSERT OR REPLACE INTO intraday_cache (ticker, interval, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("HDFC", "minute", "2025-01-01 09:15:00", 100, 110, 90, 105, 1000, "now")
            )
            await db.execute(
                "INSERT OR REPLACE INTO intraday_cache (ticker, interval, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("HDFC", "minute", "2025-01-01 09:15:00", 101, 111, 91, 106, 1001, "now2")
            )
            await db.execute(
                "INSERT INTO intraday_cache (ticker, interval, datetime, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("HDFC", "15minute", "2025-01-01 09:15:00", 99, 109, 89, 104, 5000, "now3")
            )
            await db.commit()
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache WHERE ticker='HDFC'")
            count = (await cursor.fetchone())[0]
            assert count == 2, "one row per (ticker, interval, datetime) expected"


class TestIntradayIntervalSafety:
    @pytest.mark.asyncio
    async def test_migrates_legacy_rows_conservatively_and_idempotently(
        self, patch_settings
    ):
        """Known minute groups are recovered; ambiguous bars are quarantined."""
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            await db.execute("""
                CREATE TABLE intraday_cache (
                    ticker TEXT, datetime TEXT, open REAL, high REAL, low REAL,
                    close REAL, volume REAL, fetched_at TIMESTAMP,
                    PRIMARY KEY (ticker, datetime)
                )
            """)
            rows = [
                # A non-quarter timestamp proves this whole ticker-day is minute.
                ("AAA", "2025-06-10 09:15:00", 1),
                ("AAA", "2025-06-10 09:16:00", 2),
                # Quarter-hour-only history cannot be labelled honestly.
                ("BBB", "2025-06-10 09:15:00", 3),
                ("BBB", "2025-06-10 09:30:00", 4),
            ]
            for ticker, dt, close in rows:
                await db.execute(
                    "INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?)",
                    (ticker, dt, close, close, close, close, 100, "now"),
                )
            await db.commit()

        client = KiteClient(patch_settings.DB_PATH)
        await client._init_intraday_db()
        await client._init_intraday_db()  # idempotence

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            info = await (await db.execute(
                "PRAGMA table_info(intraday_cache)"
            )).fetchall()
            migrated = await (await db.execute(
                "SELECT ticker, interval, datetime, close "
                "FROM intraday_cache ORDER BY ticker, datetime"
            )).fetchall()

        assert [row[1] for row in info] == [
            "ticker", "interval", "datetime", "open", "high", "low",
            "close", "volume", "fetched_at",
        ]
        assert [row[5] for row in info if row[5]] == [1, 2, 3]
        assert len(migrated) == 4
        assert {row[1] for row in migrated if row[0] == "AAA"} == {"minute"}
        assert {row[1] for row in migrated if row[0] == "BBB"} == {
            "legacy_unknown"
        }

    @pytest.mark.asyncio
    async def test_cache_reads_are_isolated_by_interval(self, patch_settings):
        client = KiteClient(patch_settings.DB_PATH)
        client.instrument_cache = {"AAA": 1}
        client.limiter = RateLimiter(rate=100.0, burst=10)
        await client._init_intraday_db()
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            for dt in ("09:30", "09:45", "10:00", "10:15"):
                await db.execute(
                    "INSERT INTO intraday_cache "
                    "(ticker, interval, datetime, open, high, low, close, volume) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    ("AAA", "15minute", f"2025-06-10 {dt}:00", 10, 11, 9, 10, 1),
                )
            await db.commit()

        requested_urls = []

        async def mock_get(url, **kwargs):
            requested_urls.append(url)
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": [
                [f"2025-06-10T10:{minute:02d}:00+0530", 20, 21, 19, 20, 2]
                for minute in (26, 27, 28, 29)
            ]}}
            return resp

        client.client.get = mock_get
        result = await client.get_intraday(
            "AAA", "2025-06-10 09:15:00", "2025-06-10 10:30:00",
            interval="minute",
        )

        assert requested_urls == ["/instruments/historical/1/minute"]
        assert list(result.index.minute) == [26, 27, 28, 29]
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            intervals = await (await db.execute(
                "SELECT interval, COUNT(*) FROM intraday_cache GROUP BY interval"
            )).fetchall()
        assert dict(intervals) == {"15minute": 4, "minute": 4}

    @pytest.mark.asyncio
    async def test_freshness_uses_requested_interval_width(self, patch_settings):
        client = KiteClient(patch_settings.DB_PATH)
        client.instrument_cache = {"AAA": 1}
        client.limiter = RateLimiter(rate=100.0, burst=10)
        await client._init_intraday_db()
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            for interval, times in {
                "15minute": ("09:30", "09:45", "10:00", "10:15"),
                "minute": ("10:25", "10:26", "10:27", "10:28"),
            }.items():
                for dt in times:
                    await db.execute(
                        "INSERT INTO intraday_cache "
                        "(ticker, interval, datetime, open, high, low, close, volume) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        ("AAA", interval, f"2025-06-10 {dt}:00", 10, 11, 9, 10, 1),
                    )
            await db.commit()

        calls = []

        async def mock_get(url, **kwargs):
            calls.append(url)
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": []}}
            return resp

        client.client.get = mock_get
        fifteen = await client.get_intraday(
            "AAA", "2025-06-10 09:15:00", "2025-06-10 10:30:00",
            interval="15minute",
        )
        minute = await client.get_intraday(
            "AAA", "2025-06-10 09:15:00", "2025-06-10 10:30:00",
            interval="minute",
        )

        assert len(fifteen) == 4
        assert minute.empty
        assert calls == ["/instruments/historical/1/minute"]


# ---------------------------------------------------------------------
# KiteClient - clear_intraday_cache
# ---------------------------------------------------------------------

class TestClearIntradayCache:
    """[INTRADAY-RETENTION 2026-08-04] This job used to delete everything older
    than yesterday, and that one line is why no intraday strategy in this
    system could ever be backtested: momentum and F&O trade intraday, and the
    only intraday history kept was three days. It now ages out on
    INTRADAY_RETENTION_DAYS instead.

    The tests below pin both halves: recent history must SURVIVE (the
    regression that mattered), and genuinely ancient rows must still go (or
    the disk guard is gone)."""

    @pytest.mark.asyncio
    async def test_recent_history_is_retained_not_purged(self, patch_settings):
        client = KiteClient(patch_settings.DB_PATH)
        await client._init_intraday_db()

        # Two days old: under any sane retention this is research data, and
        # under the old behaviour it was deleted overnight.
        old_dt = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d 10:00:00")
        recent_dt = datetime.utcnow().strftime("%Y-%m-%d 10:00:00")

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            for dt in (old_dt, recent_dt):
                await db.execute(
                    "INSERT INTO intraday_cache (ticker, datetime, open, high, "
                    "low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("RELIANCE", dt, 100, 110, 90, 105, 50000, "now"),
                )
            await db.commit()

        await client.clear_intraday_cache()

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache")
            count = (await cursor.fetchone())[0]
        assert count == 2, "recent intraday history must survive the nightly job"

    @pytest.mark.asyncio
    async def test_rows_past_the_retention_window_are_aged_out(self, patch_settings, monkeypatch):
        """Retention still bounds disk. Without this the table grows forever."""
        from config import settings as _s
        monkeypatch.setattr(_s, "INTRADAY_RETENTION_DAYS", 30, raising=False)

        client = KiteClient(patch_settings.DB_PATH)
        await client._init_intraday_db()

        ancient = (datetime.utcnow() - timedelta(days=400)).strftime("%Y-%m-%d 10:00:00")
        fresh = datetime.utcnow().strftime("%Y-%m-%d 10:00:00")
        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            for dt in (ancient, fresh):
                await db.execute(
                    "INSERT INTO intraday_cache (ticker, datetime, open, high, "
                    "low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                    ("RELIANCE", dt, 100, 110, 90, 105, 50000, "now"),
                )
            await db.commit()

        await client.clear_intraday_cache()

        async with aiosqlite.connect(patch_settings.DB_PATH) as db:
            cursor = await db.execute("SELECT datetime FROM intraday_cache")
            rows = [r[0] for r in await cursor.fetchall()]
        assert rows == [fresh], f"expected only the fresh row, got {rows}"


# ---------------------------------------------------------------------
# KiteClient - writes to correct cache table
# ---------------------------------------------------------------------

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
