from copy import deepcopy
from datetime import date
import importlib.util
from pathlib import Path
import sqlite3

import pytest

SPEC = importlib.util.spec_from_file_location("fno_assessment", Path(__file__).parents[1] / "assess_fno_profitability.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def evidence():
    return {"tables": {"fno_positions": [
        {"id": 1, "source": "FNO_PAPER", "status": "CLOSED", "pnl": 90., "gross_pnl": 100., "costs": 10.,
         "exit_time": "2026-09-01T10:00:00+05:30"}
    ], "fno_dr_positions": [], "bankroll_ledger": [
        {"id": 2, "source": "FNO_PAPER", "origin_ref": "fno_position:1", "event_type": "TRADE_CLOSED",
         "timestamp": "2026-08-31T20:00:00+00:00", "pnl": 90., "settlement_generation": 1}
    ]}}


def run(s):
    return module.assess(s, date(2026, 9, 1), date(2026, 9, 30))


def test_exact_link_ist_month_and_no_backtest_claim():
    result = run(evidence())
    assert result["reconciliation"]["status"] == "LINKED_CASH_MATCHES_RETAINED_ROWS"
    book = result["books"]["fno_positions:FNO_PAPER"]
    assert book["monthly_realized_cash"]["2026-09"]["net_rs"] == 90
    assert book["closed_lifetime_outcomes"]["net_without_best_winner_rs"] == 0
    assert result["is_historical_backtest"] is False
    assert result["can_qualify"] is False


@pytest.mark.parametrize("case", ["missing", "duplicate", "mismatch", "nan", "wrong_source", "naive", "arithmetic"])
def test_unavailable_evidence_never_counts_as_reconciled_profit(case):
    s = evidence()
    event = s["tables"]["bankroll_ledger"][0]
    if case == "missing":
        s["tables"]["bankroll_ledger"] = []
    elif case == "duplicate":
        extra = deepcopy(event)
        extra["id"] = 3
        s["tables"]["bankroll_ledger"].append(extra)
    elif case == "mismatch":
        event["pnl"] = 999.
    elif case == "nan":
        event["pnl"] = float("nan")
    elif case == "wrong_source":
        event["source"] = "FNO_LIVE"
    elif case == "naive":
        event["timestamp"] = "2026-09-01T10:00:00"
    else:
        s["tables"]["fno_positions"][0]["costs"] = 20.
    result = run(s)
    assert result["reconciliation"]["status"] == "UNAVAILABLE"
    assert result["books"]["fno_positions:FNO_PAPER"]["closed_lifetime_outcomes"]["count"] == 0


def test_prior_window_partial_in_lifetime_not_window_and_not_extra_trade():
    s = evidence()
    extra = deepcopy(s["tables"]["bankroll_ledger"][0])
    extra.update(id=1, event_type="TRADE_PARTIAL", timestamp="2026-08-25T10:00:00Z", pnl=20., settlement_generation=0)
    s["tables"]["bankroll_ledger"].append(extra)
    book = run(s)["books"]["fno_positions:FNO_PAPER"]
    assert book["closed_lifetime_outcomes"]["net_rs"] == 110
    assert book["closed_lifetime_outcomes"]["count"] == 1
    assert book["window_cash"]["net_rs"] == 90


def test_metrics_drawdown_and_empty_are_not_returns():
    result = module.metrics([100, -40, -80, 30])
    assert result["realized_cash_drawdown_rs"] == 120
    assert result["net_without_best_winner_rs"] == -90
    assert module.metrics([])["win_rate"] is None
    assert module.metrics([100])["profit_factor"] is None


def test_read_only_does_not_create_missing_db(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(sqlite3.OperationalError):
        module.collect(str(missing), str(tmp_path))
    assert not missing.exists()


def test_collection_reads_consistent_snapshot_without_mutation(tmp_path):
    path = tmp_path / "evidence.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE fno_positions(id INTEGER, source TEXT)")
        db.execute("INSERT INTO fno_positions VALUES(1,'FNO_PAPER')")
    before = path.read_bytes()
    assert module.collect(str(path), str(tmp_path))["tables"]["fno_positions"][0]["id"] == 1
    assert path.read_bytes() == before
