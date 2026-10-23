"""EDGE overnight paper book: buy the EDGE scan near the close, sell at the next open.

Broker-free. It never imports an executor or places an order. Research basis:
docs/2026-10-05-edge-overnight-study.md. The shipped EDGE candidates earn their
move overnight, while the runtime EDGE buys the following morning.

* 15:20 IST (``run_overnight_entry``): one quote batch gives today's provisional
  bar (open/high/low from the session so far, LTP as the close, volume so far)
  for every cached ticker in or near the EDGE price band. The shipped
  ``scan_today`` ranks them on a temporary copy of recent history plus that bar.
  Each pick is bought on paper at LTP + ``ENTRY_SLIPPAGE_BPS``, capped by 1% of
  today's traded value and by own cash.
* 09:17 IST (``run_overnight_exit``): every open position is sold at today's
  opening-auction price (the quote's ``ohlc.open``) less ``EXIT_SLIPPAGE_BPS``.
  A ticker with no trade today stays open and is retried the next session.
* Restart catch-up (``catch_up``, every 5 min in market hours): a missed exit
  runs later the same session. Up to ``AUCTION_EXIT_LATEST`` it still uses the
  opening-auction price; later it sells at the then-current LTP
  (``CATCHUP_LTP``), never at an auction the process was not present for. A
  missed entry is caught up only before ``ENTRY_LATEST`` (pre-close).
* Waiting-leg retry (``retry_waiting_exits``, from the same catch-up, audit
  Oct 7 T1): after today's EXIT receipt, a position that had no trade at 09:17
  is retried until ``EXIT_LATEST``. It sells at the open (``OPEN_RETRY``) while
  inside the auction grace, else at LTP (``CATCHUP_LTP``). Each refusal keeps
  its exact predicate (``no_quote``, ``no_open_price``, ``no_basis_price``,
  ``no_trade_today`` with the quote's last trade time). Still untraded at
  ``EXIT_LATEST`` means an explicit carry to the next session.
* Telegram summaries are written to an outbox in the same transaction as the
  phase receipt and sent by ``flush_notices``, which marks a notice sent only
  after a 2xx response, so a failed send retries without re-running the book.

Costs use ``penny_risk.calc_penny_costs`` on the delivery (CNC) schedule.
State lives in a sibling store ``<DB_PATH>.edge-overnight-paper.db``; each phase
runs once per day (restart safe) and nothing touches the operational ledger.
"""
from __future__ import annotations

import asyncio
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
import json
import logging
import math
import os
import sqlite3
import tempfile
from typing import Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)

ENTRY_SLIPPAGE_BPS = 25.0
EXIT_SLIPPAGE_BPS = 5.0
MAX_PARTICIPATION = 0.01
MIN_FILL_FRACTION = 0.25
BUY_COST_BUFFER = 0.002
# penny_edge_engine trades closes in [5, 55]; quote a slightly wider band of
# yesterday's closes so a stock that moved into range today is still scored.
UNIVERSE_PRICE_BAND = (4.0, 60.0)
NIFTY_PROXY = "NIFTYBEES"
HISTORY_BARS = 60
IST = ZoneInfo("Asia/Kolkata")
EXIT_START = time(9, 17)
AUCTION_EXIT_LATEST = time(9, 47)     # the 09:17 job's existing misfire grace
EXIT_LATEST = time(15, 20)
RANK_DEPTH = 10
SME_SUFFIXES = ("-SM", "-ST")
SKIP_KINDS = ("MR_mid",)
# [O8-O1 2026-10-08] Entries fill against the visible sell depth: missing
# depth refuses, shares never exceed the displayed ask quantity and the price
# is the walked average ask (never better than the 25 bps model).
# v2 (review, Oct 8 night): the shortlist is re-quoted after the scan, a pick
# whose last trade is older than ENTRY_MAX_TRADE_AGE refuses, and price and
# fees are re-walked for the final (cash-trimmed) share count.
# v3 (follow-up review F1): admission is decided on a clock read after the
# re-quote, refused past ENTRY_LATEST, recorded at that actual time, and each
# quote snapshot must itself be fresh (ENTRY_QUOTE_TTL), separately from the
# last-trade activity rule (ENTRY_MAX_TRADE_AGE).
ENTRY_FILL_CONTRACT = "visible-asks-v3"


@dataclass(frozen=True)
class OvernightShadow:
    """[O21-ON] A forward shadow of this book (research only; it never
    changes the book). ``slots`` None means the book's slot count."""
    name: str
    slots: Optional[int]
    fill_cash_share: bool
    max_entry_cost_pct: Optional[float]
    rationale: str


# [O21-ON 2026-10-21] Declared before any scoring, from the book's own cost
# structure. Over the 16 trades with a recorded split, close->open earned
# +Rs 986.97 (about +0.77% a trade); the spread paid at the ask cost Rs 462.11
# (about 0.36%; 15:20->close drift only -Rs 108, mixed signs) and delivery
# charges about Rs 33 a trade (about 0.42% at Rs 8k, the DP charge being fixed
# per scrip). The edge is real; the costs take it. Each shadow uses the same
# ranked picks, re-quote and decision time at entry and the same exit quotes,
# with its own cash (EDGE_OVERNIGHT_PAPER_BANKROLL + its realised P&L).
OVERNIGHT_SHADOWS_DECLARED = "2026-10-21"
OVERNIGHT_SHADOWS = (
    OvernightShadow("ON_TWO_LARGER", 2, True, None,
                    "two equal positions of half the book each: the fixed DP charge and the per-order "
                    "minimums weigh less per rupee"),
    OvernightShadow("ON_TIGHT_SPREAD", None, False, 0.0035,
                    "only picks filled within 0.35% of LTP (edge 0.77% less charges 0.42%), so the spread "
                    "cannot take the edge"),
)
ENTRY_MAX_TRADE_AGE = timedelta(minutes=30)     # activity: the stock traded recently
ENTRY_QUOTE_TTL = timedelta(seconds=120)        # snapshot: the displayed depth is current
ENTRY_QUOTE_MAX_AHEAD = timedelta(seconds=5)    # provider clock may lead ours by this much


def prior_session(today_iso: str, db_path: str) -> str:
    """The trading session before ``today_iso`` (weekends and cached NSE holidays).

    Cache only, never the network: ``market_calendar._load_holidays_sync``.
    """
    from datetime import date, timedelta
    from market_calendar import _load_holidays_sync
    holidays = set(_load_holidays_sync(db_path))
    day = date.fromisoformat(today_iso) - timedelta(days=1)
    while day.weekday() >= 5 or day in holidays:
        day -= timedelta(days=1)
    return day.isoformat()


