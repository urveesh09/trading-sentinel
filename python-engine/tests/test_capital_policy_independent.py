"""Independent F6 regressions: no fabricated risk input or account authority."""
import pytest

from capital_policy import (CapitalPolicyThresholds, CapitalIncreaseVerdict,
                            evaluate_capital_increase, evaluate_capital_increase_for_account)


def _inputs():
    return dict(requested_delta_inr=300, live_current_inr=1500, drawdown_pct=2,
                win_rate_pct=60, avg_r_multiple=.5, consecutive_losses=1,
                reconciliation_status="MATCH", proactive_research_evidence_present=True)


@pytest.mark.parametrize("delta", [-1, 0, True])
def test_increase_requires_strictly_positive_nonboolean_delta(delta):
    inputs = {**_inputs(), "requested_delta_inr": delta}
    with pytest.raises(ValueError, match="requested_delta_inr"):
        evaluate_capital_increase(**inputs, thresholds=CapitalPolicyThresholds(loss_tolerance_pct=25))


def test_unknown_user_loss_tolerance_refuses_and_stays_unknown():
    result = evaluate_capital_increase(**_inputs())
    assert result.verdict == CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE
    assert result.loss_tolerance_pct is None


@pytest.mark.parametrize("field", ["win_rate_pct", "avg_r_multiple"])
def test_missing_execution_quality_is_not_a_pass(field):
    result = evaluate_capital_increase(**{**_inputs(), field: None},
        thresholds=CapitalPolicyThresholds(loss_tolerance_pct=25))
    assert result.verdict == CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE


@pytest.mark.asyncio
async def test_accountless_wrapper_refuses_without_creating_database(tmp_path):
    path = tmp_path / "never-create.db"
    result = await evaluate_capital_increase_for_account(str(path), account_id="account-B",
        requested_delta_inr=300, thresholds=CapitalPolicyThresholds(loss_tolerance_pct=25))
    assert result.verdict == CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE
    assert "account" in result.reason.lower()
    assert result.live_current_inr is None and result.drawdown_pct is None
    assert not path.exists()


@pytest.mark.parametrize("field", ["loss_tolerance_pct", "max_drawdown_pct", "min_win_rate_pct",
                                    "min_avg_r_multiple", "min_live_bankroll_inr"])
def test_boolean_numeric_threshold_rejected(field):
    with pytest.raises(ValueError, match=field):
        CapitalPolicyThresholds(**{field: True})
