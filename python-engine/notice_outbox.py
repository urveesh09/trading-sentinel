"""Delivery-failure policy shared by the durable paper-book outboxes.

[OUTBOX-CLASSIFY 2026-10-08, follow-up review F2] The gateway's
``/api/internal/notify`` with ``require_delivery`` answers 422 when Telegram
rejected *this* message (it will never be accepted as is) and 502 for any
other failure. The old step-over heuristic took a second failure in a row as
"gateway down", so two permanently bad notices blocked every healthy one
behind them. With the cause known:

* ``content`` (422): step over the row at once, keep it, retry it on a
  backoff; later notices still go out.
* ``transport`` (network error, timeout, any other HTTP status): stop the
  round so a real outage does not hammer every queued row; order is kept.
* ``unknown`` (any other exception): keep order until the row has failed
  ``STEP_OVER_AFTER`` times, then treat it like ``content``.

A row that is backing off is skipped until it is due, so even unknown or
content failures cannot make each round resend old bad rows. Delivery stays
at-least-once: a crash or lost response after Telegram accepted a message
but before the row is marked sent resends it on the next round.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

STEP_OVER_AFTER = 3
BACKOFF_FIRST = timedelta(minutes=1)
BACKOFF_MAX = timedelta(minutes=30)


def classify_send_failure(exc: BaseException) -> str:
    """``content``, ``transport`` or ``unknown`` for a failed send."""
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        return "content" if exc.response.status_code == 422 else "transport"
    if isinstance(exc, (httpx.TransportError, OSError, asyncio.TimeoutError, TimeoutError)):
        return "transport"
    return "unknown"


def backoff(attempts: int) -> timedelta:
    """Wait before the next try of a stepped-over row after ``attempts`` failures."""
    steps = max(0, attempts - 1)
    return min(BACKOFF_MAX, BACKOFF_FIRST * (2 ** min(steps, 10)))


def is_due(next_attempt_at: Optional[str], now: datetime) -> bool:
    if not next_attempt_at:
        return True
    try:
        return datetime.fromisoformat(next_attempt_at) <= now
    except ValueError:
        return True


def after_failure(kind: str, attempts: int, now: datetime) -> tuple[bool, Optional[str]]:
    """``(continue_round, next_attempt_at)`` after a row's ``attempts``-th failure."""
    if kind == "transport":
        return False, None
    if kind == "content" or attempts >= STEP_OVER_AFTER:
        return True, (now + backoff(attempts)).isoformat()
    return False, None


__all__ = ["STEP_OVER_AFTER", "after_failure", "backoff", "classify_send_failure", "is_due"]
