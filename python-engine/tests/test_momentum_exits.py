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

from config import settings
from momentum_exits import (
    ACTION_EXIT, ACTION_HOLD, ACTION_SCALE_OUT, ACTION_TRAIL,
    cost_adjusted_breakeven, evaluate_momentum_exit, momentum_exit_status,
)

NOW = datetime(2026, 7, 14, 6, 0, 0, tzinfo=timezone.utc)  # 11:30 IST


@pytest.fixture(autouse=True)
def _scale_out_off_by_default(monkeypatch):
    """[SCALE-OUT 2026-08-04] The partial fires at +1R, which is exactly where
    the breakeven-ratchet tests probe. Default it OFF so those tests keep
    exercising the ratchet; TestScaleOut turns it on explicitly."""
    monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", False)


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
    # 95 min in, still at +0.1R -- below the +0.25R survival bar. Cut it.
    stale = _pos(entry_date=(NOW - timedelta(minutes=95)).isoformat())
    d = evaluate_momentum_exit(stale, ltp=100.5, now=NOW)
    assert d["action"] == ACTION_EXIT
    assert d["reason"].startswith("time_stop_")


def test_fast_time_stop_cuts_an_already_negative_trade():
    """[TIME-STOP-V2 2026-07-31] Tier one: a trade that has gone NEGATIVE has
    falsified its thesis and should not be held for the full slow window."""
    losing = _pos(entry_date=(NOW - timedelta(minutes=30)).isoformat())
    d = evaluate_momentum_exit(losing, ltp=98.5, now=NOW)   # -0.3R
    assert d["action"] == ACTION_EXIT
    assert d["reason"].startswith("time_stop_fast_")


def test_a_working_trade_is_given_real_runway():
    """[TIME-STOP-V2 2026-07-31] The change that matters most.

    The old single 45-min / +0.5R rule fired on 8 of 8 live trades between
    27-30 Jul, every one landing between -0.71R and +0.49R -- a 2R target on a
    ~1% stop needs a ~2% move, and 45 minutes does not supply it, so the rule
    guaranteed a ~0R exit minus costs. A trade that is positive at 60 minutes
    must now be allowed to keep working."""
    working = _pos(entry_date=(NOW - timedelta(minutes=60)).isoformat())
    d = evaluate_momentum_exit(working, ltp=100.5, now=NOW)   # +0.1R
    assert d["action"] != ACTION_EXIT


def test_time_stop_window_shortens_in_elevated_regime():
    """Chop gets less runway than a trend -- 90 min * 0.67 = ~60 min."""
    stale = _pos(
        entry_date=(NOW - timedelta(minutes=65)).isoformat(),
        regime_at_entry="REGIME_2_ELEVATED",
    )
    d = evaluate_momentum_exit(stale, ltp=100.5, now=NOW)   # +0.1R
    assert d["action"] == ACTION_EXIT
    assert d["reason"].startswith("time_stop_")
    # The same trade in a normal regime still has runway left.
    calm = _pos(
        entry_date=(NOW - timedelta(minutes=65)).isoformat(),
        regime_at_entry="REGIME_1_NORMAL",
    )
    assert evaluate_momentum_exit(calm, ltp=100.5, now=NOW)["action"] != ACTION_EXIT


def test_time_stop_never_cuts_a_runner():
    # 95 min, but the trade is at +1R. A winner is never cut on the clock.
    runner = _pos(entry_date=(NOW - timedelta(minutes=95)).isoformat())
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


# ---------------------------------------------------------------------------
# momentum_exit_status: the terminal status persisted on a full exit.
#
# Regression for the CLOSED_T1 phantom-open bug (2026-07-20): the monitor
# hard-coded status="CLOSED_T1" on every full square-off. get_open_positions()
# treats CLOSED_T1 as still-open (penny/swing runner), so fully-exited momentum
# trades (THELEELA, LATENTVIEW) with t1_fired=0 lingered as open forever and
# /performance reported phantom open positions.
# ---------------------------------------------------------------------------

