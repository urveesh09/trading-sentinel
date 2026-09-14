from dataclasses import replace
from datetime import datetime

import pytest
import pytz

from intraday_spread_chronological import ChronologicalReplay
from intraday_spread_holdout import HeldOutCase, build_heldout_comparison, heldout_case_from_full_policy_report
from intraday_spread_replay import ReplayResult


def replay(state="CLOSED", pnl=5.0, identity="a"):
    result = ReplayResult(state, "fixture", 1.0, 2.0, 1.0, pnl if state == "CLOSED" else None,
                          "2026-09-10T10:00:00+05:30", "2026-09-10T10:05:00+05:30", identity * 64)
    return ChronologicalReplay(result, state, 1, (), result.entry_at, "take_profit", 2, identity * 64)


def test_heldout_comparison_preserves_group_and_no_fill_coverage():
    report = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"], holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "policy-a", "2026-09-10"), ("SENSEX", "policy-b", "2026-09-10")], cases=[
            HeldOutCase("NIFTY", "policy-a", "2026-09-10", replay("CLOSED", 8, "a"), "one", "d" * 64),
            HeldOutCase("NIFTY", "policy-a", "2026-09-10", replay("NO_FILL", identity="b"), "two", "d" * 64),
            HeldOutCase("SENSEX", "policy-b", "2026-09-10", replay("UNRESOLVED", identity="c"), "three", "d" * 64),
        ])
    assert report["automatic_qualification"] is False
    assert report["groups"][0]["closed"] == 1
    assert report["groups"][0]["no_fill"] == 1
    assert report["groups"][1]["unresolved"] == 1


def test_heldout_comparison_rejects_overlap_and_duplicate_evidence():
    with pytest.raises(ValueError, match="non-overlapping"):
        build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-10"],
            holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=[])
    with pytest.raises(ValueError, match="duplicate"):
        build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-08"],
            holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10"), ("SENSEX", "x", "2026-09-10")],
            cases=[HeldOutCase("NIFTY", "x", "2026-09-10", replay(identity="a"), "one", "d" * 64),
                   HeldOutCase("SENSEX", "x", "2026-09-10", replay(identity="a"), "two", "d" * 64)])


def test_heldout_requires_chronological_split_and_keeps_unavailable_coverage():
    report = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=[])
    assert report["groups"][0]["coverage"] == {"2026-09-10": "UNAVAILABLE"}
    with pytest.raises(ValueError, match="precede"):
        build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-11"],
            holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=[])


