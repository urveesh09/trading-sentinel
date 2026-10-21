"""[O21-PK 2026-10-21] The partner's own Zerodha fills, read once a day.

The partner trades by hand and will not log trades during the day, so the
coach reads them from the partner's Zerodha account instead. The partner
creates a free Kite Connect "Personal" app on their own account (orders
and portfolio APIs, no market data) and taps one Telegram button in the
evening:

  1. after the 15:40 wrap's brief the partner gets "Review your day": a Kite
     login link for the partner's app. [O21-PX] One review link goes out
     every trading day: the coach note's button when it was sent, else this
     prompt (before, a login held all day meant no link on a day without
     trades);
  2. Kite redirects to the gateway's /api/partner-kite/callback, which hands
     the one-time request_token to POST /partner/broker/session;
  3. the engine exchanges it, refuses any account other than
     PARTNER_KITE_USER_ID, reads GET /orders, GET /trades and GET
     /gtt/triggers, and stores one report per filled option order (source
     ZERODHA, exact fill price and exchange time) in partner_trade_reports,
     plus every stop the partner set (SL/SL-M sell orders and sell GTTs) in
     partner_stop_orders, so the coach can see whether a trade had a stop;
  4. after the close it sends the coach note, and the gateway opens the
     coach page with a coach-only session.

A login earlier in the day is kept in memory and the 15:40 wrap reads the
final book itself, so no tap is needed that evening.

[O21-PX] The same read also keeps, best effort, what the deeper review
uses: every option order with its status and Zerodha's reason for a
rejection (partner_orders), the price and trigger changes of each modified
order from its history (partner_order_changes), the day's positions
(partner_broker_positions) and the day's cash (partner_account_days).
After a read of a finished day, partner_trade_paths.py stores each traded
option's 1-minute prices from the owner's market data (the partner's free
app has none).

Read-only by construction: ``_kite_call`` allows only the session exchange
and GET /orders, /trades, /gtt/triggers, /portfolio/positions and
/user/margins/equity, plus GET of one order's history by its numeric id.
Placing is POST /orders/{variety}, modifying PUT and cancelling DELETE
/orders/{variety}/{id}, so there is no place, modify or cancel path for
orders or GTTs. Reads need no static IP (the exchange rule covers API order
endpoints), so they go direct, not through the relay. The access token
lives in memory until Kite's 06:00 expiry and never reaches a log line, the
DB or a response.

On a day with a Zerodha read the coach scores these fills and ignores
Telegram/dashboard BUY/SELL reports for that day (partner_coach.py). Nothing
here places orders, blocks a card or changes card text.
"""
from __future__ import annotations

import asyncio
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
                  ("GET", "/orders"), ("GET", "/trades"), ("GET", "/gtt/triggers"),
                  ("GET", "/portfolio/positions"), ("GET", "/user/margins/equity")}
