"""[WORKFLOW-C.B1 2026-09-15] Tests for the held-out
evidence adequacy diagnostic.

Per the 2026-09-15 production deep audit B-1:
> 6. **Adequate genuine held-out evidence.** Need real production
> sessions with non-tampered captures.

The bounded dev-side diagnostic:
- inspects a held-out comparison report
- returns ADEQUATE / INADEQUATE with rationale
- does NOT collect sessions (operator must run J.3 capture review)

These tests pin the diagnostic's contract. They use synthetic
held-out reports (built via the existing build_heldout_comparison +
HeldOutCase helpers) so they don't require /data/cache.db.
"""
from __future__ import annotations

import os
import sys

import pytest


HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from intraday_spread_chronological import ChronologicalReplay  # noqa: E402
from intraday_spread_holdout import (  # noqa: E402
    HeldOutCase,
    _digest,
    build_heldout_comparison,
)
from intraday_spread_holdout_adequacy import (  # noqa: E402
    AdequacyThresholds,
    HeldOutAdequacy,
    evaluate_heldout_adequacy,
    format_adequacy,
)
from intraday_spread_replay import ReplayResult  # noqa: E402


def _replay(state="CLOSED", pnl=5.0, identity="a"):
    """Build a synthetic ChronologicalReplay for fixture use."""
    result = ReplayResult(
        state, "fixture", 1.0, 2.0, 1.0,
        pnl if state == "CLOSED" else None,
        "2026-09-10T10:00:00+05:30",
        "2026-09-10T10:05:00+05:30",
        identity * 64,
    )
    return ChronologicalReplay(
        result, state, 1, (), result.entry_at, "take_profit", 2, identity * 64,
    )


def _cost_sensitivity(opportunity_id: str = "one", underlying: str = "NIFTY",
                      policy_id: str = "policy-a", replay_identity: str = "a",
                      replay_state: str = "CLOSED", replay_pnl: float = 5.0):
    """Build a valid cost-sensitivity dict that passes the
    build_heldout_comparison fingerprint / scope / format
    / baseline-match checks. Format follows the canonical
    schema from ``intraday_spread_cost_sensitivity_v1``.

    The baseline scenario's ``evidence_sha256`` MUST match
    the chronological replay's ``evidence_sha256`` -- both
    are ``replay_identity * 64``. The baseline scenario's
    ``state`` / ``reason`` / ``net_pnl_rs`` MUST also match
    the replay's fields exactly.
    """
    # Match the replay helper: identity * 64.
    scenario_evidence = replay_identity * 64
    body = {
        "format": "intraday_spread_cost_sensitivity_v1",
        "underlying": underlying,
        "expiry": "2026-09-24",
        "policy_id": policy_id,
        "scenarios": [
            {
                "fee_multiplier": 1.0,
                "additional_slippage_bps": 0.0,
                "state": replay_state,
                "reason": "fixture",
                "net_pnl_rs": replay_pnl if replay_state == "CLOSED" else None,
                "evidence_sha256": scenario_evidence,
            }
        ],
        "can_qualify": False,
        "can_place_orders": False,
    }
    body["evidence_sha256"] = _digest(body)
    return body


def _adequate_report():
    """Build a held-out report with 1 CLOSED + 1 UNRESOLVED
    case across two groups. Per the plan doc's acceptance
    criterion, this is the minimum for ADEQUATE.
    """
    return build_heldout_comparison(
        dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"],
        declared_coverage=[
            ("NIFTY", "policy-a", "2026-09-10"),
            ("SENSEX", "policy-b", "2026-09-10"),
        ],
        cases=[
            HeldOutCase(
                "NIFTY", "policy-a", "2026-09-10",
                _replay("CLOSED", pnl=8.0, identity="a"),
                "one", "d" * 64,
                cost_sensitivity=_cost_sensitivity(
                    "one", replay_identity="a",
                    replay_state="CLOSED", replay_pnl=8.0,
                ),
            ),
            HeldOutCase(
                "SENSEX", "policy-b", "2026-09-10",
                _replay("UNRESOLVED", identity="c"),
                "three", "d" * 64,
                cost_sensitivity=_cost_sensitivity(
                    "three", underlying="SENSEX", policy_id="policy-b",
                    replay_identity="c", replay_state="UNRESOLVED",
                ),
            ),
        ],
    )


