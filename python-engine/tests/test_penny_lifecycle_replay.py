"""[B2 2026-10-03] Classic Penny MIS lifecycle replay: parity with shipped runtime."""
import asyncio
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from penny_lifecycle_replay import (
    PennyLifecycleConfig, _Replay, _TickerDay, reject_code, run_penny_lifecycle,
)
from research_data_contracts import IST, validate_daily_rows, validate_intraday_rows

DAY = "2026-08-10"  # Monday

BASE = (98.8, 100.0, 98.0)          # open, high, low of quiet pre-breakout bars
BREAKOUT = (99.5, 101.0, 99.0, 100.5, 1000.0)
POST = (101.0, 101.2, 100.5, 101.0, 1000.0)


def _bars(ticker="AAA", day=DAY, *, overrides=None, end="15:29", post_from=None, post=POST):
    """One minute session; ``overrides`` maps HH:MM -> (o, h, l, c, v)."""
    overrides = overrides or {}
    rows, start = [], datetime.fromisoformat(f"{day}T09:15:00")
    minute = 0
    while True:
        stamp = start + timedelta(minutes=minute)
        label = stamp.strftime("%H:%M")
        if label > end:
            break
        if label in overrides:
            values = overrides[label]
        elif post_from and label >= post_from:
            values = post
        else:
            close = 98.5 if minute % 2 else 99.0
            values = (*BASE, close, 1000.0)
        if values is not None:
            rows.append((ticker, "minute", stamp.strftime("%Y-%m-%d %H:%M:%S"), *values))
        minute += 1
    return rows


def _daily(tickers=("AAA",), day=DAY, close=99.0, volume=100000.0):
    rows = []
    for ticker in tickers:
        current, count = date.fromisoformat(day), 0
        while count < 25:
            current -= timedelta(days=1)
            if current.weekday() >= 5:
                continue
            rows.append((ticker, current.isoformat(), close, close * 1.01, close * 0.99, close, volume))
            count += 1
    return rows


def _run(rows, tickers=("AAA",), daily=None, start=DAY, end=DAY, **config):
    intraday = validate_intraday_rows(rows, interval="minute", start=start, end=end, tickers=tickers)
    daily_ds = validate_daily_rows(daily or _daily(tickers, start), tickers=tickers, before=end)
    cfg = PennyLifecycleConfig(tickers=tuple(tickers), **config)
    return run_penny_lifecycle(intraday, daily_ds, cfg, start=start, end=end)


def _breakout_day(**extra):
    overrides = {"10:30": BREAKOUT, "10:31": (100.7, 101.2, 100.5, 101.0, 1000.0)}
    overrides.update(extra.pop("overrides", {}))
    return _bars(overrides=overrides, post_from="10:32", **extra)


def test_entry_uses_live_clock_next_minute_ltp_fill_and_real_sizing():
    result = _run(_breakout_day())
    assert result["scope"] == "LIFECYCLE" and result["status"] == "COMPLETE"
    trade = result["trades"][0]
    assert trade["decision_bar_ts"] == "2026-08-10T10:30:00+05:30"
    assert trade["as_of"] == "2026-08-10T10:31:00+05:30"
    assert trade["entry_fill_ts"] == "2026-08-10T10:31:00+05:30"
    assert trade["entry_fill_price"] == 100.7           # LTP = open of bar k, not signal close
    assert trade["signal_entry"] == round(100.5 * 1.003, 2)
    assert trade["stop_price"] == 99.0
    # PennyRiskEngine: min(5% of 100000 / risk, PER_STOCK_CAP 500 / entry) = 4 shares
    assert trade["shares"] == 4
    assert result["funnel"]["admission_outcomes"] == {"FILLED": 1}


def test_live_book_never_exits_at_target_and_force_closes_at_1500():
    rows = _breakout_day(overrides={"12:00": (101.0, 110.0, 101.0, 102.0, 1000.0)})
    trade = _run(rows)["trades"][0]
    assert trade["target_price"] < 110.0                 # target touched intraday ...
    assert trade["exit_reason"] == "MIS_TIME_STOP_1500"  # ... but the live book holds
    assert trade["exit_fill_ts"] == "2026-08-10T15:00:00+05:30"
    assert trade["smart_eod"]["reason"] == "profit_far_from_target"


