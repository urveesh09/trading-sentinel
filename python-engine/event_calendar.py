"""
[ROADMAP-3.10 2026-07-12] Earnings / corporate-event no-trade windows.

For Indian small-caps, results-day gaps are a top source of
stop-jumping losses: the stop is meaningless when the open prints 12%
through it. No engine had any event awareness; this module adds the
roadmap's "manual quarterly results-calendar CSV" -- deliberately
manual, because there is no reliable free machine-readable earnings
calendar for the NSE small-cap universe, and a curated 30-line CSV the
operator refreshes each results season beats a scraper that silently
rots.

DESIGN (inherited from penny_sector_filter, operator-mandated):
  1. NEVER kill proactiveness for lack of data: missing CSV, malformed
     row, unknown ticker -> ALLOW.
  2. Only a positive match blocks: the ticker IS in the CSV and today
     falls inside [event - EVENT_BLOCK_DAYS_BEFORE,
     event + EVENT_BLOCK_DAYS_AFTER].
  3. The CSV is the operator's curatorial lever, read fresh (with a
     short TTL) so a mid-day edit takes effect within a minute.

CSV format (header optional, ignored if present):
    ticker,event_date,event_type
    SUZLON,2026-07-25,RESULTS
    IDEA,2026-07-28,AGM

Public API:
    event_block(ticker, on_date, csv_path=None) -> (blocked, reason)
    load_event_map(csv_path) -> dict[ticker, list[(date, type)]]
"""
from __future__ import annotations

import csv
import os
import time as _time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import structlog

from config import settings

logger = structlog.get_logger()

# TTL cache: the scanner calls this per ticker per 30s tick; one disk
# read a minute is plenty and keeps mid-day CSV edits live.
_CACHE_TTL_SEC = 60.0
_cache: dict = {"path": None, "loaded_monotonic": None, "events": {}}


def load_event_map(csv_path: str) -> Dict[str, List[Tuple[date, str]]]:
    """Parse the CSV into {TICKER: [(event_date, event_type), ...]}.
    Malformed rows are skipped with a log line, never raised."""
    events: Dict[str, List[Tuple[date, str]]] = {}
    if not csv_path or not os.path.exists(csv_path):
        return events
    try:
        with open(csv_path, newline="") as fh:
            for lineno, row in enumerate(csv.reader(fh), start=1):
                if not row or not row[0].strip():
                    continue
                ticker = row[0].strip().upper()
                if ticker in ("TICKER", "SYMBOL"):
                    continue  # header line
                if len(row) < 2:
                    logger.warning(
                        "event_calendar_bad_row line=%d row=%r", lineno, row
                    )
                    continue
                try:
                    ev_date = datetime.strptime(row[1].strip(), "%Y-%m-%d").date()
                except ValueError:
                    logger.warning(
                        "event_calendar_bad_date line=%d row=%r", lineno, row
                    )
                    continue
                ev_type = row[2].strip().upper() if len(row) > 2 and row[2].strip() else "EVENT"
                events.setdefault(ticker, []).append((ev_date, ev_type))
    except OSError as e:
        logger.warning("event_calendar_read_failed path=%s error=%s", csv_path, str(e))
        return {}
    return events


def _events_cached(csv_path: str) -> Dict[str, List[Tuple[date, str]]]:
    now = _time.monotonic()
    if (
        _cache["path"] == csv_path
        and _cache["loaded_monotonic"] is not None
        and (now - _cache["loaded_monotonic"]) < _CACHE_TTL_SEC
    ):
        return _cache["events"]
    _cache["events"] = load_event_map(csv_path)
    _cache["path"] = csv_path
    _cache["loaded_monotonic"] = now
    return _cache["events"]


def event_block(
    ticker: str, on_date: date, csv_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """(blocked, reason) for entering `ticker` on `on_date`.

    Blocked iff the master toggle is on AND the ticker has a CSV event
    with on_date in [event - EVENT_BLOCK_DAYS_BEFORE,
    event + EVENT_BLOCK_DAYS_AFTER]. Every failure path returns
    (False, "") -- allow."""
    try:
        if not getattr(settings, "PENNY_USE_EVENT_FILTER", True):
            return False, ""
        path = csv_path or settings.EVENT_CALENDAR_CSV_PATH
        events = _events_cached(path)
        if not events:
            return False, ""
        for ev_date, ev_type in events.get((ticker or "").strip().upper(), []):
            start = ev_date - timedelta(days=int(settings.EVENT_BLOCK_DAYS_BEFORE))
            end = ev_date + timedelta(days=int(settings.EVENT_BLOCK_DAYS_AFTER))
            if start <= on_date <= end:
                return True, f"event_window: {ev_type} on {ev_date.isoformat()}"
        return False, ""
    except Exception as e:
        # Rule 1: an event-filter crash must never block (or break) a scan.
        logger.warning("event_block_failed ticker=%s error=%s", ticker, str(e))
        return False, ""