# Mirror position_tracker.get_open_positions() -- statuses it counts as open.
_OPEN_STATUSES = ("OPEN", "CLOSED_T1")


def test_exit_status_target_hit_is_terminal():
    assert momentum_exit_status("target_hit") == "CLOSED_T2"


def test_exit_status_time_stop_is_terminal():
    assert momentum_exit_status("time_stop_240min_at_-0.30R") == "CLOSED_TIME"


def test_exit_status_unknown_reason_is_terminal_fallback():
    assert momentum_exit_status("something_new") == "CLOSED_MANUAL"


def test_every_action_exit_reason_maps_to_a_non_open_status():
    """The core guard: no ACTION_EXIT reason may map to a status the
    open-position query still counts. Otherwise the phantom-open bug returns."""
    # target_hit branch
    target = evaluate_momentum_exit(
        _pos(), ltp=200.0, now=NOW,  # far above target -> target_hit
    )
    # time_stop branch: old position, small positive R, past the time limit
    time_stop = evaluate_momentum_exit(
        _pos(entry_date=(NOW - timedelta(hours=6)).isoformat()),
        ltp=100.5, now=NOW,
    )
    exit_reasons = [
        d["reason"] for d in (target, time_stop) if d["action"] == ACTION_EXIT
    ]
    assert exit_reasons, "expected at least one ACTION_EXIT witness"
    for reason in exit_reasons:
        status = momentum_exit_status(reason)
        assert status not in _OPEN_STATUSES, (
            f"reason {reason!r} -> {status!r} would be counted as open"
        )


# ---- [SCALE-OUT 2026-08-04] partial profit-taking -------------------------
#
# Momentum was all-or-nothing and almost never reached its target: 27 Jul -
# 03 Aug produced thirteen closes, one at target and twelve on the clock or a
# ratcheted stop, between -0.71R and +0.49R. SUMICHEM on 2026-08-03 is the
# canonical case -- stopped at breakeven 11:27, printed its target at 12:00.

class TestScaleOut:
    def test_fires_at_the_configured_r_and_sells_the_configured_fraction(self, monkeypatch):
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_FRAC", 0.5)

        # entry 100, stop 95 -> R = 5. ltp 105 is exactly +1R.
        d = evaluate_momentum_exit(_pos(t1_fired=0), ltp=105.0, now=NOW)

        assert d["action"] == ACTION_SCALE_OUT
        assert d["scale_shares"] == 25          # half of 50
        assert d["reason"].startswith("scale_out_at_1.00R")
        # The runner is de-risked in the same decision: its stop moves to
        # cost-adjusted breakeven, above entry, so the runner cannot lose.
        assert d["new_stop"] > 100.0
        assert d["new_stop"] < 105.0

    def test_does_not_fire_below_the_threshold(self, monkeypatch):
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        d = evaluate_momentum_exit(_pos(t1_fired=0), ltp=104.0, now=NOW)  # +0.8R
        assert d["action"] != ACTION_SCALE_OUT

    def test_fires_only_once_per_position(self, monkeypatch):
        """t1_fired is the latch. Without it the partial would re-fire every
        60-second tick and grind the position to nothing."""
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        d = evaluate_momentum_exit(_pos(t1_fired=1), ltp=106.0, now=NOW)
        assert d["action"] != ACTION_SCALE_OUT

    def test_target_still_wins_over_the_partial(self, monkeypatch):
        """A trade that reached its target books the whole thing."""
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        d = evaluate_momentum_exit(_pos(t1_fired=0), ltp=115.0, now=NOW)
        assert d["action"] == ACTION_EXIT
        assert d["reason"] == "target_hit"

    def test_single_share_position_cannot_scale_and_falls_through(self, monkeypatch):
        """The common case on a 2,428 pool: one share of a 1,600-rupee stock.
        Half of one share is nothing, so the ladder must fall through to the
        ordinary ratchet rather than emit a zero-share sell."""
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        d = evaluate_momentum_exit(_pos(shares=1, t1_fired=0), ltp=105.0, now=NOW)
        assert d["action"] != ACTION_SCALE_OUT
        assert "scale_shares" not in d

    def test_never_sells_the_entire_position_as_a_partial(self, monkeypatch):
        """FRAC=1.0 would make the 'partial' a full exit that leaves the row
        open with zero shares. Guarded by scale_shares < shares."""
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_FRAC", 1.0)
        d = evaluate_momentum_exit(_pos(t1_fired=0), ltp=105.0, now=NOW)
        assert d["action"] != ACTION_SCALE_OUT

    def test_disabled_flag_restores_the_old_all_or_nothing_ladder(self, monkeypatch):
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", False)
        d = evaluate_momentum_exit(_pos(t1_fired=0), ltp=105.0, now=NOW)
        assert d["action"] != ACTION_SCALE_OUT

    def test_runner_stop_never_ratchets_backwards(self, monkeypatch):
        """If the trail has already pushed the stop above cost-adjusted
        breakeven, the partial must not drag it back down."""
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
        high_stop = 103.0
        d = evaluate_momentum_exit(
            _pos(t1_fired=0, trailing_stop_current=high_stop), ltp=105.0, now=NOW,
        )
        assert d["action"] == ACTION_SCALE_OUT
        assert d["new_stop"] >= high_stop


