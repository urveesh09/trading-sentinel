"""
[PENNY-BREAKOUT 2026-06-21] Tests for the Volume Breakout MIS signal evaluator
+ 14:30 smart-EOD rule.

Spec section 5:
  - Volume surge: today cumulative vol by 10:30 IST > 3x 20-day median
  - Breakout: close > day's high + 0.3% on a 1-min bar (not just touch)
  - RSI(14) < 70 (not overbought)
  - Entry: limit at LTP + 0.3%
  - Stop: low of breakout candle (1-min)
  - Target: +2.0R
  - Time-stop: 15:00 IST hard exit
  - 14:30 smart-EOD rule (3-way decision):
      * In profit + within 0.5R of target -> exit NOW
      * In profit + > 0.5R from target -> hold to 15:00
      * In loss + > 30 min in loss -> exit NOW
      * In loss + fresh entry (< 30 min) -> hold to 15:00
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest


# ---- entry: volume + breakout + time gates ---------------------------

def test_entry_rejects_outside_time_window():
    from penny_engine_breakout import evaluate_breakout_entry
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=30000, median_vol_20d=10000,
        breakout_bar={"high": 10.5, "low": 10.0, "close": 10.4},
        day_high=10.30, rsi_14=55.0, as_of=datetime(2026, 6, 21, 9, 30),
        risk_engine=MagicMock(),
    )
    assert result["accept"] is False
    assert "time" in result["reject_reason"].lower()


def test_entry_rejects_low_volume():
    """cum_vol < PENNY_BREAKOUT_VOL_MULT * median_vol_20d -> reject.

    [PENNY-AGGRESSIVE 2026-06-24] The threshold is now 1.8x (was 3.0x).
    Test uses 1.5x (cum=15000, median=10000) so it's strictly below 1.8x
    and still rejected. A separate test (test_entry_accepts_at_relaxed_volume)
    confirms 2.0x now passes.
    """
    from penny_engine_breakout import evaluate_breakout_entry
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=15000, median_vol_20d=10000,
        breakout_bar={"high": 10.5, "low": 10.0, "close": 10.4},
        day_high=10.30, rsi_14=55.0, as_of=datetime(2026, 6, 21, 11, 0),
        risk_engine=MagicMock(),
    )
    assert result["accept"] is False
    assert "volume" in result["reject_reason"].lower()


def test_entry_accepts_at_relaxed_volume():
    """[PENNY-AGGRESSIVE 2026-06-24] At the new 1.8x threshold, a 2.0x volume
    surge passes the volume filter (it would have been rejected at 3.0x).
    All other gates (time window, breakout confirm, RSI) must also pass.
    """
    from penny_engine_breakout import evaluate_breakout_entry
    mock_risk = MagicMock()
    mock_risk.position_size.return_value = 50
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=20000, median_vol_20d=10000,  # 2.0x
        breakout_bar={"high": 10.45, "low": 10.30, "close": 10.40},
        day_high=10.35, rsi_14=55.0, as_of=datetime(2026, 6, 21, 11, 0),
        risk_engine=mock_risk,
    )
    assert result["accept"] is True
    assert result["entry_order_type"] == "LIMIT"


def test_entry_rejects_no_breakout():
    """Close not above day's high by 0.3% -> reject."""
    from penny_engine_breakout import evaluate_breakout_entry
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=30000, median_vol_20d=10000,
        breakout_bar={"high": 10.30, "low": 10.0, "close": 10.25},
        day_high=10.30, rsi_14=55.0, as_of=datetime(2026, 6, 21, 11, 0),
        risk_engine=MagicMock(),
    )
    assert result["accept"] is False
    assert "breakout" in result["reject_reason"].lower()


def test_entry_rejects_overbought():
    from penny_engine_breakout import evaluate_breakout_entry
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=30000, median_vol_20d=10000,
        breakout_bar={"high": 10.5, "low": 10.0, "close": 10.45},
        day_high=10.30, rsi_14=75.0, as_of=datetime(2026, 6, 21, 11, 0),
        risk_engine=MagicMock(),
    )
    assert result["accept"] is False
    assert "rsi" in result["reject_reason"].lower()


def test_entry_accepts_when_all_conditions_met():
    from penny_engine_breakout import evaluate_breakout_entry
    mock_risk = MagicMock()
    mock_risk.position_size.return_value = 50
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=30000, median_vol_20d=10000,
        breakout_bar={"high": 10.45, "low": 10.30, "close": 10.40},
        day_high=10.35, rsi_14=55.0, as_of=datetime(2026, 6, 21, 11, 0),
        risk_engine=mock_risk,
    )
    assert result["accept"] is True
    assert result["entry_order_type"] == "LIMIT"
    assert result["sl_order_type"] == "SL-M"
    # Entry at close + 0.3% = 10.43, stop at breakout candle low = 10.30
    assert abs(result["entry"] - 10.43) < 0.01
    assert result["stop_loss"] == 10.30
    # Risk = 10.43 - 10.30 = 0.13; target = +2R = 10.43 + 0.26 = 10.69
    assert abs(result["target"] - 10.69) < 0.01


