"""[WORKFLOW-B.6 2026-09-17] Tests for the archive retention
audit.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Review retention cleanup so capture files and referenced
> masters outlive qualification review.

These tests pin the classification rules:

  - REFERENCED: file appears in partner_research_capture
    or partner_advisory_ideas rows.
  - OLD_AND_UNREFERENCED: older than retention + not
    referenced. Safe to clean.
  - OLD_AND_REFERENCED: older than retention + referenced.
    KEEP (reference wins).
  - RECENT_AND_UNREFERENCED: newer than retention + not
    referenced. Wait.
  - MISSING: could not stat or DB-only artifact_ref.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = (Path(__file__).resolve().parents[1]
                 / "audit_archive_retention.py")
WORKDIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(SCRIPTS_DIR))

from audit_archive_retention import (  # noqa: E402  -- import path
    RetentionClass,
    RetentionEntry,
    RetentionReport,
    audit_retention,
    format_report,
)


def _make_archive(tmp_path: Path) -> Path:
    return tmp_path / "archive"


def _make_file(
    archive: Path,
    name: str,
    *,
    age_days: int = 0,
    content: str = "{}",
) -> Path:
    """Create a file with controlled mtime."""
    path = archive / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if age_days > 0:
        old = datetime.now(timezone.utc) - timedelta(days=age_days)
        ts = old.timestamp()
        os.utime(path, (ts, ts))
    return path


def _make_db(tmp_path: Path, *, refs: list[str]) -> Path:
    db = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE partner_research_capture ("
        "  capture_id TEXT, generated_at TEXT, kind TEXT, state TEXT, "
        "  artifact_ref TEXT)"
    )
    for i, ref in enumerate(refs):
        conn.execute(
            "INSERT INTO partner_research_capture VALUES "
            "(?, ?, ?, ?, ?)",
            (f"cap-{i}", "2026-09-17T13:00:00+00:00",
             "qualified", "VERIFIED", ref),
        )
    conn.commit()
    conn.close()
    return db


# -- 1. RetentionClass enum ----------------------------------


def test_retention_class_has_five_values():
    """[WORKFLOW-B.6 2026-09-17] Five classifications:
    REFERENCED, OLD_AND_UNREFERENCED, OLD_AND_REFERENCED,
    RECENT_AND_UNREFERENCED, MISSING."""
    assert {c.value for c in RetentionClass} == {
        "REFERENCED",
        "OLD_AND_UNREFERENCED",
        "OLD_AND_REFERENCED",
        "RECENT_AND_UNREFERENCED",
        "MISSING",
    }


def test_only_old_and_unreferenced_is_cleanable():
    assert RetentionClass.OLD_AND_UNREFERENCED.is_cleanable() is True
    for cls in RetentionClass:
        if cls == RetentionClass.OLD_AND_UNREFERENCED:
            continue
        assert cls.is_cleanable() is False


# -- 2. Empty / missing archive ------------------------------


def test_audit_missing_archive_returns_empty_report(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] Missing archive is not a
    crash; the audit returns an empty report so the
    upstream CLI can format a useful message."""
    bogus = tmp_path / "does_not_exist"
    report = audit_retention(archive_root=bogus)
    assert report.entries == ()


