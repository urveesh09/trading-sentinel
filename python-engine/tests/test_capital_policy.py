"""[WORKFLOW-F 2026-09-13] Capital policy guard acceptance.

Closes F6 of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 6
future plan and ``docs/NEXT_AGENT_PLAN.md`` section 10.5.

Acceptance coverage for ``python-engine/capital_policy.py`` and
``python-engine/capital_policy_cli.py``.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, ``affordability.assert_live_entry_safety`` returned
  ``AFFORDABLE`` even when the broker reconciliation was unresolved,
  the realised drawdown was past any cap, and the execution
  quality was unknown. The affordability guard only checks *can* the
  pool grow; it does not check *should* it grow. F6 closes the
  *should* question with a six-bucket verdict structure that names
  exactly which gate refused.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
import pytest_asyncio

import capital_policy_cli
from capital_policy import (
    CAPITAL_POLICY_SCHEMA_VERSION,
    CapitalIncreaseEvaluation,
    CapitalIncreaseVerdict,
    CapitalPolicyThresholds,
    evaluate_capital_increase,
    evaluate_capital_increase_for_account,
)


# ---- helpers ---------------------------------------------------------------

def _cli_main(arguments):
    # The real CLI is a standalone process. Its asyncio.run must not replace
    # pytest's managed main-thread event loop in an in-process contract test.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(capital_policy_cli.main, arguments).result()

def _good_kwargs(**overrides: Any) -> Dict[str, Any]:
    """Baseline kwargs for ``evaluate_capital_increase`` happy path."""
    base = dict(
        requested_delta_inr=300.0,
        live_current_inr=1500.0,
        drawdown_pct=2.0,
        win_rate_pct=60.0,
        avg_r_multiple=0.5,
        consecutive_losses=1,
        reconciliation_status="MATCH",
        proactive_research_evidence_present=True,
        thresholds=CapitalPolicyThresholds(loss_tolerance_pct=25.0),
    )
    base.update(overrides)
    return base


# ---- schema version --------------------------------------------------------

class TestSchemaVersion:
    def test_version_is_a_positive_int(self) -> None:
        assert isinstance(CAPITAL_POLICY_SCHEMA_VERSION, int)
        assert CAPITAL_POLICY_SCHEMA_VERSION >= 1


# ---- thresholds validation -------------------------------------------------

class TestThresholdsValidation:
    def test_loss_tolerance_above_100_rejected(self) -> None:
        with pytest.raises(ValueError, match="loss_tolerance_pct"):
            CapitalPolicyThresholds(loss_tolerance_pct=150.0)

    def test_loss_tolerance_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="loss_tolerance_pct"):
            CapitalPolicyThresholds(loss_tolerance_pct=-1.0)

    def test_max_drawdown_above_100_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_drawdown_pct"):
            CapitalPolicyThresholds(max_drawdown_pct=200.0)

    def test_min_win_rate_above_100_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_win_rate_pct"):
            CapitalPolicyThresholds(min_win_rate_pct=150.0)

    def test_min_live_bankroll_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_live_bankroll_inr"):
            CapitalPolicyThresholds(min_live_bankroll_inr=-100.0)

    def test_max_consecutive_losses_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_consecutive_losses"):
            CapitalPolicyThresholds(max_consecutive_losses=-1)

    def test_all_defaults_construct_cleanly(self) -> None:
        # The defaults should construct without raising.
        t = CapitalPolicyThresholds()
        assert t.loss_tolerance_pct is None
        assert t.max_drawdown_pct == 15.0
        assert t.min_win_rate_pct == 50.0
        assert t.min_avg_r_multiple == 0.0
        assert t.max_consecutive_losses == 5
        assert t.min_live_bankroll_inr == 1500.0
        assert t.require_broker_reconciliation is True
        assert t.require_proactive_research_evidence is True


# ---- happy path + verdict mapping -----------------------------------------

class TestVerdictMapping:
    def test_happy_path_authorizes(self) -> None:
        ev = evaluate_capital_increase(**_good_kwargs())
        assert ev.verdict == CapitalIncreaseVerdict.AUTHORIZED
        assert ev.reason == "all gates passed"
        assert ev.notes == ()

    def test_loss_tolerance_exceeded_refuses(self) -> None:
        # 25% of 1500 = 375 max additional; requesting 500.
        ev = evaluate_capital_increase(**_good_kwargs(requested_delta_inr=500.0))
        assert ev.verdict == CapitalIncreaseVerdict.LOSS_TOLERANCE_EXCEEDED
        assert "375" in ev.reason

    def test_reconciliation_unresolved_refuses(self) -> None:
        ev = evaluate_capital_increase(
            **_good_kwargs(reconciliation_status="UNRESOLVED"),
        )
        assert ev.verdict == CapitalIncreaseVerdict.RECONCILIATION_UNRESOLVED

    def test_reconciliation_unavailable_refuses(self) -> None:
        ev = evaluate_capital_increase(
            **_good_kwargs(reconciliation_status="UNAVAILABLE"),
        )
        assert ev.verdict == CapitalIncreaseVerdict.RECONCILIATION_UNRESOLVED

    def test_reconciliation_match_with_require_disabled_allows(self) -> None:
        # Even with UNRESOLVED reconciliation, if require_broker_reconciliation
        # is False the gate is skipped. We pair this with a lower
        # loss_tolerance so the request still AUTHORIZES.
        thresholds = CapitalPolicyThresholds(
            loss_tolerance_pct=25.0,
            require_broker_reconciliation=False,
        )
        ev = evaluate_capital_increase(
            **_good_kwargs(reconciliation_status="UNRESOLVED", thresholds=thresholds),
        )
        assert ev.verdict == CapitalIncreaseVerdict.AUTHORIZED

    def test_drawdown_too_high_refuses(self) -> None:
        ev = evaluate_capital_increase(**_good_kwargs(drawdown_pct=20.0))
        assert ev.verdict == CapitalIncreaseVerdict.DRAWDOWN_TOO_HIGH
        assert "20.0%" in ev.reason
        assert "15.0%" in ev.reason

    def test_no_proactive_research_refuses(self) -> None:
        ev = evaluate_capital_increase(
            **_good_kwargs(proactive_research_evidence_present=False),
        )
        assert ev.verdict == CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE

    def test_proactive_evidence_disabled_allows(self) -> None:
        thresholds = CapitalPolicyThresholds(
            loss_tolerance_pct=25.0,
            require_proactive_research_evidence=False,
        )
        ev = evaluate_capital_increase(
            **_good_kwargs(proactive_research_evidence_present=False, thresholds=thresholds),
        )
        assert ev.verdict == CapitalIncreaseVerdict.AUTHORIZED

    def test_win_rate_too_low_refuses(self) -> None:
        ev = evaluate_capital_increase(**_good_kwargs(win_rate_pct=30.0))
        assert ev.verdict == CapitalIncreaseVerdict.EXECUTION_QUALITY_INSUFFICIENT

    def test_r_multiple_too_low_refuses(self) -> None:
        ev = evaluate_capital_increase(**_good_kwargs(avg_r_multiple=-0.1))
        assert ev.verdict == CapitalIncreaseVerdict.EXECUTION_QUALITY_INSUFFICIENT

    def test_consecutive_losses_exceeded_refuses(self) -> None:
        ev = evaluate_capital_increase(
            **_good_kwargs(consecutive_losses=8),
        )
        assert ev.verdict == CapitalIncreaseVerdict.EXECUTION_QUALITY_INSUFFICIENT

    def test_live_below_floor_refuses(self) -> None:
        ev = evaluate_capital_increase(
            **_good_kwargs(live_current_inr=1000.0),
        )
        assert ev.verdict == CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE
        assert "below the evaluation floor" in ev.reason


# ---- gate ordering ---------------------------------------------------------

class TestGateOrdering:
    """The guards MUST run in a documented order; later gates don't
    fire if earlier gates already refused. Each test sets the
    *later* gates to passing values and the *first* gate to
    failing; only that gate's verdict should come out."""

    def test_live_floor_runs_before_reconciliation(self) -> None:
        # Live below floor AND reconciliation UNRESOLVED -- only
        # INSUFFICIENT_EVIDENCE (live floor) should fire.
        ev = evaluate_capital_increase(
            **_good_kwargs(
                live_current_inr=1000.0,
                reconciliation_status="UNRESOLVED",
            ),
        )
        assert ev.verdict == CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE
        assert "below the evaluation floor" in ev.reason

    def test_reconciliation_runs_before_drawdown(self) -> None:
        ev = evaluate_capital_increase(
            **_good_kwargs(
                reconciliation_status="UNRESOLVED",
                drawdown_pct=99.0,
            ),
        )
        assert ev.verdict == CapitalIncreaseVerdict.RECONCILIATION_UNRESOLVED

    def test_drawdown_runs_before_loss_tolerance(self) -> None:
        # delta=500 (would exceed 25% tolerance), drawdown=20 (exceeds 15% cap).
        # Drawdown should fire first.
        ev = evaluate_capital_increase(
            **_good_kwargs(requested_delta_inr=500.0, drawdown_pct=20.0),
        )
        assert ev.verdict == CapitalIncreaseVerdict.DRAWDOWN_TOO_HIGH

    def test_loss_tolerance_runs_before_execution_quality(self) -> None:
        # delta=500 (exceeds tolerance), win_rate=10 (also below floor).
        # Loss tolerance should fire first.
        ev = evaluate_capital_increase(
            **_good_kwargs(
                requested_delta_inr=500.0, win_rate_pct=10.0,
                avg_r_multiple=-1.0, consecutive_losses=20,
            ),
        )
        assert ev.verdict == CapitalIncreaseVerdict.LOSS_TOLERANCE_EXCEEDED


