#!/usr/bin/env python3
"""[WORKFLOW-J.10 2026-09-13] CAS-branch reachability check CLI.

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
    args = parser.parse_args(argv)

    captures_dir = args.captures_dir or (
        _resolve_repo_root() / "docs" / "j2_captures"
    )
    if not captures_dir.exists():
        sys.stderr.write(
            f"captures directory does not exist: {captures_dir}\n"
        )
        return 2

    report = cas_reachability_report(captures_dir=captures_dir)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(format_report(report))
        sys.stdout.write("\n")
    if args.write:
        write_report(report, out_path=args.write)
    # Exit 0 on REACHABLE, exit 1 on UNREACHABLE. Exit codes
    # are documented for CI / operator scripts.
    return 0 if report["verdict"] == "REACHABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
