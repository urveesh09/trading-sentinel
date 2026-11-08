from datetime import datetime, timedelta

import pandas as pd
import pytest

from round27 import earned_budget, signal_after_winner


def test_only_booked_profit_funds_bounded_risk():
    assert earned_budget(1799.99) is None
    assert earned_budget(1800.) == 900.
    assert earned_budget(3000.) == 1500.
    assert earned_budget(10000.) == 2000.


@pytest.mark.parametrize("side", (1, -1))
def test_signal_requires_two_candles_started_after_exit(side):
    end = datetime(2024, 6, 3, 11, 5)
    index = pd.date_range(end=end, periods=7, freq="5min")
    bars = pd.DataFrame([(100., 105., 95., 100.)] * 5 + [(99., 101., 94., 96.), (96., 104., 95., 103.)],
                        index=index, columns=("open", "high", "low", "close"))
    if side == -1:
        bars = pd.DataFrame({"open": 200 - bars.open, "high": 200 - bars.low,
                             "low": 200 - bars.high, "close": 200 - bars.close})
    settled = {"entry_underlying": 100 - 10 * side, "initial_stop_underlying": 100 - 20 * side,
               "exit_underlying": 100., "direction": "LONG" if side == 1 else "SHORT",
               "exit_time": (end - timedelta(minutes=6)).isoformat()}
    now = end + timedelta(minutes=5)
    trade = signal_after_winner(settled, bars, now, 100 + 2 * side)
    assert trade.direction.value == settled["direction"]
    assert trade.stop_underlying == 100 - 7 * side
    assert trade.target_underlying == pytest.approx(100 + 22.25 * side)
    assert signal_after_winner(settled, bars, now - timedelta(seconds=1), 100 + 2 * side) is None
    settled["exit_time"] = (end - timedelta(minutes=5)).isoformat()
    assert signal_after_winner(settled, bars, now, 100 + 2 * side) is None
