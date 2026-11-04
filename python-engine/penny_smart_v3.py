"""[SV3 2026-11-04] Smart V3 paper book: the opening-auction reversal (paper only, no orders).

Research: docs/research/penny/2026-11-04-intraday/ (REPORT.md). Penny stocks that open
well below the previous close recover during the day, and most of the recovery is between the
pre-open auction print and the first minutes; after 09:30 no intraday window earns a spread
(the drift that sinks Smart V1/V2). The rule passed its sealed Jan-Jul 2026 check (Kite minutes,
89 names, Rs 2,000): capped +2,936 vs V1 -1,117 / V2 -802.

Rule (one slot, own Rs 2,000 book, profits withheld, losses reduce the next day's capital):
  the Penny universe (EQ series only), previous close Rs 1-55, 20-day median traded value
  >= Rs 5 lakh, opening at least 2% below the previous close; deepest gap first; skip a name whose
  usual opening volume (median of its last 20 recorded first-minute volumes, at least 5, else
  0.8% of its 20-day median daily volume) x 10% cannot take a quarter of the ticket.
  Buy at the official open (pre-open auction), at most 10% of the volume traded by about 09:16.
  Sell at the official close (post-close session) the same day, intraday charges. A stock that
  closes on its low below the open (lower-circuit lock, no buyers) is sold at the next open with
  delivery charges.

Variants, each with its own book:
  SV3_PREOPEN  decided at 09:07 on the pre-open quote (last_price as the indicative price); the
               order is a limit 1% above it, so an official open above the limit does not fill.
               This is the version that could be traded.
  SV3_REF      decided at 09:16 on the official open - what the replays assume. A reference only:
               the auction is over by then.

Jobs (scheduler_setup, trading days, ``PENNY_SMART_V3_ENABLED``):
  09:07 ``run_preopen``  quote the universe, record the pre-open evidence, decide SV3_PREOPEN
  09:16 ``run_open``     settle yesterday's positions from the quote's ohlc.close (previous
                         session close) or ohlc.open (locked), record every name's first-minute
                         volume, fill SV3_PREOPEN and decide + fill SV3_REF at ohlc.open
  15:15 ``run_bid``      snapshot each open position: LTP, best bid, day low, lower circuit -
                         the bid is a measured MIS-style exit, the low feeds the lock rule
Store: ``<DB_PATH>.penny-smart-v3.db``. Never touches the ledger, the executor or V1/V2.

Enrichment Nov4: exact NSE ETF identities also gate new Smart V3 entries;
previous positions/history still settle normally. The additive morning_evidence
read side is a separate default-off matching-volume/09:30-bid observer, not fills.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, time
import json
import logging
import math
import sqlite3
import statistics
from typing import Optional
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

SMART_V3_VERSION = "PEN_SMART_V3"
SMART_V3_DECLARED = "2026-11-04"
VARIANTS = ("SV3_PREOPEN", "SV3_REF")
SLOTS = 1
GAP_MAX = -0.02
PRICE_BAND = (1.0, 55.0)
MIN_MEDIAN_VALUE = 500_000.0
MEDIAN_SESSIONS = 20
LIMIT_ABOVE_INDICATIVE = 0.01
CAPACITY_SHARE = 0.10            # of the volume traded by ~09:16 (auction match + first minute)
THIN_SESSIONS = 20
THIN_MIN_SESSIONS = 5
FIRST_MINUTE_DAY_SHARE = 0.008   # Production Kite 09:15 candle, median share of the day (gap-down days)
MIN_FILL_FRACTION = 0.25
PREOPEN_WINDOW = (time(9, 0), time(9, 8))
OPEN_WINDOW = (time(9, 15, 30), time(9, 45))
BID_WINDOW = (time(15, 10), time(15, 29))
LOCK_TOL = 1e-4

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS sv3_trades (
        variant TEXT NOT NULL, trade_date TEXT NOT NULL, ticker TEXT NOT NULL, status TEXT NOT NULL,
        prev_close REAL NOT NULL, decided_price REAL, decided_gap REAL, limit_price REAL,
        open_price REAL, entry_price REAL, plan_shares INTEGER, shares INTEGER, capacity_volume REAL,
        thin_estimate REAL, thin_source TEXT, decided_at TEXT, entry_at TEXT,
        ltp_1515 REAL, bid_1515 REAL, low_1515 REAL, lower_circuit REAL, bid_net REAL,
        exit_date TEXT, exit_price REAL, exit_basis TEXT, costs REAL, net_pnl REAL, refusal TEXT,
        PRIMARY KEY (variant, trade_date, ticker))""",
    """CREATE TABLE IF NOT EXISTS sv3_runs (
        run_date TEXT NOT NULL, phase TEXT NOT NULL, summary TEXT NOT NULL, at TEXT NOT NULL,
        PRIMARY KEY (run_date, phase))""",
    """CREATE TABLE IF NOT EXISTS sv3_first_minute (
        trade_date TEXT NOT NULL, ticker TEXT NOT NULL, volume REAL NOT NULL, at TEXT NOT NULL,
        PRIMARY KEY (trade_date, ticker))""",
    """CREATE TABLE IF NOT EXISTS sv3_preopen (
        trade_date TEXT NOT NULL, ticker TEXT NOT NULL, prev_close REAL, last_price REAL,
        buy_quantity REAL, sell_quantity REAL, at TEXT NOT NULL, PRIMARY KEY (trade_date, ticker))""",
)


