from __future__ import annotations

import asyncio
import sqlite3
import json
from datetime import date, datetime, timedelta

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backtest_lab
from backtest_lab import get_run, list_strategies, submit_run
from config import settings
from routes_backtest import router


def _seed_daily(db_path: str, ticker: str = "RELIANCE", count: int = 230,
                breakout: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE ohlcv_cache (
            ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,
            volume REAL,PRIMARY KEY(ticker,date)
        )
    """)
    start = date(2025, 1, 1)
    rows = []
    for i in range(count):
        day = start + timedelta(days=i)
        close = 100.0 + i * 0.1
        high, volume = close + 1, 100_000 + (i % 20) * 1000
        if breakout and i == 205:
            close, high, volume = close + 5, close + 6, 1_000_000
        if breakout and i == 206:
            close, high = close + 8, close + 9
        rows.append((ticker, day.isoformat(), close - 0.2, high,
                     close - 1, close, volume))
    conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()


async def _wait_terminal(db_path: str, run_id: str):
    for _ in range(150):
        run = await get_run(db_path, run_id)
        if run and run["status"] in backtest_lab.TERMINAL_STATUSES:
            return run
        await asyncio.sleep(0.02)
    raise AssertionError("backtest did not finish")


@pytest.mark.asyncio
async def test_registry_exposes_executable_and_honestly_unavailable_adapters(db_path):
    _seed_daily(db_path)
    by_id = {row["strategy_id"]: row for row in await list_strategies(db_path)}
    assert by_id["swing_regime_daily"]["available"] is True
    assert by_id["penny_breakout_daily_proxy"]["available"] is True
    assert by_id["fno_momentum_5m"]["available"] is False
    assert "provenance" in by_id["fno_momentum_5m"]["availability_reason"]
    assert all(row["research_only"] and not row["can_place_orders"] for row in by_id.values())


@pytest.mark.asyncio
async def test_swing_run_persists_frozen_evidence_and_terminal_rows_are_immutable(db_path):
    _seed_daily(db_path)
    created = await submit_run(
        db_path, "swing_regime_daily", "2025-07-20", "2025-08-18",
        {"ticker": "RELIANCE", "initial_bankroll": 12345.0}, {},
    )
    run = await _wait_terminal(db_path, created["run_id"])
    assert run["status"] == "SUCCEEDED"
    assert run["config"] == {"ticker": "RELIANCE", "initial_bankroll": 12345.0}
    assert run["dataset_fingerprint"].startswith("sha256:")
    assert run["dataset"]["source"] == "ohlcv_cache"
    assert run["summary"]["oos"]["available"] is False
    assert run["result"] is not None
    async with aiosqlite.connect(db_path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            await db.execute("UPDATE backtest_runs SET error='changed' WHERE run_id=?", (created["run_id"],))


@pytest.mark.asyncio
async def test_swing_summary_net_pnl_is_derived_from_complete_trade_results(db_path, monkeypatch):
    _seed_daily(db_path)
    adapter = backtest_lab.STRATEGY_REGISTRY["swing_regime_daily"]
    request = backtest_lab.BacktestRequest(
        "swing_regime_daily", "2025-01-01", "2025-08-01",
        {"ticker": "RELIANCE", "initial_bankroll": 1000.0}, adapter.metadata.default_assumptions,
    )
    summary, _ = adapter.normalize({
        "trades": [{"pnl": 125.0}, {"pnl": -25.0}],
        "stats": {"total_trades": 2, "win_rate": 50, "profit_factor": 5,
                  "max_drawdown_pct": 2.5, "avg_R": 0.4},
    }, request)
    assert summary["net_pnl"] == 100.0
    assert summary["net_return_pct"] == 10.0


@pytest.mark.asyncio
async def test_penny_snapshot_fingerprint_includes_pre_window_warmup(db_path):
    _seed_daily(db_path, ticker="CHEAP", count=60)
    adapter = backtest_lab.STRATEGY_REGISTRY["penny_breakout_daily_proxy"]
    request = backtest_lab.BacktestRequest(
        "penny_breakout_daily_proxy", "2025-02-10", "2025-02-20",
        {"preset": "baseline", "initial_bankroll": 100000.0}, adapter.metadata.default_assumptions,
    )
    prepared = adapter.prepare(db_path, request)
    assert prepared.details["first_bar"] == "2025-01-01"
    assert prepared.row_count > 11


@pytest.mark.asyncio
async def test_unavailable_strategy_creates_auditable_unavailable_run(db_path):
    created = await submit_run(db_path, "fno_momentum_5m", "2026-01-01", "2026-02-01")
    assert backtest_lab._BACKGROUND_TASKS
    run = await _wait_terminal(db_path, created["run_id"])
    assert run["status"] == "UNAVAILABLE"
    assert run["summary"] is None and run["result"] is None
    assert "provenance" in run["error"]
    await asyncio.sleep(0)
    assert not backtest_lab._BACKGROUND_TASKS


@pytest.mark.asyncio
async def test_init_closes_orphaned_background_runs_after_restart(db_path):
    # Seed the schema, then insert a synthetic prior-process run. Temporarily
    # disable triggers only through a normal non-terminal insert.
    await backtest_lab.init_backtest_lab_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO backtest_experiments VALUES (?,?,?,?,?,?,?,?)",
        ("old-exp", 1, "swing_regime_daily", "1", "{}", "{}", "{}", "2000-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO backtest_runs(run_id,experiment_id,status,created_at,warnings_json) VALUES (?,?,?,?,?)",
        ("old-run", "old-exp", "RUNNING", "2000-01-01T00:00:00+00:00", "[]"),
    )
    conn.commit(); conn.close()
    await backtest_lab.init_backtest_lab_db(db_path)
    run = await get_run(db_path, "old-run")
    assert run["status"] == "FAILED"
    assert "restarted" in run["error"]
    assert run["completed_at"] is not None


@pytest.mark.asyncio
async def test_custom_execution_assumptions_are_rejected_instead_of_mislabelled(db_path):
    _seed_daily(db_path)
    with pytest.raises(ValueError, match="misleading"):
        await submit_run(
            db_path, "swing_regime_daily", "2025-01-01", "2025-08-01",
            {}, {"fees_bps": 10.0},
        )


@pytest.mark.asyncio
async def test_non_finite_result_values_persist_and_retrieve_as_strict_json_null(db_path):
    await backtest_lab.init_backtest_lab_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO backtest_experiments VALUES (?,?,?,?,?,?,?,?)",
            ("finite-exp", 1, "swing_regime_daily", "1", "{}", "{}", "{}",
             "2026-01-01T00:00:00+00:00"),
        )
        summary_json = backtest_lab._json({"net_pnl": float("nan"), "risk": float("inf")})
        result_json = backtest_lab._json({"curve": [1.0, float("-inf"), float("nan")]})
        assert "NaN" not in summary_json + result_json
        assert "Infinity" not in summary_json + result_json
        await db.execute(
            "INSERT INTO backtest_runs(run_id,experiment_id,status,created_at,completed_at,"
            "summary_json,warnings_json,result_json) VALUES (?,?,?,?,?,?,?,?)",
            ("finite-run", "finite-exp", "SUCCEEDED", "2026-01-01T00:00:00+00:00",
             "2026-01-01T00:01:00+00:00", summary_json, "[]", result_json),
        )
        await db.commit()

    run = await get_run(db_path, "finite-run")
    assert run["summary"] == {"net_pnl": None, "risk": None}
    assert run["result"] == {"curve": [1.0, None, None]}


def test_http_routes_require_internal_secret_and_never_advertise_order_capability(db_path):
    _seed_daily(db_path)
    settings.DB_PATH = db_path
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    assert client.get("/backtests/strategies").status_code == 403
    response = client.get("/backtests/strategies", headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET})
    assert response.status_code == 200
    assert response.json()["can_place_orders"] is False
    bad = client.post(
        "/backtests/runs", headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        json={"strategy_id": "does_not_exist", "start_date": "2026-01-01", "end_date": "2026-02-01"},
    )
    assert bad.status_code == 422


def _fake_penny_result(config, start, end, pnl):
    from penny_backtest_v2 import BacktestResult
    return BacktestResult(
        config_name=config, from_date=start, to_date=end,
        bankroll=100000.0, n_trading_days=10, n_tickers_considered=1,
        n_trades=1, wins=1 if pnl > 0 else 0, losses=1 if pnl <= 0 else 0,
        total_pnl=pnl, avg_r_multiple=pnl / 100.0,
        max_drawdown_pct=1.0 if pnl > 0 else 3.0,
    )


def test_penny_walk_forward_selects_on_train_and_scores_only_winner_on_test(
    db_path, monkeypatch,
):
    _seed_daily(db_path, ticker="CHEAP", count=180)
    adapter = backtest_lab.STRATEGY_REGISTRY[
        "penny_breakout_daily_proxy_walk_forward"
    ]
    config = adapter.snapshot_config({
        "train_days": 30, "test_days": 10, "step_days": 10,
        "anchored": False,
    })
    request = backtest_lab.BacktestRequest(
        adapter.metadata.strategy_id, "2025-01-01", "2025-05-30",
        config, adapter.metadata.default_assumptions,
    )
    prepared = adapter.prepare(db_path, request)
    from walk_forward import generate_folds
    folds = generate_folds(
        request.start_date, request.end_date, 30, 10, 10, False
    )
    train_windows = {(fold.train_start, fold.train_end) for fold in folds}
    test_windows = {(fold.test_start, fold.test_end) for fold in folds}
    calls = []

    def fake_run_backtest(from_date, to_date, config_name, bankroll, db_path):
        calls.append((config_name, from_date, to_date))
        if (from_date, to_date) in train_windows:
            pnl = {"baseline": 10.0, "relaxed": 5.0, "phase3": 1.0}[config_name]
        else:
            assert (from_date, to_date) in test_windows
            pnl = 3.0
        return _fake_penny_result(config_name, from_date, to_date, pnl)

    monkeypatch.setattr("penny_backtest_v2.run_backtest", fake_run_backtest)
    report = adapter.execute(prepared, request)
    assert report["n_scored_folds"] >= 3
    assert report["dataset_fingerprint"] == prepared.fingerprint
    assert all(fold["chosen_config"] == "baseline" for fold in report["folds"])
    assert all(fold["train"][1] < fold["test"][0] for fold in report["folds"])
    assert all(a["test"][1] < b["test"][0] for a, b in zip(report["folds"], report["folds"][1:]))
    for fold in folds:
        test_calls = [call for call in calls if call[1:] == (fold.test_start, fold.test_end)]
        assert test_calls == [("baseline", fold.test_start, fold.test_end)]
    assert report["positive_oos_fraction"] == 1.0
    assert report["selection_stability"] == 1.0
    assert report["folds"][0]["oos_scores"]["net_pnl"] == 3.0


def test_penny_walk_forward_insufficient_folds_has_no_aggregate(db_path, monkeypatch):
    _seed_daily(db_path, ticker="CHEAP", count=60)
    adapter = backtest_lab.STRATEGY_REGISTRY[
        "penny_breakout_daily_proxy_walk_forward"
    ]
    config = adapter.snapshot_config({
        "train_days": 30, "test_days": 10, "step_days": 10,
        "anchored": True,
    })
    request = backtest_lab.BacktestRequest(
        adapter.metadata.strategy_id, "2025-01-01", "2025-02-10",
        config, adapter.metadata.default_assumptions,
    )
    prepared = adapter.prepare(db_path, request)
    monkeypatch.setattr(
        "penny_backtest_v2.run_backtest",
        lambda from_date, to_date, config_name, bankroll, db_path:
            _fake_penny_result(config_name, from_date, to_date, 2.0),
    )
    report = adapter.execute(prepared, request)
    summary, warnings = adapter.normalize(report, request)
    assert report["verdict"] == "insufficient_data"
    assert "aggregate_oos_net_pnl" not in report
    assert summary["net_pnl"] is None
    assert summary["trade_count"] is None
    assert summary["oos"]["available"] is False
    assert any("Insufficient OOS" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_penny_walk_forward_run_persists_typed_config_and_fold_evidence(
    db_path, monkeypatch,
):
    _seed_daily(db_path, ticker="CHEAP", count=180)

    def fake_run_backtest(from_date, to_date, config_name, bankroll, db_path):
        pnl = {"baseline": 10.0, "relaxed": 5.0, "phase3": 1.0}[config_name]
        return _fake_penny_result(config_name, from_date, to_date, pnl)

    monkeypatch.setattr("penny_backtest_v2.run_backtest", fake_run_backtest)
    created = await submit_run(
        db_path, "penny_breakout_daily_proxy_walk_forward",
        "2025-01-01", "2025-05-30",
        {"train_days": 30, "test_days": 10, "step_days": 10,
         "anchored": False, "initial_bankroll": 100000},
        {},
    )
    run = await _wait_terminal(db_path, created["run_id"])
    assert run["status"] == "SUCCEEDED"
    assert run["config"] == {
        "initial_bankroll": 100000.0, "train_days": 30,
        "test_days": 10, "step_days": 10, "anchored": False,
    }
    assert run["dataset_fingerprint"].startswith("sha256:")
    assert run["dataset"]["shared_by_all_folds"] is True
    assert len(run["result"]["folds"]) >= 3
    assert run["summary"]["oos"]["available"] is True
    assert "DAILY PROXY ONLY" in " ".join(run["warnings"])


@pytest.mark.parametrize("config, message", [
    ({"train_days": 0}, "train_days"),
    ({"test_days": 20, "step_days": 10}, "overlapping"),
    ({"anchored": "true"}, "boolean"),
])
def test_penny_walk_forward_typed_config_validation(config, message):
    adapter = backtest_lab.STRATEGY_REGISTRY[
        "penny_breakout_daily_proxy_walk_forward"
    ]
    with pytest.raises(ValueError, match=message):
        adapter.snapshot_config(config)


def _seed_intraday_lab(db_path, interval="minute"):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE intraday_cache (
            ticker TEXT,interval TEXT,datetime TEXT,open REAL,high REAL,low REAL,
            close REAL,volume REAL,fetched_at TEXT,
            PRIMARY KEY(ticker,interval,datetime));
        CREATE TABLE ohlcv_cache (
            ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,
            volume REAL,fetched_at TEXT,PRIMARY KEY(ticker,date));
    """)
    for i in range(20):
        day = date(2026, 7, 1) + timedelta(days=i)
        conn.execute("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
                     ("AAA", day.isoformat(), 99, 101, 98, 100, 100000, "frozen"))
    step = 1 if interval == "minute" else 15
    for i in range(6):
        stamp = (date(2026, 8, 10).strftime("%Y-%m-%d") + "T" +
                 (datetime(2026, 8, 10, 10, 0) + timedelta(minutes=i * step)).strftime("%H:%M:%S"))
        conn.execute("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
                     ("AAA", interval, stamp, 99, 101, 98, 100, 1000, "frozen"))
    conn.commit(); conn.close()


