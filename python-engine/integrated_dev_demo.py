"""One deterministic, Dev-only acceptance artifact for the proactive system.

The artifact deliberately composes the real persistence-facing components
without a scheduler, broker, Telegram transport, external partner, or model
credential.  It is therefore useful as a repeatable implementation check, not
as evidence that a live integration has been operated successfully.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from optional_ai_status import record_optional_ai_status
from partner_lifecycle_demo import run_partner_lifecycle_demo
from proactive_demo import run_proactive_shadow_demo


async def run_integrated_dev_demo(output_dir: str) -> dict:
    """Build the complete offline evidence set in a previously unused folder."""
    root = Path(output_dir)
    if root.exists():
        raise FileExistsError("integrated demo output already exists; choose a new directory")
    root.mkdir(parents=True)
    proactive = await run_proactive_shadow_demo(str(root / "proactive.sqlite3"))
    partner = await run_partner_lifecycle_demo(str(root / "partner.sqlite3"))
    reported_at = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    ai = await record_optional_ai_status(
        str(root / "optional-ai.sqlite3"),
        {
            "state": "OUTAGE_CIRCUIT_OPEN", "reported_at": reported_at.isoformat(),
            "async_requested": True, "policy_allows_annotation": True,
            "queue": {"pending": 0, "cached": 0, "daily_requests": 1,
                      "daily_budget": 20, "max_pending": 5, "circuit_state": "OPEN"},
            "reason": "deterministic integrated outage fixture",
        },
        received_at=reported_at,
    )
    if not (proactive["assertions"]["completed_bar_exit"]
            and partner["assertions"]["corporate_action_new_lifecycle"]
            and ai["state"] == "OUTAGE_CIRCUIT_OPEN"):
        raise RuntimeError("integrated fixture did not establish all required evidence")
    if any((
        proactive["can_place_orders"], partner["can_send"], partner["can_trade"],
        ai["can_place_orders"],
    )):
        raise RuntimeError("integrated fixture unexpectedly granted live authority")
    return {
        "mode": "DEV_FIXTURE", "research_only": True,
        "can_place_orders": False, "can_send": False, "can_trade": False,
        "authorization_effect": "NONE", "output_dir": str(root),
        "proactive": proactive, "partner": partner, "optional_ai": ai,
        "assertions": {
            "scheduled_workflow_contract_exercised": True,
            "cash_position_outcome_evidence": True,
            "matched_entry_exit_trials": True,
            "partner_create_close_reopen_and_corporate_action": True,
            "optional_ai_outage_does_not_block": True,
            "no_live_delivery_or_execution_authority": True,
        },
        "limitations": [
            "This is deterministic offline fixture evidence; it does not start a scheduler or contact any external service.",
            "Live broker, partner delivery, Telegram recovery and forward market performance require separate operational evidence.",
        ],
    }
