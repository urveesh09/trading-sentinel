"""B2: classic Penny CNC Connors lifecycle replay, held to the real runtime code."""
import asyncio
import copy
from datetime import date, datetime, timedelta, timezone

import aiosqlite
import pandas as pd
import pytest

from research_data_contracts import IST, validate_daily_rows, validate_intraday_rows
from research_penny_cnc_lifecycle import (
    PennyCncConfig, connors_decision, partial_candle, run_penny_cnc_lifecycle,
    scanner_daily_frame, tracker_step,
)

D = date(2026, 8, 10)          # Monday
ENTRY_DATE_UTC = "2026-08-10T04:00:00+00:00"


def _position(**overrides):
    pos = {"ticker": "AAA", "entry_price": 10.0, "entry_date": ENTRY_DATE_UTC, "shares": 40,
           "stop_loss_initial": 9.7, "trailing_stop_current": 9.7, "target_1": 10.3,
           "target_2": 10.6, "highest_close_since_entry": 10.0, "status": "OPEN",
           "realised_pnl": None, "atr_14_at_entry": 0.0, "regime_at_entry": "PR1_CALM"}
    pos.update(overrides)
    return pos


def _days(n, start=D):
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5 and day != date(2026, 8, 15):
            out.append(day)
        day += timedelta(days=1)
    return out


class _DailyKite:
    def __init__(self, bars, minutes=None):
        self.bars = bars
        self.minutes = minutes or {}
        self.minute_calls = []

    async def get_historical(self, ticker, from_date, to_date):
        row = self.bars.get(to_date)
        if row is None:
            return pd.DataFrame()
        return pd.DataFrame([{"date": pd.Timestamp(to_date), **row}]).set_index("date")

    async def get_intraday(self, ticker, from_datetime, to_datetime, interval="15minute"):
        assert interval == "minute"
        self.minute_calls.append(from_datetime[:10])
        rows = self.minutes.get(from_datetime[:10])
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{"datetime": pd.Timestamp(r["start"]), **{k: r[k] for k in ("open", "high", "low",
                                                                                         "close")}}
                             for r in rows]).set_index("datetime")


async def _real_tracker(tmp_path, pos, bars_by_day, minutes=None, kite=None):
    """Run the real position_tracker.update_daily_positions day by day."""
    from position_tracker import init_positions_db, update_daily_positions
    db_path = str(tmp_path / "tracker.db")
    await init_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO positions (ticker,exchange,entry_date,entry_price,shares,stop_loss_initial,"
            "trailing_stop_current,target_1,target_2,atr_14_at_entry,highest_close_since_entry,status,"
            "source,product_type,regime_at_entry) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("AAA", "NSE", pos["entry_date"], pos["entry_price"], pos["shares"],
             pos["stop_loss_initial"], pos["trailing_stop_current"], pos["target_1"], pos["target_2"],
             0.0, pos["highest_close_since_entry"], "OPEN", "PENNY_PAPER", "CNC", "PR1_CALM"))
        await db.commit()

    async def record(ticker, pnl, source):
        return None

    kite = kite or _DailyKite({d.isoformat(): bar for d, bar in bars_by_day}, minutes)
    states = []
    for day, _bar in bars_by_day:
        await update_daily_positions(db_path, kite, day.isoformat(), record)
        async with aiosqlite.connect(db_path) as db:
            states.append(await (await db.execute(
                "SELECT status,shares,trailing_stop_current,exit_price,exit_date,realised_pnl "
                "FROM positions")).fetchone())
    return states


def _pure_tracker(pos, bars_by_day, minutes=None):
    pos = copy.deepcopy(pos)
    states = []
    for day, bar in bars_by_day:
        if not pos.get("closed"):
            tracker_step(pos, bar, day, minutes=(minutes or {}).get(day.isoformat()))
            if pos.get("closed"):
                pos["exit_date"] = day.isoformat()
        states.append((pos["status"], pos["shares"], pos["trailing_stop_current"],
                       pos.get("exit_price"), pos.get("exit_date"), pos.get("realised_pnl")))
    return states


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 100000}