@pytest.mark.asyncio
async def test_registry_exposes_distinct_true_intraday_adapters_and_daily_proxy(db_path):
    _seed_intraday_lab(db_path, "minute")
    # Add a distinct, explicitly-provenanced Momentum row without contaminating
    # the Penny ticker/day (Penny intentionally rejects mixed ticker-days).
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
                 ("BBB", "2026-07-01", 99, 101, 98, 100, 100000, "frozen"))
    conn.execute("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
                 ("BBB", "15minute", "2026-08-10T10:00:00", 99, 101, 98, 100, 1000, "frozen"))
    conn.commit(); conn.close()
    by_id = {row["strategy_id"]: row for row in await list_strategies(db_path)}
    penny = by_id["penny_breakout_intraday_1m_replay"]
    momentum = by_id["momentum_intraday_15m_replay"]
    assert penny["timeframe"] == "1 minute" and penny["available"] is True
    assert momentum["timeframe"] == "15 minute" and momentum["available"] is True
    assert "walk_forward" in penny["capabilities"]
    assert momentum["default_config"]["oos_folds"] == 3
    assert "penny_breakout_daily_proxy" in by_id


def test_true_intraday_adapter_configs_are_typed_and_non_overlapping():
    penny = backtest_lab.STRATEGY_REGISTRY["penny_breakout_intraday_1m_replay"]
    momentum = backtest_lab.STRATEGY_REGISTRY["momentum_intraday_15m_replay"]
    with pytest.raises(ValueError, match="overlapping"):
        penny.snapshot_config({"test_days": 20, "step_days": 10})
    with pytest.raises(ValueError, match="unknown Penny replay"):
        penny.snapshot_config({"variants": ["UNKNOWN"]})
    with pytest.raises(ValueError, match="three OOS"):
        momentum.snapshot_config({"oos_folds": 2})
    assert momentum.snapshot_config({"tickers": [" aaa "]})["tickers"] == ["AAA"]
    assert momentum.snapshot_config({"regime": "REGIME_2_ELEVATED"})["regime"] == "REGIME_2_ELEVATED"
    assert "REGIME_2_ELEVATED" in momentum.metadata.parameter_schema["regime"]["enum"]
    assert "REGIME_2_BEAR" not in momentum.metadata.parameter_schema["regime"]["enum"]


