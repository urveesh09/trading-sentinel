"""Causal strength, timing, durable paper cash and winner-management contracts."""

from dataclasses import replace
from datetime import datetime, timedelta
import json
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from adaptive_penny_policy import CompletedBar, EntryPlan, open_thesis_position
from penny_smart_policy import strength_evidence, smart_setup, manage_smart, SMART_PARAMS
from penny_smart_book import new_book, step_book
from penny_smart_shadow import IST, quote_evidence, observe_smart_shadow

START = datetime(2026, 10, 5, 9, 15, tzinfo=IST)


def bars(opening=9.8):
    result = []
    for i in range(76):
        at = START + timedelta(minutes=i)
        if i == 0:
            values = (opening, 9.99, min(opening, 9.94), 9.98, 1000.0)
        elif i == 75:
            values = (9.99, 10.02, 9.99, 10.01, 4000.0)
        else:
            values = (9.98, 10.0, 9.94, 9.98, 1000.0)
        result.append(CompletedBar(str(i), at, at + timedelta(minutes=1), *values))
    return result


def quote(entry=10.01, exit_=10.01):
    return {"entry": entry, "exit": exit_, "executable": True}


def observe(state=None, *, items=None, quotes=None, now=None, **kwargs):
    data = bars()
    items = items or {"AAA": {"bars": data, "median_volume": 100000}}
    if state is None:
        state, _ = step_book(
            new_book("2026-10-05", 2000.0, {}),
            items,
            quotes or {"AAA": quote()},
            now=data[-1].available_at,
            cost=lambda e, x, q: 0.05,
            **kwargs
        )
    items = {t: {**obs, "bars": obs["bars"] + [retest(obs["bars"])]} for t, obs in items.items()}
    return step_book(
        state,
        items,
        quotes or {"AAA": quote()},
        now=now or retest(data).available_at,
        cost=lambda e, x, q: 0.05,
        **kwargs
    )


def retest(data):
    return CompletedBar(
        "retest",
        data[-1].available_at,
        data[-1].available_at + timedelta(minutes=1),
        10.01,
        10.03,
        10.0,
        10.02,
        1500.0,
    )


def test_rising_stock_in_falling_market_is_positive_not_blanket_veto():
    data = bars()
    benchmark = [
        replace(b, open=11.0, high=11.01, low=9.0, close=10.0 - i * 0.005)
        for i, b in enumerate(data)
    ]
    evidence = strength_evidence(data, decision_at=data[-1].available_at, benchmark_bars=benchmark)
    assert evidence["positive_momentum"] and evidence["excess_return"] > 0
    assert evidence["benchmark_status"] == "OBSERVED"
    falling = [
        replace(b, open=12.0, high=12.01, low=9.0, close=10.0 - i * 0.001)
        for i, b in enumerate(data)
    ]
    assert not strength_evidence(
        falling, decision_at=data[-1].available_at, benchmark_bars=benchmark
    )["positive_momentum"]


def test_missing_benchmark_is_explicit_not_fabricated():
    data = bars()
    e = strength_evidence(data, decision_at=data[-1].available_at)
    assert e["benchmark_status"] == "UNAVAILABLE" and e["excess_return"] is None


def test_future_unsorted_duplicate_and_missing_opening_are_not_signals():
    data = bars()
    for changed in (
        data
        + [
            replace(
                data[-1],
                observation_id="future",
                observed_at=data[-1].available_at,
                available_at=data[-1].available_at + timedelta(minutes=1),
            )
        ],
        data[::-1],
        data + [data[-1]],
    ):
        with pytest.raises(ValueError):
            strength_evidence(changed, decision_at=data[-1].available_at)
    assert not strength_evidence(data[1:], decision_at=data[-1].available_at)["available"]


def test_arm_retest_and_expensive_quote_expiry_are_stateful():
    data = bars()
    params = replace(SMART_PARAMS, fast_entry_score=1.1)
    outcome = smart_setup(
        "AAA", data, median_volume=100000, decision_at=data[-1].available_at, params=params
    )
    assert outcome.action == "ARMED"
    bar = CompletedBar(
        "retest",
        data[-1].available_at,
        data[-1].available_at + timedelta(minutes=1),
        10.01,
        10.03,
        10.0,
        10.02,
        1500.0,
    )
    intent = smart_setup(
        "AAA",
        data + [bar],
        median_volume=100000,
        decision_at=bar.available_at,
        setup=outcome.setup,
        params=params,
    )
    assert intent.intent and intent.intent.entry_kind == "RETEST_RECLAIM"
    state, events = observe(quotes={"AAA": quote(10.5, 10.49)})
    assert not state["positions"] and any(e["kind"] == "ENTRY_EXPIRED" for e in events)


