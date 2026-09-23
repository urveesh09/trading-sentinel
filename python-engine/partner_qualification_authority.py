"""Read-only verification of reviewed evidence at each advisory authority boundary.

Registration is not authority. An artifact must reproduce the existing heldout
and review contracts, bind current code/config/profile, and carry a dated human
approval. No configuration switch bypasses these delivery requirements.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from config import settings
from policy_identity import module_sha256s

MAX_PACKAGE_BYTES = 16 * 1024 * 1024


def read_artifact(dataset_ref: str) -> bytes:
    root = Path(settings.PARTNER_ARTIFACT_ROOT).resolve()
    path = (root / dataset_ref).resolve()
    if not dataset_ref.strip() or not path.is_relative_to(root) or path == root:
        raise ValueError("research artifact must be inside PARTNER_ARTIFACT_ROOT")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_PACKAGE_BYTES + 1)
    except OSError as exc:
        raise ValueError("research artifact is unavailable") from exc
    if len(data) > MAX_PACKAGE_BYTES:
        raise ValueError("research artifact exceeds size limit")
    return data


def _clock(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("qualification clocks must be timezone-aware")
    return parsed


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    default=str, allow_nan=False).encode()).hexdigest()


def policy_configuration():
    """Same semantic configuration projection as the frozen policy producer."""
    return {key: value for key, value in settings.model_dump().items()
            if key.startswith(("FNO_", "PARTNER_MANUAL_ADVISORY_"))
            and not any(word in key for word in ("TOKEN", "SECRET", "PASSWORD", "KEY"))}


def verify_authorization_package(data: bytes, sha256: str, *, underlying: str,
                                 structure_kind: str, horizon: str, policy_version: str,
                                 profile, now: datetime, reviewed_at: datetime | None = None) -> dict:
    """Raise ValueError unless the report is currently usable for this profile."""
    from intraday_spread_holdout import build_heldout_comparison, heldout_case_from_full_policy_report
    from partner_qualification_review import QualificationCriteria, build_qualification_review_package

    try:
        if len(data) > MAX_PACKAGE_BYTES or hashlib.sha256(data).hexdigest() != sha256.lower():
            raise ValueError("research artifact fingerprint mismatch")
        value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if value.get("format") != "partner_advisory_authorization_v1":
            raise ValueError("verified advisory authorization package required")
        if (value["underlying"], value["structure_kind"], value["horizon"], value["policy_version"]) != (
                underlying, structure_kind, horizon, policy_version):
            raise ValueError("qualification package scope mismatch")
        now = _clock(now)
        review = value["review_identity"]
        reviewed = _clock(review["reviewed_at"])
        start, end = (_clock(value["validity_period"][key]) for key in ("start", "end"))
        if (review.get("decision") != "APPROVED" or not str(review.get("operator", "")).strip()
                or not reviewed <= start <= now < end or end - reviewed > timedelta(days=30)
                or (reviewed_at is not None and reviewed != reviewed_at)):
            raise ValueError("qualification review or validity is invalid/expired")
        manifest = value["policy_manifest"]
        frozen = manifest["frozen_policy"]
        if (frozen["source_sha256"] != module_sha256s(Path(__file__).parent)
                or frozen["configuration"] != policy_configuration()
                or _digest(frozen["profile"]) != _digest(asdict(profile))
                or frozen["underlying"] != underlying or frozen["structure_kind"] != structure_kind
                or _digest({k: v for k, v in frozen.items() if k != "manifest_sha256"}) != frozen["manifest_sha256"]
                or manifest["policy_sha256"] != frozen["manifest_sha256"]):
            raise ValueError("qualification policy/code/config/profile is incompatible")
        criteria_manifest = value["criteria_manifest"]
        heldout = value["heldout_report"]
        if max(heldout["holdout_sessions"]) >= reviewed.date().isoformat():
            raise ValueError("qualification review must follow completed holdout sessions")
        reports = value["source_reports"]
        if not isinstance(reports, list) or not reports:
            raise ValueError("full-policy source reports required")
        cases = [heldout_case_from_full_policy_report(item["report"],
                 signal_artifact_sha256=item["signal_artifact_sha256"]) for item in reports]
        reconstructed = build_heldout_comparison(
            dataset_sha256=heldout["dataset_sha256"], code_revision=heldout["code_revision"],
            training_sessions=heldout["training_sessions"], holdout_sessions=heldout["holdout_sessions"],
            declared_coverage=[(r["underlying"], r["policy_id"], r["session_date"]) for r in heldout["declared_coverage"]],
            cases=cases, review_criteria_sha256=criteria_manifest["criteria_manifest_sha256"])
        if reconstructed != heldout:
            raise ValueError("heldout report differs from verified source outcomes")
        package = build_qualification_review_package(policy_manifest=manifest,
            criteria=QualificationCriteria(**criteria_manifest["criteria"]),
            heldout_report=reconstructed, readiness=value.get("readiness", {}), criteria_manifest=criteria_manifest)
        rows = package["per_index"]
        if (len(rows) != 1 or rows[0]["underlying"] != underlying or rows[0]["blockers"]
                or rows[0]["review_state"] != "READY_FOR_HUMAN_REVIEW"
                or rows[0]["net_pnl_rs"] <= 0 or (rows[0]["stressed_net_pnl_rs"] or 0) <= 0):
            raise ValueError("qualification evidence is insufficient or fails net/stressed economics")
        return {"valid_until": end.isoformat(), "reviewed_at": reviewed.isoformat(),
                "report_sha256": sha256.lower(), "review_package_sha256": package["evidence_sha256"]}
    except (KeyError, TypeError, AttributeError, OverflowError, json.JSONDecodeError) as exc:
        raise ValueError("malformed qualification authorization package") from exc
