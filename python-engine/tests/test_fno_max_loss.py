"""
[FNO-MAX-LOSS 2026-07-10] The heaviest-covered function in the repo
(spec §4). 100% branch coverage on fno_risk.max_loss is a P0 exit
criterion and a go-live gate. The §4 truth table is encoded verbatim.

Run coverage locally with:
  pytest tests/test_fno_max_loss.py --cov=fno_risk --cov-branch
"""
import math

import pytest

from fno_models import Leg, OptionType
from fno_risk import lots_for_pool, max_loss, min_viable_pool, validate_position

LOT = 75


def _ce(strike, qty, prem):
    return Leg(opt_type=OptionType.CE, strike=strike, quantity=qty, premium=prem)


def _pe(strike, qty, prem):
    return Leg(opt_type=OptionType.PE, strike=strike, quantity=qty, premium=prem)


# ---------------------------------------------------------------------------
# §4 truth table
# ---------------------------------------------------------------------------

def test_long_ce_max_loss_is_debit():
    assert max_loss([_ce(25000, 1, 100.0)], LOT) == pytest.approx(100.0 * LOT)


def test_long_pe_max_loss_is_debit():
    assert max_loss([_pe(25000, 1, 80.0)], LOT) == pytest.approx(80.0 * LOT)


def test_bull_call_spread_net_debit():
    # long 25000 CE @100, short 25100 CE @60 -> net debit 40
    legs = [_ce(25000, 1, 100.0), _ce(25100, -1, 60.0)]
    assert max_loss(legs, LOT) == pytest.approx(40.0 * LOT)


def test_bear_call_spread_width_minus_credit():
    # short 25000 CE @100, long 25100 CE @60 -> credit 40, width 100
    legs = [_ce(25000, -1, 100.0), _ce(25100, 1, 60.0)]
    assert max_loss(legs, LOT) == pytest.approx((100.0 - 40.0) * LOT)


def test_iron_condor_width_minus_credit():
    # put wing: long 24800 @20, short 24900 @45 (credit 25)
    # call wing: short 25100 @45, long 25200 @20 (credit 25)
    # width 100, total credit 50 -> max loss 50/pt
    legs = [
        _pe(24800, 1, 20.0), _pe(24900, -1, 45.0),
        _ce(25100, -1, 45.0), _ce(25200, 1, 20.0),
    ]
    assert max_loss(legs, LOT) == pytest.approx(50.0 * LOT)


def test_naked_short_call_is_inf():
    assert math.isinf(max_loss([_ce(25000, -1, 100.0)], LOT))


def test_ratio_spread_is_inf():
    # long 1 CE 25000, short 2 CE 25100 -> slope_right = -1
    legs = [_ce(25000, 1, 100.0), _ce(25100, -2, 60.0)]
    assert math.isinf(max_loss(legs, LOT))


def test_short_put_is_finite_but_large():
    # slope_right = 0 (no calls); worst case at S=0: K - premium
    legs = [_pe(25000, -1, 80.0)]
    assert max_loss(legs, LOT) == pytest.approx((25000.0 - 80.0) * LOT)


# ---------------------------------------------------------------------------
# edges / branches
# ---------------------------------------------------------------------------

def test_empty_legs_zero():
    assert max_loss([], LOT) == 0.0


def test_bad_lot_size_raises():
    with pytest.raises(ValueError):
        max_loss([_ce(25000, 1, 100.0)], 0)


def test_floor_at_zero():
    # Free call (premium 0) can never lose -> floored at 0.
    assert max_loss([_ce(25000, 1, 0.0)], LOT) == 0.0


def test_multi_lot_scales():
    assert max_loss([_ce(25000, 2, 100.0)], LOT) == pytest.approx(2 * 100.0 * LOT)


# ---------------------------------------------------------------------------
# validate_position -- the order-path gate
# ---------------------------------------------------------------------------

def test_validate_rejects_unbounded_unconditionally():
    ok, reason, ml = validate_position([_ce(25000, -1, 100.0)], LOT)
    assert not ok
    assert reason == "max_loss_unbounded"
    assert math.isinf(ml)


def test_validate_no_override_parameter_exists():
    """Spec §4: no force=True kwarg, no code path around the inf reject."""
    import inspect
    params = inspect.signature(validate_position).parameters
    assert "force" not in params
    assert set(params) == {"legs", "lot_size", "max_loss_cap"}


def test_validate_rejects_over_structural_cap():
    # 2 lots @ 100 = Rs 15,000 structural > 12,000 default cap
    ok, reason, ml = validate_position([_ce(25000, 2, 100.0)], LOT)
    assert not ok
    assert reason == "max_loss_over_cap"
    assert ml == pytest.approx(15000.0)


def test_validate_accepts_normal_long():
    ok, reason, ml = validate_position([_ce(25000, 1, 100.0)], LOT)
    assert ok and reason == ""
    assert ml == pytest.approx(7500.0)


def test_validate_custom_cap():
    ok, reason, _ = validate_position([_ce(25000, 1, 100.0)], LOT, max_loss_cap=5000.0)
    assert not ok and reason == "max_loss_over_cap"


# ---------------------------------------------------------------------------
# §3 capital arithmetic
# ---------------------------------------------------------------------------

def test_min_viable_pool_spec_numbers():
    # P=100, L=75, s=25%, cap 2% -> Rs 93,750
    assert min_viable_pool(100.0, 75, 0.25, 0.02) == pytest.approx(93750.0)
    # P=150 -> Rs 1,40,625 (the spec's "we do not have it" day)
    assert min_viable_pool(150.0, 75, 0.25, 0.02) == pytest.approx(140625.0)


def test_min_viable_pool_zero_risk_pct_is_inf():
    assert math.isinf(min_viable_pool(100.0, 75, 0.25, 0.0))


def test_lots_for_pool_declines_rich_premium():
    # P=150: risk/lot 2,812 > min(2000, 2500) -> 0 lots, never oversize
    assert lots_for_pool(100000.0, 150.0, 75, 0.25, 0.02, 2) == 0


def test_lots_for_pool_one_lot_at_typical_premium():
    # P=100: risk/lot 1,875 <= 2,000 budget -> exactly 1 lot
    assert lots_for_pool(100000.0, 100.0, 75, 0.25, 0.02, 2) == 1


def test_lots_for_pool_caps_at_max_lots():
    # P=40: risk/lot 750 -> budget admits 2 (capped by max_lots)
    assert lots_for_pool(100000.0, 40.0, 75, 0.25, 0.02, 2) == 2


def test_lots_for_pool_degenerate_inputs():
    assert lots_for_pool(100000.0, 0.0, 75, 0.25, 0.02, 2) == 0
    assert lots_for_pool(100000.0, 100.0, 0, 0.25, 0.02, 2) == 0
    assert lots_for_pool(100000.0, 100.0, 75, 0.0, 0.02, 2) == 0


def test_lots_for_pool_respects_rupee_cap_override():
    # With a Rs 1,000 cap, P=100 (risk/lot 1,875) admits nothing.
    assert lots_for_pool(100000.0, 100.0, 75, 0.25, 0.02, 2, max_risk_rupees=1000.0) == 0
