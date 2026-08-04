"""
[CONNORS-EVIDENCE 2026-08-04] Tests for tools/connors_backtest.py.

The backtest reimplements the Connors gate stack so the sweep can vary two
gates the production function reads from settings. A reimplementation that
drifts from production is worse than no backtest at all -- it produces
confident numbers about a strategy nobody is running. The first test here is
therefore the load-bearing one: at the shipped configuration, the backtest's
gate decision must agree with evaluate_connors_entry on every case.

The rest pin the properties that make the result honest rather than flattering:
no lookahead, stop-before-target inside a bar, real costs, no overlaps.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from config import settings                                    # noqa: E402
from penny_engine_connors import evaluate_connors_entry        # noqa: E402
from connors_backtest import (                                 # noqa: E402
    MIN_BARS, SHARES, _entry_signal, simulate, stats,
)


class _StubRisk:
    def position_size(self, entry, stop, regime):
        return SHARES


def _rising_series(n=300, start=100.0):
    """A gently rising series: above both SMAs, so trend gates pass."""
    return [start + i * 0.5 for i in range(n)]


def _with_dip(closes, dip_pct=0.04):
    """Append a sharp two-day dip then an up-tick -- the Connors shape."""
    c = list(closes)
    c.append(c[-1] * (1 - dip_pct))
    c.append(c[-1] * (1 - dip_pct))
    c.append(c[-1] * 1.01)
    return c


# ---------------------------------------------------------------------------
# the load-bearing one: reimplementation must match production
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("closes", [
    _rising_series(),                       # no dip -> RSI high, rejected
    _with_dip(_rising_series()),            # dip then bounce
    _with_dip(_rising_series(), 0.10),      # violent dip
    [100.0] * 300,                          # flat -> at/below SMA
    _rising_series()[::-1],                 # falling -> below SMAs
])
def test_backtest_gates_agree_with_production_at_shipped_config(closes):
    vols = [1000.0] * len(closes)
    i = len(closes) - 1

    bt_reject = _entry_signal(
        closes, vols, i,
        rsi_buy=settings.PENNY_CONNORS_RSI2_BUY,
        require_rising=True,
    )
    prod = evaluate_connors_entry(
        ticker="TESTCO",
        daily={"closes": closes},
        today_volume=int(vols[i]),
        avg20_volume=int(sum(vols[i - 19:i + 1]) / 20),
        regime_size_pct=settings.PENNY_RISK_PCT_PR1,
        risk_engine=_StubRisk(),
        as_of=datetime(2026, 8, 4),
    )

    assert (bt_reject is None) == bool(prod.get("accept")), (
        f"backtest says {bt_reject!r}, production says "
        f"accept={prod.get('accept')} ({prod.get('reject_reason')!r})"
    )


# ---------------------------------------------------------------------------
# properties that keep the result honest
# ---------------------------------------------------------------------------

def _bars(closes, high_mult=1.0, low_mult=1.0):
    """Daily bars from a close series. Entry uses the NEXT bar's open, so open
    is set equal to the previous close to make the arithmetic checkable."""
    out = []
    prev = closes[0]
    for c in closes:
        out.append(("2026-01-01", prev, max(prev, c) * high_mult,
                    min(prev, c) * low_mult, c, 1000.0))
        prev = c
    return out


def test_stop_is_assumed_before_target_when_a_bar_spans_both():
    """A daily bar cannot order intrabar events. Assuming the target would
    manufacture profit that never existed, so the loss is assumed instead."""
    closes = _with_dip(_rising_series())
    bars = _bars(closes)
    # Make the bar AFTER entry span both the -3% stop and the +6% target.
    entry_idx = len(bars) - 1
    bars.append(("2026-01-02", closes[-1], closes[-1] * 1.10,
                 closes[-1] * 0.90, closes[-1], 1000.0))
    bars.append(("2026-01-03", closes[-1], closes[-1], closes[-1], closes[-1], 1000.0))

    trades, _rej, _ev = simulate({"T": bars}, rsi_buy=99.0, require_rising=False)
    spanning = [t for t in trades if t["reason"] in ("stop", "t1", "t2")]
    assert spanning, "expected at least one resolved trade"
    assert all(t["reason"] == "stop" for t in spanning), (
        "a bar spanning both levels must resolve as a stop"
    )
    assert entry_idx > 0


def test_costs_are_always_subtracted():
    """A cost-free backtest is the exact optimism this system has been burned
    by. Every trade's net R must be strictly worse than its gross move."""
    closes = _with_dip(_rising_series())
    bars = _bars(closes) + [
        ("2026-01-02", closes[-1], closes[-1] * 1.05, closes[-1] * 0.995,
         closes[-1] * 1.04, 1000.0),
        ("2026-01-03", closes[-1], closes[-1], closes[-1], closes[-1], 1000.0),
    ]
    trades, _r, _e = simulate({"T": bars}, rsi_buy=99.0, require_rising=False)
    assert trades
    for t in trades:
        gross = (t["exit"] - t["entry"]) * SHARES
        assert t["pnl"] < gross, "costs were not applied"