@pytest.mark.asyncio
async def test_penny_true_intraday_background_run_persists_frozen_result(db_path, monkeypatch):
    _seed_intraday_lab(db_path, "minute")
    fake = {
        "status": "complete", "dataset_fingerprint": "sha256:result",
        "variants": [{
            "variant": "PEN_BASE", "paper_entries": 1, "open_trades": 0,
            "closed_trades": 1, "net_pnl": 2.0, "profit_factor": None,
            "expectancy": 2.0, "avg_r": 1.0, "max_drawdown": 0.0,
        }], "warnings": ["synthetic replay"],
    }
    monkeypatch.setattr("penny_intraday_replay.run_penny_intraday_replay", lambda *args, **kwargs: fake)
    created = await submit_run(
        db_path, "penny_breakout_intraday_1m_replay", "2026-08-10", "2026-08-10",
        {"tickers": ["AAA"], "variants": ["PEN_BASE"]}, {},
    )
    run = await _wait_terminal(db_path, created["run_id"])
    assert run["status"] == "SUCCEEDED"
    assert run["dataset_fingerprint"].startswith("sha256:")
    assert run["dataset"]["timeframe"] == "minute"
    assert run["summary"]["net_pnl"] == 2.0
    assert run["result"]["dataset_fingerprint"] == "sha256:result"


