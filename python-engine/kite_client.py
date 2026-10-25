import asyncio
import collections
import math
import contextlib
import contextvars
import os
import re
import time
import uuid
from typing import Callable, Optional
import httpx
import background_tasks
import sqlite3
import pandas as pd
import structlog
from datetime import datetime, timedelta, timezone
import aiosqlite
from config import settings
from halt_switch import TradingHalted, assert_not_halted, trip as trip_halt
from owner_entry_halt import is_owner_entry_halted
from order_execution_readiness import (
    is_permission_or_static_ip_rejection,
    mark_authorized as mark_order_execution_authorized,
    mark_blocked as mark_order_execution_blocked,
)
from account_cash_reservations import AccountCashReservations, ReservationRefused

logger = structlog.get_logger()

_LEGACY_INTRADAY_INTERVAL = "legacy_unknown"

# Cache reads and writes share /data/cache.db with the scanners, scheduler,
# and partner advisory jobs.  The default sqlite timeout (5s) is too short for
# the brief writer bursts produced by a full momentum scan; the 2026-09-03
# Production audit recorded two otherwise recoverable ``database is locked``
# failures.  Keep the wait bounded (rather than retrying indefinitely), and
# apply it to every connection opened by this client.
SQLITE_OPERATION_TIMEOUT_SEC = 30.0


def _interval_minutes(interval: str) -> int:
    """Return the candle width used to decide whether a cache is current.

    Kite names its one-minute interval ``minute`` and the wider intraday
    intervals ``3minute``, ``5minute`` ... ``60minute``.  Rejecting unknown
    values here is safer than silently applying the old 15-minute freshness
    rule to a new interval.

    [WORKFLOW-H H4.B 2026-09-13] ``day`` is also supported: ``partner_orchestrator``
    calls ``get_intraday_by_token(..., interval="day")`` for the realised-vol
    computation. A daily candle has no "minute-level" freshness concern; the
    freshness gate for daily uses a 24-hour (1440-minute) window. The §12
    forming-bar filter exempts daily in
    ``_INTERVALS_EXEMPT_FROM_FORMING_FILTER``.
    """
    value = str(interval or "").strip().lower()
    if value == "minute":
        return 1
    if value == "day":
        return 1440
    match = re.fullmatch(r"([1-9][0-9]*)minute", value)
    if match:
        return int(match.group(1))
    raise ValueError(f"unsupported intraday interval: {interval!r}")


# Intervals that are exempt from the §12 completed-bar cutoff filter.
# A daily candle has no "forming" problem in the cache sense: today's
# candle IS the current day, and the same day's row gets overwritten
# on the next fetch. Forcing a forming-bar exclusion on daily would
# drop today's row entirely (datetime == to_datetime), which is wrong.
# Per plan §12: "Do not mix mutable forming bars with completed
# historical bars" -- the intent is intraday bars. Daily is exempt.
_INTERVALS_EXEMPT_FROM_FORMING_FILTER = frozenset({"day"})


def _intraday_cache_gate_evaluate(
    *,
    rows: list,
    to_datetime_str: str,
    interval: str,
    interval_mins: int,
    freshness_seconds: int,
    include_forming: bool,
    min_candles: int,
    source_kind: str,
    source_id: object,
) -> tuple | None:
    """[WORKFLOW-H H4 + H4.B 2026-09-13] Shared HIT-path gate.

    Evaluates the four §12 explicit semantics on a list of raw cache
    rows and returns either ``None`` (no HIT) or a tuple
    ``(filtered_rows, debug_event)``. Caller logs the debug event
    and constructs the DataFrame from filtered_rows.

    The two callers (``get_intraday`` and ``get_intraday_by_token``)
    share this gate so the four semantics can never drift between
    the by-symbol and by-token paths.

    Parameters
    ----------
    rows
        Raw rows from a cache table, ordered by datetime ascending.
        Each row's first column is the ``datetime`` string in the
        ``"%Y-%m-%d %H:%M:%S"`` format.
    to_datetime_str
        The ``to_datetime`` argument the caller passed in.
    interval
        The Kite interval name (``"minute"``, ``"5minute"``, ...).
        Used only for the "exempt from forming filter" check.
    interval_mins
        Numeric candle width (1 for "minute", 5 for "5minute", ...).
    freshness_seconds
        Operator-tunable leniency budget on the freshness gate.
        Negative values are clamped to 0.
    include_forming
        §12 completed-bar cutoff. ``False`` (default) means forming
        candles (``datetime >= to_datetime_str``) are EXCLUDED from
        the returned set. Daily interval is exempt.
    min_candles
        Floor on the returned candle count after the forming-bar
        filter. Below the floor: no HIT.
    source_kind
        ``"ticker"`` or ``"instrument_token"``. Logged only.
    source_id
        The ticker string or instrument_token int. Logged only.

    Returns
    -------
    ``None`` if no HIT. Otherwise ``(filtered_rows, debug_event)``
    where ``debug_event`` is a dict suitable for
    ``logger.debug(..., **debug_event)``.
    """
    if not rows or len(rows) < min_candles:
        return None
    last_cached_dt = datetime.strptime(rows[-1][0], "%Y-%m-%d %H:%M:%S")
    to_dt_obj = datetime.strptime(to_datetime_str, "%Y-%m-%d %H:%M:%S")

    # Freshness gate: the most recent cached candle must cover up
    # to ``to_dt_obj - interval_minutes - freshness_seconds``. The
    # default freshness_seconds=0 matches the strict pre-H4 gate.
    effective_freshness_seconds = max(0, freshness_seconds)
    expected_latest = (
        to_dt_obj
        - timedelta(minutes=interval_mins)
        - timedelta(seconds=effective_freshness_seconds)
    )
    if last_cached_dt < expected_latest:
        return None

    # Completed-bar cutoff: drop forming candles unless the operator
    # has opted in OR the interval is exempt (e.g. daily).
    if include_forming or interval in _INTERVALS_EXEMPT_FROM_FORMING_FILTER:
        filtered_rows = list(rows)
    else:
        filtered_rows = [
            r for r in rows
            if datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") < to_dt_obj
        ]

    if not filtered_rows:
        return (
            [],
            dict(
                event_type="intraday_cache_only_forming",
                source_kind=source_kind, source_id=source_id,
                total_rows=len(rows), forming_rows=len(rows),
            ),
        )
    if len(filtered_rows) < min_candles:
        return (
            [],
            dict(
                event_type="intraday_cache_filtered_below_floor",
                source_kind=source_kind, source_id=source_id,
                raw_rows=len(rows), filtered_rows=len(filtered_rows),
                min_candles=min_candles,
            ),
        )
    return (
        filtered_rows,
        dict(
            event_type="intraday_cache_hit",
            source_kind=source_kind, source_id=source_id,
            candles=len(filtered_rows),
            forming_dropped=len(rows) - len(filtered_rows),
        ),
    )

_PROVIDER_LANES = ("management", "normal", "bulk")
_provider_lane: contextvars.ContextVar[str] = contextvars.ContextVar(
    "kite_provider_lane", default="normal",
)


@contextlib.contextmanager
def provider_lane(lane: str):
    """Run provider calls created in this scope in one limiter lane.

    asyncio tasks copy the current context when they are created, so wrapping
    the creation of a bulk ``gather`` labels every request those tasks make
    without threading a priority argument through each fetch helper.  An
    explicit ``priority=`` on ``RateLimiter.acquire`` still wins.
    """
    if lane not in _PROVIDER_LANES:
        raise ValueError(f"unknown provider lane: {lane}")
    token = _provider_lane.set(lane)
    try:
        yield
    finally:
        _provider_lane.reset(token)


class RateLimiter:
    """Shared token bucket with bounded management priority and a bulk lane.

    Every provider caller uses this one limiter.  Management reads may pass
    ``priority="management"`` so an already-queued research request cannot
    repeatedly win the next token, but ``management_burst`` prevents a steady
    stream of exits from starving lower lanes forever.  Bulk scans (the
    momentum screener's per-ticker fetches) use ``"bulk"``: queued normal work
    is admitted ahead of them, but at most ``normal_burst`` consecutive normal
    admissions occur while bulk waits, so a bulk scan cannot starve either.
    Lanes change ordering only; rate, burst and concurrency are unchanged.
    Waiting is cancellation-safe: a cancelled waiter removes itself before
    another caller is admitted.
    """

    def __init__(self, rate: float, burst: int, *, management_burst: int = 3,
                 normal_burst: int = 3):
        if rate <= 0 or burst < 1 or management_burst < 1 or normal_burst < 1:
            raise ValueError("rate, burst, management_burst and normal_burst must be positive")
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self.management_burst = management_burst
        self.normal_burst = normal_burst
        self._condition = asyncio.Condition()
        self._waiting = {lane: 0 for lane in _PROVIDER_LANES}
        self._management_streak = 0
        self._normal_streak = 0

    def _lane_turn(self) -> Optional[str]:
        """Return the lane entitled to the next token, or None if idle."""
        management = self._waiting["management"] > 0
        normal = self._waiting["normal"] > 0
        bulk = self._waiting["bulk"] > 0
        if management and (not (normal or bulk) or self._management_streak < self.management_burst):
            return "management"
        if normal and (not bulk or self._normal_streak < self.normal_burst):
            return "normal"
        if bulk:
            return "bulk"
        return None

    async def acquire(self, *, priority: Optional[str] = None):
        """Acquire one shared provider token without exceeding ``rate``.

        ``priority`` defaults to the ambient ``provider_lane`` (normal unless a
        caller opted into another lane); an unknown value is treated as normal.
        """
        lane = priority if priority is not None else _provider_lane.get()
        if lane not in _PROVIDER_LANES:
            lane = "normal"
        admitted = False
        async with self._condition:
            self._waiting[lane] += 1
            try:
                while True:
                    now = time.monotonic()
                    elapsed = now - self.last_update
                    self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                    self.last_update = now
                    if self._lane_turn() == lane and self.tokens >= 1:
                        self.tokens -= 1
                        if lane == "management":
                            self._management_streak += 1
                        elif lane == "normal":
                            self._management_streak = 0
                            self._normal_streak += 1
                        else:
                            self._management_streak = 0
                            self._normal_streak = 0
                        admitted = True
                        self._condition.notify_all()
                        return
                    delay = max(0.001, (1.0 - self.tokens) / self.rate)
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        # Token replenishment is time-based; wake and recalculate.
                        pass
            finally:
                self._waiting[lane] -= 1
                if not admitted:
                    self._condition.notify_all()

