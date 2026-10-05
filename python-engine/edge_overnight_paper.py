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
from datetime import datetime, time
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
ENTRY_CATCHUP_START = time(15, 21)  # after the 15:20 job's own run
ENTRY_LATEST = time(15, 29)

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
)


def overnight_db_path(db_path: str) -> str:
    return f"{db_path}.edge-overnight-paper.db"


@contextmanager
def _store(path: str):
    """One transaction on the paper store; the handle is always closed."""
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        with conn:
            yield conn


def _read_only(path: str):
    return closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True))


def _finite_positive(value) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def book_state(conn: sqlite3.Connection, bankroll: float) -> dict:
    realized = conn.execute(
        "SELECT COALESCE(SUM(net_pnl), 0), COUNT(*), COALESCE(SUM(net_pnl > 0), 0) "
        "FROM edge_overnight_paper_trades WHERE status='CLOSED'").fetchone()
    held = conn.execute(
        "SELECT ticker, entry_price * shares FROM edge_overnight_paper_trades WHERE status='OPEN'").fetchall()
    equity = bankroll + float(realized[0])
    return {"equity": round(equity, 4), "realized_pnl": round(float(realized[0]), 4), "closed": int(realized[1]),
            "wins": int(realized[2]), "held": {ticker: value for ticker, value in held},
            "cash": round(equity - sum(value for _, value in held), 4)}


def _already_ran(conn: sqlite3.Connection, day: str, phase: str) -> Optional[dict]:
    row = conn.execute("SELECT summary FROM edge_overnight_paper_runs WHERE run_date=? AND phase=?",
                       (day, phase)).fetchone()
    return json.loads(row[0]) if row else None


def _record_run(conn: sqlite3.Connection, day: str, phase: str, summary: dict, now: datetime,
                message: Optional[str] = None) -> None:
    conn.execute("INSERT OR REPLACE INTO edge_overnight_paper_runs VALUES (?,?,?,?)",
                 (day, phase, json.dumps(summary, sort_keys=True), now.isoformat()))
    if message:
        conn.execute("INSERT OR IGNORE INTO edge_overnight_paper_notices (run_date, phase, message, created_at) "
                     "VALUES (?,?,?,?)", (day, phase, message, now.isoformat()))


async def flush_notices(send: Callable[[str], Awaitable[None]], db_path: Optional[str] = None,
                        now: Optional[datetime] = None) -> int:
    """Send unsent phase summaries oldest first; ``send`` raises on failure."""
    store = overnight_db_path(db_path or settings.DB_PATH)
    now = now or datetime.now(IST)
    with _store(store) as conn:
        pending = conn.execute("SELECT run_date, phase, message FROM edge_overnight_paper_notices "
                               "WHERE sent_at IS NULL ORDER BY created_at").fetchall()
    sent = 0
    for day, phase, message in pending:
        try:
            await send(message)
        except Exception as exc:
            logger.warning("edge_overnight_notice_failed date=%s phase=%s err=%s", day, phase, type(exc).__name__)
            with _store(store) as conn:
                conn.execute("UPDATE edge_overnight_paper_notices SET attempts = attempts + 1 "
                             "WHERE run_date=? AND phase=?", (day, phase))
            break
        with _store(store) as conn:
            conn.execute("UPDATE edge_overnight_paper_notices SET sent_at=?, attempts = attempts + 1 "
                         "WHERE run_date=? AND phase=?", (now.isoformat(), day, phase))
        sent += 1
    return sent


