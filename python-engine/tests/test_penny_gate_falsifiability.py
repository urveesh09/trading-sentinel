"""
[GAP-1 GATE FALSIFIABILITY 2026-07-10] Witness tests for every penny
entry gate, backported from the F&O module spec (docs/superpowers/specs/
fno-module.md §9.1).

The rule: for every gate, a test that constructs an input which PASSES
it. Not "the gate rejects bad input" -- proof that the gate is
SATISFIABLE AT ALL. BUG-1 (the `bar_close > running day_high` anchor,
215,814 evaluations / 0 accepts / nine months) dies instantly under
this rule, because nobody can write the passing case for an
unsatisfiable gate.

Each engine gets:
  1. a WITNESS input that must be ACCEPTED end-to-end -- this proves
     every gate in the chain admits at least one passing input; and
  2. one falsifier per gate: a single mutation of the witness that must
     be rejected WITH THAT GATE'S reason -- this proves each gate is
     live, reachable, and discriminates (the witness really did pass
     *through* it, not around it).

A gate without a witness does not merge (spec §9.1).
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from penny_engine_breakout import evaluate_breakout_entry
from penny_engine_connors import evaluate_connors_entry
from penny_risk import PennyRiskEngine


def _make_risk_engine(bankroll=100_000.0):
    re = PennyRiskEngine(bankroll=bankroll, ledger_writer=MagicMock())
    re.daily_pnl = 0.0
    re.daily_pnl_date = datetime.now().date().isoformat()
    return re


def _zero_size_risk_engine():
    re = MagicMock()
    re.position_size = MagicMock(return_value=0)
    return re


def _stub_breakout_settings(monkeypatch, **overrides):
    from config import settings
    defaults = dict(
        PENNY_BREAKOUT_VOL_MULT=1.8,
        PENNY_BREAKOUT_TARGET_R=2.0,
        PENNY_BREAKOUT_BUFFER_PCT=0.003,
        PENNY_BREAKOUT_TIME_START=10 * 60 + 30,
        PENNY_BREAKOUT_TIME_END=14 * 60 + 30,
        PENNY_BREAKOUT_USE_VWAP=False,
        PENNY_BREAKOUT_ADAPTIVE_THRESHOLD=False,
        PENNY_BREAKOUT_RVOL_TIME_ADJUSTED=True,
        PENNY_BREAKOUT_RSI_MAX=70.0,
        PENNY_PER_STOCK_CAP=200_000.0,
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        monkeypatch.setattr(settings, k, v, raising=False)


# ---------------------------------------------------------------------------
# MIS breakout engine
# ---------------------------------------------------------------------------

def breakout_witness_kwargs():
    """An input that passes EVERY breakout entry gate. If this stops
    accepting, a gate has gone dead -- exactly the BUG-1 failure mode."""
    close = 10.30
    return dict(
        ticker="WIT",
        cum_vol_today=1_000_000,          # far above 1.8x time-scaled median
        median_vol_20d=100_000,
        breakout_bar={"close": close, "low": close * 0.99,
                      "high": close * 1.001, "volume": 50_000},
        day_high=10.00,                    # prior-bars high; close clears *1.003
        rsi_14=50.0,                       # mid-range, below the 70 ceiling
        as_of=datetime(2026, 7, 9, 12, 0),  # inside 10:30-14:30 IST
    )


# (gate name, witness mutation, expected reject_reason substring)
BREAKOUT_FALSIFIERS = [
    ("time_window",
     lambda kw: kw.update(as_of=datetime(2026, 7, 9, 9, 30)),
     "outside breakout time window"),
    ("volume_surge",
     lambda kw: kw.update(cum_vol_today=1_000),
     "volume"),
    ("volume_no_baseline",
     lambda kw: kw.update(median_vol_20d=0),
     "volume"),
    ("breakout_confirm",
     lambda kw: kw.update(breakout_bar={**kw["breakout_bar"], "close": 10.00}),
     "breakout not confirmed"),
    ("rsi_ceiling",
     lambda kw: kw.update(rsi_14=75.0),
     "overbought"),
    ("non_positive_risk",
     lambda kw: kw.update(breakout_bar={**kw["breakout_bar"], "low": 11.00}),
     "non-positive risk"),
    ("shares_positive",
     lambda kw: kw.update(risk_engine=_zero_size_risk_engine()),
     "position size = 0"),
]


class TestBreakoutGates:
    def test_witness_is_accepted(self, monkeypatch):
        """Every breakout gate MUST admit at least one passing input."""
        _stub_breakout_settings(monkeypatch)
        r = evaluate_breakout_entry(risk_engine=_make_risk_engine(),
                                    **breakout_witness_kwargs())
        assert r["accept"] is True, (
            f"The breakout gate chain is unsatisfiable: witness rejected "
            f"with {r.get('reject_reason')!r}. This is the BUG-1 failure "
            f"mode -- find the dead gate before shipping."
        )
        assert r["shares"] > 0

    @pytest.mark.parametrize(
        "gate_name,mutate,expected_reason",
        BREAKOUT_FALSIFIERS,
        ids=[g[0] for g in BREAKOUT_FALSIFIERS],
    )
    def test_each_gate_is_live(self, monkeypatch, gate_name, mutate,
                               expected_reason):
        """One mutation flips exactly one gate: proves the gate is
        reachable and the witness genuinely passed through it."""
        _stub_breakout_settings(monkeypatch)
        kw = breakout_witness_kwargs()
        kw["risk_engine"] = _make_risk_engine()
        mutate(kw)
        r = evaluate_breakout_entry(**kw)
        assert r["accept"] is False, f"gate {gate_name} did not fire"
        assert expected_reason in r["reject_reason"], (
            f"gate {gate_name}: expected reason containing "
            f"{expected_reason!r}, got {r['reject_reason']!r}"
        )

    def test_pr3_regime_gate_is_live(self, monkeypatch):
        from penny_models import PennyRegime
        _stub_breakout_settings(monkeypatch)
        r = evaluate_breakout_entry(risk_engine=_make_risk_engine(),
                                    regime=PennyRegime.PR3_HOT,
                                    **breakout_witness_kwargs())
        assert r["accept"] is False
        assert "PR3_HOT" in r["reject_reason"]

    def test_pr2_regime_still_satisfiable(self, monkeypatch):
        """Half-size regime must reduce size, not become a hidden
        no-entry regime."""
        from penny_models import PennyRegime
        _stub_breakout_settings(monkeypatch)
        r = evaluate_breakout_entry(risk_engine=_make_risk_engine(),
                                    regime=PennyRegime.PR2_ELEVATED,
                                    **breakout_witness_kwargs())
        assert r["accept"] is True
        assert r["shares"] > 0


# ---------------------------------------------------------------------------
# CNC Connors engine
# ---------------------------------------------------------------------------

def connors_witness_closes():
    """250 daily closes that pass every Connors gate.

    Construction: a slow uptrend (keeps last > SMA-200/SMA-50), a spike
    to 12, then a controlled 3-bar pullback whose last three RSI(2)
    windows are strictly rising while staying below the buy threshold:

        closes[-5:] = [12.0, 11.0, 10.0, 10.02, 9.52]
        rsi_prev2 = R(-1.0, -1.0)  = 0.00
        rsi_prev1 = R(-1.0, +0.02) = 1.96
        rsi       = R(+0.02, -0.5) = 3.85   (< 10, rising for 2 bars)
    """
    base = [4.0 + (8.0 - 4.0) * i / 244 for i in range(245)]
    return base + [12.0, 11.0, 10.0, 10.02, 9.52]


def connors_witness_kwargs():
    return dict(
        ticker="WIT",
        daily={"closes": connors_witness_closes()},
        today_volume=100_000,
        avg20_volume=100_000,
        regime_size_pct=0.05,   # PR1_CALM
        as_of=datetime(2026, 7, 9, 9, 30),
    )


def _mutate_tail(kw, tail):
    closes = connors_witness_closes()
    kw["daily"] = {"closes": closes[: len(closes) - len(tail)] + list(tail)}


CONNORS_FALSIFIERS = [
    ("history_floor",
     lambda kw: kw.update(daily={"closes": connors_witness_closes()[:100]}),
     "insufficient history"),
    ("trend_sma200",
     lambda kw: _mutate_tail(kw, [1.0]),
     "below 200 SMA"),
    ("trend_sma50",
     # Between SMA-200 (~6.4) and SMA-50 (~7.9).
     lambda kw: _mutate_tail(kw, [7.0]),
     "below 50 SMA"),
    ("rsi2_trigger",
     # A final up-bar sends RSI(2) to 100: not oversold, no trigger.
     lambda kw: _mutate_tail(kw, [10.5]),
     "not below threshold"),
    ("rsi_rising_confirmation",
     # Accelerating losses: RSI(2) sequence not strictly rising.
     lambda kw: _mutate_tail(kw, [10.02, 10.0, 9.0]),
     "RSI not rising"),
    ("volume_sanity",
     lambda kw: kw.update(today_volume=10_000),
     "volume too low"),
]


class TestConnorsGates:
    def test_witness_is_accepted(self):
        r = evaluate_connors_entry(risk_engine=_make_risk_engine(),
                                   **connors_witness_kwargs())
        assert r["accept"] is True, (
            f"The Connors gate chain is unsatisfiable: witness rejected "
            f"with {r.get('reject_reason')!r}."
        )
        assert r["shares"] > 0

    @pytest.mark.parametrize(
        "gate_name,mutate,expected_reason",
        CONNORS_FALSIFIERS,
        ids=[g[0] for g in CONNORS_FALSIFIERS],
    )
    def test_each_gate_is_live(self, gate_name, mutate, expected_reason):
        kw = connors_witness_kwargs()
        kw["risk_engine"] = _make_risk_engine()
        mutate(kw)
        r = evaluate_connors_entry(**kw)
        assert r["accept"] is False, f"gate {gate_name} did not fire"
        assert expected_reason in r["reject_reason"], (
            f"gate {gate_name}: expected reason containing "
            f"{expected_reason!r}, got {r['reject_reason']!r}"
        )

    def test_shares_gate_is_live(self):
        kw = connors_witness_kwargs()
        kw["risk_engine"] = _zero_size_risk_engine()
        r = evaluate_connors_entry(**kw)
        assert r["accept"] is False
        assert "position size = 0" in r["reject_reason"]

    # -- optional gates (default-disabled): still must be satisfiable
    #    AND falsifiable when armed --------------------------------------

    def test_rsi_floor_gate_when_armed(self, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "PENNY_CONNORS_RSI2_FLOOR", 5.0)
        # Witness rsi=3.85 falls below the armed floor: dead-cat reject.
        kw = connors_witness_kwargs()
        kw["risk_engine"] = _make_risk_engine()
        r = evaluate_connors_entry(**kw)
        assert r["accept"] is False
        assert "below floor" in r["reject_reason"]
        # Satisfiable: tail tuned so rsi = R(+0.04, -0.5) = 7.41,
        # inside the (5, 10) band and still rising.
        kw = connors_witness_kwargs()
        kw["risk_engine"] = _make_risk_engine()
        _mutate_tail(kw, [12.0, 11.0, 10.0, 10.04, 9.54])
        r = evaluate_connors_entry(**kw)
        assert r["accept"] is True, (
            f"RSI-floor gate unsatisfiable when armed: "
            f"{r.get('reject_reason')!r}"
        )

    def test_cumulative_rsi_gate_when_armed(self, monkeypatch):
        from config import settings
        # Witness streak: RSI(2) < 10 on the last 3 prefixes (3.85,
        # 1.96, 0.00) and the 4th prefix breaks it (spike bar, RSI 80).
        monkeypatch.setattr(settings, "PENNY_CONNORS_CUMULATIVE_RSI_DAYS", 2)
        kw = connors_witness_kwargs()
        kw["risk_engine"] = _make_risk_engine()
        r = evaluate_connors_entry(**kw)
        assert r["accept"] is True, (
            f"cumulative-RSI gate unsatisfiable at 2 days: "
            f"{r.get('reject_reason')!r}"
        )
        monkeypatch.setattr(settings, "PENNY_CONNORS_CUMULATIVE_RSI_DAYS", 4)
        kw = connors_witness_kwargs()
        kw["risk_engine"] = _make_risk_engine()
        r = evaluate_connors_entry(**kw)
        assert r["accept"] is False
        assert "cumulative RSI" in r["reject_reason"]
