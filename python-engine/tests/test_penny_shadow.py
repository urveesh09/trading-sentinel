import ast
from dataclasses import FrozenInstanceError
from datetime import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock

import aiosqlite
import pandas as pd
import pytest

from penny_engine_breakout import evaluate_breakout_entry
from penny_shadow import (
    VARIANTS,
    evaluate_penny_shadows,
    init_penny_shadow_db,
    penny_shadow_comparison,
    persist_penny_shadow_results,
)
from penny_risk import calc_penny_costs


def _snapshot(as_of=datetime(2026, 8, 10, 10, 15), cum_vol=30000):
    frame = pd.DataFrame({
        "open": [10.0, 10.1], "high": [10.35, 10.45],
        "low": [9.95, 10.30], "close": [10.2, 10.40],
        "volume": [1000, 5000],
    }, index=pd.date_range("2026-08-10 10:13", periods=2, freq="min"))
    risk = MagicMock()
    risk.position_size.return_value = 50
    return {
        "ticker": "TEST", "cum_vol_today": cum_vol,
        "median_vol_20d": 10000,
        "breakout_bar": {"high": 10.45, "low": 10.30, "close": 10.40, "volume": 5000},
        "day_high": 10.35, "rsi_14": 55.0, "as_of": as_of,
        "risk_engine": risk, "intraday": frame,
    }


def test_baseline_variant_has_exact_live_evaluator_parity():
    inputs = _snapshot(as_of=datetime(2026, 8, 10, 11, 0))
    live = evaluate_breakout_entry(**inputs)
    shadow = evaluate_penny_shadows(**inputs, variants=["PEN_BASE"])[0]
    assert shadow["accepted"] == live["accept"]
    assert shadow["decision"] == live


def test_window_and_volume_candidates_change_only_declared_axis():
    early = evaluate_penny_shadows(**_snapshot())
    by_name = {row["variant"]: row for row in early}
    assert by_name["PEN_BASE"]["accepted"] is False
    assert "time window" in by_name["PEN_BASE"]["reject_reason"]
    assert by_name["PEN_WINDOW"]["accepted"] is True
    assert by_name["PEN_VOLUME"]["accepted"] is False

    volume = evaluate_penny_shadows(**_snapshot(
        as_of=datetime(2026, 8, 10, 11, 0), cum_vol=4500,
    ))
    by_name = {row["variant"]: row for row in volume}
    assert by_name["PEN_BASE"]["accepted"] is False
    assert "volume" in by_name["PEN_BASE"]["reject_reason"]
    assert by_name["PEN_VOLUME"]["accepted"] is True
    assert by_name["PEN_WINDOW"]["accepted"] is False


def test_registry_and_module_are_structurally_broker_free():
    with pytest.raises(TypeError):
        VARIANTS["X"] = VARIANTS["PEN_BASE"]
    with pytest.raises(FrozenInstanceError):
        VARIANTS["PEN_BASE"].time_start_min = 1
    tree = ast.parse((Path(__file__).parents[1] / "penny_shadow.py").read_text())
    imports = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    assert not any(
        token in name.lower() for name in imports
        for token in ("kite", "executor", "order")
    )


@pytest.mark.parametrize("kwargs", [
    {"time_start_min": 500}, {"time_start_min": True},
    {"volume_multiplier": 0}, {"volume_multiplier": float("nan")},
])
def test_invalid_declared_overrides_rejected(kwargs):
    with pytest.raises(ValueError):
        evaluate_breakout_entry(**_snapshot(), **kwargs)


def _row(variant, bar_ts, accepted, ticker="AAA", reason=None):
    return {
        "trading_date": "2026-08-10", "ticker": ticker,
        "bar_ts": bar_ts, "variant": variant, "accepted": accepted,
        "reject_reason": reason, "dataset_fingerprint": "abc123",
        "features": {"x": 1.0}, "config": {"name": variant},
    }


