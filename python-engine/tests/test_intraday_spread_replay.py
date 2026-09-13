from datetime import datetime, timedelta

import pytest

from intraday_spread_replay import LegQuote, ReplayInputError, replay_intraday_debit_spread


IST = __import__("pytz").timezone("Asia/Kolkata")
ENTRY = IST.localize(datetime(2026, 9, 10, 11, 0))
EXIT = IST.localize(datetime(2026, 9, 10, 14, 30))


MASTER = "a" * 64


def quote(symbol, side, *, at=ENTRY, bid=100, ask=102, bid_depth=75, ask_depth=75, exchange="NFO", lot=75,
          oi=10_000, volume=5_000):
    strike = 25000 if "25000" in symbol else 25200
    return LegQuote(symbol, side, exchange, lot, bid, ask, bid_depth, ask_depth, at - timedelta(seconds=2), at,
                    token=strike, option_type="CE", strike=strike, expiry="2026-09-24", quantity=lot,
                    master_sha256=MASTER, oi=oi, volume=volume)


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


def test_replay_rejects_wrong_exchange_and_keeps_overnight_exit_as_exposure_uncertainty():
    wrong_exchange = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY,
        entry_quotes=pair(exchange="BFO"), exit_at=EXIT, exit_quotes=pair(at=EXIT), fee_per_leg_rs=1,
    )
    overnight = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=EXIT + timedelta(days=1), exit_quotes=pair(at=EXIT + timedelta(days=1)), fee_per_leg_rs=1,
    )
    assert (wrong_exchange.state, wrong_exchange.reason, wrong_exchange.net_pnl_rs) == ("NO_FILL", "entry_wrong_exchange", None)
    assert (overnight.state, overnight.reason, overnight.net_pnl_rs) == ("UNRESOLVED", "overnight_or_reverse_exit_unresolved", None)
    assert overnight.accepted_entry is True and overnight.entry_debit_rs == 4050.0


def test_replay_keeps_missing_exit_as_uncertainty_not_expiry_payoff():
    result = replay_intraday_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", entry_at=ENTRY, entry_quotes=pair(),
        exit_at=None, exit_quotes=[], fee_per_leg_rs=1,
    )
    assert result.state == "UNRESOLVED"
    assert result.reason == "exit_observation_missing"
    assert result.net_pnl_rs is None
    assert result.accepted_entry is True
    assert result.entry_debit_rs == 4050.0
    assert result.entry_max_loss_rs > result.entry_cost_rs


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


def test_slippage_uses_gross_leg_notional_and_cannot_be_negative():
    distressed = [quote("NIFTY26SEP25000CE", "BUY", at=EXIT, bid=1, ask=2),
                  quote("NIFTY26SEP25200CE", "SELL", at=EXIT, bid=999, ask=1000)]
    result = replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=ENTRY, entry_quotes=pair(), exit_at=EXIT, exit_quotes=distressed,
        fee_per_leg_rs=1, slippage_bps=10)
    assert result.state == "CLOSED"
    assert result.exit_credit_rs < 0
    assert result.total_cost_rs >= 4


@pytest.mark.parametrize("kwargs,reason", [
    ({"max_leg_spread_pct": .005}, "entry_spread_too_wide"),
    ({"min_oi": 20_000}, "entry_insufficient_oi"),
    ({"min_volume": 10_000}, "entry_insufficient_volume"),
    ({"min_depth_units": 100}, "entry_book_not_executable_for_full_lot"),
])
def test_execution_rechecks_deployed_liquidity_at_actual_book(kwargs, reason):
    result = replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=ENTRY, entry_quotes=pair(), exit_at=None, exit_quotes=[], fee_per_leg_rs=1, **kwargs)
    assert (result.state, result.reason) == ("NO_FILL", reason)


def test_cost_inclusive_reward_and_exact_expiry_and_clock_boundaries():
    costly = [quote("NIFTY26SEP25000CE", "BUY", bid=198, ask=200),
              quote("NIFTY26SEP25200CE", "SELL", bid=1, ask=2)]
    erased = replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=ENTRY, entry_quotes=costly, exit_at=None, exit_quotes=[], fee_per_leg_rs=20)
    assert erased.reason == "entry_cost_erases_expiry_reward"
    same_day = [LegQuote(**{**item.__dict__, "expiry": ENTRY.date().isoformat()}) for item in pair()]
    assert replay_intraday_debit_spread(underlying="NIFTY", expiry=ENTRY.date().isoformat(),
        entry_at=ENTRY, entry_quotes=same_day, exit_at=None, exit_quotes=[], fee_per_leg_rs=1).reason == \
        "entry_not_a_valid_preexpiry_market_session"
    cutoff = ENTRY.replace(hour=14, minute=45, second=0)
    at_cutoff = [LegQuote(**{**item.__dict__, "observed_at": cutoff, "received_at": cutoff}) for item in pair()]
    assert replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=cutoff, entry_quotes=at_cutoff, exit_at=None, exit_quotes=[], fee_per_leg_rs=1).accepted_entry
    after = cutoff + timedelta(microseconds=1)
    after_quotes = [LegQuote(**{**item.__dict__, "observed_at": after, "received_at": after}) for item in pair()]
    assert replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=after, entry_quotes=after_quotes, exit_at=None, exit_quotes=[], fee_per_leg_rs=1).reason == \
        "entry_after_intraday_deadline"
    management = ENTRY.replace(hour=15, minute=15, second=0)
    exact_exit = [LegQuote(**{**item.__dict__, "observed_at": management, "received_at": management}) for item in pair(at=EXIT)]
    assert replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=ENTRY, entry_quotes=pair(), exit_at=management, exit_quotes=exact_exit, fee_per_leg_rs=1).state == "CLOSED"
    late = management + timedelta(microseconds=1)
    late_exit = [LegQuote(**{**item.__dict__, "observed_at": late, "received_at": late}) for item in pair(at=EXIT)]
    assert replay_intraday_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        entry_at=ENTRY, entry_quotes=pair(), exit_at=late, exit_quotes=late_exit, fee_per_leg_rs=1).reason == \
        "exit_after_intraday_management_deadline"
