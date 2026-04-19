"""
Tests for python-engine/models.py — Pydantic model validation.
Verifies field types, validators, rounding, and enums.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError
from models import (
    Signal,
    MomentumSignal,
    PortfolioResponse,
    HealthResponse,
    OpenPosition,
    PerformanceReport,
    LedgerRow,
    ManualPositionRequest,
    BankrollAdjustment,
)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _valid_signal_kwargs():
    """Minimal valid kwargs for Signal."""
    return dict(
        ticker="RELIANCE", exchange="NSE", signal_time=datetime.utcnow(),
        close=500.0, ema_21=495.0, ema_50=490.0, ema_200=480.0,
        atr_14=15.0, volume_ratio=2.0, rsi_14=58.0, slope_5=0.005,
        stop_loss=475.0, target_1=537.5, target_2=575.0, trailing_stop=475.0,
        shares=10, capital_deployed=5000.0, capital_at_risk=250.0,
        net_ev=100.0, score=65, sector="ENERGY",
        strategy_version="1.0.0", strategy_type="SWING"
    )


def _valid_momentum_signal_kwargs():
    """Minimal valid kwargs for MomentumSignal."""
    return dict(
        ticker="TCS", exchange="NSE", signal_time=datetime.utcnow(),
        strategy_type="MOMENTUM", close=3500.0, vwap=3480.0,
        prev_day_high=3490.0, stop_loss=3450.0, target_1=3600.0,
        trailing_stop=3450.0, shares=5, capital_deployed=17500.0,
        capital_at_risk=250.0, net_ev=150.0, cost_ratio=0.12,
        volume_ratio=2.5, product_type="CNC", sector="IT",
        strategy_version="1.0.0"
    )


# ═══════════════════════════════════════════════════════════════
# SIGNAL MODEL
# ═══════════════════════════════════════════════════════════════


class TestSignalModel:

    def test_valid_signal(self):
        s = Signal(**_valid_signal_kwargs())
        assert s.ticker == "RELIANCE"
        assert s.strategy_type == "SWING"

    def test_float_rounding_2dp(self):
        """Float fields marked with round_float_2dp should round to 2 decimal places."""
        kwargs = _valid_signal_kwargs()
        kwargs["close"] = 500.123456
        s = Signal(**kwargs)
        assert s.close == 500.12

    def test_slope_rounded_4dp(self):
        """slope_5 uses round_float_4dp."""
        kwargs = _valid_signal_kwargs()
        kwargs["slope_5"] = 0.00512345
        s = Signal(**kwargs)
        assert s.slope_5 == 0.0051

    def test_cost_ratio_optional_on_signal(self):
        """Signal has cost_ratio as Optional[float] = None."""
        kwargs = _valid_signal_kwargs()
        # Without cost_ratio → defaults to None
        s = Signal(**kwargs)
        assert s.cost_ratio is None

    def test_cost_ratio_can_be_set_on_signal(self):
        """Signal CAN accept cost_ratio (it's Optional)."""
        kwargs = _valid_signal_kwargs()
        kwargs["cost_ratio"] = 0.15
        s = Signal(**kwargs)
        assert s.cost_ratio == 0.15

    def test_strategy_type_default_swing(self):
        kwargs = _valid_signal_kwargs()
        del kwargs["strategy_type"]
        s = Signal(**kwargs)
        assert s.strategy_type == "SWING"

    def test_stale_data_default_false(self):
        s = Signal(**_valid_signal_kwargs())
        assert s.stale_data is False


# ═══════════════════════════════════════════════════════════════
# MOMENTUM SIGNAL MODEL
# ═══════════════════════════════════════════════════════════════


class TestMomentumSignalModel:

    def test_valid_momentum_signal(self):
        ms = MomentumSignal(**_valid_momentum_signal_kwargs())
        assert ms.strategy_type == "MOMENTUM"
        assert ms.cost_ratio == 0.12

    def test_cost_ratio_required(self):
        """MomentumSignal requires cost_ratio (not Optional)."""
        kwargs = _valid_momentum_signal_kwargs()
        del kwargs["cost_ratio"]
        with pytest.raises(ValidationError):
            MomentumSignal(**kwargs)

    def test_product_type_mis_allowed(self):
        """MomentumSignal allows product_type='MIS'."""
        kwargs = _valid_momentum_signal_kwargs()
        kwargs["product_type"] = "MIS"
        ms = MomentumSignal(**kwargs)
        assert ms.product_type == "MIS"

    def test_product_type_cnc_allowed(self):
        kwargs = _valid_momentum_signal_kwargs()
        kwargs["product_type"] = "CNC"
        ms = MomentumSignal(**kwargs)
        assert ms.product_type == "CNC"

    def test_product_type_invalid_rejected(self):
        """Only MIS and CNC are valid product types."""
        kwargs = _valid_momentum_signal_kwargs()
        kwargs["product_type"] = "NRML"
        with pytest.raises(ValidationError):
            MomentumSignal(**kwargs)

    def test_strategy_type_must_be_momentum(self):
        """MomentumSignal.strategy_type must be 'MOMENTUM'."""
        kwargs = _valid_momentum_signal_kwargs()
        kwargs["strategy_type"] = "SWING"
        with pytest.raises(ValidationError):
            MomentumSignal(**kwargs)

    def test_float_rounding_2dp(self):
        kwargs = _valid_momentum_signal_kwargs()
        kwargs["close"] = 3500.999
        ms = MomentumSignal(**kwargs)
        assert ms.close == 3501.0


# ═══════════════════════════════════════════════════════════════
# PORTFOLIO RESPONSE
# ═══════════════════════════════════════════════════════════════


class TestPortfolioResponse:

    def test_valid_portfolio_response(self):
        pr = PortfolioResponse(
            run_time=datetime.utcnow(),
            market_regime="BULL",
            backtest_gate="NOT_RUN",
            trading_halted=False,
            halt_reasons=[],
            stale_data=False,
            total_capital_at_risk=250.0,
            total_capital_deployed=5000.0,
            bankroll_utilization_pct=0.50,
            open_positions_count=1,
            remaining_slots=5,
            signals=[]
        )
        assert pr.market_regime == "BULL"

    def test_backtest_gate_not_run(self):
        """PortfolioResponse.backtest_gate accepts 'NOT_RUN'."""
        pr = PortfolioResponse(
            run_time=datetime.utcnow(), market_regime="BULL",
            backtest_gate="NOT_RUN", trading_halted=False,
            halt_reasons=[], stale_data=False,
            total_capital_at_risk=0, total_capital_deployed=0,
            bankroll_utilization_pct=0, open_positions_count=0,
            remaining_slots=6, signals=[]
        )
        assert pr.backtest_gate == "NOT_RUN"

    def test_invalid_regime_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioResponse(
                run_time=datetime.utcnow(), market_regime="INVALID",
                backtest_gate="PASS", trading_halted=False,
                halt_reasons=[], stale_data=False,
                total_capital_at_risk=0, total_capital_deployed=0,
                bankroll_utilization_pct=0, open_positions_count=0,
                remaining_slots=6, signals=[]
            )


# ═══════════════════════════════════════════════════════════════
# OPEN POSITION MODEL
# ═══════════════════════════════════════════════════════════════


class TestOpenPositionModel:

    def _valid_kwargs(self):
        return dict(
            ticker="INFY", exchange="NSE", entry_date=datetime.utcnow(),
            entry_price=1500.0, shares=5, stop_loss_initial=1450.0,
            trailing_stop_current=1460.0, target_1=1575.0, target_2=1650.0,
            atr_14_at_entry=33.33, highest_close_since_entry=1520.0,
            status="OPEN", source="SYSTEM"
        )

    def test_valid_open_position(self):
        op = OpenPosition(**self._valid_kwargs())
        assert op.status == "OPEN"

    def test_valid_statuses(self):
        for status in ["OPEN", "CLOSED_T1", "CLOSED_T2", "STOPPED_OUT", "CLOSED_TIME", "CLOSED_MANUAL"]:
            kwargs = self._valid_kwargs()
            kwargs["status"] = status
            op = OpenPosition(**kwargs)
            assert op.status == status

    def test_invalid_status_rejected(self):
        kwargs = self._valid_kwargs()
        kwargs["status"] = "PENDING"
        with pytest.raises(ValidationError):
            OpenPosition(**kwargs)

    def test_valid_sources(self):
        for source in ["SYSTEM", "MANUAL", "MOMENTUM"]:
            kwargs = self._valid_kwargs()
            kwargs["source"] = source
            op = OpenPosition(**kwargs)
            assert op.source == source

    def test_invalid_source_rejected(self):
        kwargs = self._valid_kwargs()
        kwargs["source"] = "BOT"
        with pytest.raises(ValidationError):
            OpenPosition(**kwargs)


# ═══════════════════════════════════════════════════════════════
# LEDGER & BANKROLL MODELS
# ═══════════════════════════════════════════════════════════════


class TestLedgerRow:

    def test_valid_ledger_row(self):
        lr = LedgerRow(
            id=1, timestamp=datetime.utcnow(),
            event_type="TRADE_CLOSED", ticker="RELIANCE",
            pnl=100.0, bankroll_before=5000.0, bankroll_after=5100.0,
            notes="Profit"
        )
        assert lr.event_type == "TRADE_CLOSED"

    def test_invalid_event_type(self):
        with pytest.raises(ValidationError):
            LedgerRow(
                id=1, timestamp=datetime.utcnow(),
                event_type="INVALID", ticker="X",
                pnl=0, bankroll_before=5000, bankroll_after=5000
            )


class TestBankrollAdjustment:

    def test_valid_deposit(self):
        ba = BankrollAdjustment(
            amount=1000.0, event_type="MANUAL_DEPOSIT", notes="Top up"
        )
        assert ba.event_type == "MANUAL_DEPOSIT"

    def test_invalid_event_type(self):
        with pytest.raises(ValidationError):
            BankrollAdjustment(
                amount=1000.0, event_type="TRADE_CLOSED", notes="Nope"
            )
