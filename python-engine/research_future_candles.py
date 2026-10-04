"""End-of-day index-futures candle recording for research (NIFTY, SENSEX).

The F&O replay needs each session's front-future candles. Until now they were
retained only as a side effect of the trading tick fetching bars, so an
underlying the tick did not evaluate (SENSEX before the growth slice) has no
history. This job asks for the whole session once after the close; the
broker client's by-token cache (``intraday_cache_by_token``, never aged out)
stores it. Read-only market data: no order, sizing or trading-state path.
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List

from config import settings

logger = logging.getLogger(__name__)

RECORDED_INTERVALS = ("5minute", "minute")


def recorded_underlyings() -> List[str]:
    from fno_underlyings import SPECS
    names = [raw.strip().upper() for raw in settings.RESEARCH_ARCHIVE_UNDERLYINGS.split(",") if raw.strip()]
    return [name for name in dict.fromkeys(names) if name in SPECS]


async def record_index_future_candles(kite, now_ist: datetime) -> Dict[str, Any]:
    """Fetch (and thereby cache) today's front-future candles per underlying.

    Returns ``{underlying: {interval: candle_count}}`` plus skip reasons; a
    failure on one underlying never stops the others.
    """
    from fno_underlyings import get_instruments_for
    day = now_ist.date().isoformat()
    result: Dict[str, Any] = {"day": day, "recorded": {}, "skipped": {}}
    for name in recorded_underlyings():
        future = get_instruments_for(name).front_future(now_ist.date())
        if future is None:
            result["skipped"][name] = "front_future_unavailable"
            continue
        counts: Dict[str, int] = {}
        for interval in RECORDED_INTERVALS:
            try:
                frame = await kite.get_intraday_by_token(
                    future.token, f"{day} 09:15:00", f"{day} 15:30:00", interval)
                counts[interval] = 0 if frame is None else len(frame)
            except Exception as exc:  # one failure must not lose the other series
                logger.error("future_candle_record_failed underlying=%s interval=%s err=%s",
                             name, interval, exc)
                counts[interval] = -1
        result["recorded"][name] = {"tradingsymbol": future.tradingsymbol, **counts}
        logger.info("future_candles_recorded underlying=%s symbol=%s counts=%s",
                    name, future.tradingsymbol, counts)
    return result
