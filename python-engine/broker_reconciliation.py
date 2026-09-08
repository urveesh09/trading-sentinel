"""Read-only broker statement reconciliation for account-level cash truth.

Imports are explicit fixtures/adapters, never broker calls.  This keeps a
statement's reported closing cash distinct from local strategy books while
making funding, costs and unresolved residuals visible.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

import aiosqlite


_SCHEMA = """
CREATE TABLE IF NOT EXISTS broker_statement_imports (
 account_id TEXT NOT NULL, statement_id TEXT NOT NULL, as_of TEXT NOT NULL,
 opening_cash REAL NOT NULL, closing_cash REAL NOT NULL, payload_sha256 TEXT NOT NULL,
 imported_at TEXT NOT NULL, PRIMARY KEY(account_id, statement_id)
);
CREATE TABLE IF NOT EXISTS broker_statement_entries (
 account_id TEXT NOT NULL, statement_id TEXT NOT NULL, entry_id TEXT NOT NULL,
 entry_type TEXT NOT NULL, amount REAL NOT NULL, PRIMARY KEY(account_id, statement_id, entry_id)
);
CREATE TABLE IF NOT EXISTS broker_statement_fills (
 account_id TEXT NOT NULL, statement_id TEXT NOT NULL, fill_id TEXT NOT NULL,
 order_id TEXT NOT NULL, status TEXT NOT NULL, quantity REAL NOT NULL,
 price REAL NOT NULL, fees REAL NOT NULL, PRIMARY KEY(account_id, statement_id, fill_id)
);
"""
_ENTRY_TYPES = frozenset({"DEPOSIT", "WITHDRAWAL", "TRADE_REALIZED", "CHARGE", "OPERATING_EXPENSE"})
_FILL_STATUSES = frozenset({"FILLED", "PARTIAL", "CANCELLED", "REJECTED"})


def _stamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(timezone.utc)


def _finite(value: object, field: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{field} is invalid")
    return result


async def import_broker_statement(
    db_path: str, *, account_id: str, statement_id: str, as_of: datetime,
    opening_cash: float, closing_cash: float, entries: list[dict[str, Any]], fills: list[dict[str, Any]],
) -> bool:
    """Atomically import one immutable broker statement; identical retry is safe."""
    if not account_id or not statement_id or not isinstance(entries, list) or not isinstance(fills, list):
        raise ValueError("statement identity and lists are required")
    at = _stamp(as_of)
    opening, closing = _finite(opening_cash, "opening_cash"), _finite(closing_cash, "closing_cash")
    clean_entries = []
    for row in entries:
        if not isinstance(row, dict) or str(row.get("entry_id", "")).strip() == "":
            raise ValueError("statement entry identity is required")
        kind = str(row.get("entry_type", "")).upper()
        if kind not in _ENTRY_TYPES:
            raise ValueError("unsupported statement entry type")
        amount = _finite(row.get("amount"), "statement entry amount", positive=kind != "TRADE_REALIZED")
        clean_entries.append((str(row["entry_id"]), kind, amount))
    if len({row[0] for row in clean_entries}) != len(clean_entries):
        raise ValueError("duplicate statement entry identity")
    clean_fills = []
    for row in fills:
        if not isinstance(row, dict):
            raise ValueError("fill must be an object")
        fill_id, order_id = str(row.get("fill_id", "")).strip(), str(row.get("order_id", "")).strip()
        status = str(row.get("status", "")).upper()
        if not fill_id or not order_id or status not in _FILL_STATUSES:
            raise ValueError("fill identity or status is invalid")
        quantity = _finite(row.get("quantity"), "fill quantity")
        price = _finite(row.get("price"), "fill price")
        fees = _finite(row.get("fees", 0), "fill fees")
        if quantity < 0 or price < 0 or fees < 0 or (status in {"FILLED", "PARTIAL"} and (quantity <= 0 or price <= 0)):
            raise ValueError("fill economics are invalid")
        clean_fills.append((fill_id, order_id, status, quantity, price, fees))
    if len({row[0] for row in clean_fills}) != len(clean_fills):
        raise ValueError("duplicate fill identity")
    payload = {"as_of": at.isoformat(), "opening_cash": opening, "closing_cash": closing, "entries": clean_entries, "fills": clean_fills}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA); await db.execute("BEGIN IMMEDIATE")
        existing = await (await db.execute("SELECT payload_sha256 FROM broker_statement_imports WHERE account_id=? AND statement_id=?", (account_id, statement_id))).fetchone()
        if existing:
            if existing[0] != digest:
                await db.rollback(); raise ValueError("statement identity conflicts with prior import")
            await db.commit(); return False
        await db.execute("INSERT INTO broker_statement_imports VALUES (?,?,?,?,?,?,?)", (account_id, statement_id, at.isoformat(), opening, closing, digest, datetime.now(timezone.utc).isoformat()))
        await db.executemany("INSERT INTO broker_statement_entries VALUES (?,?,?,?,?)", [(account_id, statement_id, *row) for row in clean_entries])
        await db.executemany("INSERT INTO broker_statement_fills VALUES (?,?,?,?,?,?,?,?)", [(account_id, statement_id, *row) for row in clean_fills])
        await db.commit()
    return True


async def broker_statement_report(db_path: str, *, account_id: str) -> dict:
    """Return the newest statement's post-cost reconciliation, or unavailable."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        statement = await (await db.execute("SELECT statement_id,as_of,opening_cash,closing_cash FROM broker_statement_imports WHERE account_id=? ORDER BY as_of DESC LIMIT 1", (account_id,))).fetchone()
        if not statement:
            return {"account_id": account_id, "status": "UNAVAILABLE", "reason": "NO_BROKER_STATEMENT", "can_place_orders": False}
        entries = await (await db.execute("SELECT entry_type,amount FROM broker_statement_entries WHERE account_id=? AND statement_id=?", (account_id, statement[0]))).fetchall()
        fills = await (await db.execute("SELECT status FROM broker_statement_fills WHERE account_id=? AND statement_id=?", (account_id, statement[0]))).fetchall()
    totals = {kind: 0.0 for kind in _ENTRY_TYPES}
    for kind, amount in entries: totals[kind] += float(amount)
    expected = float(statement[2]) + totals["DEPOSIT"] - totals["WITHDRAWAL"] + totals["TRADE_REALIZED"] - totals["CHARGE"] - totals["OPERATING_EXPENSE"]
    residual = float(statement[3]) - expected
    return {"account_id": account_id, "statement_id": statement[0], "as_of": statement[1], "status": "MATCH" if abs(residual) <= .01 else "UNRESOLVED", "opening_cash": statement[2], "closing_cash": statement[3], "net_trading_result": round(totals["TRADE_REALIZED"], 2), "deposits": round(totals["DEPOSIT"], 2), "withdrawals": round(totals["WITHDRAWAL"], 2), "charges": round(totals["CHARGE"], 2), "operating_expenses": round(totals["OPERATING_EXPENSE"], 2), "expected_closing_cash": round(expected, 2), "residual": round(residual, 2), "fills": {status: sum(1 for row in fills if row[0] == status) for status in sorted(_FILL_STATUSES)}, "can_place_orders": False}
