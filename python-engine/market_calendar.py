import aiosqlite
#import aiosqlite
import httpx
import sqlite3
from datetime import date, timedelta, time
import structlog
from datetime import datetime
import pytz

logger = structlog.get_logger()

IST = pytz.timezone("Asia/Kolkata")

# [ROADMAP-3.10 2026-07-12] Static NSE trading-holiday list -- the
# LAST-RESORT fallback when both the DB cache is empty and the
# nseindia.com fetch fails (it routinely bot-blocks). Source: the NSE
# holiday-master API response fetched successfully on 2026-06-15
# (verified against the prod holidays cache). MAINTENANCE: NSE publishes
# the next year's list each December -- refresh this list every January
# (it only matters for fresh deploys / wiped caches; a populated cache
# always wins).
NSE_HOLIDAYS_STATIC = frozenset({
    date(2026, 1, 15), date(2026, 1, 26), date(2026, 2, 15),
    date(2026, 3, 3),  date(2026, 3, 21), date(2026, 3, 26),
    date(2026, 3, 31), date(2026, 4, 3),  date(2026, 4, 14),
    date(2026, 5, 1),  date(2026, 5, 28), date(2026, 6, 26),
    date(2026, 8, 15), date(2026, 9, 14), date(2026, 10, 2),
    date(2026, 10, 20), date(2026, 11, 8), date(2026, 11, 10),
    date(2026, 11, 24), date(2026, 12, 25),
})

# One loud page per process when the static fallback is in use (the
# operator must know the system is running on a baked-in calendar).
_static_fallback_alerted = False


def _alert_static_fallback(reason: str) -> None:
    """Fire-and-forget Telegram warning that the holiday calendar is
    running on the static fallback. Never raises; dedupes per process."""
    global _static_fallback_alerted
    if _static_fallback_alerted:
        return
    _static_fallback_alerted = True
    logger.warning("holiday_static_fallback_active reason=%s", reason)
    try:
        import asyncio

        from config import settings

        async def _send():
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.CONTAINER_A_URL}/api/internal/notify",
                        json={"message": (
                            "📅 HOLIDAY CALENDAR DEGRADED: nseindia.com fetch "
                            f"failed ({reason}) and the DB cache is empty. "
                            "Running on the static 2026 holiday list -- fine "
                            "for 2026, but if it is past 2026 or a special "
                            "session was announced, verify today is a trading "
                            "day yourself."
                        )},
                        headers={
                            "X-Internal-Secret": settings.INTERNAL_API_SECRET or ""
                        },
                        timeout=5.0,
                    )
            except Exception as exc:
                logger.warning("holiday_fallback_alert_failed error=%s", str(exc))

        asyncio.get_running_loop()
        asyncio.create_task(_send())
    except RuntimeError:
        # No running loop (sync caller) -- the log line above still fires.
        pass
    except Exception as exc:
        logger.warning("holiday_fallback_alert_failed error=%s", str(exc))


def is_market_open() -> bool:
    """Check if current time is within NSE market hours: 09:15-15:30 IST
    (inclusive). [ROADMAP-3.10 2026-07-12] Now holiday-aware: previously
    weekday+time only, so every caller believed the market was open on
    NSE holidays. Uses the static list (sync, no DB dependency) -- a
    populated DB cache is consulted by the async is_trading_day();
    callers that need per-date precision should use that."""
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:
        return False
    if now_ist.date() in NSE_HOLIDAYS_STATIC:
        return False
    market_open = time(9, 15)
    market_close = time(15, 30)
    current_time = now_ist.time()
    return market_open <= current_time <= market_close

async def get_holiday_cache(db_path: str) -> list[date]:
    holidays = []
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS holidays (holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)")
            async with db.execute("SELECT holiday_date FROM holidays") as cursor:
                async for row in cursor:
                    holidays.append(date.fromisoformat(row[0]))
    except sqlite3.Error as e:
        logger.error("calendar_db_error", error=str(e))
    return holidays

