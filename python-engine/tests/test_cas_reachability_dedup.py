"""[WORKFLOW-J.10.DEDUP 2026-09-14] Capture-fingerprint dedup tests.

The gate's reachability count must reflect UNIQUE observations,
not files-on-disk. A duplicate capture (operator retry without
changing inputs, or an accidental ``cp``) must NOT silently
inflate the count toward the REACHABLE threshold.

These tests pin the dedup contract at two layers:
  1. ``cas_reachability_dedup`` -- the pure helpers
     (``fingerprint_of``, ``dedup_count``).
  2. ``cas_reachability_gate`` -- the integration: the gate
     counts UNIQUE captures per branch and surfaces
     ``duplicates_by_branch`` in the report dict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_dedup import (  # noqa: E402
    FINGERPRINT_HEX_LENGTH,
    dedup_count,
    fingerprint_of,
)
from cas_reachability_gate import (  # noqa: E402
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    cas_reachability_report,
    format_report,
    update_summary,
)


# ---------------------------------------------------------------------------
# Helper: build a J.3-shaped capture


def _make_capture(
    phase: str,
    *,
    symbol: str = "RELIANCE",
    observation_at_ist: str = "2026-09-14T15:17:00+05:30",
    schema_version: int = 2,
) -> dict[str, Any]:
    """Build a minimal J.3-shaped capture dict for the given phase.

    The schema fields are exactly what the gate reads:
    ``rows[0].classifier_phase``. Everything else is filler that
    matches the documented required keys.
    """
    return {
        "tool": "j2_cas_probe",
        "schema_version": schema_version,
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
    captures_dir: Path,
    name: str,
    capture: dict[str, Any],
) -> Path:
    """Serialise a capture to ``captures_dir/<name>.json`` and return the path."""
    captures_dir.mkdir(parents=True, exist_ok=True)
    path = captures_dir / name
    path.write_text(
        json.dumps(capture, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 1. cas_reachability_dedup -- pure helpers


class TestFingerprintOf:
    """The SHA-256[:16] fingerprint helper."""

    def test_returns_16_hex_chars(self, tmp_path: Path):
        p = tmp_path / "cap.json"
        p.write_text(json.dumps({"x": 1}), encoding="utf-8")
        fp = fingerprint_of(p)
        assert fp is not None
        assert len(fp) == FINGERPRINT_HEX_LENGTH == 16
        # All hex chars.
        int(fp, 16)  # raises if not hex

    def test_stable_across_calls(self, tmp_path: Path):
        p = tmp_path / "cap.json"
        p.write_text(json.dumps({"x": 1}), encoding="utf-8")
        assert fingerprint_of(p) == fingerprint_of(p)

    def test_different_bytes_produce_different_fingerprints(
        self, tmp_path: Path
    ):
        p1 = tmp_path / "a.json"
        p2 = tmp_path / "b.json"
        p1.write_text(json.dumps({"x": 1}), encoding="utf-8")
        p2.write_text(json.dumps({"x": 2}), encoding="utf-8")
        assert fingerprint_of(p1) != fingerprint_of(p2)

    def test_byte_order_is_canonical(self, tmp_path: Path):
        """The bytes-path contract: two files with the same bytes
        fingerprint the same; two files with different bytes
        fingerprint differently.

        The probe uses ``json.dumps(..., sort_keys=True)`` so
        in production the bytes are deterministic, but the
        helper itself treats the bytes as opaque. If the probe
        ever stops sorting keys, the gate will surface the
        duplicates section more aggressively -- that's the
        correct behaviour.
        """
        p_a = tmp_path / "a.json"
        p_b = tmp_path / "b.json"
        p_a.write_text(json.dumps({"a": 1, "b": 2}), encoding="utf-8")
        p_b.write_text(json.dumps({"b": 2, "a": 1}), encoding="utf-8")
        # Different byte representations -> different fingerprints.
        assert fingerprint_of(p_a) != fingerprint_of(p_b)
        # Equal bytes -> equal fingerprints.
        p_c = tmp_path / "c.json"
        p_c.write_bytes(p_a.read_bytes())
        assert fingerprint_of(p_a) == fingerprint_of(p_c)

    def test_unreadable_returns_none(self, tmp_path: Path):
        # Nonexistent path.
        assert fingerprint_of(tmp_path / "does-not-exist.json") is None

    def test_matches_full_sha256_truncation(self, tmp_path: Path):
        """The 16-char truncation is exactly the first 16 hex chars
        of a full SHA-256 digest. Pin this so future refactors
        don't silently switch to a different hash.
        """
        p = tmp_path / "cap.json"
        p.write_text(json.dumps({"x": 1, "y": [1, 2, 3]}), encoding="utf-8")
        data = p.read_bytes()
        full = hashlib.sha256(data).hexdigest()
        assert fingerprint_of(p) == full[:16]


class TestDedupCount:
    """The pure dedup counting helper."""

    def test_empty_list_is_zero(self):
        assert dedup_count([]) == 0

    def test_unique_list_is_zero(self):
        assert dedup_count(["a", "b", "c"]) == 0

    def test_one_duplicate(self):
        assert dedup_count(["a", "a", "b"]) == 1

    def test_two_duplicates_of_same(self):
        assert dedup_count(["a", "a", "a"]) == 2

    def test_mixed(self):
        assert dedup_count(["a", "b", "a", "c", "b"]) == 2

    def test_never_raises(self):
        # Even on a single-element list.
        assert dedup_count(["only"]) == 0


# ---------------------------------------------------------------------------
# 2. cas_reachability_gate -- integration


class TestGateDedup:
    """The gate counts UNIQUE captures per branch and surfaces
    ``duplicates_by_branch`` in the report."""

    def test_unique_captures_counted_normally(self, tmp_path: Path):
        # One unique capture per branch -- gate flips to REACHABLE,
        # duplicates_by_branch is all-zero.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                tmp_path,
                f"{phase}_cap.json",
                _make_capture(phase),
            )
        report = cas_reachability_report(tmp_path)
        assert report["verdict"] == "REACHABLE"
        assert report["captures_scanned"] == len(
            CAS_BRANCHES_REQUIRING_EVIDENCE
        )
        assert report["duplicates_by_branch"] == {
            phase: 0 for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
        }

    def test_duplicate_in_same_branch_does_not_inflate(
        self, tmp_path: Path
    ):
        # Two byte-identical captures under the SAME branch --
        # only one should count toward the branch's REACHABLE
        # threshold. The second is a duplicate.
        cap = _make_capture("CAS_REFERENCE_PRICE_WINDOW")
        _write_capture(tmp_path, "RELIANCE_15_17_a.json", cap)
        _write_capture(tmp_path, "RELIANCE_15_17_b.json", cap)
        report = cas_reachability_report(tmp_path)
        # Branch has 1 UNIQUE capture.
        assert (
            report["captured_phases"]["CAS_REFERENCE_PRICE_WINDOW"]
            == 1
        )
        # duplicates_by_branch shows 1 duplicate for that branch.
        assert (
            report["duplicates_by_branch"][
                "CAS_REFERENCE_PRICE_WINDOW"
            ]
            == 1
        )
        # captures_scanned is 2 (both files were scanned).
        assert report["captures_scanned"] == 2

    def test_three_duplicates_count_one_unique(self, tmp_path: Path):
        cap = _make_capture("CAS_MATCHING")
        for i in range(3):
            _write_capture(tmp_path, f"copy_{i}.json", cap)
        report = cas_reachability_report(tmp_path)
        assert report["captured_phases"]["CAS_MATCHING"] == 1
        assert report["duplicates_by_branch"]["CAS_MATCHING"] == 2
        assert report["captures_scanned"] == 3

    def test_duplicates_do_not_silently_flip_to_reachable(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.DEDUP 2026-09-14] The core defensive
        invariant: a single unique capture, copied 5 times, must
        NOT count as 6 captures. The gate stays UNREACHABLE.
        """
        cap = _make_capture("CAS_REFERENCE_PRICE_WINDOW")
        for i in range(5):
            _write_capture(tmp_path, f"copy_{i}.json", cap)
        report = cas_reachability_report(tmp_path)
        assert report["verdict"] == "UNREACHABLE"
        # 5 missing branches remain missing.
        assert len(report["missing_phases"]) == 5
        # The single unique capture shows up exactly once.
        assert (
            report["captured_phases"]["CAS_REFERENCE_PRICE_WINDOW"]
            == 1
        )
        # 4 duplicates surfaced for audit.
        assert (
            report["duplicates_by_branch"][
                "CAS_REFERENCE_PRICE_WINDOW"
            ]
            == 4
        )

    def test_distinct_captures_same_branch_count_independently(
        self, tmp_path: Path
    ):
        # Two DIFFERENT captures under the same branch.
        cap_a = _make_capture("CAS_MATCHING", symbol="RELIANCE")
        cap_b = _make_capture("CAS_MATCHING", symbol="TCS")
        _write_capture(tmp_path, "RELIANCE.json", cap_a)
        _write_capture(tmp_path, "TCS.json", cap_b)
        report = cas_reachability_report(tmp_path)
        assert report["captured_phases"]["CAS_MATCHING"] == 2
        assert report["duplicates_by_branch"]["CAS_MATCHING"] == 0

    def test_duplicates_by_branch_always_present_in_report(
        self, tmp_path: Path
    ):
        # Even when the directory is empty, the field is present
        # with the documented shape.
        report = cas_reachability_report(tmp_path)
        assert "duplicates_by_branch" in report
        assert report["duplicates_by_branch"] == {
            phase: 0 for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
        }

    def test_duplicates_by_branch_present_when_directory_missing(
        self, tmp_path: Path
    ):
        # The "missing directory" path also includes the new field.
        nonexistent = tmp_path / "no-such-dir"
        report = cas_reachability_report(nonexistent)
        assert report["verdict"] == "UNREACHABLE"
        assert "duplicates_by_branch" in report

    def test_format_report_includes_duplicates(self, tmp_path: Path):
        # The human-readable report includes the duplicates
        # surface.
        cap = _make_capture("CAS_MATCHING")
        _write_capture(tmp_path, "a.json", cap)
        _write_capture(tmp_path, "b.json", cap)
        _write_capture(tmp_path, "c.json", cap)
        report = cas_reachability_report(tmp_path)
        rendered = format_report(report)
        assert "duplicates" in rendered.lower()


