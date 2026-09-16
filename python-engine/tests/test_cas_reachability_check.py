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
from datetime import datetime, timedelta, timezone
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
    # [WORKFLOW-J.10.DEDUP 2026-09-14] The ``duplicates_by_branch``
    # field is additive; the contract is "the 12 documented keys are
    # present, no extras, no missing".
    expected_keys = {
        "verdict",
        "captured_phases",
        "missing_phases",
        "coverage_pct",
        "captures_scanned",
        "captures_skipped",
        "captures_by_branch",
        "duplicates_by_branch",
        # [WORKFLOW-J.10.FRESHNESS 2026-09-14] The new
        # ``captures_skipped_stale`` field is the freshness
        # filter's audit surface; always present, default 0
        # when no filter was applied.
        "captures_skipped_stale",
        # [WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] The new
        # ``min_unique_per_branch`` field is the threshold's
        # audit surface; always present, default 1 when no
        # threshold was applied.
        "min_unique_per_branch",
        # [WORKFLOW-J.10.CAPTURE_SUMMARY_AGGREGATE 2026-09-14]
        # The new ``captures_per_day`` field is the per-day
        # histogram (date -> {scanned, unique}); always
        # present, default {} when no captures exist.
        "captures_per_day",
        # [WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] The new
        # ``branch_per_day`` field is the per-branch-per-day
        # matrix (branch -> date -> {scanned, unique}); always
        # present, default empty matrix when no captures exist.
        "branch_per_day",
        # [WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14] The
        # ``recency_by_branch`` field is the per-branch
        # timestamp range (oldest / newest first-occurrence
        # capture + backing paths + span in days); always
        # present, default {} when no captures exist.
        "recency_by_branch",
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


def test_cli_status_emits_single_line_unreachable(tmp_path):
    """``--status`` emits a single-line status suitable for
    shell prompts. Format:

        J.10: <VERDICT> <coverage_pct>% (<captured>/<total> branches,
        <scanned> scanned, <skipped> skipped)

    Exit code follows the gate's verdict (1 = UNREACHABLE).
    Stdout does NOT contain the multi-line report.
    """
    (tmp_path / "2026-09-10").mkdir(parents=True)
    result = _run_cli("--captures-dir", str(tmp_path), "--status")
    assert result.returncode == 1
    # Single line, ends with newline.
    assert result.stdout.count("\n") == 1, result.stdout
    # Format contract.
    assert result.stdout.startswith("J.10: UNREACHABLE 0.0% (0/6 branches,")
    assert "0 scanned" in result.stdout
    assert "0 skipped" in result.stdout
    # The multi-line report is suppressed.
    assert "captured per branch:" not in result.stdout
    assert "missing branches" not in result.stdout


def test_cli_status_emits_single_line_reachable(tmp_path):
    """``--status`` exits 0 when the gate is REACHABLE; the
    status line reflects the captured/total branches count.
    """
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        _write_capture(tmp_path, f"{branch}.json", branch)
    result = _run_cli("--captures-dir", str(tmp_path), "--status")
    assert result.returncode == 0
    assert result.stdout.count("\n") == 1
    assert "J.10: REACHABLE 100.0% (6/6 branches" in result.stdout


def test_cli_status_counts_only_nonzero_branches(tmp_path):
    """``--status`` counts branches with at least one capture;
    a branch with 5 captures still counts as 1 (the gate's
    verdict is count-driven at >=1, not proportional).
    """
    # Five captures all on CAS_REFERENCE_PRICE_WINDOW: that's
    # still only 1 branch captured.
    for i in range(5):
        _write_capture(tmp_path, f"r{i}.json", "CAS_REFERENCE_PRICE_WINDOW")
    result = _run_cli("--captures-dir", str(tmp_path), "--status")
    assert result.returncode == 1
    assert "1/6 branches" in result.stdout
    assert "5 scanned" in result.stdout


# ---------------------------------------------------------------------------
# [WORKFLOW-J.10.FRESHNESS 2026-09-14] --captures-since CLI tests
# ---------------------------------------------------------------------------


def _write_capture_with_age(
    dir_: Path, name: str, phase: str, *, days_old: float
) -> Path:
    """Write a J.3-schema capture with a controlled
    ``generated_at_utc`` so we can exercise the freshness filter."""
    day = dir_ / "2026-09-10"
    day.mkdir(parents=True, exist_ok=True)
    cap = day / name
    generated = (
        datetime.now(timezone.utc) - timedelta(days=days_old)
    ).isoformat()
    cap.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at_utc": generated,
                "rows": [{"classifier_phase": phase}],
            }
        ),
        encoding="utf-8",
    )
    return cap


