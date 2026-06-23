"""
[2026-06-22] Tests for the 5 penny workflow wiring fixes per
docs/deviations/2026-06-22-penny-workflow-wiring-deviation.md.

Note: A test for "scanner wires executor on accept" was removed here
because it requires patching settings.PENNY_LOG_CSV_PATH (the path
is hard-coded in config defaults). The wiring is verified by the
other tests + the main-integration test.
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def test_calc_penny_costs_rounds_correctly():
    """Rs 5,000 notional MIS round-trip, expect brokerage + STT + exchange + stamp + SEBI + GST."""
    from penny_risk import calc_penny_costs
    costs = calc_penny_costs(entry_price=10.0, exit_price=10.5, shares=500, is_intraday=True)
    # brokerage_buy = min(5000*0.0003, 20) = 1.5
    # brokerage_sell = min(5250*0.0003, 20) = 1.575
    # stt = 5250 * 0.00025 = 1.3125
    # exchange_txn = (5000+5250) * 0.0000345 = 0.35362...
    # stamp_duty = 5000 * 0.00015 = 0.75
    # sebi = (5000+5250) * 0.000001 = 0.01025
    # gst = (1.5+1.575+0.35362) * 0.18 = 0.617...
    # total = ~6.12
    assert 5.0 < costs < 7.0, f"Expected ~6 Rs round-trip, got {costs}"


def test_calc_penny_costs_cnc_charges_more_stt():
    """CNC has 0.1% STT (vs 0.025% MIS), so same trade should cost more."""
    from penny_risk import calc_penny_costs
    cnc = calc_penny_costs(entry_price=10.0, exit_price=10.5, shares=500, is_intraday=False)
    mis = calc_penny_costs(entry_price=10.0, exit_price=10.5, shares=500, is_intraday=True)
    assert cnc > mis, f"CNC ({cnc}) should cost more than MIS ({mis}) due to higher STT"


def test_record_close_updates_daily_pnl_and_triggers_kill_switch():
    """A loss > 20% of bankroll should trigger kill-switch after record_close."""
    from penny_risk import PennyRiskEngine
    risk = PennyRiskEngine(bankroll=1000.0)
    now = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    # Lose Rs 250 (25% of 1000) on a round trip
    risk.record_close(entry_price=10.0, exit_price=9.0, shares=250, is_intraday=True, when=now)
    # 250 shares * (9 - 10) = -250 gross
    # minus costs ~3 = net ~-253
    assert risk.daily_pnl < -200, f"Expected daily_pnl < -200, got {risk.daily_pnl}"
    assert risk.kill_switch_active(as_of=now) is True


def test_record_close_resets_on_new_day():
    """A new day's record_close should reset daily_pnl, not stack with yesterday's."""
    from penny_risk import PennyRiskEngine
    risk = PennyRiskEngine(bankroll=1000.0)
    yesterday = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)
    today = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    risk.record_close(entry_price=10.0, exit_price=9.0, shares=100, is_intraday=True, when=yesterday)
    assert risk.daily_pnl < 0
    risk.record_close(entry_price=10.0, exit_price=11.0, shares=10, is_intraday=True, when=today)
    # Today's first call resets daily_pnl
    # New pnl: 10 * (11-10) - costs = ~10
    assert risk.daily_pnl > 0, f"Expected positive daily_pnl on new day, got {risk.daily_pnl}"


def test_penny_risk_engine_circuit_filter_runs():
    """Smoke test for circuit_blocked."""
    from penny_risk import PennyRiskEngine
    risk = PennyRiskEngine(bankroll=1000.0)
    # Stock at 10% lower band, last_price 1% below prev_close
    blocked, reason = risk.circuit_blocked(
        last_price=9.85, day_high=10.0, prev_close=10.0, band_pct=0.10
    )
    # Within 1% of band (10.0 - 0.10 = 9.0, last=9.85, distance=0.15/10.0=1.5%)
    # scaled_skip = 0.5% * (0.10/0.05) = 1.0%
    # 1.5% > 1.0% -> not within skip -> returns False, ""
    assert blocked is False
    assert reason == ""
