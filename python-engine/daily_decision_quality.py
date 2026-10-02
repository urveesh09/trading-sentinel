"""Read-only S8 daily decision-quality report; never a strategy controller."""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from fno_audit_report import build_fno_daily_audit_report
from momentum_paper_audit import build_momentum_paper_decision_audit


IST = ZoneInfo("Asia/Kolkata")
SCHEMA = "daily_decision_quality_v1"


def _day(value: date | str) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("day must be ISO YYYY-MM-DD") from exc


def _event_clock(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # The retained ledger writer's timezone-less legacy clocks are UTC.
    return (stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _same_ist_day(value: object, day: date) -> bool:
    stamp = _event_clock(value)
    return stamp is not None and stamp.astimezone(IST).date() == day


def _cash_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    partial = [float(row["pnl"] or 0.0) for row in events if row.get("event_type") == "TRADE_PARTIAL"]
    terminal = [float(row["pnl"] or 0.0) for row in events if row.get("event_type") == "TRADE_CLOSED"]
    equity = peak = drawdown = 0.0
    clocks = [_event_clock(row.get("timestamp")) for row in events]
    ordered = all(clock is not None for clock in clocks) and len(set(clocks)) == len(clocks)
    # Grouped admissions are not a chronological cash stream. Equal clocks
    # without ledger row identity cannot establish the intratimestamp order.
    cash_events = sorted(zip(clocks, events), key=lambda item: item[0]) if ordered else []
    for _clock, row in cash_events:
        equity += float(row["pnl"] or 0.0)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {"partial_cash": round(sum(partial), 6), "terminal_cash": round(sum(terminal), 6),
            "net_cash": round(sum(partial) + sum(terminal), 6), "cash_event_count": len(events),
            "daily_cash_drawdown": round(drawdown, 6) if ordered else None,
            "cash_ordering": "CHRONOLOGICAL" if ordered else "UNAVAILABLE_CLOCK_ORDER",
            # A fixed-pool label is not recorded management-policy lineage.
            "version_specific_cash_drawdown": None}


def _momentum_book(db_path: str, day: date) -> dict[str, Any]:
    audit = build_momentum_paper_decision_audit(db_path)
    opportunities = [row for row in audit.get("opportunities", []) if _same_ist_day(row.get("recorded_at"), day)]
    events = [event for row in audit.get("opportunities", []) for event in row.get("cash", {}).get("events", [])
              if event.get("event_type") in {"TRADE_PARTIAL", "TRADE_CLOSED"}
              and _same_ist_day(event.get("timestamp"), day)]
    rejected = [{"admission_key": row["admission_key"], "outcome": row["outcome"], "reason": row.get("reason")}
                for row in opportunities if row.get("outcome") != "opened"]
    return {"book": "MOMENTUM_PAPER", "mode": "PAPER", "policy": "MOMENTUM_PAPER_FIXED_POOL_V1",
            "source_lineage": {"reader": "momentum_paper_decision_audit", "status": audit.get("status"),
                               "cash_truth": audit.get("cash_truth"),
                               "cash_coverage": "LINKED_ADMISSIONS_WITHIN_AUDIT_LIMIT_NOT_ALL_LEDGER_ROWS"},
            "opportunity_count": len(opportunities), "opened_count": sum(row.get("outcome") == "opened" for row in opportunities),
            "rejected_or_not_selected": rejected, "cash": _cash_summary(events),
            "unknown_count": sum(str(row.get("lifecycle", "")).startswith(("UNRESOLVED", "UNAVAILABLE")) for row in opportunities)}


def _shadow_book(db_path: str, day: date, *, table: str, book: str) -> dict[str, Any]:
    path = Path(db_path)
    empty = {"book": book, "mode": "SHADOW", "policy": "VARIANT_RECORDED_PER_ROW",
             "source_lineage": {"reader": "sqlite_read_only", "status": "UNAVAILABLE"},
             "opportunity_count": 0, "opened_count": 0, "rejected_or_not_selected": [],
             "cash": _cash_summary([]), "unknown_count": 0}
    if not path.is_file():
        return empty
    try:
        con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        required = {"trading_date", "ticker", "variant", "accepted", "reject_reason"}
        if not required <= columns:
            con.close(); return empty
        rows = con.execute(f"SELECT ticker,variant,accepted,reject_reason FROM {table} WHERE trading_date=? ORDER BY ticker,variant", (day.isoformat(),)).fetchall()
        con.close()
    except sqlite3.Error:
        return empty
    rejected = [{"ticker": row[0], "policy": row[1], "reason": row[3] or "rejected_without_reason"}
                for row in rows if not bool(row[2])]
    return {**empty, "source_lineage": {"reader": "sqlite_read_only", "status": "OK"},
            "opportunity_count": len(rows), "opened_count": sum(bool(row[2]) for row in rows),
            "rejected_or_not_selected": rejected}


async def build_daily_decision_quality_report(db_path: str, day: date | str) -> dict[str, Any]:
    """Produce reproducible daily facts; selection remains explicitly human review."""
    report_day = _day(day)
    fno = await build_fno_daily_audit_report(db_path, report_day)
    financial = fno.get("financial", {}).get("by_source", {})
    fno_books = []
    for source, values in sorted(financial.items()):
        closed, partial = values.get("closed", {}), values.get("partial", {})
        fno_books.append({"book": source, "mode": "PAPER", "policy": "RECORDED_RUNTIME_POLICY",
                          "source_lineage": {"reader": "fno_daily_audit", "status": fno.get("financial", {}).get("status")},
                          "opportunity_count": fno.get("signal_evidence", {}).get("decision_unit_count", 0),
                          "opened_count": None, "rejected_or_not_selected": [],
                          "cash": {"partial_cash": partial.get("realised_pnl"), "terminal_cash": closed.get("realised_pnl"),
                                   "net_cash": round(float(partial.get("realised_pnl") or 0) + float(closed.get("realised_pnl") or 0), 6),
                                   "cash_event_count": int(partial.get("event_count") or 0) + int(closed.get("event_count") or 0),
                                   "version_specific_cash_drawdown": None}, "unknown_count": fno.get("defined_risk_settlement", {}).get("unresolved_count", 0)})
    books = [_momentum_book(db_path, report_day), _shadow_book(db_path, report_day, table="momentum_shadow_evaluations", book="MOMENTUM_SHADOW"),
             _shadow_book(db_path, report_day, table="penny_shadow_evaluations", book="PENNY_SHADOW"), *fno_books]
    rejected = [item for book in books for item in book["rejected_or_not_selected"]]
    return {"schema": SCHEMA, "report_day_ist": report_day.isoformat(), "read_only": True, "books": books,
            "rejected_hypotheses": rejected or [{"state": "NO_REJECTED_HYPOTHESIS_RECORDED"}],
            "selection": {"state": "HUMAN_REVIEW_REQUIRED", "automatic_change": "NONE", "reason": "Daily facts do not authorize retuning, capital changes, or qualification."},
            "qualification": "NOT_ASSESSED"}


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only daily decision-quality report")
    parser.add_argument("--db", required=True); parser.add_argument("--day", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(asyncio.run(build_daily_decision_quality_report(args.db, args.day)), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
