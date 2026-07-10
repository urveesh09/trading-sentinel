"""
test_penny_audit_phase3_fixes.py — Regression tests for the Phase-3 audit
findings (2026-07-09 deep audit: 215,814 lifetime evaluations, zero accepts).

These tests guard against:
  * Bug #1 — unsatisfiable breakout anchor: the scanner passed the live
    quote's running day high (which includes the breakout bar itself) as
    the anchor, so `close > day_high * 1.003` could never be true. The
    anchor must be the max high of the bars STRICTLY BEFORE the breakout
    bar.
  * Bug #2 — volume gate compared running cumulative volume against the
    FULL-DAY 20-day median (demanding ~9x pace at window open). With
    PENNY_BREAKOUT_RVOL_TIME_ADJUSTED the median is scaled by session
    fraction elapsed.
  * Bug #3 — RSI(14) overbought ceiling hardcoded at 70 rejected the very
    breakouts the strategy exists to catch; now PENNY_BREAKOUT_RSI_MAX.
  * Bug #4 — no-token guards: penny scans must skip (like the swing and
    momentum screeners) when kite.access_token is empty, instead of
    firing thousands of doomed HTTP 400 calls (2026-07-09 incident).
  * Bug #5 — token persistence: POST /token now persists the token with
    an IST date stamp; startup restores it ONLY same-day.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from penny_engine_breakout import evaluate_breakout_entry
from penny_risk import PennyRiskEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_risk_engine(bankroll=100_000.0):
    re = PennyRiskEngine(bankroll=bankroll, ledger_writer=MagicMock())
    re.daily_pnl = 0.0
    re.daily_pnl_date = datetime.now().date().isoformat()
    return re


def _stub_settings(monkeypatch, **overrides):
    from config import settings
    defaults = dict(
        PENNY_BREAKOUT_VOL_MULT=1.8,
        PENNY_BREAKOUT_TARGET_R=2.0,
        PENNY_BREAKOUT_BUFFER_PCT=0.003,
        PENNY_BREAKOUT_TIME_START=10 * 60 + 30,
        PENNY_BREAKOUT_TIME_END=14 * 60 + 30,
        PENNY_BREAKOUT_USE_VWAP=False,
        PENNY_BREAKOUT_ADAPTIVE_THRESHOLD=False,
        PENNY_BREAKOUT_RVOL_TIME_ADJUSTED=True,
        PENNY_BREAKOUT_RSI_MAX=70.0,
        PENNY_PER_STOCK_CAP=200_000.0,
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        monkeypatch.setattr(settings, k, v, raising=False)


def _eval(monkeypatch, *, close, day_high, rsi_14=50.0, cum_vol=1_000_000,
          median_vol=100_000, as_of=None, **settings_overrides):
    _stub_settings(monkeypatch, **settings_overrides)
    as_of = as_of or datetime(2026, 7, 9, 12, 0)  # inside 10:30-14:30
    bar = {"close": close, "low": close * 0.99, "high": close * 1.001,
           "volume": 50_000}
    return evaluate_breakout_entry(
        ticker="TST", cum_vol_today=cum_vol, median_vol_20d=median_vol,
        breakout_bar=bar, day_high=day_high, rsi_14=rsi_14,
        as_of=as_of, risk_engine=_make_risk_engine(),
    )


# ---------------------------------------------------------------------------
# Bug #1 — scanner must anchor on the PRIOR bars' high, not the running
# day high from the quote
# ---------------------------------------------------------------------------

class TestBreakoutAnchor:
    def _make_scanner(self, tmp_path, monkeypatch, *, prior_high, bar_close,
                      quote_day_high, cum_vol=1_000_000):
        """Scanner whose fake kite reproduces the killing configuration:
        the quote's running day high already includes the breakout bar,
        while the PRIOR bars' max high is lower than the bar close."""
        import pandas as pd
        from config import settings
        from penny_scanner import PennyScanner

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "t.db"))
        monkeypatch.setattr(
            settings, "PENNY_LOG_CSV_PATH", str(tmp_path / "sig.csv"), raising=False)
        _stub_settings(monkeypatch)

        k = MagicMock()
        k.instrument_cache = {"AAA": 1001}
        k.get_quote = AsyncMock(return_value={
            1001: {"last_price": bar_close,
                   "ohlc": {"high": quote_day_high, "low": prior_high * 0.97,
                            "close": bar_close},
                   "volume": cum_vol},
        })

        # 40 prior bars capped at prior_high, then the breakout bar that
        # closes ABOVE prior_high (this is what a real breakout looks
        # like). All bars are complete (index ends before as_of minute).
        def _fake_intraday(ticker, from_datetime, to_datetime, interval="minute"):
            times = pd.date_range("2026-07-09 09:15", periods=41, freq="1min")
            highs = [prior_high] * 40 + [bar_close * 1.001]
            # Oscillating prior closes (not flat) so RSI(14) stays
            # mid-range -- a flat series then one jump reads RSI=100
            # and would trip the overbought gate instead of exercising
            # the anchor logic under test. The swing amplitude must be
            # comparable to the final breakout move, otherwise the last
            # bar's gain dominates the Wilder averages and RSI still
            # creeps above the 70 ceiling.
            closes = [
                prior_high * (0.96 if i % 2 == 0 else 1.0)
                for i in range(40)
            ] + [bar_close]
            return pd.DataFrame({
                "open": closes, "high": highs,
                "low": [c * 0.99 for c in closes], "close": closes,
                "volume": [25_000] * 41,
            }, index=pd.DatetimeIndex(times, name="datetime"))

        k.get_intraday = AsyncMock(side_effect=_fake_intraday)

        def _fake_historical(ticker, from_date, to_date):
            dates = pd.date_range(end="2026-07-08", periods=20, freq="D")
            return pd.DataFrame({
                "open": [10.0] * 20, "high": [10.5] * 20, "low": [9.5] * 20,
                "close": [10.0] * 20, "volume": [100_000] * 20,
            }, index=pd.DatetimeIndex(dates, name="date"))

        k.get_historical = AsyncMock(side_effect=_fake_historical)

        import json
        universe_path = tmp_path / "penny_static.json"
        universe_path.write_text(json.dumps({
            "as_of": "2026-07-09", "universe_size_target": 100,
            "tickers": [{
                "symbol": "AAA", "series": "EQ", "prev_close": 10.0,
                "promoter_holding_pct": 50.0, "pb_ratio": 1.2,
                "is_t2t": False, "is_asm": False, "is_gsm": False,
                "median_traded_value_20d": 1_000_000,
            }],
        }))
        s = PennyScanner(
            kite=k, universe_json_path=str(universe_path),
            paper_mode=True, regime="PR1_CALM",
        )
        s.risk_engine = _make_risk_engine()
        return s

    def test_breakout_accepted_when_close_exceeds_prior_bars_high(
            self, tmp_path, monkeypatch):
        """THE 215,814-rejects regression. close=10.30 > prior_high=10.00
        * 1.003, but the quote's running day high (10.31, includes the
        breakout bar) would make the gate unsatisfiable. Pre-fix this
        was a reject; post-fix it must accept."""
        s = self._make_scanner(tmp_path, monkeypatch, prior_high=10.00,
                               bar_close=10.30, quote_day_high=10.31)
        decision = asyncio.run(s._evaluate_ticker_breakout(
            "AAA", as_of=datetime(2026, 7, 9, 12, 0)))
        assert decision is not None
        assert decision.get("accept") is True, (
            f"Breakout close 10.30 above prior-bars high 10.00 must be "
            f"accepted; got reject_reason={decision.get('reject_reason')!r}. "
            f"If this reads 'breakout not confirmed (close 10.30 <= 10.34)' "
            f"the scanner is anchoring on the quote's running day high again."
        )
        # The anchor the engine used must be the prior-bars high.
        assert decision.get("anchor") == pytest.approx(10.00), (
            f"anchor should be the prior bars' max high (10.00), got "
            f"{decision.get('anchor')}"
        )

    def test_breakout_rejected_when_close_below_prior_high_buffer(
            self, tmp_path, monkeypatch):
        """Sanity: a bar that does NOT clear prior_high * 1.003 stays
        rejected (the fix must not turn the gate into a pass-through)."""
        s = self._make_scanner(tmp_path, monkeypatch, prior_high=10.00,
                               bar_close=10.01, quote_day_high=10.02)
        decision = asyncio.run(s._evaluate_ticker_breakout(
            "AAA", as_of=datetime(2026, 7, 9, 12, 0)))
        assert decision is not None
        assert decision.get("accept") is False
        assert "breakout not confirmed" in decision.get("reject_reason", "")