def _price_exit(quote: dict, *, today: str, auction: bool, trade_date: str, ticker: str,
                entry_price: float, shares: int, delayed: bool, entry_session_prior: bool,
                retry: bool = False) -> tuple[Optional[dict], Optional[dict]]:
    """(closed item, None) or (None, waiting item with the exact refusal predicate)."""
    from penny_risk import calc_penny_costs
    quote = quote or {}
    ohlc = quote.get("ohlc") or {}
    open_price = ohlc.get("open")
    basis = open_price if auction else quote.get("last_price")
    stamp = str(quote.get("last_trade_time") or quote.get("timestamp") or "")
    refusal = ("no_quote" if not quote else "no_open_price" if not _finite_positive(open_price)
               else "no_basis_price" if not _finite_positive(basis)
               else "no_trade_today" if not stamp.startswith(today) else None)
    if refusal is not None:
        return None, {"ticker": ticker, "trade_date": trade_date, "reason": refusal,
                      "last_trade_time": stamp[:19] or None}
    exit_price = round(float(basis) * (1 - EXIT_SLIPPAGE_BPS / 10000.0), 4)
    costs = float(calc_penny_costs(entry_price, exit_price, shares, is_intraday=False))
    net = round((exit_price - entry_price) * shares - costs, 4)
    reason = ("CATCHUP_LTP" if not auction else "OPEN_DELAYED" if delayed
              else "OPEN_RETRY" if retry else "NEXT_OPEN")
    item = {"trade_date": trade_date, "ticker": ticker, "exit_open": float(open_price),
            "exit_price": exit_price, "costs": round(costs, 4), "net_pnl": net, "reason": reason}
    # [S23-S1 2026-10-23] The modelled exit is the open less 5 bp, but the
    # exit runs at 09:17 and two Oct 23 entries showed ~3% displayed spreads.
    # Record what selling into the quote's best bid would have paid, so the
    # comparison can show how far the model sits above it. Measurement only.
    bid = _best_bid(quote)
    if bid is not None:
        bid_costs = float(calc_penny_costs(entry_price, bid, shares, is_intraday=False))
        item["exit_bid"] = bid
        item["exit_bid_net"] = round((bid - entry_price) * shares - bid_costs, 4)
    # [OVERNIGHT-ATTRIBUTION 2026-10-06, date-checked 2026-10-07 T3] A quote's
    # ohlc.close is the PREVIOUS session's close. It is the entry day's close
    # only when the entry day is the session right before today; a missed
    # session (with or without a failed attempt) would mislabel a later close,
    # so the split is then left out.
    prior_close = ohlc.get("close")
    # An open equal to the previous close may be a no-equilibrium pre-open
    # placeholder, but a discovered open can also equal it, so this is an
    # equality flag for measurement only, not proof of an untraded open.
    # The Oct 5-7 fills had 3 of 6 exactly so.
    if _finite_positive(prior_close):
        item["open_is_prev_close"] = float(open_price) == float(prior_close)
    if entry_session_prior and _finite_positive(prior_close):
        item["entry_day_close"] = float(prior_close)
        item["entry_vs_close_rs"] = round((float(prior_close) - entry_price) * shares, 4)
        item["overnight_rs"] = round((float(open_price) - float(prior_close)) * shares, 4)
        if not auction:
            item["after_open_rs"] = round((float(basis) - float(open_price)) * shares, 4)
    return item, None
ENTRY_CATCHUP_START = time(15, 21)  # after the 15:20 job's own run
ENTRY_LATEST = time(15, 29)
CATCHUP_EVERY_MINUTES = 5           # scheduler_setup edge_overnight_catchup cadence
ENTRY_MIN_QUOTE_COVERAGE = 0.5      # normal days quote ~90% of the universe (877/967 Oct 8)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS edge_overnight_paper_trades (
        trade_date TEXT NOT NULL, ticker TEXT NOT NULL, kind TEXT NOT NULL, strength REAL NOT NULL,
        entry_ltp REAL NOT NULL, entry_price REAL NOT NULL, shares INTEGER NOT NULL, entry_ts TEXT NOT NULL,
        status TEXT NOT NULL, exit_date TEXT, exit_open REAL, exit_price REAL, costs REAL, net_pnl REAL,
        exit_reason TEXT, exit_attempts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (trade_date, ticker))""",
    """CREATE TABLE IF NOT EXISTS edge_overnight_paper_runs (
        run_date TEXT NOT NULL, phase TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (run_date, phase))""",
    """CREATE TABLE IF NOT EXISTS edge_overnight_paper_notices (
        run_date TEXT NOT NULL, phase TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL,
        sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (run_date, phase))""",
    # [O21-ON] Shadow books: one row per variant and position.
    """CREATE TABLE IF NOT EXISTS edge_overnight_shadow_trades (
        variant TEXT NOT NULL, trade_date TEXT NOT NULL, ticker TEXT NOT NULL, kind TEXT NOT NULL,
        entry_ltp REAL NOT NULL, entry_price REAL NOT NULL, shares INTEGER NOT NULL, entry_ts TEXT NOT NULL,
        status TEXT NOT NULL, exit_date TEXT, exit_open REAL, exit_price REAL, costs REAL, net_pnl REAL,
        exit_reason TEXT, entry_day_close REAL, PRIMARY KEY (variant, trade_date, ticker))""",
)


def overnight_db_path(db_path: str) -> str:
    return f"{db_path}.edge-overnight-paper.db"


@contextmanager
def _store(path: str):
    """One transaction on the paper store; the handle is always closed."""
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(edge_overnight_paper_trades)")}
        if "entry_day_close" not in columns:
            conn.execute("ALTER TABLE edge_overnight_paper_trades ADD COLUMN entry_day_close REAL")
        # [S23-S1 2026-10-23] Displayed bid/ask at entry; the bid on the exit
        # quote and the net had the position been sold there.
        for table in ("edge_overnight_paper_trades", "edge_overnight_shadow_trades"):
            have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column in ("entry_bid", "entry_ask", "exit_bid", "exit_bid_net"):
                if column not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} REAL")
        notice_columns = {row[1] for row in conn.execute("PRAGMA table_info(edge_overnight_paper_notices)")}
        for column in ("next_attempt_at", "last_error"):
            if column not in notice_columns:
                conn.execute(f"ALTER TABLE edge_overnight_paper_notices ADD COLUMN {column} TEXT")
        with conn:
            yield conn


def _read_only(path: str):
    return closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True))


def _finite_positive(value) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def buy_charges(entry_price: float, shares: int) -> float:
    """Delivery buy-side charges (STT, stamp, exchange, SEBI, IPFT, GST).

    ``calc_penny_costs`` with a zero sell leg is the buy side plus the DP
    charge, which belongs to the sell. The full round trip is still booked
    once, at exit; this only reserves the buy part while a position is open.
    """
    from penny_risk import calc_penny_costs
    if shares < 1:
        return 0.0
    whole = float(calc_penny_costs(entry_price, 0.0, shares, is_intraday=False))
    return round(max(0.0, whole - float(settings.PENNY_CNC_DP_CHARGE)), 4)


def book_state(conn: sqlite3.Connection, bankroll: float) -> dict:
    """Equity is bankroll + realized P&L; cash also reserves each open
    position's premium and buy charges (rebuilt the same way after a restart)."""
    realized = conn.execute(
        "SELECT COALESCE(SUM(net_pnl), 0), COUNT(*), COALESCE(SUM(net_pnl > 0), 0) "
        "FROM edge_overnight_paper_trades WHERE status='CLOSED'").fetchone()
    held = conn.execute(
        "SELECT ticker, entry_price, shares FROM edge_overnight_paper_trades WHERE status='OPEN'").fetchall()
    equity = bankroll + float(realized[0])
    reserved = sum(buy_charges(price, shares) for _, price, shares in held)
    return {"equity": round(equity, 4), "realized_pnl": round(float(realized[0]), 4), "closed": int(realized[1]),
            "wins": int(realized[2]), "held": {ticker: price * shares for ticker, price, shares in held},
            "reserved_buy_charges": round(reserved, 4),
            "cash": round(equity - sum(price * shares for _, price, shares in held) - reserved, 4)}


def shadows_enabled() -> bool:
    return bool(getattr(settings, "EDGE_OVERNIGHT_SHADOWS_ENABLED", True))


