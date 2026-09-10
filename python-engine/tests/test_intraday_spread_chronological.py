from dataclasses import replace
from datetime import datetime, timedelta

import pytest
import pytz

from intraday_spread_chronological import ChronologicalPolicy, SpreadObservation, replay_chronological_debit_spread
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
