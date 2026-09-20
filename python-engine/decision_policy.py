"""[WORKFLOW-A.2 2026-09-17] Decision-policy enum + version.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Choose and document the deployed policy: either evaluate
> on a declared frozen completed-bar cutoff with later
> availability, or recompute at a genuine post-acquisition
> decision clock. Do not silently mix both.

The base ``partner_decision_clock.py`` hardcodes a single
policy ``FROZEN_COMPLETED_BAR_CUTOFF_V1``. This module
introduces the policy enum, lists the supported policies,
and exposes:

  - ``DecisionPolicy`` -- enum of supported policies.
  - ``SUPPORTED_POLICIES`` -- tuple of all supported
    policy versions.
  - ``policy_family(policy) -> str`` -- strip the
    ``_V<n>`` suffix to get the family.
  - ``policy_is_frozen(policy) -> bool`` -- True for
    FROZEN_COMPLETED_BAR_CUTOFF_V* policies.
  - ``policy_is_post_acquisition(policy) -> bool`` -- True
    for POST_ACQUISITION_RECOMPUTE_V* policies.
  - ``assert_policy_supports_clock(policy, clock)`` --
    assert that the clock satisfies the policy's invariants.
  - ``incompatible_policies(...)`` -- compare two policies
    and return whether they're compatible.

The base ``DecisionClock.__post_init__`` still rejects
non-FROZEN policies because extending it requires changing
the production constructor. We surface the supported
policies here so the audit pipeline and tests can reason
about them. Future work (A.3 capture-bundle binding) will
wire ``DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1``
through the captured bundle so operators can switch
policies with version invalidation of old captures.

Read-only. No DB writes. No network. No Telegram.
"""
from __future__ import annotations

import enum
from typing import Iterable

from partner_decision_clock import DecisionClock


class DecisionPolicy(str, enum.Enum):
    """The supported decision-clock policies.

    The two families correspond to the two strategies the
    Workstream A plan calls out:

    - ``FROZEN_COMPLETED_BAR_CUTOFF_V1``: the public-bar
      eligibility is frozen at tick start. The evaluation
      cutoff equals tick_started_at. Later arrivals
      (network fetch delays) do not change the
      bar-eligibility decision; they only change when
      the candidate becomes available.

    - ``POST_ACQUISITION_RECOMPUTE_V1``: the decision is
      recomputed at a genuine post-acquisition clock
      (``candidate_constructed_at``). The bar-eligibility
      decision reflects data the system actually had
      available, not data frozen at tick start.

    Operators must NOT mix the two policies in the same
    captured bundle -- the audit pipeline flags
    FAMILY_MISMATCH between policies in the same run.
    """
    FROZEN_COMPLETED_BAR_CUTOFF_V1 = "FROZEN_COMPLETED_BAR_CUTOFF_V1"
    POST_ACQUISITION_RECOMPUTE_V1 = "POST_ACQUISITION_RECOMPUTE_V1"


SUPPORTED_POLICIES: tuple[DecisionPolicy, ...] = tuple(DecisionPolicy)


def policy_family(policy: str) -> str:
    """Strip the ``_V<n>`` suffix to get the family name.

    >>> policy_family("FROZEN_COMPLETED_BAR_CUTOFF_V1")
    'FROZEN_COMPLETED_BAR_CUTOFF'
    >>> policy_family("POST_ACQUISITION_RECOMPUTE_V2")
    'POST_ACQUISITION_RECOMPUTE'
    """
    if "_V" in policy:
        return policy.split("_V")[0]
    return policy


def policy_is_frozen(policy: str) -> bool:
    """True iff ``policy`` is a FROZEN family policy."""
    return policy_family(policy) == "FROZEN_COMPLETED_BAR_CUTOFF"


def policy_is_post_acquisition(policy: str) -> bool:
    """True iff ``policy`` is a POST_ACQUISITION family policy."""
    return policy_family(policy) == "POST_ACQUISITION_RECOMPUTE"


def is_supported_policy(policy: str) -> bool:
    """True iff ``policy`` is in ``SUPPORTED_POLICIES``."""
    return policy in {p.value for p in DecisionPolicy}


