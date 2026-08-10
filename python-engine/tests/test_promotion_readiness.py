from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import ast
import json
from pathlib import Path

import pytest

from promotion_readiness import (
    CANDIDATE,
    COLLECTING,
    INELIGIBLE,
    THRESHOLDS,
    assess_promotion_readiness,
    readiness_json,
)


def _shadow(family="MOMENTUM", **changes):
    row = {
        "variant": "MOM_BASE" if family == "MOMENTUM" else "PEN_BASE",
        "evaluations": 100, "accepts": 40, "raw_accepts": 40,
        "distinct_candidates": 30 if family == "MOMENTUM" else 50,
        "closed_trades": 20 if family == "MOMENTUM" else 30,
        "net_expectancy": 10.0, "expectancy": 10.0,
        "profit_factor": 1.5, "max_drawdown": 100.0,
    }
    row.update(changes)
    return {"variants": [row]}


def _run(family="MOMENTUM", **changes):
    strategy_id = (
        "momentum_intraday_15m_replay" if family == "MOMENTUM"
        else "penny_breakout_intraday_1m_replay"
    )
    variant = "MOM_BASE" if family == "MOMENTUM" else "PEN_BASE"
    row = {
        "run_id": "run-new", "strategy_id": strategy_id, "status": "SUCCEEDED",
        "created_at": "2026-08-10T10:00:00+00:00",
        "completed_at": "2026-08-10T10:01:00+00:00",
        "config": {"variants": [variant]}, "dataset": {"status": "valid"},
        "result": {"oos": {"status": "scored", "scored_folds": 3}},
        "summary": {"oos": {"available": True, "n_scored_folds": 3}},
    }
    row.update(changes)
    return row


def _assess(family="MOMENTUM", shadow=None, runs=None, reconciliation=None, legacy=None):
    variant = "MOM_BASE" if family == "MOMENTUM" else "PEN_BASE"
    return assess_promotion_readiness(
        family, variant, shadow_comparison=shadow or _shadow(family),
        backtest_runs=runs if runs is not None else [_run(family)],
        reconciliation=reconciliation or {"status": "MATCH"},
        legacy_promotion=legacy,
        source_timestamps={"shadow_as_of": "2026-08-10T10:00:00+00:00"},
    )


def test_all_static_gates_only_reach_candidate_for_paper_review():
    result = _assess()
    assert result["state"] == CANDIDATE
    assert result["blockers"] == []
    assert result["maximum_possible_state"] == CANDIDATE
    assert result["research_only"] is True and result["can_place_orders"] is False
    assert result["state"] != "LIVE_READY"


def test_small_or_null_samples_collect_without_fabricating_zero():
    result = _assess(shadow=_shadow(
        distinct_candidates=2, closed_trades=0, net_expectancy=None, expectancy=None,
        profit_factor=None, max_drawdown=None,
    ))
    assert result["state"] == COLLECTING
    assert result["evidence"]["net_expectancy_after_costs"] is None
    by_gate = {row["gate"]: row for row in result["blockers"]}
    assert by_gate["distinct_candidates"]["status"] == COLLECTING
    assert by_gate["profit_factor"]["observed"] is None


@pytest.mark.parametrize("changes,gate", [
    ({"net_expectancy": -1.0}, "net_expectancy_after_costs"),
    ({"profit_factor": 1.0}, "profit_factor"),
    ({"max_drawdown": 1001.0}, "max_drawdown"),
    ({"accepts": 100, "raw_accepts": 100, "distinct_candidates": 30}, "repeat_inflation"),
])
def test_mature_but_failed_quality_gate_is_ineligible(changes, gate):
    result = _assess(shadow=_shadow(**changes))
    assert result["state"] == INELIGIBLE
    assert next(row for row in result["blockers"] if row["gate"] == gate)["status"] == INELIGIBLE


def test_oos_reconciliation_and_provenance_fail_closed_differently():
    collecting = _assess(runs=[])
    assert collecting["state"] == COLLECTING
    assert {row["gate"] for row in collecting["blockers"]} >= {"oos_folds", "data_provenance"}

    mismatch = _assess(reconciliation={"status": "MISMATCH"})
    assert mismatch["state"] == INELIGIBLE
    unavailable_run = _run(status="UNAVAILABLE", error="legacy_unknown provenance")
    invalid = _assess(runs=[unavailable_run])
    assert invalid["state"] == INELIGIBLE
    assert invalid["evidence"]["provenance_status"] == "INVALID"

    failed = _assess(runs=[_run(status="FAILED", dataset={})])
    assert failed["state"] == COLLECTING
    assert failed["evidence"]["provenance_status"] == "UNKNOWN"

    degraded = _assess(runs=[_run(dataset={
        "status": "valid", "coverage": [{"missing_minutes_within_span": 2}],
    })])
    assert degraded["state"] == INELIGIBLE
    assert degraded["evidence"]["provenance_status"] == "DEGRADED"


