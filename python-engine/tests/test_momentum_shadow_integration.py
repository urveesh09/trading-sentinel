from datetime import datetime as RealDateTime
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pandas as pd
import pytest


def _universe():
    return pd.DataFrame({
        "tradingsymbol": ["AAA", "BBB"],
        "exchange": ["NSE", "NSE"],
        "sector": ["ONE", "TWO"],
    })


def _intra():
    index = pd.date_range("2026-08-10 09:15", periods=6, freq="15min")
    return pd.DataFrame({
        "open": [99, 100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105, 106],
        "low": [98, 99, 100, 101, 102, 103],
        "close": [100, 101, 102, 103, 104, 105],
        "volume": [100, 100, 100, 100, 100, 300],
    }, index=index)


def _daily():
    index = pd.date_range("2026-07-15", periods=20, freq="D")
    return pd.DataFrame({
        "open": [100.0] * 20,
        "high": [102.0] * 20,
        "low": [98.0] * 20,
        "close": [100.0] * 20,
        "volume": [10000.0] * 20,
    }, index=index)


def _shadow_rows(ticker, bar_ts):
    return [{
        "trading_date": "2026-08-10",
        "ticker": ticker,
        "bar_ts": str(bar_ts),
        "variant": variant,
        "accepted": variant == "MOM_BASE",
        "reject_reason": None if variant == "MOM_BASE" else "candidate_reject",
        "features": {"close": 105.0},
        "config": {"name": variant},
        "decision": ({"entry_price": 105.0, "stop_loss": 100.0,
                      "target_1": 110.0, "shares": 5}
                     if variant == "MOM_BASE" else {}),
        "dataset_fingerprint": f"sha256:{ticker.lower()}",
        "bars": [{"bar_ts": str(bar_ts), "open": 104, "high": 106,
                  "low": 103, "close": 105}],
    } for variant in ("MOM_BASE", "MOM_RECENCY_5")]


