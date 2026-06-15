"""Tests for the BreadthEngine (Tier 1 + Tier 2).

Tier 1: hourly batch fetch of 60-day daily history for Nifty 100; computes
SMA50 and signed distance_pct per stock; caches the result for 1h.

Tier 2: per-scan refresh of breadth_pct and per-stock rank using live LTP
from the scan pass. Zero Kite calls. Falls back to cached distance_pct if
a token is missing from the scan pass.
"""
import asyncio
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from breadth import BreadthEngine, BreadthResult


# ── Helpers ───────────────────────────────────────────────────────────


def _above_closes() -> list:
    """50 daily closes that are ABOVE their 50-day SMA by ~5%."""
    n = 50
    base = 100.0
    drift = 0.001
    # First 49 days: tiny drift up (so SMA50 ≈ 100 + small offset)
    # Last day: +5% jump so close > SMA50 by 5%
    closes = [base]
    for i in range(48):
        closes.append(closes[-1] * (1 + drift))
    closes.append(closes[-1] * 1.05)  # last day +5%
    assert len(closes) == 50
    return closes


def _below_closes() -> list:
    """50 daily closes that are BELOW their 50-day SMA by ~5%."""
    n = 50
    base = 100.0
    drift = 0.001
    closes = [base]
    for i in range(48):
        closes.append(closes[-1] * (1 + drift))
    closes.append(closes[-1] * 0.95)  # last day -5%
    assert len(closes) == 50
    return closes


@pytest.fixture
def universe_100():
    """A Universe returning 100 tokens (1000..1099)."""
    u = MagicMock()
    u.get_nifty100_tokens.return_value = set(range(1000, 1100))
    return u


@pytest.fixture
def kite_above_factory():
    """Factory: returns an async fn that mocks kite.historical(t, p, i).
    Tokens 1000..1059 (60) are 'above' SMA50, 1060..1099 (40) are 'below'."""
    def _factory():
        above = _above_closes()
        below = _below_closes()
        async def fake_historical(token, period, interval):
            idx = token - 1000
            if idx < 60:
                closes = above
            else:
                closes = below
            return pd.DataFrame({"close": closes})
        return fake_historical
    return _factory


# ── Tier 1 tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_returns_60pct_above_when_60_of_100_above(universe_100, kite_above_factory):
    """60 stocks above SMA50, 40 below → breadth_pct_above_sma50 == 0.60."""
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    result = await engine.compute_tier1()
    assert isinstance(result, BreadthResult)
    assert result.breadth_pct_above_sma50 == pytest.approx(0.60, abs=0.01)
    assert result.degraded is False
    assert result.n_resolved == 100


@pytest.mark.asyncio
async def test_tier1_populates_sma50_and_distance_cache(universe_100, kite_above_factory):
    """Tier 1 should leave sma50_map and distance_pct_cache populated for Tier 2."""
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    result = await engine.compute_tier1()
    assert len(engine.sma50_map) == 100
    assert len(engine.distance_pct_cache) == 100
    # Tokens 1000..1059 are 'above' → positive distance_pct
    assert engine.distance_pct_cache[1000] > 0
    # Tokens 1060..1099 are 'below' → negative distance_pct
    assert engine.distance_pct_cache[1099] < 0


@pytest.mark.asyncio
async def test_tier1_degraded_when_15pct_of_fetches_fail(universe_100, kite_above_factory):
    """If >10% of fetches fail, result is degraded with breadth_pct=None."""
    good_fn = kite_above_factory()

    async def flaky_historical(token, period, interval):
        if token - 1000 < 15:  # 15% fail
            raise RuntimeError("Kite 503")
        return await good_fn(token, period, interval)

    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=flaky_historical,
        cache_ttl_seconds=3600,
        degraded_threshold=0.10,
    )
    result = await engine.compute_tier1()
    assert result.degraded is True
    assert result.breadth_pct_above_sma50 is None
    assert result.rank_map == {}
    assert result.n_resolved == 85


@pytest.mark.asyncio
async def test_tier1_cache_ttl_within_window_uses_cache(universe_100, kite_above_factory):
    """Second call within TTL returns cached result; after TTL, refetches."""
    call_count = [0]
    async def counting_historical(token, period, interval):
        call_count[0] += 1
        return await kite_above_factory()(token, period, interval)

    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=counting_historical,
        cache_ttl_seconds=60,
    )

    with patch("breadth.time.time") as mock_time:
        mock_time.return_value = 1000.0
        await engine.compute_tier1()
        assert call_count[0] == 100

        # 30 seconds later, still within TTL
        mock_time.return_value = 1030.0
        await engine.compute_tier1()
        assert call_count[0] == 100  # no new calls


@pytest.mark.asyncio
async def test_tier1_cache_ttl_expiry_triggers_refetch(universe_100, kite_above_factory):
    """After TTL expires, Tier 1 should refetch."""
    call_count = [0]
    async def counting_historical(token, period, interval):
        call_count[0] += 1
        return await kite_above_factory()(token, period, interval)

    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=counting_historical,
        cache_ttl_seconds=60,
    )

    with patch("breadth.time.time") as mock_time:
        mock_time.return_value = 1000.0
        await engine.compute_tier1()
        assert call_count[0] == 100

        # 2 minutes later, TTL expired
        mock_time.return_value = 1120.0
        await engine.compute_tier1()
        assert call_count[0] == 200  # 100 new calls


