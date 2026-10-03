"""Reporting must describe the complete evidenced sample without selection claims."""
import pytest

from backtest_reporting import standard_metrics, validate_holdout


@pytest.mark.parametrize("values,expected", [([-2, -1], -3), ([0, -2], -2), ([5, -2, 1], -1)])
def test_winner_exclusion_only_removes_a_positive_winner(values, expected):
    report = {"result": {"trades": [{"status": "CLOSED", "net_pnl": v} for v in values]}}
    assert standard_metrics(report)["net_excluding_best_winner"] == expected


def test_partial_trade_fields_do_not_become_full_sample_metrics():
    metrics = standard_metrics({"result": {"trades": [
        {"status": "CLOSED", "net_pnl": 5, "holding_minutes": 10, "mfe_r": 2,
         "mae_r": -1, "exit_date": "2026-08-10"},
        {"status": "CLOSED"},
        {"status": "CLOSED", "net_pnl": float("nan")},
    ]}})
    assert metrics["closed_trades"] == 3
    for field in ("net_pnl", "net_excluding_best_winner", "uncertainty", "win_loss",
                  "holding_minutes", "exposure_minutes", "mfe_r_mean", "mae_r_mean",
                  "monthly_net_pnl"):
        assert metrics[field] is None, field
    assert metrics["field_coverage"]["net_pnl"] == {"present": 1, "closed_trades": 3, "complete": False}


def test_absent_trade_evidence_is_distinct_from_an_archived_empty_sample():
    absent = standard_metrics({"result": {"decisions": []}})
    empty = standard_metrics({"result": {"trades": []}})
    assert absent["closed_trades"] is None and absent["trade_evidence"] == "ABSENT"
    assert empty["closed_trades"] == 0 and empty["trade_evidence"] == "ARCHIVED"
    assert absent["net_pnl"] is None and empty["net_pnl"] is None


def test_full_metrics_and_valid_months_are_preserved():
    trades = [{"status": "CLOSED", "net_pnl": net, "gross_pnl": net + 1,
               "costs": 1, "holding_minutes": 10, "mfe_r": 2, "mae_r": -1,
               "quantity": 2, "entry_fill": 10, "exit_fill": 12, "exit_date": stamp}
              for net, stamp in [(5, "2026-08-10"), (-2, "2026-09-01")]]
    metrics = standard_metrics({"result": {"trades": trades}})
    assert metrics["net_pnl"] == 3 and metrics["gross_pnl"] == 5
    assert metrics["fees_and_costs"] == 2 and metrics["turnover"] == 88
    assert metrics["exposure_minutes"] == 20
    assert metrics["monthly_net_pnl"] == {"2026-08": 5, "2026-09": -2}
    assert metrics["uncertainty"] is not None
    trades[1]["exit_date"] = "not-a-date"
    assert standard_metrics({"result": {"trades": trades}})["monthly_net_pnl"] is None


def test_past_dates_do_not_prove_an_untouched_holdout():
    declaration = validate_holdout("2026-08-10", "2026-08-10", "2026-08-11", "2026-08-12")
    assert declaration["status"] == "DECLARED_UNVERIFIED"
    assert declaration["untouched_verified"] is False
    assert "prior-use audit" in declaration["reason"]
