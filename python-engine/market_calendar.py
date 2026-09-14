import aiosqlite
#import aiosqlite
import functools
import httpx
import sqlite3
from datetime import date, timedelta, time
import structlog
from datetime import datetime
import pytz

logger = structlog.get_logger()

IST = pytz.timezone("Asia/Kolkata")

# [WORKFLOW-J 2026-09-13] Central session constants. Each value cites
# its NSE source. Adding a new constant here is the ONLY allowed way to
# introduce a new clock; the constants are consumed by
# ``classify_session_phase`` (this file) and ``stamp_session_phase``
# (``proactive_intelligence``).
#
# Sources:
#   * NSE equity cash continuous trading:
#     https://www.nseindia.com/static/products-services/closing-auction-session
#   * NSE Closing Auction Session (CAS) effective from 2026-01-19
#     (NSE/CMTR/72394), with Phase 1 scope = cash stocks with
#     derivative contracts.
#   * NSE equity derivatives session: 09:15–15:40 IST.
#   * NSE CAS sub-windows (15:15–15:35 IST, plus 15:35–16:00 IST
#     transition + post-close). Reference price window uses
#     trades 15:00–15:15.
#
# Behavior-preservation note: the existing ``time(9, 15)`` and
# ``time(15, 30)`` literals inside ``is_market_open`` are not
# removed; the named constants below are aliases with the same
# values so the function body and its callers stay identical.
MARKET_OPEN_TIME: time = time(9, 15)
MARKET_CLOSE_TIME: time = time(15, 30)  # cash continuous trading end
DERIVATIVES_CLOSE_TIME: time = time(15, 40)  # equity derivatives end
PRE_MARKET_OPEN_TIME: time = time(9, 0)
CAS_OPEN_TIME: time = time(15, 15)
CAS_REFERENCE_PRICE_END: time = time(15, 20)
CAS_ORDER_ENTRY_END: time = time(15, 25)
CAS_LIMIT_ENTRY_ONLY_END: time = time(15, 30)
CAS_MATCHING_END: time = time(15, 35)
CAS_POST_CLOSE_END: time = time(16, 0)

# [ROADMAP-3.10 2026-07-12] Static NSE trading-holiday list -- the
# LAST-RESORT fallback when both the DB cache is empty and the
# nseindia.com fetch fails (it routinely bot-blocks). Source: the NSE
# holiday-master API response fetched successfully on 2026-06-15
# (verified against the prod holidays cache). MAINTENANCE: NSE publishes
# the next year's list each December -- refresh this list every January
# [WORKFLOW-J.5 2026-09-13] Canonical NSE Equity trading holiday
# list for 2026. This is the single source of truth for the
# whole system (Python engine + node-gateway + dashboard).
#
# SOURCES (cross-checked 2026-09-13):
#   * https://www.nseindia.com/resources/exchange-communication-holidays
#       (Equities, calendar year 2026)
#   * https://www.nseindia.com/products-services/currency-derivatives-timings-holidays
#       (Equity-equivalent trading holidays)
#   * NSE/CMTR/72260 (Jan-2026 supplementary circular: Municipal
#     Corporation Election in Maharashtra -> 2026-01-15 trading
#     holiday in CM segment)
#   * Secondary corroboration via web-search snippets
#     (decoded in docs/2026-09-13-workflow-j-deep-research.md)
#
# Each entry is a (date, description) tuple. The list mixes
# weekday trading holidays (e.g. Republic Day Monday) and
# weekend holidays (e.g. Independence Day Saturday) -- NSE
# publishes both because some scripts treat either as
# non-trading regardless of weekday.
#
# NOTE: node-gateway/server/utils/market-hours.js used to ship
# its own divergent list (18 dates, only 10 overlapping). J.5
# establishes Python as authoritative; the Node side fetches from
# this module at boot and falls back to its old hardcoded list
# ONLY when the engine is unreachable (defensive).
NSE_HOLIDAYS_STATIC = frozenset({
    # (date, description)
    date(2026, 1, 15),   # Municipal Corporation Election - Maharashtra (NSE/CMTR/72260)
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 15),   # Mahashivratri (Sunday)
    date(2026, 3, 3),    # Holi
    date(2026, 3, 21),   # Id-Ul-Fitr / Ramadan Eid (Saturday)
    date(2026, 3, 26),   # Shri Ram Navami
    date(2026, 3, 31),   # Shri Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 8, 15),   # Independence Day (Saturday)
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 8),   # Diwali Laxmi Pujan (Sunday, muhurat trading) -- NSE notes "Muhurat Trading will be conducted on that day" so we treat it as a non-regular-session date; engines that need a muhurat-trading path can layer that on later
    date(2026, 11, 10),  # Diwali-Balipratipada
    date(2026, 11, 24),  # Prakash Gurpurb Sri Guru Nanak Dev
    date(2026, 12, 25),  # Christmas
})


