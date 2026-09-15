"""[WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] Per-branch minimum-captures threshold.

The J.10 gate's verdict is "REACHABLE when every branch has
>= 1 capture". That threshold was right when the only failure
mode was "no evidence at all". After J.10.DEDUP and
J.10.FRESHNESS, a single unique fresh capture is enough to
flip a branch to "captured".

A single flaky capture is a real failure mode:
  - A probe that crashed mid-write but left a valid-looking
    JSON file
  - A timestamp that's accidentally the right minute (e.g.
    15:30:00 IST) but a different day
  - An operator who reviewed a capture without actually
    observing the corresponding CAS sub-window

This module exposes one pure helper:

    meets_min_unique_threshold(branch_captures, min_unique)
        Returns ``True`` when ``branch_captures`` has at
        least ``min_unique`` entries. The caller passes the
        list of unique fingerprints for one branch (from the
        existing ``fingerprints_by_branch`` dict). Pure / total
        / never raises.

The gate in ``cas_reachability_gate.py`` accepts a new
``min_unique_per_branch`` kwarg (default 1, preserving the
pre-threshold behaviour). When >1, the per-branch count is
the number of UNIQUE fingerprints (not files-on-disk --
J.10.DEDUP semantics), and ``captured_phases[phase]`` only
counts toward the REACHABLE threshold when the unique count
meets the threshold.

No new dependencies. Stdlib only.
"""
from __future__ import annotations

from typing import Iterable


def meets_min_unique_threshold(
    branch_unique: Iterable[str], min_unique: int
) -> bool:
    """Return ``True`` when ``branch_unique`` has >= ``min_unique`` entries.

    Args:
        branch_unique: An iterable of unique fingerprints (or any
            other "is one observation" identifier) for a single
            branch. Order doesn't matter -- ``len(set(...))`` is
            the canonical operation.
        min_unique: The minimum number of unique observations
            required. Must be >= 1; values <= 0 would mark every
            branch as captured regardless of evidence, which is
            nonsensical. Callers should validate this at their
            own boundary (the CLI rejects ``--min-unique-per-branch
            <= 0`` with exit 2).

    Returns:
        ``True`` when the count of unique entries meets the
        threshold. ``False`` otherwise. Pure and total.
    """
    return len(set(branch_unique)) >= min_unique


__all__ = ["meets_min_unique_threshold"]
