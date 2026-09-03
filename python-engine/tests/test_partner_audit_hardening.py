"""Regression coverage for the 2026-09-03 partial-day audit follow-ups."""

from datetime import datetime
import asyncio

import aiosqlite
import pytest
import pytz

import kite_client
import partner_orchestrator as po
from config import settings


IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 3, 15, 40))


@pytest.mark.asyncio
async def test_suppressed_partner_event_is_counted_without_send_or_row(
    tmp_path, monkeypatch,
):
    db_path = str(tmp_path / "cache.db")
    await po.init_partner_db(db_path)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_SUPPRESS_ANALYTICS", True)

    async def must_not_send(*args, **kwargs):
        raise AssertionError("suppressed analytics event reached Telegram")

    monkeypatch.setattr(po, "send_partner", must_not_send)
    metrics = {}
    result = await po._send_event(
        db_path, "pcr_shift", "NIFTY", "diagnostic", NOW, metrics=metrics,
    )

    assert result == "suppressed"
    assert metrics == {"events_considered": 1, "suppressed": 1}
    async with aiosqlite.connect(db_path) as db:
        assert await (await db.execute("SELECT COUNT(*) FROM partner_messages")).fetchone() == (0,)


@pytest.mark.asyncio
async def test_eod_non_momentum_position_audit_is_observational(tmp_path, monkeypatch):
    db_path = str(tmp_path / "cache.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE positions (ticker TEXT, source TEXT, product_type TEXT, "
            "entry_date TEXT, shares INTEGER, status TEXT)"
        )
        await db.execute(
            "INSERT INTO positions VALUES ('AKI', 'EDGE_PAPER', 'CNC', ?, 5207, 'OPEN')",
            (NOW.isoformat(),),
        )
        await db.commit()

    warnings = []
    monkeypatch.setattr(po.logger, "warning", lambda event, **kw: warnings.append((event, kw)))
    await po._log_non_momentum_open_positions(db_path, NOW)

    assert warnings[0][0] == "non_momentum_positions_open_at_eod"
    assert warnings[0][1]["count"] == 1
    assert warnings[0][1]["positions"][0]["ticker"] == "AKI"
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT status, shares FROM positions")).fetchone()
    assert row == ("OPEN", 5207)


@pytest.mark.asyncio
async def test_kite_cache_connections_wait_for_long_writer_bursts(tmp_path):
    client = kite_client.KiteClient(str(tmp_path / "cache.db"))
    try:
        async with client._cache_db() as db:
            busy_timeout = (await (await db.execute("PRAGMA busy_timeout")).fetchone())[0]
        assert busy_timeout == int(kite_client.SQLITE_OPERATION_TIMEOUT_SEC * 1000)
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_analytics_summary_distinguishes_no_event_from_suppressed(
    monkeypatch,
):
    """A scheduled empty tick is observable, without inventing a message."""
    import main

    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_SUPPRESS_DIRECTIONAL", True)
    monkeypatch.setattr(po, "_gates_open", lambda *args: _true())
    monkeypatch.setattr(po, "analytics_underlyings", lambda: [])
    monkeypatch.setattr(main, "state_lock", asyncio.Lock())
    monkeypatch.setattr(main, "_fno_regime_str", lambda: "REGIME_1_NORMAL")

    async def _no_halt(*args, **kwargs):
        return False, []

    monkeypatch.setattr(main, "check_circuit_breakers", _no_halt)
    info = []
    monkeypatch.setattr(po.logger, "info", lambda *args, **kw: info.append((args[0], kw)))
    await po.partner_analytics_tick(NOW)

    summaries = [kw for event, kw in info if event == "partner_analytics_tick_summary"]
    assert len(summaries) == 1
    assert summaries[0]["underlyings_seen"] == 0
    assert summaries[0]["events_considered"] == 0
    assert summaries[0]["suppressed"] == 0
    assert summaries[0]["analytics_suppression_enabled"] is True


async def _true():
    return True