def test_time_window_is_aligned_to_the_completed_bar_clock():
    early = _bars(overrides={"10:29": BREAKOUT, "10:30": (100.7, 101.2, 100.5, 101.0, 1000.0)},
                  post_from="10:31")
    trade = _run(early)["trades"][0]
    assert trade["decision_bar_ts"].endswith("10:29:00+05:30")   # visible and in window at 10:30
    late = _bars(overrides={"14:29": BREAKOUT, "14:30": (100.7, 101.2, 100.5, 101.0, 1000.0)})
    result = _run(late)
    assert result["trades"] == [] and result["summary"]["net_pnl"] is None
    assert result["funnel"]["reject_codes"]["TIME_WINDOW"] > 0


def test_decision_never_sees_future_bars():
    base = _run(_breakout_day())["trades"][0]
    future = _breakout_day(overrides={"10:31": (100.7, 999.0, 100.5, 101.0, 9_999_999.0)})
    changed = _run(future)["trades"][0]
    keys = ("decision_bar_ts", "signal_entry", "stop_price", "target_price", "shares",
            "rsi_14", "cum_vol_today", "median_vol_20d")
    assert {k: base[k] for k in keys} == {k: changed[k] for k in keys}


@pytest.mark.parametrize("bar,outcome", [
    ((103.0, 103.2, 102.9, 103.0, 1000.0), "DRIFT_REJECTED"),
    ((98.9, 99.2, 98.5, 99.0, 1000.0), "STOP_ALREADY_BREACHED"),
    ((100.7, 100.7, 100.7, 100.7, 0.0), "NO_EXECUTABLE_EVIDENCE"),
])
def test_executor_checks_and_execution_evidence(bar, outcome):
    result = _run(_breakout_day(overrides={"10:31": bar}))
    assert result["funnel"]["admission_outcomes"].get(outcome) >= 1
    assert all(t["entry_fill_ts"] != "2026-08-10T10:31:00+05:30" for t in result["trades"])


def test_paper_stop_polls_ltp_while_live_broker_stop_sees_the_wick():
    wick = {"11:00": (101.0, 101.2, 98.5, 101.0, 1000.0)}
    paper = _run(_breakout_day(overrides=wick), book="PENNY_PAPER")["trades"][0]
    live = _run(_breakout_day(overrides=wick), book="PENNY")["trades"][0]
    assert paper["exit_reason"] == "MIS_TIME_STOP_1500"
    assert live["exit_reason"] == "BROKER_STOP" and live["exit_fill_price"] == 99.0
    assert live["exit_fill_ts"] == "2026-08-10T11:00:00+05:30"


def test_paper_stop_fills_at_the_polled_ltp_and_live_gap_fills_at_open():
    gap = {"11:00": (97.0, 97.5, 96.5, 97.0, 1000.0)}
    paper = _run(_breakout_day(overrides=gap), book="PENNY_PAPER")["trades"][0]
    assert (paper["exit_reason"], paper["exit_fill_price"]) == ("PAPER_STOP_LTP", 97.0)
    live = _run(_breakout_day(overrides=gap), book="PENNY")["trades"][0]
    assert (live["exit_reason"], live["exit_fill_price"]) == ("BROKER_STOP_GAP", 97.0)
    assert paper["net_pnl"] < 0 and paper["r_multiple"] < -1


@pytest.mark.parametrize("price,reason", [
    (103.8, "SMART_EOD:within_0_5R_of_target"),
    (99.5, "SMART_EOD:time_stop_30min_in_loss"),
])
def test_1430_job_uses_runtime_branch_order(price, reason):
    late = (price, price + 0.1, price - 0.1, price, 1000.0)
    rows = _breakout_day(overrides={f"{h:02d}:{m:02d}": late
                                    for h in (14,) for m in range(0, 60)})
    trade = _run(rows)["trades"][0]
    assert trade["exit_reason"] == reason
    assert trade["exit_fill_ts"] == "2026-08-10T14:30:00+05:30" and trade["exit_fill_price"] == price