class EndpointBudget:
    """Per-endpoint provider usage against Kite's documented rate limits.

    [REVIEW-R6 2026-10-08] The shared ``RateLimiter`` allows 3 requests/s on
    every endpoint, while Kite documents quotes at 1/s, historical candles at
    3/s and orders/other endpoints at 10/s. Oct 8 Production logs show no
    429 rejection, so the limiter is not narrowed blindly (that would triple
    quote queueing for expiry, F&O exits and Penny). This records the real
    per-second rate of each endpoint class, the peak, and how many times it
    exceeded the documented limit, and logs (at most once a minute per class)
    when it does, so an endpoint-specific cap can be set from evidence.
    Measurement only: it never delays or refuses a call.
    """

    DOCUMENTED_LIMITS = {"quote": 1, "historical": 3, "order": 10, "other": 10}
    WINDOW_SEC = 1.0
    LOG_EVERY_SEC = 60.0

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time):
        self._clock = clock
        self._wall = wall_clock
        self._recent: dict[str, collections.deque] = {k: collections.deque() for k in self.DOCUMENTED_LIMITS}
        self.calls = {k: 0 for k in self.DOCUMENTED_LIMITS}
        self.peak_per_sec = {k: 0 for k in self.DOCUMENTED_LIMITS}
        self.over_limit = {k: 0 for k in self.DOCUMENTED_LIMITS}
        self._last_log = {k: float("-inf") for k in self.DOCUMENTED_LIMITS}
        self.statuses: dict[str, dict[int, int]] = {}
        self.started_at = datetime.now(timezone.utc).isoformat()
        # [O15-N1] Failures with no HTTP answer (DNS, connect, timeout) and
        # the outage they form: first failure -> next provider answer.
        self.transport_errors: dict[str, dict[str, int]] = {}
        self.current_outage: Optional[dict] = None
        self.recent_outages: collections.deque = collections.deque(maxlen=20)

    def record(self, endpoint: str) -> int:
        """Count one admitted call; return the calls seen in the last second."""
        if endpoint not in self.DOCUMENTED_LIMITS:
            endpoint = "other"
        now = self._clock()
        window = self._recent[endpoint]
        window.append(now)
        while window and now - window[0] >= self.WINDOW_SEC:
            window.popleft()
        current = len(window)
        self.calls[endpoint] += 1
        self.peak_per_sec[endpoint] = max(self.peak_per_sec[endpoint], current)
        limit = self.DOCUMENTED_LIMITS[endpoint]
        if current > limit:
            self.over_limit[endpoint] += 1
            if now - self._last_log[endpoint] >= self.LOG_EVERY_SEC:
                self._last_log[endpoint] = now
                logger.warning("kite_endpoint_over_documented_limit endpoint=%s observed_per_sec=%d "
                               "limit_per_sec=%d over_limit_calls=%d", endpoint, current, limit,
                               self.over_limit[endpoint])
        return current

    def record_status(self, endpoint: str, status: int) -> None:
        """Count a non-2xx provider answer (429 is the rate-limit evidence)."""
        if endpoint not in self.DOCUMENTED_LIMITS:
            endpoint = "other"
        bucket = self.statuses.setdefault(endpoint, {})
        bucket[int(status)] = bucket.get(int(status), 0) + 1
        if int(status) == 429:
            logger.warning("kite_endpoint_http_429 endpoint=%s total=%d", endpoint, bucket[429])

    def record_transport(self, endpoint: str, exc: BaseException) -> str:
        """[O15-N1] Count a call that got no HTTP answer and fold it into the
        current outage. Oct 15 14:57-15:15: DNS failures left 154 instruments
        and 101 expiry decisions without quotes while ``http_errors`` read
        ``{}``. Returns the failure kind."""
        if endpoint not in self.DOCUMENTED_LIMITS:
            endpoint = "other"
        kind = transport_error_kind(exc)
        bucket = self.transport_errors.setdefault(endpoint, {})
        bucket[kind] = bucket.get(kind, 0) + 1
        now = self._wall()
        outage = self.current_outage
        if outage is None:
            outage = self.current_outage = {"start_epoch": now, "failures": 0, "kinds": {},
                                            "endpoints": {}}
            logger.warning("provider_connectivity_lost endpoint=%s kind=%s", endpoint, kind)
        outage["failures"] += 1
        outage["last_failure_epoch"] = now
        outage["kinds"][kind] = outage["kinds"].get(kind, 0) + 1
        outage["endpoints"][endpoint] = outage["endpoints"].get(endpoint, 0) + 1
        return kind

    def record_answer(self) -> None:
        """Any HTTP answer from the provider (2xx or not) ends an outage."""
        outage = self.current_outage
        if outage is None:
            return
        self.current_outage = None
        outage["end_epoch"] = self._wall()
        self.recent_outages.append(outage)
        logger.warning("provider_connectivity_restored outage_sec=%.1f failures=%d kinds=%s",
                       outage["end_epoch"] - outage["start_epoch"], outage["failures"],
                       ",".join(f"{k}:{n}" for k, n in sorted(outage["kinds"].items())))

    def connectivity(self) -> dict:
        return {"current": dict(self.current_outage) if self.current_outage else None,
                "recent": [dict(o) for o in self.recent_outages]}

    def snapshot(self) -> dict:
        return {k: {"calls": self.calls[k], "peak_per_sec": self.peak_per_sec[k],
                    "over_documented_limit": self.over_limit[k], "documented_limit_per_sec": v,
                    "http_errors": {str(code): n for code, n in sorted(self.statuses.get(k, {}).items())},
                    "http_429": self.statuses.get(k, {}).get(429, 0),
                    "transport_errors": dict(sorted(self.transport_errors.get(k, {}).items()))}
                for k, v in self.DOCUMENTED_LIMITS.items()}


_DNS_MARKERS = ("name or service not known", "temporary failure in name resolution",
                "nodename nor servname", "getaddrinfo failed", "no address associated")


def transport_error_kind(exc: BaseException) -> str:
    """``dns`` / ``connect_timeout`` / ``connect`` / ``pool_timeout`` /
    ``timeout`` / ``read`` / ``write`` / ``protocol`` / ``other:<Class>``.

    [T21-X] Oct 21 kept two failures as a bare ``other``. ``pool_timeout`` is
    this process's own connection pool (not the provider); the class name of
    anything else is kept (a class name carries no credential)."""
    import socket
    chain, seen = [], exc
    while seen is not None and len(chain) < 6:
        chain.append(seen)
        seen = seen.__cause__ or seen.__context__
    if any(isinstance(e, socket.gaierror) for e in chain) or any(
            marker in str(e).lower() for e in chain for marker in _DNS_MARKERS):
        return "dns"
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ReadError):
        return "read"
    if isinstance(exc, httpx.WriteError):
        return "write"
    if isinstance(exc, httpx.RemoteProtocolError):
        return "protocol"
    return f"other:{type(exc).__name__}"