# ---------------------------------------------------------------------------
# Bug #2 — time-of-day-adjusted relative volume
# ---------------------------------------------------------------------------

class TestTimeAdjustedRVOL:
    def test_morning_pace_passes_with_time_adjustment(self, monkeypatch):
        """10:35 IST: 80 of 375 session minutes elapsed (21.3%). A stock
        that has already traded 50% of its full-day median volume is
        running at ~2.3x pace -- must PASS the 1.8x gate. Pre-fix it was
        rejected (50k < 1.8 * 100k)."""
        r = _eval(monkeypatch, close=10.30, day_high=10.00,
                  cum_vol=50_000, median_vol=100_000,
                  as_of=datetime(2026, 7, 9, 10, 35))
        assert "volume" not in (r.get("reject_reason") or ""), (
            f"time-adjusted RVOL should pass 50k vs 21.3%-scaled median; "
            f"got {r.get('reject_reason')!r}"
        )

    def test_slow_tape_still_rejected_with_time_adjustment(self, monkeypatch):
        """Same clock, but volume merely at normal pace (21% of median
        traded at 21% of session) must still be rejected -- 1.0x != 1.8x."""
        r = _eval(monkeypatch, close=10.30, day_high=10.00,
                  cum_vol=21_000, median_vol=100_000,
                  as_of=datetime(2026, 7, 9, 10, 35))
        assert r.get("accept") is False
        assert "volume" in r.get("reject_reason", "")

    def test_flag_off_restores_full_day_comparison(self, monkeypatch):
        """PENNY_BREAKOUT_RVOL_TIME_ADJUSTED=False keeps pre-fix
        behaviour: 50k < 1.8x full-day 100k median -> reject."""
        r = _eval(monkeypatch, close=10.30, day_high=10.00,
                  cum_vol=50_000, median_vol=100_000,
                  as_of=datetime(2026, 7, 9, 10, 35),
                  PENNY_BREAKOUT_RVOL_TIME_ADJUSTED=False)
        assert r.get("accept") is False
        assert "volume" in r.get("reject_reason", "")

    def test_zero_median_still_rejected(self, monkeypatch):
        r = _eval(monkeypatch, close=10.30, day_high=10.00,
                  cum_vol=50_000, median_vol=0)
        assert r.get("accept") is False
        assert "volume" in r.get("reject_reason", "")


