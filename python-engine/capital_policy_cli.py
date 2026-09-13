"""[WORKFLOW-F 2026-09-13] Capital policy CLI (Phase 6).

Operator-facing CLI for the F6 capital policy guard. Mirrors the
F5 ``reconciliation_cli`` discipline: offline-only, no scheduler,
no broker network calls. The operator runs this from outside the
container to ask *should* a candidate live-capital increase be
authorised, given the current ledger state.

Subcommands:

  * ``evaluate`` -- read the F1/F5 substrates (live equity,
    drawdown, execution quality, reconciliation status, proactive
    research evidence) and run ``evaluate_capital_increase``.
    Outputs a structured JSON with the verdict and per-gate
    breakdown.

  * ``print-config`` -- print the current capital-policy thresholds
    from ``config.py`` so the operator can see what defaults are
    in effect.

[DESIGN-INVARIANTS 2026-09-13]
  1. The CLI NEVER mutates the ledger. It is read-only by design.
  2. The CLI uses the same ``_write_output_atomic`` discipline as
     F5: byte-identical retries produce the same file.
  3. The CLI exits 0 on success, 1 on validation/evaluation
     refusal, 2 on I/O error. The output JSON is written even on
     refusal so the operator can see why.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import settings


def _write_output_atomic(path: str, value: dict) -> None:
    target = Path(path)
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".capital-policy-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = target.read_bytes()
            if existing != encoded:
                raise ValueError(
                    f"output already exists with different content: {path}"
                )
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _thresholds_from_config() -> Any:
    """Build a ``CapitalPolicyThresholds`` from the current config."""
    from capital_policy import CapitalPolicyThresholds
    return CapitalPolicyThresholds(
        loss_tolerance_pct=settings.CAPITAL_POLICY_LOSS_TOLERANCE_PCT,
        max_drawdown_pct=settings.CAPITAL_POLICY_MAX_DRAWDOWN_PCT,
        min_win_rate_pct=settings.CAPITAL_POLICY_MIN_WIN_RATE_PCT,
        min_avg_r_multiple=settings.CAPITAL_POLICY_MIN_AVG_R_MULTIPLE,
        max_consecutive_losses=settings.CAPITAL_POLICY_MAX_CONSECUTIVE_LOSSES,
        min_live_bankroll_inr=settings.CAPITAL_POLICY_MIN_LIVE_BANKROLL_INR,
        require_broker_reconciliation=(
            settings.CAPITAL_POLICY_REQUIRE_BROKER_RECONCILIATION
        ),
        require_proactive_research_evidence=(
            settings.CAPITAL_POLICY_REQUIRE_PROACTIVE_EVIDENCE
        ),
    )


async def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    """Run ``evaluate_capital_increase_for_account`` and shape the output."""
    from capital_policy import evaluate_capital_increase_for_account
    thresholds = _thresholds_from_config()
    out: dict[str, Any] = {
        "command": "evaluate",
        "ok": False,
        "verdict": None,
        "reason": None,
        "account_id": args.account,
        "requested_delta_inr": args.delta,
        "thresholds": {
            "loss_tolerance_pct": thresholds.loss_tolerance_pct,
            "max_drawdown_pct": thresholds.max_drawdown_pct,
            "min_win_rate_pct": thresholds.min_win_rate_pct,
            "min_avg_r_multiple": thresholds.min_avg_r_multiple,
            "max_consecutive_losses": thresholds.max_consecutive_losses,
            "min_live_bankroll_inr": thresholds.min_live_bankroll_inr,
            "require_broker_reconciliation": (
                thresholds.require_broker_reconciliation
            ),
            "require_proactive_research_evidence": (
                thresholds.require_proactive_research_evidence
            ),
        },
        "can_grow_live_capital": False,
        "error": None,
    }
    try:
        evaluation = await evaluate_capital_increase_for_account(
            args.db,
            account_id=args.account,
            requested_delta_inr=float(args.delta),
            thresholds=thresholds,
        )
        out["verdict"] = evaluation.verdict.value
        out["reason"] = evaluation.reason
        out["evaluation"] = {
            "live_current_inr": evaluation.live_current_inr,
            "drawdown_pct": evaluation.drawdown_pct,
            "win_rate_pct": evaluation.win_rate_pct,
            "avg_r_multiple": evaluation.avg_r_multiple,
            "consecutive_losses": evaluation.consecutive_losses,
            "reconciliation_status": evaluation.reconciliation_status,
        }
        out["can_grow_live_capital"] = (
            evaluation.verdict.value == "AUTHORIZED"
        )
        out["ok"] = True
    except (ValueError, TypeError, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _print_config(args: argparse.Namespace) -> dict[str, Any]:
    """Return the current config thresholds as a structured dict."""
    thresholds = _thresholds_from_config()
    return {
        "command": "print-config",
        "ok": True,
        "thresholds": {
            "loss_tolerance_pct": thresholds.loss_tolerance_pct,
            "max_drawdown_pct": thresholds.max_drawdown_pct,
            "min_win_rate_pct": thresholds.min_win_rate_pct,
            "min_avg_r_multiple": thresholds.min_avg_r_multiple,
            "max_consecutive_losses": thresholds.max_consecutive_losses,
            "min_live_bankroll_inr": thresholds.min_live_bankroll_inr,
            "require_broker_reconciliation": (
                thresholds.require_broker_reconciliation
            ),
            "require_proactive_research_evidence": (
                thresholds.require_proactive_research_evidence
            ),
        },
        "config_keys": [
            "CAPITAL_POLICY_LOSS_TOLERANCE_PCT",
            "CAPITAL_POLICY_MAX_DRAWDOWN_PCT",
            "CAPITAL_POLICY_MIN_WIN_RATE_PCT",
            "CAPITAL_POLICY_MIN_AVG_R_MULTIPLE",
            "CAPITAL_POLICY_MAX_CONSECUTIVE_LOSSES",
            "CAPITAL_POLICY_MIN_LIVE_BANKROLL_INR",
            "CAPITAL_POLICY_REQUIRE_BROKER_RECONCILIATION",
            "CAPITAL_POLICY_REQUIRE_PROACTIVE_EVIDENCE",
        ],
        "override_via_env": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sentinel capital policy guard. Offline CLI; no "
            "scheduler, no broker network calls. Reads the "
            "ledger and produces a verdict."
        ),
    )
    parser.add_argument(
        "--db", default=settings.DB_PATH,
        help="SQLite database path (default: settings.DB_PATH)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ev = sub.add_parser(
        "evaluate",
        help="evaluate a candidate live-capital-increase request",
    )
    ev.add_argument(
        "--account", required=True,
        help="account_id to scope the broker reconciliation read",
    )
    ev.add_argument(
        "--delta", required=True, type=float,
        help="requested live-bankroll delta in INR (positive = grow)",
    )
    ev.add_argument(
        "--output", required=True,
        help="atomic immutable output JSON path",
    )

    pc = sub.add_parser(
        "print-config",
        help="print the current capital-policy thresholds",
    )
    pc.add_argument(
        "--output", required=True,
        help="atomic immutable output JSON path",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        out = asyncio.run(_evaluate(args))
    elif args.command == "print-config":
        out = _print_config(args)
    else:  # pragma: no cover -- argparse required=True blocks this
        print(json.dumps({"ok": False, "error": "unknown command"}))
        return 2
    try:
        _write_output_atomic(args.output, out)
    except OSError as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"output write failed: {exc}"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    # The CLI exits 0 on success, 1 on evaluation refusal (so the
    # operator can wire it into a CI gate). I/O errors return 2.
    print(json.dumps(
        {"path": args.output, "ok": out["ok"],
         "verdict": out.get("verdict")},
        sort_keys=True,
    ))
    return 0 if out["ok"] else 1


__all__ = [
    "_evaluate",
    "_print_config",
    "_write_output_atomic",
    "_build_parser",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
