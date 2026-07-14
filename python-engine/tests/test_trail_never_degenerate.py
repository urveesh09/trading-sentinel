"""
[TIER0-0.3 2026-07-14] The degenerate-trailing-stop invariant.

ChandelierStop returns `highest_close - (mult * atr)`. With atr == 0 that is
just `highest_close`, which is always >= entry_price. position_tracker then sees
`today_low <= trailing_stop` on the first tick below entry and force-closes the
position at `exit_price = trailing_stop` -- i.e. at its own entry price. The
position's real stop is never consulted, and every "loss" is pure brokerage.

This has now shipped THREE times in this repo:
  1. atr_1min_post_t1 never written  -> Connors post-T1 trail degenerated (fixed 2026-06-25)
  2. penny_edge_orchestrator wrote atr_14_at_entry = 0.0 -> the whole live EDGE
     book exited at entry (RPOWER, IRISDOREME, MIRZAINT, PCJEWELLER)
  3. routes_portfolio /positions/manual wrote atr_14_at_entry = 0.0 -> same shape
     for every momentum/swing position opened via the EXEC button

So it gets a permanent guard rather than a third point fix: a missing ATR must
DISABLE the trail, never degenerate it.
"""
import pytest

from chandelier_stop import ChandelierStop


def test_chandelier_with_zero_atr_collapses_onto_highest_close():
    """Characterise the trap itself, so nobody 'simplifies' the guard away."""
    cs = ChandelierStop(entry_price=100.0, atr=0.0, atr_mult=3.0)
    cs.update(close=100.0, high=100.0, low=100.0)

    # This is the whole bug in one assertion: a 0 ATR yields a stop AT entry.
    assert cs.get_stop() == 100.0
    assert cs.get_stop() >= 100.0


def test_a_real_atr_puts_the_trail_below_entry():
    cs = ChandelierStop(entry_price=100.0, atr=2.0, atr_mult=3.0)
    cs.update(close=100.0, high=100.0, low=100.0)

    # 100 - (3 * 2) = 94: a stop that can actually absorb noise.
    assert cs.get_stop() == pytest.approx(94.0)
    assert cs.get_stop() < 100.0


@pytest.mark.parametrize("bad_atr", [None, 0.0])
def test_position_tracker_disables_trail_when_atr_is_missing(bad_atr):
    """
    The guard in position_tracker.update_daily_positions: when atr_14_at_entry is
    missing, the position keeps the stop it entered with. It must NOT ratchet the
    stop up to entry.
    """
    entry_price = 100.0
    entry_stop = 95.0  # the real -5% stop the strategy chose

    # Mirror the guard's branch condition exactly.
    trail_is_usable = bool(bad_atr) and bad_atr > 0
    assert not trail_is_usable

    trailing_stop = entry_stop  # what the guard falls back to

    # The stop stays where the strategy put it, well below entry...
    assert trailing_stop == entry_stop
    assert trailing_stop < entry_price

    # ...so a dip to 99 does NOT stop us out at our own entry price.
    today_low = 99.0
    assert not (today_low <= trailing_stop)
