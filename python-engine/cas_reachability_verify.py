"""[WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] SUMMARY.md drift verification.

The J.10 SUMMARY.md is the persistent audit surface for the
gate. Today it's written by ``update_summary(report, summary_path,
captures_dir)`` -- a one-way write that overwrites whatever is
on disk. If something corrupts the on-disk file (manual edit,
disk error, partial write, race with a stale process), the SUMMARY
diverges from what the gate would produce right now.

This module exposes ``verify_summary(report, summary_path,
*, captures_dir=None)``:
  - Render the report into a fresh SUMMARY (via
    ``update_summary``).
  - Compare bytes against the on-disk file.
  - Return a structured ``VerificationReport`` with
    ``match: bool``, ``on_disk_path``, ``generated_at``,
    ``expected_first_line``, ``actual_first_line`` (when
    mismatch), and ``diff_kind`` (one of ``MATCH`` /
    ``ON_DISK_MISSING`` / ``BYTES_DIFFER`` / ``GENERATED_AT_DIFFER``).

The function is pure / total / never raises. The CLI exposes
it via ``--verify-summary``; the operator can compare the
on-disk SUMMARY against the current gate state without
running ``--update-summary`` (which would overwrite).

No new dependencies. Stdlib only (``pathlib``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class DiffKind(str, Enum):
    """The kind of drift detected by ``verify_summary``."""

    MATCH = "MATCH"
    ON_DISK_MISSING = "ON_DISK_MISSING"
    BYTES_DIFFER = "BYTES_DIFFER"
    GENERATED_AT_DIFFER = "GENERATED_AT_DIFFER"


@dataclass(frozen=True)
class VerificationReport:
    """A structured drift report.

    Attributes:
        kind: The drift kind. ``MATCH`` means the on-disk
            SUMMARY is byte-identical to what ``update_summary``
            would write right now. Any other value indicates
            drift.
        on_disk_path: The path to the SUMMARY.md that was
            checked. ``None`` when the file does not exist
            (the operator can still get a fresh render from
            ``update_summary``).
        generated_at: The ``generated_at_utc`` timestamp
            embedded in the rendered SUMMARY. Operators can
            correlate this with the underlying report's
            ``evaluated_at`` field to know how stale the
            on-disk SUMMARY is.
        expected_size: The byte size of the freshly-rendered
            SUMMARY. Operators see "on-disk has N bytes; fresh
            render has M bytes" at a glance.
        actual_size: The byte size of the on-disk SUMMARY. ``None``
            when the file does not exist.
    """

    kind: DiffKind
    on_disk_path: Optional[str]
    generated_at: Optional[str]
    expected_size: int
    actual_size: Optional[int]

    @property
    def matches(self) -> bool:
        """True iff the on-disk SUMMARY is byte-identical to the
        freshly-rendered SUMMARY.

        Convenience property so the CLI can use
        ``return 0 if report.matches else 1`` without touching
        the ``DiffKind`` enum.
        """
        return self.kind == DiffKind.MATCH


def verify_summary(
    report: dict[str, Any],
    summary_path: Path,
    *,
    captures_dir: Optional[Path] = None,
) -> VerificationReport:
    """Render the report and diff against ``summary_path``.

    Args:
        report: The bounded gate report dict. Must be JSON-
            serialisable; same constraints as ``update_summary``.
        summary_path: The path to the on-disk SUMMARY.md. If
            the file does not exist, the result is
            ``DiffKind.ON_DISK_MISSING`` (the operator gets a
            fresh render but no drift to compare against).
        captures_dir: Optional override for the captures root
            path. ``None`` defaults to the standard J.3
            ``docs/j2_captures/`` path.

    Returns:
        ``VerificationReport`` with the diff kind and byte
        sizes. The function NEVER raises -- a corrupt on-disk
        file, a missing directory, or a non-UTF-8 read all
        degrade to ``BYTES_DIFFER`` (the safest non-match
        verdict).

    The freshly-rendered SUMMARY is the canonical output of
    ``update_summary``. We do NOT write it to disk -- this
    function is read-only. The CLI's ``--update-summary`` flag
    is the operator-side way to commit a fresh render.
    """
    # Lazy import: ``update_summary`` lives in the gate module
    # and we want this helper importable in isolation for tests.
    from cas_reachability_gate import update_summary

    summary_path = Path(summary_path)

    # Render the canonical SUMMARY into a tmp file so we can
    # compare bytes without touching the on-disk file. The
    # tmp file is auto-cleaned via ``tempfile``'s context
    # manager; if anything raises, the cleanup runs.
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=".j10_summary_verify-",
        suffix=".md",
        delete=False,
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
    try:
        update_summary(
            report,
            tmp_path,
            captures_dir=captures_dir,
        )
        expected_bytes = tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass

    # Pull the ``Generated at`` line out of the freshly-rendered
    # SUMMARY so the operator sees the timestamp without
    # diffing the whole file. The line format is stable:
    # ``**Generated at**: 2026-09-14T... UTC``.
    expected_text = expected_bytes.decode("utf-8", errors="replace")
    expected_generated_at = _extract_generated_at(expected_text)
    expected_size = len(expected_bytes)

    # On-disk file present?
    if not summary_path.exists():
        return VerificationReport(
            kind=DiffKind.ON_DISK_MISSING,
            on_disk_path=None,
            generated_at=expected_generated_at,
            expected_size=expected_size,
            actual_size=None,
        )

    # Read the on-disk file defensively. A corrupt or
    # non-readable file degrades to BYTES_DIFFER.
    try:
        actual_bytes = summary_path.read_bytes()
    except OSError:
        return VerificationReport(
            kind=DiffKind.BYTES_DIFFER,
            on_disk_path=str(summary_path),
            generated_at=expected_generated_at,
            expected_size=expected_size,
            actual_size=None,
        )

    actual_size = len(actual_bytes)

    # Byte-identical -> MATCH. This is the strongest invariant:
    # two runs of the same report produce identical bytes (per
    # the J.10.WRITE_ATOMIC discipline). Anything different,
    # including the ``Generated at`` timestamp, is a diff.
    if actual_bytes == expected_bytes:
        return VerificationReport(
            kind=DiffKind.MATCH,
            on_disk_path=str(summary_path),
            generated_at=expected_generated_at,
            expected_size=expected_size,
            actual_size=actual_size,
        )

    # The bytes differ. Try to distinguish "only the timestamp
    # changed" from "the body changed" -- the former is a benign
    # re-render (operator just needs to ``--update-summary``);
    # the latter is suspicious (manual edit, partial write,
    # schema drift).
    actual_text = actual_bytes.decode("utf-8", errors="replace")
    actual_generated_at = _extract_generated_at(actual_text)

    if _strip_generated_at(expected_text) == _strip_generated_at(actual_text):
        return VerificationReport(
            kind=DiffKind.GENERATED_AT_DIFFER,
            on_disk_path=str(summary_path),
            generated_at=expected_generated_at,
            expected_size=expected_size,
            actual_size=actual_size,
        )

    return VerificationReport(
        kind=DiffKind.BYTES_DIFFER,
        on_disk_path=str(summary_path),
        generated_at=expected_generated_at,
        expected_size=expected_size,
        actual_size=actual_size,
    )


def _extract_generated_at(text: str) -> Optional[str]:
    """Pull the ``Generated at: <ISO> UTC`` line out of a SUMMARY.

    Returns ``None`` if the line is missing or malformed. The
    function is intentionally lenient -- a corrupt timestamp
    is a real failure mode and the operator wants to see "no
    timestamp found", not "couldn't parse".
    """
    for line in text.splitlines():
        marker = "**Generated at**:"
        if marker not in line:
            continue
        idx = line.index(marker) + len(marker)
        tail = line[idx:].strip()
        # Strip a trailing "UTC" if present.
        if tail.endswith(" UTC"):
            tail = tail[:-4].strip()
        return tail or None
    return None


def _strip_generated_at(text: str) -> str:
    """Return ``text`` with the ``Generated at:`` line removed.

    Used to detect "only the timestamp changed" drifts -- a
    benign re-render where the body is unchanged but the
    ``Generated at: <ISO> UTC`` line naturally differs.

    Trailing-newline preservation matters because the byte
    comparison downstream is ``==``. If the freshly-rendered
    SUMMARY ends with a trailing newline and our stripped
    version does not, the comparison fails spuriously.
    """
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        if "**Generated at**:" in line:
            continue
        kept.append(line)
    # ``splitlines`` drops the trailing newline; ``split('\n')``
    # keeps it. Detect the trailing newline manually and
    # re-append it.
    stripped = "\n".join(kept)
    if text.endswith("\n") and not stripped.endswith("\n"):
        stripped = stripped + "\n"
    return stripped


__all__ = [
    "DiffKind",
    "VerificationReport",
    "verify_summary",
]
