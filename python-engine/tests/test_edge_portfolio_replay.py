"""R2 EDGE own-cash portfolio replay and EDGE_TRADER_V1 (research only)."""
from datetime import date, timedelta

import pytest

from edge_portfolio_replay import EdgeReplayConfig, run_edge_portfolio
from penny_edge_engine import Position


def _days(start="2026-08-03", n=12):
    out, day = [], date.fromisoformat(start)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


DAYS = _days()


def _rows(paths: dict, nifty="NIFTYBEES"):
    """paths: ticker -> {day: (o, h, l, c, v)}; default flat 20.0 bars."""
    rows = []
    for ticker in [nifty, *paths]:
        for day in DAYS:
            o, h, l, c, v = paths.get(ticker, {}).get(day, (20.0, 20.2, 19.8, 20.0, 1000.0))
            rows.append((ticker, day, o, h, l, c, v))
    return rows


def _scanner(signals: dict):
    """signals: day -> list[Position]; mimics scan_today's output contract."""
    def scan(**kwargs):
        return {"positions": list(signals.get(kwargs["as_of_date"], []))}
    return scan


def _pos(ticker="AAA", day=DAYS[0], close=20.0, subtype="MO_mid", shares=100, stop=19.5, target=20.6, hold=1):
    return Position(ticker, day, close, shares, target, stop, hold, subtype, 0.7, 0.7)


def _run(monkeypatch, rows, signals, **cfg):
    monkeypatch.setattr("penny_edge_live.scan_today", _scanner(signals))
    config = EdgeReplayConfig(tickers=tuple(sorted({r[0] for r in rows} - {"NIFTYBEES"})), **cfg)
    return run_edge_portfolio(rows, start=DAYS[0], end=DAYS[-1], config=config)