def enabled() -> bool:
    return bool(getattr(settings, "PENNY_SMART_V3_ENABLED", True))


def bankroll() -> float:
    return float(getattr(settings, "PENNY_SMART_V3_BANKROLL", 2000.0))


def store_path(db_path: str) -> str:
    return f"{db_path}.penny-smart-v3.db"


@contextmanager
def _store(path: str):
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        with conn:
            yield conn


def _read_only(path: str):
    return closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True))


def _positive(value) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


# ---- pure rule (shared with the research parity check) --------------------------------------

@dataclass(frozen=True)
class Candidate:
    ticker: str
    prev_close: float
    price: float            # indicative (pre-open) or official open
    median_value20: float
    median_vol20: float


def eq_series(ticker: str) -> bool:
    """Same-day sale needs rolling settlement: no -BE/-BZ/-SM/... suffix, not an SGB/ETF/bond."""
    from penny_universe import _is_non_equity_symbol
    from penny_instrument_identity import is_known_etf
    return "-" not in ticker and not _is_non_equity_symbol(ticker) and not is_known_etf(ticker)


def eligible(c: Candidate) -> bool:
    return (eq_series(c.ticker) and PRICE_BAND[0] <= c.prev_close <= PRICE_BAND[1]
            and c.median_value20 >= MIN_MEDIAN_VALUE and _positive(c.price)
            and c.price / c.prev_close - 1 <= GAP_MAX)


def thin_estimate(history: list[float], median_vol20: float) -> tuple[float, str]:
    """Usual opening volume: median of the last <= 20 recorded first minutes, else a daily share."""
    recent = history[-THIN_SESSIONS:]
    if len(recent) >= THIN_MIN_SESSIONS:
        return float(statistics.median(recent)), "first_minute_history"
    return FIRST_MINUTE_DAY_SHARE * float(median_vol20), "daily_share"


