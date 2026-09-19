"""[WORKFLOW-A.2 2026-09-17] Tests for the decision-policy
enum + version.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Choose and document the deployed policy: either evaluate
> on a declared frozen completed-bar cutoff with later
> availability, or recompute at a genuine post-acquisition
> decision clock. Do not silently mix both.

The base ``partner_decision_clock`` previously hardcoded
``FROZEN_COMPLETED_BAR_CUTOFF_V1``. These tests pin the
new policy-aware behavior:

  - DecisionPolicy enum exposes both supported families.
  - Per-policy invariants (FROZEN requires eval_cutoff ==
    tick_start; POST_ACQ requires candidate > tick_start).
  - start_clock_for_policy constructs valid clocks for
    either policy.
  - incompatible_policies surfaces policy mismatch.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from decision_policy import (  # noqa: E402  -- import path
    SUPPORTED_POLICIES,
    DecisionPolicy,
    assert_policy_supports_clock,
    incompatible_policies,
    is_supported_policy,
    policy_family,
    policy_is_frozen,
    policy_is_post_acquisition,
    start_clock_for_policy,
)
from partner_decision_clock import (  # noqa: E402  -- import path
    DecisionClock,
)


IST = ZoneInfo("Asia/Kolkata")


def _tick() -> datetime:
    return datetime(2026, 9, 14, 9, 45, tzinfo=IST)


# -- 1. DecisionPolicy enum ------------------------------------


def test_decision_policy_has_two_members():
    """[WORKFLOW-A.2 2026-09-17] The plan calls out two
    strategies -- both must be supported."""
    members = list(DecisionPolicy)
    assert len(members) == 2


def test_decision_policy_includes_frozen():
    assert hasattr(DecisionPolicy, "FROZEN_COMPLETED_BAR_CUTOFF_V1")


def test_decision_policy_includes_post_acquisition():
    assert hasattr(DecisionPolicy, "POST_ACQUISITION_RECOMPUTE_V1")


def test_supported_policies_matches_enum():
    assert SUPPORTED_POLICIES == tuple(DecisionPolicy)


def test_supported_policies_values_are_strings():
    for p in SUPPORTED_POLICIES:
        assert isinstance(p.value, str)


# -- 2. policy_family -----------------------------------------


def test_policy_family_strips_version_suffix():
    """[WORKFLOW-A.2 2026-09-17] Family = policy minus the
    ``_V<n>`` suffix."""
    assert policy_family("FROZEN_COMPLETED_BAR_CUTOFF_V1") == "FROZEN_COMPLETED_BAR_CUTOFF"
    assert policy_family("POST_ACQUISITION_RECOMPUTE_V1") == "POST_ACQUISITION_RECOMPUTE"


def test_policy_family_unchanged_for_unversioned_string():
    assert policy_family("FROZEN_COMPLETED_BAR_CUTOFF") == "FROZEN_COMPLETED_BAR_CUTOFF"


# -- 3. is_supported_policy ----------------------------------


def test_is_supported_policy_true_for_enum_values():
    for p in SUPPORTED_POLICIES:
        assert is_supported_policy(p.value) is True


def test_is_supported_policy_false_for_unknown():
    assert is_supported_policy("GIBBERISH") is False
    assert is_supported_policy("FROZEN_COMPLETED_BAR_CUTOFF_V99") is False


# -- 4. policy_is_frozen / policy_is_post_acquisition ---------


def test_policy_is_frozen_true_for_frozen_family():
    assert policy_is_frozen("FROZEN_COMPLETED_BAR_CUTOFF_V1") is True


def test_policy_is_frozen_false_for_other_families():
    assert policy_is_frozen("POST_ACQUISITION_RECOMPUTE_V1") is False


def test_policy_is_post_acquisition_true_for_post_acq_family():
    assert policy_is_post_acquisition("POST_ACQUISITION_RECOMPUTE_V1") is True


def test_policy_is_post_acquisition_false_for_other_families():
    assert policy_is_post_acquisition("FROZEN_COMPLETED_BAR_CUTOFF_V1") is False


# -- 5. assert_policy_supports_clock --------------------------


def test_frozen_policy_accepts_clock_with_eval_cutoff_equal_to_tick():
    clock = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    assert_policy_supports_clock(
        DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value, clock,
    )  # should not raise


def test_frozen_policy_rejects_clock_with_eval_cutoff_after_tick():
    """[WORKFLOW-A.2 2026-09-17] A FROZEN-policy clock with
    ``evaluation_cutoff_at`` != ``tick_started_at`` must be
    rejected. The check fires either at ``with_stage``
    (which re-runs ``__post_init__``) or at
    ``assert_policy_supports_clock``."""
    clock = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    with pytest.raises(ValueError, match="FROZEN policy"):
        clock.with_stage(evaluation_cutoff_at=_tick() + timedelta(minutes=5))


def test_post_acquisition_policy_accepts_clock_with_candidate_after_tick():
    clock = start_clock_for_policy(
        policy=DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    ).with_stage(candidate_constructed_at=_tick() + timedelta(seconds=2))
    assert_policy_supports_clock(
        DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value, clock,
    )  # should not raise


def test_post_acquisition_policy_rejects_clock_without_candidate():
    """[WORKFLOW-A.2 2026-09-17] POST_ACQ policy requires
    candidate_constructed_at to be set."""
    clock = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    ).with_stage(candidate_constructed_at=None)
    with pytest.raises(ValueError, match="candidate_constructed_at to be set"):
        assert_policy_supports_clock(
            DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value, clock,
        )


def test_post_acquisition_policy_rejects_clock_with_candidate_equal_to_tick():
    clock = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    ).with_stage(candidate_constructed_at=_tick())  # equal to tick, not > tick
    with pytest.raises(ValueError, match="candidate_constructed_at > tick_started_at"):
        assert_policy_supports_clock(
            DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value, clock,
        )


def test_assert_policy_supports_clock_rejects_unknown_policy():
    clock = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    with pytest.raises(ValueError, match="unsupported policy"):
        assert_policy_supports_clock("GIBBERISH", clock)


# -- 6. start_clock_for_policy -------------------------------


def test_start_clock_for_policy_frozen_constructs_decision_clock():
    clock = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    assert isinstance(clock, DecisionClock)
    assert clock.policy == "FROZEN_COMPLETED_BAR_CUTOFF_V1"
    assert clock.evaluation_cutoff_at == clock.tick_started_at


def test_start_clock_for_policy_post_acquisition_constructs_decision_clock():
    clock = start_clock_for_policy(
        policy=DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value,
        tick_started_at=_tick(), underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    assert isinstance(clock, DecisionClock)
    assert clock.policy == "POST_ACQUISITION_RECOMPUTE_V1"
    # POST_ACQ initial state has candidate = tick + 1us
    # to satisfy the invariant.
    assert clock.candidate_constructed_at > clock.tick_started_at


def test_start_clock_for_policy_rejects_unknown_policy():
    with pytest.raises(ValueError, match="unsupported policy"):
        start_clock_for_policy(
            policy="GIBBERISH",
            tick_started_at=_tick(), underlying="NIFTY",
            account_id="manual-profile:p1",
        )


def test_start_clock_for_policy_different_policies_get_different_run_ids():
    """[WORKFLOW-A.2 2026-09-17] Same tick + underlying +
    account but different policies = different run_ids
    (the policy is part of the run identity)."""
    tick = _tick()
    a = start_clock_for_policy(
        policy=DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        tick_started_at=tick, underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    b = start_clock_for_policy(
        policy=DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value,
        tick_started_at=tick, underlying="NIFTY",
        account_id="manual-profile:p1",
    )
    assert a.run_id != b.run_id


# -- 7. incompatible_policies --------------------------------


def test_incompatible_policies_match_for_identical():
    assert incompatible_policies(
        DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
    ) == "MATCH"


def test_incompatible_policies_family_mismatch_for_diff_families():
    assert incompatible_policies(
        DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value,
    ) == "FAMILY_MISMATCH"


def test_incompatible_policies_unknown_for_unrecognized_string():
    assert incompatible_policies(
        DecisionPolicy.FROZEN_COMPLETED_BAR_CUTOFF_V1.value,
        "GIBBERISH",
    ) == "UNKNOWN_POLICY"
    assert incompatible_policies(
        "GIBBERISH",
        DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value,
    ) == "UNKNOWN_POLICY"