# [O21-PX] One order's history: GET and a numeric order id only.
_ORDER_HISTORY = re.compile(r"^/orders/[0-9]{1,24}$")
HISTORY_MAX_ORDERS = 40        # order histories read per sync
HISTORY_CONCURRENCY = 3
# History states the exchange confirmed; a refused modify is not a change.
_CONFIRMED_STATES = {"OPEN", "TRIGGER PENDING", "COMPLETE", "CANCELLED"}
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
  account TEXT,
  stops_known INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS partner_stop_orders (
  source_id TEXT PRIMARY KEY,
  session_date TEXT NOT NULL,
  kind TEXT NOT NULL,
  exchange TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  trigger_price REAL NOT NULL,
  quantity INTEGER,
  status TEXT NOT NULL,
  placed_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_partner_stop_orders_day ON partner_stop_orders(session_date, tradingsymbol);
CREATE TABLE IF NOT EXISTS partner_orders (
  order_id TEXT PRIMARY KEY,
  session_date TEXT NOT NULL,
  exchange TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  transaction_type TEXT NOT NULL,
  order_type TEXT,
  product TEXT,
  quantity INTEGER,
  filled_quantity INTEGER,
  price REAL,
  trigger_price REAL,
  average_price REAL,
  status TEXT NOT NULL,
  status_message TEXT,
  placed_at TEXT NOT NULL,
  updated_at TEXT,
  modified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_partner_orders_day ON partner_orders(session_date);
CREATE TABLE IF NOT EXISTS partner_order_changes (
  order_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  session_date TEXT NOT NULL,
  changed_at TEXT NOT NULL,
  field TEXT NOT NULL,
  old_value REAL NOT NULL,
  new_value REAL NOT NULL,
  PRIMARY KEY (order_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_partner_order_changes_day ON partner_order_changes(session_date);
CREATE TABLE IF NOT EXISTS partner_broker_positions (
  session_date TEXT NOT NULL,
  exchange TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  product TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  overnight_quantity INTEGER NOT NULL,
  average_price REAL,
  last_price REAL,
  close_price REAL,
  read_at TEXT NOT NULL,
  PRIMARY KEY (session_date, exchange, tradingsymbol, product)
);
CREATE TABLE IF NOT EXISTS partner_account_days (
  session_date TEXT PRIMARY KEY,
  opening_balance REAL NOT NULL,
  intraday_payin REAL NOT NULL,
  live_balance REAL,
  option_premium REAL,
  read_at TEXT NOT NULL
);
"""
# A stop's state: PENDING (resting), TRIGGERED (it sold), CANCELLED, REJECTED.
_ORDER_STOP_STATUS = {"COMPLETE": "TRIGGERED", "OPEN": "TRIGGERED", "CANCELLED": "CANCELLED",
                      "REJECTED": "REJECTED"}
_GTT_STOP_STATUS = {"active": "PENDING", "triggered": "TRIGGERED", "cancelled": "CANCELLED",
                    "deleted": "CANCELLED", "disabled": "CANCELLED", "expired": "CANCELLED",
                    "rejected": "REJECTED"}


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


def allowed(method: str, path: str) -> bool:
    """The allowlist: the session calls and GET reads only."""
    return (method, path) in _ALLOWED_CALLS or (method == "GET" and bool(_ORDER_HISTORY.match(path)))


async def _kite_call(method: str, path: str, *, data: Optional[dict] = None,
                     params: Optional[dict] = None, token: Optional[str] = None):
    """One Kite REST call from the allowlist; returns the ``data`` field."""
    if not allowed(method, path):
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


def _stop_row(source_id: str, kind: str, exchange: str, symbol: str, trigger: float, quantity,
              status: str, placed_at: datetime, updated_at: Optional[datetime]) -> dict:
    return {"source_id": source_id, "session_date": placed_at.date().isoformat(), "kind": kind,
            "exchange": exchange, "tradingsymbol": symbol, "trigger_price": round(float(trigger), 2),
            "quantity": int(quantity) if quantity else None, "status": status,
            "placed_at": placed_at.isoformat(), "updated_at": updated_at.isoformat() if updated_at else None}


def stops_from_orders(orders: list, resolve: Optional[Callable] = None) -> list:
    """Every SL / SL-M SELL order on an option: the partner's resting stops."""
    resolve = resolve or resolve_option
    rows = []
    for order in orders or []:
        if (str(order.get("transaction_type") or "").upper() != "SELL"
                or str(order.get("order_type") or "").upper() not in ("SL", "SL-M")
                or not float(order.get("trigger_price") or 0) > 0):
            continue
        exchange = str(order.get("exchange") or "").upper()
        symbol = str(order.get("tradingsymbol") or "").upper()
        placed_at = kite_time(order.get("order_timestamp"))
        if exchange not in ("NFO", "BFO") or placed_at is None or resolve(symbol, exchange) is None:
            continue
        raw = str(order.get("status") or "").upper()
        status = _ORDER_STOP_STATUS.get(raw, "PENDING")
        if raw == "CANCELLED" and int(order.get("filled_quantity") or 0) > 0:
            status = "TRIGGERED"          # it sold part before the cancel
        updated = kite_time(order.get("exchange_update_timestamp") or order.get("exchange_timestamp")) or placed_at
        rows.append(_stop_row(f"kite:{order.get('order_id')}", "SL_ORDER", exchange, symbol,
                              float(order["trigger_price"]), order.get("quantity"), status, placed_at, updated))
    return rows


def stops_from_gtts(gtts: list, resolve: Optional[Callable] = None) -> list:
    """Sell GTTs on an option that work as a stop: an OCO's lower leg, or a
    single trigger set below the price at creation (a single one above it is
    a target, not a stop)."""
    resolve = resolve or resolve_option
    rows = []
    for gtt in gtts or []:
        condition = gtt.get("condition") or {}
        exchange = str(condition.get("exchange") or "").upper()
        symbol = str(condition.get("tradingsymbol") or "").upper()
        triggers = [float(v) for v in condition.get("trigger_values") or [] if v]
        sells = [o for o in gtt.get("orders") or [] if str(o.get("transaction_type") or "").upper() == "SELL"]
        placed_at = kite_time(gtt.get("created_at"))
        if (exchange not in ("NFO", "BFO") or not triggers or not sells or placed_at is None
                or resolve(symbol, exchange) is None):
            continue
        if str(gtt.get("type") or "").lower() == "two-leg":
            trigger = min(triggers)
        else:
            last = float(condition.get("last_price") or 0)
            if not (last and triggers[0] < last):
                continue
            trigger = triggers[0]
        status = _GTT_STOP_STATUS.get(str(gtt.get("status") or "").lower(), "PENDING")
        rows.append(_stop_row(f"gtt:{gtt.get('id')}", "GTT", exchange, symbol, trigger, sells[0].get("quantity"),
                              status, placed_at, kite_time(gtt.get("updated_at"))))
    return rows


def _num(value) -> Optional[float]:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def option_orders(orders: list, resolve: Optional[Callable] = None) -> list:
    """[O21-PX] Every option order in the book, filled or not, as stored rows.

    ``modified`` is Kite's own flag; a book without it marks every LIMIT and
    SL order, so their histories are read instead of guessed."""
    resolve = resolve or resolve_option
    rows = []
    for order in orders or []:
        order_id = str(order.get("order_id") or "")
        exchange = str(order.get("exchange") or "").upper()
        symbol = str(order.get("tradingsymbol") or "").upper()
        side = str(order.get("transaction_type") or "").upper()
        placed = kite_time(order.get("order_timestamp"))
        if (not order_id or exchange not in ("NFO", "BFO") or side not in ("BUY", "SELL") or placed is None
                or resolve(symbol, exchange) is None):
            continue
        order_type = str(order.get("order_type") or "").upper()
        modified = (bool(order.get("modified")) if "modified" in order
                    else order_type in ("LIMIT", "SL", "SL-M"))
        updated = kite_time(order.get("exchange_update_timestamp") or order.get("exchange_timestamp"))
        rows.append({
            "order_id": order_id, "session_date": placed.date().isoformat(), "exchange": exchange,
            "tradingsymbol": symbol, "transaction_type": side, "order_type": order_type,
            "product": str(order.get("product") or "").upper(), "quantity": int(order.get("quantity") or 0),
            "filled_quantity": int(order.get("filled_quantity") or 0), "price": _num(order.get("price")),
            "trigger_price": _num(order.get("trigger_price")), "average_price": _num(order.get("average_price")),
            "status": str(order.get("status") or "").upper(),
            "status_message": (str(order.get("status_message") or "").strip()[:200] or None),
            "placed_at": placed.isoformat(), "updated_at": updated.isoformat() if updated else None,
            "modified": int(modified),
        })
    return rows


def order_changes(order_id: str, history: list) -> list:
    """[O21-PX] Each confirmed change of an order's price or trigger, in time order.

    Kite's history lists every state the order went through; a modification
    is a later confirmed state with another price or trigger. Pending states
    are skipped, so a modify the exchange refused is not counted."""
    changes, last = [], None
    for state in history or []:
        if str(state.get("status") or "").upper() not in _CONFIRMED_STATES:
            continue
        at = kite_time(state.get("exchange_update_timestamp") or state.get("order_timestamp"))
        values = {"price": _num(state.get("price")) or 0.0, "trigger_price": _num(state.get("trigger_price")) or 0.0}
        if last is not None and at is not None:
            for field in ("price", "trigger_price"):
                if values[field] and last[field] and abs(values[field] - last[field]) >= 0.005:
                    changes.append({"order_id": order_id, "seq": len(changes), "session_date": at.date().isoformat(),
                                    "changed_at": at.isoformat(), "field": field, "old_value": last[field],
                                    "new_value": values[field]})
        last = values
    return changes


def option_positions(payload, resolve: Optional[Callable] = None) -> list:
    """[O21-PX] The option rows of Kite's net positions."""
    resolve = resolve or resolve_option
    rows = []
    for position in ((payload or {}).get("net") or []) if isinstance(payload, dict) else []:
        exchange = str(position.get("exchange") or "").upper()
        symbol = str(position.get("tradingsymbol") or "").upper()
        if exchange not in ("NFO", "BFO") or resolve(symbol, exchange) is None:
            continue
        rows.append({"exchange": exchange, "tradingsymbol": symbol,
                     "product": str(position.get("product") or "").upper(),
                     "quantity": int(position.get("quantity") or 0),
                     "overnight_quantity": int(position.get("overnight_quantity") or 0),
                     "average_price": _num(position.get("average_price")),
                     "last_price": _num(position.get("last_price")), "close_price": _num(position.get("close_price"))})
    return rows


def account_row(margins) -> Optional[dict]:
    """[O21-PX] The day's cash from Kite's equity margins: the opening balance
    plus money added today. ``None`` without an opening balance."""
    if not isinstance(margins, dict):
        return None
    available = margins.get("available") or {}
    opening = _num(available.get("opening_balance"))
    if opening is None:
        return None
    return {"opening_balance": opening, "intraday_payin": _num(available.get("intraday_payin")) or 0.0,
            "live_balance": _num(available.get("live_balance")),
            "option_premium": _num((margins.get("utilised") or {}).get("option_premium"))}


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
        await db.executescript(_DDL)
        await db.commit()


_STOP_COLS = ("source_id", "session_date", "kind", "exchange", "tradingsymbol", "trigger_price", "quantity",
              "status", "placed_at", "updated_at")


async def store_stops(db_path: str, stops: list) -> None:
    if not stops:
        return
    sql = (f"INSERT INTO partner_stop_orders ({', '.join(_STOP_COLS)}) VALUES ({', '.join('?' for _ in _STOP_COLS)}) "
           f"ON CONFLICT(source_id) DO UPDATE SET "
           f"{', '.join(f'{c}=excluded.{c}' for c in _STOP_COLS if c != 'source_id')}")
    async with aiosqlite.connect(db_path) as db:
        for stop in stops:
            await db.execute(sql, tuple(stop.get(c) for c in _STOP_COLS))
        await db.commit()


async def stop_orders(db_path: str, first_day: str, last_day: str) -> list:
    """The partner's stops placed in the window, oldest first."""
    await init_partner_broker_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            f"SELECT {', '.join(_STOP_COLS)} FROM partner_stop_orders WHERE session_date>=? AND session_date<=? "
            "ORDER BY placed_at", (first_day, last_day))).fetchall()
    return [dict(zip(_STOP_COLS, row)) for row in rows]


_ORDER_COLS = ("order_id", "session_date", "exchange", "tradingsymbol", "transaction_type", "order_type", "product",
               "quantity", "filled_quantity", "price", "trigger_price", "average_price", "status", "status_message",
               "placed_at", "updated_at", "modified")
_CHANGE_COLS = ("order_id", "seq", "session_date", "changed_at", "field", "old_value", "new_value")
_POSITION_COLS = ("session_date", "exchange", "tradingsymbol", "product", "quantity", "overnight_quantity",
                  "average_price", "last_price", "close_price", "read_at")
_ACCOUNT_COLS = ("session_date", "opening_balance", "intraday_payin", "live_balance", "option_premium", "read_at")


def _upsert_sql(table: str, cols: tuple, keys: tuple) -> str:
    return (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT({', '.join(keys)}) DO UPDATE SET "
            f"{', '.join(f'{c}=excluded.{c}' for c in cols if c not in keys)}")


async def store_orders(db_path: str, rows: list) -> None:
    if not rows:
        return
    sql = _upsert_sql("partner_orders", _ORDER_COLS, ("order_id",))
    async with aiosqlite.connect(db_path) as db:
        for row in rows:
            await db.execute(sql, tuple(row.get(c) for c in _ORDER_COLS))
        await db.commit()


async def store_changes(db_path: str, order_id: str, changes: list) -> None:
    """An order's changes as read now (a re-read replaces them)."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM partner_order_changes WHERE order_id=?", (order_id,))
        for change in changes:
            await db.execute(f"INSERT INTO partner_order_changes ({', '.join(_CHANGE_COLS)}) "
                             f"VALUES ({', '.join('?' for _ in _CHANGE_COLS)})",
                             tuple(change.get(c) for c in _CHANGE_COLS))
        await db.commit()


async def store_positions(db_path: str, day: str, rows: list, read_at: datetime) -> None:
    """The day's positions as read now (a re-read replaces them)."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM partner_broker_positions WHERE session_date=?", (day,))
        for row in rows:
            values = row | {"session_date": day, "read_at": read_at.isoformat()}
            await db.execute(f"INSERT OR REPLACE INTO partner_broker_positions ({', '.join(_POSITION_COLS)}) "
                             f"VALUES ({', '.join('?' for _ in _POSITION_COLS)})",
                             tuple(values.get(c) for c in _POSITION_COLS))
        await db.commit()


async def store_account(db_path: str, day: str, row: dict, read_at: datetime) -> None:
    values = row | {"session_date": day, "read_at": read_at.isoformat()}
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_upsert_sql("partner_account_days", _ACCOUNT_COLS, ("session_date",)),
                         tuple(values.get(c) for c in _ACCOUNT_COLS))
        await db.commit()


async def book_details(db_path: str, first_day: str, last_day: str) -> dict:
    """[O21-PX] Orders, order changes, positions and cash for the window:
    {"orders": [...], "changes": {order_id: [...]}, "positions": {day: [...]},
    "accounts": {day: {...}}}."""
    await init_partner_broker_db(db_path)
    window = (first_day, last_day)
    async with aiosqlite.connect(db_path) as db:
        orders = await (await db.execute(
            f"SELECT {', '.join(_ORDER_COLS)} FROM partner_orders WHERE session_date>=? AND session_date<=? "
            "ORDER BY placed_at, order_id", window)).fetchall()
        changes = await (await db.execute(
            f"SELECT {', '.join(_CHANGE_COLS)} FROM partner_order_changes WHERE session_date>=? AND session_date<=? "
            "ORDER BY order_id, seq", window)).fetchall()
        positions = await (await db.execute(
            f"SELECT {', '.join(_POSITION_COLS)} FROM partner_broker_positions WHERE session_date>=? AND session_date<=?",
            window)).fetchall()
        accounts = await (await db.execute(
            f"SELECT {', '.join(_ACCOUNT_COLS)} FROM partner_account_days WHERE session_date>=? AND session_date<=?",
            window)).fetchall()
    by_order: dict = defaultdict(list)
    for row in changes:
        change = dict(zip(_CHANGE_COLS, row))
        by_order[change["order_id"]].append(change)
    by_day: dict = defaultdict(list)
    for row in positions:
        position = dict(zip(_POSITION_COLS, row))
        by_day[position["session_date"]].append(position)
    return {"orders": [dict(zip(_ORDER_COLS, row)) for row in orders], "changes": dict(by_order),
            "positions": dict(by_day),
            "accounts": {row[0]: dict(zip(_ACCOUNT_COLS, row)) for row in accounts}}


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
            "SELECT session_date, synced_at, complete, option_orders, other_orders, stops_known "
            "FROM partner_broker_days WHERE session_date>=? AND session_date<=?", (first_day, last_day))).fetchall()
    return {day: {"synced_at": synced_at, "complete": bool(complete), "option_orders": n, "other_orders": other,
                  "stops_known": bool(stops_known)}
            for day, synced_at, complete, n, other, stops_known in rows}


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
    # Stops: SL orders are in the order book; a GTT stop only shows here. If
    # the GTT list cannot be read, "no stop" is unknown and never flagged.
    try:
        gtts = await _read("/gtt/triggers")
        stops_known = True
    except BrokerError as exc:
        if exc.code in ("TokenException", "not_connected"):
            raise
        logger.warning("partner_zerodha_gtts_unavailable code=%s", exc.code)
        gtts, stops_known = [], False
    await store_stops(db_path, stops_from_orders(orders) + stops_from_gtts(gtts))
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
                "INSERT INTO partner_broker_days(session_date,synced_at,complete,option_orders,other_orders,account,"
                "stops_known) VALUES(?,?,?,?,?,?,?) ON CONFLICT(session_date) DO UPDATE SET "
                "synced_at=excluded.synced_at, complete=MAX(partner_broker_days.complete, excluded.complete), "
                "option_orders=excluded.option_orders, other_orders=excluded.other_orders, "
                "account=excluded.account, stops_known=excluded.stops_known",
                (day, now.isoformat(), int(complete), len(day_reports), other,
                 _session.account if _session else None, int(stops_known)))
            result_days[day] = {"option_orders": len(day_reports), "complete": complete, "stops_known": stops_known}
        await db.commit()
    details = await _read_details(db_path, orders, now)
    paths = await _store_paths(db_path, [d for d, row in result_days.items() if row["complete"]], now)
    logger.info("partner_zerodha_synced days=%s option_orders=%d other=%d unfilled=%d on_card=%d",
                ",".join(days), counts["option_orders"], counts["other_orders"], counts["unfilled_orders"],
                sum(1 for r in reports if r["advisory_id"]))
    return {"synced_at": now.isoformat(), "days": result_days, **counts,
            "on_card": sum(1 for r in reports if r["advisory_id"]), "details": details, "paths": paths}