def test_fresh_loss_holds_at_1430_then_force_closes():
    overrides = {"14:15": BREAKOUT, "14:16": (100.7, 101.2, 100.5, 101.0, 1000.0)}
    overrides.update({f"{h:02d}:{m:02d}": (100.0, 100.1, 99.9, 100.0, 1000.0)
                      for h in (14, 15) for m in range(0, 60) if (h, m) > (14, 16)})
    trade = _run(_bars(overrides=overrides))["trades"][0]
    assert trade["smart_eod"]["reason"] == "fresh_loss"
    assert trade["exit_reason"] == "MIS_TIME_STOP_1500"


def test_capacity_one_per_ticker_three_mis_and_alphabetical_admission():
    tickers = ("AAA", "BBB", "CCC", "DDD")
    rows = [row for t in tickers for row in _bars(
        t, overrides={"10:30": BREAKOUT, "10:31": (100.7, 101.2, 100.5, 101.0, 1000.0)},
        post_from="10:32")]
    result = _run(rows, tickers=tickers)
    assert sorted(t["ticker"] for t in result["trades"]) == ["AAA", "BBB", "CCC"]
    assert result["funnel"]["admission_outcomes"]["CAPACITY_REJECTED"] >= 1


def test_reentry_after_exit_is_allowed_but_not_while_occupied():
    overrides = {
        "11:00": (98.0, 98.2, 97.8, 98.0, 1000.0),              # paper stop at 98.0
        "12:00": (100.9, 101.8, 100.7, 101.6, 1000.0),          # second breakout
        "12:01": (102.1, 102.4, 101.9, 102.2, 1000.0),
    }
    overrides.update({f"11:{m:02d}": (100.9, 101.1, 100.7, 101.0 if m % 2 else 100.8, 1000.0)
                      for m in range(1, 60)})
    rows = _breakout_day(overrides=overrides, post=(101.0, 101.2, 100.5, 101.0, 1000.0))
    rows = [r if r[2][11:16] < "12:02" else (*r[:3], 102.2, 102.4, 101.9, 102.2, 1000.0) for r in rows]
    result = _run(rows)
    assert [t["exit_reason"] for t in result["trades"]][:1] == ["PAPER_STOP_LTP"]
    assert len(result["trades"]) == 2
    assert result["trades"][1]["decision_bar_ts"].endswith("12:00:00+05:30")


def test_truncated_session_marks_trade_unresolved_and_run_partial():
    rows = _breakout_day(end="14:29")
    result = _run(rows, session_policy="allow_gaps")
    trade = result["trades"][0]
    assert trade["status"] == "UNRESOLVED"
    assert trade["exit_reason"].startswith("UNRESOLVED_NO_EXIT_EVIDENCE")
    assert result["status"] == "PARTIAL" and result["summary"]["closed_trades"] == 0
    assert result["summary"]["net_pnl"] is None
    assert "MISSING_MINUTES_TREATED_AS_NO_TRADE_UNVERIFIED" in " ".join(result["warnings"])
    strict = _run(rows)  # complete_only excludes the truncated day entirely
    assert strict["status"] == "UNAVAILABLE" and strict["coverage"]["exclusions"]


def test_regime_pr3_blocks_every_entry_and_is_declared():
    result = _run(_breakout_day(), regime="PR3_HOT")
    assert result["trades"] == []
    assert set(result["funnel"]["reject_codes"]) == {"REGIME_PR3_HOT"}
    assert "PR3_HOT" in result["assumptions"]["regime"]