@pytest.mark.asyncio
async def test_persistence_dedupes_rows_and_distinct_candidates(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    rows = [
        _row("PEN_BASE", "2026-08-10T10:30:00", True),
        _row("PEN_BASE", "2026-08-10T10:31:00", True),
        _row("PEN_BASE", "2026-08-10T10:32:00", False, "BBB", "volume"),
        _row("PEN_WINDOW", "2026-08-10T10:00:00", False, reason="breakout"),
    ]
    assert await persist_penny_shadow_results(db_path, rows) == 4
    assert await persist_penny_shadow_results(db_path, rows) == 0
    comparison = await penny_shadow_comparison(db_path)
    by_name = {row["variant"]: row for row in comparison["variants"]}
    assert by_name["PEN_BASE"]["evaluations"] == 3
    assert by_name["PEN_BASE"]["raw_accepts"] == 2
    assert by_name["PEN_BASE"]["distinct_candidates"] == 1
    assert by_name["PEN_BASE"]["repeat_accepts"] == 1
    assert by_name["PEN_BASE"]["accept_rate"] == pytest.approx(2 / 3, abs=1e-6)


@pytest.mark.asyncio
async def test_empty_and_trade_metrics_are_honest_nulls(tmp_path):
    comparison = await penny_shadow_comparison(str(tmp_path / "empty.db"))
    assert {row["variant"] for row in comparison["variants"]} == set(VARIANTS)
    for row in comparison["variants"]:
        assert row["evaluations"] == 0
        assert row["accept_rate"] is None
        for metric in ("paper_entries", "fills", "closed_trades", "net_pnl", "expectancy"):
            assert row[metric] is None
        assert row["warnings"]


@pytest.mark.asyncio
async def test_non_finite_evidence_is_standard_json(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    row = _row("PEN_BASE", "2026-08-10T10:30:00", False, reason="volume")
    row["features"] = {"nan": float("nan")}
    await persist_penny_shadow_results(db_path, [row])
    async with aiosqlite.connect(db_path) as db:
        payload = (await (await db.execute(
            "SELECT features_json FROM penny_shadow_evaluations"
        )).fetchone())[0]
    assert json.loads(payload) == {"nan": None}


def _trade_row(bar_ts="2026-08-10T10:30:00", frame=None):
    row = _row("PEN_BASE", bar_ts, True)
    row["decision"] = {
        "accept": True, "entry": 10.0, "stop_loss": 9.0, "target": 12.0,
    }
    row["_intraday_frame"] = frame if frame is not None else pd.DataFrame({
        "open": [10.0], "high": [10.2], "low": [9.8], "close": [10.1],
        "volume": [1000],
    }, index=pd.to_datetime([bar_ts]))
    return row


async def _stored_trade(db_path):
    async with aiosqlite.connect(db_path) as db:
        return await (await db.execute("""
            SELECT status,entry_price,stop_price,target_price,quantity,last_bar_ts,
                   exit_price,gross_pnl,costs,net_pnl,r_multiple,exit_reason
            FROM penny_shadow_virtual_trades
        """)).fetchone()


@pytest.mark.asyncio
async def test_virtual_trade_is_one_share_restart_safe_and_same_bar_is_conservative(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])

    later = pd.DataFrame({
        "open": [10.0, 10.1], "high": [10.2, 12.5],
        "low": [9.8, 8.5], "close": [10.1, 11.0], "volume": [1000, 2000],
    }, index=pd.to_datetime(["2026-08-10T10:30:00", "2026-08-10T10:31:00"]))
    observation = _row("PEN_BASE", "2026-08-10T10:31:00", False, reason="repeat")
    observation["_intraday_frame"] = later
    await persist_penny_shadow_results(db_path, [observation])
    first = await _stored_trade(db_path)
    assert first[0:5] == ("CLOSED", 10.0, 9.0, 12.0, 1)
    assert first[6] == 9.0
    assert first[11] == "STOP_BEFORE_TARGET_SAME_BAR"
    assert first[8] == pytest.approx(calc_penny_costs(
        10.0, 9.0, 1, is_intraday=True,
    ))
    assert first[9] == pytest.approx(first[7] - first[8])
    assert first[10] == pytest.approx(first[9])

    # Replaying the same persisted frame after a process restart is a no-op.
    await persist_penny_shadow_results(db_path, [observation])
    assert await _stored_trade(db_path) == first
    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute(
            "SELECT COUNT(*) FROM penny_shadow_virtual_trades"
        )).fetchone())[0]
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("when", "open_price", "high", "low", "exit_price", "reason"), [
    ("2026-08-10T10:31:00", 8.5, 9.2, 8.2, 8.5, "STOP_GAP_WORSE"),
    ("2026-08-10T10:31:00", 12.5, 12.8, 12.2, 12.0, "TARGET_GAP_CAPPED"),
    ("2026-08-10T15:00:00", 10.4, 12.5, 8.5, 10.4, "TIME_EXIT_1500"),
])
async def test_virtual_gap_and_time_exit_fill_rules(
    tmp_path, when, open_price, high, low, exit_price, reason,
):
    db_path = str(tmp_path / f"{reason}.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])
    frame = pd.DataFrame({
        "open": [10.0, open_price], "high": [10.2, high], "low": [9.8, low],
        "close": [10.1, open_price], "volume": [1000, 1000],
    }, index=pd.to_datetime(["2026-08-10T10:30:00", when]))
    row = _row("PEN_BASE", when, False, reason="later scan")
    row["_intraday_frame"] = frame
    await persist_penny_shadow_results(db_path, [row])
    trade = await _stored_trade(db_path)
    assert trade[0] == "CLOSED"
    assert trade[6] == exit_price
    assert trade[11] == reason


@pytest.mark.asyncio
async def test_comparison_reports_only_defensible_closed_outcomes(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])
    open_metrics = (await penny_shadow_comparison(db_path))["variants"][0]
    assert open_metrics["paper_entries"] == 1
    assert open_metrics["open_trades"] == 1
    assert open_metrics["closed_trades"] == 0
    assert open_metrics["net_pnl"] is None
    assert open_metrics["expectancy"] is None
    assert open_metrics["profit_factor"] is None
    assert open_metrics["max_drawdown"] is None
    for metric in (
        "winning_trades", "losing_trades", "breakeven_trades", "win_rate", "avg_r",
    ):
        assert open_metrics[metric] is None


