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
    if not policy.policy_id.strip() or not all(math.isfinite(float(item)) for item in
                                               (policy.min_signal_score, policy.take_profit_rs, policy.stop_loss_rs,
                                                policy.fee_per_leg_rs, policy.slippage_bps)):
        raise ReplayInputError("chronological policy contains a non-finite value")
    if policy.take_profit_rs <= 0 or policy.stop_loss_rs <= 0 or policy.slippage_bps < 0:
        raise ReplayInputError("chronological policy thresholds are invalid")
    if policy.execution_delay < timedelta(0):
        raise ReplayInputError("execution_delay must be nonnegative")
    return {"policy_id": policy.policy_id, "min_signal_score": policy.min_signal_score,
            "take_profit_rs": policy.take_profit_rs, "stop_loss_rs": policy.stop_loss_rs,
            "entry_start_minute": policy.entry_start_minute, "entry_deadline_minute": policy.entry_deadline_minute,
            "management_deadline_minute": policy.management_deadline_minute,
            "max_quote_age_seconds": policy.max_quote_age.total_seconds(), "max_leg_sync_seconds": policy.max_leg_sync.total_seconds(),
            "fee_per_leg_rs": policy.fee_per_leg_rs, "slippage_bps": policy.slippage_bps,
            "execution_delay_seconds": policy.execution_delay.total_seconds()}


def _observation_payload(item: SpreadObservation) -> dict:
    return {"observed_at": _clock(item.observed_at, "observed_at").isoformat(),
            "received_at": _clock(item.received_at, "received_at").isoformat(),
            "signal_score": item.signal_score,
            "quotes": [asdict(quote) | {"observed_at": _clock(quote.observed_at, "quote.observed_at").isoformat(),
                                           "received_at": _clock(quote.received_at, "quote.received_at").isoformat()}
                       for quote in item.quotes]}


def _evidence(*, underlying: str, expiry: str, policy: ChronologicalPolicy, observations: list[SpreadObservation], outcome: dict) -> str:
    payload = {"format": "intraday_spread_chronological_v1", "underlying": underlying, "expiry": expiry,
               "policy": _policy_payload(policy), "observations": [_observation_payload(item) for item in observations],
               "outcome": outcome}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


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
    for item in rows:
        observed, received = _clock(item.observed_at, "observed_at"), _clock(item.received_at, "received_at")
        if observed > received or not math.isfinite(float(item.signal_score)):
            raise ReplayInputError("chronological observation timestamps or signal are invalid")
        if prior_received is not None and received <= prior_received:
            raise ReplayInputError("chronological observations must be strictly receipt-ordered")
        prior_received = received
    attempted = 0
    rejected: list[str] = []
    entry: SpreadObservation | None = None
    entry_probe: ReplayResult | None = None
    for item in rows:
        if item.signal_score < policy.min_signal_score:
            continue
        attempted += 1
        clock = item.received_at + policy.execution_delay
        probe = replay_intraday_debit_spread(
            underlying=underlying, expiry=expiry, entry_at=clock, entry_quotes=list(item.quotes), exit_at=None,
            exit_quotes=[], fee_per_leg_rs=policy.fee_per_leg_rs, entry_start_minute=policy.entry_start_minute,
            entry_deadline_minute=policy.entry_deadline_minute, management_deadline_minute=policy.management_deadline_minute,
            max_quote_age=policy.max_quote_age, max_leg_sync=policy.max_leg_sync, slippage_bps=policy.slippage_bps,
            execution_delay=policy.execution_delay, market_session_day=market_session_day,
        )
        if probe.state == "UNRESOLVED" and probe.reason == "exit_observation_missing":
            entry, entry_probe = item, probe
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
    for item in rows[entry_index + 1:]:
        clock = item.received_at + policy.execution_delay
        candidate = replay_intraday_debit_spread(
            underlying=underlying, expiry=expiry, entry_at=entry.received_at + policy.execution_delay,
            entry_quotes=list(entry.quotes), exit_at=clock, exit_quotes=list(item.quotes), fee_per_leg_rs=policy.fee_per_leg_rs,
            entry_start_minute=policy.entry_start_minute, entry_deadline_minute=policy.entry_deadline_minute,
            management_deadline_minute=policy.management_deadline_minute, max_quote_age=policy.max_quote_age,
            max_leg_sync=policy.max_leg_sync, slippage_bps=policy.slippage_bps, execution_delay=policy.execution_delay,
            market_session_day=market_session_day,
        )
        if candidate.state != "CLOSED":
            last_unresolved = candidate
            continue
        if candidate.net_pnl_rs is not None and candidate.net_pnl_rs >= policy.take_profit_rs:
            trigger = "take_profit"
        elif candidate.net_pnl_rs is not None and candidate.net_pnl_rs <= -policy.stop_loss_rs:
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
               "attempted_entries": attempted, "rejected": rejected}
    digest = _evidence(underlying=underlying, expiry=expiry, policy=policy, observations=rows, outcome=outcome)
    unresolved = replace(entry_probe, state="UNRESOLVED", reason=reason, evidence_sha256=digest)
    return ChronologicalReplay(unresolved, "UNRESOLVED", attempted, tuple(rejected), entry.received_at.isoformat(), None, len(rows), digest)
