from __future__ import annotations

from datetime import datetime, timezone

import pytest

from broker_internal_reconciliation import broker_internal_reference_report
from broker_reconciliation import import_broker_statement
from discrepancies import (
    DiscrepancyCategory,
    list_discrepancies,
    record_current_state,
    record_from_broker_internal_report,
)
from fno_positions import init_fno_positions_db
from position_tracker import init_positions_db


async def _seed_missing_order(db: str) -> dict:
    await import_broker_statement(
        db, account_id="owner", statement_id="s1",
        as_of=datetime(2026, 9, 19, tzinfo=timezone.utc),
        opening_cash=100, closing_cash=100, entries=[],
        fills=[{"fill_id": "f1", "order_id": "missing", "status": "FILLED",
                "quantity": 1, "price": 100, "fees": 1}],
    )
    await init_positions_db(db)
    await init_fno_positions_db(db)
    return await broker_internal_reference_report(
        db, account_id="owner", configured_account_id="owner")


@pytest.mark.asyncio
async def test_unresolved_broker_order_records_idempotently_with_unscoped_attribution(tmp_path):
    db = str(tmp_path / "r.db")
    report = await _seed_missing_order(db)
    first = await record_from_broker_internal_report(db, report=report, actor="test")
    second = await record_from_broker_internal_report(db, report=report, actor="test")
    assert first == second and len(first) == 1
    rows = await list_discrepancies(
        db, category=DiscrepancyCategory.BROKER_EXECUTED_ORDER_UNRESOLVED)
    assert len(rows) == 1
    row = rows[0]
    assert row.account_id == "owner"
    assert row.account_attribution == "OPERATOR_DECLARED_UNSCOPED_INTERNAL_BOOKS"
    assert ("broker_statement_fills", "owner:s1:f1") in row.evidence_refs


@pytest.mark.asyncio
async def test_cash_match_does_not_suppress_cross_book_discrepancy(tmp_path):
    db = str(tmp_path / "r.db")
    report = await _seed_missing_order(db)
    result = await record_current_state(
        db, account_id="owner", actor="test", broker_internal_report=report)
    assert result["broker"] == []  # broker cash arithmetic is MATCH
    assert len(result["broker_internal"]) == 1
    rows = await list_discrepancies(db)
    assert DiscrepancyCategory.BROKER_EXECUTED_ORDER_UNRESOLVED in {
        row.category for row in rows}


@pytest.mark.asyncio
async def test_ambiguous_order_uses_distinct_category(tmp_path):
    db = str(tmp_path / "r.db")
    report = await _seed_missing_order(db)
    order = report["executed_orders"][0]
    order["state"] = "AMBIGUOUS"
    order["reason"] = "MULTIPLE_INTERNAL_REFERENCES"
    import hashlib, json
    body = {key: value for key, value in report.items() if key != "evidence_sha256"}
    report["evidence_sha256"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    await record_from_broker_internal_report(db, report=report, actor="test")
    rows = await list_discrepancies(
        db, category=DiscrepancyCategory.BROKER_ORDER_REFERENCE_AMBIGUOUS)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_tampered_report_is_rejected(tmp_path):
    db = str(tmp_path / "r.db")
    report = await _seed_missing_order(db)
    report["reason"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        await record_from_broker_internal_report(db, report=report)


@pytest.mark.asyncio
async def test_rehashed_authority_escalation_is_rejected(tmp_path):
    db = str(tmp_path / "r.db")
    report = await _seed_missing_order(db)
    report["can_place_orders"] = True
    import hashlib, json
    body = {key: value for key, value in report.items() if key != "evidence_sha256"}
    report["evidence_sha256"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    with pytest.raises(ValueError, match="authority contract"):
        await record_from_broker_internal_report(db, report=report)
