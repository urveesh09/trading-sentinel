"""
[FNO-COSTS-TESTS 2026-07-10] Cost model (spec §10.2). The spec's own
estimate is ~Rs 55 on a Rs 7,500 round trip (~0.7%); with the post-Oct-
2024 STT (0.1% sell side) the honest figure is ~Rs 61. Bounds below are
deliberately loose enough to survive small schedule changes but tight
enough to catch a decimal slip.
"""
import pytest

from config import settings
from fno_costs import breakeven_move_pct, calc_fno_costs


def test_round_trip_one_lot_rs100():
    # 1 lot (75 units) at Rs 100 in, Rs 100 out. Hand arithmetic:
    # brokerage 40 + stt 7.5 + txn 5.25 + sebi 0.015 + stamp 0.225
    # + ipft 0.075 + gst 8.15 = ~61.2
    cost = calc_fno_costs(100.0, 100.0, 75)
    assert cost == pytest.approx(61.22, abs=1.0)


def test_flat_fee_dominates_small_premium():
    """Spec §10.2: flat fees punish small premiums -- the structural
    argument for fewer, larger positions."""
    small = calc_fno_costs(20.0, 20.0, 75)   # Rs 1,500 position
    big = calc_fno_costs(200.0, 200.0, 75)   # Rs 15,000 position
    small_pct = small / (20.0 * 75)
    big_pct = big / (200.0 * 75)
    assert small_pct > big_pct * 2


def test_costs_scale_with_qty():
    one_lot = calc_fno_costs(100.0, 100.0, 75)
    two_lots = calc_fno_costs(100.0, 100.0, 150)
    # variable parts double, flat brokerage does not
    assert one_lot < two_lots < 2 * one_lot


def test_stt_is_sell_side_only():
    cheap_exit = calc_fno_costs(100.0, 10.0, 75)
    rich_exit = calc_fno_costs(100.0, 200.0, 75)
    assert rich_exit > cheap_exit  # sell value drives STT


def test_degenerate_inputs_zero():
    assert calc_fno_costs(100.0, 100.0, 0) == 0.0
    assert calc_fno_costs(-1.0, 100.0, 75) == 0.0
    assert calc_fno_costs(100.0, -1.0, 75) == 0.0


def test_breakeven_move_pct_near_spec_estimate():
    # ~0.8% of premium at Rs 100 x 75 (spec said ~0.7% pre-Oct-2024 STT)
    be = breakeven_move_pct(100.0, 75)
    assert 0.005 < be < 0.012
    assert breakeven_move_pct(0.0, 75) == 0.0


def test_no_brokerage_bypass_exists():
    """Spec §10.2: there is no FNO_BROKERAGE_BYPASS. Cost is a first-order
    term; hiding it would make the paper leg lie. If someone adds the
    flag, this test fails and forces the conversation."""
    assert not hasattr(settings, "FNO_BROKERAGE_BYPASS")
