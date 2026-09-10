from datetime import datetime, timedelta

import pytest

from intraday_spread_replay import LegQuote, ReplayInputError, replay_intraday_debit_spread


IST = __import__("pytz").timezone("Asia/Kolkata")
ENTRY = IST.localize(datetime(2026, 9, 10, 11, 0))
EXIT = IST.localize(datetime(2026, 9, 10, 14, 30))


MASTER = "a" * 64


def quote(symbol, side, *, at=ENTRY, bid=100, ask=102, bid_depth=75, ask_depth=75, exchange="NFO", lot=75):
    strike = 25000 if "25000" in symbol else 25200
    return LegQuote(symbol, side, exchange, lot, bid, ask, bid_depth, ask_depth, at - timedelta(seconds=2), at,
                    token=strike, option_type="CE", strike=strike, expiry="2026-09-24", quantity=lot,
                    master_sha256=MASTER)


def pair(*, at=ENTRY, exchange="NFO"):
    return [quote("NIFTY26SEP25000CE", "BUY", at=at, bid=100, ask=102, exchange=exchange),
            quote("NIFTY26SEP25200CE", "SELL", at=at, bid=48, ask=50, exchange=exchange)]


def test_replay_uses_executable_two_leg_sides_costs_and_is_deterministic():
    first = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=2.5,
    )
    second = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=2.5,
    )
    assert first.state == "CLOSED"
    assert first.entry_debit_rs == 4050.0  # (ask long - bid short) * lot
    assert first.exit_credit_rs == 3750.0  # (bid long - ask short) * lot
    assert first.total_cost_rs == 10.0
    assert first.net_pnl_rs == -310.0
    assert first.evidence_sha256 == second.evidence_sha256
    assert first.research_only is True and first.can_place_orders is False


@pytest.mark.parametrize("mutate,expected", [
    (lambda rows: [rows[0], LegQuote(**{**rows[1].__dict__, "ask_depth": 1})], "entry_book_not_executable_for_full_lot"),
    (lambda rows: [LegQuote(**{**rows[0].__dict__, "received_at": ENTRY + timedelta(seconds=1)}), rows[1]], "entry_future_packet_or_timestamp_order_invalid"),
    (lambda rows: [LegQuote(**{**rows[0].__dict__, "observed_at": ENTRY - timedelta(seconds=8)}), rows[1]], "entry_legs_unsynchronised"),
])
def test_replay_rejects_non_executable_future_and_unsynchronised_entry_evidence(mutate, expected):
    result = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=mutate(pair()),
        exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=1,
    )
    assert result.state == "NO_FILL"
    assert result.reason == expected


def test_replay_rejects_wrong_exchange_and_overnight_exit_without_inventing_pnl():
    wrong_exchange = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY,
        entry_quotes=pair(exchange="BFO"), exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=1,
    )
    overnight = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=EXIT + timedelta(days=1), exit_quotes=pair(at=EXIT + timedelta(days=1)), fee_per_leg_rs=1,
    )
    assert (wrong_exchange.state, wrong_exchange.reason, wrong_exchange.net_pnl_rs) == ("NO_FILL", "entry_wrong_exchange", None)
    assert (overnight.state, overnight.reason, overnight.net_pnl_rs) == ("REJECTED", "overnight_or_reverse_exit_rejected", None)


def test_replay_keeps_missing_exit_as_uncertainty_not_expiry_payoff():
    result = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=None, exit_quotes=[], fee_per_leg_rs=1,
    )
    assert result.state == "UNRESOLVED"
    assert result.reason == "exit_observation_missing"
    assert result.net_pnl_rs is None


def test_replay_requires_timezone_aware_research_clocks():
    with pytest.raises(ReplayInputError, match="entry_at must be timezone-aware"):
        replay_intraday_debit_spread(
            underlying="NIFTY", expiry="2026-09-24", entry_at=datetime(2026, 9, 10, 11),
            entry_quotes=[], exit_at=None, exit_quotes=[], fee_per_leg_rs=1,
        )


def test_replay_rejects_invalid_vertical_and_freezes_full_policy_assumptions():
    from dataclasses import replace
    invalid = [replace(pair()[0], strike=25200), pair()[1]]
    rejected = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=invalid,
        exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=1,
    )
    baseline = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=1,
    )
    delayed = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=1, slippage_bps=5,
    )
    assert rejected.reason == "entry_call_strike_order_invalid"
    assert baseline.evidence_sha256 != delayed.evidence_sha256
    assert delayed.total_cost_rs > baseline.total_cost_rs


@pytest.mark.parametrize("case", ["old_observation", "wrong_exit", "negative_fee"])
def test_replay_rejects_false_execution_evidence(case):
    from dataclasses import replace
    entry, exit_ = pair(), pair(at=EXIT)
    if case == "old_observation":
        entry = [replace(q, observed_at=ENTRY-timedelta(minutes=10)) for q in entry]
    if case == "wrong_exit":
        exit_[0] = replace(exit_[0], symbol="OTHER_CONTRACT")
    kwargs = dict(underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY,
                  entry_quotes=entry, exit_at=EXIT, exit_quotes=exit_, fee_per_leg_rs=-1 if case == "negative_fee" else 1)
    if case == "negative_fee":
        with pytest.raises(ReplayInputError):
            replay_intraday_debit_spread(**kwargs)
    else:
        result = replay_intraday_debit_spread(**kwargs)
        assert result.net_pnl_rs is None
        assert result.reason == ("entry_quote_stale" if case == "old_observation" else "exit_contract_identity_mismatch")