def test_cli_captures_since_filters_stale_captures(tmp_path):
    """``--captures-since 7`` keeps only the fresh capture;
    the ancient one is skipped and surfaces in
    ``captures_skipped_stale``."""
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        # Every capture is 90 days old -> all stale under a 7-day filter.
        _write_capture_with_age(
            tmp_path, f"{branch}.json", branch, days_old=90.0
        )
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--captures-since", "7",
        "--json",
    )
    assert result.returncode == 1  # UNREACHABLE under filter
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "UNREACHABLE"
    assert payload["captures_skipped_stale"] == 6
    # No captures counted under the filter.
    for branch in payload["captured_phases"]:
        assert payload["captured_phases"][branch] == 0


def test_cli_captures_since_keeps_fresh_captures(tmp_path):
    """``--captures-since 30`` keeps the fresh capture and
    surfaces the stale-skip count."""
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        # All fresh (0 days old) -> all count under any filter.
        _write_capture_with_age(
            tmp_path, f"{branch}.json", branch, days_old=0.0
        )
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--captures-since", "30",
        "--json",
    )
    assert result.returncode == 0  # REACHABLE
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "REACHABLE"
    assert payload["captures_skipped_stale"] == 0


def test_cli_captures_since_rejects_non_positive(tmp_path):
    """``--captures-since 0`` and ``--captures-since -5`` are
    rejected at the CLI boundary with exit code 2."""
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--captures-since", "0",
        "--json",
    )
    assert result.returncode == 2
    assert "must be > 0" in result.stderr

    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--captures-since", "-5",
        "--json",
    )
    assert result.returncode == 2
    assert "must be > 0" in result.stderr


def test_cli_captures_since_mixed_fresh_and_stale(tmp_path):
    """A 14-day filter keeps captures younger than 14 days; older
    ones are skipped and counted under captures_skipped_stale."""
    # 3 fresh (0 days), 3 ancient (60 days) -- one of each per
    # the first three branches.
    fresh_branches = (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
    )
    stale_branches = (
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    )
    for branch in fresh_branches:
        _write_capture_with_age(
            tmp_path, f"{branch}.json", branch, days_old=0.0
        )
    for branch in stale_branches:
        _write_capture_with_age(
            tmp_path, f"{branch}.json", branch, days_old=60.0
        )
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--captures-since", "14",
        "--json",
    )
    assert result.returncode == 1  # UNREACHABLE: 3 missing
    payload = json.loads(result.stdout)
    assert payload["captures_skipped_stale"] == 3
    assert (
        payload["captured_phases"]["CAS_REFERENCE_PRICE_WINDOW"] == 1
    )
    assert (
        payload["captured_phases"]["CAS_MATCHING"] == 0
    )


def test_cli_captures_since_works_with_status_flag(tmp_path):
    """``--captures-since`` composes with ``--status``: the
    single-line status reflects the filtered verdict."""
    _write_capture_with_age(
        tmp_path,
        "stale.json",
        "CAS_REFERENCE_PRICE_WINDOW",
        days_old=100.0,
    )
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--captures-since", "7",
        "--status",
    )
    assert result.returncode == 1  # UNREACHABLE: 0/6 fresh branches
    assert "J.10: UNREACHABLE" in result.stdout


# ---------------------------------------------------------------------------
# [WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] --min-unique-per-branch CLI tests
# ---------------------------------------------------------------------------


