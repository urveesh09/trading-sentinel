"""N11's rules at their edges, and the wiring against a fake replay. Run with the engine venv: pytest test_n11.py"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n11_rules as R  # noqa: E402


def fees(entry, exit_, qty):
    return 40.0 + 0.0015 * exit_ * qty


# ---- the stand-aside ----------------------------------------------------------------------------------------------------

def test_nothing_waits_without_enough_history():
    assert not R.stand_aside(False, [-100.0] * 19)
    assert R.stand_aside(False, [-100.0] * 20)


def test_waits_only_when_both_readings_are_against():
    bad, good = [-100.0] * 20, [100.0] * 20
    assert R.stand_aside(False, bad)
    assert not R.stand_aside(True, bad), "a volatile day never waits"
    assert not R.stand_aside(False, good), "a good paper record never waits"
    assert not R.stand_aside(True, good)


def test_a_flat_record_is_not_positive():
    assert R.stand_aside(False, [100.0, -100.0] * 10)


def test_only_the_last_window_counts():
    assert not R.stand_aside(False, [-999.0] * 50 + [10.0] * 20)
    assert R.stand_aside(False, [999.0] * 50 + [-10.0] * 20)


def test_it_reads_only_what_it_is_given():
    nets = [-100.0] * 25
    before = list(nets)
    R.stand_aside(False, nets)
    assert nets == before


def test_evidence_positive_and_negative_never_both_true():
    for nets in ([], [1.0] * 19, [1.0] * 20, [-1.0] * 20, [0.0] * 20):
        assert not (R.evidence_positive(nets) and R.evidence_negative(nets))


# ---- the honest earned lot ---------------------------------------------------------------------------------------------

def test_adverse_distance_each_side():
    assert R.adverse_distance("LONG", 100.0, 90.0) == 10.0
    assert R.adverse_distance("SHORT", 100.0, 110.0) == 10.0
    assert R.adverse_distance("LONG", 100.0, 105.0) == 0.0, "already through it: no distance left"
    assert R.adverse_distance("SHORT", 100.0, 95.0) == 0.0


def test_parent_at_a_locked_stop_can_cost_nothing():
    loss = R.parent_loss_at_stop("LONG", 21900.0, 150.0, 0.5, 21880.0, 100.0, 75.0, 130, 420.0, fees)
    assert loss == 0.0, "still in profit at the stop"


def test_parent_loss_is_capped_by_its_backstop():
    deep = R.parent_loss_at_stop("LONG", 21900.0, 100.0, 0.5, 21000.0, 100.0, 75.0, 130, 420.0, fees)
    assert deep == pytest.approx(25.0 * 130 + fees(100.0, 75.0, 130) + 420.0)


def test_parent_loss_reads_the_current_stop_not_the_first():
    near = R.parent_loss_at_stop("SHORT", 21000.0, 110.0, -0.5, 21020.0, 100.0, 75.0, 130, 420.0, fees)
    far = R.parent_loss_at_stop("SHORT", 21000.0, 110.0, -0.5, 21060.0, 100.0, 75.0, 130, 420.0, fees)
    assert near < far


def test_put_delta_sign_does_not_flip_the_estimate():
    call = R.parent_loss_at_stop("LONG", 21000.0, 100.0, 0.5, 20950.0, 100.0, 50.0, 65, 0.0, fees)
    put = R.parent_loss_at_stop("SHORT", 21000.0, 100.0, -0.5, 21050.0, 100.0, 50.0, 65, 0.0, fees)
    assert call == pytest.approx(put)


def test_child_full_loss_is_the_whole_backstop():
    assert R.child_full_loss(100.0, 0.25, 65, 205.0, fees) == pytest.approx(25.0 * 65 + fees(100.0, 75.0, 65) + 205.0)


def test_open_net_counts_everything():
    assert R.open_net(100.0, 120.0, 130, 420.0, fees) == pytest.approx(20.0 * 130 - fees(100.0, 120.0, 130) - 420.0)


# ---- the budget ---------------------------------------------------------------------------------------------------------

def test_budget_never_scales_above_the_flat_limit():
    assert R.budget(250000.0, 0.02, 6250.0, 5000.0, 1.5) == 5000.0


def test_budget_scales_down_in_a_drawdown():
    assert R.budget(250000.0, 0.02, 6250.0, 5000.0, 0.5) == 2500.0


def test_budget_respects_a_small_pool():
    assert R.budget(100000.0, 0.02, 6250.0, 5000.0, 1.0) == 2000.0


def test_budget_zero_multiplier():
    assert R.budget(250000.0, 0.02, 6250.0, 5000.0, 0.0) == 0.0


# ---- the true-risk lot: tried and dropped, the arithmetic stays tested because the screens used it ---------------------------

def extra(lots):
    return (200.0 + 5.0 * lots) * lots


def test_true_risk_raises_when_the_stop_fits():
    lots, points = R.true_risk_lots(1, 2, 200.0, 0.5, 30.0, 65, 5000.0, 1.5, 0.25, fees, extra)
    assert lots == 2 and 1.5 * 0.5 * 30.0 <= points <= 50.0


def test_true_risk_refuses_when_the_stop_is_too_wide():
    assert R.true_risk_lots(1, 2, 200.0, 0.5, 200.0, 65, 5000.0, 1.5, 0.25, fees, extra) == (1, None)


def test_true_risk_never_lowers_or_passes_the_ceiling():
    assert R.true_risk_lots(2, 2, 200.0, 0.5, 30.0, 65, 5000.0, 1.5, 0.25, fees, extra) == (2, None)


def test_stop_price_rounds_up_so_the_loss_stays_inside():
    assert R.stop_price(100.03, 10.0) == pytest.approx(90.05)
    assert R.stop_price(100.0, 10.0) == pytest.approx(90.0)
    assert not math.isnan(R.stop_price(0.05, 0.05))


def test_noise_stop():
    assert R.noise_stop(10.0, 10.0, 1.25)
    assert not R.noise_stop(12.5, 10.0, 1.25)
    assert not R.noise_stop(10.0, 0.0, 1.25)


# ---- the wiring: only importable with the research stack, so these need N08_YEAR and the sealed data ------------------------

WITH_LAB = os.environ.get("N11_WITH_LAB") == "1"
needs_lab = pytest.mark.skipif(not WITH_LAB, reason="set N11_WITH_LAB=1 and N08_YEAR=2024")


@pytest.fixture(scope="module")
def lab():
    import n11_lab
    return n11_lab


@needs_lab
def test_frozen_book_has_no_reserve_and_no_watch(lab):
    b = lab.n11_book()
    assert b["n091"]["mode"] == "VOL_CLOCK" and "watch" not in b["n10"] and "n101" not in b


@needs_lab
def test_vol_at_one_is_exactly_the_old_reading(lab):
    table = lab.Z.vol_table()
    days = [d for d, (a, u) in table.items() if a is not None and u is not None][:400]
    assert days, "no readings"
    for d in days:
        now = datetime.fromisoformat(d + "T11:00:00")
        assert lab.vol_at(now, 1.0) == lab.vol_up(now), d


@needs_lab
def test_paper_reading_never_sees_its_own_exit(lab):
    at, _nets = lab.paper_stream()
    moment = at[50]
    assert all(when < moment for when in at[:len(lab.paper_before(moment))])
    assert len(lab.paper_before(moment)) <= 50, "an exit at exactly now isn't known yet"


@needs_lab
def test_each_part_can_be_removed_alone(lab):
    p = lab.panel_books()
    assert "stand" not in p["NO_STAND"]["n11"] and "loss_one" not in p["NO_LOSS"]["n11"] and "add" not in p["NO_ADD"]["n11"]
    assert p["NO_ADD"]["n10"]["steps"] == [] and p["N11"]["n10"]["steps"] == [[1.0, 0.0]]
    assert p["NO_VOL"]["n09"]["vol_size"] is False and p["N11"]["n09"]["vol_size"] is True


@needs_lab
def test_true_risk_is_not_in_the_frozen_book(lab):
    assert "true_risk" not in lab.n11_book()["n11"] and "evidence" not in lab.n11_book()["n11"]


@needs_lab
def test_the_real_leg_shape_the_honest_add_reads(lab):
    leg = lab.replay.OpenLeg(id=1, tradingsymbol="X", token=1, direction="LONG", lots=2, lot_size=65, entry_time="2024-01-01T10:00:00+05:30", entry_premium=100.0,
                             entry_underlying=21000.0, stop_underlying=20970.0, target_underlying=21054.0, premium_stop=75.0, atr_at_entry=15.0, delta_at_entry=0.55, bar_ts="b")
    assert leg.qty == 130 and leg.trail_active == 0 and leg.trail_stop_underlying is None