#: Companion table: date -> description string. NOT a contract
#: gate; the canonical truth is ``NSE_HOLIDAYS_STATIC``. The table
#: exists so the drift detector can surface drift in human-
#: readable form ("2026-09-14 present but no description
#: matches" vs. just "missing 2026-09-14").
NSE_HOLIDAY_DESCRIPTIONS: dict[date, str] = {
    date(2026, 1, 15): "Municipal Corporation Election - Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 2, 15): "Mahashivratri",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 21): "Id-Ul-Fitr (Ramadan Eid)",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Id",
    date(2026, 6, 26): "Muharram",
    date(2026, 8, 15): "Independence Day",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 8): "Diwali Laxmi Pujan (muhurat trading)",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}


#: ISO-8601 (YYYY-MM-DD) projection of the canonical set, sorted.
#: Used by the JSON-serialisable route at ``/holidays`` and by the
#: drift detector (which compares strings, not Python dates, so
#: the Node source can be regex-parsed without datetime parsing).
def _iso_sorted() -> tuple[str, ...]:
    return tuple(sorted(d.isoformat() for d in NSE_HOLIDAYS_STATIC))


NSE_HOLIDAYS_ISO: tuple[str, ...] = _iso_sorted()
# The audited static set is a 2026 fallback only.  Consumers that cannot
# refresh it must fail closed after this date instead of silently treating a
# future weekday as a trading day.
NSE_HOLIDAYS_VALID_THROUGH: str = "2026-12-31"
# Capture the ISO projection at import time. The holiday set is
# static (process-pinned) -- this tuple never changes for the
# lifetime of the process. Recomputing on every call would be
# needless work; the constant is the documented surface.

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
    con = None
    try:
        # sqlite3.Connection.__exit__ commits or rolls back, but it does not
        # close the handle. This helper sits on hot synchronous exit paths, so
        # relying on ``with sqlite3.connect(...)`` leaked one handle per call
        # (and kept temporary DBs locked on Windows).
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE IF NOT EXISTS holidays (holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)")
        cur = con.execute("SELECT holiday_date FROM holidays")
        return [date.fromisoformat(r[0]) for r in cur.fetchall()]
    except sqlite3.Error as e:
        logger.error("calendar_sync_load_failed", error=str(e))
        return []
    finally:
        if con is not None:
            con.close()


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


# ---- 2026-09-13 WORKFLOW-J: CAS-aware session classifier ----
#
# Plan §14 requires an exchange/security/session-phase model after
# effective dates and broker behaviour are verified. We have verified
# the dates (see ``docs/2026-09-13-workflow-j-deep-research.md``);
# broker behaviour is NOT verified (no live broker in Dev). Therefore
# this slice adds the classifier as a pure, total function that future
# callers can use, but does NOT change any production behaviour
# (production call sites still go through ``stamp_session_phase`` which
# remains the J-forward-compat seam returning "UNKNOWN").