def shadow_state(conn: sqlite3.Connection, variant: str, bankroll: float) -> dict:
    """A shadow's own book: the same equity/cash rule as ``book_state``."""
    realized = conn.execute("SELECT COALESCE(SUM(net_pnl), 0) FROM edge_overnight_shadow_trades "
                            "WHERE variant=? AND status='CLOSED'", (variant,)).fetchone()[0]
    held = conn.execute("SELECT ticker, entry_price, shares FROM edge_overnight_shadow_trades "
                        "WHERE variant=? AND status='OPEN'", (variant,)).fetchall()
    equity = bankroll + float(realized)
    reserved = sum(buy_charges(price, shares) for _, price, shares in held)
    return {"equity": round(equity, 4), "held": {ticker: price * shares for ticker, price, shares in held},
            "cash": round(equity - sum(price * shares for _, price, shares in held) - reserved, 4)}


def _shadow_entries(picks, fresh: dict, shadow_states: dict, *, today: str, decided: datetime,
                    late: Optional[dict]) -> dict:
    out = {}
    for shadow in OVERNIGHT_SHADOWS:
        state = shadow_states.get(shadow.name)
        if state is None:
            continue
        slots = shadow.slots or int(settings.PENNY_EDGE_MAX_POSITIONS)
        opened, skipped, cash = _admit(picks, fresh, state, slots=slots, today=today, decided=decided, late=late,
                                       fill_cash_share=shadow.fill_cash_share,
                                       max_entry_cost_pct=shadow.max_entry_cost_pct)
        out[shadow.name] = {"opened": opened, "skipped": skipped, "cash_after": round(cash, 4)}
    return out


def _shadow_open(conn: sqlite3.Connection, today: str) -> list:
    if not shadows_enabled():
        return []
    return conn.execute("SELECT variant, trade_date, ticker, entry_price, shares FROM edge_overnight_shadow_trades "
                        "WHERE status='OPEN' AND trade_date < ?", (today,)).fetchall()


def _price_shadows(rows: list, quotes: dict, *, today: str, auction: bool, session_before: Optional[str],
                   retry: bool) -> list[dict]:
    """Shadow exits priced exactly as the book's (``_price_exit``) on the same quotes."""
    closed = []
    for variant, trade_date, ticker, entry_price, shares in rows:
        first = trade_date == session_before
        item, _wait = _price_exit(quotes.get(ticker), today=today, auction=auction, trade_date=trade_date,
                                  ticker=ticker, entry_price=entry_price, shares=shares, delayed=not first,
                                  entry_session_prior=first, retry=retry)
        if item is not None:
            closed.append({**item, "variant": variant})
    return closed


def _close_shadow_items(conn: sqlite3.Connection, today: str, closed: list[dict]) -> None:
    for c in closed:
        conn.execute(
            "UPDATE edge_overnight_shadow_trades SET status='CLOSED', exit_date=?, exit_open=?, exit_price=?, "
            "costs=?, net_pnl=?, exit_reason=?, entry_day_close=?, exit_bid=?, exit_bid_net=? "
            "WHERE variant=? AND trade_date=? AND ticker=? AND status='OPEN'",
            (today, c["exit_open"], c["exit_price"], c["costs"], c["net_pnl"], c["reason"],
             c.get("entry_day_close"), c.get("exit_bid"), c.get("exit_bid_net"),
             c["variant"], c["trade_date"], c["ticker"]))


def _already_ran(conn: sqlite3.Connection, day: str, phase: str) -> Optional[dict]:
    row = conn.execute("SELECT summary FROM edge_overnight_paper_runs WHERE run_date=? AND phase=?",
                       (day, phase)).fetchone()
    return json.loads(row[0]) if row else None


def _record_run(conn: sqlite3.Connection, day: str, phase: str, summary: dict, now: datetime,
                message: Optional[str] = None) -> None:
    conn.execute("INSERT OR REPLACE INTO edge_overnight_paper_runs VALUES (?,?,?,?)",
                 (day, phase, json.dumps(summary, sort_keys=True), now.isoformat()))
    if message:
        # Over-long notices become numbered parts, each acknowledged on its
        # own row (the expiry book's splitter; Telegram refuses > 4,096).
        from expiry_paper import notice_parts
        parts = notice_parts(message)
        keys = [phase] if len(parts) == 1 else [f"{phase}:part{i:02d}of{len(parts):02d}"
                                               for i in range(1, len(parts) + 1)]
        conn.executemany("INSERT OR IGNORE INTO edge_overnight_paper_notices (run_date, phase, message, created_at) "
                         "VALUES (?,?,?,?)", [(day, key, part, now.isoformat()) for key, part in zip(keys, parts)])


def _dated_for_delivery(message: str, run_date: str, now: datetime) -> str:
    """[O15-D2 2026-10-15] A notice delivered on a later day says whose day it
    is. Oct 15 09:00 delivered Oct 14's "NO ENTRY - quotes unavailable" with
    no date, reading like that morning's result. The stored text is unchanged."""
    from datetime import date
    try:
        day = date.fromisoformat(str(run_date))
    except ValueError:
        return message
    if day >= now.astimezone(IST).date():
        return message
    return f"[{day.strftime('%a %d %b')}, delivered late] {message}"


_FLUSH_LOCKS: dict[str, asyncio.Lock] = {}
NOTICE_STEP_OVER_AFTER = 3          # unknown-cause failures before a notice may be stepped over


async def flush_notices(send: Callable[[str], Awaitable[None]], db_path: Optional[str] = None,
                        now: Optional[datetime] = None) -> int:
    """Send unsent phase summaries oldest first; ``send`` raises on failure.

    Flushes of one store are serialised (the phase jobs and the catch-up can
    overlap), so a row is never sent twice concurrently; ``sent_at`` is the
    acknowledgement time. Delivery is at-least-once across a crash or a lost
    acknowledgement.

    Failures follow ``notice_outbox``: a message the gateway rejects (422)
    is stepped over at once and retried on a backoff, so any number of bad
    notices cannot block healthy ones; a transport failure stops the round
    in order; an unknown failure keeps order for NOTICE_STEP_OVER_AFTER tries.
    Rows backing off are skipped until due. Failed rows are kept with
    ``last_error`` for inspection.
    """
    import notice_outbox

    store = overnight_db_path(db_path or settings.DB_PATH)
    async with _FLUSH_LOCKS.setdefault(store, asyncio.Lock()):
        with _store(store) as conn:
            pending = conn.execute("SELECT run_date, phase, message, attempts, next_attempt_at "
                                   "FROM edge_overnight_paper_notices WHERE sent_at IS NULL "
                                   "ORDER BY created_at, phase").fetchall()
        sent = 0
        for day, phase, message, attempts, next_attempt_at in pending:
            clock = now or datetime.now(IST)
            if not notice_outbox.is_due(next_attempt_at, clock):
                continue
            try:
                await send(_dated_for_delivery(message, day, clock))
            except Exception as exc:
                kind = notice_outbox.classify_send_failure(exc)
                go_on, retry_at = notice_outbox.after_failure(kind, attempts + 1, clock)
                logger.warning("edge_overnight_notice_failed date=%s phase=%s attempts=%d kind=%s err=%s%s",
                               day, phase, attempts + 1, kind, type(exc).__name__,
                               " stepped_over" if go_on else "")
                with _store(store) as conn:
                    conn.execute("UPDATE edge_overnight_paper_notices SET attempts = attempts + 1, "
                                 "next_attempt_at=?, last_error=? WHERE run_date=? AND phase=?",
                                 (retry_at, f"{kind}:{type(exc).__name__}", day, phase))
                if not go_on:
                    break
                continue
            acked = now or datetime.now(IST)
            with _store(store) as conn:
                conn.execute("UPDATE edge_overnight_paper_notices SET sent_at=?, attempts = attempts + 1, "
                             "next_attempt_at=NULL WHERE run_date=? AND phase=?", (acked.isoformat(), day, phase))
            sent += 1
        return sent


