from datetime import datetime, timedelta, timezone

import pytest

from adaptive_penny_policy import (
    CompletedBar, SetupState, advance_setup, begin_new_thesis, begin_watch,
    mark_closed, mark_exit_pending, mark_open, plan_entry, watch_from_prior_bars,
)


IST = timezone(timedelta(hours=5, minutes=30))


def _bar(identity: str, minute: int, *, open_=100.0, high=101.0, low=99.9,
         close=100.5, volume=100) -> CompletedBar:
    observed = datetime(2026, 10, 5, 9, minute, tzinfo=IST)
    # The policy does not inspect bar open; keep synthetic fixtures valid when
    # a test expresses only a low/high/close timing condition.
    open_ = min(high, max(open_, low))
    return CompletedBar(identity, observed, observed + timedelta(minutes=1),
                        open_, high, low, close, volume)


def _watch(*, expiry=10, baseline=False):
    return begin_watch(ticker="abc", anchor=100.0, anchor_available_at=_bar("anchor", 15).available_at,
                       expiry_minutes=expiry, noise_allowance=.05, baseline_accepted=baseline)


def test_baseline_rejected_continuation_has_frozen_anchor_and_intent():
    setup = _watch(baseline=False)
    armed = advance_setup(setup, _bar("break", 16, high=101, low=100.1, close=100.7),
                          decision_at=_bar("break", 16).available_at)
    assert armed.setup.state is SetupState.ARMED
    assert armed.setup.anchor == 100.0
    # The confirmation bar reaches a higher high, but the anchor remains the
    # previous structure rather than being rewritten from confirmation data.
    intent = advance_setup(armed.setup, _bar("confirm", 17, high=102, low=100.3, close=101.0),
                           decision_at=_bar("confirm", 17).available_at)
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
    # A delayed source bar is unavailable, rather than being used as future
    # structure or silently dropped to manufacture a lower anchor.
    delayed = (*prior[:-1], _bar("late-prior", 17, high=101, low=100, close=100.5))
    assert watch_from_prior_bars(ticker="ABC", prior_bars=delayed,
                                 decision_at=_bar("break", 16).available_at) is None


def test_bounded_retest_reclaim_is_distinct_from_continuation():
    armed = advance_setup(_watch(), _bar("break", 16, high=101, low=100.1, close=100.6),
                          decision_at=_bar("break", 16).available_at).setup
    outcome = advance_setup(armed, _bar("retest", 17, high=101, low=99.99, close=100.4),
                            decision_at=_bar("retest", 17).available_at)
    assert outcome.intent.entry_kind == "RETEST_RECLAIM"
    assert outcome.setup.reason == "bounded_retest_reclaim"


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


def test_stale_evidence_and_risk_sizing_fail_closed_and_stop_never_widens():
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
