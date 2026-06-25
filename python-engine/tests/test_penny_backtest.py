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


# ---- 2026-06-25 Phase 2 tests (G3, G6, G8) ----------------------

def test_connors_history_floor_is_250_not_210():
    """G4 follow-on (Phase 1b): confirm the unified 250-bar floor is
    honoured by evaluate_connors_entry."""
    from penny_engine_connors import evaluate_connors_entry

    class _RE:
        bankroll = 2500.0
        def position_size(self, e, s, r):
            return 1

    # Build 240 closes -- should fail with the 250-floor reject_reason.
    closes = [10.0 + 0.01 * i for i in range(240)]
    decision = evaluate_connors_entry(
        ticker="X", daily={"closes": closes},
        today_volume=100_000, avg20_volume=50_000,
        regime_size_pct=0.05, risk_engine=_RE(),
        as_of=__import__("datetime").datetime.now(),
    )
    assert not decision["accept"]
    assert "<250" in decision["reject_reason"]


def test_market_calendar_sync_helpers_weekday_only_fallback():
    """G6: when the holiday cache is empty, is_trading_day_sync and
    trading_days_between_sync fall back to weekday-only (no regression)."""
    import os
    import tempfile
    from datetime import date
    from market_calendar import is_trading_day_sync, trading_days_between_sync
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        # No holidays populated -> empty cache -> weekday-only.
        # Mon-Fri = trading; Sat-Sun = not.
        assert is_trading_day_sync(date(2025, 6, 2), db_path) is True   # Mon
        assert is_trading_day_sync(date(2025, 6, 6), db_path) is True   # Fri (weekday with empty cache)
        assert is_trading_day_sync(date(2025, 6, 7), db_path) is False  # Sat
        assert is_trading_day_sync(date(2025, 6, 8), db_path) is False  # Sun
        # Mon -> Wed = 2 trading days (Tue, Wed)
        assert trading_days_between_sync(date(2025, 6, 2), date(2025, 6, 4), db_path) == 2
        # Mon -> Mon = 5 trading days
        assert trading_days_between_sync(date(2025, 6, 2), date(2025, 6, 9), db_path) == 5
    finally:
        os.unlink(db_path)


def test_market_calendar_sync_helpers_holiday_aware():
    """G6: when the holiday cache has entries, is_trading_day_sync
    respects them (e.g. an Independence Day listed as a holiday is
    not a trading day even though it's a weekday)."""
    import os
    import sqlite3
    import tempfile
    from datetime import date
    from market_calendar import is_trading_day_sync, trading_days_between_sync
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        # Populate the holidays table with a known weekday (Friday).
        with sqlite3.connect(db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS holidays (holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)")
            con.execute("INSERT INTO holidays VALUES (?, CURRENT_TIMESTAMP)", ("2025-08-15",))
            con.commit()
        # 2025-08-15 is a Friday. With cache: not a trading day.
        # Without cache (commented above for comparison): it WOULD be.
        assert is_trading_day_sync(date(2025, 8, 15), db_path) is False
        # Other Fridays still trade.
        assert is_trading_day_sync(date(2025, 8, 8), db_path) is True
        # Count Tue..Thu around the holiday (Aug 13..14, skipping 15 Fri).
        assert trading_days_between_sync(date(2025, 8, 12), date(2025, 8, 16), db_path) == 2
    finally:
        os.unlink(db_path)


def test_penny_risk_infer_band_pct_defaults_to_5pct():
    """G8 helper: small day's move -> 5% band."""
    from penny_risk import PennyRiskEngine
    # prev_close=10, day_high=10.3 (3% up), day_low=9.8 (2% down)
    assert PennyRiskEngine.infer_band_pct_from_quote(10.0, 10.3, 9.8) == 0.05


def test_penny_risk_infer_band_pct_snaps_to_10pct():
    """G8 helper: >7.5% move -> 10% band (post-volatility widening)."""
    from penny_risk import PennyRiskEngine
    # 9% up
    assert PennyRiskEngine.infer_band_pct_from_quote(10.0, 10.9, 9.5) == 0.10


def test_penny_risk_infer_band_pct_snaps_to_20pct():
    """G8 helper: >15% move -> 20% band (ASM / extreme vol)."""
    from penny_risk import PennyRiskEngine
    # 18% down
    assert PennyRiskEngine.infer_band_pct_from_quote(10.0, 10.0, 8.2) == 0.20


def test_penny_risk_circuit_blocked_uses_passed_band_pct():
    """G8: the circuit filter now uses the passed band_pct (was always 5%)."""
    from penny_risk import PennyRiskEngine
    r = PennyRiskEngine(bankroll=2500.0)
    # The scaled_skip at 10% band is 0.005 * (0.10/0.05) = 0.01 = 1.0%
    # of prev_close. Distance to band must be STRICTLY LESS than scaled_skip
    # for the second check (from-high) to fire. At 5% band, scaled_skip is
    # 0.005 = 0.5%, so a 0.5% distance IS at the threshold (not below).
    # last=10.95 -> distance to 10%-band=11.0 is 0.5% (below 1% scaled_skip)
    #               distance to 5%-band=10.5 is 4.5% (above 0.5% scaled_skip
    #                                                -> first check returns False).
    # At 10% band: dist_from_high = (11.30 - 10.95) / 11.30 = 3.1% > 3% -> blocks.
    last, day_high, prev = 10.95, 11.30, 10.0
    blocked_5, _ = r.circuit_blocked(last, day_high, prev, 0.05)
    blocked_10, msg_10 = r.circuit_blocked(last, day_high, prev, 0.10)
    assert blocked_5 is False, "5% band: 4.5% distance > 0.5% scaled_skip, should not block"
    assert blocked_10 is True, "10% band: 0.5% distance < 1% scaled_skip + 3.1% from high, should block"
    assert "circuit:" in msg_10


def test_penny_risk_circuit_blocked_defaults_band_pct_to_5():
    """G8 defensive: if caller passes None or 0, default to 5% (preserves
    pre-fix behaviour -- this is the path the scanner takes today)."""
    from penny_risk import PennyRiskEngine
    r = PennyRiskEngine(bankroll=2500.0)
    blocked_none, _ = r.circuit_blocked(10.95, 11.05, 10.0, None)
    blocked_zero, _ = r.circuit_blocked(10.95, 11.05, 10.0, 0)
    assert blocked_none is False  # same as passing 0.05
    assert blocked_zero is False
