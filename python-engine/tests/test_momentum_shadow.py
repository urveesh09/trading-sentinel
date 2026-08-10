from dataclasses import FrozenInstanceError
import ast
from pathlib import Path

import aiosqlite
import pandas as pd
import pytest

from engine import evaluate_momentum_signal
from momentum_shadow import (
    VARIANTS,
    evaluate_momentum_shadows,
    momentum_shadow_comparison,
    persist_momentum_shadow_results,
)


def _recency_frames():
    # The only below->above VWAP transition is candle index 1. From the final
    # candle that is five bars back: lookback=3 cannot see it, lookback=5 can.
    close = [90.0, 110.0, 112.0, 114.0, 116.0, 118.0]
    intra = pd.DataFrame({
        "open": [89.0, 108.0, 111.0, 113.0, 115.0, 117.0],
        "high": [91.0, 111.0, 113.0, 115.0, 117.0, 119.0],
        "low": [89.0, 107.0, 110.0, 112.0, 114.0, 116.0],
        "close": close,
        "volume": [100.0, 100.0, 100.0, 100.0, 100.0, 1000.0],
    })
    daily = pd.DataFrame({
        "high": [150.0] * 20,
        "low": [50.0] * 20,
        "close": [100.0] * 20,
        "volume": [10000.0] * 20,
    })
    return intra, daily


def _evaluate(**variant):
    intra, daily = _recency_frames()
    return evaluate_momentum_signal(
        "TEST", intra, 100.0, 100000.0, 100000.0,
        df_daily=daily, vol_surge_threshold=1.5, **variant,
    )


def test_default_evaluator_matches_explicit_baseline_parameters():
    implicit = _evaluate()
    explicit = _evaluate(crossover_lookback=3, max_vwap_distance_atr=None)
    assert implicit == explicit
    assert implicit[1]["crossover_lookback"] == 3
    assert implicit[1]["max_vwap_distance_atr"] is None
    assert "vwap_distance" in implicit[1]
    assert "vwap_distance_atr" in implicit[1]


def test_recency_five_admits_the_older_cross_candidate():
    base_ok, base = _evaluate(crossover_lookback=3)
    candidate_ok, candidate = _evaluate(
        crossover_lookback=5, max_vwap_distance_atr=0.5,
    )
    assert base_ok is False
    assert base["reject_reason"] == "no_recent_vwap_crossover"
    assert candidate_ok is True, candidate
    assert candidate["crossover_lookback"] == 5
    assert candidate["vwap_distance_atr"] <= 0.5


def test_atr_distance_gate_rejects_chasing_with_evidence():
    accepted, decision = _evaluate(
        crossover_lookback=5, max_vwap_distance_atr=0.03,
    )
    assert accepted is False
    assert decision["reject_reason"] == "max_vwap_distance_atr_exceeded"
    assert decision["vwap_distance_atr"] > 0.03
    assert decision["max_vwap_distance_atr"] == 0.03


def test_invalid_variant_parameters_rejected():
    for invalid in (0, 21, 1.5, True):
        with pytest.raises(ValueError):
            _evaluate(crossover_lookback=invalid)
    for invalid in (0, -0.1, 11, float("nan"), float("inf"), "0.5", True):
        with pytest.raises(ValueError):
            _evaluate(max_vwap_distance_atr=invalid)
    intra, daily = _recency_frames()
    with pytest.raises(ValueError, match="unknown"):
        evaluate_momentum_shadows(
            "TEST", intra, 100, 100000, 100000,
            df_daily=daily, trading_date="2026-08-10", bar_ts="2026-08-10T11:00:00",
            variants=["NOT_REGISTERED"],
        )


