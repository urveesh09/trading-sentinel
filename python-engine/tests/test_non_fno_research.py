from penny_edge_engine import Position

from non_fno_research import (
    edge_next_open_lifecycle, penny_context_gate, penny_exit_thesis,
    range_candidate_gate, swing_candidate_gate,
)


def _bar(open_, high, low, close, volume=100, date="2026-10-01"):
    return {"date": date, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def test_penny_context_requires_same_minute_profile_and_a_fresh_structure():
    baseline = {"accept": True}
    bars = [_bar(10, 10.2, 9.9, 10.0), _bar(10, 10.2, 9.9, 10.1), _bar(10.1, 10.5, 10.0, 10.4)]
    assert penny_context_gate(baseline, bars, [100, 110, 120, 130])["reason"] == "missing_same_minute_volume_profile"
    result = penny_context_gate(baseline, bars, [100, 110, 120, 130, 140])
    assert result["accepted"] is True
    assert result["reason"] == "fresh_breakout"


def test_penny_exit_thesis_never_allows_stop_widening_or_repeated_rearm():
    assert penny_exit_thesis(entry=10, initial_stop=9, current_stop=8.9, current_price=10, structure_anchor=9.8,
                             prior_reentry_consumed=False)["reason"] == "stop_widening_forbidden"
    result = penny_exit_thesis(entry=10, initial_stop=9, current_stop=9.5, current_price=10, structure_anchor=9.8,
                               prior_reentry_consumed=True)
    assert result == {"action": "HOLD", "reason": "structure_intact_reentry_already_consumed"}


def test_penny_retest_anchors_before_confirmation_and_does_not_rechase():
    prior = _bar(10, 10.2, 9.9, 10)
    breakout = _bar(10.1, 10.5, 10, 10.4)
    retest = _bar(10.4, 10.45, 10.1, 10.3)
    result = penny_context_gate({"accept": True}, [prior, breakout, retest], [100] * 5)
    assert result["accepted"] and result["reason"] == "bounded_retest"
    assert result["anchor"] == 10.2
    chase = _bar(10.4, 10.7, 10.3, 10.6)
    result = penny_context_gate({"accept": True}, [prior, breakout, chase], [100] * 5)
    assert not result["accepted"]


def test_edge_lifecycle_uses_next_open_not_discovery_close_and_rejects_gap_geometry():
    position = Position("AAA", "2026-10-01", 100, 2, 105, 95, 1, "MO", .7, .7)
    result = edge_next_open_lifecycle(position, [_bar(102, 106, 101, 105, date="2026-10-02")])
    assert result["entry"] == 102
    assert result["signal_entry"] == 100
    gap = edge_next_open_lifecycle(position, [_bar(94, 96, 93, 95, date="2026-10-02")])
    assert gap["status"] == "NO_FILL"


def test_range_candidate_has_to_pay_costs_and_swing_requires_context():
    bars = [_bar(100, 101, 99, 100, date=f"2026-09-{day:02d}") for day in range(1, 16)]
    range_result = range_candidate_gate(bars, next_open=100, shares=1)
    assert range_result["accepted"] is False
    assert range_result["reason"] in {"baseline_wait_no_lower_touch", "baseline_wait_range_expanding", "baseline_wait_range_too_wide", "next_open_invalidates_geometry", "net_room_after_costs_insufficient"}
    assert swing_candidate_gate(baseline_fired=True, entry=100, stop=95, target=110,
                                relative_strength=None, correlation_to_open=.2)["reason"] == "missing_relative_strength_or_correlation"
    assert swing_candidate_gate(baseline_fired=True, entry=100, stop=95, target=110,
                                relative_strength=.1, correlation_to_open=.9)["reason"] == "correlated_exposure_cap"
