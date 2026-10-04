"""[FNO-GROWTH] Capped-loss book: multi-lot sizing inside the max-loss and capital ceilings."""
import pytest

from fno_defined_risk import StructureKind, build_debit_spread, build_iron_condor, structure_round_trip_cost
from fno_dr_book import dr_lots, plan_structure
from fno_models import FnoDirection
from tests.test_fno_entry_plan import NOW, chain


def _prem(snapshot):
    return lambda opt_type, strike: (snapshot.quote(strike, opt_type).mid
                                     if snapshot.quote(strike, opt_type) else None)


def test_lots_respect_risk_budget_lot_ceiling_and_own_cash():
    # Debit spread ~Rs 2,900 per lot: the Rs 10,000 budget allows 3; the 3-lot ceiling holds.
    assert dr_lots(StructureKind.DEBIT_SPREAD, 2_900, pool=250_000, risk_multiplier=1.0) == 3
    # Condor ~Rs 4,550 per lot: budget allows 2; reserved margin (2 x 50k <= 40% of pool) allows 2.
    assert dr_lots(StructureKind.IRON_CONDOR, 4_550, pool=250_000, risk_multiplier=1.0) == 2
    # Smaller own cash limits the margin-hungry condor, not the debit spread.
    assert dr_lots(StructureKind.IRON_CONDOR, 4_550, pool=100_000, risk_multiplier=1.0) == 0
    assert dr_lots(StructureKind.DEBIT_SPREAD, 2_900, pool=100_000, risk_multiplier=1.0) == 3
    # Drawdown halves the budget; an oversized structure stands aside.
    assert dr_lots(StructureKind.DEBIT_SPREAD, 2_900, pool=250_000, risk_multiplier=0.5) == 1
    assert dr_lots(StructureKind.DEBIT_SPREAD, 12_000, pool=250_000, risk_multiplier=1.0) == 0
    # A cut never turns a normally affordable 1-lot structure into a halt.
    assert dr_lots(StructureKind.DEBIT_SPREAD, 6_000, pool=250_000, risk_multiplier=0.25) == 1


def test_builders_and_costs_scale_with_lots():
    snapshot = chain()
    prem = _prem(snapshot)
    one = build_debit_spread(FnoDirection.LONG, 25_000.0, 50.0, 2, prem, 65, 1)
    three = build_debit_spread(FnoDirection.LONG, 25_000.0, 50.0, 2, prem, 65, 3)
    assert [leg.quantity for leg in three.legs] == [3, -3]
    assert three.max_loss_rs == pytest.approx(3 * one.max_loss_rs, rel=1e-6)
    assert three.max_profit_rs == pytest.approx(3 * one.max_profit_rs, rel=1e-6)
    # Every leg is charged for its full quantity (flat brokerage per order does
    # not triple; turnover-based charges do).
    from fno_costs import calc_fno_costs
    expected = round(sum(calc_fno_costs(leg.premium, leg.premium, 3 * 65) for leg in three.legs), 2)
    assert structure_round_trip_cost(three) == pytest.approx(expected)
    assert structure_round_trip_cost(one) == pytest.approx(
        round(sum(calc_fno_costs(leg.premium, leg.premium, 65) for leg in one.legs), 2))
    condor = build_iron_condor(25_000.0, 50.0, 2, 2, prem, 65, 2)      # strikes within the test chain
    assert sorted(leg.quantity for leg in condor.legs) == [-2, -2, 2, 2]


def test_planned_debit_spread_is_sized_and_bound_to_contracts():
    planned = plan_structure(chain(), True, FnoDirection.LONG, NOW, pool=250_000, risk_multiplier=1.0)
    assert planned is not None and planned.lots >= 1
    s = planned.structure
    assert all(abs(leg.quantity) == planned.lots for leg in s.legs)
    assert all(abs(item["quantity"]) == planned.lots for item in planned.contract_legs)
    assert s.max_loss_rs <= 10_000 + 1e-6
    halved = plan_structure(chain(), True, FnoDirection.LONG, NOW, pool=250_000, risk_multiplier=0.25)
    assert halved is None or halved.lots <= planned.lots


def test_vehicle_follows_premium_richness(monkeypatch):
    from config import settings
    import fno_dr_book
    assert fno_dr_book.choose_directional_vehicle(chain(iv=0.20), NOW) == fno_dr_book.VEHICLE_SPREAD
    assert fno_dr_book.choose_directional_vehicle(chain(iv=0.12), NOW) == fno_dr_book.VEHICLE_NAKED
    assert fno_dr_book.choose_directional_vehicle(None, NOW) == fno_dr_book.VEHICLE_NAKED
    assert settings.FNO_VEHICLE_BY_IV is False and not fno_dr_book.vehicle_by_iv_active()
    monkeypatch.setattr(settings, "FNO_VEHICLE_BY_IV", True)
    assert fno_dr_book.vehicle_by_iv_active()
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    assert not fno_dr_book.vehicle_by_iv_active()           # no spread book, no deferral
