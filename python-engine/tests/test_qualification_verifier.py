"""[WORKFLOW-A3 2026-09-20] Qualification verifier tests.

Pins every audit-acceptance check from
``docs/2026-09-20-independent-system-readiness-audit.md`` §3-A3:

  - Made-up hash / absent report: reject at byte-verification step.
  - Failed/insufficient heldout: reject with reason
    ``heldout_insufficient``.
  - Changed configuration / economics: reject with reason
    ``policy_manifest_mismatch``.
  - Expired review: reject with reason ``validity_expired``.
  - Different index than artifact: reject with reason
    ``index_mismatch``.
  - Genuine reviewed passing package: qualifies.

Plus defensive tests:

  - JSON shape (not a dict): ``report_not_json``.
  - Missing top-level keys: schema codes.
  - Empty / whitespace inputs: ``report_bytes_mismatch``.
  - ``QualificationVerdict`` serialisation.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))


from qualification_verifier import (  # noqa: E402
    QualificationReason,
    QualificationVerdict,
    qualify_research_package,
)


def _build_report_bytes(**overrides) -> bytes:
    """Return canonical report JSON bytes. Test code mutates the
    returned dict via overrides to drive each branch."""
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    report = {
        "index": "NIFTY",
        "structure_kind": "DIRECTIONAL_DEBIT_SPREAD",
        "horizon": "INTRADAY",
        "policy_version": "v1",
        "predeclared_criteria": {
            "min_win_rate_pct": 50.0,
            "max_drawdown_pct": 15.0,
        },
        "heldout_split": {
            "train_window": {"start": "2026-08-01T00:00:00+00:00", "end": "2026-08-31T00:00:00+00:00"},
            "test_window": {"start": "2026-09-01T00:00:00+00:00", "end": "2026-09-15T00:00:00+00:00"},
        },
        "outcome_availability": {"resolved": 12, "unresolved": 0},
        "costs": {"fee_model": "ZERO_COST_PAPER", "slippage_bps": 5.0},
        "review_identity": {
            "operator": "ops@trading-sentinel",
            "reviewed_at": (now - timedelta(days=2)).isoformat(),
        },
        "validity_period": {
            "start": (now - timedelta(days=2)).isoformat(),
            "end": (now + timedelta(days=30)).isoformat(),
        },
        "policy_manifest": {"strategy": "x", "version": "v1"},
    }
    report.update(overrides)
    return json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest_sha(report_bytes: bytes) -> str:
    """Return the SHA-256 the verifier computes for the report's
    ``policy_manifest`` field."""
    report = json.loads(report_bytes.decode("utf-8"))
    canonical = json.dumps(
        report["policy_manifest"], sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    import hashlib
    return hashlib.sha256(canonical).hexdigest()


# -- Acceptance tests (from the audit) ------------------------------


def test_made_up_hash_rejects_at_byte_verification():
    """Audit acceptance: a made-up hash/reference cannot authorize."""
    report_bytes = _build_report_bytes()
    bad_hash = "0" * 64
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=bad_hash,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.REPORT_BYTES_MISMATCH in verdict.reason_codes


def test_absent_report_rejected_via_byte_mismatch():
    """Audit acceptance: an absent report fails at the byte check
    (the caller raises before reaching the verifier). Here we
    simulate the empty-bytes path."""
    verdict = qualify_research_package(
        report_bytes=b"",
        registered_sha256="",
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256="",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.REPORT_BYTES_MISMATCH in verdict.reason_codes


def test_heldout_insufficient_rejects():
    """Audit acceptance: failed/insufficient heldout result."""
    report_bytes = _build_report_bytes(
        heldout_split={"train_window": {}, "test_window": {}}
    )
    # Compute the registered sha256 against the *correct* bytes --
    # the verifier first checks bytes, then schema, so we want the
    # bytes check to pass and heldout_insufficient to fire.
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.HELDOUT_INSUFFICIENT in verdict.reason_codes


def test_changed_policy_manifest_rejects():
    """Audit acceptance: changed configuration/economics (the
    policy_manifest fingerprint changes) invalidates old evidence."""
    report_bytes = _build_report_bytes()
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    # Use a fake deployed manifest sha; the verifier compares and
    # rejects.
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256="a" * 64,
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.POLICY_MANIFEST_MISMATCH in verdict.reason_codes


def test_expired_review_rejects():
    """Audit acceptance: expired review rejects."""
    past = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    report_bytes = _build_report_bytes(
        validity_period={
            "start": (past - timedelta(days=30)).isoformat(),
            "end": (past + timedelta(days=1)).isoformat(),
        }
    )
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.VALIDITY_EXPIRED in verdict.reason_codes


def test_different_index_rejects():
    """Audit acceptance: different index than artifact cannot
    authorise."""
    report_bytes = _build_report_bytes(index="SENSEX")
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.INDEX_MISMATCH in verdict.reason_codes


def test_genuine_reviewed_package_qualifies():
    """Audit acceptance: a genuine reviewed passing package can
    authorise (and binds the manifest_sha256)."""
    report_bytes = _build_report_bytes()
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert verdict.qualified
    assert verdict.reason_codes == (QualificationReason.PASS,)
    assert verdict.manifest_sha256 == _manifest_sha(report_bytes)
    assert verdict.validity_start is not None
    assert verdict.validity_end is not None


# -- Defensive tests --------------------------------------------------


def test_non_json_bytes_reports_not_json():
    verdict = qualify_research_package(
        report_bytes=b"not-json",
        registered_sha256="",
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256="",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    # Without a valid sha256 match, REPORT_BYTES_MISMATCH fires first.
    # Provide a matching sha for the bytes and the JSON parse fires.
    import hashlib
    report_bytes = b"not-json"
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256="",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.REPORT_NOT_JSON in verdict.reason_codes


def test_missing_top_level_keys_produce_schema_codes():
    """Each missing top-level key surfaces a distinct code so the
    caller can pinpoint what's missing."""
    base = _build_report_bytes()
    # Decode, drop several keys, re-encode.
    report = json.loads(base.decode("utf-8"))
    report.pop("index")
    report.pop("validity_period")
    report.pop("review_identity")
    modified = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    import hashlib
    registered = hashlib.sha256(modified).hexdigest()
    verdict = qualify_research_package(
        report_bytes=modified,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256="",
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert not verdict.qualified
    assert QualificationReason.SCHEMA_MISSING_INDEX in verdict.reason_codes
    assert QualificationReason.SCHEMA_MISSING_VALIDITY in verdict.reason_codes
    assert QualificationReason.SCHEMA_MISSING_REVIEW in verdict.reason_codes


def test_horizon_mismatch_rejects():
    report_bytes = _build_report_bytes(horizon="SWING")
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.HORIZON_MISMATCH in verdict.reason_codes


def test_policy_version_mismatch_rejects():
    report_bytes = _build_report_bytes(policy_version="v0")
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.POLICY_VERSION_MISMATCH in verdict.reason_codes


def test_costs_incomplete_rejects():
    report_bytes = _build_report_bytes(costs={"fee_model": "ZERO_COST_PAPER"})
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.COSTS_INCOMPLETE in verdict.reason_codes


def test_structure_mismatch_rejects():
    report_bytes = _build_report_bytes(structure_kind="IRON_CONDOR")
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.STRUCTURE_MISMATCH in verdict.reason_codes


def test_review_missing_rejects():
    report_bytes = _build_report_bytes(
        review_identity={"operator": "", "reviewed_at": ""}
    )
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.REVIEW_MISSING in verdict.reason_codes


def test_validity_not_yet_active_rejects():
    future = datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc)
    report_bytes = _build_report_bytes(
        validity_period={
            "start": future.isoformat(),
            "end": (future + timedelta(days=30)).isoformat(),
        }
    )
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    assert QualificationReason.VALIDITY_NOT_YET_ACTIVE in verdict.reason_codes


def test_qualification_verdict_serialises_to_dict():
    report_bytes = _build_report_bytes()
    import hashlib
    registered = hashlib.sha256(report_bytes).hexdigest()
    verdict = qualify_research_package(
        report_bytes=report_bytes,
        registered_sha256=registered,
        expected_index="NIFTY",
        expected_structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        expected_horizon="INTRADAY",
        expected_policy_version="v1",
        deployed_policy_manifest_sha256=_manifest_sha(report_bytes),
        now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    payload = verdict.to_dict()
    assert payload["qualified"] is True
    assert payload["reason_codes"] == ["pass"]
    assert payload["manifest_sha256"] == _manifest_sha(report_bytes)
    assert payload["report_sha256"] == registered
    assert payload["validity_start"] is not None
    assert payload["validity_end"] is not None
