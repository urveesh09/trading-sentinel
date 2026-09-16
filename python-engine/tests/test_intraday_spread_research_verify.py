"""[WORKFLOW-C.A5 2026-09-15] Research artifact drift tests.

The research artifact (``intraday_spread_research_v2``) is
the deterministic output of ``build_research_artifact``.
``A5`` adds a read-only drift check that pins:
  - the body fingerprint matches the on-disk
    ``evidence_sha256``,
  - the embedded run manifest's fingerprint is intact.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


from intraday_spread_research import (
    build_research_artifact,
    create_research_run_manifest,
)
from intraday_spread_research_verify import (
    ArtifactDriftKind,
    ArtifactVerificationReport,
    _recompute_evidence_fingerprint,
    verify_research_artifact,
)
from intraday_spread_replay import ReplayResult


# ---------------------------------------------------------------------------
# Helpers


def _result(state, pnl=None, identity="a"):
    return ReplayResult(state, "fixture", 100.0 if pnl is not None else None,
                        110.0 if pnl is not None else None,
                        2.0 if pnl is not None else None, pnl,
                        "2026-09-10T11:00:00+05:30",
                        "2026-09-10T14:00:00+05:30", identity * 64)


def _build_artifact(tmp_path: Path):
    """Build a canonical artifact. Returns the dict and the
    on-disk path (the dict is what the operator would
    persist; we round-trip through JSON to mimic a real
    file).
    """
    manifest = create_research_run_manifest(dataset_sha256="b" * 64, code_revision="d1f6467",
        session_dates=["2026-09-10"], declared_min_sessions=1, declared_min_closed_trades=1,
        policy_groups={"NIFTY": {}})
    artifact = build_research_artifact(dataset_sha256="b" * 64, code_revision="d1f6467",
        results=[_result("CLOSED", 8.0, "a")], session_dates=["2026-09-10"],
        declared_min_sessions=1, declared_min_closed_trades=1,
        policy_groups={"NIFTY": {}}, run_manifest=manifest)
    path = tmp_path / "research-artifact.json"
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                              default=str), encoding="utf-8")
    return artifact, path


# ---------------------------------------------------------------------------
# 1. Pure helpers -- ArtifactDriftKind, ArtifactVerificationReport


class TestArtifactDriftKind:
    def test_kind_values_are_strings(self):
        for kind in ArtifactDriftKind:
            assert isinstance(kind.value, str)
            assert kind.value == kind.name

    def test_kind_set_is_bounded(self):
        # The verify contract documents exactly five kinds.
        assert {k.value for k in ArtifactDriftKind} == {
            "MATCH",
            "ON_DISK_MISSING",
            "BYTES_UNREADABLE",
            "EVIDENCE_FINGERPRINT_MISMATCH",
            "MANIFEST_FINGERPRINT_MISMATCH",
        }


class TestArtifactVerificationReport:
    def test_matches_property_true_on_match(self):
        r = ArtifactVerificationReport(
            kind=ArtifactDriftKind.MATCH, on_disk_path="x",
            on_disk_fingerprint="a" * 64, reconstructed_fingerprint="a" * 64,
            on_disk_size=100,
        )
        assert r.matches is True

    def test_matches_property_false_on_any_drift(self):
        for kind in (
            ArtifactDriftKind.EVIDENCE_FINGERPRINT_MISMATCH,
            ArtifactDriftKind.MANIFEST_FINGERPRINT_MISMATCH,
            ArtifactDriftKind.BYTES_UNREADABLE,
            ArtifactDriftKind.ON_DISK_MISSING,
        ):
            r = ArtifactVerificationReport(
                kind=kind, on_disk_path="x", on_disk_fingerprint=None,
                reconstructed_fingerprint=None, on_disk_size=None,
            )
            assert r.matches is False

    def test_dataclass_is_frozen(self):
        r = ArtifactVerificationReport(
            kind=ArtifactDriftKind.MATCH, on_disk_path="x",
            on_disk_fingerprint="a" * 64, reconstructed_fingerprint="a" * 64,
            on_disk_size=100,
        )
        with pytest.raises(Exception):
            r.kind = ArtifactDriftKind.BYTES_UNREADABLE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Internal helper


class TestRecomputeEvidenceFingerprint:
    """[WORKFLOW-C.A5 2026-09-15] The pure helper that
    strips derived fields and re-hashes.

    Pins the contract:
      - The deterministic block (excluding ``created_at``,
        ``review_state``, ``evidence_sha256``,
        ``artifact_sha256``, ``limitations``) hashes to
        match the on-disk ``evidence_sha256``.
      - The exclusion list is exhaustive -- if a future
        change adds another derived field, the helper must
        add it to the exclusion list.
    """

    def test_recomputed_hash_matches_on_disk(self, tmp_path):
        artifact, _ = _build_artifact(tmp_path)
        on_disk = artifact["evidence_sha256"]
        recomputed = _recompute_evidence_fingerprint(artifact)
        assert recomputed == on_disk

    def test_excludes_created_at(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] Changing ``created_at``
        MUST NOT change the recomputed hash -- timestamps
        are derived, not deterministic.
        """
        artifact, _ = _build_artifact(tmp_path)
        original = _recompute_evidence_fingerprint(artifact)
        # Tamper with created_at -- the hash MUST be stable.
        tampered = dict(artifact)
        tampered["created_at"] = "2099-12-31T23:59:59+00:00"
        tampered["evidence_sha256"] = original  # restore the original hash
        # The recomputed hash should still equal original
        # because ``created_at`` is excluded.
        assert _recompute_evidence_fingerprint(tampered) == original

    def test_excludes_review_state(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] Changing
        ``review_state`` MUST NOT change the recomputed
        hash -- it's a derived field computed from the
        deterministic block.
        """
        artifact, _ = _build_artifact(tmp_path)
        original = _recompute_evidence_fingerprint(artifact)
        tampered = dict(artifact)
        tampered["review_state"] = "DIFFERENT_STATE"
        tampered["evidence_sha256"] = original
        assert _recompute_evidence_fingerprint(tampered) == original


# ---------------------------------------------------------------------------
# 3. Integration tests -- verify_research_artifact


class TestVerifyArtifact:
    """The drift-detection contract on a real on-disk artifact."""

    def test_match_when_intact(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] A freshly-built
        artifact verifies as MATCH. The body fingerprint
        check AND the manifest fingerprint check both pass.
        """
        _, path = _build_artifact(tmp_path)
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.MATCH
        assert result.matches is True
        assert result.on_disk_fingerprint == result.reconstructed_fingerprint
        assert result.on_disk_size > 0

    def test_on_disk_missing_returns_on_disk_missing(self, tmp_path):
        result = verify_research_artifact(tmp_path / "does-not-exist.json")
        assert result.kind == ArtifactDriftKind.ON_DISK_MISSING
        assert result.matches is False
        assert result.on_disk_path is None
        assert result.on_disk_size is None

    def test_corrupted_body_is_evidence_fingerprint_mismatch(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] When the body has been
        tampered with (without re-hashing), the body
        fingerprint check fails.
        """
        _, path = _build_artifact(tmp_path)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        # Tamper with a deterministic field (outcomes.net_pnl_rs).
        artifact["outcomes"]["net_pnl_rs"] = 999999.99
        path.write_text(
            json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                      default=str),
            encoding="utf-8",
        )
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.EVIDENCE_FINGERPRINT_MISMATCH
        assert result.on_disk_fingerprint != result.reconstructed_fingerprint

    def test_corrupted_manifest_is_manifest_fingerprint_mismatch(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] When the embedded
        run manifest's body has been tampered with AND the
        artifact's ``evidence_sha256`` was updated to match,
        but the embedded ``manifest_sha256`` was NOT updated,
        the manifest fingerprint check fires.

        This is a realistic attack scenario: an operator
        updates a manifest field and the artifact's overall
        hash, but forgets to update the embedded
        ``manifest_sha256``. The body check passes (because
        the artifact's overall hash matches the new
        deterministic block), but the manifest-specific
        check catches the inconsistency.
        """
        from intraday_spread_research import _sha as _research_sha
        _, path = _build_artifact(tmp_path)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        # Tamper with the manifest body.
        artifact["manifest"]["code_revision"] = "tampered-revision"
        # Re-hash the manifest body to what it would be after
        # tampering (but DON'T update the manifest_sha256
        # field -- that's the inconsistency we want to test).
        # Re-hash the artifact's deterministic block to match
        # the new manifest body. The body check will pass.
        deterministic_block = {key: value for key, value in artifact.items()
                              if key not in {"created_at", "review_state",
                                             "evidence_sha256",
                                             "artifact_sha256",
                                             "limitations"}}
        artifact["evidence_sha256"] = _research_sha(deterministic_block)
        # The embedded ``manifest_sha256`` is now stale.
        path.write_text(
            json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                      default=str),
            encoding="utf-8",
        )
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.MANIFEST_FINGERPRINT_MISMATCH

    def test_corrupt_json_is_bytes_unreadable(self, tmp_path):
        path = tmp_path / "research-artifact.json"
        path.write_text("not valid json", encoding="utf-8")
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.BYTES_UNREADABLE

    def test_non_dict_json_is_bytes_unreadable(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] Defensive: a JSON
        that's valid but isn't a dict (e.g. a JSON list at
        the top level) can't be an artifact. The helper
        degrades to ``BYTES_UNREADABLE``.
        """
        path = tmp_path / "research-artifact.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.BYTES_UNREADABLE

    def test_missing_evidence_sha256_field_is_fingerprint_mismatch(self, tmp_path):
        """Defensive: an artifact that lacks the
        ``evidence_sha256`` field entirely is reported as
        ``EVIDENCE_FINGERPRINT_MISMATCH`` -- the body is
        computable, but the on-disk fingerprint is None so
        they can't match.
        """
        _, path = _build_artifact(tmp_path)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact.pop("evidence_sha256", None)
        path.write_text(
            json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                      default=str),
            encoding="utf-8",
        )
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.EVIDENCE_FINGERPRINT_MISMATCH
        assert result.on_disk_fingerprint is None

    def test_verify_is_pure_no_writes_to_disk(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] The verify contract is
        read-only. The function MUST NOT write to the
        on-disk artifact; the operator commits via
        ``build_research_artifact`` (or the underlying CLI).
        Without this, the verifier would silently repair
        drift instead of detecting it.
        """
        _, path = _build_artifact(tmp_path)
        size_before = path.stat().st_size
        mtime_before = path.stat().st_mtime_ns
        verify_research_artifact(path)
        size_after = path.stat().st_size
        mtime_after = path.stat().st_mtime_ns
        assert size_after == size_before
        assert mtime_after == mtime_before

    def test_intact_artifact_round_trip_through_disk_is_match(self, tmp_path):
        """[WORKFLOW-C.A5 2026-09-15] The artifact's
        ``evidence_sha256`` MUST be invariant across JSON
        round-trips -- this is the byte-identical
        reproducibility contract the verifier pins.
        """
        artifact, path = _build_artifact(tmp_path)
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["evidence_sha256"] == artifact["evidence_sha256"]
        result = verify_research_artifact(path)
        assert result.kind == ArtifactDriftKind.MATCH
