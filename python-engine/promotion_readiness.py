"""Pure research promotion-readiness assessment.

This module can only recommend paper review. It has no database, scheduler,
configuration, broker, executor, or order imports and performs no mutation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence


COLLECTING = "COLLECTING"
INELIGIBLE = "INELIGIBLE"
CANDIDATE = "CANDIDATE_FOR_PAPER_REVIEW"
_STATES = {COLLECTING, INELIGIBLE, CANDIDATE}


@dataclass(frozen=True)
class ReadinessThresholds:
    minimum_distinct_candidates: int
    minimum_closed_trades: int
    minimum_profit_factor: float
    maximum_drawdown: float
    maximum_repeat_inflation: float
    minimum_oos_folds: int | None
    require_reconciliation: bool = True
    require_provenance: bool = True


THRESHOLDS: Mapping[str, ReadinessThresholds] = MappingProxyType({
    "MOMENTUM": ReadinessThresholds(30, 20, 1.20, 1000.0, 0.50, 3),
    "PENNY": ReadinessThresholds(50, 30, 1.20, 250.0, 0.50, 3),
    # No genuine F&O OOS adapter exists yet. All realised-quality gates remain
    # mandatory; target-only delta scenarios cannot satisfy them.
    "FNO": ReadinessThresholds(30, 20, 1.30, 5000.0, 0.50, None),
})

_ALIASES = {
    "MOMENTUM": "MOMENTUM", "MOMENTUM_INTRADAY_15M_REPLAY": "MOMENTUM",
    "PENNY": "PENNY", "PENNY_BREAKOUT_INTRADAY_1M_REPLAY": "PENNY",
    "FNO": "FNO", "FNO_MOMENTUM_5M": "FNO",
}
_BACKTEST_IDS = {
    "MOMENTUM": "momentum_intraday_15m_replay",
    "PENNY": "penny_breakout_intraday_1m_replay",
    "FNO": "fno_momentum_5m",
}


def _family(value: str) -> str:
    key = str(value).strip().upper()
    if key not in _ALIASES:
        raise ValueError(f"unsupported promotion strategy: {value!r}")
    return _ALIASES[key]


def _finite(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value) -> int | None:
    number = _finite(value)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


def _variant_row(comparison: Mapping[str, Any] | None, variant: str) -> dict:
    rows = comparison.get("variants", []) if isinstance(comparison, Mapping) else []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, Mapping) and row.get("variant") == variant:
            return dict(row)
    return {}


def _latest_run(runs: Sequence[Mapping[str, Any]], family: str) -> dict:
    strategy_id = _BACKTEST_IDS[family]
    matching = [dict(run) for run in runs if isinstance(run, Mapping) and run.get("strategy_id") == strategy_id]
    return max(matching, key=lambda row: str(row.get("completed_at") or row.get("created_at") or ""), default={})


def _result_variant(run: Mapping[str, Any], variant: str) -> dict:
    result = run.get("result") if isinstance(run.get("result"), Mapping) else {}
    rows = result.get("variants", []) if isinstance(result, Mapping) else []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, Mapping) and row.get("variant") == variant:
            return dict(row)
    # Momentum result is aggregate across variants. It is admissible for a
    # fixed variant only when the archived request ran that variant alone.
    configured = run.get("config", {}).get("variants") if isinstance(run.get("config"), Mapping) else None
    if configured == [variant] and isinstance(result.get("summary"), Mapping):
        return dict(result["summary"])
    return {}


def _first(*values):
    return next((value for value in values if value is not None), None)


def _block(gate: str, status: str, observed, required, reason: str) -> dict:
    return {"gate": gate, "status": status, "observed": observed, "required": required, "reason": reason}


def _reconciliation_status(reconciliation: Mapping[str, Any] | None, variant: str) -> str | None:
    if not isinstance(reconciliation, Mapping):
        return None
    if reconciliation.get("status") is not None:
        return str(reconciliation["status"]).upper()
    divisions = reconciliation.get("divisions")
    if isinstance(divisions, Mapping) and isinstance(divisions.get(variant), Mapping):
        return str(divisions[variant].get("status") or "").upper() or None
    return None


def _legacy_assessment(legacy: Mapping[str, Any] | None, variant: str) -> dict:
    verdict = None
    if isinstance(legacy, Mapping):
        if legacy.get("verdict") is not None:
            verdict = legacy.get("verdict")
        else:
            for row in legacy.get("strategies", []) if isinstance(legacy.get("strategies"), list) else []:
                if isinstance(row, Mapping) and (row.get("key") == variant or row.get("source") == variant):
                    verdict = row.get("verdict")
                    break
    return {
        "contract": "analytics.promotion_report ledger-only compatibility input",
        "provided": verdict is not None,
        "legacy_verdict": verdict,
        "sufficient_for_this_decision": False,
        "warning": (
            "Legacy ready_for_live is ledger-only and cannot satisfy candidate, provenance, OOS, "
            "repeat-inflation, profit-factor, or reconciliation gates. This engine never emits LIVE_READY."
        ),
    }


def assess_promotion_readiness(
    strategy: str,
    variant: str,
    *,
    shadow_comparison: Mapping[str, Any] | None,
    backtest_runs: Sequence[Mapping[str, Any]] = (),
    reconciliation: Mapping[str, Any] | None = None,
    legacy_promotion: Mapping[str, Any] | None = None,
    source_timestamps: Mapping[str, Any] | None = None,
) -> dict:
    """Return a deterministic, fail-closed research readiness report."""
    family = _family(strategy)
    variant = str(variant).strip()
    if not variant:
        raise ValueError("variant must not be empty")
    thresholds = THRESHOLDS[family]
    shadow = _variant_row(shadow_comparison, variant)
    run = _latest_run(backtest_runs, family)
    replay = _result_variant(run, variant)
    blockers: list[dict] = []

    distinct = _integer(_first(shadow.get("distinct_candidates"), replay.get("distinct_candidates"), replay.get("entries")))
    raw_accepts = _integer(_first(shadow.get("raw_accepts"), shadow.get("accepts"), shadow.get("accepted_evaluations")))
    closed = _integer(_first(shadow.get("closed_trades"), replay.get("closed_trades")))
    expectancy = _finite(_first(shadow.get("net_expectancy"), shadow.get("expectancy"), replay.get("net_expectancy"), replay.get("expectancy")))
    profit_factor = _finite(_first(shadow.get("profit_factor"), replay.get("profit_factor")))
    drawdown = _finite(_first(shadow.get("max_drawdown"), replay.get("max_drawdown")))
    repeat_inflation = (
        max(raw_accepts - distinct, 0) / raw_accepts
        if raw_accepts is not None and distinct is not None and raw_accepts > 0 else None
    )

    for gate, observed, required in (
        ("distinct_candidates", distinct, thresholds.minimum_distinct_candidates),
        ("closed_trades", closed, thresholds.minimum_closed_trades),
    ):
        if observed is None:
            blockers.append(_block(gate, COLLECTING, None, f">={required}", f"{gate} evidence is unavailable"))
        elif observed < required:
            blockers.append(_block(gate, COLLECTING, observed, f">={required}", f"sample is still collecting ({observed}/{required})"))

    quality_sample_ready = (
        distinct is not None and distinct >= thresholds.minimum_distinct_candidates
        and closed is not None and closed >= thresholds.minimum_closed_trades
    )
    for gate, observed, required, passes in (
        ("net_expectancy_after_costs", expectancy, ">0", expectancy is not None and expectancy > 0),
        ("profit_factor", profit_factor, f">={thresholds.minimum_profit_factor}", profit_factor is not None and profit_factor >= thresholds.minimum_profit_factor),
        ("max_drawdown", drawdown, f"<={thresholds.maximum_drawdown}", drawdown is not None and drawdown <= thresholds.maximum_drawdown),
        ("repeat_inflation", repeat_inflation, f"<={thresholds.maximum_repeat_inflation}", repeat_inflation is not None and repeat_inflation <= thresholds.maximum_repeat_inflation),
    ):
        if observed is None:
            blockers.append(_block(gate, COLLECTING, None, required, f"{gate} is unavailable; zero is not assumed"))
        elif not passes:
            status = INELIGIBLE if quality_sample_ready else COLLECTING
            blockers.append(_block(gate, status, round(observed, 6), required, f"{gate} does not meet the static gate"))

    run_result = run.get("result") if isinstance(run.get("result"), Mapping) else {}
    oos = run_result.get("oos") if isinstance(run_result.get("oos"), Mapping) else {}
    run_summary = run.get("summary") if isinstance(run.get("summary"), Mapping) else {}
    summary_oos = run_summary.get("oos") if isinstance(run_summary.get("oos"), Mapping) else {}
    scored_folds = _integer(_first(
        oos.get("scored_folds"), oos.get("n_scored_folds"),
        summary_oos.get("n_scored_folds"),
    ))
    if thresholds.minimum_oos_folds is not None:
        if scored_folds is None or scored_folds < thresholds.minimum_oos_folds:
            blockers.append(_block(
                "oos_folds", COLLECTING, scored_folds, f">={thresholds.minimum_oos_folds}",
                "strict chronological OOS evidence is missing or insufficient",
            ))

    provenance_status = None
    dataset = run.get("dataset") if isinstance(run.get("dataset"), Mapping) else {}
    if run:
        if run.get("status") == "UNAVAILABLE":
            provenance_status = "INVALID"
        elif run.get("status") != "SUCCEEDED":
            provenance_status = "UNKNOWN"
        else:
            provenance_status = str(dataset.get("status") or dataset.get("diagnostics", {}).get("status") or "VALID").upper()
            result = run.get("result") if isinstance(run.get("result"), Mapping) else {}
            coverage = result.get("coverage") if isinstance(result.get("coverage"), Mapping) else {}
            diagnostics = dataset.get("diagnostics") if isinstance(dataset.get("diagnostics"), Mapping) else dataset
            invalid_lists = (
                diagnostics.get("invalid_provenance"), diagnostics.get("missing_daily_history"),
                diagnostics.get("missing_requested_tickers"),
            )
            missing_prior = _integer(coverage.get("ticker_days_missing_prior_daily"))
            coverage_rows = diagnostics.get("coverage") if isinstance(diagnostics.get("coverage"), list) else []
            missing_minutes = sum(
                _integer(row.get("missing_minutes_within_span")) or 0
                for row in coverage_rows if isinstance(row, Mapping)
            )
            if any(bool(value) for value in invalid_lists) or (missing_prior or 0) > 0:
                provenance_status = "INVALID"
            elif missing_minutes > 0:
                provenance_status = "DEGRADED"
    if thresholds.require_provenance:
        if provenance_status in {None, "UNKNOWN"}:
            blockers.append(_block("data_provenance", COLLECTING, provenance_status, "VALID", "no completed provenance-bearing replay is available"))
        elif provenance_status not in {"VALID", "COMPLETE"}:
            blockers.append(_block("data_provenance", INELIGIBLE, provenance_status, "VALID", "replay data provenance or coverage is unhealthy"))

    recon_status = _reconciliation_status(reconciliation, variant)
    if thresholds.require_reconciliation:
        if recon_status in {None, "", "UNAVAILABLE"}:
            blockers.append(_block("reconciliation", COLLECTING, recon_status, "MATCH", "ledger/position reconciliation is unavailable"))
        elif recon_status != "MATCH":
            blockers.append(_block("reconciliation", INELIGIBLE, recon_status, "MATCH", "ledger remains cash truth and observations mismatch"))

    state = (
        INELIGIBLE if any(item["status"] == INELIGIBLE for item in blockers)
        else COLLECTING if blockers
        else CANDIDATE
    )
    assert state in _STATES and state != "LIVE_READY"
    timestamps = dict(source_timestamps or {})
    if isinstance(shadow_comparison, Mapping):
        timestamps.setdefault(
            "shadow_as_of",
            shadow_comparison.get("generated_at") or shadow_comparison.get("as_of"),
        )
    if run:
        timestamps.setdefault("backtest_completed_at", run.get("completed_at"))
    return {
        "schema_version": 1, "strategy": family, "variant": variant,
        "state": state, "research_only": True, "can_place_orders": False,
        "maximum_possible_state": CANDIDATE,
        "thresholds": asdict(thresholds),
        "evidence": {
            "distinct_candidates": distinct, "raw_accepts": raw_accepts,
            "closed_trades": closed, "net_expectancy_after_costs": expectancy,
            "profit_factor": profit_factor, "max_drawdown": drawdown,
            "repeat_inflation": round(repeat_inflation, 6) if repeat_inflation is not None else None,
            "oos_scored_folds": scored_folds, "provenance_status": provenance_status,
            "reconciliation_status": recon_status,
        },
        "blockers": blockers, "source_timestamps": timestamps,
        "sources": {
            "shadow_variant_found": bool(shadow), "backtest_run_id": run.get("run_id"),
            "backtest_status": run.get("status"), "ledger_cash_truth": True,
        },
        "legacy_compatibility": _legacy_assessment(legacy_promotion, variant),
        "explanation": (
            "Candidate means eligible for human paper-review only. It never authorizes live trading, "
            "configuration changes, sizing changes, or order placement."
        ),
    }


def _json_safe(value):
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return value


def readiness_json(report: Mapping[str, Any]) -> str:
    """Deterministic strict JSON suitable for immutable persistence later."""
    return json.dumps(
        _json_safe(report), sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
