"""[WORKFLOW-E.5 2026-09-17] Tests for liquidity-aware sizing.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Explain uncertainty and liquidity limits without
> overwhelming the message.

The sizing helper classifies each leg as SURPLUS / TIGHT /
INSUFFICIENT based on the requested contracts vs the
top-of-book depth (bid_quantity for SELL, ask_quantity for
BUY).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ENGINE = Path(__file__).resolve().parents[1] / "python-engine"
sys.path.insert(0, str(PYTHON_ENGINE))

from partner_sizing import (  # noqa: E402  -- import path
    LiquiditySizingResult,
    LiquidityTier,
    compute_liquidity_sizing,
)


def _leg(side: str, ask_qty: int | None = None,
          bid_qty: int | None = None, tradingsymbol: str = "SYM"):
    out: dict = {"side": side, "tradingsymbol": tradingsymbol}
    if ask_qty is not None:
        out["ask_quantity"] = ask_qty
    if bid_qty is not None:
        out["bid_quantity"] = bid_qty
    return out


# -- 1. Tier classification --------------------------------------


def test_buy_leg_with_ask_quantity_uses_ask_depth():
    """[WORKFLOW-E.5 2026-09-17] BUY consumes ask_quantity
    (you hit the ask); SELL consumes bid_quantity."""
    card = {"legs": [_leg("BUY", ask_qty=100, bid_qty=1)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.per_leg[0].top_of_book_quantity == 100


def test_sell_leg_with_bid_quantity_uses_bid_depth():
    card = {"legs": [_leg("SELL", ask_qty=1, bid_qty=50)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.per_leg[0].top_of_book_quantity == 50


def test_requested_5x_smaller_than_depth_is_surplus():
    """[WORKFLOW-E.5 2026-09-17] SURPLUS = ratio >= 5x."""
    card = {"legs": [_leg("BUY", ask_qty=10)]}
    r = compute_liquidity_sizing(card, requested_contracts=2)
    assert r.per_leg[0].tier == LiquidityTier.SURPLUS


def test_requested_3x_smaller_than_depth_is_tight():
    """[WORKFLOW-E.5 2026-09-17] TIGHT = 1x <= ratio < 5x."""
    card = {"legs": [_leg("BUY", ask_qty=3)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.per_leg[0].tier == LiquidityTier.TIGHT


def test_requested_exactly_at_depth_is_tight():
    card = {"legs": [_leg("BUY", ask_qty=1)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.per_leg[0].tier == LiquidityTier.TIGHT


def test_requested_exceeds_depth_is_insufficient():
    card = {"legs": [_leg("BUY", ask_qty=2)]}
    r = compute_liquidity_sizing(card, requested_contracts=5)
    assert r.per_leg[0].tier == LiquidityTier.INSUFFICIENT


def test_zero_top_of_book_is_insufficient():
    card = {"legs": [_leg("BUY", ask_qty=0)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.per_leg[0].tier == LiquidityTier.INSUFFICIENT


def test_missing_top_of_book_is_insufficient_with_warning():
    card = {"legs": [_leg("BUY")]}  # No bid/ask quantity.
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.per_leg[0].tier == LiquidityTier.INSUFFICIENT
    assert any("no ask_quantity" in w for w in r.warnings)


# -- 2. Fillable ------------------------------------------------


def test_fillable_is_min_of_requested_and_depth():
    card = {"legs": [_leg("BUY", ask_qty=3)]}
    r = compute_liquidity_sizing(card, requested_contracts=10)
    assert r.per_leg[0].fillable_contracts == 3


def test_fillable_caps_at_requested_when_depth_is_surplus():
    card = {"legs": [_leg("BUY", ask_qty=1000)]}
    r = compute_liquidity_sizing(card, requested_contracts=2)
    assert r.per_leg[0].fillable_contracts == 2


def test_max_fillable_is_min_across_legs():
    """[WORKFLOW-E.5 2026-09-17] A spread is bottlenecked by
    the leg with the least depth."""
    card = {"legs": [
        _leg("BUY", ask_qty=100, tradingsymbol="A"),
        _leg("SELL", bid_qty=2, tradingsymbol="B"),
    ]}
    r = compute_liquidity_sizing(card, requested_contracts=5)
    assert r.max_fillable_contracts == 2


# -- 3. Slippage / walk-the-book -------------------------------


def test_no_slippage_when_depth_covers_requested():
    card = {"legs": [_leg("BUY", ask_qty=100)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.walk_the_book_cost_bps == 0.0


def test_walk_the_book_cost_bps_grows_linearly_past_depth():
    """[WORKFLOW-E.5 2026-09-17] Each contract past depth
    costs ``walk_step_bps`` (default 5)."""
    card = {"legs": [_leg("BUY", ask_qty=1)]}
    r = compute_liquidity_sizing(card, requested_contracts=4,
                                    walk_step_bps=5.0)
    # 3 contracts past depth * 5 bps = 15 bps.
    assert r.per_leg[0].slippage_bps_to_fill_requested == 15.0
    assert r.walk_the_book_cost_bps == 15.0


def test_total_slippage_is_sum_across_legs():
    card = {"legs": [
        _leg("BUY", ask_qty=1, tradingsymbol="A"),
        _leg("SELL", bid_qty=1, tradingsymbol="B"),
    ]}
    r = compute_liquidity_sizing(card, requested_contracts=3,
                                    walk_step_bps=5.0)
    # Each leg: 2 contracts past depth * 5 = 10 bps; total 20.
    assert r.walk_the_book_cost_bps == 20.0


def test_custom_walk_step_bps():
    card = {"legs": [_leg("BUY", ask_qty=1)]}
    r = compute_liquidity_sizing(card, requested_contracts=3,
                                    walk_step_bps=10.0)
    # 2 contracts past depth * 10 = 20 bps.
    assert r.walk_the_book_cost_bps == 20.0


def test_slippage_above_tolerance_warns():
    card = {"legs": [_leg("BUY", ask_qty=1)]}
    r = compute_liquidity_sizing(card, requested_contracts=20,
                                    walk_step_bps=5.0,
                                    slippage_tolerance_bps=50.0)
    # 19 contracts past * 5 = 95 bps; > 50 bps tolerance.
    assert any("exceeds tolerance" in w for w in r.warnings)


def test_slippage_below_tolerance_no_warn():
    card = {"legs": [_leg("BUY", ask_qty=100)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert not any("exceeds tolerance" in w for w in r.warnings)


# -- 4. Aggregate tier ----------------------------------------


def test_aggregate_tier_is_worst_case():
    """[WORKFLOW-E.5 2026-09-17] One INSUFFICIENT leg ->
    whole card INSUFFICIENT."""
    card = {"legs": [
        _leg("BUY", ask_qty=1000, tradingsymbol="A"),
        _leg("SELL", bid_qty=0, tradingsymbol="B"),
    ]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.liquidity_tier == LiquidityTier.INSUFFICIENT


def test_aggregate_tier_tight_when_all_tight():
    card = {"legs": [
        _leg("BUY", ask_qty=2, tradingsymbol="A"),
        _leg("SELL", bid_qty=3, tradingsymbol="B"),
    ]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.liquidity_tier == LiquidityTier.TIGHT


def test_aggregate_tier_surplus_when_all_surplus():
    card = {"legs": [
        _leg("BUY", ask_qty=1000, tradingsymbol="A"),
        _leg("SELL", bid_qty=1000, tradingsymbol="B"),
    ]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert r.liquidity_tier == LiquidityTier.SURPLUS


# -- 5. Error handling -----------------------------------------


def test_raises_on_empty_legs():
    with pytest.raises(ValueError):
        compute_liquidity_sizing({"legs": []}, requested_contracts=1)


def test_raises_on_missing_legs_key():
    with pytest.raises(ValueError):
        compute_liquidity_sizing({}, requested_contracts=1)


def test_skips_invalid_leg_with_warning():
    """[WORKFLOW-E.5 2026-09-17] Invalid legs (not dicts)
    are skipped with a warning; valid legs still processed."""
    card = {"legs": [
        _leg("BUY", ask_qty=100),
        "not a dict",
    ]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    assert len(r.per_leg) == 1
    assert any("not a dict" in w for w in r.warnings)


# -- 6. to_dict serialization --------------------------------


def test_to_dict_includes_all_fields():
    card = {"legs": [_leg("BUY", ask_qty=5)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    d = r.to_dict()
    assert set(d.keys()) == {
        "requested_contracts",
        "max_fillable_contracts",
        "walk_the_book_cost_bps",
        "liquidity_tier",
        "per_leg",
        "warnings",
    }
    assert d["liquidity_tier"] in {"SURPLUS", "TIGHT", "INSUFFICIENT"}
    assert isinstance(d["per_leg"], list)
    assert len(d["per_leg"]) == 1


def test_to_dict_per_leg_keys():
    card = {"legs": [_leg("BUY", ask_qty=5)]}
    r = compute_liquidity_sizing(card, requested_contracts=1)
    leg_d = r.to_dict()["per_leg"][0]
    assert set(leg_d.keys()) == {
        "leg_index",
        "tradingsymbol",
        "side",
        "requested_contracts",
        "top_of_book_quantity",
        "fillable_contracts",
        "slippage_bps_to_fill_requested",
        "tier",
    }


# -- 7. LiquidityTier.exit_code -------------------------------


def test_insufficient_tier_exit_code_is_one():
    assert LiquidityTier.INSUFFICIENT.exit_code() == 1


def test_surplus_and_tight_exit_code_is_zero():
    assert LiquidityTier.SURPLUS.exit_code() == 0
    assert LiquidityTier.TIGHT.exit_code() == 0