# ---------------------------------------------------------------------------
# Bug #3 — configurable RSI ceiling
# ---------------------------------------------------------------------------

class TestRsiCeiling:
    """The ceiling is now PENNY_BREAKOUT_RSI_MAX (was hardcoded 70).
    Default stays 70: the penny_backtest_v2 sweep showed loosening to 80
    was net-negative on daily bars. The setting exists so the operator
    can experiment via .env once an intraday backtest justifies it."""

    def test_rsi_75_rejected_with_default_ceiling_70(self, monkeypatch):
        r = _eval(monkeypatch, close=10.30, day_high=10.00, rsi_14=75.0)
        assert r.get("accept") is False
        assert "overbought" in r.get("reject_reason", "")

    def test_ceiling_is_configurable_upward(self, monkeypatch):
        """Raising the ceiling via config admits RSI 75 without a code
        change -- this is the knob the backtest sweep will tune."""
        r = _eval(monkeypatch, close=10.30, day_high=10.00, rsi_14=75.0,
                  PENNY_BREAKOUT_RSI_MAX=80.0)
        assert r.get("accept") is True, (
            f"RSI 75 < configured ceiling 80 must pass; got "
            f"{r.get('reject_reason')!r}"
        )

    def test_rsi_above_configured_ceiling_rejected(self, monkeypatch):
        r = _eval(monkeypatch, close=10.30, day_high=10.00, rsi_14=85.0,
                  PENNY_BREAKOUT_RSI_MAX=80.0)
        assert r.get("accept") is False
        assert "overbought" in r.get("reject_reason", "")


