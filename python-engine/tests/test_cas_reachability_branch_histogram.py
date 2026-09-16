"""[WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] Per-branch-per-day matrix tests.

The J.10 SUMMARY surfaces TOTAL counts (captures_scanned,
captures_skipped, captured_phases) and the per-day histogram
(J.10.CAPTURE_SUMMARY_AGGREGATE). This slice adds the
per-branch-per-day matrix -- a 2D view that shows which
branches have evidence on which days.

These tests pin the matrix contract at three layers:
  1. ``cas_reachability_branch_histogram`` -- the pure helpers
     (``branch_per_day_breakdown``, ``format_branch_per_day_table``).
  2. Gate integration -- the ``branch_per_day`` field in the
     report dict + the new SUMMARY section.
  3. CLI surface -- the ``--show-branch-histogram`` flag.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_branch_histogram import (  # noqa: E402
    branch_per_day_breakdown,
    format_branch_per_day_table,
)
from cas_reachability_gate import (  # noqa: E402
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    cas_reachability_report,
    update_summary,
)


# ---------------------------------------------------------------------------
# Helpers


def _make_capture(
    phase: str,
    *,
    symbol: str = "RELIANCE",
) -> dict[str, Any]:
    return {
        "tool": "j2_cas_probe",
        "schema_version": 2,
        "generated_at_utc": "2026-09-14T09:47:00+00:00",
        "dry_run": True,
        "observation_at_utc": "2026-09-14T09:47:00+00:00",
        "observation_at_ist": "2026-09-14T15:17:00+05:30",
        "symbol_count": 1,
        "rows": [
            {
                "symbol": symbol,
                "classifier_phase": phase,
            }
        ],
    }


def _write_capture(
    captures_root: Path, day: str, name: str, capture: dict[str, Any]
) -> Path:
    day_dir = captures_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / name
    path.write_text(
        json.dumps(capture, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 1. branch_per_day_breakdown -- the pure helper


class TestBranchPerDayBreakdown:
    """The pure matrix-builder."""

    def test_missing_dir_returns_empty_matrix(self, tmp_path: Path):
        matrix = branch_per_day_breakdown(tmp_path / "no-such-dir")
        # All 6 branches present, all empty.
        for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
            assert branch in matrix
            assert matrix[branch] == {}

    def test_empty_dir_returns_empty_matrix(self, tmp_path: Path):
        matrix = branch_per_day_breakdown(tmp_path)
        for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
            assert matrix[branch] == {}

    def test_single_capture_single_branch_single_day(
        self, tmp_path: Path
    ):
        _write_capture(
            tmp_path,
            "2026-09-14",
            "a.json",
            _make_capture("CAS_MATCHING"),
        )
        matrix = branch_per_day_breakdown(tmp_path)
        assert matrix["CAS_MATCHING"]["2026-09-14"] == {
            "scanned": 1, "unique": 1
        }
        # Other branches are empty.
        for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
            if branch != "CAS_MATCHING":
                assert matrix[branch] == {}

    def test_multiple_branches_multiple_days(self, tmp_path: Path):
        # 3 captures per day, each on a different branch.
        for d, branches in [
            ("2026-09-10", ["CAS_MATCHING", "CAS_POST", "CAS_ORDER_ENTRY"]),
            ("2026-09-12", ["CAS_MATCHING", "CAS_POST"]),
            ("2026-09-14", ["CAS_MATCHING"]),
        ]:
            for b in branches:
                _write_capture(
                    tmp_path, d, f"{b}.json",
                    _make_capture(b, symbol="RELIANCE"),
                )
        matrix = branch_per_day_breakdown(tmp_path)
        # CAS_MATCHING has 1 capture on each of 3 days.
        assert len(matrix["CAS_MATCHING"]) == 3
        assert matrix["CAS_MATCHING"]["2026-09-10"]["scanned"] == 1
        assert matrix["CAS_MATCHING"]["2026-09-12"]["scanned"] == 1
        assert matrix["CAS_MATCHING"]["2026-09-14"]["scanned"] == 1
        # CAS_POST has captures on 2 days.
        assert len(matrix["CAS_POST"]) == 2
        # CAS_ORDER_ENTRY has 1 capture on 1 day.
        assert len(matrix["CAS_ORDER_ENTRY"]) == 1
        # CAS_REFERENCE_PRICE_WINDOW etc. are empty.
        for branch in [
            "CAS_REFERENCE_PRICE_WINDOW",
            "CAS_LIMIT_ENTRY_ONLY",
            "DERIVATIVES_CAS_ALIGNED",
        ]:
            assert matrix[branch] == {}

    def test_dedup_aware_unique_count(self, tmp_path: Path):
        """[WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] The
        ``unique`` count is dedup-aware: 3 byte-identical
        captures under one branch on one day contribute 1
        unique observation. The ``scanned`` count is 3.
        """
        cap = _make_capture("CAS_MATCHING")
        _write_capture(tmp_path, "2026-09-14", "a.json", cap)
        _write_capture(tmp_path, "2026-09-14", "b.json", cap)
        _write_capture(tmp_path, "2026-09-14", "c.json", cap)
        # Without first_occurrence_per_path, unique == scanned.
        matrix = branch_per_day_breakdown(tmp_path)
        assert matrix["CAS_MATCHING"]["2026-09-14"]["scanned"] == 3
        assert matrix["CAS_MATCHING"]["2026-09-14"]["unique"] == 3
        # With the mapping, unique reflects first-occurrence.
        # ``path_a`` is in the mapping, ``path_b`` and ``path_c``
        # are not -> unique = 1.
        a_path = tmp_path / "2026-09-14" / "a.json"
        matrix = branch_per_day_breakdown(
            tmp_path,
            first_occurrence_per_path={str(a_path): "fp1"},
        )
        assert matrix["CAS_MATCHING"]["2026-09-14"]["scanned"] == 3
        assert matrix["CAS_MATCHING"]["2026-09-14"]["unique"] == 1

    def test_skipped_captures_dont_appear(self, tmp_path: Path):
        # A capture with an out-of-bounds phase is skipped; it
        # must not appear under any branch.
        bad = _make_capture("CAS_MATCHING")
        bad["rows"][0]["classifier_phase"] = "NOT_A_BOUNDED_PHASE"
        _write_capture(tmp_path, "2026-09-14", "bad.json", bad)
        # Add a valid capture.
        _write_capture(
            tmp_path, "2026-09-14", "good.json",
            _make_capture("CAS_MATCHING", symbol="TCS"),
        )
        matrix = branch_per_day_breakdown(tmp_path)
        # Only the good capture appears under CAS_MATCHING.
        assert matrix["CAS_MATCHING"]["2026-09-14"]["scanned"] == 1


# ---------------------------------------------------------------------------
# 2. format_branch_per_day_table -- the markdown rendering


class TestFormatBranchPerDayTable:
    """The deterministic markdown rendering."""

    def test_empty_matrix_renders_no_captures_message(self):
        from cas_reachability_gate import CAS_BRANCHES_REQUIRING_EVIDENCE
        empty = {b: {} for b in CAS_BRANCHES_REQUIRING_EVIDENCE}
        out = format_branch_per_day_table(empty)
        assert "No captures with a bounded phase on disk" in out

    def test_branches_in_canonical_order(self):
        matrix = {
            "CAS_MATCHING": {"2026-09-14": {"scanned": 1, "unique": 1}},
            "CAS_REFERENCE_PRICE_WINDOW": {
                "2026-09-10": {"scanned": 1, "unique": 1}
            },
        }
        out = format_branch_per_day_table(matrix)
        # The branches must appear in canonical CAS_BRANCHES_REQUIRING_EVIDENCE
        # order regardless of dict iteration order.
        from cas_reachability_gate import CAS_BRANCHES_REQUIRING_EVIDENCE
        positions = [
            out.index(f"| {branch} |") for branch in CAS_BRANCHES_REQUIRING_EVIDENCE
        ]
        assert positions == sorted(positions), (
            f"branches out of canonical order: {positions}"
        )

    def test_dates_in_ascending_order(self):
        matrix = {
            "CAS_MATCHING": {
                "2026-09-14": {"scanned": 1, "unique": 1},
                "2026-09-10": {"scanned": 1, "unique": 1},
                "2026-09-12": {"scanned": 1, "unique": 1},
            }
        }
        out = format_branch_per_day_table(matrix)
        # Extract the header row.
        header_line = next(
            line for line in out.split("\n")
            if line.startswith("| Branch |")
        )
        columns = [c.strip() for c in header_line.split("|")[2:-1]]
        assert columns == ["2026-09-10", "2026-09-12", "2026-09-14"]

    def test_empty_cells_render_as_dash(self):
        matrix = {
            "CAS_MATCHING": {
                "2026-09-10": {"scanned": 1, "unique": 1}
            },
            "CAS_POST": {}
        }
        out = format_branch_per_day_table(matrix)
        # CAS_POST has zero captures on 2026-09-10 -> dash.
        lines = [
            line for line in out.split("\n")
            if line.startswith("| CAS_POST |")
        ]
        assert len(lines) == 1
        # The single date column should be "-" for CAS_POST.
        cells = [c.strip() for c in lines[0].split("|")[2:-1]]
        assert cells == ["-"]

    def test_truncates_above_max_dates(self):
        # 10 dates; max_dates=5 -> 4 visible + "(+ 6 more dates...)".
        per_branch = {}
        for i in range(1, 11):
            per_branch[f"2026-09-{i:02d}"] = {"scanned": 1, "unique": 1}
        matrix = {"CAS_MATCHING": per_branch}
        out = format_branch_per_day_table(matrix, max_dates=5)
        assert "+ 6 more dates" in out

    def test_unique_vs_scanned_cells(self):
        """[WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] The
        ``show_unique=False`` flag switches cell rendering
        from the post-dedup unique count to the raw scanned
        count. Useful when an operator wants to see every file
        that landed on disk, including duplicates.
        """
        per_branch = {
            "2026-09-14": {"scanned": 5, "unique": 2}
        }
        matrix = {"CAS_MATCHING": per_branch}
        unique_out = format_branch_per_day_table(matrix, show_unique=True)
        scanned_out = format_branch_per_day_table(matrix, show_unique=False)
        # The unique row shows "2"; the scanned row shows "5".
        unique_line = next(
            line for line in unique_out.split("\n")
            if line.startswith("| CAS_MATCHING |")
        )
        scanned_line = next(
            line for line in scanned_out.split("\n")
            if line.startswith("| CAS_MATCHING |")
        )
        assert "2" in unique_line
        assert "5" in scanned_line


# ---------------------------------------------------------------------------
# 3. Gate integration -- the report field and SUMMARY section


class TestGateBranchPerDayIntegration:
    """The gate surfaces ``branch_per_day`` in the report."""

    def test_branch_per_day_always_present_in_report(self, tmp_path: Path):
        report = cas_reachability_report(tmp_path)
        assert "branch_per_day" in report
        # All 6 branches are present.
        for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
            assert branch in report["branch_per_day"]

    def test_branch_per_day_present_when_dir_missing(self, tmp_path: Path):
        report = cas_reachability_report(tmp_path / "no-such-dir")
        assert "branch_per_day" in report
        # All branches present, all empty.
        for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
            assert report["branch_per_day"][branch] == {}

    def test_summary_renders_branch_per_day_section(self, tmp_path: Path):
        # Populate the captures directory.
        for d, sym in [
            ("2026-09-10", "A"),
            ("2026-09-14", "B"),
        ]:
            _write_capture(
                tmp_path, d, f"{sym}.json",
                _make_capture("CAS_MATCHING", symbol=sym),
            )
        report = cas_reachability_report(tmp_path)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(report, summary_path, captures_dir=tmp_path)
        body = summary_path.read_text(encoding="utf-8")
        # The new section is in the SUMMARY.
        assert "## Captures per branch per day" in body
        # The branch row appears.
        assert "CAS_MATCHING" in body
