"""
[FNO-DEFINED-RISK 2026-07-20] Tests for the defined-risk structure layer of
the F&O paper book. Every structure must be provably capped-loss (finite
max_loss) and its profile must agree with the audited fno_risk payoff
primitives -- a defined-risk book whose loss is secretly unbounded is the one
failure this layer exists to prevent.
"""
import math

import pytest

from fno_defined_risk import (
    RouterParams, Structure, StructureKind,
    build_debit_spread, build_iron_condor, select_structure,
    structure_round_trip_cost, net_entry_credit_rs,
)
from fno_models import FnoDirection, OptionType
import fno_risk

STEP = 50.0
LOT = 75          # NIFTY post Nov-2024
ATM = 25000.0


def _prem_lookup(table):
    """table: {(OptionType, strike): premium}. Missing -> None."""
    def prem(opt, strike):
        return table.get((opt, float(strike)))
    return prem


# --------------------------------------------------------------------------
# Debit spread
# --------------------------------------------------------------------------

def test_call_debit_spread_is_capped_and_consistent():
    prem = _prem_lookup({
        (OptionType.CE, 25000.0): 120.0,   # long ATM
        (OptionType.CE, 25100.0): 50.0,    # short OTM (width=2 steps)
    })
    s = build_debit_spread(FnoDirection.LONG, ATM, STEP, 2, prem, LOT)
    assert s is not None
    assert s.kind == StructureKind.DEBIT_SPREAD
    assert s.is_defined_risk and math.isfinite(s.max_loss_rs)

    net_debit = 120.0 - 50.0            # 70 per unit
    assert s.max_loss_rs == pytest.approx(net_debit * LOT)            # 5250
    assert s.max_profit_rs == pytest.approx((100.0 - net_debit) * LOT)  # 2250
    assert s.breakevens == [pytest.approx(25000.0 + net_debit)]        # 25070
    # net_premium is a debit (cash out) -> negative
    assert s.net_premium < 0
    assert net_entry_credit_rs(s) == pytest.approx(-net_debit * LOT)

    # Cross-check the cap against the risk constitution directly.
    assert s.max_loss_rs == pytest.approx(fno_risk.max_loss(s.legs, LOT))


def test_put_debit_spread_bearish_side():
    prem = _prem_lookup({
        (OptionType.PE, 25000.0): 110.0,
        (OptionType.PE, 24900.0): 45.0,
    })
    s = build_debit_spread(FnoDirection.SHORT, ATM, STEP, 2, prem, LOT)
    assert s is not None
    net_debit = 110.0 - 45.0            # 65
    assert s.max_loss_rs == pytest.approx(net_debit * LOT)
    assert s.breakevens == [pytest.approx(25000.0 - net_debit)]        # 24935


def test_debit_spread_rejects_nonpositive_debit_and_missing_legs():
    # short premium >= long premium -> not a real debit
    bad = _prem_lookup({(OptionType.CE, 25000.0): 40.0, (OptionType.CE, 25100.0): 55.0})
    assert build_debit_spread(FnoDirection.LONG, ATM, STEP, 2, bad, LOT) is None
    # missing short strike
    miss = _prem_lookup({(OptionType.CE, 25000.0): 120.0})
    assert build_debit_spread(FnoDirection.LONG, ATM, STEP, 2, miss, LOT) is None


# --------------------------------------------------------------------------
# Iron condor
# --------------------------------------------------------------------------

