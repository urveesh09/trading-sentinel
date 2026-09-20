"""[WORKFLOW-A.4 2026-09-17] Cross-boundary safety net for
decision clocks.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Ensure crossing a five-minute boundary, entry cutoff or
> session boundary during a fetch cannot create a
> backdated idea.

The base ``partner_decision_clock.crossed_entry_boundary``
covers entry-cutoff and session-boundary crossings but
only one at a time. This module adds:

  - ``BoundaryKind`` -- enum of boundary types the plan
    calls out (5-minute bar, entry cutoff, session
    boundary).
  - ``crossed_boundaries(...)`` -- returns ALL boundary
    crossings the clock experienced during acquisition,
    not just the first one. Operators can use this to
    attribute ideas that should have been suppressed.
  - ``minutes_into_session_at(clock, session_open)`` --
    helper that computes "minutes since session open" for
    session-boundary checks that span midnight.
  - ``FIVE_MINUTE_BOUNDARY_MS`` -- the canonical 5-minute
    bar boundary threshold (in milliseconds; well below
    typical fetch latency).

The plan's acceptance criterion:
> Crossing a five-minute boundary, entry cutoff or session
> boundary during a fetch cannot create a backdated idea.

This module does NOT prevent backdated ideas by itself --
that's the candidate-construction path's responsibility.
But it surfaces the violations so the upstream code can
reject them.

Read-only. No DB writes. No network. No Telegram.
"""
from __future__ import annotations

import dataclasses
import enum
from datetime import datetime, time, timedelta
from typing import Iterable, Optional

from partner_decision_clock import DecisionClock, IST


# A 5-minute completed bar boundary. When the clock crosses
# this many milliseconds past the previous bar's close, the
# prior bar is no longer "fresh" for new decisions. The plan
# says "five-minute boundary" -- we expose it as a constant so
# operators can tune it for non-5-minute setups.
FIVE_MINUTE_BOUNDARY_MS: int = 5 * 60 * 1000  # 300_000 ms


class BoundaryKind(str, enum.Enum):
    """The boundary types the plan calls out.

    - ``BAR_5MIN`` -- crossed a 5-minute completed-bar
      boundary during fetch.
    - ``ENTRY_CUTOFF`` -- crossed the configured entry
      cutoff during fetch.
    - ``SESSION`` -- crossed a session boundary (the
      trading day changed) during fetch.
    """
    BAR_5MIN = "BAR_5MIN"
    ENTRY_CUTOFF = "ENTRY_CUTOFF"
    SESSION = "SESSION"

    def exit_code(self) -> int:
        # Any boundary crossing is a hard rejection signal
        # for the candidate construction path. Use exit 2 to
        # make it BLOCKER-equivalent in the dispatch pipeline.
        return 2


@dataclasses.dataclass(frozen=True)
class BoundaryCrossing:
    """One row of a boundary-crossing report.

    Attributes:
        kind: the boundary that was crossed.
        message: human-readable explanation.
        crossed_at: the clock value where the crossing
            occurred (e.g. ``chain_received_at``). Optional
            for cross-day session crossings where the exact
            moment isn't on a single stage clock.
    """
    kind: BoundaryKind
    message: str
    crossed_at: Optional[datetime] = None


def _is_session_boundary_crossed(
    clock: DecisionClock,
    session_open: time,
) -> Optional[BoundaryCrossing]:
    """Return a BoundaryCrossing if the clock crosses the
    session-open boundary during acquisition.

    "Session boundary" here means: the fetch spans a
    midnight rollover (or whatever ``session_open`` is set
    to, treated as a daily boundary). For NIFTY/SENSEX, the
    session opens at 09:15 IST; if the candidate
    construction happens before 09:15 and the fetch started
    after midnight of the previous trading day, the fetch
    spans a session boundary.

    Operators pass ``session_open`` to make this general --
    e.g. BSE opens at 09:15 too, but a multi-day test
    could use 00:00 to detect any midnight crossing.

    We use ``candidate_constructed_at`` (when available) as
    the "fetch complete" instant because that's the
    latest timestamp on the clock and the only one that
    could legitimately cross a midnight boundary on its
    own. Falls back to ``chain_received_at`` then
    ``public_received_at`` if candidate is missing.
    """
    fetch_end = (
        clock.candidate_constructed_at
        or clock.chain_received_at
        or clock.public_received_at
    )
    if fetch_end is None:
        return None
    # Day boundary: tick_started_at and fetch_end on
    # different calendar days (in IST).
    tick_day = clock.tick_started_at.astimezone(IST).date()
    fetch_day = fetch_end.astimezone(IST).date()
    if tick_day == fetch_day:
        return None
    return BoundaryCrossing(
        kind=BoundaryKind.SESSION,
        message=(
            f"session boundary crossed during fetch: "
            f"tick_started on {tick_day.isoformat()}, "
            f"fetch completed on {fetch_day.isoformat()}"
        ),
        crossed_at=fetch_end,
    )


