from dataclasses import replace
from datetime import datetime, timedelta

import pytest
import pytz

from intraday_spread_chronological import ChronologicalPolicy, SpreadObservation, replay_chronological_debit_spread, replay_cost_scenarios
from intraday_spread_replay import LegQuote, ReplayInputError
from intraday_spread_chronological import PublicObservation


IST = pytz.timezone("Asia/Kolkata")
MASTER = "b" * 64


@pytest.mark.parametrize('limit_field', ['capital_limit_rs', 'risk_limit_rs'])
def test_execution_book_rechecks_cost_inclusive_limit(limit_field):
    start = IST.localize(datetime(2026, 9, 10, 10))
    later = start + timedelta(seconds=5)
    rows = [observation(start, 1), observation(later, 0, pair(later, long_ask=110))]
    result = replay_chronological_debit_spread(underlying='NIFTY', expiry='2026-09-24', observations=rows,
        policy=replace(policy(), execution_delay=timedelta(seconds=5), fee_per_leg_rs=10,
                       **{limit_field: 4500}))
    # Original debit is 4050; delayed debit plus round-trip fees is 4690.
    assert result.state == 'NO_FILL'
    assert result.rejected_entry_reasons == (f'execution_profile_{limit_field.removesuffix("_rs")}_exceeded',)


def test_round_trip_cost_reserve_cannot_be_omitted_at_entry():
    start = IST.localize(datetime(2026, 9, 10, 10))
    result = replay_chronological_debit_spread(underlying='NIFTY', expiry='2026-09-24',
        observations=[observation(start, 1)], policy=replace(policy(), fee_per_leg_rs=10, capital_limit_rs=4080))
    assert result.state == 'NO_FILL'  # 4050 debit + 40 reserve, not entry fees of 20.


def test_cost_scenarios_reuse_independent_public_stream():
    start = IST.localize(datetime(2026, 9, 10, 10))
    breach = start + timedelta(seconds=1)
    result = replay_cost_scenarios(underlying='NIFTY', expiry='2026-09-24',
        observations=[observation(start, 1), observation(start + timedelta(seconds=5), 0)],
        public_observations=iter([PublicObservation(breach, breach, 24900)]),
        fee_multipliers=[1, 2], policy=replace(policy(), exit_basis='PUBLIC_THESIS', direction='LONG',
                                             invalidation_level=24900, target_level=25100))
    assert len(result['scenarios']) == 2
    assert all(item['state'] == 'CLOSED' for item in result['scenarios'])


def test_independent_breach_survives_recovery_and_delay_uses_actual_receipt():
    start = IST.localize(datetime(2026, 9, 10, 10))
    # Entry at +5s; breach at +11s, recovery at +12s, executable book at +16s.
    rows = [observation(start, 1), observation(start + timedelta(seconds=5), 0),
            observation(start + timedelta(seconds=16), 0)]
    public = [PublicObservation(start + timedelta(seconds=s), start + timedelta(seconds=s), price)
              for s, price in [(0, 25000), (11, 24900), (12, 25000)]]
    result = replay_chronological_debit_spread(underlying='NIFTY', expiry='2026-09-24', observations=rows,
        public_observations=public, policy=replace(policy(), execution_delay=timedelta(seconds=5),
            exit_basis='PUBLIC_THESIS', direction='LONG', invalidation_level=24900, target_level=25100))
    assert result.state == 'CLOSED'
    assert result.exit_trigger == 'INVALIDATION'
    assert result.result.exit_at == rows[-1].received_at.isoformat()


def test_independent_breach_before_delayed_entry_cancels_even_after_recovery():
    start = IST.localize(datetime(2026, 9, 10, 10))
    rows = [observation(start, 1), observation(start + timedelta(seconds=5), 0)]
    public = [PublicObservation(start + timedelta(seconds=s), start + timedelta(seconds=s), price)
              for s, price in [(1, 24900), (2, 25000)]]
    result = replay_chronological_debit_spread(underlying='NIFTY', expiry='2026-09-24', observations=rows,
        public_observations=public, policy=replace(policy(), execution_delay=timedelta(seconds=5),
            exit_basis='PUBLIC_THESIS', direction='LONG', invalidation_level=24900, target_level=25100))
    assert result.state == 'NO_FILL'
    assert 'public_thesis_cancelled_before_execution' in result.rejected_entry_reasons


