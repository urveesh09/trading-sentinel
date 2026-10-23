"""[S23-M2 2026-10-23] Every paper book's closed result for one IST day.

The 16:00 digest read only the classic Penny and Nifty books: on Oct 23 it
said "+Rs 0" while Smart V1 made +16.40 and the overnight book lost 494.93
(Oct 23 audit, R23-M2). This reads each book's own store, read-only, and puts
them side by side:

  - main ledger: ``bankroll_ledger`` settlements (TRADE_CLOSED and
    TRADE_PARTIAL) dated that IST day, every division;
  - Smart books: ``EXIT_FILLED`` events per policy, by exit time;
  - overnight book: positions closed that day, plus what it still holds at
    entry value (not marked).

They are separate books with separate capital, so the subtotal (main + Smart
V1 + overnight) is a sum of closed trades, not an account balance or NAV.
Smart V2 is a parallel experiment on its own capital and is never added. A
book that cannot be read is reported as unavailable, never as zero.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_POLICY = "PEN_SMART_V1"


def _ist_day(value) -> Optional[date]:
    """IST date of a stored timestamp; a naive one is UTC (ledger convention)."""
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(IST).date()


def _read(path: str):
    return closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0))


def _main_ledger(db_path: str, day: date) -> dict:
    with _read(db_path) as conn:
        rows = conn.execute(
            "SELECT timestamp, event_type, pnl FROM bankroll_ledger "
            "WHERE event_type IN ('TRADE_CLOSED','TRADE_PARTIAL') AND timestamp >= ?",
            ((day - timedelta(days=1)).isoformat(),)).fetchall()
    picked = [(kind, float(pnl or 0)) for ts, kind, pnl in rows if _ist_day(ts) == day]
    return {"closes": sum(kind == "TRADE_CLOSED" for kind, _ in picked),
            "net": round(sum(pnl for _, pnl in picked), 4)}


def _smart_books(db_path: str, day: date) -> dict:
    from penny_smart_shadow import smart_db_path, smart_policies
    path = smart_db_path(db_path)
    if not os.path.exists(path):
        return {}
    out = {}
    with _read(path) as conn:
        for policy in smart_policies():
            rows = conn.execute(
                "SELECT at, payload_json FROM penny_smart_paper_events "
                "WHERE policy=? AND kind='EXIT_FILLED' AND at >= ?",
                (policy, (day - timedelta(days=1)).isoformat())).fetchall()
            nets = []
            for at, raw in rows:
                if _ist_day(at) != day:
                    continue
                try:
                    nets.append(float(json.loads(raw)["net_pnl"]))
                except (TypeError, ValueError, KeyError):
                    continue
            out[policy] = {"closes": len(nets), "net": round(sum(nets), 4)}
    return out


def _overnight_book(db_path: str, day: date) -> Optional[dict]:
    from edge_overnight_paper import overnight_db_path
    path = overnight_db_path(db_path)
    if not os.path.exists(path):
        return None
    with _read(path) as conn:
        closes, net = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(net_pnl), 0) FROM edge_overnight_paper_trades "
            "WHERE status='CLOSED' AND exit_date=?", (day.isoformat(),)).fetchone()
        held, principal = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(entry_price * shares), 0) FROM edge_overnight_paper_trades "
            "WHERE status='OPEN'").fetchone()
    return {"closes": int(closes), "net": round(float(net), 4), "open": int(held),
            "open_principal": round(float(principal), 2)}


def all_books_day(db_path: str, day: date) -> dict:
    """Closed results of every paper book on ``day`` (IST), read-only."""
    out: dict = {"date": day.isoformat(), "main": None, "smart": {}, "overnight": None, "unavailable": []}
    for name, read in (("main", _main_ledger), ("smart", _smart_books), ("overnight", _overnight_book)):
        try:
            out[name] = read(db_path, day)
        except (sqlite3.Error, OSError) as exc:
            out["unavailable"].append(f"{name}:{type(exc).__name__}")
    parts = [out["main"], out["smart"].get(BASE_POLICY), out["overnight"]]
    out["closed_subtotal"] = round(sum(p["net"] for p in parts if p), 4)
    out["subtotal_complete"] = all(parts)
    return out


def _rs(value: float) -> str:
    return f"Rs {value:+,.2f}"


def _closes(n: int) -> str:
    return f"{n} close" + ("" if n == 1 else "s")


def format_all_books(summary: dict) -> list[str]:
    """Digest lines; each book on its own capital."""
    lines = ["All books today (separate books and capital, not one account):"]
    main = summary.get("main")
    lines.append(f"  Main ledger: {_rs(main['net'])} ({_closes(main['closes'])})" if main
                 else "  Main ledger: unavailable")
    smart = summary.get("smart") or {}
    base = smart.get(BASE_POLICY)
    lines.append(f"  Smart V1: {_rs(base['net'])} ({_closes(base['closes'])})" if base
                 else "  Smart V1: unavailable")
    night = summary.get("overnight")
    if night:
        held = (f"; holding {night['open']}, Rs {night['open_principal']:,.2f} at entry"
                if night["open"] else "; holding none")
        lines.append(f"  Overnight: {_rs(night['net'])} ({_closes(night['closes'])}){held}")
    else:
        lines.append("  Overnight: unavailable")
    note = "" if summary.get("subtotal_complete") else ", partial"
    lines.append(f"  Closed subtotal: {_rs(summary['closed_subtotal'])} (main + Smart V1 + overnight{note})")
    for policy, book in sorted(smart.items()):
        if policy != BASE_POLICY:
            lines.append(f"  {policy.replace('PEN_SMART_', 'Smart ')} (parallel experiment, not added): "
                         f"{_rs(book['net'])} ({_closes(book['closes'])})")
    return lines
