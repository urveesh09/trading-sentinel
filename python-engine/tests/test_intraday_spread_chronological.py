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
