"""[WORKFLOW-C.A4 2026-09-15] Qualification manifest drift tests.

The qualification criteria manifest is the frozen
predeclared contract that binds a deployed policy to a
disjoint training/holdout schedule. ``A4`` adds a
read-only drift check that pins:
  - the body fingerprint matches the on-disk
    ``criteria_manifest_sha256``,
  - the body is reconstructable from
    ``freeze_qualification_criteria`` (no manual edits
    added unsupported fields).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import pytz


from partner_qualification_review import (
    QualificationCriteria,
    _sha,
    freeze_qualification_criteria,
    write_qualification_criteria_manifest,
)
from partner_qualification_verify import (
    ManifestDriftKind,
    ManifestVerificationReport,
    verify_qualification_criteria_manifest,
)


# ---------------------------------------------------------------------------
# Helpers


def _criteria():
    return QualificationCriteria(
        policy_sha256="f" * 64,
        min_covered_sessions=1,
        min_closed_outcomes=3,
        max_unresolved_outcomes=2,
        max_drawdown_rs=-100.0,
        stressed_fee_multiplier=1.5,
        stressed_slippage_bps=5.0,
    )


def _frozen_manifest(tmp_path: Path):
    """A canonical manifest written to disk via the existing
    writer. Returns the manifest dict and the on-disk path.
    """
    frozen = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 9, 11, 12))
    coverage = [("NIFTY", "f" * 64, "2026-09-12")]
    manifest = freeze_qualification_criteria(criteria=_criteria(), underlying="NIFTY",
        training_sessions=["2026-09-10"], holdout_sessions=["2026-09-12"],
        declared_coverage=coverage, frozen_at=frozen)
    path = tmp_path / "criteria-manifest.json"
    write_qualification_criteria_manifest(path, manifest)
    return manifest, path


# ---------------------------------------------------------------------------
# 1. Pure helpers -- ManifestDriftKind, ManifestVerificationReport


class TestManifestDriftKind:
    def test_kind_values_are_strings(self):
        for kind in ManifestDriftKind:
            assert isinstance(kind.value, str)
            assert kind.value == kind.name

    def test_kind_set_is_bounded(self):
        # The verify contract documents exactly five kinds.
        assert {k.value for k in ManifestDriftKind} == {
            "MATCH",
            "ON_DISK_MISSING",
            "MANIFEST_FINGERPRINT_MISMATCH",
            "CRITERIA_NOT_RECONSTRUCTABLE",
            "BYTES_UNREADABLE",
        }


class TestManifestVerificationReport:
    def test_matches_property_true_on_match(self):
        r = ManifestVerificationReport(
            kind=ManifestDriftKind.MATCH,
            on_disk_path="x",
            on_disk_fingerprint="a" * 64,
            reconstructed_fingerprint="a" * 64,
            on_disk_size=100,
        )
        assert r.matches is True

    def test_matches_property_false_on_any_drift(self):
        for kind in (
            ManifestDriftKind.MANIFEST_FINGERPRINT_MISMATCH,
            ManifestDriftKind.CRITERIA_NOT_RECONSTRUCTABLE,
            ManifestDriftKind.BYTES_UNREADABLE,
            ManifestDriftKind.ON_DISK_MISSING,
        ):
            r = ManifestVerificationReport(
                kind=kind, on_disk_path="x", on_disk_fingerprint=None,
                reconstructed_fingerprint=None, on_disk_size=None,
            )
            assert r.matches is False

    def test_dataclass_is_frozen(self):
        r = ManifestVerificationReport(
            kind=ManifestDriftKind.MATCH, on_disk_path="x",
            on_disk_fingerprint="a" * 64, reconstructed_fingerprint="a" * 64,
            on_disk_size=100,
        )
        with pytest.raises(Exception):
            r.kind = ManifestDriftKind.BYTES_UNREADABLE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Integration tests -- verify_qualification_criteria_manifest


class TestVerifyManifest:
    """The drift-detection contract on a real on-disk manifest."""

    def test_match_when_intact(self, tmp_path: Path):
        """[WORKFLOW-C.A4 2026-09-15] A freshly-written
        manifest verifies as MATCH. The fingerprint check
        AND the reconstructability check both pass.
        """
        _, path = _frozen_manifest(tmp_path)
        result = verify_qualification_criteria_manifest(path)
        assert result.kind == ManifestDriftKind.MATCH
        assert result.matches is True
        assert result.on_disk_fingerprint == result.reconstructed_fingerprint
        assert result.on_disk_size > 0

    def test_on_disk_missing_returns_on_disk_missing(self, tmp_path: Path):
        result = verify_qualification_criteria_manifest(tmp_path / "does-not-exist.json")
        assert result.kind == ManifestDriftKind.ON_DISK_MISSING
        assert result.matches is False
        assert result.on_disk_path is None
        assert result.on_disk_size is None

    def test_corrupted_fingerprint_is_fingerprint_mismatch(self, tmp_path: Path):
        """[WORKFLOW-C.A4 2026-09-15] When the body or the
        fingerprint has been tampered with, the body
        fingerprint check fails before the
        reconstructability check.
        """
        manifest, path = _frozen_manifest(tmp_path)
        # Tamper with the body (change one field).
        manifest["frozen_at"] = "2099-01-01T00:00:00+00:00"
        path.write_text(
            # Re-serialize without re-hashing -- the on-disk
            # fingerprint stays the same but the body has
            # changed.
            __import__("json").dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result = verify_qualification_criteria_manifest(path)
        # The body fingerprint changed (because we changed
        # a body field) but the on-disk
        # ``criteria_manifest_sha256`` is still the old one.
        assert result.kind == ManifestDriftKind.MANIFEST_FINGERPRINT_MISMATCH
        assert result.on_disk_fingerprint != result.reconstructed_fingerprint

    def test_unsupported_field_added_is_not_reconstructable(self, tmp_path: Path):
        """[WORKFLOW-C.A4 2026-09-15] When the body has
        added a field that ``freeze_qualification_criteria``
        doesn't produce, the fingerprint check may pass
        (if the operator also updated the fingerprint) but
        the reconstructability check fails because the
        reconstructed body doesn't have the unsupported
        field.
        """
        manifest, path = _frozen_manifest(tmp_path)
        # Add an unsupported field and re-hash.
        manifest["rogue_field"] = "tampered"
        manifest["criteria_manifest_sha256"] = _sha(
            {key: value for key, value in manifest.items()
             if key != "criteria_manifest_sha256"}
        )
        path.write_text(
            __import__("json").dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result = verify_qualification_criteria_manifest(path)
        # The body fingerprint matches the on-disk one, but
        # the reconstructability check fails because
        # ``freeze_qualification_criteria`` doesn't produce
        # ``rogue_field``.
        assert result.kind == ManifestDriftKind.CRITERIA_NOT_RECONSTRUCTABLE

    def test_frozen_at_after_holdout_is_not_reconstructable(self, tmp_path: Path):
        """[WORKFLOW-C.A4 2026-09-15] When the manifest has
        ``frozen_at`` AFTER the first holdout session,
        ``freeze_qualification_criteria`` raises
        ``"criteria must be frozen before the first
        holdout session"``. The verifier catches the
        exception and degrades to
        ``CRITERIA_NOT_RECONSTRUCTABLE``.
        """
        manifest, path = _frozen_manifest(tmp_path)
        # Move frozen_at to AFTER the first holdout session.
        manifest["frozen_at"] = "2026-09-13T00:00:00+00:00"
        manifest["criteria_manifest_sha256"] = _sha(
            {key: value for key, value in manifest.items()
             if key != "criteria_manifest_sha256"}
        )
        path.write_text(
            __import__("json").dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result = verify_qualification_criteria_manifest(path)
        assert result.kind == ManifestDriftKind.CRITERIA_NOT_RECONSTRUCTABLE

    def test_corrupt_json_is_bytes_unreadable(self, tmp_path: Path):
        path = tmp_path / "criteria-manifest.json"
        path.write_text("not valid json", encoding="utf-8")
        result = verify_qualification_criteria_manifest(path)
        assert result.kind == ManifestDriftKind.BYTES_UNREADABLE

    def test_non_dict_json_is_bytes_unreadable(self, tmp_path: Path):
        """[WORKFLOW-C.A4 2026-09-15] Defensive: a JSON
        that's valid but isn't a dict (e.g. a JSON list at
        the top level) can't be a manifest. The helper
        degrades to ``BYTES_UNREADABLE``.
        """
        path = tmp_path / "criteria-manifest.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        result = verify_qualification_criteria_manifest(path)
        assert result.kind == ManifestDriftKind.BYTES_UNREADABLE

    def test_verify_is_pure_no_writes_to_disk(self, tmp_path: Path):
        """[WORKFLOW-C.A4 2026-09-15] The verify contract
        is read-only. The function MUST NOT write to the
        on-disk manifest; the operator commits via
        ``write_qualification_criteria_manifest``.
        Without this, ``--verify-criteria-manifest`` would
        silently repair drift instead of detecting it.
        """
        _, path = _frozen_manifest(tmp_path)
        size_before = path.stat().st_size
        mtime_before = path.stat().st_mtime_ns
        verify_qualification_criteria_manifest(path)
        size_after = path.stat().st_size
        mtime_after = path.stat().st_mtime_ns
        assert size_after == size_before
        assert mtime_after == mtime_before

    def test_missing_fingerprint_field_is_fingerprint_mismatch(self, tmp_path: Path):
        """Defensive: a manifest that lacks the
        ``criteria_manifest_sha256`` field entirely is
        reported as ``MANIFEST_FINGERPRINT_MISMATCH`` --
        the body is computable, but the on-disk
        fingerprint is None so they can't match.
        """
        _, path = _frozen_manifest(tmp_path)
        import json
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.pop("criteria_manifest_sha256", None)
        path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8")
        result = verify_qualification_criteria_manifest(path)
        assert result.kind == ManifestDriftKind.MANIFEST_FINGERPRINT_MISMATCH
        assert result.on_disk_fingerprint is None
