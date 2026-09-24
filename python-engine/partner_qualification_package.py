"""Bounded assembly of reviewed full-policy research evidence.

This is deliberately an *artifact builder*, not an approval, registry or
delivery API.  It can only package independently supplied, already-approved
review identity and immutable replay evidence.  The normal registry and final
dispatch paths continue to call :mod:`partner_qualification_authority`.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from partner_qualification_authority import MAX_PACKAGE_BYTES, verify_authorization_package
from partner_qualification_review import QualificationCriteria, build_qualification_review_package


MAX_SOURCE_REPORTS = 128
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 12 * 1024 * 1024


def _clock(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    try:
        clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return clock


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       default=str, allow_nan=False).encode("utf-8")).hexdigest()


def _package_bytes(value: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_PACKAGE_BYTES:
        raise ValueError("assembled authorization package exceeds size limit")
    return encoded


def _load_json(path: Path, *, limit: int = MAX_INPUT_BYTES) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"research input is unavailable: {path.name}") from exc
    if len(raw) > limit:
        raise ValueError(f"research input exceeds size limit: {path.name}")
    try:
        value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"research input is invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"research input must be a JSON object: {path.name}")
    return value


def resolve_evidence_path(root: str | Path, relative_path: str) -> Path:
    """Resolve a declared evidence name strictly inside a declared root."""
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("evidence path is required")
    base = Path(root).resolve()
    candidate = (base / relative_path).resolve()
    if not base.is_dir() or not candidate.is_relative_to(base) or candidate == base:
        raise ValueError("evidence path must remain inside evidence root")
    return candidate


def read_bounded_evidence(root: str | Path, relative_path: str, *, limit: int = MAX_INPUT_BYTES) -> dict[str, Any]:
    return _load_json(resolve_evidence_path(root, relative_path), limit=limit)


def _validate_scope(*, underlying: str, structure_kind: str, horizon: str, policy_version: str) -> None:
    if underlying not in {"NIFTY", "SENSEX"}:
        raise ValueError("only NIFTY or SENSEX qualification packages are supported")
    if structure_kind != "DIRECTIONAL_DEBIT_SPREAD" or horizon != "INTRADAY":
        raise ValueError("only intraday directional debit-spread qualification is supported")
    if not policy_version.strip():
        raise ValueError("policy version is required")


def _validate_review_identity(review: Mapping[str, Any], *, now: datetime) -> tuple[dict[str, Any], datetime]:
    allowed = {"operator", "decision", "reviewed_at"}
    if set(review) != allowed or review.get("decision") != "APPROVED":
        raise ValueError("an externally supplied APPROVED review identity is required")
    operator = review.get("operator")
    if not isinstance(operator, str) or not operator.strip() or len(operator) > 256:
        raise ValueError("review identity requires a bounded operator name")
    reviewed = _clock(review.get("reviewed_at"), "reviewed_at")
    if reviewed > now:
        raise ValueError("review identity cannot be future dated")
    return {"operator": operator.strip(), "decision": "APPROVED", "reviewed_at": reviewed.isoformat()}, reviewed


def _validate_validity_period(value: Mapping[str, Any], *, reviewed_at: datetime, now: datetime) -> dict[str, str]:
    if set(value) != {"start", "end"}:
        raise ValueError("validity period requires only start and end")
    start = _clock(value.get("start"), "validity start")
    end = _clock(value.get("end"), "validity end")
    if not reviewed_at <= start <= now < end or end - reviewed_at > timedelta(days=30):
        raise ValueError("validity period is invalid, expired or exceeds 30 days")
    return {"start": start.isoformat(), "end": end.isoformat()}


def build_authorization_package(*, underlying: str, structure_kind: str, horizon: str,
                                policy_version: str, policy_manifest: Mapping[str, Any],
                                criteria_manifest: Mapping[str, Any], heldout_report: Mapping[str, Any],
                                source_reports: Sequence[Mapping[str, Any]], review_identity: Mapping[str, Any],
                                validity_period: Mapping[str, Any], readiness: Mapping[str, Any] | None,
                                now: datetime | None = None) -> dict[str, Any]:
    """Rebuild and bound a package; never writes a registry or sends advice.

    ``source_reports`` contains complete replay JSON and the immutable signal
    artifact digest supplied alongside it.  The held-out aggregate is rebuilt
    from those reports rather than trusted from a hand-authored summary.
    """
    from intraday_spread_holdout import build_heldout_comparison, heldout_case_from_full_policy_report
    from partner_manual_advisory import PartnerAdvisoryProfile

    _validate_scope(underlying=underlying, structure_kind=structure_kind, horizon=horizon,
                    policy_version=policy_version)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("package build clock must be timezone-aware")
    if not isinstance(policy_manifest, Mapping) or not isinstance(criteria_manifest, Mapping):
        raise ValueError("policy and criteria manifests are required")
    if not isinstance(heldout_report, Mapping) or not isinstance(readiness or {}, Mapping):
        raise ValueError("heldout report and readiness must be objects")
    if not isinstance(source_reports, Sequence) or isinstance(source_reports, (str, bytes)) or not source_reports:
        raise ValueError("at least one full-policy source report is required")
    if len(source_reports) > MAX_SOURCE_REPORTS:
        raise ValueError("too many source reports for one qualification package")

    review, reviewed_at = _validate_review_identity(review_identity, now=now)
    validity = _validate_validity_period(validity_period, reviewed_at=reviewed_at, now=now)
    policy = str(policy_manifest.get("policy_sha256", ""))
    if policy_manifest.get("underlying") != underlying or not policy:
        raise ValueError("policy manifest scope is incompatible")
    if criteria_manifest.get("underlying") != underlying or criteria_manifest.get("policy_sha256") != policy:
        raise ValueError("criteria manifest scope is incompatible")
    criteria_body = {key: value for key, value in criteria_manifest.items() if key != "criteria_manifest_sha256"}
    if _sha(criteria_body) != criteria_manifest.get("criteria_manifest_sha256"):
        raise ValueError("criteria manifest fingerprint mismatch")
    try:
        criteria = QualificationCriteria(**dict(criteria_manifest["criteria"]))
    except (KeyError, TypeError) as exc:
        raise ValueError("criteria manifest is malformed") from exc

    normalized_reports: list[dict[str, Any]] = []
    cases = []
    seen_reports: set[str] = set()
    for item in source_reports:
        if not isinstance(item, Mapping) or set(item) != {"report", "signal_artifact_sha256"}:
            raise ValueError("source report entry is malformed")
        report = item["report"]
        artifact = item["signal_artifact_sha256"]
        if not isinstance(report, Mapping) or not isinstance(artifact, str):
            raise ValueError("source report entry is malformed")
        digest = report.get("evidence_sha256")
        if not isinstance(digest, str) or digest in seen_reports:
            raise ValueError("source reports must have unique immutable evidence")
        seen_reports.add(digest)
        manifest = report.get("manifest")
        if (not isinstance(manifest, Mapping) or manifest.get("underlying") != underlying
                or manifest.get("policy_sha256") != policy
                or manifest.get("frozen_policy") != policy_manifest.get("frozen_policy")):
            raise ValueError("source report policy identity is incompatible")
        case = heldout_case_from_full_policy_report(report, signal_artifact_sha256=artifact)
        cases.append(case)
        normalized_reports.append({"report": dict(report), "signal_artifact_sha256": artifact.lower()})

    try:
        declared = [(item["underlying"], item["policy_id"], item["session_date"])
                    for item in heldout_report["declared_coverage"]]
        rebuilt_heldout = build_heldout_comparison(
            dataset_sha256=heldout_report["dataset_sha256"], code_revision=heldout_report["code_revision"],
            training_sessions=heldout_report["training_sessions"], holdout_sessions=heldout_report["holdout_sessions"],
            declared_coverage=declared, cases=cases,
            review_criteria_sha256=criteria_manifest["criteria_manifest_sha256"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("heldout evidence cannot be rebuilt from source reports") from exc
    if dict(rebuilt_heldout) != dict(heldout_report):
        raise ValueError("heldout report differs from reconstructed source reports")
    if max(rebuilt_heldout["holdout_sessions"]) >= reviewed_at.date().isoformat():
        raise ValueError("review must follow every completed holdout session")
    review_package = build_qualification_review_package(
        policy_manifest=policy_manifest, criteria=criteria, heldout_report=rebuilt_heldout,
        readiness=dict(readiness or {}), criteria_manifest=criteria_manifest,
    )
    row = review_package.get("per_index", [{}])[0]
    if (review_package.get("review_state") != "HUMAN_REVIEW_REQUIRED"
            or row.get("review_state") != "READY_FOR_HUMAN_REVIEW" or row.get("blockers")):
        raise ValueError("qualification evidence is not ready for independent human review")
    package = {
        "format": "partner_advisory_authorization_v1", "underlying": underlying,
        "structure_kind": structure_kind, "horizon": horizon, "policy_version": policy_version,
        "policy_manifest": dict(policy_manifest), "criteria_manifest": dict(criteria_manifest),
        "heldout_report": dict(rebuilt_heldout), "source_reports": normalized_reports,
        "review_identity": review, "validity_period": validity,
    }
    data = _package_bytes(package)
    try:
        raw_profile = policy_manifest["frozen_policy"]["profile"]
        profile = PartnerAdvisoryProfile(**dict(raw_profile))
    except (KeyError, TypeError) as exc:
        raise ValueError("policy manifest profile is required for authority verification") from exc
    # Final local proof: the exact bytes already meet the same current code,
    # configuration, scope and human-review contract enforced at registration.
    verify_authorization_package(data, hashlib.sha256(data).hexdigest(), underlying=underlying,
                                 structure_kind=structure_kind, horizon=horizon,
                                 policy_version=policy_version, profile=profile, now=now)
    return package


def write_authorization_package(path: str | Path, package: Mapping[str, Any]) -> str:
    """Atomically create an immutable package, permitting identical retries."""
    target = Path(path)
    data = _package_bytes(package)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".qualification-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError("qualification package destination already contains different evidence")
    finally:
        os.unlink(temporary)
    return hashlib.sha256(data).hexdigest()


def build_package_from_evidence_manifest(*, evidence_root: str | Path, manifest_path: str,
                                         criteria_path: str, heldout_path: str, review_path: str,
                                         validity_path: str, readiness_path: str | None,
                                         underlying: str, structure_kind: str, horizon: str,
                                         policy_version: str, now: datetime | None = None) -> dict[str, Any]:
    """Load only root-confined, bounded evidence named by an operator manifest."""
    evidence = read_bounded_evidence(evidence_root, manifest_path)
    if set(evidence) != {"policy_manifest", "source_reports"}:
        raise ValueError("evidence manifest requires policy_manifest and source_reports only")
    rows = evidence["source_reports"]
    if not isinstance(rows, list) or not rows or len(rows) > MAX_SOURCE_REPORTS:
        raise ValueError("evidence manifest source report list is invalid")
    total = 0
    source_reports = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "signal_artifact_sha256"}:
            raise ValueError("evidence manifest source report entry is invalid")
        path = resolve_evidence_path(evidence_root, row["path"])
        total += path.stat().st_size if path.exists() else 0
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError("source reports exceed aggregate size limit")
        source_reports.append({"report": _load_json(path), "signal_artifact_sha256": row["signal_artifact_sha256"]})
    return build_authorization_package(
        underlying=underlying, structure_kind=structure_kind, horizon=horizon, policy_version=policy_version,
        policy_manifest=evidence["policy_manifest"], criteria_manifest=read_bounded_evidence(evidence_root, criteria_path),
        heldout_report=read_bounded_evidence(evidence_root, heldout_path), source_reports=source_reports,
        review_identity=read_bounded_evidence(evidence_root, review_path),
        validity_period=read_bounded_evidence(evidence_root, validity_path),
        readiness=read_bounded_evidence(evidence_root, readiness_path) if readiness_path else {}, now=now,
    )


__all__ = ["MAX_INPUT_BYTES", "MAX_SOURCE_REPORTS", "MAX_TOTAL_SOURCE_BYTES",
           "build_authorization_package", "build_package_from_evidence_manifest",
           "read_bounded_evidence", "resolve_evidence_path", "write_authorization_package"]