async def catch_up(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> list[str]:
    """Run a phase whose receipt is missing today, inside its permitted window."""
    db_path = db_path or settings.DB_PATH
    wall_clock = now is None          # a live call decides entries on the wall clock (F1)
    now = now or datetime.now(IST)
    today, clock = now.date().isoformat(), now.time()
    with _store(overnight_db_path(db_path)) as conn:
        has_exit = _already_ran(conn, today, "EXIT") is not None
        has_entry = _already_ran(conn, today, "ENTRY") is not None
    ran = []
    if not has_exit and EXIT_START <= clock < EXIT_LATEST:
        summary = await run_overnight_exit(kite, db_path, now)
        if not summary.get("repeat"):
            ran.append("EXIT")
    elif has_exit and EXIT_START <= clock < EXIT_LATEST:
        retried = await retry_waiting_exits(kite, db_path, now)
        if retried.get("closed"):
            ran.append("EXIT_RETRY")
    if not has_entry and ENTRY_CATCHUP_START <= clock <= ENTRY_LATEST:
        summary = await run_overnight_entry(kite, db_path, now,
                                            clock=(lambda: datetime.now(IST)) if wall_clock else None)
        if not summary.get("repeat"):
            ran.append("ENTRY")
    if ran:
        logger.warning("edge_overnight_catch_up date=%s phases=%s at=%s", today, ",".join(ran),
                       now.strftime("%H:%M:%S"))
    return ran


def universe_from_cache(cache_path: str) -> list[str]:
    """Tickers whose latest cached close (last 10 days of data) is near the EDGE band."""
    lo, hi = UNIVERSE_PRICE_BAND
    with _read_only(cache_path) as conn:
        latest = conn.execute("SELECT MAX(date) FROM ohlcv_cache").fetchone()[0]
        if latest is None:
            return []
        rows = conn.execute("""
            SELECT c.ticker FROM ohlcv_cache c
            JOIN (SELECT ticker, MAX(date) AS d FROM ohlcv_cache WHERE date >= date(?, '-10 days') GROUP BY ticker) m
              ON c.ticker = m.ticker AND c.date = m.d
            WHERE c.close BETWEEN ? AND ?""", (latest, lo, hi)).fetchall()
    return sorted({r[0] for r in rows} - {NIFTY_PROXY})


def provisional_bar(quote: dict, today: str) -> Optional[tuple]:
    """Today's (open, high, low, close=LTP, volume) from a quote, or None."""
    ohlc = quote.get("ohlc") or {}
    values = (ohlc.get("open"), ohlc.get("high"), ohlc.get("low"), quote.get("last_price"))
    volume = quote.get("volume") or quote.get("volume_traded")
    if not all(_finite_positive(v) for v in values) or not _finite_positive(volume):
        return None
    stamp = str(quote.get("last_trade_time") or quote.get("timestamp") or "")
    if stamp and not stamp.startswith(today):
        return None
    o, h, l, c = (float(v) for v in values)
    if not l <= min(o, c) <= max(o, c) <= h:
        return None
    return o, h, l, c, float(volume)


def build_scan_db(cache_path: str, tickers: list[str], bars_today: dict, today: str) -> str:
    """Temporary ohlcv_cache: recent history (before today) plus today's provisional bars."""
    fd, path = tempfile.mkstemp(prefix="sentinel-edge-overnight-", suffix=".sqlite")
    os.close(fd)
    names = [*tickers, NIFTY_PROXY]
    with _read_only(cache_path) as src, closing(sqlite3.connect(path)) as dst, dst:
        dst.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
                    "close REAL, volume REAL, PRIMARY KEY (ticker, date))")
        for name in names:
            rows = src.execute("""
                SELECT ticker, date, open, high, low, close, volume FROM ohlcv_cache
                WHERE ticker=? AND date < ? ORDER BY date DESC LIMIT ?""", (name, today, HISTORY_BARS)).fetchall()
            dst.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
        dst.executemany("INSERT OR REPLACE INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)",
                        [(t, today, *bar) for t, bar in bars_today.items()])
    return path


SYMBOL_QUOTE_CHUNK = 500           # Kite full-quote limit per request


async def _quotes(kite, tickers: list[str]) -> dict:
    tokens, missing = {}, []
    cache = getattr(kite, "instrument_cache", None) or {}
    for ticker in tickers:
        token = cache.get(ticker)
        if token is not None:
            tokens[int(token)] = ticker
        else:
            missing.append(ticker)
    out = {}
    if tokens:
        raw = await kite.get_quote(list(tokens))
        out = {tokens[int(token)]: quote for token, quote in (raw or {}).items() if int(token) in tokens}
    # [O9-O1 2026-10-09] The empty post-restart cache left the Oct 9 entry
    # with 0 of 971 names quoted. A name the cache cannot resolve is quoted
    # by its documented EXCHANGE:SYMBOL key, in chunks of the 500-key limit.
    if missing and hasattr(kite, "get_quote_by_instruments"):
        for start in range(0, len(missing), SYMBOL_QUOTE_CHUNK):
            chunk = missing[start:start + SYMBOL_QUOTE_CHUNK]
            keyed = {-(start + i + 1): f"NSE:{ticker}" for i, ticker in enumerate(chunk)}
            raw = await kite.get_quote_by_instruments(keyed)
            out.update({chunk[-key - start - 1]: quote for key, quote in (raw or {}).items()
                        if key in keyed})
    return out


def base_symbol(ticker: str) -> str:
    """One company across its series twins (``CALSOFT`` / ``CALSOFT-BE``)."""
    return ticker.split("-")[0]


def visible_asks(quote: dict) -> Optional[list[tuple[float, int]]]:
    """Valid ``(price, quantity)`` sell levels, or ``None`` when depth is absent.

    ``None`` (no depth object or no sell list) is a data gap; ``[]`` means the
    book was quoted but nobody is selling.
    """
    depth = quote.get("depth")
    sell = depth.get("sell") if isinstance(depth, dict) else None
    if not isinstance(sell, list):
        return None
    asks = []
    for level in sell:
        if not isinstance(level, dict):
            continue
        price, qty = level.get("price"), level.get("quantity")
        if _finite_positive(price) and _finite_positive(qty):
            asks.append((float(price), int(qty)))
    return sorted(asks)


def walk_asks(asks: list[tuple[float, int]], shares: int) -> tuple[int, Optional[float]]:
    """Shares the visible asks can fill (up to ``shares``) and their average price."""
    filled, cost = 0, 0.0
    for price, qty in asks:
        take = min(qty, shares - filled)
        if take <= 0:
            break
        filled += take
        cost += take * price
    return filled, (cost / filled if filled else None)


def _best_bid(quote: dict) -> Optional[float]:
    depth = quote.get("depth")
    bids = depth.get("buy") if isinstance(depth, dict) else None
    prices = [float(level["price"]) for level in bids or [] if isinstance(level, dict)
              and _finite_positive(level.get("price")) and _finite_positive(level.get("quantity"))]
    return max(prices) if prices else None


