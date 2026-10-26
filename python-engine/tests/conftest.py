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


# -- Background work and connection threads [T22-BG 2026-10-22] -------
# Engine background work a test starts (registering the scheduler jobs
# after 09:30 IST starts a startup catch-up) must not be left pending when
# pytest-asyncio closes the test's loop: a task destroyed inside
# `aiosqlite.connect()` leaves a non-daemon worker thread, and the
# interpreter can then never exit (Oct 22: a passing suite hung 3.5 h).

@pytest.hookimpl(hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    yield
    import background_tasks
    for loop in {task.get_loop() for task in background_tasks.pending()}:
        if not loop.is_closed() and not loop.is_running():
            loop.run_until_complete(background_tasks.drain(grace=0, timeout=5.0))


def pytest_sessionfinish(session, exitstatus):
    """Last guard: stop any connection worker a test leaked, and say so."""
    import threading
    leaked = [thread for thread in threading.enumerate()
              if isinstance(thread, aiosqlite.Connection) and thread.is_alive()]
    for connection in leaked:
        stop = getattr(connection, "_stop_running", None)
        if stop is not None:
            stop()
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if leaked and reporter is not None:
        reporter.write_line(f"conftest: stopped {len(leaked)} leaked aiosqlite connection thread(s) "
                            "so the run can exit", yellow=True)


# -- No real network [O26c, O26d 2026-10-26] -------------------------
# The suite runs on the developer's machine, whose .env holds the real bot
# tokens. On Oct 26 a test that calls every scheduled job polled the real
# partner bot during market hours: Production's own poll got Telegram's 409
# three times (and backed off 10 minutes each time), and the penny hourly
# report test called Telegram too. Every test gets fake tokens
# (patch_settings), and tests/netguard refuses lookups and connections to
# any non-local host, numeric addresses and asyncio included. Its folder goes
# first on PYTHONPATH so a Python child process that inherits the
# environment loads the same guard (its docstring says what is not covered).

_NETGUARD_DIR = os.path.join(os.path.dirname(__file__), "netguard")


def _install_netguard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sentinel_netguard", os.path.join(_NETGUARD_DIR, "sitecustomize.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["sentinel_netguard"] = module
    if os.environ.get(module.OPT_IN) != "1":
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [_NETGUARD_DIR] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p])
    return module


netguard = _install_netguard()


# -- Fake Settings ----------------------------------------------------

@pytest.fixture(autouse=True)
def patch_settings(monkeypatch, tmp_path):
    """
    Override settings with test-safe values for every test.
    Uses a temp DB path so we never touch production cache.db.
    """
    from config import settings

    db_file = str(tmp_path / "test_cache.db")
    monkeypatch.setattr(settings, "DB_PATH", db_file)
    for name in ("TELEGRAM_BOT_TOKEN", "PARTNER_TELEGRAM_BOT_TOKEN"):        # [O26c] never the real bots
        monkeypatch.setattr(settings, name, f"test-{name.lower()}")
    for name in ("TELEGRAM_CHAT_ID", "PARTNER_TELEGRAM_CHAT_ID"):
        monkeypatch.setattr(settings, name, "1")
    for name in ("PARTNER_KITE_API_KEY", "PARTNER_KITE_API_SECRET"):
        monkeypatch.setattr(settings, name, f"test-{name.lower()}")
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
    # [TARGET-REACH 2026-07-31] Track the shipped default (1.6), not the old
    # 2.0. Pinning 2.0 here made the harness disagree with production: with the
    # ATR-floored stop, a 2.0R target puts the target 0.7 daily ATRs away, and
    # the MC5 fuel gate then rejects any entry once ~18% of the day's range is
    # consumed. Tests that need a specific R target should set it themselves.
    monkeypatch.setattr(settings, "MOMENTUM_R_TARGET", 1.6)
    monkeypatch.setattr(settings, "MOMENTUM_MAX_COST_RATIO", 0.25)
    monkeypatch.setattr(settings, "MOMENTUM_MIN_CANDLES", 4)
    monkeypatch.setattr(settings, "CONTAINER_A_URL", "http://localhost:9999")
    monkeypatch.setattr(settings, "INTERNAL_API_SECRET", "test_secret")
    monkeypatch.setattr(settings, "STRATEGY_VERSION", "1.0.0-test")
    # [O21-PK 2026-10-21] The partner's Zerodha app is off unless a test
    # turns it on: real keys in the repo .env must not change card buttons
    # or the coach note in unrelated tests.
    monkeypatch.setattr(settings, "PARTNER_KITE_API_KEY", "")
    monkeypatch.setattr(settings, "PARTNER_KITE_API_SECRET", "")
    monkeypatch.setattr(settings, "PARTNER_KITE_USER_ID", "")
    # [FNO 2026-07-10] Keep every F&O artefact inside tmp_path so no test
    # can touch /data on a dev machine.
    monkeypatch.setattr(settings, "FNO_SIGNAL_LOG_PATH", str(tmp_path / "fno_signals.csv"))
    monkeypatch.setattr(settings, "FNO_INSTRUMENTS_JSON_PATH", str(tmp_path / "fno_instruments.json"))
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
    return settings


# -- Temp DB Path ----------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Returns a temp SQLite DB path. Each test gets a fresh file."""
    return str(tmp_path / "test_cache.db")


# -- OHLCV DataFrame (daily, 250 rows) ------------------------------

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


# -- Intraday Candles (15-min) ---------------------------------------

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
    # Spike volume on last candle (3x avg = 300% surge)
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


# -- Nifty Data (for regime tests) ----------------------------------

@pytest.fixture
def nifty_bull_df():
    """NIFTY data where close > EMA50 * 1.02 -> BULL regime."""
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
    """NIFTY data where close < EMA50 -> BEAR_RS_ONLY regime."""
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


@pytest.fixture
def minimal_daily_df():
    """14+ daily OHLCV rows so calc_atr() has enough data. ATR will be ~10 pts."""
    n = 20
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    return pd.DataFrame({
        "open":   [100.0] * n,
        "high":   [105.0] * n,
        "low":    [95.0]  * n,
        "close":  [102.0] * n,
        "volume": [500_000] * n,
    }, index=dates)


@pytest.fixture
def base_momentum_df():
    """
    6-candle intraday df that passes MC1, MC2, MC4.
    Volume ratio on last candle is ~1.6x average.
    VWAP crossover: penultimate candle below VWAP, last candle above.
    Close in top 20% of intraday range (MC4 passes).
    intraday_high=101.5, intraday_low=98.5 (range=3 pts).
    """
    n = 6
    timestamps = pd.date_range("2026-05-11 09:15", periods=n, freq="15min")
    avg_vol = 100_000
    df = pd.DataFrame({
        "open":   [99.0, 99.5, 99.8, 100.0, 100.2, 100.5],
        "high":   [99.5, 100.0, 100.2, 100.5, 100.8, 101.5],
        "low":    [98.5,  99.0,  99.5,  99.8, 100.0, 100.0],
        "close":  [99.2,  99.6,  99.9, 100.1,  98.0, 101.2],  # penultimate drops below VWAP
        "volume": [avg_vol] * (n - 1) + [int(avg_vol * 1.6)],
    }, index=timestamps)
    return df