def test_registry_is_immutable_and_shadow_evaluation_has_no_side_effect(tmp_path):
    assert set(VARIANTS) >= {"MOM_BASE", "MOM_RECENCY_5"}
    with pytest.raises(TypeError):
        VARIANTS["X"] = VARIANTS["MOM_BASE"]
    with pytest.raises(FrozenInstanceError):
        VARIANTS["MOM_BASE"].crossover_lookback = 9

    source = Path(__file__).parents[1] / "momentum_shadow.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(
        token in name.lower()
        for name in imports
        for token in ("kite", "executor", "order")
    )

    intra, daily = _recency_frames()
    untouched = tmp_path / "must_not_exist.db"
    rows = evaluate_momentum_shadows(
        "TEST", intra, 100, 100000, 100000,
        df_daily=daily, trading_date="2026-08-10", bar_ts="2026-08-10T11:00:00",
    )
    assert len(rows) == 2
    assert not untouched.exists()
    assert rows[0]["config"]["name"] == "MOM_BASE"
    assert rows[1]["config"]["name"] == "MOM_RECENCY_5"


def _record(variant, bar_ts, accepted, reason=None, ticker="AAA"):
    return {
        "trading_date": "2026-08-10",
        "ticker": ticker,
        "bar_ts": bar_ts,
        "variant": variant,
        "accepted": accepted,
        "reject_reason": reason,
        "features": {"close": 100.0},
        "config": {"name": variant},
    }


def _accepted_trade(ticker, bar_ts, bars, *, variant="MOM_BASE"):
    row = _record(variant, bar_ts, True, ticker=ticker)
    row.update({
        "decision": {
            "entry_price": 100.0, "stop_loss": 95.0,
            "target_1": 110.0, "shares": 10,
        },
        "dataset_fingerprint": f"sha256:{ticker.lower()}",
        "bars": bars,
    })
    return row


@pytest.mark.asyncio
async def test_persistence_is_idempotent_and_aggregate_is_candidate_aware(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    rows = [
        _record("MOM_BASE", "2026-08-10T10:00:00", True),
        _record("MOM_BASE", "2026-08-10T10:15:00", True),
        _record("MOM_BASE", "2026-08-10T10:30:00", False, "no_cross", "BBB"),
        _record("MOM_RECENCY_5", "2026-08-10T10:00:00", False, "too_far"),
        _record("MOM_RECENCY_5", "2026-08-10T10:15:00", False, "too_far", "BBB"),
        _record("MOM_RECENCY_5", "2026-08-10T10:30:00", False, "no_cross", "CCC"),
    ]
    assert await persist_momentum_shadow_results(db_path, rows) == 6
    assert await persist_momentum_shadow_results(db_path, rows) == 0

    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_evaluations"
        )).fetchone())[0]
        config_json = (await (await db.execute(
            "SELECT config_json FROM momentum_shadow_evaluations "
            "WHERE variant='MOM_BASE' LIMIT 1"
        )).fetchone())[0]
    assert count == 6
    assert config_json == '{"name":"MOM_BASE"}'

    comparison = await momentum_shadow_comparison(db_path)
    by_name = {row["variant"]: row for row in comparison["variants"]}
    base = by_name["MOM_BASE"]
    assert base["evaluations"] == 3
    assert base["accepts"] == 2
    # Two accepts for one ticker/day are one opportunity, not two candidates.
    assert base["distinct_candidates"] == 1
    assert base["accept_rate"] == pytest.approx(2 / 3, abs=1e-6)
    assert base["top_rejects"] == [{"reason": "no_cross", "count": 1}]
    assert by_name["MOM_RECENCY_5"]["top_rejects"][0] == {
        "reason": "too_far", "count": 2,
    }