# ---------------------------------------------------------------------------
# Bug #4 — no-token guards on all three penny cron entry points
# ---------------------------------------------------------------------------

class TestNoTokenGuards:
    @pytest.mark.asyncio
    async def test_penny_scanner_once_skips_without_token(self, monkeypatch):
        """2026-07-09 incident: with kite.access_token empty the 30s MIS
        scan must skip like the momentum/swing screeners do -- NOT build
        a scanner and fire doomed quote calls."""
        import main as main_module

        monkeypatch.setattr(main_module.kite, "access_token", "")
        get_scanner = MagicMock(return_value=None)
        monkeypatch.setattr(main_module, "_get_penny_scanner", get_scanner)
        with patch("main.is_trading_day", new_callable=AsyncMock,
                   return_value=True):
            await main_module.run_penny_scanner_once()
        get_scanner.assert_not_called()

    @pytest.mark.asyncio
    async def test_penny_connors_scan_skips_without_token(self, monkeypatch):
        import main as main_module

        monkeypatch.setattr(main_module.kite, "access_token", "")
        get_scanner = MagicMock(return_value=None)
        monkeypatch.setattr(main_module, "_get_penny_scanner", get_scanner)
        with patch("main.is_trading_day", new_callable=AsyncMock,
                   return_value=True):
            await main_module.run_penny_connors_scan()
        get_scanner.assert_not_called()

    @pytest.mark.asyncio
    async def test_penny_scanner_once_proceeds_with_token(self, monkeypatch):
        """Guard must not over-block: with a token present the handler
        must reach _get_penny_scanner."""
        import main as main_module

        monkeypatch.setattr(main_module.kite, "access_token", "tok123")
        get_scanner = MagicMock(return_value=None)  # scanner=None: early exit after
        monkeypatch.setattr(main_module, "_get_penny_scanner", get_scanner)
        with patch("main.is_trading_day", new_callable=AsyncMock,
                   return_value=True):
            await main_module.run_penny_scanner_once()
        get_scanner.assert_called()


# ---------------------------------------------------------------------------
# Bug #5 — token persistence round-trip
# ---------------------------------------------------------------------------

class TestTokenPersistence:
    def test_persist_and_restore_same_day(self, tmp_path, monkeypatch):
        import main as main_module
        from config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
        set_token = MagicMock()
        monkeypatch.setattr(main_module.kite, "set_token", set_token)

        main_module._persist_kite_token("secret-token-abcd")
        assert (tmp_path / "kite_token.json").exists()

        restored = main_module.restore_kite_token_if_fresh()
        assert restored is True
        set_token.assert_called_once_with("secret-token-abcd")

    def test_stale_token_not_restored(self, tmp_path, monkeypatch):
        """A token saved on a previous IST day must NOT be restored --
        Zerodha tokens expire daily; restoring one would recreate the
        2026-07-09 HTTP-400 storm."""
        import json

        import main as main_module
        from config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
        (tmp_path / "kite_token.json").write_text(json.dumps({
            "access_token": "yesterdays-token",
            "saved_date_ist": "2020-01-01",
        }))
        set_token = MagicMock()
        monkeypatch.setattr(main_module.kite, "set_token", set_token)

        assert main_module.restore_kite_token_if_fresh() is False
        set_token.assert_not_called()

    def test_missing_file_returns_false(self, tmp_path, monkeypatch):
        import main as main_module
        from config import settings

        monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
        assert main_module.restore_kite_token_if_fresh() is False