def test_entry_is_next_open_resized_to_signal_risk_never_signal_close(monkeypatch):
    rows = _rows({"AAA": {DAYS[1]: (20.2, 20.4, 20.1, 20.3, 1000.0)}})
    result = _run(monkeypatch, rows, {DAYS[0]: [_pos()]})
    trade = result["trades"][0]
    assert trade["entry_date"] == DAYS[1]
    assert trade["entry_price"] == pytest.approx(20.2 * 1.0005)
    # Same rupee risk at the worse price: 100 * 0.5 / (20.2101 - 19.5) -> 70 shares.
    assert trade["shares"] == int(100 * 0.5 // (20.2 * 1.0005 - 19.5))


def test_scheduled_time_exit_uses_that_close_and_never_a_later_high(monkeypatch):
    # Live clock: entry DAYS[1] (Tue), calendar age 3 on Fri DAYS[4]; a big
    # high on the following Monday must not be credited.
    paths = {"AAA": {DAYS[5]: (20.0, 25.0, 19.9, 24.0, 1000.0)}}
    result = _run(monkeypatch, _rows(paths), {DAYS[0]: [_pos(target=22.0)]})
    trade = result["trades"][0]
    assert (trade["exit_reason"], trade["exit_date"]) == ("TIME", DAYS[4])
    assert trade["exit_price"] == pytest.approx(20.0 * (1 - 0.0005))


def test_stop_wins_same_bar_ambiguity_and_gap_fills_at_open(monkeypatch):
    both = {"AAA": {DAYS[2]: (20.0, 21.0, 19.0, 20.0, 1000.0)}}
    trade = _run(monkeypatch, _rows(both), {DAYS[0]: [_pos()]})["trades"][0]
    assert trade["exit_reason"] == "STOP" and trade["exit_price"] == pytest.approx(19.5 * (1 - 0.0005))
    gap = {"AAA": {DAYS[2]: (19.0, 19.2, 18.8, 19.1, 1000.0)}}
    trade = _run(monkeypatch, _rows(gap), {DAYS[0]: [_pos()]})["trades"][0]
    assert trade["exit_reason"] == "STOP_GAP" and trade["exit_price"] == pytest.approx(19.0 * (1 - 0.0005))


def test_own_cash_limits_size_and_held_ticker_is_not_doubled(monkeypatch):
    signals = {DAYS[0]: [_pos(shares=1000, stop=19.0)], DAYS[1]: [_pos(day=DAYS[1], shares=10)]}
    result = _run(monkeypatch, _rows({"AAA": {}}), signals, bankroll=10000.0)
    first = result["trades"][0]
    assert first["shares"] * first["entry_price"] <= 10000.0
    assert result["admission_outcomes"]["CASH_LIMITED_RESIZE"] >= 1
    assert result["admission_outcomes"]["ALREADY_HELD"] == 1
    # Cash for under a quarter of the planned size is a skipped dust fill.
    dust = _run(monkeypatch, _rows({"AAA": {}}), {DAYS[0]: [_pos(shares=100000, stop=19.0)]}, bankroll=10000.0)
    assert dust["admission_outcomes"] == {"CASH_REJECTED_DUST": 1} and dust["trades"] == []


def test_drift_missing_session_and_zero_volume_are_no_fills(monkeypatch):
    drift = {"AAA": {DAYS[1]: (21.0, 21.2, 20.9, 21.0, 1000.0)}}
    assert _run(monkeypatch, _rows(drift), {DAYS[0]: [_pos()]})["admission_outcomes"] == {"DRIFT_REJECTED": 1}
    zero = {"AAA": {DAYS[1]: (20.0, 20.1, 19.9, 20.0, 0.0)}}
    assert _run(monkeypatch, _rows(zero), {DAYS[0]: [_pos()]})["admission_outcomes"] == {
        "NO_FILL_MISSING_OR_ZERO_VOLUME_SESSION": 1}


def test_cash_conserves_and_open_positions_are_marked_not_closed(monkeypatch):
    rows = _rows({"AAA": {}})
    result = _run(monkeypatch, rows, {DAYS[-2]: [_pos(day=DAYS[-2], hold=3)]}, bankroll=50000.0)
    trade = result["trades"][0]
    assert trade["status"] == "OPEN_MARKED" and "exit_price" not in trade
    closed = _run(monkeypatch, rows, {DAYS[0]: [_pos()]}, bankroll=50000.0)
    final = closed["equity_curve"][-1][1]
    assert final == pytest.approx(50000.0 + closed["summary"]["net_pnl"], abs=1e-6)


def test_trader_skips_failed_overnight_theses(monkeypatch):
    gap_down = {"AAA": {DAYS[1]: (19.85, 20.0, 19.7, 19.9, 1000.0)}}
    out = _run(monkeypatch, _rows(gap_down), {DAYS[0]: [_pos()]}, policy="EDGE_TRADER_V1")
    assert out["admission_outcomes"] == {"THESIS_SKIP_MO_GAP_DOWN": 1}
    # Baseline takes the same gap-down MO entry (within the 2% drift check).
    assert _run(monkeypatch, _rows(gap_down), {DAYS[0]: [_pos()]})["admission_outcomes"] == {"FILLED": 1}
    breakdown = {"AAA": {DAYS[0]: (20.5, 20.6, 19.9, 20.0, 1000.0), DAYS[1]: (19.85, 20.0, 19.6, 19.9, 1000.0)}}
    mr = _pos(subtype="MR_mid", stop=18.9, target=20.6, hold=2)
    out = _run(monkeypatch, _rows(breakdown), {DAYS[0]: [mr]}, policy="EDGE_TRADER_V1")
    assert out["admission_outcomes"] == {"THESIS_SKIP_MR_FRESH_BREAKDOWN": 1}


def test_trader_cuts_failed_mo_thesis_and_locks_breakeven(monkeypatch):
    signal = {DAYS[0]: (19.0, 20.1, 18.9, 20.0, 1000.0)}       # signal mid = 19.5
    fail = {"AAA": {**signal, DAYS[2]: (19.9, 20.0, 19.4, 19.45, 1000.0)}}
    trade = _run(monkeypatch, _rows(fail), {DAYS[0]: [_pos(stop=19.0, hold=2)]}, policy="EDGE_TRADER_V1")["trades"][0]
    assert trade["exit_reason"] == "THESIS_MO_GAVE_BACK"
    up = {"AAA": {**signal, DAYS[1]: (20.0, 21.1, 20.0, 21.05, 1000.0),
                  DAYS[2]: (20.9, 20.95, 19.9, 20.0, 1000.0)}}
    trade = _run(monkeypatch, _rows(up), {DAYS[0]: [_pos(stop=19.0, target=22.0, hold=2)]},
                 policy="EDGE_TRADER_V1")["trades"][0]
    assert trade["exit_reason"] == "STOP" and trade["exit_price"] >= trade["entry_price"] * (1 - 0.0005) - 1e-9
