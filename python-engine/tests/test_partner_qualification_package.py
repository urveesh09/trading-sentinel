import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from partner_manual_advisory import PartnerAdvisoryProfile
from partner_qualification_authority import verify_authorization_package
from partner_qualification_package import (build_authorization_package,
                                           build_package_from_evidence_manifest,
                                           write_authorization_package)
from research_cli import main
from tests.qualification_package_fixture import authorization_package


SCOPE = dict(underlying="NIFTY", structure_kind="DIRECTIONAL_DEBIT_SPREAD",
             horizon="INTRADAY", policy_version="partner-manual-intraday-v1")


def _fixture_inputs(tmp_path, now):
    profile = PartnerAdvisoryProfile(holding_period="INTRADAY")
    package = authorization_package(profile, now)
    root = tmp_path / "evidence"
    root.mkdir(parents=True)
    report_path = root / "report.json"
    report_path.write_text(json.dumps(package["source_reports"][0]["report"]), encoding="utf-8")
    for name, value in {
        "criteria.json": package["criteria_manifest"],
        "heldout.json": package["heldout_report"],
        "review.json": package["review_identity"],
        "validity.json": package["validity_period"],
        "readiness.json": {"collection": "READY", "causal_research": "READY"},
        "manifest.json": {
            "policy_manifest": package["policy_manifest"],
            "source_reports": [{"path": "report.json",
                                "signal_artifact_sha256": package["source_reports"][0]["signal_artifact_sha256"]}],
        },
    }.items():
        (root / name).write_text(json.dumps(value), encoding="utf-8")
    return root, profile, package


def test_builder_reconstructs_real_authority_envelope(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root, profile, _ = _fixture_inputs(tmp_path, now)
    package = build_package_from_evidence_manifest(
        evidence_root=root, manifest_path="manifest.json", criteria_path="criteria.json",
        heldout_path="heldout.json", review_path="review.json", validity_path="validity.json",
        readiness_path="readiness.json", now=now, **SCOPE)
    data = json.dumps(package, sort_keys=True, separators=(",", ":")).encode("utf-8")
    verified = verify_authorization_package(data, hashlib.sha256(data).hexdigest(),
                                            profile=profile, now=now, **SCOPE)
    assert verified["report_sha256"] == hashlib.sha256(data).hexdigest()
    assert package["source_reports"][0]["report"]["format"] == "partner_full_policy_replay_v1"
    assert "readiness" not in package  # informational input is not authority.


@pytest.mark.parametrize("fault", ["tampered_report", "pending_review", "wrong_heldout"])
def test_builder_rejects_invalid_evidence_without_output(tmp_path, fault):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root, _, _ = _fixture_inputs(tmp_path, now)
    if fault == "tampered_report":
        value = json.loads((root / "report.json").read_text())
        value["state"] = "UNRESOLVED"
        (root / "report.json").write_text(json.dumps(value), encoding="utf-8")
    elif fault == "pending_review":
        value = json.loads((root / "review.json").read_text())
        value["decision"] = "PENDING"
        (root / "review.json").write_text(json.dumps(value), encoding="utf-8")
    else:
        value = json.loads((root / "heldout.json").read_text())
        value["groups"][0]["net_pnl_rs"] = -999
        (root / "heldout.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        build_package_from_evidence_manifest(
            evidence_root=root, manifest_path="manifest.json", criteria_path="criteria.json",
            heldout_path="heldout.json", review_path="review.json", validity_path="validity.json",
            readiness_path=None, now=now, **SCOPE)
    assert not (tmp_path / "artifact" / "package.json").exists()


def test_builder_refuses_outside_path_and_nonidentical_replacement(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root, _, _ = _fixture_inputs(tmp_path, now)
    value = json.loads((root / "manifest.json").read_text())
    value["source_reports"][0]["path"] = "../outside.json"
    (root / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="inside evidence root"):
        build_package_from_evidence_manifest(
            evidence_root=root, manifest_path="manifest.json", criteria_path="criteria.json",
            heldout_path="heldout.json", review_path="review.json", validity_path="validity.json",
            readiness_path=None, now=now, **SCOPE)

    root, _, _ = _fixture_inputs(tmp_path / "second", now)
    package = build_package_from_evidence_manifest(
        evidence_root=root, manifest_path="manifest.json", criteria_path="criteria.json",
        heldout_path="heldout.json", review_path="review.json", validity_path="validity.json",
        readiness_path=None, now=now, **SCOPE)
    target = tmp_path / "artifact.json"
    first = write_authorization_package(target, package)
    assert write_authorization_package(target, package) == first
    altered = dict(package, policy_version="a-different-policy")
    with pytest.raises(ValueError, match="different evidence"):
        write_authorization_package(target, altered)


def test_cli_builds_bounded_artifact_without_registry_or_authority_side_effect(tmp_path, capsys):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root, _, _ = _fixture_inputs(tmp_path, now)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    result = main(["build-qualification-package", "--evidence-root", str(root),
                   "--evidence-manifest", "manifest.json", "--criteria-manifest", "criteria.json",
                   "--heldout-report", "heldout.json", "--review-identity", "review.json",
                   "--validity-period", "validity.json", "--readiness", "readiness.json",
                   "--artifact-root", str(artifacts), "--output", "NIFTY/package.json", *sum(([f"--{key.replace('_', '-')}", value] for key, value in SCOPE.items()), [])])
    assert result == 0
    output = artifacts / "NIFTY" / "package.json"
    assert output.exists()
    response = json.loads(capsys.readouterr().out)
    assert response["can_send_advice"] is False and response["authorization_effect"] == "NONE"
    assert main(["build-qualification-package", "--evidence-root", str(root),
                 "--evidence-manifest", "manifest.json", "--criteria-manifest", "criteria.json",
                 "--heldout-report", "heldout.json", "--review-identity", "review.json",
                 "--validity-period", "validity.json", "--artifact-root", str(artifacts),
                 "--output", "../escape.json", "--underlying", "NIFTY"]) == 2


def test_builder_rejects_review_validity_beyond_30_days(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root, _, _ = _fixture_inputs(tmp_path, now)
    (root / "validity.json").write_text(json.dumps({"start": now.isoformat(),
        "end": (now + timedelta(days=31)).isoformat()}), encoding="utf-8")
    with pytest.raises(ValueError, match="30 days"):
        build_package_from_evidence_manifest(
            evidence_root=root, manifest_path="manifest.json", criteria_path="criteria.json",
            heldout_path="heldout.json", review_path="review.json", validity_path="validity.json",
            readiness_path=None, now=now, **SCOPE)
