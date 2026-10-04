from datetime import datetime, timedelta, timezone

import pytest

from adaptive_penny_policy import (
    DEFAULT_PARAMS, CompletedBar, SetupState, TickerMemory, advance_setup, begin_new_thesis,
    begin_watch, compute_context, detect_breakout, manage_position, mark_closed, mark_exit_pending,
    mark_open, open_thesis_position, plan_entry, resting_partial, score_breakout, structural_stop,
    watch_from_prior_bars,
)


IST = timezone(timedelta(hours=5, minutes=30))


def _bar(identity: str, minute: int, *, open_=100.0, high=101.0, low=99.9,
         close=100.5, volume=100, hour=9) -> CompletedBar:
    observed = datetime(2026, 10, 5, hour, 0, tzinfo=IST) + timedelta(minutes=minute)
    # The policy does not inspect bar open; keep synthetic fixtures valid when
    # a test expresses only a low/high/close timing condition.
    open_ = min(high, max(open_, low))
    return CompletedBar(identity, observed, observed + timedelta(minutes=1),
                        open_, high, low, close, volume)


def _base(n=30, *, start_minute=0, hour=11, volume=1000):
    """A quiet base: highs at 100.0, lows 99.6, ~0.4 range."""
    return [_bar(f"b{i}", start_minute + i, hour=hour, open_=99.8, high=100.0 if i % 5 == 0 else 99.9,
                 low=99.6, close=99.8, volume=volume) for i in range(n)]


def _watch(*, expiry=10, baseline=False):
    return begin_watch(ticker="abc", anchor=100.0, anchor_available_at=_bar("anchor", 15).available_at,
                       expiry_minutes=expiry, noise_allowance=.05, baseline_accepted=baseline)


# ---- T0 setup-state contracts (retained) --------------------------------

def test_baseline_rejected_continuation_has_frozen_anchor_and_intent():
    setup = _watch(baseline=False)
    armed = advance_setup(setup, _bar("break", 16, high=101, low=100.1, close=100.7),
                          decision_at=_bar("break", 16).available_at, retest_tolerance=.002)
    assert armed.setup.state is SetupState.ARMED
    assert armed.setup.anchor == 100.0
    intent = advance_setup(armed.setup, _bar("confirm", 17, high=102, low=100.3, close=101.0),
                           decision_at=_bar("confirm", 17).available_at, retest_tolerance=.002)
    assert intent.action == "ENTRY_INTENT"
    assert intent.intent.entry_kind == "CONTINUATION"
    assert intent.intent.baseline_status == "baseline_rejected"
    assert intent.setup.anchor == 100.0


def test_watch_derives_anchor_only_from_visible_prior_bars():
    prior = (
        _bar("p1", 13, high=99.5, low=98.9, close=99.2),
        _bar("p2", 14, high=100.0, low=99.1, close=99.8),
        _bar("p3", 15, high=99.8, low=99.2, close=99.5),
    )
    watch = watch_from_prior_bars(ticker="ABC", prior_bars=prior,
                                  decision_at=_bar("break", 16).available_at,
                                  baseline_accepted=False)
    assert watch and watch.anchor == 100.0 and watch.baseline_status == "baseline_rejected"
    delayed = (*prior[:-1], _bar("late-prior", 17, high=101, low=100, close=100.5))
    assert watch_from_prior_bars(ticker="ABC", prior_bars=delayed,
                                 decision_at=_bar("break", 16).available_at) is None


