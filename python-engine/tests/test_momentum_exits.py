"""
[TIER0-0.1 2026-07-14] Tests for the momentum intraday exit ladder.

Context: before momentum_exits.py existed, a momentum position had no stop and no
target -- Zerodha GTT is CNC-only so MIS got no broker order, and no scheduled job
evaluated stop/target between the fill and the 15:15 auto-square. All 7 momentum
trades in the system's history exited on the clock; none hit a target or a stop.

Each branch of the ladder gets a witness (an input that reaches it) so no branch
can silently become unreachable -- the same falsifiability discipline as
test_fno_gate_falsifiability.py. A dead exit branch is how the penny book went
349,297 evaluations without a single accept.
"""
from datetime import datetime, timedelta, timezone

import pytest

from momentum_exits import (
    ACTION_EXIT, ACTION_HOLD, ACTION_TRAIL,
    cost_adjusted_breakeven, evaluate_momentum_exit,
)

NOW = datetime(2026, 7, 14, 6, 0, 0, tzinfo=timezone.utc)  # 11:30 IST


def _pos(**over):
    """A well-formed open momentum position. entry 100, stop 95 -> R = 5."""
    base = {
        "ticker": "TESTCO",
        "entry_price": 100.0,
        "stop_loss_initial": 95.0,
        "trailing_stop_current": 95.0,
        "target_1": 110.0,          # +2R
        "shares": 50,
        "atr_14_at_entry": 3.0,
        "entry_date": (NOW - timedelta(minutes=10)).isoformat(),
        "product_type": "MIS",
        "source": "MOMENTUM",
    }
    base.update(over)
    return base


# ---- witnesses: every branch is reachable ---------------------------------

def test_target_hit_exits():
    d = evaluate_momentum_exit(_pos(), ltp=110.0, now=NOW)
    assert d["action"] == ACTION_EXIT
    assert d["reason"] == "target_hit"


def test_below_breakeven_holds():
    # +0.5R: real progress, but not yet enough to move the stop.
    d = evaluate_momentum_exit(_pos(), ltp=102.5, now=NOW)
    assert d["action"] == ACTION_HOLD
    assert "below_breakeven" in d["reason"]


def test_ratchets_at_one_r():
    # +1R (105). Trail = 105 - 1.5*3 = 100.5, which beats cost-adj breakeven,
    # so the stop ratchets from 95 up to 100.5 -- above entry. The position can
    # no longer become a loser.
    d = evaluate_momentum_exit(_pos(), ltp=105.0, now=NOW)
    assert d["action"] == ACTION_TRAIL
    assert d["new_stop"] == pytest.approx(100.5)
    assert d["new_stop"] > 100.0


def test_trail_only_ever_ratchets_up():
    # Price at +1R but the stop is already higher than the trail would put it.
    d = evaluate_momentum_exit(
        _pos(trailing_stop_current=104.0), ltp=105.0, now=NOW,
    )
    assert d["action"] == ACTION_HOLD
    assert d["reason"] == "trail_not_improved"


def test_time_stop_cuts_a_trade_going_nowhere():
    # 60 min in, still at +0.1R. Failed thesis -> cut, don't ride it to 15:15.
    stale = _pos(entry_date=(NOW - timedelta(minutes=60)).isoformat())
    d = evaluate_momentum_exit(stale, ltp=100.5, now=NOW)
    assert d["action"] == ACTION_EXIT
    assert d["reason"].startswith("time_stop_")


def test_time_stop_never_cuts_a_runner():
    # Same 60 min, but the trade is at +1R. A winner is never cut on the clock.
    runner = _pos(entry_date=(NOW - timedelta(minutes=60)).isoformat())
    d = evaluate_momentum_exit(runner, ltp=105.0, now=NOW)
    assert d["action"] != ACTION_EXIT


# ---- the traps this ladder exists to avoid --------------------------------

def test_breakeven_is_cost_adjusted_not_entry_price():
    """
    Exiting at entry_price is a LOSS -- it has paid brokerage, STT, GST and
    exchange fees. The live EDGE book force-closed every position at its entry
    and booked each one as a loss of pure cost drag. Breakeven must sit ABOVE
    entry by the round-trip cost.
    """
    be = cost_adjusted_breakeven(entry_price=100.0, shares=50)
    assert be > 100.0


def test_stop_is_never_placed_at_or_above_the_last_price():
    """A trail at/above LTP triggers the SL-M the instant we modify it."""
    # Huge ATR would push the trail above LTP if unguarded... force the case by
    # making the existing stop already above the price.
    d = evaluate_momentum_exit(
        _pos(trailing_stop_current=106.0), ltp=105.0, now=NOW,
    )
    assert d["action"] == ACTION_HOLD
    assert d["new_stop"] is None


def test_zero_atr_does_not_collapse_the_trail_onto_the_price():
    """
    The degenerate-ATR trap that has now shipped three times in this repo. With
    atr=0 an unguarded trail is `ltp - 1.5*0` == ltp, i.e. a stop exactly at the
    last price. Here it must fall back to cost-adjusted breakeven instead.
    """
    d = evaluate_momentum_exit(_pos(atr_14_at_entry=0.0), ltp=105.0, now=NOW)
    assert d["action"] == ACTION_TRAIL
    assert d["new_stop"] < 105.0
    assert d["new_stop"] == pytest.approx(cost_adjusted_breakeven(100.0, 50), abs=0.01)


def test_none_atr_is_handled_like_zero():
    d = evaluate_momentum_exit(_pos(atr_14_at_entry=None), ltp=105.0, now=NOW)
    assert d["action"] == ACTION_TRAIL
    assert d["new_stop"] < 105.0


def test_invalid_r_is_refused_loudly_not_traded_on():
    """Stop at/above entry means R <= 0 -- sizing divided by this. Manage nothing."""
    d = evaluate_momentum_exit(
        _pos(stop_loss_initial=100.0), ltp=105.0, now=NOW,
    )
    assert d["action"] == ACTION_HOLD
    assert d["reason"] == "invalid_r"
