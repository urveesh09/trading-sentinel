"""[SN477 2026-11-17] Keep the minute research archive quoting the exact contract a paper book holds, until the day's close.

Why: the minute quote collector (research_quote_collector) snapshots a rolling window of strikes around the front future
(RESEARCH_QUOTE_STRIKE_WINDOW either side). A contract a paper book bought near the money drops out of that window once the
market runs far enough, and its exit can no longer be priced from the archive. SN464 found Gold's two largest winners of the
archive window unpriced for exactly this reason (Oct 8 22600 PE, Oct 21 23100 PE). The collector already unions its window
with the exact legs registered in research_leg_subscriptions (the partner advisory uses it); the paper books now register
theirs too.

Research evidence only: no order, delivery or qualification path; a failure is logged and never changes the paper step.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Iterable

import structlog

from config import settings

logger = structlog.get_logger()

EXCHANGE = {"NIFTY": "NFO", "SENSEX": "BFO"}


def deadline_for(now: datetime) -> datetime:
    """15:20 IST of the entry's session: after every paper book's flat time (N11 15:10, Gold's failsafe 15:15)."""
    return now.replace(hour=15, minute=20, second=0, microsecond=0)


async def pin(contracts: Iterable, decision_id: str, now: datetime) -> dict:
    """Register ``contracts`` (fno_models.Contract) for the research collector under ``decision_id``. Never raises."""
    if not (settings.RESEARCH_PIN_PAPER_LEGS and settings.RESEARCH_ARCHIVE_ENABLED):
        return {"state": "off"}
    if not os.path.isdir(settings.RESEARCH_ARCHIVE_PATH):      # no archive on this machine (tests, a bare checkout): nothing to pin
        return {"state": "no_archive"}
    try:
        contracts = [c for c in contracts if c is not None]
        if not contracts:
            return {"state": "nothing"}
        exchange = EXCHANGE.get(str(contracts[0].name).upper())
        if exchange is None:
            return {"state": "unsupported_underlying"}
        from research_leg_subscriptions import ResearchLegSubscriptionStore
        count = await asyncio.to_thread(ResearchLegSubscriptionStore(settings.RESEARCH_ARCHIVE_PATH).register,
                                        decision_id=decision_id, exchange=exchange, contracts=contracts,
                                        management_deadline=deadline_for(now), registered_at=now)
        return {"state": "registered", "legs": count}
    except Exception as exc:
        logger.warning("research_pin_failed", decision_id=decision_id, err=type(exc).__name__)
        return {"state": "unavailable", "reason": type(exc).__name__}
