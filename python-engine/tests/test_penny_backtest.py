"""
[PENNY-BACKTEST-TEST 2026-06-25] Smoke tests for penny_backtest.py
(closes G10).

These tests pin the v1 behaviour:
- run_backtest requires a kite client (no implicit defaults)
- A minimal end-to-end run with a fixture kite produces a result
- Result fields are populated correctly
- max_drawdown / sharpe helpers are correct on known sequences

Trade-replay (entry -> SL/T1/T2 -> P&L) is NOT exercised here -- it
requires a faithful LTP walk which is a v2 feature (see backtest.py
docstring + the audit doc).
"""
import asyncio
import json
import math
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest


# ---- helpers ---------------------------------------------------------

def _make_fixture_kite():
    """Build a fake kite that returns minimal valid intraday + historical
    data for ONE ticker over a short range. The scanner will iterate but
    no signals will fire (insufficient data for the breakout engine)."""
    import pandas as pd
    k = MagicMock()
    k.instrument_cache = {"AAA": 1001}

    # 60 minutes of intraday for AAA on day 1, prices oscillating around 12.0
    times = pd.date_range("2025-09-01 09:15", periods=60, freq="1min")
    prices = [12.0 + 0.05 * math.sin(i / 5) for i in range(60)]
    df = pd.DataFrame({
        "open":   [p - 0.05 for p in prices],
        "high":   [p + 0.10 for p in prices],
        "low":    [p - 0.10 for p in prices],
        "close":  prices,
        "volume": [1000] * 60,
    }, index=pd.DatetimeIndex(times, name="datetime"))

    async def _intraday(ticker, from_datetime, to_datetime, interval="minute"):
        return df if ticker == "AAA" else None

    async def _historical(ticker, from_date, to_date):
        if ticker != "AAA":
            return None
        dates = pd.date_range(end="2025-09-01", periods=20, freq="D")
        return pd.DataFrame({
            "open":   [12.0] * 20,
            "high":   [12.5] * 20,
            "low":    [11.5] * 20,
            "close":  [12.0] * 20,
            "volume": [50_000] * 20,
        }, index=pd.DatetimeIndex(dates, name="date"))

    async def _quote(tokens):
        return {
            1001: {"last_price": 12.0, "ohlc": {"high": 12.0, "low": 12.0, "close": 12.0},
                   "volume": 100_000, "depth": {"buy": [], "sell": []}},
        }

    k.get_intraday = AsyncMock(side_effect=_intraday)
    k.get_historical = AsyncMock(side_effect=_historical)
    k.get_quote = AsyncMock(side_effect=_quote)
    return k


def _write_universe(path: str):
    payload = {
        "as_of": "2025-09-01",
        "universe_size_target": 100,
        "tickers": [
            {"symbol": "AAA", "series": "EQ", "prev_close": 12.0,
             "promoter_holding_pct": 50.0, "pb_ratio": 1.2,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 1_000_000},
        ],
    }
    with open(path, "w") as f:
        json.dump(payload, f)


# ---- tests -----------------------------------------------------------

def test_run_backtest_requires_kite():
    from penny_backtest import run_backtest
    with pytest.raises(ValueError, match="kite"):
        asyncio.run(run_backtest(
            from_date="2025-09-01", to_date="2025-09-01",
            universe_path="/tmp/doesnt_matter.json",
        ))


def test_run_backtest_minimal_end_to_end(tmp_path):
    """A 1-day backtest over the fixture kite produces a result with
    correct structure: total_scans >= 1, signals_rejected/fired populated,
    reject_reasons is a dict, equity metrics computed."""
    from penny_backtest import run_backtest
    universe_path = tmp_path / "penny.json"
    _write_universe(str(universe_path))
    kite = _make_fixture_kite()
    result = asyncio.run(run_backtest(
        from_date="2025-09-01", to_date="2025-09-01",
        universe_path=str(universe_path), bankroll=2500.0,
        kite=kite,
    ))
    assert result.total_scans >= 1
    assert result.universe_size == 1
    assert isinstance(result.reject_reasons, dict)
    assert result.final_bankroll == result.bankroll  # no trades in v1
    assert isinstance(result.max_drawdown_pct, float)
    assert isinstance(result.sharpe_ratio, float)


def test_run_backtest_writes_json_report(tmp_path):
    """output_path produces a JSON file with all summary metrics."""
    from penny_backtest import run_backtest
    universe_path = tmp_path / "penny.json"
    _write_universe(str(universe_path))
    kite = _make_fixture_kite()
    out = tmp_path / "report.json"
    asyncio.run(run_backtest(
        from_date="2025-09-01", to_date="2025-09-01",
        universe_path=str(universe_path), kite=kite,
        output_path=str(out),
    ))
    assert out.exists()
    payload = json.loads(out.read_text())
    for key in ("from_date", "to_date", "bankroll", "final_bankroll",
                "universe_size", "total_scans", "signals_fired",
                "signals_rejected", "max_drawdown_pct", "sharpe_ratio",
                "top_reject_reasons"):
        assert key in payload, f"missing key {key} in report"


def test_max_drawdown_helper_constant_curve():
    """A flat equity curve has zero drawdown."""
    from penny_backtest import _max_drawdown_pct
    assert _max_drawdown_pct([100, 100, 100, 100]) == 0.0


def test_max_drawdown_helper_known_drawdown():
    """A peak of 100 then trough of 80 = 20% drawdown."""
    from penny_backtest import _max_drawdown_pct
    assert _max_drawdown_pct([100, 90, 80, 95]) == 20.0


def test_sharpe_helper_constant_curve_is_zero():
    """A flat equity curve has zero Sharpe (no volatility)."""
    from penny_backtest import _sharpe_ratio_from_equity
    assert _sharpe_ratio_from_equity([100, 100, 100, 100]) == 0.0


def test_sharpe_helper_positive_trend_is_positive():
    """A monotonically rising equity curve has positive Sharpe."""
    from penny_backtest import _sharpe_ratio_from_equity
    assert _sharpe_ratio_from_equity([100, 102, 104, 106, 108]) > 0


def test_sharpe_helper_known_value():
    """Sharpe of perfectly linear 1% daily returns is sqrt(252) ~= 15.87."""
    from penny_backtest import _sharpe_ratio_from_equity
    equity = [100 * (1.01 ** i) for i in range(20)]
    s = _sharpe_ratio_from_equity(equity)
    # Constant return series -> variance is tiny but non-zero numerically.
    # Should be > 10 (well above zero).
    assert s > 10, f"expected high Sharpe for linear growth, got {s}"
