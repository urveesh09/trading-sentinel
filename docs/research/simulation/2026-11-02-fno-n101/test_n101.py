"""Price-risk, exposure/recovery and actual wrapper regressions, not fitted returns."""
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n101_rules as R


def fees(entry, exit_price, qty):
    return 40 + (entry + exit_price) * qty * .001


def test_funded_stop_covers_all_costs_and_rounds_up_to_a_tick():
    stop = R.funded_stop(100, 130, 420, 2500, fees)
    assert abs(stop / .05 - round(stop / .05)) < 1e-8
    assert R.net_at(100, stop, 130, 420, fees) >= 2500
    assert R.net_at(100, stop - .05, 130, 420, fees) < 2500


@pytest.mark.parametrize("required", [0, 100, 5000, 100000])
def test_fee_aware_solution_for_different_price_scales(required):
    stop = R.funded_stop(2.15, 65, 205, required, fees)
    assert R.net_at(2.15, stop, 65, 205, fees) >= required - 1e-6


@pytest.mark.parametrize("field,value", [("entry", float("nan")), ("qty", 0), ("extra", -1), ("required_net", float("inf")), ("tick", 0)])
def test_bad_stop_inputs_are_refused(field, value):
    args = dict(entry=100, qty=130, extra=420, required_net=2500, fees=fees, tick=.05)
    args[field] = value
    with pytest.raises(ValueError):
        R.funded_stop(**args)


def test_flat_cheap_contract_can_release_but_expensive_or_exposed_cannot():
    prior = [5000.0] * 20
    assert R.genuinely_stuck(217000, 212500, 0, 4800, prior) == (True, 5000)
    assert R.genuinely_stuck(217000, 212500, 1, 4800, prior) == (False, None)
    assert R.genuinely_stuck(245000, 212500, 0, 33000, prior) == (False, 5000)
    assert R.genuinely_stuck(217000, 212500, 0, 6000, prior) == (False, 5000)
    assert R.genuinely_stuck(217000, 212500, 0, 4800, prior[:19]) == (False, None)


def test_expensive_outlier_does_not_dominate_a_median():
    assert R.genuinely_stuck(217000, 212500, 0, 4800, [5000] * 19 + [1e6]) == (True, 5000)


@pytest.fixture(scope="module")
def lab():
    import n101_lab
    return n101_lab