def test_watch_survives_ordinary_consolidation_and_expiry_runs_from_creation():
    prior = tuple(_bar(f"p{i}", i, high=100.0 if i == 0 else 99.7, low=99.0, close=99.5) for i in range(5))
    # Created 20 minutes after the anchor bar: it must not be born expired.
    decision = _bar("now", 20).available_at
    watch = watch_from_prior_bars(ticker="ABC", prior_bars=prior, decision_at=decision)
    assert watch.expires_at == decision + timedelta(minutes=10)
    assert watch.invalidation == 99.0 < watch.initial_stop
    # A dip under anchor-minus-noise but above the base low is consolidation.
    dip = _bar("dip", 21, high=99.8, low=99.3, close=99.6)
    outcome = advance_setup(watch, dip, decision_at=dip.available_at)
    assert outcome.action == "WATCH"
    broken = _bar("broken", 22, high=99.5, low=98.9, close=99.0)
    assert advance_setup(outcome.setup, broken, decision_at=broken.available_at).action == "INVALIDATED"


def test_bounded_retest_reclaim_is_distinct_from_continuation_and_stop_only_widens():
    armed = advance_setup(_watch(), _bar("break", 16, high=101, low=100.1, close=100.6),
                          decision_at=_bar("break", 16).available_at).setup
    assert armed.invalidation == armed.initial_stop
    outcome = advance_setup(armed, _bar("retest", 17, high=101, low=99.97, close=100.4),
                            decision_at=_bar("retest", 17).available_at, retest_tolerance=.002)
    assert outcome.intent.entry_kind == "RETEST_RECLAIM"
    assert outcome.intent.stop <= armed.initial_stop


def test_duplicate_event_and_json_restart_are_deterministic():
    setup = _watch()
    event = _bar("break", 16, high=101, low=100.1, close=100.6)
    first = advance_setup(setup, event, decision_at=event.available_at)
    duplicate = advance_setup(first.setup, event, decision_at=event.available_at)
    assert duplicate.action == "IDEMPOTENT"
    restored = type(first.setup).from_dict(first.setup.to_dict())
    assert restored == first.setup


def test_invalidation_and_expiry_do_not_auto_reenter():
    setup = _watch()
    broken = advance_setup(setup, _bar("broken", 16, high=100.2, low=99.95, close=100.1),
                           decision_at=_bar("broken", 16).available_at)
    assert broken.setup.state is SetupState.INVALIDATED
    later = advance_setup(broken.setup, _bar("later", 17, high=103, low=101, close=102),
                          decision_at=_bar("later", 17).available_at)
    assert later.action == "TERMINAL"
    fresh = begin_new_thesis(broken.setup, ticker="ABC", anchor=101, anchor_available_at=_bar("new", 18).available_at)
    assert fresh.thesis_id != broken.setup.thesis_id
    expired_watch = _watch(expiry=1)
    late = _bar("late", 17, high=101, low=100.1, close=100.6)
    expired = advance_setup(expired_watch, late, decision_at=late.available_at)
    assert expired.setup.state is SetupState.EXPIRED


def test_two_closes_back_inside_base_invalidate_armed_thesis():
    armed = advance_setup(_watch(), _bar("break", 16, high=101, low=100.1, close=100.6),
                          decision_at=_bar("break", 16).available_at).setup
    one = advance_setup(armed, _bar("in1", 17, high=100.3, low=99.96, close=99.98),
                        decision_at=_bar("in1", 17).available_at)
    assert one.action == "ARMED" and one.setup.closes_inside_base == 1
    two = advance_setup(one.setup, _bar("in2", 18, high=100.0, low=99.96, close=99.97),
                        decision_at=_bar("in2", 18).available_at)
    assert two.action == "INVALIDATED" and two.reason == "breakout_failed_back_inside_base"


def test_stale_evidence_and_risk_sizing_fail_closed():
    setup = _watch()
    event = _bar("break", 16, high=101, low=100.1, close=100.6)
    with pytest.raises(ValueError, match="precedes"):
        advance_setup(setup, event, decision_at=event.observed_at)
    armed = advance_setup(setup, event, decision_at=event.available_at).setup
    intent = advance_setup(armed, _bar("confirm", 17, high=102, low=100.2, close=101),
                           decision_at=_bar("confirm", 17).available_at).intent
    assert plan_entry(intent, executable_price=99.9, own_cash=2000, risk_budget=50, per_position_cash_cap=500) is None
    plan = plan_entry(intent, executable_price=101, own_cash=2000, risk_budget=50, per_position_cash_cap=500)
    assert plan and plan.stop == 99.95 and plan.shares <= 4
    # Costs that would dominate the planned risk decline the trade.
    assert plan_entry(intent, executable_price=101, own_cash=2000, risk_budget=50, per_position_cash_cap=500,
                      round_trip_cost=lambda e, x, q: 100.0) is None
    # A gap far above the frozen stop makes the risk too wide to take.
    assert plan_entry(intent, executable_price=110, own_cash=2000, risk_budget=500, per_position_cash_cap=500) is None


