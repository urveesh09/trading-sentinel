"""[WORKFLOW-I I3 2026-09-13] Optional-AI usefulness-instrumentation CLI.

Read-only operator tooling that prints the bounded usefulness
metrics from a queue snapshot and the documented configuration
contract. The CLI runs without model requests, without
credentials, and without touching the trading control plane.

Subcommands
-----------
``print-config``
    Print the bounded configuration contract: env-var names,
    defaults, and which knobs are operator-tunable. Output is
    static text; no I/O.

``read-snapshot``
    Read a JSON snapshot file (written by another process) and
    print its contents. Used for offline operator review.

The CLI is deliberately NOT a way to invoke the model or to
mutate state. Adding such capabilities later would be a
breaking change to the §13 "must not change capital limits,
qualification or order/delivery authority" rule.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional


# The bounded config contract. Each entry documents an
# operator-tunable knob with its env-var name, default, and
# what it controls. Operators read this to know what they can
# change without breaking the §13 contract.
CONFIG_CONTRACT: List[dict[str, str]] = [
    {
        "env_var": "MINIMAX_API_KEY",
        "default": "(unset)",
        "purpose": "Credentials for the MiniMax chat-completions "
                   "endpoint. Unset -> AI_DISABLED.",
    },
    {
        "env_var": "MINIMAX_BASE_URL",
        "default": "https://api.minimax.io/v1",
        "purpose": "API base URL. Captured per-review for provenance.",
    },
    {
        "env_var": "MINIMAX_MODEL",
        "default": "MiniMax-M3",
        "purpose": "Model identifier. Captured per-review for "
                   "provenance; a future change does NOT retroactively "
                   "re-label old annotations.",
    },
    {
        "env_var": "MINIMAX_PROMPT_VERSION",
        "default": "v1",
        "purpose": "Analyst-prompt version tag. Bump when the "
                   "prompt template changes.",
    },
    {
        "env_var": "MINIMAX_REQUEST_TIMEOUT_SEC",
        "default": "45",
        "purpose": "Per-request SDK timeout (backstop on the wall).",
    },
    {
        "env_var": "MINIMAX_MAX_RETRIES",
        "default": "1",
        "purpose": "Maximum retries inside the wall.",
    },
    {
        "env_var": "MINIMAX_WALL_TIMEOUT_SEC",
        "default": "100",
        "purpose": "Wall-clock budget for one model call (thread "
                   "join). Above this the call is abandoned.",
    },
    {
        "env_var": "MINIMAX_ASYNC_REVIEW_ENABLED",
        "default": "false",
        "purpose": "Enable the bounded async review queue. "
                   "Default off; operator opt-in.",
    },
    {
        "env_var": "MINIMAX_ASYNC_REVIEW_MAX_PENDING",
        "default": "16",
        "purpose": "Maximum in-flight reviews.",
    },
    {
        "env_var": "MINIMAX_ASYNC_REVIEW_DAILY_BUDGET",
        "default": "40",
        "purpose": "Maximum model calls per UTC day.",
    },
    {
        "env_var": "MINIMAX_ASYNC_REVIEW_DEADLINE_SEC",
        "default": "90",
        "purpose": "Original-deadline budget for each review.",
    },
    {
        "env_var": "MINIMAX_UNAVAILABLE_POLICY",
        "default": "proceed",
        "purpose": "What to do when the reviewer cannot render "
                   "an opinion. 'proceed' (default) keeps the alert; "
                   "'block' refuses. Configuration, not a default.",
    },
    {
        "env_var": "MOMENTUM_MINIMAX_REJECT_POLICY",
        "default": "(unset; 'proceed')",
        "purpose": "Momentum's response to REJECT verdicts. "
                   "'block' restores a hard veto.",
    },
]


def print_config() -> int:
    """Print the bounded config contract. Exit 0 on success."""
    print("=" * 72)
    print("Optional-AI bounded configuration contract (I3 2026-09-13)")
    print("=" * 72)
    print()
    print(f"{'ENV VAR':<40} {'DEFAULT':<24} PURPOSE")
    print("-" * 120)
    for entry in CONFIG_CONTRACT:
        env = entry["env_var"]
        default = entry["default"]
        purpose = entry["purpose"]
        print(f"{env:<40} {default:<24} {purpose}")
    print()
    print("This contract is read-only -- the CLI never writes to")
    print("the runtime state. To change a knob, set the env var and")
    print("restart the agent.")
    return 0


def read_snapshot(path: str) -> int:
    """Read a JSON snapshot from ``path`` and print it. Exit 0 on
    success, 1 on I/O or parse error.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except OSError as exc:
        print(f"i/o error reading {path}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"json parse error in {path}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Optional-AI usefulness-instrumentation CLI. Read-only; "
            "does not invoke the model or mutate state."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "print-config",
        help="Print the bounded configuration contract (env vars, defaults, purpose).",
    )

    snap = subparsers.add_parser(
        "read-snapshot",
        help="Read a JSON snapshot file and print it.",
    )
    snap.add_argument("path", help="Path to the JSON snapshot file.")

    args = parser.parse_args(argv)
    if args.command == "print-config":
        return print_config()
    if args.command == "read-snapshot":
        return read_snapshot(args.path)
    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable


__all__ = ["CONFIG_CONTRACT", "main", "print_config", "read_snapshot"]


if __name__ == "__main__":
    sys.exit(main())