QUIET = _bar(10.0, 10.1, 9.9, 10.05)
SCENARIOS = {
    "stop": [_bar(10.0, 10.1, 9.6, 9.8)],
    "gap_stop": [_bar(10.0, 10.1, 9.9, 10.0), _bar(9.5, 9.6, 9.4, 9.5)],
    "t1_then_breakeven_stop": [_bar(10.0, 10.35, 10.02, 10.2), _bar(10.1, 10.15, 9.9, 10.0)],
    "t1_then_t2": [_bar(10.0, 10.35, 10.02, 10.2), _bar(10.3, 10.7, 10.2, 10.6)],
    "time_stop": [_bar(10.0, 10.1, 9.9, 10.05)] * 13,
    # [O26c] Both touched on one daily bar: the stop, unless the day opened at a target or at/under the stop.
    "after_t1_stop_and_t1_same_day_stops": [_bar(10.0, 10.35, 10.02, 10.2), _bar(10.2, 10.4, 9.9, 10.1),
                                            _bar(10.1, 10.2, 10.05, 10.1)],
    "stop_and_t1_same_day_takes_the_stop": [_bar(10.0, 10.35, 9.6, 10.0)],
    "opened_at_t2_then_fell_through_the_stop_takes_t2": [QUIET, _bar(10.8, 10.9, 9.5, 9.6)],
    "opened_under_the_stop_then_rallied_takes_the_stop": [QUIET, _bar(9.5, 10.9, 9.4, 10.6)],
    # [O26d] The open settles only what it reaches; the rest of the bar is ordered stop-first.
    "opened_at_t1_then_stop_and_t2_takes_the_half_then_breakeven": [QUIET, _bar(10.3, 10.7, 9.5, 9.6)],
    "t1_and_t2_same_day_takes_the_t1_half_first": [QUIET, _bar(10.1, 10.7, 10.05, 10.6)],
    "t1_then_under_entry_same_day_takes_breakeven": [QUIET, _bar(10.1, 10.35, 9.98, 10.2)],
    "after_t1_gap_under_breakeven_takes_the_open": [_bar(10.0, 10.35, 10.02, 10.2), _bar(9.8, 10.7, 9.7, 10.5)],
    "after_t1_open_at_t2_takes_the_open": [_bar(10.0, 10.35, 10.02, 10.2), _bar(10.8, 10.9, 9.5, 9.6)],
    "entry_day_open_came_before_the_entry": [_bar(10.8, 10.9, 9.95, 10.5)],
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_tracker_matches_the_real_position_tracker(tmp_path, name):
    bars = SCENARIOS[name]
    bars_by_day = list(zip(_days(len(bars)), bars))
    real = asyncio.run(_real_tracker(tmp_path, _position(), bars_by_day))
    pure = _pure_tracker(_position(), bars_by_day)
    for got, want in zip(pure, real):
        assert got[:5] == want[:5], (name, got, want)
        assert (got[5] is None and want[5] is None) or got[5] == pytest.approx(want[5]), name


@pytest.mark.parametrize("name,want", [
    ("stop_and_t1_same_day_takes_the_stop", [("STOPPED_OUT", 9.7)]),
    ("after_t1_stop_and_t1_same_day_stops", [("CLOSED_T1", None), ("STOPPED_OUT", 10.0)]),
    ("opened_at_t2_then_fell_through_the_stop_takes_t2", [("OPEN", None), ("CLOSED_T2", 10.8)]),
    ("opened_under_the_stop_then_rallied_takes_the_stop", [("OPEN", None), ("STOPPED_OUT", 9.5)]),
])
def test_a_daily_bar_touching_the_stop_and_a_target_takes_the_stop(tmp_path, name, want):
    """[O26c, Oct 26 audit O26-P1] The tracker's comment said stop-first; its branch took the target (stop 95,
    target 110, a bar touching both: CLOSED_T2 at 110). And after the T1 half, a day touching T1 and the breakeven
    stop held the rest. A daily bar cannot order the touches: the stop is taken unless the day opened at a target."""
    bars = SCENARIOS[name]
    real = asyncio.run(_real_tracker(tmp_path, _position(), list(zip(_days(len(bars)), bars))))
    for got, (status, price) in zip(real, want):
        assert got[0] == status and (price is None or got[3] == pytest.approx(price)), (name, got)


def _two_legs(t1, rest, day, shares=40):
    """Realised P&L of the T1 half at ``t1`` and the rest at ``rest`` on ``day``, with the tracker's charges."""
    from position_tracker import settlement_costs
    pos = _position()
    half = shares // 2
    return ((t1 - 10.0) * half - settlement_costs(pos, t1, half, day)
            + (rest - 10.0) * (shares - half) - settlement_costs(pos, rest, shares - half, day))


@pytest.mark.parametrize("name,status,shares,exit_price,t1", [
    # Independent review R1: open 10.3 (T1), high 10.7 (over T2 10.6), low 9.5 (under the stop 9.7). The open
    # proves only the T1 half; the rest then has a breakeven stop, and the bar cannot say whether 10.0 or 10.6
    # came first. It used to close all 40 at T2 10.6.
    ("opened_at_t1_then_stop_and_t2_takes_the_half_then_breakeven", "STOPPED_OUT", 20, 10.0, 10.3),
    # From 10.1 to 10.7 the price passed T1 first: the half at 10.3, the rest at T2. It closed all 40 at 10.6.
    ("t1_and_t2_same_day_takes_the_t1_half_first", "CLOSED_T2", 20, 10.6, 10.3),
    # T1, and a low under the entry: the breakeven stop that T1 made active may have come after it.
    ("t1_then_under_entry_same_day_takes_breakeven", "STOPPED_OUT", 20, 10.0, 10.3),
    # The entry day's open (10.8) came before the 09:30 entry at 10.0: not a T2 fill. It closed all 40 at 10.8.
    ("entry_day_open_came_before_the_entry", "STOPPED_OUT", 20, 10.0, 10.3),
])
def test_the_open_settles_only_what_it_reaches_and_the_rest_of_the_bar_is_stop_first(
        tmp_path, name, status, shares, exit_price, t1):
    """[O26d, independent review R1] Known events at the open are taken first; later touches are not
    ordered by a daily bar, so a stop in reach (the breakeven one included) comes before a target."""
    bars = SCENARIOS[name]
    days = _days(len(bars))
    real = asyncio.run(_real_tracker(tmp_path, _position(), list(zip(days, bars))))
    final = real[-1]
    assert final[:5] == (status, shares, 10.0, pytest.approx(exit_price), days[-1].isoformat()), (name, final)
    assert final[5] == pytest.approx(_two_legs(t1, exit_price, days[-1].isoformat())), name


@pytest.mark.parametrize("name,want", [
    # Already past T1 (stop at breakeven 10.0): a gap under it fills at the open, a gap over T2 at the open.
    ("after_t1_gap_under_breakeven_takes_the_open", ("STOPPED_OUT", 9.8)),
    ("after_t1_open_at_t2_takes_the_open", ("CLOSED_T2", 10.8)),
])
def test_an_already_partial_position_takes_what_the_open_settles(tmp_path, name, want):
    bars = SCENARIOS[name]
    real = asyncio.run(_real_tracker(tmp_path, _position(), list(zip(_days(len(bars)), bars))))
    assert real[0][:2] == ("CLOSED_T1", 20) and real[1][0] == want[0] and real[1][3] == pytest.approx(want[1])


def _minutes(day, waypoints, *, first=(9, 15), last=(15, 29)):
    """Minute bars along straight lines between (minute index, price) waypoints."""
    start = datetime(day.year, day.month, day.day, *first)
    count = (last[0] * 60 + last[1]) - (first[0] * 60 + first[1]) + 1
    prices = []
    for (i0, p0), (i1, p1) in zip(waypoints, waypoints[1:]):
        prices += [p0 + (p1 - p0) * (i - i0) / (i1 - i0) for i in range(i0, i1)]
    prices += [waypoints[-1][1]] * (count + 1 - len(prices))
    rows = []
    for i in range(count):
        o, c = round(prices[i], 4), round(prices[i + 1], 4)
        rows.append({"start": start + timedelta(minutes=i), "open": o, "high": max(o, c), "low": min(o, c),
                     "close": c})
    return rows


def _day_bar(rows):
    return _bar(rows[0]["open"], max(r["high"] for r in rows), min(r["low"] for r in rows), rows[-1]["close"])


@pytest.mark.parametrize("path,status,shares,exit_price,realised_legs", [
    # Up through T1 and T2 first, down through the stop later: the half at 10.3, the rest at T2 10.6.
    ([(0, 10.1), (30, 10.7), (200, 9.6), (374, 10.5)], "CLOSED_T2", 20, 10.6, (10.3, 10.6)),
    # Down through the stop first: all 40 at 9.7, though the day later reached T2.
    ([(0, 10.1), (30, 9.6), (200, 10.7), (374, 10.5)], "STOPPED_OUT", 40, 9.7, None),
])
def test_a_day_the_daily_bar_cannot_order_is_walked_through_its_minutes(tmp_path, path, status, shares,
                                                                        exit_price, realised_legs):
    """[O26d] The same daily bar (open 10.1, high 10.7, low 9.6) gives two different days; its minute bars
    say which. The research mirror, given the same minutes, books the same."""
    days = _days(2)
    rows = _minutes(days[1], path)
    bars_by_day = [(days[0], QUIET), (days[1], _day_bar(rows))]
    minutes = {days[1].isoformat(): rows}
    kite = _DailyKite({d.isoformat(): b for d, b in bars_by_day}, minutes)
    real = asyncio.run(_real_tracker(tmp_path, _position(), bars_by_day, kite=kite))
    pure = _pure_tracker(_position(), bars_by_day, minutes)
    assert kite.minute_calls == [days[1].isoformat()]          # the quiet day needed none
    assert real[1][:5] == (status, shares, real[1][2], pytest.approx(exit_price), days[1].isoformat())
    if realised_legs:
        assert real[1][5] == pytest.approx(_two_legs(*realised_legs, days[1].isoformat()))
    assert pure[1][:5] == real[1][:5] and pure[1][5] == pytest.approx(real[1][5])


def test_entry_day_minutes_before_the_entry_are_not_evidence(tmp_path):
    """[O26d] 09:15-09:29 ran to 10.9 (over T2) before the 09:30 entry at 10.0; after it the price only drifted.
    The daily bar alone would book the T1 half and a breakeven stop; its minutes after the entry show nothing."""
    day = _days(1)[0]
    rows = _minutes(day, [(0, 10.5), (8, 10.9), (15, 10.0), (100, 9.98), (374, 10.1)])
    bars_by_day = [(day, _day_bar(rows))]
    minutes = {day.isoformat(): rows}
    real = asyncio.run(_real_tracker(tmp_path, _position(), bars_by_day, minutes=minutes))
    assert real[0][:5] == ("OPEN", 40, 9.7, None, None)
    assert _pure_tracker(_position(), bars_by_day, minutes)[0][:5] == real[0][:5]
    (tmp_path / "daily").mkdir()
    daily_only = asyncio.run(_real_tracker(tmp_path / "daily", _position(), bars_by_day))
    assert daily_only[0][:2] == ("STOPPED_OUT", 20)


@pytest.mark.parametrize("trim", ["late_start", "early_end", "missing_low", "empty"])
def test_minutes_that_cannot_stand_for_the_day_leave_the_stop_first_result(tmp_path, trim):
    """[O26d] Minute bars that start late, end before 15:14, miss the day's low or are absent are not used."""
    days = _days(2)
    rows = _minutes(days[1], [(0, 10.1), (30, 10.7), (200, 9.6), (374, 10.5)])
    day_bar = _day_bar(rows)
    rows = {"late_start": rows[5:], "early_end": rows[:300],
            "missing_low": [r for r in rows if r["low"] > 9.65], "empty": []}[trim]
    bars_by_day = [(days[0], QUIET), (days[1], day_bar)]
    real = asyncio.run(_real_tracker(tmp_path, _position(), bars_by_day, minutes={days[1].isoformat(): rows}))
    assert real[1][0] == "STOPPED_OUT" and real[1][1] == 40 and real[1][3] == pytest.approx(9.7)


def test_unsorted_minutes_are_put_in_time_order():
    from position_tracker import day_exits
    days = _days(2)
    rows = _minutes(days[1], [(0, 10.1), (30, 10.7), (200, 9.6), (374, 10.5)])
    shuffled = rows[::-1]
    got = day_exits("OPEN", 9.7, 10.0, 10.3, 10.6, _day_bar(rows), minutes=shuffled)
    assert got["basis"] == "MINUTES" and got["t1"] == 10.3 and got["close"] == ("CLOSED_T2", 10.6)


def test_one_share_t1_closes_fully_like_the_real_tracker(tmp_path):
    bars_by_day = [(D, _bar(10.0, 10.35, 9.95, 10.2))]
    real = asyncio.run(_real_tracker(tmp_path, _position(shares=1), bars_by_day))
    pure = _pure_tracker(_position(shares=1), bars_by_day)
    assert pure[0][:5] == real[0][:5] and real[0][0] == "CLOSED_T1" and real[0][4] == D.isoformat()


def test_time_stop_is_fifteen_calendar_days():
    pos = _position()
    bars_by_day = list(zip(_days(12), [_bar(10.0, 10.1, 9.9, 10.05)] * 12))
    states = _pure_tracker(pos, bars_by_day)
    closing = [s for s in states if s[0] == "CLOSED_TIME"]
    assert closing and closing[0][4] == "2026-08-25"          # 15 calendar days after Aug 10


# ---- entry parity -------------------------------------------------------------

def _connors_history():
    """An uptrend with a 4-day pullback whose RSI(2) is < 10 and rising for 2 bars."""
    prior_days = []
    day = D - timedelta(days=1)
    while len(prior_days) < 259:
        if day.weekday() < 5 and day not in (date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26),
                                             date(2026, 3, 31), date(2026, 4, 3), date(2026, 4, 14),
                                             date(2026, 5, 1), date(2026, 5, 28), date(2026, 6, 26)):
            prior_days.append(day)
        day -= timedelta(days=1)
    prior_days.reverse()
    closes = [50.0 + 0.2 * i for i in range(len(prior_days))]
    closes[-3] = closes[-4] - 1.0      # deltas: -1, -1, +0.02, then today's partial -0.3
    closes[-2] = closes[-3] - 1.0
    closes[-1] = closes[-2] + 0.02
    rows = [("AAA", d.isoformat(), c, c * 1.01, c * 0.99, c, 100000.0) for d, c in zip(prior_days, closes)]
    return rows, closes[-1]


