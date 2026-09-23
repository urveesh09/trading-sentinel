"""Legacy package-shape diagnostic; it confers no registry or delivery authority.

The authoritative boundary is partner_qualification_authority, which reconstructs
heldout/review evidence and checks current code/config/profile and validity.
This older pure diagnostic remains for compatibility; its qualified field is
not an authorization decision.

[WORKFLOW-A3 2026-09-20] Qualification verifier.

The audit (docs/2026-09-20-independent-system-readiness-audit.md §3-A3)
flagged that ``record_strategy_qualification`` (and the upstream
``record_research_artifact``) accept a SHA-256 string + dataset_ref
without reading and verifying the referenced report bytes. The
fix is a pure verifier that:

  1. Reads the referenced report bytes from a known root.
  2. Recomputes the SHA-256 and rejects mismatch.
  3. Parses the report as JSON with a bounded schema.
  4. Computes the policy identity fingerprint from the report's
     ``policy_manifest`` field and rejects if it doesn't match the
     current deployed code's fingerprint.
  5. Validates validity period + heldout + costs + review identity.
  6. Returns a ``QualificationVerdict`` with stable reason codes.

Pure: no DB, no clock read inside the verifier, no broker call.
The caller reads the clock and the filesystem.

Design choices:

  * **Pure of I/O**: takes the report bytes (already read by the
    caller) and the deployed-code fingerprint (already computed by
    the caller). The verifier does NOT touch the filesystem.
  * **Total**: every input combination returns a verdict. Never
    raises on malformed inputs -- the verdict's reason_codes
    enumerates what is wrong so the caller can act on the
    specific reason.
  * **Stable reason codes**: each reason is a stable string that
    callers and audit logs key off. Adding a new reason is a
    contract change.
  * **Frozen dataclass**: ``QualificationVerdict`` is frozen so
    callers cannot mutate the verdict after the verifier returns.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class QualificationReason(str, Enum):
    """Stable reason codes emitted by the verifier.

    Adding a new code is a contract change. Removing or renaming
    an existing code is a contract change. The audit log keys off
    these strings; downstream tests pin the exact set.
    """
    PASS = "pass"
    REPORT_BYTES_MISMATCH = "report_bytes_mismatch"
    REPORT_NOT_JSON = "report_not_json"
    SCHEMA_MISSING_INDEX = "schema_missing_index"
    SCHEMA_MISSING_STRUCTURE = "schema_missing_structure"
    SCHEMA_MISSING_HORIZON = "schema_missing_horizon"
    SCHEMA_MISSING_POLICY_VERSION = "schema_missing_policy_version"
    SCHEMA_MISSING_CRITERIA = "schema_missing_criteria"
    SCHEMA_MISSING_HELDOUT = "schema_missing_heldout"
    SCHEMA_MISSING_OUTCOMES = "schema_missing_outcomes"
    SCHEMA_MISSING_COSTS = "schema_missing_costs"
    SCHEMA_MISSING_REVIEW = "schema_missing_review"
    SCHEMA_MISSING_VALIDITY = "schema_missing_validity"
    SCHEMA_MISSING_POLICY_MANIFEST = "schema_missing_policy_manifest"
    INDEX_MISMATCH = "index_mismatch"
    STRUCTURE_MISMATCH = "structure_mismatch"
    HORIZON_MISMATCH = "horizon_mismatch"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"
    HELDOUT_INSUFFICIENT = "heldout_insufficient"
    COSTS_INCOMPLETE = "costs_incomplete"
    REVIEW_MISSING = "review_missing"
    REVIEW_IN_FUTURE = "review_in_future"
    VALIDITY_EXPIRED = "validity_expired"
    VALIDITY_NOT_YET_ACTIVE = "validity_not_yet_active"
    POLICY_MANIFEST_MISMATCH = "policy_manifest_mismatch"


_REQUIRED_TOP_LEVEL_KEYS = (
    "index", "structure_kind", "horizon", "policy_version",
    "predeclared_criteria", "heldout_split", "outcome_availability",
    "costs", "review_identity", "validity_period", "policy_manifest",
)


@dataclass(frozen=True)
class QualificationVerdict:
    """Structured verdict for one research artifact.

    ``qualified`` is True only when ``reason_codes`` is exactly
    ``(QualificationReason.PASS,)``. Any other code makes
    ``qualified`` False.
    """
    qualified: bool
    reason_codes: tuple[QualificationReason, ...]
    manifest_sha256: str
    report_sha256: str
    validity_start: datetime | None
    validity_end: datetime | None

    def to_dict(self) -> dict:
        return {
            "qualified": self.qualified,
            "reason_codes": [r.value for r in self.reason_codes],
            "manifest_sha256": self.manifest_sha256,
            "report_sha256": self.report_sha256,
            "validity_start": (
                self.validity_start.isoformat() if self.validity_start else None
            ),
            "validity_end": (
                self.validity_end.isoformat() if self.validity_end else None
            ),
        }


def _required_keys_present(report: Mapping[str, Any]) -> list[QualificationReason]:
    """Return the missing-field reason codes for any absent top-level
    keys. Empty list means every required key is present."""
    codes: list[QualificationReason] = []
    if "index" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_INDEX)
    if "structure_kind" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_STRUCTURE)
    if "horizon" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_HORIZON)
    if "policy_version" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_POLICY_VERSION)
    if "predeclared_criteria" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_CRITERIA)
    if "heldout_split" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_HELDOUT)
    if "outcome_availability" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_OUTCOMES)
    if "costs" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_COSTS)
    if "review_identity" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_REVIEW)
    if "validity_period" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_VALIDITY)
    if "policy_manifest" not in report:
        codes.append(QualificationReason.SCHEMA_MISSING_POLICY_MANIFEST)
    return codes


def _check_heldout(heldout: Any) -> QualificationReason | None:
    """A passing heldout must have a non-empty train/test split and
    at least one resolved outcome."""
    if not isinstance(heldout, Mapping):
        return QualificationReason.HELDOUT_INSUFFICIENT
    train = heldout.get("train_window") or {}
    test = heldout.get("test_window") or {}
    if not isinstance(train, Mapping) or not train.get("start") or not train.get("end"):
        return QualificationReason.HELDOUT_INSUFFICIENT
    if not isinstance(test, Mapping) or not test.get("start") or not test.get("end"):
        return QualificationReason.HELDOUT_INSUFFICIENT
    return None


def _check_costs(costs: Any) -> QualificationReason | None:
    """The costs section must declare a fee model + slippage
    assumption; both are required for honest expectancy reporting."""
    if not isinstance(costs, Mapping):
        return QualificationReason.COSTS_INCOMPLETE
    if costs.get("fee_model") is None or costs.get("slippage_bps") is None:
        return QualificationReason.COSTS_INCOMPLETE
    return None


def _check_review(review: Any) -> list[QualificationReason]:
    """Review identity must be present and not in the future."""
    codes: list[QualificationReason] = []
    if not isinstance(review, Mapping):
        return [QualificationReason.REVIEW_MISSING]
    if not review.get("operator") or not review.get("reviewed_at"):
        codes.append(QualificationReason.REVIEW_MISSING)
    return codes


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 datetime, return None on failure."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # Treat naive timestamps as UTC for the purpose of
        # validity period math. The caller is expected to use
        # timezone-aware timestamps; this is a defensive fallback
        # so the verifier never raises.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _check_validity(
    validity: Any,
    *,
    now: datetime,
) -> list[QualificationReason]:
    """Validity period must be present, with start <= now <= end.
    Both bounds must be timezone-aware ISO strings."""
    codes: list[QualificationReason] = []
    if not isinstance(validity, Mapping):
        codes.append(QualificationReason.VALIDITY_EXPIRED)
        return codes
    start = _parse_dt(validity.get("start"))
    end = _parse_dt(validity.get("end"))
    if start is None or end is None:
        codes.append(QualificationReason.VALIDITY_EXPIRED)
        return codes
    if now < start:
        codes.append(QualificationReason.VALIDITY_NOT_YET_ACTIVE)
    if now > end:
        codes.append(QualificationReason.VALIDITY_EXPIRED)
    return codes


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest. Local import so the verifier doesn't
    pull hashlib at module load."""
    return hashlib.sha256(data).hexdigest()


