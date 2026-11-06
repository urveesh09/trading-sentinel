import pytest

from round32 import EXTRA, LOT, Print, amounts, charges, options_cost_snapshot, selection, vertical


def test_selects_opposite_right_and_farther_hedge():
    assert vertical(24397.5, "LONG") == ("PE", 24350, 24300)
    assert vertical(24397.5, "SHORT") == ("CE", 24400, 24450)


def test_prices_short_buyback_at_ask_and_hedge_sale_at_bid():
    snapshot = options_cost_snapshot("NFO")
    short, hedge = Print(90., 90.2, 6000), Print(70., 70.2, 6000)
    cover, sale = Print(80., 80.2, 6000), Print(63., 63.2, 6000)
    gross, fees, net = amounts(short, hedge, cover, sale, snapshot)
    assert gross == pytest.approx(2.6 * LOT)
    assert fees == pytest.approx(charges(80.2, 90., snapshot) + charges(70.2, 63., snapshot))
    assert net == pytest.approx(gross - fees - 2 * EXTRA)


def test_admission_reserves_cash_and_preserves_parent_budget():
    snapshot = options_cost_snapshot("NFO")
    short, hedge = Print(90., 90.2, 6000), Print(70., 70.2, 6000)
    row = {"entry_premium": 200., "n11_entry": {}, "extra_cost": 205.,
           "n091_entry": {"pool": 250000., "open_reserve": 0.}}
    status, data = selection(row, short, hedge, snapshot)
    assert status == "selected"
    assert data["reserved_cash"] > data["planned_vertical_loss"]
    row["n11_entry"]["premium_stop"] = 190.
    assert selection(row, short, hedge, snapshot) == ("risk", None)