def _minute_rows(day, last_close, *, volume=4000.0):
    start = datetime(day.year, day.month, day.day, 9, 15)
    target = last_close - 0.3
    rows = []
    for minute in range(16):                     # 09:15 .. 09:30
        stamp = start + timedelta(minutes=minute)
        px = target
        rows.append(("AAA", "minute", stamp.strftime("%Y-%m-%d %H:%M:%S"), px, px + 0.01, px - 0.01,
                     px, volume))
    return rows


class _HistoricalKite:
    def __init__(self, frame):
        self.frame = frame
        self.instrument_cache = {"AAA": 1}

    async def get_historical(self, ticker, from_date, to_date):
        return self.frame[(self.frame.index >= pd.Timestamp(from_date))
                          & (self.frame.index <= pd.Timestamp(to_date))]


@pytest.mark.parametrize("volume,accept", [(4000.0, True), (2000.0, False)])
def test_entry_matches_the_real_scanner(tmp_path, volume, accept):
    from penny_risk import PennyRiskEngine
    from penny_scanner import PennyScanner
    from config import settings

    daily_rows, last_close = _connors_history()
    daily = validate_daily_rows(daily_rows, tickers=["AAA"], before=D)
    minutes = validate_intraday_rows(_minute_rows(D, last_close, volume=volume), interval="minute",
                                     start=D, end=D, tickers=["AAA"])
    partial = partial_candle(minutes.bars[("AAA", D.isoformat())])
    frame = scanner_daily_frame(daily, "AAA", D, partial)
    as_of = datetime(2026, 8, 10, 9, 30, tzinfo=IST)
    mine = connors_decision("AAA", frame, risk_engine=PennyRiskEngine(settings.PENNY_PAPER_BANKROLL),
                            regime="PR1_CALM", as_of=as_of)
    scanner = PennyScanner(kite=_HistoricalKite(frame), universe_json_path=str(tmp_path / "u.json"),
                           paper_mode=True, regime="PR1_CALM")
    live = asyncio.run(scanner._evaluate_ticker_connors("AAA", as_of=as_of))
    assert live["accept"] is mine["accept"] is accept, (live, mine)
    if accept:
        for key in ("entry", "stop_loss", "target_1", "target_2", "shares", "rsi_2"):
            assert live[key] == mine[key], key
    else:
        assert live["reject_reason"] == mine["reject_reason"] == "volume too low (dead stock)"


