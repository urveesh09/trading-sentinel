"""[WORKFLOW-C.F5 2026-09-15] Tests for the J.10 features
inventory helper and CLI flag.

Per the 2026-09-15 production audit F-5: PR #89-#92 features
were deployed but invisible in production runtime because
they only fire on specific events (captures, agent pre-
classifications). This module gives operators a single
command that prints the full list of J.10 features wired
into this engine version, so a future audit can confirm
wiring without needing captures to happen.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
PYTHON = sys.executable

# Import the module directly so we can test the helper
# functions without needing subprocess.
from cas_reachability_features import (  # noqa: E402
    FEATURES_INVENTORY,
    features_inventory_as_json,
    format_features_inventory,
)


# ─── Direct helper tests ──────────────────────────────────


def test_features_inventory_is_a_tuple():
    """The inventory is a stable, immutable tuple of dicts."""
    assert isinstance(FEATURES_INVENTORY, tuple)
    for entry in FEATURES_INVENTORY:
        assert isinstance(entry, dict)


def test_features_inventory_entries_have_required_keys():
    """Each entry has feature_id, added_at, description,
    cli_flags (the canonical schema for downstream tooling).
    """
    required = {"feature_id", "added_at", "description", "cli_flags"}
    for entry in FEATURES_INVENTORY:
        assert required <= entry.keys(), f"missing keys: {required - entry.keys()}"


def test_features_inventory_feature_ids_are_unique():
    """feature_id is the primary key -- duplicates would
    cause confusion in downstream reports.
    """
    ids = [e["feature_id"] for e in FEATURES_INVENTORY]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_features_inventory_covers_all_j10_subfeatures():
    """The inventory must reference every J.10 feature
    mentioned in the audit: DEDUP, FRESHNESS, MIN_THRESHOLD,
    BRANCH_HISTOGRAM, CAPTURE_LISTING, SUMMARY_VERIFY,
    WRITE_ATOMIC, CAPTURE_OLDEST_NEWEST, plus the gate
    itself, the SUMMARY.md writer, and the new
    FEATURES_INVENTORY slice.
    """
    expected_ids = {
        "J.10.GATE",
        "J.10.SUMMARY",
        "J.10.DEDUP",
        "J.10.FRESHNESS",
        "J.10.MIN_THRESHOLD",
        "J.10.CAPTURE_SUMMARY_AGGREGATE",
        "J.10.WRITE_ATOMIC",
        "J.10.BRANCH_HISTOGRAM",
        "J.10.CAPTURE_LISTING",
        "J.10.SUMMARY_VERIFY",
        "J.10.CAPTURE_OLDEST_NEWEST",
        "J.10.FEATURES_INVENTORY",
    }
    actual_ids = {e["feature_id"] for e in FEATURES_INVENTORY}
    missing = expected_ids - actual_ids
    assert not missing, f"missing feature_ids: {missing}"


def test_features_inventory_features_have_iso_date():
    """added_at must be ISO format YYYY-MM-DD."""
    for entry in FEATURES_INVENTORY:
        added = entry["added_at"]
        assert len(added) == 10, f"{entry['feature_id']}: bad date {added}"
        assert added[4] == "-" and added[7] == "-", (
            f"{entry['feature_id']}: not YYYY-MM-DD format: {added}"
        )


def test_format_features_inventory_returns_table():
    """The human-readable format is a multi-line string
    with feature_id, added_at, cli_flags columns, plus a
    description line for each feature.
    """
    text = format_features_inventory()
    # Header
    assert "J.10 features inventory" in text
    # At least the gate feature appears
    assert "J.10.GATE" in text
    # All documented feature_ids appear
    for entry in FEATURES_INVENTORY:
        assert entry["feature_id"] in text
    # Total count footer
    assert f"Total: {len(FEATURES_INVENTORY)}" in text


def test_features_inventory_as_json_returns_parseable_json():
    """JSON form is parseable, has count + features fields."""
    text = features_inventory_as_json()
    parsed = json.loads(text)
    assert parsed["count"] == len(FEATURES_INVENTORY)
    assert len(parsed["features"]) == len(FEATURES_INVENTORY)
    # First feature has the expected schema
    first = parsed["features"][0]
    assert "feature_id" in first
    assert "added_at" in first
    assert "description" in first
    assert "cli_flags" in first


def test_format_features_inventory_sorted_by_feature_id():
    """The output is sorted by feature_id for stable display."""
    text = format_features_inventory()
    # Extract every feature_id line and verify monotonic order
    lines = text.splitlines()
    ids_in_order = [
        ln.split()[0] for ln in lines
        if ln and not ln.startswith("#") and not ln.startswith("-")
        and ln.split()[0].startswith("J.10.")
    ]
    assert ids_in_order == sorted(ids_in_order), (
        f"output not sorted: {ids_in_order}"
    )


def test_features_inventory_with_audit_finding_referenced():
    """The audit explicitly called out the J.10 surface as
    MED severity for F-5. The inventory's FEATURES_INVENTORY
    row should reference the audit so an operator reading
    the CLI output understands WHY this feature exists.
    """
    inventory_entry = next(
        e for e in FEATURES_INVENTORY if e["feature_id"] == "J.10.FEATURES_INVENTORY"
    )
    assert "F-5" in inventory_entry["description"] or "audit" in inventory_entry["description"]


# ─── CLI integration tests ─────────────────────────────────


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the cas_reachability_check CLI as a subprocess so
    argv parsing and exit codes are exercised exactly as an
    operator would.
    """
    return subprocess.run(
        [PYTHON, "-m", "tools.cas_reachability_check", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def test_cli_features_inventory_human(tmp_path):
    """The CLI prints the human-readable inventory."""
    result = _run_cli("--features-inventory")
    assert result.returncode == 0
    assert "J.10 features inventory" in result.stdout
    assert "J.10.GATE" in result.stdout
    assert "J.10.DEDUP" in result.stdout
    # The total footer
    assert "Total:" in result.stdout


def test_cli_features_inventory_json(tmp_path):
    """The CLI prints machine-readable JSON with --features-inventory --json."""
    result = _run_cli("--features-inventory", "--json")
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert "count" in parsed
    assert "features" in parsed
    assert parsed["count"] == len(parsed["features"])
    # Each feature has the documented schema
    for entry in parsed["features"]:
        assert {"feature_id", "added_at", "description", "cli_flags"} <= entry.keys()


def test_cli_features_inventory_does_not_require_captures_dir(tmp_path):
    """The inventory short-circuits before the captures-dir
    check, so it's safe to run even if docs/j2_captures/ is
    empty or absent (which is the F-5 audit's typical state).
    """
    # Point the CLI at a captures-dir that does NOT exist.
    # The features-inventory flag must still succeed.
    result = _run_cli(
        "--features-inventory",
        "--captures-dir", str(tmp_path / "no_such_dir"),
    )
    assert result.returncode == 0
    assert "J.10.GATE" in result.stdout


def test_cli_features_inventory_exit_0_always(tmp_path):
    """The inventory is informational -- exit code is 0
    regardless of CLI flag combinations.
    """
    for args in [
        ["--features-inventory"],
        ["--features-inventory", "--json"],
        ["--features-inventory", "--captures-dir", str(tmp_path)],
    ]:
        result = _run_cli(*args)
        assert result.returncode == 0, f"args={args} failed"
