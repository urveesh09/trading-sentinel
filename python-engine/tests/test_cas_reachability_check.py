"""[WORKFLOW-J.10.CLOSURE 2026-09-14] Tests for the
``tools.cas_reachability_check`` CLI.

The CLI is the operator-facing surface for the J.10 gate. It
must:

  * emit a non-zero exit code when the gate is UNREACHABLE
    (so it can wire into CI);
  * emit exit 0 when the gate is REACHABLE;
  * emit exit 2 when the captures directory is missing;
  * accept ``--captures-dir`` / ``--json`` / ``--update-summary``
    / ``--summary-path`` flags without crashing;
  * include the new ``captures_by_branch`` catalog field in
    both the human-readable and JSON outputs.

These tests pin the contract end-to-end via ``subprocess`` so
any regression in argv parsing / flag interaction / exit code
surfaces here, not in production.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
PYTHON = sys.executable


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the cas_reachability_check CLI as a subprocess so
    argv parsing and exit codes are exercised exactly as an
    operator would. ``cwd`` defaults to the repo root so
    ``--captures-dir`` defaults resolve correctly.
    """
    return subprocess.run(
        [PYTHON, "-m", "tools.cas_reachability_check", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def _write_capture(dir_: Path, name: str, phase: str) -> Path:
    """Write a J.3-schema capture JSON file under ``dir_``."""
    day = dir_ / "2026-09-10"
    day.mkdir(parents=True, exist_ok=True)
    cap = day / name
    cap.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "rows": [{"classifier_phase": phase}],
            }
        ),
        encoding="utf-8",
    )
    return cap


def test_cli_exits_zero_when_reachable(tmp_path):
    """A directory with all 6 branches captured exits 0."""
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        _write_capture(tmp_path, f"{branch}.json", branch)
    result = _run_cli("--captures-dir", str(tmp_path))
    assert result.returncode == 0, (
        f"stderr: {result.stderr}\nstdout: {result.stdout}"
    )
    assert "REACHABLE" in result.stdout


def test_cli_exits_one_when_unreachable(tmp_path):
    """A directory with no captures exits 1 (CI-gate-friendly)."""
    (tmp_path / "2026-09-10").mkdir(parents=True)
    # No captures.
    result = _run_cli("--captures-dir", str(tmp_path))
    assert result.returncode == 1, result.stdout
    assert "UNREACHABLE" in result.stdout


def test_cli_exits_two_when_dir_missing(tmp_path):
    """A non-existent captures directory exits 2 (operational error)."""
    missing = tmp_path / "does-not-exist"
    result = _run_cli("--captures-dir", str(missing))
    assert result.returncode == 2, result.stdout
    assert "does not exist" in result.stderr or "captures" in result.stderr


def test_cli_json_output_includes_captures_by_branch(tmp_path):
    """The --json output includes the per-branch catalog."""
    cap_a = _write_capture(tmp_path, "a.json", "CAS_REFERENCE_PRICE_WINDOW")
    cap_b = _write_capture(tmp_path, "b.json", "CAS_ORDER_ENTRY")
    result = _run_cli(
        "--captures-dir", str(tmp_path), "--json",
    )
    assert result.returncode == 1  # still UNREACHABLE (only 2/6 branches)
    payload = json.loads(result.stdout)
    assert "captures_by_branch" in payload
    assert any(
        p.endswith("a.json")
        for p in payload["captures_by_branch"]["CAS_REFERENCE_PRICE_WINDOW"]
    )
    assert any(
        p.endswith("b.json")
        for p in payload["captures_by_branch"]["CAS_ORDER_ENTRY"]
    )
    assert payload["captures_by_branch"]["CAS_MATCHING"] == []
    assert payload["captures_by_branch"]["DERIVATIVES_CAS_ALIGNED"] == []


def test_cli_human_output_includes_captures_catalog(tmp_path):
    """The default (non-JSON) human-readable output renders the
    catalog section so operators see exactly which captures
    back each branch.
    """
    _write_capture(tmp_path, "RELIANCE_15_15.json", "CAS_REFERENCE_PRICE_WINDOW")
    _write_capture(tmp_path, "RELIANCE_15_22.json", "CAS_ORDER_ENTRY")
    result = _run_cli("--captures-dir", str(tmp_path))
    # UNREACHABLE (only 2/6) but catalog should still render.
    assert result.returncode == 1
    assert "captures catalog:" in result.stdout
    assert "CAS_REFERENCE_PRICE_WINDOW" in result.stdout
    assert "RELIANCE_15_15.json" in result.stdout


def test_cli_update_summary_writes_markdown(tmp_path):
    """``--update-summary`` writes a SUMMARY.md alongside the
    captures directory; ``--summary-path`` overrides the path.
    """
    _write_capture(tmp_path, "a.json", "CAS_REFERENCE_PRICE_WINDOW")
    summary = tmp_path / "CUSTOM_SUMMARY.md"
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--update-summary", "--summary-path", str(summary),
    )
    assert result.returncode == 1  # UNREACHABLE
    assert summary.exists(), "SUMMARY.md was not written"
    body = summary.read_text(encoding="utf-8")
    # Catalog section rendered.
    assert "## Captures catalog" in body
    assert "a.json" in body
    # Captured-branch marker.
    assert "CAS_REFERENCE_PRICE_WINDOW | 1 (yes) |" in body


