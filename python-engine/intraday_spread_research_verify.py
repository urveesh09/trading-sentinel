"""[WORKFLOW-C.A5 2026-09-15] Research summary drift verification.

The research summary is the deterministic markdown render
of ``intraday_spread_research_v2`` artifacts. The artifact
itself is hashed via ``evidence_sha256`` (computed from a
``deterministic`` dict that excludes the timestamp). The
operator needs a read-only check that an on-disk artifact
matches what its declared ``evidence_sha256`` claims.

This module exposes ``verify_research_artifact``:
  - Reads the on-disk JSON.
  - Recomputes the canonical hash from the artifact's
    deterministic fields and compares to the on-disk
    ``evidence_sha256``.
  - Cross-checks the embedded ``manifest``'s
    ``manifest_sha256`` against its body.
  - Returns a structured ``ArtifactVerificationReport``
    with drift kind + byte size + recomputed fingerprint.

The helper is pure / total / never raises on filesystem
errors. Mirrors the shape of J.10.SUMMARY_VERIFY and
partner_qualification_verify so dashboards can use a
unified drift-handling pattern.

No new dependencies. Stdlib only (``json``, ``pathlib``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ArtifactDriftKind(str, Enum):
    """The kind of drift detected by
    ``verify_research_artifact``.

    Mirrors the J.10.SUMMARY_VERIFY ``DiffKind`` enum and
    the partner_qualification_verify ``ManifestDriftKind``
    enum. ``MATCH`` means the on-disk artifact is intact and
    the body matches the on-disk ``evidence_sha256``. Any
    other value indicates drift.
    """

    MATCH = "MATCH"
    ON_DISK_MISSING = "ON_DISK_MISSING"
    BYTES_UNREADABLE = "BYTES_UNREADABLE"
    EVIDENCE_FINGERPRINT_MISMATCH = "EVIDENCE_FINGERPRINT_MISMATCH"
    MANIFEST_FINGERPRINT_MISMATCH = "MANIFEST_FINGERPRINT_MISMATCH"


@dataclass(frozen=True)
class ArtifactVerificationReport:
    """A structured drift report for the research artifact.

    Attributes:
        kind: The drift kind. ``MATCH`` means the on-disk
            artifact is byte-identical to a freshly-hashed
            one AND the embedded manifest is intact.
        on_disk_path: The path to the artifact that was
            checked. ``None`` when the file does not exist.
        on_disk_fingerprint: The ``evidence_sha256`` parsed
            from the on-disk artifact. ``None`` when the file
            does not exist or the fingerprint is missing.
        reconstructed_fingerprint: The SHA-256 computed from
            the artifact's deterministic fields. ``None``
            when the artifact is unreadable.
        on_disk_size: The byte size of the on-disk artifact.
            ``None`` when the file does not exist.
    """

    kind: ArtifactDriftKind
    on_disk_path: Optional[str]
    on_disk_fingerprint: Optional[str]
    reconstructed_fingerprint: Optional[str]
    on_disk_size: Optional[int]

    @property
    def matches(self) -> bool:
        """True iff the on-disk artifact is intact and the
        body matches the on-disk ``evidence_sha256``."""
        return self.kind == ArtifactDriftKind.MATCH


def _sha(value: object) -> str:
    """[WORKFLOW-C.A5 2026-09-15] SHA-256 hex digest matching
    the ``intraday_spread_research._sha`` discipline (sort
    keys, no whitespace separators, ``default=str`` coercion).
    The deterministic fields may contain datetimes which
    ``default=str`` serializes.
    """
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()


def _recompute_evidence_fingerprint(artifact: Mapping[str, Any]) -> str:
    """[WORKFLOW-C.A5 2026-09-15] Reconstruct the canonical
    ``evidence_sha256`` from the artifact's deterministic
    fields.

    The ``build_research_artifact`` function builds a
    ``deterministic`` dict (excluding ``created_at`` and
    ``review_state``), hashes it to get ``evidence_sha256``,
    then attaches ``created_at`` and ``review_state`` as
    derived fields. To reconstruct the hash, we strip those
    two fields and hash the rest.

    The function is defensive: a malformed artifact (e.g.
    missing ``evidence_sha256`` field) returns an empty
    string so the verifier can surface a fingerprint
    mismatch rather than crashing.
    """
    deterministic = {key: value for key, value in artifact.items()
                      if key not in {"created_at", "review_state",
                                     "evidence_sha256", "artifact_sha256",
                                     "limitations"}}
    return _sha(deterministic)


def verify_research_artifact(artifact_path: Path) -> ArtifactVerificationReport:
    """Read the on-disk artifact and verify it against a
    fresh re-hash.

    Args:
        artifact_path: The path to the on-disk artifact JSON.

    Returns:
        ``ArtifactVerificationReport`` with the drift kind,
        on-disk fingerprint, reconstructed fingerprint, and
        byte size. The function NEVER raises on filesystem
        errors -- a missing or unreadable file degrades to
        ``ON_DISK_MISSING`` or ``BYTES_UNREADABLE``.

    The verification has two stages:
      1. Body fingerprint check. Recompute the canonical
         hash from the artifact's deterministic fields and
         compare to the on-disk ``evidence_sha256``. A
         mismatch means the body or the fingerprint was
         tampered with.
      2. Manifest fingerprint check. Re-hash the embedded
         ``manifest`` block and compare to its declared
         ``manifest_sha256``. A mismatch means the embedded
         run manifest was tampered with.

    Both stages must pass for ``kind == MATCH``. Either
    failing surfaces a distinct drift kind.
    """
    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        return ArtifactVerificationReport(
            kind=ArtifactDriftKind.ON_DISK_MISSING,
            on_disk_path=None,
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=None,
        )
    try:
        raw_bytes = artifact_path.read_bytes()
        on_disk_size = len(raw_bytes)
    except OSError:
        return ArtifactVerificationReport(
            kind=ArtifactDriftKind.BYTES_UNREADABLE,
            on_disk_path=str(artifact_path),
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=None,
        )
    try:
        artifact = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ArtifactVerificationReport(
            kind=ArtifactDriftKind.BYTES_UNREADABLE,
            on_disk_path=str(artifact_path),
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=on_disk_size,
        )
    if not isinstance(artifact, dict):
        return ArtifactVerificationReport(
            kind=ArtifactDriftKind.BYTES_UNREADABLE,
            on_disk_path=str(artifact_path),
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=on_disk_size,
        )

    # Stage 1: body fingerprint check.
    on_disk_fingerprint = artifact.get("evidence_sha256")
    reconstructed_fingerprint = _recompute_evidence_fingerprint(artifact)

    if (on_disk_fingerprint != reconstructed_fingerprint
            or not isinstance(on_disk_fingerprint, str)):
        return ArtifactVerificationReport(
            kind=ArtifactDriftKind.EVIDENCE_FINGERPRINT_MISMATCH,
            on_disk_path=str(artifact_path),
            on_disk_fingerprint=on_disk_fingerprint
                if isinstance(on_disk_fingerprint, str) else None,
            reconstructed_fingerprint=reconstructed_fingerprint,
            on_disk_size=on_disk_size,
        )

    # Stage 2: manifest fingerprint check. The artifact
    # embeds a predeclared run manifest with its own
    # ``manifest_sha256``. If the operator tampered with the
    # manifest body, the embedded hash will not match a
    # fresh re-hash.
    manifest = artifact.get("manifest")
    if isinstance(manifest, dict):
        manifest_body = {key: value for key, value in manifest.items()
                         if key != "manifest_sha256"}
        manifest_fingerprint = _sha(manifest_body)
        if manifest.get("manifest_sha256") != manifest_fingerprint:
            return ArtifactVerificationReport(
                kind=ArtifactDriftKind.MANIFEST_FINGERPRINT_MISMATCH,
                on_disk_path=str(artifact_path),
                on_disk_fingerprint=on_disk_fingerprint,
                reconstructed_fingerprint=reconstructed_fingerprint,
                on_disk_size=on_disk_size,
            )

    return ArtifactVerificationReport(
        kind=ArtifactDriftKind.MATCH,
        on_disk_path=str(artifact_path),
        on_disk_fingerprint=on_disk_fingerprint,
        reconstructed_fingerprint=reconstructed_fingerprint,
        on_disk_size=on_disk_size,
    )


__all__ = [
    "ArtifactDriftKind",
    "ArtifactVerificationReport",
    "verify_research_artifact",
]
