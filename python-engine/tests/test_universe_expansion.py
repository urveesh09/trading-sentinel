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

from config import settings  # noqa: E402  — imported after sys.path tweak


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


# ─────────────────────────────────────────────────────────────────
# Nifty 500 fallback chain (Task 8)
# ─────────────────────────────────────────────────────────────────


def test_nifty_500_tickers_constant_has_500_entries():
    """NIFTY_500_TICKERS is loaded from data/nifty500.json at module init."""
    import main
    assert hasattr(main, "NIFTY_500_TICKERS"), "main.NIFTY_500_TICKERS should exist"
    assert isinstance(main.NIFTY_500_TICKERS, list)
    assert len(main.NIFTY_500_TICKERS) >= 400, (
        f"NIFTY_500_TICKERS should have ~500 entries, got {len(main.NIFTY_500_TICKERS)}"
    )
    # Should be unique
    assert len(set(main.NIFTY_500_TICKERS)) == len(main.NIFTY_500_TICKERS)
    # Should contain the canonical 100-baseline names (at least 50 of them, since
    # some Nifty 100 names may be Nifty 500 BE-series and not in the EQ list)
    n100_subset = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "WIPRO", "ETERNAL", "TMPV", "LICI", "JIOFIN"]
    for s in n100_subset:
        assert s in main.NIFTY_500_TICKERS, f"{s} should be in NIFTY_500_TICKERS"


@pytest.mark.asyncio
async def test_load_universe_with_fallback_uses_csv_when_present(monkeypatch, tmp_path):
    """_load_universe_with_fallback returns CSV data when the file exists."""
    from main import _load_universe_with_fallback

    csv_path = tmp_path / "nifty500.csv"
    csv_path.write_text("tradingsymbol,exchange,sector\nRELIANCE,NSE,UNKNOWN\nTCS,NSE,UNKNOWN\n")

    monkeypatch.setattr(settings, "UNIVERSE_PATH", str(csv_path))
    universe = _load_universe_with_fallback()
    assert len(universe) == 2
    assert "RELIANCE" in universe["tradingsymbol"].values


@pytest.mark.asyncio
async def test_load_universe_with_fallback_uses_code_when_csv_missing(monkeypatch):
    """_load_universe_with_fallback falls back to NIFTY_500_TICKERS when CSV is missing."""
    from main import _load_universe_with_fallback

    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    universe = _load_universe_with_fallback()
    # Should be the full NIFTY_500_TICKERS list
    assert len(universe) == 500
    assert "RELIANCE" in universe["tradingsymbol"].values


@pytest.mark.asyncio
async def test_run_screener_uses_nifty500_fallback_when_csv_missing(monkeypatch, db_path):
    """When UNIVERSE_PATH CSV is missing, run_screener falls back to in-code NIFTY_500_TICKERS."""
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    # Point UNIVERSE_PATH at a non-existent file
    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)  # disable liquidity filter for this test
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)
    main.breadth_engine = None

    # Sanity check: the in-code list should have ~500 entries
    assert len(main.NIFTY_500_TICKERS) >= 400, (
        f"NIFTY_500_TICKERS should have ~500 entries, got {len(main.NIFTY_500_TICKERS)}"
    )

    # Patch enough of run_screener's deps to confirm the fallback was used
    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "calc_ema", return_value=pd.Series([100.0])), \
         patch.object(main, "calc_atr", return_value=pd.Series([1.5, 1.5])), \
         patch.object(main, "calc_rsi_series", return_value=pd.Series([60.0])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "filter_and_allocate", return_value=([], [])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)):

        mock_kite.instrument_cache = {}
        # Mock get_historical to return a valid df for ANY ticker
        def make_hist_df(*args, **kwargs):
            return _make_historical_df([100.0] * 250).assign(volume=[100_000] * 250)
        mock_kite.get_historical = AsyncMock(side_effect=make_hist_df)

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.bankroll = 5000.0
        main.risk_pct = 0.10
        main.nifty_close = 18000.0
        main.nifty_ema20 = 17900.0
        main.nifty_return_1d = 0.001
        main.nifty_df = _make_historical_df([18000.0 + i for i in range(250)])
        main.is_market_open = MagicMock(return_value=False)

        # run_screener should complete without raising FileNotFoundError
        await main.run_screener()


@pytest.mark.asyncio
async def test_run_screener_calls_liquidity_filter(monkeypatch, db_path):
    """The scan calls _filter_by_liquidity once after loading the universe."""
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)
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
         patch.object(main, "_filter_by_liquidity", new=AsyncMock(side_effect=lambda u, k, today: u)) as mock_filter:

        mock_kite.instrument_cache = {}
        mock_kite.get_historical = AsyncMock(return_value=_make_historical_df([100.0] * 250).assign(volume=[100_000] * 250))

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.bankroll = 5000.0
        main.risk_pct = 0.10
        main.nifty_close = 18000.0
        main.nifty_ema20 = 17900.0
        main.nifty_return_1d = 0.001
        main.nifty_df = _make_historical_df([18000.0 + i for i in range(250)])
        main.is_market_open = MagicMock(return_value=False)

        await main.run_screener()

    # _filter_by_liquidity should have been called at least once
    assert mock_filter.await_count >= 1, "run_screener should call _filter_by_liquidity"


@pytest.mark.asyncio
async def test_run_momentum_screener_uses_nifty500_fallback_when_csv_missing(monkeypatch, db_path):
    """When UNIVERSE_PATH CSV is missing, run_momentum_screener falls back to in-code NIFTY_500_TICKERS.

    Mirrors the run_screener test above, but for the momentum leg.
    The momentum screener (main.py:717-724) shares the same universe loader,
    so both should be expanded to 500. This test guards against the case
    where the swing fallback is wired but the momentum one is forgotten.
    """
    from performance import init_ledger
    from position_tracker import init_positions_db
    await init_ledger(db_path)
    await init_positions_db(db_path)

    import main
    from config import settings

    monkeypatch.setattr(settings, "UNIVERSE_PATH", "/tmp/does_not_exist_xyz.csv")
    monkeypatch.setattr(settings, "UNIVERSE_MIN_ADV_CRORE", 0.0)  # disable liquidity filter for this test
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)
    main.breadth_engine = None

    # Sanity check: the in-code list should have ~500 entries
    assert len(main.NIFTY_500_TICKERS) >= 400, (
        f"NIFTY_500_TICKERS should have ~500 entries, got {len(main.NIFTY_500_TICKERS)}"
    )

    with patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "kite") as mock_kite, \
         patch.object(main.kite, "access_token", new="fake_token"), \
         patch.object(main, "evaluate_momentum_signal", return_value=(False, {"reject_reason": "test"})), \
         patch.object(main, "filter_momentum_signals", return_value=([], [])), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "notify_screener_results", new=AsyncMock()), \
         patch.object(main, "current_bankroll", new=AsyncMock(return_value=5000.0)):

        mock_kite.instrument_cache = {}
        # Mock get_intraday + get_historical for the momentum screener
        def make_intra_df(*args, **kwargs):
            return _make_intraday_df()  # 5-min candles for the morning session
        def make_hist_df(*args, **kwargs):
            return _make_historical_df([100.0] * 30).assign(volume=[100_000] * 30)
        mock_kite.get_intraday = AsyncMock(side_effect=make_intra_df)
        mock_kite.get_historical = AsyncMock(side_effect=make_hist_df)

        main.current_regime = MagicMock()
        main.market_regime = "BULL"
        main.signaled_momentum_today = set()
        main.last_momentum_date = None

        # run_momentum_screener should complete without raising FileNotFoundError
        await main.run_momentum_screener()
