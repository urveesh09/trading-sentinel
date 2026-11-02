"""The tolerance's wiring, against a fake planner so each path is pinned. Needs the research stack: N11_WITH_LAB=1 N08_YEAR=2024 pytest test_n11t.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
pytestmark = pytest.mark.skipif(os.environ.get("N11_WITH_LAB") != "1", reason="set N11_WITH_LAB=1 and N08_YEAR=2024")


@pytest.fixture(scope="module")
def lab():
    import n11t_lab
    return n11t_lab


def engine_for(lab, **change):
    book = lab.n11t_book(**change)
    notes = {"n11t_second_lots": 0}
    return SimpleNamespace(book=book, notes=notes, _n11_last={"sentinel": True}, _n10_book=SimpleNamespace(closes=[]))


def plan(accepted=True, lots=1):
    return SimpleNamespace(accepted=accepted, lots=lots)


class Script:
    """Answers the first call (N11's own decision) and records what the settings were on the second."""

    def __init__(self, first, second, settings):
        self.answers, self.settings, self.calls = [first, second], settings, []

    def __call__(self, sig, snap, regime, now, state):
        self.calls.append((self.settings.FNO_MAX_LOSS_PER_TRADE, self.settings.FNO_MAX_RISK_PCT))
        return self.answers[len(self.calls) - 1]


def state(m=1.0, pool=250000.0, opens=0):
    return SimpleNamespace(risk_multiplier=m, pool=pool, open_positions=opens)


def run(lab, monkeypatch, engine, first, second, *, vol=True, ev=True, m=1.0, ceiling=2):
    monkeypatch.setattr(lab.L, "vol_up", lambda now: vol)
    monkeypatch.setattr(lab.L, "evidence_now", lambda now: ev)
    monkeypatch.setattr(lab.settings, "FNO_MAX_LOTS", ceiling)
    monkeypatch.setattr(lab.settings, "FNO_MAX_LOTS_PROVEN", ceiling)
    script = Script(first, second, lab.settings)
    monkeypatch.setattr(lab, "_planner", script)
    out = lab.second_lot(engine, engine.book["n11t"], engine.book["n11"], SimpleNamespace(direction=SimpleNamespace(value="SHORT")), None, "R", None, state(m))
    return out, script


def test_a_refused_trade_stays_refused(lab, monkeypatch):
    first = plan(accepted=False)
    out, script = run(lab, monkeypatch, engine_for(lab), first, plan(lots=2))
    assert out is first and len(script.calls) == 1, "the tolerance admits no new trade"


def test_a_two_lot_trade_is_left_alone(lab, monkeypatch):
    first = plan(lots=2)
    out, script = run(lab, monkeypatch, engine_for(lab), first, plan(lots=3))
    assert out is first and len(script.calls) == 1, "no third lot at entry"


@pytest.mark.parametrize("vol,ev", [(False, True), (True, False), (False, False)])
def test_both_readings_are_needed(lab, monkeypatch, vol, ev):
    first = plan()
    out, script = run(lab, monkeypatch, engine_for(lab), first, plan(lots=2), vol=vol, ev=ev)
    assert out is first and len(script.calls) == 1


def test_one_lot_after_a_loss_stays_one_lot(lab, monkeypatch):
    first = plan()
    out, script = run(lab, monkeypatch, engine_for(lab), first, plan(lots=2), ceiling=1)
    assert out is first and len(script.calls) == 1


def test_a_second_lot_when_everything_holds(lab, monkeypatch):
    engine, second = engine_for(lab), plan(lots=2)
    out, script = run(lab, monkeypatch, engine, plan(), second)
    assert out is second and engine.notes["n11t_second_lots"] == 1
    assert script.calls[1][0] == pytest.approx(7500.0)


def test_a_drawdown_scales_the_room_down(lab, monkeypatch):
    engine = engine_for(lab)
    out, script = run(lab, monkeypatch, engine, plan(), plan(lots=2), m=0.5)
    budget = script.calls[1][0] * 0.5
    assert budget == pytest.approx(3750.0)


def test_a_winning_streak_never_lifts_it_past_the_limit(lab, monkeypatch):
    engine = engine_for(lab)
    out, script = run(lab, monkeypatch, engine, plan(), plan(lots=2), m=1.5)
    assert script.calls[1][0] * 1.5 == pytest.approx(7500.0)


def test_the_proven_stance_is_never_lowered(lab, monkeypatch):
    engine = engine_for(lab, limit=5500.0)
    out, script = run(lab, monkeypatch, engine, plan(), plan(lots=2), m=1.5)
    assert script.calls[1][0] * 1.5 == pytest.approx(7500.0), "the stance already allows 2% of 2.5 lakh x 1.5"


def test_settings_come_back_whatever_happens(lab, monkeypatch):
    before = lab.settings.FNO_MAX_LOSS_PER_TRADE, lab.settings.FNO_MAX_RISK_PCT
    run(lab, monkeypatch, engine_for(lab), plan(), plan(lots=2))
    assert (lab.settings.FNO_MAX_LOSS_PER_TRADE, lab.settings.FNO_MAX_RISK_PCT) == before


def test_a_failed_second_try_leaves_no_tightened_stop(lab, monkeypatch):
    engine, first = engine_for(lab), plan()
    out, script = run(lab, monkeypatch, engine, first, plan(accepted=False))
    assert out is first and engine._n11_last is None, "the first plan's 25% backstop stands"


def test_frozen_book(lab):
    b = lab.n11t_book()
    assert b["n11t"]["clamp"] == "SECOND_LOT" and b["n11t"]["limit"] == 7500.0 and b["n11t"]["when"] == ["VOL", "EV"] and b["n11"]["k"] == 1.75 and b["n11"]["add"] == "HONEST"
    assert b["n10"]["flat_risk"] == 5000.0, "the earned lot's own charge doesn't change"
