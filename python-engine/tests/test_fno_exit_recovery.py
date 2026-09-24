"""Broker corroboration and atomic single-leg exit recovery."""
import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tests.test_atomic_settlement import fno_db, _insert_open_position
from fno_exit_recovery import RecoveryConflict, pending_exit_intents, resolve_exit_intent
from fno_positions import claim_exit_intent, init_fno_positions_db
from fno_positions import settle_position_close, closed_today
from fno_costs import calc_fno_costs

IST = ZoneInfo("Asia/Kolkata")


def broker(*, qty, filled, status="CANCELLED", price=110.0, symbol="NIFTY26SEP19500CE",
           account="USER01", order_id="EXIT01", now=None, net_qty=None):
    now = now or datetime.now(timezone.utc)
    stamp = (now + timedelta(seconds=1)).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    fill_stamp = now.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    order = {"order_id": order_id, "placed_by": account, "tradingsymbol": symbol,
             "exchange": "NFO", "product": "MIS", "transaction_type": "SELL",
             "tag": "FNO_LIVE", "status": status, "quantity": qty,
             "filled_quantity": filled, "order_timestamp": stamp}
    trades = ([{"trade_id": "T1", "order_id": order_id, "tradingsymbol": symbol,
                "exchange": "NFO", "product": "MIS", "transaction_type": "SELL",
                "quantity": filled, "average_price": price,
                "fill_timestamp": fill_stamp}] if filled else [])
    residual = qty - filled if net_qty is None else net_qty
    positions = {"net": [{"exchange": "NFO", "product": "MIS",
                          "tradingsymbol": symbol, "quantity": residual}] if residual else []}
    kite = AsyncMock()
    kite.orders_snapshot.return_value = [order]
    kite.order_trades.return_value = trades
    kite.get_broker_positions.return_value = positions
    return kite


async def claimed(db_path, *, qty=75):
    pid = await _insert_open_position(db_path, source="FNO_LIVE", qty=qty)
    assert await claim_exit_intent(db_path, pid, "FNO_LIVE")
    intent = (await pending_exit_intents(db_path))[0]
    return pid, intent["created_at"]


async def resolve(db_path, kite, pid, created, *, now=None, order_id="EXIT01"):
    return await resolve_exit_intent(
        db_path, kite, position_id=pid, source="FNO_LIVE",
        expected_created_at=created, account_id="USER01", order_id=order_id,
        operator="ops-reviewer", now=now,
    )


@pytest.mark.asyncio
async def test_terminal_zero_fill_releases_intent_with_audit_no_ledger(fno_db):
    pid, created = await claimed(fno_db)
    out = await resolve(fno_db, broker(qty=75, filled=0), pid, created)
    assert (out["filled_qty"], out["remaining_qty"], out["ledger_id"]) == (0, 75, None)
    assert await pending_exit_intents(fno_db) == []
    with closing(sqlite3.connect(fno_db)) as db:
        assert db.execute("SELECT status,qty,settlement_generation FROM fno_positions WHERE id=?", (pid,)).fetchone() == ("OPEN", 75, 0)
        assert db.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_position:{pid}",)).fetchone()[0] == 0
        assert db.execute("SELECT filled_qty,remaining_qty FROM fno_exit_recoveries").fetchone() == (0, 75)
    with pytest.raises(RecoveryConflict):
        await resolve(fno_db, broker(qty=75, filled=0), pid, created)


@pytest.mark.asyncio
async def test_recovered_intent_requires_new_exit_evaluation(fno_db):
    pid, created = await claimed(fno_db)
    stale_tick = datetime.now(timezone.utc)
    await resolve(fno_db, broker(qty=75, filled=0), pid, created)
    assert not await claim_exit_intent(
        fno_db, pid, "FNO_LIVE", evaluation_started_at=stale_tick,
    )
    assert await claim_exit_intent(
        fno_db, pid, "FNO_LIVE", evaluation_started_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_terminal_partial_fill_realizes_once_and_preserves_residual(fno_db):
    pid, created = await claimed(fno_db, qty=150)
    out = await resolve(fno_db, broker(qty=150, filled=75), pid, created)
    assert (out["filled_qty"], out["remaining_qty"], out["settlement_generation"]) == (75, 75, 1)
    with closing(sqlite3.connect(fno_db)) as db:
        assert db.execute("SELECT status,qty,lots,settlement_generation FROM fno_positions WHERE id=?", (pid,)).fetchone() == ("OPEN", 75, 1, 1)
        assert db.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_position:{pid}",)).fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM fno_exit_recoveries").fetchone()[0] == 1
    assert await pending_exit_intents(fno_db) == []
    with pytest.raises(RecoveryConflict):
        await resolve(fno_db, broker(qty=150, filled=75), pid, created)


