from datetime import datetime, timezone

import pytest

from broker_reconciliation import broker_statement_report, import_broker_statement


@pytest.mark.asyncio
async def test_statement_import_is_idempotent_and_reconciles_post_cost_cash(db_path):
    payload = dict(account_id="owner", statement_id="2026-09-07", as_of=datetime(2026, 9, 7, tzinfo=timezone.utc), opening_cash=1000, closing_cash=1137,
                   entries=[{"entry_id":"deposit","entry_type":"DEPOSIT","amount":200}, {"entry_id":"trade","entry_type":"TRADE_REALIZED","amount":-40}, {"entry_id":"charge","entry_type":"CHARGE","amount":8}, {"entry_id":"ops","entry_type":"OPERATING_EXPENSE","amount":15}],
                   fills=[{"fill_id":"f1","order_id":"o1","status":"PARTIAL","quantity":2,"price":100,"fees":2}, {"fill_id":"f2","order_id":"o1","status":"FILLED","quantity":3,"price":101,"fees":3}, {"fill_id":"f3","order_id":"o2","status":"CANCELLED","quantity":0,"price":0,"fees":0}])
    assert await import_broker_statement(db_path, **payload)
    assert not await import_broker_statement(db_path, **payload)
    report = await broker_statement_report(db_path, account_id="owner")
    assert report["status"] == "MATCH" and report["net_trading_result"] == -40
    assert report["charges"] == 8 and report["operating_expenses"] == 15
    assert report["fills"] == {"CANCELLED": 1, "FILLED": 1, "PARTIAL": 1, "REJECTED": 0}


@pytest.mark.asyncio
async def test_statement_residual_stays_unresolved_and_conflicting_retry_is_rejected(db_path):
    payload = dict(account_id="owner", statement_id="bad", as_of=datetime(2026, 9, 7, tzinfo=timezone.utc), opening_cash=100, closing_cash=150, entries=[], fills=[])
    assert await import_broker_statement(db_path, **payload)
    assert (await broker_statement_report(db_path, account_id="owner"))["status"] == "UNRESOLVED"
    with pytest.raises(ValueError, match="conflicts"):
        await import_broker_statement(db_path, **{**payload, "closing_cash": 100})


@pytest.mark.asyncio
async def test_activity_surface_exposes_imported_statement_without_order_authority(db_path, monkeypatch):
    from config import settings
    from routes_commands import get_proactive_activity

    await import_broker_statement(
        db_path, account_id="owner", statement_id="surface", as_of=datetime(2026, 9, 7, tzinfo=timezone.utc),
        opening_cash=100, closing_cash=100, entries=[], fills=[],
    )
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    monkeypatch.setattr(settings, "BROKER_RECONCILIATION_ACCOUNT_ID", "owner")
    report = await get_proactive_activity(days=7)
    assert report["broker_statement"]["status"] == "MATCH"
    assert report["broker_statement"]["can_place_orders"] is False
