from partner_qualification_review import (QualificationCriteria, build_qualification_review_package,
    freeze_qualification_criteria, _sha)
from dataclasses import replace
from datetime import datetime
import pytest
import pytz


def manifest():
    body = {"evaluator": "partner_manual_intraday_full_policy_v1", "underlying": "NIFTY",
            "policy_sha256": "f" * 64}
    return body | {"manifest_sha256": _sha(body)}


def heldout():
    body = {"automatic_qualification": False,
            "groups": [{"underlying": "NIFTY", "policy_id": "f" * 64,
                        "coverage": {"2026-09-12": "OBSERVED"}, "closed": 0,
                        "unresolved": 0, "unavailable": 0, "net_pnl_rs": 0.0}]}
    return body | {"evidence_sha256": _sha(body)}


def criteria():
    return QualificationCriteria(manifest()["policy_sha256"], min_covered_sessions=2, min_closed_outcomes=3,
                                 max_unresolved_outcomes=0, max_drawdown_rs=-1000,
                                 stressed_fee_multiplier=1.25, stressed_slippage_bps=10)


def test_review_package_preserves_insufficient_evidence_and_all_readiness_states():
    report = build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(), heldout_report=heldout(),
                                                readiness={"collection": "OBSERVED", "causal_research": "PARTIAL",
                                                           "outcome_coverage": "INSUFFICIENT", "telegram_routing": "UNVERIFIED"})
    assert report["automatic_qualification"] is False and report["can_send_advice"] is False
    assert report["per_index"][0]["review_state"] == "INSUFFICIENT_EVIDENCE"
    assert "closed_outcome_sample_insufficient" in report["per_index"][0]["blockers"]
    assert "cost_stress_evidence_missing" in report["per_index"][0]["blockers"]
    assert "predeclared_review_criteria_missing" in report["per_index"][0]["blockers"]
    assert report["readiness"]["reviewed_qualification"] == "HUMAN_REVIEW_REQUIRED"


def test_review_rejects_changed_or_simplified_policy_manifest():
    bad = manifest() | {"evaluator": "orb_threshold_v1"}
    try:
        build_qualification_review_package(policy_manifest=bad, criteria=criteria(), heldout_report=heldout(), readiness={})
    except ValueError as exc:
        assert "complete deployed-policy" in str(exc)
    else:
        raise AssertionError("simplified evaluator was incorrectly accepted")


@pytest.mark.parametrize("field,value", [("stressed_fee_multiplier", float("nan")),
    ("stressed_slippage_bps", float("inf")), ("min_closed_outcomes", 1.5), ("min_covered_sessions", True)])
def test_invalid_criteria_rejected(field, value):
    with pytest.raises(ValueError):
        replace(criteria(), **{field: value}).validate()


@pytest.mark.parametrize("target", ["manifest", "report"])
def test_tampered_artifact_rejected(target):
    policy, report = manifest(), heldout()
    if target == "manifest":
        policy["config"] = {"changed": True}
    else:
        report["groups"][0]["closed"] = 100
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        build_qualification_review_package(policy_manifest=policy, criteria=criteria(), heldout_report=report, readiness={})


@pytest.mark.parametrize("fault", ["index", "duplicate", "count", "no_fill", "coverage"])
def test_rehashed_but_invalid_group_rejected(fault):
    report = heldout()
    if fault == "index":
        report["groups"][0]["underlying"] = "SENSEX"
    elif fault == "duplicate":
        report["groups"].append(dict(report["groups"][0]))
    elif fault == "count":
        report["groups"][0]["closed"] = -1
    elif fault == "no_fill":
        report["groups"][0]["no_fill"] = True
    else:
        report["groups"][0]["coverage"] = []
    report["evidence_sha256"] = _sha({key: value for key, value in report.items() if key != "evidence_sha256"})
    with pytest.raises(ValueError):
        build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(), heldout_report=report, readiness={})


def economic_heldout(*, base_pnl=-1200.0, stressed_pnl=-1300.0, stress_slippage=10.0):
    artifact_body = {"format": "intraday_spread_cost_sensitivity_v1", "underlying": "NIFTY",
        "expiry": "2026-09-24", "policy_id": "f" * 64, "can_qualify": False,
        "can_place_orders": False, "scenarios": [{"fee_multiplier": 1.25,
            "additional_slippage_bps": stress_slippage, "state": "CLOSED",
            "net_pnl_rs": stressed_pnl}]}
    artifact = artifact_body | {"evidence_sha256": _sha(artifact_body)}
    group = {"underlying": "NIFTY", "policy_id": "f" * 64,
        "coverage": {"2026-09-12": "OBSERVED", "2026-09-13": "OBSERVED"},
        "closed": 1, "no_fill": 0, "unresolved": 0, "unavailable": 0,
        "net_pnl_rs": base_pnl, "max_sequential_drawdown_rs": base_pnl,
        "ordered_outcomes": [{"opportunity_id": "one", "state": "CLOSED",
            "entry_at": "2026-09-12T10:00:00+05:30", "exit_at": "2026-09-12T10:05:00+05:30",
            "net_pnl_rs": base_pnl, "evidence_sha256": "a" * 64, "session_date": "2026-09-12"}],
        "cost_sensitivity": [{"opportunity_id": "one", "source_report_sha256": "b" * 64,
            "source_manifest_sha256": manifest()["manifest_sha256"], "artifact": artifact}]}
    body = {"automatic_qualification": False, "evidence_contract": "VERIFIED_FULL_POLICY_REPORTS",
            "groups": [group]}
    return body | {"evidence_sha256": _sha(body)}