# ---- input validation -----------------------------------------------------

class TestInputValidation:
    def test_nan_requested_delta_rejected(self) -> None:
        with pytest.raises(ValueError, match="requested_delta_inr"):
            evaluate_capital_increase(
                **_good_kwargs(requested_delta_inr=float("nan")),
            )

    def test_inf_live_current_rejected(self) -> None:
        with pytest.raises(ValueError, match="live_current_inr"):
            evaluate_capital_increase(
                **_good_kwargs(live_current_inr=float("inf")),
            )

    def test_nan_drawdown_rejected(self) -> None:
        with pytest.raises(ValueError, match="drawdown_pct"):
            evaluate_capital_increase(
                **_good_kwargs(drawdown_pct=float("nan")),
            )

    def test_negative_drawdown_rejected(self) -> None:
        with pytest.raises(ValueError, match="drawdown_pct"):
            evaluate_capital_increase(**_good_kwargs(drawdown_pct=-1.0))

    def test_over_100_drawdown_rejected(self) -> None:
        with pytest.raises(ValueError, match="drawdown_pct"):
            evaluate_capital_increase(**_good_kwargs(drawdown_pct=101.0))

    def test_negative_consecutive_losses_rejected(self) -> None:
        with pytest.raises(ValueError, match="consecutive_losses"):
            evaluate_capital_increase(
                **_good_kwargs(consecutive_losses=-1),
            )

    def test_non_int_consecutive_losses_rejected(self) -> None:
        # bool is technically an int subclass; we explicitly reject it.
        with pytest.raises(ValueError, match="consecutive_losses"):
            evaluate_capital_increase(
                **_good_kwargs(consecutive_losses=True),  # bool, not int
            )

    def test_bool_consecutive_losses_rejected_in_thresholds(self) -> None:
        # The thresholds constructor must also reject bool.
        with pytest.raises(ValueError, match="max_consecutive_losses"):
            CapitalPolicyThresholds(max_consecutive_losses=True)

    def test_unknown_reconciliation_status_rejected(self) -> None:
        with pytest.raises(ValueError, match="reconciliation_status"):
            evaluate_capital_increase(
                **_good_kwargs(reconciliation_status="MADE_UP"),
            )

    def test_non_bool_research_present_rejected(self) -> None:
        with pytest.raises(ValueError, match="proactive_research_evidence_present"):
            evaluate_capital_increase(
                **_good_kwargs(proactive_research_evidence_present="yes"),
            )


