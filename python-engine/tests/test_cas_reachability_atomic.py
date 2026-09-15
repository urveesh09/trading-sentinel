"""[WORKFLOW-J.10.WRITE_ATOMIC 2026-09-14] Atomic-write tests.

Mirrors the F5 ``test_main_retry_writes_identical_immutable_output``
discipline: byte-identical retries produce byte-identical files;
a different-content pre-existing file refuses to be clobbered.

The J.10 gate's audit trail is the JSON report. Two CLI
invocations against the same captures directory MUST produce
the same bytes (otherwise downstream consumers see spurious
"new" reports). A different-content pre-existing file is a
bug -- the operator has either pointed at the wrong path or
has stale output from a different captures directory. We
refuse to clobber rather than silently overwriting their
audit trail.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_atomic import write_report_atomic  # noqa: E402
from cas_reachability_gate import (  # noqa: E402
    cas_reachability_report,
    write_report,
)


# ---------------------------------------------------------------------------
# Helpers


def _sample_report() -> dict[str, Any]:
    """A representative gate report (the actual shape from
    cas_reachability_report)."""
    return {
        "verdict": "UNREACHABLE",
        "captured_phases": {
            "CAS_REFERENCE_PRICE_WINDOW": 0,
            "CAS_ORDER_ENTRY": 0,
            "CAS_LIMIT_ENTRY_ONLY": 0,
            "CAS_MATCHING": 0,
            "CAS_POST": 0,
            "DERIVATIVES_CAS_ALIGNED": 0,
        },
        "missing_phases": [
            "CAS_REFERENCE_PRICE_WINDOW",
            "CAS_ORDER_ENTRY",
            "CAS_LIMIT_ENTRY_ONLY",
            "CAS_MATCHING",
            "CAS_POST",
            "DERIVATIVES_CAS_ALIGNED",
        ],
        "coverage_pct": 0.0,
        "captures_scanned": 0,
        "captures_skipped": 0,
        "captures_by_branch": {
            phase: [] for phase in [
                "CAS_REFERENCE_PRICE_WINDOW", "CAS_ORDER_ENTRY",
                "CAS_LIMIT_ENTRY_ONLY", "CAS_MATCHING",
                "CAS_POST", "DERIVATIVES_CAS_ALIGNED",
            ]
        },
        "duplicates_by_branch": {
            phase: 0 for phase in [
                "CAS_REFERENCE_PRICE_WINDOW", "CAS_ORDER_ENTRY",
                "CAS_LIMIT_ENTRY_ONLY", "CAS_MATCHING",
                "CAS_POST", "DERIVATIVES_CAS_ALIGNED",
            ]
        },
        "captures_skipped_stale": 0,
        "min_unique_per_branch": 1,
        "captures_per_day": {},
    }


# ---------------------------------------------------------------------------
# 1. write_report_atomic -- the helper


class TestWriteReportAtomic:
    """The atomic-write helper."""

    def test_writes_when_target_does_not_exist(self, tmp_path: Path):
        out = tmp_path / "report.json"
        write_report_atomic(_sample_report(), out)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["verdict"] == "UNREACHABLE"

    def test_creates_parent_directory_if_missing(self, tmp_path: Path):
        out = tmp_path / "nested" / "deeper" / "report.json"
        write_report_atomic(_sample_report(), out)
        assert out.exists()

    def test_byte_identical_retry_is_a_noop(self, tmp_path: Path):
        """[WORKFLOW-J.10.WRITE_ATOMIC 2026-09-14] The core
        discipline: two invocations with the same input produce
        byte-identical files. Without atomic + byte-identical
        semantics, a retry could produce subtly different bytes
        (e.g. dict ordering, trailing newline) and downstream
        consumers would see spurious "new" reports."""
        out = tmp_path / "report.json"
        report = _sample_report()
        write_report_atomic(report, out)
        first_bytes = out.read_bytes()
        write_report_atomic(report, out)
        second_bytes = out.read_bytes()
        assert first_bytes == second_bytes

    def test_rejects_different_content(self, tmp_path: Path):
        """A different-content pre-existing file is a real bug:
        either the operator pointed at the wrong path, or
        stale output from a different captures directory is
        sitting at this location. We refuse to clobber rather
        than silently overwriting their audit trail.
        """
        out = tmp_path / "report.json"
        # Pre-existing file with different content.
        out.write_text('{"different": "content"}', encoding="utf-8")
        with pytest.raises(ValueError, match="different content"):
            write_report_atomic(_sample_report(), out)

    def test_allows_same_content_retry_after_existing_file(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.WRITE_ATOMIC 2026-09-14] When the
        pre-existing file has the SAME content as what we would
        write, ``os.link`` will fail with ``FileExistsError``
        but the existing file IS the report -- the helper
        treats this as a noop success."""
        out = tmp_path / "report.json"
        report = _sample_report()
        write_report_atomic(report, out)
        first_bytes = out.read_bytes()
        # A second invocation with the same report -- helper
        # must NOT raise. The helper sees the existing file
        # matches what it would write and treats it as a
        # successful noop.
        write_report_atomic(report, out)
        assert out.read_bytes() == first_bytes

    def test_rejects_nan_in_report(self, tmp_path: Path):
        """``allow_nan=False`` prevents the JSON encoder from
        emitting ``NaN``/``Infinity`` which violate the JSON
        spec and break downstream consumers.
        """
        out = tmp_path / "report.json"
        bad_report = _sample_report()
        bad_report["captures_scanned"] = math.nan
        with pytest.raises(ValueError):
            write_report_atomic(bad_report, out)

    def test_rejects_inf_in_report(self, tmp_path: Path):
        """Same as the NaN test, but for ``Infinity``."""
        out = tmp_path / "report.json"
        bad_report = _sample_report()
        bad_report["coverage_pct"] = math.inf
        with pytest.raises(ValueError):
            write_report_atomic(bad_report, out)

    def test_clean_up_tempfile_on_success(self, tmp_path: Path):
        """The sibling tempfile must be unlinked after a
        successful write. Without this, repeated CLI
        invocations would litter the captures directory
        with hidden tempfiles."""
        out = tmp_path / "report.json"
        write_report_atomic(_sample_report(), out)
        siblings = [
            p for p in tmp_path.iterdir()
            if p.name.startswith(".j10_report-")
        ]
        assert siblings == [], (
            f"tempfile leaked: {[str(p) for p in siblings]}"
        )

    def test_clean_up_tempfile_on_failure(self, tmp_path: Path):
        """Even when the write fails (different-content
        pre-existing), the sibling tempfile is unlinked.
        Operators never see ``.j10_report-XXX`` files in
        their captures directory.
        """
        out = tmp_path / "report.json"
        out.write_text("stale content", encoding="utf-8")
        with pytest.raises(ValueError):
            write_report_atomic(_sample_report(), out)
        siblings = [
            p for p in tmp_path.iterdir()
            if p.name.startswith(".j10_report-")
        ]
        assert siblings == [], (
            f"tempfile leaked: {[str(p) for p in siblings]}"
        )


