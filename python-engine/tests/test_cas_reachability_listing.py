"""[WORKFLOW-J.10.CAPTURE_LISTING 2026-09-14] Capture listing tests.

The ``--list-captures`` CLI flag is a fast, side-effect-free
audit tool. It walks ``docs/j2_captures/`` and prints the
captures grouped by branch, WITHOUT computing the verdict.

These tests pin the listing contract at three layers:
  1. ``cas_reachability_listing`` -- the pure helpers
     (``list_captures``, ``format_listing``).
  2. CLI surface -- the JSON shape and the human output.
  3. Mutually-exclusive flag combinations -- the listing
     is independent of the verdict machinery.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_listing import (  # noqa: E402
    format_listing,
    list_captures,
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
# 1. list_captures -- the pure helper


class TestListCaptures:
    """The pure listing helper."""

    def test_missing_dir_returns_empty_listing(self, tmp_path: Path):
        listing = list_captures(tmp_path / "no-such-dir")
        assert listing["total_captures"] == 0
        assert listing["listed_captures"] == 0
        assert listing["skipped_captures"] == 0
        assert listing["branches_with_captures"] == 0
        # All 6 branches are present in the dict (empty lists),
        # so consumers can rely on the shape.
        from cas_reachability_gate import CAS_BRANCHES_REQUIRING_EVIDENCE
        for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
            assert listing["captures"][branch] == []

    def test_empty_dir_returns_zero_counters(self, tmp_path: Path):
        listing = list_captures(tmp_path)
        assert listing["total_captures"] == 0
        assert listing["listed_captures"] == 0

    def test_single_capture_single_branch(self, tmp_path: Path):
        _write_capture(
            tmp_path,
            "2026-09-14",
            "a.json",
            _make_capture("CAS_MATCHING"),
        )
        listing = list_captures(tmp_path)
        assert listing["total_captures"] == 1
        assert listing["listed_captures"] == 1
        assert listing["captures"]["CAS_MATCHING"] == ["2026-09-14/a.json"]
        # Empty branches stay present with empty lists.
        for branch in listing["captures"]:
            if branch != "CAS_MATCHING":
                assert listing["captures"][branch] == []

    def test_multiple_captures_grouped_by_branch(self, tmp_path: Path):
        # CAS_MATCHING: 2 captures on different days
        _write_capture(
            tmp_path, "2026-09-10", "a.json",
            _make_capture("CAS_MATCHING", symbol="RELIANCE"),
        )
        _write_capture(
            tmp_path, "2026-09-14", "b.json",
            _make_capture("CAS_MATCHING", symbol="TCS"),
        )
        # CAS_POST: 1 capture
        _write_capture(
            tmp_path, "2026-09-14", "c.json",
            _make_capture("CAS_POST"),
        )
        listing = list_captures(tmp_path)
        assert listing["total_captures"] == 3
        assert listing["listed_captures"] == 3
        assert listing["branches_with_captures"] == 2
        # Sorted ascending by date within each branch.
        assert listing["captures"]["CAS_MATCHING"] == [
            "2026-09-10/a.json",
            "2026-09-14/b.json",
        ]
        assert listing["captures"]["CAS_POST"] == ["2026-09-14/c.json"]

    def test_malformed_capture_counted_as_skipped(
        self, tmp_path: Path
    ):
        # Write a J.3-shaped capture but with an out-of-bounds
        # phase. The listing must NOT include it under any
        # branch and must count it under skipped_captures.
        bad_capture = _make_capture("CAS_MATCHING")
        bad_capture["rows"][0]["classifier_phase"] = (
            "NOT_A_BOUNDED_PHASE"
        )
        _write_capture(tmp_path, "2026-09-14", "bad.json", bad_capture)
        # Add a valid capture so the listing has at least one
        # listed entry to verify the skip path doesn't poison
        # the rest of the walk.
        _write_capture(
            tmp_path, "2026-09-14", "good.json",
            _make_capture("CAS_MATCHING", symbol="TCS"),
        )
        listing = list_captures(tmp_path)
        assert listing["total_captures"] == 2
        assert listing["listed_captures"] == 1
        assert listing["skipped_captures"] == 1
        # The good capture is listed; the bad capture is NOT.
        assert "2026-09-14/good.json" in listing["captures"]["CAS_MATCHING"]
        assert "2026-09-14/bad.json" not in str(listing["captures"])

    def test_empty_rows_array_counted_as_skipped(self, tmp_path: Path):
        # A capture with empty ``rows`` is malformed per the J.3
        # contract; the listing treats it as skipped.
        bad = _make_capture("CAS_MATCHING")
        bad["rows"] = []

        path = tmp_path / "2026-09-14"
        path.mkdir()
        (path / "empty.json").write_text(
            json.dumps(bad), encoding="utf-8"
        )
        listing = list_captures(tmp_path)
        assert listing["listed_captures"] == 0
        assert listing["skipped_captures"] == 1

    def test_schema_version_pinned(self, tmp_path: Path):
        listing = list_captures(tmp_path)
        # The version is pinned so consumers can detect shape drift.
        assert listing["schema_version"] == "i10-capture-listing-v1"

    def test_captures_root_is_absolute(self, tmp_path: Path):
        listing = list_captures(tmp_path)
        # Path.resolve() makes it absolute; relative paths in
        # ``captures[branch]`` are relative to this resolved root.
        assert Path(listing["captures_root"]).is_absolute()

    def test_paths_are_relative_to_root(self, tmp_path: Path):
        _write_capture(
            tmp_path, "2026-09-10", "a.json",
            _make_capture("CAS_MATCHING"),
        )
        _write_capture(
            tmp_path, "2026-09-14", "b.json",
            _make_capture("CAS_MATCHING"),
        )
        listing = list_captures(tmp_path)
        # Every path must be relative -- never an absolute path
        # leaking the tmp dir.
        for branch, paths in listing["captures"].items():
            for p in paths:
                assert not Path(p).is_absolute(), (
                    f"path {p!r} under branch {branch!r} is absolute"
                )


# ---------------------------------------------------------------------------
# 2. format_listing -- the human-readable rendering


class TestFormatListing:
    """The deterministic human-readable rendering."""

    def test_empty_listing_renders_zero_counters(self, tmp_path: Path):
        out = format_listing(list_captures(tmp_path))
        assert "total JSON files:   0" in out
        assert "listed (valid):     0" in out
        assert "skipped (invalid):  0" in out
        assert "branches with captures: 0/6" in out

    def test_present_branches_marked_with_plus(self, tmp_path: Path):
        _write_capture(
            tmp_path, "2026-09-14", "a.json",
            _make_capture("CAS_MATCHING"),
        )
        out = format_listing(list_captures(tmp_path))
        assert "[+] CAS_MATCHING (1 capture(s))" in out
        # The path appears below the branch header.
        assert "2026-09-14/a.json" in out

    def test_missing_branches_marked_with_square(self, tmp_path: Path):
        out = format_listing(list_captures(tmp_path))
        # All 6 branches render with the missing marker.
        for branch in [
            "CAS_REFERENCE_PRICE_WINDOW",
            "CAS_ORDER_ENTRY",
            "CAS_LIMIT_ENTRY_ONLY",
            "CAS_MATCHING",
            "CAS_POST",
            "DERIVATIVES_CAS_ALIGNED",
        ]:
            assert f"[ ] {branch} (no captures yet)" in out

    def test_branches_in_canonical_order(self, tmp_path: Path):
        # The format mirrors CAS_BRANCHES_REQUIRING_EVIDENCE
        # order so the operator can pattern-match against the
        # gate's verdict output.
        from cas_reachability_gate import CAS_BRANCHES_REQUIRING_EVIDENCE
        out = format_listing(list_captures(tmp_path))
        positions = [
            out.index(f"[ ] {branch}") for branch in CAS_BRANCHES_REQUIRING_EVIDENCE
        ]
        # Monotonic ascending positions mean canonical order.
        assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# 3. CLI surface


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the cas_reachability_check.py CLI in-process via the
    ``main`` function. We use the winvenv python from the
    python-engine directory."""
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