def test_ranked_intents_allocate_before_alphabetical_order():
    strong = bars(opening=9.5)
    weak = bars(opening=9.99)
    state, events = observe(
        items={
            "AAA": {"bars": weak, "median_volume": 100000},
            "ZZZ": {"bars": strong, "median_volume": 100000},
        },
        quotes={"AAA": quote(), "ZZZ": quote()},
        max_positions=1,
    )
    assert list(state["positions"]) == ["ZZZ"]


def test_fee_inclusive_cash_single_total_risk_and_depth_caps():
    state, events = observe(quotes={"AAA": {**quote(), "max_quantity": 10}}, stock_cap=100.0)
    assert state["positions"]
    row = state["positions"]["AAA"]
    p = row["thesis"]
    assert p["shares_initial"] <= 10
    assert p["shares_initial"] * p["entry_price"] + row["cost_reserve"] <= 100.0
    assert p["shares_initial"] * (p["entry_price"] - p["initial_stop"]) + row["cost_reserve"] <= 5.0
    crowded = {t: {"bars": bars(), "median_volume": 100000} for t in ("A", "B", "C", "D")}
    state, _ = observe(items=crowded, quotes={t: quote() for t in crowded}, total_risk_pct=0.0025)
    assert (
        sum(
            (p["thesis"]["entry_price"] - p["thesis"]["stop"]) * p["thesis"]["shares_open"]
            + p["cost_reserve"]
            for p in state["positions"].values()
        )
        <= 5.0
    )


def test_restart_duplicate_and_out_of_order_do_not_reenter():
    state, _ = observe()
    assert state["positions"]
    copy = json.loads(json.dumps(state))
    a, events = observe(state)
    b, _ = observe(copy)
    assert a == b and not any(e["kind"] == "ENTRY_FILLED" for e in events)
    with pytest.raises(ValueError):
        observe(state, now=START)


def test_entry_halt_keeps_stop_and_deadline_exit_authority():
    state, _ = observe()
    assert state["positions"]
    stop = state["positions"]["AAA"]["thesis"]["stop"]
    closed, events = observe(
        state,
        quotes={"AAA": quote(stop - 0.02, stop - 0.03)},
        allow_entries=False,
        now=bars()[-1].available_at + timedelta(minutes=1),
    )
    assert not closed["positions"] and len(closed["trades"]) == 1
    assert any(e["kind"] == "EXIT_FILLED" for e in events)
    pending, _ = observe(
        state,
        quotes={"AAA": {"executable": False}},
        allow_entries=False,
        now=START.replace(hour=15, minute=0),
    )
    assert pending["positions"]["AAA"]["exit_pending"] == "SMART_SESSION_DEADLINE"


def test_configuration_and_daily_loss_halts_do_not_allocate():
    state = new_book("2026-10-05", 2000.0, {})
    state["realized"] = -21.0
    state, events = observe(state)
    assert not state["positions"] and any(e["kind"] == "ENTRY_HALTED" for e in events)


def test_wicks_do_not_trigger_breakeven_and_confirmed_trail_never_widens():
    plan = EntryPlan("T", 10.0, 9.8, 10, 0.2, 2.0, 100.0, 0.05)
    at = START.replace(hour=11, minute=0)
    position = open_thesis_position(plan, ticker="AAA", anchor=9.9, atr=0.05, entry_at=at)
    wick = CompletedBar("wick", at, at + timedelta(minutes=1), 10.0, 10.5, 9.99, 10.01, 100.0)
    outcome = manage_smart(position, wick, decision_at=wick.available_at)
    assert outcome.new_stop is None and outcome.position.stop == 9.8
    rally = replace(
        wick,
        observation_id="rally",
        observed_at=wick.available_at,
        available_at=wick.available_at + timedelta(minutes=1),
        open=10.35,
        close=10.4,
        low=10.3,
    )
    raised = manage_smart(outcome.position, rally, decision_at=rally.available_at)
    assert raised.new_stop and raised.new_stop > 9.8 and not raised.position.breakeven_locked
    fade = replace(
        rally,
        observation_id="fade",
        observed_at=rally.available_at,
        available_at=rally.available_at + timedelta(minutes=1),
        close=10.32,
    )
    assert (
        manage_smart(raised.position, fade, decision_at=fade.available_at).position.stop
        >= raised.new_stop
    )