def test_review_evaluates_ordered_and_exact_stressed_economics():
    report = build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(),
        heldout_report=economic_heldout(), readiness={})
    row = report["per_index"][0]
    assert "maximum_drawdown_exceeds_limit" in row["blockers"]
    assert "stressed_maximum_drawdown_exceeds_limit" in row["blockers"]
    assert row["drawdown_state"] == row["cost_stress_state"] == "VERIFIED"
    assert row["stressed_net_pnl_rs"] == -1300

    missing = build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(),
        heldout_report=economic_heldout(stress_slippage=9), readiness={})
    assert missing["per_index"][0]["cost_stress_state"] == "MISSING"
    assert "declared_cost_stress_scenario_missing" in missing["per_index"][0]["blockers"]


def test_review_rejects_heldout_from_a_different_policy():
    report = economic_heldout()
    report["groups"][0]["policy_id"] = "e" * 64
    report["evidence_sha256"] = _sha({key: value for key, value in report.items() if key != "evidence_sha256"})
    with pytest.raises(ValueError, match="does not match"):
        build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(),
                                           heldout_report=report, readiness={})


def test_criteria_manifest_must_precede_and_exactly_bind_holdout_scope():
    frozen = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 9, 11, 12))
    coverage = [("NIFTY", "f" * 64, "2026-09-12")]
    result = freeze_qualification_criteria(criteria=criteria(), underlying="NIFTY",
        training_sessions=["2026-09-10"], holdout_sessions=["2026-09-12"],
        declared_coverage=coverage, frozen_at=frozen)
    assert len(result["criteria_manifest_sha256"]) == 64
    with pytest.raises(ValueError, match="before"):
        freeze_qualification_criteria(criteria=criteria(), underlying="NIFTY",
            training_sessions=["2026-09-10"], holdout_sessions=["2026-09-12"],
            declared_coverage=coverage, frozen_at=frozen.replace(day=12))
    with pytest.raises(ValueError, match="coverage"):
        freeze_qualification_criteria(criteria=criteria(), underlying="NIFTY",
            training_sessions=["2026-09-10"], holdout_sessions=["2026-09-12"],
            declared_coverage=[], frozen_at=frozen)


def test_stress_cannot_turn_unresolved_exposure_into_fabricated_profit():
    report = economic_heldout(base_pnl=10, stressed_pnl=9)
    group = report["groups"][0]
    group["unresolved"] = 1
    group["ordered_outcomes"].append({"opportunity_id": "two", "state": "UNRESOLVED",
        "entry_at": "2026-09-13T10:00:00+05:30", "exit_at": None, "net_pnl_rs": None,
        "evidence_sha256": "c" * 64, "session_date": "2026-09-13"})
    artifact_body = {"format": "intraday_spread_cost_sensitivity_v1", "underlying": "NIFTY",
        "expiry": "2026-09-24", "policy_id": "f" * 64, "can_qualify": False,
        "can_place_orders": False, "scenarios": [{"fee_multiplier": 1.25,
            "additional_slippage_bps": 10, "state": "CLOSED", "net_pnl_rs": 999999}]}
    group["cost_sensitivity"].append({"opportunity_id": "two", "source_report_sha256": "d" * 64,
        "source_manifest_sha256": manifest()["manifest_sha256"],
        "artifact": artifact_body | {"evidence_sha256": _sha(artifact_body)}})
    report["evidence_sha256"] = _sha({key: value for key, value in report.items() if key != "evidence_sha256"})
    result = build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(),
                                                heldout_report=report, readiness={})
    row = result["per_index"][0]
    assert row["cost_stress_state"] == "FAILED"
    assert "stressed_outcome_state_conflict" in row["blockers"]
    assert row["review_state"] == "INSUFFICIENT_EVIDENCE"


def test_nested_stress_scope_cannot_be_replaced_by_rehashing_outer_report():
    report = economic_heldout(base_pnl=10, stressed_pnl=9)
    report["groups"][0]["cost_sensitivity"][0]["artifact"]["underlying"] = "SENSEX"
    report["evidence_sha256"] = _sha({key: value for key, value in report.items() if key != "evidence_sha256"})
    result = build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(),
                                                heldout_report=report, readiness={})
    row = result["per_index"][0]
    assert row["cost_stress_state"] == "FAILED"
    assert "cost_stress_artifact_scope_or_fingerprint_invalid" in row["blockers"]