# ---------------------------------------------------------------------------
# 2. write_report (gate's public function) -- the integration


class TestGateWriteReportIntegration:
    """The gate's ``write_report`` delegates to the atomic helper."""

    def test_write_report_produces_valid_json(self, tmp_path: Path):
        # Generate a real report and write it.
        report = cas_reachability_report(tmp_path)
        out = tmp_path / "report.json"
        write_report(report, out)
        # Round-trip: must parse cleanly.
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["verdict"] == "UNREACHABLE"

    def test_write_report_byte_identical_retry(self, tmp_path: Path):
        report = cas_reachability_report(tmp_path)
        out = tmp_path / "report.json"
        write_report(report, out)
        first_bytes = out.read_bytes()
        write_report(report, out)
        second_bytes = out.read_bytes()
        assert first_bytes == second_bytes

    def test_write_report_refuses_different_content(self, tmp_path: Path):
        report = cas_reachability_report(tmp_path)
        out = tmp_path / "report.json"
        # Pre-existing different-content file.
        out.write_text('{"different": "content"}', encoding="utf-8")
        with pytest.raises(ValueError, match="different content"):
            write_report(report, out)


# ---------------------------------------------------------------------------
# 3. End-to-end: the full gate flow writes atomically


class TestEndToEndWriteAtomic:
    """The CLI writes its report via the atomic helper."""

    def test_cli_write_produces_byte_identical_output(
        self, tmp_path: Path
    ):
        # Simulate the CLI's write flow against an empty
        # captures directory.
        report = cas_reachability_report(tmp_path)
        out = tmp_path / "report.json"
        write_report(report, out)
        first = out.read_bytes()
        # A second CLI invocation with the same input MUST
        # produce identical bytes.
        write_report(report, out)
        second = out.read_bytes()
        assert first == second
        # And both must be valid JSON.
        for blob in (first, second):
            data = json.loads(blob)
            assert "verdict" in data
            assert "captured_phases" in data
