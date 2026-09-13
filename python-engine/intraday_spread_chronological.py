"""No-look-ahead chronological research runner for intraday debit spreads.

The lower-level replay helper remains useful for one bounded observation pair.
This module owns the decision sequence so a researcher cannot choose a lucky
entry and exit after seeing the session.  It has no broker or delivery import.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable

from intraday_spread_replay import IST, LegQuote, ReplayInputError, ReplayResult, replay_intraday_debit_spread


@dataclass(frozen=True)
class SpreadObservation:
    """One received two-leg book and deterministic signal value.

    The signal must have been computed from data available by ``received_at``;
    callers do not supply entry or exit timestamps.  ``quotes`` are immutable
    contract observations and are validated by the lower-level replay.
    """
    observed_at: datetime
    received_at: datetime
    signal_score: float
    quotes: tuple[LegQuote, ...]
    public_price: float | None = None
    public_received_at: datetime | None = None
    public_observed_at: datetime | None = None


@dataclass(frozen=True)
class PublicObservation:
    observed_at: datetime
    received_at: datetime
    price: float


@dataclass(frozen=True)
class ChronologicalPolicy:
    policy_id: str
    min_signal_score: float
    take_profit_rs: float
    stop_loss_rs: float
    entry_start_minute: int = 9 * 60 + 20
    entry_deadline_minute: int = 14 * 60 + 45
    management_deadline_minute: int = 15 * 60 + 15
    max_quote_age: timedelta = timedelta(seconds=30)
    max_leg_sync: timedelta = timedelta(seconds=5)
    fee_per_leg_rs: float = 0.0
    slippage_bps: float = 0.0
    execution_delay: timedelta = timedelta(0)
    # A delayed manual execution must use a later packet, and a decision is
    # short-lived rather than a standing permission to enter at any later price.
    execution_max_wait: timedelta = timedelta(seconds=30)
    signal_expiry: timedelta = timedelta(seconds=30)
    cancellation_score: float | None = 0.0
    exit_basis: str = "SPREAD_PNL"
    direction: str | None = None
    invalidation_level: float | None = None
    target_level: float | None = None
    max_public_age: timedelta = timedelta(minutes=10)
    capital_limit_rs: float | None = None
    risk_limit_rs: float | None = None
    max_leg_spread_pct: float | None = None
    min_oi: int = 0
    min_volume: int = 0
    min_depth_units: int = 0
    min_reward_risk: float = 0.0


@dataclass(frozen=True)
class ChronologicalReplay:
    result: ReplayResult
    state: str
    attempted_entries: int
    rejected_entry_reasons: tuple[str, ...]
    active_entry_at: str | None
    exit_trigger: str | None
    observation_count: int
    evidence_sha256: str


def _clock(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayInputError(f"{field} must be timezone-aware")
    return value


def _policy_payload(policy: ChronologicalPolicy) -> dict:
    for limit in (policy.capital_limit_rs, policy.risk_limit_rs):
        if limit is not None and (isinstance(limit, bool) or not math.isfinite(limit) or limit <= 0):
            raise ReplayInputError("execution capital/risk limits must be finite and positive")
    if policy.exit_basis not in {"SPREAD_PNL", "PUBLIC_THESIS"}:
        raise ReplayInputError("unknown exit basis")
    if policy.max_public_age <= timedelta(0):
        raise ReplayInputError("public price age bound must be positive")
    if policy.exit_basis == "PUBLIC_THESIS":
        if (policy.direction not in {"LONG", "SHORT"}
                or any(value is None or not math.isfinite(value) or value <= 0
                       for value in (policy.invalidation_level, policy.target_level))):
            raise ReplayInputError("public thesis requires direction and finite levels")
    if not policy.policy_id.strip() or not all(math.isfinite(float(item)) for item in
                                               (policy.min_signal_score, policy.take_profit_rs, policy.stop_loss_rs,
                                                policy.fee_per_leg_rs, policy.slippage_bps)):
        raise ReplayInputError("chronological policy contains a non-finite value")
    if policy.take_profit_rs <= 0 or policy.stop_loss_rs <= 0 or policy.slippage_bps < 0:
        raise ReplayInputError("chronological policy thresholds are invalid")
    if (policy.max_leg_spread_pct is not None
            and (isinstance(policy.max_leg_spread_pct, bool)
                 or not math.isfinite(policy.max_leg_spread_pct)
                 or not 0 < policy.max_leg_spread_pct <= 1)):
        raise ReplayInputError("chronological maximum leg spread is invalid")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
           for value in (policy.min_oi, policy.min_volume, policy.min_depth_units)):
        raise ReplayInputError("chronological liquidity thresholds are invalid")
    if (isinstance(policy.min_reward_risk, bool) or not math.isfinite(policy.min_reward_risk)
            or policy.min_reward_risk < 0):
        raise ReplayInputError("chronological reward/risk threshold is invalid")
    if (policy.execution_delay < timedelta(0) or policy.execution_max_wait <= timedelta(0)
            or policy.signal_expiry <= timedelta(0)
            or (policy.cancellation_score is not None and not math.isfinite(float(policy.cancellation_score)))):
        raise ReplayInputError("chronological execution policy bounds are invalid")
    return ({"policy_id": policy.policy_id, "min_signal_score": policy.min_signal_score,
            "take_profit_rs": policy.take_profit_rs, "stop_loss_rs": policy.stop_loss_rs,
            "entry_start_minute": policy.entry_start_minute, "entry_deadline_minute": policy.entry_deadline_minute,
            "management_deadline_minute": policy.management_deadline_minute,
            "max_quote_age_seconds": policy.max_quote_age.total_seconds(), "max_leg_sync_seconds": policy.max_leg_sync.total_seconds(),
            "fee_per_leg_rs": policy.fee_per_leg_rs, "slippage_bps": policy.slippage_bps,
            "execution_delay_seconds": policy.execution_delay.total_seconds(),
            "execution_max_wait_seconds": policy.execution_max_wait.total_seconds(),
            "signal_expiry_seconds": policy.signal_expiry.total_seconds(),
            "cancellation_score": policy.cancellation_score, "exit_basis": policy.exit_basis,
            "direction": policy.direction, "invalidation_level": policy.invalidation_level, "target_level": policy.target_level,
            "max_public_age_seconds": policy.max_public_age.total_seconds(),
            "capital_limit_rs": policy.capital_limit_rs, "risk_limit_rs": policy.risk_limit_rs}
            | {"max_leg_spread_pct": policy.max_leg_spread_pct, "min_oi": policy.min_oi,
               "min_volume": policy.min_volume, "min_depth_units": policy.min_depth_units,
               "min_reward_risk": policy.min_reward_risk})


def _observation_payload(item: SpreadObservation) -> dict:
    return {"observed_at": _clock(item.observed_at, "observed_at").isoformat(),
            "received_at": _clock(item.received_at, "received_at").isoformat(),
            "signal_score": item.signal_score,
            "public_price": item.public_price,
            "public_received_at": item.public_received_at.isoformat() if item.public_received_at else None,
            "public_observed_at": item.public_observed_at.isoformat() if item.public_observed_at else None,
            "quotes": [asdict(quote) | {"observed_at": _clock(quote.observed_at, "quote.observed_at").isoformat(),
                                           "received_at": _clock(quote.received_at, "quote.received_at").isoformat()}
                       for quote in item.quotes]}


def _evidence(*, underlying: str, expiry: str, policy: ChronologicalPolicy, observations: list[SpreadObservation], outcome: dict) -> str:
    payload = {"format": "intraday_spread_chronological_v1", "underlying": underlying, "expiry": expiry,
               "policy": _policy_payload(policy), "observations": [_observation_payload(item) for item in observations],
               "outcome": outcome}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _execution_observation(rows: list[SpreadObservation], decision_index: int,
                           policy: ChronologicalPolicy) -> tuple[SpreadObservation | None, str | None]:
    """Return the first later executable packet for a delayed manual entry.

    The decision packet is evidence of a signal, not evidence of a fill after
    a manual delay.  A subsequent adverse/cancelling signal removes the
    standing decision before a fill can be assumed.
    """
    decision = rows[decision_index]
    if policy.execution_delay == timedelta(0):
        return decision, None
    eligible_at = decision.received_at + policy.execution_delay
    expiry_at = min(decision.received_at + policy.execution_max_wait,
                    decision.received_at + policy.signal_expiry)
    for item in rows[decision_index + 1:]:
        if item.received_at >= expiry_at:
            break
        if (policy.cancellation_score is not None
                and item.signal_score < policy.cancellation_score):
            return None, "signal_cancelled_before_delayed_execution"
        if item.received_at >= eligible_at:
            return item, None
    return None, "delayed_execution_packet_unavailable"


def replay_chronological_debit_spread(
    *, underlying: str, expiry: str, observations: Iterable[SpreadObservation], policy: ChronologicalPolicy,
    market_session_day: bool | None = None,
    public_observations: Iterable[PublicObservation] = (),
) -> ChronologicalReplay:
    """Select first signal, then first policy exit using receipt-ordered data.

    A malformed/no-fill candidate is recorded and scanning continues until the
    policy entry deadline.  Once a valid two-leg entry occurs it cannot be
    replaced.  Missing or unusable timely exits remain unresolved exposure.
    """
    rows = list(observations)
    public_rows = tuple(public_observations)
    _policy_payload(policy)
    if not rows:
        raise ReplayInputError("chronological replay requires observations")
    prior_received: datetime | None = None
    session_date = None
    for item in rows:
        if item.public_price is not None:
            if (not math.isfinite(item.public_price) or item.public_price <= 0
                    or item.public_received_at is None
                    or item.public_observed_at is None
                    or _clock(item.public_received_at, "public_received_at") > item.received_at
                    or _clock(item.public_observed_at, "public_observed_at") > item.public_received_at
                    or item.received_at - item.public_observed_at > policy.max_public_age):
                raise ReplayInputError("invalid or future public-price evidence")
        observed, received = _clock(item.observed_at, "observed_at"), _clock(item.received_at, "received_at")
        if observed > received or not math.isfinite(float(item.signal_score)):
            raise ReplayInputError("chronological observation timestamps or signal are invalid")
        if prior_received is not None and received <= prior_received:
            raise ReplayInputError("chronological observations must be strictly receipt-ordered")
        received_session_date = received.astimezone(IST).date()
        if session_date is None:
            session_date = received_session_date
        elif received_session_date != session_date:
            raise ReplayInputError("chronological replay cannot mix exchange sessions")
        prior_received = received
    prior_public = None
    for item in public_rows:
        observed = _clock(item.observed_at, "public observed_at")
        received = _clock(item.received_at, "public received_at")
        if (not math.isfinite(item.price) or item.price <= 0 or observed > received
                or received - observed > policy.max_public_age
                or received.astimezone(IST).date() != session_date
                or (prior_public is not None and received <= prior_public)):
            raise ReplayInputError("invalid or unordered independent public evidence")
        prior_public = received
    if public_rows and any(row.public_price is not None for row in rows):
        raise ReplayInputError("cannot mix embedded and independent public evidence")
    # Keep independent events in every evidence fingerprint, including no-fill.
    public_evidence = [asdict(item) for item in public_rows]
    def evidence(outcome):
        return _evidence(underlying=underlying, expiry=expiry, policy=policy, observations=rows,
                         outcome={**outcome, "independent_public_observations": public_evidence})
    attempted = 0
    rejected: list[str] = []
    entry: SpreadObservation | None = None
    entry_probe: ReplayResult | None = None
    for decision_index, item in enumerate(rows):
        if item.signal_score < policy.min_signal_score:
            continue
        attempted += 1
        execution, execution_reason = _execution_observation(rows, decision_index, policy)
        if execution is None:
            rejected.append(execution_reason or "execution_packet_unavailable")
            continue
        if policy.exit_basis == "PUBLIC_THESIS" and public_rows:
            from partner_thesis import public_thesis_event
            latest_public = next((event for event in reversed(public_rows)
                                  if event.received_at <= execution.received_at), None)
            if latest_public is not None and execution.received_at - latest_public.observed_at > policy.max_public_age:
                rejected.append("execution_public_evidence_stale")
                continue
            if any(public_thesis_event(policy.direction, event.price, policy.invalidation_level,
                                      policy.target_level)[0] is not None
                   for event in public_rows if item.received_at <= event.received_at <= execution.received_at):
                rejected.append("public_thesis_cancelled_before_execution")
                continue
        if policy.exit_basis == "PUBLIC_THESIS" and execution.public_price is not None:
            from partner_thesis import public_thesis_event
            if public_thesis_event(policy.direction, execution.public_price,
                                   policy.invalidation_level, policy.target_level)[0] is not None:
                rejected.append("public_thesis_cancelled_before_execution")
                continue
        probe = replay_intraday_debit_spread(
            underlying=underlying, expiry=expiry, entry_at=execution.received_at, entry_quotes=list(execution.quotes), exit_at=None,
            exit_quotes=[], fee_per_leg_rs=policy.fee_per_leg_rs, entry_start_minute=policy.entry_start_minute,
            entry_deadline_minute=policy.entry_deadline_minute, management_deadline_minute=policy.management_deadline_minute,
            max_quote_age=policy.max_quote_age, max_leg_sync=policy.max_leg_sync, slippage_bps=policy.slippage_bps,
            execution_delay=policy.execution_delay, market_session_day=market_session_day,
            max_leg_spread_pct=policy.max_leg_spread_pct, min_oi=policy.min_oi,
            min_volume=policy.min_volume, min_depth_units=policy.min_depth_units,
            min_reward_risk=policy.min_reward_risk,
        )
        if probe.accepted_entry:
            buy = next(quote for quote in execution.quotes if quote.side == "BUY")
            sell = next(quote for quote in execution.quotes if quote.side == "SELL")
            debit = (buy.ask - sell.bid) * buy.lot_size
            # Match the advisory profile's round-trip reserve convention, and
            # evaluate unrounded execution economics rather than original advice.
            gross_entry_notional = (buy.ask + sell.bid) * buy.lot_size
            all_in = debit + gross_entry_notional * policy.slippage_bps / 10_000 + 4 * policy.fee_per_leg_rs
            if policy.capital_limit_rs is not None and all_in > policy.capital_limit_rs:
                rejected.append("execution_profile_capital_limit_exceeded")
                continue
            if policy.risk_limit_rs is not None and all_in > policy.risk_limit_rs:
                rejected.append("execution_profile_risk_limit_exceeded")
                continue
            entry, entry_probe = execution, probe
            break
        rejected.append(probe.reason)
    if entry is None or entry_probe is None:
        outcome = {"state": "NO_FILL", "reason": "no_executable_policy_entry", "attempted_entries": attempted, "rejected": rejected}
        digest = evidence(outcome)
        result = ReplayResult("NO_FILL", "no_executable_policy_entry", None, None, None, None,
                              rows[0].received_at.isoformat(), None, digest)
        return ChronologicalReplay(result, "NO_FILL", attempted, tuple(rejected), None, None, len(rows), digest)
    entry_index = rows.index(entry)
    last_unresolved: ReplayResult | None = None
    pending_public_trigger = None
    public_exit_eligible_at = None
    public_exit_expires_at = None
    public_index = 0
    while public_index < len(public_rows) and public_rows[public_index].received_at <= entry.received_at:
        public_index += 1
    for item in rows[entry_index + 1:]:
        # Exit observations are already the first sequentially available books.
        # Never manufacture a later timestamp by adding a delay to an older
        # packet; a delayed exit needs a later real packet and remains
        # unresolved when it is absent.
        clock = item.received_at
        if policy.exit_basis == "PUBLIC_THESIS":
            from partner_thesis import public_thesis_event
            while public_index < len(public_rows) and public_rows[public_index].received_at <= clock:
                event = public_rows[public_index]
                public_index += 1
                if pending_public_trigger is None:
                    pending_public_trigger, _ = public_thesis_event(policy.direction, event.price,
                        policy.invalidation_level, policy.target_level)
                    if pending_public_trigger is not None:
                        public_exit_eligible_at = event.received_at + policy.execution_delay
                        public_exit_expires_at = (event.received_at + policy.execution_max_wait
                                                  if policy.execution_delay > timedelta(0) else None)
        if policy.exit_basis == "PUBLIC_THESIS" and pending_public_trigger is None:
            from partner_thesis import public_thesis_event
            if item.public_price is not None:
                pending_public_trigger, _ = public_thesis_event(policy.direction, item.public_price,
                                                                policy.invalidation_level, policy.target_level)
            if pending_public_trigger is not None:
                public_exit_eligible_at = clock + policy.execution_delay
                public_exit_expires_at = (clock + policy.execution_max_wait
                                          if policy.execution_delay > timedelta(0) else None)
        if pending_public_trigger is not None and clock < public_exit_eligible_at:
            continue
        if (pending_public_trigger is not None and public_exit_expires_at is not None
                and clock > public_exit_expires_at):
            last_unresolved = replace(entry_probe, state="UNRESOLVED",
                                      reason="delayed_exit_packet_unavailable")
            break
        candidate = replay_intraday_debit_spread(
            underlying=underlying, expiry=expiry, entry_at=entry.received_at,
            entry_quotes=list(entry.quotes), exit_at=clock, exit_quotes=list(item.quotes), fee_per_leg_rs=policy.fee_per_leg_rs,
            entry_start_minute=policy.entry_start_minute, entry_deadline_minute=policy.entry_deadline_minute,
            management_deadline_minute=policy.management_deadline_minute, max_quote_age=policy.max_quote_age,
            max_leg_sync=policy.max_leg_sync, slippage_bps=policy.slippage_bps, execution_delay=policy.execution_delay,
            market_session_day=market_session_day,
            max_leg_spread_pct=policy.max_leg_spread_pct, min_oi=policy.min_oi,
            min_volume=policy.min_volume, min_depth_units=policy.min_depth_units,
            min_reward_risk=policy.min_reward_risk,
        )
        if candidate.state != "CLOSED":
            last_unresolved = candidate
            continue
        if pending_public_trigger is not None:
            trigger = pending_public_trigger
        elif policy.exit_basis == "SPREAD_PNL" and candidate.net_pnl_rs is not None and candidate.net_pnl_rs >= policy.take_profit_rs:
            trigger = "take_profit"
        elif policy.exit_basis == "SPREAD_PNL" and candidate.net_pnl_rs is not None and candidate.net_pnl_rs <= -policy.stop_loss_rs:
            trigger = "stop_loss"
        elif clock.astimezone(IST) >= clock.astimezone(IST).replace(
                hour=policy.management_deadline_minute // 60,
                minute=policy.management_deadline_minute % 60, second=0, microsecond=0):
            trigger = "management_deadline"
        else:
            continue
        outcome = {"state": candidate.state, "reason": candidate.reason, "trigger": trigger,
                   "entry_at": entry.received_at.isoformat(), "exit_at": item.received_at.isoformat(), "attempted_entries": attempted,
                   "rejected": rejected}
        digest = evidence(outcome)
        final = replace(candidate, evidence_sha256=digest)
        return ChronologicalReplay(final, final.state, attempted, tuple(rejected), entry.received_at.isoformat(), trigger, len(rows), digest)
    # A final public breach without a later book is still unresolved exposure.
    if policy.exit_basis == "PUBLIC_THESIS" and pending_public_trigger is None:
        from partner_thesis import public_thesis_event
        for event in public_rows[public_index:]:
            pending_public_trigger, _ = public_thesis_event(policy.direction, event.price,
                policy.invalidation_level, policy.target_level)
            if pending_public_trigger is not None:
                break
    management_deadline = entry.received_at.astimezone(IST).replace(
        hour=policy.management_deadline_minute // 60,
        minute=policy.management_deadline_minute % 60, second=0, microsecond=0)
    if last_unresolved is not None:
        reason = "no_timely_executable_exit"
    elif rows[-1].received_at < management_deadline and pending_public_trigger is None:
        reason = "management_deadline_exit_evidence_missing"
    else:
        reason = "no_exit_observation_after_entry"
    outcome = {"state": "UNRESOLVED", "reason": reason, "entry_at": entry.received_at.isoformat(),
               "pending_public_trigger": pending_public_trigger,
               "attempted_entries": attempted, "rejected": rejected}
    digest = evidence(outcome)
    unresolved = replace(entry_probe, state="UNRESOLVED", reason=reason, evidence_sha256=digest)
    return ChronologicalReplay(unresolved, "UNRESOLVED", attempted, tuple(rejected), entry.received_at.isoformat(), pending_public_trigger, len(rows), digest)


def replay_cost_scenarios(*, underlying: str, expiry: str, observations: Iterable[SpreadObservation],
                          policy: ChronologicalPolicy, fee_multipliers: Iterable[float] = (1.0,),
                          additional_slippage_bps: Iterable[float] = (0.0,),
                          market_session_day: bool | None = None,
                          public_observations: Iterable[PublicObservation] = ()) -> dict:
    """Run fixed, declared execution-cost stresses without changing inputs.

    Every scenario receives the same receipt-ordered observations and manual
    delay.  No unresolved/no-fill result is removed merely because another
    cost scenario closes profitably.
    """
    rows = tuple(observations)
    public_rows = tuple(public_observations)
    def numeric(values, field):
        output = set()
        for value in values:
            if isinstance(value, bool):
                raise ReplayInputError(f"{field} must not contain booleans")
            try:
                output.add(float(value))
            except (TypeError, ValueError) as exc:
                raise ReplayInputError(f"{field} must contain numeric values") from exc
        return output
    multipliers = numeric(fee_multipliers, "fee_multipliers")
    additions = numeric(additional_slippage_bps, "additional_slippage_bps")
    coordinates = {(1.0, 0.0)} | {(multiplier, additional)
        for multiplier in multipliers for additional in additions}
    scenarios = []
    for multiplier, additional in sorted(coordinates):
        if not math.isfinite(multiplier) or multiplier < 1:
            raise ReplayInputError("fee stress multiplier must be finite and at least one")
        if not math.isfinite(additional) or additional < 0:
            raise ReplayInputError("additional slippage stress must be finite and non-negative")
        stressed = replace(policy, fee_per_leg_rs=policy.fee_per_leg_rs * multiplier,
                           slippage_bps=policy.slippage_bps + additional)
        replay = replay_chronological_debit_spread(underlying=underlying, expiry=expiry, observations=rows,
                                                    policy=stressed, market_session_day=market_session_day,
                                                    public_observations=public_rows)
        scenarios.append({"fee_multiplier": multiplier, "additional_slippage_bps": additional,
                          "state": replay.state, "reason": replay.result.reason,
                          "net_pnl_rs": replay.result.net_pnl_rs, "evidence_sha256": replay.evidence_sha256})
    deterministic = {"format": "intraday_spread_cost_sensitivity_v1", "underlying": underlying,
                     "expiry": expiry, "policy_id": policy.policy_id, "scenarios": scenarios,
                     "can_qualify": False, "can_place_orders": False}
    return {**deterministic, "evidence_sha256": hashlib.sha256(
        json.dumps(deterministic, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()}
