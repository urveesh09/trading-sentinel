"""Offline full-policy replay. Results are diagnostic, never delivery authority.

The entry book must have been received by the decision clock. Independent public events
are consumed in receipt order, preserving breaches between option books.
"""
from dataclasses import asdict, replace
from datetime import datetime

from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations
from intraday_spread_chronological import PublicObservation, replay_chronological_debit_spread, replay_cost_scenarios
from intraday_spread_replay import IST, ReplayInputError
from partner_qualification import _sha, _bars_payload, evaluate_deployed_full_policy


def write_replay_report(path, report):
    """Durably create an immutable report; allow only identical retries."""
    import json
    import os
    import tempfile
    from pathlib import Path
    body = {key: value for key, value in report.items() if key != "evidence_sha256"}
    if report.get("evidence_sha256") != _sha(body):
        raise ValueError("replay report fingerprint mismatch")
    target = Path(path)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".replay-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ValueError("replay output already contains different immutable evidence")
    finally:
        os.unlink(temporary)


def replay_full_policy(*, evaluation_inputs, events, archive_root, master_sha256,
                       execution_policy, public_observations=(), public_capture_paths=(),
                       fee_multipliers=(1.0,), additional_slippage_bps=(0.0,)):
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
        from intraday_spread_archive_adapter import master_proves_public_scope
        expected_segment = getattr(inputs.get("book"), "segment", None)
        for source in public_sources["sources"]:
            scope = source.get("public_scope")
            if (source.get("public_scope_state") != "VERIFIED_CONTRACT_SCOPE"
                    or not isinstance(scope, dict)
                    or scope.get("underlying") != inputs["underlying"]
                    or scope.get("exchange") != expected_segment
                    or scope.get("contract_master_raw_sha256") != master_sha256):
                raise ReplayInputError("public capture contract/master scope mismatch")
            if not master_proves_public_scope(archive_root, scope, master_sha256):
                raise ReplayInputError("archived master does not prove public futures scope")
        decision_bars = inputs["bars"].copy()
        if getattr(decision_bars.index, "tz", None) is not None:
            decision_bars.index = decision_bars.index.tz_convert("Asia/Kolkata").tz_localize(None)
        cutoff = inputs.get("evaluation_cutoff_at", inputs["decision_at"])
        if not any(datetime.fromisoformat(source["evaluation_at"]) == cutoff
                   and source["bars_sha256"] == _sha(_bars_payload(decision_bars))
                   and source["regime"] == inputs["regime"]
                   for source in public_sources["sources"]):
            raise ReplayInputError("decision bars are not bound to an archived public capture")
    if inputs.get("contract_master_sha256") != master_sha256:
        raise ReplayInputError("evaluation and replay master digests must match")
    decision = evaluate_deployed_full_policy(**inputs)
    public_evidence_contract = ("VERIFIED_ARCHIVED_FUTURE_SCOPE_V1" if captures
                                else "CALLER_SUPPLIED_DIAGNOSTIC")
    report = {"format": "partner_full_policy_replay_v1", "decision_id": decision.decision_id,
              "manifest": decision.manifest, "state": decision.state, "reason": decision.reason,
              "can_qualify": False, "can_deliver": False, "can_place_orders": False,
              "public_sources": public_sources, "public_evidence_contract": public_evidence_contract,
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
    prior_books = [row for row in build.observations if row.received_at <= now]
    report.update(partial_batches=list(build.partial_batches),
                  conflicting_batches=list(build.conflicting_batches),
                  ignored_events=build.ignored_events)
    relevant_conflicts = [item for item in build.conflicting_batches
                          if datetime.fromisoformat(item["received_at"]) <= now]
    if relevant_conflicts and (not prior_books or
            datetime.fromisoformat(relevant_conflicts[-1]["received_at"]) >= prior_books[-1].received_at):
        report.update(state="INSUFFICIENT_EVIDENCE", reason="decision_book_conflict")
        return {**report, "evidence_sha256": _sha(report)}
    if not prior_books:
        report.update(state="INSUFFICIENT_EVIDENCE", reason="decision_book_missing")
        return {**report, "evidence_sha256": _sha(report)}
    book_at_decision = prior_books[-1]
    report["decision_book_received_at"] = book_at_decision.received_at.isoformat()
    if any(book_at_decision.received_at < datetime.fromisoformat(item["received_at"]) <= now
           for item in build.partial_batches):
        report.update(state="INSUFFICIENT_EVIDENCE", reason="partial_book_before_decision")
        return {**report, "evidence_sha256": _sha(report)}
    if any(now - quote.observed_at > execution_policy.max_quote_age for quote in book_at_decision.quotes):
        report.update(state="INSUFFICIENT_EVIDENCE", reason="decision_book_stale")
        return {**report, "evidence_sha256": _sha(report)}
    # This is a decision event using an already received book, not a new quote.
    # Each LegQuote retains its original provider and receipt timestamps.
    rows = [replace(book_at_decision, received_at=now)] + [
        row for row in build.observations if row.received_at > now]
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
    initial = next((item for item in reversed(public) if item.received_at <= now), None)
    if initial is None or now - initial.observed_at > execution_policy.max_public_age:
        report.update(state="INSUFFICIENT_EVIDENCE", reason="public_lifecycle_coverage_missing")
        return {**report, "evidence_sha256": _sha(report)}
    from partner_thesis import public_thesis_event
    thesis_crossed_at_decision = bool(public_thesis_event(
        candidate.direction, initial.price, candidate.invalidation_level, candidate.target_level)[0])
    if thesis_crossed_at_decision:
        report["decision_guard"] = "public_thesis_already_crossed_at_decision"
    for index, row in enumerate(rows):
        rows[index] = replace(row, signal_score=1.0 if index == 0 and not thesis_crossed_at_decision else 0.0)
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
        entry_deadline_minute=min(policy.entry_deadline_minute, profile.delivery_end_minute),
        max_leg_spread_pct=decision.manifest["config"]["PARTNER_MANUAL_ADVISORY_MAX_SPREAD_PCT"],
        min_oi=decision.manifest["config"]["PARTNER_MANUAL_ADVISORY_MIN_OI"],
        min_volume=decision.manifest["config"]["PARTNER_MANUAL_ADVISORY_MIN_VOLUME"],
        min_depth_units=decision.manifest["config"]["PARTNER_MANUAL_ADVISORY_MIN_DEPTH_UNITS"])
    result = replay_chronological_debit_spread(underlying=candidate.underlying, expiry=long.expiry,
                                              observations=rows, policy=policy, public_observations=public)
    sensitivity = replay_cost_scenarios(underlying=candidate.underlying, expiry=long.expiry,
        observations=rows, policy=policy, public_observations=public,
        fee_multipliers=fee_multipliers, additional_slippage_bps=additional_slippage_bps)
    report.update(state=result.state, economics_contract="FULL_POLICY_ECONOMICS_V1",
                  reason="public_thesis_already_crossed_at_decision" if thesis_crossed_at_decision else result.result.reason,
                  replay=asdict(result),
                  cost_sensitivity=sensitivity)
    return {**report, "evidence_sha256": _sha(report)}