def select(cands: list[Candidate], *, capital: float, thin: dict, slots: int = SLOTS) -> tuple[list, dict]:
    """Deepest gap first; a name too thin for the ticket is skipped without using the slot."""
    refused: dict = {}
    picks = []
    for c in sorted((c for c in cands if eligible(c)), key=lambda c: (c.price / c.prev_close, c.ticker)):
        if len(picks) >= slots:
            break
        plan = int((capital / slots) // c.price)
        est = thin.get(c.ticker)
        if est is None or CAPACITY_SHARE * est < MIN_FILL_FRACTION * plan or plan < 1:
            refused[c.ticker] = "thin_auction"
            continue
        picks.append(c)
    return picks, refused


def fill_shares(plan: int, volume_so_far) -> int:
    """Shares the auction could give: at most 10% of the volume traded by ~09:16; 0 under a quarter."""
    cap = int(CAPACITY_SHARE * float(volume_so_far)) if _positive(volume_so_far) else 0
    shares = min(plan, cap)
    return shares if shares >= 1 and shares >= MIN_FILL_FRACTION * plan else 0


def locked(*, close: float, open_: float, low_1515: Optional[float], bid_1515: Optional[float],
           ltp_1515: Optional[float], lower_circuit: Optional[float]) -> bool:
    """Lower-circuit lock: closed on (or under) its low below the open, or no bid at the circuit."""
    if _positive(low_1515) and close <= float(low_1515) * (1 + LOCK_TOL) and close < open_ * (1 - LOCK_TOL):
        return True
    return (not _positive(bid_1515) and _positive(ltp_1515) and _positive(lower_circuit)
            and float(ltp_1515) <= float(lower_circuit) * (1 + LOCK_TOL))


def charges(entry: float, exit_: float, shares: int, *, intraday: bool) -> float:
    from penny_risk import calc_penny_costs
    return float(calc_penny_costs(entry, exit_, shares, is_intraday=intraday))


# ---- state ----------------------------------------------------------------------------------

def capital(conn: sqlite3.Connection, variant: str) -> float:
    """Fixed book: profits withheld, losses reduce the next day's capital."""
    realized = conn.execute("SELECT COALESCE(SUM(net_pnl), 0) FROM sv3_trades WHERE variant=? AND status='CLOSED'",
                            (variant,)).fetchone()[0]
    return min(bankroll(), bankroll() + float(realized))


def busy(conn: sqlite3.Connection, variant: str, today: str) -> bool:
    """A position still open from an earlier session (locked, or no quote yet) holds the book's cash."""
    return conn.execute("SELECT 1 FROM sv3_trades WHERE variant=? AND status='OPEN' AND trade_date < ?",
                        (variant, today)).fetchone() is not None


def _already_ran(conn, day: str, phase: str) -> Optional[dict]:
    row = conn.execute("SELECT summary FROM sv3_runs WHERE run_date=? AND phase=?", (day, phase)).fetchone()
    return json.loads(row[0]) if row else None


def _record_run(conn, day: str, phase: str, summary: dict, now: datetime) -> None:
    conn.execute("INSERT OR REPLACE INTO sv3_runs VALUES (?,?,?,?)",
                 (day, phase, json.dumps(summary, sort_keys=True, default=str), now.isoformat()))


def universe(kite) -> list[str]:
    from penny_universe import PennyUniverse
    rows = PennyUniverse(json_path=settings.PENNY_UNIVERSE_JSON_PATH,
                         instrument_cache=getattr(kite, "instrument_cache", None)).eligible_tickers()
    return sorted({r["symbol"] for r in rows if r.get("symbol") and eq_series(r["symbol"])})


def daily_medians(db_path: str, tickers: list[str], today: str) -> dict:
    """ticker -> (median traded value, median volume) of the last 20 cached sessions before today."""
    out = {}
    with _read_only(db_path) as conn:
        for t in tickers:
            rows = conn.execute("SELECT close, volume FROM ohlcv_cache WHERE ticker=? AND date < ? "
                                "ORDER BY date DESC LIMIT ?", (t, today, MEDIAN_SESSIONS)).fetchall()
            rows = [(float(c), float(v)) for c, v in rows if _positive(c) and v is not None and float(v) >= 0]
            if len(rows) == MEDIAN_SESSIONS:
                out[t] = (statistics.median(c * v for c, v in rows), statistics.median(v for _, v in rows))
    return out


def thin_estimates(conn, tickers: list[str], today: str, medians: dict) -> tuple[dict, dict]:
    est, source = {}, {}
    for t in tickers:
        hist = [float(r[0]) for r in conn.execute(
            "SELECT volume FROM sv3_first_minute WHERE ticker=? AND trade_date < ? ORDER BY trade_date DESC LIMIT ?",
            (t, today, THIN_SESSIONS)).fetchall()][::-1]
        if t in medians:
            est[t], source[t] = thin_estimate(hist, medians[t][1])
    return est, source


def _candidates(quotes: dict, medians: dict, price_key: str) -> list[Candidate]:
    out = []
    for t, q in quotes.items():
        ohlc = q.get("ohlc") or {}
        prev, price = ohlc.get("close"), (q.get("last_price") if price_key == "last_price" else ohlc.get("open"))
        if t in medians and _positive(prev) and _positive(price):
            out.append(Candidate(t, float(prev), float(price), medians[t][0], medians[t][1]))
    return out


def _within(now: datetime, window: tuple) -> bool:
    return window[0] <= now.timetz().replace(tzinfo=None) <= window[1]


async def _quotes(kite, tickers):
    from edge_overnight_paper import _quotes as quotes
    return await quotes(kite, tickers)


def _best_bid(quote):
    from edge_overnight_paper import _best_bid as best
    return best(quote)


# ---- jobs -----------------------------------------------------------------------------------

async def run_preopen(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """09:07: record the pre-open evidence and decide SV3_PREOPEN on the indicative price."""
    db_path = db_path or settings.DB_PATH
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    with _store(store_path(db_path)) as conn:
        if (done := _already_ran(conn, today, "PREOPEN")) is not None:
            return {**done, "repeat": True}
        if not _within(now, PREOPEN_WINDOW):
            summary = {"status": "OUTSIDE_WINDOW", "at": now.isoformat()}
            _record_run(conn, today, "PREOPEN", summary, now)
            return summary
        held = conn.execute("SELECT variant, trade_date, ticker, entry_price, shares, open_price, ltp_1515, "
                            "bid_1515, low_1515, lower_circuit FROM sv3_trades WHERE status='OPEN' AND trade_date < ?",
                            (today,)).fetchall()
    from edge_overnight_paper import prior_session
    names = universe(kite)
    quotes = await _quotes(kite, sorted({*names, *(r[2] for r in held)})) if (names or held) else {}
    medians = daily_medians(db_path, names, today)
    with _store(store_path(db_path)) as conn:
        settled = _settle(conn, held, quotes, today, prior_session(today, db_path), allow_locked=False)
        cap = capital(conn, "SV3_PREOPEN")
        quotes_u = {t: q for t, q in quotes.items() if t in names}
        conn.executemany("INSERT OR REPLACE INTO sv3_preopen VALUES (?,?,?,?,?,?,?)", [
            (today, t, (q.get("ohlc") or {}).get("close"), q.get("last_price"), q.get("buy_quantity"),
             q.get("sell_quantity"), now.isoformat()) for t, q in quotes_u.items()])
        thin, source = thin_estimates(conn, names, today, medians)
        cands = _candidates(quotes_u, medians, "last_price")
        picks, refused = select(cands, capital=cap, thin=thin)
        held_over = busy(conn, "SV3_PREOPEN", today)
        if held_over:
            picks = []
        for c in picks:
            conn.execute("INSERT OR REPLACE INTO sv3_trades (variant, trade_date, ticker, status, prev_close, "
                         "decided_price, decided_gap, limit_price, thin_estimate, thin_source, decided_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         ("SV3_PREOPEN", today, c.ticker, "DECIDED", c.prev_close, c.price,
                          round(c.price / c.prev_close - 1, 6), round(c.price * (1 + LIMIT_ABOVE_INDICATIVE), 4),
                          thin.get(c.ticker), source.get(c.ticker), now.isoformat()))
        moved = sum(1 for q in quotes_u.values() if _positive(q.get("last_price"))
                    and q.get("last_price") != (q.get("ohlc") or {}).get("close"))
        summary = {"status": "DONE", "universe": len(names), "quoted": len(quotes_u), "indicative_moved": moved,
                   "settled": settled,
                   "eligible": sum(eligible(c) for c in cands), "picks": [c.ticker for c in picks],
                   "thin_refused": len(refused), "capital": round(cap, 2), "cash_in_use": held_over}
        _record_run(conn, today, "PREOPEN", summary, now)
    logger.info("penny_smart_v3_preopen %s", summary)
    return summary


def _settle(conn, rows: list, quotes: dict, today: str, prior: str, *, allow_locked: bool = True) -> list:
    """Close positions from the prior session at its official close (the quote's ohlc.close), or a
    locked one at today's open. ``allow_locked=False`` (09:07: no official open yet) leaves locked
    positions for the 09:16 run."""
    closed = []
    for (variant, trade_date, ticker, entry, shares, open_price, ltp, bid, low, lc) in rows:
        q = quotes.get(ticker) or {}
        ohlc = q.get("ohlc") or {}
        close_prev, open_today = ohlc.get("close"), ohlc.get("open")
        if trade_date != prior or not _positive(close_prev):
            continue   # the quote's close is the entry day's close only when that day is the prior session
        is_locked = locked(close=float(close_prev), open_=float(open_price), low_1515=low, bid_1515=bid,
                           ltp_1515=ltp, lower_circuit=lc)
        if is_locked:
            if not allow_locked or not _positive(open_today):
                continue   # no trade yet today: retried next run
            exit_price, basis, intraday = float(open_today), "next_open_locked", False
        else:
            exit_price, basis, intraday = float(close_prev), "official_close", True
        fees = charges(entry, exit_price, shares, intraday=intraday)
        net = round((exit_price - entry) * shares - fees, 4)
        conn.execute("UPDATE sv3_trades SET status='CLOSED', exit_date=?, exit_price=?, exit_basis=?, costs=?, "
                     "net_pnl=? WHERE variant=? AND trade_date=? AND ticker=?",
                     (today, exit_price, basis, round(fees, 4), net, variant, trade_date, ticker))
        closed.append({"variant": variant, "ticker": ticker, "net": net, "basis": basis})
    return closed


def _enter(conn, variant: str, c, q: dict, today: str, now: datetime, cap: float, *, limit: Optional[float]) -> dict:
    ohlc = q.get("ohlc") or {}
    open_price = ohlc.get("open")
    plan = int((cap / SLOTS) // float(open_price)) if _positive(open_price) else 0
    refusal, shares = None, 0
    if not _positive(open_price):
        refusal = "no_open_price"
    elif limit is not None and float(open_price) > limit:
        refusal = "open_above_limit"
    else:
        shares = fill_shares(plan, q.get("volume") or q.get("volume_traded"))
        if shares < 1:
            refusal = "auction_capacity"
    status = "OPEN" if refusal is None else "REFUSED"
    conn.execute("UPDATE sv3_trades SET status=?, open_price=?, entry_price=?, plan_shares=?, shares=?, "
                 "capacity_volume=?, entry_at=?, refusal=? WHERE variant=? AND trade_date=? AND ticker=?",
                 (status, open_price, open_price if refusal is None else None, plan, shares,
                  q.get("volume") or q.get("volume_traded"), now.isoformat(), refusal, variant, today, c))
    return {"variant": variant, "ticker": c, "status": status, "refusal": refusal, "shares": shares}


async def run_open(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """09:16: settle, record first-minute volumes, fill SV3_PREOPEN, decide and fill SV3_REF."""
    from edge_overnight_paper import prior_session
    db_path = db_path or settings.DB_PATH
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    with _store(store_path(db_path)) as conn:
        if (done := _already_ran(conn, today, "OPEN")) is not None:
            return {**done, "repeat": True}
        if not _within(now, OPEN_WINDOW):
            summary = {"status": "OUTSIDE_WINDOW", "at": now.isoformat()}
            _record_run(conn, today, "OPEN", summary, now)
            return summary
        held = conn.execute("SELECT variant, trade_date, ticker, entry_price, shares, open_price, ltp_1515, "
                            "bid_1515, low_1515, lower_circuit FROM sv3_trades WHERE status='OPEN' AND trade_date < ?",
                            (today,)).fetchall()
        decided = [r[0] for r in conn.execute("SELECT ticker FROM sv3_trades WHERE variant='SV3_PREOPEN' AND "
                                              "trade_date=? AND status='DECIDED'", (today,)).fetchall()]
    names = universe(kite)
    quotes = await _quotes(kite, sorted({*names, *(r[2] for r in held), *decided}))
    medians = daily_medians(db_path, names, today)
    prior = prior_session(today, db_path)
    with _store(store_path(db_path)) as conn:
        closed = _settle(conn, held, quotes, today, prior)
        conn.executemany("INSERT OR REPLACE INTO sv3_first_minute VALUES (?,?,?,?)", [
            (today, t, float(q.get("volume") or q.get("volume_traded") or 0.0), now.isoformat())
            for t, q in quotes.items() if t in names])
        entries = [_enter(conn, "SV3_PREOPEN", t, quotes.get(t) or {}, today, now, capital(conn, "SV3_PREOPEN"),
                          limit=conn.execute("SELECT limit_price FROM sv3_trades WHERE variant='SV3_PREOPEN' AND "
                                             "trade_date=? AND ticker=?", (today, t)).fetchone()[0])
                   for t in decided]
        thin, source = thin_estimates(conn, names, today, medians)
        cap_ref = capital(conn, "SV3_REF")
        picks, refused = select(_candidates({t: quotes[t] for t in names if t in quotes}, medians, "open"),
                                capital=cap_ref, thin=thin)
        ref_busy = busy(conn, "SV3_REF", today)
        for c in ([] if ref_busy else picks):
            conn.execute("INSERT OR REPLACE INTO sv3_trades (variant, trade_date, ticker, status, prev_close, "
                         "decided_price, decided_gap, thin_estimate, thin_source, decided_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         ("SV3_REF", today, c.ticker, "DECIDED", c.prev_close, c.price,
                          round(c.price / c.prev_close - 1, 6), thin.get(c.ticker), source.get(c.ticker), now.isoformat()))
            entries.append(_enter(conn, "SV3_REF", c.ticker, quotes[c.ticker], today, now, cap_ref, limit=None))
        summary = {"status": "DONE", "settled": closed, "entries": entries, "quoted": len(quotes),
                   "first_minutes": sum(1 for t in quotes if t in names), "ref_thin_refused": len(refused),
                   "ref_cash_in_use": ref_busy,
                   "waiting": len(held) - len(closed)}
        _record_run(conn, today, "OPEN", summary, now)
    logger.info("penny_smart_v3_open %s", summary)
    return summary


async def run_bid(kite, db_path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """15:15: LTP, best bid, day low and lower circuit of each open position (measurement)."""
    db_path = db_path or settings.DB_PATH
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    with _store(store_path(db_path)) as conn:
        if (done := _already_ran(conn, today, "BID")) is not None:
            return {**done, "repeat": True}
        rows = conn.execute("SELECT variant, ticker, entry_price, shares FROM sv3_trades WHERE status='OPEN' "
                            "AND trade_date=?", (today,)).fetchall()
    quotes = await _quotes(kite, sorted({r[1] for r in rows})) if rows else {}
    with _store(store_path(db_path)) as conn:
        for variant, ticker, entry, shares in rows:
            q = quotes.get(ticker) or {}
            bid = _best_bid(q) if q else None
            bid_net = (round((bid - entry) * shares - charges(entry, bid, shares, intraday=True), 4)
                       if _positive(bid) else None)
            conn.execute("UPDATE sv3_trades SET ltp_1515=?, bid_1515=?, low_1515=?, lower_circuit=?, bid_net=? "
                         "WHERE variant=? AND trade_date=? AND ticker=?",
                         (q.get("last_price"), bid, (q.get("ohlc") or {}).get("low"), q.get("lower_circuit_limit"),
                          bid_net, variant, today, ticker))
        summary = {"status": "DONE", "positions": len(rows), "quoted": len(quotes)}
        _record_run(conn, today, "BID", summary, now)
    return summary


# ---- read side ------------------------------------------------------------------------------

def comparison(db_path: Optional[str] = None) -> dict:
    """Both variants' paper records (read-only). Nothing here is a fill."""
    path = store_path(db_path or settings.DB_PATH)
    out = {"version": SMART_V3_VERSION, "declared": SMART_V3_DECLARED, "enabled": enabled(),
           "bankroll": bankroll(), "variants": {}, "preopen": None, "research_only": True,
           "notes": ["Paper only: the entry is the official open and the exit the official close; whether an "
                     "auction order would fill is not observed. SV3_REF decides after the auction (reference).",
                     "bid_net is the same trade sold at the 15:15 best bid (a measured MIS-style exit).",
                     "Compare with Smart V1/V2 (GET /experiments/penny-smart) on the same sessions."]}
    import os
    from penny_smart_morning_evidence import summary as morning_summary
    from penny_instrument_identity import NSE_ETF_AS_OF, NSE_ETF_SHA256
    out['morning_evidence'] = morning_summary(db_path or settings.DB_PATH)
    out['equity_identity'] = {'etf_registry_as_of': NSE_ETF_AS_OF, 'etf_registry_sha256': NSE_ETF_SHA256,
                              'scope': 'Smart V3 only; existing history and shared EDGE universe unchanged'}
    if not os.path.exists(path):
        return out
    try:
        with _read_only(path) as conn:
            for v in VARIANTS:
                rows = conn.execute("SELECT status, net_pnl, bid_net, exit_basis, refusal FROM sv3_trades "
                                    "WHERE variant=?", (v,)).fetchall()
                closed = [r for r in rows if r[0] == "CLOSED"]
                nets = [float(r[1]) for r in closed]
                gains, losses = sum(x for x in nets if x > 0), -sum(x for x in nets if x < 0)
                refusals: dict = {}
                for r in rows:
                    if r[0] == "REFUSED":
                        refusals[r[4]] = refusals.get(r[4], 0) + 1
                bids = [float(r[2]) for r in closed if r[2] is not None]
                out["variants"][v] = {
                    "since": conn.execute("SELECT MIN(trade_date) FROM sv3_trades WHERE variant=?", (v,)).fetchone()[0],
                    "closed": len(closed), "open": sum(r[0] == "OPEN" for r in rows), "net_pnl": round(sum(nets), 2),
                    "wins": sum(x > 0 for x in nets), "profit_factor": round(gains / losses, 3) if losses else None,
                    "avg_net": round(sum(nets) / len(nets), 2) if nets else None,
                    "locked_exits": sum(r[3] == "next_open_locked" for r in closed),
                    "at_1515_bid": {"closes": len(bids), "net": round(sum(bids), 2)},
                    "refusals": refusals}
            pre = conn.execute("SELECT COUNT(DISTINCT trade_date), COUNT(*), SUM(last_price IS NOT NULL AND "
                               "last_price != prev_close) FROM sv3_preopen").fetchone()
            out["preopen"] = {"sessions": pre[0], "quotes": pre[1], "indicative_moved": pre[2] or 0}
    except sqlite3.OperationalError:
        return out
    return out
