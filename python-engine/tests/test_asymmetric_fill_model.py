"""[WORKFLOW-C.C2 2026-09-15] Tests for the asymmetric
partial-fill pricing model.

Per the 2026-09-16 operator decisions:
> Q1: 'Filled at mid + 2bps' (estimate from mid-price)
> Q2: All exchanges same
> Q3: Partial counts as CLOSED with partial P&L
> Q4: No new operator-config knobs

These tests pin the contract:
- ``mid_price`` computes the top-of-book mid.
- ``estimate_missing_leg_price`` returns mid +/- slippage.
- ``compute_partial_fill_pnl`` aggregates per-leg P&L.
- Degenerate quotes (missing bid/ask) return None /
    contribute zero P&L.
- Negative slippage is rejected at the boundary.
- Side validation rejects malformed input.
"""
from __future__ import annotations

import math
import os
import sys

import pytest


HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from asymmetric_fill_model import (  # noqa: E402
    DEFAULT_MID_SLIPPAGE_BPS,
    compute_modeled_entry_slippage_pnl,
    compute_partial_fill_pnl,
    estimate_missing_leg_price,
    mid_price,
)


# ─── mid_price ──────────────────────────────────────────────


def test_mid_price_simple():
    """Mid price is (bid + ask) / 2."""
    assert mid_price(100.0, 102.0) == 101.0


def test_mid_price_float_inputs():
    """Integer and float bids/asks both work."""
    assert mid_price(99, 101) == 100.0
    assert mid_price(99.5, 100.5) == 100.0


def test_mid_price_returns_none_on_missing_bid():
    """Missing bid returns None -- the model is then
    degenerate and the caller should refuse.
    """
    assert mid_price(None, 101.0) is None


def test_mid_price_returns_none_on_missing_ask():
    """Missing ask returns None."""
    assert mid_price(100.0, None) is None


def test_mid_price_returns_none_on_non_positive():
    """Zero or negative bid/ask returns None."""
    assert mid_price(0.0, 101.0) is None
    assert mid_price(100.0, 0.0) is None
    assert mid_price(-1.0, 101.0) is None


def test_mid_price_returns_none_on_inverted_book():
    """Ask < bid returns None -- degenerate book."""
    assert mid_price(102.0, 100.0) is None


def test_mid_price_returns_none_on_non_numeric():
    """Non-numeric inputs return None."""
    assert mid_price("not-a-number", 101.0) is None
    assert mid_price(100.0, [1, 2]) is None
    assert mid_price(float("inf"), float("inf")) is None


# ─── estimate_missing_leg_price ─────────────────────────────


def test_estimate_missing_leg_price_buy_default_slippage():
    """BUY side: fill price = mid * (1 + 2bps).
    Mid = 100, 2bps = 0.0002. Expected = 100.02.
    """
    price = estimate_missing_leg_price(bid=99.0, ask=101.0, side="BUY")
    assert price is not None
    assert math.isclose(price, 100.02, rel_tol=1e-6)


def test_estimate_missing_leg_price_sell_default_slippage():
    """SELL side: fill price = mid * (1 - 2bps).
    Mid = 100, 2bps = 0.0002. Expected = 99.98.
    """
    price = estimate_missing_leg_price(bid=99.0, ask=101.0, side="SELL")
    assert price is not None
    assert math.isclose(price, 99.98, rel_tol=1e-6)


def test_estimate_missing_leg_price_custom_slippage():
    """Custom slippage is honoured."""
    price_buy = estimate_missing_leg_price(
        bid=99.0, ask=101.0, side="BUY", mid_slippage_bps=10.0,
    )
    assert price_buy is not None
    # Mid=100, 10bps = 0.001. Expected = 100.10.
    assert math.isclose(price_buy, 100.10, rel_tol=1e-6)


def test_estimate_missing_leg_price_zero_slippage_returns_mid():
    """Zero slippage returns the mid price exactly."""
    price = estimate_missing_leg_price(
        bid=99.0, ask=101.0, side="BUY", mid_slippage_bps=0.0,
    )
    assert price == 100.0