def raw_quote(now, entry=10.01, exit_=10.0):
    return {
        "timestamp": now.isoformat(),
        "depth": {
            "buy": [{"price": exit_, "quantity": 100}],
            "sell": [{"price": entry, "quantity": 100}],
        },
    }


def test_stale_one_sided_crossed_and_future_quotes_are_unavailable():
    now = bars()[-1].available_at
    for raw in (
        {},
        raw_quote(now - timedelta(seconds=61)),
        raw_quote(now + timedelta(seconds=1)),
        raw_quote(now, 9.0, 10.0),
    ):
        assert not quote_evidence(raw, now)["executable"]
    assert quote_evidence(raw_quote(now), now)["executable"]


@pytest.mark.asyncio
async def test_atomic_store_restart_and_configuration_drift_preserve_positions(tmp_path):
    import aiosqlite

    path = str(tmp_path / "paper.sqlite")
    data = bars()
    now = data[-1].available_at
    frame = pd.DataFrame(
        [
            {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
            for b in data
        ],
        index=pd.DatetimeIndex([b.observed_at for b in data]),
    )
    obs = {"AAA": {"frame": frame, "median_volume": 100000}}
    first = await observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now)
    assert first["open"] == 0
    completed = retest(data)
    now = completed.available_at
    frame.loc[completed.observed_at] = [
        completed.open,
        completed.high,
        completed.low,
        completed.close,
        completed.volume,
    ]
    first = await observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now)
    assert first["open"] == 1 and not first["can_place_orders"]
    second = await observe_smart_shadow(
        path, obs, {"AAA": raw_quote(now)}, now=now, bankroll=3000.0
    )
    assert second["open"] == 1 and second["configuration_drift"]
    async with aiosqlite.connect(path) as db:
        count = (
            await (
                await db.execute(
                    "SELECT COUNT(*) FROM penny_smart_paper_events WHERE kind='ENTRY_FILLED'"
                )
            ).fetchone()
        )[0]
    assert count == 1


def test_replay_variants_use_current_functions_and_report_zero_trade_days():
    from tests.test_penny_lifecycle_replay import _run, _breakout_day

    for policy in ("PEN_STRENGTH_RANK", "PEN_SMART_EXIT", "PEN_SMART_ENTRY", "PEN_SMART_TRADER"):
        result = _run(_breakout_day(), candidate_policy=policy, bankroll=2000.0)
        assert result["daily_returns"] and not result["can_place_orders"]
        assert result["daily_returns"][0]["allocated_return_pct"] is not None


@pytest.mark.parametrize("fees", [float("nan"), float("inf"), -1.0])
def test_invalid_costs_never_create_paper_capital(fees):
    with pytest.raises(ValueError, match="modeled cost"):
        data = bars()
        state, _ = observe()
        step_book(
            state, {}, {"AAA": quote()}, now=retest(data).available_at, cost=lambda e, x, q: fees
        )


def test_daily_loss_latch_does_not_reopen_after_quote_recovery():
    state = new_book("2026-10-05", 2000.0, {})
    state["realized"] = -21.0
    state, _ = observe(state)
    assert state["daily_loss_latched"]
    state["realized"] = 0.0
    state, _ = observe(state)
    assert not state["positions"] and state["daily_loss_latched"]


def test_entry_marks_include_spread_and_fees_immediately():
    state, _ = observe(quotes={"AAA": quote(10.01, 10.0)})
    qty = state["positions"]["AAA"]["thesis"]["shares_open"]
    assert state["marked_pnl"] == pytest.approx(-0.01 * qty - 0.05)
    assert state["max_marked_drawdown"] >= -state["marked_pnl"]


def test_overnight_missing_exit_cannot_erase_exposure_or_refill_cash():
    state, _ = observe()
    pending, events = step_book(
        state, {}, {}, now=START + timedelta(days=1), cost=lambda e, x, q: 0.05
    )
    assert pending["day"] == "2026-10-05" and pending["positions"]
    assert pending["positions"]["AAA"]["exit_pending"] == "SMART_SESSION_DEADLINE"
    assert not any(e["kind"] == "ENTRY_FILLED" for e in events)