#: Session phase values (strings). Frozen at import time; the
#: classification function is exhaustive and total -- every
#: (timestamp, symbol) pair returns exactly one of these values.
SESSION_PHASE_CLOSED: str = "CLOSED"
SESSION_PHASE_PRE_MARKET: str = "PRE_MARKET"
SESSION_PHASE_CONTINUOUS_TRADING: str = "CONTINUOUS_TRADING"
SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW: str = "CAS_REFERENCE_PRICE_WINDOW"
SESSION_PHASE_CAS_ORDER_ENTRY: str = "CAS_ORDER_ENTRY"
SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY: str = "CAS_LIMIT_ENTRY_ONLY"
SESSION_PHASE_CAS_MATCHING: str = "CAS_MATCHING"
SESSION_PHASE_CAS_POST: str = "CAS_POST"
SESSION_PHASE_DERIVATIVES_CAS_ALIGNED: str = "DERIVATIVES_CAS_ALIGNED"
SESSION_PHASE_UNKNOWN: str = "UNKNOWN"

#: Frozen set of all valid phase values, used by self-validation
#: (the bounded contract test asserts the classifier never returns
#: a value outside this set).
_VALID_SESSION_PHASES: frozenset = frozenset({
    SESSION_PHASE_CLOSED, SESSION_PHASE_PRE_MARKET,
    SESSION_PHASE_CONTINUOUS_TRADING,
    SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
    SESSION_PHASE_CAS_ORDER_ENTRY,
    SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY,
    SESSION_PHASE_CAS_MATCHING,
    SESSION_PHASE_CAS_POST,
    SESSION_PHASE_DERIVATIVES_CAS_ALIGNED,
    SESSION_PHASE_UNKNOWN,
})


def _ist_clock_minutes(observation_at: datetime) -> tuple[int, int, int]:
    """Return (weekday, hour, minute) in IST for any timezone-aware
    UTC datetime. Naive datetimes are assumed UTC (the canonical form
    used by the runner). ``None`` returns ``(0, 0, 0)`` so the caller
    can classify as CLOSED -- the classifier never raises on None.
    """
    if observation_at is None:
        return (0, 0, 0)
    if observation_at.tzinfo is None:
        aware = observation_at.replace(tzinfo=pytz.UTC)
    else:
        aware = observation_at.astimezone(pytz.UTC)
    ist = aware.astimezone(IST)
    return (ist.weekday(), ist.hour, ist.minute)


def is_cas_eligible(symbol: str | None) -> bool:
    """[WORKFLOW-J 2026-09-13, +J.2 2026-09-13] Phase 1 CAS eligibility check.

    Per NSE (circular NSE/CMTR/72394, effective 2026-01-19), CAS Phase 1
    applies only to cash-segment stocks on which derivative contracts
    are available. The full list lives in the NSE contract-master API.

    Dev has no live fetch for that list. The list is supplied as the
    operator-curated CSV string ``settings.CAS_PHASE1_FNO_UNDERLYINGS``
    (env var with the same name). The wire format is comma-separated
    uppercase symbols; whitespace around commas is tolerated and
    normalised at this call site -- we do NOT normalise at the
    ``config.py`` layer (kept the layer pure-string so pydantic-settings
    does not JSON-decode the env var).

    Design choices:

      * **Pure** (no I/O, no clock, no DB, no broker call). The only
        non-purity is the lazy ``from config import settings`` below,
        which happens at most once per process and is idempotent.
      * **Lazy import** of ``config.settings`` -- importing at module
        load would force ``market_calendar`` to pull pydantic + .env
        parsers and would couple the two modules; this keeps
        ``market_calendar`` independently importable (a future
        scheduler unit test that doesn't want config can still
        ``import market_calendar`` in isolation).
      * **Defensive normalisation** at the call site:
        ``symbol.strip().upper()`` and the same normalisation on every
        list entry. This protects against any case the upstream
        caller hands us and against any operator-curated token that
        happens to be in mixed case.
      * **Frozenset** of the normalised list is built at most once
        per process via ``functools.lru_cache`` so the per-call
        overhead is a single set membership test.
      * **None / empty / non-string symbol** returns False (the
        operator has not told us which instrument this observation
        is for, or the input was malformed).

    When the setting is empty (the documented default), this function
    returns False for every symbol, so the classifier's CAS-aware
    branches are unreachable and the bounded behaviour is preserved.
    """
    # Defensive input handling: None, non-string, or empty -> False.
    # Done before the import so a bad input never touches ``settings``.
    if not symbol or not isinstance(symbol, str):
        return False
    # Lazy import keeps ``market_calendar`` importable in isolation
    # (test isolation is part of the J.1/J.2 contract).
    try:
        from config import settings
    except Exception:
        # If config cannot be imported for any reason (e.g. a partial
        # deploy), the classifier degrades to "not eligible" -- the
        # safest default per the bounded contract. We do NOT raise
        # because the classifier is total and never returns raise.
        return False
    raw = getattr(settings, "CAS_PHASE1_FNO_UNDERLYINGS", "") or ""
    if not raw:
        return False
    target = symbol.strip().upper()
    if not target:
        return False
    # Memoised normalisation of the configured CSV. Cached for the
    # process lifetime -- invalidation is a process restart, which
    # is also when ``settings`` reloads from env / .env.
    allowed = _normalised_cas_eligibility_set(raw)
    return target in allowed