def test_cli_update_summary_default_path(tmp_path):
    """Without ``--summary-path``, SUMMARY.md lands at
    ``<captures-dir>/SUMMARY.md``.
    """
    _write_capture(tmp_path, "a.json", "CAS_REFERENCE_PRICE_WINDOW")
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--update-summary",
    )
    assert result.returncode == 1
    default_summary = tmp_path / "SUMMARY.md"
    assert default_summary.exists()
    assert "## Captures catalog" in default_summary.read_text(encoding="utf-8")


def test_cli_write_persists_json_report(tmp_path):
    """``--write`` persists the JSON report to the given path
    independent of ``--update-summary``.
    """
    _write_capture(tmp_path, "a.json", "CAS_REFERENCE_PRICE_WINDOW")
    report_path = tmp_path / "report.json"
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--write", str(report_path),
    )
    assert result.returncode == 1
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "UNREACHABLE"
    assert "captures_by_branch" in payload


def test_cli_json_shape_is_stable(tmp_path):
    """The JSON output shape is stable: the documented keys
    are present and stable across calls (no extra / missing keys
    that would break CI parsers).
    """
    _write_capture(tmp_path, "a.json", "CAS_ORDER_ENTRY")
    result = _run_cli("--captures-dir", str(tmp_path), "--json")
    payload = json.loads(result.stdout)
    expected_keys = {
        "verdict",
        "captured_phases",
        "missing_phases",
        "coverage_pct",
        "captures_scanned",
        "captures_skipped",
        "captures_by_branch",
    }
    assert set(payload.keys()) == expected_keys, (
        f"JSON shape drift: extra={set(payload.keys()) - expected_keys}, "
        f"missing={expected_keys - set(payload.keys())}"
    )


def test_cli_summary_documents_per_branch_ist_windows(tmp_path):
    """The SUMMARY written by --update-summary lists the IST
    window for every required branch. Operators need this
    cheat-sheet to know which ``--observation-at`` value to
    pass to ``tools/j2_cas_probe.py`` for each branch.

    The CLI is the public surface for SUMMARY generation, so
    this test runs the CLI subprocess rather than calling
    ``update_summary`` directly.
    """
    (tmp_path / "2026-09-10").mkdir(parents=True)
    summary = tmp_path / "SUMMARY.md"
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--update-summary", "--summary-path", str(summary),
    )
    assert result.returncode == 1  # UNREACHABLE
    assert summary.exists()
    text = summary.read_text(encoding="utf-8")
    # Every required branch is documented with its IST window.
    assert "CAS_REFERENCE_PRICE_WINDOW | 15:15:00 .. 15:19:59" in text
    assert "CAS_ORDER_ENTRY | 15:20:00 .. 15:24:59" in text
    assert "CAS_LIMIT_ENTRY_ONLY | 15:25:00 .. 15:29:59" in text
    assert "CAS_MATCHING | 15:30:00 .. 15:34:59" in text
    assert "CAS_POST (cash) | 15:35:00 .. 15:59:59" in text
    assert "DERIVATIVES_CAS_ALIGNED | 15:30:00 .. 15:39:59" in text


def test_cli_summary_uses_iso_8601_in_probe_example(tmp_path):
    """The probe command in the SUMMARY uses ISO 8601 timestamps
    (with the timezone offset or naive-IST default), NOT the
    legacy ``15:22:00 IST`` syntax that the probe CLI doesn't
    accept. Pinning this prevents the example from regressing.
    """
    (tmp_path / "2026-09-10").mkdir(parents=True)
    summary = tmp_path / "SUMMARY.md"
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--update-summary", "--summary-path", str(summary),
    )
    assert result.returncode == 1
    text = summary.read_text(encoding="utf-8")
    # The legacy broken syntax must NOT appear.
    assert "15:22:00 IST" not in text
    # The ISO 8601 examples DO appear.
    assert "2026-09-14T15:17:00" in text
    assert "2026-09-14T15:22:00" in text


def test_cli_summary_cross_references_catalog(tmp_path):
    """The SUMMARY cross-references the Captures catalog section
    from the 'How to add captures' section so operators don't
    need to re-run the CLI to confirm a passing review.
    """
    _write_capture(tmp_path, "x.json", "CAS_REFERENCE_PRICE_WINDOW")
    summary = tmp_path / "SUMMARY.md"
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--update-summary", "--summary-path", str(summary),
    )
    assert result.returncode == 1
    text = summary.read_text(encoding="utf-8")
    # Catalog cross-reference in runbook section.
    runbook_idx = text.index("## How to add captures")
    assert '"Captures catalog"' in text[runbook_idx:]
    # Catalog is rendered above the runbook.
    catalog_idx = text.index("## Captures catalog")
    assert catalog_idx < runbook_idx