async def _read_details(db_path: str, orders: list, now: datetime) -> dict:
    """[O21-PX] What the deeper review reads besides the fills, best effort:
    a part that cannot be read is left out and the review says less."""
    out = {"orders": 0, "histories": 0, "history_failures": 0, "positions": None, "account": None}
    try:
        rows = option_orders(orders)
        await store_orders(db_path, rows)
        out["orders"] = len(rows)
        wanted = [r["order_id"] for r in rows if r["modified"]
                  and _ORDER_HISTORY.match(f"/orders/{r['order_id']}")][:HISTORY_MAX_ORDERS]
        gate = asyncio.Semaphore(HISTORY_CONCURRENCY)

        async def history(order_id: str):
            async with gate:
                try:
                    return order_id, order_changes(order_id, await _read(f"/orders/{order_id}"))
                except BrokerError as exc:
                    if exc.code in ("TokenException", "not_connected"):
                        raise
                    return order_id, None

        for order_id, changes in await asyncio.gather(*(history(o) for o in wanted)):
            if changes is None:
                out["history_failures"] += 1
                continue
            await store_changes(db_path, order_id, changes)
            out["histories"] += 1
        # Positions and cash describe today, from the open on.
        if now.hour * 60 + now.minute >= OPEN_MIN:
            day = now.date().isoformat()
            try:
                positions = option_positions(await _read("/portfolio/positions"))
                await store_positions(db_path, day, positions, now)
                out["positions"] = len(positions)
            except BrokerError as exc:
                if exc.code in ("TokenException", "not_connected"):
                    raise
                logger.warning("partner_zerodha_positions_unavailable code=%s", exc.code)
            try:
                account = account_row(await _read("/user/margins/equity"))
                if account is not None:
                    await store_account(db_path, day, account, now)
                    out["account"] = True
            except BrokerError as exc:
                if exc.code in ("TokenException", "not_connected"):
                    raise
                logger.warning("partner_zerodha_margins_unavailable code=%s", exc.code)
    except BrokerError as exc:
        if exc.code == "TokenException":
            disconnect()
        logger.warning("partner_zerodha_details_failed code=%s", exc.code)
    except Exception as exc:   # the fills are stored; extras must never fail the read
        logger.warning("partner_zerodha_details_failed err=%s", type(exc).__name__)
    return out


