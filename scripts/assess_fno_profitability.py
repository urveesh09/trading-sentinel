"""Read-only operational F&O history; never a current-policy backtest.

Run locally with --db, or stream the collector into an existing container with
--container. No broker calls, credentials, migrations, orders or messages.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
LIMIT = 100_000


def collect(db_path: str, archive_root: str) -> dict:
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {"collected_at_utc": datetime.now(timezone.utc).isoformat(), "tables": {}}
        for table in ("fno_positions", "fno_dr_positions", "bankroll_ledger"):
            if table not in tables:
                result["tables"][table] = None
                continue
            where = " WHERE source IN ('FNO_PAPER','FNO_LIVE')" if table == "bankroll_ledger" else ""
            if db.execute(f"SELECT count(*) FROM {table}{where}").fetchone()[0] > LIMIT:
                raise ValueError("evidence exceeds bounded collector limit; refusing truncation")
            result["tables"][table] = [dict(r) for r in db.execute(f"SELECT * FROM {table}{where} ORDER BY id")]
        result["token_candle_coverage"] = []
        if "intraday_cache_by_token" in tables:
            result["token_candle_coverage"] = [dict(r) for r in db.execute(
                "SELECT instrument_token, interval, count(*) rows, min(datetime) first, "
                "max(datetime) last FROM intraday_cache_by_token GROUP BY instrument_token, interval")]
        quote_root = Path(archive_root) / "quotes"
        result["quote_archive_directory_days"] = sorted(
            p.name for p in quote_root.iterdir() if p.is_dir()
        ) if quote_root.is_dir() else []
        return result
    finally:
        db.close()


def day(value: str) -> date:
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("unverifiable naive settlement clock")
    return at.astimezone(IST).date()


def finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def metrics(values: list[float]) -> dict:
    winners = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    cash = peak = drawdown = 0.0
    for v in values:
        cash += v
        peak = max(peak, cash)
        drawdown = max(drawdown, peak - cash)
    return {
        "count": len(values), "wins": len(winners), "losses": len(losses),
        "breakeven": sum(v == 0 for v in values),
        "net_rs": round(sum(values), 2),
        "win_rate": len(winners) / len(values) if values else None,
        "profit_factor": sum(winners) / -sum(losses) if losses else None,
        "mean_net_rs": round(sum(values) / len(values), 2) if values else None,
        "realized_cash_drawdown_rs": round(drawdown, 2) if values else None,
        "net_without_best_winner_rs": round(sum(values) - max(winners, default=0), 2),
    }


def assess(snapshot: dict, start: date, end: date) -> dict:
    if end < start:
        raise ValueError("end precedes start")
    tables = snapshot["tables"]
    ledger = tables.get("bankroll_ledger") or []
    index = defaultdict(list)
    problems = []
    for r in ledger:
        index[(r.get("source"), r.get("origin_ref"))].append(r)
    books = {}
    known_refs = set()
    for table, prefix in (("fno_positions", "fno_position:"), ("fno_dr_positions", "fno_dr_structure:")):
        for source in ("FNO_PAPER", "FNO_LIVE"):
            key = table + ":" + source
            rows = [r for r in tables.get(table) or [] if r.get("source") == source]
            closed = []
            linked_cash = []
            selected_rows = []
            reported_rows = []
            reported_monthly = defaultdict(list)
            for row in rows:
                ref = prefix + str(row["id"])
                known_refs.add((source, ref))
                events = index[(source, ref)]
                terminal = [e for e in events if e.get("event_type") == "TRADE_CLOSED"]
                cash_events = [e for e in events if e.get("event_type") in ("TRADE_CLOSED", "TRADE_PARTIAL")]
                if row.get("status") == "CLOSED" and finite(row.get("pnl")):
                    try:
                        exit_at = row.get("exit_time", row.get("closed_at"))
                        if start <= day(exit_at) <= end:
                            reported_rows.append((datetime.fromisoformat(exit_at.replace("Z", "+00:00")), row["id"], row["pnl"]))
                            reported_monthly[day(exit_at).isoformat()[:7]].append(row["pnl"])
                    except (ValueError, TypeError, AttributeError):
                        problems.append({"book": key, "ref": ref, "reason": "invalid_position_exit_clock"})
                reason = None
                if row.get("status") == "CLOSED":
                    if len(terminal) != 1:
                        reason = "missing_or_duplicate_terminal_cash"
                    elif not finite(row.get("pnl")) or not finite(terminal[0].get("pnl")):
                        reason = "nonfinite_pnl"
                    elif abs(row["pnl"] - terminal[0]["pnl"]) > .01:
                        reason = "terminal_cash_mismatch"
                    elif not all(finite(row.get(k)) for k in ("gross_pnl", "costs")) or abs(row["gross_pnl"] - row["costs"] - row["pnl"]) > .01:
                        reason = "position_economic_arithmetic_mismatch"
                elif terminal:
                    reason = "terminal_cash_on_nonclosed_position"
                generations = [e.get("settlement_generation") for e in cash_events]
                if len(generations) != len(set(generations)):
                    reason = "duplicate_cash_generation"
                if any(not finite(e.get("pnl")) for e in cash_events):
                    reason = "nonfinite_cash"
                try:
                    clocks = {e["id"]: datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) for e in cash_events}
                    if any(at.tzinfo is None for at in clocks.values()):
                        raise ValueError("naive clock")
                except (ValueError, TypeError, KeyError):
                    reason = "invalid_cash_clock"
                if reason:
                    problems.append({"book": key, "ref": ref, "reason": reason})
                    continue
                for e in cash_events:
                    if start <= day(e["timestamp"]) <= end:
                        linked_cash.append(e)
                if terminal and start <= day(terminal[0]["timestamp"]) <= end:
                    # Entire position lifecycle, including any earlier partials.
                    lifetime = sum(e["pnl"] for e in cash_events)
                    closed.append((terminal[0], lifetime))
                    selected_rows.append({"ref": ref, "terminal_at": terminal[0]["timestamp"],
                                          "lifetime_net_rs": lifetime, "terminal_net_rs": row["pnl"],
                                          "costs_terminal_rs": row["costs"], "exit_reason": row.get("exit_reason"),
                                          "entry_at": row.get("entry_time", row.get("opened_at"))})
            ordering = lambda e: (datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")), e["id"])
            closed.sort(key=lambda pair: ordering(pair[0]))
            linked_cash.sort(key=ordering)
            monthly = defaultdict(list)
            for e in linked_cash:
                monthly[day(e["timestamp"]).isoformat()[:7]].append(e["pnl"])
            books[key] = {
                "evidence_status": "TABLE_ABSENT" if tables.get(table) is None else "RETAINED_OPERATIONAL_HISTORY",
                "retained_positions": len(rows), "open_or_unresolved": sum(r.get("status") != "CLOSED" for r in rows),
                "closed_lifetime_outcomes": metrics([pnl for _, pnl in closed]),
                "window_cash": metrics([e["pnl"] for e in linked_cash]),
                "partial_cash_events": sum(e["event_type"] == "TRADE_PARTIAL" for e in linked_cash),
                "monthly_realized_cash": {m: metrics(v) for m, v in sorted(monthly.items())},
                "closed_rows": selected_rows,
                "reported_terminal_position_pnl_NOT_FULLY_RECONCILED": metrics([pnl for _, _, pnl in sorted(reported_rows)]),
                "reported_terminal_monthly_NOT_FULLY_RECONCILED": {m: metrics(v) for m, v in sorted(reported_monthly.items())},
            }
    unmatched = [e["id"] for e in ledger if e.get("event_type") in ("TRADE_CLOSED", "TRADE_PARTIAL")
                 and (e.get("source"), e.get("origin_ref")) not in known_refs]
    return {
        "schema": "fno_operational_profitability_v1", "start_ist": start.isoformat(), "end_ist": end.isoformat(),
        "collected_at_utc": snapshot.get("collected_at_utc"),
        "assessment": "CURRENT_POLICY_PROFITABILITY_NOT_ESTABLISHED",
        "is_historical_backtest": False, "can_place_orders": False, "can_qualify": False,
        "reconciliation": {"status": "UNAVAILABLE" if tables.get("bankroll_ledger") is None or problems or unmatched else "LINKED_CASH_MATCHES_RETAINED_ROWS",
                           "problems": problems, "unmatched_cash_ids": unmatched},
        "books": books,
        "coverage": {"quote_archive_directory_days": snapshot.get("quote_archive_directory_days", []),
                     "token_candle_coverage": snapshot.get("token_candle_coverage", []),
                     "full_quote_path_completeness": "NOT_VERIFIED"},
        "limitations": ["Operational history spans changing policies/settings; not today's policy replayed backward.",
                        "Reconciliation validates retained arithmetic, not execution realism or market-price provenance.",
                        "Paper settlements are not live fills; legacy spread rows can contain modeled economics.",
                        "Realized cash drawdown excludes intratrade/open-position drawdown; no capital return or Sharpe claimed.",
                        "Closed lifetime outcomes and window cash differ when partial cash crosses window boundaries.",
                        "Empty trade samples are not zero-risk or profitable evidence; no current-policy version attribution."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="/data/cache.db")
    parser.add_argument("--archive-root", default="/data/research")
    parser.add_argument("--container")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--start", default="2026-07-01")
    parser.add_argument("--end", default="2026-10-01")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.container:
        completed = subprocess.run(["docker", "exec", "-i", args.container, "python", "-", "--collect-only",
                                    "--db", args.db, "--archive-root", args.archive_root],
                                   input=Path(__file__).read_text(encoding="utf-8"), text=True,
                                   capture_output=True, check=True, timeout=60)
        snapshot = json.loads(completed.stdout)
    else:
        snapshot = collect(args.db, args.archive_root)
    report = snapshot if args.collect_only else assess(snapshot, date.fromisoformat(args.start), date.fromisoformat(args.end))
    report["evidence_sha256"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        allowed = Path(__file__).resolve().parents[1] / "docs"
        target = args.output.resolve()
        if not target.is_relative_to(allowed) or target.exists():
            raise ValueError("output must be a new file under Dev docs; no overwrites")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"output": str(target), "assessment": report.get("assessment"),
                          "reconciliation": report.get("reconciliation"),
                          "books": {k: v["closed_lifetime_outcomes"] for k, v in report.get("books", {}).items()}}))
    else:
        print(payload)


if __name__ == "__main__":
    main()