def test_momentum_entry_deadline_is_consistent_with_square_off():
    """[MC0-DEADLINE 2026-08-04] MOMENTUM_ENTRY_END_MIN was 840 with a comment
    claiming "= 14:45". 840 minutes past 09:15 is 23:15, so the late-entry gate
    had never fired once: on 2026-08-03 TRITURBINE was accepted at 14:48 for a
    book that squares off at 15:15, giving the trade ~20 minutes of life
    against a 25-minute FAST time stop. It could only ever exit on the clock.

    The binding constraint is the fast tier, not the slow one. A trade entered
    at 14:30 will not see the 90-minute slow cut, but the 15:15 square-off
    reaches the same outcome, so that is fine. What is NOT fine is an entry
    with less life than the fast cut needs to even evaluate the thesis.

    Require the last entry to leave at least 1.5x the fast window after the
    alert/EXEC latency is paid."""
    SQUARE_OFF_MIN = (15 - 9) * 60 + 15 - 15       # 15:15 IST -> 360
    LATENCY_BUDGET_MIN = 15                         # 3-min poll + MiniMax + human
    MIN_USEFUL_LIFE = settings.MOMENTUM_TIME_STOP_FAST_MIN * 1.5

    life_after_entry = (
        SQUARE_OFF_MIN - settings.MOMENTUM_ENTRY_END_MIN - LATENCY_BUDGET_MIN
    )
    assert life_after_entry >= MIN_USEFUL_LIFE, (
        f"entry deadline {settings.MOMENTUM_ENTRY_END_MIN} min leaves only "
        f"{life_after_entry} min of managed life; need {MIN_USEFUL_LIFE}"
    )
    # And it must still permit a usable trading window after the 10:00 open gate.
    assert settings.MOMENTUM_ENTRY_END_MIN > settings.MOMENTUM_ENTRY_START_MIN + 120
    # Guard the specific regression: the gate must actually be reachable within
    # a trading day. 840 (23:15) meant it never was.
    assert settings.MOMENTUM_ENTRY_END_MIN < SQUARE_OFF_MIN


# ---- [THESIS-EXIT 2026-08-04] cut on a broken setup, not on a timer --------
#
# The fast tier asked "is r_now < 0 after 25 minutes?", which cannot separate a
# dead trade from a slow one -- and that distinction is most of the P&L:
#
#   2026-08-04 INDIACEM  -0.45R at 25 min  ->  +1.10R at 65 min
#   2026-08-03 SUMICHEM  scratched 11:27   ->  printed its target at 12:00
#
# The momentum thesis is "crossed VWAP on a volume surge and is HOLDING above
# it" (the screener's own gates are no_recent_vwap_crossover and
# crossed_but_failed_holding_vwap). So the exit now tests the same proposition
# the entry did. VWAP-at-entry is not a fitted number -- it is the level the
# signal was already measured against.