async def _store_paths(db_path: str, days: list, now: datetime) -> dict:
    """[O21-PX] The traded options' prices for each finished day (never fails the read)."""
    from partner_trade_paths import ensure_paths
    out = {}
    for day in days:
        try:
            out[day] = await ensure_paths(db_path, day, now)
        except Exception as exc:
            logger.warning("partner_trade_paths_failed day=%s err=%s", day, type(exc).__name__)
            out[day] = {"status": "failed"}
    return out


# ---------------------------------------------------------------------------
# the evening flow
# ---------------------------------------------------------------------------

def review_keyboard(label: str = "📒 Open today's review") -> Optional[dict]:
    """A URL button to the partner's Kite login, which ends on the coach page."""
    url = login_url()
    if url is None:
        return None
    return {"inline_keyboard": [[{"text": label, "url": url}]]}


def prompt_text(now: datetime) -> str:
    """The evening message: the day, what the tap does, what the review holds."""
    return (f"📒 Review your day ({now.astimezone(IST).strftime('%a %d %b')})\n"
            "Tap below and log in to Zerodha. The system reads today's orders (read-only) and opens your "
            "review: the lesson of the day, what went well, and each trade step by step.")


async def _sent_today(db_path: str, kind: str, day: str) -> bool:
    from partner_orchestrator import _partner_db
    async with _partner_db(db_path) as db:
        row = await (await db.execute("SELECT 1 FROM partner_messages WHERE kind=? AND dedup_key=? AND delivered=1",
                                      (kind, day))).fetchone()
    return row is not None