# ---------------------------------------------------------------------------
# 3. update_summary -- the SUMMARY surface


class TestSummaryDuplicates:
    """The persistent SUMMARY.md surface renders the dedup field."""

    def test_summary_no_duplicates_paragraph(self, tmp_path: Path):
        # No duplicates -> the SUMMARY says so.
        captures_dir = tmp_path / "captures"
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                captures_dir, f"{phase}.json", _make_capture(phase)
            )
        report = cas_reachability_report(captures_dir)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=captures_dir
        )
        body = summary_path.read_text(encoding="utf-8")
        assert "## Duplicate captures" in body
        assert "No duplicate captures detected" in body

    def test_summary_with_duplicates_table(self, tmp_path: Path):
        # Duplicates present -> the SUMMARY renders a per-branch
        # table with the duplicate counts.
        captures_dir = tmp_path / "captures"
        cap = _make_capture("CAS_REFERENCE_PRICE_WINDOW")
        _write_capture(captures_dir, "a.json", cap)
        _write_capture(captures_dir, "b.json", cap)
        # Fill the other branches with unique captures.
        for phase in [
            "CAS_ORDER_ENTRY",
            "CAS_LIMIT_ENTRY_ONLY",
            "CAS_MATCHING",
            "CAS_POST",
            "DERIVATIVES_CAS_ALIGNED",
        ]:
            _write_capture(
                captures_dir, f"{phase}.json", _make_capture(phase)
            )
        report = cas_reachability_report(captures_dir)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=captures_dir
        )
        body = summary_path.read_text(encoding="utf-8")
        assert "## Duplicate captures" in body
        assert "CAS_REFERENCE_PRICE_WINDOW" in body
        # The table shows the duplicate count for that branch.
        # (We don't pin the exact markdown syntax to keep the test
        # tolerant of future formatting changes.)
        assert "| 1 |" in body or "| 2 |" in body

    def test_summary_includes_fingerprint_length(self, tmp_path: Path):
        # The SUMMARY surfaces the fingerprint hex length so the
        # operator can audit what "duplicate" means.
        captures_dir = tmp_path / "captures"
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                captures_dir, f"{phase}.json", _make_capture(phase)
            )
        report = cas_reachability_report(captures_dir)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=captures_dir
        )
        body = summary_path.read_text(encoding="utf-8")
        # The template says ``SHA-256[:{fingerprint_hex_length}]``;
        # verify the length was rendered.
        assert f"SHA-256[:{FINGERPRINT_HEX_LENGTH}]" in body
