"""Shared own-cash daily book plus the Range and Swing policies (research only)."""
from datetime import date, timedelta

import pytest

from daily_portfolio import BookConfig, DailySignal, RestingLevel, run_daily_book
from range_portfolio_replay import RangeReplayConfig, RangeTraderPolicy, run_range_portfolio
from swing_portfolio_replay import SwingBaselinePolicy, SwingTraderPolicy, _entry_limit


def _days(n=12, start="2026-08-03"):
    out, day = [], date.fromisoformat(start)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


DAYS = _days()
FLAT = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0}


def _bars(overrides=None):
    overrides = overrides or {}
    return {"AAA": {d: overrides.get(d, FLAT) for d in DAYS}, "IDX": {d: FLAT for d in DAYS}}


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1000.0}


class _Hold:
    """Minimal policy: one resting target, no close-time rule."""
    def __init__(self, levels=()):
        self.levels = levels

    def admit(self, signal, open_price):
        return None

    def resting_levels(self, position):
        return self.levels or (RestingLevel(position.signal.target, 1.0, "TARGET"),)

    def on_partial(self, position, level):
        position.stop = max(position.stop, position.entry_price)

    def at_close(self, position, bar, day, session_index):
        return None


def _book(bars, signals, policy=None, **cfg):
    def emit(day, equity):
        return signals.get(day, [])
    return run_daily_book(bars, DAYS, end=DAYS[-1], signals_after_close=emit, policy=policy or _Hold(),
                          config=BookConfig(bankroll=cfg.pop("bankroll", 100000.0), slippage_bps=0, **cfg),
                          costs=lambda e, x, q, intraday: 0.0)


def _sig(**kw):
    base = dict(ticker="AAA", signal_date=DAYS[0], reference_price=100.0, stop=95.0, target=110.0,
                planned_shares=10, kind="T")
    base.update(kw)
    return DailySignal(**base)


def test_resting_limit_fills_at_limit_or_gap_open_and_expires():
    dip = _bars({DAYS[2]: _bar(100, 101, 97, 100)})
    trade = _book(dip, {DAYS[0]: [_sig(entry_limit=98.0, entry_valid_sessions=3)]})["trades"][0]
    assert (trade["entry_date"], trade["entry_price"]) == (DAYS[2], 98.0)
    gap = _bars({DAYS[1]: _bar(96, 99, 96, 98)})
    assert _book(gap, {DAYS[0]: [_sig(entry_limit=98.0)]})["trades"][0]["entry_price"] == 96.0
    never = _book(_bars(), {DAYS[0]: [_sig(entry_limit=90.0, entry_valid_sessions=2)]})
    assert never["trades"] == [] and never["admission_outcomes"] == {"ENTRY_ORDER_EXPIRED": 1}


def test_partial_then_breakeven_and_open_position_cap():
    path = _bars({DAYS[2]: _bar(100, 106, 99.5, 105), DAYS[3]: _bar(104, 104, 99.0, 100)})
    policy = _Hold((RestingLevel(105.0, 0.5, "HALF"), RestingLevel(120.0, 1.0, "T2")))
    trade = _book(path, {DAYS[0]: [_sig()]}, policy)["trades"][0]
    assert [f["reason"] for f in trade["fills"]] == ["HALF", "STOP"]
    assert trade["fills"][0]["quantity"] == 5 and trade["fills"][1]["price"] == 100.0   # breakeven
    capped = _book(_bars(), {DAYS[0]: [_sig(), _sig(ticker="IDX")]}, max_open_positions=1)
    assert capped["admission_outcomes"]["OPEN_POSITION_CAP"] == 1


def test_net_pnl_reconciles_with_marked_equity():
    path = _bars({DAYS[3]: _bar(100, 111, 99.5, 110)})
    result = _book(path, {DAYS[0]: [_sig()]})
    assert result["equity_curve"][-1][1] == pytest.approx(100000.0 + result["summary"]["net_pnl"], abs=1e-3)


