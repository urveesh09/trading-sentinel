"""[O21-PK 2026-10-21] The partner's own Zerodha fills, read once a day.

The partner trades by hand and will not log trades during the day, so the
coach reads them from the partner's Zerodha account instead. The partner
creates a free Kite Connect "Personal" app on their own account (orders
and portfolio APIs, no market data) and taps one Telegram button in the
evening:

  1. the 15:40 wrap sends "Open today's review": a Kite login link for the
     partner's app (only when no login is held for today);
  2. Kite redirects to the gateway's /api/partner-kite/callback, which hands
     the one-time request_token to POST /partner/broker/session;
  3. the engine exchanges it, refuses any account other than
     PARTNER_KITE_USER_ID, reads GET /orders and GET /trades, and stores one
     report per filled option order (source ZERODHA, exact fill price and
     exchange time) in partner_trade_reports;
  4. after the close it sends the coach note, and the gateway opens the
     coach page with a coach-only session.

A login earlier in the day is kept in memory and the 15:40 wrap reads the
final book itself, so no tap is needed that evening.

Read-only by construction: ``_kite_call`` allows only the session exchange,
GET /orders and GET /trades, so there is no order, GTT or modify path. The
exchange's static-IP rule applies to API order endpoints only, so a partner
app with no static IP registered cannot place API orders at all. The access
token lives in memory until Kite's 06:00 expiry and never reaches a log
line, the DB or a response.

On a day with a Zerodha read the coach scores these fills and ignores
Telegram/dashboard BUY/SELL reports for that day (partner_coach.py). Nothing
here places orders, blocks a card or changes card text.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from urllib.parse import urlencode

import aiosqlite
import httpx
import pytz
import structlog

from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

SOURCE = "ZERODHA"
PRICE_BASIS = "BROKER_FILL"
TIME_BASIS = "EXCHANGE_FILL"
LOGIN_URL = "https://kite.zerodha.com/connect/login"
OPEN_MIN = 9 * 60 + 15
CLOSE_MIN = 15 * 60 + 30          # F&O orders cannot fill after this; a later read is the day's book
CARD_CLOCK_SLACK = timedelta(seconds=60)   # a fill this close before the card's send time is on that card
PROMPT_KIND = "zerodha_prompt"
_REQUEST_TOKEN = re.compile(r"^[A-Za-z0-9]{8,64}$")
_ALLOWED_CALLS = {("POST", "/session/token"), ("DELETE", "/session/token"),
                  ("GET", "/orders"), ("GET", "/trades")}
_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}
_WEEKLY_MONTH = {**{str(i): i for i in range(1, 10)}, "O": 10, "N": 11, "D": 12}
# NIFTY25O2122950PE (weekly: YY, month 1-9/O/N/D, DD) or NIFTY25OCT22950PE (monthly).
_OPTION_SYMBOL = re.compile(
    r"^([A-Z][A-Z&-]*?)(\d{2})(?:([1-9OND])(\d{2})|(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC))"
    r"(\d+(?:\.\d+)?)(CE|PE)$")

_DDL = """
CREATE TABLE IF NOT EXISTS partner_broker_days (
  session_date TEXT PRIMARY KEY,
  synced_at TEXT NOT NULL,
  complete INTEGER NOT NULL,
  option_orders INTEGER NOT NULL,
  other_orders INTEGER NOT NULL,
  account TEXT
)
"""


class BrokerError(Exception):
    """A Kite call or login that failed; ``code`` is safe to show."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


@dataclass
class _Session:
    access_token: str
    account: str          # masked user id
    login_at: datetime
    expires_at: datetime


_session: Optional[_Session] = None


# ---------------------------------------------------------------------------
# configuration and session
# ---------------------------------------------------------------------------

def configured() -> bool:
    return bool(settings.PARTNER_ZERODHA_SYNC_ENABLED and settings.PARTNER_KITE_API_KEY
                and settings.PARTNER_KITE_API_SECRET and settings.PARTNER_KITE_USER_ID)


def login_url() -> Optional[str]:
    if not configured():
        return None
    return f"{LOGIN_URL}?{urlencode({'v': 3, 'api_key': settings.PARTNER_KITE_API_KEY})}"


def mask_account(user_id: str) -> str:
    user_id = str(user_id or "")
    return user_id[:2] + "***" + user_id[-2:] if len(user_id) > 4 else "***"


def next_expiry(now: datetime) -> datetime:
    """Kite access tokens end at 06:00 IST the next morning."""
    now = now.astimezone(IST)
    six = IST.localize(datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=6))
    return six if now < six else six + timedelta(days=1)


