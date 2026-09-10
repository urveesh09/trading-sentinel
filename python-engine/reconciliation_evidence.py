"""Stable-link accounting evidence for future F&O closes.

Historical rows without a durable origin reference stay visible as unresolved;
this module never guesses a one-to-one match from ticker and date.
"""
from __future__ import annotations

from typing import Any

import aiosqlite


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    return {str(row[1]) for row in rows}


async def reconciliation_evidence_report(db_path: str, *, source: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Report deterministic link states; no record is economically modified."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be within 1..1000")
    async with aiosqlite.connect(db_path) as db:
        ledger_columns = await _columns(db, "bankroll_ledger")
        required = {"id", "timestamp", "event_type", "source", "pnl"}
        if not required.issubset(ledger_columns):
            return {"status": "INSUFFICIENT_SOURCE_COVERAGE", "reason": "BANKROLL_LEDGER_SCHEMA_UNAVAILABLE", "sheets": []}
        origin_select = "origin_ref" if "origin_ref" in ledger_columns else "NULL"
        clause, params = "WHERE event_type='TRADE_CLOSED'", []
        if source:
            clause += " AND source=?"
            params.append(source)
        rows = await (await db.execute(
            f"SELECT id,timestamp,source,ticker,pnl,{origin_select} FROM bankroll_ledger {clause} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        )).fetchall()
        fno_columns = await _columns(db, "fno_positions")
        dr_columns = await _columns(db, "fno_dr_positions")
        fno_available = {"id", "source", "status", "pnl"}.issubset(fno_columns)
        dr_available = {"id", "source", "status", "pnl"}.issubset(dr_columns)
        sheets = []
        for ledger_id, timestamp, row_source, ticker, pnl, origin_ref in rows:
            item = {"ledger_id": int(ledger_id), "timestamp": timestamp, "source": row_source,
                    "ticker": ticker, "ledger_pnl": pnl, "origin_ref": origin_ref,
                    "state": "UNRESOLVED", "reason": "stable_origin_ref_missing", "position": None}
            if not origin_ref:
                sheets.append(item); continue
            prefix, _, raw_id = str(origin_ref).partition(":")
            try:
                position_id = int(raw_id)
            except ValueError:
                item["reason"] = "stable_origin_ref_malformed"; sheets.append(item); continue
            if prefix == "fno_position" and fno_available:
                match = await (await db.execute(
                    "SELECT source,status,pnl FROM fno_positions WHERE id=?", (position_id,)
                )).fetchone()
            elif prefix == "fno_dr_structure" and dr_available:
                match = await (await db.execute(
                    "SELECT source,status,pnl FROM fno_dr_positions WHERE id=?", (position_id,)
                )).fetchone()
            else:
                match = None
            if match is None:
                item["reason"] = "origin_ref_has_no_matching_position"
            else:
                item["position"] = {"source": match[0], "status": match[1], "pnl": match[2]}
                if match[0] != row_source:
                    item["reason"] = "origin_ref_source_mismatch"
                elif match[1] == "OPEN" or match[2] is None:
                    item["reason"] = "origin_ref_position_not_closed_or_unvalued"
                elif abs(float(match[2]) - float(pnl)) > .01:
                    item["reason"] = "origin_ref_pnl_difference"
                else:
                    item["state"], item["reason"] = "MATCHED_INTERNAL", "stable_origin_ref_and_pnl_match"
            sheets.append(item)
    counts: dict[str, int] = {}
    for item in sheets:
        counts[item["reason"]] = counts.get(item["reason"], 0) + 1
    status = "MATCHED_INTERNAL" if sheets and all(item["state"] == "MATCHED_INTERNAL" for item in sheets) else "UNRESOLVED"
    if not sheets:
        status = "INSUFFICIENT_SOURCE_COVERAGE"
    return {"status": status, "source": source, "sheets": sheets, "reason_counts": counts,
            "accounting_truth": "bankroll_ledger", "broker_reconciled": False,
            "note": "Internal origin matching is not broker-statement reconciliation. Legacy rows without origin_ref remain unresolved."}
