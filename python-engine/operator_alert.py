"""[OUTAGE-2026-07-13] One way to page the operator.

There are sixteen copies of the same "POST to node-gateway /api/internal/notify"
block scattered across main.py, scheduler_setup.py, token_lifecycle.py,
ops_watchdogs.py, engine_auth.py, kite_client.py and market_calendar.py. This is
not an attempt to unify all of them -- that is a separate change with its own
blast radius. It is the one helper the outage fixes need, written once, with the
property those sixteen copies do not reliably have:

    IT SAYS SOMETHING IN THE LOG WHEN THE PAGE ITSELF FAILS.

On 2026-07-13 the engine ran unarmed for six hours and sent ZERO Telegram
messages. Part of that was watchdog logic (fixed separately); but an alert path
that can fail silently means you cannot even tell the difference between "the
system was healthy" and "the system was screaming into a void". A page that
might vanish without trace is not a page.
"""
from __future__ import annotations

import httpx
import structlog

from config import settings

logger = structlog.get_logger()

NOTIFY_TIMEOUT_SEC = 5.0


async def notify_operator(message: str, *, event: str = "operator_alert") -> bool:
    """Send `message` to the operator via node-gateway's Telegram relay.

    Returns True if node accepted it. Never raises -- an alert that takes down
    the caller is worse than the condition it was reporting.

    Logs at ERROR when delivery fails, so a silent alert path is at least a LOUD
    silent alert path. `docker logs python-engine | grep operator_alert_failed`
    is then the difference between "nothing was wrong" and "we could not tell
    you what was wrong".
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": message},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                timeout=NOTIFY_TIMEOUT_SEC,
            )
            resp.raise_for_status()
        logger.info("operator_alert_sent", event_type=event)
        return True
    except Exception as e:
        logger.error(
            "operator_alert_failed",
            event_type=event,
            error=str(e),
            undelivered_message=message[:200],
        )
        return False