@pytest.mark.asyncio
async def test_persistence_sanitizes_non_finite_features(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    row = _record("MOM_BASE", "2026-08-10T10:00:00", True)
    row["features"] = {"nan": float("nan"), "inf": float("inf")}
    assert await persist_momentum_shadow_results(db_path, [row]) == 1
    async with aiosqlite.connect(db_path) as db:
        payload = (await (await db.execute(
            "SELECT features_json FROM momentum_shadow_evaluations"
        )).fetchone())[0]
    assert payload == '{"inf":null,"nan":null}'


@pytest.mark.asyncio
async def test_invalid_identity_fields_cannot_pollute_dedupe_key(tmp_path):
    intra, daily = _recency_frames()
    for ticker, trading_date, bar_ts in (
        ("", "2026-08-10", "2026-08-10T10:00:00"),
        ("TEST", "2026-02-30", "2026-08-10T10:00:00"),
        ("TEST", "2026-08-10", "not-a-timestamp"),
    ):
        with pytest.raises(ValueError):
            evaluate_momentum_shadows(
                ticker, intra, 100, 100000, 100000, df_daily=daily,
                trading_date=trading_date, bar_ts=bar_ts,
            )

    db_path = str(tmp_path / "shadow.db")
    malformed = _record("MOM_BASE", "not-a-timestamp", True, ticker="")
    with pytest.raises(ValueError):
        await persist_momentum_shadow_results(db_path, [malformed])
    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_evaluations"
        )).fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_persistence_rejects_unregistered_variant(tmp_path):
    with pytest.raises(ValueError, match="unregistered"):
        await persist_momentum_shadow_results(
            str(tmp_path / "bad.db"),
            [_record("UNKNOWN", "2026-08-10T10:00:00", False, "bad")],
        )


@pytest.mark.asyncio
async def test_virtual_trade_is_restart_safe_and_stop_wins_ambiguous_bar(tmp_path):
    db_path = str(tmp_path / "outcomes.db")
    entry = _accepted_trade("AAA", "2026-08-10T10:00:00", [{
        "bar_ts": "2026-08-10T10:00:00", "open": 99, "high": 101,
        "low": 98, "close": 100,
    }])
    later = _accepted_trade("AAA", "2026-08-10T10:15:00", [
        *entry["bars"],
        {"bar_ts": "2026-08-10T10:15:00", "open": 100, "high": 112,
         "low": 94, "close": 108},
    ])
    assert await persist_momentum_shadow_results(db_path, [entry]) == 1
    assert await persist_momentum_shadow_results(db_path, [entry, later]) == 1
    assert await persist_momentum_shadow_results(db_path, [entry, later]) == 0

    async with aiosqlite.connect(db_path) as db:
        assert (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_trades"
        )).fetchone())[0] == 1
        close = await (await db.execute(
            "SELECT reason,exit_fill,gross_pnl,costs,net_pnl "
            "FROM momentum_shadow_trade_events WHERE event_type='CLOSED'"
        )).fetchone()
        assert close[0] == "stop"
        assert close[1] < 95.0
        assert close[3] > 0
        assert close[4] < close[2]
        snapshot = await (await db.execute(
            "SELECT config_json,execution_json,dataset_fingerprint "
            "FROM momentum_shadow_trades"
        )).fetchone()
        assert snapshot[0] == '{"name":"MOM_BASE"}'
        assert '"same_bar_priority":"stop_before_target"' in snapshot[1]
        assert snapshot[2] == "sha256:aaa"
        with pytest.raises(aiosqlite.IntegrityError, match="immutable"):
            await db.execute("UPDATE momentum_shadow_trades SET quantity=99")

    comparison = await momentum_shadow_comparison(db_path)
    base = next(row for row in comparison["variants"] if row["variant"] == "MOM_BASE")
    assert (base["paper_entries"], base["open_trades"], base["closed_trades"]) == (1, 0, 1)
    assert base["gross_pnl"] < 0
    assert base["costs"] > 0
    assert base["net_expectancy"] == base["net_pnl"]
    assert base["profit_factor"] == 0.0
    assert base["max_drawdown"] == pytest.approx(-base["net_pnl"])


