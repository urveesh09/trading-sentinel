from dataclasses import replace
from datetime import datetime, timedelta

import pytest
import pytz

from intraday_spread_chronological import ChronologicalPolicy, SpreadObservation, replay_chronological_debit_spread, replay_cost_scenarios
from intraday_spread_replay import LegQuote, ReplayInputError


IST = pytz.timezone("Asia/Kolkata")
MASTER = "b" * 64


def pair(at, *, long_bid=100, long_ask=102, short_bid=48, short_ask=50, depth=75):
    return (
        LegQuote("NIFTY26SEP25000CE", "BUY", "NFO", 75, long_bid, long_ask, depth, depth, at - timedelta(seconds=1), at,
                 token=101, option_type="CE", strike=25000, expiry="2026-09-24", quantity=75, master_sha256=MASTER),
        LegQuote("NIFTY26SEP25200CE", "SELL", "NFO", 75, short_bid, short_ask, depth, depth, at - timedelta(seconds=1), at,
                 token=102, option_type="CE", strike=25200, expiry="2026-09-24", quantity=75, master_sha256=MASTER),
    )


def observation(at, score, quotes=None):
    return SpreadObservation(at - timedelta(seconds=1), at, score, quotes or pair(at))


def policy():
    return ChronologicalPolicy("fixed-test-v1", min_signal_score=0.8, take_profit_rs=100, stop_loss_rs=200)


def test_public_thesis_does_not_exit_on_spread_profit_alone():
    first = IST.localize(datetime(2026, 9, 10, 10))
    profitable = first + timedelta(minutes=1)
    invalidated = first + timedelta(minutes=2)
    rows = [observation(first, 1),
            replace(observation(profitable, 0, pair(profitable, long_bid=110)),
                    public_price=25000, public_received_at=profitable, public_observed_at=profitable),
            replace(observation(invalidated, 0), public_price=24900, public_received_at=invalidated, public_observed_at=invalidated)]
    result = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", observations=rows,
        policy=replace(policy(), exit_basis="PUBLIC_THESIS", direction="LONG", invalidation_level=24900, target_level=25100))
    assert result.exit_trigger == "INVALIDATION"
    assert result.result.exit_at == invalidated.isoformat()


def test_invalidation_survives_unexecutable_book_and_price_recovery():
    first = IST.localize(datetime(2026, 9, 10, 10))
    breach, recovery = first + timedelta(minutes=1), first + timedelta(minutes=2)
    rows = [observation(first, 1),
            replace(observation(breach, 0, pair(breach, depth=1)), public_price=24900, public_received_at=breach, public_observed_at=breach),
            replace(observation(recovery, 0), public_price=25000, public_received_at=recovery, public_observed_at=recovery)]
    result = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", observations=rows,
        policy=replace(policy(), exit_basis="PUBLIC_THESIS", direction="LONG", invalidation_level=24900, target_level=25100))
    assert result.state == "CLOSED"
    assert result.exit_trigger == "INVALIDATION"
    assert result.result.exit_at == recovery.isoformat()


@pytest.mark.parametrize("age", [-1, 601])
def test_public_event_time_cannot_be_future_or_stale(age):
    first = IST.localize(datetime(2026, 9, 10, 10))
    row = replace(observation(first, 1), public_price=25000, public_received_at=first,
                  public_observed_at=first - timedelta(seconds=age))
    with pytest.raises(ReplayInputError, match="public-price evidence"):
        replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", observations=[row], policy=policy())


def test_chronological_runner_selects_first_signal_and_first_exit_trigger_without_caller_times():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    later = first + timedelta(minutes=5)
    exit_quotes = pair(later, long_bid=110, long_ask=112, short_bid=45, short_ask=47)
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=policy(),
        observations=[observation(first, 0.1), observation(first + timedelta(minutes=1), 0.9), observation(later, 0.2, exit_quotes)],
    )
    assert replay.state == "CLOSED"
    assert replay.active_entry_at == (first + timedelta(minutes=1)).isoformat()
    assert replay.exit_trigger == "take_profit"
    assert len(replay.evidence_sha256) == 64