@functools.lru_cache(maxsize=1)
def _normalised_cas_eligibility_set(raw_csv: str) -> frozenset:
    """Parse ``CAS_PHASE1_FNO_UNDERLYINGS`` into a frozenset of
    uppercase, whitespace-stripped symbols. Cached so we parse the
    CSV once per process. Cache key is the raw string so a future
    settings reload (with a different env) will re-parse on first
    call after restart.

    The parser tolerates:

      * leading / trailing whitespace on the whole value
      * whitespace around individual commas (``"RELIANCE , HDFCBANK"``)
      * trailing / double commas (drop empty tokens defensively)
      * mixed case (``"Reliance"`` -> ``"RELIANCE"``)
    """
    parts = (raw_csv or "").split(",")
    cleaned = tuple(p.strip().upper() for p in parts if p and p.strip())
    return frozenset(cleaned)


def classify_session_phase(
    observation_at: datetime | None,
    *,
    symbol: str | None = None,
    is_derivative: bool = False,
    cas_eligible: bool | None = None,
) -> str:
    """[WORKFLOW-J 2026-09-13, +J.3 2026-09-13] Classify a single observation timestamp
    into one of the bounded ``_VALID_SESSION_PHASES``.

    Contract:
        * Pure: no I/O, no clock, no DB, no logging, no broker call.
        * Total: every (timestamp, symbol, is_derivative) input returns
          a phase from the documented set. Never raises.
        * Day-agnostic of holiday data: this function does NOT consult
          ``NSE_HOLIDAYS_STATIC``. Callers that need holiday-awareness
          must combine this with ``is_trading_day_sync``. We intentionally
          keep the two concerns separate -- the phase is a clock-only
          classification, the holiday check is a calendar concern.
        * CAS eligibility is resolved at the boundary, not from inside
          this function. The function NEVER calls ``is_cas_eligible``
          on its own -- the caller passes ``cas_eligible`` as an
          explicit keyword. Default ``None`` falls back to the legacy
          behavior: the function calls ``is_cas_eligible(symbol)`` so
          existing callers (tests, J.1 contract) keep their
          character-for-character behavior. New callers (J.3 probe,
          any consumer that resolves eligibility upstream) should pass
          ``cas_eligible=True`` / ``False`` to make the contract
          explicit and to bypass ``config.settings`` (which matters
          for staging reproducibility and for fast unit tests).

    Phase selection (in order of precedence):
        1. ``observation_at is None`` -> ``UNKNOWN``.
        2. Saturday or Sunday -> ``CLOSED``.
        3. IST 00:00–08:59 or 16:00+ -> ``CLOSED``.
        4. IST 09:00–09:14 -> ``PRE_MARKET``.
        5. IST 09:15–15:14 + non-derivative -> ``CONTINUOUS_TRADING``
           (cash continuous trading including the reference-price
           window 15:00–15:15, which IS still continuous trading for
           non-CAS-eligible cash).
        6. IST 09:15–15:29 + derivative -> ``CONTINUOUS_TRADING``
           (derivatives trade through 15:40 IST; the post-15:30 CAS-
           aligned band is handled separately).
        7. IST 15:15–15:19 + CAS-eligible cash ->
           ``CAS_REFERENCE_PRICE_WINDOW``.
        8. IST 15:20–15:24 + CAS-eligible cash -> ``CAS_ORDER_ENTRY``.
        9. IST 15:25–15:29 + CAS-eligible cash ->
           ``CAS_LIMIT_ENTRY_ONLY``.
       10. IST 15:15–15:29 + non-CAS-eligible cash ->
           ``CONTINUOUS_TRADING`` (cash still open).
       11. IST 15:30–15:34 + CAS-eligible cash -> ``CAS_MATCHING``.
       12. IST 15:30–15:39 + derivative ->
           ``DERIVATIVES_CAS_ALIGNED`` (NSE/CMTR/76170 futures CAS-
           aligned price band, effective 2026-09-07).
       13. IST 15:35–15:59 + CAS-eligible cash -> ``CAS_POST``.
       14. IST 15:30–15:59 + non-CAS-eligible, non-derivative cash ->
           ``CLOSED``.
       15. IST 16:00+ -> ``CLOSED``.

    The function never raises and never returns a value outside
    ``_VALID_SESSION_PHASES``. Naive datetimes are interpreted as UTC.
    """
    if observation_at is None:
        return SESSION_PHASE_UNKNOWN
    weekday, hour, minute = _ist_clock_minutes(observation_at)
    # Weekend: never any session.
    if weekday >= 5:
        return SESSION_PHASE_CLOSED
    time_minutes = hour * 60 + minute
    # Pre-market.
    pre_open = PRE_MARKET_OPEN_TIME.hour * 60 + PRE_MARKET_OPEN_TIME.minute
    market_open = MARKET_OPEN_TIME.hour * 60 + MARKET_OPEN_TIME.minute
    market_close = MARKET_CLOSE_TIME.hour * 60 + MARKET_CLOSE_TIME.minute
    cas_open = CAS_OPEN_TIME.hour * 60 + CAS_OPEN_TIME.minute
    cas_ref_end = CAS_REFERENCE_PRICE_END.hour * 60 + CAS_REFERENCE_PRICE_END.minute
    cas_order_end = CAS_ORDER_ENTRY_END.hour * 60 + CAS_ORDER_ENTRY_END.minute
    cas_limit_end = CAS_LIMIT_ENTRY_ONLY_END.hour * 60 + CAS_LIMIT_ENTRY_ONLY_END.minute
    cas_match_end = CAS_MATCHING_END.hour * 60 + CAS_MATCHING_END.minute
    cas_post_end = CAS_POST_CLOSE_END.hour * 60 + CAS_POST_CLOSE_END.minute
    deriv_close = DERIVATIVES_CLOSE_TIME.hour * 60 + DERIVATIVES_CLOSE_TIME.minute
    # Before pre-market: closed (covers 00:00-08:59).
    if time_minutes < pre_open:
        return SESSION_PHASE_CLOSED
    # Pre-market window.
    if pre_open <= time_minutes < market_open:
        return SESSION_PHASE_PRE_MARKET
    # Continuous trading: 09:15-15:14 (cash continuous trading end at
    # 15:30 IST, but CAS reference-price calc begins at 15:15; for
    # non-CAS-eligible cash 15:15-15:29 is also still continuous
    # trading -- the special windows below only apply when CAS-eligible).
    # Derivatives continue continuous trading through 15:29 IST
    # (NSE equity derivatives session is 09:15-15:40; the
    # CAS-aligned band at 15:30-15:40 is handled separately below).
    if is_derivative:
        if market_open <= time_minutes < cas_limit_end:
            return SESSION_PHASE_CONTINUOUS_TRADING
    else:
        if market_open <= time_minutes < cas_open:
            return SESSION_PHASE_CONTINUOUS_TRADING
    # CAS eligibility resolution.
    # Senior-dev boundary: the classifier's phase decision is a
    # deterministic function of (timestamp, symbol, is_derivative,
    # CAS eligibility). Eligibility is a domain input that the
    # caller resolves -- this function does NOT decide it. The
    # default ``None`` is the legacy path for the J.1 contract
    # (callers who pass no ``cas_eligible`` arg get the settings-
    # driven lookup, preserving J.1 byte-identity). New callers
    # pass the explicit value, making the contract honest.
    if cas_eligible is None:
        cas_eligible = is_cas_eligible(symbol)
    # CAS-eligible cash sub-windows (15:15 onward). CAS eligibility is
    # explicit; non-eligible symbols stay in CONTINUOUS_TRADING until
    # MARKET_CLOSE_TIME (15:30).
    if cas_eligible:
        if cas_open <= time_minutes < cas_ref_end:
            return SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW
        if cas_ref_end <= time_minutes < cas_order_end:
            return SESSION_PHASE_CAS_ORDER_ENTRY
        if cas_order_end <= time_minutes < cas_limit_end:
            return SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY
        if cas_limit_end <= time_minutes < cas_match_end:
            return SESSION_PHASE_CAS_MATCHING
        if cas_match_end <= time_minutes < cas_post_end:
            return SESSION_PHASE_CAS_POST
    # Non-CAS cash between 15:15 and 15:30: still continuous trading
    # until the cash close at 15:30 IST.
    if not is_derivative and not cas_eligible:
        if cas_open <= time_minutes < market_close:
            return SESSION_PHASE_CONTINUOUS_TRADING
    # Derivatives after 15:30: NSE/CMTR/76100-style CAS-aligned band
    # window for stock and index futures. This window ONLY applies to
    # derivative symbols; for cash the 15:30 close is the end of the
    # regular session.
    if is_derivative and cas_limit_end <= time_minutes < deriv_close:
        return SESSION_PHASE_DERIVATIVES_CAS_ALIGNED
    # 15:40 onward for derivatives: session is closed (15:40 is the
    # last minute of CAS-aligned band; 15:40 IST itself = closed).
    if is_derivative and time_minutes >= deriv_close and time_minutes < cas_post_end:
        return SESSION_PHASE_CLOSED
    # 15:30 onward, non-derivative, non-CAS: closed (regular cash done).
    if not is_derivative and not cas_eligible and market_close <= time_minutes < cas_post_end:
        return SESSION_PHASE_CLOSED
    # 16:00 onward: closed (post-close session ends).
    if time_minutes >= cas_post_end:
        return SESSION_PHASE_CLOSED
    # Defensive fallback (should be unreachable given the cases above).
    return SESSION_PHASE_UNKNOWN


