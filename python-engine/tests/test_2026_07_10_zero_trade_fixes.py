"""
Tests for the 2026-07-10 zero-trade-day investigation fixes
(docs/post-mortem/2026-07-10-zero-trade-investigation.md, action items §6).

1. /momentum-signals serves the CUMULATIVE day list (momentum_signals_today),
   not the latest 15-min snapshot. The snapshot made the endpoint lossy:
   the agent's poll saw 3 of 17 accepted signals and the gateway EXEC
   callback failed for any signal wiped by a newer scan.
2. Day guard: before the first scan of a new day the endpoint serves [],
   never yesterday's list.
3. Penny 30s MIS tick gates to market hours (09:15-15:30 IST) --
   ~32k wasted evaluations/day happened off-hours on 2026-07-10.
"""
import datetime as dt
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import main as main_module
from config import settings
from main import app
from models import MomentumSignal
from performance import init_ledger
from position_tracker import init_positions_db


# ===============================================================
# FIXTURES
# ===============================================================

@pytest_asyncio.fixture
async def client(db_path, monkeypatch):
    """Async test client with initialised test DB (same shape as
    test_main_api.py's fixture)."""
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    await init_positions_db(db_path)
    await init_ledger(db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_momentum_signal(ticker: str, signal_time=None) -> MomentumSignal:
    return MomentumSignal(
        ticker=ticker,
        signal_time=signal_time or datetime.now(timezone.utc),
        close=100.0,
        vwap=99.5,
        prev_day_high=98.0,
        stop_loss=97.0,
        target_1=104.0,
        trailing_stop=98.5,
        shares=10,
        capital_deployed=1000.0,
        capital_at_risk=30.0,
        net_ev=45.0,
        cost_ratio=0.12,
        volume_ratio=2.4,
        product_type="MIS",
        strategy_version="test",
    )


# ===============================================================
# 1+2) /momentum-signals cumulative-for-the-day
# ===============================================================

class TestMomentumSignalsCumulativeEndpoint:

    @pytest.mark.asyncio
    async def test_serves_cumulative_day_list_not_snapshot(
        self, client, monkeypatch
    ):
        """Signals from EARLIER scans must stay visible even after a newer
        scan overwrote current_momentum_signals (the 2026-07-10 bug: only
        the latest snapshot was served, so 14 of 17 signals were never
        pollable and their EXEC buttons could never execute)."""
        today_ist = datetime.now(main_module.IST).date()
        early = _make_momentum_signal("COCHINSHIP")
        later = _make_momentum_signal("YESBANK")
        monkeypatch.setattr(
            main_module, "momentum_signals_today", [early, later]
        )
        # Latest scan accepted nothing -- old behavior would serve [].
        monkeypatch.setattr(main_module, "current_momentum_signals", [])
        monkeypatch.setattr(main_module, "last_momentum_date", today_ist)

        resp = await client.get("/momentum-signals")
        assert resp.status_code == 200
        body = resp.json()
        tickers = [s["ticker"] for s in body["signals"]]
        assert tickers == ["COCHINSHIP", "YESBANK"]
        assert body["latest_scan_signals"] == []

    @pytest.mark.asyncio
    async def test_day_guard_serves_empty_before_first_scan_of_day(
        self, client, monkeypatch
    ):
        """Before the first scan of a new day, momentum_signals_today still
        holds YESTERDAY's signals -- the endpoint must serve []."""
        yesterday = datetime.now(main_module.IST).date() - dt.timedelta(days=1)
        stale = _make_momentum_signal("HDFCBANK")
        monkeypatch.setattr(main_module, "momentum_signals_today", [stale])
        monkeypatch.setattr(main_module, "current_momentum_signals", [stale])
        monkeypatch.setattr(main_module, "last_momentum_date", yesterday)

        resp = await client.get("/momentum-signals")
        assert resp.status_code == 200
        assert resp.json()["signals"] == []

    @pytest.mark.asyncio
    async def test_stale_flag_set_on_old_cumulative_signals(
        self, client, monkeypatch
    ):
        """Cumulative signals older than 30 min must carry stale_data=True
        so consumers can see the entry levels have aged."""
        today_ist = datetime.now(main_module.IST).date()
        old_time = datetime.now(timezone.utc) - dt.timedelta(minutes=45)
        aged = _make_momentum_signal("IGL", signal_time=old_time)
        fresh = _make_momentum_signal("POLYMED")
        monkeypatch.setattr(
            main_module, "momentum_signals_today", [aged, fresh]
        )
        monkeypatch.setattr(main_module, "last_momentum_date", today_ist)

        resp = await client.get("/momentum-signals")
        by_ticker = {s["ticker"]: s for s in resp.json()["signals"]}
        assert by_ticker["IGL"]["stale_data"] is True
        assert by_ticker["POLYMED"]["stale_data"] is False


# ===============================================================
# 3) Penny 30s tick market-hours gate
# ===============================================================

class TestPennyMarketHoursGate:

    @pytest.mark.parametrize("hhmm,expected", [
        ((9, 14), False),    # last pre-open minute
        ((9, 15), True),     # open
        ((12, 0), True),     # mid-session
        ((15, 30), True),    # close (inclusive)
        ((15, 31), False),   # first post-close minute
        ((6, 30), False),    # the 2026-07-10 pre-market noise window
        ((20, 35), False),   # evening restart window
    ])
    def test_within_penny_market_hours_boundaries(self, hhmm, expected):
        hour, minute = hhmm
        now = datetime.now(main_module.IST).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        assert main_module._within_penny_market_hours(now) is expected

    @pytest.mark.asyncio
    async def test_scanner_tick_skips_off_hours_before_any_io(
        self, monkeypatch
    ):
        """Off-hours the tick must return BEFORE the calendar lookup and
        before building a scanner -- zero Kite/DB work."""
        monkeypatch.setattr(
            main_module, "_within_penny_market_hours", lambda _now: False
        )
        get_scanner = MagicMock(return_value=None)
        monkeypatch.setattr(main_module, "_get_penny_scanner", get_scanner)
        with patch("main.is_trading_day", new_callable=AsyncMock,
                   return_value=True) as mock_cal:
            await main_module.run_penny_scanner_once()
        mock_cal.assert_not_awaited()
        get_scanner.assert_not_called()

    @pytest.mark.asyncio
    async def test_scanner_tick_proceeds_in_hours(self, monkeypatch):
        """In-hours the gate must not over-block: the tick reaches the
        scanner factory (given calendar + token pass)."""
        monkeypatch.setattr(
            main_module, "_within_penny_market_hours", lambda _now: True
        )
        monkeypatch.setattr(main_module.kite, "access_token", "tok123")
        get_scanner = MagicMock(return_value=None)  # None: early exit after
        monkeypatch.setattr(main_module, "_get_penny_scanner", get_scanner)
        with patch("main.is_trading_day", new_callable=AsyncMock,
                   return_value=True):
            await main_module.run_penny_scanner_once()
        get_scanner.assert_called()
