from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
import pytest

from broker_internal_reconciliation import broker_internal_reference_report
from broker_reconciliation import import_broker_statement
from fno_positions import init_fno_positions_db
from position_tracker import init_positions_db


async def _statement(db_path, *, statement_id="s1", as_of=None, fills=None):
    await import_broker_statement(
        db_path,
        account_id="owner",
        statement_id=statement_id,
        as_of=as_of or datetime(2026, 9, 19, tzinfo=timezone.utc),
        opening_cash=100.0,
        closing_cash=100.0,
        entries=[],
        fills=fills or [],
    )


def _fill(fill_id, order_id, status="FILLED", quantity=1, price=100, fees=1):
    return {"fill_id": fill_id, "order_id": order_id, "status": status,
            "quantity": quantity, "price": price, "fees": fees}


async def _books(db_path):
    await init_positions_db(db_path)
    await init_fno_positions_db(db_path)


async def _equity_ref(db_path, order_id, *, source="PENNY", shares=5):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO positions "
            "(ticker,exchange,entry_date,entry_price,shares,status,source,broker_entry_order_id) "
            "VALUES ('TCS','NSE','2026-09-19',100,?,'OPEN',?,?)",
            (shares, source, order_id),
        )
        await db.commit()


async def _fno_ref(db_path, order_id, *, source="FNO_LIVE", qty=5, role="entry"):
    column = "entry_order_id" if role == "entry" else "exit_order_id"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"INSERT INTO fno_positions (source,tradingsymbol,status,qty,{column}) "
            "VALUES (?, 'NIFTY26SEP25000CE', 'OPEN', ?, ?)",
            (source, qty, order_id),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_blank_or_mismatched_binding_fails_closed(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "o1")])
    for configured, reason in (("", "CONFIGURED_ACCOUNT_ID_MISSING"),
                               ("other", "CONFIGURED_ACCOUNT_ID_MISMATCH")):
        report = await broker_internal_reference_report(
            db, account_id="owner", configured_account_id=configured)
        assert report["status"] == "INSUFFICIENT_SCOPE"
        assert report["reason"] == reason
        assert report["executed_orders"][0]["state"] == "INSUFFICIENT_SCOPE"
        assert report["broker_reconciled"] is False
        assert report["authorization_effect"] == "NONE"


@pytest.mark.asyncio
async def test_missing_internal_table_coverage_cannot_claim_match(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "o1")])
    await init_positions_db(db)
    await _equity_ref(db, "o1")
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    assert report["status"] == "INSUFFICIENT_SCOPE"
    assert report["executed_orders"][0]["state"] == "INSUFFICIENT_SCOPE"
    assert {row["table"]: row["status"] for row in report["table_coverage"]} == {
        "positions": "AVAILABLE", "fno_positions": "MISSING_TABLE"}


@pytest.mark.asyncio
async def test_unique_live_equity_reference_matches_without_claiming_reconciliation(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[
        _fill("f1", "o1", "PARTIAL", 2, 100, 0.5),
        _fill("f2", "o1", "FILLED", 3, 101, 0.75),
        _fill("f3", "o2", "CANCELLED", 0, 0, 0),
    ])
    await _books(db)
    await _equity_ref(db, "o1", shares=2)  # mutable remaining shares are not compared
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    assert report["status"] == "MATCHED_REFERENCE"
    assert report["broker_reconciled"] is False
    order = report["executed_orders"][0]
    assert order["fill_ids"] == ["f1", "f2"]
    assert order["quantity"] == 5
    assert order["fill_count"] == 2
    assert order["quantity_check"] == "UNVERIFIED_MUTABLE_POSITION_QUANTITY"
    assert report["nonexecuted_orders"][0]["order_id"] == "o2"
    assert report["account_binding"]["account_attribution_verified"] is False
    assert len(report["evidence_sha256"]) == 64


@pytest.mark.asyncio
async def test_missing_reference_is_unresolved_even_when_cash_statement_matches(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "missing")])
    await _books(db)
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    assert report["status"] == "UNRESOLVED"
    assert report["executed_orders"][0]["reason"] == "INTERNAL_REFERENCE_MISSING"


@pytest.mark.asyncio
async def test_duplicate_reference_across_books_is_ambiguous(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "dup")])
    await _books(db)
    await _equity_ref(db, "dup")
    await _fno_ref(db, "dup")
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    order = report["executed_orders"][0]
    assert report["status"] == "UNRESOLVED"
    assert order["state"] == "AMBIGUOUS"
    assert order["reason"] == "MULTIPLE_INTERNAL_REFERENCES"
    assert len(order["matches"]) == 2


@pytest.mark.asyncio
async def test_paper_reference_cannot_satisfy_live_broker_fill(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "paper")])
    await _books(db)
    await _equity_ref(db, "paper", source="PENNY_PAPER")
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    assert report["status"] == "UNRESOLVED"
    assert report["executed_orders"][0]["reason"] == (
        "PAPER_REFERENCE_CANNOT_MATCH_BROKER_EXECUTION")


@pytest.mark.asyncio
async def test_fno_quantity_excess_is_unresolved(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "fno", quantity=6)])
    await _books(db)
    await _fno_ref(db, "fno", qty=5)
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    order = report["executed_orders"][0]
    assert order["reason"] == "BROKER_QUANTITY_EXCEEDS_INTERNAL"
    assert order["quantity_check"] == "EXCEEDS_RECORDED_POSITION_QUANTITY"


@pytest.mark.asyncio
async def test_explicit_statement_selection_does_not_silently_use_newest(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, statement_id="old", as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
                     fills=[_fill("f-old", "old-order")])
    await _statement(db, statement_id="new", as_of=datetime(2026, 9, 19, tzinfo=timezone.utc),
                     fills=[_fill("f-new", "new-order")])
    await _books(db)
    await _equity_ref(db, "old-order")
    old = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner", statement_id="old")
    newest = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    assert old["statement_id"] == "old" and old["status"] == "MATCHED_REFERENCE"
    assert newest["statement_id"] == "new" and newest["status"] == "UNRESOLVED"


@pytest.mark.asyncio
async def test_no_executed_fills_is_not_upgraded_to_match(tmp_path):
    db = str(tmp_path / "r.db")
    await _statement(db, fills=[_fill("f1", "o1", "REJECTED", 0, 0, 0)])
    await _books(db)
    report = await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")
    assert report["status"] == "INSUFFICIENT_SCOPE"
    assert report["reason"] == "NO_EXECUTED_BROKER_FILLS"
    assert report["executed_orders"] == []
    assert report["nonexecuted_orders"][0]["statuses"] == ["REJECTED"]


@pytest.mark.asyncio
async def test_missing_database_is_read_only_and_does_not_create_file(tmp_path):
    db = tmp_path / "missing.db"
    report = await broker_internal_reference_report(
        str(db), account_id="owner", configured_account_id="owner")
    assert report["reason"] == "DATABASE_UNAVAILABLE"
    assert not db.exists()