def test_chronological_runner_does_not_replace_active_entry_or_hide_missing_exit():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    bad_exit = tuple(replace(item, bid_depth=1, ask_depth=1, observed_at=first + timedelta(minutes=5) - timedelta(seconds=1), received_at=first + timedelta(minutes=5)) for item in pair(first + timedelta(minutes=5)))
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=policy(),
        observations=[observation(first, 0.9), observation(first + timedelta(minutes=5), 1.0, bad_exit)],
    )
    assert replay.state == "UNRESOLVED"
    assert replay.result.reason == "no_timely_executable_exit"
    assert replay.active_entry_at == first.isoformat()


def test_chronological_runner_rejects_out_of_order_receipt_evidence():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    with pytest.raises(ReplayInputError, match="receipt-ordered"):
        replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", policy=policy(),
            observations=[observation(first + timedelta(minutes=1), .9), observation(first, .9)])


def test_management_deadline_uses_exchange_time_for_utc_archive_packets():
    first = IST.localize(datetime(2026, 9, 10, 10, 0)).astimezone(pytz.UTC)
    deadline = IST.localize(datetime(2026, 9, 10, 15, 15)).astimezone(pytz.UTC)
    quiet_policy = replace(policy(), take_profit_rs=10000, stop_loss_rs=10000)
    replay = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        policy=quiet_policy, observations=[observation(first, .9), observation(deadline, 0)])
    assert replay.state == "CLOSED"
    assert replay.exit_trigger == "management_deadline"


def test_delayed_execution_uses_first_later_packet_not_decision_book():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    executed = first + timedelta(seconds=15)
    later = first + timedelta(minutes=5)
    delayed = replace(policy(), execution_delay=timedelta(seconds=10), execution_max_wait=timedelta(seconds=30))
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=delayed,
        observations=[observation(first, .9), observation(executed, .2, pair(executed, long_ask=104)),
                      observation(later, .1, pair(later, long_bid=112, long_ask=114, short_bid=43, short_ask=45))],
    )
    assert replay.active_entry_at == executed.isoformat()
    assert replay.state == "CLOSED"


def test_cancelled_delayed_signal_does_not_consume_a_later_book():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    delayed = replace(policy(), execution_delay=timedelta(seconds=10), execution_max_wait=timedelta(seconds=30), cancellation_score=.5)
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=delayed,
        observations=[observation(first, .9), observation(first + timedelta(seconds=5), .1),
                      observation(first + timedelta(seconds=15), .1)],
    )
    assert replay.state == "NO_FILL"
    assert "signal_cancelled_before_delayed_execution" in replay.rejected_entry_reasons


def test_chronological_runner_rejects_mixed_exchange_sessions():
    first = IST.localize(datetime(2026, 9, 10, 14, 59))
    with pytest.raises(ReplayInputError, match="mix exchange sessions"):
        replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", policy=policy(),
            observations=[observation(first, .9), observation(first + timedelta(days=1), .1)])


def test_invalid_first_entry_does_not_hide_a_later_accepted_exposure():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    # A nonpositive debit is invalid; the next signal is independently tested.
    invalid = (replace(pair(first)[0], bid=45, ask=47), pair(first)[1])
    later = first + timedelta(minutes=1)
    replay = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", policy=policy(),
        observations=[observation(first, .9, invalid), observation(later, .9)])
    assert replay.state == "UNRESOLVED"
    assert replay.active_entry_at == later.isoformat()
    assert "entry_debit_nonpositive" in replay.rejected_entry_reasons
    assert replay.result.accepted_entry is True


def test_cost_sensitivity_keeps_the_same_delayed_execution_evidence():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    later = first + timedelta(minutes=5)
    report = replay_cost_scenarios(
        underlying="NIFTY", expiry="2026-09-24", policy=replace(policy(), fee_per_leg_rs=5),
        observations=[observation(first, .9), observation(later, .1, pair(later, long_bid=110, long_ask=112, short_bid=43, short_ask=45))],
        fee_multipliers=[1, 2], additional_slippage_bps=[0, 10],
    )
    assert len(report["scenarios"]) == 4
    assert {row["state"] for row in report["scenarios"]} == {"CLOSED"}
    assert report["can_qualify"] is False
