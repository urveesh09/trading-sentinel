import json
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


def _kite():
    kite = MagicMock()
    kite.instrument_cache = {"AAA": 1001}
    kite.get_quote = AsyncMock(return_value={
        1001: {
            "last_price": 10.4, "volume": 30000,
            "ohlc": {"high": 10.45, "low": 10.0, "close": 10.2},
        }
    })
    index = pd.date_range("2026-08-10 10:40", periods=20, freq="min")
    intraday = pd.DataFrame({
        "open": [10.0] * 20, "high": [10.35] * 19 + [10.45],
        "low": [9.95] * 19 + [10.30], "close": [10.2] * 19 + [10.40],
        "volume": [1000] * 19 + [5000],
    }, index=index)
    kite.get_intraday = AsyncMock(return_value=intraday)
    daily_index = pd.date_range("2026-07-15", periods=20, freq="D")
    kite.get_historical = AsyncMock(return_value=pd.DataFrame({
        "open": [10.0] * 20, "high": [10.5] * 20, "low": [9.5] * 20,
        "close": [10.0] * 20, "volume": [10000] * 20,
    }, index=daily_index))
    return kite


def _universe(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "penny.json"
    path.write_text(json.dumps({
        "as_of": "2026-08-10", "tickers": [{
            "symbol": "AAA", "series": "EQ", "prev_close": 10.2,
            "promoter_holding_pct": 50, "pb_ratio": 1.0,
            "is_t2t": False, "is_asm": False, "is_gsm": False,
            "median_traded_value_20d": 1000000,
        }],
    }))
    return str(path)


def _shadow_row(kwargs):
    return [{
        "trading_date": "2026-08-10", "ticker": kwargs["ticker"],
        "bar_ts": str(kwargs["bar_ts"]), "variant": "PEN_BASE",
        "accepted": True, "reject_reason": None,
        "dataset_fingerprint": "fingerprint", "features": {},
        "config": {"name": "PEN_BASE"},
    }]


async def _scan(tmp_path, monkeypatch, enabled, shadow_effect=None, persist=None, order_result=None):
    from config import settings
    from penny_scanner import PennyScanner

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "scan.db"))
    monkeypatch.setattr(settings, "PENNY_LOG_CSV_PATH", str(tmp_path / "signals.csv"))
    monkeypatch.setattr(settings, "PENNY_SHADOW_ENABLED", enabled)
    monkeypatch.setattr(settings, "PENNY_USE_SECTOR_FILTER", False)
    kite = _kite()
    scanner = PennyScanner(
        kite=kite, universe_json_path=_universe(tmp_path),
        paper_mode=True, regime="PR1_CALM",
    )
    scanner.executor.execute_entry = AsyncMock(return_value=order_result or {
        "paper": True, "entry_status": "paper", "unwound": False,
        "entry_order_id": "PAPER-1", "sl_order_id": "PAPER-SL-1",
        "fill_price": 10.4,
    })

    def baseline(**kwargs):
        return {
            "accept": True, "ticker": kwargs["ticker"], "entry": 10.43,
            "stop_loss": 10.30, "target": 10.69, "shares": 5,
            "rsi_14": 55.0, "breakout_level": 10.35,
        }

    def shadow(**kwargs):
        if shadow_effect:
            return shadow_effect(**kwargs)
        return _shadow_row(kwargs)

    persistence = persist or AsyncMock(return_value=1)
    persist_order_counts = []

    async def persist_after_baseline(*args):
        persist_order_counts.append(scanner.executor.execute_entry.await_count)
        return await persistence(*args)

    with patch("penny_engine_breakout.evaluate_breakout_entry", side_effect=baseline), \
         patch("penny_scanner.evaluate_penny_shadows", side_effect=shadow) as shadow_mock, \
         patch("penny_scanner.persist_penny_shadow_results", side_effect=persist_after_baseline):
        summary = await scanner.scan_once(datetime(2026, 8, 10, 11, 0))
    return {
        "full_summary": summary,
        "db_path": str(tmp_path / "scan.db"),
        "summary": {key: summary[key] for key in ("accept", "reject", "error")},
        "quote_calls": kite.get_quote.await_count,
        "intraday_calls": kite.get_intraday.await_count,
        "historical_calls": kite.get_historical.await_count,
        "order_calls": scanner.executor.execute_entry.await_count,
        "shadow_calls": shadow_mock.call_args_list,
        "persist": persistence,
        "persist_order_counts": persist_order_counts,
    }


