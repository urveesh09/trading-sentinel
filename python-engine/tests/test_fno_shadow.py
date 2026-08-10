from __future__ import annotations

import ast
import asyncio
import copy
from datetime import date, datetime
import inspect
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import aiosqlite
import pandas as pd
import pytest
import pytz
from fastapi.testclient import TestClient

import fno_orchestrator
import fno_shadow
from config import settings
from fno_engine_mom import evaluate_fno_mom
from fno_models import Contract, ContractQuote


IST = pytz.timezone("Asia/Kolkata")
DAY = date(2026, 7, 10)


def _bars(include_confirmation: bool = False) -> pd.DataFrame:
    frames = []
    for day in ("2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"):
        index = pd.date_range(f"{day} 09:15", periods=74, freq="5min")
        frames.append(pd.DataFrame({
            "open": 25000.0, "high": 25010.0, "low": 24990.0,
            "close": 25000.0, "volume": 100.0,
        }, index=index))
    rows = [
        ("09:15", 25000), ("09:20", 25000), ("09:25", 25000),
        ("09:30", 25000), ("09:35", 25000), ("09:40", 25000),
        ("09:45", 25002), ("09:50", 25003), ("09:55", 25017),
    ]
    if include_confirmation:
        rows.append(("10:00", 25018))
    index = pd.to_datetime([f"2026-07-10 {time}" for time, _ in rows])
    closes = [close for _, close in rows]
    frames.append(pd.DataFrame({
        "open": closes, "high": [value + 10 for value in closes],
        "low": [value - 10 for value in closes], "close": closes,
        "volume": [300.0 if i >= 8 else 100.0 for i in range(len(rows))],
    }, index=index))
    return pd.concat(frames)


def test_baseline_is_exact_production_evaluator_parity():
    bars = _bars()
    now = IST.localize(datetime(2026, 7, 10, 10, 1))
    production = evaluate_fno_mom(bars, "REGIME_1_BULL", now)
    row = fno_shadow.evaluate_fno_shadows(
        bars, "REGIME_1_BULL", now, variants=["FNO_BASE"],
    )[0]
    assert row["accepted"] is (production.direction is not None)
    assert row["direction"] == (production.direction.value if production.direction else None)
    assert row["reject_reason"] == (None if production.direction else production.reject_reason)
    assert row["bar_ts"] == production.bar_ts
    assert row["features"]["stop_underlying"] == production.stop_underlying
    assert row["features"]["target_underlying"] == production.target_underlying


def test_confirmation_variant_accepts_only_first_bounded_bar_after_cross():
    bars = _bars(include_confirmation=True)
    now = IST.localize(datetime(2026, 7, 10, 10, 6))
    rows = {row["variant"]: row for row in fno_shadow.evaluate_fno_shadows(
        bars, "REGIME_1_BULL", now, variants=["FNO_BASE", "FNO_CONFIRM_1"],
    )}
    assert rows["FNO_BASE"]["accepted"] is False
    assert rows["FNO_BASE"]["reject_reason"] == "not_fresh_break"
    assert rows["FNO_CONFIRM_1"]["accepted"] is True
    assert rows["FNO_CONFIRM_1"]["direction"] == "LONG"


def test_cost_scenario_uses_resolved_quote_and_production_cost_model(monkeypatch):
    bars = _bars()
    now = IST.localize(datetime(2026, 7, 10, 10, 1))
    rows = fno_shadow.evaluate_fno_shadows(
        bars, "REGIME_1_BULL", now, variants=["FNO_BASE"],
    )
    contract = Contract(1, "NIFTYCE", "NIFTY", date(2026, 7, 14), 25000, "CE", 75)
    quote = ContractQuote(contract, bid=99.0, ask=101.0, ltp=100.0)
    monkeypatch.setattr(fno_shadow, "select_strike_by_delta", lambda *_: (quote, 0.15, 0.55))
    snapshot = SimpleNamespace(lot_size=75)
    fno_shadow.attach_resolved_cost_estimates(rows, snapshot, now)
    outcome = rows[0]["post_cost_outcome"]
    assert outcome["available"] is True
    assert outcome["estimated_costs"] > 0
    assert outcome["estimated_net_pnl"] < outcome["gross_pnl"]
    assert "target_scenario" in outcome["kind"]
    assert outcome["execution_snapshot"]["schedule_version"] == "ZERODHA_NSE_OPTIONS_2026-04-01"
    assert outcome["execution_snapshot"]["effective_date"] == "2026-04-01"


