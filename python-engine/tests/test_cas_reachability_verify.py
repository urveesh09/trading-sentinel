"""[WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] SUMMARY drift verification tests.

The J.10 SUMMARY.md is the persistent audit surface. If
something (manual edit, partial write, disk error) desynchronizes
the on-disk file from the gate's render, operators need a
read-only check that says "drift detected" without overwriting.

These tests pin the verify-summary contract at three layers:
  1. ``cas_reachability_verify`` -- the pure helpers
     (``verify_summary``, ``DiffKind``, ``VerificationReport``).
  2. The CLI surface -- ``--verify-summary`` flag with structured
     output and the right exit codes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_gate import (  # noqa: E402
    cas_reachability_report,
    update_summary,
)
from cas_reachability_verify import (  # noqa: E402
    DiffKind,
    VerificationReport,
    _extract_generated_at,
    _strip_generated_at,
    verify_summary,
)


# ---------------------------------------------------------------------------
# 1. Pure helpers -- DiffKind, VerificationReport


class TestDiffKind:
    """The drift-kind enum is bounded."""

    def test_kind_values_are_strings(self):
        for kind in DiffKind:
            assert isinstance(kind.value, str)
            assert kind.value == kind.name

    def test_kind_set_is_bounded(self):
        # The verify contract documents exactly four kinds.
        assert {k.value for k in DiffKind} == {
            "MATCH",
            "ON_DISK_MISSING",
            "BYTES_DIFFER",
            "GENERATED_AT_DIFFER",
        }


class TestVerificationReport:
    """The structured drift report dataclass."""

    def test_matches_property_true_on_match(self):
        r = VerificationReport(
            kind=DiffKind.MATCH,
            on_disk_path="x",
            generated_at="t",
            expected_size=10,
            actual_size=10,
        )
        assert r.matches is True

    def test_matches_property_false_on_drift(self):
        r = VerificationReport(
            kind=DiffKind.BYTES_DIFFER,
            on_disk_path="x",
            generated_at="t",
            expected_size=10,
            actual_size=11,
        )
        assert r.matches is False

    def test_matches_property_false_on_missing(self):
        r = VerificationReport(
            kind=DiffKind.ON_DISK_MISSING,
            on_disk_path=None,
            generated_at="t",
            expected_size=10,
            actual_size=None,
        )
        assert r.matches is False

    def test_dataclass_is_frozen(self):
        r = VerificationReport(
            kind=DiffKind.MATCH,
            on_disk_path="x",
            generated_at="t",
            expected_size=10,
            actual_size=10,
        )
        with pytest.raises(Exception):
            r.kind = DiffKind.BYTES_DIFFER  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Internal helpers


class TestExtractGeneratedAt:
    """The timestamp-line extractor."""

    def test_extracts_iso_timestamp_with_utc_marker(self):
        text = (
            "header\n"
            "**Generated at**: 2026-09-14T15:35:25.099989+00:00 UTC\n"
            "footer\n"
        )
        assert _extract_generated_at(text) == "2026-09-14T15:35:25.099989+00:00"

    def test_returns_none_when_line_missing(self):
        assert _extract_generated_at("no timestamp here\n") is None

    def test_returns_none_for_empty_string(self):
        assert _extract_generated_at("") is None

    def test_handles_iso_without_utc_marker(self):
        text = "**Generated at**: 2026-09-14T15:35:25+00:00 UTC\n"
        assert _extract_generated_at(text) == "2026-09-14T15:35:25+00:00"


class TestStripGeneratedAt:
    """The line-removal helper used for GENERATED_AT_DIFFER detection."""

    def test_removes_the_generated_at_line(self):
        text = (
            "header\n"
            "**Generated at**: 2026-09-14T15:35:25+00:00 UTC\n"
            "footer\n"
        )
        out = _strip_generated_at(text)
        assert "header" in out
        assert "footer" in out
        assert "Generated at" not in out

    def test_preserves_other_lines_exactly(self):
        text = (
            "line 1\n"
            "line 2\n"
            "**Generated at**: T1 UTC\n"
            "line 4\n"
        )
        assert _strip_generated_at(text) == "line 1\nline 2\nline 4\n"

    def test_no_change_when_line_absent(self):
        text = "line 1\nline 2\n"
        assert _strip_generated_at(text) == text


# ---------------------------------------------------------------------------
# 3. verify_summary -- the integration


def _populate_captures(captures_root: Path) -> None:
    """One capture per branch so the SUMMARY has real content."""
    from tests.test_cas_reachability_listing import (
        _make_capture,
        _write_capture,
    )
    for branch in (
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        _write_capture(
            captures_root, "2026-09-14", f"{branch}.json",
            _make_capture(branch),
        )


def _render_summary(captures_root: Path, summary_path: Path) -> dict[str, Any]:
    """Run the gate and write the SUMMARY to ``summary_path``."""
    report = cas_reachability_report(captures_root)
    update_summary(report, summary_path, captures_dir=captures_root)
    return report


class TestVerifySummary:
    """The drift-detection contract."""

    def test_match_when_on_disk_is_byte_identical(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        # Same report, same path -> MATCH.
        result = verify_summary(report, summary_path, captures_dir=captures_root)
        assert result.kind == DiffKind.MATCH
        assert result.matches is True
        assert result.on_disk_path == str(summary_path)
        assert result.actual_size == result.expected_size
        assert result.generated_at is not None

    def test_only_timestamp_diff_is_generated_at_drift(
        self, tmp_path: Path
    ):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        # Manually replace the on-disk SUMMARY with one whose
        # timestamp differs but body is otherwise identical.
        # This simulates a benign re-render (e.g. two operator
        # runs 1 minute apart).
        body = summary_path.read_text(encoding="utf-8")
        # Replace the generated-at line with a different ISO.
        old_ts = _extract_generated_at(body)
        assert old_ts is not None
        new_body = body.replace(
            f"**Generated at**: {old_ts} UTC",
            "**Generated at**: 1999-01-01T00:00:00+00:00 UTC",
        )
        # Strip the trailing newline from the original line so
        # the substitute carries the same trailing chars.
        assert new_body != body
        summary_path.write_text(new_body, encoding="utf-8")
        result = verify_summary(report, summary_path, captures_dir=captures_root)
        assert result.kind == DiffKind.GENERATED_AT_DIFFER
        assert result.matches is False
        # The size MAY differ (timestamps differ in length --
        # the old one was 32 chars, the new one is 25 chars).
        # The contract is the KIND, not the size.

    def test_body_change_is_bytes_differ(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        # Manually corrupt the body (not just the timestamp line).
        body = summary_path.read_text(encoding="utf-8")
        corrupted = body + "\n\n# manual operator note\n"
        summary_path.write_text(corrupted, encoding="utf-8")
        result = verify_summary(report, summary_path, captures_dir=captures_root)
        assert result.kind == DiffKind.BYTES_DIFFER
        assert result.matches is False
        # The actual size is LARGER than expected (corruption
        # added bytes).
        assert result.actual_size > result.expected_size

    def test_on_disk_missing_returns_on_disk_missing(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY_NEVER_WRITTEN.md"
        _populate_captures(captures_root)
        report = cas_reachability_report(captures_root)
        result = verify_summary(report, summary_path, captures_dir=captures_root)
        assert result.kind == DiffKind.ON_DISK_MISSING
        assert result.matches is False
        assert result.on_disk_path is None
        assert result.actual_size is None
        # The expected size is still meaningful -- it's the
        # byte count the fresh render would produce.
        assert result.expected_size > 0

    def test_verify_is_pure_no_writes_to_disk(self, tmp_path: Path):
        """[WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] The verify
        contract is read-only. The function MUST NOT write to
        the on-disk SUMMARY; the operator commits via
        ``--update-summary``. Without this, ``--verify-summary``
        would silently repair drift instead of detecting it.
        """
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        # Capture mtime + size before verify.
        size_before = summary_path.stat().st_size
        mtime_before = summary_path.stat().st_mtime_ns
        verify_summary(report, summary_path, captures_dir=captures_root)
        size_after = summary_path.stat().st_size
        mtime_after = summary_path.stat().st_mtime_ns
        # Both unchanged.
        assert size_after == size_before
        assert mtime_after == mtime_before


# ---------------------------------------------------------------------------
# 4. CLI surface


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the cas_reachability_check.py CLI in-process via the
    ``main`` function."""
    cmd = [
        sys.executable,
        "-m",
        "tools.cas_reachability_check",
        *args,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        timeout=60,
    )


