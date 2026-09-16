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
from cas_reachability_verify import (
    DiffKind,
    VerificationReport,
    verify_summary,
)
from cas_reachability_features import (
    FEATURES_INVENTORY,
    features_inventory_as_json,
    format_features_inventory,
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
    parser.add_argument(
        "--show-branch-histogram",
        action="store_true",
        help=(
            "[WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] Print "
            "the per-branch-per-day matrix in addition to the "
            "standard verdict report. The matrix shows which "
            "branches have evidence on which days -- useful for "
            "spotting branches that never got refreshed vs "
            "branches with evidence clustered on a single day. "
            "Composes with --json (the matrix is appended to "
            "the JSON output as the ``branch_per_day`` field). "
            "The matrix is also rendered in the persistent "
            "SUMMARY.md (the gate runs the full report regardless "
            "of this flag)."
        ),
    )
    parser.add_argument(
        "--verify-summary",
        action="store_true",
        help=(
            "[WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] Render a "
            "fresh SUMMARY.md and diff it byte-for-byte against "
            "the on-disk file. Exits 0 on match OR on "
            "timestamp-only drift (a benign re-render), 1 on "
            "real body drift (manual edit / partial write), 2 "
            "on missing on-disk file. The flag NEVER overwrites "
            "the on-disk file -- use --update-summary to commit "
            "a fresh render. Useful for catching partial writes, "
            "manual edits, or stale renders between operator "
            "runs. The output distinguishes ``BYTES_DIFFER`` "
            "(body changed) from ``GENERATED_AT_DIFFER`` "
            "(only the timestamp changed -- benign). Composes "
            "with --json (emits the structured "
            "VerificationReport) and --captures-dir."
        ),
    )
    parser.add_argument(
        "--features-inventory",
        action="store_true",
        help=(
            "[WORKFLOW-C.F5 2026-09-15] Print the J.10 features "
            "inventory: every feature wired into this CLI version, "
            "the date it was added, its description, and the CLI "
            "flags that activate it. Lets operators confirm wiring "
            "without needing captures to happen (per the 2026-09-15 "
            "production audit F-5: PR #89-#92 features deployed but "
            "invisible in runtime). Side-effect free -- no captures "
            "dir is read. Composes with --json (emits the inventory "
            "as a structured JSON object). Exit code is always 0."
        ),
    )
    args = parser.parse_args(argv)

    # [WORKFLOW-C.F5 2026-09-15] Short-circuit: if the operator
    # asked for the features inventory, we don't need any
    # captures dir or verdict machinery. The inventory is a
    # constant table -- the same answer every time, no matter
    # the deployment.
    if args.features_inventory:
        if args.json:
            sys.stdout.write(features_inventory_as_json())
        else:
            sys.stdout.write(format_features_inventory())
        return 0

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
        # [WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] When
        # --verify-summary is set, the gate's JSON output is
        # suppressed so the verify-summary JSON can be emitted
        # as the sole JSON object on stdout (operators parsing
        # the output with ``json.loads`` would otherwise see
        # two concatenated objects -- invalid JSON).
        if not args.verify_summary:
            sys.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            sys.stdout.write("\n")
    else:
        sys.stdout.write(format_report(report))
        sys.stdout.write("\n")
        # [WORKFLOW-J.10.BRANCH_HISTOGRAM 2026-09-14] When
        # --show-branch-histogram is set, append the per-branch-
        # per-day matrix to the human-readable output. The JSON
        # output (--json) already includes the matrix under
        # ``branch_per_day``; the human-readable output gets the
        # matrix as a follow-up section so the operator can read
        # it without flipping to JSON.
        if args.show_branch_histogram:
            sys.stdout.write("\n")
            sys.stdout.write("Captures per branch per day:\n")
            sys.stdout.write(
                format_branch_per_day_table(
                    report.get("branch_per_day", {}),
                    max_dates=7,
                )
            )
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
    # [WORKFLOW-J.10.SUMMARY_VERIFY 2026-09-14] Drift
    # detection. Render a fresh SUMMARY and diff against the
    # on-disk file. This is a read-only check; the operator
    # commits a fresh render via --update-summary. Exit code
    # is INDEPENDENT of the gate's REACHABLE/UNREACHABLE
    # verdict -- the verify-summary check exits 0 on match,
    # 1 on drift, 2 on missing on-disk. If both --update-summary
    # and --verify-summary are set, --update-summary wins
    # (it overwrites the on-disk file, making the verify a
    # tautology). We refuse the combination at the CLI
    # boundary rather than silently committing a no-op.
    if args.verify_summary:
        if args.update_summary:
            sys.stderr.write(
                "--verify-summary is mutually exclusive with "
                "--update-summary (--update-summary overwrites "
                "the on-disk file, making --verify-summary a "
                "tautology). Run them in sequence: --verify-summary "
                "first, then --update-summary if drift is benign.\n"
            )
            return 2
        if args.summary_path is not None:
            verify_path = args.summary_path
        else:
            verify_path = captures_dir / "SUMMARY.md"
        verification = verify_summary(
            report, verify_path, captures_dir=captures_dir,
        )
        if args.json:
            sys.stdout.write(
                json.dumps(
                    {
                        "kind": verification.kind.value,
                        "on_disk_path": verification.on_disk_path,
                        "generated_at": verification.generated_at,
                        "expected_size": verification.expected_size,
                        "actual_size": verification.actual_size,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            sys.stdout.write("\n")
        else:
            sys.stdout.write(f"J.10 SUMMARY drift: {verification.kind.value}\n")
            sys.stdout.write(
                f"  expected size: {verification.expected_size} bytes\n"
            )
            if verification.on_disk_path is None:
                sys.stdout.write("  on-disk:       (missing)\n")
            else:
                sys.stdout.write(
                    f"  on-disk:       {verification.on_disk_path} "
                    f"({verification.actual_size} bytes)\n"
                )
            if verification.generated_at:
                sys.stdout.write(
                    f"  fresh render generated_at: "
                    f"{verification.generated_at}\n"
                )
        # Exit codes: 0 = match (or benign timestamp-only drift),
        # 1 = real body drift, 2 = missing. ``GENERATED_AT_DIFFER``
        # is treated as exit 0 because the body's byte content is
        # identical after stripping the timestamp line -- the
        # only difference is the freshly-rendered ``Generated at``
        # value. Operators who want a strict no-timestamp-drift
        # check can compare bytes via ``diff`` on the rendered
        # output (the JSON output includes the kind field for
        # programmatic inspection).
        if verification.kind == DiffKind.MATCH:
            return 0
        if verification.kind == DiffKind.GENERATED_AT_DIFFER:
            # Benign re-render; the body is byte-identical
            # after stripping the timestamp line. Surface a
            # warning to stderr so operators notice the on-disk
            # SUMMARY was rendered at a different moment than
            # the fresh one.
            sys.stderr.write(
                "WARNING: SUMMARY.md drift is timestamp-only "
                "(benign re-render); body is byte-identical. "
                "Run --update-summary to commit the fresh "
                "timestamp.\n"
            )
            return 0
        if verification.kind == DiffKind.ON_DISK_MISSING:
            return 2
        return 1
    # Exit 0 on REACHABLE, exit 1 on UNREACHABLE. Exit codes
    # are documented for CI / operator scripts.
    return 0 if report["verdict"] == "REACHABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