async def catch_up(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> list[str]:
    """Run a phase whose receipt is missing today, inside its permitted window."""
    db_path = db_path or settings.DB_PATH
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
    if not has_entry and ENTRY_CATCHUP_START <= clock <= ENTRY_LATEST:
        summary = await run_overnight_entry(kite, db_path, now)
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


async def _quotes(kite, tickers: list[str]) -> dict:
    tokens = {}
    for ticker in tickers:
        token = kite.instrument_cache.get(ticker)
        if token is not None:
            tokens[int(token)] = ticker
    if not tokens:
        return {}
    raw = await kite.get_quote(list(tokens))
    return {tokens[int(token)]: quote for token, quote in (raw or {}).items() if int(token) in tokens}


async def run_overnight_entry(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """15:20 IST: score today's provisional bars and open the paper picks."""
    from penny_edge_live import scan_today

    db_path = db_path or settings.DB_PATH
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    store = overnight_db_path(db_path)
    with _store(store) as conn:
        previous = _already_ran(conn, today, "ENTRY")
        if previous is not None:
            return {**previous, "repeat": True}
        state = book_state(conn, float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL))

    tickers = universe_from_cache(db_path)
    quotes = await _quotes(kite, [*tickers, NIFTY_PROXY])
    bars_today = {t: bar for t, q in quotes.items() if (bar := provisional_bar(q, today)) is not None}
    scan_path = build_scan_db(db_path, tickers, bars_today, today)
    try:
        scan = await asyncio.to_thread(
            scan_today, bankroll=state["equity"], max_positions=int(settings.PENNY_EDGE_MAX_POSITIONS),
            min_strength=float(settings.PENNY_EDGE_MIN_STRENGTH), db_path=scan_path, as_of_date=today,
            nifty_ticker=NIFTY_PROXY)
    finally:
        os.remove(scan_path)

    cash, opened, skipped = state["cash"], [], []
    for pick in scan["positions"]:
        bar = bars_today.get(pick.ticker)
        if bar is None:
            skipped.append({"ticker": pick.ticker, "reason": "no_provisional_bar"})
            continue
        if pick.ticker in state["held"]:
            skipped.append({"ticker": pick.ticker, "reason": "already_held"})
            continue
        ltp, volume = bar[3], bar[4]
        entry_price = round(ltp * (1 + ENTRY_SLIPPAGE_BPS / 10000.0), 4)
        capacity = int(MAX_PARTICIPATION * ltp * volume // entry_price)
        affordable = int(cash // (entry_price * (1 + BUY_COST_BUFFER)))
        shares = min(int(pick.shares), capacity, affordable)
        if shares < 1 or shares < MIN_FILL_FRACTION * int(pick.shares):
            reason = "liquidity" if capacity <= affordable else "cash"
            skipped.append({"ticker": pick.ticker, "reason": f"{reason}_below_quarter_of_plan",
                            "planned": int(pick.shares), "capacity": capacity, "affordable": affordable})
            continue
        cash -= entry_price * shares
        opened.append({"ticker": pick.ticker, "kind": pick.signal_subtype,
                       "strength": round(float(pick.adjusted_strength), 4), "entry_ltp": ltp,
                       "entry_price": entry_price, "shares": shares})

    summary = {"date": today, "phase": "ENTRY", "universe": len(tickers), "quoted": len(bars_today),
               "candidates": len(scan["candidates"]), "opened": opened, "skipped": skipped,
               "equity": state["equity"]}
    with _store(store) as conn:
        if _already_ran(conn, today, "ENTRY") is not None:      # a concurrent run won
            return {**_already_ran(conn, today, "ENTRY"), "repeat": True}
        conn.executemany(
            "INSERT INTO edge_overnight_paper_trades (trade_date, ticker, kind, strength, entry_ltp, entry_price, "
            "shares, entry_ts, status) VALUES (?,?,?,?,?,?,?,?, 'OPEN')",
            [(today, o["ticker"], o["kind"], o["strength"], o["entry_ltp"], o["entry_price"], o["shares"],
              now.isoformat()) for o in opened])
        _record_run(conn, today, "ENTRY", summary, now, format_entry_telegram(summary))
    logger.info("edge_overnight_entry date=%s quoted=%d candidates=%d opened=%d",
                today, len(bars_today), len(scan["candidates"]), len(opened))
    return summary


async def run_overnight_exit(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """09:17 IST: sell every earlier-session paper position at today's opening auction."""
    from penny_risk import calc_penny_costs

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
    quotes = await _quotes(kite, sorted({row[1] for row in held})) if held else {}

    closed, waiting = [], []
    auction = now.time() <= AUCTION_EXIT_LATEST
    for trade_date, ticker, entry_price, shares, attempts in held:
        quote = quotes.get(ticker) or {}
        open_price = (quote.get("ohlc") or {}).get("open")
        basis = open_price if auction else quote.get("last_price")
        stamp = str(quote.get("last_trade_time") or quote.get("timestamp") or "")
        if not _finite_positive(open_price) or not _finite_positive(basis) or not stamp.startswith(today):
            waiting.append({"ticker": ticker, "trade_date": trade_date, "reason": "no_trade_today"})
            continue
        exit_price = round(float(basis) * (1 - EXIT_SLIPPAGE_BPS / 10000.0), 4)
        costs = float(calc_penny_costs(entry_price, exit_price, shares, is_intraday=False))
        net = round((exit_price - entry_price) * shares - costs, 4)
        closed.append({"trade_date": trade_date, "ticker": ticker, "exit_open": float(open_price),
                       "exit_price": exit_price, "costs": round(costs, 4), "net_pnl": net,
                       "reason": "CATCHUP_LTP" if not auction else "OPEN_DELAYED" if attempts else "NEXT_OPEN"})

    with _store(store) as conn:
        if _already_ran(conn, today, "EXIT") is not None:
            return {**_already_ran(conn, today, "EXIT"), "repeat": True}
        for c in closed:
            conn.execute(
                "UPDATE edge_overnight_paper_trades SET status='CLOSED', exit_date=?, exit_open=?, exit_price=?, "
                "costs=?, net_pnl=?, exit_reason=? WHERE trade_date=? AND ticker=? AND status='OPEN'",
                (today, c["exit_open"], c["exit_price"], c["costs"], c["net_pnl"], c["reason"],
                 c["trade_date"], c["ticker"]))
        for w in waiting:
            conn.execute("UPDATE edge_overnight_paper_trades SET exit_attempts = exit_attempts + 1 "
                         "WHERE trade_date=? AND ticker=? AND status='OPEN'", (w["trade_date"], w["ticker"]))
        state = book_state(conn, float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL))
        summary = {"date": today, "phase": "EXIT", "closed": closed, "waiting": waiting,
                   "session_pnl": round(sum(c["net_pnl"] for c in closed), 4), "book": {
                       k: state[k] for k in ("equity", "realized_pnl", "closed", "wins")}}
        message = format_exit_telegram(summary) if closed or waiting else None
        _record_run(conn, today, "EXIT", summary, now, message)
    logger.info("edge_overnight_exit date=%s closed=%d waiting=%d session_pnl=%.2f",
                today, len(closed), len(waiting), summary["session_pnl"])
    return summary


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
        lines.append(f"  {c['ticker']} @ {c['exit_price']:.2f} net Rs {c['net_pnl']:+,.2f}")
    if summary["waiting"]:
        lines.append(f"  still held (no trade yet): {', '.join(w['ticker'] for w in summary['waiting'])}")
    return "\n".join(lines)
