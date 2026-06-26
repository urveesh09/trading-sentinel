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

def is_market_open() -> bool:
    """Check if current time is within NSE market hours: 09:15-15:30 IST (inclusive)."""
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:
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
            logger.warning("holiday_fetch_failed", error=str(e), fallback="weekend_only_check")

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
        # Cache empty = the async job never ran. Log once, return weekend-only.
        # G6 audit note: this is the same fallback the connors engine
        # implicitly had pre-2026-06-25 (just hardcoded weekday check).
        return True
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
