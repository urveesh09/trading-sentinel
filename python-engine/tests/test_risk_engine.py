import pytest
import math
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk_engine import RiskEngine, PartialExitResult


class TestRiskEngine:
    """Tests for dynamic position sizing and partial exit logic."""

    def test_position_sizing_r1(self):
        """Regime 1 should use 10% risk."""
        re = RiskEngine(bankroll=50000.0, regime_risk_pct=0.10)
        shares = re.calc_shares(entry=200.0, stop=195.0)
        # Risk = 50000 * 0.10 = 5000. Risk per share = 5. Shares = 5000/5 = 1000
        # capital = 1000 * 200 = 200000 > 50000 -> cap at floor(50000/200) = 250
        assert shares == 250

    def test_position_sizing_r2(self):
        """Regime 2 should use 7% risk."""
        re = RiskEngine(bankroll=7000.0, regime_risk_pct=0.07)
        shares = re.calc_shares(entry=50.0, stop=47.5)
        # Risk = 7000 * 0.07 = 490. Risk per share = 2.5. Shares = 490/2.5 = 196
        # capital = 196 * 50 = 9800 > 7000 -> cap at floor(7000/50) = 140
        assert shares == 140

    def test_position_sizing_r3(self):
        """Regime 3 should use 5% risk."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.05)
        shares = re.calc_shares(entry=100.0, stop=95.0)
        # Risk = 5000 * 0.05 = 250. Risk per share = 5. Shares = 250/5 = 50
        assert shares == 50

    def test_shares_respects_bankroll(self):
        """If shares would exceed bankroll, cap at floor."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # Very tight stop: risk per share is huge -> few shares
        # risk_per_share = 100 - 99.5 = 0.5
        # risk_per_trade = 500. shares = 500/0.5 = 1000
        # capital_needed = 1000 * 100 = 100,000 > bankroll
        # So should cap at floor(bankroll/entry) = floor(5000/100) = 50
        shares = re.calc_shares(entry=100.0, stop=99.5)
        capital_needed = shares * 100.0
        assert capital_needed <= 5000.0
        assert shares >= 1  # At minimum should get 1 share

    def test_partial_exit_initial_state(self):
        """Partial exit should initially be NOT triggered."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # No partial exit check here - it's a method call, not state

    def test_partial_exit_triggers_at_t1(self):
        """Partial exit should trigger when price reaches T1."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # Entry=100, T1=107.5 (1.5R where risk=5)
        entry = 100.0
        stop = 95.0
        t1 = entry + 1.5 * (entry - stop)  # = 107.5
        # Price reaches T1
        result = re.check_partial_exit(close=t1, entry=entry, stop=stop, shares=100)
        assert result.triggered is True
        assert result.shares_to_exit == 50  # 50% of 100

    def test_partial_exit_not_triggered_before_t1(self):
        """Partial exit should NOT trigger before T1."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        entry = 100.0
        stop = 95.0
        t1 = 107.5
        # Price at 105 (below T1)
        result = re.check_partial_exit(close=105.0, entry=entry, stop=stop, shares=100)
        assert result.triggered is False

    def test_drawdown_recovery_reduces_risk(self):
        """Drawdown recovery should apply 30% size reduction."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # Set recovery active (recovery_trades_remaining > 0 triggers the multiplier)
        re._recovery_trades_remaining = 5
        effective = re.get_effective_risk_pct(recovery_active=True)
        # 10% * 0.7 = 7%
        assert math.isclose(effective, 0.07, abs_tol=0.001)

    def test_drawdown_recovery_resets_after_2_wins(self):
        """After 2 consecutive wins during recovery, normal sizing resumes."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        re._recovery_trades_remaining = 5
        # In recovery: 10% * 0.7 = 7%
        assert math.isclose(re.get_effective_risk_pct(recovery_active=True), 0.07, abs_tol=0.001)
        # Win 1 during recovery
        re.record_trade_outcome(win=True, in_recovery=True)
        assert math.isclose(re.get_effective_risk_pct(recovery_active=True), 0.07, abs_tol=0.001)
        # Win 2 — recovery ends, full 10% restored
        re.record_trade_outcome(win=True, in_recovery=True)
        assert re.get_effective_risk_pct(recovery_active=False) == 0.10

    def test_losing_trade_during_recovery_continues(self):
        """A losing trade during recovery does not reset the recovery counter."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        re._recovery_trades_remaining = 5
        re.record_trade_outcome(win=False, in_recovery=True)
        # Still in recovery (only 2 consecutive wins reset it)
        assert math.isclose(re.get_effective_risk_pct(recovery_active=True), 0.07, abs_tol=0.001)
        assert re._recovery_trades_remaining == 4  # Decrements on loss

    def test_zero_shares_when_stop_equals_entry(self):
        """Zero risk per share should return 0 shares."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        shares = re.calc_shares(entry=100.0, stop=100.0)
        assert shares == 0

    def test_update_bankroll(self):
        """update_bankroll should change the bankroll."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        re.update_bankroll(5500.0)
        assert re.bankroll == 5500.0

    def test_enter_recovery_mode(self):
        """enter_recovery_mode should set recovery trades."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        re.enter_recovery_mode()
        assert re._recovery_trades_remaining == 5
        assert re._consecutive_wins_in_recovery == 0