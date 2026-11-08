import pytest

from round34 import geometry, strikes


def test_strikes_are_strictly_out_of_the_money_for_each_right():
    assert strikes(24397., "CE") == (24400, 24450, 24500)
    assert strikes(24397., "PE") == (24350, 24300, 24250)
    assert strikes(24400., "PE") == (24350, 24300, 24250)


def test_geometry_cannot_increase_full_cash_or_estimated_stop_loss():
    row = {"entry_premium": 100., "delta_at_entry": .55, "extra_cost": 205., "n11_entry": {}}

    def fees(_a, _b, _n):
        return 50.

    assert geometry(row, 50., 49., .30, fees) == ("delta", None)
    assert geometry(row, 50., 49., .32, fees) == ("cash", None)
    status, data = geometry(row, 45., 44., .32, fees)
    assert status == "eligible"
    assert data["stop"] == pytest.approx(33.75)
    assert data["modeled_stop_loss"] <= data["native_modeled_stop_loss"]
    assert data["new_reserve"] <= data["native_reserve"]