def test_heldout_drawdown_uses_event_clock_not_caller_order():
    first = replay("CLOSED", 100, "a")
    second = replay("CLOSED", -80, "b")
    first = replace(first, result=replace(first.result, entry_at="2026-09-10T10:00:00+05:30"))
    second = replace(second, result=replace(second.result, entry_at="2026-09-10T10:01:00+05:30"))
    arguments = dict(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")])
    cases = [HeldOutCase("NIFTY", "x", "2026-09-10", second, "two", "d" * 64),
             HeldOutCase("NIFTY", "x", "2026-09-10", first, "one", "d" * 64)]
    report = build_heldout_comparison(**arguments, cases=cases)
    group = report["groups"][0]
    assert [row["opportunity_id"] for row in group["ordered_outcomes"]] == ["one", "two"]
    assert group["max_sequential_drawdown_rs"] == -80
    assert report == build_heldout_comparison(**arguments, cases=list(reversed(cases)))


def test_heldout_drawdown_follows_realisation_not_entry_order():
    loss_early = replay("CLOSED", -50, "a")
    gain = replay("CLOSED", 100, "b")
    loss_late = replay("CLOSED", -100, "c")
    loss_early = replace(loss_early, result=replace(loss_early.result,
        entry_at="2026-09-10T10:00:00+05:30", exit_at="2026-09-10T10:20:00+05:30"))
    gain = replace(gain, result=replace(gain.result,
        entry_at="2026-09-10T10:01:00+05:30", exit_at="2026-09-10T10:10:00+05:30"))
    loss_late = replace(loss_late, result=replace(loss_late.result,
        entry_at="2026-09-10T10:02:00+05:30", exit_at="2026-09-10T10:30:00+05:30"))
    cases = [HeldOutCase("NIFTY", "x", "2026-09-10", item, str(index), "d" * 64)
             for index, item in enumerate((loss_early, gain, loss_late))]
    report = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"], holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=cases)
    group = report["groups"][0]
    assert [row["net_pnl_rs"] for row in group["ordered_outcomes"]] == [100, -50, -100]
    assert group["max_sequential_drawdown_rs"] == -150


def test_full_policy_report_adapter_rejects_tampering_and_simplified_manifest():
    from dataclasses import asdict
    import hashlib
    import json
    from partner_qualification_review import _sha
    chronological = replay("CLOSED", 5, "a")
    manifest_body = {"evaluator": "partner_manual_intraday_full_policy_v1", "underlying": "NIFTY",
                     "decision_at": "2026-09-10T10:00:00+05:30", "policy_sha256": "f" * 64}
    manifest = manifest_body | {"manifest_sha256": _sha(manifest_body)}
    sensitivity_body = {"format": "intraday_spread_cost_sensitivity_v1", "underlying": "NIFTY",
        "expiry": "2026-09-24", "policy_id": "f" * 64,
        "scenarios": [{"fee_multiplier": 1.0, "additional_slippage_bps": 0.0,
                       "state": "CLOSED", "reason": "fixture", "net_pnl_rs": 5,
                       "evidence_sha256": "a" * 64}], "can_qualify": False, "can_place_orders": False}
    sensitivity = sensitivity_body | {"evidence_sha256": _sha(sensitivity_body)}
    body = {"format": "partner_full_policy_replay_v1", "decision_id": "decision-one",
            "manifest": manifest, "state": "CLOSED", "replay": asdict(chronological),
            "economics_contract": "FULL_POLICY_ECONOMICS_V1", "cost_sensitivity": sensitivity,
            "public_evidence_contract": "VERIFIED_ARCHIVED_FUTURE_SCOPE_V1"}
    report = body | {"evidence_sha256": hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()}
    case = heldout_case_from_full_policy_report(report, signal_artifact_sha256="d" * 64)
    assert case.opportunity_id == "decision-one" and case.replay.result.net_pnl_rs == 5
    report["state"] = "UNRESOLVED"
    with pytest.raises(ValueError, match="fingerprint"):
        heldout_case_from_full_policy_report(report, signal_artifact_sha256="d" * 64)
    report = body | {"evidence_sha256": hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()}
    report["manifest"] = dict(manifest, evaluator="orb_threshold_v1")
    report["evidence_sha256"] = hashlib.sha256(json.dumps({key: value for key, value in report.items()
        if key != "evidence_sha256"}, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    with pytest.raises(ValueError, match="deployed"):
        heldout_case_from_full_policy_report(report, signal_artifact_sha256="d" * 64)


def test_legacy_full_policy_report_remains_readable_but_cannot_claim_verified_economics():
    from dataclasses import asdict
    from partner_qualification_review import _sha
    chronological = replay("CLOSED", 5, "a")
    manifest_body = {"evaluator": "partner_manual_intraday_full_policy_v1", "underlying": "NIFTY",
                     "decision_at": "2026-09-10T10:00:00+05:30", "policy_sha256": "f" * 64}
    manifest = manifest_body | {"manifest_sha256": _sha(manifest_body)}
    body = {"format": "partner_full_policy_replay_v1", "decision_id": "legacy-one",
            "manifest": manifest, "state": "CLOSED", "replay": asdict(chronological)}
    report = body | {"evidence_sha256": _sha(body)}
    case = heldout_case_from_full_policy_report(report, signal_artifact_sha256="d" * 64)
    assert case.cost_sensitivity is None
    heldout = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="legacy",
        training_sessions=["2026-09-08"], holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "f" * 64, "2026-09-10")], cases=[case])
    assert heldout["evidence_contract"] == "LEGACY_CHRONOLOGICAL_CASES"
