"""Read-only, exact-key lifecycle audit for momentum-paper evidence.

The audit intentionally refuses ticker/date joins.  Only future paper rows with
the immutable ``paper_admission_key`` and ledger ``origin_ref`` can form a
complete lifecycle; legacy records remain visible as unavailable evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from typing import Any, Sequence


SOURCE = "MOMENTUM_PAPER"
SCHEMA = "momentum_paper_decision_audit_v1"
_OUTCOME_COLUMNS = {"admission_key", "signal_key", "ticker", "outcome", "recorded_at"}
_POSITION_COLUMNS = {
    "paper_admission_key", "ticker", "entry_date", "exit_date", "status",
    "entry_price", "shares", "initial_capital_at_risk", "realised_pnl", "r_multiple", "source",
}
_LEDGER_COLUMNS = {"origin_ref", "event_type", "pnl", "timestamp", "source"}


class MomentumPaperAuditError(ValueError):
    """Invalid audit request; the source database is never changed."""


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unavailable(reason: str, *, limit: int) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "UNAVAILABLE",
        "reason": reason,
        "limit": limit,
        "cash_truth": "bankroll_ledger",
        "qualification": "NOT_ASSESSED",
        "opportunities": [],
    }


def _open_readonly(db_path: str) -> sqlite3.Connection | None:
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _round(value: float | None, digits: int = 6) -> float | None:
    return round(float(value), digits) if value is not None else None


def _entry_snapshot(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, str) or len(raw) > 4096:
        return None
    try:
        value = json.loads(raw)
        # Reject NaN/Infinity even though Python's JSON reader accepts them.
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _position_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "ticker": row["ticker"],
        "entry_date": row["entry_date"],
        "exit_date": row["exit_date"],
        "status": row["status"],
        "entry_price": _round(row["entry_price"]),
        "shares": int(row["shares"] or 0),
        "initial_capital_at_risk": _round(row["initial_capital_at_risk"]),
        "realised_pnl": _round(row["realised_pnl"]),
        "r_multiple": _round(row["r_multiple"], 8),
    }


def _cash_view(rows: list[sqlite3.Row], position: dict[str, Any] | None) -> dict[str, Any]:
    partials = [row for row in rows if row["event_type"] == "TRADE_PARTIAL"]
    closes = [row for row in rows if row["event_type"] == "TRADE_CLOSED"]
    other = [row for row in rows if row["event_type"] not in {"TRADE_PARTIAL", "TRADE_CLOSED"}]
    partial_pnl = sum(float(row["pnl"] or 0.0) for row in partials)
    terminal_pnl = sum(float(row["pnl"] or 0.0) for row in closes)
    net_pnl = partial_pnl + terminal_pnl
    if position is None:
        state = "UNRESOLVED_POSITION_MISSING"
        reconciled = None
    elif position["exit_date"] is None:
        state = "OPEN_NO_TERMINAL_CASH" if not closes and not other else "UNRESOLVED_OPEN_POSITION_CASH"
        reconciled = None
    elif len(closes) != 1 or other:
        state = "UNRESOLVED_TERMINAL_CASH"
        reconciled = None
    elif position["realised_pnl"] is None:
        state = "UNAVAILABLE_POSITION_PNL"
        reconciled = None
    else:
        delta = float(position["realised_pnl"]) - net_pnl
        state = "MATCH" if abs(delta) <= 0.01 else "MISMATCH"
        reconciled = _round(delta)
    return {
        "state": state,
        "partial_count": len(partials),
        "terminal_count": len(closes),
        "other_event_count": len(other),
        "partial_pnl": _round(partial_pnl),
        "terminal_pnl": _round(terminal_pnl),
        "net_pnl": _round(net_pnl) if rows else None,
        "position_pnl_delta": reconciled,
        "events": [
            {"event_type": row["event_type"], "timestamp": row["timestamp"], "pnl": _round(row["pnl"])}
            for row in rows
        ],
    }


def build_momentum_paper_decision_audit(db_path: str, *, limit: int = 1000) -> dict[str, Any]:
    """Build a deterministic audit from an existing SQLite DB in read-only mode."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20_000:
        raise MomentumPaperAuditError("limit must be an integer from 1 through 20000")
    connection = _open_readonly(db_path)
    if connection is None:
        return _unavailable("database_unavailable_or_missing", limit=limit)
    try:
        outcome_cols = _table_columns(connection, "momentum_paper_admission_outcomes")
        position_cols = _table_columns(connection, "positions")
        ledger_cols = _table_columns(connection, "bankroll_ledger")
        if not _OUTCOME_COLUMNS.issubset(outcome_cols):
            return _unavailable("admission_outcome_schema_unavailable", limit=limit)
        connection.row_factory = sqlite3.Row
        economics_column = "entry_economics_json" if "entry_economics_json" in outcome_cols else "NULL AS entry_economics_json"
        admissions = connection.execute(
            f"SELECT admission_key,signal_key,ticker,outcome,recorded_at,{economics_column} "
            "FROM momentum_paper_admission_outcomes "
            "ORDER BY recorded_at,admission_key LIMIT ?",
            (limit + 1,),
        ).fetchall()
        truncated = len(admissions) > limit
        admissions = admissions[:limit]
        keys = {str(row["admission_key"]) for row in admissions}

        position_by_key: dict[str, list[sqlite3.Row]] = {}
        position_schema_available = _POSITION_COLUMNS.issubset(position_cols)
        if position_schema_available and keys:
            marks = ",".join("?" for _ in keys)
            rows = connection.execute(
                "SELECT paper_admission_key,ticker,entry_date,exit_date,status,entry_price,shares,"
                "initial_capital_at_risk,realised_pnl,r_multiple "
                f"FROM positions WHERE source=? AND paper_admission_key IN ({marks}) "
                "ORDER BY entry_date,rowid",
                (SOURCE, *sorted(keys)),
            ).fetchall()
            for row in rows:
                position_by_key.setdefault(str(row["paper_admission_key"]), []).append(row)

        cash_by_key: dict[str, list[sqlite3.Row]] = {}
        ledger_schema_available = _LEDGER_COLUMNS.issubset(ledger_cols)
        unlinked_cash_count = None
        if ledger_schema_available and keys:
            marks = ",".join("?" for _ in keys)
            ledger_rows = connection.execute(
                "SELECT origin_ref,event_type,pnl,timestamp FROM bankroll_ledger "
                f"WHERE source=? AND origin_ref IN ({marks}) ORDER BY timestamp,rowid",
                (SOURCE, *sorted(keys)),
            ).fetchall()
            for row in ledger_rows:
                cash_by_key.setdefault(str(row["origin_ref"]), []).append(row)
            unlinked_cash_count = int(connection.execute(
                "SELECT COUNT(*) FROM bankroll_ledger WHERE source=? "
                "AND event_type IN ('TRADE_PARTIAL','TRADE_CLOSED') AND ("
                "origin_ref IS NULL OR origin_ref NOT IN ("
                "SELECT admission_key FROM momentum_paper_admission_outcomes))",
                (SOURCE,),
            ).fetchone()[0])

        opportunities = []
        for admission in admissions:
            key = str(admission["admission_key"])
            linked_positions = position_by_key.get(key, [])
            position = _position_view(linked_positions[0]) if len(linked_positions) == 1 else None
            outcome = str(admission["outcome"])
            if not position_schema_available:
                lifecycle = "UNAVAILABLE_POSITION_LINK_SCHEMA"
            elif len(linked_positions) > 1:
                lifecycle = "UNRESOLVED_DUPLICATE_POSITION_KEY"
            elif outcome == "opened" and position is None:
                lifecycle = "UNRESOLVED_POSITION_MISSING"
            elif outcome != "opened" and position is not None:
                lifecycle = "UNRESOLVED_POSITION_FOR_NONOPENED_ADMISSION"
            elif outcome == "opened" and position and position["exit_date"] is None:
                lifecycle = "OPEN"
            elif outcome == "opened":
                lifecycle = "CLOSED"
            else:
                lifecycle = f"NOT_OPENED_{outcome.upper()}"
            cash = (
                _cash_view(cash_by_key.get(key, []), position)
                if ledger_schema_available else {
                    "state": "UNAVAILABLE_LEDGER_LINK_SCHEMA", "partial_count": None,
                    "terminal_count": None, "other_event_count": None, "partial_pnl": None,
                    "terminal_pnl": None, "net_pnl": None, "position_pnl_delta": None, "events": [],
                }
            )
            opportunities.append({
                "admission_key": key,
                "signal_key": admission["signal_key"],
                "ticker": admission["ticker"],
                "outcome": outcome,
                "recorded_at": admission["recorded_at"],
                "entry_economics": _entry_snapshot(admission["entry_economics_json"]),
                "lifecycle": lifecycle,
                "position": position,
                "cash": cash,
            })

        matched_closed = [
            row for row in opportunities
            if row["lifecycle"] == "CLOSED" and row["cash"]["state"] == "MATCH"
        ]
        report = {
            "schema": SCHEMA,
            # A syntactically readable legacy DB can still lack the exact-key
            # columns needed for a lifecycle conclusion.  Do not label that
            # evidence set complete merely because the admission table exists.
            "status": "PARTIAL" if (
                truncated or not position_schema_available or not ledger_schema_available
            ) else "COMPLETE",
            "limit": limit,
            "truncated": truncated,
            "cash_truth": "bankroll_ledger",
            "qualification": "NOT_ASSESSED",
            "schema_availability": {
                "positions_admission_identity": position_schema_available,
                "ledger_origin_identity": ledger_schema_available,
            },
            "unlinked_legacy_cash_event_count": unlinked_cash_count,
            "summary": {
                "admission_count": len(opportunities),
                "outcomes": {
                    outcome: sum(1 for row in opportunities if row["outcome"] == outcome)
                    for outcome in sorted({row["outcome"] for row in opportunities})
                },
                "matched_closed_count": len(matched_closed),
                "matched_closed_net_pnl": _round(sum(float(row["cash"]["net_pnl"]) for row in matched_closed)) if matched_closed else None,
                "unresolved_or_unavailable_count": sum(
                    1 for row in opportunities
                    if row["lifecycle"].startswith(("UNRESOLVED", "UNAVAILABLE"))
                    or row["cash"]["state"].startswith(("UNRESOLVED", "UNAVAILABLE"))
                ),
            },
            "opportunities": opportunities,
        }
        return report
    except sqlite3.Error:
        return _unavailable("database_query_unavailable", limit=limit)
    finally:
        connection.close()


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only momentum-paper decision audit")
    parser.add_argument("--db", required=True, help="existing SQLite database")
    parser.add_argument("--limit", type=int, default=1000, help="admission rows to inspect (1..20000)")
    args = parser.parse_args(argv)
    try:
        print(_canonical(build_momentum_paper_decision_audit(args.db, limit=args.limit)))
    except MomentumPaperAuditError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
