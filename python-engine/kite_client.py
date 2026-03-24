import asyncio
import os
import time
import httpx
import sqlite3
import pandas as pd
import structlog
from datetime import datetime
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
        self.client = httpx.AsyncClient(base_url="https://api.kite.trade")

    def set_token(self, token: str):
        self.access_token = token
        api_key = os.getenv("ZERODHA_API_KEY", "")
        self.client.headers.update({
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{token}"
        })
    """
    def set_token(self, token: str):
        self.access_token = token
        self.client.headers.update({"X-Kite-Version": "3", "Authorization": f"token {token}"})
    """
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

    async def refresh_instrument_cache(self):
        if not self.access_token:
            return
        async with self._cache_lock:
            try:
                resp = await self.client.get("/instruments/NSE")
                resp.raise_for_status()
                lines = resp.text.split("\n")
                if len(lines) > 1:
                    for line in lines[1:]:
                        parts = line.split(",")
                        if len(parts) > 2:
                            self.instrument_cache[parts[2].strip('"')] = parts[0]
                logger.info("instruments_refreshed", count=len(self.instrument_cache))
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.error("instrument_refresh_failed", error=str(e))

    async def get_historical(self, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
        await self._init_db()
        
        # Check Cache
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT date, open, high, low, close, volume FROM ohlcv_cache WHERE ticker=? AND date >= ? AND date <= ? ORDER BY date",
                (ticker, from_date, to_date)
            )
            rows = await cursor.fetchall()
            if rows and len(rows) >= 60: 
                logger.info("data_fetch", event_type="cache_hit", ticker=ticker)
                df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                return df

        # Cache Miss -> API
        logger.info("data_fetch", event_type="cache_miss", ticker=ticker)
        instrument_token = self.instrument_cache.get(ticker)
        #if ticker=="NIFTY 50":
         #   instrument_token="256265"
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
                if e.response.status_code in (429, 503):
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.RequestError:
                await asyncio.sleep(2 ** attempt)
                continue
        
        logger.error("max_retries_exceeded", ticker=ticker)
        return pd.DataFrame()
