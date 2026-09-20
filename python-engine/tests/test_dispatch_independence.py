"""[WORKFLOW-A.5 2026-09-17] Tests for dispatch independence
verification.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Keep final dispatch revalidation independent: source
> availability does not grant transport authority.

The live dispatcher in ``partner_orchestrator._send_event``
implements these gates already. This module pins the
contract so the audit pipeline can verify it without
mocking the entire dispatcher.

These tests cover:

  - ``check_dispatch_gates`` -- pure gate evaluation from
    explicit boolean inputs.
  - ``DispatchGateReport`` -- aggregate report with
    ``overall_ok`` and ``failed_gates()``.
  - ``dispatch_independence_assertion`` -- structured
    explanation string for audit logs.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from dispatch_independence import (  # noqa: E402  -- import path
    DispatchGateReport,
    DispatchGateStatus,
    GateOutcome,
    check_dispatch_gates,
    dispatch_independence_assertion,
)


IST = ZoneInfo("Asia/Kolkata")


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 14, hour, minute, tzinfo=IST)


def _all_pass_args(now=None):
    if now is None:
        now = _at(10, 0)
    return dict(
        now=now, enabled=True,
        session_open_minute=9*60 + 15,
        session_close_minute=15*60 + 30,
        is_trading_day=True, token_fresh=True,
    )


# -- 1. check_dispatch_gates: all pass -----------------------


def test_all_gates_pass_for_normal_session():
    report = check_dispatch_gates(**_all_pass_args())
    assert report.enabled.outcome == GateOutcome.PASS
    assert report.in_session_window.outcome == GateOutcome.PASS
    assert report.is_trading_day.outcome == GateOutcome.PASS
    assert report.fresh_token.outcome == GateOutcome.PASS
    assert report.overall_ok is True


def test_overall_ok_true_when_all_gates_pass():
    report = check_dispatch_gates(**_all_pass_args())
    assert report.overall_ok is True


def test_failed_gates_empty_when_all_pass():
    report = check_dispatch_gates(**_all_pass_args())
    assert report.failed_gates() == ()


# -- 2. Per-gate failures -----------------------------------


def test_enabled_false_fails_enabled_gate():
    args = _all_pass_args()
    args["enabled"] = False
    report = check_dispatch_gates(**args)
    assert report.enabled.outcome == GateOutcome.FAIL
    assert report.overall_ok is False
    assert "enabled" in report.failed_gates()


def test_outside_session_window_fails_in_session_window_gate():
    args = _all_pass_args()
    args["now"] = _at(16, 0)  # after 15:30
    report = check_dispatch_gates(**args)
    assert report.in_session_window.outcome == GateOutcome.FAIL
    assert report.overall_ok is False
    assert "in_session_window" in report.failed_gates()


def test_just_before_session_open_fails():
    args = _all_pass_args()
    args["now"] = _at(9, 14)  # 1 min before 9:15
    report = check_dispatch_gates(**args)
    assert report.in_session_window.outcome == GateOutcome.FAIL


def test_just_after_session_close_fails():
    args = _all_pass_args()
    args["now"] = _at(15, 31)  # 1 min after 15:30
    report = check_dispatch_gates(**args)
    assert report.in_session_window.outcome == GateOutcome.FAIL


def test_non_trading_day_fails_trading_day_gate():
    args = _all_pass_args()
    args["is_trading_day"] = False
    report = check_dispatch_gates(**args)
    assert report.is_trading_day.outcome == GateOutcome.FAIL
    assert "is_trading_day" in report.failed_gates()


def test_stale_token_fails_fresh_token_gate():
    args = _all_pass_args()
    args["token_fresh"] = False
    report = check_dispatch_gates(**args)
    assert report.fresh_token.outcome == GateOutcome.FAIL
    assert "fresh_token" in report.failed_gates()


def test_multiple_gates_can_fail_simultaneously():
    args = _all_pass_args()
    args["enabled"] = False
    args["token_fresh"] = False
    args["is_trading_day"] = False
    report = check_dispatch_gates(**args)
    assert len(report.failed_gates()) == 3
    assert "enabled" in report.failed_gates()
    assert "fresh_token" in report.failed_gates()
    assert "is_trading_day" in report.failed_gates()


# -- 3. DispatchGateReport ----------------------------------


def test_failed_gates_lists_in_order():
    args = _all_pass_args()
    args["enabled"] = False
    args["token_fresh"] = False
    report = check_dispatch_gates(**args)
    failed = report.failed_gates()
    assert failed.index("enabled") < failed.index("fresh_token")


def test_to_dict_includes_all_gates():
    report = check_dispatch_gates(**_all_pass_args())
    d = report.to_dict()
    assert set(d.keys()) == {
        "enabled", "in_session_window", "is_trading_day",
        "fresh_token", "overall_ok", "failed_gates",
    }
    assert d["overall_ok"] is True
    assert d["failed_gates"] == []


def test_to_dict_includes_failed_gates_list():
    args = _all_pass_args()
    args["enabled"] = False
    report = check_dispatch_gates(**args)
    d = report.to_dict()
    assert "enabled" in d["failed_gates"]


# -- 4. dispatch_independence_assertion ---------------------


def _good_report():
    return check_dispatch_gates(**_all_pass_args())


def _bad_report():
    args = _all_pass_args()
    args["token_fresh"] = False
    return check_dispatch_gates(**args)


def test_assertion_ok_when_source_and_gates_pass():
    text = dispatch_independence_assertion(
        source_data_captured=True,
        candidate_constructed=True,
        dispatch_report=_good_report(),
    )
    assert "DISPATCH_INDEPENDENCE_OK" in text


def test_assertion_suppressed_by_gates_when_source_present_but_gates_fail():
    """[WORKFLOW-A.5 2026-09-17] The plan's rule: source
    availability does NOT grant transport authority. Even
    when source+candidate are ready, the dispatcher must
    NOT send unless gates pass."""
    text = dispatch_independence_assertion(
        source_data_captured=True,
        candidate_constructed=True,
        dispatch_report=_bad_report(),
    )
    assert "DISPATCH_SUPPRESSED_BY_GATES" in text
    assert "fresh_token" in text


def test_assertion_not_triggered_when_source_not_captured():
    text = dispatch_independence_assertion(
        source_data_captured=False,
        candidate_constructed=False,
        dispatch_report=_good_report(),
    )
    assert "DISPATCH_NOT_TRIGGERED" in text
    assert "source not captured" in text


def test_assertion_not_triggered_when_candidate_not_constructed():
    text = dispatch_independence_assertion(
        source_data_captured=True,
        candidate_constructed=False,
        dispatch_report=_good_report(),
    )
    assert "DISPATCH_NOT_TRIGGERED" in text
    assert "candidate not constructed" in text


def test_assertion_includes_audit_language():
    """[WORKFLOW-A.5 2026-09-17] The output must include
    audit-language so operators can grep for it."""
    text = dispatch_independence_assertion(
        source_data_captured=True,
        candidate_constructed=True,
        dispatch_report=_bad_report(),
    )
    assert "Source availability does NOT grant transport authority" in text


# -- 5. Per-gate exit codes ---------------------------------


def test_gate_outcome_exit_code():
    assert GateOutcome.PASS.exit_code() == 0
    assert GateOutcome.FAIL.exit_code() == 1