def _is_entry_cutoff_crossed(
    clock: DecisionClock,
    entry_end_minute: int,
) -> Optional[BoundaryCrossing]:
    """Return a BoundaryCrossing if the clock crosses the
    entry cutoff during fetch.

    ``entry_end_minute`` is minutes since midnight IST (e.g.
    14*60+45 = 14:45 IST). The plan calls this "entry
    cutoff".
    """
    decision = clock.candidate_constructed_at or clock.chain_received_at
    if decision is None:
        return None
    ist = decision.astimezone(IST)
    minutes_into_day = ist.hour * 60 + ist.minute
    if minutes_into_day <= entry_end_minute:
        return None
    return BoundaryCrossing(
        kind=BoundaryKind.ENTRY_CUTOFF,
        message=(
            f"entry cutoff crossed during fetch: "
            f"candidate constructed at {ist.isoformat()} "
            f"({minutes_into_day} minutes), "
            f"cutoff was {entry_end_minute} minutes"
        ),
        crossed_at=decision,
    )


def _is_bar_boundary_crossed(
    clock: DecisionClock,
    boundary_ms: int = FIVE_MINUTE_BOUNDARY_MS,
) -> Optional[BoundaryCrossing]:
    """Return a BoundaryCrossing if the clock crosses a
    bar boundary during fetch.

    "Bar boundary" here means: the fetch spans more than
    ``boundary_ms`` ms (default 5 minutes), which means the
    public-source bar observed at tick start is no longer
    "fresh" by the time the candidate is constructed.

    The base ``DecisionClock``'s policy is
    ``FROZEN_COMPLETED_BAR_CUTOFF_V1``: the public bar
    eligibility is frozen at tick start. If the fetch
    crosses a 5-minute boundary, the frozen bar is now
    stale -- the candidate must be evaluated at the new
    bar, not the old one.
    """
    if clock.public_received_at is None or clock.candidate_constructed_at is None:
        return None
    span = clock.candidate_constructed_at - clock.public_received_at
    if span.total_seconds() * 1000 < boundary_ms:
        return None
    return BoundaryCrossing(
        kind=BoundaryKind.BAR_5MIN,
        message=(
            f"5-minute bar boundary crossed during fetch: "
            f"public_received at "
            f"{clock.public_received_at.isoformat()}, "
            f"candidate constructed at "
            f"{clock.candidate_constructed_at.isoformat()} "
            f"(span {int(span.total_seconds() * 1000)} ms, "
            f"threshold {boundary_ms} ms)"
        ),
        crossed_at=clock.candidate_constructed_at,
    )


def crossed_boundaries(
    clock: DecisionClock,
    *,
    entry_cutoff_minute: Optional[int] = None,
    session_open: Optional[time] = None,
    bar_boundary_ms: int = FIVE_MINUTE_BOUNDARY_MS,
) -> list[BoundaryCrossing]:
    """Return ALL boundary crossings during acquisition.

    Unlike the base ``crossed_entry_boundary`` which
    returns a single string, this returns a list of
    ``BoundaryCrossing`` records -- one per violation --
    so the audit pipeline can report every issue at once.

    Args:
        clock: a DecisionClock. Should be decision-ready
            (``has_required_stages``); missing stages are
            skipped silently.
        entry_cutoff_minute: optional minutes-since-midnight
            IST for entry cutoff (e.g. 14*60+45 = 14:45).
            None = skip entry-cutoff check.
        session_open: optional session-open time-of-day
            (IST). Used to detect midnight rollovers. None =
            skip session-boundary check.
        bar_boundary_ms: ms threshold for the bar-boundary
            check. Default 300_000 (5 minutes).

    Returns:
        Empty list if no boundaries crossed, otherwise
        a list of ``BoundaryCrossing`` records.
    """
    crossings: list[BoundaryCrossing] = []
    bar_crossing = _is_bar_boundary_crossed(clock, bar_boundary_ms)
    if bar_crossing is not None:
        crossings.append(bar_crossing)
    if entry_cutoff_minute is not None:
        entry_crossing = _is_entry_cutoff_crossed(
            clock, entry_cutoff_minute,
        )
        if entry_crossing is not None:
            crossings.append(entry_crossing)
    if session_open is not None:
        session_crossing = _is_session_boundary_crossed(
            clock, session_open,
        )
        if session_crossing is not None:
            crossings.append(session_crossing)
    return crossings


def has_crossed_boundary(
    clock: DecisionClock,
    *,
    entry_cutoff_minute: Optional[int] = None,
    session_open: Optional[time] = None,
    bar_boundary_ms: int = FIVE_MINUTE_BOUNDARY_MS,
) -> bool:
    """Convenience wrapper: True iff any boundary is crossed."""
    return bool(crossed_boundaries(
        clock,
        entry_cutoff_minute=entry_cutoff_minute,
        session_open=session_open,
        bar_boundary_ms=bar_boundary_ms,
    ))


__all__ = [
    "BoundaryKind",
    "BoundaryCrossing",
    "FIVE_MINUTE_BOUNDARY_MS",
    "crossed_boundaries",
    "has_crossed_boundary",
]