def test_suspected_corporate_action_in_warmup_excludes_the_day():
    daily = _daily()
    daily = [(t, d, o * 3, h * 3, l * 3, c * 3, v) if d >= "2026-08-05" else (t, d, o, h, l, c, v)
             for t, d, o, h, l, c, v in daily]
    result = _run(_breakout_day(), daily=daily)
    assert result["status"] == "UNAVAILABLE"
    assert result["coverage"]["exclusions"][0]["reason"] == "suspected_corporate_action_in_warmup"


def test_costs_drawdown_and_adverse_bound_are_reported_and_deterministic():
    rows = _breakout_day(overrides={"11:00": (97.0, 97.5, 96.5, 97.0, 1000.0)})
    first, second = _run(rows), _run(rows)
    assert first["run_fingerprint"] == second["run_fingerprint"]
    assert first["trades"] == second["trades"]
    summary = first["summary"]
    trade = first["trades"][0]
    assert trade["costs"] > 0 and trade["net_pnl"] == round(trade["gross_pnl"] - trade["costs"], 4)
    assert summary["max_drawdown"] == pytest.approx(-trade["net_pnl"])
    assert summary["adverse_fill_bound_net"] < summary["net_pnl"]
    assert first["assumptions"]["kill_switch"].startswith("replicated inert")
    assert first["can_place_orders"] is False and first["can_qualify"] is False


def test_reject_codes_are_bounded():
    assert reject_code("volume 1 < 2 (1.8x pace-adjusted median 1)") == "VOLUME_BELOW_PACE"
    assert reject_code("breakout not confirmed (close 1.00 <= 2.00)") == "BREAKOUT_NOT_CONFIRMED"
    assert reject_code("circuit_blocked: circuit: within") == "CIRCUIT_BLOCKED"
    assert reject_code("something new") == "OTHER"


class _FakeKite:
    """Serves the same evidence the replay sees to the real PennyScanner."""

    def __init__(self, td, daily_rows, boundary):
        self.instrument_cache = {"AAA": 1}
        self.td, self.daily_rows, self.boundary = td, daily_rows, boundary
        self.access_token = "test"

    def quote(self):
        ltp, _ = self.td.ltp_at(self.boundary)
        completed = self.td.completed_count(self.boundary)
        visible = self.td.bars[:completed]
        return {
            "last_price": ltp, "volume": int(sum(bar.volume for bar in visible)),
            "ohlc": {"high": max([b.high for b in visible] + [ltp]),
                     "low": min([b.low for b in visible] + [ltp])},
        }

    async def get_quote(self, tokens):
        return {1: self.quote()}

    async def get_intraday(self, ticker, from_datetime, to_datetime, interval):
        to = datetime.fromisoformat(to_datetime)
        frame = self.td.frame
        return frame[frame.index <= to].copy()

    async def get_historical(self, ticker, from_date, to_date):
        rows = [r for r in self.daily_rows if from_date <= r[1] < to_date]
        return pd.DataFrame(rows, columns=("ticker", "date", "open", "high", "low", "close", "volume"))


def test_replay_inputs_match_the_live_scanner_at_every_minute(tmp_path):
    from penny_scanner import PennyScanner

    rows = _breakout_day()
    daily_rows = _daily()
    intraday = validate_intraday_rows(rows, interval="minute", start=DAY, end=DAY, tickers=["AAA"])
    daily = validate_daily_rows(daily_rows, tickers=["AAA"], before=DAY)
    replay = _Replay(intraday, daily, PennyLifecycleConfig(tickers=("AAA",)),
                     date.fromisoformat(DAY), date.fromisoformat(DAY))
    td = _TickerDay(intraday.bars[("AAA", DAY)])
    scanner = PennyScanner(kite=None, universe_json_path=str(tmp_path / "u.json"),
                           paper_mode=True, regime="PR1_CALM")
    prev_close = daily.bars["AAA"][-1].close
    compared = accepted = 0
    for boundary in range(9 * 60 + 16, 14 * 60 + 40):
        scanner.kite = _FakeKite(td, daily_rows, boundary)
        as_of = datetime.fromisoformat(DAY).replace(hour=boundary // 60, minute=boundary % 60,
                                                    second=5, tzinfo=IST)
        live = asyncio.run(scanner._evaluate_ticker_breakout("AAA", as_of, prev_close=prev_close))
        mine = replay._evaluate("AAA", date.fromisoformat(DAY), td, boundary)
        assert live["accept"] == mine["accept"], boundary
        if live["accept"]:
            accepted += 1
            for key in ("entry", "stop_loss", "target", "shares", "rsi_14", "anchor", "buffer_pct"):
                assert live[key] == mine[key], (boundary, key)
        else:
            assert live["reject_reason"] == mine["reject_reason"], boundary
        compared += 1
    assert compared == 324 and accepted >= 1


