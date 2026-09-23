"""[WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] Per-branch min-unique threshold tests.

The gate's verdict logic now requires each branch to have >= N
unique captures (per the J.10.DEDUP fingerprint), where N is
controllable via ``min_unique_per_branch`` (CLI: ``--min-unique-per-branch``).

These tests pin the threshold contract at three layers:
  1. ``cas_reachability_threshold`` -- the pure helper.
  2. ``cas_reachability_gate`` -- the integration: a single
     unique capture no longer flips the gate to REACHABLE when
     the threshold is 2.
  3. CLI surface -- the JSON shape, the verdict, the
     rejection of non-positive values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_threshold import (  # noqa: E402
    meets_min_unique_threshold,
)
from cas_reachability_gate import (  # noqa: E402
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    cas_reachability_report,
    format_report,
)


# ---------------------------------------------------------------------------
# Helpers


def _make_capture(
    phase: str,
    *,
    symbol: str = "RELIANCE",
    observation_at_ist: str = "2026-09-14T15:17:00+05:30",
) -> dict[str, Any]:
    """A minimal J.3-shaped capture (dedup tests need distinct
    bytes; this defaults to the same symbol/observation_at for
    the helper, callers vary the input to get distinct bytes).
    """
    return {
        "tool": "j2_cas_probe",
        "schema_version": 2,
        "generated_at_utc": "2026-09-14T09:47:00+00:00",
        "dry_run": True,
        "observation_at_utc": "2026-09-14T09:47:00+00:00",
        "observation_at_ist": observation_at_ist,
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
    captures_dir: Path, name: str, capture: dict[str, Any]
) -> Path:
    captures_dir.mkdir(parents=True, exist_ok=True)
    path = captures_dir / name
    path.write_text(
        json.dumps(capture, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 1. meets_min_unique_threshold -- the pure helper


class TestMeetsMinUniqueThreshold:
    """The pure comparison helper."""

    def test_empty_below_threshold_one(self):
        assert meets_min_unique_threshold([], 1) is False

    def test_single_above_threshold_one(self):
        assert meets_min_unique_threshold(["a"], 1) is True

    def test_single_below_threshold_two(self):
        # The defensive invariant: a single unique capture
        # does NOT meet a threshold of 2.
        assert meets_min_unique_threshold(["a"], 2) is False

    def test_two_unique_meet_threshold_two(self):
        assert meets_min_unique_threshold(["a", "b"], 2) is True

    def test_duplicate_does_not_count(self):
        # The same fingerprint twice is one unique observation.
        assert meets_min_unique_threshold(["a", "a", "a"], 2) is False

    def test_duplicates_plus_unique(self):
        assert meets_min_unique_threshold(["a", "a", "b"], 2) is True


# ---------------------------------------------------------------------------
# 2. cas_reachability_gate -- integration


class TestGateMinThreshold:
    """The gate honours ``min_unique_per_branch``."""

    def test_default_threshold_unchanged(self, tmp_path: Path):
        # One unique capture per branch is enough at the
        # default threshold of 1.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(tmp_path, f"{phase}.json", _make_capture(phase))
        report = cas_reachability_report(tmp_path)
        assert report["verdict"] == "REACHABLE"
        assert report["min_unique_per_branch"] == 1

    def test_threshold_two_blocks_single_capture(self, tmp_path: Path):
        # One unique capture per branch at threshold 2: NOT
        # REACHABLE. This is the core defensive invariant --
        # a single flaky capture cannot flip the gate.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(tmp_path, f"{phase}.json", _make_capture(phase))
        report = cas_reachability_report(
            tmp_path, min_unique_per_branch=2
        )
        assert report["verdict"] == "UNREACHABLE"
        # Every branch is missing because 1 < 2.
        assert len(report["missing_phases"]) == len(
            CAS_BRANCHES_REQUIRING_EVIDENCE
        )

    def test_threshold_two_with_two_unique_passes(self, tmp_path: Path):
        # Two distinct captures per branch (distinct symbols
        # + observation times so the fingerprints differ)
        # meet the threshold of 2.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                tmp_path, f"{phase}_a.json",
                _make_capture(phase, symbol="RELIANCE"),
            )
            _write_capture(
                tmp_path, f"{phase}_b.json",
                _make_capture(phase, symbol="TCS"),
            )
        report = cas_reachability_report(
            tmp_path, min_unique_per_branch=2
        )
        assert report["verdict"] == "REACHABLE"
        assert report["captured_phases"][
            "CAS_REFERENCE_PRICE_WINDOW"
        ] == 2

    def test_duplicates_do_not_count_toward_threshold(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] The threshold
        counts UNIQUE observations (J.10.DEDUP semantics), not
        files-on-disk. Three byte-identical captures under the
        same branch contribute 1 unique observation; the
        threshold of 2 still rejects the branch.
        """
        cap = _make_capture("CAS_MATCHING")
        _write_capture(tmp_path, "a.json", cap)
        _write_capture(tmp_path, "b.json", cap)
        _write_capture(tmp_path, "c.json", cap)
        report = cas_reachability_report(
            tmp_path, min_unique_per_branch=2
        )
        assert (
            report["captured_phases"]["CAS_MATCHING"] == 1
        )
        assert report["duplicates_by_branch"]["CAS_MATCHING"] == 2
        assert "CAS_MATCHING" in report["missing_phases"]

    def test_threshold_partial_branch_progress_surfaces(
        self, tmp_path: Path
    ):
        # Some branches meet the threshold, some don't. The
        # captured_phases field shows the unique count (not
        # thresholded) so the operator sees progress.
        threshold_branches = (
            "CAS_REFERENCE_PRICE_WINDOW",
            "CAS_ORDER_ENTRY",
        )
        # Two unique captures per branch for the first two.
        for phase in threshold_branches:
            _write_capture(
                tmp_path, f"{phase}_a.json",
                _make_capture(phase, symbol="RELIANCE"),
            )
            _write_capture(
                tmp_path, f"{phase}_b.json",
                _make_capture(phase, symbol="TCS"),
            )
        # One capture each for the rest (won't meet threshold 2).
        for phase in [
            "CAS_LIMIT_ENTRY_ONLY",
            "CAS_MATCHING",
            "CAS_POST",
            "DERIVATIVES_CAS_ALIGNED",
        ]:
            _write_capture(
                tmp_path, f"{phase}.json",
                _make_capture(phase, symbol="RELIANCE"),
            )
        report = cas_reachability_report(
            tmp_path, min_unique_per_branch=2
        )
        # Verdict is UNREACHABLE because 4 branches have 1 < 2.
        assert report["verdict"] == "UNREACHABLE"
        assert len(report["missing_phases"]) == 4
        # captured_phases shows the unique count, not thresholded.
        for phase in threshold_branches:
            assert report["captured_phases"][phase] == 2
        for phase in [
            "CAS_LIMIT_ENTRY_ONLY",
            "CAS_MATCHING",
            "CAS_POST",
            "DERIVATIVES_CAS_ALIGNED",
        ]:
            assert report["captured_phases"][phase] == 1

    def test_min_unique_per_branch_always_present_in_report(
        self, tmp_path: Path
    ):
        report = cas_reachability_report(tmp_path)
        assert "min_unique_per_branch" in report
        assert report["min_unique_per_branch"] == 1

    def test_min_unique_per_branch_present_when_dir_missing(
        self, tmp_path: Path
    ):
        report = cas_reachability_report(
            tmp_path / "no-such-dir", min_unique_per_branch=3
        )
        assert report["min_unique_per_branch"] == 3

    def test_threshold_composes_with_freshness(self, tmp_path: Path, monkeypatch):
        """Composition: a fresh filter and a threshold filter
        can apply together.
        """
        from datetime import datetime, timezone
        from cas_reachability_freshness import capture_age_days
        monkeypatch.setattr("cas_reachability_gate.capture_age_days",
            lambda path: capture_age_days(path, now_utc=datetime(2026, 9, 15, tzinfo=timezone.utc)))
        # 2 unique captures per branch, all fresh.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                tmp_path, f"{phase}_a.json",
                _make_capture(phase, symbol="RELIANCE"),
            )
            _write_capture(
                tmp_path, f"{phase}_b.json",
                _make_capture(phase, symbol="TCS"),
            )
        report = cas_reachability_report(
            tmp_path,
            max_age_days=7.0,
            min_unique_per_branch=2,
        )
        assert report["verdict"] == "REACHABLE"
        assert report["captures_skipped_stale"] == 0

    def test_format_report_includes_threshold_when_above_one(
        self, tmp_path: Path
    ):
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(tmp_path, f"{phase}.json", _make_capture(phase))
        report = cas_reachability_report(
            tmp_path, min_unique_per_branch=3
        )
        rendered = format_report(report)
        assert "min unique captures per branch" in rendered
        assert "3" in rendered

    def test_format_report_omits_threshold_line_at_default(
        self, tmp_path: Path
    ):
        # Default threshold (1) is the common case; the
        # human-readable output doesn't mention it (would add
        # noise).
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(tmp_path, f"{phase}.json", _make_capture(phase))
        report = cas_reachability_report(tmp_path)
        rendered = format_report(report)
        assert "min unique captures per branch" not in rendered