@pytest.mark.asyncio
async def test_paper_fill_creates_isolated_position_at_actual_fill_with_stop(tmp_path, monkeypatch):
    import aiosqlite
    result = await _scan(tmp_path, monkeypatch, False)
    summary = result["full_summary"]
    assert summary["order_attempt"] == summary["fill"] == 1
    assert summary["protected"] == summary["position"] == 1
    assert summary["failure"] == 0
    async with aiosqlite.connect(result["db_path"]) as db:
        row = await (await db.execute(
            "SELECT entry_price,source,sl_order_id,status FROM positions"
        )).fetchone()
        events = await (await db.execute(
            "SELECT event_type FROM penny_execution_events ORDER BY sequence"
        )).fetchall()
    assert row == (10.4, "PENNY_PAPER", "PAPER-SL-1", "OPEN")
    assert [item[0] for item in events] == [
        "CANDIDATE_ACCEPTED", "EXECUTION_RESULT", "POSITION_CREATED",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [
    {"paper": True, "entry_status": "paper", "unwound": False,
     "entry_order_id": "PAPER-1", "fill_price": 10.4, "sl_order_id": None},
    {"paper": False, "entry_status": "unprotected", "unwound": False,
     "entry_order_id": "LIVE-1", "fill_price": 10.4, "sl_order_id": None},
    {"paper": False, "entry_status": "unwound", "unwound": True,
     "entry_order_id": "LIVE-2", "fill_price": 10.4, "sl_order_id": None},
])
async def test_unprotected_unwound_or_missing_stop_never_becomes_position(
    tmp_path, monkeypatch, outcome,
):
    import aiosqlite
    result = await _scan(tmp_path, monkeypatch, False, order_result=outcome)
    assert result["full_summary"]["position"] == 0
    assert result["full_summary"]["failure"] == 1
    async with aiosqlite.connect(result["db_path"]) as db:
        count = (await (await db.execute("SELECT COUNT(*) FROM positions")).fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_repeated_scan_of_same_visible_bar_dedupes_attempt_and_position(tmp_path, monkeypatch):
    import aiosqlite
    first = await _scan(tmp_path, monkeypatch, False)
    second = await _scan(tmp_path, monkeypatch, False)
    assert first["full_summary"]["order_attempt"] == 1
    assert second["full_summary"]["order_attempt"] == 0
    async with aiosqlite.connect(first["db_path"]) as db:
        positions = (await (await db.execute(
            "SELECT COUNT(*) FROM positions WHERE source='PENNY_PAPER'"
        )).fetchone())[0]
        attempts = (await (await db.execute(
            "SELECT COUNT(DISTINCT attempt_id) FROM penny_execution_events"
        )).fetchone())[0]
    assert positions == attempts == 1


@pytest.mark.asyncio
async def test_restart_with_broker_progress_but_no_final_result_never_reenters(
    tmp_path, monkeypatch, caplog,
):
    from unittest.mock import AsyncMock, patch
    lifecycle = AsyncMock(return_value=("CANDIDATE_ACCEPTED", "ENTRY_SUBMITTED", "ENTRY_FILLED"))
    with patch("penny_scanner.attempt_event_types", lifecycle):
        result = await _scan(tmp_path, monkeypatch, False)
    assert result["order_calls"] == 0
    assert result["full_summary"]["order_attempt"] == 0
    assert result["full_summary"]["position"] == 0
    assert result["full_summary"]["failure"] == 1
    assert "reconciliation_UNRESOLVED" in caplog.text


@pytest.mark.asyncio
async def test_restart_with_protected_result_but_missing_position_flags_unresolved(
    tmp_path, monkeypatch, caplog,
):
    from unittest.mock import AsyncMock, patch
    lifecycle = AsyncMock(return_value=(
        "CANDIDATE_ACCEPTED", "ENTRY_FILLED", "SL_PLACED", "EXECUTION_RESULT",
    ))
    payload = AsyncMock(return_value={
        "entry_status": "paper", "sl_order_id": "PAPER-SL-CRASH",
        "unwound": False, "fill_price": 10.4,
    })
    with patch("penny_scanner.attempt_event_types", lifecycle), \
         patch("penny_scanner.attempt_event_payload", payload):
        result = await _scan(tmp_path, monkeypatch, False)
    assert result["order_calls"] == 0
    assert result["full_summary"]["position"] == 0
    assert result["full_summary"]["failure"] == 1
    assert "protected_fill_missing_local_position" in caplog.text


@pytest.mark.asyncio
async def test_restart_with_terminal_unfilled_result_dedupes_without_false_alarm(
    tmp_path, monkeypatch,
):
    from unittest.mock import AsyncMock, patch
    lifecycle = AsyncMock(return_value=("CANDIDATE_ACCEPTED", "EXECUTION_RESULT"))
    payload = AsyncMock(return_value={
        "entry_status": "rejected", "sl_order_id": None,
        "unwound": False, "fill_price": None,
    })
    with patch("penny_scanner.attempt_event_types", lifecycle), \
         patch("penny_scanner.attempt_event_payload", payload):
        result = await _scan(tmp_path, monkeypatch, False)
    assert result["order_calls"] == 0
    assert result["full_summary"]["failure"] == 0


@pytest.mark.asyncio
async def test_shadow_on_off_preserves_baseline_and_market_call_counts(tmp_path, monkeypatch):
    off = await _scan(tmp_path / "off", monkeypatch, False)
    on = await _scan(tmp_path / "on", monkeypatch, True)
    assert on["summary"] == off["summary"] == {"accept": 1, "reject": 0, "error": 0}
    assert (on["quote_calls"], on["intraday_calls"], on["historical_calls"]) == (1, 1, 1)
    assert (off["quote_calls"], off["intraday_calls"], off["historical_calls"]) == (1, 1, 1)
    assert on["order_calls"] == off["order_calls"] == 1
    assert len(on["shadow_calls"]) == 1
    assert len(off["shadow_calls"]) == 0
    on["persist"].assert_awaited_once()
    off["persist"].assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_failure_does_not_change_order_path(tmp_path, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("candidate failure")

    result = await _scan(tmp_path, monkeypatch, True, shadow_effect=fail)
    assert result["summary"] == {"accept": 1, "reject": 0, "error": 0}
    assert result["order_calls"] == 1
    result["persist"].assert_awaited_once_with(str(tmp_path / "scan.db"), [])


@pytest.mark.asyncio
async def test_slow_failing_persistence_runs_after_order_attempt(tmp_path, monkeypatch):
    persist = AsyncMock()

    async def persistence_failure(db_path, rows):
        await asyncio.sleep(0.02)
        raise RuntimeError("sqlite locked")

    persist.side_effect = persistence_failure
    result = await _scan(tmp_path, monkeypatch, True, persist=persist)
    assert result["persist_order_counts"] == [1]
    assert result["order_calls"] == 1
    assert result["summary"] == {"accept": 1, "reject": 0, "error": 0}
    persist.assert_awaited_once()
