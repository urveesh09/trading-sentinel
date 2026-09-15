"""[WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14] Per-branch recency.

The J.10 SUMMARY surfaces counts (captures per branch, per day,
per branch-per-day) but not the **timestamp range** of evidence.
A branch with 4 captures all on the same day looks identical
to a branch with 4 captures spread across 4 days -- but those
are different risk profiles. Operators need the timestamp range
to spot:
  - Branches whose evidence is concentrated on a single day
    (suspicious -- one CAS observation doesn't establish the
    behaviour holds across market conditions).
  - Branches whose newest capture is weeks old (stale evidence;
    the operator hasn't refreshed the broker-behaviour probe
    recently).
  - Branches with a wide span (good coverage velocity).

This module exposes ``oldest_newest_per_branch``:
  - Walks the captures root, parses the J.3 capture schema.
  - For each branch with >=1 first-occurrence capture (per the
    dedup discipline), records the oldest and newest
    observation_at_utc timestamps plus the backing paths.
  - Returns a structured dict the gate extends the report
    with and the SUMMARY renders under
    ``## Captures recency per branch``.

The helper is pure / total: never raises, returns an empty
``{branch: {}}`` for branches with no first-occurrence evidence,
and returns ``{}`` for the whole dict when the captures root is
missing / has no JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_observation_at_utc(capture_path: Path) -> str | None:
    """Pull ``observation_at_utc`` out of a J.3 capture.

    Defensive: a missing / corrupt capture returns ``None``
    rather than raising. The caller (the gate's main loop)
    treats ``None`` as a skip, so we preserve that contract.
    """
    try:
        doc = json.loads(capture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    val = doc.get("observation_at_utc")
    if not isinstance(val, str) or not val:
        return None
    return val


def _safe_phase_from_recency(capture_path: Path) -> str | None:
    """Read the bounded phase from a J.3 capture.

    Mirrors the gate's ``_safe_phase_from_capture`` discipline
    (schema-bug fix: iterate ``rows[]`` and read
    ``rows[0].classifier_phase``). Returns ``None`` for
    malformed / non-bounded captures.
    """
    try:
        doc = json.loads(capture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    rows = doc.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    first_row = rows[0]
    if not isinstance(first_row, dict):
        return None
    phase = first_row.get("classifier_phase")
    if not isinstance(phase, str) or not phase:
        return None
    return phase


def _span_days(oldest_iso: str, newest_iso: str) -> int:
    """Compute the day-span between two ISO timestamps.

    Returns 0 if both timestamps are on the same day, 1 if
    they straddle a day boundary. Negative spans (newest
    < oldest, indicating malformed data) are clamped to 0
    rather than returning a negative -- ``span_days`` is a
    coverage-velocity signal, not a duration invariant.

    The function tolerates the ``+00:00`` suffix used by
    the J.3 probe (``observation_at_utc`` is always UTC).
    """
    # ISO timestamps parse best-effort; malformed pairs
    # fall back to 0 rather than raising.
    try:
        oldest = oldest_iso.split("+")[0].split("Z")[0]
        newest = newest_iso.split("+")[0].split("Z")[0]
        # Date is the first 10 chars (YYYY-MM-DD).
        if oldest[:10] == newest[:10]:
            return 0
        # Parse the dates and subtract. Use datetime to avoid
        # pulling in ``dateutil`` for what's a stdlib operation.
        from datetime import date
        o = date.fromisoformat(oldest[:10])
        n = date.fromisoformat(newest[:10])
        delta = (n - o).days
        return max(0, int(delta))
    except (ValueError, IndexError):
        return 0


def oldest_newest_per_branch(
    captures_root: Path,
    *,
    first_occurrence_paths: set[str] | None = None,
) -> dict[str, dict[str, str | int]]:
    """Walk the captures root and produce per-branch recency.

    Args:
        captures_root: The directory to walk recursively.
        first_occurrence_paths: Optional set of path strings
            that were recorded as FIRST occurrences under their
            branch during the gate's dedup loop. When provided,
            the helper restricts the recency to those paths
            only (matching the dedup discipline -- redundant
            duplicates don't contribute to the verdict, so
            they don't contribute to recency either). When
            ``None``, every JSON file under the root is
            considered.

    Returns:
        A dict keyed by branch (the bounded classifier phase).
        Each value is a dict with:
          - ``oldest``: ISO timestamp of the oldest first-
            occurrence capture for this branch.
          - ``newest``: ISO timestamp of the newest first-
            occurrence capture for this branch.
          - ``oldest_path``: The capture path that backed
            ``oldest`` (relative to ``captures_root`` when
            possible; absolute fallback).
          - ``newest_path``: The capture path that backed
            ``newest`` (same convention).
          - ``span_days``: ``(newest - oldest)`` rounded to
            whole days (>=0).

        Branches with no first-occurrence evidence appear in
        the dict with ``{}`` -- so the SUMMARY can render a
        consistent row count without having to check the
        captured_phases dict separately.

    The function NEVER raises. A missing captures_root,
    unreadable file, or schema deviation all degrade to "no
    evidence for that branch".
    """
    captures_root = Path(captures_root)
    if not captures_root.exists():
        return {}

    # ``recency[branch]`` accumulates (iso, path_str) tuples
    # during the walk; we pick the min and max ISO at the end
    # via str comparison (ISO 8601 with consistent TZ is
    # lexicographic-monotonic).
    recency: dict[str, list[tuple[str, str]]] = {}

    for capture_path in sorted(captures_root.rglob("*.json")):
        # [WORKFLOW-J.10.CAPTURE_OLDEST_NEWEST 2026-09-14]
        # When ``first_occurrence_paths`` is provided, restrict
        # to those paths. The gate's main loop has already
        # classified each path as first-occurrence or duplicate.
        path_key = str(capture_path)
        if (
            first_occurrence_paths is not None
            and path_key not in first_occurrence_paths
        ):
            continue
        # [WORKFLOW-J.10.SCHEMA-BUG-FIX 2026-09-14] The J.3
        # schema stores the bounded phase at
        # ``rows[0].classifier_phase``, NOT at the top-level
        # ``classifier.phase`` (which doesn't exist in the
        # v2 schema). Mirror the gate's fix.
        phase = _safe_phase_from_recency(capture_path)
        if phase is None:
            continue
        iso = _safe_observation_at_utc(capture_path)
        if iso is None:
            continue
        # Relative path so the SUMMARY is portable. Absolute
        # path is a defensive fallback when the capture lives
        # outside ``captures_root`` (uncommon but defensive).
        try:
            rel = capture_path.relative_to(captures_root)
            rel_str = str(rel)
        except ValueError:
            rel_str = str(capture_path)
        recency.setdefault(phase, []).append((iso, rel_str))

    # Reduce to oldest/newest per branch. ISO 8601 strings
    # with a consistent TZ (the J.3 probe always emits
    # ``+00:00``) are lexicographic-monotonic, so min/max on
    # the string is correct.
    out: dict[str, dict[str, str | int]] = {}
    for branch, entries in recency.items():
        if not entries:
            out[branch] = {}
            continue
        # ``min`` / ``max`` on ISO strings works because the
        # probe always emits ``YYYY-MM-DDTHH:MM:SS.ssssss+00:00``
        # and we strip the trailing newline before sorting.
        oldest_iso, oldest_path = min(entries, key=lambda x: x[0])
        newest_iso, newest_path = max(entries, key=lambda x: x[0])
        out[branch] = {
            "oldest": oldest_iso,
            "newest": newest_iso,
            "oldest_path": oldest_path,
            "newest_path": newest_path,
            "span_days": _span_days(oldest_iso, newest_iso),
        }
    return out


def format_recency_table(
    recency: dict[str, dict[str, str | int]],
) -> str:
    """Render the recency dict as a markdown table.

    The output is a markdown table with columns:
        | Branch | Oldest | Newest | Span (days) | Oldest path | Newest path |

    Branches with no recency evidence render as
    ``| BRANCH | (no evidence) | ... |``. The full table is
    wrapped in a section header so the SUMMARY can drop it
    into the doc with a single ``.format`` call.

    The function NEVER raises. Empty input renders a
    "no recency data" line.
    """
    if not recency:
        return "_No recency data available._\n"
    lines: list[str] = [
        "| Branch | Oldest | Newest | Span (days) | Oldest path | Newest path |",
        "|---|---|---|---|---|---|",
    ]
    # Stable iteration order: branches sorted by name. This
    # matches the dedup / branch-per-day helpers (sorted by
    # CAS_BRANCHES_REQUIRING_EVIDENCE when present).
    for branch in sorted(recency.keys()):
        entry = recency[branch]
        if not entry:
            lines.append(
                f"| {branch} | (no evidence) | - | - | - | - |"
            )
            continue
        lines.append(
            "| "
            + " | ".join([
                branch,
                str(entry.get("oldest", "-")),
                str(entry.get("newest", "-")),
                str(entry.get("span_days", "-")),
                str(entry.get("oldest_path", "-")),
                str(entry.get("newest_path", "-")),
            ])
            + " |"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "oldest_newest_per_branch",
    "format_recency_table",
]