def test_end_to_end_one_trade_with_t1_partial_then_t2(tmp_path):
    daily_rows, last_close = _connors_history()
    entry_close = last_close - 0.3
    after = []
    for day, (o, h, l, c) in zip(_days(3), [(entry_close, entry_close * 1.005, entry_close * 0.99,
                                             entry_close * 1.0),
                                            (entry_close * 1.02, entry_close * 1.07, entry_close * 1.01,
                                             entry_close * 1.06),
                                            (entry_close, entry_close, entry_close, entry_close)]):
        after.append(("AAA", day.isoformat(), o, h, l, c, 100000.0))
    daily = validate_daily_rows(daily_rows + after, tickers=["AAA"], before=date(2026, 8, 31))
    minutes = validate_intraday_rows(_minute_rows(D, last_close), interval="minute",
                                     start=D, end=D, tickers=["AAA"])
    result = run_penny_cnc_lifecycle(minutes, daily, PennyCncConfig(tickers=("AAA",)),
                                     start=D.isoformat(), end=D.isoformat(),
                                     settle_through="2026-08-12")
    assert result["scope"] == "LIFECYCLE"
    assert result["funnel"]["admission_outcomes"] == {"FILLED": 1}
    trade = result["trades"][0]
    assert [e["reason"] for e in trade["events"]] == ["T1_PARTIAL", "CLOSED_T2"]
    assert trade["net_pnl"] is not None and result["summary"]["closed_trades"] == 1
    assert result["can_place_orders"] is False


