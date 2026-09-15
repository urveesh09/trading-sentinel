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
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    cas_reachability_report,
    format_report,
    update_summary,
    write_report,
)
from cas_reachability_listing import (
    format_listing,
    list_captures,
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
    parser.add_argument(
        "--min-unique-per-branch",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Per-branch minimum UNIQUE capture count (per J.10.DEDUP "
            "fingerprint) for the branch to count as captured toward "
            "the REACHABLE verdict. Default: 1 (the pre-threshold "
            "behaviour). Values <= 0 are nonsensical and rejected "
            "at the CLI boundary. Use this to defend against a "
            "single flaky capture flipping the gate -- set to 2 "
            "to require corroborating evidence per branch."
        ),
    )
    parser.add_argument(
        "--list-captures",
        action="store_true",
        help=(
            "[WORKFLOW-J.10.CAPTURE_LISTING 2026-09-14] Print a "
            "structured listing of every capture on disk, grouped "
            "by branch, WITHOUT computing the verdict. This is a "
            "fast, side-effect-free audit tool -- no fingerprinting, "
            "no freshness check, no dedup. Use it to answer 'what "
            "captures exist?' without paying the cost of the "
            "full gate walk. Composes with --json (the listing is "
            "emitted as machine-readable JSON) and --captures-dir. "
            "Mutually exclusive with --status / --update-summary / "
            "--write (those are verdict-output flags). Exit code is "
            "always 0 -- the listing is informational only."
        ),
    )
    args = parser.parse_args(argv)

    # [WORKFLOW-J.10.CAPTURE_LISTING 2026-09-14] Short-circuit:
    # if the operator asked for a listing, we don't need to run
    # the freshness / dedup / threshold machinery at all. The
    # listing is a fast walk that only reads rows[0].classifier_phase.
    if args.list_captures:
        # Listing does NOT honour --captures-since / --min-unique-per-branch:
        # those are verdict filters, not listing filters. Refuse early so
        # the operator doesn't get a confusing result.
        if args.captures_since is not None:
            sys.stderr.write(
                "--list-captures does not compose with --captures-since. "
                "Listing is a side-effect-free audit tool; freshness is a "
                "verdict concern. Use the gate (without --list-captures) "
                "for freshness-filtered output.\n"
            )
            return 2
        if args.min_unique_per_branch is not None:
            sys.stderr.write(
                "--list-captures does not compose with --min-unique-per-branch. "
                "Listing is a side-effect-free audit tool; the threshold "
                "is a verdict concern.\n"
            )
            return 2
        if args.update_summary or args.write or args.status:
            sys.stderr.write(
                "--list-captures is mutually exclusive with --update-summary, "
                "--write, and --status (those are verdict-output flags). "
                "The listing does not produce a verdict or update the SUMMARY.\n"
            )
            return 2
        captures_dir = args.captures_dir or (
            _resolve_repo_root() / "docs" / "j2_captures"
        )
        # The listing tolerates a missing directory: it returns an
        # empty listing rather than raising. The operator gets a
        # clean "0 captures" report instead of an error.
        listing = list_captures(captures_dir)
        if args.json:
            sys.stdout.write(
                json.dumps(listing, indent=2, sort_keys=True)
            )
            sys.stdout.write("\n")
        else:
            sys.stdout.write(format_listing(listing))
            sys.stdout.write("\n")
        # Exit 0 always -- listing is informational.
        return 0

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

    # [WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] Forward the
    # --min-unique-per-branch flag to the gate. Values <= 0
    # would mark every branch as captured regardless of
    # evidence, which is nonsensical; rejected at the CLI.
    min_unique_per_branch: int = 1
    if args.min_unique_per_branch is not None:
        if args.min_unique_per_branch <= 0:
            sys.stderr.write(
                f"--min-unique-per-branch must be > 0, "
                f"got {args.min_unique_per_branch}\n"
            )
            return 2
        min_unique_per_branch = args.min_unique_per_branch

    report = cas_reachability_report(
        captures_dir=captures_dir,
        max_age_days=max_age_days,
        min_unique_per_branch=min_unique_per_branch,
    )
    if args.status:
        # Single-line status for shell prompts / monitoring.
        # Format: ``J.10: <VERDICT> <coverage_pct>% (<captured>/<total>
        # branches, <scanned> scanned, <skipped> skipped)``.
        # [WORKFLOW-J.10.MIN_THRESHOLD 2026-09-14] The captured
        # count must reflect the threshold, not just ``count > 0``.
        # Without this, ``--status`` would say "6/6 branches"
        # when the verdict is UNREACHABLE because of a high
        # threshold -- a confusing diagnostic for shell prompts
        # and monitoring. We compute the count from the same
        # predicate the gate used for the verdict.
        threshold = int(
            report.get("min_unique_per_branch", 1)
        )
        captured_count = sum(
            1
            for phase in CAS_BRANCHES_REQUIRING_EVIDENCE
            if report["captured_phases"].get(phase, 0) >= threshold
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
