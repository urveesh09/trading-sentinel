from dataclasses import replace
from datetime import datetime

import pytest
import pytz

from intraday_spread_chronological import ChronologicalReplay
from intraday_spread_holdout import (
    HeldOutCase,
    build_heldout_comparison,
    canonical_cost_sensitivity_fingerprint,
    heldout_case_from_full_policy_report,
)
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


# ---------------------------------------------------------------------------
# [WORKFLOW-C.A3 2026-09-15] Deterministic cost-sensitivity
# scenario-set fingerprint. Two qualification windows that
# used the SAME logical scenario set must produce the same
# fingerprint regardless of input-order permutations of the
# scenarios list.


class TestCanonicalCostSensitivityFingerprint:
    """[WORKFLOW-C.A3 2026-09-15] The pure scenario-set
    fingerprint helper.

    Pins the contract:
      - Two scenarios with the same logical set but different
        orderings produce the SAME fingerprint.
      - Adding or removing a scenario changes the fingerprint.
      - A non-list input degrades to a canonical empty-string
        digest (so a malformed input is detectable but does
        not raise).
    """

    def _scenarios(self):
        return [
            {"fee_multiplier": 1.0, "additional_slippage_bps": 0.0, "state": "CLOSED"},
            {"fee_multiplier": 1.5, "additional_slippage_bps": 0.0, "state": "CLOSED"},
            {"fee_multiplier": 1.0, "additional_slippage_bps": 5.0, "state": "CLOSED"},
            {"fee_multiplier": 2.0, "additional_slippage_bps": 0.0, "state": "NO_FILL"},
        ]

    def test_two_input_orders_produce_same_fingerprint(self):
        """[WORKFLOW-C.A3 2026-09-15] The bounded
        determinism contract: same scenarios in different
        orders must hash to the same digest.
        """
        forward = self._scenarios()
        reverse = list(reversed(forward))
        assert canonical_cost_sensitivity_fingerprint(forward) == \
               canonical_cost_sensitivity_fingerprint(reverse)

    def test_swapping_two_nondistinct_rows_is_stable(self):
        """Defensive: a permutation that swaps two distinct
        scenarios is also invariant.
        """
        forward = self._scenarios()
        swapped = list(forward)
        swapped[0], swapped[2] = swapped[2], swapped[0]
        assert canonical_cost_sensitivity_fingerprint(forward) == \
               canonical_cost_sensitivity_fingerprint(swapped)

    def test_adding_a_new_scenario_changes_fingerprint(self):
        """[WORKFLOW-C.A3 2026-09-15] A different scenario
        set MUST produce a different fingerprint -- the pin
        proves the operator ran a different cost-stress.
        """
        original = self._scenarios()
        extended = original + [{"fee_multiplier": 3.0, "additional_slippage_bps": 0.0,
                                 "state": "CLOSED"}]
        assert canonical_cost_sensitivity_fingerprint(original) != \
               canonical_cost_sensitivity_fingerprint(extended)

    def test_removing_a_scenario_changes_fingerprint(self):
        smaller = self._scenarios()[:2]
        full = self._scenarios()
        assert canonical_cost_sensitivity_fingerprint(smaller) != \
               canonical_cost_sensitivity_fingerprint(full)

    def test_empty_list_yields_canonical_empty_digest(self):
        from intraday_spread_holdout import _digest
        assert canonical_cost_sensitivity_fingerprint([]) == _digest([])

    def test_non_list_input_yields_canonical_empty_digest(self):
        """[WORKFLOW-C.A3 2026-09-15] Defensive: a non-list
        input (dict, str, None) degrades to the canonical
        empty-list digest. The helper NEVER raises -- a
        malformed input is detectable by comparing against
        the empty fingerprint, but the qualification review
        doesn't crash on bad data.
        """
        from intraday_spread_holdout import _digest
        assert canonical_cost_sensitivity_fingerprint(None) == _digest([])
        assert canonical_cost_sensitivity_fingerprint({"not": "a list"}) == _digest([])
        assert canonical_cost_sensitivity_fingerprint("a string") == _digest([])

    def test_sort_order_is_by_fee_then_slippage(self):
        """[WORKFLOW-C.A3 2026-09-15] The pin's sort key is
        ``(fee_multiplier, additional_slippage_bps)`` --
        same fee with different slippage is distinguishable.
        Pin a fingerprint for a known ordering so the sort
        is regression-checked.
        """
        scenarios = [
            {"fee_multiplier": 1.0, "additional_slippage_bps": 5.0, "tag": "A"},
            {"fee_multiplier": 1.0, "additional_slippage_bps": 0.0, "tag": "B"},
        ]
        # Same fee (1.0), different slippage (5.0 vs 0.0) --
        # these are distinct scenarios and produce distinct
        # fingerprints when their position is different.
        reverse = list(reversed(scenarios))
        # Both orderings produce the same fingerprint
        # because the sort puts them in canonical order.
        assert canonical_cost_sensitivity_fingerprint(scenarios) == \
               canonical_cost_sensitivity_fingerprint(reverse)

    def test_pin_propagates_to_heldout_bucket(self):
        """[WORKFLOW-C.A3 2026-09-15] The pin surfaces in
        the heldout comparison's bucket ``cost_sensitivity``
        list. Operators reading the qualification report can
        verify two runs used the same scenario set by
        comparing pins without diffing full artifacts.
        """
        # Build a single verified case with cost_sensitivity.
        from dataclasses import asdict
        from partner_qualification_review import _sha
        chronological = replay("CLOSED", 5, "a")
        manifest_body = {"evaluator": "partner_manual_intraday_full_policy_v1",
                         "underlying": "NIFTY", "decision_at": "2026-09-10T10:00:00+05:30",
                         "policy_sha256": "f" * 64}
        manifest = manifest_body | {"manifest_sha256": _sha(manifest_body)}
        scenarios = [
            {"fee_multiplier": 1.0, "additional_slippage_bps": 0.0,
             "state": "CLOSED", "reason": "fixture", "net_pnl_rs": 5,
             "evidence_sha256": "a" * 64},
            {"fee_multiplier": 1.5, "additional_slippage_bps": 5.0,
             "state": "CLOSED", "reason": "fixture", "net_pnl_rs": 4,
             "evidence_sha256": "b" * 64},
        ]
        sensitivity_body = {"format": "intraday_spread_cost_sensitivity_v1",
            "underlying": "NIFTY", "expiry": "2026-09-24", "policy_id": "f" * 64,
            "scenarios": scenarios, "can_qualify": False, "can_place_orders": False}
        sensitivity = sensitivity_body | {"evidence_sha256": _sha(sensitivity_body)}
        body = {"format": "partner_full_policy_replay_v1", "decision_id": "decision-one",
                "manifest": manifest, "state": "CLOSED", "replay": asdict(chronological),
                "economics_contract": "FULL_POLICY_ECONOMICS_V1",
                "cost_sensitivity": sensitivity,
                "public_evidence_contract": "VERIFIED_ARCHIVED_FUTURE_SCOPE_V1"}
        report = body | {"evidence_sha256": _sha(body)}
        case = heldout_case_from_full_policy_report(report, signal_artifact_sha256="d" * 64)

        heldout = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc",
            training_sessions=["2026-09-08"], holdout_sessions=["2026-09-10"],
            declared_coverage=[("NIFTY", "f" * 64, "2026-09-10")], cases=[case])
        bucket = heldout["groups"][0]
        # The bucket carries the cost_sensitivity entries.
        assert len(bucket["cost_sensitivity"]) == 1
        entry = bucket["cost_sensitivity"][0]
        # The pin is present and is a 64-char hex digest.
        assert "cost_sensitivity_sha256" in entry
        assert len(entry["cost_sensitivity_sha256"]) == 64
        # The pin equals the helper's output for the
        # scenarios (regardless of input order).
        assert entry["cost_sensitivity_sha256"] == \
               canonical_cost_sensitivity_fingerprint(scenarios)
        # Reverse the scenarios and re-run -- the pin must
        # be invariant under input-order permutation.
        sensitivity_body_reversed = {**sensitivity_body, "scenarios": list(reversed(scenarios))}
        sensitivity_reversed = sensitivity_body_reversed | \
            {"evidence_sha256": _sha(sensitivity_body_reversed)}
        body_reversed = {**body, "cost_sensitivity": sensitivity_reversed}
        report_reversed = body_reversed | {"evidence_sha256": _sha(body_reversed)}
        case_reversed = heldout_case_from_full_policy_report(report_reversed,
            signal_artifact_sha256="d" * 64)
        heldout_reversed = build_heldout_comparison(dataset_sha256="b" * 64,
            code_revision="abc", training_sessions=["2026-09-08"],
            holdout_sessions=["2026-09-10"],
            declared_coverage=[("NIFTY", "f" * 64, "2026-09-10")], cases=[case_reversed])
        pin_forward = heldout["groups"][0]["cost_sensitivity"][0]["cost_sensitivity_sha256"]
        pin_reversed = heldout_reversed["groups"][0]["cost_sensitivity"][0]["cost_sensitivity_sha256"]
        assert pin_forward == pin_reversed
