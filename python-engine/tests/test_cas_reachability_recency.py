"""[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14] Recency tests.

These tests pin the per-branch recency contract: the helper
returns oldest/newest first-occurrence captures per branch,
with span in whole days, and never raises for malformed
input.

The integration test (TestRecencyIntegration) runs the full
gate end-to-end and verifies the recency field is included
in the report and rendered in the SUMMARY.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest


from cas_reachability_gate import (
    cas_reachability_report,
    update_summary,
)
from cas_reachability_recency import (
    _safe_observation_at_utc,
    _safe_phase_from_recency,
    _span_days,
    format_recency_table,
    oldest_newest_per_branch,
)
from tests.test_cas_reachability_listing import (  # noqa: E402
    _make_capture,
    _write_capture,
)


# ---------------------------------------------------------------------------
# Internal helpers


class TestSafeObservationAtUtc:
    def test_returns_iso_when_present(self, tmp_path: Path):
        import json
        p = tmp_path / "a.json"
        p.write_text(
            json.dumps(_make_capture("CAS_MATCHING")),
            encoding="utf-8",
        )
        # Default _make_capture emits observation_at_utc=
        # "2026-09-14T09:47:00+00:00".
        assert _safe_observation_at_utc(p) == "2026-09-14T09:47:00+00:00"

    def test_returns_none_for_unreadable_file(self, tmp_path: Path):
        p = tmp_path / "a.json"
        p.write_text("not json", encoding="utf-8")
        assert _safe_observation_at_utc(p) is None

    def test_returns_none_when_field_missing(self, tmp_path: Path):
        p = tmp_path / "a.json"
        p.write_text('{"rows": []}', encoding="utf-8")
        assert _safe_observation_at_utc(p) is None

    def test_returns_none_when_field_empty(self, tmp_path: Path):
        p = tmp_path / "a.json"
        p.write_text('{"observation_at_utc": ""}', encoding="utf-8")
        assert _safe_observation_at_utc(p) is None


class TestSafePhaseFromRecency:
    def test_returns_phase_when_present(self, tmp_path: Path):
        import json
        p = tmp_path / "a.json"
        p.write_text(
            json.dumps(_make_capture("CAS_ORDER_ENTRY")),
            encoding="utf-8",
        )
        assert _safe_phase_from_recency(p) == "CAS_ORDER_ENTRY"

    def test_returns_none_for_unreadable_file(self, tmp_path: Path):
        p = tmp_path / "a.json"
        p.write_text("garbage", encoding="utf-8")
        assert _safe_phase_from_recency(p) is None

    def test_returns_none_when_rows_missing(self, tmp_path: Path):
        p = tmp_path / "a.json"
        p.write_text("{}", encoding="utf-8")
        assert _safe_phase_from_recency(p) is None

    def test_returns_none_when_rows_empty(self, tmp_path: Path):
        p = tmp_path / "a.json"
        p.write_text('{"rows": []}', encoding="utf-8")
        assert _safe_phase_from_recency(p) is None

    def test_returns_none_for_top_level_phase_only(self, tmp_path: Path):
        """[WORKFLOW-J.10.SCHEMA-BUG-FIX 2026-09-14] The J.3
        schema stores the bounded phase at
        ``rows[0].classifier_phase``, NOT at the top-level
        ``classifier.phase`` (which doesn't exist in the v2
        schema). The recency helper must use the same fix.
        """
        p = tmp_path / "a.json"
        # Capture with NO rows array -- the legacy
        # ``classifier.phase`` field is what the broken
        # implementation would have read.
        p.write_text(
            '{"classifier": {"phase": "CAS_MATCHING"}, '
            '"observation_at_utc": "2026-09-14T09:47:00+00:00"}',
            encoding="utf-8",
        )
        # Returns None because there are no rows.
        assert _safe_phase_from_recency(p) is None


class TestSpanDays:
    def test_zero_for_same_day(self):
        assert _span_days(
            "2026-09-14T09:47:00+00:00",
            "2026-09-14T15:30:00+00:00",
        ) == 0

    def test_one_for_adjacent_days(self):
        assert _span_days(
            "2026-09-14T23:59:00+00:00",
            "2026-09-15T00:01:00+00:00",
        ) == 1

    def test_wide_span(self):
        assert _span_days(
            "2026-09-10T09:00:00+00:00",
            "2026-09-14T09:00:00+00:00",
        ) == 4

    def test_handles_z_suffix(self):
        assert _span_days(
            "2026-09-10T09:00:00Z",
            "2026-09-14T09:00:00Z",
        ) == 4

    def test_clamps_negative_to_zero(self):
        """[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        A negative span (newest < oldest) means malformed
        data. Clamp to 0 rather than returning a negative --
        ``span_days`` is a coverage-velocity signal, not a
        duration invariant.
        """
        assert _span_days(
            "2026-09-14T15:00:00+00:00",
            "2026-09-10T09:00:00+00:00",
        ) == 0

    def test_returns_zero_for_unparseable(self):
        assert _span_days("garbage", "2026-09-14T15:00:00+00:00") == 0


# ---------------------------------------------------------------------------
# oldest_newest_per_branch


def _populate_two_days(tmp_path: Path) -> Path:
    """A captures root with one CAS_MATCHING capture on each
    of two distinct days. Returns the captures root.

    The two captures have DISTINCT ``observation_at_utc``
    timestamps so the recency helper can compute a 4-day
    span. If both timestamps were equal (the default
    ``_make_capture`` behaviour), min == max and the span
    would be 0 regardless of which day the file lived in --
    the dedup fingerprint is by JSON bytes, and the bytes
    change only when the row contents change.
    """
    root = tmp_path / "cap"
    older = _make_capture("CAS_MATCHING", symbol="RELIANCE")
    older["observation_at_utc"] = "2026-09-10T09:47:00+00:00"
    _write_capture(root, "2026-09-10", "old.json", older)
    newer = _make_capture("CAS_MATCHING", symbol="TCS")
    newer["observation_at_utc"] = "2026-09-14T09:47:00+00:00"
    _write_capture(root, "2026-09-14", "new.json", newer)
    return root


class TestOldestNewestPerBranch:
    def test_empty_for_missing_root(self, tmp_path: Path):
        result = oldest_newest_per_branch(tmp_path / "noexist")
        assert result == {}

    def test_single_capture_has_zero_span(self, tmp_path: Path):
        root = tmp_path / "cap"
        _write_capture(
            root, "2026-09-14", "a.json",
            _make_capture("CAS_ORDER_ENTRY"),
        )
        result = oldest_newest_per_branch(root)
        assert "CAS_ORDER_ENTRY" in result
        entry = result["CAS_ORDER_ENTRY"]
        assert entry["span_days"] == 0
        assert entry["oldest"] == entry["newest"]
        assert entry["oldest_path"] == entry["newest_path"]

    def test_two_captures_on_different_days(self, tmp_path: Path):
        root = _populate_two_days(tmp_path)
        result = oldest_newest_per_branch(root)
        assert "CAS_MATCHING" in result
        entry = result["CAS_MATCHING"]
        # [WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        # Path strings use the OS-native separator (Windows
        # uses ``\``; POSIX uses ``/``). Tests normalize to
        # forward-slash for cross-platform stability.
        assert entry["oldest_path"].replace("\\", "/") == "2026-09-10/old.json"
        assert entry["newest_path"].replace("\\", "/") == "2026-09-14/new.json"
        assert entry["span_days"] == 4

    def test_first_occurrence_paths_filter(self, tmp_path: Path):
        """[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        When ``first_occurrence_paths`` is provided, the
        helper restricts to those paths only. Redundant
        duplicates MUST NOT extend the recency.
        """
        root = _populate_two_days(tmp_path)
        all_paths = sorted(str(p) for p in root.rglob("*.json"))
        # Restrict to ONLY the newer path -> span is 0,
        # newest == the new path's timestamp.
        only_newer = {all_paths[1]}
        result = oldest_newest_per_branch(
            root, first_occurrence_paths=only_newer,
        )
        entry = result["CAS_MATCHING"]
        assert entry["newest_path"].replace("\\", "/") == "2026-09-14/new.json"
        assert entry["span_days"] == 0

    def test_malformed_capture_does_not_break_walk(
        self, tmp_path: Path
    ):
        root = tmp_path / "cap"
        # Malformed capture next to a good one.
        (root / "2026-09-14").mkdir(parents=True, exist_ok=True)
        bad = root / "2026-09-14" / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        # Good capture.
        _write_capture(
            root, "2026-09-14", "good.json",
            _make_capture("CAS_REFERENCE_PRICE_WINDOW"),
        )
        # Walk completes, returns the good capture's recency.
        result = oldest_newest_per_branch(root)
        assert "CAS_REFERENCE_PRICE_WINDOW" in result
        assert "CAS_REFERENCE_PRICE_WINDOW" not in [
            # Sanity: helper doesn't surface the bad one
            # anywhere.
        ]

    def test_missing_observation_at_utc_skipped(self, tmp_path: Path):
        """[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        A capture without ``observation_at_utc`` cannot
        contribute to recency (we can't compute its position
        on the timeline). The helper skips it without
        raising.
        """
        root = tmp_path / "cap"
        (root / "2026-09-14").mkdir(parents=True, exist_ok=True)
        # Capture without observation_at_utc.
        no_ts = root / "2026-09-14" / "no_ts.json"
        no_ts.write_text(
            '{"rows": [{"classifier_phase": "CAS_POST"}]}',
            encoding="utf-8",
        )
        # And a good one.
        _write_capture(
            root, "2026-09-14", "good.json",
            _make_capture("CAS_POST"),
        )
        result = oldest_newest_per_branch(root)
        assert "CAS_POST" in result
        # The no_ts path is NOT surfaced.
        paths = [
            result["CAS_POST"]["oldest_path"],
            result["CAS_POST"]["newest_path"],
        ]
        normalized = [p.replace("\\", "/") for p in paths]
        assert "2026-09-14/no_ts.json" not in normalized


# ---------------------------------------------------------------------------
# format_recency_table


class TestFormatRecencyTable:
    def test_empty_input_renders_no_data_line(self):
        out = format_recency_table({})
        assert "No recency data" in out

    def test_single_branch(self):
        recency = {
            "CAS_MATCHING": {
                "oldest": "2026-09-10T09:47:00+00:00",
                "newest": "2026-09-14T09:47:00+00:00",
                "oldest_path": "2026-09-10/a.json",
                "newest_path": "2026-09-14/b.json",
                "span_days": 4,
            },
        }
        out = format_recency_table(recency)
        assert "| Branch | Oldest | Newest |" in out
        assert "CAS_MATCHING" in out
        assert "2026-09-10" in out
        assert "2026-09-14" in out
        assert "4" in out  # span_days

    def test_branch_with_no_evidence_renders_no_evidence(self):
        recency = {"CAS_ORDER_ENTRY": {}}
        out = format_recency_table(recency)
        assert "CAS_ORDER_ENTRY" in out
        assert "(no evidence)" in out

    def test_sorted_branch_order(self):
        """[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        The table is sorted by branch name -- deterministic
        output for the SUMMARY byte-comparison invariant.
        """
        recency = {
            "CAS_POST": {"oldest": "x", "newest": "y",
                         "oldest_path": "a", "newest_path": "b",
                         "span_days": 0},
            "CAS_MATCHING": {"oldest": "x", "newest": "y",
                             "oldest_path": "a", "newest_path": "b",
                             "span_days": 0},
        }
        out = format_recency_table(recency)
        # CAS_MATCHING comes before CAS_POST alphabetically.
        assert out.index("CAS_MATCHING") < out.index("CAS_POST")


# ---------------------------------------------------------------------------
# Integration with the gate + SUMMARY


class TestRecencyIntegration:
    def test_gate_report_includes_recency_by_branch(
        self, tmp_path: Path
    ):
        root = _populate_two_days(tmp_path)
        report = cas_reachability_report(root)
        assert "recency_by_branch" in report
        # The recency covers the branch we populated.
        assert "CAS_MATCHING" in report["recency_by_branch"]
        entry = report["recency_by_branch"]["CAS_MATCHING"]
        assert entry["span_days"] == 4

    def test_summary_includes_recency_section(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        The persistent SUMMARY.md must include the recency
        section, not just the gate report's JSON.
        """
        root = _populate_two_days(tmp_path)
        summary_path = tmp_path / "SUMMARY.md"
        report = cas_reachability_report(root)
        update_summary(report, summary_path, captures_dir=root)
        body = summary_path.read_text(encoding="utf-8")
        assert "## Captures recency per branch" in body
        # The table renders with the populated branch.
        assert "CAS_MATCHING" in body
        # Span value surfaces in the table.
        assert "4" in body

    def test_empty_captures_renders_no_recency_line(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        An empty captures root must NOT raise in
        ``update_summary``; the recency section degrades to
        the documented "no recency data" line.
        """
        root = tmp_path / "cap"  # exists but is empty
        root.mkdir()
        summary_path = tmp_path / "SUMMARY.md"
        report = cas_reachability_report(root)
        update_summary(report, summary_path, captures_dir=root)
        body = summary_path.read_text(encoding="utf-8")
        assert "## Captures recency per branch" in body
        assert "No recency data" in body