async def is_trading_day(target_date: date, db_path: str) -> bool:
    if target_date.weekday() >= 5:
        return False

    holidays = await get_holiday_cache(db_path)
    if not holidays:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://www.nseindia.com/api/holiday-master?type=trading", 
                                        headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                async with aiosqlite.connect(db_path) as db:
                    for h in data.get("CBM", []):
                        h_date = datetime.strptime(h["tradingDate"], "%d-%b-%Y").date()
                        holidays.append(h_date)
                        await db.execute("INSERT OR IGNORE INTO holidays (holiday_date, fetched_at) VALUES (?, CURRENT_TIMESTAMP)", (h_date.isoformat(),))
                    await db.commit()
        except (httpx.RequestError, httpx.HTTPStatusError, KeyError) as e:
            # [ROADMAP-3.10 2026-07-12 / HIGH-010] The old fail-open fell
            # back to weekday-only SILENTLY -- the system could run a full
            # trading day on an NSE holiday believing the market was open.
            # Now: static list + one loud operator page per process. The
            # static list is NOT persisted to the DB cache, so the network
            # fetch retries on the next call and a successful fetch
            # replaces the fallback organically.
            logger.warning("holiday_fetch_failed", error=str(e), fallback="static_list")
            _alert_static_fallback(str(e))
            holidays = list(NSE_HOLIDAYS_STATIC)

    return target_date not in holidays

async def next_trading_day(current: date, db_path: str) -> date:
    nxt = current + timedelta(days=1)
    while not await is_trading_day(nxt, db_path):
        nxt += timedelta(days=1)
    return nxt

async def prev_trading_day(current: date, db_path: str) -> date:
    prv = current - timedelta(days=1)
    while not await is_trading_day(prv, db_path):
        prv -= timedelta(days=1)
    return prv


# ---- 2026-06-25 sync helpers for non-async call sites (G6 fix) -----

def _load_holidays_sync(db_path: str) -> list:
    """
    Sync read of the holidays cache. Used by sync exit-decision paths
    that cannot be made async (e.g. penny_engine_connors.evaluate_connors_exit).

    Returns a list of date objects. Empty list = treat as weekend-only.
    Does NOT hit the network -- only the local SQLite cache populated by
    the async is_trading_day() above.
    """
    try:
        with sqlite3.connect(db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS holidays (holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)")
            cur = con.execute("SELECT holiday_date FROM holidays")
            return [date.fromisoformat(r[0]) for r in cur.fetchall()]
    except sqlite3.Error as e:
        logger.error("calendar_sync_load_failed", error=str(e))
        return []


def is_trading_day_sync(target_date: date, db_path: str) -> bool:
    """
    Sync version of is_trading_day. NEVER hits the network.

    Used by sync code paths (penny_engine_connors._trading_days_elapsed,
    penny_engine_breakout.smart_eod_check, etc.) that need to know if a
    given date was an NSE trading day but cannot be made async without
    breaking the existing call contracts.

    Fallback when cache is empty: weekend-only check (slightly looser
    than async is_trading_day but better than nothing).
    """
    if target_date.weekday() >= 5:
        return False
    holidays = _load_holidays_sync(db_path)
    if not holidays:
        # Cache empty = the async job never ran. [ROADMAP-3.10 2026-07-12]
        # Fall back to the static list instead of weekday-only (G6's old
        # behaviour) -- same calendar the async path now degrades to.
        return target_date not in NSE_HOLIDAYS_STATIC
    return target_date not in holidays


def trading_days_between_sync(start: date, end: date, db_path: str) -> int:
    """
    Count trading days strictly between start (exclusive) and end
    (inclusive). Used by penny_engine_connors._trading_days_elapsed
    (replacing the old hardcoded weekday check).

    Sync version uses the local holiday cache. For dates beyond the cache
    horizon, falls back to weekday-only (correct for ~95% of cases since
    NSE has <15 holidays/year).
    """
    if end <= start:
        return 0
    days = 0
    d = start + timedelta(days=1)
    while d <= end:
        if is_trading_day_sync(d, db_path):
            days += 1
        d += timedelta(days=1)
    return days