class SendWindowGate:
    """[O15-H1 2026-10-15] At most ``limit`` real sends in any
    ``window_sec``, stamped right before the HTTP call.

    The shared limiter admits at 3/s, but an admitted task can be scheduled
    late and then go out next to the following one: Oct 15 recorded 4
    historical calls inside one second (documented 3/s) and one HTTP 504.
    Same idea as the quote ``before_send`` gate. The caller records the
    endpoint and sends with nothing awaited in between.
    """

    def __init__(self, limit: int, window_sec: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_sec = window_sec
        self._clock = clock
        self._sends: collections.deque = collections.deque()
        self.waits = 0

    async def before_send(self) -> float:
        started = self._clock()
        while True:
            now = self._clock()
            while self._sends and now - self._sends[0] >= self.window_sec:
                self._sends.popleft()
            if len(self._sends) < self.limit:
                self._sends.append(now)
                return now - started
            self.waits += 1
            await asyncio.sleep(max(0.001, self._sends[0] + self.window_sec - now))


_LANE_RANK = {"management": 0, "normal": 1, "bulk": 2}


class _TruncatedInstrumentDump(ValueError):
    """An HTTP 200 instrument dump with fewer symbols than a real NSE catalogue."""


class QuoteBatchCancelled(RuntimeError):
    """A merged quote request was cancelled before its response arrived."""


async def _acquire_shared(limiter, lane: Optional[str]) -> None:
    """Shared all-endpoint limiter; tolerates pre-lane test/broker adapters."""
    try:
        await limiter.acquire(priority=lane)
    except TypeError as exc:
        # Small adapters used by replay/tests may expose the pre-S2
        # no-argument contract; only the lane annotation is lost there.
        if "priority" not in str(exc):
            raise
        await limiter.acquire()


class QuoteBudget:
    """Kite's quote budget (1 request/s) with transparent request batching.

    [FOLLOW-UP-F3 2026-10-08] Kite documents 1 quote request per second and
    up to 500 instruments per request, while the shared limiter allows 3/s on
    every endpoint. Concurrent token requests waiting for a slot are merged
    into one call of up to ``MAX_INSTRUMENTS``, each caller receiving only
    its own tokens. The limiter is rebuilt per event loop (tests run several
    loops).

    [O12-Q1 2026-10-12] Admission order is now: the shared all-endpoint
    limiter, then this 1/s quote bucket (priority lanes), then the send, with
    nothing awaited in between. The Oct 9 version took the quote slot first
    and spaced sends with a first-come lock after the shared limiter, so a
    management read could queue behind research at that lock, and the batch
    lane was chosen before the wait (a stale label). Now:

    * priority decides who sends next, and sends stay >= 1/rate apart on the
      endpoint counter's clock (a strict spacing check guards rounding);
    * the batch is built after admission, so everything that arrived during
      the wait is merged, and its lane is the best lane it contains;
    * fairness counts the real waiting callers: after ``FAIRNESS_BURST``
      batches led by a higher lane while a lower-lane request waits, the
      oldest lower-lane request leads the next batch;
    * in-flight batches are tracked, and a cancelled batch hands every
      waiting caller ``QuoteBatchCancelled`` instead of leaving it hanging.

    [O13-Q1 2026-10-15] Spacing is enforced at the send itself.
    ``before_send`` runs on the same path as the endpoint counter and the
    HTTP call, with nothing awaited between them, for every attempt (merged
    batches, retries and instrument-keyed calls). Admission alone could not
    guarantee it: the batch runs as a new task, and an event-loop stall
    between admission and that task let two sends go out ~2 ms apart (Oct 13:
    one over-limit quote call after the 11:40 restart, two in the morning
    process). Admission also waits for the last real send.

    [O13-Q2 2026-10-15] A dispatcher that is cancelled or fails while
    waiting for admission hands every queued caller the outcome
    (``QuoteBatchCancelled`` or the error) instead of leaving it pending.
    """

    MAX_INSTRUMENTS = 500
    FAIRNESS_BURST = 3
    SPACING_MARGIN_SEC = 0.002

    def __init__(self, rate: float = 1.0):
        self.rate = rate
        self._limiter: Optional[RateLimiter] = None
        self._loop = None
        self._pending: list = []
        self._dispatcher: Optional[asyncio.Task] = None
        self._inflight: set = set()
        self._seq = 0
        self._streak = 0
        self._last_dispatch = float("-inf")
        self._last_send = float("-inf")
        self.batches = 0
        self.merged_requests = 0
        self.max_wait_sec = {lane: 0.0 for lane in _LANE_RANK}
        self.spacing_waits = 0
        self.fairness_promotions = 0
        self.cancelled_batches = 0
        self.send_gate_waits = 0
        self.cancelled_queued = 0

    def limiter(self) -> RateLimiter:
        loop = asyncio.get_running_loop()
        if self._limiter is None or self._loop is not loop:
            self._limiter, self._loop = RateLimiter(rate=self.rate, burst=1), loop
            self._pending, self._dispatcher, self._inflight = [], None, set()
            self._last_dispatch = self._last_send = float("-inf")
        return self._limiter

    def _interval(self) -> float:
        return 1.0 / self.rate + self.SPACING_MARGIN_SEC

    async def before_send(self) -> float:
        """Hold one ``/quote`` HTTP attempt until it is >= 1/rate after the
        previous send, then stamp it. The caller records the endpoint and
        sends with nothing awaited in between. Returns seconds waited."""
        self.limiter()
        started = time.monotonic()
        wait = self._last_send + self._interval() - started
        while wait > 0:
            self.send_gate_waits += 1
            await asyncio.sleep(wait)
            wait = self._last_send + self._interval() - time.monotonic()
        self._last_send = time.monotonic()
        return self._last_send - started

    async def admit(self, shared, lane: Optional[str] = None) -> float:
        """Admit one ``/quote`` HTTP attempt; the caller sends immediately.

        ``lane`` None uses the ambient ``provider_lane``. Returns the seconds
        spent waiting (shared limiter + quote bucket + spacing).
        """
        started = time.monotonic()
        if shared is not None:
            await _acquire_shared(shared, lane)
        await self.limiter().acquire(priority=lane)
        wait = max(self._last_dispatch, self._last_send) + self._interval() - time.monotonic()
        while wait > 0:
            self.spacing_waits += 1
            await asyncio.sleep(wait)
            wait = max(self._last_dispatch, self._last_send) + self._interval() - time.monotonic()
        self._last_dispatch = time.monotonic()
        return self._last_dispatch - started

    async def submit(self, fetch, tokens: list, lane: str, shared=None) -> tuple:
        """Queue ``tokens``; the dispatcher merges queued requests per slot."""
        self.limiter()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._seq += 1
        self._pending.append((_LANE_RANK.get(lane, 1), self._seq, lane, tokens, future, time.monotonic()))
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = loop.create_task(self._dispatch(fetch, shared))
        return await future

    def _order(self) -> tuple[list, bool]:
        """Live requests in send order and whether fairness promoted one."""
        live = sorted((item for item in self._pending if not item[4].done()),
                      key=lambda item: (item[0], item[1]))
        self._pending = live
        if live and self._streak >= self.FAIRNESS_BURST:
            lower = [item for item in live if item[0] > live[0][0]]
            if lower:
                oldest = min(lower, key=lambda item: item[1])
                return [oldest] + [item for item in live if item is not oldest], True
        return live, False

    async def _dispatch(self, fetch, shared) -> None:
        try:
            await self._dispatch_loop(fetch, shared)
        except BaseException as exc:                  # noqa: BLE001 - no queued caller may hang
            failure = exc if isinstance(exc, Exception) else QuoteBatchCancelled(
                "quote dispatcher cancelled before this request was sent")
            waiting = [item for item in self._pending if not item[4].done()]
            self._pending = []
            for item in waiting:
                item[4].set_exception(failure)
            if not isinstance(exc, Exception):
                self.cancelled_queued += len(waiting)
                raise
            logger.warning("kite_quote_dispatcher_failed err=%s queued=%d", type(exc).__name__, len(waiting))

    async def _dispatch_loop(self, fetch, shared) -> None:
        loop = asyncio.get_running_loop()
        while True:
            order, _promoted = self._order()
            if not order:
                return
            await self.admit(shared, order[0][2])
            admitted_at = time.monotonic()
            order, promoted = self._order()
            if not order:
                return                                 # every waiter left; the slot goes unused
            batch, merged, seen = [], [], set()
            for item in order:
                new = [t for t in item[3] if t not in seen]
                if batch and len(merged) + len(new) > self.MAX_INSTRUMENTS:
                    continue
                batch.append(item)
                merged.extend(new)
                seen.update(new)
            taken = {id(item) for item in batch}
            self._pending = [item for item in self._pending if id(item) not in taken]
            lane = min((item[2] for item in batch), key=lambda name: _LANE_RANK.get(name, 1))
            if promoted:
                self.fairness_promotions += 1
                self._streak = 0
            elif any(item[0] > batch[0][0] for item in self._pending):
                self._streak += 1
            else:
                self._streak = 0
            for item in batch:
                self.max_wait_sec[item[2]] = max(self.max_wait_sec.get(item[2], 0.0), admitted_at - item[5])
            self.batches += 1
            self.merged_requests += len(batch)
            task = loop.create_task(self._run(fetch, batch, merged, lane, admitted_at))
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)

    async def _run(self, fetch, batch, merged, lane, admitted_at) -> None:
        try:
            result, timing = await fetch(merged, lane)
        except BaseException as exc:                  # noqa: BLE001 - hand the outcome to every caller
            failure = exc if isinstance(exc, Exception) else QuoteBatchCancelled(
                "quote batch cancelled before its response")
            for item in batch:
                if not item[4].done():
                    item[4].set_exception(failure)
            if not isinstance(exc, Exception):
                self.cancelled_batches += 1
                raise
            return
        finished = time.monotonic()
        for item in batch:
            if item[4].done():
                continue
            mine = {t: result[t] for t in item[3] if t in result}
            # quote_batch_wait_sec is the queue wait up to admission (no
            # transport); quote_batch_elapsed_sec runs to the response. The
            # caller's own admission wait also counts as its limiter wait.
            queued = admitted_at - item[5]
            item[4].set_result((mine, {**timing,
                                       "limiter_wait_sec": round(float(timing.get("limiter_wait_sec") or 0.0)
                                                                 + queued, 6),
                                       "quote_batch_wait_sec": round(queued, 6),
                                       "quote_batch_elapsed_sec": round(finished - item[5], 6),
                                       "quote_batch_lane": lane,
                                       "quote_batch_requests": len(batch),
                                       "quote_batch_instruments": len(merged)}))

    def snapshot(self) -> dict:
        return {"rate_per_sec": self.rate, "batches": self.batches, "merged_requests": self.merged_requests,
                "spacing_waits": self.spacing_waits, "fairness_promotions": self.fairness_promotions,
                "cancelled_batches": self.cancelled_batches, "cancelled_queued": self.cancelled_queued,
                "send_gate_waits": self.send_gate_waits, "in_flight": len(self._inflight),
                "max_wait_sec": {lane: round(v, 3) for lane, v in self.max_wait_sec.items()}}


_SUMMED_TIMING = ("limiter_wait_sec", "transport_sec", "parse_sec", "retry_backoff_sec",
                  "attempt_count", "retry_count")


def _aggregate_chunk_timing(parts: list) -> dict:
    """Timing of a request split into ``MAX_INSTRUMENTS`` chunks.

    Waits, transport and attempts add up across chunks; batch sizes are the
    largest single request (never a sum, so they still describe one HTTP
    call); queue waits are the longest chunk's.
    """
    out: dict = {"chunks": len(parts)}
    for part in parts:
        for key, value in part.items():
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            if key in _SUMMED_TIMING and numeric:
                out[key] = round(out.get(key, 0) + value, 6)
            elif numeric:
                out[key] = max(out.get(key, value), value)
            else:
                out.setdefault(key, value)
    return out


def _record_endpoint(client, endpoint: str) -> None:
    """Count a dispatched provider call (tolerates bare test doubles)."""
    budget = getattr(client, "endpoint_budget", None)
    if budget is not None:
        budget.record(endpoint)


def _record_status(client, endpoint: str, status: int) -> None:
    budget = getattr(client, "endpoint_budget", None)
    if budget is not None:
        budget.record_status(endpoint, status)
        if hasattr(budget, "record_answer"):
            budget.record_answer()


def _record_answer(client) -> None:
    """A provider HTTP answer arrived (ends a connectivity outage)."""
    budget = getattr(client, "endpoint_budget", None)
    if budget is not None and hasattr(budget, "record_answer"):
        budget.record_answer()


def _record_transport(client, endpoint: str, exc: BaseException) -> None:
    """[O15-N1] A call that got no HTTP answer (DNS/connect/timeout)."""
    budget = getattr(client, "endpoint_budget", None)
    if budget is not None and hasattr(budget, "record_transport"):
        budget.record_transport(endpoint, exc)


async def _historical_send_gate(client) -> None:
    gate = getattr(client, "historical_gate", None)
    if gate is not None:
        await gate.before_send()


