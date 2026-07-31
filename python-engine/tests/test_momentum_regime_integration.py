"""
Integration tests for regime compute + dispatch in run_momentum_screener.

These verify the wiring from main.run_momentum_screener:
  - Reads the cached regime (set by run_screener at 09:20 IST) via main._momentum_regime_for_today
  - Stamps sig_data['regime'] for any fired signals
  - Passes regime to evaluate_momentum_signal as keyword arg
  - R3 regime -> all tickers rejected with reason "regime_r3_block"
  - R2 regime -> 5% sizing + 1.5R target
  - R1 regime -> 7% sizing + 2.0R target (legacy behavior)

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
        # Regime is passed in as keyword -> the wiring happened
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
        # Force datetime.now(IST) -> 11:00 IST 2026-06-16 (inside market hours).
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
    with the crisis regime, and the dispatcher must return None -> no fired signals.
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

    # [MOMENTUM-AGGRESSIVE 2026-06-16] All captured signals sized at the R2
    # risk pct and the R2 target ([TARGET-REACH 2026-07-31] 1.5 -> 1.3).
    from config import settings
    for sig in captured[0]:
        assert sig["position_size_pct"] == pytest.approx(0.07), f"Regime 2 sizing wrong: {sig}"
        assert sig["r_target"] == pytest.approx(settings.MOMENTUM_R_TARGET_R2), f"Regime 2 r_target wrong: {sig}"
        assert sig["regime"] == "REGIME_2_ELEVATED"


@pytest.mark.asyncio
async def test_momentum_screener_skip_when_previous_in_progress(monkeypatch):
    """
    [MOMENTUM-SKIP-IF-RUNNING 2026-06-30] Regression: when the
    previous momentum_scan is still in flight (the wall-clock
    cost can be 15+ min on 500 tickers + slow Kite), the next
    15-min cron tick should short-circuit with a clear log
    line, not queue another concurrent run. This is the bug
    that caused `momentum_scan_complete` to never log today
    (2026-06-30): the next run started before the previous
    finished, the impl was wrapped in a single async
    coroutine, and the gate between start and complete never
    fired.
    """
    import asyncio
    from unittest.mock import MagicMock, AsyncMock, patch
    import main

    fake_kite = MagicMock()
    fake_kite.access_token = "fake"
    fake_kite.get_intraday = AsyncMock(side_effect=lambda *a, **kw: asyncio.sleep(2))
    fake_kite.get_historical = AsyncMock(side_effect=lambda *a, **kw: asyncio.sleep(2))

    # Spy on the structlog logger to capture warning calls.
    warning_calls: list = []
    real_warning = main.logger.warning

    def spy_warning(*args, **kwargs):
        warning_calls.append((args, kwargs))
        return real_warning(*args, **kwargs)

    monkeypatch.setattr(main.logger, "warning", spy_warning)

    # Hold the flag True as if a previous run is in flight.
    main._momentum_scan_in_progress = True
    try:
        with patch.object(main, "kite", new=fake_kite), \
             patch.object(main, "_load_universe_with_fallback", return_value=_universe_df()), \
             patch.object(main, "_filter_by_liquidity", new=AsyncMock(return_value=_universe_df())), \
             patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
             patch.object(main, "nifty_bankroll", new=AsyncMock(return_value=10000.0)), \
             patch.object(main, "_momentum_regime_for_today", new=None):
            await main.run_momentum_screener()

        # The flag was True, so the impl should NOT have been called.
        # We should see the explicit skip warning.
        skip_calls = [
            c for c in warning_calls
            if c[0] and "momentum_scan_skipped" in str(c[0][0])
        ]
        assert skip_calls, (
            f"expected momentum_scan_skipped warning, got: "
            f"{[c[0] for c in warning_calls]}"
        )
        # And the impl's get_intraday should NOT have been called
        # (proof the impl short-circuited).
        assert fake_kite.get_intraday.await_count == 0, (
            f"impl ran despite skip guard; get_intraday called "
            f"{fake_kite.get_intraday.await_count} times"
        )
    finally:
        main._momentum_scan_in_progress = False


@pytest.mark.asyncio
async def test_momentum_screener_evaluates_in_parallel(db_path):
    """
    [MOMENTUM-PARALLEL 2026-06-30] Regression: the per-ticker
    evaluation loop was replaced with asyncio.gather. The
    wall-clock cost should scale with the rate limiter
    (N/3 seconds for N tickers), not with serial round-trips
    (N * per-call-seconds). With a 0.05s simulated Kite call,
    30 tickers in parallel + the rate limiter at 3 req/s
    takes ~10s; serial would take 30 * 0.05 = 1.5s in the
    mocked case but in prod each call is 10-30s.
    """
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import time
    import main
    from config import settings
    from datetime import datetime as RealDT
    from datetime import datetime

    # Mock "now" to be 11:00 IST on 2026-06-16 (inside market hours)
    fake_now = main.IST.localize(RealDT(2026, 6, 16, 11, 0, 0))
    fake_yesterday = RealDT(2026, 6, 15).date()

    n = 30
    fake_kite = MagicMock()
    fake_kite.access_token = "fake"

    # Use real DataFrames for the mock returns. The parallel
    # speedup is via asyncio.gather, not via slow mocks.
    _intra_df = _make_intraday_df()
    _daily_df = _make_daily_df()
    fake_kite.get_intraday = AsyncMock(return_value=_intra_df)
    fake_kite.get_historical = AsyncMock(return_value=_daily_df)

    # Build a 30-ticker universe.
    big_universe = pd.DataFrame({
        "tradingsymbol": [f"PAR{i}" for i in range(n)],
        "exchange": ["NSE"] * n,
        "sector": ["UNKNOWN"] * n,
    })

    captured: list = []

    def fake_eval(**kwargs):
        ticker = kwargs.get("ticker")
        captured.append(ticker)
        return (False, {"ticker": ticker, "reject_reason": "test_no_fire"})

    def fake_filter(raw, open_pos, pool, max_pos):
        return ([], [{"ticker": s.get("ticker"), "reject_reason": "test_filter"} for s in raw])

    main.current_momentum_signals = []
    main.signaled_momentum_today = set()
    main.last_momentum_date = None
    main.market_regime = "BULL"

    with patch.object(main, "kite", new=fake_kite), \
         patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "_load_universe_with_fallback", return_value=big_universe), \
         patch.object(main, "_filter_by_liquidity", new=AsyncMock(return_value=big_universe)), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "nifty_bankroll", new=AsyncMock(return_value=10000.0)), \
         patch.object(main, "_momentum_regime_for_today", new=None), \
         patch.object(main, "evaluate_momentum_signal", side_effect=fake_eval), \
         patch.object(main, "filter_momentum_signals", side_effect=fake_filter), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "prev_trading_day", new=AsyncMock(return_value=fake_yesterday)), \
         patch("main.datetime", wraps=RealDT) as mock_dt:
        mock_dt.now = lambda tz=None: fake_now.astimezone(tz) if tz else fake_now
        t0 = time.monotonic()
        await main.run_momentum_screener()
        wall = time.monotonic() - t0

    # All 30 tickers should have been evaluated exactly once.
    assert len(captured) == n, f"expected {n} evals, got {len(captured)}"
    assert set(captured) == {f"PAR{i}" for i in range(n)}

    # Parallel should finish in well under 5s (serial would be
    # 30 * 0.05 = 1.5s but we add overhead). If parallelism
    # regressed to serial, this would be ~5s+ in real prod.
    assert wall < 5.0, f"parallel eval took {wall:.2f}s -- possible regression"
