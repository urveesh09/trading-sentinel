"""
[PENNY-MODELS 2026-06-21] Tests for PennySignal, PennyRegime, PennyLeg.
Mirrors the field-validation pattern from tests/test_models.py.
"""
from datetime import datetime
import pytest


def test_penny_signal_constructs_with_all_fields():
    from penny_models import PennySignal, PennyRegime, PennyLeg
    sig = PennySignal(
        scan_id="test-001",
        ticker="ABC",
        exchange="NSE",
        signal_time=datetime(2026, 6, 21, 9, 30),
        leg=PennyLeg.CNC,
        regime=PennyRegime.PR1_CALM,
        close=10.50,
        stop_loss=10.18,
        target_1=10.82,
        target_2=11.13,
        trailing_stop=10.55,
        shares=100,
        capital_deployed=1050.0,
        capital_at_risk=100.0,
        net_ev=200.0,
        entry_order_type="LIMIT",
        sl_order_type="SL-M",
        strategy_version="1.0.0",
    )
    assert sig.ticker == "ABC"
    assert sig.leg == PennyLeg.CNC
    assert sig.regime == PennyRegime.PR1_CALM
    assert sig.entry_order_type == "LIMIT"
    assert sig.sl_order_type == "SL-M"
    assert sig.scan_id == "test-001"


def test_penny_signal_rejects_invalid_leg():
    from penny_models import PennySignal, PennyRegime, PennyLeg
    with pytest.raises(Exception):
        PennySignal(
            scan_id="x",
            ticker="XYZ",
            exchange="NSE",
            signal_time=datetime(2026, 6, 21, 9, 30),
            leg="GARBAGE",
            regime=PennyRegime.PR1_CALM,
            close=10.0,
            stop_loss=9.5,
            target_1=11.0,
            target_2=12.0,
            trailing_stop=0.0,
            shares=1,
            capital_deployed=10.0,
            capital_at_risk=0.5,
            net_ev=1.0,
            entry_order_type="LIMIT",
            sl_order_type="SL-M",
            strategy_version="1.0.0",
        )


def test_penny_regime_enum_members():
    from penny_models import PennyRegime
    assert PennyRegime.PR1_CALM.value == "PR1_CALM"
    assert PennyRegime.PR2_ELEVATED.value == "PR2_ELEVATED"
    assert PennyRegime.PR3_HOT.value == "PR3_HOT"
    assert PennyRegime.UNKNOWN.value == "UNKNOWN"


def test_penny_leg_enum_members():
    from penny_models import PennyLeg
    assert PennyLeg.CNC.value == "CNC"
    assert PennyLeg.MIS.value == "MIS"
