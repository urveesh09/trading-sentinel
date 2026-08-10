from datetime import datetime, timedelta
import sqlite3

import pandas as pd
import pytest

from penny_engine_breakout import _rsi_14_wilder, evaluate_breakout_entry
from penny_intraday_replay import (
    PennyReplayConfig,
    run_penny_intraday_replay,
    run_penny_intraday_walk_forward,
)
from penny_shadow import _costs_from_snapshot


def _make_db(path, days, *, exit_kind="target"):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE intraday_cache (
            ticker TEXT, interval TEXT, datetime TEXT, open REAL, high REAL,
            low REAL, close REAL, volume REAL, fetched_at TEXT,
            PRIMARY KEY(ticker,interval,datetime))""")
        db.execute("""CREATE TABLE ohlcv_cache (
            ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,
            volume INTEGER,fetched_at TEXT,PRIMARY KEY(ticker,date))""")
        first = datetime.fromisoformat(days[0]).date()
        for offset in range(25, 0, -1):
            day = (first - timedelta(days=offset)).isoformat()
            db.execute("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
                       ("AAA", day, 99, 101, 98, 100, 100000, "frozen"))
        for day_text in days:
            start = datetime.fromisoformat(f"{day_text}T09:15:00")
            for minute in range(346):  # through the 15:00 bar
                stamp = start + timedelta(minutes=minute)
                close = 98.5 if minute % 2 else 99.0
                row = ["AAA", "minute", stamp.isoformat(), 98.8, 100, 98, close, 1000, "frozen"]
                if stamp.strftime("%H:%M") == "10:30":
                    row[3:8] = [99.5, 101, 99, 100.5, 1000]
                elif exit_kind == "time" and stamp > datetime.fromisoformat(f"{day_text}T10:30:00"):
                    row[3:8] = [101, 102, 100, 101, 1000]
                elif stamp.strftime("%H:%M") == "10:31":
                    if exit_kind == "gap":
                        row[3:8] = [98, 99, 97, 98, 1000]
                    elif exit_kind == "same_bar":
                        row[3:8] = [101, 106, 98, 102, 1000]
                    elif exit_kind == "target":
                        row[3:8] = [101, 106, 100, 105, 1000]
                    elif exit_kind == "time":
                        row[3:8] = [101, 102, 100, 101, 1000]
                if exit_kind == "time" and stamp.strftime("%H:%M") == "15:00":
                    row[3:8] = [102, 200, 1, 150, 1000]
                db.execute("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)", row)


def _variant(result, name="PEN_BASE"):
    return next(row for row in result["variants"] if row["variant"] == name)


def test_replay_uses_production_default_evaluator_with_first_distinct_candidate(tmp_path):
    path = tmp_path / "cache.db"
    _make_db(path, ["2026-08-10"])
    result = run_penny_intraday_replay(str(path), "2026-08-10", "2026-08-10")
    assert result["status"] == "complete"
    assert result["dataset_fingerprint"].startswith("sha256:")
    base = _variant(result)
    assert base["distinct_candidates"] == base["paper_entries"] == 1

    # Reconstruct precisely the signal-time prefix and call the shipped
    # evaluator with defaults: the replay entry must be identical.
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT datetime,open,high,low,close,volume FROM intraday_cache "
            "WHERE interval='minute' AND datetime <= '2026-08-10T10:30:00' ORDER BY datetime"
        ).fetchall()
    frame = pd.DataFrame(rows, columns=("datetime", "open", "high", "low", "close", "volume"))
    frame["datetime"] = pd.to_datetime(frame.datetime)
    visible = frame.set_index("datetime")
    risk = type("Risk", (), {"position_size": lambda self, entry, stop, regime: 1})()
    direct = evaluate_breakout_entry(
        "AAA", int(frame.volume.sum()), 100000, frame.iloc[-1].to_dict(),
        float(frame.iloc[:-1].high.max()), _rsi_14_wilder(frame.close.tolist()),
        frame.iloc[-1].datetime.to_pydatetime(), risk, intraday=visible,
    )
    trade = base["trades"][0]
    assert direct["accept"] is True
    assert (trade["entry_price"], trade["stop_price"], trade["target_price"]) == (
        direct["entry"], direct["stop_loss"], direct["target"],
    )


def test_future_volume_and_extremes_cannot_change_signal_features(tmp_path):
    first, second = tmp_path / "a.db", tmp_path / "b.db"
    _make_db(first, ["2026-08-10"])
    _make_db(second, ["2026-08-10"])
    with sqlite3.connect(second) as db:
        db.execute("UPDATE intraday_cache SET volume=999999,high=9999 "
                   "WHERE datetime='2026-08-10T10:31:00'")
    a = _variant(run_penny_intraday_replay(str(first), "2026-08-10", "2026-08-10"))["trades"][0]
    b = _variant(run_penny_intraday_replay(str(second), "2026-08-10", "2026-08-10"))["trades"][0]
    assert (a["entry_bar_ts"], a["entry_price"], a["stop_price"], a["target_price"]) == (
        b["entry_bar_ts"], b["entry_price"], b["stop_price"], b["target_price"],
    )


@pytest.mark.parametrize("kind,reason", [
    ("gap", "STOP_GAP_WORSE"),
    ("same_bar", "STOP_BEFORE_TARGET_SAME_BAR"),
    ("target", "TARGET"),
    ("time", "TIME_EXIT_1500"),
])
def test_conservative_subsequent_bar_exit_rules_and_real_costs(tmp_path, kind, reason):
    path = tmp_path / f"{kind}.db"
    _make_db(path, ["2026-08-10"], exit_kind=kind)
    result = run_penny_intraday_replay(str(path), "2026-08-10", "2026-08-10")
    trade = _variant(result)["trades"][0]
    assert trade["exit_reason"] == reason
    if kind == "gap":
        assert trade["exit_price"] == 98
    if kind == "time":
        assert trade["exit_price"] == 102  # cutoff bar open, never later extremes
    expected = _costs_from_snapshot(
        trade["entry_price"], trade["exit_price"], 1,
        result["assumptions"]["execution"],
    )
    assert trade["costs"] == expected > 0
    assert trade["net_pnl"] == pytest.approx(trade["gross_pnl"] - expected, abs=1e-4)


def test_provenance_rejects_legacy_mixed_and_missing_interval_schema(tmp_path):
    mixed = tmp_path / "mixed.db"
    _make_db(mixed, ["2026-08-10"])
    with sqlite3.connect(mixed) as db:
        db.execute("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)",
                   ("AAA", "legacy_unknown", "2026-08-10T09:15:00", 1, 1, 1, 1, 1, "old"))
    result = run_penny_intraday_replay(str(mixed), "2026-08-10", "2026-08-10")
    assert result["status"] == "invalid_data"
    assert result["dataset_fingerprint"] is None
    assert result["diagnostics"]["invalid_provenance"][0]["intervals"] == ["legacy_unknown", "minute"]

    legacy = tmp_path / "legacy.db"
    with sqlite3.connect(legacy) as db:
        db.execute("CREATE TABLE intraday_cache (ticker TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        db.execute("CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    result = run_penny_intraday_replay(str(legacy), "2026-08-10", "2026-08-10")
    assert result["status"] == "invalid_data"
    assert "provenance" in result["diagnostics"]["warning"]


def test_walk_forward_selects_train_only_and_scores_three_strict_later_folds(tmp_path):
    path = tmp_path / "walk.db"
    days = [f"2026-08-{day:02d}" for day in range(1, 9)]
    _make_db(path, days)
    result = run_penny_intraday_walk_forward(
        str(path), days[0], days[-1], train_days=1, test_days=1, step_days=2,
    )
    assert result["n_scored_folds"] == 4
    assert result["verdict"] != "insufficient_data"
    assert result["dataset_fingerprint"].startswith("sha256:")
    for fold in result["folds"]:
        assert fold["test"][0] > fold["train"][1]
        assert fold["chosen_config"] in {"PEN_BASE", "PEN_WINDOW", "PEN_VOLUME"}


def test_invalid_config_and_insufficient_oos_are_honest(tmp_path):
    with pytest.raises(ValueError):
        PennyReplayConfig(("UNKNOWN",))
    path = tmp_path / "short.db"
    _make_db(path, ["2026-08-01", "2026-08-02"])
    result = run_penny_intraday_walk_forward(
        str(path), "2026-08-01", "2026-08-02", train_days=1, test_days=1,
    )
    assert result["n_scored_folds"] == 1
    assert result["verdict"] == "insufficient_data"
    assert "mean_out_of_sample_score" not in result
