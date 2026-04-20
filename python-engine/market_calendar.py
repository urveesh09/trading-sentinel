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
    """Check if current time is within NSE market hours: 09:15–15:30 IST (inclusive)."""
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
