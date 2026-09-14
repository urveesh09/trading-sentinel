"""[WORKFLOW-J.5 2026-09-13] GET /holidays route.

The node-gateway needs the canonical NSE holiday list to decide
whether ``isMarketOpen()`` should return false. Pre-J.5 the
gateway shipped its own list and the two sources diverged (20
Python dates vs 18 Node dates, only 10 overlap). J.5 makes Python
authoritative; this route is the surface Node fetches at boot.

The route is read-only and public (no auth gate) -- the data is
already published on the NSE website. The ``/holidays`` endpoint
follows the same shape as the rest of the engine's read-only
operational state (compare ``/ops/metrics``).
"""
from __future__ import annotations

from fastapi import APIRouter

from market_calendar import (
    NSE_HOLIDAYS_ISO,
    NSE_HOLIDAY_DESCRIPTIONS,
    NSE_HOLIDAYS_STATIC,
    NSE_HOLIDAYS_VALID_THROUGH,
)

router = APIRouter()


@router.get("/holidays")
def get_nse_holidays():
    """Canonical NSE Equity trading holidays for the calendar year.

    Read-only. Returns:

      * ``holidays``: ``[YYYY-MM-DD, ...]`` -- sorted ISO strings.
      * ``descriptions``: ``{"YYYY-MM-DD": "Description", ...}`` --
        human-readable companion table (operator-facing).
      * ``source``: the canonical Python source identifier.
      * ``generated_at_utc``: ISO 8601 UTC timestamp (request-time).

    The Node gateway's ``market-hours.js`` fetches this at boot
    and falls back to its prior hardcoded set ONLY when the
    engine is unreachable (defensive degraded mode).

    See ``docs/2026-09-13-j5-holiday-reconciliation-done.md`` for
    the cross-container flow.
    """
    from datetime import datetime, timezone
    descriptions_iso = {
        d.isoformat(): label
        for d, label in NSE_HOLIDAY_DESCRIPTIONS.items()
    }
    # Sanity: every key in ``descriptions_iso`` must match a holiday.
    holiday_set = set(NSE_HOLIDAYS_ISO)
    extras = [k for k in descriptions_iso if k not in holiday_set]
    if extras:
        # Defensive: a description key without a holiday entry
        # indicates upstream inconsistency. The drift detector
        # owns the long-term check; this guard makes a fault
        # loud at request time.
        raise RuntimeError(
            f"orphan holiday descriptions: {extras}"
        )
    return {
        "holidays": list(NSE_HOLIDAYS_ISO),
        "descriptions": descriptions_iso,
        "count": len(NSE_HOLIDAYS_ISO),
        "valid_through": NSE_HOLIDAYS_VALID_THROUGH,
        "source": (
            "python-engine/market_calendar.py::NSE_HOLIDAYS_STATIC"
        ),
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
    }