class KiteClient:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.access_token = ""
        self.token_set_ist_date = None  # [BOOTSTRAP-2026-07-17] see set_token
        self.limiter = RateLimiter(rate=3.0, burst=1)
        self.endpoint_budget = EndpointBudget()
        # 3/s documented, with a small margin for provider-side clock jitter.
        self.historical_gate = SendWindowGate(limit=3, window_sec=1.05)
        self.quote_budget = QuoteBudget(rate=float(getattr(settings, "KITE_QUOTE_RATE_PER_SEC", 1.0)))
        self.instrument_cache = {}
        self._cache_lock = asyncio.Lock()
        # P1 uses the same durable file as Node's gateway.  ``:memory:`` is
        # retained for isolated tests; production config resolves to /data.
        self.account_cash_reservations = AccountCashReservations(db_path)
        # KITE_BASE_URL: direct = "https://api.kite.trade" (default); via OCI relay = "http://161.118.160.180:31527"
        # Relay is a path-preserving forward proxy. Auth + X-Kite-Version headers pass through unchanged.
        self.client = httpx.AsyncClient(base_url=settings.KITE_BASE_URL, timeout=15.0)
        # [O25] Order writes leave from the registered static IP when
        # KITE_ORDER_BASE_URL names one (the relay); None = the client above.
        order_url = (getattr(settings, "KITE_ORDER_BASE_URL", "") or "").strip().rstrip("/")
        self.order_client = (httpx.AsyncClient(base_url=order_url, timeout=15.0)
                             if order_url and order_url != settings.KITE_BASE_URL.rstrip("/") else None)

    @property
    def _orders_http(self) -> httpx.AsyncClient:
        """The client for place, modify and cancel (Kite checks their static IP)."""
        return self.order_client or self.client

    def _cache_db(self):
        """Return a cache connection with a contention-safe bounded wait."""
        return aiosqlite.connect(
            self.db_path, timeout=SQLITE_OPERATION_TIMEOUT_SEC,
        )

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
        for http in (self.client, self.order_client):
            if http is not None:
                http.headers.update({
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
        # + a bounded busy timeout. Today's incident: penny_scanner_once
        # held a write lock on cache.db while iterating the universe,
        # and the heartbeat's `health_circuit_query_failed
        # error=database is locked` fired repeatedly because the
        # default sqlite3 busy_timeout is 0 (fail-fast). WAL mode
        # allows concurrent readers + a single writer (vs. the old
        # rollback-journal mode which serialises everyone). A bounded
        # 30s busy_timeout gives a bursty scanner writer time to finish
        # before the caller gives up.
        async with self._cache_db() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                f"PRAGMA busy_timeout={int(SQLITE_OPERATION_TIMEOUT_SEC * 1000)}"
            )
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
        async with self._cache_db() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                f"PRAGMA busy_timeout={int(SQLITE_OPERATION_TIMEOUT_SEC * 1000)}"
            )
            await db.execute("PRAGMA synchronous=NORMAL")
            # [WORKFLOW-H H4.B 2026-09-13] The by-token cache
            # table is created here alongside the by-symbol one.
            # F&O candles include an OI column (open interest),
            # which the by-symbol path does not store. PRIMARY KEY
            # is (instrument_token, interval, datetime) to match
            # the by-symbol PRIMARY KEY shape (ticker, interval,
            # datetime) -- never the two keys mixed.
            await self._create_intraday_cache_by_token_table(db)
            # `interval` was absent from the original schema even though this
            # client stores both one-minute Penny bars and 15-minute Momentum
            # bars.  The old (ticker, datetime) key allowed one resolution to
            # overwrite and later masquerade as the other.
            #
            # Migrate transactionally and conservatively.  A legacy ticker-day
            # containing any non-quarter-hour timestamp can only have come from
            # a one-minute fetch, so that whole coherent fetch is recoverable as
            # `minute`.  Quarter-hour-only groups are ambiguous and are retained
            # as `legacy_unknown`; they are deliberately never served for a
            # known interval, forcing one clean broker refetch rather than using
            # potentially mislabelled market data.  Re-running this initializer
            # sees the new column and is a no-op.
            cursor = await db.execute("PRAGMA table_info(intraday_cache)")
            columns = [row[1] for row in await cursor.fetchall()]
            if columns and "interval" in columns:
                return

            # Only the first initialization/migration needs a writer lock. The
            # Penny scanner calls this method concurrently for many tickers; a
            # BEGIN IMMEDIATE on the already-current hot path would serialize
            # every cache read for no benefit.
            await db.execute("BEGIN IMMEDIATE")
            try:
                # Another connection may have completed the migration while we
                # waited for the lock, so re-check under the transaction.
                cursor = await db.execute("PRAGMA table_info(intraday_cache)")
                columns = [row[1] for row in await cursor.fetchall()]
                if not columns:
                    await self._create_intraday_cache_table(db)
                elif "interval" not in columns:
                    await db.execute(
                        "ALTER TABLE intraday_cache "
                        "RENAME TO intraday_cache_pre_interval"
                    )
                    await self._create_intraday_cache_table(db)
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO intraday_cache
                            (ticker, interval, datetime, open, high, low, close,
                             volume, fetched_at)
                        SELECT old.ticker,
                               CASE WHEN EXISTS (
                                   SELECT 1
                                   FROM intraday_cache_pre_interval AS probe
                                   WHERE probe.ticker = old.ticker
                                     AND substr(probe.datetime, 1, 10) =
                                         substr(old.datetime, 1, 10)
                                     AND CAST(substr(probe.datetime, 15, 2) AS INTEGER)
                                         NOT IN (0, 15, 30, 45)
                               ) THEN 'minute' ELSE ? END,
                               old.datetime, old.open, old.high, old.low,
                               old.close, old.volume, old.fetched_at
                        FROM intraday_cache_pre_interval AS old
                        """,
                        (_LEGACY_INTRADAY_INTERVAL,),
                    )
                    await db.execute("DROP TABLE intraday_cache_pre_interval")
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    @staticmethod
    async def _create_intraday_cache_table(db) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS intraday_cache (
                ticker   TEXT NOT NULL,
                interval TEXT NOT NULL DEFAULT 'legacy_unknown',
                datetime TEXT NOT NULL,
                open     REAL,
                high     REAL,
                low      REAL,
                close    REAL,
                volume   REAL,
                fetched_at TIMESTAMP,
                PRIMARY KEY (ticker, interval, datetime)
            )
        """)

    @staticmethod
    async def _create_intraday_cache_by_token_table(db) -> None:
        """[WORKFLOW-H H4.B 2026-09-13] The by-token cache table.

        Sibling of ``intraday_cache`` keyed on ``instrument_token``
        instead of ``ticker``. The two tables NEVER share rows:
        the by-token path is for NFO/F&O contracts whose symbol
        cache (``self.instrument_cache``) covers NSE equities only,
        and the by-symbol path is for cash equity Penny scanners.

        The ``oi`` (open-interest) column is by-token-only because
        F&O candles include OI; the by-symbol path does not.

        PRIMARY KEY shape mirrors the by-symbol path
        ``(instrument_token, interval, datetime)`` so §12 four
        semantics (instrument + interval + completed-bar cutoff +
        freshness) are honoured on the same gate contract.
        """
        await db.execute("""
            CREATE TABLE IF NOT EXISTS intraday_cache_by_token (
                instrument_token INTEGER NOT NULL,
                interval         TEXT NOT NULL,
                datetime         TEXT NOT NULL,
                open             REAL,
                high             REAL,
                low              REAL,
                close            REAL,
                volume           REAL,
                oi               REAL,
                fetched_at       TIMESTAMP,
                PRIMARY KEY (instrument_token, interval, datetime)
            )
        """)




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

        async with self._cache_db() as db:
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


    # [O9-R1 2026-10-09] On Oct 9 the 11:19 restart hit a DNS failure on the
    # one-shot startup refresh. The cache stayed EMPTY for the rest of the
    # session (the only other refresh is the 08:00 cron), which blinded
    # Momentum, Penny, Smart exits and the overnight entry. A refresh failure
    # now (a) falls back to the last good snapshot on /data -- NSE equity
    # tokens are stable day to day -- and (b) is retried by
    # ensure_instrument_cache() on a short market-hours cadence until a
    # provider refresh succeeds. The status is published on /health.
    INSTRUMENT_SNAPSHOT_MAX_AGE_DAYS = 7
    INSTRUMENT_SNAPSHOT_MAX_SKEW_SEC = 300   # a saved_at later than now + this is refused
    INSTRUMENT_CACHE_MIN_SIZE = 1000   # a real NSE dump is ~9,000 symbols

    def _instrument_snapshot_path(self) -> Optional[str]:
        if not self.db_path or self.db_path == ":memory:":
            return None
        return os.path.join(os.path.dirname(self.db_path) or ".", "nse_instrument_cache.json")

    def _instrument_status(self) -> dict:
        status = getattr(self, "_instrument_cache_status", None)
        if status is None:
            status = {"source": "EMPTY", "provider_refreshed_at": None, "snapshot_date": None,
                      "last_attempt_at": None, "last_error_type": None, "failures": 0}
            self._instrument_cache_status = status
        return status

    def instrument_cache_status(self) -> dict:
        """Read-only view for /health and the readiness watchdog."""
        status = dict(self._instrument_status())
        status["size"] = len(self.instrument_cache)
        status["usable"] = status["size"] >= self.INSTRUMENT_CACHE_MIN_SIZE
        return status

    def _save_instrument_snapshot(self, mapping: dict) -> None:
        path = self._instrument_snapshot_path()
        if path is None:
            return
        tmp = path + ".tmp"
        try:
            import json as _json
            with open(tmp, "w", encoding="utf-8") as fh:
                _json.dump({"saved_at": datetime.now(timezone.utc).isoformat(), "tokens": mapping}, fh)
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("instrument_snapshot_save_failed error_type=%s", type(exc).__name__)

    def _load_instrument_snapshot(self) -> bool:
        """Fill an EMPTY cache from the last good snapshot. Never overwrites provider data."""
        path = self._instrument_snapshot_path()
        if path is None or self.instrument_cache or not os.path.exists(path):
            return False
        try:
            import json as _json
            with open(path, encoding="utf-8") as fh:
                saved = _json.load(fh)
            saved_at = datetime.fromisoformat(saved["saved_at"])
            tokens = {str(k).upper(): int(v) for k, v in saved["tokens"].items()}
            # [O12-C2 2026-10-12] A naive clock made the age subtraction below
            # raise outside this handler, and a future clock passed the age
            # check with a negative age. Both are refused here.
            if saved_at.tzinfo is None or saved_at.utcoffset() is None:
                raise ValueError("snapshot saved_at has no timezone")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
            logger.warning("instrument_snapshot_unreadable error_type=%s", type(exc).__name__)
            return False
        age_days = (datetime.now(timezone.utc) - saved_at).total_seconds() / 86400
        if age_days < -self.INSTRUMENT_SNAPSHOT_MAX_SKEW_SEC / 86400:
            logger.warning("instrument_snapshot_rejected reason=future_saved_at age_days=%.3f", age_days)
            return False
        if age_days > self.INSTRUMENT_SNAPSHOT_MAX_AGE_DAYS or len(tokens) < self.INSTRUMENT_CACHE_MIN_SIZE:
            logger.warning("instrument_snapshot_rejected age_days=%.1f size=%d", age_days, len(tokens))
            return False
        # Mutate in place: universes and scanners hold a reference to this dict.
        self.instrument_cache.update(tokens)
        status = self._instrument_status()
        status["source"] = "SNAPSHOT"
        status["snapshot_date"] = saved_at.date().isoformat()
        logger.warning("instrument_cache_from_snapshot size=%d saved_at=%s", len(tokens), saved["saved_at"])
        return True

    async def refresh_instrument_cache(self) -> bool:
        """Refresh NSE symbol->token. Returns True only for a provider refresh."""
        if not self.access_token:
            return False
        status = self._instrument_status()
        status["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
        async with self._cache_lock:
            try:
                # Fetch NSE instruments only -- INDICES segment returns 403 on this plan
                fresh: dict[str, int] = {}
                for segment in ["NSE"]:
                    _record_endpoint(self, "other")
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
                                    fresh[symbol] = int(raw_token)
                                except ValueError:
                                    # Malformed row (header line, blank
                                    # row, partial parse). Skip silently.
                                    continue
                if not fresh:
                    raise ValueError("instrument dump contained no symbols")
                if len(fresh) < self.INSTRUMENT_CACHE_MIN_SIZE:
                    # [O12-C1 2026-10-12] A truncated HTTP 200 dump used to be
                    # a provider success: refreshed today, failures 0, so the
                    # recovery job stopped retrying while the cache stayed
                    # unusable. It is now a failed attempt and is not merged.
                    raise _TruncatedInstrumentDump(f"instrument dump had {len(fresh)} symbols")
                # A full dump replaces the catalogue in place (scanners hold
                # this dict): symbols the provider no longer lists are dropped.
                stale = [symbol for symbol in self.instrument_cache if symbol not in fresh]
                for symbol in stale:
                    del self.instrument_cache[symbol]
                self.instrument_cache.update(fresh)
                status.update(source="PROVIDER", provider_refreshed_at=status["last_attempt_at"],
                              snapshot_date=None, last_error_type=None, failures=0,
                              last_dump_size=len(fresh))
                logger.info("instruments_refreshed", count=len(self.instrument_cache), dropped=len(stale))
            except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
                status["failures"] = int(status.get("failures") or 0) + 1
                status["last_error_type"] = type(e).__name__
                if isinstance(e, _TruncatedInstrumentDump):
                    status["last_dump_size"] = len(fresh)
                logger.error("instrument_refresh_failed", error_type=type(e).__name__,
                             failures=status["failures"])
                if not self.instrument_cache:
                    self._load_instrument_snapshot()
                return False
        self._save_instrument_snapshot(fresh)
        return True

    async def ensure_instrument_cache(self) -> bool:
        """Bounded recovery job: one provider attempt when today's refresh is missing.

        Cheap no-op once a provider refresh succeeded on the current IST date,
        so it can run every few minutes through the session.
        """
        status = self._instrument_status()
        refreshed = status.get("provider_refreshed_at")
        # [O12-C1] Done for the day only while the catalogue is also usable.
        if refreshed and len(self.instrument_cache) >= self.INSTRUMENT_CACHE_MIN_SIZE:
            import pytz as _pytz
            ist = _pytz.timezone("Asia/Kolkata")
            if datetime.fromisoformat(refreshed).astimezone(ist).date() == datetime.now(ist).date():
                return True
        if not self.access_token:
            if not self.instrument_cache:
                self._load_instrument_snapshot()
            return False
        failed_before = int(status.get("failures") or 0)
        ok = await self.refresh_instrument_cache()
        if ok and failed_before:
            logger.info("instrument_cache_recovered size=%d after_failures=%d",
                        len(self.instrument_cache), failed_before)
        return ok


    async def get_historical(self, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
        await self._init_db()
        ticker = ticker.upper()
        
        # Check Cache
# Check Cache
        async with self._cache_db() as db:
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

            # [WORKFLOW-C.F3 2026-09-16] F-3 from the 2026-09-16
            # production audit: 0% cache_hit rate is chronic
            # (4th consecutive audit). The bounded fix here
            # is observability -- surface WHICH condition
            # caused the cache_miss so the audit can answer
            # "is the writer broken, the freshness window
            # too short, or the date window off?". The 4
            # miss reasons are: no_rows, insufficient_rows,
            # date_window_miss, freshness_exceeded.
            cache_miss_reason: str | None = None

            if not rows:
                cache_miss_reason = "no_rows"
            elif len(rows) < _min_rows:
                cache_miss_reason = "insufficient_rows"
            else:
                last_cached_date = rows[-1][0] # Index 0 is 'date'
                # [CRIT] FIX: Force a cache miss if the DB doesn't have today's live candle yet!
                if last_cached_date < to_date:
                    cache_miss_reason = "date_window_miss"
                else:
                    last_fetched_str = rows[-1][6] # fetched_at is index 6
                    try:
                        last_fetched = datetime.strptime(last_fetched_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        age_seconds = (datetime.now(timezone.utc) - last_fetched).total_seconds()
                        if age_seconds >= 86400:
                            cache_miss_reason = "freshness_exceeded"
                        else:
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
                        cache_miss_reason = "timestamp_parse_failed"
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
        # [WORKFLOW-C.F3 2026-09-16] F-3 observability: include
        # the cache_miss_reason so the audit can attribute
        # zero-hit-rate days to one of: no_rows,
        # insufficient_rows, date_window_miss,
        # freshness_exceeded, or timestamp_parse_failed.
        # Without this, "0% hit rate" is unattributable.
        logger.info(
            "data_fetch",
            event_type="cache_miss",
            ticker=ticker,
            cache_miss_reason=cache_miss_reason or "unknown",
        )
        instrument_token = self.instrument_cache.get(ticker)
        if not instrument_token:
            raise ValueError(f"Unknown ticker: {ticker}")
        
        for attempt in range(5):
            await self.limiter.acquire()
            await _historical_send_gate(self)
            _record_endpoint(self, "historical")
            try:
                resp = await self.client.get(
                    f"/instruments/historical/{instrument_token}/day",
                    params={"from": from_date, "to": to_date}
                )
                _record_answer(self)
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("candles", [])
                if not data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                
                # Write to Cache
                async with self._cache_db() as db:
                    for _, row in df.iterrows():
                        await db.execute(
                            "INSERT OR REPLACE INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                            (ticker, row['date'].strftime("%Y-%m-%d"), row['open'], row['high'], row['low'], row['close'], row['volume'])
                        )
                    await db.commit()
                
                df.set_index('date', inplace=True)
                return df

            except httpx.HTTPStatusError as e:
                _record_status(self, "historical", e.response.status_code)
                if e.response.status_code in (429, 503, 504):  # 504 = Zerodha gateway timeout, also retried
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.RequestError as e:
                _record_transport(self, "historical", e)
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

        [WORKFLOW-H H4 2026-09-13] Cache semantics per plan section 12:
        the four explicit invariants -- instrument, interval,
        completed-bar cutoff, freshness -- are now honoured by
        the HIT path. The cache still contains forming candles
        (the writer cannot know when Kite's most recent candle is
        closed); the HIT path EXCLUDES forming candles when
        ``settings.INTRADAY_CACHE_INCLUDE_FORMING=False`` (default,
        per section 12 "do not mix mutable forming bars with
        completed historical bars").

        Freshness semantics: the most recent cached candle must
        be no older than ``expected_latest - freshness_seconds``,
        where ``expected_latest = to_datetime - interval_minutes``.
        The default ``freshness_seconds=0`` matches the pre-H4
        strict "last candle covers up to most recent interval
        boundary" gate.

        Operator-tunable knobs in ``config.py``:
            INTRADAY_CACHE_FRESHNESS_SECONDS
            INTRADAY_CACHE_INCLUDE_FORMING
            INTRADAY_CACHE_MIN_CANDLES

        The 00:05 IST cron ``clear_intraday_cache`` (retention
        default 365 days) does the daily ageing; the H4 path
        does NOT change that schedule.

        from_datetime / to_datetime format: "YYYY-MM-DD HH:MM:SS"
        """
        from config import settings
        interval = str(interval or "").strip().lower()
        interval_mins = _interval_minutes(interval)
        await self._init_intraday_db()
        ticker = ticker.upper()
        # [WORKFLOW-H H4 2026-09-13] Config knobs read ONCE per call;
        # defaults preserve the pre-H4 strict behaviour.
        freshness_seconds = int(
            getattr(settings, "INTRADAY_CACHE_FRESHNESS_SECONDS", 0)
        )
        include_forming = bool(
            getattr(settings, "INTRADAY_CACHE_INCLUDE_FORMING", False)
        )
        min_candles = int(
            getattr(settings, "INTRADAY_CACHE_MIN_CANDLES", 4)
        )

        # Check cache: only use if all rows are from today
        async with self._cache_db() as db:
            cursor = await db.execute(
                """SELECT datetime, open, high, low, close, volume
                   FROM intraday_cache
                   WHERE ticker=? AND interval=?
                     AND datetime >= ? AND datetime <= ?
                   ORDER BY datetime""",
                (ticker, interval, from_datetime, to_datetime)
            )
            rows = await cursor.fetchall()
            # [WORKFLOW-H H4 2026-09-13] Shared gate evaluates the
            # four §12 explicit semantics. See ``_intraday_cache_gate_evaluate``
            # for the gate contract.
            verdict = _intraday_cache_gate_evaluate(
                rows=rows,
                to_datetime_str=to_datetime,
                interval=interval,
                interval_mins=interval_mins,
                freshness_seconds=freshness_seconds,
                include_forming=include_forming,
                min_candles=min_candles,
                source_kind="ticker",
                source_id=ticker,
            )
            if verdict is not None:
                filtered_rows, debug_event = verdict
                # The gate's debug_event uses ``source_kind`` /
                # ``source_id`` for the cross-cutting case. The
                # by-symbol path keeps the legacy ``ticker`` field
                # name so log-grep operators continue to find it.
                if "ticker" not in debug_event:
                    debug_event["ticker"] = ticker
                if filtered_rows:
                    logger.debug("data_fetch", **debug_event)
                    df = pd.DataFrame(
                        filtered_rows,
                        columns=['datetime','open','high','low','close','volume'],
                    )
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                    return df
                # No HIT (only-forming or below-floor). Fall through.
                logger.debug("data_fetch", **debug_event)
            else:
                # Stale: gate rejected on freshness. Differentiate
                # this from a true miss so operators can distinguish
                # "cache out of date" from "cache empty".
                last_cached_dt = (
                    datetime.strptime(rows[-1][0], "%Y-%m-%d %H:%M:%S")
                    if rows else None
                )
                expected_latest = (
                    datetime.strptime(to_datetime, "%Y-%m-%d %H:%M:%S")
                    - timedelta(minutes=interval_mins)
                    - timedelta(seconds=max(0, freshness_seconds))
                )
                logger.debug(
                    "data_fetch",
                    event_type="intraday_cache_stale",
                    ticker=ticker,
                    last_candle=str(last_cached_dt) if last_cached_dt else None,
                    expected=str(expected_latest),
                )

        # Cache miss -> API
        logger.debug("data_fetch", event_type="intraday_cache_miss", ticker=ticker)
        instrument_token = self.instrument_cache.get(ticker)
        if not instrument_token:
            raise ValueError(f"Unknown ticker: {ticker}")

        for attempt in range(5):
            await self.limiter.acquire()
            await _historical_send_gate(self)
            _record_endpoint(self, "historical")
            try:
                resp = await self.client.get(
                    f"/instruments/historical/{instrument_token}/{interval}",
                    params={"from": from_datetime, "to": to_datetime}
                )
                _record_answer(self)
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("candles", [])
                if not data:
                    return pd.DataFrame()

                df = pd.DataFrame(
                    data, columns=['datetime','open','high','low','close','volume']
                )
                df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)

                # Write to intraday cache
                async with self._cache_db() as db:
                    for _, row in df.iterrows():
                        await db.execute(
                            """INSERT OR REPLACE INTO intraday_cache
                               (ticker, interval, datetime, open, high, low, close,
                                volume, fetched_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            (ticker,
                             interval,
                             row['datetime'].strftime("%Y-%m-%d %H:%M:%S"),
                             row['open'], row['high'], row['low'],
                             row['close'], row['volume'])
                        )
                    await db.commit()

                df.set_index('datetime', inplace=True)
                return df

            except httpx.HTTPStatusError as e:
                _record_status(self, "historical", e.response.status_code)
                if e.response.status_code in (429, 503, 504):  # 504 = Zerodha gateway timeout, also retried
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.RequestError as e:
                _record_transport(self, "historical", e)
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
        """Compatibility wrapper; ``self.limiter.acquire`` is owned by timing API."""
        result, _timing = await self.get_quote_with_timing(tokens)
        return result

    async def get_quote_with_timing(self, tokens, *, priority: Optional[str] = None) -> tuple[dict, dict]:
        """Fetch live quotes for tokens through the quote budget (merged batches).

        See ``QuoteBudget``; without one (bare test doubles) the request goes
        straight to ``_quote_direct``.
        """
        if isinstance(tokens, (int, str)):
            tokens = [tokens]
        tokens = [int(t) for t in tokens] if tokens else []
        budget = getattr(self, "quote_budget", None)
        if len(tokens) > QuoteBudget.MAX_INSTRUMENTS:
            # [O9-Q3 2026-10-09] Kite's full quote takes at most 500 keys; a
            # larger request (the ~970-name overnight universe) was sent whole.
            # Each chunk goes through the normal (budgeted) path in turn.
            merged, parts = {}, []
            size = QuoteBudget.MAX_INSTRUMENTS
            for start in range(0, len(tokens), size):
                part, part_timing = await self.get_quote_with_timing(
                    tokens[start:start + size], priority=priority)
                merged.update(part)
                parts.append(part_timing)
            return merged, _aggregate_chunk_timing(parts)
        if not tokens or budget is None:
            return await self._quote_direct(tokens, priority=priority)
        lane = priority if priority in _LANE_RANK else _provider_lane.get()
        return await budget.submit(
            lambda merged, batch_lane: self._quote_direct(merged, priority=batch_lane, admitted=True),
            tokens, lane, shared=self.limiter)

    async def _quote_direct(self, tokens, *, priority: Optional[str] = None,
                            admitted: bool = False) -> tuple[dict, dict]:
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
        timing = {
            "limiter_wait_sec": 0.0, "transport_sec": 0.0,
            "parse_sec": 0.0, "retry_backoff_sec": 0.0,
            "attempt_count": 0, "retry_count": 0,
        }

        def _finish(result: dict) -> tuple[dict, dict]:
            return result, {
                "limiter_wait_sec": round(timing["limiter_wait_sec"], 6),
                "transport_sec": round(timing["transport_sec"], 6),
                "parse_sec": round(timing["parse_sec"], 6),
                "retry_backoff_sec": round(timing["retry_backoff_sec"], 6),
                "attempt_count": int(timing["attempt_count"]),
                "retry_count": int(timing["retry_count"]),
            }

        if isinstance(tokens, (int, str)):
            tokens = [tokens]
        if not tokens:
            return _finish({})
        tokens = [int(t) for t in tokens]

        # Retry config (KITE-QUOTE-RETRY 2026-07-02): 3 attempts,
        # 0.5s -> 1.0s -> 2.0s backoff. Total worst-case wait ~3.5s,
        # which is fine because the penny scanner runs on a 30s cron.
        max_attempts = 3
        backoff = 0.5
        last_exc: Optional[Exception] = None
        budget = getattr(self, "quote_budget", None)
        for attempt in range(1, max_attempts + 1):
            timing["attempt_count"] = attempt
            limiter_started = time.monotonic()
            # Every HTTP attempt is admitted (shared limiter, then the quote
            # bucket) right before it is sent; the batch dispatcher already
            # admitted the first one.
            if not (admitted and attempt == 1):
                if budget is not None:
                    await budget.admit(self.limiter, priority)
                else:
                    await _acquire_shared(self.limiter, priority)
            if budget is not None:
                await budget.before_send()
            _record_endpoint(self, "quote")
            timing["limiter_wait_sec"] += time.monotonic() - limiter_started
            try:
                transport_started = time.monotonic()
                resp = await self.client.get(
                    "/quote",
                    params=[("i", str(t)) for t in tokens],
                )
                timing["transport_sec"] += time.monotonic() - transport_started
                _record_answer(self)
                resp.raise_for_status()
                parse_started = time.monotonic()
                data = resp.json().get("data", {})
                result = {int(k): v for k, v in data.items()}
                timing["parse_sec"] += time.monotonic() - parse_started
                if not result and tokens:
                    # [KITE-QUOTE-RETRY] Empty body with 200 OK -- this
                    # is the case today's 2,649 403s turned into. Treat
                    # as transient and retry unless we're on the last
                    # attempt. If still empty after retries, fall through
                    # to the existing failure logger.
                    if attempt < max_attempts:
                        timing["retry_count"] += 1
                        logger.warning(
                            "kite_quote_empty_body_retrying attempt=%d/%d tokens=%d",
                            attempt, max_attempts, len(tokens),
                        )
                        backoff_started = time.monotonic()
                        await asyncio.sleep(backoff)
                        timing["retry_backoff_sec"] += time.monotonic() - backoff_started
                        backoff *= 2
                        continue
                    self._log_quote_batch_failure(len(tokens))
                    self._note_quote_rate_failure()
                elif result:
                    self._note_quote_batch_success()
                return _finish(result)
            except httpx.HTTPStatusError as e:
                last_exc = e
                status = e.response.status_code
                _record_status(self, "quote", status)
                # Retry on 401 (token expired), 403 (rate-limit /
                # momentary overload), 429 (explicit rate-limit), and
                # any 5xx server error.
                if status in (401, 403, 429) or status >= 500:
                    if attempt < max_attempts:
                        timing["retry_count"] += 1
                        logger.warning(
                            "kite_quote_http_retry status=%d attempt=%d/%d tokens=%d",
                            status, attempt, max_attempts, len(tokens),
                        )
                        backoff_started = time.monotonic()
                        await asyncio.sleep(backoff)
                        timing["retry_backoff_sec"] += time.monotonic() - backoff_started
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
                return _finish({})
            except httpx.RequestError as e:
                last_exc = e
                _record_transport(self, "quote", e)
                if attempt < max_attempts:
                    timing["retry_count"] += 1
                    logger.warning(
                        "kite_quote_request_retry attempt=%d/%d tokens=%d err=%s",
                        attempt, max_attempts, len(tokens), str(e),
                    )
                    backoff_started = time.monotonic()
                    await asyncio.sleep(backoff)
                    timing["retry_backoff_sec"] += time.monotonic() - backoff_started
                    backoff *= 2
                    continue
                logger.error(
                    "kite_quote_failed error=%s", str(e),
                )
                self._log_quote_batch_failure(len(tokens))
                self._note_quote_rate_failure()
                return _finish({})
        # Should be unreachable given the loops above, but be defensive.
        if last_exc is not None:
            logger.error("kite_quote_failed_unreachable %s", str(last_exc))
        return _finish({})

    async def get_quote_by_instruments(self, instruments: dict[int, str]) -> dict:
        """Documented Kite full-quote lookup keyed by ``EXCHANGE:SYMBOL``.

        Existing consumers deliberately retain ``get_quote(tokens)`` for
        backwards compatibility.  New F&O research must not assume that a
        numeric token is accepted by the documented full-quote endpoint: it
        supplies the dated exchange/symbol identity and maps returned packets
        back to the caller's token only after checking the requested key.
        """
        result, _timing = await self.get_quote_by_instruments_with_timing(instruments)
        return result

    async def get_quote_by_instruments_with_timing(
        self, instruments: dict[int, str],
    ) -> tuple[dict, dict]:
        """``get_quote_by_instruments`` plus bounded limiter/transport timing.

        Research collection uses this to attribute a slow call to shared
        limiter queueing versus provider transport.  Behaviour, single attempt
        and failure-to-empty semantics are identical to the untimed method.
        """
        timing = {"limiter_wait_sec": 0.0, "transport_sec": 0.0, "parse_sec": 0.0,
                  "attempt_count": 0, "outcome": "EMPTY_REQUEST"}

        def _finish(result: dict) -> tuple[dict, dict]:
            return result, {key: (round(value, 6) if isinstance(value, float) else value)
                            for key, value in timing.items()}

        requested = {int(token): str(key) for token, key in instruments.items() if str(key).strip()}
        if not requested:
            return _finish({})
        if len(requested) > QuoteBudget.MAX_INSTRUMENTS:
            # [O12-Q2 2026-10-12] Kite's full quote takes at most 500 keys;
            # bound every caller here, as the token path already does.
            items, merged, parts = list(requested.items()), {}, []
            size = QuoteBudget.MAX_INSTRUMENTS
            for start in range(0, len(items), size):
                part, part_timing = await self.get_quote_by_instruments_with_timing(
                    dict(items[start:start + size]))
                merged.update(part)
                parts.append(part_timing)
            timing = _aggregate_chunk_timing(parts)
            outcomes = {part.get("outcome") for part in parts}
            timing["outcome"] = ("COMPLETE" if outcomes == {"COMPLETE"} else
                                 "FAILED" if outcomes == {"FAILED"} else "PARTIAL")
            return merged, timing
        limiter_started = time.monotonic()
        budget = getattr(self, "quote_budget", None)
        if budget is not None:
            await budget.admit(self.limiter)          # ambient lane, shares the 1/s quote budget
            await budget.before_send()
        else:
            await _acquire_shared(self.limiter, None)
        _record_endpoint(self, "quote")
        timing["limiter_wait_sec"] = time.monotonic() - limiter_started
        timing["attempt_count"] = 1
        try:
            transport_started = time.monotonic()
            response = await self.client.get("/quote", params=[("i", key) for key in requested.values()])
            timing["transport_sec"] = time.monotonic() - transport_started
            _record_answer(self)
            response.raise_for_status()
            parse_started = time.monotonic()
            payload = response.json().get("data", {})
            reverse = {key: token for token, key in requested.items()}
            result = {reverse[key]: value for key, value in payload.items() if key in reverse and isinstance(value, dict)}
            timing["parse_sec"] = time.monotonic() - parse_started
            if len(result) != len(requested):
                # [S23-Q1] Name what is missing: Oct 23 15:20 logged 15 -> 0
                # and the audit could not tell which symbols went unquoted.
                missing = sorted(key for token, key in requested.items() if token not in result)
                logger.warning("kite_quote_instrument_partial requested=%d returned=%d missing=%s",
                               len(requested), len(result),
                               ",".join(missing[:20]) + (f",+{len(missing) - 20} more" if len(missing) > 20 else ""))
            timing["outcome"] = "COMPLETE" if len(result) == len(requested) else "PARTIAL"
            return _finish(result)
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            if not timing["transport_sec"]:
                timing["transport_sec"] = time.monotonic() - transport_started
            # [O9-Q2 2026-10-09] This path's non-2xx answers (429 included)
            # were never counted, so http_429=0 did not cover it.
            if isinstance(exc, httpx.HTTPStatusError):
                _record_status(self, "quote", exc.response.status_code)
                timing["http_status"] = exc.response.status_code
            else:
                _record_transport(self, "quote", exc)
            logger.warning("kite_quote_instrument_failed requested=%d err=%s", len(requested),
                           type(exc).__name__)
            timing["outcome"] = "FAILED"
            return _finish({})

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
            background_tasks.spawn(_send(), name="kite_operator_alert")
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
        _record_endpoint(self, "other")
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
        _record_endpoint(self, "other")
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
        [WORKFLOW-H H4.B 2026-09-13] Intraday candles by raw
        instrument token, with §12 cache semantics. The four
        explicit invariants -- instrument, interval, completed-bar
        cutoff, freshness -- are honoured by the same HIT-path
        gate as ``get_intraday`` (see ``_intraday_cache_gate_evaluate``).
        The previous "no sqlite caching" rationale ("F&O ticks
        re-read every 5 minutes, so a cache would only serve
        stale bars") is replaced by the forming-bar filter:
        forming candles are EXCLUDED from the HIT path, so a
        cache HIT serves strictly completed candles.

        The ``oi`` (open-interest) column is preserved through
        the HIT path -- it is part of the Kite F&O candle schema
        and downstream callers (``partner_orchestrator.realized_vol_20d``)
        read it.

        Failure contract: returns an empty DataFrame on cache
        MISS + API failure (preserves pre-H4 behaviour). The
        5-attempt retry loop is preserved.

        from_datetime / to_datetime format: "YYYY-MM-DD HH:MM:SS"
        """
        from config import settings
        interval = str(interval or "").strip().lower()
        interval_mins = _interval_minutes(interval)
        await self._init_intraday_db()
        # [WORKFLOW-H H4.B 2026-09-13] Same three knobs as the
        # by-symbol path, read once per call. Defaults preserve
        # the pre-H4 strict behaviour.
        freshness_seconds = int(
            getattr(settings, "INTRADAY_CACHE_FRESHNESS_SECONDS", 0)
        )
        include_forming = bool(
            getattr(settings, "INTRADAY_CACHE_INCLUDE_FORMING", False)
        )
        min_candles = int(
            getattr(settings, "INTRADAY_CACHE_MIN_CANDLES", 4)
        )

        # Check cache: HIT path. The by-token table has an
        # additional ``oi`` column (F&O open interest) that the
        # by-symbol path does not store.
        async with self._cache_db() as db:
            cursor = await db.execute(
                """SELECT datetime, open, high, low, close, volume, oi
                   FROM intraday_cache_by_token
                   WHERE instrument_token=? AND interval=?
                     AND datetime >= ? AND datetime <= ?
                   ORDER BY datetime""",
                (int(instrument_token), interval, from_datetime, to_datetime)
            )
            rows = await cursor.fetchall()
            verdict = _intraday_cache_gate_evaluate(
                rows=rows,
                to_datetime_str=to_datetime,
                interval=interval,
                interval_mins=interval_mins,
                freshness_seconds=freshness_seconds,
                include_forming=include_forming,
                min_candles=min_candles,
                source_kind="instrument_token",
                source_id=int(instrument_token),
            )
            if verdict is not None:
                filtered_rows, debug_event = verdict
                if "instrument_token" not in debug_event:
                    debug_event["instrument_token"] = int(instrument_token)
                if filtered_rows:
                    logger.debug("data_fetch", **debug_event)
                    cols = ['datetime','open','high','low','close','volume','oi']
                    df = pd.DataFrame(filtered_rows, columns=cols)
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                    return df
                # No HIT (only-forming or below-floor). Fall through.
                logger.debug("data_fetch", **debug_event)
            else:
                # Stale: gate rejected on freshness. The by-token
                # path logs ``instrument_token`` instead of
                # ``ticker`` -- operators grep differently for the
                # two paths.
                last_cached_dt = (
                    datetime.strptime(rows[-1][0], "%Y-%m-%d %H:%M:%S")
                    if rows else None
                )
                expected_latest = (
                    datetime.strptime(to_datetime, "%Y-%m-%d %H:%M:%S")
                    - timedelta(minutes=interval_mins)
                    - timedelta(seconds=max(0, freshness_seconds))
                )
                logger.debug(
                    "data_fetch",
                    event_type="intraday_cache_stale",
                    instrument_token=int(instrument_token),
                    last_candle=str(last_cached_dt) if last_cached_dt else None,
                    expected=str(expected_latest),
                )

        # Cache MISS -> API. Retry loop preserved from the pre-H4.B
        # implementation; on success, INSERT OR REPLACE the rows
        # into ``intraday_cache_by_token`` for future HITs.
        logger.debug(
            "data_fetch", event_type="intraday_cache_miss",
            instrument_token=int(instrument_token),
        )
        for attempt in range(5):
            await self.limiter.acquire()
            await _historical_send_gate(self)
            _record_endpoint(self, "historical")
            try:
                resp = await self.client.get(
                    f"/instruments/historical/{int(instrument_token)}/{interval}",
                    params={"from": from_datetime, "to": to_datetime},
                )
                _record_answer(self)
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

                # [WORKFLOW-H H4.B 2026-09-13] Write-through to
                # the by-token cache. INSERT OR REPLACE on the
                # PRIMARY KEY (instrument_token, interval,
                # datetime) ensures idempotency on retry.
                async with self._cache_db() as db:
                    for _, row in df.iterrows():
                        oi_value = (
                            float(row['oi']) if 'oi' in row and row['oi'] is not None
                            and not (isinstance(row['oi'], float)
                                     and (row['oi'] != row['oi']))  # NaN check
                            else None
                        )
                        await db.execute(
                            """INSERT OR REPLACE INTO intraday_cache_by_token
                               (instrument_token, interval, datetime, open, high,
                                low, close, volume, oi, fetched_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            (
                                int(instrument_token),
                                interval,
                                row['datetime'].strftime("%Y-%m-%d %H:%M:%S"),
                                row['open'], row['high'], row['low'],
                                row['close'], row['volume'], oi_value,
                            ),
                        )
                    await db.commit()

                df.set_index('datetime', inplace=True)
                return df
            except httpx.HTTPStatusError as e:
                _record_status(self, "historical", e.response.status_code)
                if e.response.status_code in (429, 503, 504):
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(
                    "kite_intraday_by_token_failed token=%d status=%d",
                    instrument_token, e.response.status_code,
                )
                return pd.DataFrame()
            except httpx.RequestError as e:
                _record_transport(self, "historical", e)
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
        *,
        intent: str,
        channel: Optional[str] = None,
    ) -> dict:
        """
        Place an order on Kite.
        Kite endpoint: POST /orders/{variety}
        Returns: {order_id, status, message}

        `intent` is REQUIRED and keyword-only, and it is the halt boundary.

        [HALT 2026-08-05] The kill switch blocks ENTRIES and never blocks
        EXITS. Refusing an exit during a halt would strand a live position with
        no protective stop -- strictly worse than whatever condition tripped the
        halt in the first place. So `intent="entry"` is gated and
        `intent="exit"` always proceeds.

        There is deliberately no default. A default would let a future call site
        inherit the wrong side of that boundary silently, and both directions of
        that mistake are expensive: a forgotten exit gets blocked and goes
        naked, a forgotten entry trades straight through a halt. Making it
        required converts either mistake into an immediate TypeError.

        [F0-R2 2026-10-03] Every return carries ``dispatch_certainty``:
        ``NOT_SENT`` (refused before any request left this process),
        ``BROKER_REJECTED`` (explicit HTTP 4xx, no order created),
        ``AMBIGUOUS`` (the broker may hold an order: 5xx, a transport error
        after connecting, or an accepted response without an order id) or
        ``ACCEPTED``. Callers must not release capital on ``AMBIGUOUS``.
        """
        if intent not in ("entry", "exit"):
            raise ValueError(f"intent must be 'entry' or 'exit', got {intent!r}")

        if not tradingsymbol or quantity <= 0:
            return {"order_id": None, "status": "ERROR", "dispatch_certainty": "NOT_SENT",
                    "message": "tradingsymbol and positive quantity are required"}

        def entry_blocker():
            if intent != "entry":
                return None
            owner_halt = is_owner_entry_halted(channel)
            if not owner_halt.allowed:
                logger.error(
                    "kite_order_blocked_by_owner_entry_halt",
                    tradingsymbol=tradingsymbol,
                    channel=channel,
                    reason=owner_halt.reason,
                )
                return {
                    "order_id": None,
                    "status": "ERROR",
                    "dispatch_certainty": "NOT_SENT",
                    "halted": True,
                    "owner_entry_halted": True,
                    "message": f"Owner entry halt: {owner_halt.reason}",
                }
            try:
                assert_not_halted(channel)
            except TradingHalted as exc:
                logger.error(
                    "kite_order_blocked_by_halt",
                    tradingsymbol=tradingsymbol, channel=channel,
                    scope=exc.attribution.get("scope"),
                    by=exc.attribution.get("by"),
                    reason=exc.attribution.get("reason"),
                )
                # Status is "ERROR", not a novel "HALTED": every caller already
                # branches on ERROR / falsy order_id, and inventing a status
                # string they do not know would read as SUCCESS. The `halted`
                # flag is there for callers that want to tell the two apart.
                return {"order_id": None, "status": "ERROR", "halted": True,
                        "dispatch_certainty": "NOT_SENT", "message": str(exc)}
            return None

        blocked = entry_blocker()
        if blocked is not None:
            return blocked
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
        # A stable tag makes both broker reconciliation and the shared cash
        # reservation idempotent.  Kite permits at most 20 characters.
        if intent == "entry" and str(transaction_type).upper() == "BUY" and not tag:
            tag = f"AC_{uuid.uuid4().hex[:17]}"
        if tag:
            params["tag"] = tag

        await self.limiter.acquire()
        # The limiter can yield while an operator trips either entry halt.
        # Recheck at dispatch; exits never consult either halt predicate.
        blocked = entry_blocker()
        if blocked is not None:
            return blocked
        # [F1-A 2026-10-03] A new BUY must be fully paid from own uncommitted
        # cash; broker leverage never funds an entry. Exits are never checked.
        reservation_id = None
        if intent == "entry" and str(transaction_type).upper() == "BUY":
            refusal = await self._own_cash_refusal(tradingsymbol, quantity, price)
            if refusal is not None:
                return refusal
            reservation_id, refusal = await self._reserve_account_cash(
                broker_tag=str(tag or ""), channel=channel, tradingsymbol=tradingsymbol,
                quantity=quantity, price=price,
            )
            if refusal is not None:
                return refusal
        try:
            _record_endpoint(self, "order")     # counted at dispatch; refusals above never reach HTTP
            resp = await self._orders_http.post(f"/orders/{variety}", data=params)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            # An accepted POST is the only honest proof available that this
            # token + route + static IP may place orders.
            if data.get("order_id"):
                mark_order_execution_authorized()
            result = {
                "order_id": data.get("order_id"),
                "status": "PLACED",
                "dispatch_certainty": "ACCEPTED" if data.get("order_id") else "AMBIGUOUS",
                "message": "order placed",
            }
            if reservation_id:
                self.account_cash_reservations.mark_dispatch(
                    reservation_id, broker_order_id=data.get("order_id"),
                    ambiguous=not bool(data.get("order_id")),
                )
            return result
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response.text else ""
            logger.error("kite_place_order_failed status=%d body=%s", e.response.status_code, body)
            if is_permission_or_static_ip_rejection(e.response.status_code, body):
                reason = (
                    f"Kite order authorization rejected via {self._orders_http.base_url}: "
                    f"HTTP {e.response.status_code}; verify the app's registered static IP "
                    "and the configured relay egress"
                )
                first_transition = mark_order_execution_blocked(
                    reason, http_status=e.response.status_code,
                )
                # Account/route permission affects every live strategy, so this
                # is intentionally global.  Exits remain exempt at the broker
                # boundary and will continue to be attempted and reconciled.
                try:
                    trip_halt(reason, by="kite_order_authorization")
                except OSError as halt_exc:
                    logger.critical(
                        "kite_order_authorization_halt_failed", error=str(halt_exc),
                    )
                if first_transition:
                    try:
                        from operator_alert import notify_operator
                        await notify_operator(
                            "🔴 LIVE ORDER AUTHORIZATION BLOCKED\n\n"
                            f"{reason}. New live entries are halted. Existing exits will "
                            "still be attempted, but manage open positions in Kite until "
                            "a real order is accepted and the halt is manually cleared.",
                            event="kite_order_authorization_blocked",
                        )
                    except Exception as alert_exc:
                        logger.error(
                            "kite_order_authorization_alert_failed", error=str(alert_exc),
                        )
            result = {"order_id": None, "status": "ERROR",
                    "dispatch_certainty": (
                        "BROKER_REJECTED" if 400 <= e.response.status_code < 500 else "AMBIGUOUS"
                    ),
                    "execution_blocked": is_permission_or_static_ip_rejection(
                        e.response.status_code, body
                    ),
                    "message": f"HTTP {e.response.status_code}: {body}"}
            if reservation_id:
                if result["dispatch_certainty"] == "BROKER_REJECTED":
                    # A POST 4xx has no broker order id; release this local
                    # reservation through the dedicated known-not-sent path.
                    self.account_cash_reservations.release_not_sent(reservation_id, "broker_http_4xx")
                else:
                    self.account_cash_reservations.mark_dispatch(
                        reservation_id, broker_order_id=None, ambiguous=True)
            return result
        except httpx.RequestError as e:
            logger.error("kite_place_order_failed error=%s", str(e))
            # Only a failure to connect proves the request never left.
            certainty = (
                "NOT_SENT" if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout))
                else "AMBIGUOUS"
            )
            result = {"order_id": None, "status": "ERROR", "dispatch_certainty": certainty,
                    "message": str(e)}
            if reservation_id:
                if certainty == "NOT_SENT":
                    self.account_cash_reservations.release_not_sent(reservation_id, "transport_not_connected")
                else:
                    self.account_cash_reservations.mark_dispatch(
                        reservation_id, broker_order_id=None, ambiguous=True)
            return result

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
        _record_endpoint(self, "order")
        try:
            resp = await self._orders_http.put(f"/orders/{variety}/{order_id}", data=params)
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
        _record_endpoint(self, "order")
        try:
            resp = await self._orders_http.delete(f"/orders/{variety}/{order_id}")
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
        _record_endpoint(self, "other")
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

    async def get_funds_margins(self) -> dict | None:
        """[F1-A] Read-only ``GET /user/margins``; ``None`` when unavailable."""
        try:
            _record_endpoint(self, "other")
            resp = await self.client.get("/user/margins")
            resp.raise_for_status()
            data = resp.json().get("data")
            return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.error("kite_margins_failed", error=str(exc))
            return None

    async def _own_cash_refusal(self, tradingsymbol: str, quantity: int, price) -> dict | None:
        """``None`` when the entry is fully covered by own cash, else a refusal."""
        def refuse(reason: str) -> dict:
            logger.error("kite_order_refused_own_cash", tradingsymbol=tradingsymbol, reason=reason)
            return {"order_id": None, "status": "ERROR", "dispatch_certainty": "NOT_SENT",
                    "own_cash_refused": True, "message": reason}

        value = _finite(price, non_negative=True)
        if not value or not isinstance(quantity, int) or quantity <= 0:
            return refuse("OWN_CASH_EVIDENCE_UNAVAILABLE: entry order value unknown (LIMIT price required)")
        order_value = value * quantity
        margins = await self.get_funds_margins()
        positions = await self.get_broker_positions()
        orders = await self.orders_snapshot()
        own = own_uncommitted_cash(margins, positions, orders)
        if own is None:
            return refuse("OWN_CASH_EVIDENCE_UNAVAILABLE: margins/positions/orders missing or invalid")
        if order_value > own:
            return refuse(f"OWN_CASH_INSUFFICIENT: order value {order_value:.2f} > "
                          f"own uncommitted cash {own:.2f}")
        return None

    async def _reserve_account_cash(self, *, broker_tag: str, channel: Optional[str],
                                    tradingsymbol: str, quantity: int, price) -> tuple[str | None, dict | None]:
        """Atomically retain this entry's cash across Python and gateway paths.

        The preceding F1-A check remains useful for a clear immediate refusal;
        this second evidence read closes the race between that snapshot and the
        broker POST.  A failed reservation is a no-send refusal.
        """
        def refuse(reason: str) -> tuple[None, dict]:
            logger.error("kite_order_refused_account_cash", tradingsymbol=tradingsymbol, reason=reason)
            return None, {"order_id": None, "status": "ERROR", "dispatch_certainty": "NOT_SENT",
                          "own_cash_refused": True, "message": reason}

        value = _finite(price, non_negative=True)
        if not value or not isinstance(quantity, int) or quantity <= 0 or not broker_tag:
            return refuse("ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: bounded LIMIT value/tag required")
        margins = await self.get_funds_margins()
        positions = await self.get_broker_positions()
        orders = await self.orders_snapshot()
        own = own_uncommitted_cash(margins, positions, orders)
        if own is None:
            return refuse("ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: margins/positions/orders missing or invalid")
        reservation_id = f"PY:{broker_tag}"
        try:
            reservation = self.account_cash_reservations.reserve(
                reservation_id=reservation_id,
                account_id=settings.ACCOUNT_CASH_ACCOUNT_ID,
                book=str(channel or "python").strip().lower() or "python",
                broker_tag=broker_tag,
                notional=value * quantity,
                own_uncommitted_cash=own,
                broker_orders=orders,
            )
        except (ReservationRefused, ValueError, sqlite3.Error) as exc:
            return refuse(str(exc))
        logger.info("entry_account_cash_reserved", tradingsymbol=tradingsymbol,
                    reservation_id=reservation.reservation_id, book=channel or "python",
                    amount=reservation.amount, charge_reserve=reservation.charge_reserve,
                    fill_buffer=reservation.fill_buffer, available_after=reservation.available_after)
        return reservation_id, None

    def settle_entry_reservation(self, order_id: str, *, final_status: str, filled_quantity) -> bool:
        """[O25] Release a BUY's own-cash hold once its outcome is proven.

        COMPLETE: the broker's position and later its cash balance carry the
        money. CANCELLED/REJECTED with nothing filled: no money moved. Anything
        else keeps the hold (fail closed). True when a hold was released."""
        reservation_id = self.account_cash_reservations.reservation_for_order(order_id)
        if reservation_id is None:
            return False
        status = str(final_status or "").upper()
        if status == "COMPLETE":
            released = self.account_cash_reservations.release_filled(reservation_id, broker_order_id=order_id)
        elif status in ("CANCELLED", "REJECTED") and filled_quantity == 0:
            released = self.account_cash_reservations.release_zero_fill(
                reservation_id, broker_order_id=order_id, terminal_status=status, filled_quantity=0)
        else:
            return False
        logger.info("entry_account_cash_released", order_id=order_id, status=status, released=released)
        return released

    async def orders_snapshot(self) -> list | None:
        """Return today's broker order book, or ``None`` when unreadable.

        An empty successful response is materially different from a transport
        failure for idempotency recovery: only the former proves that a stable
        tagged order was not accepted and may be submitted.
        """
        await self.limiter.acquire()
        _record_endpoint(self, "other")
        try:
            resp = await self.client.get("/orders")
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            return data if isinstance(data, list) else None
        except httpx.HTTPStatusError as e:
            logger.error("kite_orders_snapshot_failed status=%d", e.response.status_code)
            return None
        except httpx.RequestError as e:
            logger.error("kite_orders_snapshot_failed error=%s", str(e))
            return None
        except ValueError as e:
            logger.error("kite_orders_snapshot_failed invalid_json=%s", str(e))
            return None

    async def order_trades(self, order_id: str) -> list | None:
        """Today's executions for one order; None means broker read failed."""
        if not order_id:
            return None
        await self.limiter.acquire()
        _record_endpoint(self, "other")
        try:
            resp = await self.client.get(f"/orders/{order_id}/trades")
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            return data if isinstance(data, list) else None
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            logger.error("kite_order_trades_failed order_id=%s error=%s", order_id, str(exc))
            return None

    async def get_broker_positions(self) -> dict:
        """Broker-side positions. Kite endpoint: GET /portfolio/positions.
        Returns {"net": [...], "day": [...]} ({} on failure).

        [ORDER-HISTORY-2026-07-17] Added for post-timeout reconciliation:
        when an entry order's final state cannot be determined (history
        fetch failed, cancel returned "order does not exist"), the last
        word on whether we actually hold stock is the positions book, not
        our bookkeeping. See PennyExecutor.execute_entry."""
        await self.limiter.acquire()
        _record_endpoint(self, "other")
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


_OPEN_ORDER_STATUSES = frozenset({
    "OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "OPEN PENDING", "VALIDATION PENDING",
    "PUT ORDER REQ RECEIVED", "MODIFY PENDING", "MODIFY VALIDATION PENDING",
})


def _finite(value, *, non_negative: bool = False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or (non_negative and number < 0):
        return None
    return number


def own_uncommitted_cash(margins, positions, orders):
    """[F1-A 2026-10-03] Owner rule "no extra margin": own cash still free today.

    ``equity.available.cash`` (never collateral, adhoc margin or broker
    leverage) minus the cost of open long positions, pending BUY orders and
    today's realised losses. A short position or any malformed evidence
    returns ``None`` so the caller refuses the entry.
    """
    equity = (margins or {}).get("equity") if isinstance(margins, dict) else None
    if not isinstance(equity, dict) or equity.get("enabled") is False:
        return None
    own_cash = _finite((equity.get("available") or {}).get("cash"), non_negative=True)
    if own_cash is None:
        return None
    realised_loss = 0.0
    utilised = equity.get("utilised")
    if isinstance(utilised, dict) and "m2m_realised" in utilised:
        realised = _finite(utilised.get("m2m_realised"))
        if realised is None:
            return None
        realised_loss = max(0.0, -realised)
    net = positions.get("net") if isinstance(positions, dict) else None
    if not isinstance(net, list) or not isinstance(orders, list):
        return None
    committed = 0.0
    for row in net:
        qty = _finite((row or {}).get("quantity"))
        if qty is None or qty < 0:
            return None
        if qty == 0:
            continue
        avg = _finite(row.get("average_price"), non_negative=True)
        if not avg:
            return None
        committed += qty * avg
    pending = 0.0
    for order in orders:
        if str((order or {}).get("status") or "").upper() not in _OPEN_ORDER_STATUSES:
            continue
        if str(order.get("transaction_type") or "").upper() != "BUY":
            continue
        qty = order.get("pending_quantity", order.get("quantity"))
        qty = _finite(qty, non_negative=True)
        price = _finite(order.get("price"), non_negative=True)
        if qty is None or not price:
            return None
        pending += qty * price
    return max(0.0, own_cash - committed - pending - realised_loss)


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
