"""[WORKFLOW-J.10.CAPTURE_LISTING 2026-09-14] Lightweight capture listing.

The full ``cas_reachability_report`` walk does fingerprinting,
freshness checks, dedup logic, and per-day aggregation. An
operator asking "what captures exist on disk?" doesn't need
any of that -- they want a fast, side-effect-free listing.

This module exposes ``list_captures(captures_root)``:
  - walks ``captures_root.rglob("*.json")``,
  - reads each capture's ``rows[0].classifier_phase`` (the J.3
    schema -- same source of truth the gate reads; preserves the
    J.10.CLOSURE schema-bug fix),
  - skips malformed / non-bounded captures (same contract as
    the gate's ``captures_skipped``),
  - returns a structured dict with per-branch lists of
    relative paths and a top-level summary.

Pure / total / never raises. No model calls. No filesystem
mutation. The helper is importable in isolation; the CLI uses
it for the ``--list-captures`` flag.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cas_reachability_gate import (
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    _safe_phase_from_capture,
)


def list_captures(captures_root: Path) -> dict[str, Any]:
    """Walk ``captures_root`` and return a structured listing.

    Args:
        captures_root: The captures directory (per docs/j2_captures/
            README.md). Walks ``captures_root.rglob("*.json")`` and
            groups by ``rows[0].classifier_phase``.

    Returns:
        ``dict[str, Any]`` with:
          - ``schema_version`` (pinned ``"i10-capture-listing-v1"``)
          - ``captures_root`` (resolved absolute path)
          - ``total_captures`` (every .json file in the tree)
          - ``listed_captures`` (count of files that contributed to
            a branch -- the rest are ``skipped_captures``)
          - ``skipped_captures`` (count of malformed / non-bounded)
          - ``branches_with_captures`` (count of branches with
            ``len(captures[branch]) >= 1``)
          - ``captures``: ``dict[str, list[str]]`` mapping each of
            ``CAS_BRANCHES_REQUIRING_EVIDENCE`` to a SORTED list
            of relative paths (relative to ``captures_root``,
            normalised to forward slashes for cross-platform
            consistency). Branches with zero captures map to
            ``[]`` so the shape is stable across empty and
            non-empty cases.

    The function is pure / total / never raises. Missing or
    empty directories return an empty listing with
    ``total_captures=0``.
    """
    captures_root = Path(captures_root)
    listing: dict[str, list[str]] = {
        phase: [] for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
    }
    total_captures = 0
    listed_captures = 0
    skipped_captures = 0

    if not captures_root.exists():
        return {
            "schema_version": "i10-capture-listing-v1",
            "captures_root": str(captures_root),
            "total_captures": 0,
            "listed_captures": 0,
            "skipped_captures": 0,
            "branches_with_captures": 0,
            "captures": listing,
        }

    for capture_path in sorted(captures_root.rglob("*.json")):
        total_captures += 1
        phase = _safe_phase_from_capture(capture_path)
        if phase is None:
            skipped_captures += 1
            continue
        if phase in listing:
            listed_captures += 1
            try:
                rel = capture_path.relative_to(captures_root)
            except ValueError:
                rel = capture_path
            # Normalise to forward slashes so the JSON output
            # is identical on Windows and POSIX. Python's
            # ``Path.relative_to`` returns paths with the OS
            # separator (``\\`` on Windows); downstream
            # consumers expect the JSON-canonical forward
            # slash. The gate's ``cas_reachability_report``
            # does NOT normalise today; this helper does, as
            # a fresh audit-tool contract.
            listing[phase].append(str(rel).replace(os.sep, "/"))

    # Sort each branch's paths for deterministic output.
    for phase in listing:
        listing[phase] = sorted(listing[phase])

    branches_with_captures = sum(
        1 for paths in listing.values() if paths
    )
    return {
        "schema_version": "i10-capture-listing-v1",
        "captures_root": str(captures_root),
        "total_captures": total_captures,
        "listed_captures": listed_captures,
        "skipped_captures": skipped_captures,
        "branches_with_captures": branches_with_captures,
        "captures": listing,
    }


def format_listing(listing: dict[str, Any]) -> str:
    """Render a listing as a deterministic human-readable string.

    The format mirrors the gate's ``format_report`` style so
    operators can pattern-match: branches listed in the same
    order as the gate, missing branches prefixed with ``[ ]``,
    non-missing branches prefixed with the path count.
    """
    lines = [
        f"J.10 CAS capture listing -- {listing['captures_root']}",
        f"  total JSON files:   {listing['total_captures']}",
        f"  listed (valid):     {listing['listed_captures']}",
        f"  skipped (invalid):  {listing['skipped_captures']}",
        f"  branches with captures: "
        f"{listing['branches_with_captures']}/"
        f"{len(listing['captures'])}",
        "",
        "Captures per branch:",
    ]
    for phase, paths in listing["captures"].items():
        if not paths:
            lines.append(f"  [ ] {phase} (no captures yet)")
            continue
        lines.append(f"  [+] {phase} ({len(paths)} capture(s)):")
        for p in paths:
            lines.append(f"      - {p}")
    return "\n".join(lines)


__all__ = ["list_captures", "format_listing"]