def test_cli_min_unique_per_branch_blocks_single_capture(tmp_path):
    """``--min-unique-per-branch 2`` keeps the gate UNREACHABLE
    when each branch has only one unique capture.
    """
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        _write_capture(tmp_path, f"{branch}.json", branch)
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--min-unique-per-branch", "2",
        "--json",
    )
    assert result.returncode == 1  # UNREACHABLE
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "UNREACHABLE"
    assert payload["min_unique_per_branch"] == 2
    assert len(payload["missing_phases"]) == 6


def test_cli_min_unique_per_branch_rejects_non_positive(tmp_path):
    """``--min-unique-per-branch 0`` and ``-5`` are rejected
    at the CLI boundary with exit code 2."""
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--min-unique-per-branch", "0",
        "--json",
    )
    assert result.returncode == 2
    assert "must be > 0" in result.stderr

    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--min-unique-per-branch", "-3",
        "--json",
    )
    assert result.returncode == 2
    assert "must be > 0" in result.stderr


def test_cli_min_unique_per_branch_default_is_one(tmp_path):
    """Without ``--min-unique-per-branch``, the JSON report's
    ``min_unique_per_branch`` is 1 (backwards-compatible)."""
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        _write_capture(tmp_path, f"{branch}.json", branch)
    result = _run_cli("--captures-dir", str(tmp_path), "--json")
    payload = json.loads(result.stdout)
    assert payload["min_unique_per_branch"] == 1
    assert payload["verdict"] == "REACHABLE"


def test_cli_min_unique_per_branch_status_reflects_verdict(tmp_path):
    """``--min-unique-per-branch`` composes with ``--status``:
    a high threshold flips the gate's single-line status to
    UNREACHABLE even when every branch has at least one
    capture."""
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        _write_capture(tmp_path, f"{branch}.json", branch)
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--min-unique-per-branch", "2",
        "--status",
    )
    assert result.returncode == 1  # UNREACHABLE
    assert "J.10: UNREACHABLE" in result.stdout
    assert "0/6 branches" in result.stdout


# ---------------------------------------------------------------------------
# [WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] --show-branch-histogram CLI tests
# ---------------------------------------------------------------------------


def test_cli_show_branch_histogram_appends_matrix_human(tmp_path):
    """``--show-branch-histogram`` appends the per-branch-per-day
    matrix to the human-readable report.
    """
    from tests.test_cas_reachability_branch_histogram import (
        _make_capture, _write_capture
    )
    _write_capture(
        tmp_path, "2026-09-10", "a.json",
        _make_capture("CAS_MATCHING", symbol="RELIANCE"),
    )
    _write_capture(
        tmp_path, "2026-09-14", "b.json",
        _make_capture("CAS_MATCHING", symbol="TCS"),
    )
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--show-branch-histogram",
    )
    assert result.returncode == 1  # UNREACHABLE (5 missing branches)
    out = result.stdout
    # The matrix header is present.
    assert "Captures per branch per day:" in out
    # The branch row appears.
    assert "CAS_MATCHING" in out
    # The two dates appear as columns.
    assert "2026-09-10" in out
    assert "2026-09-14" in out


def test_cli_show_branch_histogram_in_json_payload(tmp_path):
    """``--show-branch-histogram`` doesn't change the JSON
    payload -- the matrix is ALWAYS included as
    ``branch_per_day`` (the flag only affects the
    human-readable output)."""
    from tests.test_cas_reachability_branch_histogram import (
        _make_capture, _write_capture
    )
    _write_capture(
        tmp_path, "2026-09-14", "a.json",
        _make_capture("CAS_MATCHING"),
    )
    result = _run_cli(
        "--captures-dir", str(tmp_path),
        "--json",
    )
    payload = json.loads(result.stdout)
    # branch_per_day is present in JSON regardless of the flag.
    assert "branch_per_day" in payload
    assert "CAS_MATCHING" in payload["branch_per_day"]
