import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chandelier_stop import ChandelierStop


class TestChandelierStop:
    """Tests for Chandelier trailing stop logic."""

    def test_initial_stop_below_entry(self):
        """The initial stop should be below the entry price."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        assert cs.get_stop() < 100.0
        # stop = 100 - (3 * 5) = 85

    def test_stop_trails_highest_close(self):
        """Stop should track the highest closing price since entry."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        # Price moves up to 110 (highest close)
        cs.update(close=110.0, high=112.0, low=108.0)
        # Stop is now: highest_close (110) - 3*ATR(5) = 110 - 15 = 95
        assert cs.get_stop() == 95.0
        assert cs.get_stop() < 100.0  # Still below entry

    def test_stop_lock_in_profit(self):
        """After a strong move, stop should lock in profit above entry."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=120.0, high=122.0, low=118.0)
        # Highest close: 120. Stop: 120 - 15 = 105
        assert cs.get_stop() == 105.0
        # Now stop is ABOVE entry -- trade is profitable
        assert cs.is_profitable()

    def test_stop_not_triggered_by_pullback(self):
        """Stop should NOT move down on a pullback -- it only tracks highest closes."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Highest close = 110, stop = 95
        cs.update(close=105.0, high=106.0, low=100.0)  # Pullback -- highest close still 110
        # Stop should still be 95 (based on highest close of 110)
        assert cs.get_stop() == 95.0

    def test_is_stopped_out_buy(self):
        """Stop should trigger when price closes below the stop level."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Stop = 95
        # Price drops to 93 -- below stop of 95
        triggered, price = cs.check_stop_out(close=93.0)
        assert triggered is True
        assert price == 93.0

    def test_not_stopped_out_buy(self):
        """Stop should NOT trigger if price stays above stop."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Stop = 95
        # Price pulls back to 97 -- still above stop
        triggered, price = cs.check_stop_out(close=97.0)
        assert triggered is False
        assert price == 97.0

    def test_atr_can_increase(self):
        """ATR can change over time -- stop should use current ATR each update."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Stop = 110 - 15 = 95 (ATR=5)
        # ATR increases to 8 (market getting volatile)
        cs.update(close=110.0, high=112.0, low=108.0, atr=8.0)
        # Highest close still 110. Stop = 110 - (3 * 8) = 86
        assert cs.get_stop() == 86.0

    def test_initial_stop_uses_entry_price_not_highest_close(self):
        """Before any update, stop is based on entry price, not a phantom high."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        # Initial stop: entry - 3*ATR = 100 - 15 = 85
        assert cs.get_stop() == 85.0

    def test_get_r_multiple_profitable(self):
        """R-multiple should be positive in a winning trade."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=115.0, high=116.0, low=114.0)
        # Initial risk distance: 100 - 85 = 15
        # Current PnL: 115 - 100 = 15
        # R = 15/15 = 1.0R
        r = cs.get_r_multiple(115.0)
        assert r == 1.0

    def test_get_r_multiple_losing(self):
        """R-multiple should be negative in a losing trade."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=92.0, high=93.0, low=91.0)
        # PnL: 92 - 100 = -8
        # R = -8/15 = -0.53R
        r = cs.get_r_multiple(92.0)
        assert r < 0

    def test_repr(self):
        """repr should include key state."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        r = repr(cs)
        assert "100" in r
        assert "85" in r  # stop = 100 - 3*5 = 85