@pytest.mark.asyncio
async def test_concurrent_observers_admit_once_and_invalid_frame_cannot_block_exit(tmp_path):
    import asyncio
    import aiosqlite

    data = bars()
    path = str(tmp_path / "concurrent.sqlite")
    frame = pd.DataFrame(
        [
            {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
            for b in data
        ],
        index=pd.DatetimeIndex([b.observed_at for b in data]),
    )
    obs = {"AAA": {"frame": frame, "median_volume": 100000}}
    now = data[-1].available_at
    await observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now)
    bar = retest(data)
    now = bar.available_at
    frame.loc[bar.observed_at] = [bar.open, bar.high, bar.low, bar.close, bar.volume]
    result = await asyncio.gather(
        *(observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now) for _ in range(2))
    )
    assert all(r["open"] == 1 for r in result)
    async with aiosqlite.connect(path) as db:
        count = (
            await (
                await db.execute(
                    "SELECT COUNT(*) FROM penny_smart_paper_events WHERE kind='ENTRY_FILLED'"
                )
            ).fetchone()
        )[0]
    assert count == 1
    bad = {"AAA": {"frame": frame.iloc[::-1], "median_volume": 100000}}
    closed = await observe_smart_shadow(
        path, bad, {"AAA": raw_quote(now, 9.0, 8.99)}, now=now, allow_entries=False
    )
    assert closed["open"] == 0 and closed["invalid_observations"] == ["AAA"]


@pytest.mark.asyncio
async def test_new_session_carries_equity_without_daily_topup(tmp_path):
    import aiosqlite

    path = str(tmp_path / "carry.sqlite")
    now = bars()[-1].available_at
    await observe_smart_shadow(path, {}, {}, now=now)
    async with aiosqlite.connect(path) as db:
        state = json.loads(
            (await (await db.execute("SELECT state_json FROM penny_smart_paper_state")).fetchone())[
                0
            ]
        )
        state["realized"] = -15.0
        await db.execute("UPDATE penny_smart_paper_state SET state_json=?", (json.dumps(state),))
        await db.commit()
    await observe_smart_shadow(path, {}, {}, now=now + timedelta(days=1))
    async with aiosqlite.connect(path) as db:
        state = json.loads(
            (await (await db.execute("SELECT state_json FROM penny_smart_paper_state")).fetchone())[
                0
            ]
        )
    assert state["bankroll"] == 1985.0 and state["realized"] == 0.0
    assert state["binding"]["bankroll"] == 2000.0


@pytest.mark.asyncio
async def test_monitor_has_one_bounded_quote_batch_and_no_order_authority(tmp_path, monkeypatch):
    import aiosqlite
    from types import SimpleNamespace
    import penny_smart_shadow as shadow

    path = str(tmp_path / "monitor.sqlite")
    state, _ = observe()
    now = retest(bars()).available_at
    await observe_smart_shadow(path, {}, {}, now=now)
    async with aiosqlite.connect(path) as db:
        original = json.loads(
            (await (await db.execute("SELECT state_json FROM penny_smart_paper_state")).fetchone())[
                0
            ]
        )
        state["binding"] = original["binding"]
        state["execution"] = original["execution"]
        await db.execute("UPDATE penny_smart_paper_state SET state_json=?", (json.dumps(state),))
        await db.commit()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(shadow, "datetime", Clock)
    kite = SimpleNamespace(
        instrument_cache={"AAA": 1},
        get_quote=AsyncMock(return_value={1: raw_quote(now, 9.0, 8.99)}),
        place_order=AsyncMock(side_effect=AssertionError("real order forbidden")),
    )
    result = await shadow.monitor_smart_shadow(path, kite, now=now)
    assert result["open"] == 0 and not result["can_place_orders"]
    kite.get_quote.assert_awaited_once_with([1])
    kite.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_stop_job_observes_shadow_even_without_incumbent_paper_book(monkeypatch):
    from types import SimpleNamespace
    import main
    import penny_smart_shadow
    from config import settings

    monitor = AsyncMock()
    monkeypatch.setattr(settings, "PENNY_SMART_SHADOW_ENABLED", True)
    monkeypatch.setattr(
        main,
        "_get_penny_scanner",
        lambda: SimpleNamespace(kite=object(), executor=SimpleNamespace(paper_mode=False)),
    )
    monkeypatch.setattr(penny_smart_shadow, "monitor_smart_shadow", monitor)
    result = await main.run_penny_paper_stop_monitor()
    assert result["checked"] == 0
    monitor.assert_awaited_once()


