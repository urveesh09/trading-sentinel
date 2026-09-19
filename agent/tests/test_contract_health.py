"""[WORKFLOW-I.4.E 2026-09-14] Bounded contract-health tests.

The 5 bounded invariants from ``agent/contract_health.py`` each get:

    - happy-path test (well-formed input -> passed=True)
    - negative test (the exact violation -> passed=False, correct
      violation string in the report)
    - None-input test (input not inspected -> passed=True, observed
      says "not inspected")

Plus aggregate tests on ``evaluate_contract()`` and ``ContractReport``
and the CLI (``agent/tools/contract_health_check.py``).
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

import pytest


# ---------------------------------------------------------------------------
# Lightweight test stand-ins for ClassificationResult / Review
# (avoid importing the real modules so the tests run in isolation)


@dataclass(frozen=True)
class FakeClassification:
    """Stand-in for ``agent.news_classifier.ClassificationResult``."""

    category: Any
    confidence: float
    rationale: str = "synthetic"


class FakeReview:
    """Stand-in for ``agent.advisory.Review``.

    Deliberately NOT a dataclass and NOT slotted: the contract-health
    tests need to inject forbidden authority fields (e.g.
    ``can_place_orders=True``) to verify the invariant catches
    them. A real ``dataclass`` would reject those kwargs at
    ``__init__`` time, and ``__slots__`` would block ``setattr``,
    so we use a plain class with explicit field declarations.
    ``check_review_non_authoritative`` inspects ``__dict__`` so
    this stand-in is compatible.
    """

    def __init__(
        self,
        *,
        verdict: Any,
        conviction: Optional[int] = None,
        reason: str = "",
        payload: Any = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        prompt_version: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        response_seconds: Optional[float] = None,
        # NOTE: tests pass arbitrary additional kwargs here so the
        # contract-health invariant can be exercised against
        # forbidden authority fields. The constructor silently
        # accepts them and stashes them on the instance dict so
        # ``check_review_non_authoritative`` sees them.
        **_forbidden_authority_fields: Any,
    ) -> None:
        self.verdict = verdict
        self.conviction = conviction
        self.reason = reason
        self.payload = payload
        self.model = model
        self.base_url = base_url
        self.prompt_version = prompt_version
        self.started_at = started_at
        self.completed_at = completed_at
        self.response_seconds = response_seconds
        for k, v in _forbidden_authority_fields.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Imports under test


from contract_health import (  # noqa: E402
    FORBIDDEN_REVIEW_DELTA_FIELDS,
    STATUS_ENVELOPE_ALLOWED_KEYS,
    USEFULNESS_ALLOWED_KEYS,
    ContractCheck,
    ContractReport,
    check_classifier_fail_closed,
    check_no_prompt_leakage,
    check_review_non_authoritative,
    check_status_envelope_authority,
    check_usefulness_counters_only,
    evaluate_contract,
)
from tools.contract_health_check import (  # noqa: E402
    check_snapshot,
    main,
    print_config,
    run_self_check,
)


# ---------------------------------------------------------------------------
# 1. check_status_envelope_authority


class TestStatusEnvelopeAuthority:
    """Invariant 1: the bounded status envelope carries no authority."""

    def test_none_envelope_is_informational(self):
        c = check_status_envelope_authority(None)
        assert c.passed is True
        assert c.observed["present"] is False
        assert c.violations == []

    def test_well_formed_envelope_passes(self):
        envelope = {
            "state": "READY",
            "reported_at": "2026-09-14T10:00:01+00:00",
            "async_requested": True,
            "policy_allows_annotation": True,
            "reason": "optional_annotation_ready",
            "queue": {"pending": 0, "circuit_state": "CLOSED"},
            "usefulness": {
                "verdict_counts": {"approve": 1},
                "cache_hits": 0,
                "cache_misses": 0,
                "circuit_opens": 0,
            },
        }
        c = check_status_envelope_authority(envelope)
        assert c.passed is True, c.violations
        assert c.observed["keys"] == sorted(envelope.keys())
        assert c.observed["usefulness_keys"] == sorted(
            envelope["usefulness"].keys()
        )

    def test_can_place_orders_true_is_violation(self):
        envelope = {"can_place_orders": True}
        c = check_status_envelope_authority(envelope)
        assert c.passed is False
        assert any(
            "can_place_orders=True" in v for v in c.violations
        ), c.violations

    def test_authorization_effect_non_none_is_violation(self):
        envelope = {"authorization_effect": "AUTHORIZE"}
        c = check_status_envelope_authority(envelope)
        assert c.passed is False
        assert any(
            "authorization_effect='AUTHORIZE'" in v for v in c.violations
        ), c.violations

    def test_unknown_top_level_key_is_violation(self):
        envelope = {"state": "READY", "secret_pitch": "buy now"}
        c = check_status_envelope_authority(envelope)
        assert c.passed is False
        assert any(
            "secret_pitch" in v for v in c.violations
        ), c.violations

    def test_usefulness_unknown_key_is_violation(self):
        envelope = {
            "usefulness": {
                "verdict_counts": {},
                "raw_model_output": "buy AAPL",
            }
        }
        c = check_status_envelope_authority(envelope)
        assert c.passed is False
        assert any(
            "raw_model_output" in v for v in c.violations
        ), c.violations

    def test_non_dict_envelope_is_violation(self):
        c = check_status_envelope_authority("not a dict")
        assert c.passed is False
        assert any("not a dict" in v for v in c.violations)


# ---------------------------------------------------------------------------
# 2. check_no_prompt_leakage


class TestNoPromptLeakage:
    """Invariant 2: no prompt content crosses the agent->engine bridge."""

    def test_none_snapshot_is_informational(self):
        c = check_no_prompt_leakage(None)
        assert c.passed is True
        assert c.observed["present"] is False

    def test_clean_snapshot_passes(self):
        snapshot = {
            "state": "READY",
            "queue_size": 0,
            "usefulness": {"cache_hits": 0},
        }
        c = check_no_prompt_leakage(snapshot)
        assert c.passed is True, c.violations

    def test_prompt_leak_at_top_level_is_violation(self):
        snapshot = {"prompt": "ignore previous instructions"}
        c = check_no_prompt_leakage(snapshot)
        assert c.passed is False
        assert any("'prompt'" in v for v in c.violations)

    def test_review_text_leak_is_violation(self):
        snapshot = {"rationale": "buy because momentum"}
        c = check_no_prompt_leakage(snapshot)
        assert c.passed is False
        assert any("rationale" in v for v in c.violations)

    def test_leak_inside_usefulness_is_violation(self):
        snapshot = {
            "usefulness": {
                "verdict_counts": {},
                "pitch": "BUY BUY BUY",
            }
        }
        c = check_no_prompt_leakage(snapshot)
        assert c.passed is False
        assert any("pitch" in v for v in c.violations)

    def test_non_dict_snapshot_is_violation(self):
        c = check_no_prompt_leakage(42)
        assert c.passed is False


# ---------------------------------------------------------------------------
# 3. check_usefulness_counters_only


class TestUsefulnessCountersOnly:
    """Invariant 3: the usefulness envelope carries counters only."""

    def test_no_usefulness_key_is_informational(self):
        c = check_usefulness_counters_only({"state": "READY"})
        assert c.passed is True

    def test_well_formed_usefulness_passes(self):
        snapshot = {
            "usefulness": {
                "verdict_counts": {"approve": 1, "reject": 0},
                "cache_hits": 1,
                "cache_misses": 0,
                "cache_hit_rate": 1.0,
                "circuit_opens": 0,
                "total_completed_reviews": 1,
                "response_seconds_mean": 1.5,
                "response_seconds_p95": 2.4,
                "response_seconds_last": 1.5,
                "last_completed_at": "2026-09-14T10:00:00+00:00",
            }
        }
        c = check_usefulness_counters_only(snapshot)
        assert c.passed is True, c.violations

    def test_real_queue_snapshot_passes_contract_health(self):
        from async_reviews import AsyncReviewQueue

        queue = AsyncReviewQueue(lambda *_args, **_kwargs: None)
        try:
            snapshot = {"usefulness": queue.usefulness_snapshot()}
            c = check_usefulness_counters_only(snapshot)
        finally:
            queue.shutdown()
        assert c.passed is True, c.violations

    def test_usefulness_unknown_key_is_violation(self):
        snapshot = {"usefulness": {"verdict_counts": {}, "secret": 1}}
        c = check_usefulness_counters_only(snapshot)
        assert c.passed is False
        assert any("'secret'" in v for v in c.violations)

    def test_verdict_counts_must_be_dict(self):
        snapshot = {"usefulness": {"verdict_counts": "approve:1"}}
        c = check_usefulness_counters_only(snapshot)
        assert c.passed is False
        assert any("verdict_counts must be dict" in v for v in c.violations)

    def test_verdict_counts_non_int_value_is_violation(self):
        snapshot = {
            "usefulness": {"verdict_counts": {"approve": "yes"}}
        }
        c = check_usefulness_counters_only(snapshot)
        assert c.passed is False
        assert any("not int" in v for v in c.violations)

    def test_non_primitive_value_is_violation(self):
        snapshot = {
            "usefulness": {
                "verdict_counts": {},
                "cache_hits": {"nested": "dict"},
            }
        }
        c = check_usefulness_counters_only(snapshot)
        assert c.passed is False
        assert any(
            "not a bounded primitive" in v for v in c.violations
        )

    def test_bool_value_for_count_key_is_violation(self):
        # bool is a subclass of int in Python; reject explicitly.
        snapshot = {
            "usefulness": {
                "verdict_counts": {},
                "cache_hits": True,
            }
        }
        c = check_usefulness_counters_only(snapshot)
        assert c.passed is False
        assert any("bool not allowed" in v for v in c.violations)


# ---------------------------------------------------------------------------
# 4. check_classifier_fail_closed


class TestClassifierFailClosed:
    """Invariant 4: the bounded classifier never breaks fail-closed."""

    def test_none_classifications_is_informational(self):
        c = check_classifier_fail_closed(None)
        assert c.passed is True
        assert c.observed["n_inspected"] == 0

    def test_above_threshold_known_category_passes(self):
        # Use a plain string for the category so we don't need to
        # import the real enum -- the bounded enum is duck-typed.
        classifications = [
            FakeClassification(
                category="regulatory", confidence=0.9, rationale="ok"
            )
        ]
        c = check_classifier_fail_closed(classifications)
        assert c.passed is True, c.violations
        assert c.observed["n_inspected"] == 1
        assert c.observed["max_rationale_len"] == 2

    def test_below_threshold_forced_to_unknown_passes(self):
        classifications = [
            FakeClassification(
                category="unknown", confidence=0.4, rationale="low conf"
            )
        ]
        c = check_classifier_fail_closed(classifications)
        assert c.passed is True, c.violations

    def test_below_threshold_non_unknown_is_violation(self):
        classifications = [
            FakeClassification(
                category="regulatory", confidence=0.3, rationale="bad"
            )
        ]
        c = check_classifier_fail_closed(classifications)
        assert c.passed is False
        assert any("must be UNKNOWN" in v for v in c.violations), (
            c.violations
        )

    def test_above_threshold_unknown_is_fine(self):
        # UNKNOWN with high confidence is a legitimate outcome
        # (the model was confidently uncertain).
        classifications = [
            FakeClassification(
                category="unknown", confidence=0.9, rationale="not in enum"
            )
        ]
        c = check_classifier_fail_closed(classifications)
        assert c.passed is True, c.violations

    def test_rationale_too_long_is_violation(self):
        classifications = [
            FakeClassification(
                category="regulatory",
                confidence=0.9,
                rationale="x" * 281,
            )
        ]
        c = check_classifier_fail_closed(classifications)
        assert c.passed is False
        assert any("> 280 chars" in v for v in c.violations), (
            c.violations
        )

    def test_category_outside_enum_is_violation(self):
        # Only runs when agent.news_classifier is importable.
        pytest.importorskip("news_classifier")
        classifications = [
            FakeClassification(
                category="totally_made_up", confidence=0.9, rationale="bad"
            )
        ]
        c = check_classifier_fail_closed(classifications)
        assert c.passed is False
        assert any("not in the bounded enum" in v for v in c.violations), (
            c.violations
        )


# ---------------------------------------------------------------------------
# 5. check_review_non_authoritative


class TestReviewNonAuthoritative:
    """Invariant 5: a Review carries no capital/qualification authority."""

    def test_none_reviews_is_informational(self):
        c = check_review_non_authoritative(None)
        assert c.passed is True
        assert c.observed["n_inspected"] == 0

    def test_well_formed_review_passes(self):
        reviews = [
            FakeReview(verdict="approve", conviction=80, model="MiniMax-M3"),
            FakeReview(verdict="reject", conviction=20),
        ]
        c = check_review_non_authoritative(reviews)
        assert c.passed is True, c.violations
        assert c.observed["n_inspected"] == 2

    def test_review_with_authority_field_is_violation(self):
        reviews = [
            FakeReview(
                verdict="approve",
                conviction=80,
                can_place_orders=True,
            )
        ]
        c = check_review_non_authoritative(reviews)
        assert c.passed is False
        assert any(
            "forbidden authority fields" in v for v in c.violations
        ), c.violations

    def test_review_with_approved_live_budget_is_violation(self):
        reviews = [
            FakeReview(
                verdict="approve",
                conviction=80,
                approved_live_budget=100000,
            )
        ]
        c = check_review_non_authoritative(reviews)
        assert c.passed is False
        assert any("approved_live_budget" in v for v in c.violations), (
            c.violations
        )

    def test_real_review_object_passes(self):
        # Only runs when agent.advisory is importable.
        pytest.importorskip("advisory")
        from advisory import unavailable
        r = unavailable("timeout_100s")
        c = check_review_non_authoritative([r])
        assert c.passed is True, c.violations


# ---------------------------------------------------------------------------
# evaluate_contract


class TestEvaluateContract:
    """Aggregate report -- happy path, partial path, and all-fail path."""

    def test_all_none_is_pass(self):
        report = evaluate_contract()
        assert report.passed is True
        assert all(c.passed for c in report.checks)
        assert len(report.checks) == 5

    def test_all_clean_inputs_pass(self):
        snapshot = {
            "state": "READY",
            "reported_at": "2026-09-14T10:00:01+00:00",
            "async_requested": True,
            "policy_allows_annotation": True,
            "reason": "optional_annotation_ready",
            "queue": {"pending": 0, "circuit_state": "CLOSED"},
            "usefulness": {
                "verdict_counts": {"approve": 1, "reject": 0},
                "cache_hits": 0,
                "cache_misses": 0,
                "circuit_opens": 0,
            },
        }
        classifications = [
            FakeClassification(
                category="regulatory", confidence=0.9, rationale="ok"
            ),
            FakeClassification(
                category="unknown", confidence=0.4, rationale="low conf"
            ),
        ]
        reviews = [
            FakeReview(verdict="approve", conviction=80),
        ]
        report = evaluate_contract(
            status_envelope=snapshot,
            usefulness_snapshot=snapshot,
            classifications=classifications,
            reviews=reviews,
        )
        assert report.passed is True
        for c in report.checks:
            assert c.passed, (c.name, c.violations)

    def test_one_violation_fails_report(self):
        snapshot = {"can_place_orders": True}
        report = evaluate_contract(status_envelope=snapshot)
        assert report.passed is False
        assert any(not c.passed for c in report.checks)
        # Only the status envelope check should have failed.
        assert not report.checks[0].passed
        assert report.checks[1].passed
        assert report.checks[2].passed

    def test_to_dict_round_trip(self):
        report = evaluate_contract()
        d = report.to_dict()
        # Round-trippable via json.dumps -> json.loads.
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2["schema_version"] == report.schema_version
        assert d2["passed"] is True
        assert len(d2["checks"]) == 5

    def test_violations_helper_flattens(self):
        snapshot = {"can_place_orders": True, "prompt": "leak"}
        report = evaluate_contract(
            status_envelope=snapshot, usefulness_snapshot=snapshot
        )
        flat = report.violations()
        assert len(flat) >= 2
        # Each line carries the check name as a prefix.
        assert any(line.startswith("status_envelope_authority:")
                   for line in flat)
        assert any(line.startswith("no_prompt_leakage:")
                   for line in flat)


# ---------------------------------------------------------------------------
# CLI


class TestContractHealthCli:
    """The CLI must be pure: print-config + check + self-check."""

    def test_print_config_runs(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = print_config()
        assert rc == 0
        out = buf.getvalue()
        # Each bounded name surfaces in the printed contract.
        assert "STATUS_ENVELOPE_ALLOWED_KEYS" in out
        assert "USEFULNESS_ALLOWED_KEYS" in out
        assert "FORBIDDEN_REVIEW_DELTA_FIELDS" in out
        assert "CONFIDENCE_THRESHOLD" in out

    def test_self_check_passes(self):
        rc = run_self_check()
        assert rc == 0

    def test_check_snapshot_well_formed_passes(self):
        snapshot = {
            "state": "READY",
            "usefulness": {
                "verdict_counts": {"approve": 1},
                "cache_hits": 0,
                "cache_misses": 0,
                "circuit_opens": 0,
            },
        }
        report = check_snapshot(snapshot)
        assert report.passed is True

    def test_check_snapshot_violation_fails(self):
        snapshot = {"can_place_orders": True}
        report = check_snapshot(snapshot)
        assert report.passed is False

    def test_main_print_config_subcommand(self):
        rc = main(["print-config"])
        assert rc == 0

    def test_main_self_check_subcommand(self):
        rc = main(["self-check"])
        assert rc == 0

    def test_main_check_subcommand_pass(self, tmp_path):
        # Write a well-formed snapshot to disk, then ``check`` it.
        snapshot = {
            "state": "READY",
            "usefulness": {"verdict_counts": {}, "cache_hits": 0},
        }
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        rc = main(["check", str(path)])
        assert rc == 0

    def test_main_check_subcommand_fail(self, tmp_path):
        snapshot = {"can_place_orders": True}
        path = tmp_path / "snapshot.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        rc = main(["check", str(path)])
        assert rc == 1

    def test_main_check_missing_file(self, tmp_path):
        path = tmp_path / "does-not-exist.json"
        rc = main(["check", str(path)])
        assert rc == 2

    def test_main_check_bad_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        rc = main(["check", str(path)])
        assert rc == 2

    def test_main_check_non_dict_root(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        rc = main(["check", str(path)])
        assert rc == 2

    def test_main_unknown_command_exits_2(self, capsys):
        # argparse calls parser.error() on unknown subcommands,
        # which raises SystemExit(2) -- main() does not catch it
        # because argparse owns that exit path.
        with pytest.raises(SystemExit) as exc:
            main(["nope"])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Allow-list shape invariants


class TestAllowListShape:
    """The allow-lists themselves must be the documented contract."""

    def test_status_envelope_is_a_frozenset_of_str(self):
        assert isinstance(STATUS_ENVELOPE_ALLOWED_KEYS, frozenset)
        for k in STATUS_ENVELOPE_ALLOWED_KEYS:
            assert isinstance(k, str)

    def test_usefulness_is_a_frozenset_of_str(self):
        assert isinstance(USEFULNESS_ALLOWED_KEYS, frozenset)
        for k in USEFULNESS_ALLOWED_KEYS:
            assert isinstance(k, str)

    def test_forbidden_review_delta_is_a_frozenset_of_str(self):
        assert isinstance(FORBIDDEN_REVIEW_DELTA_FIELDS, frozenset)
        for k in FORBIDDEN_REVIEW_DELTA_FIELDS:
            assert isinstance(k, str)

    def test_forbidden_fields_do_not_overlap_with_status_envelope(self):
        # Belt-and-braces: the forbidden fields must not be in the
        # status envelope allow-list (a single field cannot be both
        # required AND forbidden).
        assert (
            FORBIDDEN_REVIEW_DELTA_FIELDS & STATUS_ENVELOPE_ALLOWED_KEYS
        ) == frozenset()