def test_estimate_missing_leg_price_returns_none_on_degenerate_quote():
    """Missing bid/ask returns None (degenerate quote)."""
    assert estimate_missing_leg_price(bid=None, ask=101.0, side="BUY") is None
    assert estimate_missing_leg_price(bid=99.0, ask=None, side="SELL") is None


def test_estimate_missing_leg_price_rejects_negative_slippage():
    """Negative slippage is rejected -- it would mean a
    *better-than-mid* fill, which the model does not allow.
    """
    with pytest.raises(ValueError, match="mid_slippage_bps"):
        estimate_missing_leg_price(
            bid=99.0, ask=101.0, side="BUY", mid_slippage_bps=-1.0,
        )


def test_estimate_missing_leg_price_default_is_2bps():
    """The module-level DEFAULT is 2.0 bps, matching Q1."""
    assert DEFAULT_MID_SLIPPAGE_BPS == 2.0


def test_estimate_missing_leg_price_side_case_insensitive():
    """Side accepts both upper and lower case."""
    price_upper = estimate_missing_leg_price(bid=99.0, ask=101.0, side="BUY")
    price_lower = estimate_missing_leg_price(bid=99.0, ask=101.0, side="buy")
    assert price_upper == price_lower


def test_estimate_missing_leg_price_rejects_unknown_side():
    with pytest.raises(ValueError, match="side must be"):
        estimate_missing_leg_price(bid=99.0, ask=101.0, side="HOLD")


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_modeled_entry_slippage_is_a_cost(side):
    pnl = compute_modeled_entry_slippage_pnl(
        qty=10, bid=99.0, ask=101.0, side=side)
    assert pnl is not None
    assert math.isclose(pnl, -0.2, rel_tol=1e-4)


def test_modeled_entry_slippage_refuses_degenerate_quote():
    assert compute_modeled_entry_slippage_pnl(
        qty=10, bid=None, ask=101.0, side="BUY") is None


# ─── compute_partial_fill_pnl ──────────────────────────────


def test_compute_partial_fill_pnl_long_leg_profit():
    """Long leg: BUY entry at 100, SELL exit at 105.
    qty=10 -> profit = 10 * 5 = 50.
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"long": {"side": "BUY", "fill_price": 105.0, "entry_price": 100.0}},
        missing_legs={},
    )
    assert math.isclose(pnl, 50.0, rel_tol=1e-6)


def test_compute_partial_fill_pnl_long_leg_loss():
    """Long leg with loss: BUY at 100, SELL at 95.
    qty=10 -> loss = 10 * -5 = -50.
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"long": {"side": "BUY", "fill_price": 95.0, "entry_price": 100.0}},
        missing_legs={},
    )
    assert math.isclose(pnl, -50.0, rel_tol=1e-6)


def test_compute_partial_fill_pnl_short_leg_profit():
    """Short leg: SELL entry at 100, BUY cover at 95.
    qty=10 -> profit = 10 * (100-95) = 50.
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"short": {"side": "SELL", "fill_price": 95.0, "entry_price": 100.0}},
        missing_legs={},
    )
    assert math.isclose(pnl, 50.0, rel_tol=1e-6)


def test_compute_partial_fill_pnl_both_filled_spread_profit():
    """Spread trade with both legs filled: long +50, short +30.
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={
            "long": {"side": "BUY", "fill_price": 105.0, "entry_price": 100.0},
            "short": {"side": "SELL", "fill_price": 97.0, "entry_price": 100.0},
        },
        missing_legs={},
    )
    # Long profit: 10 * (105-100) = 50. Short profit: 10 * (100-97) = 30.
    assert math.isclose(pnl, 80.0, rel_tol=1e-6)


