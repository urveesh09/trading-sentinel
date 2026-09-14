"""[WORKFLOW-I.4.E 2026-09-14] Bounded contract-health CLI.

Read-only operator tooling that prints the bounded contract-health
report from an agent status snapshot. Runs without model calls,
without broker/network, and without touching the trading control
plane.

Subcommands
-----------
``print-config``
    Print the bounded configuration contract: the allow-list
    keys, the forbidden authority fields, and the invariants.
    Output is static text; no I/O.

``check``
    Read a JSON snapshot file (the agent's bounded status
    envelope + optional usefulness sub-envelope) and run every
    invariant. Exit 0 iff every check passed; exit 1 on any
    violation; exit 2 on I/O / parse / shape error.

``self-check``
    Run every invariant against synthetic well-formed inputs.
    A "does the harness work" smoke test; exit 0 iff every
    check passed.

The CLI is deliberately NOT a way to mutate state. Adding such
capabilities later would be a breaking change to the §13
"must not change capital limits, qualification or
order/delivery authority" rule.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, List, Optional

from contract_health import (
    ContractCheck,
    ContractReport,
    FORBIDDEN_REVIEW_DELTA_FIELDS,
    STATUS_ENVELOPE_ALLOWED_KEYS,
    USEFULNESS_ALLOWED_KEYS,
    evaluate_contract,
)


# ---------------------------------------------------------------------------
# print-config


CONFIG_CONTRACT: List[dict[str, str]] = [
    {
        "name": "STATUS_ENVELOPE_ALLOWED_KEYS",
        "default": ", ".join(sorted(STATUS_ENVELOPE_ALLOWED_KEYS)),
        "purpose": (
            "Top-level keys the agent may publish in the bounded "
            "status envelope. Any other key is a contract violation."
        ),
    },
    {
        "name": "USEFULNESS_ALLOWED_KEYS",
        "default": ", ".join(sorted(USEFULNESS_ALLOWED_KEYS)),
        "purpose": (
            "Keys allowed inside the usefulness sub-envelope. "
            "Counters only -- never review content."
        ),
    },
    {
        "name": "FORBIDDEN_REVIEW_DELTA_FIELDS",
        "default": ", ".join(sorted(FORBIDDEN_REVIEW_DELTA_FIELDS)),
        "purpose": (
            "Fields a Review MUST NOT carry. The verdict is "
            "informational only and may never grant authority."
        ),
    },
    {
        "name": "CONFIDENCE_THRESHOLD",
        "default": "0.6",
        "purpose": (
            "Classifier fail-closed threshold. A ClassificationResult "
            "below this MUST map to UNKNOWN."
        ),
    },
    {
        "name": "RATIONALE_MAX_CHARS",
        "default": "280",
        "purpose": (
            "Bounded rationale length. Anything longer is a contract "
            "violation (the rationale must never be the prompt)."
        ),
    },
]


def print_config() -> int:
    """Print the bounded config contract. Exit 0 on success."""
    print("=" * 72)
    print("Contract-health bounded configuration contract (I.4.E 2026-09-14)")
    print("=" * 72)
    print()
    print(f"{'NAME':<36} {'DEFAULT':<60} PURPOSE")
    print("-" * 120)
    for entry in CONFIG_CONTRACT:
        # Wrap the default across lines if needed.
        default = entry["default"]
        if len(default) > 58:
            # Render as a comma-joined multi-line block in a single cell.
            chunks = [
                default[i : i + 58] for i in range(0, len(default), 58)
            ]
            for i, chunk in enumerate(chunks):
                label = entry["name"] if i == 0 else ""
                purpose = entry["purpose"] if i == 0 else ""
                print(f"{label:<36} {chunk:<60} {purpose}")
        else:
            print(
                f"{entry['name']:<36} {default:<60} {entry['purpose']}"
            )
    print()
    print("This contract is read-only -- the CLI never writes to")
    print("runtime state. To change a knob, edit agent/contract_health.py")
    print("and restart the agent.")
    return 0


# ---------------------------------------------------------------------------
# check


def _load_snapshot(path: str) -> tuple[int, Optional[dict[str, Any]]]:
    """Read + parse a JSON snapshot from ``path``.

    Returns ``(exit_code, payload)``. Exit code 0 on success,
    2 on I/O / parse / shape error (with a structured diagnostic
    written to stderr).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except OSError as exc:
        print(f"i/o error reading {path}: {exc}", file=sys.stderr)
        return 2, None
    except json.JSONDecodeError as exc:
        print(f"json parse error in {path}: {exc}", file=sys.stderr)
        return 2, None
    if not isinstance(payload, dict):
        print(
            f"snapshot root must be a dict, got {type(payload).__name__}",
            file=sys.stderr,
        )
        return 2, None
    return 0, payload


