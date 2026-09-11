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
    if (policy.execution_delay < timedelta(0) or policy.execution_max_wait <= timedelta(0)
            or policy.signal_expiry <= timedelta(0)
            or (policy.cancellation_score is not None and not math.isfinite(float(policy.cancellation_score)))):
        raise ReplayInputError("chronological execution policy bounds are invalid")
    return {"policy_id": policy.policy_id, "min_signal_score": policy.min_signal_score,
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
            "max_public_age_seconds": policy.max_public_age.total_seconds()}


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
        if item.received_at > expiry_at:
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
) -> ChronologicalReplay:
    """Select first signal, then first policy exit using receipt-ordered data.

    A malformed/no-fill candidate is recorded and scanning continues until the
    policy entry deadline.  Once a valid two-leg entry occurs it cannot be
    replaced.  Missing or unusable timely exits remain unresolved exposure.
    """
    rows = list(observations)
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
        probe = replay_intraday_debit_spread(
            underlying=underlying, expiry=expiry, entry_at=execution.received_at, entry_quotes=list(execution.quotes), exit_at=None,
            exit_quotes=[], fee_per_leg_rs=policy.fee_per_leg_rs, entry_start_minute=policy.entry_start_minute,
            entry_deadline_minute=policy.entry_deadline_minute, management_deadline_minute=policy.management_deadline_minute,
            max_quote_age=policy.max_quote_age, max_leg_sync=policy.max_leg_sync, slippage_bps=policy.slippage_bps,
            execution_delay=policy.execution_delay, market_session_day=market_session_day,
        )
        if probe.accepted_entry:
            entry, entry_probe = execution, probe
            break
        rejected.append(probe.reason)
    if entry is None or entry_probe is None:
        outcome = {"state": "NO_FILL", "reason": "no_executable_policy_entry", "attempted_entries": attempted, "rejected": rejected}
        digest = _evidence(underlying=underlying, expiry=expiry, policy=policy, observations=rows, outcome=outcome)
        result = ReplayResult("NO_FILL", "no_executable_policy_entry", None, None, None, None,
                              rows[0].received_at.isoformat(), None, digest)
        return ChronologicalReplay(result, "NO_FILL", attempted, tuple(rejected), None, None, len(rows), digest)
    entry_index = rows.index(entry)
    last_unresolved: ReplayResult | None = None
    pending_public_trigger = None
    public_exit_eligible_at = None
    for item in rows[entry_index + 1:]:
        # Exit observations are already the first sequentially available books.
        # Never manufacture a later timestamp by adding a delay to an older
        # packet; a delayed exit needs a later real packet and remains
        # unresolved when it is absent.
        clock = item.received_at
        if policy.exit_basis == "PUBLIC_THESIS" and pending_public_trigger is None:
            from partner_thesis import public_thesis_event
            if item.public_price is not None:
                pending_public_trigger, _ = public_thesis_event(policy.direction, item.public_price,
                                                                policy.invalidation_level, policy.target_level)
            if pending_public_trigger is not None:
                public_exit_eligible_at = clock + policy.execution_delay
        if pending_public_trigger is not None and clock < public_exit_eligible_at:
            continue
        candidate = replay_intraday_debit_spread(
            underlying=underlying, expiry=expiry, entry_at=entry.received_at,
            entry_quotes=list(entry.quotes), exit_at=clock, exit_quotes=list(item.quotes), fee_per_leg_rs=policy.fee_per_leg_rs,
            entry_start_minute=policy.entry_start_minute, entry_deadline_minute=policy.entry_deadline_minute,
            management_deadline_minute=policy.management_deadline_minute, max_quote_age=policy.max_quote_age,
            max_leg_sync=policy.max_leg_sync, slippage_bps=policy.slippage_bps, execution_delay=policy.execution_delay,
            market_session_day=market_session_day,
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
        elif clock.astimezone(IST).hour * 60 + clock.astimezone(IST).minute >= policy.management_deadline_minute:
            trigger = "management_deadline"
        else:
            continue
        outcome = {"state": candidate.state, "reason": candidate.reason, "trigger": trigger,
                   "entry_at": entry.received_at.isoformat(), "exit_at": item.received_at.isoformat(), "attempted_entries": attempted,
                   "rejected": rejected}
        digest = _evidence(underlying=underlying, expiry=expiry, policy=policy, observations=rows, outcome=outcome)
        final = replace(candidate, evidence_sha256=digest)
        return ChronologicalReplay(final, final.state, attempted, tuple(rejected), entry.received_at.isoformat(), trigger, len(rows), digest)
    reason = "no_timely_executable_exit" if last_unresolved is not None else "no_exit_observation_after_entry"
    outcome = {"state": "UNRESOLVED", "reason": reason, "entry_at": entry.received_at.isoformat(),
               "pending_public_trigger": pending_public_trigger,
               "attempted_entries": attempted, "rejected": rejected}
    digest = _evidence(underlying=underlying, expiry=expiry, policy=policy, observations=rows, outcome=outcome)
    unresolved = replace(entry_probe, state="UNRESOLVED", reason=reason, evidence_sha256=digest)
    return ChronologicalReplay(unresolved, "UNRESOLVED", attempted, tuple(rejected), entry.received_at.isoformat(), pending_public_trigger, len(rows), digest)


def replay_cost_scenarios(*, underlying: str, expiry: str, observations: Iterable[SpreadObservation],
                          policy: ChronologicalPolicy, fee_multipliers: Iterable[float] = (1.0,),
                          additional_slippage_bps: Iterable[float] = (0.0,),
                          market_session_day: bool | None = None) -> dict:
    """Run fixed, declared execution-cost stresses without changing inputs.

    Every scenario receives the same receipt-ordered observations and manual
    delay.  No unresolved/no-fill result is removed merely because another
    cost scenario closes profitably.
    """
    rows = tuple(observations)
    scenarios = []
    for multiplier in sorted(set(float(value) for value in fee_multipliers)):
        if not math.isfinite(multiplier) or multiplier < 1:
            raise ReplayInputError("fee stress multiplier must be finite and at least one")
        for additional in sorted(set(float(value) for value in additional_slippage_bps)):
            if not math.isfinite(additional) or additional < 0:
                raise ReplayInputError("additional slippage stress must be finite and non-negative")
            stressed = replace(policy, fee_per_leg_rs=policy.fee_per_leg_rs * multiplier,
                               slippage_bps=policy.slippage_bps + additional)
            replay = replay_chronological_debit_spread(underlying=underlying, expiry=expiry, observations=rows,
                                                        policy=stressed, market_session_day=market_session_day)
            scenarios.append({"fee_multiplier": multiplier, "additional_slippage_bps": additional,
                              "state": replay.state, "reason": replay.result.reason,
                              "net_pnl_rs": replay.result.net_pnl_rs, "evidence_sha256": replay.evidence_sha256})
    deterministic = {"format": "intraday_spread_cost_sensitivity_v1", "underlying": underlying,
                     "expiry": expiry, "policy_id": policy.policy_id, "scenarios": scenarios,
                     "can_qualify": False, "can_place_orders": False}
    return {**deterministic, "evidence_sha256": hashlib.sha256(
        json.dumps(deterministic, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()}