def test_iron_condor_is_capped_and_consistent():
    prem = _prem_lookup({
        (OptionType.CE, 25200.0): 40.0,   # short call
        (OptionType.CE, 25300.0): 20.0,   # long call wing
        (OptionType.PE, 24800.0): 42.0,   # short put
        (OptionType.PE, 24700.0): 22.0,   # long put wing
    })
    s = build_iron_condor(ATM, STEP, short_offset=4, wing_width=2, prem=prem, lot_size=LOT)
    assert s is not None
    assert s.kind == StructureKind.IRON_CONDOR
    assert s.is_defined_risk

    credit = (40.0 + 42.0) - (20.0 + 22.0)     # 40 per unit
    wing = 2 * STEP                            # 100
    assert s.net_premium == pytest.approx(credit)          # positive = credit
    assert s.max_profit_rs == pytest.approx(credit * LOT)          # 3000
    assert s.max_loss_rs == pytest.approx((wing - credit) * LOT)   # 4500
    assert s.max_loss_rs == pytest.approx(fno_risk.max_loss(s.legs, LOT))
    # two breakevens straddling ATM
    assert len(s.breakevens) == 2
    lo, hi = s.breakevens
    assert lo == pytest.approx(24800.0 - credit)   # 24760
    assert hi == pytest.approx(25200.0 + credit)   # 25240
    assert net_entry_credit_rs(s) == pytest.approx(credit * LOT)


def test_iron_condor_rejects_nonpositive_credit():
    # wings cost more than the shorts collect -> no credit
    prem = _prem_lookup({
        (OptionType.CE, 25200.0): 20.0, (OptionType.CE, 25300.0): 25.0,
        (OptionType.PE, 24800.0): 20.0, (OptionType.PE, 24700.0): 25.0,
    })
    assert build_iron_condor(ATM, STEP, 4, 2, prem, LOT) is None


def test_no_structure_has_unbounded_loss():
    """The one invariant that matters: whatever we build, max_loss is finite."""
    prem = _prem_lookup({
        (OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0,
        (OptionType.CE, 25200.0): 40.0, (OptionType.CE, 25300.0): 20.0,
        (OptionType.PE, 24800.0): 42.0, (OptionType.PE, 24700.0): 22.0,
    })
    ds = build_debit_spread(FnoDirection.LONG, ATM, STEP, 2, prem, LOT)
    ic = build_iron_condor(ATM, STEP, 4, 2, prem, LOT)
    for s in (ds, ic):
        assert s is not None and math.isfinite(s.max_loss_rs) and s.max_loss_rs > 0


# --------------------------------------------------------------------------
# Regime router
# --------------------------------------------------------------------------

def test_router_directional_signal_gives_debit_spread():
    assert select_structure(True, iv_rank=0.3, expected_move_pct=0.006) == StructureKind.DEBIT_SPREAD


def test_router_directional_but_dead_flat_stands_aside():
    # expected move below the debit floor -> not worth paying premium
    assert select_structure(True, iv_rank=0.3, expected_move_pct=0.002) is None


def test_router_range_and_rich_iv_gives_condor():
    assert select_structure(False, iv_rank=0.6, expected_move_pct=0.008) == StructureKind.IRON_CONDOR


def test_router_stands_aside_when_iv_cheap_or_move_too_big():
    assert select_structure(False, iv_rank=0.40, expected_move_pct=0.008) is None   # IV not rich
    assert select_structure(False, iv_rank=0.70, expected_move_pct=0.020) is None   # move too big
    assert select_structure(False, iv_rank=None, expected_move_pct=None) is None


def test_router_params_are_overridable():
    p = RouterParams(min_iv_rank_condor=0.9)
    assert select_structure(False, iv_rank=0.6, expected_move_pct=0.005, params=p) is None


# --------------------------------------------------------------------------
# Cost model
# --------------------------------------------------------------------------

def test_condor_costs_more_to_churn_than_a_two_leg_spread():
    prem = _prem_lookup({
        (OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0,
        (OptionType.CE, 25200.0): 40.0, (OptionType.CE, 25300.0): 20.0,
        (OptionType.PE, 24800.0): 42.0, (OptionType.PE, 24700.0): 22.0,
    })
    ds = build_debit_spread(FnoDirection.LONG, ATM, STEP, 2, prem, LOT)
    ic = build_iron_condor(ATM, STEP, 4, 2, prem, LOT)
    ds_cost = structure_round_trip_cost(ds)
    ic_cost = structure_round_trip_cost(ic)
    assert ds_cost > 0 and ic_cost > 0
    assert ic_cost > ds_cost      # 4 legs each pay their own brokerage + taxes
