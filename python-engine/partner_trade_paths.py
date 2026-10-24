"""[O21-PX 2026-10-21] What each option the partner traded did that day.

The partner's free Kite app has no market data, so after a read of a
finished day (partner_broker_sync.sync_book) this module stores the session's
1-minute candles of every option the partner bought or sold, from the
owner's market data (KiteClient.get_intraday_by_token, interval "minute").
When a contract is not in the morning instrument books or the candle read
fails, the 5-minute prints the analytics tick stored for that strike
(fno_chain_oi) are kept instead, marked as such. A later read retries a
contract that only has prints.

partner_insights.py reads these paths to show the best and worst price while
the partner held, the run before a buy, what the option did after a sale,
and a small chart. Read-only market data; nothing here places an order.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional

import aiosqlite
import pytz
import structlog

from market_calendar import DERIVATIVES_CLOSE_TIME

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

BASIS_CANDLES = "1MIN_CANDLES"
BASIS_PRINTS = "5MIN_PRINTS"
CLOSE_MIN = DERIVATIVES_CLOSE_TIME.hour * 60 + DERIVATIVES_CLOSE_TIME.minute   # [O24-MC] F&O trades until 15:40
MAX_CONTRACTS = 12             # options per day (a busy day still stays quick at login)
FETCH_TIMEOUT_SEC = 8.0        # one contract's candle read
BUDGET_SEC = 20.0              # the whole day's reads; the gateway waits for the login

_DDL = """
CREATE TABLE IF NOT EXISTS partner_trade_paths (
  session_date TEXT NOT NULL,
  exchange TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  basis TEXT NOT NULL,
  bars_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (session_date, exchange, tradingsymbol)
)
"""

# fetch(token, from "YYYY-MM-DD HH:MM:SS", to) -> [(ts "YYYY-MM-DD HH:MM:SS", open, high, low, close)]
Fetch = Callable[[int, str, str], Awaitable[list]]


async def init_partner_paths_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.commit()


def _day_over(day: str, now: datetime) -> bool:
    close = IST.localize(datetime.fromisoformat(day) + timedelta(minutes=CLOSE_MIN))
    return now.astimezone(IST) >= close


async def traded_contracts(db_path: str, day: str) -> list:
    """Distinct options with an active BUY or SELL report on ``day``."""
    async with aiosqlite.connect(db_path) as db:
        try:
            rows = await (await db.execute(
                "SELECT exchange, tradingsymbol, underlying, expiry, strike, opt_type, MIN(trade_at) "
                "FROM partner_trade_reports WHERE session_date=? AND status='ACTIVE' AND action IN ('BUY','SELL') "
                "AND tradingsymbol IS NOT NULL GROUP BY exchange, tradingsymbol ORDER BY MIN(trade_at)",
                (day,))).fetchall()
        except aiosqlite.OperationalError:
            return []
    return [{"exchange": str(e or "NFO").upper(), "tradingsymbol": str(s).upper(), "underlying": u, "expiry": x,
             "strike": k, "opt_type": t} for e, s, u, x, k, t, _ in rows]


def contract_token(exchange: str, symbol: str) -> Optional[int]:
    """The instrument token from the morning books (None when not there)."""
    try:
        from fno_underlyings import SPECS, get_instruments_for
        for name, spec in SPECS.items():
            if spec.segment != exchange:
                continue
            contract = get_instruments_for(name).by_symbol.get(symbol)
            if contract is not None:
                return int(contract.token)
    except Exception as exc:   # an unloaded book only means no candles
        logger.warning("partner_paths_book_lookup_failed err=%s", type(exc).__name__)
    return None


async def kite_minutes(token: int, start: str, end: str) -> list:
    """The owner's 1-minute candles for one contract."""
    import main as _main
    frame = await _main.kite.get_intraday_by_token(token, start, end, interval="minute")
    if frame is None or frame.empty:
        return []
    return [(ts.strftime("%Y-%m-%d %H:%M:%S"), float(row["open"]), float(row["high"]), float(row["low"]),
             float(row["close"])) for ts, row in frame.iterrows()]


async def stored_prints(db_path: str, day: str, contract: dict) -> list:
    """The analytics tick's 5-minute prints for the strike, as flat bars."""
    if not (contract.get("underlying") and contract.get("expiry") and contract.get("strike")
            and contract.get("opt_type")):
        return []
    import fno_oi_store
    try:
        rows = await fno_oi_store.strike_ltp_series(db_path, contract["underlying"], day, str(contract["expiry"]),
                                                    float(contract["strike"]), str(contract["opt_type"]))
    except (aiosqlite.Error, ValueError, TypeError):
        return []
    return [(str(ts)[:19], px, px, px, px) for ts, px in rows]


