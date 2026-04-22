"""
Shared test fixtures for Trading Sentinel Python Engine.
All fixtures use deterministic data - no random().
"""
import os
import sys
import math
import tempfile
import pytest
import pytest_asyncio
import pandas as pd
import numpy as np
import aiosqlite
from datetime import datetime, date

# Ensure python-engine is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fake Settings ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_settings(monkeypatch, tmp_path):
    """
    Override settings with test-safe values for every test.
    Uses a temp DB path so we never touch production cache.db.
    """
    from config import settings

    db_file = str(tmp_path / "test_cache.db")
    monkeypatch.setattr(settings, "DB_PATH", db_file)
    monkeypatch.setattr(settings, "INITIAL_BANKROLL", 5000.0)
    monkeypatch.setattr(settings, "RISK_PCT", 0.10)
    monkeypatch.setattr(settings, "MAX_OPEN_POSITIONS", 6)
    monkeypatch.setattr(settings, "MAX_CAPITAL_PER_TRADE_PCT", 0.50)
    monkeypatch.setattr(settings, "MAX_SECTOR_EXPOSURE_PCT", 0.40)
    monkeypatch.setattr(settings, "MAX_CORRELATED_POSITIONS", 2)
    monkeypatch.setattr(settings, "MAX_TOTAL_RISK_PCT", 0.6)
    monkeypatch.setattr(settings, "CB_DAILY_LOSS_PCT", 0.20)
    monkeypatch.setattr(settings, "CB_MAX_CONSECUTIVE_LOSSES", 5)
    monkeypatch.setattr(settings, "CB_MAX_DRAWDOWN_PCT", 0.50)
    monkeypatch.setattr(settings, "CB_FLOOR_PCT", 0.40)
    monkeypatch.setattr(settings, "MAX_MOMENTUM_POSITIONS", 5)
    monkeypatch.setattr(settings, "MOMENTUM_VOL_SURGE_PCT", 2.0)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT", 0.10)
    monkeypatch.setattr(settings, "MOMENTUM_R_TARGET", 2.0)
    monkeypatch.setattr(settings, "MOMENTUM_MAX_COST_RATIO", 0.25)
    monkeypatch.setattr(settings, "MOMENTUM_MIN_CANDLES", 4)
    monkeypatch.setattr(settings, "CONTAINER_A_URL", "http://localhost:9999")
    monkeypatch.setattr(settings, "INTERNAL_API_SECRET", "test_secret")
    monkeypatch.setattr(settings, "TOKEN_INJECTION_SECRET", "test_secret")
    monkeypatch.setattr(settings, "STRATEGY_VERSION", "1.0.0-test")
    return settings


# ── Temp DB Path ────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """Returns a temp SQLite DB path. Each test gets a fresh file."""
    return str(tmp_path / "test_cache.db")


# ── OHLCV DataFrame (daily, 250 rows) ──────────────────────────────

@pytest.fixture
def fake_ohlcv_df():
    """
    250-row daily OHLCV with a gentle uptrend.
    Starts at 500, ends near 625 (~25% over 250 days).
    Deterministic: slope ~0.5/day.
    """
    n = 250
    base = 500.0
    close = np.array([base + 0.5 * i + 2 * np.sin(i / 10) for i in range(n)])
    high = close + np.linspace(3, 5, n)
    low = close - np.linspace(3, 5, n)
    opn = close - np.linspace(0.5, 1.0, n)
    volume = np.array([200_000 + 5000 * (i % 20) for i in range(n)])

    # Spike volume on last candle for volume ratio tests
    volume[-1] = int(volume[-21:-1].mean() * 2.5)

    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "open": opn, "high": high, "low": low,
        "close": close, "volume": volume, "date": dates
    })
    df.index = dates
    return df


@pytest.fixture
def fake_ohlcv_short():
    """Only 50 rows - insufficient for evaluate_signal (needs 200)."""
    n = 50
    close = np.linspace(500, 525, n)
    df = pd.DataFrame({
        "open": close - 1, "high": close + 3,
        "low": close - 3, "close": close,
        "volume": [150_000] * n
    })
    df.index = pd.date_range("2025-10-01", periods=n, freq="B")
    return df


# ── Intraday Candles (15-min) ───────────────────────────────────────

@pytest.fixture
def fake_momentum_candles():
    """
    10 fifteen-minute candles for momentum tests.
    Price trends up, volume surges on last candle,
    VWAP crossover on the last candle.
    """
    n = 10
    base = 1000.0
    data = {
        "open":   [base + i * 2 for i in range(n)],
        "high":   [base + i * 2 + 5 for i in range(n)],
        "low":    [base + i * 2 - 3 for i in range(n)],
        "close":  [base + i * 2 + 1 for i in range(n)],
        "volume": [100_000] * n,
    }
    # Spike volume on last candle (3× avg = 300% surge)
    data["volume"][-1] = 300_000

    # Make VWAP crossover happen on last candle:
    # penultimate candle close below VWAP, last candle close above VWAP
    # VWAP is cumulative, so we need close[-2] < vwap[-2] and close[-1] > vwap[-1]
    # With uptrend and stable volume, VWAP tracks close closely.
    # Force the penultimate candle close below VWAP by dropping it
    data["close"][-2] = base  # low close on penultimate
    data["close"][-1] = base + 25  # high close on last
    data["high"][-1] = base + 28

    return pd.DataFrame(data)


@pytest.fixture
def fake_momentum_candles_no_crossover():
    """All candles above VWAP - no crossover event."""
    n = 10
    base = 1000.0
    data = {
        "open":   [base + i * 5 for i in range(n)],
        "high":   [base + i * 5 + 8 for i in range(n)],
        "low":    [base + i * 5 - 2 for i in range(n)],
        "close":  [base + i * 5 + 4 for i in range(n)],
        "volume": [100_000] * n,
    }
    data["volume"][-1] = 300_000
    return pd.DataFrame(data)


# ── Nifty Data (for regime tests) ──────────────────────────────────

@pytest.fixture
def nifty_bull_df():
    """NIFTY data where close > EMA50 * 1.02 → BULL regime."""
    n = 60
    # Steady uptrend: close well above any 50-EMA
    close = np.linspace(18000, 19500, n)
    df = pd.DataFrame({
        "open": close - 10, "high": close + 20,
        "low": close - 20, "close": close,
        "volume": [1_000_000] * n
    })
    df.index = pd.date_range("2025-06-01", periods=n, freq="B")
    return df


@pytest.fixture
def nifty_bear_df():
    """NIFTY data where close < EMA50 → BEAR_RS_ONLY regime."""
    n = 60
    # Downtrend: close drops below EMA50
    close_arr = np.concatenate([
        np.linspace(19000, 19500, 30),  # up first
        np.linspace(19500, 18000, 30),  # then sharp drop
    ])
    df = pd.DataFrame({
        "open": close_arr - 10, "high": close_arr + 20,
        "low": close_arr - 20, "close": close_arr,
        "volume": [1_000_000] * n
    })
    df.index = pd.date_range("2025-06-01", periods=n, freq="B")
    return df
