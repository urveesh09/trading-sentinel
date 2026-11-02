"""Budget invariants and actual planner-boundary regressions, not P&L assertions."""
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace as NS
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n091_rules as R


def test_cash_backed_floor_only_rises_with_realized_equity():
    old = R.Budget(250000., 250000., 212500.)
    up = R.advance(old, 300000., 0., .15)
    assert up == R.Budget(250000., 300000., 255000.)
    assert R.advance(up, 280000., 20000., .15) == up


def test_a_win_cannot_ratchet_above_cash_behind_an_existing_open_loss():
    old = R.Budget(250000., 250000., 212500.)
    assert R.advance(old, 300000., 60000., .15).floor == 240000.


def test_floor_breach_cannot_be_reset():
    with pytest.raises(ValueError, match="breached"):
        R.advance(R.Budget(250000., 250000., 212500.), 212499., 0., .15)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1., True])
def test_invalid_inputs_cannot_create_capital(bad):
    with pytest.raises(ValueError):
        R.advance(R.Budget(250000., 250000., 212500.), bad, 0., .15)


def test_whole_lots_must_fit_including_already_open_full_premium():
    costs = {1: 10001., 2: 20004.}
    assert R.affordable(2, 250000., 212500., 18000., costs) == 1
    assert R.affordable(2, 250000., 212500., 30000., costs) == 0
    assert R.affordable(2, 250000., 212500., 0., costs) == 2


def test_exact_budget_boundary_is_allowed_but_one_paise_over_is_not():
    assert R.affordable(1, 100., 80., 5., {1: 15.}) == 1
    assert R.affordable(1, 100., 80., 5., {1: 15.01}) == 0


def test_missing_and_nonfinite_reserves_refuse_admission():
    assert R.affordable(1, 100., 80., 0., {}) == 0
    assert R.affordable(1, 100., 80., 0., {1: float("nan")}) == 0
    assert R.affordable(1, float("nan"), 80., 0., {1: 10.}) == 0


def test_even_total_premium_loss_leaves_the_funded_floor():
    state = R.Budget(250000., 250000., 212500.)
    equity = 250000.
    for loss in (12000., 10000., 6000., 4000., 3000., 2000., 1000.):
        state = R.advance(state, equity, 0., .15)
        if R.affordable(1, equity, state.floor, 0., {1: loss}):
            equity -= loss
            assert equity >= state.floor
    assert equity >= 212500.


@pytest.fixture
def lab():
    os.environ.setdefault("N08_YEAR", "2025")
    import n091_lab
    return n091_lab


def test_true_vol_control_preserves_noon_and_late_entry_limits(lab):
    original = lab.Z.n08()
    new = lab.candidates()["VOL_CLOCK"]
    old = lab.Z.cash_books()["CASH|S_VOL"]
    assert new["n08"] == original["n08"]
    assert old["n08"]["low_two_lots_before"] == 1440
    assert new["n08"]["low_two_lots_before"] == 720
    assert new["members"] == original["members"] and new["cfg"] == original["cfg"]
    assert new["n09"]["vol_size"]


def test_full_reserve_contains_premium_fees_and_nonlinear_stress(lab):
    from fno_costs import calc_fno_costs
    assert lab.full_reserve(100., 130, 2, [200., 5.]) == 13000 + calc_fno_costs(100., 100., 130) + 420
    assert lab.full_reserve(100., 65, 1, [0., 0.]) > 6500


def make_plan(lab, accepted=True):
    from fno_entry_plan import EntryPlan
    from fno_gates import GateContext
    fields = {name: None for name in GateContext.__dataclass_fields__}
    return EntryPlan(accepted, "" if accepted else "native_gate", quote=NS(ask=100., contract=NS(tradingsymbol="X", token=1)),
                     lots=2, lot_size=65, gate_context=GateContext(**fields))


def setup_engine(lab, equity):
    return NS(book={"n091": {"mode": "CUSHION"}, "cost": [200., 5.]},
              _n091_book=NS(open={}), _n091_budget=R.Budget(250000., 250000., 212500.),
              _n091_drawdown=.15, _n091_receipts=[]), NS(pool=equity)


def test_native_gate_failure_is_never_reversed(lab, monkeypatch):
    rejected = make_plan(lab, False)
    monkeypatch.setattr(lab, "_plan", lambda *a: rejected)
    monkeypatch.setattr(lab, "ACTIVE", NS())
    assert lab.plan(None, None, None, None, None) is rejected


