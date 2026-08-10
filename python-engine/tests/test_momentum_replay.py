import sqlite3

import pandas as pd
import pytest

import momentum_replay as replay


def _cache(path, *, days=5, provenance="15minute"):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE intraday_cache (
            ticker TEXT NOT NULL, interval TEXT, datetime TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL, fetched_at TEXT,
            PRIMARY KEY(ticker,interval,datetime)
        );
        CREATE TABLE ohlcv_cache (
            ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,
            volume INTEGER,fetched_at TEXT,PRIMARY KEY(ticker,date)
        );
    """)
    for stamp in pd.date_range("2026-07-01", periods=30, freq="D"):
        connection.execute(
            "INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
            ("AAA", stamp.date().isoformat(), 98, 102, 97, 100, 100000, "fetched"),
        )
    for day in pd.date_range("2026-08-03", periods=days, freq="D"):
        for offset, stamp in enumerate(pd.date_range(
            f"{day.date().isoformat()} 10:00", periods=6, freq="15min",
        )):
            high = 104 if offset == 4 else 101
            low = 98 if offset == 4 else 99
            connection.execute(
                "INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
                ("AAA", provenance, stamp.isoformat(), 100, high, low, 100.5, 1000 + offset, "fetched"),
            )
    connection.commit()
    connection.close()


def _accept_on_four(call_log):
    def evaluator(**kwargs):
        frame = kwargs["df"]
        daily = kwargs["df_daily"]
        call_log.append({
            "length": len(frame), "last": frame.index[-1],
            "daily_last": daily.index[-1], "kwargs": kwargs,
        })
        fired = len(frame) >= 4
        return fired, ({
            "entry_price": 100.0, "stop_loss": 99.0, "target_1": 103.0,
            "shares": 10, "reject_reason": None,
        } if fired else {"reject_reason": "synthetic_prefix"})
    return evaluator


def test_replay_is_prefix_only_first_candidate_idempotent_and_three_fold_oos(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.db")
    _cache(path)
    calls = []
    monkeypatch.setattr(replay, "evaluate_momentum_signal", _accept_on_four(calls))
    first = replay.run_momentum_replay(path)
    second = replay.run_momentum_replay(path)
    assert first == second
    assert first["coverage"]["selected_interval"] == "15minute"
    assert first["summary"]["entries"] == 10  # 5 days x 2 variants, once each
    assert first["oos"]["status"] == "scored"
    assert first["oos"]["scored_folds"] == 3
    for fold in first["oos"]["folds"]:
        assert fold["train_end"] < fold["test_start"]
    assert all(item["daily_last"].date() < item["last"].date() for item in calls)
    # Evaluator receives chronological prefixes, never the six-bar completed day
    # on its first evaluation or a future daily row.
    assert {item["length"] for item in calls} == set(range(1, 7))
    assert first["funnel"]["MOM_BASE"]["accepted_prefixes"] == 15
    assert first["funnel"]["MOM_BASE"]["distinct_candidates"] == 5


def test_variant_arguments_have_production_parity_contract(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.db")
    _cache(path, days=1)
    calls = []
    monkeypatch.setattr(replay, "evaluate_momentum_signal", _accept_on_four(calls))
    result = replay.run_momentum_replay(path)
    base = next(item for item in calls if item["kwargs"]["crossover_lookback"] == 3)
    recency = next(item for item in calls if item["kwargs"]["crossover_lookback"] == 5)
    assert base["kwargs"]["max_vwap_distance_atr"] is None
    assert recency["kwargs"]["max_vwap_distance_atr"] == 0.50
    assert base["kwargs"]["regime"].name == result["config"]["regime"]
    assert base["kwargs"]["min_candles"] == result["config"]["min_candles"]
    assert result["config"]["evaluator_settings"]


def test_baseline_replay_decisions_are_the_actual_production_evaluator_outputs(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.db")
    _cache(path, days=1)
    production = replay.evaluate_momentum_signal
    observed = []

    def capture(**kwargs):
        outcome = production(**kwargs)
        observed.append((kwargs["crossover_lookback"], outcome))
        return outcome

    monkeypatch.setattr(replay, "evaluate_momentum_signal", capture)
    result = replay.run_momentum_replay(path)
    for variant, lookback in (("MOM_BASE", 3), ("MOM_RECENCY_5", 5)):
        outcomes = [outcome for seen_lookback, outcome in observed if seen_lookback == lookback]
        assert result["funnel"][variant]["evaluations"] == len(outcomes)
        assert result["funnel"][variant]["accepted_prefixes"] == sum(bool(item[0]) for item in outcomes)
        expected_rejects = {}
        for fired, decision in outcomes:
            if not fired:
                reason = decision.get("reject_reason", "unknown")
                expected_rejects[reason] = expected_rejects.get(reason, 0) + 1
        assert result["funnel"][variant]["rejects"] == expected_rejects


@pytest.mark.parametrize("provenance", ["legacy_unknown", ""])
def test_replay_rejects_missing_or_legacy_provenance(tmp_path, provenance):
    path = str(tmp_path / "cache.db")
    _cache(path, days=1, provenance=provenance)
    with pytest.raises(replay.ReplayDataError, match="provenance"):
        replay.run_momentum_replay(path)


def test_replay_rejects_legacy_schema_without_interval(tmp_path):
    path = str(tmp_path / "cache.db")
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE intraday_cache(ticker TEXT,datetime TEXT)")
    connection.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT)")
    connection.commit()
    connection.close()
    with pytest.raises(replay.ReplayDataError, match="lacks interval"):
        replay.run_momentum_replay(path)


def test_fill_model_is_stop_first_cost_aware_and_full_quantity():
    execution = replay.momentum_shadow_execution_config()
    candidate = {
        "variant": "MOM_BASE", "ticker": "AAA", "trading_date": "2026-08-03",
        "bar_ts": "2026-08-03T10:45:00", "dataset_fingerprint": "sha256:test",
        "decision": {"entry_price": 100, "stop_loss": 99, "target_1": 103, "shares": 10},
    }
    future = pd.DataFrame({
        "open": [100], "high": [104], "low": [98], "close": [101], "volume": [1],
    }, index=pd.to_datetime(["2026-08-03T11:00:00"]))
    trade = replay._simulate(candidate, future, execution)
    assert trade["exit_reason"] == "stop_before_target_same_bar"
    assert trade["quantity"] == 10
    assert trade["costs"] > 0
    assert trade["net_pnl"] == pytest.approx(trade["gross_pnl"] - trade["costs"])


def test_oos_selection_never_uses_test_fold_outcomes():
    trades = []
    for day in range(1, 6):
        for variant, pnl in (("MOM_BASE", 1.0), ("MOM_RECENCY_5", 1000.0 if day == 5 else -1.0)):
            trades.append({
                "status": "CLOSED", "variant": variant,
                "trading_date": f"2026-08-0{day}", "net_pnl": pnl,
            })
    result = replay.chronological_oos(trades, tuple(replay.VARIANTS), folds=3)
    assert result["scored_folds"] == 3
    assert all(fold["selected_variant"] == "MOM_BASE" for fold in result["folds"])


def test_oos_does_not_score_alphabetical_selection_without_train_evidence():
    trades = [{
        "status": "CLOSED", "variant": "UNREGISTERED",
        "trading_date": f"2026-08-0{day}", "net_pnl": 1.0,
    } for day in range(1, 6)]
    result = replay.chronological_oos(trades, tuple(replay.VARIANTS), folds=3)
    assert result["status"] == "insufficient_data"
    assert result["scored_folds"] == 0
    assert all(fold["reason"] == "no_train_sample" for fold in result["folds"])


def test_oos_fold_requires_a_close_for_the_train_selected_variant():
    trades = []
    for day in range(1, 6):
        # BASE wins the sole train day, but disappears from every test period.
        if day == 1:
            trades.append({"status": "CLOSED", "variant": "MOM_BASE", "trading_date": "2026-08-01", "net_pnl": 10.0})
        trades.append({"status": "CLOSED", "variant": "MOM_RECENCY_5", "trading_date": f"2026-08-0{day}", "net_pnl": -1.0})
    result = replay.chronological_oos(trades, tuple(replay.VARIANTS), folds=3)
    assert result["status"] == "insufficient_data"
    assert result["scored_folds"] < 3
    assert any(fold["reason"] == "selected_variant_has_no_oos_close" for fold in result["folds"])
