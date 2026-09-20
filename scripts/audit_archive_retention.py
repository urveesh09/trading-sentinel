#!/usr/bin/env python3
"""[WORKFLOW-B.6 2026-09-17] Archive retention audit.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Review retention cleanup so capture files and referenced
> masters outlive qualification review.

This tool reads PROD's archive directory and reports which
files are safe to clean, which must be retained (because
they're referenced by qualification records), and which
fall in between.

Classification:

  REFERENCED              -- file is referenced by a
                             ``partner_research_capture`` or
                             ``partner_advisory_ideas`` row.
                             MUST outlive review.
  OLD_AND_UNREFERENCED     -- older than retention threshold
                             AND not referenced. Safe to clean.
  OLD_AND_REFERENCED       -- older than threshold AND
                             referenced. KEEP (referenced
                             wins).
  RECENT_AND_UNREFERENCED   -- newer than threshold and not
                             referenced. Likely still
                             in-flight; do not clean.
  MISSING                  -- artifact_ref in DB points to a
                             file that no longer exists.
                             Reference is dangling.

Read-only. Never deletes files.

Usage::

    # Audit PROD's archive.
    python scripts/audit_archive_retention.py \\
        --archive-root /data/archive \\
        --db-path /data/cache.db \\
        --retention-days 30

    # JSON output.
    python scripts/audit_archive_retention.py \\
        --archive-root /data/archive \\
        --db-path /data/cache.db \\
        --json

Exit codes:
  0  -- audit completed (regardless of cleanup candidates).
  2  -- input invalid (missing archive / DB).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional


class RetentionClass(str, enum.Enum):
    """Classification of a single file."""
    REFERENCED = "REFERENCED"
    OLD_AND_UNREFERENCED = "OLD_AND_UNREFERENCED"
    OLD_AND_REFERENCED = "OLD_AND_REFERENCED"
    RECENT_AND_UNREFERENCED = "RECENT_AND_UNREFERENCED"
    MISSING = "MISSING"

    def is_cleanable(self) -> bool:
        """True iff the file is safe to delete."""
        return self == RetentionClass.OLD_AND_UNREFERENCED


@dataclasses.dataclass(frozen=True)
class RetentionEntry:
    """One row of the retention audit report."""
    path: str
    size_bytes: int
    modified_at: Optional[str]
    referenced_by: tuple[str, ...]
    classification: RetentionClass
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "referenced_by": list(self.referenced_by),
            "classification": self.classification.value,
            "is_cleanable": self.classification.is_cleanable(),
            "notes": list(self.notes),
        }


@dataclasses.dataclass(frozen=True)
class RetentionReport:
    """Combined retention audit report."""
    archive_root: str
    db_path: Optional[str]
    retention_days: int
    cutoff_at: str
    entries: tuple[RetentionEntry, ...]

    @property
    def cleanable_bytes(self) -> int:
        return sum(
            e.size_bytes for e in self.entries
            if e.classification.is_cleanable()
        )

    @property
    def cleanable_count(self) -> int:
        return sum(
            1 for e in self.entries
            if e.classification.is_cleanable()
        )

    @property
    def referenced_count(self) -> int:
        return sum(
            1 for e in self.entries
            if e.classification == RetentionClass.REFERENCED
            or e.classification == RetentionClass.OLD_AND_REFERENCED
        )

    @property
    def missing_refs_count(self) -> int:
        return sum(
            1 for e in self.entries if e.classification == RetentionClass.MISSING
        )

    def to_dict(self) -> dict:
        return {
            "archive_root": self.archive_root,
            "db_path": self.db_path,
            "retention_days": self.retention_days,
            "cutoff_at": self.cutoff_at,
            "cleanable_count": self.cleanable_count,
            "cleanable_bytes": self.cleanable_bytes,
            "referenced_count": self.referenced_count,
            "missing_refs_count": self.missing_refs_count,
            "entries": [e.to_dict() for e in self.entries],
        }


def _load_referenced_artifacts(db_path: Path) -> set[str]:
    """Return the set of artifact paths referenced by
    ``partner_research_capture`` or ``partner_advisory_ideas``.

    Both tables have a column ``artifact_ref`` (or
    ``rendered_card``/``payload`` -- we focus on
    ``artifact_ref``). Returns ``{}`` when the DB or
    columns are missing.
    """
    if not db_path.is_file():
        return set()
    refs: set[str] = set()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # partner_research_capture rows: artifact_ref column.
        try:
            cur = conn.execute(
                "SELECT artifact_ref FROM partner_research_capture "
                "WHERE artifact_ref IS NOT NULL AND artifact_ref != ''"
            )
            for row in cur.fetchall():
                if row[0]:
                    refs.add(row[0])
        except sqlite3.OperationalError:
            pass
        # partner_advisory_ideas rows: artifact_ref or payload
        # paths inside the rendered_card / payload columns.
        try:
            cur = conn.execute(
                "SELECT payload FROM partner_advisory_ideas "
                "WHERE payload IS NOT NULL"
            )
            for row in cur.fetchall():
                try:
                    payload = json.loads(row[0])
                except (ValueError, TypeError):
                    continue
                if isinstance(payload, dict):
                    for key in ("artifact_ref", "master_ref",
                                "rendered_card_ref"):
                        v = payload.get(key)
                        if isinstance(v, str) and v:
                            refs.add(v)
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()
    return refs


def _scan_archive_files(
    archive_root: Path,
) -> list[tuple[Path, int, Optional[datetime]]]:
    """Walk the archive and return every regular file with
    size + modified timestamp."""
    if not archive_root.is_dir():
        return []
    out: list[tuple[Path, int, Optional[datetime]]] = []
    for path in archive_root.rglob("*"):
        if not path.is_file():
            continue
        # Skip the SQLite database files themselves; they're
        # always "referenced" by the system but the
        # retention audit is about content artifacts.
        if path.suffix == ".sqlite3":
            continue
        try:
            size = path.stat().st_size
            mtime = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc,
            )
            out.append((path, size, mtime))
        except OSError:
            out.append((path, 0, None))
    return out


def _classify_file(
    archive_root: Path,
    file_path: Path,
    size: int,
    mtime: Optional[datetime],
    cutoff: datetime,
    referenced: set[str],
) -> RetentionEntry:
    """Classify a single file.

    A file is "referenced" if its absolute path matches one
    of the strings in ``referenced``. We also accept the
    basename match as a fallback (some DB rows record just
    the file name).
    """
    rel_path = str(file_path.relative_to(archive_root))
    abs_path = str(file_path)
    base = file_path.name
    refs_for_this = tuple(
        r for r in sorted(referenced)
        if r and (r == abs_path or r == rel_path or r == base
                   or r.endswith(base))
    )
    is_referenced = bool(refs_for_this)

    notes: list[str] = []
    if mtime is None:
        return RetentionEntry(
            path=rel_path, size_bytes=size,
            modified_at=None,
            referenced_by=refs_for_this,
            classification=RetentionClass.MISSING,
            notes=("could not stat mtime",),
        )

    age_seconds = (datetime.now(timezone.utc) - mtime).total_seconds()
    is_old = mtime < cutoff

    if is_referenced:
        if is_old:
            cls = RetentionClass.OLD_AND_REFERENCED
            notes.append("referenced; must outlive review")
        else:
            cls = RetentionClass.REFERENCED
    else:
        if is_old:
            cls = RetentionClass.OLD_AND_UNREFERENCED
            notes.append(f"age={int(age_seconds // 86400)}d "
                          f"> retention; safe to clean")
        else:
            cls = RetentionClass.RECENT_AND_UNREFERENCED
            notes.append(f"recent ({int(age_seconds // 3600)}h); "
                          "not yet safe to clean")
    return RetentionEntry(
        path=rel_path,
        size_bytes=size,
        modified_at=mtime.isoformat(),
        referenced_by=refs_for_this,
        classification=cls,
        notes=tuple(notes),
    )


def audit_retention(
    *,
    archive_root: str | Path,
    db_path: Optional[str | Path] = None,
    retention_days: int = 30,
    now: Optional[datetime] = None,
) -> RetentionReport:
    """Audit the archive's retention status.

    Args:
        archive_root: PROD's archive directory.
        db_path: optional path to ``cache.db`` to read
            referenced-artifact records from. When ``None``,
            every file is treated as unreferenced (conservative
            "nothing is safe to clean").
        retention_days: age threshold in days. Files older
            than this are candidates for cleanup (subject to
            reference check).
        now: override current time (timezone-aware).

    Returns:
        A ``RetentionReport`` with one entry per file in
        the archive.
    """
    archive_root_path = Path(archive_root)
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    referenced: set[str] = set()
    if db_path is not None:
        referenced = _load_referenced_artifacts(Path(db_path))

    files = _scan_archive_files(archive_root_path)
    entries = tuple(
        _classify_file(
            archive_root_path, file_path, size, mtime,
            cutoff, referenced,
        )
        for file_path, size, mtime in files
    )
    return RetentionReport(
        archive_root=str(archive_root_path),
        db_path=str(db_path) if db_path else None,
        retention_days=retention_days,
        cutoff_at=cutoff.isoformat(),
        entries=entries,
    )


def format_report(report: RetentionReport) -> str:
    """Render the audit report as human-readable text."""
    lines = [
        "# Archive retention audit",
        "# ----------------------",
        f"# archive_root:    {report.archive_root}",
        f"# db_path:         {report.db_path or '<none>'}",
        f"# retention_days:  {report.retention_days}",
        f"# cutoff_at:       {report.cutoff_at}",
        "",
        f"# cleanable:       {report.cleanable_count} file(s) "
        f"({report.cleanable_bytes} bytes)",
        f"# referenced:      {report.referenced_count} file(s)",
        f"# missing refs:    {report.missing_refs_count}",
        "",
    ]
    # Group by classification.
    by_class: dict[str, list[RetentionEntry]] = {}
    for e in report.entries:
        by_class.setdefault(e.classification.value, []).append(e)
    for cls_name in (
        "MISSING",
        "OLD_AND_UNREFERENCED",
        "OLD_AND_REFERENCED",
        "REFERENCED",
        "RECENT_AND_UNREFERENCED",
    ):
        items = by_class.get(cls_name, [])
        if not items:
            continue
        lines.append(f"## [{cls_name}] ({len(items)})")
        for e in items[:50]:  # cap display
            lines.append(f"- {e.path} ({e.size_bytes}B)")
            for note in e.notes:
                lines.append(f"  - {note}")
            if e.referenced_by:
                for ref in e.referenced_by:
                    lines.append(f"  referenced: {ref}")
        if len(items) > 50:
            lines.append(f"  ... and {len(items) - 50} more")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", required=True,
                        help="path to PROD's archive root")
    parser.add_argument("--db-path", default=None,
                        help="path to PROD's cache.db (optional)")
    parser.add_argument("--retention-days", type=int, default=30,
                        help="retention threshold in days (default 30)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    archive_root = Path(args.archive_root)
    if not archive_root.is_dir():
        print(
            f"audit_archive_retention: archive root not found: "
            f"{archive_root}", file=sys.stderr,
        )
        return 2

    report = audit_retention(
        archive_root=archive_root,
        db_path=args.db_path,
        retention_days=args.retention_days,
    )
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(format_report(report))
    return 0


__all__ = [
    "RetentionClass",
    "RetentionEntry",
    "RetentionReport",
    "audit_retention",
    "format_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
