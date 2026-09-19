#!/usr/bin/env python3
"""[WORKFLOW-E.1 2026-09-17] Partner readiness diagnostic.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Checklist for meaningful delivery: saved intraday
> profile, current index inputs, valid candidate, genuine
> compatible qualification, configured destination/token,
> transport test, final dispatch/session gates. Diagnose
> each separately. Never require partner positions for a
> general market setup.

This script is the bounded dev-side diagnostic for E.1.
It walks the 7 checklist items INDEPENDENTLY and reports
the status of each, with the operator-actionable next
step for every FAIL.

Why this matters: when a partner is "not receiving
messages", the cause is ambiguous -- is it config,
readiness evidence, transport, or session gates? This
diagnostic reports each axis so the operator can
attribute the failure to one specific subsystem.

The script is READ-ONLY: never mutates state, never sends
Telegram messages, never places orders. Operators run it
locally (or on prod read-only) to get a structured report.

Usage:
    # Default: prints human-readable checklist.
    python scripts/check_partner_readiness.py

    # JSON output for piping into the audit pipeline.
    python scripts/check_partner_readiness.py --json

    # With the readiness DB (reads partner_hedge_service_state
    # + phase3 evidence counts).
    python scripts/check_partner_readiness.py \
        --db-path /data/cache.db

    # Exit code 0 (all PASS), 1 (any FAIL), 2 (any BLOCKER).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "python-engine"


class Status(str, enum.Enum):
    """Per-checklist-item status. Operators act on these."""
    PASS = "PASS"        # Item is configured AND verified.
    WARN = "WARN"        # Item is configured but has a soft gap.
    FAIL = "FAIL"        # Item is missing or broken. Cannot dispatch.
    BLOCKER = "BLOCKER"  # Operator must take action (e.g. staging_days).

    def exit_code(self) -> int:
        """Map status to exit code for the CLI."""
        if self == Status.BLOCKER:
            return 2
        if self == Status.FAIL:
            return 1
        return 0


@dataclasses.dataclass(frozen=True)
class ChecklistItem:
    """One row of the partner-readiness diagnostic.

    Attributes:
        name: short identifier (e.g. ``transport_test``).
        title: human-readable label.
        status: PASS / WARN / FAIL / BLOCKER.
        detail: human-readable explanation.
        next_step: what the operator should do to move it to PASS.
        evidence: optional machine-readable payload (table counts,
            env-var values, db row contents) for the JSON output.
    """
    name: str
    title: str
    status: Status
    detail: str
    next_step: str
    evidence: dict[str, Any] = dataclasses.field(default_factory=dict)


def _check_intraday_profile(engine_dir: Path) -> ChecklistItem:
    """Check 1: saved intraday profile.

    The partner manual advisory uses a saved intraday
    profile (entry/exit windows, quote age, etc.). If
    ``partner_manual_advisory.py`` raises at import time
    because of a missing profile, the partner informer
    silently skips every tick.
    """
    profile_path = engine_dir / "partner_intraday_profile.json"
    if profile_path.is_file():
        try:
            import json as _json
            data = _json.loads(profile_path.read_text())
            return ChecklistItem(
                name="saved_intraday_profile",
                title="Saved intraday profile",
                status=Status.PASS,
                detail=f"Profile file present: {profile_path}",
                next_step="No action needed.",
                evidence={"path": str(profile_path),
                           "keys": list(data.keys())[:10]},
            )
        except Exception as exc:
            return ChecklistItem(
                name="saved_intraday_profile",
                title="Saved intraday profile",
                status=Status.FAIL,
                detail=f"Profile file present but invalid: {exc}",
                next_step=(
                    "Re-save the intraday profile: 'python "
                    "python-engine/partner_manual_advisory.py "
                    "--save-profile'. The JSON must be valid."
                ),
                evidence={"path": str(profile_path)},
            )
    return ChecklistItem(
        name="saved_intraday_profile",
        title="Saved intraday profile",
        status=Status.WARN,
        detail=(
            "No partner_intraday_profile.json found. The "
            "manual advisory uses sane defaults from "
            "config.PARTNER_* if the file is absent, but the "
            "audit cannot verify which window/quote-age the "
            "partner is using."
        ),
        next_step=(
            "Optional: run 'python "
            "python-engine/partner_manual_advisory.py "
            "--save-profile' to capture the current profile."
        ),
        evidence={"path": str(profile_path)},
    )


def _check_index_inputs(engine_dir: Path) -> ChecklistItem:
    """Check 2: current index inputs.

    The partner informer needs the NIFTY + SENSEX intraday
    inputs (LTP, IV, PCR) to evaluate. We check the
    ``partner_advisory_input_status`` table if a DB is
    available; otherwise we report WARN (no DB to read).
    """
    # This is a STATIC check; the DB read happens in
    # _check_partner_messages_in_db below when --db-path is
    # provided. Without the DB, return WARN.
    return ChecklistItem(
        name="current_index_inputs",
        title="Current index inputs (NIFTY + SENSEX)",
        status=Status.WARN,
        detail=(
            "DB path not provided. To verify NIFTY+SENSEX "
            "intraday inputs are fresh, re-run with "
            "'--db-path /data/cache.db'."
        ),
        next_step=(
            "Re-run with '--db-path <cache.db>' to check "
            "partner_advisory_input_status freshness."
        ),
        evidence={},
    )


def _check_valid_candidate(engine_dir: Path) -> ChecklistItem:
    """Check 3: a valid candidate has been generated.

    If the partner informer is healthy but no candidate has
    fired in the last N hours, the operator should check
    whether the input filter is too tight. We can't read
    the DB without --db-path; we return WARN.
    """
    return ChecklistItem(
        name="valid_candidate",
        title="Valid candidate generated recently",
        status=Status.WARN,
        detail=(
            "DB path not provided. To see the most recent "
            "partner advisory idea, re-run with "
            "'--db-path /data/cache.db'."
        ),
        next_step=(
            "Re-run with '--db-path' to check the partner's "
            "last candidate idea + its status."
        ),
        evidence={},
    )


def _check_qualification_compatibility(engine_dir: Path) -> ChecklistItem:
    """Check 4: a genuine compatible qualification exists.

    The partner informer accepts qualification records
    only if they have a verified public-source scope.
    Without a qualifying candidate, the partner is silent.
    This is informational without --db-path.
    """
    return ChecklistItem(
        name="compatible_qualification",
        title="Genuine compatible qualification exists",
        status=Status.WARN,
        detail=(
            "DB path not provided. To verify a qualifying "
            "candidate, re-run with '--db-path /data/cache.db'."
        ),
        next_step=(
            "Re-run with '--db-path' to confirm a "
            "qualifying candidate is currently ready."
        ),
        evidence={},
    )


def _check_destination_configured(engine_dir: Path) -> ChecklistItem:
    """Check 5: configured destination + token.

    The partner Telegram bot needs:
      - PARTNER_TELEGRAM_BOT_TOKEN (or TELEGRAM_BOT_TOKEN)
      - PARTNER_TELEGRAM_CHAT_ID (or TELEGRAM_CHAT_ID)
    These are read at startup; if either is empty, every
    send attempt fails silently (no log emitted).
    """
    # We statically load config defaults. The actual values
    # come from env vars at runtime -- the diagnostic only
    # checks whether the SETTINGS have defaults that look
    # like real credentials (non-empty strings).
    config_path = engine_dir / "config.py"
    has_partner_token = False
    has_partner_chat_id = False
    has_global_token = False
    has_global_chat_id = False
    if config_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location(
                "_partner_check_config", str(config_path),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            Settings = module.Settings
            s = Settings()
            has_partner_token = bool(
                getattr(s, "PARTNER_TELEGRAM_BOT_TOKEN", "")
            )
            has_partner_chat_id = bool(
                getattr(s, "PARTNER_TELEGRAM_CHAT_ID", "")
            )
            has_global_token = bool(getattr(s, "TELEGRAM_BOT_TOKEN", ""))
            has_global_chat_id = bool(getattr(s, "TELEGRAM_CHAT_ID", ""))
        except Exception:
            pass

    has_any_token = has_partner_token or has_global_token
    has_any_chat_id = has_partner_chat_id or has_global_chat_id

    if has_any_token and has_any_chat_id:
        return ChecklistItem(
            name="configured_destination",
            title="Configured Telegram destination + token",
            status=Status.PASS,
            detail=(
                "Telegram bot token + chat ID are configured "
                "(partner-specific or global fallback)."
            ),
            next_step="No action needed.",
            evidence={
                "partner_token": has_partner_token,
                "partner_chat_id": has_partner_chat_id,
                "global_token": has_global_token,
                "global_chat_id": has_global_chat_id,
            },
        )

    missing = []
    if not has_any_token:
        missing.append("bot_token")
    if not has_any_chat_id:
        missing.append("chat_id")
    return ChecklistItem(
        name="configured_destination",
        title="Configured Telegram destination + token",
        status=Status.FAIL,
        detail=(
            f"Missing Telegram config: {', '.join(missing)}. "
            "Partner sends will silently fail."
        ),
        next_step=(
            "Set PARTNER_TELEGRAM_BOT_TOKEN + "
            "PARTNER_TELEGRAM_CHAT_ID (or the global "
            "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) in "
            ".env / .env.prod. Restart the python-engine."
        ),
        evidence={
            "missing": missing,
            "partner_token_configured": has_partner_token,
            "partner_chat_id_configured": has_partner_chat_id,
            "global_token_configured": has_global_token,
            "global_chat_id_configured": has_global_chat_id,
        },
    )


def _check_transport_via_db(db_path: Path) -> ChecklistItem:
    """Check 6: transport test (last successful Telegram send).

    Queries the partner_messages table for the most recent
    row + checks if `delivered=1` was ever recorded.
    """
    if not db_path.is_file():
        return ChecklistItem(
            name="transport_test",
            title="Transport test (last successful send)",
            status=Status.WARN,
            detail=(
                f"DB not found at {db_path}. Cannot verify "
                "transport."
            ),
            next_step=(
                "Re-run with the correct --db-path."
            ),
            evidence={},
        )
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT sent_at, kind, delivered, detail "
                "FROM partner_messages ORDER BY sent_at DESC "
                "LIMIT 1"
            ).fetchone()
            total = conn.execute(
                "SELECT COUNT(*) FROM partner_messages"
            ).fetchone()[0]
            delivered_count = conn.execute(
                "SELECT COUNT(*) FROM partner_messages "
                "WHERE delivered=1"
            ).fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:
        return ChecklistItem(
            name="transport_test",
            title="Transport test (last successful send)",
            status=Status.WARN,
            detail=f"DB read error: {exc}",
            next_step="Verify the DB path and permissions.",
            evidence={},
        )

    if row is None:
        return ChecklistItem(
            name="transport_test",
            title="Transport test (last successful send)",
            status=Status.FAIL,
            detail="No partner_messages rows on disk.",
            next_step=(
                "Check why partner_messages is empty: "
                "telegram_init, telegram_send failures, "
                "or the cron hasn't fired yet."
            ),
            evidence={"total_rows": total, "delivered": delivered_count},
        )

    delivered = bool(row[2])
    return ChecklistItem(
        name="transport_test",
        title="Transport test (last successful send)",
        status=Status.PASS if delivered else Status.WARN,
        detail=(
            f"Last message: kind={row[1]} sent_at={row[0]} "
            f"delivered={delivered}. Total: {total} rows, "
            f"{delivered_count} delivered."
        ),
        next_step="No action needed." if delivered else (
            "Most recent send was NOT delivered. Check "
            "TELEGRAM_BOT_TOKEN validity."
        ),
        evidence={
            "last_kind": row[1],
            "last_sent_at": row[0],
            "last_delivered": delivered,
            "last_detail": row[3],
            "total_rows": total,
            "delivered_count": delivered_count,
        },
    )


def _check_session_gates(db_path: Path) -> ChecklistItem:
    """Check 7: final dispatch/session gates (phase3 readiness).

    Reads hedge_readiness.assess_hedge_readiness() to
    surface the phase3 blockers. The most common ones are
    staging_days < 7, live_chain_verification == 0,
    sample_review < 5 per kind.
    """
    if not db_path.is_file():
        return ChecklistItem(
            name="session_gates",
            title="Final dispatch / session gates",
            status=Status.WARN,
            detail=(
                f"DB not found at {db_path}. Cannot read "
                "phase3 readiness."
            ),
            next_step=(
                "Re-run with '--db-path /data/cache.db'."
            ),
            evidence={},
        )

    # Lazy-import hedge_readiness to avoid heavy deps on a
    # static check. We exec the module via importlib so the
    # path requirement is just one file.
    hr_path = ENGINE_DIR / "hedge_readiness.py"
    if not hr_path.is_file():
        return ChecklistItem(
            name="session_gates",
            title="Final dispatch / session gates",
            status=Status.WARN,
            detail=(
                "hedge_readiness.py not found at "
                f"{hr_path}. Cannot run assess_hedge_readiness."
            ),
            next_step="Verify the python-engine checkout.",
            evidence={},
        )

    try:
        import asyncio
        spec = importlib.util.spec_from_file_location(
            "_check_hedge_readiness", str(hr_path),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["_check_hedge_readiness"] = module
        spec.loader.exec_module(module)
        readiness = asyncio.run(module.assess_hedge_readiness(str(db_path)))
        can_enable = bool(readiness.get("can_enable"))
        blockers = readiness.get("blockers") or []
        # Categorize each blocker for the operator.
        return ChecklistItem(
            name="session_gates",
            title="Final dispatch / session gates",
            status=Status.PASS if can_enable else Status.BLOCKER,
            detail=(
                f"can_enable={can_enable}. "
                f"{len(blockers)} blocker(s) found."
            ),
            next_step=(
                "Resolve blockers listed in 'evidence.blockers'. "
                "Common fixes: advance staging_days, run "
                "live_chain_verification, populate sample_review."
            ),
            evidence={
                "can_enable": can_enable,
                "blockers": blockers,
                "research_only": readiness.get("research_only"),
                "automatic_execution": readiness.get("automatic_execution"),
                "can_place_orders": readiness.get("can_place_orders"),
            },
        )
    except Exception as exc:
        return ChecklistItem(
            name="session_gates",
            title="Final dispatch / session gates",
            status=Status.WARN,
            detail=f"assess_hedge_readiness failed: {exc}",
            next_step="Verify the readiness DB schema.",
            evidence={"error": str(exc)},
        )


def _check_index_inputs_via_db(db_path: Path) -> ChecklistItem:
    """Check 2 with DB: query partner_advisory_input_status."""
    if not db_path.is_file():
        return _check_index_inputs(ENGINE_DIR)
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT underlying, status, freshness_sec, "
                "evaluated_at FROM partner_advisory_input_status"
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return ChecklistItem(
            name="current_index_inputs",
            title="Current index inputs (NIFTY + SENSEX)",
            status=Status.WARN,
            detail=f"DB read error: {exc}",
            next_step="Verify the DB path and permissions.",
            evidence={},
        )
    if not rows:
        return ChecklistItem(
            name="current_index_inputs",
            title="Current index inputs (NIFTY + SENSEX)",
            status=Status.WARN,
            detail="partner_advisory_input_status is empty.",
            next_step=(
                "Check that partner_manual_advisory_lifecycle_tick "
                "is firing and writing to partner_advisory_input_status."
            ),
            evidence={},
        )
    by_underlying = {row[0]: row for row in rows}
    fresh = all(
        r[2] is not None and r[2] < 600 for r in rows
    )
    return ChecklistItem(
        name="current_index_inputs",
        title="Current index inputs (NIFTY + SENSEX)",
        status=Status.PASS if fresh else Status.WARN,
        detail=(
            f"{len(rows)} underlying(s) tracked: "
            + ", ".join(f"{name}={row[1]}/freshness={row[2]}s"
                          for name, row in by_underlying.items())
        ),
        next_step=(
            "No action needed." if fresh else
            "Freshness > 600s for at least one underlying. "
            "Check the advisory lifecycle tick is firing."
        ),
        evidence={
            "rows": [
                {"underlying": r[0], "status": r[1],
                 "freshness_sec": r[2], "evaluated_at": r[3]}
                for r in rows
            ],
        },
    )


def _check_valid_candidate_via_db(db_path: Path) -> ChecklistItem:
    """Check 3 with DB: look at the most recent partner advisory idea."""
    if not db_path.is_file():
        return _check_valid_candidate(ENGINE_DIR)
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT idea_id, generated_at, regime, direction "
                "FROM partner_advisory_ideas ORDER BY generated_at "
                "DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except Exception as exc:
        return ChecklistItem(
            name="valid_candidate",
            title="Valid candidate generated recently",
            status=Status.WARN,
            detail=f"DB read error: {exc}",
            next_step="Verify the DB path and permissions.",
            evidence={},
        )
    if row is None:
        return ChecklistItem(
            name="valid_candidate",
            title="Valid candidate generated recently",
            status=Status.WARN,
            detail="No partner_advisory_ideas row on disk.",
            next_step=(
                "The advisory idea generator hasn't produced "
                "any output yet. Check the partner_input_refresh "
                "cron + the qualification gate."
            ),
            evidence={},
        )
    return ChecklistItem(
        name="valid_candidate",
        title="Valid candidate generated recently",
        status=Status.PASS,
        detail=(
            f"Latest idea: id={row[0]} at {row[1]} "
            f"(regime={row[2]}, direction={row[3]})."
        ),
        next_step="No action needed.",
        evidence={
            "idea_id": row[0], "generated_at": row[1],
            "regime": row[2], "direction": row[3],
        },
    )


def _check_qualification_via_db(db_path: Path) -> ChecklistItem:
    """Check 4 with DB: latest qualifying candidate."""
    if not db_path.is_file():
        return _check_qualification_compatibility(ENGINE_DIR)
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT capture_id, generated_at, kind, state "
                "FROM partner_research_capture ORDER BY "
                "generated_at DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
    except Exception as exc:
        return ChecklistItem(
            name="compatible_qualification",
            title="Genuine compatible qualification exists",
            status=Status.WARN,
            detail=f"DB read error: {exc}",
            next_step="Verify the DB path and permissions.",
            evidence={},
        )
    if row is None:
        return ChecklistItem(
            name="compatible_qualification",
            title="Genuine compatible qualification exists",
            status=Status.WARN,
            detail="No partner_research_capture rows on disk.",
            next_step=(
                "The qualification pipeline hasn't produced a "
                "compatible candidate yet. Check the J.10 "
                "capture gate (CAS_REACHABILITY)."
            ),
            evidence={},
        )
    return ChecklistItem(
        name="compatible_qualification",
        title="Genuine compatible qualification exists",
        status=Status.PASS,
        detail=(
            f"Latest capture: id={row[0]} at {row[1]} "
            f"(kind={row[2]}, state={row[3]})."
        ),
        next_step="No action needed.",
        evidence={
            "capture_id": row[0], "generated_at": row[1],
            "kind": row[2], "state": row[3],
        },
    )


def run_checks(engine_dir: Path, db_path: Path | None) -> list[ChecklistItem]:
    """Run all 7 checklist items and return them in order."""
    items = [
        _check_intraday_profile(engine_dir),
        _check_destination_configured(engine_dir),
    ]
    # DB-dependent checks.
    if db_path is not None:
        items.append(_check_index_inputs_via_db(db_path))
        items.append(_check_valid_candidate_via_db(db_path))
        items.append(_check_qualification_via_db(db_path))
        items.append(_check_transport_via_db(db_path))
        items.append(_check_session_gates(db_path))
    else:
        # Static-only checks (WARN without DB).
        items.append(_check_index_inputs(engine_dir))
        items.append(_check_valid_candidate(engine_dir))
        items.append(_check_qualification_compatibility(engine_dir))
    return items


def format_checklist(items: list[ChecklistItem]) -> str:
    """Render the checklist as a human-readable table."""
    lines = [
        "# Partner readiness diagnostic",
        "# --------------------------",
        f"# {len(items)} checklist items",
        "",
    ]
    for item in items:
        lines.append(f"## [{item.status.value}] {item.title}")
        lines.append(f"Name: `{item.name}`")
        lines.append("")
        lines.append(f"Detail: {item.detail}")
        lines.append("")
        lines.append(f"Next step: {item.next_step}")
        if item.evidence:
            lines.append("")
            lines.append("Evidence:")
            for key, value in item.evidence.items():
                lines.append(f"  - {key}: {value}")
        lines.append("")
    return "\n".join(lines) + "\n"


def items_as_dicts(items: list[ChecklistItem]) -> list[dict]:
    """Serialize checklist items for JSON output."""
    return [
        {
            "name": item.name,
            "title": item.title,
            "status": item.status.value,
            "detail": item.detail,
            "next_step": item.next_step,
            "evidence": item.evidence,
        }
        for item in items
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, default=ENGINE_DIR,
                        help="Path to the python-engine directory.")
    parser.add_argument("--db-path", type=Path, default=None,
                        help="Path to cache.db (optional; enables DB checks).")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON to stdout.")
    args = parser.parse_args(argv)
    if not args.engine_dir.is_dir():
        print(
            f"check_partner_readiness: not a directory: {args.engine_dir}",
            file=sys.stderr,
        )
        return 2
    items = run_checks(args.engine_dir, args.db_path)
    if args.json:
        sys.stdout.write(
            json.dumps(items_as_dicts(items), indent=2) + "\n"
        )
    else:
        sys.stdout.write(format_checklist(items))
    # Exit code: 2 if any BLOCKER, 1 if any FAIL, else 0.
    has_blocker = any(i.status == Status.BLOCKER for i in items)
    has_fail = any(i.status == Status.FAIL for i in items)
    if has_blocker:
        return 2
    if has_fail:
        return 1
    return 0


__all__ = [
    "ChecklistItem",
    "Status",
    "format_checklist",
    "items_as_dicts",
    "main",
    "run_checks",
]


if __name__ == "__main__":
    raise SystemExit(main())
