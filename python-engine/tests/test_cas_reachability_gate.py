"""[WORKFLOW-J.10 2026-09-13] Tests for the CAS-branch reachability gate.

The gate answers: "have the CAS sub-window branches of
``classify_session_phase`` been exercised by real production
call sites?"

The implementation walks ``docs/j2_captures/`` and emits
``{verdict, coverage, captured_phases, missing_phases}``.
The plan §14 "auction-imbalance research is excluded" means
J.10 ships the gate, not a strategy. Any future auction code
must pass this gate to ship.

These tests pin:
  1. Pure / total contract: the gate never raises, returns
     a documented shape.
  2. The 5 CAS sub-windows + DERIVATIVES_CAS_ALIGNED must
     each have at least one captured receipt.
  3. The verdict is REACHABLE when coverage >= 1 receipt
     per CAS sub-window; UNREACHABLE otherwise.
  4. The gate accepts the documented j2_captures/ layout
     (one sub-directory per day, JSON per capture) and
     tolerates extra files (SUMMARY.md, README.md).
  5. The gate is deterministic for a given filesystem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cas_reachability_gate import (
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    cas_reachability_report,
    format_report,
    write_report,
)


# The 5 CAS sub-windows + DERIVATIVES_CAS_ALIGNED = 6 branches
# that J.10 requires evidence for. CONTINUOUS_TRADING /
# PRE_MARKET / CLOSED do not require J.3-style broker evidence
# -- they are wired through ``isMarketOpen()`` and the
# production paths are exercised whenever a signal arrives.
CAS_BRANCHES_REQUIRING_EVIDENCE_TEST = frozenset({
    "CAS_REFERENCE_PRICE_WINDOW",
    "CAS_ORDER_ENTRY",
    "CAS_LIMIT_ENTRY_ONLY",
    "CAS_MATCHING",
    "CAS_POST",
    "DERIVATIVES_CAS_ALIGNED",
})


def test_branches_requiring_evidence_is_documented_set():
    """The 6 CAS sub-windows + DERIVATIVES_CAS_ALIGNED are
    the branches that need real broker evidence. CONTINUOUS_TRADING
    / PRE_MARKET / CLOSED are exercised by every market-day signal,
    so they don't need separate J.3 captures.
    """
    assert frozenset(CAS_BRANCHES_REQUIRING_EVIDENCE) == \
        CAS_BRANCHES_REQUIRING_EVIDENCE_TEST


def test_empty_captures_returns_unreachable(tmp_path):
    """An empty docs/j2_captures/ directory returns UNREACHABLE
    with all 6 required branches at zero count.
    """
    report = cas_reachability_report(captures_dir=tmp_path)
    assert report["verdict"] == "UNREACHABLE"
    # All 6 required branches present, all with zero count.
    assert set(report["captured_phases"].keys()) == \
        CAS_BRANCHES_REQUIRING_EVIDENCE_TEST
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE_TEST:
        assert report["captured_phases"][branch] == 0
    # All 6 required branches missing.
    assert set(report["missing_phases"]) == \
        CAS_BRANCHES_REQUIRING_EVIDENCE_TEST


def test_all_six_branches_covered_returns_reachable(tmp_path):
    """A directory with one capture per branch returns REACHABLE."""
    day = tmp_path / "2026-09-10"
    day.mkdir()
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE_TEST:
        cap = day / f"RELIANCE_{branch}.json"
        cap.write_text(json.dumps({
            "schema_version": 2,
            "rows": [{"classifier_phase": branch}],
        }), encoding="utf-8")
    report = cas_reachability_report(captures_dir=tmp_path)
    assert report["verdict"] == "REACHABLE"
    assert report["missing_phases"] == []
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE_TEST:
        assert report["captured_phases"][branch] >= 1


def test_partial_coverage_lists_missing_branches(tmp_path):
    """A directory with only 2 branches returns UNREACHABLE
    with the other 4 listed as missing.
    """
    day = tmp_path / "2026-09-10"
    day.mkdir()
    for branch in ("CAS_REFERENCE_PRICE_WINDOW", "CAS_ORDER_ENTRY"):
        cap = day / f"RELIANCE_{branch}.json"
        cap.write_text(json.dumps({
            "schema_version": 2,
            "rows": [{"classifier_phase": branch}],
        }), encoding="utf-8")
    report = cas_reachability_report(captures_dir=tmp_path)
    assert report["verdict"] == "UNREACHABLE"
    missing = set(report["missing_phases"])
    assert "CAS_LIMIT_ENTRY_ONLY" in missing
    assert "CAS_MATCHING" in missing
    assert "CAS_POST" in missing
    assert "DERIVATIVES_CAS_ALIGNED" in missing


def test_extra_files_are_tolerated(tmp_path):
    """SUMMARY.md / README.md / review_log.md are not captures
    but should not cause the gate to crash. They are simply
    ignored.
    """
    day = tmp_path / "2026-09-10"
    day.mkdir()
    (day / "README.md").write_text("# readme", encoding="utf-8")
    (day / "review_log.md").write_text("# log", encoding="utf-8")
    (tmp_path / "SUMMARY.md").write_text("# summary", encoding="utf-8")
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE_TEST:
        cap = day / f"RELIANCE_{branch}.json"
        cap.write_text(json.dumps({
            "schema_version": 2,
            "rows": [{"classifier_phase": branch}],
        }), encoding="utf-8")
    report = cas_reachability_report(captures_dir=tmp_path)
    assert report["verdict"] == "REACHABLE"


def test_corrupt_capture_is_skipped(tmp_path):
    """A capture with malformed JSON is skipped, not fatal."""
    day = tmp_path / "2026-09-10"
    day.mkdir()
    (day / "broken.json").write_text("not json {", encoding="utf-8")
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE_TEST:
        cap = day / f"RELIANCE_{branch}.json"
        cap.write_text(json.dumps({
            "schema_version": 2,
            "rows": [{"classifier_phase": branch}],
        }), encoding="utf-8")
    report = cas_reachability_report(captures_dir=tmp_path)
    # 6 valid captures -> REACHABLE; the broken one is skipped.
    assert report["verdict"] == "REACHABLE"


def test_capture_with_unknown_phase_is_ignored(tmp_path):
    """A capture whose classifier phase is not in the
    documented 10-phase set (e.g. a future phase) is ignored
    -- not counted toward coverage and not added to the
    missing set. The bounded-phase set is the authority.
    """
    day = tmp_path / "2026-09-10"
    day.mkdir()
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE_TEST:
        cap = day / f"RELIANCE_{branch}.json"
        cap.write_text(json.dumps({
            "schema_version": 2,
            "rows": [{"classifier_phase": branch}],
        }), encoding="utf-8")
    # Add a capture with a non-bounded phase -- ignored.
    (day / "FUTURE.json").write_text(json.dumps({
        "schema_version": 2,
        "rows": [{"classifier_phase": "FUTURE_CAS_SUB_WINDOW"}],
    }), encoding="utf-8")
    report = cas_reachability_report(captures_dir=tmp_path)
    assert report["verdict"] == "REACHABLE"


def test_format_report_emits_documented_shape():
    """format_report returns a string with REACHABLE/UNREACHABLE
    verdict, coverage percentages, and a missing-phases list.
    """
    report = {
        "verdict": "UNREACHABLE",
        "captured_phases": {"CAS_REFERENCE_PRICE_WINDOW": 1},
        "missing_phases": ["CAS_MATCHING"],
        "coverage_pct": 16.7,
        "captures_scanned": 7,
        "captures_skipped": 1,
    }
    text = format_report(report)
    assert "UNREACHABLE" in text
    assert "CAS_MATCHING" in text
    assert "16.7%" in text


def test_write_report_is_idempotent(tmp_path):
    """write_report writes a JSON file and is idempotent."""
    report = cas_reachability_report(captures_dir=tmp_path)
    out_path = tmp_path / "reachability.json"
    write_report(report, out_path=out_path)
    assert out_path.exists()
    # Re-running produces the same shape (the timestamps may
    # differ but the verdict + missing_phases are stable).
    report2 = json.loads(out_path.read_text(encoding="utf-8"))
    assert report2["verdict"] == report["verdict"]
    assert report2["missing_phases"] == report["missing_phases"]