class TestListCapturesCli:
    """The ``--list-captures`` CLI flag."""

    def _populate_captures(self, tmp_path: Path) -> None:
        # Three captures spanning two branches and two days.
        _write_capture(
            tmp_path, "2026-09-10", "a.json",
            _make_capture("CAS_MATCHING", symbol="RELIANCE"),
        )
        _write_capture(
            tmp_path, "2026-09-14", "b.json",
            _make_capture("CAS_MATCHING", symbol="TCS"),
        )
        _write_capture(
            tmp_path, "2026-09-14", "c.json",
            _make_capture("CAS_POST"),
        )

    def test_cli_human_output(self, tmp_path: Path):
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
        )
        assert result.returncode == 0, (
            f"stderr: {result.stderr}"
        )
        out = result.stdout
        # Branches with captures are marked.
        assert "[+] CAS_MATCHING (2 capture(s))" in out
        assert "[+] CAS_POST (1 capture(s))" in out
        # Missing branches are marked.
        assert "[ ] CAS_REFERENCE_PRICE_WINDOW (no captures yet)" in out
        # Paths appear.
        assert "2026-09-10/a.json" in out
        assert "2026-09-14/b.json" in out
        assert "2026-09-14/c.json" in out
        # Summary counters.
        assert "total JSON files:   3" in out
        assert "listed (valid):     3" in out
        assert "skipped (invalid):  0" in out
        assert "branches with captures: 2/6" in out

    def test_cli_json_output(self, tmp_path: Path):
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
            "--json",
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "i10-capture-listing-v1"
        assert payload["total_captures"] == 3
        assert payload["listed_captures"] == 3
        assert payload["branches_with_captures"] == 2
        assert payload["captures"]["CAS_MATCHING"] == [
            "2026-09-10/a.json",
            "2026-09-14/b.json",
        ]

    def test_cli_exit_zero_on_empty_dir(self, tmp_path: Path):
        # Empty captures directory: exit 0, listing is empty.
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
        )
        assert result.returncode == 0
        assert "total JSON files:   0" in result.stdout

    def test_cli_exit_zero_on_missing_dir(self, tmp_path: Path):
        # Missing captures directory: exit 0 (the listing
        # tolerates a missing dir; the verdict gate rejects).
        result = _run_cli(
            "--captures-dir", str(tmp_path / "no-such-dir"),
            "--list-captures",
        )
        assert result.returncode == 0
        assert "total JSON files:   0" in result.stdout

    def test_cli_does_not_compute_verdict(self, tmp_path: Path):
        # The listing must NOT print verdict machinery (no
        # "J.10 CAS-branch reachability:" header, no
        # coverage_pct, no missing-branches list). It's the
        # pure listing tool, not a gate invocation.
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
        )
        out = result.stdout
        assert "J.10 CAS-branch reachability:" not in out
        assert "coverage:" not in out
        assert "missing branches" not in out
        # But the listing header IS present.
        assert "J.10 CAS capture listing" in out

    def test_cli_rejects_captures_since_combination(self, tmp_path: Path):
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
            "--captures-since", "7",
        )
        assert result.returncode == 2
        assert "--list-captures does not compose" in result.stderr

    def test_cli_rejects_min_unique_per_branch_combination(
        self, tmp_path: Path
    ):
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
            "--min-unique-per-branch", "2",
        )
        assert result.returncode == 2
        assert "--list-captures does not compose" in result.stderr

    def test_cli_rejects_status_combination(self, tmp_path: Path):
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
            "--status",
        )
        assert result.returncode == 2
        assert "mutually exclusive" in result.stderr

    def test_cli_rejects_update_summary_combination(self, tmp_path: Path):
        self._populate_captures(tmp_path)
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
            "--update-summary",
        )
        assert result.returncode == 2
        assert "mutually exclusive" in result.stderr

    def test_cli_rejects_write_combination(self, tmp_path: Path):
        self._populate_captures(tmp_path)
        out_path = tmp_path / "report.json"
        result = _run_cli(
            "--captures-dir", str(tmp_path),
            "--list-captures",
            "--write", str(out_path),
        )
        assert result.returncode == 2
        assert "mutually exclusive" in result.stderr
        # The listing did NOT write the report file.
        assert not out_path.exists()
