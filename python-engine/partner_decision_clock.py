"""Explicit causal clocks for the partner intraday advisory pipeline.

The deployed policy freezes public-bar eligibility at tick start, while all
network response and candidate/dispatch clocks retain when work really became
available.  This module is pure and has no execution or delivery authority.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timedelta
from typing import Callable, Mapping
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
CLOCK_POLICY = "FROZEN_COMPLETED_BAR_CUTOFF_V1"


def aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(IST)


def source_identity(kind: str, underlying: str, token: int | None = None) -> str:
    suffix = "" if token is None else f":{int(token)}"
    return f"{kind.upper()}:{underlying.upper()}{suffix}"


@dataclass(frozen=True)
class DecisionClock:
    policy: str
    run_id: str
    account_id: str
    underlying: str
    tick_started_at: datetime
    evaluation_cutoff_at: datetime
    public_requested_at: datetime | None = None
    public_received_at: datetime | None = None
    public_source_id: str | None = None
    chain_requested_at: datetime | None = None
    chain_received_at: datetime | None = None
    chain_source_id: str | None = None
    candidate_constructed_at: datetime | None = None
    dispatch_checked_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.policy != CLOCK_POLICY:
            raise ValueError("unsupported decision clock policy")
        for field in (
            "tick_started_at", "evaluation_cutoff_at", "public_requested_at",
            "public_received_at", "chain_requested_at", "chain_received_at",
            "candidate_constructed_at", "dispatch_checked_at",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, aware(value, field))
        if self.evaluation_cutoff_at != self.tick_started_at:
            raise ValueError("frozen evaluation cutoff must equal tick start")
        ordered = [
            self.tick_started_at, self.public_requested_at, self.public_received_at,
            self.chain_requested_at, self.chain_received_at, self.candidate_constructed_at,
            self.dispatch_checked_at,
        ]
        present = [value for value in ordered if value is not None]
        if any(later < earlier for earlier, later in zip(present, present[1:])):
            raise ValueError("decision clocks must be monotonic")
        if not self.run_id or not self.account_id or self.underlying.upper() not in {"NIFTY", "SENSEX"}:
            raise ValueError("decision clock scope is incomplete")

    def with_stage(self, **values) -> "DecisionClock":
        return replace(self, **values)

    def payload(self) -> dict:
        value = asdict(self)
        for key, item in tuple(value.items()):
            if isinstance(item, datetime):
                value[key] = item.isoformat()
        return value


def start_clock(*, underlying: str, account_id: str, tick_started_at: datetime) -> DecisionClock:
    tick = aware(tick_started_at, "tick_started_at")
    scope = {
        "policy": CLOCK_POLICY, "account_id": account_id,
        "underlying": underlying.upper(), "tick_started_at": tick.isoformat(),
    }
    run_id = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return DecisionClock(CLOCK_POLICY, run_id, account_id, underlying.upper(), tick, tick)


def validate_clock_payload(value: Mapping[str, object]) -> DecisionClock:
    """Parse a retained clock and verify its deterministic run identity."""
    if not isinstance(value, Mapping):
        raise ValueError("decision clock payload must be an object")
    fields = {}
    for key in DecisionClock.__dataclass_fields__:
        item = value.get(key)
        if key.endswith("_at") and item is not None:
            item = datetime.fromisoformat(str(item))
        fields[key] = item
    clock = DecisionClock(**fields)
    expected = start_clock(
        underlying=clock.underlying, account_id=clock.account_id,
        tick_started_at=clock.tick_started_at,
    )
    if clock.run_id != expected.run_id:
        raise ValueError("decision clock run identity mismatch")
    return clock


def sampled(clock: Callable[[], datetime] | None = None) -> datetime:
    return aware(clock() if clock is not None else datetime.now(IST), "sampled clock")


def crossed_entry_boundary(decision_clock: DecisionClock, *, entry_end_minute: int) -> str | None:
    decision = decision_clock.candidate_constructed_at or decision_clock.chain_received_at
    if decision is None:
        return "candidate_clock_missing"
    if decision.date() != decision_clock.evaluation_cutoff_at.date():
        return "session_boundary_crossed_during_acquisition"
    deadline = datetime.combine(decision_clock.evaluation_cutoff_at.date(), time.min, IST) + timedelta(minutes=entry_end_minute)
    if decision > deadline:
        return "entry_deadline_crossed_during_acquisition"
    return None
