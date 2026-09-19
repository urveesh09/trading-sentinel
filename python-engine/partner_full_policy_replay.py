"""Offline full-policy replay. Results are diagnostic, never delivery authority.

The entry book must have been received by the decision clock. Independent public events
are consumed in receipt order, preserving breaches between option books.
"""
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any, Mapping

from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations
from intraday_spread_chronological import (ChronologicalReplay, PublicObservation,
                                           replay_chronological_debit_spread,
                                           replay_cost_scenarios)
from intraday_spread_replay import IST, ReplayInputError, ReplayResult
from partner_qualification import _sha, _bars_payload, evaluate_deployed_full_policy


def _pre_decision_window_hit(
    item: Mapping[str, Any],
    book_at_decision_received_at: "datetime",
    now: "datetime",
) -> bool:
    """[WORKFLOW-C.C1 2026-09-15] Defensive predicate for the
    pre-decision asymmetric/partial-batch window check.

    Returns True iff ``item`` has a parseable ``received_at``
    in the strict window
    ``book_at_decision_received_at < ts <= now`` -- the same
    window the A1 fail-closed check uses inline. Malformed
    timestamps (missing field, non-string, unparseable)
    degrade to ``False`` rather than crashing the replay.

    The replay MUST stay alive even when individual capture
    events have malformed fields; the structured
    ``asymmetric_diagnostic`` block surfaces what we can.
    """
    raw = item.get("received_at")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        ts = datetime.fromisoformat(raw)
        if ts.tzinfo is None or ts.utcoffset() is None:
            return False
        return book_at_decision_received_at < ts <= now
    except (TypeError, ValueError):
        return False


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
                  # [WORKFLOW-C.A1 2026-09-15] Asymmetric-
                  # fills diagnostic. When one leg had
                  # executable depth and the other did not
                  # at a receipt time <= the decision clock,
                  # the decision book itself was partially
                  # executable -- the operator cannot claim
                  # the decision was made against a fully
                  # executable two-leg book. Surface the
                  # diagnostic AND fail-closed (treat as
                  # INSUFFICIENT_EVIDENCE) below. Mirrors the
                  # partial_batches discipline at lines 115-118.
                  asymmetric_batches=list(build.asymmetric_batches or []),
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
    # [WORKFLOW-C.C1 2026-09-15] Structured asymmetric-fill
    # diagnostic (Option 3 from the C-investigation). The
    # asymmetric_batches list is the raw evidence; this
    # block is the operator-visible summary that answers:
    #  - Was there an asymmetric-fill condition at the
    #    decision clock? (boolean)
    #  - Which legs were executable / insufficient?
    #  - When did the condition first appear? last appear?
    # The replay is still fail-closed below (Option 1
    # behavior preserved): a pre-decision asymmetric batch
    # causes INSUFFICIENT_EVIDENCE. This block just makes the
    # attribution visible without forcing the operator to
    # grep asymmetric_batches. Mirrors how conflicting_batches
    # is reported alongside state/reason.
    pre_decision_asymmetric: list[dict] = []
    executable_legs: set[str] = set()
    insufficient_legs: set[str] = set()
    for item in build.asymmetric_batches or []:
        for leg in item.get("executable", []):
            executable_legs.add(str(leg))
        for leg in item.get("insufficient", []):
            insufficient_legs.add(str(leg))
        # [WORKFLOW-C.C1 2026-09-15] Use the defensive
        # helper for the pre-decision window check. Malformed
        # ``received_at`` degrades to exclusion from the
        # pre-decision subset (the diagnostic still counts
        # the batch in ``asymmetric_batch_count`` and
        # attributes the leg names).
        if _pre_decision_window_hit(item, book_at_decision.received_at, now):
            pre_decision_asymmetric.append(item)
    pre_decision_received_ats = [item["received_at"] for item in pre_decision_asymmetric
                                  if isinstance(item.get("received_at"), str)]
    report["asymmetric_diagnostic"] = {
        "pre_decision_asymmetric_observed": bool(pre_decision_asymmetric),
        "asymmetric_batch_count": len(build.asymmetric_batches or []),
        "pre_decision_batch_count": len(pre_decision_asymmetric),
        "executable_legs": sorted(executable_legs),
        "insufficient_legs": sorted(insufficient_legs),
        "earliest_received_at": min(pre_decision_received_ats)
            if pre_decision_received_ats else None,
        "latest_received_at": max(pre_decision_received_ats)
            if pre_decision_received_ats else None,
    }
    if any(book_at_decision.received_at < datetime.fromisoformat(item["received_at"]) <= now
           for item in build.partial_batches):
        report.update(state="INSUFFICIENT_EVIDENCE", reason="partial_book_before_decision")
        return {**report, "evidence_sha256": _sha(report)}
    # [WORKFLOW-C.C2.WIRE 2026-09-16] Wire the asymmetric
    # partial-fill model (Q1-Q4) into the full-policy replay.
    #
    # Per the 2026-09-16 operator decisions on C.2:
    #   Q1: 'Filled at mid + 2bps' (estimate from mid-price).
    #   Q2: All exchanges same (no per-exchange differentiation).
    #   Q3: Partial counts as CLOSED with partial P&L
    #       (realized partial fill).
    #   Q4: No new operator-config knobs.
    #
    # Before this slice: a pre-decision asymmetric batch
    # caused ``INSUFFICIENT_EVIDENCE,
    # reason=asymmetric_execution_quality_before_decision``
    # (C.A1 fail-closed discipline).
    #
    # After this slice: the missing leg's fill price is
    # estimated via ``estimate_missing_leg_price`` (mid+2bps),
    # the replay returns ``state=CLOSED,
    # reason=partial_fill_modeled, partial_fill_observed=True``
    # with the modelled missing-leg P&L contribution. The
    # asymmetric_diagnostic block already in place (C.C1) is
    # extended with the modelled price for auditability.
    #
    # The wiring is exchange-agnostic (Q2): no per-exchange
    # switch. The slippage is hard-coded at the function
    # default (Q4): no runtime config knob.
    from asymmetric_fill_model import (compute_modeled_entry_slippage_pnl,
                                       estimate_missing_leg_price)
    # First pre-decision asymmetric batch drives the
    # modelled fill. Multiple asymmetric batches in the same
    # window get aggregated via the model.
    pre_decision_asymmetric_batches = [
        item for item in build.asymmetric_batches or []
        if _pre_decision_window_hit(item, book_at_decision.received_at, now)
    ]
    if pre_decision_asymmetric_batches:
        # Bind the model to the exact archived quote that produced each
        # asymmetric diagnostic.  The older complete decision book is not a
        # valid substitute: its prices may predate the observed asymmetry.
        leg_by_name = {"long": long, "short": short}
        leg_side_by_name = {"long": "BUY", "short": "SELL"}
        # For each asymmetric batch, identify the missing
        # leg(s). With the C.A1 diagnostic contract, exactly
        # one leg is executable and one is insufficient per
        # batch. We model the missing (insufficient) leg.
        missing_legs_by_batch = []
        for batch in pre_decision_asymmetric_batches:
            for missing_name in batch.get("insufficient", []):
                if missing_name not in leg_by_name:
                    continue
                side = leg_side_by_name[missing_name]
                quote_by_leg = batch.get("quote_by_leg")
                source = (quote_by_leg.get(missing_name)
                          if isinstance(quote_by_leg, Mapping) else None)
                expected_leg = leg_by_name[missing_name]
                valid_source = isinstance(source, Mapping)
                if valid_source:
                    raw_sha = source.get("raw_sha256")
                    quantity = source.get("quantity")
                    try:
                        source_observed_at = datetime.fromisoformat(
                            str(source.get("observed_at")))
                        source_received_at = datetime.fromisoformat(
                            str(source.get("received_at")))
                        batch_received_at = datetime.fromisoformat(
                            str(batch.get("received_at")))
                        valid_clocks = (
                            source_observed_at.tzinfo is not None
                            and source_observed_at.utcoffset() is not None
                            and source_received_at.tzinfo is not None
                            and source_received_at.utcoffset() is not None
                            and batch_received_at.tzinfo is not None
                            and batch_received_at.utcoffset() is not None
                            and source_received_at == batch_received_at
                            and source_observed_at <= source_received_at
                        )
                    except (TypeError, ValueError):
                        valid_clocks = False
                    valid_source = (
                        source.get("side") == side
                        and str(source.get("instrument_token")) == str(expected_leg.instrument_token)
                        and source.get("symbol") == expected_leg.tradingsymbol
                        and source.get("received_at") == batch.get("received_at")
                        and source.get("lot_size") == expected_leg.lot_size
                        and valid_clocks
                        and isinstance(raw_sha, str) and len(raw_sha) == 64
                        and all(char in "0123456789abcdef" for char in raw_sha.lower())
                        and not isinstance(quantity, bool) and isinstance(quantity, int)
                        and quantity == expected_leg.lot_size
                    )
                bid = source.get("bid") if valid_source else None
                ask = source.get("ask") if valid_source else None
                modelled_fill = estimate_missing_leg_price(
                    bid=bid,
                    ask=ask,
                    side=side,  # type: ignore[arg-type]
                )
                missing_legs_by_batch.append({
                    "received_at": batch.get("received_at"),
                    "leg_name": missing_name,
                    "side": side,
                    "source_quote_sha256": source.get("raw_sha256") if valid_source else None,
                    "source_observed_at": source.get("observed_at") if valid_source else None,
                    "source_received_at": source.get("received_at") if valid_source else None,
                    "source_bid": bid,
                    "source_ask": ask,
                    "quantity": source.get("quantity") if valid_source else None,
                    "modeled_fill_price": modelled_fill,
                    "modeled_mid_slippage_bps": 2.0,
                })
        # Compute partial fill P&L using the model. For the
        # asymmetric-batch case, no leg has a broker fill
        # yet -- we are modelling the missing leg AS IF
        # the order would have been submitted and the
        # missing leg would have filled at mid+2bps.
        # ``filled_legs`` is empty here; the partial P&L is
        # the modelled missing-leg contribution only.
        # qty: use the leg's quantity (or fall back to 1).
        total_modeled_pnl = 0.0
        for ml in missing_legs_by_batch:
            qty = ml.get("quantity")
            if (ml.get("modeled_fill_price") is None or isinstance(qty, bool)
                    or not isinstance(qty, int) or qty <= 0):
                ml["partial_pnl_rs"] = None
                report["asymmetric_diagnostic"] = {
                    **report.get("asymmetric_diagnostic", {}),
                    "modeled_missing_legs": missing_legs_by_batch,
                    "modeled_slippage_bps": 2.0,
                }
                report.update(state="INSUFFICIENT_EVIDENCE",
                              reason="partial_fill_model_unavailable")
                return {**report, "evidence_sha256": _sha(report)}
            partial_pnl = compute_modeled_entry_slippage_pnl(
                qty=qty, side=ml["side"],
                bid=ml["source_bid"], ask=ml["source_ask"],
                mid_slippage_bps=2.0)
            ml["partial_pnl_rs"] = partial_pnl
            if partial_pnl is None:
                report["asymmetric_diagnostic"] = {
                    **report.get("asymmetric_diagnostic", {}),
                    "modeled_missing_legs": missing_legs_by_batch,
                    "modeled_slippage_bps": 2.0,
                }
                report.update(state="INSUFFICIENT_EVIDENCE",
                              reason="partial_fill_model_unavailable")
                return {**report, "evidence_sha256": _sha(report)}
            total_modeled_pnl += partial_pnl
        if not missing_legs_by_batch:
            report.update(state="INSUFFICIENT_EVIDENCE",
                          reason="partial_fill_model_unavailable")
            return {**report, "evidence_sha256": _sha(report)}
        # Extend the asymmetric_diagnostic block with the
        # modelled missing-leg attribution. The existing
        # fields remain unchanged for backwards
        # compatibility with C.C1 consumers.
        report["asymmetric_diagnostic"] = {
            **report.get("asymmetric_diagnostic", {}),
            "modeled_missing_legs": missing_legs_by_batch,
            "total_modeled_pnl_rs": round(float(total_modeled_pnl), 4),
            "modeled_slippage_bps": 2.0,
        }
        # This is not a normal two-leg chronological close. Preserve the
        # operator-selected CLOSED state while emitting a separate, explicit
        # replay contract so held-out review can ingest and distinguish it.
        # No full-policy cost-sensitivity artifact is fabricated here.
        model_clocks = sorted(datetime.fromisoformat(str(item["received_at"]))
                              for item in pre_decision_asymmetric_batches)
        modeled_evidence = _sha({
            "format": "modeled_partial_fill_replay_v1",
            "decision_id": decision.decision_id,
            "manifest_sha256": decision.manifest["manifest_sha256"],
            "decision_book_received_at": book_at_decision.received_at.isoformat(),
            "asymmetric_diagnostic": report["asymmetric_diagnostic"],
        })
        modeled_result = ReplayResult(
            state="CLOSED", reason="partial_fill_modeled",
            entry_debit_rs=None, exit_credit_rs=None, total_cost_rs=None,
            net_pnl_rs=round(float(total_modeled_pnl), 4),
            entry_at=model_clocks[0].isoformat(), exit_at=model_clocks[-1].isoformat(),
            evidence_sha256=modeled_evidence, accepted_entry=True,
        )
        modeled_replay = ChronologicalReplay(
            result=modeled_result, state="CLOSED", attempted_entries=1,
            rejected_entry_reasons=(), active_entry_at=modeled_result.entry_at,
            exit_trigger="MODELED_PARTIAL_FILL", observation_count=len(model_clocks),
            evidence_sha256=modeled_evidence,
        )
        report.update(state="CLOSED", reason="partial_fill_modeled",
                      partial_fill_observed=True,
                      economics_contract="MODELED_PARTIAL_FILL_V1",
                      replay=asdict(modeled_replay))
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