async def _stored(db_path: str, day: str) -> dict:
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT exchange, tradingsymbol, basis FROM partner_trade_paths WHERE session_date=?", (day,))).fetchall()
    return {(e, s): b for e, s, b in rows}


async def _save(db_path: str, day: str, contract: dict, basis: str, bars: list, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO partner_trade_paths(session_date,exchange,tradingsymbol,basis,bars_json,fetched_at) "
            "VALUES(?,?,?,?,?,?)",
            (day, contract["exchange"], contract["tradingsymbol"], basis,
             json.dumps([[str(b[0])[:19], *(round(float(v), 2) for v in b[1:5])] for b in bars]), now.isoformat()))
        await db.commit()


async def ensure_paths(db_path: str, day: str, now: Optional[datetime] = None, *, fetch: Optional[Fetch] = None,
                       token_of: Optional[Callable[[str, str], Optional[int]]] = None,
                       budget_sec: float = BUDGET_SEC) -> dict:
    """Store the day's traded options' prices once the session is over.

    A contract already stored from candles is not read again; one stored
    from prints is retried. Returns counts by basis."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not _day_over(day, now):
        return {"status": "day_not_over"}
    await init_partner_paths_db(db_path)
    contracts = await traded_contracts(db_path, day)
    stored = await _stored(db_path, day)
    todo = [c for c in contracts if stored.get((c["exchange"], c["tradingsymbol"])) != BASIS_CANDLES][:MAX_CONTRACTS]
    fetch = fetch or kite_minutes
    token_of = token_of or contract_token
    out = {"status": "ok", "contracts": len(contracts), BASIS_CANDLES: 0, BASIS_PRINTS: 0, "missing": 0}

    async def one(contract: dict) -> None:
        bars, basis = [], BASIS_CANDLES
        token = token_of(contract["exchange"], contract["tradingsymbol"])
        if token:
            try:
                bars = await asyncio.wait_for(fetch(token, f"{day} 09:15:00", f"{day} {CLOSE_MIN // 60:02d}:{CLOSE_MIN % 60:02d}:00"),
                                              timeout=FETCH_TIMEOUT_SEC)
            except Exception as exc:   # timeout or provider error: fall back to prints
                logger.warning("partner_paths_candles_failed symbol=%s err=%s", contract["tradingsymbol"],
                               type(exc).__name__)
                bars = []
        if not bars:
            bars, basis = await stored_prints(db_path, day, contract), BASIS_PRINTS
        if not bars:
            out["missing"] += 1
            return
        if basis == BASIS_PRINTS and stored.get((contract["exchange"], contract["tradingsymbol"])) == BASIS_PRINTS:
            out[BASIS_PRINTS] += 1
            return
        await _save(db_path, day, contract, basis, bars, now)
        out[basis] += 1

    async def all_contracts() -> None:
        for contract in todo:
            await one(contract)

    try:
        await asyncio.wait_for(all_contracts(), timeout=budget_sec)
    except asyncio.TimeoutError:
        out["status"] = "budget_spent"
        logger.warning("partner_paths_budget_spent day=%s", day)
    logger.info("partner_paths_stored day=%s candles=%d prints=%d missing=%d", day, out[BASIS_CANDLES],
                out[BASIS_PRINTS], out["missing"])
    return out


async def load_paths(db_path: str, first_day: str, last_day: str) -> dict:
    """{(day, exchange, symbol): {"basis", "bars": [(datetime IST, o, h, l, c)]}}."""
    await init_partner_paths_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT session_date, exchange, tradingsymbol, basis, bars_json FROM partner_trade_paths "
            "WHERE session_date>=? AND session_date<=?", (first_day, last_day))).fetchall()
    out = {}
    for day, exchange, symbol, basis, bars_json in rows:
        try:
            raw = json.loads(bars_json)
        except (TypeError, ValueError):
            continue
        bars = []
        for ts, o, h, l, c in raw:
            try:
                bars.append((IST.localize(datetime.fromisoformat(str(ts)[:19])), float(o), float(h), float(l),
                             float(c)))
            except (TypeError, ValueError):
                continue
        out[(day, exchange, symbol)] = {"basis": basis, "bars": sorted(bars, key=lambda b: b[0])}
    return out