@pytest.mark.asyncio
async def test_partial_then_final_close_reports_total_economics_and_scaled_risk(fno_db):
    pid, created = await claimed(fno_db, qty=150)
    await resolve(fno_db, broker(qty=150, filled=75), pid, created)
    second_fill = 90.0
    gross = (second_fill - 100.0) * 75
    costs = calc_fno_costs(100.0, second_fill, 75)
    await settle_position_close(
        fno_db, pid, source="FNO_LIVE", ticker="NIFTY26SEP19500CE",
        exit_time_ist=datetime.now(IST), exit_premium=second_fill,
        exit_underlying=19500.0, exit_reason="hard_flat_1510",
        gross_pnl=gross, costs=costs, pnl=gross - costs,
        r_multiple=-0.5, exit_order_id="EXIT02", settlement_generation=2,
    )
    with closing(sqlite3.connect(fno_db)) as db:
        row = db.execute("SELECT pnl,gross_pnl,costs,max_loss_rupees,initial_max_loss_rupees FROM fno_positions WHERE id=?", (pid,)).fetchone()
        ledger = db.execute("SELECT SUM(pnl),COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_position:{pid}",)).fetchone()
    assert row[0] == pytest.approx(ledger[0])
    assert row[1] - row[2] == pytest.approx(row[0])
    assert row[3] == 750.0 and row[4] == 1500.0
    assert ledger[1] == 2
    report = await closed_today(fno_db, "FNO_LIVE", datetime.now(IST).date().isoformat())
    assert report[0]["pnl"] == pytest.approx(ledger[0])
    assert report[0]["lots"] == 2


@pytest.mark.asyncio
async def test_recovery_retains_verifiable_broker_snapshot(fno_db):
    import hashlib
    pid, created = await claimed(fno_db)
    await resolve(fno_db, broker(qty=75, filled=0), pid, created)
    with closing(sqlite3.connect(fno_db)) as db:
        evidence, digest = db.execute("SELECT broker_evidence_json,broker_evidence_sha256 FROM fno_exit_recoveries").fetchone()
    assert hashlib.sha256(evidence.encode()).hexdigest() == digest
    assert '"order_id":"EXIT01"' in evidence


@pytest.mark.asyncio
async def test_partial_loss_reaches_intraday_kill_switch(fno_db):
    from fno_risk import kill_switch_status
    pid, created = await claimed(fno_db, qty=150)
    await resolve(fno_db, broker(qty=150, filled=75, price=10.0), pid, created)
    reasons = await kill_switch_status(fno_db, "FNO_LIVE", 100000.0, datetime.now(IST).date())
    assert any(reason.startswith("daily_loss_halt") for reason in reasons)


@pytest.mark.asyncio
async def test_kill_switch_attributes_partial_loss_to_its_realized_ist_day(fno_db):
    from fno_risk import kill_switch_status
    pid, created = await claimed(fno_db, qty=150)
    await resolve(fno_db, broker(qty=150, filled=75, price=10.0), pid, created)
    yesterday = datetime.now(IST).date() - timedelta(days=1)
    today = datetime.now(IST).date()
    with closing(sqlite3.connect(fno_db)) as db:
        db.execute("UPDATE bankroll_ledger SET timestamp=? WHERE origin_ref=? AND settlement_generation=1",
                   (datetime.combine(yesterday, datetime.min.time(), IST).replace(hour=14).isoformat(), f"fno_position:{pid}"))
        db.commit()
    assert any(r.startswith("daily_loss_halt") for r in await kill_switch_status(fno_db, "FNO_LIVE", 100000.0, yesterday))
    final_price = 120.0
    gross = (final_price - 100.0) * 75
    costs = calc_fno_costs(100.0, final_price, 75)
    await settle_position_close(
        fno_db, pid, source="FNO_LIVE", ticker="NIFTY26SEP19500CE",
        exit_time_ist=datetime.now(IST), exit_premium=final_price,
        exit_underlying=19500.0, exit_reason="hard_flat_1510",
        gross_pnl=gross, costs=costs, pnl=gross - costs,
        r_multiple=0.5, exit_order_id="EXIT02", settlement_generation=2,
    )
    assert not any(r.startswith("daily_loss_halt") for r in await kill_switch_status(fno_db, "FNO_LIVE", 10000.0, today))


@pytest.mark.asyncio
async def test_terminal_full_fill_closes_with_one_ledger_row(fno_db):
    pid, created = await claimed(fno_db)
    out = await resolve(fno_db, broker(qty=75, filled=75, status="COMPLETE"), pid, created)
    assert out["remaining_qty"] == 0
    with closing(sqlite3.connect(fno_db)) as db:
        assert db.execute("SELECT status,qty,settlement_generation FROM fno_positions WHERE id=?", (pid,)).fetchone() == ("CLOSED", 0, 1)
        assert db.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_position:{pid}",)).fetchone()[0] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["open", "wrong_account", "wrong_symbol", "trade_mismatch", "net_mismatch", "broker_unavailable", "other_order", "old_intent"])