@pytest.mark.asyncio
async def test_quote_samples_manage_failed_thesis_while_all_entry_scans_are_halted(tmp_path):
    import aiosqlite

    path = str(tmp_path / "sampled.sqlite")
    data = bars()
    now = data[-1].available_at
    frame = pd.DataFrame(
        [
            {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
            for b in data
        ],
        index=pd.DatetimeIndex([b.observed_at for b in data]),
    )
    obs = {"AAA": {"frame": frame, "median_volume": 100000}}
    await observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now)
    bar = retest(data)
    now = bar.available_at
    frame.loc[bar.observed_at] = [bar.open, bar.high, bar.low, bar.close, bar.volume]
    admitted = await observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now)
    assert admitted["open"] == 1
    for minutes in (1, 2, 3):
        at = now + timedelta(minutes=minutes)
        result = await observe_smart_shadow(
            path, {}, {"AAA": raw_quote(at, 9.99, 9.98)}, now=at, allow_entries=False
        )
    assert result["open"] == 0
    async with aiosqlite.connect(path) as db:
        state = json.loads(
            (await (await db.execute("SELECT state_json FROM penny_smart_paper_state")).fetchone())[
                0
            ]
        )
    assert state["trades"][0]["exit_reason"] == "SMART_THESIS_FAILED"
    assert state["trades"][0]["exit_observation_source"] == "SAMPLED_BID_CLOSE"


def test_sampled_quote_minutes_are_not_future_candles_or_gap_fills():
    from penny_smart_shadow import _exit_observations

    state, _ = observe()
    at = retest(bars()).available_at + timedelta(seconds=20)
    state["quote_samples"] = {"AAA": {"at": at.isoformat(), "price": 10.0}}
    assert _exit_observations(state, {}, at) == {}
    assert _exit_observations(state, {}, at + timedelta(minutes=3)) == {}
    obs = _exit_observations(state, {}, at + timedelta(minutes=1))
    assert obs["AAA"]["exit_observation_source"] == "SAMPLED_BID_CLOSE"
    assert not obs["AAA"]["entry_allowed"] and obs["AAA"]["bars"][0].volume == 0.0


@pytest.mark.parametrize("price", [float("inf"), float("nan")])
def test_nonfinite_depth_does_not_become_fill_evidence(price):
    now = bars()[-1].available_at
    assert not quote_evidence(raw_quote(now, price, 10.0), now)["executable"]


def test_smart_replay_fills_after_reclaim_and_future_wick_cannot_change_entry():
    from tests.test_penny_lifecycle_replay import _run, _daily
    from research_data_contracts import default_calendar
    from datetime import date

    data = bars() + [retest(bars())]
    for i in range(len(data), 375):
        at = START + timedelta(minutes=i)
        data.append(
            CompletedBar(str(i), at, at + timedelta(minutes=1), 10.02, 10.03, 10.01, 10.02, 1000.0)
        )

    def replay(changed):
        rows = [
            (
                "AAA",
                "minute",
                b.observed_at.strftime("%Y-%m-%d %H:%M:%S"),
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
            )
            for b in changed
        ]
        return _run(
            rows,
            start="2026-10-05",
            end="2026-10-05",
            daily=[
                row
                for row in _daily(day="2026-10-05", close=9.98)
                if default_calendar().is_trading_day(date.fromisoformat(row[1]))
            ],
            candidate_policy="PEN_SMART_TRADER",
            bankroll=2000.0,
        )

    first = replay(data)
    assert first["summary"]["closed_trades"] == 1
    trade = first["trades"][0]
    assert trade["entry_fill_ts"] == "2026-10-05T10:32:00+05:30"
    assert trade["entry_fill_price"] == 10.02
    changed = list(data)
    changed[77] = replace(changed[77], high=20.0)
    altered = replay(changed)["trades"][0]
    keys = ("entry_fill_ts", "entry_fill_price", "shares", "initial_stop_price", "evidence")
    assert {k: trade[k] for k in keys} == {k: altered[k] for k in keys}
