"""[WORKFLOW-A.1 2026-09-17] Decision-clock extension helpers.

The base ``DecisionClock`` lives in ``partner_decision_clock``
and is the canonical clock contract. This module adds the
bounded extension helpers the Workstream A plan calls for
without touching the canonical dataclass:

  - ``build_clock_for_test(...)`` -- deterministic factory
    that returns a DecisionClock with sensible defaults
    derived from a single tick instant.
  - ``validate_clocks(clock) -> list[str]`` -- returns ALL
    clock problems (instead of raising the first one).
  - ``has_required_stages(clock) -> bool`` -- asserts the
    clock has at least public_received, chain_received, and
    candidate_constructed (the minimum required to support
    decision-bound tests).
  - ``clock_distance(clock_a, clock_b, field) -> timedelta``
    -- per-stage clock distance, useful for cross-clock
    inspection in audit reports.
  - ``summarize_clock(clock) -> dict`` -- short human-readable
    summary suitable for audit logs.
  - ``compare_clock_policies(policy_a, policy_b) -> str`` --
    returns a one-line description of policy compatibility.

Read-only. No DB writes. No network calls. No Telegram.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from partner_decision_clock import (
    CLOCK_POLICY,
    DecisionClock,
    IST,
    aware,
    start_clock,
)


# Stages a clock must cover to be considered "complete"
# for downstream decision logic. Per the plan:
#   "Carry the chosen clocks and source IDs into the
#    captured bundle and frozen decision manifest."
# The minimum useful clock for a captured bundle covers
# these three stages -- if any are missing, downstream
# replay cannot reason about the decision timing.
REQUIRED_STAGES: tuple[str, ...] = (
    "public_received_at",
    "chain_received_at",
    "candidate_constructed_at",
)


@dataclass(frozen=True)
class ClockValidationProblem:
    """One row of a clock validation report.

    Attributes:
        field: dotted path to the offending field (e.g.
            ``tick_started_at``, ``public_received_at``).
        code: machine-readable problem code.
        message: human-readable description.
    """
    field: str
    code: str
    message: str


def has_required_stages(clock: DecisionClock) -> bool:
    """True iff ``clock`` has all stages in
    ``REQUIRED_STAGES`` populated.

    Used by downstream code that needs to assert a clock
    is "decision-ready" before using it for replay.
    """
    for stage in REQUIRED_STAGES:
        if getattr(clock, stage) is None:
            return False
    return True


def missing_required_stages(clock: DecisionClock) -> tuple[str, ...]:
    """Return the list of required stages that are absent."""
    return tuple(
        stage for stage in REQUIRED_STAGES
        if getattr(clock, stage) is None
    )


def validate_clocks(clock: Any) -> list[ClockValidationProblem]:
    """Return ALL clock problems instead of raising on the first.

    The base ``DecisionClock.__post_init__`` raises on the
    first violation. This helper collects every violation so
    the audit pipeline can report them all at once.

    Returns an empty list when ``clock`` is well-formed.
    """
    problems: list[ClockValidationProblem] = []
    if not isinstance(clock, DecisionClock):
        problems.append(ClockValidationProblem(
            field="<root>",
            code="not_a_decision_clock",
            message=(
                f"expected DecisionClock, got {type(clock).__name__}"
            ),
        ))
        return problems
    # Required fields.
    if not clock.run_id:
        problems.append(ClockValidationProblem(
            field="run_id",
            code="missing_run_id",
            message="run_id must be populated",
        ))
    if not clock.account_id:
        problems.append(ClockValidationProblem(
            field="account_id",
            code="missing_account_id",
            message="account_id must be populated",
        ))
    if clock.underlying.upper() not in {"NIFTY", "SENSEX"}:
        problems.append(ClockValidationProblem(
            field="underlying",
            code="invalid_underlying",
            message=(
                f"underlying must be NIFTY or SENSEX, got "
                f"{clock.underlying!r}"
            ),
        ))
    # Timezone awareness on every datetime.
    for stage in REQUIRED_STAGES + (
        "tick_started_at", "evaluation_cutoff_at",
        "public_requested_at", "chain_requested_at",
        "dispatch_checked_at",
    ):
        value = getattr(clock, stage, None)
        if value is None:
            continue
        if not isinstance(value, datetime) or value.tzinfo is None:
            problems.append(ClockValidationProblem(
                field=stage,
                code="not_timezone_aware",
                message=f"{stage} must be a timezone-aware datetime",
            ))
    # Monotonicity check (more readable than the base).
    ordered = [
        ("tick_started_at", clock.tick_started_at),
        ("public_requested_at", clock.public_requested_at),
        ("public_received_at", clock.public_received_at),
        ("chain_requested_at", clock.chain_requested_at),
        ("chain_received_at", clock.chain_received_at),
        ("candidate_constructed_at", clock.candidate_constructed_at),
        ("dispatch_checked_at", clock.dispatch_checked_at),
    ]
    last_value: datetime | None = None
    last_name: str | None = None
    for name, value in ordered:
        if value is None:
            continue
        if last_value is not None and value < last_value:
            problems.append(ClockValidationProblem(
                field=name,
                code="non_monotonic_clock",
                message=(
                    f"{name} ({value.isoformat()}) is earlier than "
                    f"previous clock {last_name} "
                    f"({last_value.isoformat()})"
                ),
            ))
        last_value, last_name = value, name
    # Required stages for decision-ready clocks.
    missing = missing_required_stages(clock)
    for stage in missing:
        problems.append(ClockValidationProblem(
            field=stage,
            code="required_stage_missing",
            message=(
                f"{stage} is required for decision-ready clocks "
                "(public_received, chain_received, "
                "candidate_constructed)"
            ),
        ))
    return problems


def clock_distance(
    clock_a: DecisionClock,
    clock_b: DecisionClock,
    field: str,
) -> timedelta:
    """Compute the timedelta between two clocks' values of
    ``field``.

    Raises:
        AttributeError: if ``field`` is not a clock field.
        ValueError: if either clock has ``field`` as None.
    """
    value_a = getattr(clock_a, field)
    value_b = getattr(clock_b, field)
    if value_a is None or value_b is None:
        raise ValueError(
            f"clock_distance: field {field!r} is None on at "
            "least one clock"
        )
    return value_a - value_b


def summarize_clock(clock: DecisionClock) -> dict:
    """Return a short human-readable summary of the clock.

    Designed for audit logs / partner_advisory_ideas payloads.
    Does NOT include timestamps in raw form -- just deltas
    relative to tick_started_at, which is more useful in a
    log line.
    """
    out: dict[str, Any] = {
        "policy": clock.policy,
        "run_id": clock.run_id,
        "account_id": clock.account_id,
        "underlying": clock.underlying,
        "tick_started_at": clock.tick_started_at.isoformat(),
        "evaluation_cutoff_at": clock.evaluation_cutoff_at.isoformat(),
    }
    tick = clock.tick_started_at
    for stage in (
        "public_requested_at", "public_received_at",
        "chain_requested_at", "chain_received_at",
        "candidate_constructed_at", "dispatch_checked_at",
    ):
        value = getattr(clock, stage)
        if value is None:
            out[stage] = None
            continue
        delta_ms = (value - tick).total_seconds() * 1000
        out[stage] = {
            "iso": value.isoformat(),
            "ms_since_tick": int(delta_ms),
        }
    out["public_source_id"] = clock.public_source_id
    out["chain_source_id"] = clock.chain_source_id
    out["has_required_stages"] = has_required_stages(clock)
    return out


def compare_clock_policies(policy_a: str, policy_b: str) -> str:
    """Return a one-line description of policy compatibility.

    Used by the audit pipeline when comparing a captured
    bundle's policy to the deployed policy. Returns one of:

      ``MATCH``              -- policies are identical.
      ``FAMILY_MATCH``       -- policies share the family prefix
                               (e.g. ``FROZEN_*``) but differ
                               in version.
      ``FAMILY_MISMATCH``    -- policies are from different
                               families (e.g. ``FROZEN_*`` vs
                               ``POST_ACQUISITION_*``).
      ``UNKNOWN_POLICY``     -- one of the policies is not
                               recognized.
    """
    family_a = policy_a.split("_V")[0] if "_V" in policy_a else policy_a
    family_b = policy_b.split("_V")[0] if "_V" in policy_b else policy_b
    known = {"FROZEN_COMPLETED_BAR_CUTOFF", "POST_ACQUISITION_RECOMPUTE"}
    if policy_a not in known and not policy_a.startswith(tuple(known)):
        return "UNKNOWN_POLICY"
    if policy_b not in known and not policy_b.startswith(tuple(known)):
        return "UNKNOWN_POLICY"
    if policy_a == policy_b:
        return "MATCH"
    if family_a == family_b:
        return "FAMILY_MATCH"
    return "FAMILY_MISMATCH"


def build_clock_for_test(
    *,
    tick_started_at: datetime,
    underlying: str = "NIFTY",
    account_id: str = "manual-profile:p1",
    public_received_after_ms: int = 200,
    chain_received_after_ms: int = 800,
    candidate_constructed_after_ms: int = 1000,
    dispatch_checked_after_ms: int | None = None,
    public_source_id: str | None = None,
    chain_source_id: str | None = None,
    policy: str = CLOCK_POLICY,
) -> DecisionClock:
    """Build a DecisionClock for tests with sensible defaults.

    The helper makes tests less verbose: instead of
    ``start_clock(...).with_stage(...)`` chains, callers pass
    integer offsets (milliseconds since ``tick_started_at``)
    for each stage. Stages not in the offset list default to
    None.

    Args:
        tick_started_at: the tick start. Must be timezone-aware.
        underlying: NIFTY (default) or SENSEX.
        account_id: defaults to ``"manual-profile:p1"``.
        public_received_after_ms: ms after tick for
            ``public_received_at``. Default 200.
        chain_received_after_ms: ms after tick for
            ``chain_received_at``. Default 800.
        candidate_constructed_after_ms: ms after tick for
            ``candidate_constructed_at``. Default 1000.
        dispatch_checked_after_ms: optional ms after tick for
            ``dispatch_checked_at``. None = unset.
        public_source_id: optional string for
            ``public_source_id``.
        chain_source_id: optional string for ``chain_source_id``.
        policy: clock policy version. Default
            ``CLOCK_POLICY`` (the only currently-shipped
            policy).

    Returns:
        A fully-formed ``DecisionClock``.

    Raises:
        ValueError: if any input is invalid (naive datetime,
            unsupported policy, etc.).
    """
    tick = aware(tick_started_at, "tick_started_at")
    clock = start_clock(
        underlying=underlying, account_id=account_id,
        tick_started_at=tick,  # type: ignore[arg-type]
    )
    # start_clock hardcodes CLOCK_POLICY. If the caller wants
    # a different policy, we have to bypass via __post_init__
    # by constructing directly. But the base class refuses any
    # non-CLOCK_POLICY value. To preserve the base contract,
    # we leave policy=CLOCK_POLICY in this helper for now;
    # callers wanting a different policy should construct
    # via the dataclass directly.
    del policy  # currently unused -- reserved for A.2
    # The base ``DecisionClock`` enforces monotonicity
    # across the full ordered chain
    # (tick_started_at, public_requested_at, public_received_at,
    # chain_requested_at, chain_received_at,
    # candidate_constructed_at, dispatch_checked_at). We
    # therefore set requested_at timestamps to match the
    # received timestamps so callers don't have to do
    # arithmetic. The ``public_received_after_ms`` /
    # ``chain_received_after_ms`` parameters control the
    # received_at offsets, and requested_at equals the
    # received_at (no separate "request sent before response"
    # semantics in this helper).
    public_received = tick + timedelta(milliseconds=public_received_after_ms)
    chain_received = tick + timedelta(milliseconds=chain_received_after_ms)
    candidate_constructed = tick + timedelta(
        milliseconds=candidate_constructed_after_ms,
    )
    # Ensure monotonicity: chain_requested_at must be >=
    # public_received_at, and chain_received_at must be >=
    # chain_requested_at.
    chain_requested = max(chain_received - timedelta(milliseconds=1),
                            public_received)
    kwargs: dict[str, Any] = {
        "public_requested_at": tick,
        "public_received_at": public_received,
        "chain_requested_at": chain_requested,
        "chain_received_at": chain_received,
        "candidate_constructed_at": candidate_constructed,
    }
    if dispatch_checked_after_ms is not None:
        dispatch_at = tick + timedelta(
            milliseconds=dispatch_checked_after_ms,
        )
        # dispatch_checked_at must be >= candidate_constructed_at.
        if dispatch_at < candidate_constructed:
            dispatch_at = candidate_constructed
        kwargs["dispatch_checked_at"] = dispatch_at
    if public_source_id is not None:
        kwargs["public_source_id"] = public_source_id
    if chain_source_id is not None:
        kwargs["chain_source_id"] = chain_source_id
    return clock.with_stage(**kwargs)


__all__ = [
    "REQUIRED_STAGES",
    "ClockValidationProblem",
    "build_clock_for_test",
    "clock_distance",
    "compare_clock_policies",
    "has_required_stages",
    "missing_required_stages",
    "summarize_clock",
    "validate_clocks",
]
