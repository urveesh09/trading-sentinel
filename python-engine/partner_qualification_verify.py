"""[WORKFLOW-C.A4 2026-09-15] Qualification criteria manifest drift verification.

The qualification criteria manifest is the frozen
predeclared contract that binds a deployed policy to a
disjoint training/holdout schedule. Operators must be
able to verify, in isolation, that an on-disk manifest
hasn't been tampered with -- without rebuilding the
qualification review package.

This module exposes ``verify_qualification_criteria_manifest``:
  - Reads the on-disk JSON.
  - Recomputes the ``criteria_manifest_sha256`` from the
    manifest body.
  - Reconstructs the canonical manifest from the manifest's
    fields via ``freeze_qualification_criteria`` (same
    function used by ``build_qualification_review_package``)
    and compares the reconstructed body to the on-disk body
    field-by-field.
  - Returns a structured ``ManifestVerificationReport`` with
    drift kind + byte size + reconstructed fingerprint.

The helper is pure / total / never raises on the happy
path. Malformed input degrades to a documented drift kind.
The CLI surface (added in ``research_cli``) reuses this
helper via subprocess; the helper is also importable for
in-process tests.

No new dependencies. Stdlib only (``json``, ``pathlib``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ManifestDriftKind(str, Enum):
    """The kind of drift detected by
    ``verify_qualification_criteria_manifest``.

    Mirrors the J.10.SUMMARY_VERIFY ``DiffKind`` enum so
    operators can compare drift types across surfaces.
    """

    MATCH = "MATCH"
    ON_DISK_MISSING = "ON_DISK_MISSING"
    MANIFEST_FINGERPRINT_MISMATCH = "MANIFEST_FINGERPRINT_MISMATCH"
    CRITERIA_NOT_RECONSTRUCTABLE = "CRITERIA_NOT_RECONSTRUCTABLE"
    BYTES_UNREADABLE = "BYTES_UNREADABLE"


@dataclass(frozen=True)
class ManifestVerificationReport:
    """A structured drift report for the qualification
    criteria manifest.

    Attributes:
        kind: The drift kind. ``MATCH`` means the on-disk
            manifest is byte-identical to a freshly-
            reconstructed one AND the body fingerprint
            matches the on-disk ``criteria_manifest_sha256``.
            Any other value indicates drift.
        on_disk_path: The path to the manifest that was
            checked. ``None`` when the file does not exist.
        on_disk_fingerprint: The
            ``criteria_manifest_sha256`` parsed from the
            on-disk manifest. ``None`` when the file does
            not exist or the fingerprint is missing.
        reconstructed_fingerprint: The SHA-256 computed
            from the on-disk body. ``None`` when the body
            is unreadable.
        on_disk_size: The byte size of the on-disk manifest.
            ``None`` when the file does not exist.
    """

    kind: ManifestDriftKind
    on_disk_path: Optional[str]
    on_disk_fingerprint: Optional[str]
    reconstructed_fingerprint: Optional[str]
    on_disk_size: Optional[int]

    @property
    def matches(self) -> bool:
        """True iff the on-disk manifest is intact and the
        body matches the on-disk fingerprint."""
        return self.kind == ManifestDriftKind.MATCH


def verify_qualification_criteria_manifest(
    manifest_path: Path,
) -> ManifestVerificationReport:
    """Read the on-disk manifest and verify it against a
    fresh reconstruction.

    Args:
        manifest_path: The path to the on-disk criteria
            manifest JSON.

    Returns:
        ``ManifestVerificationReport`` with the drift kind,
        on-disk fingerprint, reconstructed fingerprint, and
        byte size. The function NEVER raises on filesystem
        errors -- a missing or unreadable file degrades to
        ``ON_DISK_MISSING`` or ``BYTES_UNREADABLE``.

    The verification has two stages:
      1. Body fingerprint check. Recompute
         ``_sha(body)`` from the on-disk body (excluding
         the ``criteria_manifest_sha256`` field) and
         compare to the on-disk
         ``criteria_manifest_sha256``. A mismatch means
         the body or the fingerprint was tampered with.
      2. Reconstructability check. Re-run
         ``freeze_qualification_criteria`` from the
         manifest's declared fields and compare the
         reconstructed body to the on-disk body. A
         mismatch means the manifest has fields that
         ``freeze_qualification_criteria`` doesn't know
         how to produce (e.g. a manual edit added
         unsupported fields), OR the manifest's declared
         fields don't satisfy
         ``freeze_qualification_criteria``'s validation
         (frozen_at after first holdout, etc.).

    Both stages must pass for ``kind == MATCH``. Either
    failing surfaces a distinct drift kind.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return ManifestVerificationReport(
            kind=ManifestDriftKind.ON_DISK_MISSING,
            on_disk_path=None,
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=None,
        )
    try:
        raw_bytes = manifest_path.read_bytes()
        on_disk_size = len(raw_bytes)
    except OSError:
        return ManifestVerificationReport(
            kind=ManifestDriftKind.BYTES_UNREADABLE,
            on_disk_path=str(manifest_path),
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=None,
        )
    try:
        manifest = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ManifestVerificationReport(
            kind=ManifestDriftKind.BYTES_UNREADABLE,
            on_disk_path=str(manifest_path),
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=on_disk_size,
        )
    if not isinstance(manifest, dict):
        return ManifestVerificationReport(
            kind=ManifestDriftKind.BYTES_UNREADABLE,
            on_disk_path=str(manifest_path),
            on_disk_fingerprint=None,
            reconstructed_fingerprint=None,
            on_disk_size=on_disk_size,
        )

    # Lazy import: ``freeze_qualification_criteria`` and
    # ``_sha`` live in ``partner_qualification_review``;
    # importing at module top would create a cycle risk if
    # that module ever imports us.
    from partner_qualification_review import (
        _sha,
        freeze_qualification_criteria,
    )

    on_disk_fingerprint = manifest.get("criteria_manifest_sha256")
    body = {key: value for key, value in manifest.items()
            if key != "criteria_manifest_sha256"}
    reconstructed_fingerprint = _sha(body)

    if (on_disk_fingerprint != reconstructed_fingerprint
            or not isinstance(on_disk_fingerprint, str)):
        return ManifestVerificationReport(
            kind=ManifestDriftKind.MANIFEST_FINGERPRINT_MISMATCH,
            on_disk_path=str(manifest_path),
            on_disk_fingerprint=on_disk_fingerprint
                if isinstance(on_disk_fingerprint, str) else None,
            reconstructed_fingerprint=reconstructed_fingerprint,
            on_disk_size=on_disk_size,
        )

    # Stage 2: reconstructability. Re-run
    # ``freeze_qualification_criteria`` from the manifest's
    # declared fields and compare to the on-disk body.
    # Any exception (malformed declared coverage, bad
    # frozen_at, etc.) surfaces as
    # ``CRITERIA_NOT_RECONSTRUCTABLE``.
    try:
        from datetime import datetime
        frozen_at_raw = str(manifest.get("frozen_at", ""))
        frozen_at = datetime.fromisoformat(frozen_at_raw.replace("Z", "+00:00"))
        declared_coverage = [
            (item["underlying"], item["policy_id"], item["session_date"])
            for item in manifest.get("declared_coverage", ())
        ]
        # The ``criteria`` block is a plain dict in the
        # manifest. ``freeze_qualification_criteria`` takes
        # a ``QualificationCriteria`` dataclass -- we have
        # to reconstruct it from the on-disk fields.
        from partner_qualification_review import QualificationCriteria
        criteria_dict = manifest.get("criteria", {})
        criteria = QualificationCriteria(
            policy_sha256=str(criteria_dict["policy_sha256"]),
            min_covered_sessions=int(criteria_dict["min_covered_sessions"]),
            min_closed_outcomes=int(criteria_dict["min_closed_outcomes"]),
            max_unresolved_outcomes=int(criteria_dict["max_unresolved_outcomes"]),
            max_drawdown_rs=float(criteria_dict["max_drawdown_rs"]),
            stressed_fee_multiplier=float(criteria_dict["stressed_fee_multiplier"]),
            stressed_slippage_bps=float(criteria_dict["stressed_slippage_bps"]),
        )
        reconstructed = freeze_qualification_criteria(
            criteria=criteria,
            underlying=str(manifest.get("underlying")),
            training_sessions=manifest.get("training_sessions", ()),
            holdout_sessions=manifest.get("holdout_sessions", ()),
            declared_coverage=declared_coverage,
            frozen_at=frozen_at,
        )
        # The reconstructed dict is the canonical form. The
        # on-disk body MUST equal it (including the
        # reconstructed fingerprint). Any field-level
        # mismatch means a manual edit added/removed a
        # field, OR a field was rewritten to a value that
        # ``freeze_qualification_criteria`` doesn't
        # produce.
        reconstructed_body = {key: value for key, value in reconstructed.items()
                              if key != "criteria_manifest_sha256"}
        if reconstructed_body != body:
            return ManifestVerificationReport(
                kind=ManifestDriftKind.CRITERIA_NOT_RECONSTRUCTABLE,
                on_disk_path=str(manifest_path),
                on_disk_fingerprint=on_disk_fingerprint,
                reconstructed_fingerprint=reconstructed_fingerprint,
                on_disk_size=on_disk_size,
            )
    except (KeyError, TypeError, ValueError):
        return ManifestVerificationReport(
            kind=ManifestDriftKind.CRITERIA_NOT_RECONSTRUCTABLE,
            on_disk_path=str(manifest_path),
            on_disk_fingerprint=on_disk_fingerprint,
            reconstructed_fingerprint=reconstructed_fingerprint,
            on_disk_size=on_disk_size,
        )

    return ManifestVerificationReport(
        kind=ManifestDriftKind.MATCH,
        on_disk_path=str(manifest_path),
        on_disk_fingerprint=on_disk_fingerprint,
        reconstructed_fingerprint=reconstructed_fingerprint,
        on_disk_size=on_disk_size,
    )


__all__ = [
    "ManifestDriftKind",
    "ManifestVerificationReport",
    "verify_qualification_criteria_manifest",
]
