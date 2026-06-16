"""
Tests for the universe-expansion changes in main.py (Tasks 7-8).

Task 7: liquidity filter (drop tickers below 20-day median ADV floor).
Task 8: Nifty 500 fallback chain (CSV → in-code → crash).
"""

import asyncio
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


# ─────────────────────────────────────────────────────────────────
# Liquidity filter (Task 7)
# ─────────────────────────────────────────────────────────────────


def _make_historical_df(closes):
    """Create a minimal historical DF with the given close prices."""
    dates = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": [c - 0.5 for c in closes],
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
        "volume": [1_000_000] * len(closes),
    })


def _make_intraday_df(n_candles: int = 30) -> pd.DataFrame:
    """Create a minimal intraday 5-min DF with a clean uptrend.

    Used by the run_momentum_screener tests (Task 8). The 30-candle
    default ≈ 2.5 hours of 5-min data (covers the morning session
    up to 12:00 IST), which is enough to trigger the MC3-T / MC5 /
    MC6 gates in evaluate_momentum_signal. The test mocks
    `evaluate_momentum_signal` to return False, so the actual
    indicator values don't matter — the DF just needs to be
    non-empty and well-formed so the `len(df_intra) < 4` check
    in run_momentum_screener passes.
    """
    times = pd.date_range("2025-01-15 09:15", periods=n_candles, freq="5min")
    closes = [100.0 + i * 0.1 for i in range(n_candles)]
    return pd.DataFrame({
        "date": times,
        "open": [c - 0.05 for c in closes],
        "high": [c + 0.10 for c in closes],
        "low":  [c - 0.10 for c in closes],
        "close": closes,
        "volume": [10_000] * n_candles,
    })


@pytest.mark.asyncio
async def test_filter_by_liquidity_drops_below_threshold(monkeypatch):
    """Tickers with 20-day median ADV below threshold are dropped."""
    from main import _filter_by_liquidity
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 2.0)
    monkeypatch.setattr(settings, "UNIVERSE_LIQUIDITY_LOOKBACK_DAYS", 20)

    # Build a fake universe: 3 tickers, 2 pass + 1 fail
    universe = pd.DataFrame({
        "tradingsymbol": ["LIQUID_A", "LIQUID_B", "ILLIQUID_C"],
        "exchange": ["NSE", "NSE", "NSE"],
        "sector": ["UNKNOWN"] * 3,
    })

    # Build a fake kite: get_historical returns different ADV per ticker
    # 1 share × ₹100 × 100,000 vol/day = ₹10,000,000 = ₹1 cr ADV
    # For LIQUID: close=1000, vol=100k → ADV = 1000*100k = ₹100 cr → passes
    # For ILLIQUID: close=10, vol=10k → ADV = 10*10k = ₹1 lakh = ₹0.0001 cr → fails
    async def fake_get_historical(ticker, from_date, to_date):
        if ticker == "LIQUID_A" or ticker == "LIQUID_B":
            # close=1000, vol=100_000, 20 days
            return _make_historical_df([1000.0] * 25).assign(volume=[100_000] * 25)
        else:
            # close=10, vol=10_000, 20 days → very illiquid
            return _make_historical_df([10.0] * 25).assign(volume=[10_000] * 25)

    fake_kite = MagicMock()
    fake_kite.get_historical = fake_get_historical

    result = await _filter_by_liquidity(universe, fake_kite, today=pd.Timestamp("2026-06-15"))

    assert "LIQUID_A" in result["tradingsymbol"].values
    assert "LIQUID_B" in result["tradingsymbol"].values
    assert "ILLIQUID_C" not in result["tradingsymbol"].values


@pytest.mark.asyncio
async def test_filter_by_liquidity_handles_fetch_failure_gracefully(monkeypatch):
    """If a ticker's historical fetch fails, drop the ticker (fail-soft)."""
    from main import _filter_by_liquidity
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 2.0)
    monkeypatch.setattr(settings, "UNIVERSE_LIQUIDITY_LOOKBACK_DAYS", 20)

    universe = pd.DataFrame({
        "tradingsymbol": ["GOOD", "BAD"],
        "exchange": ["NSE", "NSE"],
        "sector": ["UNKNOWN"] * 2,
    })

    async def fake_get_historical(ticker, from_date, to_date):
        if ticker == "BAD":
            return pd.DataFrame()  # empty
        return _make_historical_df([1000.0] * 25).assign(volume=[100_000] * 25)

    fake_kite = MagicMock()
    fake_kite.get_historical = fake_get_historical

    result = await _filter_by_liquidity(universe, fake_kite, today=pd.Timestamp("2026-06-15"))
    assert "GOOD" in result["tradingsymbol"].values
    assert "BAD" not in result["tradingsymbol"].values


@pytest.mark.asyncio
async def test_filter_by_liquidity_returns_input_when_threshold_zero(monkeypatch):
    """If UNIVERSE_MIN_ADV_CRORE=0, no filtering happens (escape hatch)."""
    from main import _filter_by_liquidity
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)
    monkeypatch.setattr(settings, "UNIVERSE_LIQUIDITY_LOOKBACK_DAYS", 20)

    universe = pd.DataFrame({
        "tradingsymbol": ["ANY", "TICKER"],
        "exchange": ["NSE"] * 2,
        "sector": ["UNKNOWN"] * 2,
    })
    fake_kite = MagicMock()

    result = await _filter_by_liquidity(universe, fake_kite, today=pd.Timestamp("2026-06-15"))
    assert len(result) == 2