# ─── Adequate case ──────────────────────────────────────────


def test_adequate_report_with_minimum_thresholds():
    """Plan doc acceptance criterion: 1 CLOSED + 1 UNRESOLVED
    case across held-out groups is ADEQUATE.
    """
    adequacy = evaluate_heldout_adequacy(_adequate_report())
    assert adequacy.verdict == "ADEQUATE"
    assert adequacy.total_closed == 1
    assert adequacy.total_unresolved == 1
    assert adequacy.unmet_thresholds == ()


def test_adequate_diagnostic_preserves_thresholds():
    """The diagnostic carries the applied thresholds for
    auditability -- an operator can see what minimums were
    checked.
    """
    report = _adequate_report()
    adequacy = evaluate_heldout_adequacy(report)
    assert isinstance(adequacy.thresholds, AdequacyThresholds)
    assert adequacy.thresholds.min_closed == 1
    assert adequacy.thresholds.min_unresolved == 1


def test_adequate_diagnostic_per_group_counts():
    """The diagnostic surfaces per-group breakdown so
    operators can see which underlying/policy contributed
    each count.
    """
    adequacy = evaluate_heldout_adequacy(_adequate_report())
    assert len(adequacy.per_group_counts) == 2
    by_underlying = {row["underlying"]: row for row in adequacy.per_group_counts}
    assert by_underlying["NIFTY"]["closed"] == 1
    assert by_underlying["SENSEX"]["unresolved"] == 1


def test_adequate_diagnostic_format():
    """The format helper produces a human-readable summary
    with the verdict, totals, per-group breakdown, and any
    unmet thresholds.
    """
    adequacy = evaluate_heldout_adequacy(_adequate_report())
    text = format_adequacy(adequacy)
    assert "Verdict: ADEQUATE" in text
    assert "Total closed:    1" in text
    assert "Total unresolved:1" in text
    assert "NIFTY" in text
    assert "SENSEX" in text


# ─── Inadequate cases ──────────────────────────────────────


def test_inadequate_when_no_closed():
    """A report with 0 CLOSED cases is INADEQUATE per the
    plan doc's "one finite costed close" criterion.
    """
    report = build_heldout_comparison(
        dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "policy-a", "2026-09-10")],
        cases=[
            HeldOutCase(
                "NIFTY", "policy-a", "2026-09-10",
                _replay("UNRESOLVED", identity="a"),
                "one", "d" * 64,
                cost_sensitivity=_cost_sensitivity(
                    "one", replay_identity="a", replay_state="UNRESOLVED",
                ),
            ),
        ],
    )
    adequacy = evaluate_heldout_adequacy(report)
    assert adequacy.verdict == "INADEQUATE"
    assert any("closed=0 < min_closed=1" in t for t in adequacy.unmet_thresholds)


def test_inadequate_when_no_unresolved():
    """A report with 0 UNRESOLVED cases is INADEQUATE per the
    plan doc's "one unresolved outcome" criterion.
    """
    report = build_heldout_comparison(
        dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "policy-a", "2026-09-10")],
        cases=[
            HeldOutCase(
                "NIFTY", "policy-a", "2026-09-10",
                _replay("CLOSED", pnl=5.0, identity="a"),
                "one", "d" * 64,
                cost_sensitivity=_cost_sensitivity(
                    "one", replay_identity="a",
                    replay_state="CLOSED", replay_pnl=5.0,
                ),
            ),
        ],
    )
    adequacy = evaluate_heldout_adequacy(report)
    assert adequacy.verdict == "INADEQUATE"
    assert any("unresolved=0" in t for t in adequacy.unmet_thresholds)


def test_inadequate_when_no_evaluated():
    """A report with 0 evaluated cases (empty case list) is
    INADEQUATE -- the diagnostic must not return ADEQUATE
    just because no thresholds are violated.
    """
    report = build_heldout_comparison(
        dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "policy-a", "2026-09-10")],
        cases=[],
    )
    adequacy = evaluate_heldout_adequacy(report)
    assert adequacy.verdict == "INADEQUATE"
    assert any("evaluated=0" in t for t in adequacy.unmet_thresholds)