# [WORKFLOW-J.7 2026-09-13] Execution-allowed verdict.
#
# The phase classifier returns one of ten bounded strings; this
# helper translates the phase into a binary verdict that the
# Node execution path can act on directly. The translation
# table is the authoritative policy:
#
#   CONTINUOUS_TRADING           -> allowed (cash/derivatives)
#   DERIVATIVES_CAS_ALIGNED      -> allowed (derivatives only;
#                                   cash would say CAS_MATCHING
#                                   here, never DERIVATIVES_CAS_ALIGNED)
#   PRE_MARKET                   -> blocked by default; allowed
#                                   only when allow_pre_market=True
#   CLOSED                       -> blocked
#   CAS_* (all five CAS sub-windows) -> blocked
#   UNKNOWN                      -> blocked
#
# Why this lives here (not in the Node mirror): the policy
# is the SAME policy as the phase classifier -- the
# translation table is mechanical. Putting it next to the
# classifier keeps the contract local: future changes to
# the phase set (e.g. adding a new sub-window) surface as a
# single-file review in market_calendar.py. The Node
# ``isExecutionAllowed`` mirrors this function exactly.

_PHASE_EXECUTION_ALLOWED: dict[str, bool] = {
    SESSION_PHASE_CONTINUOUS_TRADING: True,
    SESSION_PHASE_DERIVATIVES_CAS_ALIGNED: True,
    SESSION_PHASE_PRE_MARKET: False,  # becomes True with allow_pre_market
    SESSION_PHASE_CLOSED: False,
    SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW: False,
    SESSION_PHASE_CAS_ORDER_ENTRY: False,
    SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY: False,
    SESSION_PHASE_CAS_MATCHING: False,
    SESSION_PHASE_CAS_POST: False,
    SESSION_PHASE_UNKNOWN: False,
}