def test_audit_empty_archive_returns_empty_report(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    report = audit_retention(archive_root=archive)
    assert report.entries == ()


def test_audit_skips_sqlite_files(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] The .sqlite3 DB files are
    always referenced by the system; the retention audit
    is about content artifacts, so we skip them."""
    archive = _make_archive(tmp_path)
    archive.mkdir()
    (archive / "partner-collection-attempts.sqlite3").write_bytes(b"")
    report = audit_retention(archive_root=archive)
    paths = [e.path for e in report.entries]
    assert "partner-collection-attempts.sqlite3" not in paths


# -- 3. Classification rules ---------------------------------


def test_old_unreferenced_file_classified_as_cleanable(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    report = audit_retention(archive_root=archive, retention_days=30)
    assert len(report.entries) == 1
    e = report.entries[0]
    assert e.classification == RetentionClass.OLD_AND_UNREFERENCED
    assert e.classification.is_cleanable()


def test_recent_unreferenced_file_is_not_cleanable(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "recent.json", age_days=1)
    report = audit_retention(archive_root=archive, retention_days=30)
    e = report.entries[0]
    assert e.classification == RetentionClass.RECENT_AND_UNREFERENCED
    assert not e.classification.is_cleanable()


def test_old_referenced_file_classified_as_old_and_referenced(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] Old + referenced = KEEP.
    Reference wins over retention threshold."""
    archive = _make_archive(tmp_path)
    archive.mkdir()
    old_ref = _make_file(archive, "old_ref.json", age_days=60)
    db = _make_db(tmp_path, refs=[str(old_ref)])
    report = audit_retention(
        archive_root=archive, db_path=db, retention_days=30,
    )
    e = report.entries[0]
    assert e.classification == RetentionClass.OLD_AND_REFERENCED
    assert not e.classification.is_cleanable()
    assert str(old_ref) in e.referenced_by


def test_recent_referenced_file_is_just_referenced(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    ref = _make_file(archive, "ref.json", age_days=2)
    db = _make_db(tmp_path, refs=[str(ref)])
    report = audit_retention(
        archive_root=archive, db_path=db, retention_days=30,
    )
    e = report.entries[0]
    assert e.classification == RetentionClass.REFERENCED


def test_relative_path_reference_also_matches(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] Some DB rows store the
    relative path; the audit must accept that."""
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "subdir/file.json", age_days=60)
    db = _make_db(tmp_path, refs=["subdir/file.json"])
    report = audit_retention(
        archive_root=archive, db_path=db, retention_days=30,
    )
    e = report.entries[0]
    assert e.classification == RetentionClass.OLD_AND_REFERENCED


def test_basename_reference_also_matches(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] Some DB rows store just
    the file name; the audit must accept that."""
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "deep/nested/file.json", age_days=60)
    db = _make_db(tmp_path, refs=["file.json"])
    report = audit_retention(
        archive_root=archive, db_path=db, retention_days=30,
    )
    e = report.entries[0]
    assert e.classification == RetentionClass.OLD_AND_REFERENCED


# -- 4. Aggregate report --------------------------------------


def test_report_aggregates_cleanable_count(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old1.json", age_days=60)
    _make_file(archive, "old2.json", age_days=45)
    _make_file(archive, "recent.json", age_days=1)
    report = audit_retention(archive_root=archive, retention_days=30)
    assert report.cleanable_count == 2
    assert report.cleanable_bytes > 0


def test_report_referenced_count_includes_old_and_referenced(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    old_ref = _make_file(archive, "old_ref.json", age_days=60)
    recent_ref = _make_file(archive, "recent_ref.json", age_days=1)
    db = _make_db(tmp_path, refs=[str(old_ref), str(recent_ref)])
    report = audit_retention(
        archive_root=archive, db_path=db, retention_days=30,
    )
    assert report.referenced_count == 2


def test_report_to_dict_includes_aggregate_fields(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    report = audit_retention(archive_root=archive, retention_days=30)
    d = report.to_dict()
    assert "cleanable_count" in d
    assert "cleanable_bytes" in d
    assert "referenced_count" in d
    assert "missing_refs_count" in d


def test_report_handles_no_db_path(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] When db_path is None, the
    audit is conservative: every file is treated as
    unreferenced."""
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    report = audit_retention(
        archive_root=archive, db_path=None, retention_days=30,
    )
    e = report.entries[0]
    assert e.classification == RetentionClass.OLD_AND_UNREFERENCED


def test_report_handles_missing_db_file(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    bogus_db = tmp_path / "does_not_exist.db"
    report = audit_retention(
        archive_root=archive, db_path=bogus_db, retention_days=30,
    )
    e = report.entries[0]
    assert e.classification == RetentionClass.OLD_AND_UNREFERENCED


# -- 5. RetentionEntry dataclass ------------------------------


def test_entry_to_dict_includes_required_fields(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "x.json", age_days=60)
    report = audit_retention(archive_root=archive, retention_days=30)
    e = report.entries[0]
    d = e.to_dict()
    expected = {"path", "size_bytes", "modified_at", "referenced_by",
                "classification", "is_cleanable", "notes"}
    assert set(d.keys()) == expected


# -- 6. format_report -----------------------------------------


def test_format_report_includes_summary(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    report = audit_retention(archive_root=archive, retention_days=30)
    text = format_report(report)
    assert "Archive retention audit" in text
    assert "cleanable:" in text


def test_format_report_groups_by_classification(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    _make_file(archive, "recent.json", age_days=1)
    report = audit_retention(archive_root=archive, retention_days=30)
    text = format_report(report)
    assert "OLD_AND_UNREFERENCED" in text
    assert "RECENT_AND_UNREFERENCED" in text


# -- 7. CLI integration ---------------------------------------


def _run_cli(archive: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--archive-root", str(archive), *args],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=15,
    )


def test_cli_missing_archive_returns_exit_two(tmp_path):
    bogus = tmp_path / "does_not_exist"
    result = _run_cli(bogus)
    assert result.returncode == 2


def test_cli_empty_archive_returns_exit_zero(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    result = _run_cli(archive)
    assert result.returncode == 0
    assert "cleanable:       0" in result.stdout


def test_cli_json_flag_emits_valid_json(tmp_path):
    archive = _make_archive(tmp_path)
    archive.mkdir()
    _make_file(archive, "old.json", age_days=60)
    result = _run_cli(archive, "--json")
    parsed = json.loads(result.stdout)
    assert "cleanable_count" in parsed
    assert "entries" in parsed


def test_cli_with_db_references_old_files(tmp_path):
    """[WORKFLOW-B.6 2026-09-17] End-to-end: archive + DB
    referencing an old file -> file is OLD_AND_REFERENCED
    (KEEP)."""
    archive = _make_archive(tmp_path)
    archive.mkdir()
    old_ref = _make_file(archive, "important.json", age_days=60)
    db = _make_db(tmp_path, refs=[str(old_ref)])
    result = _run_cli(archive, "--db-path", str(db))
    assert "OLD_AND_REFERENCED" in result.stdout
    assert "must outlive review" in result.stdout