def connected(now: Optional[datetime] = None) -> bool:
    now = (now or datetime.now(IST)).astimezone(IST)
    return _session is not None and now < _session.expires_at


def disconnect() -> None:
    global _session
    _session = None


async def _kite_call(method: str, path: str, *, data: Optional[dict] = None,
                     params: Optional[dict] = None, token: Optional[str] = None):
    """One Kite REST call from the allowlist; returns the ``data`` field."""
    if (method, path) not in _ALLOWED_CALLS:
        raise BrokerError("not_allowed", f"{method} {path} is not a read call")
    headers = {"X-Kite-Version": "3"}
    if token:
        headers["Authorization"] = f"token {settings.PARTNER_KITE_API_KEY}:{token}"
    async with httpx.AsyncClient(base_url=settings.PARTNER_KITE_BASE_URL, timeout=15.0) as client:
        try:
            response = await client.request(method, path, data=data, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise BrokerError("network", type(exc).__name__) from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400 or body.get("status") == "error":
        raise BrokerError(str(body.get("error_type") or f"http_{response.status_code}"),
                          str(body.get("message") or "")[:160])
    return body.get("data")


async def create_session(request_token: str, now: Optional[datetime] = None) -> dict:
    """Exchange the one-time request_token; only PARTNER_KITE_USER_ID is kept."""
    global _session
    now = (now or datetime.now(IST)).astimezone(IST)
    if not configured():
        raise BrokerError("not_configured")
    if not _REQUEST_TOKEN.match(str(request_token or "")):
        raise BrokerError("bad_request_token")
    api_key, secret = settings.PARTNER_KITE_API_KEY, settings.PARTNER_KITE_API_SECRET
    checksum = hashlib.sha256(f"{api_key}{request_token}{secret}".encode()).hexdigest()
    data = await _kite_call("POST", "/session/token",
                            data={"api_key": api_key, "request_token": request_token, "checksum": checksum})
    token = str((data or {}).get("access_token") or "")
    user_id = str((data or {}).get("user_id") or "")
    if not token:
        raise BrokerError("no_access_token")
    if user_id.upper() != settings.PARTNER_KITE_USER_ID.strip().upper():
        try:
            await _kite_call("DELETE", "/session/token", params={"api_key": api_key, "access_token": token})
        except BrokerError:
            pass
        logger.warning("partner_zerodha_wrong_account account=%s", mask_account(user_id))
        raise BrokerError("wrong_account")
    _session = _Session(access_token=token, account=mask_account(user_id), login_at=now,
                        expires_at=next_expiry(now))
    logger.info("partner_zerodha_login account=%s expires=%s", _session.account, _session.expires_at.isoformat())
    return {"account": _session.account, "login_at": now.isoformat(), "expires_at": _session.expires_at.isoformat()}


async def _read(path: str):
    if _session is None:
        raise BrokerError("not_connected")
    try:
        return await _kite_call("GET", path, token=_session.access_token) or []
    except BrokerError as exc:
        if exc.code == "TokenException":
            disconnect()
        raise


# ---------------------------------------------------------------------------
# orders -> reports (pure)
# ---------------------------------------------------------------------------

def kite_time(value) -> Optional[datetime]:
    """Kite's 'YYYY-MM-DD HH:MM:SS' (IST) or ISO with an offset."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("T", " "))
    except ValueError:
        return None
    return parsed.astimezone(IST) if parsed.tzinfo else IST.localize(parsed)


def parse_option_symbol(symbol: str) -> Optional[dict]:
    """Underlying, strike, CE/PE and (weekly) expiry from a Kite option symbol."""
    match = _OPTION_SYMBOL.match(str(symbol or "").upper())
    if not match:
        return None
    name, yy, week_month, week_day, month, strike, opt_type = match.groups()
    expiry = None
    if week_month:
        try:
            expiry = date(2000 + int(yy), _WEEKLY_MONTH[week_month], int(week_day)).isoformat()
        except ValueError:
            return None
    return {"underlying": name, "strike": float(strike), "opt_type": opt_type, "expiry": expiry,
            "expiry_month": f"20{yy}-{_MONTHS[month]:02d}" if month else None, "lot_size": None}


def resolve_option(symbol: str, exchange: str) -> Optional[dict]:
    """The contract from the morning instrument books, else the symbol itself."""
    try:
        from fno_underlyings import SPECS, get_instruments_for
        for name, spec in SPECS.items():
            if spec.segment != exchange:
                continue
            contract = get_instruments_for(name).by_symbol.get(symbol)
            if contract is not None and contract.instrument_type in ("CE", "PE"):
                return {"underlying": contract.name, "strike": float(contract.strike),
                        "opt_type": contract.instrument_type, "expiry": contract.expiry.isoformat(),
                        "lot_size": int(contract.lot_size) or None}
    except Exception as exc:   # an unloaded book must not stop the read
        logger.warning("partner_zerodha_book_lookup_failed err=%s", type(exc).__name__)
    parsed = parse_option_symbol(symbol)
    if parsed is not None:
        from partner_fill_capture import _off_card_lot_size
        parsed["lot_size"] = _off_card_lot_size(parsed["underlying"])
    return parsed


def _filled_orders(orders: list, trades: list, resolve: Callable) -> tuple[list, dict]:
    fills: dict = defaultdict(list)
    for trade in trades or []:
        fills[str(trade.get("order_id") or "")].append(trade)
    counts = {"option_orders": 0, "other_orders": 0, "unfilled_orders": 0}
    rows = []
    for order in orders or []:
        order_id = str(order.get("order_id") or "")
        if not order_id:
            continue
        own = fills.get(order_id, [])
        qty = sum(int(f.get("quantity") or 0) for f in own) or int(order.get("filled_quantity") or 0)
        if qty <= 0:
            counts["unfilled_orders"] += 1
            continue
        exchange = str(order.get("exchange") or "").upper()
        symbol = str(order.get("tradingsymbol") or "").upper()
        contract = resolve(symbol, exchange) if exchange in ("NFO", "BFO") else None
        if contract is None:
            counts["other_orders"] += 1
            continue
        if own:
            priced = [(float(f.get("average_price") or 0), int(f.get("quantity") or 0)) for f in own]
            price = round(sum(p * q for p, q in priced) / qty, 4)
            times = [kite_time(f.get("fill_timestamp") or f.get("exchange_timestamp")) for f in own]
            at = min((t for t in times if t), default=None)
        else:
            price = float(order.get("average_price") or 0) or None
            at = None
        at = at or kite_time(order.get("exchange_timestamp") or order.get("order_timestamp"))
        if at is None or str(order.get("transaction_type") or "").upper() not in ("BUY", "SELL"):
            counts["other_orders"] += 1
            continue
        counts["option_orders"] += 1
        rows.append({"order_id": order_id, "action": str(order["transaction_type"]).upper(), "symbol": symbol,
                     "exchange": exchange, "contract": contract, "qty": qty, "price": price, "at": at,
                     "order_type": str(order.get("order_type") or ""), "status": str(order.get("status") or ""),
                     "product": str(order.get("product") or "")})
    rows.sort(key=lambda r: (r["at"], r["order_id"]))
    return rows, counts


def build_reports(orders: list, trades: list, cards: list, *, received_at: datetime,
                  resolve: Optional[Callable] = None) -> tuple[list, dict]:
    """One report per filled option order, matched to the partner's cards.

    A BUY belongs to the latest card for the same contract sent before it;
    a SELL to the card it closes (the latest one still holding quantity),
    else the latest card for that contract. Anything else is off-card.
    """
    rows, counts = _filled_orders(orders, trades, resolve or resolve_option)
    by_contract: dict = defaultdict(list)
    for card in sorted(cards, key=lambda c: c["delivered_at"]):
        by_contract[(str(card.get("exchange") or "").upper(), str(card.get("tradingsymbol") or "").upper())].append(card)
    open_qty: dict = defaultdict(int)
    reports = []
    for row in rows:
        candidates = [c for c in by_contract.get((row["exchange"], row["symbol"]), [])
                      if c["delivered_at"] <= row["at"] + CARD_CLOCK_SLACK
                      and c.get("session_date") in (None, row["at"].date().isoformat())]
        card = None
        if row["action"] == "BUY":
            card = candidates[-1] if candidates else None
            if card is not None:
                open_qty[card["advisory_id"]] += row["qty"]
        else:
            holding = [c for c in candidates if open_qty[c["advisory_id"]] > 0]
            card = holding[-1] if holding else (candidates[-1] if candidates else None)
            if card is not None:
                open_qty[card["advisory_id"]] = max(open_qty[card["advisory_id"]] - row["qty"], 0)
        contract = row["contract"]
        lot_size = contract.get("lot_size") or (card or {}).get("lot_size")
        note = f"Zerodha {row['order_type'] or 'order'} {row['product']} #{row['order_id']}".replace("  ", " ")
        if row["status"] and row["status"] != "COMPLETE":
            note += f", {row['status'].lower()} after {row['qty']} filled"
        if lot_size and row["qty"] % lot_size == 0:
            lots = row["qty"] // lot_size
        else:
            # Never invent lots: score the exact quantity as units.
            note += f"; {row['qty']} qty is not a multiple of lot size {lot_size or '?'}, scored as units"
            lots, lot_size = row["qty"], 1
        reports.append({
            "dedup_key": f"kite:{row['order_id']}", "source": SOURCE, "received_at": received_at.isoformat(),
            "trade_at": row["at"].isoformat(), "trade_at_basis": TIME_BASIS, "action": row["action"],
            "advisory_id": card["advisory_id"] if card else None,
            "session_date": row["at"].date().isoformat(), "underlying": contract.get("underlying"),
            "tradingsymbol": row["symbol"], "strike": contract.get("strike"), "opt_type": contract.get("opt_type"),
            "expiry": contract.get("expiry"), "exchange": row["exchange"], "lots": lots, "lot_size": lot_size,
            "price": row["price"], "price_basis": PRICE_BASIS, "note": note,
        })
    return reports, counts


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

_UPSERT_COLS = ("dedup_key", "source", "received_at", "trade_at", "trade_at_basis", "action", "advisory_id",
                "session_date", "underlying", "tradingsymbol", "strike", "opt_type", "expiry", "exchange",
                "lots", "lot_size", "price", "price_basis", "note")
_REFRESHED = ("received_at", "trade_at", "advisory_id", "lots", "lot_size", "price", "note")


async def init_partner_broker_db(db_path: str) -> None:
    from partner_fill_capture import init_partner_fill_db
    await init_partner_fill_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.commit()


async def store_reports(db_path: str, reports: list) -> int:
    """Insert or refresh by order id (a partly filled order grows); voided rows stay voided."""
    if not reports:
        return 0
    sql = (f"INSERT INTO partner_trade_reports ({', '.join(_UPSERT_COLS)}, status) "
           f"VALUES ({', '.join('?' for _ in _UPSERT_COLS)}, 'ACTIVE') "
           f"ON CONFLICT(dedup_key) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in _REFRESHED)} "
           "WHERE partner_trade_reports.status='ACTIVE'")
    async with aiosqlite.connect(db_path) as db:
        for report in reports:
            await db.execute(sql, tuple(report.get(c) for c in _UPSERT_COLS))
        await db.commit()
    return len(reports)


async def broker_days(db_path: str, first_day: str, last_day: str) -> dict:
    """{day: {synced_at, complete, option_orders, other_orders}} for days read from Zerodha."""
    await init_partner_broker_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT session_date, synced_at, complete, option_orders, other_orders FROM partner_broker_days "
            "WHERE session_date>=? AND session_date<=?", (first_day, last_day))).fetchall()
    return {day: {"synced_at": synced_at, "complete": bool(complete), "option_orders": n, "other_orders": other}
            for day, synced_at, complete, n, other in rows}


async def _day_cards(db_path: str, first_day: str, last_day: str) -> list:
    """Delivered buyer cards in the window, with their Kite symbol and send time."""
    from partner_fill_capture import CARD_KIND, load_card
    async with aiosqlite.connect(db_path) as db:
        try:
            rows = await (await db.execute(
                "SELECT dedup_key, sent_at FROM partner_hedge_messages WHERE kind=? AND delivered=1",
                (CARD_KIND,))).fetchall()
        except aiosqlite.OperationalError:
            return []
    cards = []
    for advisory_id, sent_at in rows:
        delivered_at = kite_time(sent_at)
        if delivered_at is None or not first_day <= delivered_at.date().isoformat() <= last_day:
            continue
        card = await load_card(db_path, str(advisory_id))
        if card is None or not card.get("tradingsymbol"):
            continue
        card["delivered_at"] = delivered_at
        cards.append(card)
    return cards


def _complete(day: str, at: datetime) -> bool:
    close = IST.localize(datetime.fromisoformat(day) + timedelta(minutes=CLOSE_MIN))
    return at.astimezone(IST) >= close


async def sync_book(now: Optional[datetime] = None, *, db_path: Optional[str] = None) -> dict:
    """Read the partner's order book and store its filled option orders."""
    now = (now or datetime.now(IST)).astimezone(IST)
    db_path = db_path or settings.DB_PATH
    if not connected(now):
        disconnect()
        raise BrokerError("not_connected")
    await init_partner_broker_db(db_path)
    orders = await _read("/orders")
    try:
        trades = await _read("/trades")
    except BrokerError as exc:
        if exc.code in ("TokenException", "not_connected"):
            raise
        # Orders alone still carry the average price and exchange time.
        logger.warning("partner_zerodha_trades_unavailable code=%s", exc.code)
        trades = []
    today = now.date().isoformat()
    stamps = [kite_time(o.get("order_timestamp")) for o in orders or []]
    days = {s.date().isoformat() for s in stamps if s}
    if now.hour * 60 + now.minute >= OPEN_MIN:
        days.add(today)   # an empty book after the open is a day without trades; before it, it says nothing
    days = sorted(days)
    cards = await _day_cards(db_path, days[0], days[-1]) if days else []
    reports, counts = build_reports(orders, trades, cards, received_at=now)
    await store_reports(db_path, reports)
    result_days = {}
    async with aiosqlite.connect(db_path) as db:
        for day in days:
            day_reports = [r for r in reports if r["session_date"] == day]
            other = counts["other_orders"] if day == today else 0
            complete = _complete(day, now)
            await db.execute(
                "INSERT INTO partner_broker_days(session_date,synced_at,complete,option_orders,other_orders,account) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(session_date) DO UPDATE SET synced_at=excluded.synced_at, "
                "complete=MAX(partner_broker_days.complete, excluded.complete), "
                "option_orders=excluded.option_orders, other_orders=excluded.other_orders, account=excluded.account",
                (day, now.isoformat(), int(complete), len(day_reports), other, _session.account if _session else None))
            result_days[day] = {"option_orders": len(day_reports), "complete": complete}
        await db.commit()
    logger.info("partner_zerodha_synced days=%s option_orders=%d other=%d unfilled=%d on_card=%d",
                ",".join(days), counts["option_orders"], counts["other_orders"], counts["unfilled_orders"],
                sum(1 for r in reports if r["advisory_id"]))
    return {"synced_at": now.isoformat(), "days": result_days, **counts,
            "on_card": sum(1 for r in reports if r["advisory_id"])}


# ---------------------------------------------------------------------------
# the evening flow
# ---------------------------------------------------------------------------

def review_keyboard(label: str = "📒 Open today's review") -> Optional[dict]:
    """A URL button to the partner's Kite login, which ends on the coach page."""
    url = login_url()
    if url is None:
        return None
    return {"inline_keyboard": [[{"text": label, "url": url}]]}


PROMPT_TEXT = ("📒 Today's review\n"
               "Tap below and log in to Zerodha. The system reads today's orders "
               "(read-only) and opens your review with what to keep and what to change.")


async def partner_broker_eod(now: Optional[datetime] = None) -> dict:
    """15:40 wrap: read the book when a login is held, else send the review button once."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not configured():
        return {"status": "not_configured"}
    if connected(now):
        try:
            return {"status": "synced", **await sync_book(now)}
        except BrokerError as exc:
            logger.warning("partner_zerodha_eod_sync_failed code=%s", exc.code)
    from partner_bot import partner_enabled, send_partner_result
    from partner_orchestrator import _record, _seen
    day = now.date().isoformat()
    if not partner_enabled():
        return {"status": "partner_disabled"}
    if await _seen(settings.DB_PATH, PROMPT_KIND, day):
        return {"status": "already_prompted"}
    result = await send_partner_result(PROMPT_TEXT, kind=PROMPT_KIND, reply_markup=review_keyboard())
    await _record(settings.DB_PATH, PROMPT_KIND, day, result.delivered, now=now)
    return {"status": "prompted" if result.delivered else "prompt_failed"}


async def on_login(request_token: str, now: Optional[datetime] = None) -> dict:
    """The partner's Kite login: session, read, then the coach note after the close."""
    now = (now or datetime.now(IST)).astimezone(IST)
    session = await create_session(request_token, now)
    synced = await sync_book(now)
    note = "before_close"
    today = synced["days"].get(now.date().isoformat())
    if today and today["complete"]:
        from partner_coach import partner_coach_eod
        try:
            note = (await partner_coach_eod(now)).get("note")
        except Exception as exc:
            logger.warning("partner_zerodha_coach_note_failed err=%s", type(exc).__name__)
            note = "failed"
    return {"connected": True, **session, **synced, "note": note, "automatic_execution": False}


def status(now: Optional[datetime] = None) -> dict:
    now = (now or datetime.now(IST)).astimezone(IST)
    live = connected(now)
    return {"configured": configured(), "connected": live,
            "account": _session.account if live else None,
            "login_at": _session.login_at.isoformat() if live else None,
            "expires_at": _session.expires_at.isoformat() if live else None,
            "read_only": True}
