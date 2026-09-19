"""[WORKFLOW-F.8 2026-09-17] Tests for the cost-per-trade
audit.

Per Workstream F in NEXT_AGENT_PLAN.md:
> Audit true cost per trade relative to expected edge for
> INR 8k capital. Prevent a large configured paper
> bankroll from implying owner live affordability.

These tests pin the cost/edge classification:

  - CostSeverity CHEAP / REASONABLE / EXPENSIVE / BREACH.
  - ``audit_costs`` aggregates per-trade costs.
  - Breach count = trades with cost_to_edge > threshold.
  - Empty input returns a "no records" report.
  - Defensive strategy (negative edge) -> ratio is None.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from cost_audit import (  # noqa: E402  -- import path
    CostAuditReport,
    CostSeverity,
    TradeCost,
    audit_costs,
)


# -- 1. CostSeverity enum -----------------------------------


def test_cost_severity_has_four_values():
    assert {s.value for s in CostSeverity} == {
        "CHEAP", "REASONABLE", "EXPENSIVE", "BREACH",
    }


# -- 2. Per-trade classification -----------------------------


def test_cheap_trade_classification():
    """[WORKFLOW-F.8 2026-09-17] cost/edge <= 0.25 = CHEAP."""
    trades = [{
        "trade_id": "t1", "broker_fees": 5, "slippage": 5,
        "charges": 5, "expected_edge": 100,
    }]  # cost=15, ratio=0.15.
    r = audit_costs(trades)
    assert r.trades[0].severity == CostSeverity.CHEAP


def test_expensive_trade_classification():
    """[WORKFLOW-F.8 2026-09-17] 0.5 < cost/edge <= 1.0
    = EXPENSIVE."""
    trades = [{
        "trade_id": "t1", "broker_fees": 30, "slippage": 20,
        "charges": 30, "expected_edge": 100,
    }]  # cost=80, ratio=0.8.
    r = audit_costs(trades)
    assert r.trades[0].severity == CostSeverity.EXPENSIVE


def test_breach_trade_classification():
    """[WORKFLOW-F.8 2026-09-17] cost/edge > 1.0 = BREACH
    (cost exceeds edge)."""
    trades = [{
        "trade_id": "t1", "broker_fees": 50, "slippage": 30,
        "charges": 30, "expected_edge": 50,
    }]  # cost=110, ratio=2.2.
    r = audit_costs(trades)
    assert r.trades[0].severity == CostSeverity.BREACH


def test_zero_expected_edge_means_no_ratio():
    """[WORKFLOW-F.8 2026-09-17] Defensive strategy with
    negative expected edge -> ratio is None (can't classify
    the cost against an expected loss)."""
    trades = [{
        "trade_id": "t1", "broker_fees": 5, "slippage": 2,
        "charges": 3, "expected_edge": -100,
    }]
    r = audit_costs(trades)
    assert r.trades[0].cost_to_edge_ratio is None
    # With no expected edge, default to EXPENSIVE.
    assert r.trades[0].severity == CostSeverity.EXPENSIVE


# -- 3. Aggregate stats -------------------------------------


def test_total_cost_is_sum_of_components():
    trades = [
        {"trade_id": "t1", "broker_fees": 10, "slippage": 5,
         "charges": 5, "expected_edge": 100},  # 20
        {"trade_id": "t2", "broker_fees": 20, "slippage": 10,
         "charges": 10, "expected_edge": 100},  # 40
    ]
    r = audit_costs(trades)
    assert r.total_cost == 60.0
    assert r.total_edge == 200.0


def test_mean_cost_to_edge_averages_ratios():
    trades = [
        {"trade_id": "t1", "broker_fees": 10, "slippage": 5,
         "charges": 5, "expected_edge": 100},  # ratio=0.2
        {"trade_id": "t2", "broker_fees": 20, "slippage": 10,
         "charges": 10, "expected_edge": 100},  # ratio=0.4
    ]
    r = audit_costs(trades)
    # mean(0.2, 0.4) = 0.3.
    assert r.mean_cost_to_edge == pytest.approx(0.3)


def test_mean_cost_to_edge_excludes_defensive_trades():
    """[WORKFLOW-F.8 2026-09-17] Trades with expected_edge <= 0
    are excluded from the mean (their ratio is None)."""
    trades = [
        {"trade_id": "t1", "broker_fees": 5, "slippage": 5,
         "charges": 5, "expected_edge": 100},  # ratio=0.15
        {"trade_id": "t2", "broker_fees": 5, "slippage": 5,
         "charges": 5, "expected_edge": -100},  # excluded
    ]
    r = audit_costs(trades)
    # Only t1 contributes: 15/100 = 0.15.
    assert r.mean_cost_to_edge == pytest.approx(0.15)


def test_worst_trade_is_highest_ratio():
    trades = [
        {"trade_id": "t1", "broker_fees": 10, "slippage": 5,
         "charges": 5, "expected_edge": 100},  # ratio=0.2
        {"trade_id": "t2", "broker_fees": 50, "slippage": 30,
         "charges": 30, "expected_edge": 50},  # ratio=2.2 (worst)
        {"trade_id": "t3", "broker_fees": 5, "slippage": 5,
         "charges": 5, "expected_edge": 50},  # ratio=0.3
    ]
    r = audit_costs(trades)
    assert r.worst_trade.trade_id == "t2"


def test_breach_count_counts_only_breaches():
    trades = [
        {"trade_id": "t1", "broker_fees": 10, "slippage": 5,
         "charges": 5, "expected_edge": 100},  # ratio=0.2 (no breach)
        {"trade_id": "t2", "broker_fees": 50, "slippage": 30,
         "charges": 30, "expected_edge": 50},  # ratio=2.2 (breach)
        {"trade_id": "t3", "broker_fees": 60, "slippage": 0,
         "charges": 0, "expected_edge": 50},  # ratio=1.2 (breach)
    ]
    r = audit_costs(trades)
    assert r.breach_count == 2
    assert r.threshold_breach_ratio == pytest.approx(2 / 3)


def test_breach_threshold_is_configurable():
    """[WORKFLOW-F.8 2026-09-17] Operators can tighten
    the threshold for stricter audit."""
    trades = [{
        "trade_id": "t1", "broker_fees": 50, "slippage": 30,
        "charges": 30, "expected_edge": 100,  # ratio=1.1
    }]
    # Default threshold 1.0 -> BREACH.
    r = audit_costs(trades)
    assert r.breach_count == 1
    # Tighter threshold 0.5 -> also BREACH (since ratio=1.1 > 0.5).
    r = audit_costs(trades, breach_threshold=0.5)
    assert r.breach_count == 1
    # Looser threshold 2.0 -> not BREACH.
    r = audit_costs(trades, breach_threshold=2.0)
    assert r.breach_count == 0


# -- 4. Empty input ----------------------------------------


def test_empty_input_returns_empty_report():
    r = audit_costs([])
    assert r.trades == ()
    assert r.total_cost == 0.0
    assert r.total_edge == 0.0
    assert r.mean_cost_to_edge is None
    assert r.worst_trade is None
    assert r.breach_count == 0
    assert "no trade records" in r.notes[0]


def test_invalid_trade_dicts_are_skipped():
    """[WORKFLOW-F.8 2026-09-17] Non-dict trades in the
    input are silently skipped (defensive against bad
    upstream data)."""
    trades = [
        "not a dict",
        {"trade_id": "t1", "broker_fees": 5, "slippage": 5,
         "charges": 5, "expected_edge": 100},
        None,
        42,
    ]
    r = audit_costs(trades)
    assert len(r.trades) == 1
    assert r.trades[0].trade_id == "t1"


# -- 5. Notes ------------------------------------------------


def test_notes_say_sustainable_when_no_breaches():
    trades = [
        {"trade_id": "t1", "broker_fees": 5, "slippage": 5,
         "charges": 5, "expected_edge": 100},
    ]
    r = audit_costs(trades)
    assert any("sustainable" in n for n in r.notes)


def test_notes_warn_when_breaches_exceed_threshold():
    trades = [
        {"trade_id": "t1", "broker_fees": 50, "slippage": 30,
         "charges": 30, "expected_edge": 50},
    ]
    r = audit_costs(trades)
    assert any("exceeded breach_threshold" in n for n in r.notes)


def test_notes_warn_when_mean_cost_to_edge_high():
    trades = [
        {"trade_id": "t1", "broker_fees": 50, "slippage": 30,
         "charges": 30, "expected_edge": 50},  # ratio=2.2
        {"trade_id": "t2", "broker_fees": 50, "slippage": 30,
         "charges": 30, "expected_edge": 100},  # ratio=1.1
    ]
    r = audit_costs(trades)
    # mean = 1.65 > 0.5.
    assert any("cost_to_edge" in n and "burden" in n
                 for n in r.notes)


# -- 6. dataclass serialization -----------------------------


def test_trade_cost_to_dict_includes_required_fields():
    trades = [{
        "trade_id": "t1", "broker_fees": 5, "slippage": 2,
        "charges": 3, "expected_edge": 100,
    }]
    r = audit_costs(trades)
    d = r.trades[0].to_dict()
    expected = {"trade_id", "broker_fees", "slippage", "charges",
                "total_cost", "expected_edge", "cost_to_edge_ratio",
                "severity"}
    assert set(d.keys()) == expected


def test_cost_audit_report_to_dict_includes_required_fields():
    trades = [{
        "trade_id": "t1", "broker_fees": 5, "slippage": 2,
        "charges": 3, "expected_edge": 100,
    }]
    r = audit_costs(trades)
    d = r.to_dict()
    expected = {"trade_count", "total_cost", "total_edge",
                "mean_cost_to_edge", "worst_trade", "breach_count",
                "threshold_breach_ratio", "notes"}
    assert set(d.keys()) == expected


def test_report_to_dict_serializes_worst_trade():
    trades = [
        {"trade_id": "t1", "broker_fees": 10, "slippage": 5,
         "charges": 5, "expected_edge": 100},
        {"trade_id": "t2", "broker_fees": 50, "slippage": 30,
         "charges": 30, "expected_edge": 50},
    ]
    r = audit_costs(trades)
    d = r.to_dict()
    assert d["worst_trade"] is not None
    assert d["worst_trade"]["trade_id"] == "t2"