async def test_ambiguous_or_mismatched_broker_evidence_keeps_intent(fno_db, fault):
    pid, created = await claimed(fno_db)
    kite = broker(qty=75, filled=0)
    if fault == "open":
        kite.orders_snapshot.return_value[0]["status"] = "OPEN"
    elif fault == "wrong_account":
        kite.orders_snapshot.return_value[0]["placed_by"] = "OTHER"
    elif fault == "wrong_symbol":
        kite.orders_snapshot.return_value[0]["tradingsymbol"] = "OTHER"
    elif fault == "trade_mismatch":
        kite.orders_snapshot.return_value[0]["filled_quantity"] = 75
    elif fault == "net_mismatch":
        kite.get_broker_positions.return_value["net"][0]["quantity"] = 0
    elif fault == "other_order":
        other = dict(kite.orders_snapshot.return_value[0])
        other["order_id"] = "OTHER_EXIT"
        other["transaction_type"] = "BUY"
        kite.orders_snapshot.return_value.append(other)
    elif fault == "old_intent":
        with closing(sqlite3.connect(fno_db)) as db:
            db.execute("UPDATE fno_exit_intents SET created_at=? WHERE position_id=?", ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), pid))
            db.commit()
        created = (await pending_exit_intents(fno_db))[0]["created_at"]
    else:
        kite.order_trades.return_value = None
    with pytest.raises(RecoveryConflict):
        await resolve(fno_db, kite, pid, created)
    assert len(await pending_exit_intents(fno_db)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("filled", [0, 75])
async def test_concurrent_and_restart_resolution_has_one_winner(fno_db, filled):
    qty = 150 if filled else 75
    pid, created = await claimed(fno_db, qty=qty)
    results = await asyncio.gather(
        resolve(fno_db, broker(qty=qty, filled=filled), pid, created),
        resolve(fno_db, broker(qty=qty, filled=filled), pid, created),
        return_exceptions=True,
    )
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, RecoveryConflict) for item in results) == 1
    with closing(sqlite3.connect(fno_db)) as db:
        assert db.execute("SELECT COUNT(*) FROM fno_exit_recoveries").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_position:{pid}",)).fetchone()[0] == (1 if filled else 0)
    # A fresh process reads the durable state and cannot replay the old claim.
    with pytest.raises(RecoveryConflict):
        await resolve(fno_db, broker(qty=qty, filled=filled), pid, created)


@pytest.mark.asyncio
async def test_recovery_routes_require_internal_auth_and_operator_confirmation(fno_db, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    import main
    from config import settings
    pid, created = await claimed(fno_db)
    monkeypatch.setattr(settings, "DB_PATH", fno_db)
    monkeypatch.setattr(main, "kite", broker(qty=75, filled=0))
    payload = {"source": "FNO_LIVE", "expected_created_at": created,
               "account_id": "USER01", "order_id": "EXIT01",
               "operator": "ops-reviewer", "confirm": "RECONCILE_VERIFIED_BROKER_EXIT"}
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        path = f"/ops/fno-exit-intents/{pid}/resolve"
        assert (await client.get("/ops/fno-exit-intents")).status_code == 403
        assert (await client.post(path, json=payload)).status_code == 403
        headers = {"X-Internal-Secret": settings.INTERNAL_API_SECRET}
        assert (await client.get("/ops/fno-exit-intents", headers=headers)).json()["intents"][0]["position_id"] == pid
        bad = dict(payload, confirm="yes")
        assert (await client.post(path, json=bad, headers=headers)).status_code == 422
        response = await client.post(path, json=payload, headers=headers)
        assert response.status_code == 200, response.text
    assert await pending_exit_intents(fno_db) == []


@pytest.mark.asyncio
async def test_recovery_audit_write_failure_rolls_back_partial_settlement(fno_db):
    pid, created = await claimed(fno_db, qty=150)
    with closing(sqlite3.connect(fno_db)) as db:
        db.execute("CREATE TRIGGER block_recovery BEFORE INSERT ON fno_exit_recoveries BEGIN SELECT RAISE(ABORT,'audit unavailable'); END")
        db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        await resolve(fno_db, broker(qty=150, filled=75), pid, created)
    with closing(sqlite3.connect(fno_db)) as db:
        assert db.execute("SELECT status,qty,settlement_generation FROM fno_positions WHERE id=?", (pid,)).fetchone() == ("OPEN", 150, 0)
        assert db.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_position:{pid}",)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM fno_exit_intents WHERE position_id=?", (pid,)).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_legacy_position_migration_backfills_original_risk_once(tmp_path):
    path = str(tmp_path / "legacy.sqlite3")
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE fno_positions(id INTEGER PRIMARY KEY,source TEXT,status TEXT,qty INTEGER,lots INTEGER,max_loss_rupees REAL)")
        db.execute("INSERT INTO fno_positions VALUES (1,'FNO_LIVE','OPEN',150,2,3000.0)")
        db.commit()
    await init_fno_positions_db(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT initial_qty,initial_lots,initial_max_loss_rupees FROM fno_positions WHERE id=1").fetchone() == (150, 2, 3000.0)
        db.execute("UPDATE fno_positions SET qty=75,lots=1,max_loss_rupees=1500.0 WHERE id=1")
        db.commit()
    await init_fno_positions_db(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT initial_qty,initial_lots,initial_max_loss_rupees FROM fno_positions WHERE id=1").fetchone() == (150, 2, 3000.0)


@pytest.mark.asyncio
async def test_intent_inspection_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(RecoveryConflict):
        await pending_exit_intents(str(missing))
    assert not missing.exists()