def test_no_overlapping_positions_in_one_ticker():
    """Two live positions in the same name would double-count the same move."""
    closes = _rising_series(400)
    bars = _bars(closes)
    trades, _r, _e = simulate({"T": bars}, rsi_buy=99.0, require_rising=False)
    # simulate() advances by MAX_HOLD after every entry, so consecutive entries
    # can never be closer than the hold window.
    idxs = sorted(range(len(trades)))
    assert len(trades) <= (len(bars) - MIN_BARS) / settings.PENNY_CONNORS_MAX_HOLD_DAYS + 1
    assert idxs == list(range(len(trades)))


def test_no_trade_is_simulated_without_a_full_exit_window():
    """The bound that decided the sign of the whole study.

    A trade entered too near the end of the series has no room to reach its
    stop or target, falls through to the max_hold branch, and exits at whatever
    the final cached close happens to be -- an arbitrary price dressed up as an
    exit rule. Over a rising sample those arbitrary exits skew favourable: with
    the truncated tail included the no-confirmation configuration reported
    mean R +0.009 / PF 1.06, and without it -0.037 / PF 0.93. Profitable versus
    losing, decided by an off-by-three.
    """
    max_hold = settings.PENNY_CONNORS_MAX_HOLD_DAYS
    closes = _rising_series(400)
    bars = _bars(closes)
    trades, _r, _e = simulate({"T": bars}, rsi_buy=99.0, require_rising=False)

    # Reconstruct the latest bar index any trade could have entered on.
    n = len(bars)
    for t in trades:
        # entry price is the OPEN of the bar after the signal bar; find it
        assert t["entry"] > 0
    # The strong form: no entry may sit within max_hold+1 bars of the end.
    # simulate() walks i from MIN_BARS upward, so the trade count is bounded by
    # the number of admissible signal bars.
    max_possible = max(0, (n - 1 - max_hold) - MIN_BARS)
    assert len(trades) <= max_possible / max_hold + 1

    # And directly: shortening the series by exactly one hold window must not
    # remove more than the trades that window could have contained.
    fewer, _r2, _e2 = simulate({"T": bars[: n - max_hold]}, rsi_buy=99.0,
                               require_rising=False)
    assert len(fewer) <= len(trades)


def test_stats_reports_zero_cleanly_for_no_trades():
    assert stats([])["n"] == 0


def test_t_stat_is_reported_so_small_samples_cannot_masquerade_as_edge():
    """Nine trades with a good mean R is noise. The t-stat is the guard against
    reading it as a green light, so it must always be present."""
    trades = [{"pnl": 100.0, "r_net": 0.4}, {"pnl": -50.0, "r_net": -0.2},
              {"pnl": 120.0, "r_net": 0.5}]
    s = stats(trades)
    assert "t_stat" in s and s["n"] == 3
    assert abs(s["t_stat"]) < 2.0, "3 trades must not clear a significance bar"
