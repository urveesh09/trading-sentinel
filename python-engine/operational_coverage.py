"""Shared, read-only producer coverage contract for the operations dashboard."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from config import settings


def _coverage(*, source_kind: str, configured: bool, enabled: bool, state: str,
              reason: str, attempted_at: str | None = None, last_success_at: str | None = None,
              observed_at: str | None = None, receipt_at: str | None = None,
              counts: dict[str, Any] | None = None, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_kind": source_kind, "configured": configured, "enabled": enabled,
        "state": state, "reason": reason, "attempted_at": attempted_at,
        "last_success_at": last_success_at, "observed_at": observed_at,
        "receipt_at": receipt_at, "counts": counts or {}, "identity": identity or {},
        "can_place_orders": False,
    }


async def operational_coverage_report(db_path: str) -> dict[str, Any]:
    """Map producer evidence without treating missing rows as zero activity."""
    from optional_ai_status import load_optional_ai_status
    from partner_manual_advisory import load_advisory_input_status
    from proactive_intelligence import proactive_activity_report
    from research_archive import readiness_view
    from scheduler_telemetry import scheduler_timing_report

    # These readers also perform idempotent schema initialization.  Running
    # them concurrently against one SQLite file can race on WAL/schema locks,
    # making this read-only report intermittently fail.  Serialize the local
    # DB reads; archive inspection below remains offloaded from the event loop.
    inputs = await load_advisory_input_status(db_path)
    proactive = await proactive_activity_report(
        db_path, now=datetime.now(timezone.utc)
    )
    timing = await scheduler_timing_report(db_path, limit=250)
    optional_ai = await load_optional_ai_status(db_path)
    archive = await asyncio.to_thread(readiness_view, settings.RESEARCH_ARCHIVE_PATH)
    producers: dict[str, dict[str, Any]] = {}
    for underlying, status in sorted(inputs.items()):
        stage = status["stage"]
        healthy = stage == "NO_ENTRY_SETUP" or stage in {"CANDIDATE_VALIDATED", "DELIVERY_QUEUED"}
        producers[f"manual_advisory:{underlying}"] = _coverage(
            source_kind="MANUAL_ADVISORY_INPUT", configured=True,
            enabled=bool(settings.PARTNER_MANUAL_ADVISORY_ENABLED),
            state="HEALTHY_NO_SETUP" if stage == "NO_ENTRY_SETUP" else ("AVAILABLE" if healthy else "UNAVAILABLE"),
            reason=status["reason"], attempted_at=status["attempted_at"],
            last_success_at=status["last_success_at"], observed_at=status["observed_at"],
            receipt_at=status["received_at"],
            counts={"freshness_seconds_at_receipt": status["freshness_seconds"]},
            identity={"underlying": underlying, "profile_state": status["profile_state"],
                      "qualification_state": status["qualification_state"]},
        )
    latest = proactive.get("market_data", {}).get("latest", [])
    if not latest:
        source = str(settings.PROACTIVE_SHADOW_DATA_SOURCE).strip().upper()
        configured = bool(settings.PROACTIVE_SHADOW_COMPLETED_BAR_FIXTURE_PATH) if source == "RECORDED_COMPLETED_BARS_V1" else (bool(settings.PROACTIVE_SHADOW_KITE_TOKENS_JSON) if source == "KITE_COMPLETED_BARS_V1" else bool(settings.PROACTIVE_SHADOW_FIXTURE_PATH))
        producers["proactive_completed_bars"] = _coverage(
            source_kind=source or "COMPLETED_BAR_SHADOW", configured=configured,
            enabled=bool(settings.PROACTIVE_SHADOW_ENABLED), state="UNCONFIGURED",
            reason="NO_RECORDED_COMPLETED_BAR_OBSERVATION",
        )
    else:
        for row in latest:
            key = f"proactive_completed_bars:{row['account_id']}:{row['run_id']}"
            producers[key] = _coverage(
                source_kind="COMPLETED_BAR_SHADOW", configured=True,
                enabled=bool(settings.PROACTIVE_SHADOW_ENABLED), state=row["state"], reason=row["reason"],
                observed_at=row.get("observed_at"), receipt_at=row.get("received_at"),
                counts={"instruments": row.get("instrument_count"), "bars": row.get("bar_count"),
                        "current_age_seconds": row.get("freshness_seconds")},
                identity={"account_id": row["account_id"], "run_id": row["run_id"],
                          "provider": row.get("provider"), "policy": "SHADOW"},
            )
    for underlying, record in sorted((archive.get("per_index") or {}).items()):
        quote_state = record.get("quote_observation_status", "NOT_YET_OBSERVED")
        producers[f"fno_collection:{underlying}"] = _coverage(
            source_kind="FNO_QUOTE_ARCHIVE", configured=bool(settings.RESEARCH_ARCHIVE_ENABLED),
            enabled=bool(settings.RESEARCH_ARCHIVE_ENABLED),
            state=quote_state, reason=(record.get("latest_gap") or {}).get("reason", quote_state),
            attempted_at=record.get("last_collection_run_utc"), last_success_at=record.get("last_valid_quote_utc"),
            observed_at=record.get("provider_timestamp_utc"), receipt_at=record.get("last_seen_quote_utc"),
            counts={"recent_gaps": record.get("recent_gap_count"),
                    "provider_age_seconds": record.get("provider_age_seconds"),
                    "contracts_in_latest_master": (record.get("master") or {}).get("contract_count"),
                    "active_selected_legs": (record.get("selected_leg_coverage") or {}).get("active_legs"),
                    "selected_leg_missing_packets": (record.get("selected_leg_coverage") or {}).get("missing_packets")},
            identity={"underlying": underlying, "source": "research_archive",
                      "master_sha256": (record.get("master") or {}).get("raw_sha256")},
        )
    for job_id, job in timing["jobs"].items():
        latest_event = next((event for event in reversed(timing["events"]) if event["job_id"] == job_id), None)
        producers[f"scheduler:{job_id}"] = _coverage(
            source_kind="SCHEDULER_TELEMETRY", configured=True, enabled=True,
            state="SCHEDULER_REJECTED" if job["rejected"] else "OBSERVED",
            reason=(latest_event or {}).get("reason") or "timing_observed",
            attempted_at=(latest_event or {}).get("started_at"),
            last_success_at=(latest_event or {}).get("ended_at") if (latest_event or {}).get("result") == "COMPLETED" else None,
            counts={"runs": job["runs"], "rejected": job["rejected"], **job["elapsed_seconds"]},
            identity={"job_id": job_id, "boot_id": (latest_event or {}).get("boot_id")},
        )
    # [WORKFLOW-H H2 2026-09-13] Tier-level coverage. One entry per
    # §12 priority tier (exit, advice, scan, research, system,
    # other) so the operator can see WHICH priority bucket has
    # observed activity. A tier with zero jobs is emitted with
    # state="UNCONFIGURED" and reason="no_jobs_in_tier" -- the UI
    # fixture covers unavailable-vs-zero per §12 acceptance.
    by_tier = timing.get("by_tier") or {}
    for tier_name, tier_data in sorted(by_tier.items()):
        tier_state = (
            "UNCONFIGURED"
            if int(tier_data.get("job_count", 0)) == 0
            else "OBSERVED"
        )
        tier_reason = (
            "no_jobs_in_tier"
            if tier_state == "UNCONFIGURED"
            else "tier_observed"
        )
        producers[f"scheduler_tier:{tier_name}"] = _coverage(
            source_kind="SCHEDULER_TIER_TELEMETRY",
            configured=True,
            enabled=True,
            state=tier_state,
            reason=tier_reason,
            counts={
                "job_count": int(tier_data.get("job_count", 0)),
                "runs": int(tier_data.get("runs", 0)),
                "executed_runs": int(tier_data.get("executed_runs", 0)),
                "rejected": int(tier_data.get("rejected", 0)),
                "in_flight": int(tier_data.get("in_flight", 0)),
                **tier_data.get("elapsed_seconds", {}),
            },
            identity={
                "tier": tier_name,
                "jobs": list(tier_data.get("jobs", [])),
            },
        )
    # [WORKFLOW-I I.C 2026-09-13] Optional-AI producer. The agent's
    # status envelope is already validated by I.A's bounded
    # validator; here we surface it through the same
    # ``_coverage`` contract as the other producers so the
    # dashboard's ``OperationalCoverage`` section shows it
    # alongside the rest. The state passes through the H5
    # vocabulary validator at the end of this function (no
    # additional allow-list needed -- ``STATE_TO_DESCRIPTOR``
    # is extended in ``coverage_vocabulary.py``).
    #
    # The optional AI appears as a single producer (no
    # per-account shape -- the agent is a single worker, not
    # a per-index pipeline). The bounded ``detail`` from the
    # engine's ``load_optional_ai_status`` carries the queue
    # snapshot plus the I.A usefulness envelope; both are
    # already validated by the producer side.
    oa_state = str(optional_ai.get("state", "NOT_REPORTED"))
    oa_detail = optional_ai.get("detail") or {}
    oa_queue = oa_detail.get("queue") or {}
    oa_reason = (
        oa_detail.get("reason")
        or oa_state.lower().replace("_", " ")
        or "optional_annotation_unknown"
    )
    producers["optional_ai"] = _coverage(
        source_kind="OPTIONAL_AI_ANNOTATION",
        configured=True,
        enabled=oa_state not in {
            "DISABLED_NO_CREDENTIAL",
            "DISABLED_BY_CONFIGURATION",
            "DISABLED_BY_POLICY",
            "NOT_REPORTED",
        },
        state=oa_state,
        reason=str(oa_reason)[:160],
        attempted_at=None,
        last_success_at=None,
        observed_at=oa_detail.get("reported_at"),
        receipt_at=oa_detail.get("received_at"),
        counts={
            "stale": bool(oa_detail.get("stale", False)),
            "pending": oa_queue.get("pending"),
            "cached": oa_queue.get("cached"),
            "daily_requests": oa_queue.get("daily_requests"),
            "daily_budget": oa_queue.get("daily_budget"),
            "circuit_state": oa_queue.get("circuit_state"),
            # I.A usefulness envelope, when present. Absent means
            # the operator hasn't opted in; we surface "null"
            # explicitly so the dashboard can distinguish.
            "usefulness": oa_detail.get("usefulness"),
        },
        identity={
            "reported_state": oa_detail.get("reported_state", oa_state),
            "execution_authority": oa_detail.get("execution_authority", "NONE"),
            "can_place_orders": oa_detail.get("can_place_orders", False),
        },
    )
    report = {"as_of": datetime.now(timezone.utc).isoformat(), "producers": producers,
              "note": "Coverage is operational evidence. Empty or unavailable sources never mean zero market opportunities or broker P&L."}
    # [WORKFLOW-H H5 2026-09-13] Validate every producer's state/reason
    # against the documented vocabulary. Unmapped values are surfaced
    # in the report and logged at WARNING so operators see the gap.
    # The report is returned unchanged so callers can choose to ignore
    # the drift list if they don't care.
    from coverage_vocabulary import validate_coverage_report
    _, drift = validate_coverage_report(report)
    if drift:
        report = dict(report)
        report["vocabulary_drift"] = [
            {
                "producer_id": d.producer_id,
                "state": d.state,
                "reason": d.reason,
                "descriptor": d.descriptor.value if d.descriptor else None,
            }
            for d in drift
        ]
        for d in drift:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "coverage_vocabulary_drift %s", d,
            )
    return report