async def _run_scan(main, monkeypatch, shadow_enabled, shadow_side_effect=None):
    fake_now = main.IST.localize(RealDateTime(2026, 8, 10, 11, 0, 0))
    fake_kite = MagicMock()
    fake_kite.access_token = "fake"
    fake_kite.get_intraday = AsyncMock(return_value=_intra())
    fake_kite.get_historical = AsyncMock(return_value=_daily())

    def baseline_eval(**kwargs):
        if kwargs["ticker"] == "AAA":
            return True, {
                "trigger_price": 105.0, "stop_loss": 100.0,
                "target_1": 110.0, "reason": "accepted",
            }
        return False, {"reject_reason": "baseline_reject"}

    def shadow_eval(**kwargs):
        if shadow_side_effect is not None:
            return shadow_side_effect(**kwargs)
        return _shadow_rows(kwargs["ticker"], kwargs["bar_ts"])

    captured = {}

    def filter_signals(raw, open_positions, pool, maximum):
        captured["raw"] = [dict(item) for item in raw]
        return raw, [{"ticker": "POST", "reject_reason": "portfolio_reject"}]

    notify = AsyncMock()
    monkeypatch.setattr(main.settings, "MOMENTUM_SHADOW_ENABLED", shadow_enabled)
    monkeypatch.setattr(main.settings, "MOMENTUM_LOG_ENABLED", False)
    main.current_momentum_signals = []
    main.signaled_momentum_today = set()
    main.momentum_signals_today = []
    main.last_momentum_date = None
    main._momentum_scan_in_progress = False
    main.market_regime = "BULL"

    with patch.object(main, "kite", fake_kite), \
         patch.object(main, "is_trading_day", new=AsyncMock(return_value=True)), \
         patch.object(main, "prev_trading_day", new=AsyncMock(return_value=RealDateTime(2026, 8, 7).date())), \
         patch.object(main, "_load_universe_with_fallback", return_value=_universe()), \
         patch.object(main, "_filter_by_liquidity", new=AsyncMock(return_value=_universe())), \
         patch.object(main, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(main, "nifty_bankroll", new=AsyncMock(return_value=10000.0)), \
         patch.object(main, "evaluate_momentum_signal", side_effect=baseline_eval), \
         patch.object(main, "evaluate_momentum_shadows", side_effect=shadow_eval) as shadow_mock, \
         patch.object(main, "filter_momentum_signals", side_effect=filter_signals), \
         patch.object(main, "notify_screener_results", notify), \
         patch.object(main, "is_market_open", return_value=True), \
         patch("main.datetime", wraps=RealDateTime) as mock_dt:
        mock_dt.now = lambda tz=None: fake_now.astimezone(tz) if tz else fake_now
        await main.run_momentum_screener()

    captured["accepted"] = [dict(item) for item in main.current_momentum_signals]
    captured["rejected"] = [dict(item) for item in notify.await_args.args[2]]
    captured["intraday_calls"] = fake_kite.get_intraday.await_count
    captured["historical_calls"] = fake_kite.get_historical.await_count
    captured["shadow_calls"] = shadow_mock.call_args_list
    # Avoid leaking the synthetic dict signals into route tests that expect
    # the production Signal model stored in this process-global day cache.
    main.current_momentum_signals = []
    main.momentum_signals_today = []
    main.signaled_momentum_today = set()
    main.last_momentum_date = None
    return captured


@pytest.mark.asyncio
async def test_shadow_on_off_preserves_baseline_and_adds_no_market_calls(monkeypatch, db_path):
    import main

    off = await _run_scan(main, monkeypatch, False)
    on = await _run_scan(main, monkeypatch, True)

    assert on["accepted"] == off["accepted"]
    assert on["rejected"] == off["rejected"]
    assert (on["intraday_calls"], on["historical_calls"]) == (2, 2)
    assert (off["intraday_calls"], off["historical_calls"]) == (2, 2)
    assert len(off["shadow_calls"]) == 0
    assert len(on["shadow_calls"]) == 2
    for call in on["shadow_calls"]:
        assert call.kwargs["vol_surge_threshold"] == main.settings.MOMENTUM_VOL_SURGE_PCT
        assert call.kwargs["market_regime"] == "BULL"
        assert call.kwargs["trading_date"].isoformat() == "2026-08-10"
        assert call.kwargs["bar_ts"] == _intra().index[-1]


@pytest.mark.asyncio
async def test_repeat_scan_persistence_is_idempotent(monkeypatch, db_path):
    import main

    await _run_scan(main, monkeypatch, True)
    await _run_scan(main, monkeypatch, True)
    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_evaluations"
        )).fetchone())[0]
        trade_count = (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_trades"
        )).fetchone())[0]
    assert count == 4
    assert trade_count == 2


@pytest.mark.asyncio
async def test_candidate_failure_isolated_from_baseline(monkeypatch, db_path):
    import main

    def one_candidate_fails(**kwargs):
        if kwargs["ticker"] == "AAA":
            raise RuntimeError("candidate exploded")
        return _shadow_rows(kwargs["ticker"], kwargs["bar_ts"])

    result = await _run_scan(main, monkeypatch, True, one_candidate_fails)
    assert [row["ticker"] for row in result["accepted"]] == ["AAA"]
    assert {row["ticker"] for row in result["rejected"]} == {"BBB", "POST"}
    async with aiosqlite.connect(db_path) as db:
        tickers = [row[0] for row in await (await db.execute(
            "SELECT DISTINCT ticker FROM momentum_shadow_evaluations"
        )).fetchall()]
    assert tickers == ["BBB"]


@pytest.mark.asyncio
async def test_single_persistence_failure_isolated_from_baseline(monkeypatch, db_path):
    import main

    persist = AsyncMock(side_effect=RuntimeError("disk unavailable"))
    with patch.object(main, "persist_momentum_shadow_results", persist):
        result = await _run_scan(main, monkeypatch, True)

    assert [row["ticker"] for row in result["accepted"]] == ["AAA"]
    assert {row["ticker"] for row in result["rejected"]} == {"BBB", "POST"}
    persist.assert_awaited_once()
    persisted_rows = persist.await_args.args[1]
    assert len(persisted_rows) == 4
