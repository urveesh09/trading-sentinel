"""Selective Momentum gate and the runner exit (research candidates)."""
import pandas as pd
import pytest

import momentum_replay as replay
from momentum_selective import SelectivePolicy, selective_gate


def _bars(rows, start="2026-08-03T09:15:00+05:30"):
    index = pd.date_range(start, periods=len(rows), freq="15min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index)


INDEX_UP = _bars([(100, 100.4, 99.9, 100.2), (100.2, 100.5, 100.1, 100.4), (100.4, 100.6, 100.3, 100.5)])
STOCK = _bars([(200, 202, 199.5, 201.5), (201.5, 203, 201, 202.8), (202.8, 205, 202.5, 204.6)])


def test_strong_stock_on_an_up_day_through_yesterdays_high_passes():
    ok, reason, evidence = selective_gate(STOCK, INDEX_UP, prev_day_high=203.0)
    assert ok and reason is None
    assert evidence["relative_strength"] == pytest.approx(204.6 / 200 - 1 - (100.5 / 100 - 1), abs=1e-6)


@pytest.mark.parametrize("index,prev_high,reason", [
    (_bars([(100, 100.1, 99, 99.5), (99.5, 99.6, 99.2, 99.4), (99.4, 99.5, 99.0, 99.2)]), 203.0, "market_not_up"),
    (INDEX_UP, 206.0, "below_prev_day_high"),
    (INDEX_UP.iloc[:2], 203.0, "index_bar_unavailable"),           # the signal bar's index bar is missing
])
def test_context_refusals(index, prev_high, reason):
    ok, why, _ = selective_gate(STOCK, index, prev_day_high=prev_high)
    assert not ok and why == reason


def test_relative_strength_must_clear_the_threshold():
    laggard = _bars([(200, 200.5, 199.9, 200.2), (200.2, 200.6, 200.1, 200.5), (200.5, 201.2, 200.4, 201.0)])
    ok, why, evidence = selective_gate(laggard, INDEX_UP, prev_day_high=200.8)
    assert not ok and why == "relative_strength_too_low" and evidence["relative_strength"] < 0.003
    ok, _, _ = selective_gate(laggard, INDEX_UP, 200.8, SelectivePolicy(min_relative_strength=-1.0))
    assert ok


def _frame(rows):
    return pd.DataFrame([r[1:] for r in rows], columns=["open", "high", "low", "close", "volume"],
                        index=pd.to_datetime([r[0] for r in rows]))


def _candidate():
    return {"variant": "MOM_SELECTIVE", "ticker": "AAA", "trading_date": "2026-08-03",
            "bar_ts": "2026-08-03T10:45:00", "dataset_fingerprint": "test",
            "decision": {"entry_price": 100.0, "stop_loss": 99.0, "target_1": 101.6, "shares": 10}}


def test_runner_ignores_the_target_moves_to_breakeven_and_trails_bar_lows():
    execution = replay.momentum_shadow_execution_config()
    run = _frame([("2026-08-03T11:00:00", 100.2, 101.4, 100.1, 101.3, 10),   # +1R close: arm
                  ("2026-08-03T11:15:00", 101.3, 102.5, 101.2, 102.4, 10),   # past the old target, no exit
                  ("2026-08-03T11:30:00", 102.3, 102.6, 101.0, 101.1, 10)])  # under the prior bar low
    trade = replay._simulate_runner_exit(_candidate(), run, execution)
    assert trade["status"] == "CLOSED" and trade["exit_reason"] == "runner_trail_stop"
    slip = 1 - execution["exit_slippage_bps"] / 10000
    assert trade["fills"][0]["price"] == pytest.approx(101.2 * slip)        # the 11:15 bar's low


def test_runner_initial_stop_and_square_off():
    execution = replay.momentum_shadow_execution_config()
    stopped = replay._simulate_runner_exit(_candidate(), _frame([
        ("2026-08-03T11:00:00", 100.0, 100.3, 98.8, 99.1, 10)]), execution)
    assert stopped["exit_reason"] == "stop"
    held = replay._simulate_runner_exit(_candidate(), _frame([
        ("2026-08-03T11:00:00", 100.0, 100.5, 99.6, 100.4, 10),
        ("2026-08-03T15:15:00", 100.6, 100.9, 100.5, 100.8, 10)]), execution)
    assert held["exit_reason"] == "hard_square_off"
    assert held["fills"][0]["price"] == pytest.approx(100.6 * (1 - execution["exit_slippage_bps"] / 10000))