@pytest.mark.asyncio
async def test_intraday_provenance_failure_is_archived_as_unavailable(db_path):
    _seed_intraday_lab(db_path, "legacy_unknown")
    created = await submit_run(
        db_path, "penny_breakout_intraday_1m_replay", "2026-08-10", "2026-08-10",
        {"tickers": ["AAA"]}, {},
    )
    run = await _wait_terminal(db_path, created["run_id"])
    assert run["status"] == "UNAVAILABLE"
    assert run["summary"] is None and run["result"] is None
    assert "provenance" in run["error"] or "minute" in run["error"]


@pytest.mark.asyncio
async def test_momentum_true_intraday_background_run_persists_oos_and_coverage(db_path, monkeypatch):
    _seed_intraday_lab(db_path, "15minute")
    fake = {
        "dataset_fingerprint": "sha256:momentum-result", "coverage": {"bars": 6},
        "funnel": {"MOM_BASE": {"evaluations": 6}}, "trades": [], "equity": [],
        "summary": {"entries": 0, "open_trades": 0, "closed_trades": 0,
                    "net_pnl": None, "profit_factor": None, "avg_r": None},
        "oos": {"status": "insufficient_data", "required_folds": 3,
                "scored_folds": 0, "folds": []},
        "warnings": ["no closed sample"],
    }
    monkeypatch.setattr("momentum_replay.run_momentum_replay", lambda *args, **kwargs: fake)
    created = await submit_run(
        db_path, "momentum_intraday_15m_replay", "2026-08-10", "2026-08-10",
        {"tickers": ["AAA"], "variants": ["MOM_BASE"]}, {},
    )
    run = await _wait_terminal(db_path, created["run_id"])
    assert run["status"] == "SUCCEEDED"
    assert run["dataset"]["selected_interval"] == "15minute"
    assert run["summary"]["net_pnl"] is None
    assert run["summary"]["oos"]["available"] is False
    assert run["result"]["coverage"] == {"bars": 6}