async def _send_prompt(now: datetime) -> dict:
    from partner_bot import partner_enabled, send_partner_result
    from partner_orchestrator import _record, _seen
    day = now.date().isoformat()
    if not partner_enabled():
        return {"status": "partner_disabled"}
    if await _seen(settings.DB_PATH, PROMPT_KIND, day):
        return {"status": "already_prompted"}
    result = await send_partner_result(prompt_text(now), kind=PROMPT_KIND, reply_markup=review_keyboard())
    await _record(settings.DB_PATH, PROMPT_KIND, day, result.delivered, now=now)
    return {"status": "prompted" if result.delivered else "prompt_failed"}


async def partner_broker_eod(now: Optional[datetime] = None) -> dict:
    """15:40 wrap, after the day's brief: read the book when a login is held,
    else send the review button once."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not configured():
        return {"status": "not_configured"}
    if connected(now):
        try:
            return {"status": "synced", **await sync_book(now)}
        except BrokerError as exc:
            logger.warning("partner_zerodha_eod_sync_failed code=%s", exc.code)
    return await _send_prompt(now)


async def ensure_review_message(now: Optional[datetime] = None) -> dict:
    """[O21-PX] The wrap's last partner step: every trading day the partner
    gets one message with the review link, the coach note (whose button is
    the same login) or else this prompt. A login held all day used to mean
    no link on a day without trades."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not configured():
        return {"status": "not_configured"}
    if await _sent_today(settings.DB_PATH, "coach", now.date().isoformat()):
        return {"status": "coach_note_sent"}
    return await _send_prompt(now)


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