def test_latest_completed_backtest_is_selected_and_timestamped():
    old = _run(run_id="old", completed_at="2026-08-09T10:00:00+00:00")
    new = _run(run_id="new", completed_at="2026-08-11T10:00:00+00:00")
    result = _assess(runs=[new, old])
    assert result["sources"]["backtest_run_id"] == "new"
    assert result["source_timestamps"]["backtest_completed_at"] == new["completed_at"]


def test_fno_target_scenario_is_not_misrepresented_as_realised_profitability():
    shadow = {"variants": [{
        "variant": "FNO_BASE", "evaluations": 100,
        "accepted_evaluations": 40, "distinct_candidates": 30,
        "estimated_post_cost": {"available_samples": 30, "estimated_net_pnl": 99999},
    }]}
    result = assess_promotion_readiness(
        "FNO", "FNO_BASE", shadow_comparison=shadow,
        reconciliation={"status": "MATCH"},
    )
    assert result["state"] == COLLECTING
    assert result["evidence"]["closed_trades"] is None
    assert result["evidence"]["net_expectancy_after_costs"] is None


def test_legacy_ready_for_live_is_explicitly_weaker_and_never_authoritative():
    legacy = {"verdict": "ready_for_live", "trades": 100, "expectancy": 50}
    candidate = _assess(legacy=legacy)
    assert candidate["state"] == CANDIDATE
    compat = candidate["legacy_compatibility"]
    assert compat["legacy_verdict"] == "ready_for_live"
    assert compat["sufficient_for_this_decision"] is False
    assert "ledger-only" in compat["warning"]

    no_research = _assess(
        shadow={"variants": []}, runs=[], reconciliation={"status": "UNAVAILABLE"},
        legacy=legacy,
    )
    assert no_research["state"] == COLLECTING


def test_thresholds_are_static_immutable_and_module_has_no_execution_imports():
    with pytest.raises(TypeError):
        THRESHOLDS["NEW"] = THRESHOLDS["PENNY"]
    with pytest.raises(FrozenInstanceError):
        THRESHOLDS["PENNY"].minimum_closed_trades = 1
    tree = ast.parse((Path(__file__).parents[1] / "promotion_readiness.py").read_text(encoding="utf-8"))
    imports = {
        alias.name.lower() for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    assert not any(token in name for name in imports for token in ("kite", "executor", "order", "config"))


def test_strict_json_is_deterministic_and_sanitizes_nonfinite_evidence():
    report = _assess()
    report["evidence"]["diagnostic"] = float("nan")
    report["source_timestamps"]["object_time"] = datetime(2026, 8, 10, tzinfo=timezone.utc)
    first = readiness_json(report)
    assert first == readiness_json(report)
    assert "NaN" not in first and json.loads(first)["evidence"]["diagnostic"] is None
    assert json.loads(first)["source_timestamps"]["object_time"] == "2026-08-10T00:00:00+00:00"


def test_invalid_strategy_or_variant_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        assess_promotion_readiness("UNKNOWN", "X", shadow_comparison={})
    with pytest.raises(ValueError, match="variant"):
        assess_promotion_readiness("PENNY", "", shadow_comparison={})


@pytest.mark.parametrize("status,expected", [
    ("FAILED", COLLECTING),
    ("UNAVAILABLE", INELIGIBLE),
])
def test_nullable_legacy_run_fields_fail_closed_and_never_produce_candidate(status, expected):
    malformed = {
        "run_id": "legacy-malformed", "strategy_id": "momentum_intraday_15m_replay",
        "status": status, "completed_at": "2026-08-10T11:00:00+00:00",
        "config": None, "result": None, "summary": {"oos": None}, "dataset": None,
    }
    result = _assess(runs=[malformed])
    assert result["state"] == expected
    assert result["state"] != CANDIDATE
    assert result["evidence"]["oos_scored_folds"] is None
    assert result["evidence"]["provenance_status"] == (
        "UNKNOWN" if status == "FAILED" else "INVALID"
    )
    assert {row["gate"] for row in result["blockers"]} >= {
        "oos_folds", "data_provenance",
    }
