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
    rowids = [row.get("ledger_rowid") for row in events]
    have_rowids = bool(events) and all(isinstance(value, int) and not isinstance(value, bool) for value in rowids)
    all_clocks = all(clock is not None for clock in clocks)
    unique_clocks = len(set(clocks)) == len(clocks)
    # Equal clocks are ordered only by the ledger's own row identity; without
    # it the intratimestamp order is unknown and no drawdown is invented.
    ordered = all_clocks and (unique_clocks or have_rowids)
    ordering = ("CHRONOLOGICAL" if all_clocks and unique_clocks else
                "CHRONOLOGICAL_LEDGER_ROWID_TIEBREAK" if ordered else "UNAVAILABLE_CLOCK_ORDER")
    cash_events = (sorted(zip(clocks, events), key=lambda item: (item[0], item[1].get("ledger_rowid") or 0))
                   if ordered else [])
    for _clock, row in cash_events:
        equity += float(row["pnl"] or 0.0)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {"partial_cash": round(sum(partial), 6), "terminal_cash": round(sum(terminal), 6),
            "net_cash": round(sum(partial) + sum(terminal), 6), "cash_event_count": len(events),
            "daily_cash_drawdown": round(drawdown, 6) if ordered else None,
            "cash_ordering": ordering,
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
    closed_today = [row for row in audit.get("opportunities", [])
                    if row.get("lifecycle") == "CLOSED" and row.get("cash", {}).get("state") == "MATCH"
                    and any(_same_ist_day(event.get("timestamp"), day) and event.get("event_type") == "TRADE_CLOSED"
                            for event in row.get("cash", {}).get("events", []))]
    trades = [_trade_decomposition(row) for row in closed_today]
    nets = [trade["net_cash"] for trade in trades if isinstance(trade["net_cash"], (int, float))]
    lineage: dict[str, dict[str, Any]] = {}
    for trade in trades:
        key = f"{trade['policy_version']}|{trade['regime']}"
        bucket = lineage.setdefault(key, {"policy_version": trade["policy_version"], "regime": trade["regime"],
                                          "closed_trades": 0, "net_cash": 0.0})
        bucket["closed_trades"] += 1
        bucket["net_cash"] = round(bucket["net_cash"] + (trade["net_cash"] or 0.0), 6)
    capital_skipped = [row for row in opportunities if row.get("outcome") == "zero_shares"
                       and row.get("reason") in {"capital_exhausted", "allocation_rounding"}]
    return {"book": "MOMENTUM_PAPER", "mode": "PAPER", "policy": "MOMENTUM_PAPER_FIXED_POOL_V1",
            "trades": trades,
            "lineage": sorted(lineage.values(), key=lambda item: (str(item["policy_version"]), str(item["regime"]))),
            "missed_allocation": {"capital_skipped_count": len(capital_skipped),
                                  "admission_keys": [row["admission_key"] for row in capital_skipped]},
            "sensitivity": {
                "closed_trade_net_cash": round(sum(nets), 6) if nets else None,
                "best_winner_excluded_net_cash": (round(sum(nets) - max(nets), 6)
                                                  if nets and max(nets) > 0 else (round(sum(nets), 6) if nets else None)),
            },
            "source_lineage": {"reader": "momentum_paper_decision_audit", "status": audit.get("status"),
                               "cash_truth": audit.get("cash_truth"),
                               "cash_coverage": "LINKED_ADMISSIONS_WITHIN_AUDIT_LIMIT_NOT_ALL_LEDGER_ROWS"},
            "opportunity_count": len(opportunities), "opened_count": sum(row.get("outcome") == "opened" for row in opportunities),
            "rejected_or_not_selected": rejected, "cash": _cash_summary(events),
            "unknown_count": sum(str(row.get("lifecycle", "")).startswith(("UNRESOLVED", "UNAVAILABLE")) for row in opportunities)}


def _trade_decomposition(row: dict[str, Any]) -> dict[str, Any]:
    """Per closed lifecycle facts; missing evidence stays explicitly unavailable."""
    position = row.get("position") or {}
    entry, admission = row.get("entry_economics") or {}, row.get("admission_economics") or {}
    packet = row.get("source_packet") or {}
    decided, bar = _event_clock(packet.get("received_at")), _event_clock(packet.get("bar_ts"))
    opened, closed = _event_clock(position.get("entry_date")), _event_clock(position.get("exit_date"))
    return {
        "admission_key": row.get("admission_key"), "ticker": row.get("ticker"),
        "policy_version": admission.get("allocation_policy_version") if isinstance(admission, dict) else None,
        "regime": entry.get("regime_at_entry") if isinstance(entry, dict) else None,
        # bar_ts is the screener's bar timestamp as recorded, not a claimed bar-close clock.
        "seconds_from_signal_bar_timestamp": (round((decided - bar).total_seconds(), 3)
                                              if decided is not None and bar is not None else None),
        "hold_minutes": round((closed - opened).total_seconds() / 60, 3) if opened and closed else None,
        "exit_status": position.get("status"),
        "net_cash": row.get("cash", {}).get("net_pnl"),
        "r_multiple": position.get("r_multiple"),
        "giveback": "UNAVAILABLE_WITHOUT_VERIFIED_PATH",
        "costs": "UNAVAILABLE_NOT_SEPARATELY_IN_LEDGER",
    }


def _shadow_book(db_path: str, day: date, *, table: str, book: str) -> dict[str, Any]:
    path = Path(db_path)
    # An absent book is unavailable evidence, not a complete zero day.
    empty = {"book": book, "mode": "SHADOW", "policy": "VARIANT_RECORDED_PER_ROW",
             "source_lineage": {"reader": "sqlite_read_only", "status": "UNAVAILABLE"},
             "opportunity_count": None, "variant_evaluations": None, "accepted_evaluations": None,
             "opened_count": None, "rejected_or_not_selected": [],
             "cash": _cash_summary([]), "unknown_count": None}
    if not path.is_file():
        return empty
    try:
        con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        required = {"trading_date", "ticker", "variant", "accepted", "reject_reason"}
        if not required <= columns:
            con.close(); return empty
        bar = "bar_ts" if "bar_ts" in columns else "NULL"
        rows = con.execute(f"SELECT ticker,variant,accepted,reject_reason,{bar} FROM {table} WHERE trading_date=? "
                           "ORDER BY ticker,variant", (day.isoformat(),)).fetchall()
        con.close()
    except sqlite3.Error:
        return empty
    rejected = [{"ticker": row[0], "policy": row[1], "reason": row[3] or "rejected_without_reason"}
                for row in rows if not bool(row[2])]
    # One opportunity is one ticker/bar; each variant is an evaluation of it,
    # and a shadow acceptance is never an opened position.
    opportunities = {(row[0], row[4]) if row[4] is not None else (row[0], f"row:{index}")
                     for index, row in enumerate(rows)}
    return {**empty, "source_lineage": {"reader": "sqlite_read_only", "status": "OK",
                                        "opportunity_identity": "ticker_bar_ts" if bar == "bar_ts" else "row_unbounded"},
            "opportunity_count": len(opportunities), "variant_evaluations": len(rows),
            "accepted_evaluations": sum(bool(row[2]) for row in rows), "opened_count": None,
            "rejected_or_not_selected": rejected, "unknown_count": 0}


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