def test_smaller_size_replans_before_leg_creation_and_restores_settings(lab, monkeypatch):
    original = make_plan(lab)
    seen = []
    def planner(*args):
        seen.append(lab.settings.FNO_MAX_LOTS)
        return replace(original, lots=min(2, lab.settings.FNO_MAX_LOTS))
    engine, state = setup_engine(lab, 220000.)
    monkeypatch.setattr(lab, "ACTIVE", engine)
    monkeypatch.setattr(lab, "_plan", planner)
    monkeypatch.setattr(lab.settings, "FNO_MAX_LOTS", 2)
    monkeypatch.setattr(lab.settings, "FNO_MAX_LOTS_PROVEN", 2)
    sig = NS(bar_ts="2025-01-01 10:00:00", direction=NS(value="LONG"), stop_underlying=100., target_underlying=120.)
    result = lab.plan(sig, None, None, datetime(2025, 1, 1, 10, 5), state)
    assert result.accepted and result.lots == 1 and seen == [2, 1]
    assert lab.settings.FNO_MAX_LOTS == lab.settings.FNO_MAX_LOTS_PROVEN == 2


def test_unsafe_minimum_lot_is_refused(lab, monkeypatch):
    original = make_plan(lab)
    engine, state = setup_engine(lab, 215000.)
    monkeypatch.setattr(lab, "ACTIVE", engine)
    monkeypatch.setattr(lab, "_plan", lambda *a: original)
    sig = NS(bar_ts="2025-01-01 10:00:00", direction=NS(value="LONG"), stop_underlying=100., target_underlying=120.)
    result = lab.plan(sig, None, None, datetime(2025, 1, 1, 10, 5), state)
    assert not result.accepted and result.reject_reason == "n091:full_premium_reserve"


def test_replan_exception_restores_settings(lab, monkeypatch):
    original = make_plan(lab)
    engine, state = setup_engine(lab, 220000.)
    monkeypatch.setattr(lab, "ACTIVE", engine)
    monkeypatch.setattr(lab.settings, "FNO_MAX_LOTS", 2)
    monkeypatch.setattr(lab.settings, "FNO_MAX_LOTS_PROVEN", 2)
    def planner(*args):
        if lab.settings.FNO_MAX_LOTS == 1:
            raise RuntimeError("synthetic planner failure")
        return original
    monkeypatch.setattr(lab, "_plan", planner)
    sig = NS(bar_ts="x", direction=NS(value="LONG"))
    with pytest.raises(RuntimeError, match="synthetic"):
        lab.plan(sig, None, None, datetime(2025, 1, 1), state)
    assert lab.settings.FNO_MAX_LOTS == lab.settings.FNO_MAX_LOTS_PROVEN == 2


def test_restart_cannot_take_the_winner_that_establishes_its_paper_evidence():
    from stress import simulate
    rows = [{"entry_time": "01", "exit_time": "02", "net_pnl": -40000., "full_reserve": 50000.},
            {"entry_time": "03", "exit_time": "04", "net_pnl": 100000., "full_reserve": 10000.},
            {"entry_time": "05", "exit_time": "06", "net_pnl": 1000., "full_reserve": 10000.}]
    result = simulate(("Y",), {"Y": rows}, "SHADOW", need=1)
    assert result["end"] == 211000. and result["trades"] == 2


def test_shadow_exit_at_same_instant_is_not_earlier_evidence():
    from stress import simulate
    rows = [{"entry_time": "01", "exit_time": "02", "net_pnl": -40000., "full_reserve": 50000.},
            {"entry_time": "03", "exit_time": "04", "net_pnl": 100000., "full_reserve": 10000.},
            {"entry_time": "04", "exit_time": "06", "net_pnl": 1000., "full_reserve": 10000.}]
    assert simulate(("Y",), {"Y": rows}, "SHADOW", need=1)["end"] == 210000.


def test_proxy_keeps_funded_floor_through_repeated_full_losses():
    from stress import simulate
    rows = [{"entry_time": f"{i:02d}a", "exit_time": f"{i:02d}b", "net_pnl": -10000., "full_reserve": 10000.} for i in range(20)]
    result = simulate(("Y",) * 4, {"Y": rows}, "CUSHION")
    assert result["end"] == 220000. and result["restarts"] == 0