class TestVerifySummaryCli:
    """The ``--verify-summary`` CLI flag."""

    def test_verify_exits_zero_when_match(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        # The CLI runs the gate fresh and compares; result is MATCH.
        result = _run_cli(
            "--captures-dir", str(captures_root),
            "--summary-path", str(summary_path),
            "--verify-summary",
        )
        assert result.returncode == 0, (
            f"stderr: {result.stderr}"
        )
        assert "MATCH" in result.stdout

    def test_verify_exits_one_on_bytes_differ(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        # Corrupt the on-disk body.
        body = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(body + "# corrupted\n", encoding="utf-8")
        result = _run_cli(
            "--captures-dir", str(captures_root),
            "--summary-path", str(summary_path),
            "--verify-summary",
        )
        assert result.returncode == 1
        assert "BYTES_DIFFER" in result.stdout

    def test_verify_exits_two_on_missing(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY_NEVER_WRITTEN.md"
        _populate_captures(captures_root)
        result = _run_cli(
            "--captures-dir", str(captures_root),
            "--summary-path", str(summary_path),
            "--verify-summary",
        )
        assert result.returncode == 2
        assert "ON_DISK_MISSING" in result.stdout

    def test_verify_json_output_shape(self, tmp_path: Path):
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        result = _run_cli(
            "--captures-dir", str(captures_root),
            "--summary-path", str(summary_path),
            "--verify-summary",
            "--json",
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        # Shape: documented fields.
        # The kind MAY be MATCH or GENERATED_AT_DIFFER (the
        # subprocess re-renders at a slightly later moment than
        # the test wrote -- benign timestamp-only drift). Both
        # are exit 0.
        assert payload["kind"] in {"MATCH", "GENERATED_AT_DIFFER"}
        assert payload["on_disk_path"] == str(summary_path)
        # actual_size == expected_size for MATCH; may differ by
        # a few bytes for GENERATED_AT_DIFFER (timestamp length).
        if payload["kind"] == "MATCH":
            assert payload["expected_size"] == payload["actual_size"]
        assert payload["generated_at"] is not None

    def test_verify_refuses_combination_with_update_summary(
        self, tmp_path: Path
    ):
        """``--verify-summary`` + ``--update-summary`` is a
        tautology (the update overwrites the on-disk file, then
        the verify sees its own write). The CLI refuses the
        combination with exit code 2.
        """
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        result = _run_cli(
            "--captures-dir", str(captures_root),
            "--summary-path", str(summary_path),
            "--verify-summary",
            "--update-summary",
        )
        assert result.returncode == 2
        assert "mutually exclusive" in result.stderr

    def test_verify_does_not_overwrite_on_disk(self, tmp_path: Path):
        """[WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] The CLI's
        ``--verify-summary`` MUST NOT overwrite the on-disk
        SUMMARY. We verify by corrupting the on-disk file
        before the call and asserting the corruption survives.
        """
        captures_root = tmp_path / "cap"
        summary_path = tmp_path / "SUMMARY.md"
        _populate_captures(captures_root)
        report = _render_summary(captures_root, summary_path)
        body = summary_path.read_text(encoding="utf-8")
        corrupted = body + "# operator manual edit\n"
        summary_path.write_text(corrupted, encoding="utf-8")
        result = _run_cli(
            "--captures-dir", str(captures_root),
            "--summary-path", str(summary_path),
            "--verify-summary",
        )
        assert result.returncode == 1
        # The on-disk file STILL has the manual edit --
        # --verify-summary did not overwrite it.
        after = summary_path.read_text(encoding="utf-8")
        assert after == corrupted