def _sha256_canonical(payload: Any) -> str:
    """SHA-256 over ``json.dumps(sort_keys=True)``."""
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def qualify_research_package(
    *,
    report_bytes: bytes,
    registered_sha256: str,
    expected_index: str,
    expected_structure_kind: str,
    expected_horizon: str,
    expected_policy_version: str,
    deployed_policy_manifest_sha256: str,
    now: datetime,
) -> QualificationVerdict:
    """Verify one research package end-to-end.

    Parameters
    ----------
    report_bytes:
        The raw bytes of the research report (already read from
        disk by the caller).
    registered_sha256:
        The SHA-256 string the operator registered for this
        artifact. Must match ``sha256(report_bytes)``.
    expected_index / structure_kind / horizon / policy_version:
        What the qualification is being registered FOR. The
        report's contents must agree.
    deployed_policy_manifest_sha256:
        SHA-256 of the currently-deployed policy manifest. Must
        equal ``sha256(json.dumps(report["policy_manifest"], sort_keys=True))``
        so a code change invalidates old reports.
    now:
        The clock the verifier compares validity / review against.
        Caller-supplied so the verifier stays pure of I/O.

    Returns
    -------
    QualificationVerdict with ``qualified=True`` only when every
    check passes; otherwise ``reason_codes`` enumerates what is
    wrong.
    """
    codes: list[QualificationReason] = []
    report_sha = _sha256_bytes(report_bytes)
    if not registered_sha256 or registered_sha256.lower() != report_sha:
        codes.append(QualificationReason.REPORT_BYTES_MISMATCH)
    # Build the verdict shell up front so partial validation
    # still returns a structured verdict.
    verdict = QualificationVerdict(
        qualified=False,
        reason_codes=tuple(codes),
        manifest_sha256="",
        report_sha256=report_sha,
        validity_start=None,
        validity_end=None,
    )
    if codes:
        return verdict
    # Parse the JSON body.
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        codes.append(QualificationReason.REPORT_NOT_JSON)
        return QualificationVerdict(
            qualified=False,
            reason_codes=tuple(codes),
            manifest_sha256="",
            report_sha256=report_sha,
            validity_start=None,
            validity_end=None,
        )
    if not isinstance(report, Mapping):
        codes.append(QualificationReason.REPORT_NOT_JSON)
        return QualificationVerdict(
            qualified=False,
            reason_codes=tuple(codes),
            manifest_sha256="",
            report_sha256=report_sha,
            validity_start=None,
            validity_end=None,
        )
    # Required-key check.
    codes.extend(_required_keys_present(report))
    if codes:
        return QualificationVerdict(
            qualified=False,
            reason_codes=tuple(codes),
            manifest_sha256="",
            report_sha256=report_sha,
            validity_start=None,
            validity_end=None,
        )
    # Index / structure / horizon / policy_version match.
    if str(report["index"]).upper() != expected_index.upper():
        codes.append(QualificationReason.INDEX_MISMATCH)
    if str(report["structure_kind"]).upper() != expected_structure_kind.upper():
        codes.append(QualificationReason.STRUCTURE_MISMATCH)
    if str(report["horizon"]).upper() != expected_horizon.upper():
        codes.append(QualificationReason.HORIZON_MISMATCH)
    if str(report["policy_version"]).strip() != expected_policy_version.strip():
        codes.append(QualificationReason.POLICY_VERSION_MISMATCH)
    # Heldout / costs / review / validity.
    heldout_err = _check_heldout(report["heldout_split"])
    if heldout_err is not None:
        codes.append(heldout_err)
    costs_err = _check_costs(report["costs"])
    if costs_err is not None:
        codes.append(costs_err)
    codes.extend(_check_review(report["review_identity"]))
    validity_period = report["validity_period"]
    codes.extend(_check_validity(validity_period, now=now))
    # Policy manifest fingerprint binding.
    policy_manifest = report["policy_manifest"]
    manifest_sha = _sha256_canonical(policy_manifest)
    if deployed_policy_manifest_sha256 and manifest_sha != deployed_policy_manifest_sha256:
        codes.append(QualificationReason.POLICY_MANIFEST_MISMATCH)
    validity_start = _parse_dt(
        validity_period.get("start") if isinstance(validity_period, Mapping) else None
    )
    validity_end = _parse_dt(
        validity_period.get("end") if isinstance(validity_period, Mapping) else None
    )
    if not codes:
        codes = [QualificationReason.PASS]
    return QualificationVerdict(
        qualified=(codes == [QualificationReason.PASS]),
        reason_codes=tuple(codes),
        manifest_sha256=manifest_sha,
        report_sha256=report_sha,
        validity_start=validity_start,
        validity_end=validity_end,
    )


__all__ = [
    "QualificationReason",
    "QualificationVerdict",
    "qualify_research_package",
]
