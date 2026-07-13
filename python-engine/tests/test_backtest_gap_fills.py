"""
[ROADMAP-3.3 2026-07-12] Gap-through stops must fill at the OPEN.

Both walk-forward simulators used to fill stop-outs at the stop price
even when the bar gapped below it overnight -- a fill the market never
offered. That flattered win rate and average R in every historical
sweep. These are the witnesses that a gap-down now fills at the open
while an ordinary intraday breach still fills at the stop.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

import penny_edge_engine as pee
from backtest import _simulate_trade
from models import Regime


# -------------------------------------------------------------------
# backtest._simulate_trade (swing walk-forward)
# -------------------------------------------------------------------

def _df(rows):
    """rows: list of (open, high, low, close); daily index."""
    start = datetime(2026, 1, 1)
    idx = [start + timedelta(days=i) for i in range(len(rows))]
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows],
        index=pd.DatetimeIndex(idx),
    )


def test_swing_gap_through_stop_fills_at_open():
    """Entry 100, stop 95; next day opens at 88 (gap through the stop):
    fill must be 88, and the realized R must reflect the full gap loss."""
    df = _df([(100, 101, 99, 100), (88, 90, 86, 89)])
    trade = _simulate_trade(
        entry_date=df.index[0], entry_price=100.0, shares=10,
        stop_loss=95.0, target_1=110.0, target_2=120.0,
        regime=Regime.REGIME_1_NORMAL, df_slice=df,
    )
    assert trade["exit_reason"] == "stop_out"
    assert trade["exit_price"] == 88.0
    assert trade["r_multiple"] == pytest.approx((88.0 - 100.0) / 5.0)


def test_swing_intraday_stop_breach_still_fills_at_stop():
    """Open above the stop, close below it: normal stop-out at the stop."""
    df = _df([(100, 101, 99, 100), (98, 99, 93, 94)])
    trade = _simulate_trade(
        entry_date=df.index[0], entry_price=100.0, shares=10,
        stop_loss=95.0, target_1=110.0, target_2=120.0,
        regime=Regime.REGIME_1_NORMAL, df_slice=df,
    )
    assert trade["exit_reason"] == "stop_out"
    assert trade["exit_price"] == 95.0


# -------------------------------------------------------------------
# penny_edge_engine.simulate_position
# -------------------------------------------------------------------

def _pos():
    return pee.Position(
        ticker="T", entry_date="2026-01-01",
        entry_price=10.0, shares=100,
        target=11.0, stop_loss=9.5,
        hold_days=5,
        signal_subtype="MR_strong",
        raw_strength=0.7, adjusted_strength=0.7,
    )


def test_penny_edge_gap_through_stop_fills_at_open():
    """Bar opens at 8.8, below the 9.5 stop: fill at the open (minus the
    usual slippage), not at a stop price the market gapped past."""
    bars = [{"date": "2026-01-02", "open": 8.8, "high": 9.0, "low": 8.6, "close": 8.9}]
    result = pee.simulate_position(_pos(), bars, slippage_bps=5)
    assert result["exit_reason"] == "sl"
    assert result["exit_price"] == pytest.approx(8.8 * (1 - 5 / 10000))


def test_penny_edge_intraday_stop_breach_still_fills_at_stop():
    bars = [{"date": "2026-01-02", "open": 9.9, "high": 10.1, "low": 9.4, "close": 9.7}]
    result = pee.simulate_position(_pos(), bars, slippage_bps=5)
    assert result["exit_reason"] == "sl"
    assert result["exit_price"] == pytest.approx(9.5 * (1 - 5 / 10000))