def _seed_lab_db(path, rows, daily_rows):
    import sqlite3
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,"
                   "high REAL,low REAL,close REAL,volume REAL,fetched_at TEXT)")
        db.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,"
                   "close REAL,volume REAL,fetched_at TEXT)")
        db.executemany("INSERT INTO intraday_cache VALUES(?,?,?,?,?,?,?,?,'frozen')", rows)
        db.executemany("INSERT INTO ohlcv_cache VALUES(?,?,?,?,?,?,?,'frozen')", daily_rows)
    sqlite3.connect(path).close()


async def _terminal(db_path, run_id):
    import backtest_lab
    for _ in range(1000):
        run = await backtest_lab.get_run(db_path, run_id)
        if run and run["status"] in backtest_lab.TERMINAL_STATUSES:
            return run
        await asyncio.sleep(0.02)
    raise AssertionError("lifecycle run did not finish")


@pytest.mark.asyncio
async def test_lab_registers_lifecycle_scope_and_runs_end_to_end(db_path):
    import backtest_lab
    rows = _breakout_day() + _bars("AAA", "2026-08-11", end="14:29")
    _seed_lab_db(db_path, rows, _daily())
    by_id = {row["strategy_id"]: row for row in await backtest_lab.list_strategies(db_path)}
    lifecycle = by_id["penny_breakout_mis_lifecycle_1m"]
    assert lifecycle["scope"] == "LIFECYCLE" and lifecycle["available"] is True
    assert by_id["penny_breakout_intraday_1m_replay"]["scope"] == "EVALUATOR"
    adapter = backtest_lab.STRATEGY_REGISTRY["penny_breakout_mis_lifecycle_1m"]
    with pytest.raises(ValueError, match="explicit ticker list"):
        adapter.snapshot_config({})
    with pytest.raises(ValueError, match="book"):
        adapter.snapshot_config({"tickers": ["AAA"], "book": "EDGE"})
    with pytest.raises(ValueError, match="documented default"):
        adapter.snapshot_assumptions({"fills": "signal_close"})
    created = await backtest_lab.submit_run(
        db_path, "penny_breakout_mis_lifecycle_1m", "2026-08-10", "2026-08-11", {"tickers": ["aaa"]}, {},
    )
    run = await _terminal(db_path, created["run_id"])
    assert run["status"] == "SUCCEEDED", run.get("error")
    assert run["summary"]["scope"] == "LIFECYCLE" and run["summary"]["trade_count"] == 1
    assert run["summary"]["status"] == "PARTIAL"   # 2026-08-11 truncated -> excluded and reported
    assert run["dataset"]["intraday"]["dataset_sha256"].startswith("sha256:")
    assert run["result"]["coverage"]["exclusions"][0]["trading_date"] == "2026-08-11"


@pytest.mark.asyncio
async def test_lab_lifecycle_without_usable_sessions_is_archived_unavailable(db_path):
    import backtest_lab
    _seed_lab_db(db_path, _bars(end="14:29"), _daily())
    created = await backtest_lab.submit_run(
        db_path, "penny_breakout_mis_lifecycle_1m", "2026-08-10", "2026-08-10", {"tickers": ["AAA"]}, {},
    )
    run = await _terminal(db_path, created["run_id"])
    assert run["status"] == "UNAVAILABLE" and "complete_only" in run["error"]
    assert run["summary"] is None
