"""
Tests for backtest.py -- regime-aware backtesting harness.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from backtest import run_backtest, run_universe_backtest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sweet_df():
    """
    250-row daily OHLCV with a gentle uptrend.
    Starts at 500, ends near 625. Enough history for evaluate_signal (200+).
    """
    n = 250
    base = 500.0
    close = np.array([base + 0.5 * i + 2 * np.sin(i / 10) for i in range(n)])
    high = close + np.linspace(3, 5, n)
    low = close - np.linspace(3, 5, n)
    opn = close - np.linspace(0.5, 1.0, n)
    volume = np.array([200_000 + 5000 * (i % 20) for i in range(n)])
    volume[-1] = int(volume[-21:-1].mean() * 2.5)  # volume spike on last day

    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "open": opn, "high": high, "low": low,
        "close": close, "volume": volume,
    }, index=dates)
    return df


@pytest.fixture
def empty_df():
    """Fewer than 200 rows -- should be handled gracefully."""
    n = 50
    return pd.DataFrame({
        "open":   np.linspace(500, 525, n),
        "high":   np.linspace(505, 530, n),
        "low":    np.linspace(495, 520, n),
        "close":  np.linspace(500, 525, n),
        "volume": np.full(n, 150_000),
    }, index=pd.date_range("2025-10-01", periods=n, freq="B"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_backtest_runs_without_error(sweet_df):
    """Smoke test -- run_backtest completes without raising an exception."""
    result = run_backtest(
        ticker="TEST",
        df=sweet_df,
        start_date="2025-06-01",
        end_date="2025-12-31",
        initial_bankroll=5000.0,
    )
    # Should return a dict, not raise
    assert isinstance(result, dict)
    assert "ticker" in result
    assert "trades" in result
    assert "stats" in result


def test_backtest_returns_structure(sweet_df):
    """Verify the return dict has all expected keys."""
    result = run_backtest(
        ticker="TEST",
        df=sweet_df,
        start_date="2025-06-01",
        end_date="2025-12-31",
    )

    # Top-level keys
    assert result["ticker"] == "TEST"
    assert result["start_date"] == "2025-06-01"
    assert result["end_date"] == "2025-12-31"
    assert isinstance(result["trades"], list)
    assert isinstance(result["stats"], dict)
    assert isinstance(result["regime_transitions"], list)

    # Stats keys
    stats = result["stats"]
    for key in ("total_trades", "win_rate", "avg_R", "profit_factor",
               "max_drawdown_pct", "total_return_pct", "regime_distribution"):
        assert key in stats, f"Missing stat key: {key}"


def test_backtest_empty_data(empty_df):
    """Handles a DataFrame with fewer than 200 rows gracefully."""
    result = run_backtest(
        ticker="SMALL",
        df=empty_df,
        start_date="2025-10-01",
        end_date="2025-12-31",
    )

    assert result["error"] == "insufficient_data_200_rows"
    assert result["trades"] == []
    assert result["stats"]["total_trades"] == 0


def test_universe_backtest_runs_without_error(sweet_df):
    """Smoke test for run_universe_backtest."""
    results = run_universe_backtest(
        tickers=["A", "B", "C"],
        start_date="2025-06-01",
        end_date="2025-12-31",
        historical_data={
            "A": sweet_df,
            "B": sweet_df,
            "C": sweet_df,
        },
        initial_bankroll=5000.0,
    )

    assert isinstance(results, list)
    assert len(results) == 4  # 3 tickers + 1 universe_aggregate

    # Last entry is universe aggregate
    agg = results[-1]
    assert agg["ticker"] == "universe_aggregate"
    assert "stats" in agg
    assert "trades" in agg


def test_universe_backtest_missing_ticker():
    """Handles missing tickers gracefully without crashing."""
    results = run_universe_backtest(
        tickers=["EXISTS", "MISSING"],
        start_date="2025-06-01",
        end_date="2025-12-31",
        historical_data={
            "EXISTS": pd.DataFrame({
                "open": [100]*250, "high": [105]*250, "low": [95]*250,
                "close": [102]*250, "volume": [500000]*250,
            }, index=pd.date_range("2025-01-01", periods=250, freq="B")),
        },
    )

    # Should return 3 entries: EXISTS, MISSING (error), universe_aggregate
    assert len(results) == 3
    missing_result = next(r for r in results if r["ticker"] == "MISSING")
    assert missing_result["error"] == "no_data_for_ticker"