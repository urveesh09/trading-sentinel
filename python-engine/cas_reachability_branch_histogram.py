"""[WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] Per-branch-per-day capture matrix.

The J.10 SUMMARY already surfaces per-day totals across all
branches (J.10.CAPTURE_SUMMARY_AGGREGATE). That tells the
operator "evidence is concentrated on 2026-09-10". This
slice adds the per-branch dimension: "evidence is concentrated
on 2026-09-10 for CAS_MATCHING but CAS_REFERENCE_PRICE_WINDOW
never got refreshed".

The matrix is the natural complement to the per-day
histogram. Operators triaging evidence gaps can read the
matrix top-to-bottom (one branch per row) and see at a glance
which days each branch was exercised.

This module exposes two pure helpers:

    branch_per_day_breakdown(
        captures_root,
        *,
        first_occurrence_per_path=None,
    ) -> dict[str, dict[str, dict[str, int]]]
        Walk ``captures_root.rglob("*.json")`` and bucket by
        BOTH branch AND date. Returns
        ``{branch: {date: {scanned: M, unique: N}}}``.
        ``unique`` is dedup-aware (only first-occurrence per
        branch counts, matching the gate's existing semantics).

    format_branch_per_day_table(
        matrix,
        *,
        max_dates=7,
        show_unique=True,
    ) -> str
        Render the matrix as a markdown table. Rows are the
        6 required branches in canonical order; columns are
        dates ascending. Cell values are ``unique`` counts
        (or ``scanned`` if ``show_unique=False``). Empty cells
        render as ``-``. Collapses to ``max_dates`` columns
        when the matrix has more.

The gate in ``cas_reachability_gate.py`` calls the breakdown
inside ``cas_reachability_report`` (after the dedup loop, so
``first_occurrence_per_path`` reflects which captures actually
counted toward coverage). The SUMMARY gains a ``## Captures
per branch per day`` table between the per-day section and
the duplicates section.

No new dependencies. Stdlib only (``pathlib``).

NOTE on imports: this module imports ``CAS_BRANCHES_REQUIRING_EVIDENCE``
and ``_safe_phase_from_capture`` from ``cas_reachability_gate`` LAZILY,
inside the function body. The lazy import breaks the circular
dependency (``gate`` -> ``branch_histogram`` -> ``gate``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional


def _gate_constants():
    """Lazily import constants from ``cas_reachability_gate``.

    Avoids a circular import: ``cas_reachability_gate`` imports
    from this module at module load; if we imported back at
    module load, the gate's import would see a partially-
    initialised module and raise ImportError.
    """
    from cas_reachability_gate import (
        CAS_BRANCHES_REQUIRING_EVIDENCE,
        _safe_phase_from_capture,
    )
    return CAS_BRANCHES_REQUIRING_EVIDENCE, _safe_phase_from_capture


def branch_per_day_breakdown(
    captures_root: Path,
    *,
    first_occurrence_per_path: Optional[Mapping[str, str]] = None,
) -> dict[str, dict[str, dict[str, int]]]:
    """Bucket captures by branch AND date.

    Args:
        captures_root: The captures directory (per docs/j2_captures/
            README.md). Walks ``captures_root.rglob("*.json")`` and
            buckets by ``rows[0].classifier_phase`` (the J.3 schema's
            bounded phase; preserves the J.10.CLOSURE schema-bug fix)
            and the immediate-parent directory name relative to
            ``captures_root`` (the YYYY-MM-DD date).

        first_occurrence_per_path: Optional mapping from capture
            path (as a string, the ``str(capture_path)`` value the
            gate uses) to the unique fingerprint that was counted.
            When provided, ``unique`` counts only the captures whose
            fingerprint is the FIRST occurrence under its branch
            (post-J.10.DEDUP semantics). When ``None``, ``unique``
            equals ``scanned`` (pre-dedup count).

    Returns:
        ``dict[str, dict[str, dict[str, int]]]`` mapping branch to
        date to ``{"scanned": M, "unique": N}``. Every required
        branch is present as a top-level key (even if empty),
        so the shape is stable. Every date that contributed a
        capture to any branch is present as a sub-key (sorted
        on demand in ``format_branch_per_day_table``).

    The function is pure / total / never raises. A missing or
    empty directory returns an empty matrix with the 6
    required branches as top-level keys and empty per-date
    dicts.
    """
    CAS_BRANCHES_REQUIRING_EVIDENCE, _safe_phase_from_capture = (
        _gate_constants()
    )

    captures_root = Path(captures_root)
    matrix: dict[str, dict[str, dict[str, int]]] = {
        phase: {} for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }

    if not captures_root.exists():
        return matrix

    for capture_path in sorted(captures_root.rglob("*.json")):
        phase = _safe_phase_from_capture(capture_path)
        if phase is None or phase not in matrix:
            continue
        # Bucket by parent directory name (the YYYY-MM-DD).
        try:
            rel_parent = capture_path.parent.relative_to(captures_root)
        except ValueError:
            day_bucket = "(unfiled)"
        else:
            parent_parts = rel_parent.parts
            day_bucket = (
                parent_parts[0] if parent_parts else "(unfiled)"
            )
        bucket = matrix[phase].setdefault(
            day_bucket, {"scanned": 0, "unique": 0}
        )
        bucket["scanned"] += 1
        # Increment ``unique`` only when the caller passed the
        # first-occurrence mapping AND the capture's path is
        # mapped. Mirrors the dedup-aware semantics of
        # ``per_day_breakdown`` (J.10.CAPTURE_SUMMARY_AGGREGATE).
        if first_occurrence_per_path is not None:
            if str(capture_path) in first_occurrence_per_path:
                bucket["unique"] += 1
        else:
            bucket["unique"] += 1

    return matrix


def format_branch_per_day_table(
    matrix: dict[str, dict[str, dict[str, int]]],
    *,
    max_dates: int = 7,
    show_unique: bool = True,
) -> str:
    """Render the matrix as a markdown table.

    Args:
        matrix: The output of ``branch_per_day_breakdown``.
            Branches are in canonical order (CAS_BRANCHES_REQUIRING_EVIDENCE);
            dates are sorted ascending.
        max_dates: Maximum number of date columns to render. When
            the matrix has more dates, the table shows the most
            recent ``max_dates`` columns and a ``"(+ N more dates,
            oldest first)"`` footer. Operators with long histories
            get a compact view by default.
        show_unique: When True (default), each cell shows the
            ``unique`` count (post-dedup). When False, shows the
            ``scanned`` count (every file under that day,
            regardless of validity).

    Returns:
        Markdown table text. Empty cells render as ``-``.
        Branches with no captures show ``-`` across all date
        columns so the row is visually present (operators can
        see at a glance which branches have zero coverage).

    The table renders the same shape regardless of whether
    the directory is empty or has thousands of captures --
    ``## Captures per branch per day`` is always present in
    the SUMMARY when the gate runs.
    """
    # Lazy import for the canonical branch order.
    CAS_BRANCHES_REQUIRING_EVIDENCE, _ = _gate_constants()

    # Collect the union of dates across all branches.
    dates: set[str] = set()
    for per_branch in matrix.values():
        dates.update(per_branch.keys())
    # Sort: "(unfiled)" first (defensive), then date ascending.
    sorted_dates = sorted(dates, key=lambda d: (d != "(unfiled)", d))

    if not sorted_dates:
        return (
            "_No captures with a bounded phase on disk._"
        )

    # Truncate to most-recent ``max_dates`` columns.
    truncated = False
    truncated_count = 0
    if len(sorted_dates) > max_dates:
        truncated = True
        truncated_count = len(sorted_dates) - (max_dates - 1)
        sorted_dates = sorted_dates[-(max_dates - 1):]

    # Header row + alignment row.
    header = "| Branch | " + " | ".join(sorted_dates) + " |"
    align = "|---|" + "|".join(["---"] * len(sorted_dates)) + "|"

    cell_key = "unique" if show_unique else "scanned"
    lines = [
        header,
        align,
    ]
    for branch in CAS_BRANCHES_REQUIRING_EVIDENCE:
        per_branch = matrix.get(branch, {})
        cells = []
        for day in sorted_dates:
            bucket = per_branch.get(day)
            value = bucket[cell_key] if bucket else 0
            cells.append(str(value) if value else "-")
        lines.append(f"| {branch} | " + " | ".join(cells) + " |")

    if truncated:
        # A footer row spanning all date columns.
        lines.append(
            "|_(" + f"+ {truncated_count} more dates, oldest first"
            + ")_| " + "|".join([" "] * len(sorted_dates)) + " |"
        )

    return "\n".join(lines)


__all__ = ["branch_per_day_breakdown", "format_branch_per_day_table"]
