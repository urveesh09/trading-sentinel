"""[WORKFLOW-J.10.CAPTURE_SUMMARY_AGGREGATE 2026-09-14] Per-day capture histogram.

The J.10 SUMMARY surfaces TOTAL counts (captures_scanned,
captures_skipped, captured_phases). The operator's audit picture
is complete only when they can see *evidence velocity over
time* -- how many captures per day, when the bulk of evidence
was collected, and whether evidence is fresh or stale.

This module exposes two pure helpers:

    per_day_breakdown(
        captures_root: Path,
        *,
        unique_per_path: Optional[Mapping[str, str]] = None,
    ) -> dict[str, dict[str, int]]
        Walk ``captures_root.rglob("*.json")`` and bucket by the
        ``YYYY-MM-DD`` subdirectory name. Each day maps to
        ``{"unique": N, "scanned": M}``. ``unique`` is the count
        of DISTINCT capture paths that contributed evidence
        (after the dedup filter, if the caller passes the
        ``unique_per_path`` mapping); ``scanned`` is the count
        of all .json files found under that date (regardless of
        validity). Pure / total / never raises.

    format_per_day_table(
        per_day: dict[str, dict[str, int]],
        *,
        max_rows: int = 7,
    ) -> str
        Render ``per_day`` as a markdown table, sorted ascending
        by date, with the most recent days at the bottom.
        Collapses to ``max_rows`` rows + ``"+ N more days"`` if
        the dictionary has more entries.

The gate in ``cas_reachability_gate.py`` calls ``per_day_breakdown``
inside ``cas_reachability_report`` (after the dedup loop, so
``unique_per_path`` reflects which captures actually counted
toward coverage). The SUMMARY gains a ``## Captures per day``
section between the catalog and the duplicates sections.

No new dependencies. Stdlib only (``pathlib``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional


def per_day_breakdown(
    captures_root: Path,
    *,
    unique_per_path: Optional[Mapping[str, str]] = None,
) -> dict[str, dict[str, int]]:
    """Bucket captures by their ``YYYY-MM-DD`` parent directory.

    Args:
        captures_root: The captures directory (per docs/j2_captures/
            README.md). Walks ``captures_root.rglob("*.json")`` and
            uses the immediate-parent directory name (relative to
            ``captures_root``) as the date bucket. Files at the
            root level (no YYYY-MM-DD subdirectory) are bucketed
            under the literal string ``"(unfiled)"`` so they are
            visible in the SUMMARY instead of silently dropped.

        unique_per_path: Optional mapping from capture path (as a
            string, the ``str(capture_path)`` value the gate uses)
            to the unique fingerprint that was counted. When
            provided, ``unique`` counts only the captures whose
            fingerprint is the FIRST occurrence under its branch
            (i.e. the captures that actually contributed to the
            REACHABLE verdict, post-J.10.DEDUP). When ``None``,
            ``unique`` equals ``scanned`` (the pre-dedup count).

    Returns:
        ``dict[str, dict[str, int]]`` mapping ``YYYY-MM-DD`` (or
        ``"(unfiled)"``) to ``{"scanned": M, "unique": N}``. Sorted
        by date ascending on demand in ``format_per_day_table``.

    The function is pure / total / never raises. A missing or
    empty directory returns an empty dict.
    """
    captures_root = Path(captures_root)
    if not captures_root.exists():
        return {}

    per_day: dict[str, dict[str, int]] = {}

    for capture_path in captures_root.rglob("*.json"):
        # Bucket by the immediate-parent directory name relative
        # to ``captures_root``. The gate's contract (per docs/
        # j2_captures/README.md) is YYYY-MM-DD subdirectories;
        # a stray file at the root lands in "(unfiled)".
        try:
            rel_parent = capture_path.parent.relative_to(captures_root)
        except ValueError:
            # capture_path is on a different drive or outside
            # the captures_root tree -- defensive, should never
            # happen for the gate's recursive glob.
            day_bucket = "(unfiled)"
        else:
            parent_parts = rel_parent.parts
            day_bucket = (
                parent_parts[0] if parent_parts else "(unfiled)"
            )
        bucket = per_day.setdefault(
            day_bucket, {"scanned": 0, "unique": 0}
        )
        bucket["scanned"] += 1
        # Increment ``unique`` only when the caller passed a
        # fingerprint mapping AND the capture's fingerprint is
        # the FIRST occurrence under its branch (i.e. it
        # contributed to coverage). Without the mapping, every
        # scanned file is treated as unique.
        if unique_per_path is not None:
            # Use the path's str() as the lookup key -- the
            # gate computes fingerprints against the same
            # ``Path`` object the gate walked.
            fp = unique_per_path.get(str(capture_path))
            if fp is not None:
                # The caller is expected to pass only the
                # FIRST-occurrence fingerprints; we increment
                # ``unique`` only when the fingerprint is
                # recorded for this path. If the same fingerprint
                # appears under multiple paths in the mapping,
                # that's a caller-side bug; we count each
                # mapped path once.
                bucket["unique"] += 1
        else:
            bucket["unique"] += 1

    return per_day


def format_per_day_table(
    per_day: dict[str, dict[str, int]],
    *,
    max_rows: int = 7,
) -> str:
    """Render ``per_day`` as a markdown table.

    Args:
        per_day: The output of ``per_day_breakdown``. Buckets
            ordered by string-sort ascending (so ``"(unfiled)"``
            floats to the top of the table when present).
        max_rows: Maximum number of rows to render. When the
            dict has more entries, the table shows the most
            recent ``max_rows - 1`` days and a ``"+ N more days"``
            footer.

    Returns:
        Markdown table text. Returns ``"_No captures scanned yet._"``
        when ``per_day`` is empty.
    """
    if not per_day:
        return "_No captures scanned yet._"

    # Sort: place "(unfiled)" first (defensive), then by date
    # ascending. We can't trust ``sorted()`` to put the most
    # recent at the bottom if dates are mixed-format, but the
    # J.3 contract pins YYYY-MM-DD format, so lex-sort == chrono.
    keys = sorted(per_day.keys(), key=lambda k: (k != "(unfiled)", k))

    # Collapse if too many.
    truncated = False
    truncated_count = 0
    if len(keys) > max_rows:
        truncated = True
        truncated_count = len(keys) - (max_rows - 1)
        keys = keys[-(max_rows - 1):]  # most-recent N-1 days

    lines = [
        "Captures bucketed by their parent directory's "
        "``YYYY-MM-DD`` date. ``Scanned`` is every JSON file "
        "under that day; ``Unique`` is the count that contributed "
        "to coverage (after J.10.DEDUP).",
        "",
        "| Date | Scanned | Unique |",
        "|---|---|---|",
    ]
    for day in keys:
        bucket = per_day[day]
        lines.append(
            f"| {day} | {bucket['scanned']} | {bucket['unique']} |"
        )
    if truncated:
        lines.append(
            f"| _(+ {truncated_count} more days, oldest first)_ "
            f"| | |"
        )

    return "\n".join(lines)


__all__ = ["per_day_breakdown", "format_per_day_table"]