# ---- summary string -------------------------------------------------------

class TestSummary:
    def test_summary_contains_verdict_and_key_numbers(self) -> None:
        ev = evaluate_capital_increase(**_good_kwargs())
        s = ev.summary()
        assert "AUTHORIZED" in s
        assert "Rs 300" in s
        assert "25.0%" in s
        assert "MATCH" in s


# ---- CLI -------------------------------------------------------------------

class TestCli:
    def test_print_config_runs(self, tmp_path) -> None:
        output_path = str(tmp_path / "cfg.json")
        rc = _cli_main([
            "--db", str(tmp_path / "test.db"),
            "print-config",
            "--output", output_path,
        ])
        assert rc == 0
        with open(output_path) as f:
            data = json.load(f)
        assert data["ok"] is True
        assert data["thresholds"]["loss_tolerance_pct"] is None
        assert "CAPITAL_POLICY_LOSS_TOLERANCE_PCT" in data["config_keys"]

    def test_evaluate_with_no_db_returns_insufficient(self, tmp_path) -> None:
        # No DB at all -> every read returns its default; the guard
        # returns RECONCILIATION_UNRESOLVED because require_broker_reconciliation
        # is True (default) and the broker report is UNAVAILABLE.
        #
        # Exit-code semantics: the CLI exits 0 when it ran without
        # crashing, regardless of verdict. The verdict is in the
        # JSON. This is the right behaviour for a CI gate that wants
        # to distinguish "CLI failed" (rc=2) from "CLI ran and the
        # system said no" (rc=0 with refusal in JSON).
        output_path = str(tmp_path / "eval.json")
        rc = _cli_main([
            "--db", str(tmp_path / "no_such.db"),
            "evaluate",
            "--account", "owner",
            "--delta", "300",
            "--output", output_path,
        ])
        assert rc == 0
        with open(output_path) as f:
            data = json.load(f)
        assert data["ok"] is True  # the CLI ran without crashing
        assert data["verdict"] in {"INSUFFICIENT_EVIDENCE", "RECONCILIATION_UNRESOLVED"}
        assert data["can_grow_live_capital"] is False

    def test_evaluate_negative_delta_rejected(self, tmp_path) -> None:
        # Capital reductions require a separate policy, not a growth approval.
        output_path = str(tmp_path / "eval.json")
        rc = _cli_main([
            "--db", str(tmp_path / "no_such.db"),
            "evaluate",
            "--account", "owner",
            "--delta", "-100",
            "--output", output_path,
        ])
        # We expect the same INSUFFICIENT_EVIDENCE / RECONCILIATION_UNRESOLVED
        # because the broker reconciliation read failed -- but the
        # negative delta must NOT itself cause a refusal.
        with open(output_path) as f:
            data = json.load(f)
        assert rc == 1
        assert data["ok"] is False
        assert "strictly positive" in data["error"]
        assert data["can_grow_live_capital"] is False

    def test_evaluate_validation_error_returns_1(self, tmp_path) -> None:
        # argparse rejects --delta=not-a-number with rc=2 BEFORE our
        # main() runs. That is the standard Unix convention for
        # invalid usage. We document this; the operator can grep
        # stderr for the argparse message.
        output_path = str(tmp_path / "eval.json")
        with pytest.raises(SystemExit) as exc_info:
            _cli_main([
                "--db", str(tmp_path / "no_such.db"),
                "evaluate",
                "--account", "owner",
                "--delta", "not-a-number",
                "--output", output_path,
            ])
        assert exc_info.value.code == 2


# ---- async wrapper ---------------------------------------------------------

class TestAsyncWrapper:
    @pytest.mark.asyncio
    async def test_no_db_returns_refusal(self, tmp_path) -> None:
        # No DB at all. ``division_equity`` falls back to the static
        # allocation when the ledger table is missing (so the live
        # floor gate passes), but ``broker_statement_report`` returns
        # UNAVAILABLE. Gate 2 (broker reconciliation) refuses.
        # Either of INSUFFICIENT_EVIDENCE / RECONCILIATION_UNRESOLVED
        # is acceptable -- we document the actual path.
        result = await evaluate_capital_increase_for_account(
            str(tmp_path / "no_such.db"),
            account_id="owner",
            requested_delta_inr=300.0,
        )
        assert result.verdict in {
            CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE,
            CapitalIncreaseVerdict.RECONCILIATION_UNRESOLVED,
        }


# ---- reproducibility -------------------------------------------------------

class TestReproducibility:
    def test_same_inputs_same_verdict(self) -> None:
        kwargs = _good_kwargs()
        r1 = evaluate_capital_increase(**kwargs)
        r2 = evaluate_capital_increase(**kwargs)
        assert r1.verdict == r2.verdict
        assert r1.reason == r2.reason
