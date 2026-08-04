import asyncio
import os
import time
from typing import Optional
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
        self.token_set_ist_date = None  # [BOOTSTRAP-2026-07-17] see set_token
        self.limiter = RateLimiter(rate=3.0, burst=1)
        self.instrument_cache = {}
        self._cache_lock = asyncio.Lock()
        # KITE_BASE_URL: direct = "https://api.kite.trade" (default); via OCI relay = "http://161.118.160.180:31527"
        # Relay is a path-preserving forward proxy. Auth + X-Kite-Version headers pass through unchanged.
        self.client = httpx.AsyncClient(base_url=settings.KITE_BASE_URL, timeout=15.0)

    def set_token(self, token: str):
        self.access_token = token
        # [BOOTSTRAP-2026-07-17] IST date this token was armed. A non-empty
        # access_token is NOT proof of freshness: on a day with no restart
        # the client still holds yesterday's token, expired at the broker
        # since ~06:00 IST. daily_bootstrap.token_is_fresh_today() compares
        # this stamp against today; the startup-restore path also goes
        # through set_token and only ever restores a same-day token.
        import pytz as _pytz
        self.token_set_ist_date = datetime.now(
            _pytz.timezone("Asia/Kolkata")
        ).date()
        api_key = os.getenv("ZERODHA_API_KEY", "")
        self.client.headers.update({
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{token}"
        })
        # [FIX-PHASE3-AUDIT 2026-07-09] Masked breadcrumb: the armed vs
        # disarmed transition was previously invisible in the logs.
        logger.info(
            "kite_token_set suffix=...%s",
            token[-4:] if token and len(token) >= 4 else "?",
        )

    async def _init_db(self):
        # [PENNY-SQLITE-WAL 2026-07-02] Switch cache.db to WAL mode
        # + busy_timeout=5s. Today's incident: penny_scanner_once
        # held a write lock on cache.db while iterating the universe,
        # and the heartbeat's `health_circuit_query_failed
        # error=database is locked` fired repeatedly because the
        # default sqlite3 busy_timeout is 0 (fail-fast). WAL mode
        # allows concurrent readers + a single writer (vs. the old
        # rollback-journal mode which serialises everyone). 5s
        # busy_timeout gives the writer time to finish a typical
        # commit before the reader gives up.
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    ticker TEXT, date TEXT, open REAL, high REAL, low REAL,
                    close REAL, volume INTEGER, fetched_at TIMESTAMP,
                    PRIMARY KEY (ticker, date)
                )
            """)
            await db.commit()

    async def _init_intraday_db(self):
        # [PENNY-SQLITE-WAL 2026-07-02] Same WAL + busy_timeout
        # enforcement as _init_db. The two tables share the same
        # cache.db file so PRAGMA is idempotent here.
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS intraday_cache (
                    ticker   TEXT,
                    datetime TEXT,
                    open     REAL,
                    high     REAL,
                    low      REAL,
                    close    REAL,
                    volume   REAL,
                    fetched_at TIMESTAMP,
                    PRIMARY KEY (ticker, datetime)
                )
            """)
            await db.commit()




    async def clear_intraday_cache(self):
        """Age out intraday candles past the retention window (midnight, IST).

        [INTRADAY-RETENTION 2026-08-04] This used to delete EVERYTHING before
        yesterday, and that single line is why no intraday strategy in this
        system has ever been validated.

        The deletion was never needed for correctness. get_intraday() already
        bounds its read with `datetime >= from AND datetime <= to` and decides
        freshness from the last candle against `expected_latest`, so stale rows
        can neither be served nor confuse a scan. The purge was pure disk
        management -- and it was throwing away the only record of what the
        market did minute by minute.

        The cost of that: momentum and F&O are intraday strategies whose every
        parameter (stop floor, R target, time-stop window, entry gates) was
        tuned on the handful of live trades the operator happened to take,
        because there was no history to test against. `ohlcv_cache` keeps 2.5
        years of DAILY bars for 4,668 tickers; intraday kept three days. So
        the two strategies that trade every day are precisely the two that
        cannot be backtested, and no amount of parameter work can produce
        evidence that they will not lose money.

        Retaining it is cheap: measured at 2.53 MB/day (94 B/row, ~29k rows
        per session), so a full year is ~633 MB against 17 GB free. That is
        less than the 800 MB of stale cache.db.bak-* files already sitting in
        /data.
        """
        await self._init_intraday_db()
        from datetime import timedelta
        import pytz
        from config import settings

        retention_days = int(getattr(settings, "INTRADAY_RETENTION_DAYS", 365))
        IST = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(IST)
        cutoff = (now_ist - timedelta(days=retention_days)).strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM intraday_cache WHERE datetime < ?",
                (cutoff + " 00:00:00",)
            )
            deleted = cur.rowcount
            await db.commit()
            async with db.execute(
                "SELECT COUNT(*), COUNT(DISTINCT substr(datetime,1,10)) "
                "FROM intraday_cache"
            ) as c2:
                remaining, sessions = await c2.fetchone()

        # Log the corpus size, not just the deletion. This is now a research
        # dataset that grows toward a usable backtest, and "how much history do
        # we have" is the number that decides when a strategy can be evaluated.
        logger.info(
            "intraday_cache_aged_out", cutoff=cutoff, deleted=deleted,
            rows_retained=remaining, sessions_retained=sessions,
            retention_days=retention_days,
        )


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
                                # [INSTRUMENT-CACHE-INT 2026-07-03] Coerce
                                # to int so downstream callsites can do
                                # `kite.instrument_cache.get(symbol)`
                                # and treat the result as a token int.
                                # Pre-fix: stored the raw CSV cell
                                # (a string) and penny_scanner's
                                # `_get_quote_safe(token)` silently
                                # missed the int-keyed /quote response
                                # dict, logging `quote_unavailable` for
                                # 100% of penny tickers even though the
                                # cache was full.
                                raw_token = parts[0].strip('"') if parts[0] else ""
                                try:
                                    self.instrument_cache[symbol] = int(raw_token)
                                except ValueError:
                                    # Malformed row (header line, blank
                                    # row, partial parse). Skip silently.
                                    continue
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

            # [DAILY-CACHE-COVERAGE 2026-07-15] The old `len(rows) >= 60` floor
            # assumed a long (swing / EMA200) window. Momentum requests only
            # ~30 days (~22 trading rows), so 22 < 60 made EVERY momentum daily
            # fetch a cache MISS -> ~500 redundant Kite calls per 30-min scan.
            # That monopolised the 3 req/s limiter and starved the penny scan
            # (the penny_scan_timeout bursts on 2026-07-15). Gate on window
            # COVERAGE instead: require ~80% of the trading days the requested
            # window should contain. A long-window (swing) caller still refuses a
            # momentum-truncated cache (its expected count is high, so a 22-row
            # cache misses and it re-fetches), while momentum's short window hits
            # after the first fetch of the day. Correctness AND load, together.
            try:
                _d0 = datetime.strptime(from_date, "%Y-%m-%d")
                _d1 = datetime.strptime(to_date, "%Y-%m-%d")
                _expected_td = max(1, int((_d1 - _d0).days * 5 / 7))  # ~trading days
                _min_rows = max(2, int(_expected_td * 0.8))
            except (ValueError, TypeError):
                _min_rows = 60  # malformed dates -> fall back to the old floor

            if rows and len(rows) >= _min_rows:
                last_cached_date = rows[-1][0] # Index 0 is 'date'
                
                # [CRIT] FIX: Force a cache miss if the DB doesn't have today's live candle yet!
                if last_cached_date >= to_date:
                    last_fetched_str = rows[-1][6] # fetched_at is index 6
                    try:
                        last_fetched = datetime.strptime(last_fetched_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last_fetched).total_seconds() < 86400:
                            # [LOG-HYGIENE 2026-07-17] debug, not info: the
                            # 30s penny loop emitted ~55k of these per
                            # morning -- 53% of all engine log lines -- and
                            # the volume pushed docker's json-log rotation
                            # past what `docker logs` can read back.
                            # Cache MISSES stay at info (they cost quota).
                            logger.debug("data_fetch", event_type="cache_hit", ticker=ticker)
                            df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'fetched_at'])
                            df.drop(columns=['fetched_at'], inplace=True)
                            df['date'] = pd.to_datetime(df['date'])
                            df.set_index('date', inplace=True)
                            return df
                    except (ValueError, TypeError) as e:
                        # [ROADMAP-4.3 2026-07-13] Genuinely benign -- we fall
                        # through to a live fetch, which is correct. But if the
                        # cache timestamp format ever drifts, EVERY ticker
                        # silently becomes a cache miss and the scan starts
                        # hammering the Kite rate limiter for no visible reason.
                        logger.debug("cache_timestamp_parse_failed",
                                     ticker=ticker, error=str(e))

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
                    # [LOG-HYGIENE 2026-07-17] debug -- see the cache_hit
                    # comment in get_historical.
                    logger.debug("data_fetch", event_type="intraday_cache_hit",
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

        [KITE-QUOTE-RETRY 2026-07-02] Wraps the underlying call with
        exponential-backoff retry on 401/403/429/5xx. Today's incident:
        2,649 kite_quote_failed status=403 events between 09:00-10:30
        IST, every single one an immediate failure with no retry.
        Most 403s from Kite during market open are transient (token
        re-auth mid-session, momentary overload); a single retry with
        0.5s backoff recovers the vast majority. After 3 attempts the
        call is given up and logged at WARNING. Also emits a
        kite_auth_degraded WARNING once when the per-minute failure
        rate exceeds 30 (today hit ~600/min at the peak).
        """
        if isinstance(tokens, (int, str)):
            tokens = [tokens]
        if not tokens:
            return {}
        tokens = [int(t) for t in tokens]

        # Retry config (KITE-QUOTE-RETRY 2026-07-02): 3 attempts,
        # 0.5s -> 1.0s -> 2.0s backoff. Total worst-case wait ~3.5s,
        # which is fine because the penny scanner runs on a 30s cron.
        max_attempts = 3
        backoff = 0.5
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            await self.limiter.acquire()
            try:
                resp = await self.client.get(
                    "/quote",
                    params=[("i", str(t)) for t in tokens],
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                result = {int(k): v for k, v in data.items()}
                if not result and tokens:
                    # [KITE-QUOTE-RETRY] Empty body with 200 OK -- this
                    # is the case today's 2,649 403s turned into. Treat
                    # as transient and retry unless we're on the last
                    # attempt. If still empty after retries, fall through
                    # to the existing failure logger.
                    if attempt < max_attempts:
                        logger.warning(
                            "kite_quote_empty_body_retrying attempt=%d/%d tokens=%d",
                            attempt, max_attempts, len(tokens),
                        )
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    self._log_quote_batch_failure(len(tokens))
                    self._note_quote_rate_failure()
                elif result:
                    self._note_quote_batch_success()
                return result
            except httpx.HTTPStatusError as e:
                last_exc = e
                status = e.response.status_code
                # Retry on 401 (token expired), 403 (rate-limit /
                # momentary overload), 429 (explicit rate-limit), and
                # any 5xx server error.
                if status in (401, 403, 429) or status >= 500:
                    if attempt < max_attempts:
                        logger.warning(
                            "kite_quote_http_retry status=%d attempt=%d/%d tokens=%d",
                            status, attempt, max_attempts, len(tokens),
                        )
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                # [FIX-PHASE3-AUDIT 2026-07-09] Kite returns HTTP 400
                # InputException "Invalid api_key or access_token" for a
                # missing/expired token -- NOT 401/403. On 2026-07-09 this
                # produced 26,311 unexplained status=400 lines. Surface
                # the likely cause so the operator doesn't hunt elsewhere.
                if status == 400:
                    logger.error(
                        "kite_quote_failed status=400 tokens=%d "
                        "hint=likely_invalid_or_missing_access_token "
                        "FIX=log in via Telegram /login (Zerodha token expires daily)",
                        len(tokens),
                    )
                    # [ROADMAP-2.1 2026-07-12] Page the operator too --
                    # deduped to once/hour inside the helper.
                    self._maybe_alert_invalid_token()
                else:
                    logger.error(
                        "kite_quote_failed status=%d tokens=%d",
                        status, len(tokens),
                    )
                self._log_quote_batch_failure(len(tokens))
                self._note_quote_rate_failure()
                return {}
            except httpx.RequestError as e:
                last_exc = e
                if attempt < max_attempts:
                    logger.warning(
                        "kite_quote_request_retry attempt=%d/%d tokens=%d err=%s",
                        attempt, max_attempts, len(tokens), str(e),
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                logger.error(
                    "kite_quote_failed error=%s", str(e),
                )
                self._log_quote_batch_failure(len(tokens))
                self._note_quote_rate_failure()
                return {}
        # Should be unreachable given the loops above, but be defensive.
        if last_exc is not None:
            logger.error("kite_quote_failed_unreachable %s", str(last_exc))
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

    # [KITE-QUOTE-RETRY 2026-07-02] Per-minute failure counter that
    # emits a single kite_auth_degraded WARNING once per minute when
    # the failure rate exceeds the threshold. Today (2026-07-02) the
    # peak was ~600 failures/min between 09:00-10:30 IST; without
    # this latch the operator's log buffer fills with thousands of
    # "kite_quote_failed" ERROR lines and the actual signal (auth is
    # degraded) is invisible.
    #
    # Class-level state so the latch is shared across instances
    # (defensive -- the codebase only constructs one KiteClient, but
    # a future test fixture might construct more).
    _quote_fail_window_start: float = 0.0
    _quote_fail_window_count: int = 0
    _quote_fail_degraded_emitted: bool = False
    KITE_QUOTE_FAIL_RATE_THRESHOLD_PER_MIN = 30

    # [ROADMAP-2.1 2026-07-12] Operator alarm for the invalid/expired-token
    # signature (HTTP 400 InputException). On 2026-07-09 this failure mode
    # produced 26,311 log lines but zero Telegram messages -- the operator
    # found out from the day report. `None` sentinel (not 0.0) because
    # time.monotonic() can be < the dedupe window right after host boot.
    _invalid_token_alert_last_monotonic: Optional[float] = None
    INVALID_TOKEN_ALERT_MIN_INTERVAL_SEC = 3600.0

    def _maybe_alert_invalid_token(self):
        """Fire-and-forget Telegram alert (via node-gateway /api/internal/
        notify) when quote calls start failing with the HTTP-400
        invalid-token signature. Deduped to once per hour so a 400 storm
        produces ONE page, not thousands. Never raises and never blocks
        the caller's error path."""
        now = time.monotonic()
        last = KiteClient._invalid_token_alert_last_monotonic
        if last is not None and (now - last) < KiteClient.INVALID_TOKEN_ALERT_MIN_INTERVAL_SEC:
            return
        KiteClient._invalid_token_alert_last_monotonic = now

        async def _send():
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.CONTAINER_A_URL}/api/internal/notify",
                        json={"message": (
                            "🔑 KITE TOKEN INVALID/EXPIRED\n"
                            "Quote calls are failing with HTTP 400 InputException "
                            "(Zerodha's signature for a missing/expired access token).\n"
                            "All scans are blind until you log in again via the "
                            "/login link. Tokens expire daily ~06:00 IST."
                        )},
                        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET or ""},
                        timeout=5.0,
                    )
            except Exception as e:
                logger.warning("invalid_token_alert_failed error=%s", str(e))

        try:
            asyncio.get_running_loop()
            asyncio.create_task(_send())
        except RuntimeError:
            # No running loop (sync/test context) -- the ERROR log above
            # already carries the hint; skip the Telegram hop.
            pass

    def _note_quote_rate_failure(self) -> None:
        """[KITE-QUOTE-RETRY 2026-07-02] Track per-minute quote
        failure rate and emit a single kite_auth_degraded WARNING
        once per rolling minute when the rate exceeds
        KITE_QUOTE_FAIL_RATE_THRESHOLD_PER_MIN (default 30). Resets
        after 60s of no failures OR when _note_quote_batch_success
        fires.
        """
        now = time.monotonic()
        if (now - KiteClient._quote_fail_window_start) > 60.0:
            KiteClient._quote_fail_window_start = now
            KiteClient._quote_fail_window_count = 0
            KiteClient._quote_fail_degraded_emitted = False
        KiteClient._quote_fail_window_count += 1
        if (
            not KiteClient._quote_fail_degraded_emitted
            and KiteClient._quote_fail_window_count
            >= KiteClient.KITE_QUOTE_FAIL_RATE_THRESHOLD_PER_MIN
        ):
            # [FIX-PHASE3-AUDIT 2026-07-09] Message previously said
            # "401/403/5xx" -- but a missing/expired token surfaces as
            # HTTP 400 InputException, which sent the operator hunting in
            # the wrong direction on 2026-07-09.
            logger.warning(
                "kite_auth_degraded failures_in_last_min=%d "
                "threshold=%d -- Kite quote calls are failing "
                "(HTTP 400 usually means invalid/missing access_token: "
                "log in via Telegram; 401/403/5xx are transient and retried); "
                "signals may be delayed until auth recovers",
                KiteClient._quote_fail_window_count,
                KiteClient.KITE_QUOTE_FAIL_RATE_THRESHOLD_PER_MIN,
            )
            KiteClient._quote_fail_degraded_emitted = True

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

    async def get_instruments_dump(self, segment: str) -> str:
        """
        [FNO 2026-07-10] Fetch a raw instruments CSV dump for any exchange
        segment (e.g. "NFO"). Returns "" on failure -- callers own the
        parse. Deliberately does NOT touch self.instrument_cache: pouring
        60-90k NFO rows into the flat NSE-equity symbol->token dict would
        collide with equity symbols and inflate a cache that already takes
        ~38 min to fill cold (spec §6.1, ops rule 61). fno_instruments
        keeps its own keyed structure instead.
        """
        if not self.access_token:
            logger.warning("kite_instruments_dump_skip segment=%s reason=no_access_token", segment)
            return ""
        await self.limiter.acquire()
        try:
            resp = await self.client.get(f"/instruments/{segment}")
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            # VERIFY-6: this plan 403s the INDICES segment; if NFO also
            # 403s the whole F&O module is dead in the water -- be loud.
            logger.error(
                "kite_instruments_dump_failed segment=%s status=%d "
                "FIX=if 403, the Kite plan may not include %s -- F&O module "
                "cannot run without it",
                segment, e.response.status_code, segment,
            )
            return ""
        except httpx.RequestError as e:
            logger.error("kite_instruments_dump_failed segment=%s error=%s", segment, str(e))
            return ""

    async def get_intraday_by_token(
        self,
        instrument_token: int,
        from_datetime: str,
        to_datetime: str,
        interval: str = "5minute",
    ) -> pd.DataFrame:
        """
        [FNO 2026-07-10] Intraday candles by raw instrument token (the
        symbol->token cache only covers NSE equities, so NFO callers
        resolve their own tokens). No sqlite caching: the F&O signal loop
        re-reads the full session every tick and today's candles change
        every 5 minutes, so a cache would only serve stale bars.
        Returns an empty DataFrame on failure.
        """
        for attempt in range(5):
            await self.limiter.acquire()
            try:
                resp = await self.client.get(
                    f"/instruments/historical/{int(instrument_token)}/{interval}",
                    params={"from": from_datetime, "to": to_datetime},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("candles", [])
                if not data:
                    return pd.DataFrame()
                # Kite appends an OI column for derivatives candles, so the
                # row width must be checked BEFORE constructing the frame.
                cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
                if len(data[0]) > 6:
                    cols = cols + ['oi']
                df = pd.DataFrame(data, columns=cols)
                df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
                df.set_index('datetime', inplace=True)
                return df
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503, 504):
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(
                    "kite_intraday_by_token_failed token=%d status=%d",
                    instrument_token, e.response.status_code,
                )
                return pd.DataFrame()
            except httpx.RequestError:
                await asyncio.sleep(2 ** attempt)
                continue
        logger.error("max_retries_exceeded_intraday_token token=%d", instrument_token)
        return pd.DataFrame()

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

    async def modify_order(
        self,
        order_id: str,
        variety: str = "regular",
        quantity: int = None,
        price: float = None,
        trigger_price: float = None,
        order_type: str = None,
    ) -> dict:
        """
        Modify a pending order in place.
        Kite endpoint: PUT /orders/{variety}/{order_id}
        Returns: {order_id, status}

        [TIER0-0.1 2026-07-14] Needed to ratchet the trigger on a resting SL-M as
        the trail moves. Modifying beats cancel-then-replace: a cancel/place pair
        leaves the position momentarily unprotected, and if the place leg fails we
        are naked with no stop at all.
        """
        if not order_id:
            return {"order_id": None, "status": "ERROR", "message": "order_id required"}
        params = {}
        if quantity is not None:
            params["quantity"] = int(quantity)
        if price is not None:
            params["price"] = float(price)
        if trigger_price is not None:
            params["trigger_price"] = float(trigger_price)
        if order_type is not None:
            params["order_type"] = order_type
        if not params:
            return {"order_id": order_id, "status": "ERROR", "message": "nothing to modify"}

        await self.limiter.acquire()
        try:
            resp = await self.client.put(f"/orders/{variety}/{order_id}", data=params)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {"order_id": data.get("order_id", order_id), "status": "MODIFIED"}
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response.text else ""
            logger.error("kite_modify_order_failed status=%d order_id=%s body=%s",
                         e.response.status_code, order_id, body)
            return {"order_id": order_id, "status": "ERROR",
                    "message": f"HTTP {e.response.status_code}: {body}"}
        except httpx.RequestError as e:
            logger.error("kite_modify_order_failed error=%s", str(e))
            return {"order_id": order_id, "status": "ERROR", "message": str(e)}

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
        Returns: list of dicts, each with status/timestamp/etc., in
                 CHRONOLOGICAL order -- index 0 is the OLDEST event, the
                 current state is the LAST entry.

        [ORDER-HISTORY-2026-07-17] This docstring used to claim "Index 0 is
        the most recent", and three call sites believed it. Zerodha returns
        the history ascending, so history[0] is the initial PUT-ORDER-REQ /
        OPEN event and a filled order NEVER shows COMPLETE at index 0. On
        2026-07-17 the JINDWORLD edge-live entry polled history[0] for 74s,
        declared timeout, and tried to cancel -- every live edge entry since
        2026-07-15 died this way (the accept-watchdog's "entry_status=
        timeout 100%" alarm). Use latest_order_state() to read the current
        status; do not index the list directly.
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

    async def get_broker_positions(self) -> dict:
        """Broker-side positions. Kite endpoint: GET /portfolio/positions.
        Returns {"net": [...], "day": [...]} ({} on failure).

        [ORDER-HISTORY-2026-07-17] Added for post-timeout reconciliation:
        when an entry order's final state cannot be determined (history
        fetch failed, cancel returned "order does not exist"), the last
        word on whether we actually hold stock is the positions book, not
        our bookkeeping. See PennyExecutor.execute_entry."""
        await self.limiter.acquire()
        try:
            resp = await self.client.get("/portfolio/positions")
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return data if isinstance(data, dict) else {}
        except httpx.HTTPStatusError as e:
            logger.error("kite_positions_failed status=%d", e.response.status_code)
            return {}
        except httpx.RequestError as e:
            logger.error("kite_positions_failed error=%s", str(e))
            return {}


def latest_order_state(history: list) -> dict:
    """Current state row of a GET /orders/{id} history response.

    Kite returns rows in CHRONOLOGICAL order (oldest first). Sorting by
    order_timestamp instead of blindly taking [-1] keeps this correct even
    if a relay/proxy ever reorders rows; rows without a timestamp fall back
    to list position. Returns {} for an empty history."""
    if not history:
        return {}
    try:
        return max(
            enumerate(history),
            key=lambda ih: (str(ih[1].get("order_timestamp") or ""), ih[0]),
        )[1]
    except (TypeError, AttributeError):
        return history[-1]
