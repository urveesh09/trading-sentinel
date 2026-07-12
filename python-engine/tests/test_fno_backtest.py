"""
[ROADMAP-3.11 2026-07-12] F&O backtest witnesses.

The backtest's trustworthiness rests on reusing the LIVE signal engine,
gates, sizing and cost model -- these tests pin that reuse: the same
bar frame the orchestrator test uses to fire a live paper entry must
produce a backtest trade, exits must follow the live ladder order with
the 3.3 gap discipline, and P&L must settle through calc_fno_costs.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from config import settings
from fno_backtest import run_fno_backtest
from fno_costs import calc_fno_costs

# Friday 2026-07-10; synthetic weekly expiry (Tuesday) = 2026-07-14.
SIGNAL_DAY = "2026-07-10"
PRIOR_DAYS = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]


def _flat_day(d: str, price: float = 25000.0) -> pd.DataFrame:
    idx = pd.date_range(f"{d} 09:15", periods=75, freq="5min")
    return pd.DataFrame({
        "open": price, "high": price + 5.0, "low": price - 5.0,
        "close": price, "volume": 100.0,
    }, index=idx)


def _frame(signal_day_rows) -> pd.DataFrame:
    """4 flat prior sessions (EMA/RVOL baselines) + a signal day built
    from (HH:MM, o, h, l, c, v) rows."""
    frames = [_flat_day(d) for d in PRIOR_DAYS]
    idx = pd.to_datetime([f"{SIGNAL_DAY} {hm}" for hm, *_ in signal_day_rows])
    cols = list(zip(*[r[1:] for r in signal_day_rows]))
    frames.append(pd.DataFrame({
        "open": cols[0], "high": cols[1], "low": cols[2],
        "close": cols[3], "volume": cols[4],
    }, index=idx))
    return pd.concat(frames)


# The same shape the orchestrator test fires a live entry on: flat OR,
# then a +100 breakout at 09:55 with 3x volume.
_OR_AND_BREAK = [
    ("09:15", 25000, 25010, 24990, 25000, 100),
    ("09:20", 25000, 25008, 24992, 25000, 100),
    ("09:25", 25000, 25010, 24990, 25000, 100),
    ("09:30", 25000, 25007, 24993, 25000, 100),
    ("09:35", 25000, 25009, 24991, 25000, 100),
    ("09:40", 25000, 25010, 24990, 25000, 100),
    ("09:45", 25000, 25008, 25000, 25005, 100),
    ("09:50", 25005, 25010, 25002, 25005, 100),
    ("09:55", 25010, 25105, 25005, 25100, 300),
]


def _drift(hm_list, price, spread=3.0, vol=100):
    return [(hm, price, price + spread, price - spread, price, vol) for hm in hm_list]


class TestEntryParityAndSizing:
    def test_breakout_frame_produces_one_long_trade(self):
        # After entry, drift ~+0.7R so neither time stop nor target ends
        # the day early -- the 15:10 hard flat closes it.
        rows = _OR_AND_BREAK + _drift(
            [f"{h:02d}:{m:02d}" for h in range(10, 15) for m in (0, 30)]
            + ["15:10"],
            25117.0,
        )
        result = run_fno_backtest(_frame(rows))
        assert result["n_trades"] == 1, result
        t = result["trades"][0]
        assert t["direction"] == "LONG"
        assert t["entry_time"] == f"{SIGNAL_DAY} 10:00"
        assert t["entry_underlying"] == 25100.0
        # ATM-or-ITM: CE strike at/below the forward, on the 50 ladder.
        assert t["strike"] <= 25100.0 * 1.001
        assert t["strike"] % settings.FNO_BT_STRIKE_STEP == 0
        assert t["expiry"] == "2026-07-14"  # next Tuesday
        assert t["lots"] >= 1

    def test_flat_frame_produces_no_trades(self):
        rows = _OR_AND_BREAK[:8] + _drift(["09:55", "10:00", "10:30"], 25005.0)
        result = run_fno_backtest(_frame(rows))
        assert result["n_trades"] == 0

    def test_pnl_settles_through_real_cost_model(self):
        rows = _OR_AND_BREAK + _drift(
            [f"{h:02d}:{m:02d}" for h in range(10, 15) for m in (0, 30)]
            + ["15:10"],
            25117.0,
        )
        t = run_fno_backtest(_frame(rows))["trades"][0]
        qty = t["lots"] * 75
        expected_costs = calc_fno_costs(t["entry_premium"], t["exit_premium"], qty)
        assert t["costs"] == pytest.approx(expected_costs, abs=0.02)
        assert t["pnl"] == pytest.approx(t["gross_pnl"] - t["costs"], abs=0.02)


class TestExitLadder:
    def test_gap_through_stop_fills_from_open(self):
        """Next bar OPENS 60 points below the stop: the exit basis must
        be the open (3.3 discipline), not the stop level."""
        rows = _OR_AND_BREAK + [("10:00", 25000, 25010, 24990, 25000, 100)]
        t = run_fno_backtest(_frame(rows))["trades"][0]
        assert t["exit_reason"] == "underlying_stop"
        assert t["exit_underlying"] == 25000.0  # the gap open, not the stop
        assert t["pnl"] < 0

    def test_intraday_stop_breach_fills_at_stop(self):
        """Open above the stop, low below it: basis is the stop itself."""
        rows = _OR_AND_BREAK + [("10:00", 25095, 25096, 25000, 25010, 100)]
        t = run_fno_backtest(_frame(rows))["trades"][0]
        assert t["exit_reason"] == "underlying_stop"
        assert t["exit_underlying"] > 25000.0
        assert t["exit_underlying"] < 25100.0  # the stop, between low and entry

    def test_target_then_pullback_exits_on_trail(self):
        rows = _OR_AND_BREAK + [
            ("10:00", 25100, 25160, 25098, 25155, 150),  # through target
            ("10:05", 25155, 25165, 25150, 25160, 100),  # trail ratchets
            ("10:10", 25160, 25161, 25080, 25085, 200),  # falls through trail
        ]
        t = run_fno_backtest(_frame(rows))["trades"][0]
        assert t["exit_reason"] == "trail_stop"
        assert t["pnl"] > 0  # trail locked in part of the move

    def test_stagnation_hits_time_stop(self):
        """No progress for FNO_TIME_STOP_MIN minutes -> time stop, well
        before the hard flat."""
        rows = _OR_AND_BREAK + _drift(
            ["10:00", "10:15", "10:30", "10:45", "11:00", "11:15"], 25100.0,
            spread=2.0,
        )
        t = run_fno_backtest(_frame(rows))["trades"][0]
        assert t["exit_reason"] == "time_stop"
        assert t["exit_time"] <= f"{SIGNAL_DAY} 11:20"

    def test_hard_flat_closes_survivors_at_1510(self):
        rows = _OR_AND_BREAK + _drift(
            [f"{h:02d}:{m:02d}" for h in range(10, 15) for m in (0, 30)]
            + ["15:10"],
            25117.0,
        )
        t = run_fno_backtest(_frame(rows))["trades"][0]
        assert t["exit_reason"] == "hard_flat_1510"


class TestReplayedGates:
    def test_expiry_day_entries_blocked(self, monkeypatch):
        """Make the signal day itself the synthetic expiry weekday:
        the live expiry_day_block gate must reject the entry."""
        # 2026-07-10 is a Friday (weekday 4).
        monkeypatch.setattr(settings, "FNO_BT_EXPIRY_WEEKDAY", 4)
        rows = _OR_AND_BREAK + [("10:00", 25100, 25105, 25095, 25100, 100)]
        result = run_fno_backtest(_frame(rows))
        assert result["n_trades"] == 0
        assert result["entry_rejects"].get("expiry_day_block", 0) >= 1

    def test_empty_frame_is_clean(self):
        result = run_fno_backtest(pd.DataFrame())
        assert result["n_trades"] == 0
        assert result["trades"] == []

    def test_stats_are_consistent(self):
        rows = _OR_AND_BREAK + [("10:00", 25000, 25010, 24990, 25000, 100)]
        result = run_fno_backtest(_frame(rows))
        assert result["n_trades"] == len(result["trades"]) == 1
        assert result["win_rate"] == 0.0  # the stop-out is a loss
        assert result["total_pnl"] == result["trades"][0]["pnl"]
        assert result["days_traded"] == 1
        assert result["model"]["iv"] == settings.FNO_BT_IV
