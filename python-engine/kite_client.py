import asyncio
import os
import time
import httpx
import sqlite3
import pandas as pd
import structlog
from datetime import datetime, timezone
import aiosqlite

logger = structlog.get_logger()

class RateLimiter:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep(1 / self.rate)

class KiteClient:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.access_token = ""
        self.limiter = RateLimiter(rate=3.0, burst=1)
        self.instrument_cache = {}
        self._cache_lock = asyncio.Lock()
        self.client = httpx.AsyncClient(base_url="https://api.kite.trade", timeout=15.0)

    def set_token(self, token: str):
        self.access_token = token
        api_key = os.getenv("ZERODHA_API_KEY", "")
        self.client.headers.update({
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{token}"
        })

    async def _init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    ticker TEXT, date TEXT, open REAL, high REAL, low REAL, 
                    close REAL, volume INTEGER, fetched_at TIMESTAMP,
                    PRIMARY KEY (ticker, date)
                )
            """)
            await db.commit()

    async def _init_intraday_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS intraday_cache (
                    ticker   TEXT,
                    datetime TEXT,
                    open     REAL,
                    high     REAL,
                    low      REAL,
                    close    REAL,
                    volume   INTEGER,
                    fetched_at TIMESTAMP,
                    PRIMARY KEY (ticker, datetime)
                )
            """)
            await db.commit()




    async def clear_intraday_cache(self):
        """Purge yesterday's intraday candles at midnight using explicit IST."""
        await self._init_intraday_db()
        from datetime import timedelta
        import pytz
        IST = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(IST)
        yesterday = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM intraday_cache WHERE datetime < ?",
                (yesterday + " 23:59:59",)
            )
            await db.commit()
        logger.info("intraday_cache_cleared", before=yesterday)


    async def refresh_instrument_cache(self):
        if not self.access_token:
            return
        async with self._cache_lock:
            try:
                # Fetch both NSE and INDICES to ensure NIFTY 50 etc are found
                for segment in ["NSE", "INDICES"]:
                    resp = await self.client.get(f"/instruments/{segment}")
                    resp.raise_for_status()
                    lines = resp.text.split("\n")
                    if len(lines) > 1:
                        for line in lines[1:]:
                            parts = line.split(",")
                            if len(parts) > 2:
                                symbol = parts[2].strip('"').upper()
                                self.instrument_cache[symbol] = parts[0]
                logger.info("instruments_refreshed", count=len(self.instrument_cache))

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.error("instrument_refresh_failed", error=str(e))


    async def get_historical(self, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
        await self._init_db()
        ticker = ticker.upper()
        
        # Check Cache
# Check Cache
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT date, open, high, low, close, volume, fetched_at FROM ohlcv_cache WHERE ticker=? AND date >= ? AND date <= ? ORDER BY date",
                (ticker, from_date, to_date)
            )
            rows = await cursor.fetchall()
            
            if rows and len(rows) >= 60: 
                last_cached_date = rows[-1][0] # Index 0 is 'date'
                
                # 🚨 FIX: Force a cache miss if the DB doesn't have today's live candle yet!
                if last_cached_date >= to_date:
                    last_fetched_str = rows[-1][6] # fetched_at is index 6
                    try:
                        last_fetched = datetime.strptime(last_fetched_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last_fetched).total_seconds() < 86400:
                            logger.info("data_fetch", event_type="cache_hit", ticker=ticker)
                            df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'fetched_at'])
                            df.drop(columns=['fetched_at'], inplace=True)
                            df['date'] = pd.to_datetime(df['date'])
                            df.set_index('date', inplace=True)
                            return df
                    except (ValueError, TypeError):
                        pass

        # async with aiosqlite.connect(self.db_path) as db:
        #     cursor = await db.execute(
        #         "SELECT date, open, high, low, close, volume FROM ohlcv_cache WHERE ticker=? AND date >= ? AND date <= ? ORDER BY date",
        #         (ticker, from_date, to_date)
        #     )
        #     rows = await cursor.fetchall()
        #     if rows and len(rows) >= 60: 
        #         logger.info("data_fetch", event_type="cache_hit", ticker=ticker)
        #         df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        #         df['date'] = pd.to_datetime(df['date'])
        #         df.set_index('date', inplace=True)
        #         return df

        # Cache Miss -> API
        logger.info("data_fetch", event_type="cache_miss", ticker=ticker)
        instrument_token = self.instrument_cache.get(ticker)
        if not instrument_token:
            raise ValueError(f"Unknown ticker: {ticker}")
        
        for attempt in range(5):
            await self.limiter.acquire()
            try:
                resp = await self.client.get(
                    f"/instruments/historical/{instrument_token}/day",
                    params={"from": from_date, "to": to_date}
                )
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("candles", [])
                if not data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                
                # Write to Cache
                async with aiosqlite.connect(self.db_path) as db:
                    for _, row in df.iterrows():
                        await db.execute(
                            "INSERT OR REPLACE INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                            (ticker, row['date'].strftime("%Y-%m-%d"), row['open'], row['high'], row['low'], row['close'], row['volume'])
                        )
                    await db.commit()
                
                df.set_index('date', inplace=True)
                return df

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503, 504):  # 504 = Zerodha gateway timeout, also retried
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.RequestError:
                await asyncio.sleep(2 ** attempt)
                continue
        
        logger.error("max_retries_exceeded", ticker=ticker)
        return pd.DataFrame()

    async def get_intraday(
        self,
        ticker: str,
        from_datetime: str,
        to_datetime: str,
        interval: str = "15minute"
    ) -> pd.DataFrame:
        """
        Fetch intraday candles (15-minute default).
        Cache TTL: current trading day only.
        Cache is invalidated at next day's 00:00 IST.
        
        from_datetime / to_datetime format: "YYYY-MM-DD HH:MM:SS"
        """
        await self._init_intraday_db()
        ticker = ticker.upper()
        trade_date = from_datetime[:10]   # YYYY-MM-DD portion


        # Check cache: only use if all rows are from today
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT datetime, open, high, low, close, volume
                   FROM intraday_cache
                   WHERE ticker=? AND datetime >= ? AND datetime <= ?
                   ORDER BY datetime""",
                (ticker, from_datetime, to_datetime)
            )
            rows = await cursor.fetchall()
            if rows and len(rows) >= 4:   # minimum 4 candles for VWAP
                logger.info("data_fetch", event_type="intraday_cache_hit",
                            ticker=ticker, candles=len(rows))
                df = pd.DataFrame(
                    rows, columns=['datetime','open','high','low','close','volume']
                )
                df['datetime'] = pd.to_datetime(df['datetime'])
                df.set_index('datetime', inplace=True)
                return df

        # Cache miss → API
        logger.info("data_fetch", event_type="intraday_cache_miss", ticker=ticker)
        instrument_token = self.instrument_cache.get(ticker)
        if not instrument_token:
            raise ValueError(f"Unknown ticker: {ticker}")

        for attempt in range(5):
            await self.limiter.acquire()
            try:
                resp = await self.client.get(
                    f"/instruments/historical/{instrument_token}/{interval}",
                    params={"from": from_datetime, "to": to_datetime}
                )
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("candles", [])
                if not data:
                    return pd.DataFrame()

                df = pd.DataFrame(
                    data, columns=['datetime','open','high','low','close','volume']
                )
                df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)

                # Write to intraday cache
                async with aiosqlite.connect(self.db_path) as db:
                    for _, row in df.iterrows():
                        await db.execute(
                            """INSERT OR REPLACE INTO intraday_cache
                               (ticker, datetime, open, high, low, close,
                                volume, fetched_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            (ticker,
                             row['datetime'].strftime("%Y-%m-%d %H:%M:%S"),
                             row['open'], row['high'], row['low'],
                             row['close'], row['volume'])
                        )
                    await db.commit()

                df.set_index('datetime', inplace=True)
                return df

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503, 504):  # 504 = Zerodha gateway timeout, also retried
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.RequestError:
                await asyncio.sleep(2 ** attempt)
                continue

        logger.error("max_retries_exceeded_intraday", ticker=ticker)
        return pd.DataFrame()