def test_public_breach_without_later_book_remains_unresolved():
    start = IST.localize(datetime(2026, 9, 10, 10))
    breach = start + timedelta(seconds=1)
    result = replay_chronological_debit_spread(underlying='NIFTY', expiry='2026-09-24',
        observations=[observation(start, 1)], public_observations=[PublicObservation(breach, breach, 24900)],
        policy=replace(policy(), exit_basis='PUBLIC_THESIS', direction='LONG', invalidation_level=24900, target_level=25100))
    assert result.state == 'UNRESOLVED'
    assert result.exit_trigger == 'INVALIDATION'


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


# [WORKFLOW-C.A2 2026-09-15] Monotonic delayed-execution
# assertion. The chronological replay's delayed-execution
# helper (``_execution_observation``) returns the FIRST
# later observation whose ``received_at >= eligible_at``
# where ``eligible_at = decision.received_at +
# execution_delay``. The invariant -- the active entry
# can never be earlier than the configured execution
# delay -- is critical for the operator to trust the
# diagnostic. Without a hard test, a future refactor
# could break the invariant silently.


def test_delayed_execution_entry_is_strictly_at_or_after_configured_delay():
    """[WORKFLOW-C.A2 2026-09-15] The active entry's
    received_at MUST be at or after the decision packet's
    received_at + the configured execution_delay. Pin
    this monotonic invariant.
    """
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    delay = timedelta(seconds=10)
    executed = first + timedelta(seconds=15)  # 5s after eligible_at
    later = first + timedelta(minutes=5)
    delayed = replace(policy(), execution_delay=delay, execution_max_wait=timedelta(seconds=30))
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=delayed,
        observations=[observation(first, .9), observation(executed, .2, pair(executed, long_ask=104)),
                      observation(later, .1, pair(later, long_bid=112, long_ask=114, short_bid=43, short_ask=45))],
    )
    active_entry_at = datetime.fromisoformat(replay.active_entry_at)
    decision_at = first  # the first observation is the decision.
    eligible_at = decision_at + delay
    assert active_entry_at >= eligible_at, (
        f"active_entry_at={active_entry_at} is BEFORE eligible_at={eligible_at} "
        f"(decision={decision_at}, delay={delay})"
    )


def test_delayed_execution_chooses_first_eligible_packet_in_receipt_order():
    """[WORKFLOW-C.A2 2026-09-15] When multiple packets
    arrive after eligible_at, the helper must choose the
    FIRST eligible one in RECEIPT order. The chronological
    replay requires observations to be strictly receipt-
    ordered (line 221: ``prior_received < received``), so
    the list order IS the receipt order.

    The active entry is therefore the EARLIEST packet whose
    ``received_at >= eligible_at``. This pins the "forward
    consumption" invariant: the helper never skips an
    earlier eligible packet for a later one.
    """
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    delay = timedelta(seconds=10)
    # Three candidates, all AFTER eligible_at, in receipt
    # order (strictly increasing ``received_at``).
    candidate_a = first + timedelta(seconds=10)  # exactly at eligible_at
    candidate_b = first + timedelta(seconds=20)
    candidate_c = first + timedelta(seconds=30)
    delayed = replace(policy(), execution_delay=delay, execution_max_wait=timedelta(seconds=60))
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=delayed,
        observations=[
            observation(first, .9),
            observation(candidate_a, .2, pair(candidate_a, long_ask=104)),
            observation(candidate_b, .2, pair(candidate_b, long_ask=104)),
            observation(candidate_c, .1, pair(candidate_c, long_bid=112, long_ask=114, short_bid=43, short_ask=45)),
        ],
    )
    active_entry_at = datetime.fromisoformat(replay.active_entry_at)
    # The active entry is candidate_a -- the FIRST eligible
    # packet by receipt order.
    assert active_entry_at == candidate_a, (
        f"active_entry_at={active_entry_at} != candidate_a={candidate_a} "
        f"(the first eligible packet by receipt order)"
    )


