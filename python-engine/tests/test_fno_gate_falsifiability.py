"""
[FNO-FALSIFIABILITY 2026-07-10] Every gate MUST admit at least one
passing input (spec §9.1). This is the test class that would have killed
penny BUG-1 (bar_close > running day_high -- unsatisfiable by
construction) on the day it was written, instead of nine months later.

A gate without a witness does not merge.
"""
import dataclasses

import pytest

from fno_gates import (
    ALL_ENTRY_GATES, GateContext, evaluate_entry_gates, make_witness_context,
)
from fno_risk import lots_for_pool, validate_position
from fno_models import Leg, OptionType
from config import settings


@pytest.mark.parametrize("gate", ALL_ENTRY_GATES, ids=lambda g: g.name)
def test_gate_is_satisfiable(gate):
    """Every gate MUST admit at least one passing input."""
    assert gate.accepts(gate.witness_input()), f"{gate.name} is unsatisfiable"


def test_every_gate_has_a_witness():
    for gate in ALL_ENTRY_GATES:
        assert callable(gate.witness_input), f"{gate.name} ships no witness"


def test_full_ladder_passes_on_witness():
    ok, reason = evaluate_entry_gates(make_witness_context())
    assert ok, f"witness context rejected by: {reason}"
    assert reason == ""


def test_ladder_reports_first_failure_in_spec_order():
    ctx = dataclasses.replace(make_witness_context(), is_trading_day=False, oi=0)
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok
    # trading_day (§7.1) is evaluated before min_oi (§7.3)
    assert reason == "trading_day"


def test_pool_min_viable_uses_spec_reject_taxonomy():
    """§9.2 hinges on this exact string: the watchdog classifies
    pool_below_min_viable as self-regulation, not a dead gate."""
    ctx = dataclasses.replace(make_witness_context(), premium=500.0, ltp=500.0,
                              bid=499.0, ask=501.0)
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok
    assert reason == "pool_below_min_viable"


# ---------------------------------------------------------------------------
# Per-gate rejection spot-checks: each gate must also actually gate.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,value,expected", [
    ("is_trading_day", False, "trading_day"),
    ("now_min", 9 * 60, "entry_window"),               # 09:00 < 09:45
    ("now_min", 15 * 60, "entry_window"),              # 15:00 >= 14:45
    ("is_expiry_day", True, "expiry_day_block"),
    ("regime", "REGIME_3_CRISIS", "regime_not_crisis"),
    ("oi", 100, "min_oi"),
    ("volume", 10, "min_volume"),
    ("bid", 0.0, "two_sided_market"),
    ("quote_age_sec", 600.0, "quote_freshness"),
    ("iv", None, "iv_sanity"),
    ("iv", 2.5, "iv_sanity"),
    ("open_positions", 2, "concurrency"),
    ("trades_today", 3, "trades_per_day"),
    ("active_kill_switches", ["daily_loss_halt"], "kill_switches_clear"),
    ("chain_age_sec", 120.0, "chain_freshness"),
])
def test_each_gate_rejects_its_failure_mode(field, value, expected):
    ctx = dataclasses.replace(make_witness_context(), **{field: value})
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok
    assert reason == expected


def test_spread_gate_rejects_wide_market():
    ctx = dataclasses.replace(make_witness_context(), bid=95.0, ask=105.0, ltp=100.0)
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok and reason == "max_spread"


def test_intrinsic_floor_rejects_below_intrinsic_print():
    # deep ITM call (intrinsic 500) offered at 300 -> arbitrage or bad data
    ctx = dataclasses.replace(
        make_witness_context(),
        strike=24500.0, premium=300.0, bid=299.0, ask=301.0, ltp=300.0,
    )
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok and reason == "intrinsic_floor"


def test_quote_envelope_rejects_freak_ltp():
    ctx = dataclasses.replace(make_witness_context(), ltp=150.0)
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok and reason == "quote_envelope"


def test_open_premium_cap_rejects():
    # [ROADMAP-3.1 2026-07-12] cap is 0.15 x 250k pool = 37,500;
    # 36,000 committed + this trade's 7,515 breaches it.
    ctx = dataclasses.replace(make_witness_context(), open_premium=36000.0)
    ok, reason = evaluate_entry_gates(ctx)
    assert not ok and reason == "open_premium_cap"


# ---------------------------------------------------------------------------
# End-to-end satisfiability of the SIZING + CONSTITUTION path.
# This is the regression test for the spec bug found on 2026-07-10: the
# draft applied FNO_MAX_LOSS_PER_TRADE (Rs 2,500) to structural
# max_loss(), which for any affordable long option is the full premium
# (Rs ~7,500) -- an unsatisfiable order path. If someone "restores the
# spec" this test goes red immediately.
# ---------------------------------------------------------------------------

def test_order_path_is_satisfiable_end_to_end():
    ctx = make_witness_context()
    lots = lots_for_pool(
        ctx.pool, ctx.premium, ctx.lot_size,
        settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
        settings.FNO_MAX_LOTS,
    )
    assert lots >= 1, "sizing admits no lots for the witness contract"
    legs = [Leg(opt_type=OptionType.CE, strike=ctx.strike,
                quantity=lots, premium=ctx.premium)]
    ok, reason, ml = validate_position(legs, ctx.lot_size)
    assert ok, (
        f"constitution rejects the witness position ({reason}, ml={ml}) -- "
        "the order path is a dead gate"
    )
