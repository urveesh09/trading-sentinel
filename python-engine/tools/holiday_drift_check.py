#!/usr/bin/env python3
"""[WORKFLOW-J.5 2026-09-13] Operator / CI CLI for the holiday-drift detector.

A thin wrapper around ``holiday_drift.holiday_drift_report`` that
exits 1 on drift so CI catches divergence; prints a human-readable
report on both pass and fail.

Usage::

    ./winvenv/Scripts/python.exe tools/holiday_drift_check.py
        # exit 0 if aligned, 1 if drift

    ./winvenv/Scripts/python.exe tools/holiday_drift_check.py --json
        # exit 0/1; emit the JSON report to stdout (no preamble)

    ./winvenv/Scripts/python.exe tools/holiday_drift_check.py \\
        --node-source path/to/fixture.js
        # point at a fixture during tests; default is the canonical
        # node-gateway/server/utils/market-hours.js

The CLI hook in ``holiday_drift.py`` itself (``python -m holiday_drift``)
also exits 1 on drift; this CLI is the operator-friendly wrapper
with ``--json`` and the canonical path argument.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable

_TOOLS_DIR = __import__("pathlib").Path(__file__).resolve().parent
_ENGINE_DIR = _TOOLS_DIR.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

import holiday_drift as _drift  # noqa: E402  -- intentional sys.path insert


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="holiday_drift_check",
        description=(
            "Static drift check between Python canonical holidays "
            "and node-gateway/server/utils/market-hours.js. "
            "Exits 0 when the two sets are equal (modulo ordering); "
            "1 on drift. Use in CI to catch node-side regressions."
        ),
    )
    p.add_argument(
        "--node-source",
        default=None,
        help=(
            "Path to the Node market-hours.js source. "
            "Default: the canonical "
            "node-gateway/server/utils/market-hours.js in this repo."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help=(
            "Emit the JSON-formatted drift report to stdout "
            "instead of the human-readable rendering. Useful "
            "for piping to jq or for an opaque CI log."
        ),
    )
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    rpt = _drift.holiday_drift_report(
        node_source_path=args.node_source or _drift._NODE_MARKET_HOURS_JS
    )
    if args.json:
        sys.stdout.write(json.dumps(rpt, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(_drift.format_drift_report(rpt) + "\n")
    return 0 if rpt["verdict"] == "ALIGNED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
