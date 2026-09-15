"""[WORKFLOW-J.10.CAPTURE_SUMMARY_AGGREGATE 2026-09-14] Per-day histogram tests.

The SUMMARY surfaces TOTAL counts but not evidence velocity
over time. The per-day histogram completes the operator's
audit picture: how many captures per day, when the bulk of
evidence was collected, and whether evidence is concentrated
or stale.

These tests pin the histogram contract at two layers:
  1. ``cas_reachability_aggregate`` -- the pure helpers
     (``per_day_breakdown``, ``format_per_day_table``).
  2. ``cas_reachability_gate`` -- the integration: the
     histogram is computed from the dedup filter's
     verdict-contributing paths.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_aggregate import (  # noqa: E402
    format_per_day_table,
    per_day_breakdown,
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
    day: str = "2026-09-14",
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
                "classifier_observation_at_utc": "2026-09-14T09:47:00+00:00",
            }
        ],
    }


def _write_capture(
    captures_root: Path, day: str, name: str, capture: dict[str, Any]
) -> Path:
    """Write a J.3 capture under ``<captures_root>/<day>/<name>.json``."""
    day_dir = captures_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / name
    path.write_text(
        json.dumps(capture, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 1. per_day_breakdown -- the pure helper


class TestPerDayBreakdown:
    """The pure bucketing helper."""

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        assert per_day_breakdown(tmp_path) == {}

    def test_missing_dir_returns_empty(self, tmp_path: Path):
        assert per_day_breakdown(tmp_path / "no-such-dir") == {}

    def test_single_day_single_capture(self, tmp_path: Path):
        _write_capture(
            tmp_path,
            "2026-09-14",
            "a.json",
            _make_capture("CAS_MATCHING"),
        )
        result = per_day_breakdown(tmp_path)
        assert result == {
            "2026-09-14": {"scanned": 1, "unique": 1}
        }

    def test_single_day_multiple_captures(self, tmp_path: Path):
        for sym in ("RELIANCE", "TCS", "INFY"):
            _write_capture(
                tmp_path,
                "2026-09-14",
                f"{sym}.json",
                _make_capture("CAS_MATCHING", symbol=sym),
            )
        result = per_day_breakdown(tmp_path)
        assert result == {
            "2026-09-14": {"scanned": 3, "unique": 3}
        }

    def test_multiple_days_separate_buckets(self, tmp_path: Path):
        for day, sym in [
            ("2026-09-10", "A"),
            ("2026-09-12", "B"),
            ("2026-09-14", "C"),
        ]:
            _write_capture(
                tmp_path,
                day,
                f"{sym}.json",
                _make_capture("CAS_MATCHING", symbol=sym),
            )
        result = per_day_breakdown(tmp_path)
        assert result == {
            "2026-09-10": {"scanned": 1, "unique": 1},
            "2026-09-12": {"scanned": 1, "unique": 1},
            "2026-09-14": {"scanned": 1, "unique": 1},
        }

    def test_unfiled_bucket_for_root_level_capture(
        self, tmp_path: Path
    ):
        # A stray JSON at the captures_root level (no
        # YYYY-MM-DD subdirectory) buckets under "(unfiled)".
        (tmp_path / "stray.json").write_text(
            json.dumps(_make_capture("CAS_MATCHING")),
            encoding="utf-8",
        )
        result = per_day_breakdown(tmp_path)
        assert "(unfiled)" in result
        assert result["(unfiled)"] == {"scanned": 1, "unique": 1}

    def test_unique_per_path_only_counts_mapped_paths(
        self, tmp_path: Path
    ):
        # Two captures in one day. Pass a mapping that ONLY
        # includes the first path; ``unique`` for that day
        # should be 1 (only the mapped path counts as unique).
        p1 = _write_capture(
            tmp_path,
            "2026-09-14",
            "first.json",
            _make_capture("CAS_MATCHING", symbol="RELIANCE"),
        )
        p2 = _write_capture(
            tmp_path,
            "2026-09-14",
            "second.json",
            _make_capture("CAS_MATCHING", symbol="TCS"),
        )
        # Map only the first path. ``scanned`` is still 2 (every
        # JSON file under the day); ``unique`` is 1 (only p1
        # contributes as a verdict-bearing observation).
        result = per_day_breakdown(
            tmp_path, unique_per_path={str(p1): "fp1"}
        )
        assert result["2026-09-14"]["scanned"] == 2
        assert result["2026-09-14"]["unique"] == 1
        assert str(p2) not in result  # defensive: the helper only
        # touches the mapping's keys; p2 was scanned but not
        # mapped so it doesn't appear in ``unique`` count beyond
        # the bucket-level counter.


# ---------------------------------------------------------------------------
# 2. format_per_day_table -- the markdown rendering


class TestFormatPerDayTable:
    """The markdown rendering helper."""

    def test_empty_returns_no_captures_message(self):
        out = format_per_day_table({})
        assert "No captures" in out

    def test_single_day_renders_table(self):
        out = format_per_day_table(
            {"2026-09-14": {"scanned": 3, "unique": 2}}
        )
        assert "| Date | Scanned | Unique |" in out
        assert "| 2026-09-14 | 3 | 2 |" in out

    def test_sorted_ascending(self):
        out = format_per_day_table(
            {
                "2026-09-14": {"scanned": 1, "unique": 1},
                "2026-09-10": {"scanned": 1, "unique": 1},
                "2026-09-12": {"scanned": 1, "unique": 1},
            }
        )
        # Lex-sort puts 2026-09-10 first; check the order.
        lines = [
            line for line in out.split("\n")
            if line.startswith("| 2026-")
        ]
        assert lines[0].startswith("| 2026-09-10")
        assert lines[1].startswith("| 2026-09-12")
        assert lines[2].startswith("| 2026-09-14")

    def test_unfiled_appears_first(self):
        out = format_per_day_table(
            {
                "2026-09-14": {"scanned": 1, "unique": 1},
                "(unfiled)": {"scanned": 1, "unique": 1},
            }
        )
        lines = [
            line for line in out.split("\n")
            if line.startswith("| ")
            and ("2026-" in line or "(unfiled)" in line)
        ]
        assert "(unfiled)" in lines[0]

    def test_truncates_above_max_rows(self):
        per_day = {
            f"2026-09-{i:02d}": {"scanned": 1, "unique": 1}
            for i in range(1, 20)
        }
        out = format_per_day_table(per_day, max_rows=5)
        # Should show max_rows - 1 = 4 dates + "+ N more days" footer.
        assert "+ 15 more days" in out
        # The footer row count check: 20 days total - 4 shown = 16
        # collapsed. The footer says "+ 16 more days" but the
        # most recent 4 are shown.
        # (Per-day dict has 20 entries; max_rows=5 means we keep
        # 4 most-recent; the "+ 16 more days" footer sums the
        # remaining 16.)

    def test_max_rows_exact_no_truncation(self):
        per_day = {
            f"2026-09-{i:02d}": {"scanned": 1, "unique": 1}
            for i in range(1, 8)
        }
        out = format_per_day_table(per_day, max_rows=7)
        assert "more days" not in out

    def test_max_rows_one_shows_only_footer(self):
        per_day = {
            f"2026-09-{i:02d}": {"scanned": 1, "unique": 1}
            for i in range(1, 5)
        }
        out = format_per_day_table(per_day, max_rows=1)
        # max_rows=1 -> 0 visible rows + "+ N more days" footer.
        assert "+ 4 more days" in out


# ---------------------------------------------------------------------------
# 3. cas_reachability_gate -- integration


class TestGatePerDay:
    """The gate computes the per-day histogram and surfaces it."""

    def test_captures_per_day_always_present_in_report(
        self, tmp_path: Path
    ):
        report = cas_reachability_report(tmp_path)
        assert "captures_per_day" in report
        assert report["captures_per_day"] == {}

    def test_captures_per_day_present_when_dir_missing(
        self, tmp_path: Path
    ):
        report = cas_reachability_report(
            tmp_path / "no-such-dir"
        )
        assert "captures_per_day" in report
        assert report["captures_per_day"] == {}

    def test_captures_per_day_reflects_writes(self, tmp_path: Path):
        # Six unique captures across three days.
        for day, sym in [
            ("2026-09-10", "A"),
            ("2026-09-12", "B"),
            ("2026-09-14", "C"),
            ("2026-09-10", "D"),
            ("2026-09-12", "E"),
            ("2026-09-14", "F"),
        ]:
            _write_capture(
                tmp_path,
                day,
                f"{sym}.json",
                _make_capture("CAS_MATCHING", symbol=sym),
            )
        report = cas_reachability_report(tmp_path)
        # All six under one branch -> one unique per branch per
        # day (J.10.DEDUP semantics; fingerprint differs by
        # symbol). Each day has scanned=2, unique=2.
        assert report["captures_per_day"]["2026-09-10"]["scanned"] == 2
        assert report["captures_per_day"]["2026-09-10"]["unique"] == 2
        assert report["captures_per_day"]["2026-09-12"]["scanned"] == 2
        assert report["captures_per_day"]["2026-09-12"]["unique"] == 2
        assert report["captures_per_day"]["2026-09-14"]["scanned"] == 2
        assert report["captures_per_day"]["2026-09-14"]["unique"] == 2

    def test_dedup_inside_branch_does_not_inflate_unique(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.CAPTURE_SUMMARY_AGGREGATE 2026-09-14]
        The histogram's ``unique`` column must reflect J.10.DEDUP
        semantics: a duplicate under the same branch contributes
        1 unique observation (the FIRST occurrence). Captures
        with the same fingerprint don't inflate ``unique``.
        """
        cap = _make_capture("CAS_MATCHING")
        _write_capture(tmp_path, "2026-09-14", "a.json", cap)
        _write_capture(tmp_path, "2026-09-14", "b.json", cap)
        _write_capture(tmp_path, "2026-09-14", "c.json", cap)
        report = cas_reachability_report(tmp_path)
        assert (
            report["captures_per_day"]["2026-09-14"]["scanned"] == 3
        )
        assert (
            report["captures_per_day"]["2026-09-14"]["unique"] == 1
        )

    def test_summary_renders_per_day_section(self, tmp_path: Path):
        for day, sym in [
            ("2026-09-10", "A"),
            ("2026-09-12", "B"),
            ("2026-09-14", "C"),
        ]:
            _write_capture(
                tmp_path,
                day,
                f"{sym}.json",
                _make_capture("CAS_MATCHING", symbol=sym),
            )
        report = cas_reachability_report(tmp_path)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=tmp_path
        )
        body = summary_path.read_text(encoding="utf-8")
        # The SUMMARY has the new section.
        assert "## Captures per day" in body
        # The table renders all three days.
        assert "2026-09-10" in body
        assert "2026-09-12" in body
        assert "2026-09-14" in body
        # The columns are labelled.
        assert "| Date | Scanned | Unique |" in body

    def test_summary_with_no_captures_says_so(self, tmp_path: Path):
        report = cas_reachability_report(tmp_path)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=tmp_path
        )
        body = summary_path.read_text(encoding="utf-8")
        assert "## Captures per day" in body
        assert "No captures scanned yet" in body