def test_entry_after_14_30_window_closes_rejects():
    from penny_engine_breakout import evaluate_breakout_entry
    result = evaluate_breakout_entry(
        ticker="X", cum_vol_today=30000, median_vol_20d=10000,
        breakout_bar={"high": 10.45, "low": 10.30, "close": 10.40},
        day_high=10.35, rsi_14=55.0, as_of=datetime(2026, 6, 21, 14, 35),
        risk_engine=MagicMock(),
    )
    assert result["accept"] is False
    assert "time" in result["reject_reason"].lower()


# ---- smart-EOD 14:30 rule --------------------------------------------

def test_smart_eod_exits_profit_close_to_target():
    """In profit + within 0.5R of target -> exit NOW."""
    from penny_engine_breakout import smart_eod_check
    pos = {
        "entry_price": 10.00, "entry_time": datetime(2026, 6, 21, 11, 0),
        "stop_loss": 9.80, "target": 10.40,
    }
    # R = 0.20, target = 10.40. Price 10.32 = +0.32 from entry = +1.6R
    # 10.40 - 10.32 = 0.08 = 0.4R from target -> within 0.5R -> exit
    decision = smart_eod_check(pos, current_price=10.32,
                               now=datetime(2026, 6, 21, 14, 30))
    assert decision["action"] == "exit_now"
    assert decision["reason"] == "within_0_5R_of_target"


def test_smart_eod_holds_profit_far_from_target():
    """In profit but >0.5R from target -> hold to 15:00."""
    from penny_engine_breakout import smart_eod_check
    pos = {
        "entry_price": 10.00, "entry_time": datetime(2026, 6, 21, 11, 0),
        "stop_loss": 9.80, "target": 10.40,
    }
    # Price 10.15 = +0.15 = +0.75R from entry. 10.40 - 10.15 = 0.25 = 1.25R from target
    # -> > 0.5R from target -> hold
    decision = smart_eod_check(pos, current_price=10.15,
                               now=datetime(2026, 6, 21, 14, 30))
    assert decision["action"] == "hold"


def test_smart_eod_cuts_old_loss():
    """In loss AND in loss for >30 min -> exit NOW."""
    from penny_engine_breakout import smart_eod_check
    pos = {
        "entry_price": 10.00,
        "entry_time": datetime(2026, 6, 21, 9, 30),   # 5 hours ago
        "stop_loss": 9.80, "target": 10.40,
    }
    # Price 9.85, in loss by 0.15. Held for >30 min -> cut
    decision = smart_eod_check(pos, current_price=9.85,
                               now=datetime(2026, 6, 21, 14, 30))
    assert decision["action"] == "exit_now"
    assert decision["reason"] == "loss_over_30_min"


def test_smart_eod_holds_fresh_loss():
    """In loss but recent entry (<30 min) -> hold (give it room)."""
    from penny_engine_breakout import smart_eod_check
    pos = {
        "entry_price": 10.00,
        "entry_time": datetime(2026, 6, 21, 14, 10),  # 20 min ago
        "stop_loss": 9.80, "target": 10.40,
    }
    # Price 9.85, in loss but fresh -> hold
    decision = smart_eod_check(pos, current_price=9.85,
                               now=datetime(2026, 6, 21, 14, 30))
    assert decision["action"] == "hold"


def test_smart_eod_boundary_30_min_exactly():
    """Edge case: in loss for exactly 30 min -> use > 30, so hold at 30."""
    from penny_engine_breakout import smart_eod_check
    pos = {
        "entry_price": 10.00,
        "entry_time": datetime(2026, 6, 21, 14, 0),  # exactly 30 min ago
        "stop_loss": 9.80, "target": 10.40,
    }
    decision = smart_eod_check(pos, current_price=9.85,
                               now=datetime(2026, 6, 21, 14, 30))
    # Boundary: 30 min elapsed = NOT > 30 -> hold
    assert decision["action"] == "hold"


def test_smart_eod_boundary_31_min_exits():
    """31 min in loss -> exit."""
    from penny_engine_breakout import smart_eod_check
    pos = {
        "entry_price": 10.00,
        "entry_time": datetime(2026, 6, 21, 13, 59),
        "stop_loss": 9.80, "target": 10.40,
    }
    decision = smart_eod_check(pos, current_price=9.85,
                               now=datetime(2026, 6, 21, 14, 30))
    assert decision["action"] == "exit_now"


# ---- time-stop at 15:00 ----------------------------------------------

def test_mis_time_stop_fires_at_15_00():
    from penny_engine_breakout import mis_time_stop_active
    at_15_00 = datetime(2026, 6, 21, 15, 0)
    at_14_59 = datetime(2026, 6, 21, 14, 59)
    assert mis_time_stop_active(at_15_00) is True
    assert mis_time_stop_active(at_14_59) is False
