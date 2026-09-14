from datetime import datetime, timedelta, timezone

import pytest
from zoneinfo import ZoneInfo

from partner_decision_clock import (
    CLOCK_POLICY, crossed_entry_boundary, source_identity, start_clock, validate_clock_payload,
)


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize("underlying", ["NIFTY", "SENSEX"])
@pytest.mark.parametrize("tz", [IST, timezone.utc])
def test_clock_identity_is_stable_and_timezone_aware(underlying, tz):
    instant = datetime(2026, 9, 14, 9, 45, tzinfo=IST).astimezone(tz)
    first = start_clock(underlying=underlying, account_id="manual-profile:p1", tick_started_at=instant)
    repeated = start_clock(underlying=underlying, account_id="manual-profile:p1", tick_started_at=instant)
    assert first == repeated
    assert first.policy == CLOCK_POLICY
    assert first.tick_started_at.tzinfo is not None
    assert first.run_id == repeated.run_id
    assert source_identity("kite", underlying, 123).endswith(f":{underlying}:123")


def test_new_cutoff_is_a_new_run_and_clocks_must_be_monotonic():
    tick = datetime(2026, 9, 14, 10, 0, tzinfo=IST)
    first = start_clock(underlying="NIFTY", account_id="manual-profile:p1", tick_started_at=tick)
    second = start_clock(underlying="NIFTY", account_id="manual-profile:p1", tick_started_at=tick + timedelta(minutes=5))
    assert first.run_id != second.run_id
    with pytest.raises(ValueError, match="monotonic"):
        first.with_stage(public_requested_at=tick + timedelta(seconds=2), public_received_at=tick + timedelta(seconds=1))


def test_fetch_crossing_entry_or_session_boundary_is_suppressed():
    tick = datetime(2026, 9, 14, 14, 44, 59, tzinfo=IST)
    decision = start_clock(underlying="NIFTY", account_id="manual-profile:p1", tick_started_at=tick).with_stage(
        public_requested_at=tick, public_received_at=tick + timedelta(milliseconds=200),
        chain_requested_at=tick + timedelta(milliseconds=300),
        chain_received_at=tick + timedelta(seconds=2),
        candidate_constructed_at=tick + timedelta(seconds=2),
    )
    assert crossed_entry_boundary(decision, entry_end_minute=14 * 60 + 45) == "entry_deadline_crossed_during_acquisition"
    overnight = decision.with_stage(
        chain_received_at=tick + timedelta(days=1), candidate_constructed_at=tick + timedelta(days=1),
    )
    assert crossed_entry_boundary(overnight, entry_end_minute=14 * 60 + 45) == "session_boundary_crossed_during_acquisition"


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        start_clock(underlying="NIFTY", account_id="manual-profile:p1", tick_started_at=datetime(2026, 9, 14, 9, 45))


def test_retained_clock_run_identity_cannot_be_relabelled():
    clock = start_clock(
        underlying="NIFTY", account_id="manual-profile:p1",
        tick_started_at=datetime(2026, 9, 14, 9, 45, tzinfo=IST),
    )
    assert validate_clock_payload(clock.payload()) == clock
    altered = clock.payload()
    altered["account_id"] = "manual-profile:other"
    with pytest.raises(ValueError, match="run identity"):
        validate_clock_payload(altered)
