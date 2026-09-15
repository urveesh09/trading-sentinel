#!/usr/bin/env python3
"""[WORKFLOW-J.10 / J.10.CLOSURE 2026-09-13] CAS-branch reachability check CLI.

Operator-facing tool: walk ``docs/j2_captures/`` and emit
the reachability verdict. Exit 0 if every CAS sub-window +
DERIVATIVES_CAS_ALIGNED has at least one capture (REACHABLE);
exit 1 otherwise (UNREACHABLE).

Usage:

    # Default location (relative to repo root):
    python tools/cas_reachability_check.py

    # Custom location:
    python tools/cas_reachability_check.py --captures-dir /path/to/j2_captures

    # Machine-readable JSON to stdout (no human rendering):
    python tools/cas_reachability_check.py --json

    # Write the report next to the captures directory:
    python tools/cas_reachability_check.py --write docs/j2_captures/reachability.json

    # Update the persistent operator-facing SUMMARY.md
    # (the audit surface for the gate; default path is
    # ``<repo>/docs/j2_captures/SUMMARY.md``):
    python tools/cas_reachability_check.py --update-summary

This CLI is the J.10 gate. Per plan §14, ``auction-imbalance
research is excluded`` and ``any auction-based strategy is
separate research with auction execution semantics, not an
extension of a continuous-market fill model``. J.10 ships
the gate, not a strategy. Any future auction-aware code MUST
pass this gate before shipping.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cas_reachability_gate import (
    cas_reachability_report,
    format_report,
    update_summary,
    write_report,
)


def _resolve_repo_root() -> Path:
    """Walk up from this file to find the repo root (the
    directory containing ``docs/j2_captures``).
    """
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "docs" / "j2_captures").is_dir():
            return candidate
    # Fallback: assume we are running from the engine dir.
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="J.10 CAS-branch reachability gate."
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=None,
        help="Path to docs/j2_captures/. Defaults to <repo>/docs/j2_captures.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout instead of the human-readable report.",
    )
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Write the report as JSON to this path.",
    )
    parser.add_argument(
        "--update-summary",
        action="store_true",
        help="Update the persistent operator-facing SUMMARY.md "
             "at docs/j2_captures/SUMMARY.md. Use after each "
             "capture-review pass to keep the audit surface "
             "in sync with the gate.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Override the SUMMARY.md path (defaults to "
             "<repo>/docs/j2_captures/SUMMARY.md).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Emit a single-line status (verdict + coverage_pct + "
             "captured/total branches) suitable for shell prompts, "
             "monitoring, or CI summaries. Exit code is REACHABLE (0) "
             "or UNREACHABLE (1) as usual; the line itself contains the "
             "details. Suppresses the standard human-readable report.",
    )
    parser.add_argument(
        "--captures-since",
        type=float,
        default=None,
        metavar="DAYS",
        help=(
            "Freshness filter: only count captures whose "
            "``generated_at_utc`` is within the last DAYS days. "
            "Default: no filter (every capture counts regardless "
            "of age). Captures older than the threshold are skipped "
            "and surfaced in the new ``captures_skipped_stale`` "
            "report field. Use this to answer 'is the gate "
            "REACHABLE with fresh evidence?' without manually "
            "inspecting each capture's timestamp."
        ),
    )
    args = parser.parse_args(argv)

    captures_dir = args.captures_dir or (
        _resolve_repo_root() / "docs" / "j2_captures"
    )
    if not captures_dir.exists():
        sys.stderr.write(
            f"captures directory does not exist: {captures_dir}\n"
        )
        return 2

    # [WORKFLOW-J.10.FRESHNESS 2026-09-14] Forward the
    # --captures-since flag to the gate. Negative values are
    # nonsensical (would mark every capture as stale) and are
    # rejected at the CLI boundary; the gate itself trusts the
    # value when it is a positive float.
    max_age_days: float | None = None
    if args.captures_since is not None:
        if args.captures_since <= 0:
            sys.stderr.write(
                f"--captures-since must be > 0 days, "
                f"got {args.captures_since}\n"
            )
            return 2
        max_age_days = args.captures_since

    report = cas_reachability_report(
        captures_dir=captures_dir,
        max_age_days=max_age_days,
    )
    if args.status:
        # Single-line status for shell prompts / monitoring.
        # Format: ``J.10: <VERDICT> <coverage_pct>% (<captured>/<total>
        # branches, <scanned> scanned, <skipped> skipped)``.
        captured_count = sum(
            1 for c in report["captured_phases"].values() if c > 0
        )
        total_branches = len(report["captured_phases"])
        sys.stdout.write(
            f"J.10: {report['verdict']} {report['coverage_pct']:.1f}% "
            f"({captured_count}/{total_branches} branches, "
            f"{report['captures_scanned']} scanned, "
            f"{report['captures_skipped']} skipped)\n"
        )
    elif args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(format_report(report))
        sys.stdout.write("\n")
    if args.write:
        write_report(report, out_path=args.write)
    if args.update_summary:
        # The SUMMARY.md is the persistent operator-facing surface.
        # The default path is next to the captures directory; the
        # ``--summary-path`` flag overrides for tests / power users.
        if args.summary_path is not None:
            summary_path = args.summary_path
        else:
            summary_path = captures_dir / "SUMMARY.md"
        update_summary(
            report, summary_path=summary_path, captures_dir=captures_dir,
        )
        sys.stderr.write(f"updated {summary_path}\n")
    # Exit 0 on REACHABLE, exit 1 on UNREACHABLE. Exit codes
    # are documented for CI / operator scripts.
    return 0 if report["verdict"] == "REACHABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
