"""[WORKFLOW-J.10.CLOSURE 2026-09-13] End-to-end test for the
SUMMARY.md auto-update on ``j2_capture_review.py`` happy-path.

This test verifies the operator workflow:
  1. Operator drops a valid capture into ``docs/j2_captures/``.
  2. Operator runs ``j2_capture_review.py <file>``.
  3. On happy-path (every check passes), the SUMMARY.md
     auto-updates -- the operator does not need to remember
     ``--update-summary``.

The test uses an in-process fixture (tmp dir with the
canonical ``docs/j2_captures/`` layout) and an in-memory
capture document that satisfies every review check.

This is the operator-loop test: it pins the contract that
the audit surface (``SUMMARY.md``) stays in lockstep with
the gate's verdict as soon as a capture is reviewed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
_ENGINE_DIR = _TOOLS_DIR.parent

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

import j2_capture_review as _review_mod  # noqa: E402
from cas_reachability_gate import (  # noqa: E402
    cas_reachability_report,
    update_summary,
)


PYTHON = sys.executable
REVIEW_TOOL = (
    Path(__file__).resolve().parent.parent
    / "tools" / "j2_capture_review.py"
)


def _make_capture_dir(tmp_path: Path) -> tuple[Path, Path]:
    """Create the canonical ``docs/j2_captures/`` layout
    under ``tmp_path`` and return (repo_root, captures_dir).
    """
    repo = tmp_path / "synthetic_repo"
    captures_dir = repo / "docs" / "j2_captures"
    (captures_dir / "2026-09-10").mkdir(parents=True)
    (captures_dir / "README.md").write_text(
        "# j2_captures\n", encoding="utf-8",
    )
    return repo, captures_dir


def _write_valid_capture(capture_path: Path) -> None:
    """Write a capture document that satisfies every review check.

    The shape is the minimum-viable document the probe emits
    under ``--dry-run``: every required field is present, the
    schema version matches, the classifier phase is in the
    bounded set, the eligibility list contains the symbol,
    and the dry_run flag short-circuits the quote / circuit /
    broker-extras checks.

    The observation time is 09:45:01 UTC = 15:15:01 IST, which
    is the boundary into ``CAS_REFERENCE_PRICE_WINDOW`` for a
    CAS-eligible symbol. The classifier therefore returns
    ``CAS_REFERENCE_PRICE_WINDOW`` -- a deterministic, CAS
    phase that satisfies the ``classifier_phase`` check.
    Using a CAS phase here is deliberate: this test exercises
    the J.10 SUMMARY.md auto-update wire, and the gate's
    counter only increments on the 6 required CAS branches.
    """
    document = {
        "tool": "j2_cas_probe",
        "schema_version": 2,
        "generated_at_utc": "2026-09-10T09:45:01+00:00",
        "dry_run": True,
        "observation_at_utc": "2026-09-10T09:45:01+00:00",
        "observation_at_ist": "2026-09-10T15:15:01+05:30",
        "symbol_count": 1,
        "eligibility_source": "cli",
        "expected_eligibility": ["RELIANCE"],
        "rows": [
            {
                "symbol": "RELIANCE",
                "is_derivative": False,
                "is_cas_eligible": True,
                "classifier_phase": "CAS_REFERENCE_PRICE_WINDOW",
                "observation_at_utc": "2026-09-10T09:45:01+00:00",
                "observation_at_ist": "2026-09-10T15:15:01+05:30",
                "quote": None,
                "circuit_limits": None,
                "broker_extras": None,
            }
        ],
        "eligibility": {
            "source": "cli",
            "csv": "RELIANCE",
        },
        "cas_window_keys": [],
        "dry_run_note": (
            "dry_run: skipped quote, circuit_limits, broker_extras"
        ),
    }
    capture_path.write_text(json.dumps(document), encoding="utf-8")


def test_happy_path_review_auto_updates_summary(tmp_path: Path) -> None:
    """A passing ``j2_capture_review.py`` call auto-updates
    ``docs/j2_captures/SUMMARY.md`` -- the operator does not
    need to run ``--update-summary`` separately.

    This pins the operator-loop contract: every successful
    capture-review flips the audit surface in lockstep.
    """
    repo, captures_dir = _make_capture_dir(tmp_path)
    summary_path = captures_dir / "SUMMARY.md"
    capture_path = (
        captures_dir
        / "2026-09-10"
        / "RELIANCE_CAS_REFERENCE_PRICE_WINDOW.json"
    )
    _write_valid_capture(capture_path)

    # Sanity: SUMMARY.md does not exist yet.
    assert not summary_path.exists()

    # Run the review tool against the synthetic capture.
    env = os.environ.copy()
    env["CAS_PHASE1_FNO_UNDERLYINGS"] = ""  # override the env
    # The CLI's --expected-eligibility CSV drives the eligibility
    # check. RELIANCE matches the captured symbol.
    proc = subprocess.run(
        [
            PYTHON,
            str(REVIEW_TOOL),
            str(capture_path.relative_to(repo)),
            "--expected-eligibility",
            "RELIANCE",
        ],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Happy-path: review passes, exit 0.
    assert proc.returncode == 0, (
        f"review failed; stderr: {proc.stderr}; "
        f"stdout: {proc.stdout}"
    )
    # The auto-update surfaces in stderr (so operators see
    # "updated <path>" in their logs).
    assert "updated" in proc.stderr

    # The SUMMARY.md was created (or updated if pre-existing).
    assert summary_path.exists()
    text = summary_path.read_text(encoding="utf-8")
    # The SUMMARY reflects the gate's verdict -- one branch is
    # covered so coverage is 1/6 = 16.7% (not REACHABLE).
    verdict_line = next(
        line for line in text.splitlines()
        if line.startswith("**") and "-- coverage" in line
    )
    assert "**UNREACHABLE**" in verdict_line
    assert "16.7%" in verdict_line
    # The captured branch is shown with its count.
    assert "| CAS_REFERENCE_PRICE_WINDOW | 1 (yes) |" in text
    # The 5 missing branches are listed.
    for missing in (
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ):
        assert f"- [ ] {missing}" in text


def test_failed_review_does_not_auto_update_summary(tmp_path: Path) -> None:
    """A failing review (overall_passed = false) does NOT
    auto-update SUMMARY.md -- the operator must fix the
    capture first.

    This pins the fail-closed contract: a broken capture
    must not silently flip the audit surface to REACHABLE.
    """
    repo, captures_dir = _make_capture_dir(tmp_path)
    summary_path = captures_dir / "SUMMARY.md"
    capture_path = (
        captures_dir
        / "2026-09-10"
        / "RELIANCE_CAS_REFERENCE_PRICE_WINDOW.json"
    )

    # Write a deliberately broken capture: wrong schema
    # version so the schema check fails.
    broken = {
        "schema_version": 99,  # wrong!
        "tool": "j2_cas_probe",
    }
    capture_path.write_text(json.dumps(broken), encoding="utf-8")

    # Pre-write a SUMMARY with UNREACHABLE so we can detect
    # whether the broken review tried to overwrite it.
    pre_report = cas_reachability_report(captures_dir=captures_dir)
    update_summary(pre_report, summary_path=summary_path,
                   captures_dir=captures_dir)
    pre_text = summary_path.read_text(encoding="utf-8")

    env = os.environ.copy()
    env["CAS_PHASE1_FNO_UNDERLYINGS"] = ""
    proc = subprocess.run(
        [
            PYTHON,
            str(REVIEW_TOOL),
            str(capture_path.relative_to(repo)),
            "--expected-eligibility",
            "RELIANCE",
        ],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Review fails.
    assert proc.returncode != 0
    # Fail-closed: SUMMARY.md was NOT re-written (its content
    # matches the pre-write snapshot -- the timestamp line is
    # the only line that may have changed if any update ran;
    # in the failed-review path no update runs at all so the
    # file is untouched).
    post_text = summary_path.read_text(encoding="utf-8")
    assert post_text == pre_text


def test_in_process_review_helper_path(tmp_path: Path) -> None:
    """In-process: import the review helper directly and
    verify the auto-update branch fires when ``main()``
    returns 0 with all checks passing.

    This is the lightweight in-process companion to the
    subprocess-based tests above. It catches regressions in
    the ``main()`` function without the cost of spawning a
    subprocess.
    """
    repo, captures_dir = _make_capture_dir(tmp_path)
    summary_path = captures_dir / "SUMMARY.md"
    capture_path = (
        captures_dir
        / "2026-09-10"
        / "RELIANCE_CAS_REFERENCE_PRICE_WINDOW.json"
    )
    _write_valid_capture(capture_path)

    # The review tool resolves capture paths relative to its
    # ``cwd``. Chdir into the synthetic repo so the
    # ``docs/j2_captures/...`` path resolves.
    cwd = os.getcwd()
    try:
        os.chdir(str(repo))
        os.environ["CAS_PHASE1_FNO_UNDERLYINGS"] = ""
        # Direct call to main(); pass the synthetic capture's
        # path and ``--expected-eligibility RELIANCE`` to satisfy
        # the eligibility check.
        args = [
            "docs/j2_captures/2026-09-10/RELIANCE_CAS_REFERENCE_PRICE_WINDOW.json",
            "--expected-eligibility",
            "RELIANCE",
        ]
        rc = _review_mod.main(args)
    finally:
        os.chdir(cwd)

    # Happy-path: review passes.
    assert rc == 0, (
        f"in-process review returned {rc}; expected 0"
    )
    # The auto-update surfaces in stderr (we can't easily
    # capture it here, but the file existence is the proof).
    assert summary_path.exists()