@pytest.mark.asyncio
async def test_persistence_is_idempotent_and_comparison_separates_counts(db_path):
    rows = fno_shadow.evaluate_fno_shadows(
        _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    )
    assert await fno_shadow.persist_fno_shadow_results(db_path, rows) == 4
    assert await fno_shadow.persist_fno_shadow_results(db_path, rows) == 0
    comparison = await fno_shadow.fno_shadow_comparison(db_path)
    base = next(row for row in comparison["variants"] if row["variant"] == "FNO_BASE")
    assert base["evaluations"] == 1
    assert base["accepted_evaluations"] == 1
    assert base["distinct_candidates"] == 1
    assert base["estimated_post_cost"]["available_samples"] == 0
    assert base["estimated_post_cost"]["estimated_net_pnl"] is None

    repeated = copy.deepcopy(next(row for row in rows if row["variant"] == "FNO_BASE"))
    repeated["bar_ts"] = "2026-07-10 10:05:00"
    repeated["candidate_key"] = "poisoned|per-bar|identity"
    assert await fno_shadow.persist_fno_shadow_results(db_path, [repeated]) == 1
    base = next(row for row in (await fno_shadow.fno_shadow_comparison(db_path))["variants"]
                if row["variant"] == "FNO_BASE")
    assert base["evaluations"] == 2
    assert base["accepted_evaluations"] == 2
    assert base["distinct_candidates"] == 1


@pytest.mark.asyncio
async def test_shadow_failure_is_isolated_from_orchestrator(monkeypatch, db_path):
    monkeypatch.setattr(fno_shadow, "evaluate_fno_shadows", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("shadow down")))
    assert await fno_orchestrator._record_shadow_observation(
        db_path, _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    ) == 0


@pytest.mark.asyncio
async def test_slow_shadow_is_supervised_and_never_awaited_by_tick_path(monkeypatch, db_path):
    release = threading.Event()

    def slow(*_args, **_kwargs):
        release.wait(timeout=5)
        return 1

    monkeypatch.setattr(fno_shadow, "persist_fno_shadow_results_sync", slow)
    task = fno_orchestrator._schedule_shadow_observation(
        db_path, _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    )
    assert task in fno_orchestrator._SHADOW_TASKS
    assert not task.done()
    # Scheduling returned while persistence is still blocked; the production
    # path does not receive a result that could alter signal/sizing/order flow.
    release.set()
    assert await asyncio.to_thread(task.result, 5) == 1
    assert task not in fno_orchestrator._SHADOW_TASKS

    source = inspect.getsource(fno_orchestrator.run_fno_tick)
    assert source.rfind("_try_entry_for_leg(") < source.rfind("_schedule_shadow_observation(")


def test_operational_toggle_prevents_scheduling(monkeypatch, db_path):
    monkeypatch.setattr(settings, "FNO_SHADOW_ENABLED", False)
    submit = Mock(wraps=fno_orchestrator._SHADOW_EXECUTOR.submit)
    monkeypatch.setattr(fno_orchestrator._SHADOW_EXECUTOR, "submit", submit)
    assert fno_orchestrator._schedule_shadow_observation(
        db_path, _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    ) is None
    submit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("trading_date", "not-a-date"),
    ("bar_ts", "2026-07-11 10:00:00"),
    ("underlying", ""),
    ("underlying", "NIFTY;DROP"),
    ("direction", "SIDEWAYS"),
])
async def test_malformed_identity_evidence_is_rejected(db_path, field, value):
    row = fno_shadow.evaluate_fno_shadows(
        _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
        variants=["FNO_BASE"],
    )[0]
    row[field] = value
    with pytest.raises(ValueError):
        await fno_shadow.persist_fno_shadow_results(db_path, [row])
    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute("SELECT COUNT(*) FROM fno_shadow_evaluations")).fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_non_finite_close_cannot_poison_comparison(db_path):
    row = fno_shadow.evaluate_fno_shadows(
        _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
        variants=["FNO_BASE"],
    )[0]
    row["features"]["close"] = float("nan")
    with pytest.raises(ValueError, match="finite close"):
        await fno_shadow.persist_fno_shadow_results(db_path, [row])


def test_shadow_has_no_order_sizing_or_broker_surface():
    tree = ast.parse(inspect.getsource(fno_shadow))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported.intersection({"fno_executor", "fno_positions", "fno_risk", "kite_client"})
    assert "kite" not in inspect.signature(fno_orchestrator._record_shadow_observation).parameters
    assert not hasattr(fno_shadow, "execute_entry")
    assert not hasattr(fno_shadow, "lots_for_pool")


def test_live_leg_remains_triple_disarmed_by_default():
    assert settings.FNO_DISABLE_LIVE is True
    assert settings.FNO_LIVE_TRADING is False
    assert settings.FNO_LIVE_BANKROLL == 0


def test_authenticated_registry_and_comparison_endpoint(monkeypatch, db_path):
    from main import app

    monkeypatch.setattr(settings, "DB_PATH", db_path)
    client = TestClient(app)
    assert client.get("/experiments/fno-opening-range").status_code == 403
    response = client.get(
        "/experiments/fno-opening-range",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["research_only"] is True and body["can_place_orders"] is False
    assert set(body["registry"]) == set(fno_shadow.VARIANTS)
    assert body["comparison"]["can_place_orders"] is False

    monkeypatch.setattr(settings, "FNO_SHADOW_ENABLED", False)
    disabled = client.get(
        "/experiments/fno-opening-range",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    ).json()
    assert disabled["enabled"] is False
    assert disabled["config"] == {"enabled": False}
    assert disabled["status"] == "disabled"