def test_compute_partial_fill_pnl_partial_long_filled_short_modelled():
    """One leg filled at 105 profit, the other is missing
    and gets modelled at mid+2bps. The signal's entry for
    the missing leg is the mid (default fair entry baseline).
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"long": {"side": "BUY", "fill_price": 105.0, "entry_price": 100.0}},
        missing_legs={
            "short": {"side": "SELL", "bid": 99.0, "ask": 101.0},
        },
    )
    # Long profit: 10 * (105-100) = 50.
    # Short leg: missing, modelled fill = mid-2bps = 99.98.
    # entry_price defaults to mid = 100.0. SELL side:
    # profit = 10 * (entry - modelled_fill) = 10 * (100 - 99.98) = 0.2.
    assert math.isclose(pnl, 50.2, rel_tol=1e-4)


def test_compute_partial_fill_pnl_partial_short_filled_long_modelled():
    """Short leg filled at 97, long leg missing modelled
    at mid+2bps.
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"short": {"side": "SELL", "fill_price": 97.0, "entry_price": 100.0}},
        missing_legs={
            "long": {"side": "BUY", "bid": 99.0, "ask": 101.0},
        },
    )
    # Short profit: 10 * (100-97) = 30.
    # Long leg: missing, modelled fill = mid+2bps = 100.02.
    # entry_price defaults to mid = 100.0. BUY side:
    # profit = 10 * (modelled_fill - entry) = 10 * 0.02 = 0.2.
    assert math.isclose(pnl, 30.2, rel_tol=1e-4)


def test_compute_partial_fill_pnl_missing_leg_degenerate_quote_zero_pnl():
    """When a missing leg has a degenerate quote (bid/ask
    missing), the model returns zero P&L contribution
    rather than crashing the held-out replay.
    """
    pnl = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"long": {"side": "BUY", "fill_price": 105.0, "entry_price": 100.0}},
        missing_legs={"short": {"side": "SELL", "bid": None, "ask": None}},
    )
    # Long profit: 50. Short leg: degenerate quote -> 0 P&L.
    assert math.isclose(pnl, 50.0, rel_tol=1e-6)


def test_compute_partial_fill_pnl_rejects_zero_qty():
    """Zero or negative qty is rejected at the boundary."""
    with pytest.raises(ValueError, match="qty"):
        compute_partial_fill_pnl(qty=0, filled_legs={}, missing_legs={})
    with pytest.raises(ValueError, match="qty"):
        compute_partial_fill_pnl(qty=-5, filled_legs={}, missing_legs={})


def test_compute_partial_fill_pnl_rejects_missing_side():
    """A filled leg without a side is rejected."""
    with pytest.raises(ValueError, match="side"):
        compute_partial_fill_pnl(
            qty=10,
            filled_legs={"long": {"fill_price": 105.0, "entry_price": 100.0}},
            missing_legs={},
        )


def test_compute_partial_fill_pnl_rejects_missing_side_in_missing_leg():
    """A missing leg without a side is rejected."""
    with pytest.raises(ValueError, match="side"):
        compute_partial_fill_pnl(
            qty=10,
            filled_legs={},
            missing_legs={"short": {"bid": 99.0, "ask": 101.0}},
        )


def test_compute_partial_fill_pnl_rejects_missing_fill_price():
    """A filled leg without fill_price is rejected."""
    with pytest.raises(ValueError, match="fill_price"):
        compute_partial_fill_pnl(
            qty=10,
            filled_legs={"long": {"side": "BUY", "entry_price": 100.0}},
            missing_legs={},
        )


def test_compute_partial_fill_pnl_empty_legs_returns_zero():
    """No legs -> zero P&L (caller should not invoke this
    in practice but the function is total).
    """
    assert compute_partial_fill_pnl(qty=10, filled_legs={}, missing_legs={}) == 0.0


def test_compute_partial_fill_pnl_is_exchange_agnostic():
    """Per Q2: same model across NSE / NSE F&O / BSE.
    The function takes bid/ask/side/qty -- no exchange
    parameter. Two calls with identical inputs return
    identical P&L regardless of the calling code's
    exchange label.
    """
    pnl_a = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"long": {"side": "BUY", "fill_price": 105.0, "entry_price": 100.0}},
        missing_legs={"short": {"side": "SELL", "bid": 99.0, "ask": 101.0}},
    )
    pnl_b = compute_partial_fill_pnl(
        qty=10,
        filled_legs={"long": {"side": "BUY", "fill_price": 105.0, "entry_price": 100.0}},
        missing_legs={"short": {"side": "SELL", "bid": 99.0, "ask": 101.0}},
    )
    assert pnl_a == pnl_b
