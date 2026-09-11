from partner_qualification_review import QualificationCriteria, build_qualification_review_package


def manifest():
    return {"evaluator": "partner_manual_intraday_full_policy_v1", "manifest_sha256": "a" * 64}


def heldout():
    return {"automatic_qualification": False, "evidence_sha256": "b" * 64,
            "groups": [{"underlying": "NIFTY", "policy_id": "partner-manual-intraday-v1",
                        "coverage": {"2026-09-12": "OBSERVED"}, "closed": 0,
                        "unresolved": 0, "unavailable": 0, "net_pnl_rs": 0.0}]}


def criteria():
    return QualificationCriteria("a" * 64, min_covered_sessions=2, min_closed_outcomes=3,
                                 max_unresolved_outcomes=0, max_drawdown_rs=-1000,
                                 stressed_fee_multiplier=1.25, stressed_slippage_bps=10)


def test_review_package_preserves_insufficient_evidence_and_all_readiness_states():
    report = build_qualification_review_package(policy_manifest=manifest(), criteria=criteria(), heldout_report=heldout(),
                                                readiness={"collection": "OBSERVED", "causal_research": "PARTIAL",
                                                           "outcome_coverage": "INSUFFICIENT", "telegram_routing": "UNVERIFIED"})
    assert report["automatic_qualification"] is False and report["can_send_advice"] is False
    assert report["per_index"][0]["review_state"] == "INSUFFICIENT_EVIDENCE"
    assert "closed_outcome_sample_insufficient" in report["per_index"][0]["blockers"]
    assert report["readiness"]["reviewed_qualification"] == "HUMAN_REVIEW_REQUIRED"


def test_review_rejects_changed_or_simplified_policy_manifest():
    bad = manifest() | {"evaluator": "orb_threshold_v1"}
    try:
        build_qualification_review_package(policy_manifest=bad, criteria=criteria(), heldout_report=heldout(), readiness={})
    except ValueError as exc:
        assert "complete deployed-policy" in str(exc)
    else:
        raise AssertionError("simplified evaluator was incorrectly accepted")