@pytest.mark.asyncio
async def test_gap_fill_time_exit_and_no_closed_metrics_are_honest(tmp_path):
    db_path = str(tmp_path / "outcomes.db")
    open_trade = _accepted_trade("OPEN", "2026-08-10T10:00:00", [])
    gap_entry = _accepted_trade("GAP", "2026-08-10T10:00:00", [])
    time_entry = _accepted_trade("TIME", "2026-08-10T10:00:00", [])
    await persist_momentum_shadow_results(db_path, [open_trade, gap_entry, time_entry])

    gap_later = _accepted_trade("GAP", "2026-08-10T10:15:00", [{
        "bar_ts": "2026-08-10T10:15:00", "open": 90, "high": 92,
        "low": 89, "close": 91,
    }])
    time_later = _accepted_trade("TIME", "2026-08-10T15:15:00", [{
        # Both thresholds occur later in this candle, but the timestamp is
        # its start: the declared time exit must use its open without hindsight.
        "bar_ts": "2026-08-10T15:15:00", "open": 103, "high": 112,
        "low": 94, "close": 109,
    }])
    await persist_momentum_shadow_results(db_path, [gap_later, time_later])
    async with aiosqlite.connect(db_path) as db:
        events = await (await db.execute(
            "SELECT ticker,reason,exit_fill FROM momentum_shadow_trade_events "
            "WHERE event_type='CLOSED' ORDER BY ticker"
        )).fetchall()
    assert events[0][0:2] == ("GAP", "stop_gap")
    assert events[0][2] < 90.0
    assert events[1][0:2] == ("TIME", "time_exit")
    assert events[1][2] == pytest.approx(103 * (1 - 5 / 10000))
    comparison = await momentum_shadow_comparison(db_path)
    realised = next(row for row in comparison["variants"] if row["variant"] == "MOM_BASE")
    assert realised["closed_trades"] == 2
    assert realised["wins"] == realised["losses"] == 1
    assert realised["profit_factor"] is not None
    assert realised["max_drawdown"] > 0
    assert realised["net_expectancy"] == pytest.approx(realised["net_pnl"] / 2, abs=1e-6)

    empty_db = str(tmp_path / "empty.db")
    empty = await momentum_shadow_comparison(empty_db)
    base = next(row for row in empty["variants"] if row["variant"] == "MOM_BASE")
    assert base["paper_entries"] == base["closed_trades"] == 0
    for field in ("gross_pnl", "costs", "net_pnl", "net_expectancy",
                  "profit_factor", "win_rate", "avg_r", "max_drawdown"):
        assert base[field] is None


@pytest.mark.asyncio
async def test_restart_closes_prior_day_trade_at_first_observed_open(tmp_path):
    db_path = str(tmp_path / "overnight.db")
    await persist_momentum_shadow_results(db_path, [
        _accepted_trade("AAA", "2026-08-10T14:45:00", []),
    ])
    next_day = _record(
        "MOM_BASE", "2026-08-11T09:15:00", False,
        "candidate_reject", ticker="AAA",
    )
    next_day["trading_date"] = "2026-08-11"
    next_day["bars"] = [{
        "bar_ts": "2026-08-11T09:15:00", "open": 92, "high": 120,
        "low": 90, "close": 115,
    }]
    await persist_momentum_shadow_results(db_path, [next_day])
    await persist_momentum_shadow_results(db_path, [next_day])
    async with aiosqlite.connect(db_path) as db:
        event = await (await db.execute(
            "SELECT trading_date,reason,exit_fill FROM momentum_shadow_trade_events "
            "WHERE event_type='CLOSED'"
        )).fetchone()
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_trade_events WHERE event_type='CLOSED'"
        )).fetchone())[0]
    assert event[0:2] == ("2026-08-10", "overnight_gap_exit")
    assert event[2] < 92
    assert count == 1


@pytest.mark.asyncio
async def test_slippage_cannot_create_entry_at_or_above_target(tmp_path):
    db_path = str(tmp_path / "tight.db")
    row = _accepted_trade("TIGHT", "2026-08-10T10:00:00", [])
    row["decision"]["target_1"] = 100.01
    await persist_momentum_shadow_results(db_path, [row])
    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM momentum_shadow_trades"
        )).fetchone())[0]
    assert count == 0