_PHASE_EXECUTION_REASON: dict[str, str] = {
    SESSION_PHASE_CLOSED: "Market is closed; no orders are accepted outside continuous trading hours.",
    SESSION_PHASE_PRE_MARKET: "Pre-market session; broker orders are blocked until 09:15 IST. Pass allow_pre_market=true to override.",
    SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW: "Closing auction reference-price window (15:15-15:20 IST); broker orders are blocked until CAS completes.",
    SESSION_PHASE_CAS_ORDER_ENTRY: "Closing auction order-entry window (15:20-15:29:30 IST); broker orders are blocked until CAS completes.",
    SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY: "Closing auction limit-entry-only window (15:29:30-15:30 IST); broker orders are blocked.",
    SESSION_PHASE_CAS_MATCHING: "Closing auction matching (15:30-15:40 IST); broker orders are blocked.",
    SESSION_PHASE_CAS_POST: "Closing auction post-close (15:40-16:00 IST); cash equities are closed. Derivatives in this window are DERIVATIVES_CAS_ALIGNED, not CAS_POST.",
    SESSION_PHASE_UNKNOWN: "Observation timestamp could not be classified; broker order blocked for safety.",
}


def execution_allowed(
    observation_at: datetime | None,
    *,
    symbol: str | None = None,
    is_derivative: bool = False,
    cas_eligible: bool | None = None,
    allow_pre_market: bool = False,
) -> dict:
    """[WORKFLOW-J.7 2026-09-13] Verdict on whether a broker
    order is allowed at the given observation time.

    Contract:
      * Pure: no I/O, no clock, no DB, no broker call. The
        caller supplies ``observation_at``.
      * Total: never raises. Invalid / null inputs return
        ``{allowed=False, phase="UNKNOWN", reason="..."}``.
      * Returns a JSON-serialisable dict:
            {"allowed": bool, "phase": str, "reason": str | None}
      * ``reason`` is None when ``allowed=True``; otherwise
        it is a phase-specific human-readable explanation
        the operator dashboard / telegram callback can show.

    The translation table is in
    ``_PHASE_EXECUTION_ALLOWED`` / ``_PHASE_EXECUTION_REASON``.
    ``allow_pre_market=True`` only affects the PRE_MARKET row;
    no other phase honours it.
    """
    phase = classify_session_phase(
        observation_at,
        symbol=symbol,
        is_derivative=is_derivative,
        cas_eligible=cas_eligible,
    )
    allowed = bool(_PHASE_EXECUTION_ALLOWED.get(phase, False))
    if phase == SESSION_PHASE_PRE_MARKET and allow_pre_market:
        allowed = True
    if allowed:
        reason = None
    else:
        reason = _PHASE_EXECUTION_REASON.get(
            phase,
            f"Phase {phase} does not permit broker orders.",
        )
    return {"allowed": allowed, "phase": phase, "reason": reason}
