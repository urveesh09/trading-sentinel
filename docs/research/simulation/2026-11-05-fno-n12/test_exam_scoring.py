from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from exam_scoring import score


FREEZE = json.loads(Path(__file__).with_name("exam-2022-h1-freeze.json").read_bytes())


def tickets(net, count=15):
    return [{"tradingsymbol": "NIFTYTEST", "entry_time": f"2099-01-{day:02}T10:00:00+05:30",
             "exit_time": f"2099-01-{day:02}T11:00:00+05:30", "entry_qty": 65,
             "entry_premium": 100, "exit_premium": 105, "exit_reason": "test",
             "status": "CLOSED", "net_pnl": net} for day in range(1, count + 1)]


def test_changed_floor_and_risk_ratios():
    result = score(tickets(-20), tickets(1), tickets(-25), tickets(-24), FREEZE)
    assert result["verdict"] == "pass"
    assert result["changed_trades"] == 15
    assert result["ex_best_day_delta"] == Decimal(294)
    assert result["summaries"]["control"]["net_to_worst_day"] == Decimal(-15)
    assert score(tickets(-20, 14), tickets(1, 14), [], [], FREEZE)["verdict"] == "insufficient"


def test_identity_and_quantity_changes_count_only_once():
    control = tickets(1)
    candidate = deepcopy(control)
    candidate[0]["entry_qty"] = 130
    candidate[0]["exit_reason"] = "other"
    candidate[-1]["tradingsymbol"] = "NIFTYOTHER"
    result = score(control, candidate, control, candidate, FREEZE)
    assert result["changed_trades"] == 3
    assert result["verdict"] == "insufficient"


def test_concentration_and_doubled_cost_fail():
    control = tickets(0)
    candidate = tickets(-1)
    candidate[0]["net_pnl"] = 100
    result = score(control, candidate, control, control, FREEZE)
    assert result["gates"]["positive_net"]
    assert not result["gates"]["positive_ex_best_day"]
    assert not result["gates"]["positive_doubled_cost_net"]
    assert result["verdict"] == "fail"


def test_downside_limits_are_inclusive():
    control, candidate = tickets(0), tickets(1000)
    candidate[0]["net_pnl"] = -1000
    assert score(control, candidate, control, candidate, FREEZE)["gates"]["worst_day"]
    candidate[0]["net_pnl"] = -1001
    result = score(control, candidate, control, candidate, FREEZE)
    assert not result["gates"]["worst_day"]
    for row in candidate[:3]:
        row["net_pnl"] = -1000
    result = score(control, candidate, control, candidate, FREEZE)
    assert result["gates"]["worst_day"]
    assert not result["gates"]["closed_drawdown"]


def test_unresolved_doubled_book_and_duplicate_identities():
    control, candidate = tickets(0), tickets(1)
    unresolved = {**candidate[0], "status": "UNRESOLVED", "net_pnl": None}
    assert score(control, candidate, control, [unresolved], FREEZE)["verdict"] == "incomplete"
    with pytest.raises(ValueError, match="Duplicate trade identity"):
        score(control + [control[0]], candidate, control, candidate, FREEZE)