def _format_report(report: ContractReport) -> str:
    """Render a ContractReport as a deterministic operator-readable string."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(
        f"Contract health report ({report.schema_version}) -- "
        f"{'PASS' if report.passed else 'FAIL'}"
    )
    lines.append(
        f"Evaluated at: {report.evaluated_at.isoformat()}"
    )
    lines.append("=" * 72)
    for c in report.checks:
        marker = "PASS" if c.passed else "FAIL"
        lines.append(f"[{marker}] {c.name}")
        for k, v in sorted(c.observed.items()):
            lines.append(f"    observed.{k} = {v!r}")
        for v in c.violations:
            lines.append(f"    violation: {v}")
    lines.append("-" * 72)
    if not report.passed:
        flat = report.violations()
        lines.append(f"{len(flat)} violation(s):")
        for v in flat:
            lines.append(f"  - {v}")
    else:
        lines.append("All 5 bounded invariants passed.")
    return "\n".join(lines)


def check_snapshot(snapshot: dict[str, Any]) -> ContractReport:
    """Run every invariant against a loaded snapshot dict.

    The snapshot is expected to carry the bounded status envelope
    at the top level (and may carry a ``usefulness`` sub-envelope).
    Reviews / classifications are not expected in a persisted
    snapshot (they never cross the agent->engine bridge); if they
    are present they are honoured.
    """
    return evaluate_contract(
        status_envelope=snapshot,
        usefulness_snapshot=snapshot,
        classifications=snapshot.get("classifications"),
        reviews=snapshot.get("reviews"),
    )


def run_check(path: str) -> int:
    """CLI subcommand: ``check <path>``."""
    rc, snapshot = _load_snapshot(path)
    if rc != 0:
        return rc
    assert snapshot is not None  # rc==0 guarantees this
    report = check_snapshot(snapshot)
    print(_format_report(report))
    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# self-check


def _well_formed_snapshot() -> dict[str, Any]:
    """A synthetic, well-formed status envelope + usefulness sub-envelope.

    Used by the ``self-check`` subcommand to verify the harness
    itself works without requiring an operator-supplied snapshot.
    """
    return {
        "state": "READY",
        "queue_size": 0,
        "in_flight": 0,
        "circuit_open": False,
        "last_completed_at": "2026-09-14T10:00:00+00:00",
        "usefulness": {
            "verdict_counts": {"approve": 5, "reject": 1},
            "cache_hits": 12,
            "cache_misses": 3,
            "circuit_opens": 0,
            "response_seconds_mean": 1.5,
            "response_seconds_p95": 2.4,
            "last_response_seconds": 1.2,
            "last_completed_at": "2026-09-14T10:00:00+00:00",
            "snapshot_at": "2026-09-14T10:00:01+00:00",
        },
    }


def run_self_check() -> int:
    """CLI subcommand: ``self-check``.

    Runs every invariant against synthetic well-formed inputs.
    A "does the harness work" smoke test; exit 0 iff every check
    passed.
    """
    snapshot = _well_formed_snapshot()
    report = check_snapshot(snapshot)
    print(_format_report(report))
    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# main


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Contract-health self-evaluation CLI. Read-only; does "
            "not invoke the model or mutate state."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "print-config",
        help=(
            "Print the bounded configuration contract (allow-lists, "
            "forbidden fields, invariants)."
        ),
    )

    check_p = subparsers.add_parser(
        "check",
        help=(
            "Read a JSON snapshot file and run every invariant. "
            "Exit 0 iff every check passed."
        ),
    )
    check_p.add_argument(
        "path", help="Path to the JSON snapshot file."
    )

    subparsers.add_parser(
        "self-check",
        help=(
            "Run every invariant against synthetic well-formed inputs. "
            "A harness smoke test; exit 0 iff every check passed."
        ),
    )

    args = parser.parse_args(argv)
    if args.command == "print-config":
        return print_config()
    if args.command == "check":
        return run_check(args.path)
    if args.command == "self-check":
        return run_self_check()
    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable


__all__ = [
    "CONFIG_CONTRACT",
    "print_config",
    "check_snapshot",
    "run_check",
    "run_self_check",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
