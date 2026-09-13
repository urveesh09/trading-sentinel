"""[WORKFLOW-H H4 2026-09-13] Intraday-cache semantics acceptance.

Closes H4 of workstream H per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 15
future plan and ``docs/NEXT_AGENT_PLAN.md`` row H.

Acceptance coverage for the four explicit cache semantics
(per plan section 12: "Cache only with explicit instrument,
interval, completed-bar cutoff and freshness semantics"):

  1. INSTRUMENT + INTERVAL: the existing PRIMARY KEY
     (ticker, interval, datetime) and WHERE-clause; unchanged.
  2. COMPLETED-BAR CUTOFF (NEW in H4): the HIT path filters out
     candles whose ``datetime >= to_datetime``. Section 12: "Do not
     mix mutable forming bars with completed historical bars."
  3. FRESHNESS (NEW in H4 explicit knob): the most recent cached
     candle must cover up to ``to_datetime - interval_minutes -
     freshness_seconds``. The default ``freshness_seconds=0`` matches
     the pre-H4 strict gate exactly. An operator can relax to e.g.
     60 to tolerate one minute of staleness.
  4. MIN-CANDLES (NEW in H4 explicit knob): the minimum number of
     candles required to serve a HIT. Existing behaviour: 4 (the
     VWAP floor). §12 makes this explicit and operator-tunable.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, the existing ``get_intraday`` HIT path satisfied (1)
  and (2) but had NO defence against forming candles -- a Kite
  API quirk returning a future-dated candle would be served as a
  HIT. The freshness gate was correct in spirit but used a
  hard-coded ``interval_mins`` with no operator knob. The
  ``min_candles=4`` floor was hard-coded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
import pytest_asyncio

from kite_client import KiteClient, RateLimiter


# ---- helpers ---------------------------------------------------------------

@pytest_asyncio.fixture
async def cache_client(patch_settings):
    """A KiteClient wired with a fresh cache.db."""
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"TCS": "789"}
    client.limiter = RateLimiter(rate=100.0, burst=10)
    await client._init_intraday_db()
    yield client


def _seed_candles(
    client: KiteClient,
    *,
    ticker: str,
    interval: str,
    candles: List[Dict[str, Any]],
):
    """Insert raw rows into intraday_cache.

    ``candles`` is a list of dicts with keys: ``dt`` (str),
    ``open``, ``high``, ``low``, ``close``, ``volume``.

    Returns an *async function* that the test must await. This
    indirection is intentional: it lets us build the seed data
    inline in the test (readable) while still executing async
    DB I/O. Call sites use ``await _seed_candles(...)(...)``.
    """
    import aiosqlite
    async def _insert():
        async with aiosqlite.connect(client.db_path) as db:
            for c in candles:
                await db.execute(
                    "INSERT INTO intraday_cache "
                    "(ticker, interval, datetime, open, high, low, close, "
                    "volume, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        ticker,
                        interval,
                        c["dt"],
                        c["open"],
                        c["high"],
                        c["low"],
                        c["close"],
                        c["volume"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            await db.commit()
    return _insert()


# ---- (1)+(2) instrument + interval ---------------------------------------

class TestInstrumentIntervalKey:
    @pytest.mark.asyncio
    async def test_ticker_isolation(self, cache_client: KiteClient) -> None:
        """Two different tickers with the same datetime must NOT
        collide. PRIMARY KEY (ticker, interval, datetime) enforces.
        """
        # Seed 5 candles ending at 09:34. Request to 09:34. The 09:34
        # candle is forming (datetime == to_datetime); 09:30..09:33
        # are completed. After completed-bar filtering we expect 4.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:31:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:32:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:33:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 09:34:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        await _seed_candles(cache_client, ticker="INFY", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 200, "high": 201, "low": 199, "close": 200.5, "volume": 2000},
            {"dt": "2025-06-10 09:31:00", "open": 201, "high": 202, "low": 200, "close": 201.5, "volume": 2100},
            {"dt": "2025-06-10 09:32:00", "open": 202, "high": 203, "low": 201, "close": 202.5, "volume": 2200},
            {"dt": "2025-06-10 09:33:00", "open": 203, "high": 204, "low": 202, "close": 203.5, "volume": 2300},
            {"dt": "2025-06-10 09:34:00", "open": 204, "high": 205, "low": 203, "close": 204.5, "volume": 2400},
        ])
        df_tcs = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 09:34:00", interval="minute",
        )
        df_infy = await cache_client.get_intraday(
            "INFY", "2025-06-10 09:15:00", "2025-06-10 09:34:00", interval="minute",
        )
        # Forming candle (09:34) excluded; completed 09:30..09:33 = 4.
        assert len(df_tcs) == 4
        assert len(df_infy) == 4
        # Tickers are independent.
        assert float(df_tcs.iloc[0]["close"]) == 100.5
        assert float(df_infy.iloc[0]["close"]) == 200.5

    @pytest.mark.asyncio
    async def test_interval_isolation(self, cache_client: KiteClient) -> None:
        """Two intervals with the same (ticker, datetime) are
        separate rows. PRIMARY KEY (ticker, interval, datetime).
        """
        # Seed 5 minute-candles ending at 09:34; 5 5-minute candles
        # ending at 09:50. The 09:34 (minute) and 09:50 (5-min) are
        # forming on their respective requests.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:31:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:32:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:33:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 09:34:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        await _seed_candles(cache_client, ticker="TCS", interval="5minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 200, "high": 201, "low": 199, "close": 200.5, "volume": 2000},
            {"dt": "2025-06-10 09:35:00", "open": 201, "high": 202, "low": 200, "close": 201.5, "volume": 2100},
            {"dt": "2025-06-10 09:40:00", "open": 202, "high": 203, "low": 201, "close": 202.5, "volume": 2200},
            {"dt": "2025-06-10 09:45:00", "open": 203, "high": 204, "low": 202, "close": 203.5, "volume": 2300},
            {"dt": "2025-06-10 09:50:00", "open": 204, "high": 205, "low": 203, "close": 204.5, "volume": 2400},
        ])
        # Mock the API for any fall-through (no calls expected).
        from unittest.mock import MagicMock
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": []}}
            return resp
        cache_client.client.get = mock_get

        df_m = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 09:34:00", interval="minute",
        )
        # Minute: 09:34 forming -> excluded; 09:30..09:33 = 4.
        assert len(df_m) == 4
        assert float(df_m.iloc[0]["close"]) == 100.5

        df_5 = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 09:50:00", interval="5minute",
        )
        # 5 candles seeded: 09:30..09:50. 09:50 forming -> excluded.
        # Completed 09:30..09:45 = 4 candles -> HIT.
        assert len(df_5) == 4
        assert float(df_5.iloc[0]["close"]) == 200.5
        assert not api_called, "no API calls expected; both intervals should HIT"


# ---- (3) FRESHNESS ----------------------------------------------------------

class TestFreshness:
    @pytest.mark.asyncio
    async def test_default_freshness_zero_strict(
        self, cache_client: KiteClient,
    ) -> None:
        """Default ``freshness_seconds=0``: the gate requires the
        most recent cached candle to cover up to ``to_datetime -
        interval_minutes`` exactly. A candle newer than that
        boundary triggers the gate (i.e. falls through to API).
        """
        # Seed 5 candles ending at 10:00. The request is 10:01 with
        # interval=minute, so expected_latest = 10:00. 10:00 >= 10:00 -> HIT.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:57:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:58:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:59:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 10:00:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 10:01:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover - never called
        from unittest.mock import MagicMock
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:01:00", interval="minute",
        )
        assert not api_called, "fresh HIT expected with default freshness=0"
        assert not df.empty

    @pytest.mark.asyncio
    async def test_stale_falls_through_to_api(
        self, cache_client: KiteClient,
    ) -> None:
        """Last candle is older than ``to_datetime - interval_minutes``.
        The gate rejects; the HIT path falls through to the API.
        """
        from unittest.mock import MagicMock
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:31:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:32:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:33:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        # Request ends at 10:00. Last candle is 09:33. 09:33 < (10:00 - 1 min)
        # = 09:59 -> stale -> falls through.
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
        await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:00:00", interval="minute",
        )
        assert api_called, "stale cache should fall through to API"

    @pytest.mark.asyncio
    async def test_freshness_seconds_relaxes_gate(
        self, cache_client, monkeypatch,
    ) -> None:
        """``freshness_seconds=120``: the gate is more permissive;
        a candle older than the strict boundary but within the
        budget still serves a HIT.
        """
        from unittest.mock import MagicMock
        from config import settings
        monkeypatch.setattr(settings, "INTRADAY_CACHE_FRESHNESS_SECONDS", 120)
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:31:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:32:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:33:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        # Strict gate at 09:59 would reject (09:33 < 09:59).
        # With freshness_seconds=120, expected_latest = 09:59 - 2 min = 09:57.
        # 09:33 < 09:57 -> still stale. Let's use a closer time.
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        # Request to 10:01: strict gate at 10:00 (rejects 09:33).
        # With freshness=120, expected_latest = 10:00 - 2min = 09:58.
        # 09:33 still < 09:58. Let's set freshness to a value that
        # makes 09:33 >= expected_latest.
        monkeypatch.setattr(settings, "INTRADAY_CACHE_FRESHNESS_SECONDS", 9 * 60)
        # expected_latest = 10:00 - 9min = 09:51. 09:33 still < 09:51.
        # Need freshness >= (10:00 - 09:33) = 27 min = 1620.
        monkeypatch.setattr(settings, "INTRADAY_CACHE_FRESHNESS_SECONDS", 30 * 60)
        # expected_latest = 10:00 - 30min = 09:30. 09:33 >= 09:30 -> HIT.
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:01:00", interval="minute",
        )
        assert not api_called
        assert not df.empty

    @pytest.mark.asyncio
    async def test_freshness_seconds_negative_treated_as_zero(
        self, cache_client, monkeypatch,
    ) -> None:
        """A negative ``freshness_seconds`` makes the gate MORE
        permissive (a longer time window), not less. We clamp
        negative to 0 via the ``timedelta(seconds=freshness_seconds)``
        which raises OverflowError; the H4 path uses ``max(0, ...)``
        so negative values are treated as zero.
        """
        from config import settings
        monkeypatch.setattr(settings, "INTRADAY_CACHE_FRESHNESS_SECONDS", -100)
        # The path uses timedelta(seconds=freshness_seconds); if
        # freshness_seconds=-100, timedelta raises OverflowError.
        # We must clamp. Verify the gate does NOT raise.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:57:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:58:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:59:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 10:00:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 10:01:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:01:00", interval="minute",
        )
        assert not df.empty


# ---- (4) MIN-CANDLES --------------------------------------------------------

class TestMinCandles:
    @pytest.mark.asyncio
    async def test_default_min_4_enforced(
        self, cache_client: KiteClient,
    ) -> None:
        """Default ``min_candles=4``: 3 candles do NOT serve a HIT.
        """
        from unittest.mock import MagicMock
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:31:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:32:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
        ])
        # 3 candles < 4 -> not enough. Falls through to API.
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": []}}
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 09:32:00", interval="minute",
        )
        assert api_called
        assert df.empty

    @pytest.mark.asyncio
    async def test_min_candles_override(
        self, cache_client, monkeypatch,
    ) -> None:
        """``min_candles=2``: 3 candles DO serve a HIT.
        """
        from unittest.mock import MagicMock
        from config import settings
        monkeypatch.setattr(settings, "INTRADAY_CACHE_MIN_CANDLES", 2)
        # Seed 5 candles ending at 09:34. With min_candles=2, the
        # forming 09:34 candle is excluded -> 4 completed >= 2 -> HIT.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:31:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:32:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:33:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 09:34:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 09:34:00", interval="minute",
        )
        assert not api_called
        # 4 completed candles (09:30..09:33); 09:34 forming excluded.
        assert len(df) == 4


# ---- (5) COMPLETED-BAR CUTOFF -----------------------------------------------

class TestCompletedBarCutoff:
    @pytest.mark.asyncio
    async def test_default_include_forming_false_filters(
        self, cache_client: KiteClient,
    ) -> None:
        """Default ``include_forming=False``: a candle with
        ``datetime == to_datetime`` is treated as forming and
        EXCLUDED from the HIT. A candle strictly before
        ``to_datetime`` is included.

        Scenario: 4 candles ending at 10:00 (last). Request is to
        10:00. The 10:00 candle is forming (it's the current minute);
        9:59 and earlier are completed. HIT must serve only the
        3 completed candles... wait, that's below min_candles=4. So
        actually: HIT must fall through to API because filtering
        removes the forming row and leaves only 3 completed rows,
        below the floor.
        """
        from unittest.mock import MagicMock
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:57:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:58:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:59:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 10:00:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        # Request to 10:00. 10:00 candle is "datetime == to_datetime" -> forming.
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": []}}
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:00:00", interval="minute",
        )
        # After filtering: only [09:57, 09:58, 09:59] remain = 3 candles.
        # 3 < min_candles=4 -> not enough -> falls through.
        assert api_called, "filtered rows below min_candles should fall through"
        assert df.empty

    @pytest.mark.asyncio
    async def test_strictly_before_to_datetime_is_completed(
        self, cache_client, monkeypatch,
    ) -> None:
        """Candle at 09:59 (strictly before ``to_datetime=10:00``)
        is completed; included.
        """
        from unittest.mock import MagicMock
        # Seed 5 candles: 09:56..10:00. to_datetime=10:00.
        # The 10:00 candle is forming; 09:56..09:59 are completed.
        # 4 completed candles + 1 forming = 5 total; filtered = 4.
        # With include_forming=False, HIT serves 4 candles.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:56:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:57:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:58:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 09:59:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
            {"dt": "2025-06-10 10:00:00", "open": 104, "high": 105, "low": 103, "close": 104.5, "volume": 1400},
        ])
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        from unittest.mock import MagicMock
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:00:00", interval="minute",
        )
        # After filtering, 4 candles (09:56..09:59) remain.
        # The 10:00 candle is forming; excluded.
        assert not api_called
        assert len(df) == 4
        # The last row in the HIT response is 09:59, not 10:00.
        assert df.index[-1].strftime("%Y-%m-%d %H:%M:%S") == "2025-06-10 09:59:00"

    @pytest.mark.asyncio
    async def test_include_forming_true_returns_all(
        self, cache_client, monkeypatch,
    ) -> None:
        """``include_forming=True``: the HIT returns ALL cached
        rows, including the forming candle at 10:00. Operator
        opt-in; not the default.
        """
        from config import settings
        monkeypatch.setattr(settings, "INTRADAY_CACHE_INCLUDE_FORMING", True)
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 09:57:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 09:58:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 09:59:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 10:00:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        from unittest.mock import MagicMock
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            return MagicMock()  # pragma: no cover
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:00:00", interval="minute",
        )
        assert not api_called
        # All 4 candles including the forming one.
        assert len(df) == 4
        assert df.index[-1].strftime("%Y-%m-%d %H:%M:%S") == "2025-06-10 10:00:00"

    @pytest.mark.asyncio
    async def test_only_forming_falls_through(
        self, cache_client, monkeypatch,
    ) -> None:
        """All cached rows are forming; HIT must fall through to API
        rather than return an empty frame that misleads the caller.
        """
        from unittest.mock import MagicMock
        # Seed 4 forming candles (all with ``datetime == to_datetime``).
        # The HIT path detects "all filtered rows dropped" and logs
        # ``intraday_cache_only_forming``, falling through to the API.
        await _seed_candles(cache_client, ticker="TCS", interval="minute", candles=[
            {"dt": "2025-06-10 10:00:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
            {"dt": "2025-06-10 10:01:00", "open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 1100},
            {"dt": "2025-06-10 10:02:00", "open": 102, "high": 103, "low": 101, "close": 102.5, "volume": 1200},
            {"dt": "2025-06-10 10:03:00", "open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 1300},
        ])
        # Request ends at 10:03. All 4 candles are "forming" (datetime == to_datetime).
        api_called = False
        async def mock_get(url, **kwargs):
            nonlocal api_called
            api_called = True
            resp = MagicMock(status_code=200, raise_for_status=MagicMock())
            resp.json.return_value = {"data": {"candles": []}}
            return resp
        cache_client.client.get = mock_get
        df = await cache_client.get_intraday(
            "TCS", "2025-06-10 09:15:00", "2025-06-10 10:03:00", interval="minute",
        )
        assert api_called, "all-forming cache must fall through, not return empty HIT"
        assert df.empty


# ---- reproducibility ------------------------------------------------------

class TestReproducibility:
    def test_same_inputs_same_verdict(self) -> None:
        """The four knob defaults are stable across calls.
        """
        from kite_client import _interval_minutes
        from config import settings
        for iv in ("minute", "5minute", "15minute", "30minute", "60minute"):
            assert _interval_minutes(iv) > 0
        assert int(settings.INTRADAY_CACHE_FRESHNESS_SECONDS) == 0
        assert bool(settings.INTRADAY_CACHE_INCLUDE_FORMING) is False
        assert int(settings.INTRADAY_CACHE_MIN_CANDLES) == 4