def test_range_trader_exits_broken_range_and_dead_money():
    signal = _sig(target=104.0, context={"range_low": 97.0})
    from daily_portfolio import OpenPosition
    position = OpenPosition(signal, DAYS[1], 1, 100.0, 10, 95.0)
    policy = RangeTraderPolicy()
    assert policy.at_close(position, _bar(100, 100, 96.5, 96.8), DAYS[2], 2) == "THESIS_RANGE_BROKEN"
    assert policy.at_close(position, _bar(100, 101, 99.5, 100.5), DAYS[4], 4) == "THESIS_NO_PROGRESS"
    assert policy.at_close(position, _bar(100, 103, 99.5, 102.5), DAYS[2], 2) is None
    assert position.stop == 100.0       # breakeven after half the way to the mean


def test_swing_entry_waits_for_pullback_only_when_extended():
    extended = {"close": 110.0, "ema_21": 100.0, "atr_14": 4.0}
    assert _entry_limit(extended, "BASELINE") is None
    assert _entry_limit(extended, "SWING_PULLBACK_ENTRY") == 106.0
    assert _entry_limit({"close": 103.0, "ema_21": 100.0, "atr_14": 4.0}, "SWING_TRADER_V1") is None


def test_swing_baseline_halves_at_t1_and_trader_lets_it_run():
    from daily_portfolio import OpenPosition
    signal = _sig(context={"target_1": 105.0, "target_2": 115.0, "atr": 2.0, "ema_21": 98.0,
                           "regime": "UNKNOWN", "score": 70})
    base = OpenPosition(signal, DAYS[1], 1, 100.0, 10, 95.0)
    reasons = sorted(level.reason for level in SwingBaselinePolicy().resting_levels(base))
    assert reasons == ["TARGET_1_HALF", "TARGET_2"]
    trader = OpenPosition(signal, DAYS[1], 1, 100.0, 10, 95.0)
    assert [l.reason for l in SwingTraderPolicy().resting_levels(trader)] == ["TARGET_2"]
    policy = SwingTraderPolicy()
    assert policy.at_close(trader, _bar(100, 106, 100, 105.5), DAYS[2], 2) is None
    assert trader.stop >= 100.0                         # breakeven after +1R close
    policy.at_close(trader, _bar(99, 99, 90, 91), DAYS[3], 3)
    assert policy.at_close(trader, _bar(91, 92, 89, 90), DAYS[4], 4) == "THESIS_TREND_BROKEN"


def test_range_reclaim_entry_waits_for_stabilization(monkeypatch):
    # A quiet 14-bar range needs more history than DAYS provides; build rows directly.
    days, day = [], date.fromisoformat("2026-06-01")
    while len(days) < 24:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    rows = []
    for i, d in enumerate(days):
        o, h, l, c = 100.0, 101.0, 99.7, 100.0 + (0.3 if i % 2 else -0.3)
        if i == 3:
            l = 98.0                                   # the range floor
        if i == 16:
            o, h, l, c = 99.6, 99.8, 98.4, 99.2       # touch of the range low
        if i == 17:
            o, h, l, c = 99.0, 99.5, 98.95, 99.1       # still weak: close below prior close
        if i == 18:
            o, h, l, c = 99.2, 99.7, 99.1, 99.6        # stabilization: up close above open
        if i == 19:
            o, h, l, c = 99.5, 100.5, 99.4, 100.0      # next open still below the range mean
        rows += [("AAA", d, o, h, l, c, 1000.0), ("NIFTY 50", d, 100, 101, 99, 100, 1000.0)]
    monkeypatch.setattr("config.settings.MAX_OPEN_POSITIONS", 6, raising=False)
    base = run_range_portfolio(rows, start=days[15], end=days[-1],
                               config=RangeReplayConfig(tickers=("AAA",), policy="BASELINE"))
    reclaim = run_range_portfolio(rows, start=days[15], end=days[-1],
                                  config=RangeReplayConfig(tickers=("AAA",), policy="RANGE_RECLAIM_ENTRY"))
    assert base["trades"][0]["entry_date"] == days[17]          # buys the day after the touch
    assert reclaim["trades"][0]["entry_date"] == days[19]       # waits for the stabilization close
    assert reclaim["funnel"]["arm:armed"] == 1 and reclaim["funnel"]["arm:entry"] == 1
