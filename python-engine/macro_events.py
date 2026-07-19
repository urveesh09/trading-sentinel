"""
[PARTNER-ENRICH 2026-07-19] Macro event calendar for the partner brief (T3c).

A deliberately dumb, operator-maintained date map: scheduled events that
gut long option premium (IV builds in, then crushes out after the
announcement). The brief warns on event day and the session before it.

MAINTENANCE: this is a static list, not a feed. Extend it when new
schedules are announced (RBI publishes the MPC calendar yearly; the Fed
publishes FOMC dates ~a year ahead). An empty/missing date is silent —
a stale calendar degrades to "no warning", never to a wrong one.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

# date -> short label. Keep labels partner-readable.
# Sources: RBI MPC schedule FY2026-27, FOMC 2026 calendar (verify when
# extending — a wrong date here sends a wrong warning).
MACRO_EVENTS: Dict[str, str] = {
    # RBI MPC decision days (announcement ~10:00 IST)
    "2026-08-06": "RBI MPC decision",
    "2026-10-01": "RBI MPC decision",
    "2026-12-04": "RBI MPC decision",
    # FOMC decision days (statement ~23:30 IST; gap risk NEXT morning)
    "2026-07-29": "US Fed FOMC decision (overnight for India)",
    "2026-09-16": "US Fed FOMC decision (overnight for India)",
    "2026-10-28": "US Fed FOMC decision (overnight for India)",
    "2026-12-09": "US Fed FOMC decision (overnight for India)",
}


def event_note_for(day: date) -> str:
    """Warning line for the morning brief; '' on a no-event day.

    Event day: premium already carries the event — IV crush after the
    announcement routinely eats a "right" directional trade.
    Day before: warns against carrying long premium into the build-up's
    collapse."""
    today = MACRO_EVENTS.get(day.isoformat())
    if today:
        return (
            f"{today} TODAY — IV is bid into the event and crushes after; "
            "long premium can lose even on a right view"
        )
    nxt = MACRO_EVENTS.get((day + timedelta(days=1)).isoformat())
    if nxt:
        return (
            f"{nxt} tomorrow — avoid holding long premium into the event; "
            "IV crush follows the announcement"
        )
    return ""


def next_event(day: date, horizon_days: int = 7) -> Optional[str]:
    """(unused hook) nearest labelled event inside the horizon."""
    for i in range(horizon_days + 1):
        label = MACRO_EVENTS.get((day + timedelta(days=i)).isoformat())
        if label:
            when = "today" if i == 0 else f"in {i}d"
            return f"{label} {when}"
    return None
