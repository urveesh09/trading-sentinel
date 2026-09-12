"""Offline full-policy replay. Results are diagnostic, never delivery authority.

The entry book must be retained at the decision clock. Independent public events
are consumed in receipt order, preserving breaches between option books.
"""
from dataclasses import asdict, replace
from datetime import datetime

from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations
from intraday_spread_chronological import PublicObservation, replay_chronological_debit_spread
from intraday_spread_replay import IST, ReplayInputError
from partner_qualification import _sha, evaluate_deployed_full_policy


def replay_full_policy(*, evaluation_inputs, events, archive_root, master_sha256,
                       execution_policy, public_observations=(), public_capture_paths=()):
    """Recompute the deployed decision and replay only its selected two legs."""
    inputs = dict(evaluation_inputs)
    captures = tuple(public_capture_paths)
    public_observations = tuple(public_observations)
    public_sources = None
    if captures:
        if public_observations:
            raise ReplayInputError("cannot mix archived and caller-supplied public observations")
        from partner_research_capture import load_public_lifecycle
        public_sources = load_public_lifecycle(captures, underlying=inputs["underlying"],
            max_age_seconds=execution_policy.max_public_age.total_seconds())
        public_observations = public_sources["observations"]
    if inputs.get("contract_master_sha256") != master_sha256:
        raise ReplayInputError("evaluation and replay master digests must match")
    decision = evaluate_deployed_full_policy(**inputs)
    report = {"format": "partner_full_policy_replay_v1", "decision_id": decision.decision_id,
              "manifest": decision.manifest, "state": decision.state, "reason": decision.reason,
              "can_qualify": False, "can_deliver": False, "can_place_orders": False,
              "public_sources": public_sources,
              "limitations": ["Diagnostic only; public-source completeness, delayed-entry economics and reviewed qualification remain required."]}
    if decision.state != "ACCEPTED":
        return {**report, "evidence_sha256": _sha(report)}
    candidate = decision.candidate
    if candidate is None or len(candidate.legs) != 2 or {leg.side for leg in candidate.legs} != {"BUY", "SELL"}:
        raise ReplayInputError("accepted decision requires a two-leg vertical")
    def identity(leg):
        return SpreadContractIdentity(leg.instrument_token, leg.tradingsymbol, candidate.underlying,
            candidate.segment, leg.option_type, leg.strike, leg.expiry, leg.lot_size)
    long, short = (next(leg for leg in candidate.legs if leg.side == side) for side in ("BUY", "SELL"))
    build = build_spread_observations(events=events, long_contract=identity(long), short_contract=identity(short),
                                     master_sha256=master_sha256, archive_root=archive_root)
    now = inputs["decision_at"]
    rows = [row for row in build.observations if row.received_at >= now]
    report.update(partial_batches=list(build.partial_batches), ignored_events=build.ignored_events)
    if not rows or rows[0].received_at != now:
        report.update(state="INSUFFICIENT_EVIDENCE", reason="decision_book_missing")
        return {**report, "evidence_sha256": _sha(report)}
    for quote in rows[0].quotes:
        leg = next(leg for leg in candidate.legs if leg.instrument_token == quote.token)
        if (leg.bid, leg.ask, leg.bid_quantity, leg.ask_quantity) != (quote.bid, quote.ask, quote.bid_depth, quote.ask_depth):
            raise ReplayInputError("decision book differs from selected candidate")
    public = []
    previous = None
    for item in public_observations:
        received = item["received_at"]
        if not isinstance(received, datetime) or received.tzinfo is None:
            raise ReplayInputError("public receipt must be timezone-aware")
        if previous is not None and received <= previous:
            raise ReplayInputError("public observations must be unique and receipt-ordered")
        previous = received
        public.append(PublicObservation(item["observed_at"], received, item["price"]))
    for index, row in enumerate(rows):
        rows[index] = replace(row, signal_score=1.0 if index == 0 else 0.0)
    initial = next((item for item in reversed(public) if item.received_at <= now), None)
    if initial is None or now - initial.observed_at > execution_policy.max_public_age:
        report.update(state="INSUFFICIENT_EVIDENCE", reason="public_lifecycle_coverage_missing")
        return {**report, "evidence_sha256": _sha(report)}
    from partner_thesis import public_thesis_event
    if public_thesis_event(candidate.direction, initial.price, candidate.invalidation_level, candidate.target_level)[0]:
        report.update(state="NO_FILL", reason="public_thesis_already_crossed_at_decision")
        return {**report, "evidence_sha256": _sha(report)}
    def minute(clock):
        local = clock.astimezone(IST)
        return local.hour * 60 + local.minute
    remaining = candidate.valid_until - now
    if remaining.total_seconds() <= 0:
        raise ReplayInputError("candidate is already expired")
    policy = replace(execution_policy, policy_id=decision.manifest["policy_sha256"],
        min_signal_score=1.0, cancellation_score=None, exit_basis="PUBLIC_THESIS", direction=candidate.direction,
        invalidation_level=candidate.invalidation_level, target_level=candidate.target_level,
        entry_deadline_minute=min(execution_policy.entry_deadline_minute, minute(candidate.entry_deadline)),
        management_deadline_minute=minute(candidate.management_deadline),
        signal_expiry=min(execution_policy.signal_expiry, remaining),
        execution_max_wait=min(execution_policy.execution_max_wait, remaining),
        fee_per_leg_rs=max(execution_policy.fee_per_leg_rs, (candidate.estimated_round_trip_cost_rs or 0) / 4))
    profile = inputs["profile"]
    def tighter(first, second):
        limits = [value for value in (first, second) if value is not None]
        return min(limits) if limits else None
    policy = replace(policy,
        capital_limit_rs=tighter(policy.capital_limit_rs, profile.capital_limit_rs),
        risk_limit_rs=tighter(policy.risk_limit_rs, profile.risk_limit_rs),
        entry_start_minute=max(policy.entry_start_minute, profile.delivery_start_minute),
        entry_deadline_minute=min(policy.entry_deadline_minute, profile.delivery_end_minute))
    result = replay_chronological_debit_spread(underlying=candidate.underlying, expiry=long.expiry,
                                              observations=rows, policy=policy, public_observations=public)
    report.update(state=result.state, reason=result.result.reason, replay=asdict(result))
    return {**report, "evidence_sha256": _sha(report)}