class TestThesisAwareFastStop:
    def _late(self):
        """Past the fast checkpoint."""
        return NOW + timedelta(minutes=settings.MOMENTUM_TIME_STOP_FAST_MIN + 1)

    def test_holds_a_negative_trade_that_is_still_above_its_vwap(self, monkeypatch):
        """INDIACEM's shape: down at the checkpoint, setup intact."""
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", True)
        # entry 100, stop 95 (R=5), vwap 97. ltp 98 -> -0.4R but above VWAP.
        d = evaluate_momentum_exit(
            _pos(vwap_at_entry=97.0), ltp=98.0, now=self._late(),
        )
        assert d["action"] != ACTION_EXIT, (
            "a trade holding above its breakout VWAP has not failed yet"
        )

    def test_cuts_a_negative_trade_that_has_LOST_its_vwap(self, monkeypatch):
        """The thesis is dead: cut it, exactly as before."""
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", True)
        d = evaluate_momentum_exit(
            _pos(vwap_at_entry=97.0), ltp=96.5, now=self._late(),
        )
        assert d["action"] == ACTION_EXIT
        assert d["reason"].startswith("time_stop_fast_")

    def test_falls_back_to_the_r_test_when_no_vwap_was_recorded(self, monkeypatch):
        """Positions opened before the column existed must keep working."""
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", True)
        d = evaluate_momentum_exit(_pos(vwap_at_entry=None), ltp=98.0, now=self._late())
        assert d["action"] == ACTION_EXIT
        assert d["reason"].startswith("time_stop_fast_")

    def test_a_zero_vwap_is_not_treated_as_thesis_intact(self, monkeypatch):
        """0.0 would read as 'price is above VWAP' and defeat every fast stop.
        Same class of bug as the 0.0-ATR trail collapse."""
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", True)
        d = evaluate_momentum_exit(_pos(vwap_at_entry=0.0), ltp=98.0, now=self._late())
        assert d["action"] == ACTION_EXIT

    def test_flag_off_restores_the_pure_clock_and_r_behaviour(self, monkeypatch):
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", False)
        d = evaluate_momentum_exit(_pos(vwap_at_entry=97.0), ltp=98.0, now=self._late())
        assert d["action"] == ACTION_EXIT

    def test_the_slow_tier_still_bounds_a_thesis_intact_loser(self, monkeypatch):
        """Deferring the fast cut must not make a position immortal. A trade
        that sits above VWAP forever is still cut by the slow tier."""
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", True)
        very_late = NOW + timedelta(
            minutes=settings.MOMENTUM_TIME_STOP_MIN
            * settings.MOMENTUM_TIME_STOP_R1_MULT + 5
        )
        d = evaluate_momentum_exit(
            _pos(vwap_at_entry=97.0), ltp=98.0, now=very_late,
        )
        assert d["action"] == ACTION_EXIT
        assert d["reason"].startswith("time_stop_")

    def test_indiacem_2026_08_04_replayed(self, monkeypatch):
        """The real trade, with the real numbers, at both checkpoints."""
        monkeypatch.setattr(settings, "MOMENTUM_FAST_STOP_USES_THESIS", True)
        monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
        # Fill 393.80; F1-anchored stop 391.80 (R=2.00); VWAP at signal 391.47.
        pos = _pos(
            entry_price=393.80, stop_loss_initial=391.80,
            trailing_stop_current=391.80, target_1=397.80,
            vwap_at_entry=391.47, shares=6, atr_14_at_entry=12.01,
        )
        # 13:05, 25 min in: price 392.90 = -0.45R, but still above 391.47.
        at_25 = evaluate_momentum_exit(pos, ltp=392.90, now=self._late())
        assert at_25["action"] != ACTION_EXIT, "this is the cut that cost Rs 13.68"

        # 13:45, price 395.80 = +1.00R -> the partial can now fire.
        at_65 = evaluate_momentum_exit(
            pos, ltp=395.80, now=NOW + timedelta(minutes=65),
        )
        assert at_65["action"] == ACTION_SCALE_OUT
        assert at_65["scale_shares"] == 3