def test_delayed_execution_zero_delay_returns_decision_packet():
    """[WORKFLOW-C.A2 2026-09-15] When execution_delay is
    zero, the helper returns the decision packet itself.
    The monotonic invariant trivially holds (active_entry
    == decision + 0 delay).
    """
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    replay = replay_chronological_debit_spread(
        underlying="NIFTY", expiry="2026-09-24", policy=policy(),
        observations=[observation(first, .9, pair(first, long_ask=104)),
                      observation(first + timedelta(seconds=10), .1, pair(first + timedelta(seconds=10),
                                                                       long_bid=112, long_ask=114,
                                                                       short_bid=43, short_ask=45))],
    )
    active_entry_at = datetime.fromisoformat(replay.active_entry_at)
    assert active_entry_at == first


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


def test_cost_sensitivity_always_includes_baseline_and_rejects_boolean_coordinates():
    first = IST.localize(datetime(2026, 9, 10, 10, 0))
    report = replay_cost_scenarios(underlying="NIFTY", expiry="2026-09-24", policy=policy(),
        observations=[observation(first, .9)], fee_multipliers=[1.25], additional_slippage_bps=[10])
    assert {(row["fee_multiplier"], row["additional_slippage_bps"]) for row in report["scenarios"]} == {
        (1.0, 0.0), (1.25, 10.0)}
    with pytest.raises(ReplayInputError, match="booleans"):
        replay_cost_scenarios(underlying="NIFTY", expiry="2026-09-24", policy=policy(),
            observations=[observation(first, .9)], fee_multipliers=[True], additional_slippage_bps=[0])


def test_embedded_public_breach_at_delayed_fill_cancels_entry_on_boundary():
    start = IST.localize(datetime(2026, 9, 10, 10))
    fill = start + timedelta(seconds=5)
    rows = [observation(start, 1), replace(observation(fill, 0), public_price=24900,
            public_received_at=fill, public_observed_at=fill)]
    replay = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24", observations=rows,
        policy=replace(policy(), execution_delay=timedelta(seconds=5), exit_basis="PUBLIC_THESIS",
                       direction="LONG", invalidation_level=24900, target_level=25100))
    assert replay.state == "NO_FILL"
    assert replay.rejected_entry_reasons == ("public_thesis_cancelled_before_execution",)


def test_exact_signal_expiry_is_not_a_delayed_fill_and_late_exit_stays_unresolved():
    start = IST.localize(datetime(2026, 9, 10, 10))
    boundary = start + timedelta(seconds=10)
    no_fill = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        observations=[observation(start, 1), observation(boundary, 0)],
        policy=replace(policy(), execution_delay=timedelta(seconds=10), signal_expiry=timedelta(seconds=10)))
    assert no_fill.state == "NO_FILL"
    assert no_fill.rejected_entry_reasons == ("delayed_execution_packet_unavailable",)
    fill = start + timedelta(seconds=5)
    breach = start + timedelta(seconds=6)
    too_late = start + timedelta(seconds=40)
    unresolved = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        observations=[observation(start, 1), observation(fill, 0), observation(too_late, 0)],
        public_observations=[PublicObservation(start, start, 25000), PublicObservation(breach, breach, 24900)],
        policy=replace(policy(), execution_delay=timedelta(seconds=5), execution_max_wait=timedelta(seconds=30),
                       exit_basis="PUBLIC_THESIS", direction="LONG", invalidation_level=24900, target_level=25100))
    assert unresolved.state == "UNRESOLVED"
    assert unresolved.result.reason == "no_timely_executable_exit"


def test_delayed_fill_rechecks_public_observation_age():
    start = IST.localize(datetime(2026, 9, 10, 10))
    fill = start + timedelta(seconds=5)
    result = replay_chronological_debit_spread(underlying="NIFTY", expiry="2026-09-24",
        observations=[observation(start, 1), observation(fill, 0)],
        public_observations=[PublicObservation(start - timedelta(minutes=10), start, 25000)],
        policy=replace(policy(), execution_delay=timedelta(seconds=5), exit_basis="PUBLIC_THESIS",
                       direction="LONG", invalidation_level=24900, target_level=25100))
    assert result.state == "NO_FILL"
    assert result.rejected_entry_reasons == ("execution_public_evidence_stale",)
