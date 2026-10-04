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
    def __init__(self, bars):
        self.bars = bars

    async def get_historical(self, ticker, from_date, to_date):
        row = self.bars.get(to_date)
        if row is None:
            return pd.DataFrame()
        return pd.DataFrame([{"date": pd.Timestamp(to_date), **row}]).set_index("date")


async def _real_tracker(tmp_path, pos, bars_by_day):
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

    kite = _DailyKite({d.isoformat(): bar for d, bar in bars_by_day})
    states = []
    for day, _bar in bars_by_day:
        await update_daily_positions(db_path, kite, day.isoformat(), record)
        async with aiosqlite.connect(db_path) as db:
            states.append(await (await db.execute(
                "SELECT status,shares,trailing_stop_current,exit_price,exit_date,realised_pnl "
                "FROM positions")).fetchone())
    return states


def _pure_tracker(pos, bars_by_day):
    pos = copy.deepcopy(pos)
    states = []
    for day, bar in bars_by_day:
        if not pos.get("closed"):
            tracker_step(pos, bar, day)
            if pos.get("closed"):
                pos["exit_date"] = day.isoformat()
        states.append((pos["status"], pos["shares"], pos["trailing_stop_current"],
                       pos.get("exit_price"), pos.get("exit_date"), pos.get("realised_pnl")))
    return states


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 100000}


SCENARIOS = {
    "stop": [_bar(10.0, 10.1, 9.6, 9.8)],
    "gap_stop": [_bar(10.0, 10.1, 9.9, 10.0), _bar(9.5, 9.6, 9.4, 9.5)],
    "t1_then_breakeven_stop": [_bar(10.0, 10.35, 9.95, 10.2), _bar(10.1, 10.15, 9.9, 10.0)],
    "t1_then_t2": [_bar(10.0, 10.35, 9.95, 10.2), _bar(10.3, 10.7, 10.2, 10.6)],
    "time_stop": [_bar(10.0, 10.1, 9.9, 10.05)] * 13,
    "after_t1_stop_and_t1_same_day_holds": [_bar(10.0, 10.35, 9.95, 10.2), _bar(10.2, 10.4, 9.9, 10.1),
                                            _bar(10.1, 10.2, 10.05, 10.1)],
    "stop_and_t1_same_day_takes_t1": [_bar(10.0, 10.35, 9.6, 10.0)],
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
    for day, (o, h, l, c) in zip(_days(3), [(entry_close, entry_close * 1.04, entry_close * 0.99,
                                             entry_close * 1.02),
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
