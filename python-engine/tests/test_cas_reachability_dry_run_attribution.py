"""[WORKFLOW-J.10.DRY_RUN_ATTRIBUTION 2026-09-16] Tests
for the dry_run attribution field in the gate report.

Per the 2026-09-15 production audit F-5: features deployed
but invisible in runtime. The audit couldn't confirm
whether the J.10 REACHABLE verdict was grounded in REAL
broker-behaviour captures or simulation captures. This
slice surfaces the dry_run attribution so operators can
audit "how much of the verdict comes from real broker
calls vs simulation".

The dry_run field is read from each capture's top-level
boolean (``true`` = simulation, ``false`` = real). The
attribution is computed only on UNIQUE first-occurrence
captures -- duplicates don't inflate the real/sim count.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from cas_reachability_gate import (  # noqa: E402
    cas_reachability_report,
    _read_dry_run,
)


def _write_capture(tmp_path: Path, name: str, phase: str, *,
                   dry_run: bool = False, generated_at_utc: str | None = None) -> Path:
    """Write a minimal J.3 capture document.

    Args:
        tmp_path: parent directory.
        name: filename (e.g. "RELIANCE_15_10.json").
        phase: classifier_phase value (must be in CAS_BRANCHES).
        dry_run: simulation flag.
        generated_at_utc: ISO timestamp (defaults to NOW).
    """
    if generated_at_utc is None:
        generated_at_utc = datetime.now(timezone.utc).isoformat()
    doc = {
        "tool": "j2_cas_probe",
        "schema_version": "j2_cas_probe_v1",
        "generated_at_utc": generated_at_utc,
        "dry_run": dry_run,
        "observation_at_utc": generated_at_utc,
        "observation_at_ist": generated_at_utc,
        "symbol_count": 1,
        "rows": [
            {"classifier_phase": phase, "symbol": "RELIANCE"}
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return path


# ─── _read_dry_run helper ──────────────────────────────────


def test_read_dry_run_real_capture(tmp_path):
    """A capture with ``dry_run: false`` returns False."""
    p = _write_capture(tmp_path, "real.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=False)
    assert _read_dry_run(p) is False


def test_read_dry_run_dry_run_capture(tmp_path):
    """A capture with ``dry_run: true`` returns True."""
    p = _write_capture(tmp_path, "sim.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=True)
    assert _read_dry_run(p) is True


def test_read_dry_run_missing_field_returns_none(tmp_path):
    """A capture without a dry_run field returns None (not
    False -- this is schema-drift diagnostic territory).
    """
    doc = {
        "tool": "j2_cas_probe",
        "schema_version": "j2_cas_probe_v1",
        "generated_at_utc": "2026-09-16T00:00:00+00:00",
        "observation_at_utc": "2026-09-16T00:00:00+00:00",
        "observation_at_ist": "2026-09-16T05:30:00+05:30",
        "symbol_count": 1,
        "rows": [{"classifier_phase": "CAS_ORDER_ENTRY", "symbol": "X"}],
    }
    p = tmp_path / "missing_dry_run.json"
    p.write_text(json.dumps(doc))
    assert _read_dry_run(p) is None


def test_read_dry_run_non_boolean_returns_none(tmp_path):
    """A capture with a non-boolean dry_run returns None."""
    doc = {
        "tool": "j2_cas_probe",
        "schema_version": "j2_cas_probe_v1",
        "generated_at_utc": "2026-09-16T00:00:00+00:00",
        "dry_run": "yes",  # wrong type
        "observation_at_utc": "2026-09-16T00:00:00+00:00",
        "observation_at_ist": "2026-09-16T05:30:00+05:30",
        "symbol_count": 1,
        "rows": [{"classifier_phase": "CAS_ORDER_ENTRY", "symbol": "X"}],
    }
    p = tmp_path / "string_dry_run.json"
    p.write_text(json.dumps(doc))
    assert _read_dry_run(p) is None


def test_read_dry_run_unreadable_returns_none(tmp_path):
    """An unreadable capture returns None."""
    p = tmp_path / "broken.json"
    p.write_text("not valid json {{{")
    assert _read_dry_run(p) is None


def test_read_dry_run_empty_doc_returns_none(tmp_path):
    """An empty JSON document returns None."""
    p = tmp_path / "empty.json"
    p.write_text("{}")
    assert _read_dry_run(p) is None


# ─── cas_reachability_report dry_run attribution ──────────


def test_dry_run_attribution_present_in_empty_report(tmp_path):
    """Empty captures dir returns the attribution field
    with all buckets at zero.
    """
    report = cas_reachability_report(captures_dir=tmp_path)
    attr = report["dry_run_attribution"]
    assert attr == {
        "real": 0, "dry_run": 0, "unknown": 0, "total_unique": 0,
    }


def test_dry_run_attribution_real_only(tmp_path):
    """All-real captures: real=2, dry_run=0, unknown=0."""
    _write_capture(tmp_path, "a.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=False)
    _write_capture(tmp_path, "b.json", "CAS_ORDER_ENTRY", dry_run=False)
    report = cas_reachability_report(captures_dir=tmp_path)
    attr = report["dry_run_attribution"]
    assert attr["real"] == 2
    assert attr["dry_run"] == 0
    assert attr["unknown"] == 0
    assert attr["total_unique"] == 2


def test_dry_run_attribution_mixed_real_and_sim(tmp_path):
    """Mixed captures: real + dry_run buckets populated."""
    _write_capture(tmp_path, "real.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=False)
    _write_capture(tmp_path, "sim.json", "CAS_ORDER_ENTRY", dry_run=True)
    _write_capture(tmp_path, "real2.json", "CAS_MATCHING", dry_run=False)
    report = cas_reachability_report(captures_dir=tmp_path)
    attr = report["dry_run_attribution"]
    assert attr["real"] == 2
    assert attr["dry_run"] == 1
    assert attr["unknown"] == 0
    assert attr["total_unique"] == 3


def test_dry_run_attribution_unknown_bucket(tmp_path):
    """A capture with missing dry_run field goes into
    ``unknown``, not silently bucketed as real.
    """
    _write_capture(tmp_path, "real.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=False)
    # Now write a capture with NO dry_run field.
    doc = {
        "tool": "j2_cas_probe",
        "schema_version": "j2_cas_probe_v1",
        "generated_at_utc": "2026-09-16T00:00:00+00:00",
        "observation_at_utc": "2026-09-16T00:00:00+00:00",
        "observation_at_ist": "2026-09-16T05:30:00+05:30",
        "symbol_count": 1,
        "rows": [{"classifier_phase": "CAS_ORDER_ENTRY", "symbol": "X"}],
    }
    (tmp_path / "unknown.json").write_text(json.dumps(doc))
    report = cas_reachability_report(captures_dir=tmp_path)
    attr = report["dry_run_attribution"]
    assert attr["real"] == 1
    assert attr["dry_run"] == 0
    assert attr["unknown"] == 1
    assert attr["total_unique"] == 2


def test_dry_run_attribution_dedupes_duplicates(tmp_path):
    """A duplicate capture does NOT inflate the attribution
    count -- the gate's dedup discipline applies. Two
    identical files count as ONE unique capture.
    """
    p1 = _write_capture(tmp_path, "a.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=False)
    # Copy the same content to a different filename.
    p2_content = p1.read_text()
    (tmp_path / "a_copy.json").write_text(p2_content)
    report = cas_reachability_report(captures_dir=tmp_path)
    attr = report["dry_run_attribution"]
    # Only the FIRST occurrence is counted toward attribution.
    assert attr["real"] == 1
    assert attr["total_unique"] == 1


def test_dry_run_attribution_does_not_change_verdict(tmp_path):
    """Dry-run captures count toward REACHABLE the same as
    real captures (per the slice design: the verdict logic
    is unchanged; the attribution is purely diagnostic).
    """
    # Fill all 6 branches with dry_run=True captures.
    branches = [
        "CAS_REFERENCE_PRICE_WINDOW",
        "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY",
        "CAS_MATCHING",
        "CAS_POST",
        "DERIVATIVES_CAS_ALIGNED",
    ]
    for i, branch in enumerate(branches):
        _write_capture(
            tmp_path, f"sim_{i}.json", branch,
            dry_run=True,
        )
    report = cas_reachability_report(captures_dir=tmp_path)
    # Verdict is REACHABLE (all 6 covered).
    assert report["verdict"] == "REACHABLE"
    # But attribution shows ALL of them are dry_run.
    assert report["dry_run_attribution"]["dry_run"] == 6
    assert report["dry_run_attribution"]["real"] == 0


def test_dry_run_attribution_total_equals_real_plus_dry_run_plus_unknown(tmp_path):
    """Invariant: total_unique = real + dry_run + unknown.
    This holds even when there are duplicates -- total
    counts only UNIQUE first-occurrence captures.
    """
    _write_capture(tmp_path, "real.json", "CAS_REFERENCE_PRICE_WINDOW", dry_run=False)
    _write_capture(tmp_path, "sim.json", "CAS_ORDER_ENTRY", dry_run=True)
    _write_capture(tmp_path, "real2.json", "CAS_MATCHING", dry_run=False)
    report = cas_reachability_report(captures_dir=tmp_path)
    attr = report["dry_run_attribution"]
    assert attr["total_unique"] == (
        attr["real"] + attr["dry_run"] + attr["unknown"]
    )
