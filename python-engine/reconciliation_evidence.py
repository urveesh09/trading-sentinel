"""Read-consistent, explicitly bounded internal reconciliation evidence.

This is an accounting investigation, not a broker-reconciliation claim. Every
requested strategy has a sheet even when no rows exist: zero never means
unavailable or outside the selected window.
"""
from __future__ import annotations

import math
import hashlib
import json
from collections import Counter
from typing import Any

import aiosqlite


SOURCES = ("MOMENTUM", "EDGE_LIVE", "MOMENTUM_PAPER", "PENNY_PAPER", "EDGE_PAPER")
_TRADE_EVENTS = {"TRADE_CLOSED", "TRADE_PARTIAL", "TRADE_OPEN"}


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    return {str(row[1]) for row in rows}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


async def _position_lookup(db: aiosqlite.Connection, origin_ref: str) -> tuple[Any, ...] | None:
    prefix, _, raw_id = origin_ref.partition(":")
    try:
        position_id = int(raw_id)
    except ValueError:
        return None
    if prefix == "fno_position" and {"id", "source", "status", "pnl"}.issubset(await _columns(db, "fno_positions")):
        return await (await db.execute("SELECT source,status,pnl FROM fno_positions WHERE id=?", (position_id,))).fetchone()
    if prefix == "fno_dr_structure" and {"id", "source", "status", "pnl"}.issubset(await _columns(db, "fno_dr_positions")):
        return await (await db.execute("SELECT source,status,pnl FROM fno_dr_positions WHERE id=?", (position_id,))).fetchone()
    return None


