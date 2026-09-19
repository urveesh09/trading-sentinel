"""Read-only broker-fill to internal order-reference verification.

This is deliberately narrower than economic reconciliation.  It proves only
whether executed order IDs in one imported broker statement have a unique,
supported live reference in Sentinel's retained position books.  Internal
books are not account-scoped, so even a successful result is never presented
as broker reconciliation or execution authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import aiosqlite


REPORT_FORMAT = "broker_internal_reference_report_v1"
_EXECUTED_STATUSES = frozenset({"FILLED", "PARTIAL"})
_NONEXECUTED_STATUSES = frozenset({"CANCELLED", "REJECTED"})
_POSITION_LIVE_SOURCES = frozenset({"MOMENTUM", "PENNY", "EDGE_LIVE", "MANUAL", "SYSTEM"})
_POSITION_PAPER_SOURCES = frozenset({"MOMENTUM_PAPER", "PENNY_PAPER", "EDGE_PAPER"})
_POSITIONS_COLUMNS = frozenset({
    "source", "status", "ticker", "shares", "broker_entry_order_id",
})
_FNO_COLUMNS = frozenset({
    "id", "source", "status", "tradingsymbol", "qty",
    "entry_order_id", "exit_order_id",
})


def _sha(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finish(report: dict[str, Any]) -> dict[str, Any]:
    return {**report, "evidence_sha256": _sha(report)}


def _base_report(*, account_id: str, configured_account_id: str) -> dict[str, Any]:
    return {
        "format": REPORT_FORMAT,
        "account_id": account_id,
        "configured_account_id": configured_account_id,
        "status": "INSUFFICIENT_SCOPE",
        "reason": "NOT_EVALUATED",
        "statement_id": None,
        "statement_as_of": None,
        "account_binding": {
            "status": "INSUFFICIENT_SCOPE",
            "basis": "OPERATOR_DECLARED_ACCOUNT_ID",
            "internal_books_account_scoped": False,
            "account_attribution_verified": False,
        },
        "coverage_direction": "BROKER_EXECUTED_TO_INTERNAL_REFERENCE_ONLY",
        "table_coverage": [],
        "executed_orders": [],
        "nonexecuted_orders": [],
        "counts": {
            "executed_orders": 0,
            "matched_references": 0,
            "unresolved": 0,
            "ambiguous": 0,
            "insufficient_scope": 0,
        },
        "limitations": [
            "Internal position tables do not retain broker account_id.",
            "Statement period bounds are unavailable, so inverse completeness is not evaluated.",
            "A matched order reference does not prove price, fee, cash, or P&L agreement.",
        ],
        "broker_reconciled": False,
        "can_place_orders": False,
        "can_grow_live_capital": False,
        "authorization_effect": "NONE",
    }


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str] | None:
    exists = await (await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
    )).fetchone()
    if exists is None:
        return None
    rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    return {str(row[1]) for row in rows}


def _scope_for_source(table: str, source: str) -> str:
    normalized = source.strip().upper()
    if table == "fno_positions":
        if normalized == "FNO_LIVE":
            return "LIVE"
        if normalized == "FNO_PAPER":
            return "PAPER"
        return "UNSUPPORTED"
    if normalized in _POSITION_LIVE_SOURCES:
        return "LIVE"
    if normalized in _POSITION_PAPER_SOURCES or normalized.endswith("_PAPER"):
        return "PAPER"
    return "UNSUPPORTED"


async def _load_internal_references(
    db: aiosqlite.Connection,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    references: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    position_columns = await _table_columns(db, "positions")
    if position_columns is None:
        coverage.append({"table": "positions", "status": "MISSING_TABLE", "missing_columns": []})
    else:
        missing = sorted(_POSITIONS_COLUMNS - position_columns)
        if missing:
            coverage.append({"table": "positions", "status": "MISSING_COLUMNS", "missing_columns": missing})
        else:
            coverage.append({"table": "positions", "status": "AVAILABLE", "missing_columns": []})
            rows = await (await db.execute(
                "SELECT rowid,source,status,ticker,shares,broker_entry_order_id "
                "FROM positions WHERE broker_entry_order_id IS NOT NULL "
                "AND TRIM(broker_entry_order_id)<>'' ORDER BY rowid",
            )).fetchall()
            for row in rows:
                source = str(row[1] or "")
                references.append({
                    "order_id": str(row[5]).strip(),
                    "table": "positions",
                    "row_id": str(row[0]),
                    "role": "ENTRY",
                    "source": source,
                    "execution_scope": _scope_for_source("positions", source),
                    "status": str(row[2] or ""),
                    "symbol": str(row[3] or ""),
                    "internal_quantity": row[4],
                    "quantity_semantics": "MUTABLE_REMAINING_SHARES_UNVERIFIED",
                })

    fno_columns = await _table_columns(db, "fno_positions")
    if fno_columns is None:
        coverage.append({"table": "fno_positions", "status": "MISSING_TABLE", "missing_columns": []})
    else:
        missing = sorted(_FNO_COLUMNS - fno_columns)
        if missing:
            coverage.append({"table": "fno_positions", "status": "MISSING_COLUMNS", "missing_columns": missing})
        else:
            coverage.append({"table": "fno_positions", "status": "AVAILABLE", "missing_columns": []})
            rows = await (await db.execute(
                "SELECT id,source,status,tradingsymbol,qty,entry_order_id,exit_order_id "
                "FROM fno_positions ORDER BY id",
            )).fetchall()
            for row in rows:
                source = str(row[1] or "")
                common = {
                    "table": "fno_positions",
                    "row_id": str(row[0]),
                    "source": source,
                    "execution_scope": _scope_for_source("fno_positions", source),
                    "status": str(row[2] or ""),
                    "symbol": str(row[3] or ""),
                    "internal_quantity": row[4],
                    "quantity_semantics": "IMMUTABLE_POSITION_UNITS",
                }
                for role, raw_order_id in (("ENTRY", row[5]), ("EXIT", row[6])):
                    order_id = str(raw_order_id or "").strip()
                    if order_id:
                        references.append({**common, "order_id": order_id, "role": role})

    references.sort(key=lambda row: (
        row["order_id"], row["table"], row["row_id"], row["role"],
    ))
    complete = all(row["status"] == "AVAILABLE" for row in coverage)
    return references, coverage, complete


def _aggregate_fills(rows: list[aiosqlite.Row]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    executed: dict[str, dict[str, Any]] = {}
    nonexecuted: dict[str, dict[str, Any]] = {}
    for row in rows:
        fill_id = str(row[0])
        order_id = str(row[1])
        status = str(row[2]).upper()
        quantity, price, fees = float(row[3]), float(row[4]), float(row[5])
        target = executed if status in _EXECUTED_STATUSES else nonexecuted
        if status not in _EXECUTED_STATUSES | _NONEXECUTED_STATUSES:
            continue
        bucket = target.setdefault(order_id, {
            "order_id": order_id,
            "fill_ids": [],
            "statuses": [],
            "fill_count": 0,
            "quantity": 0.0,
            "gross_value": 0.0,
            "fees": 0.0,
        })
        bucket["fill_ids"].append(fill_id)
        bucket["statuses"].append(status)
        bucket["fill_count"] += 1
        bucket["quantity"] += quantity
        bucket["gross_value"] += quantity * price
        bucket["fees"] += fees
    for buckets in (executed, nonexecuted):
        for bucket in buckets.values():
            bucket["fill_ids"].sort()
            bucket["statuses"] = sorted(set(bucket["statuses"]))
            bucket["quantity"] = round(float(bucket["quantity"]), 8)
            bucket["gross_value"] = round(float(bucket["gross_value"]), 8)
            bucket["fees"] = round(float(bucket["fees"]), 8)
    return ([executed[key] for key in sorted(executed)],
            [nonexecuted[key] for key in sorted(nonexecuted)])


def _evaluate_order(
    broker_order: dict[str, Any], *, references: list[dict[str, Any]],
    complete_coverage: bool,
) -> dict[str, Any]:
    matches = [row for row in references if row["order_id"] == broker_order["order_id"]]
    result = {**broker_order, "state": "UNRESOLVED", "reason": "INTERNAL_REFERENCE_MISSING",
              "matches": matches, "quantity_check": "UNAVAILABLE"}
    if len(matches) > 1:
        result.update(state="AMBIGUOUS", reason="MULTIPLE_INTERNAL_REFERENCES")
        return result
    if not matches:
        if not complete_coverage:
            result.update(state="INSUFFICIENT_SCOPE", reason="INTERNAL_TABLE_COVERAGE_INCOMPLETE")
        return result
    match = matches[0]
    if match["execution_scope"] == "PAPER":
        result.update(state="UNRESOLVED", reason="PAPER_REFERENCE_CANNOT_MATCH_BROKER_EXECUTION")
        return result
    if match["execution_scope"] != "LIVE":
        result.update(state="UNRESOLVED", reason="UNSUPPORTED_INTERNAL_SOURCE")
        return result
    if match["quantity_semantics"] == "IMMUTABLE_POSITION_UNITS":
        quantity = match.get("internal_quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or float(quantity) <= 0:
            result["quantity_check"] = "INTERNAL_QUANTITY_UNAVAILABLE"
        elif float(broker_order["quantity"]) > float(quantity):
            result.update(
                state="UNRESOLVED", reason="BROKER_QUANTITY_EXCEEDS_INTERNAL",
                quantity_check="EXCEEDS_RECORDED_POSITION_QUANTITY",
            )
            return result
        else:
            result["quantity_check"] = "WITHIN_RECORDED_POSITION_QUANTITY"
    else:
        result["quantity_check"] = "UNVERIFIED_MUTABLE_POSITION_QUANTITY"
    if not complete_coverage:
        result.update(state="INSUFFICIENT_SCOPE", reason="INTERNAL_TABLE_COVERAGE_INCOMPLETE")
    else:
        result.update(state="MATCHED_REFERENCE", reason="UNIQUE_SUPPORTED_LIVE_REFERENCE")
    return result


async def broker_internal_reference_report(
    db_path: str, *, account_id: str, configured_account_id: str,
    statement_id: str | None = None,
) -> dict[str, Any]:
    """Verify broker-executed order references against retained live books.

    The function performs SELECT/PRAGMA reads only.  ``configured_account_id``
    is required to equal the statement account, but this remains an operator
    declaration because the internal position rows have no account column.
    """
    account = str(account_id).strip()
    configured = str(configured_account_id or "").strip()
    if not account:
        raise ValueError("account_id must be a non-empty string")
    requested_statement = str(statement_id or "").strip() or None
    report = _base_report(account_id=account, configured_account_id=configured)
    if not Path(db_path).exists():
        report["reason"] = "DATABASE_UNAVAILABLE"
        return _finish(report)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA query_only=ON")
        broker_columns = await _table_columns(db, "broker_statement_imports")
        fill_columns = await _table_columns(db, "broker_statement_fills")
        required_imports = {"account_id", "statement_id", "as_of"}
        required_fills = {"account_id", "statement_id", "fill_id", "order_id", "status", "quantity", "price", "fees"}
        if broker_columns is None or fill_columns is None:
            report["reason"] = "BROKER_STATEMENT_SCHEMA_UNAVAILABLE"
            return _finish(report)
        if not required_imports <= broker_columns or not required_fills <= fill_columns:
            report["reason"] = "BROKER_STATEMENT_SCHEMA_INCOMPATIBLE"
            return _finish(report)

        if requested_statement is None:
            statement = await (await db.execute(
                "SELECT statement_id,as_of FROM broker_statement_imports "
                "WHERE account_id=? ORDER BY as_of DESC,statement_id DESC LIMIT 1",
                (account,),
            )).fetchone()
        else:
            statement = await (await db.execute(
                "SELECT statement_id,as_of FROM broker_statement_imports "
                "WHERE account_id=? AND statement_id=?",
                (account, requested_statement),
            )).fetchone()
        if statement is None:
            report["reason"] = "BROKER_STATEMENT_UNAVAILABLE"
            return _finish(report)
        report["statement_id"], report["statement_as_of"] = str(statement[0]), str(statement[1])
        fill_rows = await (await db.execute(
            "SELECT fill_id,order_id,status,quantity,price,fees "
            "FROM broker_statement_fills WHERE account_id=? AND statement_id=? "
            "ORDER BY fill_id",
            (account, report["statement_id"]),
        )).fetchall()
        executed, nonexecuted = _aggregate_fills(fill_rows)
        report["nonexecuted_orders"] = nonexecuted

        if not configured or configured != account:
            report["reason"] = ("CONFIGURED_ACCOUNT_ID_MISSING" if not configured
                                else "CONFIGURED_ACCOUNT_ID_MISMATCH")
            report["table_coverage"] = [
                {"table": "positions", "status": "NOT_EVALUATED_ACCOUNT_BINDING", "missing_columns": []},
                {"table": "fno_positions", "status": "NOT_EVALUATED_ACCOUNT_BINDING", "missing_columns": []},
            ]
            report["executed_orders"] = [
                {**row, "state": "INSUFFICIENT_SCOPE", "reason": report["reason"],
                 "matches": [], "quantity_check": "UNAVAILABLE"}
                for row in executed
            ]
        else:
            report["account_binding"]["status"] = "OPERATOR_DECLARED_MATCH"
            references, coverage, complete = await _load_internal_references(db)
            report["table_coverage"] = coverage
            report["executed_orders"] = [
                _evaluate_order(row, references=references, complete_coverage=complete)
                for row in executed
            ]

    if not report["executed_orders"]:
        report["status"] = "INSUFFICIENT_SCOPE"
        if report["reason"] == "NOT_EVALUATED":
            report["reason"] = "NO_EXECUTED_BROKER_FILLS"
    else:
        states = {row["state"] for row in report["executed_orders"]}
        if states & {"UNRESOLVED", "AMBIGUOUS"}:
            report.update(status="UNRESOLVED", reason="BROKER_ORDER_REFERENCE_ISSUES")
        elif "INSUFFICIENT_SCOPE" in states:
            if report["reason"] == "NOT_EVALUATED":
                report["reason"] = "INTERNAL_REFERENCE_SCOPE_INCOMPLETE"
            report["status"] = "INSUFFICIENT_SCOPE"
        else:
            report.update(status="MATCHED_REFERENCE", reason="ALL_EXECUTED_ORDERS_HAVE_UNIQUE_SUPPORTED_REFERENCES")
    report["counts"] = {
        "executed_orders": len(report["executed_orders"]),
        "matched_references": sum(row["state"] == "MATCHED_REFERENCE" for row in report["executed_orders"]),
        "unresolved": sum(row["state"] == "UNRESOLVED" for row in report["executed_orders"]),
        "ambiguous": sum(row["state"] == "AMBIGUOUS" for row in report["executed_orders"]),
        "insufficient_scope": sum(row["state"] == "INSUFFICIENT_SCOPE" for row in report["executed_orders"]),
    }
    return _finish(report)


__all__ = ["REPORT_FORMAT", "broker_internal_reference_report"]