def test_live_book_is_unsupported_and_missing_partial_candle_is_reported():
    daily_rows, last_close = _connors_history()
    daily = validate_daily_rows(daily_rows, tickers=["AAA"], before=D)
    minutes = validate_intraday_rows([], interval="minute", start=D, end=D, tickers=["AAA"])
    live = run_penny_cnc_lifecycle(minutes, daily, PennyCncConfig(tickers=("AAA",), book="PENNY"),
                                   start=D.isoformat(), end=D.isoformat())
    assert live["status"] == "UNSUPPORTED"
    paper = run_penny_cnc_lifecycle(minutes, daily, PennyCncConfig(tickers=("AAA",)),
                                    start=D.isoformat(), end=D.isoformat())
    assert paper["status"] == "UNAVAILABLE"
    assert paper["funnel"]["NO_PARTIAL_CANDLE_EVIDENCE"] == 1


def test_lab_registers_cnc_lifecycle_with_honest_scope():
    import backtest_lab
    adapter = backtest_lab.STRATEGY_REGISTRY["penny_cnc_connors_lifecycle_1d"]
    assert adapter.metadata.scope == "LIFECYCLE" and adapter.metadata.can_place_orders is False
    with pytest.raises(ValueError, match="explicit ticker list"):
        adapter.snapshot_config({})
    assert adapter.snapshot_config({"tickers": [" aaa "]}) == {"tickers": ["AAA"], "regime": "PR1_CALM"}