def _stamp_age(quote: dict, field: str, now: datetime) -> Optional[timedelta]:
    """Age at ``now`` of a quote timestamp field, or ``None`` when absent/unparseable."""
    raw = quote.get(field)
    if raw in (None, ""):
        return None
    try:
        stamp = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=IST)
    return now - stamp


def _trade_age(quote: dict, now: datetime) -> Optional[timedelta]:
    """Age of the quote's last trade at ``now`` (trading activity)."""
    return _stamp_age(quote, "last_trade_time", now)


def snapshot_refusal(quote: dict, now: datetime) -> Optional[str]:
    """Why the quote packet itself is not current at ``now``, else ``None``."""
    age = _stamp_age(quote, "timestamp", now)
    if age is None:
        return "no_quote_timestamp"
    if age < -ENTRY_QUOTE_MAX_AHEAD:
        return "quote_time_ahead"
    if age > ENTRY_QUOTE_TTL:
        return "stale_quote_snapshot"
    return None


def price_for_cash(asks: list[tuple[float, int]], wanted: int, model_price: float,
                   cash: float) -> tuple[int, float]:
    """Largest share count up to ``wanted`` whose walked price plus buy charges
    fit ``cash``, and that price (never below ``model_price``)."""
    def priced(n: int) -> float:
        _filled, walked = walk_asks(asks, n)
        return round(max(model_price, walked or 0.0), 4)

    def fits(n: int) -> bool:
        price = priced(n)
        return price * n + buy_charges(price, n) <= cash

    shares = wanted
    while shares > 0 and not fits(shares):
        shares = min(shares - 1, int(cash // (priced(shares) * (1 + BUY_COST_BUFFER))))
    # The estimate above uses the larger order's (higher) average; grow back
    # while the next share still fits at its own walked price.
    while 0 < shares < wanted and fits(shares + 1):
        shares += 1
    return (shares, priced(shares)) if shares > 0 else (0, round(model_price, 4))


def realism_refusal(ticker: str, kind: str, quote: dict, bar: tuple, taken_bases: set) -> Optional[str]:
    """[EDGE-OVERNIGHT-REALISM 2026-10-07] Why a pick cannot be bought honestly, else ``None``.

    The live-universe replay (docs/research/edge-overnight/2026-10-07-live-universe)
    found 75% of the modeled profit came from closes locked at the day's high
    after a rise, which have no sellers and cannot be bought at the close.
    Without them, and without SME or duplicate-series picks and the weak
    ``MR_mid`` kind, the book was positive in every quarter
    (+0.62% a trade, max drawdown 13.4% from peak, Jul 2025-Oct 2026).
    """
    series = series_refusal(ticker, kind, taken_bases)
    if series is not None:
        return series
    ltp = bar[3]
    upper = quote.get("upper_circuit_limit")
    if _finite_positive(upper) and ltp >= float(upper) * (1 - 0.005):
        return "at_upper_circuit"
    asks = visible_asks(quote)
    if asks is None:
        return "no_depth"
    if not asks:
        return "no_sellers"
    return day_high_refusal(bar, (quote.get("ohlc") or {}).get("close"))


# The two parts of realism_refusal a daily bar decides on its own; the EDGE
# portfolio replay (EDGE_OVERNIGHT_RUNTIME) applies them unchanged.
def series_refusal(ticker: str, kind: str, taken_bases: set) -> Optional[str]:
    if ticker.endswith(SME_SUFFIXES):
        return "sme_series"
    if base_symbol(ticker) in taken_bases:
        return "duplicate_series"
    if kind in SKIP_KINDS:
        return f"weak_kind_{kind}"
    return None


def day_high_refusal(bar: tuple, prev_close) -> Optional[str]:
    """A close locked at the day's high after a >= 1.9% rise has no sellers."""
    _open, high, _low, ltp, _volume = bar
    if _finite_positive(prev_close) and ltp >= high * 0.999 and ltp / float(prev_close) - 1 >= 0.019:
        return "at_day_high_after_rise"
    return None


def _admit(picks, fresh: dict, state: dict, *, slots: int, today: str, decided: datetime,
           late: Optional[dict], fill_cash_share: bool = False,
           max_entry_cost_pct: Optional[float] = None) -> tuple[list, list, float]:
    """Admit ranked picks into one book: (opened, skipped, cash left).

    The book calls it with the defaults. [O21-ON] A shadow changes only its
    declared fields: ``fill_cash_share`` sizes each pick to its equal share
    of equity instead of the scan's risk plan; ``max_entry_cost_pct`` refuses
    a pick whose fill is further above LTP (it does not use a slot).
    """
    held_bases = {base_symbol(t) for t in state["held"]}
    cash, opened, skipped = state["cash"], [], []
    for pick in picks:
        if late is not None:
            skipped.append({"ticker": pick.ticker, **late})
            continue
        if len(opened) >= slots:
            break
        if pick.ticker in state["held"]:
            skipped.append({"ticker": pick.ticker, "reason": "already_held"})
            continue
        quote = fresh.get(pick.ticker) or {}
        bar = provisional_bar(quote, today)
        if bar is None:
            skipped.append({"ticker": pick.ticker, "reason": "no_fresh_quote"})
            continue
        stale = snapshot_refusal(quote, decided)
        if stale is not None:
            skipped.append({"ticker": pick.ticker, "reason": stale,
                            "quote_timestamp": str(quote.get("timestamp") or "")})
            continue
        age = _trade_age(quote, decided)
        if age is None or age > ENTRY_MAX_TRADE_AGE:
            skipped.append({"ticker": pick.ticker, "reason": "stale_last_trade",
                            "last_trade_time": str(quote.get("last_trade_time") or "")})
            continue
        refusal = realism_refusal(pick.ticker, pick.signal_subtype, quote, bar,
                                  held_bases | {base_symbol(o["ticker"]) for o in opened})
        if refusal is not None:
            skipped.append({"ticker": pick.ticker, "reason": refusal})
            continue
        ltp, volume = bar[3], bar[4]
        asks = visible_asks(quote) or []
        visible = sum(qty for _price, qty in asks)
        model_price = ltp * (1 + ENTRY_SLIPPAGE_BPS / 10000.0)
        capacity = int(MAX_PARTICIPATION * ltp * volume // model_price)
        planned = int(state["equity"] / slots // model_price) if fill_cash_share else int(pick.shares)
        wanted = min(planned, capacity, visible)
        # [O1 2026-10-06] Each admission fits premium plus its own buy charges
        # inside the cash left after earlier picks. The asks are re-walked for
        # the final share count, so price and fees match what is bought.
        # [O19-O1] Each pick may use at most an equal share of the cash still
        # free (cash / open slots), so cash a smaller pick leaves passes to the
        # later picks. Risk sizing alone let one name take half the book (Oct 19
        # KMSUGAR, 50%) and left the third pick cash-limited.
        # The quarter-of-plan dust floor is measured against the plan capped at
        # an equal share of equity, so the cap itself never refuses a pick.
        share_cash = cash / (slots - len(opened))
        plan = min(planned, int(state["equity"] / slots // model_price))
        shares, entry_price = price_for_cash(asks, wanted, model_price, share_cash)
        if shares < 1 or shares < MIN_FILL_FRACTION * plan:
            reason = ("cash" if shares < wanted
                      else "thin_asks" if visible == wanted < planned
                      else "liquidity")
            skipped.append({"ticker": pick.ticker, "reason": f"{reason}_below_quarter_of_plan",
                            "planned": planned, "capacity": capacity, "affordable": shares,
                            "visible_ask_qty": visible})
            continue
        if max_entry_cost_pct is not None and entry_price > ltp * (1 + max_entry_cost_pct):
            skipped.append({"ticker": pick.ticker, "reason": "entry_cost_above_limit",
                            "entry_cost_pct": round(entry_price / ltp - 1, 6)})
            continue
        charges = buy_charges(entry_price, shares)
        cash -= entry_price * shares + charges
        _filled, walked_avg = walk_asks(asks, shares)
        # [O12 rec 10 2026-10-12] The receipt keeps the whole visible ladder,
        # the walked average and which floor set the price, so an audit can
        # re-walk the fill instead of seeing only the best ask and a total.
        opened.append({"ticker": pick.ticker, "kind": pick.signal_subtype,
                       "strength": round(float(pick.adjusted_strength), 4), "entry_ltp": ltp,
                       "entry_price": entry_price, "shares": shares, "buy_charges": charges,
                       "planned": planned, "visible_ask_qty": visible,
                       "best_ask": asks[0][0] if asks else None, "best_bid": _best_bid(quote),
                       "ask_levels": [[price, qty] for price, qty in asks],
                       "walked_avg": round(walked_avg, 4) if walked_avg is not None else None,
                       "price_basis": ("ask_walk" if walked_avg is not None and walked_avg > model_price
                                       else "slippage_floor"),
                       "capacity": capacity,
                       "quote_ts": str(quote.get("timestamp") or quote.get("last_trade_time") or "")})
    return opened, skipped, cash


async def run_overnight_entry(kite, db_path: Optional[str] = None, now: Optional[datetime] = None,
                              clock: Optional[Callable[[], datetime]] = None) -> dict:
    """15:20 IST: score today's provisional bars and open the paper picks.

    ``now`` starts the run; ``clock`` gives the admission decision time after
    the scan and re-quote (defaults to the wall clock, or to ``now`` when only
    ``now`` is injected).
    """
    from penny_edge_live import scan_today

    db_path = db_path or settings.DB_PATH
    if clock is None:
        clock = (lambda: now) if now is not None else (lambda: datetime.now(IST))
    now = now or clock()
    today = now.date().isoformat()
    store = overnight_db_path(db_path)
    with _store(store) as conn:
        previous = _already_ran(conn, today, "ENTRY")
        if previous is not None:
            return {**previous, "repeat": True}
        state = book_state(conn, float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL))
        shadow_states = ({shadow.name: shadow_state(conn, shadow.name, float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL))
                          for shadow in OVERNIGHT_SHADOWS} if shadows_enabled() else {})

    tickers = universe_from_cache(db_path)
    quotes = await _quotes(kite, [*tickers, NIFTY_PROXY])
    bars_today = {t: bar for t, q in quotes.items() if (bar := provisional_bar(q, today)) is not None}
    if tickers and len(bars_today) < ENTRY_MIN_QUOTE_COVERAGE * len(tickers):
        return _entry_data_unavailable(store, today, tickers, bars_today, now, clock())
    scan_path = build_scan_db(db_path, tickers, bars_today, today)
    try:
        # Rank deeper than the slots so a refused pick is replaced by the next
        # one (sizing is risk-based per pick, independent of the slot count).
        scan = await asyncio.to_thread(
            scan_today, bankroll=state["equity"], max_positions=RANK_DEPTH,
            min_strength=float(settings.PENNY_EDGE_MIN_STRENGTH), db_path=scan_path, as_of_date=today,
            nifty_ticker=NIFTY_PROXY)
    finally:
        os.remove(scan_path)

    # The scan takes minutes; price and refuse on a fresh quote of the shortlist.
    try:
        fresh = await _quotes(kite, [pick.ticker for pick in scan["positions"]])
    except Exception as exc:                          # noqa: BLE001 - a failed refresh refuses, never stale fills
        logger.warning("edge_overnight_entry_requote_failed error=%s", type(exc).__name__)
        fresh = {}
    # Decide on the clock after the scan and re-quote, not the start time.
    decided = clock()
    if decided.date().isoformat() != today or decided.time() > ENTRY_LATEST:
        fresh = {}
        late = {"reason": "past_entry_cutoff", "decided_at": decided.isoformat()}
    else:
        late = None
    slots = int(settings.PENNY_EDGE_MAX_POSITIONS)
    opened, skipped, cash = _admit(scan["positions"], fresh, state, slots=slots, today=today,
                                   decided=decided, late=late)
    shadows = _shadow_entries(scan["positions"], fresh, shadow_states, today=today, decided=decided, late=late)

    summary = {"date": today, "phase": "ENTRY", "universe": len(tickers), "quoted": len(bars_today),
               "candidates": len(scan["candidates"]), "opened": opened, "skipped": skipped,
               "equity": state["equity"], "cash_after": round(cash, 4), "fill_contract": ENTRY_FILL_CONTRACT,
               "started_at": now.isoformat(), "decided_at": decided.isoformat()}
    if shadows:
        summary["shadows"] = {name: {"opened": [{"ticker": o["ticker"], "shares": o["shares"],
                                                 "entry_price": o["entry_price"]} for o in result["opened"]],
                                     "skipped": len(result["skipped"]), "cash_after": result["cash_after"]}
                              for name, result in shadows.items()}
    with _store(store) as conn:
        if _already_ran(conn, today, "ENTRY") is not None:      # a concurrent run won
            return {**_already_ran(conn, today, "ENTRY"), "repeat": True}
        conn.executemany(
            "INSERT INTO edge_overnight_paper_trades (trade_date, ticker, kind, strength, entry_ltp, entry_price, "
            "shares, entry_ts, status, entry_bid, entry_ask) VALUES (?,?,?,?,?,?,?,?, 'OPEN',?,?)",
            [(today, o["ticker"], o["kind"], o["strength"], o["entry_ltp"], o["entry_price"], o["shares"],
              decided.isoformat(), o.get("best_bid"), o.get("best_ask")) for o in opened])
        for name, result in shadows.items():
            conn.executemany(
                "INSERT OR IGNORE INTO edge_overnight_shadow_trades (variant, trade_date, ticker, kind, entry_ltp, "
                "entry_price, shares, entry_ts, status, entry_bid, entry_ask) VALUES (?,?,?,?,?,?,?,?, 'OPEN',?,?)",
                [(name, today, o["ticker"], o["kind"], o["entry_ltp"], o["entry_price"], o["shares"],
                  decided.isoformat(), o.get("best_bid"), o.get("best_ask")) for o in result["opened"]])
        _record_run(conn, today, "ENTRY", summary, decided, format_entry_telegram(summary))
    logger.info("edge_overnight_entry date=%s quoted=%d candidates=%d opened=%d",
                today, len(bars_today), len(scan["candidates"]), len(opened))
    return summary


def _entry_data_unavailable(store: str, today: str, tickers: list, bars_today: dict,
                            started: datetime, decided: datetime) -> dict:
    """[O9-O1 2026-10-09] Missing input is not a valid zero-candidate day.

    Oct 9 stored "971 names, 0 quoted, 0 candidates" as a completed ENTRY, so
    the catch-up never retried. Below ENTRY_MIN_QUOTE_COVERAGE no receipt is
    written while a later catch-up slot still fits before ENTRY_LATEST; the
    last attempt records an explicit DATA_UNAVAILABLE receipt and notice.
    """
    summary = {"date": today, "phase": "ENTRY", "status": "DATA_UNAVAILABLE", "universe": len(tickers),
               "quoted": len(bars_today), "candidates": 0, "opened": [], "skipped": [],
               "fill_contract": ENTRY_FILL_CONTRACT, "started_at": started.isoformat(),
               "decided_at": decided.isoformat()}
    nxt = (decided.replace(second=0, microsecond=0)
           + timedelta(minutes=CATCHUP_EVERY_MINUTES - decided.minute % CATCHUP_EVERY_MINUTES))
    if decided.date().isoformat() == today and nxt.time() <= ENTRY_LATEST:
        logger.warning("edge_overnight_entry_data_unavailable date=%s quoted=%d universe=%d retry_at=%s",
                       today, len(bars_today), len(tickers), nxt.strftime("%H:%M"))
        return {**summary, "retry": True}
    with _store(store) as conn:
        if _already_ran(conn, today, "ENTRY") is not None:
            return {**_already_ran(conn, today, "ENTRY"), "repeat": True}
        state = book_state(conn, float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL))
        summary.update(equity=state["equity"], cash_after=state["cash"])
        _record_run(conn, today, "ENTRY", summary, decided,
                    f"EDGE overnight (paper) {today}: NO ENTRY - quotes unavailable "
                    f"({len(bars_today)} of {len(tickers)} names quoted). Not a no-signal day.")
    logger.error("edge_overnight_entry_data_unavailable date=%s quoted=%d universe=%d final=true",
                 today, len(bars_today), len(tickers))
    return summary


async def run_overnight_exit(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """09:17 IST: sell every earlier-session paper position at today's opening auction."""
    db_path = db_path or settings.DB_PATH
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    store = overnight_db_path(db_path)
    with _store(store) as conn:
        previous = _already_ran(conn, today, "EXIT")
        if previous is not None:
            return {**previous, "repeat": True}
        held = conn.execute(
            "SELECT trade_date, ticker, entry_price, shares, exit_attempts FROM edge_overnight_paper_trades "
            "WHERE status='OPEN' AND trade_date < ?", (today,)).fetchall()
        shadow_held = _shadow_open(conn, today)
    names = sorted({row[1] for row in held} | {row[2] for row in shadow_held})
    quotes = await _quotes(kite, names) if names else {}
    session_before = prior_session(today, db_path) if names else None

    closed, waiting = [], []
    auction = now.time() <= AUCTION_EXIT_LATEST
    for trade_date, ticker, entry_price, shares, attempts in held:
        first_session = trade_date == session_before
        item, wait = _price_exit(quotes.get(ticker), today=today, auction=auction, trade_date=trade_date,
                                 ticker=ticker, entry_price=entry_price, shares=shares,
                                 delayed=bool(attempts) or not first_session, entry_session_prior=first_session)
        if item is None:
            waiting.append(wait)
        else:
            closed.append(item)
    shadow_closed = _price_shadows(shadow_held, quotes, today=today, auction=auction,
                                   session_before=session_before, retry=False)

    with _store(store) as conn:
        if _already_ran(conn, today, "EXIT") is not None:
            return {**_already_ran(conn, today, "EXIT"), "repeat": True}
        _close_items(conn, today, closed)
        _close_shadow_items(conn, today, shadow_closed)
        for w in waiting:
            conn.execute("UPDATE edge_overnight_paper_trades SET exit_attempts = exit_attempts + 1 "
                         "WHERE trade_date=? AND ticker=? AND status='OPEN'", (w["trade_date"], w["ticker"]))
        summary = _exit_summary(conn, today, "EXIT", closed, waiting)
        message = format_exit_telegram(summary) if closed or waiting else None
        _record_run(conn, today, "EXIT", summary, now, message)
    logger.info("edge_overnight_exit date=%s closed=%d waiting=%d session_pnl=%.2f refusals=%s",
                today, len(closed), len(waiting), summary["session_pnl"],
                ",".join(f"{w['ticker']}:{w['reason']}" for w in waiting) or "-")
    return summary


async def retry_waiting_exits(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Retry today's still-waiting exits after the EXIT receipt (audit Oct 7 T1).

    Runs from ``catch_up`` every 5 minutes until ``EXIT_LATEST``. Only legs
    that closed get written; a leg that still has no trade keeps waiting and
    is carried to the next session after ``EXIT_LATEST``. A notice is queued
    per retry that closed something (phase ``EXIT_RETRY_HHMM``).
    """
    db_path = db_path or settings.DB_PATH
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    if not (EXIT_START <= now.time() < EXIT_LATEST):
        return {"closed": [], "waiting": []}
    store = overnight_db_path(db_path)
    with _store(store) as conn:
        if _already_ran(conn, today, "EXIT") is None:
            return {"closed": [], "waiting": []}
        held = conn.execute(
            "SELECT trade_date, ticker, entry_price, shares, exit_attempts FROM edge_overnight_paper_trades "
            "WHERE status='OPEN' AND trade_date < ?", (today,)).fetchall()
        shadow_held = _shadow_open(conn, today)
    if not held and not shadow_held:
        return {"closed": [], "waiting": []}
    quotes = await _quotes(kite, sorted({row[1] for row in held} | {row[2] for row in shadow_held}))
    session_before = prior_session(today, db_path)
    auction = now.time() <= AUCTION_EXIT_LATEST
    shadow_closed = _price_shadows(shadow_held, quotes, today=today, auction=auction,
                                   session_before=session_before, retry=True)
    if shadow_closed:
        with _store(store) as conn:
            _close_shadow_items(conn, today, shadow_closed)
    closed, waiting = [], []
    for trade_date, ticker, entry_price, shares, attempts in held:
        first_session = trade_date == session_before
        # exit_attempts already counts today's 09:17 refusal, so only earlier
        # sessions' refusals or a missed session make this a delayed exit.
        item, wait = _price_exit(quotes.get(ticker), today=today, auction=auction, trade_date=trade_date,
                                 ticker=ticker, entry_price=entry_price, shares=shares,
                                 delayed=not first_session, entry_session_prior=first_session, retry=True)
        if item is None:
            waiting.append(wait)
        else:
            closed.append(item)
    if not closed:
        return {"closed": [], "waiting": waiting}
    phase = f"EXIT_RETRY_{now.strftime('%H%M')}"
    with _store(store) as conn:
        if _already_ran(conn, today, phase) is not None:
            return {"closed": [], "waiting": waiting, "repeat": True}
        _close_items(conn, today, closed)
        summary = _exit_summary(conn, today, phase, closed, waiting)
        _record_run(conn, today, phase, summary, now, format_exit_telegram(summary))
    logger.info("edge_overnight_exit_retry date=%s closed=%d still_waiting=%d session_pnl=%.2f",
                today, len(closed), len(waiting), summary["session_pnl"])
    return summary


def _realism(rows: list, closed: list) -> dict:
    """[S23-S1] What the paper model may flatter, on the same trades.

    ``entry_spread_pct``: displayed (best ask - best bid) / LTP at entry; the
    ON_TIGHT_SPREAD arm measures fill over LTP instead. ``exit_at_bid``: the
    net had each close sold into the exit quote's best bid; ``model_minus_bid``
    is how much the modelled open-auction exit adds. ``entry_at_close``: the
    net had the same shares been bought at the entry day's close. Counter-
    factuals for measurement; rows recorded before S23-S1 lack the fields."""
    from penny_risk import calc_penny_costs
    spreads = [100 * (float(r[7]) - float(r[6])) / float(r[0]) for r in rows
               if r[0] and r[6] is not None and r[7] is not None]
    at_bid = [(float(r[4]), float(r[8])) for r in closed if r[8] is not None]
    at_close = []
    for r in closed:
        if r[9] is None or r[10] is None:
            continue
        close_px, exit_px, shares = float(r[9]), float(r[10]), int(r[2])
        alt = (exit_px - close_px) * shares - float(calc_penny_costs(close_px, exit_px, shares, is_intraday=False))
        at_close.append((float(r[4]), alt))
    return {
        "entry_spread_pct": round(sum(spreads) / len(spreads), 3) if spreads else None,
        "exit_at_bid": {"closes": len(at_bid), "net": round(sum(b for _n, b in at_bid), 2),
                        "model_minus_bid": round(sum(n - b for n, b in at_bid), 2)},
        "entry_at_close": {"closes": len(at_close), "net": round(sum(a for _n, a in at_close), 2),
                           "versus_actual": round(sum(a - n for n, a in at_close), 2)},
    }


def _book_stats(rows: list) -> dict:
    """rows: (entry_ltp, entry_price, shares, status, net_pnl, costs, entry_bid,
    entry_ask, exit_bid_net, entry_day_close, exit_price)."""
    closed = [r for r in rows if r[3] == "CLOSED" and r[4] is not None]
    nets = [float(r[4]) for r in closed]
    wins, losses = [n for n in nets if n > 0], [n for n in nets if n < 0]
    costs = [float(r[5] or 0) for r in closed]
    spreads = [float(r[1]) / float(r[0]) - 1 for r in rows if r[0]]
    values = [float(r[1]) * int(r[2]) for r in rows]
    return {"closed": len(closed), "open": sum(1 for r in rows if r[3] == "OPEN"),
            "net_pnl": round(sum(nets), 2), "wins": len(wins), "losses": len(losses),
            "profit_factor": round(sum(wins) / -sum(losses), 3) if losses else None,
            "avg_net_per_trade": round(sum(nets) / len(nets), 2) if nets else None,
            "charges": round(sum(costs), 2),
            "avg_entry_cost_pct": round(100 * sum(spreads) / len(spreads), 3) if spreads else None,
            "avg_position_value": round(sum(values) / len(values), 2) if values else None,
            "realism": _realism(rows, closed)}


def overnight_shadow_comparison(db_path: Optional[str] = None) -> dict:
    """[O21-ON] Each shadow against the book on the same nights (since the
    first shadow entry). Paper and research only: nothing here is a fill."""
    store = overnight_db_path(db_path or settings.DB_PATH)
    out = {"declared": OVERNIGHT_SHADOWS_DECLARED, "enabled": shadows_enabled(), "since": None,
           "book": None, "shadows": [], "research_only": True,
           "notes": ["Same picks, quotes and decision time at entry and the same exit quotes as the book; "
                     "each shadow has its own cash.",
                     "Declared before scoring; compare only on the nights since the first shadow entry.",
                     "[S23-S1] ON_TIGHT_SPREAD limits the fill premium over LTP, not the displayed bid-ask "
                     "spread; realism.entry_spread_pct is the displayed spread. realism.exit_at_bid and "
                     "entry_at_close are counterfactuals on the same trades, for measurement only."]}
    if not os.path.exists(store):
        return out
    try:
        with _read_only(store) as conn:
            since = conn.execute("SELECT MIN(trade_date) FROM edge_overnight_shadow_trades").fetchone()[0]
            if since is None:
                return out
            wanted = ("entry_ltp", "entry_price", "shares", "status", "net_pnl", "costs", "entry_bid", "entry_ask",
                      "exit_bid_net", "entry_day_close", "exit_price")

            def cols(table):
                # A store not yet migrated by S23-S1 (read-only here) lacks the new fields.
                have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                return ", ".join(c if c in have else f"NULL AS {c}" for c in wanted)

            book = conn.execute(f"SELECT {cols('edge_overnight_paper_trades')} FROM edge_overnight_paper_trades "
                                "WHERE trade_date >= ?", (since,)).fetchall()
            shadow_cols = cols("edge_overnight_shadow_trades")
            shadows = {shadow.name: conn.execute(
                f"SELECT {shadow_cols} FROM edge_overnight_shadow_trades WHERE variant=? AND trade_date >= ?",
                (shadow.name, since)).fetchall() for shadow in OVERNIGHT_SHADOWS}
    except sqlite3.OperationalError:
        return out
    out.update(since=since, book=_book_stats(book), shadows=[
        {"variant": shadow.name, "rationale": shadow.rationale,
         "config": {k: v for k, v in asdict(shadow).items() if k not in ("name", "rationale")},
         **_book_stats(shadows[shadow.name])} for shadow in OVERNIGHT_SHADOWS])
    return out


def _close_items(conn: sqlite3.Connection, today: str, closed: list[dict]) -> None:
    for c in closed:
        conn.execute(
            "UPDATE edge_overnight_paper_trades SET status='CLOSED', exit_date=?, exit_open=?, exit_price=?, "
            "costs=?, net_pnl=?, exit_reason=?, entry_day_close=?, exit_bid=?, exit_bid_net=? "
            "WHERE trade_date=? AND ticker=? AND status='OPEN'",
            (today, c["exit_open"], c["exit_price"], c["costs"], c["net_pnl"], c["reason"],
             c.get("entry_day_close"), c.get("exit_bid"), c.get("exit_bid_net"), c["trade_date"], c["ticker"]))


def _exit_summary(conn: sqlite3.Connection, today: str, phase: str, closed: list, waiting: list) -> dict:
    state = book_state(conn, float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL))
    return {"date": today, "phase": phase, "closed": closed, "waiting": waiting,
            "session_pnl": round(sum(c["net_pnl"] for c in closed), 4), "book": {
                k: state[k] for k in ("equity", "realized_pnl", "closed", "wins")}}


def format_entry_telegram(summary: dict) -> str:
    lines = [f"EDGE overnight (paper) {summary['date']}: bought {len(summary['opened'])} "
             f"of {summary['candidates']} candidates, equity Rs {summary['equity']:,.0f}"]
    for o in summary["opened"]:
        lines.append(f"  {o['ticker']} [{o['kind']}] {o['shares']} @ {o['entry_price']:.2f}")
    return "\n".join(lines)


def format_exit_telegram(summary: dict) -> str:
    book = summary["book"]
    lines = [f"EDGE overnight (paper) {summary['date']}: sold {len(summary['closed'])}, "
             f"session Rs {summary['session_pnl']:+,.2f}; book Rs {book['realized_pnl']:+,.2f} "
             f"over {book['closed']} trades, equity Rs {book['equity']:,.0f}"]
    for c in summary["closed"]:
        line = f"  {c['ticker']} @ {c['exit_price']:.2f} net Rs {c['net_pnl']:+,.2f}"
        if c["reason"] != "NEXT_OPEN":
            line += f" [{c['reason']}]"
        if "overnight_rs" in c:
            line += (f" (15:20 entry vs close Rs {c['entry_vs_close_rs']:+,.2f}, "
                     f"overnight close->open Rs {c['overnight_rs']:+,.2f}")
            if "after_open_rs" in c:
                line += f", open->sale Rs {c['after_open_rs']:+,.2f}"
            line += ")"
        lines.append(line)
    if summary["waiting"]:
        lines.append("  still held, retried until 15:20: "
                     + ", ".join(f"{w['ticker']} ({w['reason']})" for w in summary["waiting"]))
    return "\n".join(lines)