AT = datetime(2025, 3, 3, 11, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


def setup_add(lab, bid=160, ask=160.5):
    leg = lab.T.replay.OpenLeg(id=1, tradingsymbol="X", token=1, direction="LONG", lots=2, lot_size=65,
         entry_time=(AT-timedelta(minutes=10)).isoformat(), entry_premium=100, entry_underlying=23000,
         stop_underlying=22950, target_underlying=23090, premium_stop=75, atr_at_entry=10,
         delta_at_entry=.5, bar_ts="b", initial_qty=130)
    book = NS(equity=250000, closes=[], open={1: leg})
    leg._n10 = {"book": book, "cost": [200, 5], "native": 2, "risk_points": 50,
                "children": [], "next": 0, "stopped": False, "reference": 100, "refused": set()}
    engine = NS(book=lab.candidate("PREMIUM_LOCK"), notes=Counter(), _n101_events=[],
         _n091_budget=lab.M.R.Budget(250000, 250000, 212500), _n091_drawdown=.15,
         _halts=lambda *a: (), _stance=lambda *a: NS(single_leg_halted_today=False, multiplier=1))
    obs = NS(future=NS(ltp=23060), options={1: NS(bid=bid, ask=ask)})
    return engine, book, leg, obs


def test_underlying_trail_cannot_finance_an_option_loss(lab):
    engine, book, leg, obs = setup_add(lab, bid=95, ask=95.5)
    leg.trail_active, leg.trail_stop_underlying = 1, 23010
    assert lab.T.R.parent_risk(100, .25, 130, True) == 0  # old inference
    lab.maybe_add(engine, book, leg, obs, AT)
    assert not leg._n10["children"] and leg.premium_stop == 75
    assert engine._n101_events[-1]["reason"] == "profit_unfunded"


def test_price_funded_add_installs_a_real_premium_stop_and_keeps_full_reserve(lab):
    engine, book, leg, obs = setup_add(lab)
    lab.maybe_add(engine, book, leg, obs, AT)
    assert len(leg._n10["children"]) == 1
    c = leg._n10["children"][0]
    assert c["n101_parent_stop_net"] >= -c["n101_child_stop_net"]
    assert 75 < leg.premium_stop < obs.options[1].bid
    assert c["planned_total"] <= c["limit"] <= 5000
    assert lab.M.open_reserve(book, [200, 5]) > 23000  # no risk-free cash fiction
    lab.maybe_add(engine, book, leg, obs, AT+timedelta(minutes=1))
    assert len(leg._n10["children"]) == 1


def test_refused_add_does_not_raise_stop_and_retry_is_explicitly_bounded(lab):
    engine, book, leg, obs = setup_add(lab, bid=95, ask=95.5)
    lab.maybe_add(engine, book, leg, obs, AT)
    obs.options[1] = NS(bid=160, ask=160.5)
    lab.maybe_add(engine, book, leg, obs, AT+timedelta(seconds=30))
    assert len(engine._n101_events) == 1 and leg.premium_stop == 75
    lab.maybe_add(engine, book, leg, obs, AT+timedelta(minutes=1))
    assert len(leg._n10["children"]) == 1


def test_reserve_failure_does_not_install_unfunded_stop(lab):
    engine, book, leg, obs = setup_add(lab)
    engine._n091_budget = lab.M.R.Budget(250000, 250000, 230000)
    lab.maybe_add(engine, book, leg, obs, AT)
    assert engine._n101_events[-1]["reason"] == "reserve"
    assert leg.premium_stop == 75 and not leg._n10["children"]


@pytest.mark.parametrize("minute", [14*60+45, 15*60+10])
def test_entry_deadline_and_independently_stopped_child_cannot_be_bypassed(lab, minute):
    engine, book, leg, obs = setup_add(lab)
    lab.maybe_add(engine, book, leg, obs, AT.replace(hour=minute//60, minute=minute%60))
    assert not leg._n10["children"]
    leg._n10["stopped"] = True
    lab.maybe_add(engine, book, leg, obs, AT)
    assert not leg._n10["children"]


def test_a_gap_is_an_actual_observed_loss_not_a_fill_at_the_protective_stop(lab):
    engine, book, leg, obs = setup_add(lab)
    lab.maybe_add(engine, book, leg, obs, AT)
    stop = leg.premium_stop
    # Exercise the native exit evaluator with the installed price stop.
    from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
    result = evaluate_single_leg_exit(leg, now_ist=AT+timedelta(minutes=1), fut_price=23060,
                 exit_px_basis=stop-20, hard_flat=False, params=live_single_leg_exit_params(lab.settings))
    assert result.exit_reason is not None
    record, _ = lab.T.replay._close_record(leg, AT+timedelta(minutes=1), stop-20, result.exit_reason, 23060)
    assert record["exit_premium"] == stop-20
    assert record["n10_children"][0]["bid"] == stop-20


def test_event_storage_is_bounded_fail_closed(lab):
    engine = NS(_n101_events=[{}] * lab.MAX_EVENTS)
    with pytest.raises(RuntimeError):
        lab.event(engine, {})


def test_watch_wrapper_uses_closed_evidence_and_refuses_open_exposure(lab, monkeypatch):
    engine, book, leg, obs = setup_add(lab)
    engine.book["n101"]["mode"] = "WATCH_FLAT"
    engine._n091_book = book
    engine._n091_receipts = [{"full_reserves": {1: 4800}}]
    engine._n091_budget = lab.M.R.Budget(250000, 250000, 212500)
    rows = tuple((AT-timedelta(days=i+1), {"entry_premium": 100}) for i in reversed(range(20)))
    # A huge trade closing exactly NOW cannot enter the median.
    monkeypatch.setattr(lab, "paper_rows", lambda: rows+((AT, {"entry_premium": 1e6}),))
    calls = []
    monkeypatch.setattr(lab, "_refund", lambda *args: calls.append(args) or True)
    assert not lab.refund(engine, 217000, AT)
    assert not calls
    book.open.clear()
    assert lab.refund(engine, 217000, AT)
    assert len(calls) == 1
    event = engine._n101_events[-1]
    assert event["prior_closed"] == 20 and event["latest_evidence_exit"] < AT.isoformat()