async def _detail_rows(db: aiosqlite.Connection, *, source: str | None, limit: int) -> tuple[list[dict[str, Any]], int]:
    columns = await _columns(db, "bankroll_ledger")
    origin = "origin_ref" if "origin_ref" in columns else "NULL"
    where, params = "WHERE event_type='TRADE_CLOSED'", []
    if source:
        where += " AND source=?"; params.append(source)
    total = int((await (await db.execute(f"SELECT COUNT(*) FROM bankroll_ledger {where}", params)).fetchone())[0])
    rows = await (await db.execute(
        f"SELECT id,timestamp,source,ticker,pnl,{origin} FROM bankroll_ledger {where} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    )).fetchall()
    origin_counts = Counter(str(row[5]) for row in rows if row[5])
    details: list[dict[str, Any]] = []
    for ledger_id, timestamp, row_source, ticker, pnl, origin_ref in rows:
        item = {"ledger_id": int(ledger_id), "timestamp": timestamp, "source": row_source,
                "ticker": ticker, "ledger_pnl": pnl, "origin_ref": origin_ref,
                "state": "UNRESOLVED", "reason": "stable_origin_ref_missing", "position": None}
        if not origin_ref:
            details.append(item); continue
        if origin_counts[str(origin_ref)] > 1:
            item["reason"] = "multiple_ledger_rows_share_origin_ref"
            details.append(item); continue
        match = await _position_lookup(db, str(origin_ref))
        if match is None:
            item["reason"] = "origin_ref_has_no_matching_position"
        else:
            position_pnl, ledger_pnl = _finite(match[2]), _finite(pnl)
            item["position"] = {"source": match[0], "status": match[1], "pnl": match[2]}
            if match[0] != row_source:
                item["reason"] = "origin_ref_source_mismatch"
            elif match[1] == "OPEN" or position_pnl is None:
                item["reason"] = "origin_ref_position_not_closed_or_unvalued"
            elif ledger_pnl is None:
                item["reason"] = "ledger_pnl_nonfinite_or_missing"
            elif abs(position_pnl - ledger_pnl) > .01:
                item["reason"] = "origin_ref_pnl_difference"
            else:
                item["state"], item["reason"] = "MATCHED_INTERNAL", "stable_origin_ref_and_pnl_match"
        details.append(item)
    return details, total


async def _source_sheet(db: aiosqlite.Connection, source: str) -> dict[str, Any]:
    rows = await (await db.execute(
        "SELECT id,timestamp,event_type,pnl,bankroll_before,bankroll_after,notes FROM bankroll_ledger WHERE source=? ORDER BY id",
        (source,),
    )).fetchall()
    snapshot = hashlib.sha256(json.dumps([list(row) for row in rows], sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    if not rows:
        return {"source": source, "status": "NO_INTERNAL_LEDGER_ROWS", "scope": {"row_count": 0, "truncated": False},
                "time_range": {"first": None, "last": None}, "amounts": {"realized_pnl": None, "funding_or_adjustments": None, "costs": None},
                "counts": {"trade_closed": 0, "trade_partial": 0, "trade_open": 0, "funding_or_adjustments": 0, "nonfinite_amounts": 0},
                "coverage": ["No internal ledger rows for this source; broker evidence was not queried."], "snapshot_sha256": snapshot,
                "reproducibility": {"query": "bankroll_ledger WHERE source=? ORDER BY id", "parameters": [source]}, "broker_reconciled": False}
    events = Counter(str(row[2]) for row in rows)
    amounts = [_finite(row[3]) for row in rows]
    nonfinite = sum(value is None for value in amounts)
    realized = sum(value for row, value in zip(rows, amounts) if row[2] in _TRADE_EVENTS and value is not None)
    adjustments = sum(value for row, value in zip(rows, amounts) if row[2] not in _TRADE_EVENTS and value is not None)
    balance_deltas = []
    balance_mismatches = 0
    for row, pnl in zip(rows, amounts):
        before, after = _finite(row[4]), _finite(row[5])
        delta = after - before if before is not None and after is not None else None
        balance_deltas.append(delta)
        if delta is not None and pnl is not None and abs(delta - pnl) > .01:
            balance_mismatches += 1
    return {"source": source, "status": "INTERNAL_EVIDENCE_AVAILABLE" if not nonfinite else "INTERNAL_EVIDENCE_HAS_INVALID_AMOUNTS",
            "scope": {"row_count": len(rows), "truncated": False, "read_consistency": "single_sqlite_read_transaction"},
            "time_range": {"first": rows[0][1], "last": rows[-1][1]},
            "amounts": {"realized_pnl": round(realized, 4), "funding_or_adjustments": round(adjustments, 4), "costs": None,
                        "bankroll_delta": round(sum(value for value in balance_deltas if value is not None), 4),
                        "pnl_to_bankroll_delta_difference_count": balance_mismatches},
            "counts": {"trade_closed": events["TRADE_CLOSED"], "trade_partial": events["TRADE_PARTIAL"], "trade_open": events["TRADE_OPEN"],
                       "funding_or_adjustments": sum(count for event, count in events.items() if event not in _TRADE_EVENTS), "nonfinite_amounts": nonfinite},
            "coverage": ["Costs and broker statement balances are not present in bankroll_ledger.",
                          "Partial exits are counted but require durable origins for position matching."],
            "snapshot_sha256": snapshot,
            "reproducibility": {"query": "bankroll_ledger WHERE source=? ORDER BY id", "parameters": [source]},
            "broker_reconciled": False}


async def reconciliation_evidence_report(db_path: str, *, source: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Return five forensic source sheets plus bounded stable-origin details."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be within 1..1000")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN")
        try:
            required = {"id", "timestamp", "event_type", "source", "pnl"}
            if not required.issubset(await _columns(db, "bankroll_ledger")):
                return {"status": "INSUFFICIENT_SOURCE_COVERAGE", "reason": "BANKROLL_LEDGER_SCHEMA_UNAVAILABLE", "sheets": [], "source_sheets": []}
            details, total = await _detail_rows(db, source=source, limit=limit)
            source_sheets = [await _source_sheet(db, item) for item in SOURCES]
        finally:
            await db.rollback()
    counts = Counter(item["reason"] for item in details)
    status = "MATCHED_INTERNAL" if details and all(item["state"] == "MATCHED_INTERNAL" for item in details) else "UNRESOLVED"
    if not details:
        status = "INSUFFICIENT_SOURCE_COVERAGE"
    return {"status": status, "source": source, "sheets": details, "source_sheets": source_sheets,
            "reason_counts": dict(counts), "pagination": {"requested_limit": limit, "matching_closed_rows": total,
            "returned_closed_rows": len(details), "truncated": total > len(details), "sort": "id_desc"},
            "accounting_truth": "bankroll_ledger", "broker_reconciled": False,
            "note": "Internal evidence only. Stable origin matching is bounded and duplicates are explicit; it is not broker-statement reconciliation."}
