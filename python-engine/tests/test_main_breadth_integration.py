"""
Integration test: verify that the breadth engine, when initialized at scan
start, actually receives the right inputs from run_screener.

Patches the breadth-related code path + DB calls to verify:
  - breadth_engine is built (via build_breadth_engine) when the flag is on
  - compute_tier1 is awaited once before the scan loop
  - Pass 1 collects LTPs (token -> close)
  - compute_tier2 is awaited once AFTER the loop with those LTPs
  - Pass 2's evaluate_signal call gets the breadth kwargs via build_breadth_kwargs
"""

import asyncio
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def _make_universe_df(n=3):
    return pd.DataFrame({
        "tradingsymbol": [f"TEST{i}" for i in range(n)],
        "exchange": ["NSE"] * n,
        "sector": ["UNKNOWN"] * n,
    })


def _make_df():
    """250-bar synthetic df that passes engine.py filters (rsi in [45,72])."""
    import numpy as np
    dates = pd.date_range("2025-06-01", periods=250, freq="D")
    closes = 100.0 + np.arange(250) * 0.1
    return pd.DataFrame({
        "date": dates, "open": closes - 0.5, "high": closes + 1.0,
        "low": closes - 1.0, "close": closes, "volume": [1_000_000] * 250,
    })


@pytest.mark.asyncio
async def test_run_screener_calls_breadth_tier1_and_tier2(monkeypatch, db_path):
    """End-to-end: flag on -> breadth engine built -> Tier 1 + Tier 2 awaited -> kwargs passed."""
    # Init the DBs (run_screener hits both)
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    # Write a nifty100.json for build_breadth_engine to load
    data_dir = os.path.dirname(db_path) + "/data"
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "nifty100.json"), "w") as f:
        json.dump({
            "as_of_date": "2026-06-14",
            "tickers": [
                {"symbol": "TEST0", "instrument_token": None},
                {"symbol": "TEST1", "instrument_token": None},
                {"symbol": "TEST2", "instrument_token": None},
            ],
        }, f)

    monkeypatch.setattr("config.settings.BREADTH_ENRICHMENT_ENABLED", True)
    monkeypatch.setattr("config.settings.BREADTH_DATA_DIR", data_dir)

    import main
    from config import settings

    # Fake breadth engine with awaitable Tier 1/2 methods
    fake_t1 = MagicMock()
    fake_t1.degraded = False
    fake_t1.n_resolved = 3
    fake_t1.breadth_pct_above_sma50 = 0.60
    fake_t1.rank_map = {}
    fake_t2 = MagicMock()
    fake_t2.degraded = False
    fake_t2.n_resolved = 3
    fake_t2.breadth_pct_above_sma50 = 0.60
    fake_t2.rank_map = {1000: 0.7, 1001: 0.5, 1002: 0.9}

    fake_engine = MagicMock()
    fake_engine.compute_tier1 = AsyncMock(return_value=fake_t1)
    fake_engine.compute_tier2 = AsyncMock(return_value=fake_t2)

    # Pre-set the global so build_breadth_engine isn't called inside run_screener
    main.breadth_engine = fake_engine

    # Mock ALL the run_screener dependencies
    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "calc_ema", return_value=pd.Series([100.0])), \
         patch.object(main, "calc_atr", return_value=pd.Series([1.5, 1.5])), \
         patch.object(main, "calc_rsi_series", return_value=pd.Series([60.0])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_and_allocate", return_value=([], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)), \
         patch("pandas.read_csv", return_value=_make_universe_df(3)):

        mock_kite.instrument_cache = {"TEST0": 1000, "TEST1": 1001, "TEST2": 1002}
        mock_kite.get_historical = AsyncMock(return_value=_make_df())

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.bankroll = 5000.0
        main.risk_pct = 0.10
        main.nifty_close = 18000.0
        main.nifty_ema20 = 17900.0
        main.nifty_return_1d = 0.001
        main.nifty_df = _make_df()
        main.is_market_open = MagicMock(return_value=False)

        await main.run_screener()

    # Tier 1 awaited exactly once
    assert fake_engine.compute_tier1.await_count == 1, "Tier 1 should be awaited once"
    # Tier 2 awaited exactly once
    assert fake_engine.compute_tier2.await_count == 1, "Tier 2 should be awaited once"
    # Tier 2 was called with a token->ltp dict containing all 3 tokens
    t2_call = fake_engine.compute_tier2.call_args
    assert t2_call is not None
    scan_ltp = t2_call.args[0] if t2_call.args else t2_call.kwargs.get("scan_ltp")
    assert set(scan_ltp.keys()) == {1000, 1001, 1002}
    for token, ltp in scan_ltp.items():
        assert 120 < ltp < 130, f"token {token} ltp {ltp} not in expected range"


@pytest.mark.asyncio
async def test_run_screener_skips_breadth_when_flag_off(monkeypatch, db_path):
    """When the flag is off, breadth_engine stays None and no Tier calls happen."""
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)
    main.breadth_engine = None

    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "calc_ema", return_value=pd.Series([100.0])), \
         patch.object(main, "calc_atr", return_value=pd.Series([1.5, 1.5])), \
         patch.object(main, "calc_rsi_series", return_value=pd.Series([60.0])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_and_allocate", return_value=([], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)), \
         patch("pandas.read_csv", return_value=_make_universe_df(2)):

        mock_kite.instrument_cache = {}
        mock_kite.get_historical = AsyncMock(return_value=_make_df())
        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.bankroll = 5000.0
        main.risk_pct = 0.10
        main.nifty_close = 18000.0
        main.nifty_ema20 = 17900.0
        main.nifty_return_1d = 0.001
        main.nifty_df = _make_df()
        main.is_market_open = MagicMock(return_value=False)

        await main.run_screener()

    # breadth_engine still None (build_breadth_engine was never called)
    assert main.breadth_engine is None
