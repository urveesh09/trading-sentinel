import asyncio
import os
import time
import httpx
import sqlite3
import pandas as pd
import structlog
from datetime import datetime, timedelta, timezone
import aiosqlite
from config import settings

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
        # KITE_BASE_URL: direct = "https://api.kite.trade" (default); via OCI relay = "http://161.118.160.180:31527"
        # Relay is a path-preserving forward proxy. Auth + X-Kite-Version headers pass through unchanged.
        self.client = httpx.AsyncClient(base_url=settings.KITE_BASE_URL, timeout=15.0)

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
                # Fetch NSE instruments only -- INDICES segment returns 403 on this plan
                for segment in ["NSE"]:
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
                
                # [CRIT] FIX: Force a cache miss if the DB doesn't have today's live candle yet!
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
                last_cached_dt = datetime.strptime(rows[-1][0], "%Y-%m-%d %H:%M:%S")
                to_dt_obj      = datetime.strptime(to_datetime,  "%Y-%m-%d %H:%M:%S")
                # Cache is fresh only if the last stored candle covers up to the
                # expected latest complete candle (one interval before scan time).
                # If stale, fall through to API so new candles are fetched.
                expected_latest = to_dt_obj - timedelta(minutes=15)
                if last_cached_dt >= expected_latest:
                    logger.info("data_fetch", event_type="intraday_cache_hit",
                                ticker=ticker, candles=len(rows))
                    df = pd.DataFrame(
                        rows, columns=['datetime','open','high','low','close','volume']
                    )
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                    return df
                logger.info("data_fetch", event_type="intraday_cache_stale",
                            ticker=ticker, last_candle=str(last_cached_dt),
                            expected=str(expected_latest))

        # Cache miss -> API
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

    # ---- 2026-06-22 deviation: 6 methods added that the penny code calls ----
    # See docs/deviations/2026-06-22-kite-client-methods-deviation.md
    # Standard Zerodha Kite Connect API endpoints.

    # [AUDIT-FIX-2.3] Module-level latch so we only emit the CRITICAL
    # log once per process. Reset on a successful batch to surface
    # new failure modes (e.g. auth was working, then expired).
    _quote_batch_fail_emitted: bool = False

    async def get_quote(self, tokens) -> dict:
        """Fetch live quote for one or more instrument tokens.
        Kite endpoint: GET /quote?i={token1}&i={token2}...
        Returns: dict {token_int: {last_price, ohlc, volume, depth, ...}, ...}

        [AUDIT-FIX-2.3 2026-06-25] Whole-batch failures are now loud.
        When the Kite call returns ZERO quotes but the caller asked for
        N>0 tokens, that's a "full batch failure" -- something's wrong
        with the connection/auth/rate-limit. Pre-fix we only logged
        at WARNING per call, which was lost in noise when scanning 100
        tickers. Now the FIRST full-batch failure per process emits a
        CRITICAL log so the operator sees it. Subsequent failures log
        at WARNING (not CRITICAL) to avoid spam.
        """
        if isinstance(tokens, (int, str)):
            tokens = [tokens]
        if not tokens:
            return {}
        tokens = [int(t) for t in tokens]

        await self.limiter.acquire()
        try:
            resp = await self.client.get(
                "/quote",
                params=[("i", str(t)) for t in tokens],
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            result = {int(k): v for k, v in data.items()}
            # [AUDIT-FIX-2.3] Loud on full-batch failure. Per-token
            # partial failures still log at WARNING (existing behaviour);
            # a total empty return for a non-empty request is suspicious
            # and worth a CRITICAL the first time it happens per process.
            if not result and tokens:
                self._log_quote_batch_failure(len(tokens))
            elif result:
                # Successful batch -- reset the latch so the next full
                # failure is loud again.
                self._note_quote_batch_success()
            return result
        except httpx.HTTPStatusError as e:
            logger.error("kite_quote_failed status=%d tokens=%d", e.response.status_code, len(tokens))
            self._log_quote_batch_failure(len(tokens))
            return {}
        except httpx.RequestError as e:
            logger.error("kite_quote_failed error=%s", str(e))
            self._log_quote_batch_failure(len(tokens))
            return {}

    def _log_quote_batch_failure(self, n_tokens: int):
        """[AUDIT-FIX-2.3] Log a full-batch quote failure once at
        CRITICAL level, then at WARNING. Resets to CRITICAL after a
        successful batch (so a new failure mode -- e.g. token expiry --
        is loud again)."""
        if not KiteClient._quote_batch_fail_emitted:
            logger.critical(
                "kite_quote_batch_total_failure "
                "tokens_requested=%d tokens_returned=0 "
                "first_failure_in_process=True",
                n_tokens,
            )
            KiteClient._quote_batch_fail_emitted = True
        else:
            logger.warning(
                "kite_quote_batch_total_failure tokens_requested=%d",
                n_tokens,
            )

    def _note_quote_batch_success(self):
        """[AUDIT-FIX-2.3] Called on any non-empty successful batch.
        Resets the latch so the next full-batch failure is loud again."""
        if KiteClient._quote_batch_fail_emitted:
            logger.info(
                "kite_quote_batch_recovered "
                "next_batch_failure_will_be_critical_again",
            )
            KiteClient._quote_batch_fail_emitted = False

    async def get_instruments_nse_eq(self) -> list:
        """
        Fetch the full NSE equity instruments list.
        Kite endpoint: GET /instruments/NSE (returns CSV)
        Also refreshes self.instrument_cache (symbol -> token).
        """
        await self.limiter.acquire()
        try:
            resp = await self.client.get("/instruments/NSE")
            resp.raise_for_status()
            lines = resp.text.strip().split("\n")
            if len(lines) < 2:
                return []
            headers = lines[0].split(",")
            out = []
            async with self._cache_lock:
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) < len(headers):
                        continue
                    rec = dict(zip(headers, parts))
                    try:
                        token = int(rec.get("instrument_token", "0"))
                    except ValueError:
                        continue
                    sym = rec.get("tradingsymbol", "").strip().upper()
                    if rec.get("segment") == "NSE" and rec.get("instrument_type") == "EQ":
                        out.append({
                            "instrument_token": token,
                            "tradingsymbol": sym,
                            "exchange": rec.get("exchange", "NSE"),
                            "segment": rec.get("segment"),
                            "instrument_type": rec.get("instrument_type"),
                            "name": rec.get("name", ""),
                            "tick_size": float(rec.get("tick_size", "0.05") or "0.05"),
                            "lot_size": int(rec.get("lot_size", "1") or "1"),
                            "series": rec.get("instrument_type", "EQ"),
                        })
                        if sym:
                            self.instrument_cache[sym] = token
            logger.info("instruments_nse_eq_loaded count=%d", len(out))
            return out
        except httpx.HTTPStatusError as e:
            logger.error("kite_instruments_failed status=%d", e.response.status_code)
            return []
        except httpx.RequestError as e:
            logger.error("kite_instruments_failed error=%s", str(e))
            return []

    async def get_corporate_actions(self) -> list:
        """
        Kite Connect does not expose corporate actions via a public endpoint.
        Returns an empty list. Callers (penny_universe.refresh_from_kite) fall
        back to reading from a local penny_company_data.json file per spec §2.4.
        """
        return []

    async def place_order(
        self,
        variety: str = "regular",
        exchange: str = "NSE",
        tradingsymbol: str = "",
        transaction_type: str = "BUY",
        quantity: int = 0,
        product: str = "MIS",
        order_type: str = "MARKET",
        price: float = None,
        trigger_price: float = None,
        validity: str = "DAY",
        tag: str = None,
    ) -> dict:
        """
        Place an order on Kite.
        Kite endpoint: POST /orders/{variety}
        Returns: {order_id, status, message}
        """
        if not tradingsymbol or quantity <= 0:
            return {"order_id": None, "status": "ERROR",
                    "message": "tradingsymbol and positive quantity are required"}
        params = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol.upper(),
            "transaction_type": transaction_type,
            "quantity": int(quantity),
            "product": product,
            "order_type": order_type,
            "validity": validity,
        }
        if price is not None:
            params["price"] = float(price)
        if trigger_price is not None:
            params["trigger_price"] = float(trigger_price)
        if tag:
            params["tag"] = tag

        await self.limiter.acquire()
        try:
            resp = await self.client.post(f"/orders/{variety}", data=params)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "order_id": data.get("order_id"),
                "status": "PLACED",
                "message": "order placed",
            }
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response.text else ""
            logger.error("kite_place_order_failed status=%d body=%s", e.response.status_code, body)
            return {"order_id": None, "status": "ERROR",
                    "message": f"HTTP {e.response.status_code}: {body}"}
        except httpx.RequestError as e:
            logger.error("kite_place_order_failed error=%s", str(e))
            return {"order_id": None, "status": "ERROR", "message": str(e)}

    async def cancel_order(self, order_id: str, variety: str = "regular") -> dict:
        """
        Cancel a pending order.
        Kite endpoint: DELETE /orders/{variety}/{order_id}
        Returns: {order_id, status}
        """
        if not order_id:
            return {"order_id": None, "status": "ERROR", "message": "order_id required"}
        await self.limiter.acquire()
        try:
            resp = await self.client.delete(f"/orders/{variety}/{order_id}")
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {"order_id": data.get("order_id", order_id), "status": "CANCELLED"}
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response.text else ""
            logger.error("kite_cancel_order_failed status=%d order_id=%s body=%s",
                         e.response.status_code, order_id, body)
            return {"order_id": order_id, "status": "ERROR",
                    "message": f"HTTP {e.response.status_code}: {body}"}
        except httpx.RequestError as e:
            logger.error("kite_cancel_order_failed error=%s", str(e))
            return {"order_id": order_id, "status": "ERROR", "message": str(e)}

    async def order_history(self, order_id: str) -> list:
        """
        Fetch the order history (status updates over time).
        Kite endpoint: GET /orders/{order_id}
        Returns: list of dicts, each with status/timestamp/etc.
                 Index 0 is the most recent.
        """
        if not order_id:
            return []
        await self.limiter.acquire()
        try:
            resp = await self.client.get(f"/orders/{order_id}")
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data if isinstance(data, list) else [data]
        except httpx.HTTPStatusError as e:
            logger.error("kite_order_history_failed status=%d order_id=%s",
                         e.response.status_code, order_id)
            return []
        except httpx.RequestError as e:
            logger.error("kite_order_history_failed error=%s", str(e))
            return []
