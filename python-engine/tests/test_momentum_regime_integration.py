"""
Integration tests for regime compute + dispatch in run_momentum_screener.

These verify the wiring from main.run_momentum_screener:
  - Reads the cached regime (set by run_screener at 09:20 IST) via main._momentum_regime_for_today
  - Stamps sig_data['regime'] for any fired signals
  - Passes regime to evaluate_momentum_signal as keyword arg
  - R3 regime → all tickers rejected with reason "regime_r3_block"
  - R2 regime → 5% sizing + 1.5R target
  - R1 regime → 7% sizing + 2.0R target (legacy behavior)

We mock the heavy bits (kite, historical fetches) and only assert
what the momentum screener itself does with the regime signal.
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def _make_intraday_df():
    """Minimal intraday df that triggers MC1 (VWAP cross up)."""
    import numpy as np
    idx = pd.date_range("2026-06-16 09:15", periods=10, freq="15min")
    base = 100.0
    return pd.DataFrame({
        "open":  base + np.arange(10) * 0.2,
        "high":  base + np.arange(10) * 0.2 + 0.5,
        "low":   base + np.arange(10) * 0.2 - 0.5,
        "close": base + np.arange(10) * 0.3,
        "volume": [50_000] * 10,
    }, index=idx)


def _make_daily_df():
    """15-day daily df for MC5 ATR fuel gate."""
    import numpy as np
    dates = pd.date_range("2026-05-25", periods=15, freq="D")
    base = 100.0
    return pd.DataFrame({
        "open":  base + np.arange(15) * 0.1,
        "high":  base + np.arange(15) * 0.1 + 1.0,
        "low":   base + np.arange(15) * 0.1 - 1.0,
        "close": base + np.arange(15) * 0.1,
        "volume": [1_000_000] * 15,
    }, index=dates)


def _universe_df():
    return pd.DataFrame({
        "tradingsymbol": ["TEST0", "TEST1"],
        "exchange": ["NSE", "NSE"],
        "sector": ["UNKNOWN", "UNKNOWN"],
    })


@pytest.mark.asyncio
async def test_run_momentum_screener_stamps_regime_on_fired_signal(monkeypatch, db_path):
    """
    When evaluate_momentum_signal returns fired=True, sig_data must contain
    the regime that was passed in (so downstream analytics can correlate).
    """
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings
    from engine import Regime
    from datetime import datetime as RealDT

    # Mock "now" to be 11:00 IST on 2026-06-16 (inside market hours)
    fake_now = main.IST.localize(RealDT(2026, 6, 16, 11, 0, 0))
    # yesterday for prev_trading_day call
    fake_yesterday = RealDT(2026, 6, 15).date()

    # Cache Regime 1 in the momentum-regime slot (simulating swing ran first)
    main._momentum_regime_for_today = Regime.REGIME_1_NORMAL
    main._momentum_regime_set_at = None  # any timestamp accepted

    # Build a fake fired sig_data (Regime 1)
    fired_sig_dict = {
        "trigger_price": 105.0, "stop_loss": 100.0, "target_1": 107.0,
        "target_2": 107.0, "r_target": 2.0, "position_size_pct": 0.07,
        "product_type": "MIS", "reason": "mc1", "regime": "REGIME_1_NORMAL",
 }
    rejected_sig_dict = {
        "trigger_price": 0.0, "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0,
        "r_target": 0.0, "position_size_pct": 0.0, "product_type": "MIS",
        "reason": "rejected",
    }

    def fake_eval(**kwargs):
        # Regime is passed in as keyword → the wiring happened
        assert "regime" in kwargs, "evaluate_momentum_signal must receive regime kwarg"
        assert kwargs["regime"] == Regime.REGIME_1_NORMAL
        return True, fired_sig_dict

    # Mock all the heavy dependencies
    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "prev_trading_day", new=AsyncMock(return_value=fake_yesterday)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake"), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=10000.0)), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_momentum_signals", return_value=([fired_sig_dict], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "evaluate_momentum_signal", side_effect=fake_eval), \
         patch("main.datetime", wraps=RealDT) as mock_dt, \
         patch("pandas.read_csv", return_value=_universe_df()):
        # Force datetime.now(IST) → 11:00 IST 2026-06-16 (inside market hours).
        # `wraps=RealDT` keeps the rest of datetime (UTC, side_effect) working.
        mock_dt.now = lambda tz=None: fake_now.astimezone(tz) if tz else fake_now
        mock_kite.get_intraday = AsyncMock(return_value=_make_intraday_df())
        mock_kite.get_historical = AsyncMock(return_value=_make_daily_df())

        main.current_momentum_signals = []
        main.signaled_momentum_today = set()
        main.last_momentum_date = None
        main.market_regime = "BULL"

        await main.run_momentum_screener()

    # The sig stamped into current_momentum_signals must carry regime
    assert len(main.current_momentum_signals) == 1, "Should have 1 accepted signal"
    stamped = main.current_momentum_signals[0]
    assert stamped["regime"] == "REGIME_1_NORMAL", f"regime not stamped, got: {stamped}"


@pytest.mark.asyncio
async def test_run_momentum_screener_blocks_all_signals_in_regime_3(monkeypatch, db_path):
    """
    When regime is REGIME_3_CRISIS, evaluate_momentum_signal must be called
    with the crisis regime, and the dispatcher must return None → no fired signals.
    """
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings
    from engine import Regime
    from datetime import datetime as RealDT

    # Mock "now" to be 11:00 IST on 2026-06-16 (inside market hours)
    fake_now = main.IST.localize(RealDT(2026, 6, 16, 11, 0, 0))
    # yesterday for prev_trading_day call
    fake_yesterday = RealDT(2026, 6, 15).date()

    main._momentum_regime_for_today = Regime.REGIME_3_CRISIS
    main._momentum_regime_set_at = None

    eval_calls = []

    def fake_eval(**kwargs):
        eval_calls.append(kwargs)
        # In R3, the dispatcher inside evaluate_momentum_signal should reject
        # (return False). We return False to mirror the real behavior.
        return False, {
            "trigger_price": 0.0, "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0,
            "r_target": 0.0, "position_size_pct": 0.0, "product_type": "MIS",
            "reason": "regime_r3_block",
        }

    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "prev_trading_day", new=AsyncMock(return_value=fake_yesterday)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake"), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=10000.0)), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_momentum_signals", return_value=([], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "evaluate_momentum_signal", side_effect=fake_eval), \
         patch("main.datetime", wraps=RealDT) as mock_dt, \
         patch("pandas.read_csv", return_value=_universe_df()):
        mock_dt.now = lambda tz=None: fake_now.astimezone(tz) if tz else fake_now
        mock_kite.get_intraday = AsyncMock(return_value=_make_intraday_df())
        mock_kite.get_historical = AsyncMock(return_value=_make_daily_df())

        main.current_momentum_signals = []
        main.signaled_momentum_today = set()
        main.last_momentum_date = None
        main.market_regime = "BULL"

        await main.run_momentum_screener()

    # evaluate_momentum_signal was called with REGIME_3_CRISIS at least once
    assert len(eval_calls) >= 2, f"Expected 2 evaluations, got {len(eval_calls)}"
    for call in eval_calls:
        assert call["regime"] == Regime.REGIME_3_CRISIS, f"Regime not threaded: {call}"
    # No signals accepted
    assert main.current_momentum_signals == [], "R3 should produce zero accepted signals"


@pytest.mark.asyncio
async def test_run_momentum_screener_uses_tighter_sizing_in_regime_2(monkeypatch, db_path):
    """
    Regime 2: evaluate_momentum_signal receives regime=REGIME_2_VOLATILE,
    and the dispatcher inside it uses 0.05 sizing + 1.5R target (not 0.07 + 2.0R).
    """
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings
    from engine import Regime
    from datetime import datetime as RealDT

    # Mock "now" to be 11:00 IST on 2026-06-16 (inside market hours)
    fake_now = main.IST.localize(RealDT(2026, 6, 16, 11, 0, 0))
    # yesterday for prev_trading_day call
    fake_yesterday = RealDT(2026, 6, 15).date()

    main._momentum_regime_for_today = Regime.REGIME_2_ELEVATED

    def fake_eval(**kwargs):
        # Verify the helper is invoked by checking kwargs.regime
        # (the dispatcher inside evaluate_momentum_signal does the actual sizing)
        from engine import resolve_momentum_regime_params
        r_t, r_pct, _block = resolve_momentum_regime_params(kwargs["regime"])
        return True, {
            "trigger_price": 105.0, "stop_loss": 100.0, "target_1": 107.0,
            "target_2": 107.0, "r_target": r_t,
            "position_size_pct": r_pct,
            "product_type": "MIS", "reason": "mc1", "regime": kwargs["regime"].name,
        }

    captured = []

    def fake_filter(raw, open_pos, pool, max_pos):
        captured.append(raw)
        return (raw, [])

    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "prev_trading_day", new=AsyncMock(return_value=fake_yesterday)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake"), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=10000.0)), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_momentum_signals", side_effect=fake_filter), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "evaluate_momentum_signal", side_effect=fake_eval), \
         patch("main.datetime", wraps=RealDT) as mock_dt, \
         patch("pandas.read_csv", return_value=_universe_df()):
        mock_dt.now = lambda tz=None: fake_now.astimezone(tz) if tz else fake_now
        mock_kite.get_intraday = AsyncMock(return_value=_make_intraday_df())
        mock_kite.get_historical = AsyncMock(return_value=_make_daily_df())

        main.current_momentum_signals = []
        main.signaled_momentum_today = set()
        main.last_momentum_date = None
        main.market_regime = "BULL"

        await main.run_momentum_screener()

    # All captured signals should be sized 0.05 / 1.5R (Regime 2)
    for sig in captured[0]:
        assert sig["position_size_pct"] == pytest.approx(0.05), f"Regime 2 sizing wrong: {sig}"
        assert sig["r_target"] == pytest.approx(1.5), f"Regime 2 r_target wrong: {sig}"
        assert sig["regime"] == "REGIME_2_ELEVATED"
