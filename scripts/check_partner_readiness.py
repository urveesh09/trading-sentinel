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

    # With the runtime DB (reads the current manual-advisory schemas and
    # reports advanced hedge progress separately).
    python scripts/check_partner_readiness.py \
        --db-path /data/cache.db

    # Exit code 0 (all PASS/WARN), 1 (any FAIL), 2 (any BLOCKER).
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import enum
import importlib.util
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
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


def _load_settings(engine_dir: Path):
    """Load the effective engine settings without exposing credential values."""
    config_path = engine_dir / "config.py"
    if not config_path.is_file():
        return None
    try:
        module_name = f"_partner_check_config_{abs(hash(config_path.resolve()))}"
        spec = importlib.util.spec_from_file_location(module_name, str(config_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        engine_text = str(engine_dir.resolve())
        inserted = engine_text not in sys.path
        if inserted:
            sys.path.insert(0, engine_text)
        try:
            spec.loader.exec_module(module)
        finally:
            if inserted:
                sys.path.remove(engine_text)
        return module.Settings()
    except Exception:
        return None


def _effective_bool(engine_dir: Path, name: str, default: bool = False) -> bool:
    """Resolve a boolean env override, then its literal Settings default."""
    raw = os.getenv(name)
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    try:
        tree = ast.parse((engine_dir / "config.py").read_text(encoding="utf-8-sig"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "Settings":
                for item in node.body:
                    if (isinstance(item, ast.AnnAssign)
                            and isinstance(item.target, ast.Name)
                            and item.target.id == name
                            and isinstance(item.value, ast.Constant)
                            and isinstance(item.value.value, bool)):
                        return item.value.value
    except (OSError, SyntaxError):
        pass
    return default


def _parse_clock(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA schema_version").fetchone()
        return conn
    except sqlite3.OperationalError:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    wal = Path(f"{db_path}-wal")
    if wal.is_file() and wal.stat().st_size:
        raise sqlite3.OperationalError(
            "read-only mount has a non-empty WAL; take a consistent read-only snapshot first"
        )
    # A truly quiescent read-only Docker volume may still reject SQLite's
    # shared-memory setup. Immutable mode is safe only after the WAL check.
    conn = sqlite3.connect(
        f"file:{db_path.resolve().as_posix()}?mode=ro&immutable=1", uri=True,
    )
    conn.execute("PRAGMA schema_version").fetchone()
    return conn


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


def _check_intraday_profile_via_db(db_path: Path) -> ChecklistItem:
    """Check the persisted profile used by the runtime, not a legacy file."""
    if not db_path.is_file():
        return ChecklistItem(
            name="saved_intraday_profile",
            title="Saved intraday profile",
            status=Status.WARN,
            detail=f"DB not found at {db_path}.",
            next_step="Re-run with the correct cache.db path.",
            evidence={},
        )
    try:
        conn = _connect_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT profile_id, version, payload, updated_at "
                "FROM partner_advisory_profiles WHERE profile_id='default'"
            ).fetchone()
        finally:
            conn.close()
    except Exception as exc:
        return ChecklistItem(
            name="saved_intraday_profile",
            title="Saved intraday profile",
            status=Status.WARN,
            detail=f"DB read error: {exc}",
            next_step="Verify the runtime schema and DB path.",
            evidence={},
        )
    if row is None:
        return ChecklistItem(
            name="saved_intraday_profile",
            title="Saved intraday profile",
            status=Status.FAIL,
            detail="The runtime has no saved default partner advisory profile.",
            next_step="Save the reviewed default INTRADAY profile through the authenticated profile route.",
            evidence={},
        )
    try:
        payload = json.loads(row[2])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    intraday = payload.get("holding_period") == "INTRADAY"
    instruments = set(payload.get("instruments") or ())
    supported = {"NIFTY", "SENSEX"} <= instruments
    valid = intraday and supported
    return ChecklistItem(
        name="saved_intraday_profile",
        title="Saved intraday profile",
        status=Status.PASS if valid else Status.FAIL,
        detail=(f"profile_id={row[0]}, version={row[1]}, intraday={intraday}, "
                f"NIFTY+SENSEX={supported}."),
        next_step=("No action needed." if valid else
                   "Save a reviewed INTRADAY profile covering NIFTY and SENSEX."),
        evidence={"profile_id": row[0], "version": row[1],
                  "holding_period": payload.get("holding_period"),
                  "instruments": sorted(instruments), "updated_at": row[3]},
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
    has_partner_token = False
    has_partner_chat_id = False
    has_global_token = False
    has_global_chat_id = False
    s = _load_settings(engine_dir)
    if s is not None:
        try:
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
    """Check 6 against the hardened advisory/hedge transport ledger."""
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
        conn = _connect_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT sent_at, kind, delivered "
                "FROM partner_hedge_messages ORDER BY sent_at DESC "
                "LIMIT 1"
            ).fetchone()
            total = conn.execute(
                "SELECT COUNT(*) FROM partner_hedge_messages"
            ).fetchone()[0]
            delivered_count = conn.execute(
                "SELECT COUNT(*) FROM partner_hedge_messages "
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
            detail="No partner_hedge_messages rows on disk.",
            next_step=(
                "Check why the hardened transport ledger is empty: "
                "telegram_init, telegram_send failures, "
                "or the cron hasn't fired yet."
            ),
            evidence={"total_rows": total, "delivered": delivered_count},
        )

    delivered = bool(row[2])
    sent_at = _parse_clock(row[0])
    age = ((datetime.now(timezone.utc) - sent_at).total_seconds()
           if sent_at is not None else None)
    recent = age is not None and -60 <= age <= 7 * 86400
    status = Status.PASS if delivered and recent else Status.WARN
    return ChecklistItem(
        name="transport_test",
        title="Transport test (last successful send)",
        status=status,
        detail=(
            f"Last message: kind={row[1]} sent_at={row[0]} "
            f"delivered={delivered}, recent_7d={recent}. Total: {total} rows, "
            f"{delivered_count} delivered."
        ),
        next_step=(
            "No action needed." if delivered and recent else
            "Run an explicitly authorized no-advice transport test if current "
            "routing evidence is required; do not manufacture a trade card."
        ),
        evidence={
            "last_kind": row[1],
            "last_sent_at": row[0],
            "last_delivered": delivered,
            "last_recent_7d": recent,
            "total_rows": total,
            "delivered_count": delivered_count,
        },
    )


def _advanced_hedge_progress(db_path: Path) -> dict[str, Any]:
    """Read advanced-hedge evidence without initializing or mutating the DB."""
    try:
        conn = _connect_readonly(db_path)
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='partner_hedge_gate_evidence'"
            ).fetchone()
            if not exists:
                return {"available": False, "reason": "evidence_table_missing"}
            rows = conn.execute(
                "SELECT evidence_type, kind, observed_on "
                "FROM partner_hedge_gate_evidence WHERE phase='phase3'"
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        return {"available": False, "reason": f"read_failed:{type(exc).__name__}"}
    cutoff = (
        datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
        - timedelta(days=30)
    ).isoformat()
    rows = [row for row in rows if str(row[2]) >= cutoff]
    staging_days = sorted({row[2] for row in rows if row[0] == "phase3_staging_day"})
    live_checks = sum(row[0] == "phase3_live_chain_verification" for row in rows)
    sample_reviews: dict[str, int] = {}
    for evidence_type, kind, _ in rows:
        if evidence_type == "phase3_sample_review":
            sample_reviews[kind] = sample_reviews.get(kind, 0) + 1
    return {
        "available": True,
        "staging_days": len(staging_days),
        "required_staging_days": 7,
        "evidence_window_days": 30,
        "live_chain_verifications": live_checks,
        "sample_reviews": dict(sorted(sample_reviews.items())),
        "blocks_manual_advisory": False,
    }


def _check_session_gates(engine_dir: Path, db_path: Path) -> ChecklistItem:
    """Check 7: manual-advisory switches, independent of advanced hedges."""
    if not db_path.is_file():
        return ChecklistItem(
            name="session_gates",
            title="Final dispatch / session gates",
            status=Status.WARN,
            detail=(
                f"DB not found at {db_path}. Cannot read runtime evidence."
            ),
            next_step=(
                "Re-run with '--db-path /data/cache.db'."
            ),
            evidence={},
        )

    resolved = _load_settings(engine_dir)
    enabled = (bool(getattr(resolved, "PARTNER_MANUAL_ADVISORY_ENABLED"))
               if resolved is not None else
               _effective_bool(engine_dir, "PARTNER_MANUAL_ADVISORY_ENABLED"))
    delivery = (bool(getattr(resolved, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED"))
                if resolved is not None else
                _effective_bool(engine_dir, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED"))
    configured = enabled and delivery
    advanced = _advanced_hedge_progress(db_path)
    return ChecklistItem(
        name="session_gates",
        title="Manual advisory final dispatch configuration",
        status=Status.PASS if configured else Status.BLOCKER,
        detail=(
            f"manual_advisory_enabled={enabled}, delivery_enabled={delivery}. "
            "Advanced Phase-3 hedge evidence is separate and does not block "
            "ordinary NIFTY/SENSEX manual advisory cards."
        ),
        next_step=(
            "No configuration action needed; evaluate the independent input, "
            "candidate, qualification and transport rows above."
            if configured else
            "Enable both manual-advisory switches through the reviewed deployment "
            "configuration, then recreate and verify the engine service."
        ),
        evidence={
            "manual_advisory_enabled": enabled,
            "manual_advisory_delivery_enabled": delivery,
            "advanced_phase3": advanced,
            "advanced_phase3_blocks_manual_advisory": False,
            "can_place_orders": False,
        },
    )


def _check_index_inputs_via_db(db_path: Path) -> ChecklistItem:
    """Check 2 with DB: query partner_advisory_input_status."""
    if not db_path.is_file():
        return _check_index_inputs(ENGINE_DIR)
    try:
        conn = _connect_readonly(db_path)
        try:
            rows = conn.execute(
                "SELECT underlying, stage, reason, entry_state, received_at, "
                "profile_state, qualification_state "
                "FROM partner_advisory_input_status"
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
    now = datetime.now(timezone.utc)
    freshness = {
        row[0]: ((now - stamp).total_seconds() if (stamp := _parse_clock(row[4])) else None)
        for row in rows
    }
    required = {"NIFTY", "SENSEX"}
    fresh = required <= set(by_underlying) and all(
        freshness[name] is not None and -60 <= freshness[name] <= 180
        for name in required
    )
    return ChecklistItem(
        name="current_index_inputs",
        title="Current index inputs (NIFTY + SENSEX)",
        status=Status.PASS if fresh else Status.WARN,
        detail=(
            f"{len(rows)} underlying(s) tracked: "
            + ", ".join(f"{name}={row[1]}/freshness={freshness[name]}s"
                          for name, row in by_underlying.items())
        ),
        next_step=(
            "No action needed." if fresh else
            "Both NIFTY and SENSEX require a current <=180s receipt. Check the "
            "broker login, public-input fetch and advisory lifecycle tick."
        ),
        evidence={
            "rows": [
                {"underlying": r[0], "stage": r[1], "reason": r[2],
                 "entry_state": r[3], "freshness_seconds": freshness[r[0]],
                 "received_at": r[4], "profile_state": r[5],
                 "qualification_state": r[6]}
                for r in rows
            ],
        },
    )


def _check_valid_candidate_via_db(db_path: Path) -> ChecklistItem:
    """Check 3 with DB: look at the most recent partner advisory idea."""
    if not db_path.is_file():
        return _check_valid_candidate(ENGINE_DIR)
    try:
        conn = _connect_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT advisory_id, created_at, underlying, status, valid_until "
                "FROM partner_advisory_ideas ORDER BY created_at "
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
    created_at = _parse_clock(row[1])
    current_session = bool(
        created_at and created_at.astimezone(timezone(timedelta(hours=5, minutes=30))).date()
        == datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    )
    return ChecklistItem(
        name="valid_candidate",
        title="Valid candidate generated recently",
        status=Status.PASS if current_session else Status.WARN,
        detail=(
            f"Latest idea: id={row[0]} at {row[1]} "
            f"(underlying={row[2]}, status={row[3]}, current_session={current_session})."
        ),
        next_step=("No action needed." if current_session else
                   "Wait for a genuine current-session setup; do not relax gates merely to create a message."),
        evidence={
            "advisory_id": row[0], "created_at": row[1],
            "underlying": row[2], "status": row[3],
            "valid_until": row[4], "current_session": current_session,
        },
    )


def _check_qualification_via_db(db_path: Path) -> ChecklistItem:
    """Check 4 with DB: latest qualifying candidate."""
    if not db_path.is_file():
        return _check_qualification_compatibility(ENGINE_DIR)
    try:
        conn = _connect_readonly(db_path)
        try:
            rows = conn.execute(
                "SELECT underlying, structure_kind, horizon, policy_version, "
                "dataset_ref, reviewed_at, status "
                "FROM partner_advisory_strategy_qualifications "
                "ORDER BY reviewed_at DESC"
            ).fetchall()
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
    if not rows:
        return ChecklistItem(
            name="compatible_qualification",
            title="Genuine compatible qualification exists",
            status=Status.WARN,
            detail="No partner_advisory_strategy_qualifications rows on disk.",
            next_step=(
                "Complete and review genuine current-policy research; only then "
                "record a qualification linked to an immutable artifact."
            ),
            evidence={},
        )
    compatible = [row for row in rows if row[2] == "INTRADAY"
                  and row[3] == "partner-manual-intraday-v1"
                  and row[6] == "QUALIFIED_FOR_ADVISORY"]
    return ChecklistItem(
        name="compatible_qualification",
        title="Genuine compatible qualification exists",
        status=Status.PASS if compatible else Status.WARN,
        detail=(
            f"{len(compatible)} compatible qualification(s) across "
            f"{len(rows)} retained row(s)."
        ),
        next_step=("No action needed." if compatible else
                   "Review retained rows against the current INTRADAY policy; do not relabel incompatible evidence."),
        evidence={
            "rows": [
                {"underlying": row[0], "structure_kind": row[1],
                 "horizon": row[2], "policy_version": row[3],
                 "dataset_ref": row[4], "reviewed_at": row[5],
                 "status": row[6]}
                for row in rows
            ],
        },
    )


def run_checks(engine_dir: Path, db_path: Path | None) -> list[ChecklistItem]:
    """Run all 7 checklist items and return them in order."""
    items = [_check_destination_configured(engine_dir)]
    # DB-dependent checks.
    if db_path is not None:
        items.insert(0, _check_intraday_profile_via_db(db_path))
        items.append(_check_index_inputs_via_db(db_path))
        items.append(_check_valid_candidate_via_db(db_path))
        items.append(_check_qualification_via_db(db_path))
        items.append(_check_transport_via_db(db_path))
        items.append(_check_session_gates(engine_dir, db_path))
    else:
        # Static-only checks (WARN without DB).
        items.insert(0, _check_intraday_profile(engine_dir))
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
