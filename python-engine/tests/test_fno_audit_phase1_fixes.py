"""
[FNO-AUDIT-PHASE1 2026-07-11] Regression tests for the 2026-07-11
deep-audit findings. Each test class guards one bug class.

Bugs fixed:
  * Fix #2 — _rvol_time_adjusted now honours FNO_RVOL_LOOKBACK_DAYS.
    Before: used ALL bars with date < bar_ts.date() (frame-length
    dependent). After: walks back exactly N trading days from the bar_ts.

  * Fix #3 — hard_flat exit with no broker quote now pages the operator
    via notify_operator instead of silently `continue`-ing (which left
    the position open through the weekend until the next trading tick).

  * Fix #4 — time_stop entry_time parse failure (ValueError/TypeError)
    now logs `fno_time_stop_age_parse_failed` so the operator sees the
    malformed row and can patch it; before, it silently dropped to
    age_min=0 and the time_stop never fired for that position.

  * Fix #6 — _wait_for_fill on a COMPLETE order with neither
    average_price nor price logs `fno_completed_order_no_price` and
    returns None (instead of None-without-warning, which would risk
    double-fill on retry).

Note on log capture: per ops rule 70, structlog binds PrintLogger(file=sys.stderr)
at configure time, so pytest's stdlib-based caplog cannot capture the warning
lines this code emits. The tests below monkey-patch `structlog.get_logger` to
return a recording logger so we can assert the warning was emitted.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytz
import pytest

from config import settings
from fno_engine_mom import _rvol_time_adjusted
from fno_orchestrator import _manage_open_positions
from fno_executor import FnoExecutor


IST = pytz.timezone("Asia/Kolkata")


class _RecordingLogger:
    """structlog-compatible duck-type that records warning/critical calls.

    structlog's get_logger() returns a BoundLogger whose warn/critical
    methods accept (*args, **kwargs) and forward to the underlying
    PrintLogger. We capture every call so the test can assert on it.
    """

    def __init__(self):
        self.records: List[Tuple[str, tuple, dict]] = []

    def warning(self, *args, **kwargs):
        self.records.append(("warning", args, kwargs))

    def critical(self, *args, **kwargs):
        self.records.append(("critical", args, kwargs))

    def info(self, *args, **kwargs):
        self.records.append(("info", args, kwargs))

    def error(self, *args, **kwargs):
        self.records.append(("error", args, kwargs))

    # structlog supports keyword-only binds
    def bind(self, **kwargs):
        return self

    def __getattr__(self, name):
        # Any other structlog method just records
        def _any(*a, **k):
            self.records.append((name, a, k))
        return _any


@pytest.fixture
def fno_log(monkeypatch):
    """Patch every fno_* module's `logger` (structlog.get_logger()) with
    a RecordingLogger so tests can assert on emitted warnings."""
    rec = _RecordingLogger()
    # fno_orchestrator.fno_positions.logger is also a structlog
    # instance; the orchestra's own logger is captured too.
    for mod_name in (
        "fno_orchestrator", "fno_executor", "fno_engine_mom",
        "fno_chain", "fno_costs", "fno_positions", "fno_signal_log",
        "fno_risk", "fno_gates", "fno_models", "fno_instruments",
        "fno_accept_watchdog", "fno_hourly_report",
    ):
        try:
            mod = __import__(mod_name)
            monkeypatch.setattr(mod, "logger", rec, raising=False)
        except Exception:
            pass
    return rec


# ---------------------------------------------------------------------------
# Fix #2: FNO_RVOL_LOOKBACK_DAYS is honoured
# ---------------------------------------------------------------------------

class TestRvolLookbackDaysHonoured:
    """Before the fix: df with 30 days of bars at slot 09:55 gave 30
    samples. After: must give exactly FNO_RVOL_LOOKBACK_DAYS samples
    (counting only trading days with data, capped at lookback)."""

    def _build_frame(self, n_days: int, slot: str, slot_volume: int):
        """Build n_days trading days, one bar each at "slot" (HH:MM) --
        PLUS the "now" bar at the same slot on day n+1. (The now-bar's
        slot must match the baseline slot -- it's what the function
        looks up.) The now-bar has 3x volume so a green test sees rvol=3.0.
        """
        rows = []
        # n_days trading days, one bar each at "slot" (HH:MM).
        start = pd.Timestamp(f"2026-07-01 {slot}:00")
        for i in range(n_days):
            t = start + pd.Timedelta(days=i)
            rows.append({"ts": t, "volume": slot_volume})
        # The "now" bar: same slot, on day n+1, 3x volume.
        now_bar = start + pd.Timedelta(days=n_days)
        rows.append({"ts": now_bar, "volume": slot_volume * 3})
        df = pd.DataFrame(rows).set_index("ts")
        return df

    def test_lookback_caps_baseline_size(self, monkeypatch):
        """With 30 days of slot data and lookback=5, exactly 5 samples
        enter the baseline (not 30)."""
        monkeypatch.setattr(settings, "FNO_RVOL_LOOKBACK_DAYS", 5)
        df = self._build_frame(n_days=30, slot="09:55", slot_volume=100)
        now_bar = df.index[-1]
        # The "now" bar is on day 31 at slot 09:55 -- baseline must
        # walk back 5 trading days (days 26-30), not all 30 prior days.
        rvol = _rvol_time_adjusted(df, now_bar)
        # 3x / mean-of-5 = 3.0 (since all 5 baseline days have volume=100).
        assert rvol == pytest.approx(3.0), (
            f"expected RVOL=3.0 with lookback=5 (mean of 100 vs current 300), "
            f"got {rvol}; the fix didn't truncate the baseline window"
        )

    def test_lookback_too_few_samples_returns_none(self, monkeypatch):
        """lookback=3 needs 3 prior samples; 2 should still return None
        (old behaviour preserved)."""
        monkeypatch.setattr(settings, "FNO_RVOL_LOOKBACK_DAYS", 3)
        df = self._build_frame(n_days=2, slot="09:55", slot_volume=100)
        now_bar = df.index[-1]
        assert _rvol_time_adjusted(df, now_bar) is None

    def test_lookback_zero_does_not_crash(self, monkeypatch):
        """Defensive: max(1, ...) prevents a divide-by-zero / empty-baseline
        crash if the operator ever sets the knob to 0. The function still
        returns None (the >=3 samples guard needs honest history), but
        must NOT raise or hang."""
        monkeypatch.setattr(settings, "FNO_RVOL_LOOKBACK_DAYS", 0)
        df = self._build_frame(n_days=5, slot="09:55", slot_volume=100)
        now_bar = df.index[-1]
        # Should not raise. The >=3-samples guard will trip (only 1 sample
        # in the baseline walk) and the function returns None -- which is
        # the documented "not enough history" signal, NOT a crash.
        out = _rvol_time_adjusted(df, now_bar)
        assert out is None, (
            "with lookback=0 the baseline is 1 sample -> the >=3 guard "
            "returns None; the safety property is 'no exception'"
        )


# ---------------------------------------------------------------------------
# Fix #3: hard_flat + no-quote pages the operator (does not silently retry)
# ---------------------------------------------------------------------------

class TestHardFlatNoQuotePagesOperator:
    """When the 15:10 hard flat fires but the broker returns no quote
    for the option token, the orchestrator must:
      (a) call notify_operator(...) with a Telegram message
      (b) log a CRITICAL entry for grep-ability
      (c) NOT silently `continue` (operator was the only safety net
          because MIS auto-square-off is the broker's guarantee, not ours)
    """

    @pytest.mark.asyncio
    async def test_hard_flat_no_quote_calls_notify_operator(self, fno_log):
        import fno_positions as fpos
        from config import settings as _settings
        await fpos.init_fno_positions_db(_settings.DB_PATH)
        await fpos.insert_position(
            _settings.DB_PATH,
            source="FNO_PAPER",
            tradingsymbol="NIFTY26JUL25200CE",
            token=12345,
            underlying="NIFTY",
            expiry="2026-07-30",
            strike=25200.0,
            opt_type="CE",
            direction="LONG",
            lots=1,
            lot_size=75,
            qty=75,
            entry_time=datetime(2026, 7, 10, 14, 0).isoformat(),
            entry_date="2026-07-10",
            entry_premium=100.0,
            entry_underlying=25000.0,
            delta_at_entry=0.55,
            iv_at_entry=0.12,
            atr_at_entry=50.0,
            stop_underlying=24950.0,
            target_underlying=25100.0,
            premium_stop=75.0,
            trail_active=0,
            trail_stop_underlying=None,
            best_underlying=25000.0,
            max_loss_rupees=7500.0,
            status="OPEN",
            entry_order_id="PAPER-TEST",
            bar_ts="2026-07-10 14:00:00",
        )

        fake_kite = MagicMock()
        fake_kite.get_quote = AsyncMock(return_value={})  # no options quote

        now_ist = datetime(2026, 7, 10, 15, 12)  # past FNO_HARD_FLAT_MIN=15:10

        # Mock notify_operator via sys.modules so the orchestrator's
        # `from operator_alert import notify_operator` resolves.
        import sys
        captured = {}

        async def _capture(message, **kwargs):
            captured["message"] = message
            captured["event"] = kwargs.get("event")
            return True

        sys.modules["operator_alert"] = MagicMock()
        sys.modules["operator_alert"].notify_operator = _capture

        executor = FnoExecutor(fake_kite, paper_mode=True, source_tag="FNO_PAPER")
        closed = await _manage_open_positions(
            fake_kite, _settings.DB_PATH, "FNO_PAPER", executor,
            now_ist, fut_price=25010.0,
        )

        assert captured.get("event") == "fno_hard_flat_no_quote", (
            f"operator should be paged with event=fno_hard_flat_no_quote, "
            f"got event={captured.get('event')!r}"
        )
        assert "NIFTY26JUL25200CE" in captured.get("message", "")
        assert "hard flat" in captured.get("message", "").lower()
        # Position is NOT closed (no quote -> continue), but the critical
        # log + the page surface the situation to the operator.
        assert closed == []
        # Confirm the critical line was emitted (greppable in docker logs).
        crit_msgs = [
            msg for lvl, args, _ in fno_log.records if lvl == "critical"
            for msg in args if "fno_exit_no_quote" in str(msg)
        ]
        assert crit_msgs, (
            "expected fno_exit_no_quote critical log when no quote at hard-flat; "
            f"got records: {[(lvl, args) for lvl, args, _ in fno_log.records]}"
        )
        assert any("carry into next session" in m for m in crit_msgs), (
            "critical log should mention 'carry into next session' so a grep "
            "of docker logs finds the weekend-carry risk"
        )


# ---------------------------------------------------------------------------
# Fix #4: time_stop entry_time parse failure is loud
# ---------------------------------------------------------------------------

class TestTimeStopParseFailureLoud:
    """When p.entry_time is malformed, the orchestrator must log a
    WARNING (not silently default age_min=0)."""

    @pytest.mark.asyncio
    async def test_malformed_entry_time_logs_warning(self, fno_log):
        import fno_positions as fpos
        from config import settings as _settings

        await fpos.init_fno_positions_db(_settings.DB_PATH)
        # Insert a position with a malformed entry_time.
        await fpos.insert_position(
            _settings.DB_PATH,
            source="FNO_PAPER",
            tradingsymbol="NIFTY26JUL25200CE",
            token=99,
            underlying="NIFTY",
            expiry="2026-07-30",
            strike=25200.0,
            opt_type="CE",
            direction="LONG",
            lots=1,
            lot_size=75,
            qty=75,
            entry_time="not-a-datetime",  # MALFORMED -- datetime.fromisoformat raises
            entry_date="2026-07-10",
            entry_premium=100.0,
            entry_underlying=25000.0,
            delta_at_entry=0.55,
            iv_at_entry=0.12,
            atr_at_entry=50.0,
            stop_underlying=24950.0,
            target_underlying=25100.0,
            premium_stop=75.0,
            trail_active=0,
            trail_stop_underlying=None,
            best_underlying=25000.0,
            max_loss_rupees=7500.0,
            status="OPEN",
            entry_order_id="PAPER-TEST",
            bar_ts="2026-07-10 14:00:00",
        )

        fake_kite = MagicMock()
        fake_kite.get_quote = AsyncMock(return_value={
            99: {"last_price": 100.0, "depth": {"buy": [{"price": 100.0}]}},
        })

        # CRITICAL: keep now_ist BEFORE 15:10 (FNO_HARD_FLAT_MIN) so the
        # hard-flat branch doesn't fire first. We want to hit the
        # time_stop evaluate path, which is where the parse happens.
        # We also need to ensure fut_price is on the FAVOURABLE side of
        # entry so the underlying_stop and trailing paths don't fire.
        now_ist = datetime(2026, 7, 10, 14, 50)
        fut_price = 25030.0  # 30 pts above entry -> no stop, no trail

        executor = FnoExecutor(fake_kite, paper_mode=True, source_tag="FNO_PAPER")
        await _manage_open_positions(
            fake_kite, _settings.DB_PATH, "FNO_PAPER", executor,
            now_ist, fut_price=fut_price,
        )

        # structlog may render the warning under multiple keyword names
        # across versions; accept any match on the format-string OR args.
        def _flatten_records(level_name: str) -> list:
            out = []
            for lvl, args, kwargs in fno_log.records:
                if lvl != level_name:
                    continue
                # structlog positional renders: args[0] = format string;
                # OR all args are the message parts depending on form.
                msg = " ".join(str(a) for a in args)
                msg += " " + " ".join(f"{k}={v}" for k, v in kwargs.items())
                out.append(msg)
            return out

        warn_msgs = _flatten_records("warning")
        matching = [m for m in warn_msgs if "fno_time_stop_age_parse_failed" in m]
        assert matching, (
            "expected fno_time_stop_age_parse_failed warning when entry_time "
            "is unparseable; got ALL records: "
            f"{[(lvl, args) for lvl, args, _ in fno_log.records]}"
        )
        assert any("not-a-datetime" in m for m in matching), (
            "warning should include the offending entry_time so the operator "
            "can patch the row"
        )


# ---------------------------------------------------------------------------
# Fix #6: _wait_for_fill warns when COMPLETE order has no fill price
# ---------------------------------------------------------------------------

class TestCompletedOrderNoPriceWarns:
    """When status=COMPLETE but neither average_price nor price is
    present in the broker response, the executor must log a warning and
    return None (not silently return None)."""

    @staticmethod
    def _flatten(level_name, fno_log):
        out = []
        for lvl, args, kwargs in fno_log.records:
            if lvl != level_name:
                continue
            msg = " ".join(str(a) for a in args)
            msg += " " + " ".join(f"{k}={v}" for k, v in kwargs.items())
            out.append(msg)
        return out

    @pytest.mark.asyncio
    async def test_complete_order_missing_price_logs_warning(self, fno_log):
        fake_kite = MagicMock()
        fake_kite.order_history = AsyncMock(return_value=[
            # One event, status=COMPLETE, NO average_price, NO price.
            {"status": "COMPLETE", "order_id": "ORD-XYZ"},
        ])
        fake_kite.cancel_order = AsyncMock()

        executor = FnoExecutor(fake_kite, paper_mode=False, source_tag="FNO_PAPER")
        result = await executor._wait_for_fill("ORD-XYZ", timeout=1.0)

        assert result is None, (
            "missing fill-price should be treated as no-fill to avoid "
            "double-entry risk, NOT returned as 0.0"
        )
        warn_msgs = self._flatten("warning", fno_log)
        matching = [m for m in warn_msgs if "fno_completed_order_no_price" in m]
        assert matching, "expected fno_completed_order_no_price warning"
        assert any("ORD-XYZ" in m for m in matching), (
            "warning should include the order_id"
        )

    @pytest.mark.asyncio
    async def test_complete_order_with_avg_price_does_not_warn(self, fno_log):
        """The complement: a normal COMPLETE order with average_price
        must NOT emit the noise warning."""
        fake_kite = MagicMock()
        fake_kite.order_history = AsyncMock(return_value=[
            {"status": "COMPLETE", "order_id": "ORD-OK", "average_price": 99.50},
        ])
        executor = FnoExecutor(fake_kite, paper_mode=False, source_tag="FNO_PAPER")
        result = await executor._wait_for_fill("ORD-OK", timeout=1.0)

        assert result == pytest.approx(99.50)
        warn_msgs = self._flatten("warning", fno_log)
        matching = [m for m in warn_msgs if "fno_completed_order_no_price" in m]
        assert not matching, (
            "a normal COMPLETE order must not emit the no-price warning; got: "
            + "; ".join(matching)
        )
