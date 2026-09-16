import json
from datetime import datetime

import pytz

from partner_qualification_review import (
    QualificationCriteria,
    freeze_qualification_criteria,
    write_qualification_criteria_manifest,
)
from research_cli import main


def test_full_policy_cli_writes_nonqualifying_causal_decision(tmp_path, capsys):
    bars = tmp_path / "bars.csv"
    bars.write_text("bar_start,open,high,low,close,volume\n2026-09-11 09:15:00,100,102,99,101,100\n", encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"state": "RETROSPECTIVE", "source": "historical-kite",
                                      "event_at": "2026-09-11T03:45:00+00:00",
                                      "received_at": None, "retrieved_at": "2026-09-12T03:45:00+00:00"}), encoding="utf-8")
    output = tmp_path / "decision.json"
    result = main(["full-policy-diagnostic", "--underlying", "NIFTY", "--bars", str(bars),
                   "--regime", "REGIME_1_NORMAL", "--decision-at", "2026-09-11T04:00:00+00:00",
                   "--bar-provenance", str(provenance), "--output", str(output)])
    assert result == 0 and output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["state"] == "NO_SETUP" and saved["can_qualify"] is False
    assert "NO_SETUP" in capsys.readouterr().out


# [WORKFLOW-C.A4-CLI 2026-09-15] Operator-facing manifest
# drift verification CLI. Reuses the helper from A4.


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


def _write_manifest(tmp_path):
    """Write a canonical criteria manifest to disk via the
    existing writer. Returns the path.
    """
    frozen = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 9, 11, 12))
    coverage = [("NIFTY", "f" * 64, "2026-09-12")]
    manifest = freeze_qualification_criteria(
        criteria=_criteria(), underlying="NIFTY",
        training_sessions=["2026-09-10"], holdout_sessions=["2026-09-12"],
        declared_coverage=coverage, frozen_at=frozen,
    )
    path = tmp_path / "criteria-manifest.json"
    write_qualification_criteria_manifest(path, manifest)
    return path


class TestVerifyCriteriaManifestCli:
    """[WORKFLOW-C.A4-CLI 2026-09-15] The CLI surface for
    ``verify-criteria-manifest``.

    Pins:
      - exit code 0 on MATCH.
      - exit code 1 on real drift (fingerprint mismatch,
        criteria not reconstructable).
      - exit code 2 on missing / unreadable file.
      - JSON output shape matches the helper.
      - CLI is read-only (no writes to the manifest).
    """

    def test_match_exits_zero_with_human_readable_text(self, tmp_path, capsys):
        path = _write_manifest(tmp_path)
        result = main(["verify-criteria-manifest", "--manifest-path", str(path)])
        assert result == 0
        out = capsys.readouterr().out
        assert "MATCH" in out
        assert str(path) in out

    def test_match_exits_zero_with_json_output(self, tmp_path, capsys):
        path = _write_manifest(tmp_path)
        result = main(["verify-criteria-manifest",
                        "--manifest-path", str(path),
                        "--json"])
        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "MATCH"
        assert payload["matches"] is True
        assert payload["on_disk_path"] == str(path)
        assert payload["on_disk_fingerprint"] is not None
        assert payload["reconstructed_fingerprint"] == payload["on_disk_fingerprint"]
        assert payload["on_disk_size"] > 0

    def test_tampered_fingerprint_exits_one(self, tmp_path, capsys):
        """[WORKFLOW-C.A4-CLI 2026-09-15] A body tampering
        (changing a field without re-hashing) is reported
        as ``MANIFEST_FINGERPRINT_MISMATCH`` and exits 1.
        """
        path = _write_manifest(tmp_path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        # Tamper with a body field WITHOUT updating the
        # fingerprint -- the helper detects the mismatch.
        manifest["frozen_at"] = "2099-01-01T00:00:00+00:00"
        path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result = main(["verify-criteria-manifest",
                        "--manifest-path", str(path),
                        "--json"])
        assert result == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "MANIFEST_FINGERPRINT_MISMATCH"

    def test_unsupported_field_exits_one(self, tmp_path, capsys):
        """[WORKFLOW-C.A4-CLI 2026-09-15] An unsupported
        field (rehashed) is reported as
        ``CRITERIA_NOT_RECONSTRUCTABLE`` and exits 1.
        """
        path = _write_manifest(tmp_path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["rogue_field"] = "tampered"
        # Re-hash so the body fingerprint matches, but the
        # reconstructability check fails.
        from partner_qualification_review import _sha
        manifest["criteria_manifest_sha256"] = _sha(
            {key: value for key, value in manifest.items()
             if key != "criteria_manifest_sha256"}
        )
        path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result = main(["verify-criteria-manifest",
                        "--manifest-path", str(path),
                        "--json"])
        assert result == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "CRITERIA_NOT_RECONSTRUCTABLE"

    def test_missing_file_exits_two(self, tmp_path, capsys):
        result = main(["verify-criteria-manifest",
                        "--manifest-path", str(tmp_path / "does-not-exist.json"),
                        "--json"])
        assert result == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "ON_DISK_MISSING"
        assert payload["on_disk_path"] is None

    def test_corrupt_json_exits_two(self, tmp_path, capsys):
        path = tmp_path / "criteria-manifest.json"
        path.write_text("not valid json", encoding="utf-8")
        result = main(["verify-criteria-manifest",
                        "--manifest-path", str(path),
                        "--json"])
        assert result == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "BYTES_UNREADABLE"

    def test_cli_does_not_overwrite_manifest(self, tmp_path, capsys):
        """[WORKFLOW-C.A4-CLI 2026-09-15] The CLI is
        read-only by contract. A corrupted on-disk
        manifest MUST stay corrupted after the CLI runs --
        ``--verify-criteria-manifest`` does not auto-repair.
        """
        path = _write_manifest(tmp_path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["rogue_field"] = "tampered"
        from partner_qualification_review import _sha
        manifest["criteria_manifest_sha256"] = _sha(
            {key: value for key, value in manifest.items()
             if key != "criteria_manifest_sha256"}
        )
        path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        size_before = path.stat().st_size
        mtime_before = path.stat().st_mtime_ns
        main(["verify-criteria-manifest", "--manifest-path", str(path)])
        size_after = path.stat().st_size
        mtime_after = path.stat().st_mtime_ns
        # The CLI did not touch the file.
        assert size_after == size_before
        assert mtime_after == mtime_before