def test_execution_state_requires_explicit_confirmations():
    setup = _watch()
    first = _bar("break", 16, high=101, low=100.1, close=100.6)
    armed = advance_setup(setup, first, decision_at=first.available_at).setup
    second = _bar("confirm", 17, high=102, low=100.2, close=101)
    intent = advance_setup(armed, second, decision_at=second.available_at).setup
    open_ = mark_open(intent, observation=_bar("fill", 18, high=102, low=100.5, close=101.2))
    pending = mark_exit_pending(open_, observation=_bar("exit-submitted", 19, high=102, low=100.5, close=101.2))
    closed = mark_closed(pending, observation=_bar("exit-fill", 20, high=102, low=100.5, close=101.2))
    assert [open_.state, pending.state, closed.state] == [SetupState.OPEN, SetupState.EXIT_PENDING, SetupState.CLOSED]


# ---- PEN_TRADER_V1 context, timing and exits -----------------------------

def test_context_freezes_anchor_and_atr_before_confirmation():
    bars = _base() + [_bar("brk", 30, hour=11, open_=99.9, high=101.0, low=99.9, close=100.9, volume=5000)]
    ctx = compute_context(bars, median_vol_20d=50_000)
    assert ctx["available"] and ctx["anchor"] == 100.0  # not the confirmation high 101
    assert ctx["atr"] == pytest.approx(0.4, abs=0.11)
    assert compute_context(bars, median_vol_20d=None)["available"] is False
    assert compute_context(bars[:10], median_vol_20d=50_000)["missing"] == ["base_bars"]


def test_strong_breakout_rejected_by_baseline_rsi_still_gets_fast_entry():
    # Rising closes push RSI(14) high (the baseline rejects RSI >= 70), but a
    # tight base, real participation and a close near the bar high is exactly
    # the setup a trader takes immediately.
    base = [_bar(f"b{i}", i, hour=11, open_=99.0 + i * .03, high=min(100.0, 99.2 + i * .03),
                 low=98.9 + i * .03, close=99.1 + i * .03 - (.1 if i % 3 == 0 else 0), volume=1000)
            for i in range(30)]
    breakout = _bar("brk", 30, hour=11, open_=99.95, high=100.22, low=99.95, close=100.2, volume=4000)
    bars = base + [breakout]
    ctx = compute_context(bars, median_vol_20d=40_000)
    assert 70 <= ctx["rsi_14"] < DEFAULT_PARAMS.exhaustion_rsi
    outcome = detect_breakout(ticker="ABC", bars=bars, median_vol_20d=40_000,
                              decision_at=breakout.available_at)
    assert outcome.action == "ENTRY_INTENT", outcome.evidence["verdict"]
    assert outcome.intent.entry_kind == "FAST_BREAKOUT"
    assert outcome.intent.stop == structural_stop(ctx["anchor"], ctx["atr"])
    assert outcome.setup.baseline_status == "baseline_rejected"


def test_extended_breakout_waits_for_retest_instead_of_chasing():
    bars = _base() + [_bar("brk", 30, hour=11, open_=99.9, high=101.0, low=99.9, close=100.95, volume=5000)]
    outcome = detect_breakout(ticker="ABC", bars=bars, median_vol_20d=50_000, decision_at=bars[-1].available_at)
    assert outcome.action == "ARMED"
    assert outcome.evidence["verdict"]["fast_entry"] is False
    retest = _bar("rt", 31, hour=11, high=100.6, low=100.1, close=100.4, volume=2000)
    entered = advance_setup(outcome.setup, retest, decision_at=retest.available_at)
    assert entered.intent and entered.intent.entry_kind == "RETEST_RECLAIM"


