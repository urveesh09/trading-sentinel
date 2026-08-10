"""Authenticated, read-only aggregation of unified promotion evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from fastapi import APIRouter, Request

from analytics import promotion_report
from backtest_lab import get_run, list_runs
from config import settings
from engine_auth import _check_internal_secret
from fno_shadow import VARIANTS as FNO_VARIANTS, fno_shadow_comparison
from momentum_shadow import VARIANTS as MOMENTUM_VARIANTS, momentum_shadow_comparison
from penny_shadow import VARIANTS as PENNY_VARIANTS, penny_shadow_comparison
from performance_analytics import division_performance
from promotion_readiness import assess_promotion_readiness, readiness_json


router = APIRouter(prefix="/research", tags=["research"])

_FAMILIES = {
    "MOMENTUM": {
        "variants": MOMENTUM_VARIANTS,
        "comparison": momentum_shadow_comparison,
        "backtest_id": "momentum_intraday_15m_replay",
        "division": "momentum_paper",
        "legacy": "momentum_paper",
    },
    "PENNY": {
        "variants": PENNY_VARIANTS,
        "comparison": penny_shadow_comparison,
        "backtest_id": "penny_breakout_intraday_1m_replay",
        "division": "penny_breakout_paper",
        "legacy": "penny_breakout_paper",
    },
    "FNO": {
        "variants": FNO_VARIANTS,
        "comparison": fno_shadow_comparison,
        "backtest_id": "fno_momentum_5m",
        "division": "fno_paper",
        "legacy": "fno_paper",
    },
}


async def _full_runs(strategy_id: str) -> tuple[list[dict], list[str]]:
    errors, full = [], []
    try:
        # The assessor consumes the latest completed archive only. Requesting
        # and reopening hundreds of immutable historical rows adds latency but
        # cannot change that selection.
        summaries = await list_runs(settings.DB_PATH, limit=1, strategy_id=strategy_id)
    except Exception as exc:
        return [], [f"backtest list unavailable: {type(exc).__name__}: {str(exc)[:240]}"]
    if not isinstance(summaries, (list, tuple)):
        return [], ["backtest list unavailable: malformed response"]
    for summary in summaries:
        run_id = summary.get("run_id") if isinstance(summary, dict) else None
        if not run_id:
            errors.append("backtest list contained a row without run_id")
            continue
        try:
            detail = await get_run(settings.DB_PATH, run_id)
            if detail is not None:
                full.append(detail)
            else:
                errors.append(f"backtest run detail missing: {run_id}")
        except Exception as exc:
            errors.append(f"backtest run {run_id} unavailable: {type(exc).__name__}: {str(exc)[:180]}")
    return full, errors


@router.get("/promotion-readiness")
async def promotion_readiness_report(request: Request):
    """Research evidence only; this response can never authorize execution."""
    _check_internal_secret(request, "research_promotion_readiness")
    global_errors = []
    try:
        performance = await division_performance(settings.DB_PATH)
    except Exception as exc:
        performance = {"divisions": [], "as_of": None}
        global_errors.append(f"division reconciliation unavailable: {type(exc).__name__}: {str(exc)[:240]}")
    if not isinstance(performance, dict):
        performance = {"divisions": [], "as_of": None}
        global_errors.append("division reconciliation unavailable: malformed response")
    performance_rows = performance.get("divisions")
    if not isinstance(performance_rows, (list, tuple)):
        performance_rows = []
        global_errors.append("division reconciliation unavailable: malformed divisions")
    divisions = {
        row.get("key"): row for row in performance_rows
        if isinstance(row, dict) and row.get("key")
    }
    try:
        legacy = await promotion_report(settings.DB_PATH)
    except Exception as exc:
        legacy = {"strategies": []}
        global_errors.append(f"legacy ledger report unavailable: {type(exc).__name__}: {str(exc)[:240]}")
    if not isinstance(legacy, dict):
        legacy = {"strategies": []}
        global_errors.append("legacy ledger report unavailable: malformed response")
    legacy_strategies = legacy.get("strategies")
    if not isinstance(legacy_strategies, (list, tuple)):
        legacy_strategies = []
        global_errors.append("legacy ledger report unavailable: malformed strategies")
    legacy_rows = {
        row.get("key"): row for row in legacy_strategies
        if isinstance(row, dict) and row.get("key")
    }

    families = []
    for family, contract in _FAMILIES.items():
        errors = []
        try:
            comparison = await contract["comparison"](settings.DB_PATH)
        except Exception as exc:
            comparison = {"variants": []}
            errors.append(f"shadow comparison unavailable: {type(exc).__name__}: {str(exc)[:240]}")
        runs, run_errors = await _full_runs(contract["backtest_id"])
        errors.extend(run_errors)
        division = divisions.get(contract["division"], {})
        reconciliation = division.get("reconciliation") if isinstance(division, dict) else None
        legacy_row = legacy_rows.get(contract["legacy"])
        reports = []
        for variant in contract["variants"]:
            try:
                report = assess_promotion_readiness(
                    family, variant, shadow_comparison=comparison,
                    backtest_runs=runs, reconciliation=reconciliation,
                    legacy_promotion=legacy_row,
                    source_timestamps={
                        "performance_as_of": performance.get("as_of"),
                        "shadow_as_of": comparison.get("as_of") or comparison.get("generated_at"),
                    },
                )
                # Round-trip through the strict encoder before FastAPI sees it.
                reports.append(json.loads(readiness_json(report)))
            except Exception as exc:
                errors.append(
                    f"variant {variant} assessment unavailable: "
                    f"{type(exc).__name__}: {str(exc)[:180]}"
                )
                reports.append({
                    "schema_version": 1, "strategy": family, "variant": variant,
                    "state": "COLLECTING", "research_only": True,
                    "can_place_orders": False,
                    "maximum_possible_state": "CANDIDATE_FOR_PAPER_REVIEW",
                    "evidence": {},
                    "blockers": [{
                        "gate": "assessment_integrity", "status": "COLLECTING",
                        "observed": None, "required": "successful assessment",
                        "reason": "variant evidence could not be assessed",
                    }],
                    "source_timestamps": {},
                    "explanation": "Assessment failure cannot authorize promotion or execution.",
                })
        families.append({
            "strategy": family, "variants": reports, "source_errors": errors,
            "reconciliation_division": contract["division"],
        })
    return {
        "schema_version": 1,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "can_place_orders": False,
        "authorization_effect": "NONE",
        "maximum_possible_state": "CANDIDATE_FOR_PAPER_REVIEW",
        "families": families, "source_errors": global_errors,
        "warning": (
            "Research evidence only. Neither this endpoint nor the deprecated ledger ladder "
            "authorizes live trading, order placement, sizing, or configuration mutation."
        ),
    }
