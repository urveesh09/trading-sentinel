"""Penny round-3 candidates: the stop moves out of one-minute noise at the same rupee risk."""
import pytest

from penny_lifecycle_replay import CANDIDATE_POLICIES, PennyLifecycleConfig, noise_floored_decision


def _decision(entry=20.0, stop=19.95, shares=40):
    return {"accept": True, "entry": entry, "stop_loss": stop, "shares": shares, "target": entry + 2 * (entry - stop)}


def test_tight_stop_widens_to_the_floor_and_size_shrinks_at_the_same_risk():
    decision = noise_floored_decision(_decision(), target_r=2.0)
    assert decision["accept"] and decision["stop_loss"] == pytest.approx(19.70)     # 1.5% of 20
    shipped_risk = 40 * 0.05
    assert decision["shares"] == int(shipped_risk // 0.30) == 6
    assert decision["shares"] * (20.0 - decision["stop_loss"]) <= shipped_risk + 1e-9
    assert decision["target"] == pytest.approx(20.60)
    assert decision["noise_floor"] == {"shipped_stop": 19.95, "shipped_shares": 40}


def test_a_stop_already_outside_the_noise_is_kept():
    decision = noise_floored_decision(_decision(stop=19.0, shares=5), target_r=2.0)
    assert decision["stop_loss"] == pytest.approx(19.0) and decision["shares"] == 5


def test_rupee_floor_applies_to_very_cheap_stocks_and_tiny_sizes_are_refused():
    cheap = noise_floored_decision(_decision(entry=1.50, stop=1.49, shares=300), target_r=2.0)
    assert cheap["stop_loss"] == pytest.approx(1.47)                                # ₹0.03 > 1.5% of 1.50
    refused = noise_floored_decision(_decision(shares=5), target_r=2.0)
    assert not refused["accept"] and refused["reject_reason"].startswith("position size = 0")


def test_candidates_are_registered():
    assert {"PEN_NOISE_STOP", "PEN_NOISE_STOP_BE"} <= set(CANDIDATE_POLICIES)
    assert PennyLifecycleConfig(tickers=("AAA",), candidate_policy="PEN_NOISE_STOP_BE").candidate_policy == "PEN_NOISE_STOP_BE"


def test_breakeven_moves_the_stop_only_after_a_completed_plus_one_r_close():
    from types import SimpleNamespace
    from penny_lifecycle_replay import _Replay

    class TickerDay:
        def __init__(self, close):
            self.bar = SimpleNamespace(close=close, executable=True)

        def bar_at(self, minute):
            return (5, self.bar) if minute == 600 else (None, None)

    trade = {"entry_fill_price": 20.0, "initial_stop_price": 19.7, "stop_price": 19.7, "_fill_index": 3}
    _Replay._breakeven_after_one_r(None, trade, TickerDay(20.2), 601)     # +0.67R: no change
    assert trade["stop_price"] == 19.7
    _Replay._breakeven_after_one_r(None, trade, TickerDay(20.31), 601)    # +1R close
    assert trade["stop_price"] == 20.0
    _Replay._breakeven_after_one_r(None, trade, TickerDay(20.5), 601)     # stops only rise
    assert trade["stop_price"] == 20.0