@pytest.mark.asyncio
async def test_virtual_book_charges_declared_costs_despite_paper_bypass(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "PENNY_BROKERAGE_BYPASS", True)
    monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)
    db_path = str(tmp_path / "shadow.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])
    later = pd.DataFrame({
        "open": [10.0, 9.0], "high": [10.2, 9.1], "low": [9.8, 8.9],
        "close": [10.1, 9.0], "volume": [1000, 1000],
    }, index=pd.to_datetime(["2026-08-10T10:30:00", "2026-08-10T10:31:00"]))
    row = _row("PEN_BASE", "2026-08-10T10:31:00", False, reason="later")
    row["_intraday_frame"] = later
    await persist_penny_shadow_results(db_path, [row])
    assert (await _stored_trade(db_path))[8] > 0


@pytest.mark.asyncio
async def test_true_zero_net_pnl_is_breakeven_and_pf_stays_undefined(tmp_path):
    db_path = str(tmp_path / "shadow.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            UPDATE penny_shadow_virtual_trades SET
                status='CLOSED', exit_bar_ts='2026-08-10T10:31:00',
                exit_price=10.25, gross_pnl=0.25, costs=0.25, net_pnl=0,
                r_multiple=0, exit_reason='TEST_EXACT_BREAKEVEN',
                closed_at='2026-08-10T10:32:00'
            WHERE variant='PEN_BASE'
        """)
        await db.commit()
    metrics = (await penny_shadow_comparison(db_path))["variants"][0]
    assert metrics["closed_trades"] == 1
    assert metrics["winning_trades"] == 0
    assert metrics["losing_trades"] == 0
    assert metrics["breakeven_trades"] == 1
    assert metrics["win_rate"] == 0
    assert metrics["avg_r"] == 0
    assert metrics["profit_factor"] is None


@pytest.mark.asyncio
async def test_restart_and_rate_change_use_entry_frozen_execution_snapshot(tmp_path, monkeypatch):
    from config import settings
    db_path = str(tmp_path / "shadow.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])
    expected = calc_penny_costs(10.0, 9.0, 1, is_intraday=True)

    for field in (
        "PENNY_BROKERAGE_PCT", "PENNY_BROKERAGE_MAX", "PENNY_STT_MIS",
        "PENNY_EXCHANGE_PCT", "PENNY_STAMP_DUTY_PCT", "PENNY_SEBI_PCT",
        "PENNY_IPFT_PCT", "PENNY_GST_PCT",
    ):
        monkeypatch.setattr(settings, field, 0.0)

    # A fresh persistence call models restart: closure must not consult the
    # now-mutated settings singleton.
    later = pd.DataFrame({
        "open": [10.0, 9.0], "high": [10.2, 9.1], "low": [9.8, 8.9],
        "close": [10.1, 9.0], "volume": [1000, 1000],
    }, index=pd.to_datetime(["2026-08-10T10:30:00", "2026-08-10T10:31:00"]))
    row = _row("PEN_BASE", "2026-08-10T10:31:00", False, reason="later")
    row["_intraday_frame"] = later
    await persist_penny_shadow_results(db_path, [row])
    assert (await _stored_trade(db_path))[8] == pytest.approx(expected)

    metrics = (await penny_shadow_comparison(db_path))["variants"][0]
    assert metrics["execution_basis"] == "FROZEN_AT_VIRTUAL_ENTRY"
    assert metrics["execution_snapshots"][0]["trade_count"] == 1
    snapshot = metrics["execution_snapshots"][0]["snapshot"]
    assert snapshot["origin"] == "ENTRY"
    assert snapshot["rates"]["brokerage_pct"] > 0


@pytest.mark.asyncio
async def test_legacy_trade_table_migration_backfills_execution_basis(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE penny_shadow_virtual_trades (
                variant TEXT NOT NULL, trading_date TEXT NOT NULL, ticker TEXT NOT NULL,
                entry_bar_ts TEXT NOT NULL, entry_price REAL NOT NULL, stop_price REAL NOT NULL,
                target_price REAL NOT NULL, quantity INTEGER NOT NULL, initial_risk REAL NOT NULL,
                sizing_basis TEXT NOT NULL, dataset_fingerprint TEXT NOT NULL,
                config_json TEXT NOT NULL, status TEXT NOT NULL, last_bar_ts TEXT NOT NULL,
                exit_bar_ts TEXT, exit_price REAL, gross_pnl REAL, costs REAL, net_pnl REAL,
                r_multiple REAL, exit_reason TEXT, created_at TEXT NOT NULL, closed_at TEXT,
                PRIMARY KEY (variant,trading_date,ticker)
            )
        """)
        await db.execute("""
            INSERT INTO penny_shadow_virtual_trades VALUES
            ('PEN_BASE','2026-08-09','OLD','2026-08-09T10:30:00',10,9,12,1,1,
             'ONE_SHARE_FIXED','legacy','{}','CLOSED','2026-08-09T10:31:00',
             '2026-08-09T10:31:00',9,-1,0.1,-1.1,-1.1,'STOP','created','closed')
        """)
        await db.execute("""
            CREATE TRIGGER penny_shadow_trade_closed_immutable
            BEFORE UPDATE ON penny_shadow_virtual_trades WHEN OLD.status='CLOSED'
            BEGIN SELECT RAISE(ABORT, 'closed virtual trades are immutable'); END
        """)
        await db.commit()
    await init_penny_shadow_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        payload = (await (await db.execute(
            "SELECT execution_json FROM penny_shadow_virtual_trades"
        )).fetchone())[0]
    assert json.loads(payload)["origin"] == "MIGRATED_AT_INIT"


@pytest.mark.asyncio
async def test_init_never_rewrites_existing_frozen_execution_json(tmp_path):
    db_path = str(tmp_path / "preserve.db")
    await persist_penny_shadow_results(db_path, [_trade_row()])
    async with aiosqlite.connect(db_path) as db:
        before = (await (await db.execute(
            "SELECT execution_json FROM penny_shadow_virtual_trades"
        )).fetchone())[0]
    await init_penny_shadow_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        after = (await (await db.execute(
            "SELECT execution_json FROM penny_shadow_virtual_trades"
        )).fetchone())[0]
    assert after == before
