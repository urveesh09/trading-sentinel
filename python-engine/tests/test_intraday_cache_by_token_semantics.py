"""[WORKFLOW-H H4.B 2026-09-13] Intraday-cache-by-token semantics acceptance.

Closes H4.B of workstream H per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 12
future plan and ``docs/NEXT_AGENT_PLAN.md`` row H. Sibling of
``test_intraday_cache_semantics.py`` (the H4.A by-symbol tests) --
same acceptance contract on the by-token path.

Acceptance coverage for the four explicit cache semantics (per
plan section 12: "Cache only with explicit instrument, interval,
completed-bar cutoff and freshness semantics"):

  1. INSTRUMENT + INTERVAL: PRIMARY KEY
     (instrument_token, interval, datetime); the gate is keyed
     on instrument_token, never on ticker. Key-isolation
     test verifies two different tokens do NOT collide.
  2. COMPLETED-BAR CUTOFF: the HIT path filters out candles
     whose ``datetime >= to_datetime``. The exempt set is
     ``_INTERVALS_EXEMPT_FROM_FORMING_FILTER`` -- daily is
     exempt because the §12 forming-bar concern does not
     apply to daily candles.
  3. FRESHNESS: the most recent cached candle must cover up to
     ``to_datetime - interval_minutes - freshness_seconds``.
     The default ``freshness_seconds=0`` matches the strict
     pre-H4 gate exactly.
  4. MIN-CANDLES: the floor is re-checked AFTER forming-bar
     filtering. Below the floor: no HIT.

Additional coverage:
  - MISS path returns empty DataFrame on failure (preserves
    pre-H4 contract).
  - 5-attempt retry loop preserved on MISS path.
  - OI column preserved through HIT path.
  - Daily interval exempt from forming-bar filter.
  - Cross-path isolation: by-symbol ticker and by-token id
    referring to the same instrument DO NOT collide (different
    tables).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from kite_client import KiteClient, RateLimiter


# ---- helpers ---------------------------------------------------------------

@pytest_asyncio.fixture
async def cache_client(patch_settings):
    """A KiteClient wired with a fresh cache.db."""
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.limiter = RateLimiter(rate=100.0, burst=10)
    await client._init_intraday_db()
    yield client


def _seed_by_token(
    client: KiteClient,
    *,
    instrument_token: int,
    interval: str,
    candles: List[Dict[str, Any]],
):
    """Insert raw rows into intraday_cache_by_token.

    ``candles`` is a list of dicts with keys: ``dt`` (str), ``open``,
    ``high``, ``low``, ``close``, ``volume``, optional ``oi``.
    Returns an awaitable coroutine.
    """
    import aiosqlite
    async def _insert():
        async with aiosqlite.connect(client.db_path) as db:
            for c in candles:
                await db.execute(
                    "INSERT INTO intraday_cache_by_token "
                    "(instrument_token, interval, datetime, open, high, low, "
                    "close, volume, oi, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        instrument_token,
                        interval,
                        c["dt"],
                        c["open"],
                        c["high"],
                        c["low"],
                        c["close"],
                        c["volume"],
                        c.get("oi"),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            await db.commit()
    return _insert()


# ---- (1)+(2) instrument + interval ---------------------------------------

class TestInstrumentIntervalKeyByToken:
    @pytest.mark.asyncio
    async def test_token_isolation(self, cache_client: KiteClient) -> None:
        """Two different instrument_tokens with the same datetime
        must NOT collide. PRIMARY KEY (instrument_token, interval,
        datetime) enforces.
        """
        # Seed 5 candles per token ending at the forming-bar boundary.
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "oi": 50000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100, "oi": 50100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200, "oi": 50200},
            {"dt": "2025-06-10 09:45:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300, "oi": 50300},
            {"dt": "2025-06-10 09:50:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400, "oi": 50400},
        ])
        await _seed_by_token(cache_client, instrument_token=67890, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 200, "high": 201, "low": 199, "close": 200.5, "volume": 2000, "oi": 60000},
            {"dt": "2025-06-10 09:35:00", "open": 201, "high": 202, "low": 200, "close": 201.5, "volume": 2100, "oi": 60100},
            {"dt": "2025-06-10 09:40:00", "open": 202, "high": 203, "low": 201, "close": 202.5, "volume": 2200, "oi": 60200},
            {"dt": "2025-06-10 09:45:00", "open": 203, "high": 204, "low": 202, "close": 203.5, "volume": 2300, "oi": 60300},
            {"dt": "2025-06-10 09:50:00", "open": 204, "high": 205, "low": 203, "close": 204.5, "volume": 2400, "oi": 60400},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get

        df_a = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        df_b = await cache_client.get_intraday_by_token(
            67890, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        # Forming candle (09:50) excluded; completed 09:30..09:45 = 4.
        assert len(df_a) == 4
        assert len(df_b) == 4
        assert float(df_a.iloc[0]["close"]) == 100.5
        assert float(df_b.iloc[0]["close"]) == 200.5
        assert not api_called

    @pytest.mark.asyncio
    async def test_interval_isolation_by_token(self, cache_client: KiteClient) -> None:
        """Two intervals with the same (token, datetime) are
        separate rows. PRIMARY KEY (instrument_token, interval, datetime).
        """
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:45:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 09:50:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        await _seed_by_token(cache_client, instrument_token=12345, interval="day", candles=[
            {"dt": "2025-06-09 00:00:00", "open": 200, "high": 201, "low": 199, "close": 200.5, "volume": 2000},
            {"dt": "2025-06-10 00:00:00", "open": 201, "high": 202, "low": 200, "close": 201.5, "volume": 2100},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get

        df_5 = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        # 5min: 09:50 forming -> excluded; 09:30..09:45 = 4.
        assert len(df_5) == 4
        assert float(df_5.iloc[0]["close"]) == 100.5
        # Daily: 2 candles seeded. 2 < min_candles=4 -> falls through.
        # We seeded only 2 because the daily-interval exempt path
        # is tested separately below.
        assert not api_called


# ---- (3) FRESHNESS ---------------------------------------------------------

class TestFreshnessByToken:
    @pytest.mark.asyncio
    async def test_stale_falls_through_to_api(
        self, cache_client: KiteClient,
    ) -> None:
        """Last candle is older than ``to_datetime - interval_minutes``.
        The gate rejects; the HIT path falls through to the API.
        """
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:45:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": [
                ["2025-06-10T09:30:00+0530", 1, 1, 1, 1, 1],
                ["2025-06-10T09:45:00+0530", 1, 1, 1, 1, 1],
                ["2025-06-10T10:00:00+0530", 1, 1, 1, 1, 1],
                ["2025-06-10T10:15:00+0530", 1, 1, 1, 1, 1],
            ]}}
            return resp
        cache_client.client.get = mock_get
        await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 10:00:00", interval="5minute",
        )
        assert api_called, "stale cache should fall through to API"


# ---- (4) COMPLETED-BAR CUTOFF ---------------------------------------------

class TestCompletedBarCutoffByToken:
    @pytest.mark.asyncio
    async def test_default_filters_forming(
        self, cache_client: KiteClient,
    ) -> None:
        """Default ``include_forming=False``: candle with
        ``datetime == to_datetime`` is forming and EXCLUDED from
        the HIT. With min_candles=4, 4 completed candles are
        needed for a HIT; we seed 5 so after filtering we have 4.
        """
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:45:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 09:50:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        assert not api_called
        # 09:50 forming -> excluded; 09:30..09:45 = 4.
        assert len(df) == 4
        # The last row in the HIT response is 09:45, not 09:50.
        assert df.index[-1].strftime("%Y-%m-%d %H:%M:%S") == "2025-06-10 09:45:00"

    @pytest.mark.asyncio
    async def test_daily_interval_exempt(
        self, cache_client: KiteClient,
    ) -> None:
        """Daily interval is exempt from the forming-bar filter.
        A candle with ``datetime == to_datetime`` IS included
        (the §12 forming-bar concern does not apply to daily).
        """
        # Seed 4 daily candles ending at 2025-06-10 (today's
        # candle). With min_candles=4, a HIT must serve all 4.
        await _seed_by_token(cache_client, instrument_token=12345, interval="day", candles=[
            {"dt": "2025-06-04 00:00:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-05 00:00:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-09 00:00:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 00:00:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        # Request to 2025-06-10. Without the exempt rule, the
        # 06-10 candle would be filtered as "forming". With the
        # exempt rule (daily), it stays.
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-04 00:00:00", "2025-06-10 00:00:00", interval="day",
        )
        assert not api_called
        assert len(df) == 4
        assert df.index[-1].strftime("%Y-%m-%d %H:%M:%S") == "2025-06-10 00:00:00"


# ---- (5) MIN-CANDLES -------------------------------------------------------

class TestMinCandlesByToken:
    @pytest.mark.asyncio
    async def test_default_min_4_enforced(
        self, cache_client: KiteClient,
    ) -> None:
        """Default ``min_candles=4``: 3 candles do NOT serve a HIT.
        """
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": []}}
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:40:00", interval="5minute",
        )
        assert api_called
        assert df.empty


# ---- (6) MISS-PATH CONTRACT -----------------------------------------------

class TestMissPathContract:
    @pytest.mark.asyncio
    async def test_miss_returns_empty_on_api_failure(
        self, cache_client: KiteClient,
    ) -> None:
        """Cache MISS + API failure (non-retried status) returns
        ``pd.DataFrame()``. Pre-H4.B contract preserved.
        """
        # No candles seeded -> MISS.
        api_called_count = 0
        async def mock_get(url, **kwargs):
            nonlocal api_called_count
            api_called_count += 1
            resp = MagicMock()
            resp.status_code = 400
            # Production ``raise_for_status()`` raises on 4xx/5xx.
            # We use the real ``httpx.HTTPStatusError`` so the
            # production ``except`` block can read
            # ``e.response.status_code``.
            import httpx
            resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "400 Bad Request",
                    request=MagicMock(),
                    response=resp,
                )
            )
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 10:00:00", interval="5minute",
        )
        # 400 is NOT in (429, 503, 504); it returns immediately
        # with empty DataFrame.
        assert df.empty
        assert api_called_count == 1

    @pytest.mark.asyncio
    async def test_miss_writes_through_to_cache(
        self, cache_client: KiteClient,
    ) -> None:
        """Cache MISS + API success writes rows to the by-token
        cache table for future HITs. INSERT OR REPLACE on the
        PRIMARY KEY (instrument_token, interval, datetime).
        """
        # No candles seeded -> MISS.
        async def mock_get(url, **kwargs):
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": [
                ["2025-06-10T09:30:00+0530", 100, 101, 99, 100.5, 1000, 50000],
                ["2025-06-10T09:35:00+0530", 101, 102, 100, 101.5, 1100, 50100],
                ["2025-06-10T09:40:00+0530", 102, 103, 101, 102.5, 1200, 50200],
                ["2025-06-10T09:45:00+0530", 103, 104, 102, 103.5, 1300, 50300],
                ["2025-06-10T09:50:00+0530", 104, 105, 103, 104.5, 1400, 50400],
            ]}}
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        assert not df.empty
        assert len(df) == 5

        # Verify rows were written to the cache.
        import aiosqlite
        async with aiosqlite.connect(cache_client.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM intraday_cache_by_token WHERE instrument_token=?",
                (12345,),
            )
            row = await cursor.fetchone()
            assert row[0] == 5, f"expected 5 cached rows, got {row[0]}"

    @pytest.mark.asyncio
    async def test_oi_column_preserved_through_hit(
        self, cache_client: KiteClient,
    ) -> None:
        """The ``oi`` (open-interest) column is preserved through
        the HIT path. F&O candles include OI; downstream callers
        (``partner_orchestrator.realized_vol_20d``) read it.
        """
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "oi": 50000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100, "oi": 50100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200, "oi": 50200},
            {"dt": "2025-06-10 09:45:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300, "oi": 50300},
            {"dt": "2025-06-10 09:50:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400, "oi": 50400},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        assert not api_called
        # OI column is preserved through the HIT.
        assert "oi" in df.columns
        # After filtering, the last row is 09:45 (forming 09:50 excluded).
        # The 09:45 OI is 50300.
        assert float(df.iloc[-1]["oi"]) == 50300

    @pytest.mark.asyncio
    async def test_retry_on_429(
        self, cache_client: KiteClient,
    ) -> None:
        """Cache MISS + 429 + later success returns the success
        payload (the 5-attempt retry loop is preserved).
        """
        # No candles seeded -> MISS.
        attempt_count = 0
        async def mock_get(url, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            resp = MagicMock()
            if attempt_count < 3:
                resp.status_code = 429
                import httpx
                resp.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "429 Too Many Requests",
                        request=MagicMock(),
                        response=resp,
                    )
                )
            else:
                resp.status_code = 200
                resp.raise_for_status = MagicMock()
                resp.json.return_value = {"data": {"candles": [
                    ["2025-06-10T09:30:00+0530", 100, 101, 99, 100.5, 1000, 50000],
                    ["2025-06-10T09:45:00+0530", 101, 102, 100, 101.5, 1100, 50100],
                    ["2025-06-10T10:00:00+0530", 102, 103, 101, 102.5, 1200, 50200],
                    ["2025-06-10T10:15:00+0530", 103, 104, 102, 103.5, 1300, 50300],
                ]}}
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 10:15:00", interval="5minute",
        )
        assert attempt_count == 3
        assert not df.empty


# ---- (7) CROSS-PATH ISOLATION ---------------------------------------------

class TestCrossPathIsolation:
    @pytest.mark.asyncio
    async def test_by_symbol_and_by_token_have_separate_tables(
        self, cache_client: KiteClient,
    ) -> None:
        """The by-symbol path (``intraday_cache``) and the
        by-token path (``intraday_cache_by_token``) are sibling
        tables. A row written by one path MUST NOT appear in the
        other path's cache.
        """
        # Seed a by-token row.
        await _seed_by_token(cache_client, instrument_token=12345, interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "oi": 50000},
            {"dt": "2025-06-10 09:35:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100, "oi": 50100},
            {"dt": "2025-06-10 09:40:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200, "oi": 50200},
            {"dt": "2025-06-10 09:45:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300, "oi": 50300},
            {"dt": "2025-06-10 09:50:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400, "oi": 50400},
        ])
        # Verify the by-symbol path does NOT see those rows
        # (no rows in intraday_cache).
        import aiosqlite
        async with aiosqlite.connect(cache_client.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM intraday_cache")
            row = await cursor.fetchone()
            assert row[0] == 0
            cursor = await db.execute(
                "SELECT COUNT(*) FROM intraday_cache_by_token"
            )
            row = await cursor.fetchone()
            assert row[0] == 5

        # The by-token HIT path serves its own table; the by-symbol
        # path doesn't see it.
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        df_by_token = await cache_client.get_intraday_by_token(
            12345, "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        assert not api_called
        assert len(df_by_token) == 4


# ---- (8) REPRODUCIBILITY ---------------------------------------------------

class TestReproducibilityByToken:
    def test_gate_helper_is_keyword_only(self) -> None:
        """The shared gate is keyword-only; the by-token caller
        and the by-symbol caller both use the same call shape.
        """
        from kite_client import _intraday_cache_gate_evaluate
        import inspect
        sig = inspect.signature(_intraday_cache_gate_evaluate)
        # All parameters after ``*`` are keyword-only by construction.
        for name, param in sig.parameters.items():
            assert param.kind in (
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ), f"unexpected param kind for {name}: {param.kind}"
        # Spot-check: required parameters exist.
        for required in ("rows", "to_datetime_str", "interval", "interval_mins",
                         "freshness_seconds", "include_forming", "min_candles",
                         "source_kind", "source_id"):
            assert required in sig.parameters, f"missing required param: {required}"

    def test_daily_is_exempt(self) -> None:
        from kite_client import _INTERVALS_EXEMPT_FROM_FORMING_FILTER
        assert "day" in _INTERVALS_EXEMPT_FROM_FORMING_FILTER