def test_no_setup_reports_every_failed_condition():
    bars = _base(volume=10) + [_bar("brk", 30, hour=11, high=100.3, low=99.9, close=100.2, volume=20)]
    verdict = score_breakout(compute_context(bars, median_vol_20d=1_000_000))
    assert not verdict["eligible"] and "participation_below_pace" in verdict["failures"]
    early = _base(hour=8, start_minute=0) + [_bar("e", 20, hour=9, high=100.3, low=99.9, close=100.2)]
    assert "entry_window" in score_breakout(compute_context(early, median_vol_20d=1))["failures"]


def test_ticker_memory_blocks_churn_after_failure():
    now = _bar("x", 0, hour=11).available_at
    memory = TickerMemory().after_entry(100.0).after_failure(100.0, now)
    assert memory.allows(anchor=101.0, now=now + timedelta(minutes=5)) == "ticker_cooldown"
    later = now + timedelta(minutes=DEFAULT_PARAMS.cooldown_minutes)
    assert memory.allows(anchor=100.0, now=later) == "needs_higher_anchor_after_failure"
    assert memory.allows(anchor=100.5, now=later) is None
    assert memory.after_entry(100.5).allows(anchor=102, now=later) == "ticker_entry_limit"


def _position(shares=10, stop=99.5):
    intent_plan = type("P", (), {})()
    from adaptive_penny_policy import EntryPlan
    plan = EntryPlan("PEN-x", 100.5, stop, shares, 100.5 - stop, 1.0, 1005.0, round_trip_cost=0.5)
    return open_thesis_position(plan, ticker="ABC", anchor=100.0, atr=0.2,
                                entry_at=_bar("fill", 0, hour=11).observed_at)


def test_thesis_exit_cuts_failed_breakout_and_stall_but_never_lowers_stop():
    pos = _position()
    first = manage_position(pos, _bar("a", 1, hour=11, high=100.4, low=99.8, close=99.9),
                            decision_at=_bar("a", 1, hour=11).available_at)
    assert first.exit_reason is None and first.position.closes_below_anchor == 1
    second = manage_position(first.position, _bar("b", 2, hour=11, high=100.1, low=99.7, close=99.8),
                             decision_at=_bar("b", 2, hour=11).available_at)
    assert second.exit_reason == "THESIS_FAILED_BREAKOUT"
    stall_bar = _bar("s", 50, hour=11, high=100.6, low=100.2, close=100.3)
    stalled = manage_position(pos, stall_bar, decision_at=stall_bar.available_at)
    assert stalled.exit_reason == "THESIS_STALLED"


def test_thesis_exit_locks_breakeven_trails_and_banks_integer_half():
    pos = _position()
    up = _bar("u", 3, hour=11, high=101.6, low=100.6, close=101.4)   # MFE 1.1R
    be = manage_position(pos, up, decision_at=up.available_at)
    assert be.new_stop is not None and be.new_stop >= pos.entry_price
    run = _bar("r", 4, hour=11, high=102.6, low=101.5, close=102.5)  # MFE 2.1R
    partial = resting_partial(be.position, run)
    assert partial.partial_quantity == 5 and partial.partial_price == pytest.approx(102.5)
    trailed = manage_position(partial.position, run, decision_at=run.available_at)
    assert trailed.new_stop > be.new_stop
    lower = manage_position(trailed.position, _bar("d", 5, hour=11, high=102.0, low=101.6, close=101.8),
                            decision_at=_bar("d", 5, hour=11).available_at)
    assert lower.position.stop == trailed.position.stop
    single = _position(shares=1)
    assert resting_partial(single, run).partial_quantity == 0