def test_inadequate_when_no_cost_sensitivity():
    """[WORKFLOW-C.B1] If the report has CLOSED + UNRESOLVED
    but NO group has cost_sensitivity evidence attached,
    the diagnostic flags "no verified full-policy cost
    evidence" -- the operator must re-run with full-policy
    reports to satisfy this constraint.
    """
    report = build_heldout_comparison(
        dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"],
        declared_coverage=[
            ("NIFTY", "policy-a", "2026-09-10"),
            ("SENSEX", "policy-b", "2026-09-10"),
        ],
        cases=[
            HeldOutCase(
                "NIFTY", "policy-a", "2026-09-10",
                _replay("CLOSED", pnl=8.0, identity="a"),
                "one", "d" * 64,
                cost_sensitivity=None,
            ),
            HeldOutCase(
                "SENSEX", "policy-b", "2026-09-10",
                _replay("UNRESOLVED", identity="c"),
                "three", "d" * 64,
                cost_sensitivity=None,
            ),
        ],
    )
    adequacy = evaluate_heldout_adequacy(report)
    assert adequacy.verdict == "INADEQUATE"
    assert any(
        "full-policy cost evidence" in t for t in adequacy.unmet_thresholds
    )


# ─── Threshold overrides ──────────────────────────────────


def test_threshold_overrides_change_verdict():
    """Operators can tighten or relax the minimum thresholds.
    Tighter thresholds flip an ADEQUATE report to INADEQUATE.
    """
    report = _adequate_report()
    # Default thresholds: ADEQUATE
    assert evaluate_heldout_adequacy(report).verdict == "ADEQUATE"
    # Tighten: require 2 closed. INADEQUATE.
    tighter = AdequacyThresholds(min_closed=2, min_unresolved=1)
    assert evaluate_heldout_adequacy(report, thresholds=tighter).verdict == "INADEQUATE"


def test_relaxed_thresholds_allow_inadequate_report():
    """Operators can relax to 0 closed / 0 unresolved for an
    exploratory run -- but ``evaluated=0`` still flags as
    INADEQUATE (cannot have ADEQUATE with no opportunities).
    """
    report = build_heldout_comparison(
        dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "policy-a", "2026-09-10")],
        cases=[
            HeldOutCase(
                "NIFTY", "policy-a", "2026-09-10",
                _replay("NO_FILL", identity="a"),
                "one", "d" * 64,
                cost_sensitivity=_cost_sensitivity(
                    "one", replay_identity="a", replay_state="NO_FILL",
                ),
            ),
        ],
    )
    relaxed = AdequacyThresholds(
        min_closed=0, min_unresolved=0, min_no_fill=1,
        require_full_policy_evidence=True,
    )
    adequacy = evaluate_heldout_adequacy(report, thresholds=relaxed)
    assert adequacy.verdict == "ADEQUATE"


# ─── Malformed report ──────────────────────────────────────


def test_invalid_report_missing_groups_field():
    """Defensive: a report without a ``groups`` field is
    malformed -- raises ValueError rather than silently
    returning INADEQUATE.
    """
    with pytest.raises(ValueError, match="groups"):
        evaluate_heldout_adequacy({})


def test_invalid_report_groups_not_a_list():
    """Defensive: ``groups`` must be a list. A dict raises.
    """
    with pytest.raises(ValueError, match="list"):
        evaluate_heldout_adequacy({"groups": {"not_a_list": True}})


def test_invalid_report_groups_with_non_mapping_bucket():
    """Defensive: each group must be a Mapping. Non-mapping
    entries are skipped (not raised) so the diagnostic is
    resilient to legacy or partial reports.
    """
    report = {
        "groups": [
            {"underlying": "NIFTY", "policy_id": "p", "closed": 1,
             "no_fill": 0, "unresolved": 1, "evaluated": 2, "cost_sensitivity": []},
            "not_a_mapping",
        ]
    }
    adequacy = evaluate_heldout_adequacy(report)
    # The valid group contributes 1 closed + 1 unresolved but
    # no cost_sensitivity -- still INADEQUATE due to cost
    # evidence requirement.
    assert adequacy.verdict == "INADEQUATE"