def assert_policy_supports_clock(
    policy: str,
    clock: DecisionClock,
) -> None:
    """Assert that ``clock`` satisfies ``policy``'s invariants.

    Raises ``ValueError`` with a descriptive message when
    the clock violates the policy's contract.

    Per-policy invariants:

    - FROZEN_COMPLETED_BAR_CUTOFF_V1:
      ``evaluation_cutoff_at == tick_started_at``.
      The bar-eligibility decision is frozen at tick start.

    - POST_ACQUISITION_RECOMPUTE_V1:
      ``candidate_constructed_at > tick_started_at``.
      The decision must be at a genuine post-acquisition
      clock, not at tick start.

    Both policies require timezone-aware datetimes (the
    base ``DecisionClock.__post_init__`` enforces this;
    we double-check here for the audit pipeline that
    bypasses the constructor).
    """
    if not is_supported_policy(policy):
        raise ValueError(
            f"unsupported policy: {policy!r}; "
            f"supported policies: {[p.value for p in DecisionPolicy]}"
        )

    if policy_is_frozen(policy):
        if clock.evaluation_cutoff_at != clock.tick_started_at:
            raise ValueError(
                f"FROZEN policy {policy} requires "
                f"evaluation_cutoff_at == tick_started_at, "
                f"got evaluation_cutoff_at="
                f"{clock.evaluation_cutoff_at.isoformat()} "
                f"vs tick_started_at="
                f"{clock.tick_started_at.isoformat()}"
            )
    elif policy_is_post_acquisition(policy):
        if clock.candidate_constructed_at is None:
            raise ValueError(
                f"POST_ACQUISITION policy {policy} requires "
                f"candidate_constructed_at to be set"
            )
        if clock.candidate_constructed_at <= clock.tick_started_at:
            raise ValueError(
                f"POST_ACQUISITION policy {policy} requires "
                f"candidate_constructed_at > tick_started_at, "
                f"got candidate_constructed_at="
                f"{clock.candidate_constructed_at.isoformat()} "
                f"vs tick_started_at="
                f"{clock.tick_started_at.isoformat()}"
            )


def incompatible_policies(
    policy_a: str,
    policy_b: str,
) -> str:
    """Return a one-line description of policy compatibility.

    Returns one of:

    - ``MATCH`` -- policies are identical.
    - ``FAMILY_MATCH`` -- policies share the family but
      differ in version (V1 vs V2). Replays can be
      re-evaluated but operators must invalidate the
      prior qualifications.
    - ``FAMILY_MISMATCH`` -- policies are from different
      families. Replays cannot mix -- the captured bundle
      is incompatible.
    - ``UNKNOWN_POLICY`` -- one or both policies is not
      in ``SUPPORTED_POLICIES``.
    """
    if not is_supported_policy(policy_a):
        return "UNKNOWN_POLICY"
    if not is_supported_policy(policy_b):
        return "UNKNOWN_POLICY"
    if policy_a == policy_b:
        return "MATCH"
    if policy_family(policy_a) == policy_family(policy_b):
        return "FAMILY_MATCH"
    return "FAMILY_MISMATCH"


def start_clock_for_policy(
    *,
    policy: str,
    tick_started_at: "datetime",  # type: ignore[name-defined]
    underlying: str,
    account_id: str,
) -> DecisionClock:
    """Construct a ``DecisionClock`` for any supported policy.

    The base ``start_clock`` hardcodes ``CLOCK_POLICY``
    (FROZEN_COMPLETED_BAR_CUTOFF_V1). This helper supports
    both policies and constructs the clock with the
    policy-appropriate initial state.

    For FROZEN policies, ``evaluation_cutoff_at`` is set to
    ``tick_started_at`` (matching the FROZEN invariant).

    For POST_ACQUISITION policies, ``candidate_constructed_at``
    is set to ``tick_started_at + 1 microsecond`` so the
    initial clock satisfies the POST_ACQ invariant
    (``candidate_constructed_at > tick_started_at``). The
    caller is expected to overwrite this with the actual
    candidate construction time via ``with_stage``.
    """
    from datetime import timedelta as _td
    from partner_decision_clock import (  # type: ignore[import-not-found]
        aware, hashlib as _hashlib, json as _json,
    )

    if not is_supported_policy(policy):
        raise ValueError(
            f"unsupported policy: {policy!r}; supported: "
            f"{[p.value for p in DecisionPolicy]}"
        )
    tick = aware(tick_started_at, "tick_started_at")
    scope = {
        "policy": policy,
        "account_id": account_id,
        "underlying": underlying.upper(),
        "tick_started_at": tick.isoformat(),
    }
    run_id = _hashlib.sha256(
        _json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if policy_is_frozen(policy):
        # Frozen: evaluation_cutoff_at = tick_started_at.
        return DecisionClock(
            policy=policy, run_id=run_id, account_id=account_id,
            underlying=underlying.upper(),
            tick_started_at=tick, evaluation_cutoff_at=tick,
        )
    # POST_ACQUISITION: candidate_constructed_at = tick + 1us
    # so the POST_ACQ invariant passes; caller will overwrite.
    return DecisionClock(
        policy=policy, run_id=run_id, account_id=account_id,
        underlying=underlying.upper(),
        tick_started_at=tick, evaluation_cutoff_at=tick,
        candidate_constructed_at=tick + _td(microseconds=1),
    )


__all__ = [
    "DecisionPolicy",
    "SUPPORTED_POLICIES",
    "assert_policy_supports_clock",
    "incompatible_policies",
    "is_supported_policy",
    "policy_family",
    "policy_is_frozen",
    "policy_is_post_acquisition",
    "start_clock_for_policy",
]