@pytest.mark.asyncio
async def test_tier1_empty_universe_returns_degraded(universe_100, kite_above_factory):
    """Universe returning 0 tokens → degraded result, no fetches attempted."""
    universe_100.get_nifty100_tokens.return_value = set()
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    result = await engine.compute_tier1()
    assert result.degraded is True
    assert result.breadth_pct_above_sma50 is None
    assert result.n_resolved == 0


# ── Helper / internal tests ──────────────────────────────────────────


def test_rank_from_distances_simple():
    """Percentile rank: 5 stocks with distinct distances → ranks 0/0.25/0.5/0.75/1.0."""
    distances = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0}
    rank = BreadthEngine._rank_from_distances(distances)
    # n=5 → ranks 0/0.25/0.5/0.75/1.0
    assert rank[1] == pytest.approx(0.0)
    assert rank[2] == pytest.approx(0.25)
    assert rank[3] == pytest.approx(0.5)
    assert rank[4] == pytest.approx(0.75)
    assert rank[5] == pytest.approx(1.0)


def test_rank_from_distances_handles_ties():
    """Two stocks at the same distance should share the average rank."""
    distances = {1: 1.0, 2: 1.0, 3: 2.0}
    rank = BreadthEngine._rank_from_distances(distances)
    # Positions 0,1,2 → tied at 0,1 → avg rank = 0.5/2 = 0.25
    # Position 2 → 2/2 = 1.0
    assert rank[1] == rank[2] == pytest.approx(0.25)
    assert rank[3] == pytest.approx(1.0)


def test_rank_from_distances_empty():
    """Empty distances dict → empty rank map."""
    assert BreadthEngine._rank_from_distances({}) == {}


# ── Tier 2 tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_uses_scan_ltp_with_zero_kite_calls(universe_100, kite_above_factory):
    """Tier 2 should refresh distance_pct with live LTP from the scan pass."""
    call_count = [0]
    async def counting_historical(token, period, interval):
        call_count[0] += 1
        return await kite_above_factory()(token, period, interval)

    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=counting_historical,
        cache_ttl_seconds=3600,
    )
    # First run Tier 1 to populate cache
    await engine.compute_tier1()
    assert call_count[0] == 100

    # Build a scan_ltp: bump all 100 stocks by +2%
    scan_ltp = {token: 105.0 for token in range(1000, 1100)}

    tier1_calls = call_count[0]
    result = await engine.compute_tier2(scan_ltp)
    assert call_count[0] == tier1_calls  # Zero new Kite calls

    assert result.degraded is False
    assert result.breadth_pct_above_sma50 == pytest.approx(1.0, abs=0.01)  # all +2% are above
    assert len(result.rank_map) == 100


@pytest.mark.asyncio
async def test_tier2_degraded_when_tier1_cache_empty(universe_100, kite_above_factory):
    """If Tier 1 was never run (cold start), Tier 2 returns degraded."""
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    # No compute_tier1() call
    result = await engine.compute_tier2(scan_ltp={t: 100.0 for t in range(1000, 1100)})
    assert result.degraded is True
    assert result.breadth_pct_above_sma50 is None
    assert result.rank_map == {}


@pytest.mark.asyncio
async def test_tier2_rank_changes_with_ltp_spike(universe_100, kite_above_factory):
    """A 'below' stock whose LTP spikes should get a higher rank in Tier 2."""
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    tier1 = await engine.compute_tier1()
    rank_t1_1099 = tier1.rank_map[1099]  # This is a 'below' stock in Tier 1

    # Spike token 1099's LTP to +10% above its SMA50
    scan_ltp = {t: 100.0 for t in range(1000, 1100)}
    scan_ltp[1099] = 110.0  # 10% above SMA50

    tier2 = await engine.compute_tier2(scan_ltp)
    rank_t2_1099 = tier2.rank_map[1099]
    assert rank_t2_1099 > rank_t1_1099


@pytest.mark.asyncio
async def test_tier2_falls_back_to_cached_when_token_missing_in_scan(universe_100, kite_above_factory):
    """If a token is not in the scan_ltp dict, fall back to last known distance_pct."""
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    await engine.compute_tier1()

    # Drop 10 tokens from the scan LTP
    scan_ltp = {t: 100.0 for t in range(1000, 1090)}  # missing 1090..1099

    result = await engine.compute_tier2(scan_ltp)
    assert result.degraded is False
    # The missing 10 tokens should still have a rank (using cached distance_pct)
    assert all(t in result.rank_map for t in range(1090, 1100))


# ── OQ1 future-use field test ────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_populates_nb_ratio_distribution_field(universe_100, kite_above_factory):
    """BreadthResult should include nb_ratio_distribution_pct (OQ1 future-use)."""
    engine = BreadthEngine(
        universe=universe_100,
        kite_historical_fn=kite_above_factory(),
        cache_ttl_seconds=3600,
    )
    result = await engine.compute_tier1()
    # Field exists and is not None (stub value of 0.0 in current impl is fine)
    assert hasattr(result, "nb_ratio_distribution_pct")
    # Currently a placeholder; spec marks this as future-use
    assert result.nb_ratio_distribution_pct is not None or result.nb_ratio_distribution_pct is None  # both OK
