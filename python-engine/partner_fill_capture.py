"""[O21-PC 2026-10-21] Partner fill capture: what the partner actually did.

The partner trades real money by hand. Until now the system knew what it
advised but never what was bought, at what price or when:
``partner_positions`` and ``partner_advisory_feedback`` both had 0 rows on
Oct 21. This module is the inbound half of the partner bot, so a fill can be
reported in one tap:

  - every entry card carries buttons: Bought 1 lot / Bought 2 lots / Skipped;
  - every exit-type update (stop, target, square-off) carries Sold buttons;
  - after a tap the buttons change to show what was recorded, with Undo;
  - a reply to a card or update records or corrects in the partner's words:
    "518.5", "b 518.5 x2", "s 560 @14:42", "skip", "undo";
  - an off-card trade is "b NIFTY 22950 PE 120 x2" (or "/b ..." in a group,
    where Telegram only delivers commands and replies to the bot).

Prices. A tap records the option's ask (buy) or bid (sell) from one
management-lane quote at the tap, labelled ASK_AT_TAP / BID_AT_TAP. That is
an estimate of the partner's fill and is shown as "≈". A typed price is
PARTNER_STATED and replaces the estimate. No price is taken from the card.

Security. Only updates from PARTNER_TELEGRAM_CHAT_ID are read; others are
counted and dropped. The token never reaches a log line.

Nothing here places orders, blocks or delays a card, or changes card text.
partner_coach.py turns these reports into the coaching view.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
import pytz
import structlog

from config import settings
from partner_bot import partner_api, partner_enabled

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

CARD_KIND = "manual_market_advisory"
UPDATE_KIND = "manual_advisory_update"
EXIT_EVENTS = ("INVALIDATION", "TARGET_ZONE", "SESSION_EXIT_REMINDER")
CALLBACK_PREFIX = "pf"
ESTIMATE_BASES = ("ASK_AT_TAP", "BID_AT_TAP", "LTP_AT_TAP")
DOUBLE_TAP_SEC = 10           # the same button twice this fast is one tap
CORRECTION_WINDOW_MIN = 30    # a bare price this soon after a Bought tap corrects it
HELP_COOLDOWN_SEC = 600       # at most one "didn't catch that" per 10 minutes
MESSAGE_LOOKBACK_DAYS = 7     # replies are matched to messages this recent
CAPTURE_START_MIN = 9 * 60    # inbound polling window, IST, every day
CAPTURE_END_MIN = 21 * 60
MAX_LOTS = 50
_ADVISORY_ID = re.compile(r"^[0-9a-f]{8,40}$")
_INDICES = ("NIFTY", "SENSEX", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")

_DDL = """
CREATE TABLE IF NOT EXISTS partner_trade_reports (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  dedup_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  received_at TEXT NOT NULL,
  trade_at TEXT NOT NULL,
  trade_at_basis TEXT NOT NULL,
  action TEXT NOT NULL,
  advisory_id TEXT,
  session_date TEXT NOT NULL,
  underlying TEXT,
  tradingsymbol TEXT,
  strike REAL,
  opt_type TEXT,
  expiry TEXT,
  exchange TEXT,
  lots INTEGER,
  lot_size INTEGER,
  price REAL,
  price_basis TEXT NOT NULL,
  quote_bid REAL,
  quote_ask REAL,
  quote_ltp REAL,
  corrects_report_id INTEGER,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  raw_text TEXT,
  message_id INTEGER,
  note TEXT
);
CREATE INDEX IF NOT EXISTS ix_partner_trade_reports_day
  ON partner_trade_reports(session_date, status);
CREATE INDEX IF NOT EXISTS ix_partner_trade_reports_card
  ON partner_trade_reports(advisory_id, status);
CREATE TABLE IF NOT EXISTS partner_inbox_state (
  state_key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

_REPORT_COLS = (
    "report_id, dedup_key, source, received_at, trade_at, trade_at_basis, action, advisory_id, "
    "session_date, underlying, tradingsymbol, strike, opt_type, expiry, exchange, lots, lot_size, "
    "price, price_basis, quote_bid, quote_ask, quote_ltp, corrects_report_id, status, raw_text, "
    "message_id, note"
)


async def init_partner_fill_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_DDL)
        await db.commit()


# ---------------------------------------------------------------------------
# parsing (pure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedReport:
    """One partner message read as a trade report."""
    action: Optional[str]          # BUY | SELL | SKIP | UNDO | None (a bare price)
    price: Optional[float] = None
    lots: Optional[int] = None
    stated_time: Optional[str] = None   # "HH:MM"
    underlying: Optional[str] = None    # off-card contract, when named
    strike: Optional[float] = None
    opt_type: Optional[str] = None


_ACTION_WORDS = {
    "b": "BUY", "buy": "BUY", "bought": "BUY", "long": "BUY",
    "s": "SELL", "sell": "SELL", "sold": "SELL", "exit": "SELL", "exited": "SELL",
    "out": "SELL", "booked": "SELL", "book": "SELL", "sl": "SELL",
    "skip": "SKIP", "skipped": "SKIP", "pass": "SKIP", "no": "SKIP",
    "undo": "UNDO", "cancel": "UNDO", "wrong": "UNDO", "delete": "UNDO",
}
_TIME = re.compile(r"^@?([01]?\d|2[0-3])[:.]([0-5]\d)$")
_LOTS = re.compile(r"^(?:x|\*)(\d{1,2})$|^(\d{1,2})(?:lots?|l)$")
_CONTRACT = re.compile(r"^(\d{4,6})(ce|pe)$")
_NUMBER = re.compile(r"^(?:₹|rs\.?|inr)?(\d+(?:\.\d+)?)$")


def parse_report_text(text: str) -> Optional[ParsedReport]:
    """Read "b 518.5 x2 @12:10", "518.5", "skip", "s NIFTY 22950 PE 140".

    Returns ``None`` when the message is not a trade report. A message with
    an action word and nothing else ("sold") is valid: the caller prices it
    like a tap.
    """
    raw = (text or "").strip().lower()
    if not raw or len(raw) > 120:
        return None
    raw = raw.replace(",", " ")
    tokens = raw.split()
    if tokens and tokens[0].startswith("/"):
        tokens[0] = tokens[0][1:].split("@", 1)[0]
    action = None
    underlying = strike = opt_type = None
    lots = None
    stated_time = None
    numbers: list[float] = []
    pending_lots = False
    for i, tok in enumerate(tokens):
        if not tok:
            continue
        if tok in _ACTION_WORDS and action is None:
            action = _ACTION_WORDS[tok]
            continue
        if tok in ("lot", "lots") and numbers and lots is None:
            lots = int(numbers.pop())
            continue
        if tok in ("x", "qty"):
            pending_lots = True
            continue
        if tok.upper() in _INDICES:
            underlying = tok.upper()
            continue
        if tok in ("ce", "pe", "call", "put", "calls", "puts"):
            opt_type = "CE" if tok.startswith("c") else "PE"
            if numbers and strike is None and numbers[-1] >= 1000:
                strike = numbers.pop()
            continue
        if tok in ("at", "@", "rs", "₹", "for", "price", "lots", "hit", "all", "the", "i"):
            continue
        m = _TIME.match(tok)
        if m and (":" in tok or "." in tok and tok.startswith("@")):
            stated_time = f"{int(m.group(1)):02d}:{m.group(2)}"
            continue
        m = _LOTS.match(tok)
        if m:
            lots = int(m.group(1) or m.group(2))
            continue
        m = _CONTRACT.match(tok)
        if m:
            strike, opt_type = float(m.group(1)), m.group(2).upper()
            continue
        m = _NUMBER.match(tok)
        if m:
            value = float(m.group(1))
            if pending_lots and value == int(value):
                lots, pending_lots = int(value), False
            else:
                numbers.append(value)
            continue
        return None   # an unknown word: chat, not a report
    if strike is None and underlying and len(numbers) >= 2:
        # "b NIFTY 22950 120": the strike is the number a strike can be.
        candidates = [n for n in numbers if n >= 1000 and n == int(n)]
        if candidates:
            strike = candidates[0]
            numbers.remove(strike)
    if len(numbers) > 1:
        return None
    price = numbers[0] if numbers else None
    if action is None and price is None:
        return None
    if action in ("SKIP", "UNDO") and (price is not None or lots is not None):
        return None
    if price is not None and not (0.05 <= price <= 100000):
        return None
    if lots is not None and not 1 <= lots <= MAX_LOTS:
        return None
    return ParsedReport(action=action, price=price, lots=lots, stated_time=stated_time,
                        underlying=underlying, strike=strike, opt_type=opt_type)


# ---------------------------------------------------------------------------
# position state and keyboards (pure)
# ---------------------------------------------------------------------------

def position_state(reports: list[dict]) -> dict:
    """Lots bought/sold, average prices and whether they are estimates."""
    active = [r for r in reports if r.get("status") == "ACTIVE"]
    buys = [r for r in active if r["action"] == "BUY"]
    sells = [r for r in active if r["action"] == "SELL"]

    def avg(rows):
        priced = [(r["price"], r.get("lots") or 1) for r in rows if r.get("price") is not None]
        lots = sum(lot for _, lot in priced)
        return round(sum(p * lot for p, lot in priced) / lots, 2) if lots else None

    bought = sum((r.get("lots") or 1) for r in buys)
    sold = sum((r.get("lots") or 0) for r in sells)
    unknown_sell = any(r.get("lots") is None for r in sells)
    open_lots = 0 if unknown_sell else max(bought - sold, 0)
    return {
        "bought_lots": bought, "sold_lots": sold, "open_lots": open_lots,
        "closed": bool(sells) and open_lots == 0,
        "skipped": any(r["action"] == "SKIP" for r in active) and not buys,
        "avg_buy": avg(buys), "avg_sell": avg(sells),
        "buy_estimated": any(r.get("price_basis") in ESTIMATE_BASES for r in buys),
        "sell_estimated": any(r.get("price_basis") in ESTIMATE_BASES for r in sells),
        "reports": len(active),
    }


def _button(text: str, code: str, advisory_id: str) -> dict:
    return {"text": text, "callback_data": f"{CALLBACK_PREFIX}:{code}:{advisory_id}"}


def _price_text(price: Optional[float], estimated: bool) -> str:
    if price is None:
        return "price?"
    value = f"{price:,.2f}".rstrip("0").rstrip(".")
    return f"≈₹{value}" if estimated else f"₹{value}"


def entry_keyboard(advisory_id: str) -> dict:
    return {"inline_keyboard": [
        [_button("✅ Bought 1 lot", "b1", advisory_id), _button("✅ 2 lots", "b2", advisory_id)],
        [_button("⏭ Skipped", "sk", advisory_id)],
    ]}


def exit_keyboard(advisory_id: str) -> dict:
    return {"inline_keyboard": [
        [_button("💰 Sold all", "sa", advisory_id), _button("Sold 1 lot", "s1", advisory_id)],
    ]}


def state_keyboard(advisory_id: str, state: dict, *, is_card: bool) -> dict:
    """The buttons a message should show for the card's recorded state."""
    rows = []
    if state["skipped"]:
        rows.append([_button("⏭ Skipped", "nop", advisory_id)])
        rows.append([_button("↩ Undo", "ud", advisory_id)])
        return {"inline_keyboard": rows}
    if state["bought_lots"] == 0 and state["sold_lots"] == 0 and not state["closed"]:
        return entry_keyboard(advisory_id) if is_card else exit_keyboard(advisory_id)
    if state["closed"]:
        label = (f"✔ Closed {_price_text(state['avg_buy'], state['buy_estimated'])} → "
                 f"{_price_text(state['avg_sell'], state['sell_estimated'])}")
        rows.append([_button(label, "nop", advisory_id)])
    else:
        lots = state["open_lots"]
        rows.append([_button(f"✅ Open {lots} lot{'s' if lots != 1 else ''} "
                             f"{_price_text(state['avg_buy'], state['buy_estimated'])}", "nop", advisory_id)])
        rows.append([_button("💰 Sold all", "sa", advisory_id)] +
                    ([_button("Sold 1 lot", "s1", advisory_id)] if lots >= 2 else []))
    rows.append([_button("↩ Undo last", "ud", advisory_id)])
    return {"inline_keyboard": rows}


def keyboard_for(kind: str, detail: dict) -> Optional[dict]:
    """Buttons for a ledger delivery; ``None`` keeps the message unchanged."""
    if not settings.PARTNER_FILL_CAPTURE_ENABLED:
        return None
    # [O21-PK] Zerodha reads the partner's fills; taps would only add noise.
    from partner_broker_sync import configured as zerodha_configured
    if zerodha_configured() and not settings.PARTNER_FILL_BUTTONS_WITH_ZERODHA:
        return None
    advisory_id = str(detail.get("advisory_id") or "")
    if not _ADVISORY_ID.match(advisory_id):
        return None
    if kind == CARD_KIND:
        return entry_keyboard(advisory_id)
    if kind == UPDATE_KIND and detail.get("event_type") in EXIT_EVENTS:
        return exit_keyboard(advisory_id)
    return None


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def _iso(value: datetime) -> str:
    return value.astimezone(IST).isoformat()


_REPORT_KEYS = [c.strip() for c in _REPORT_COLS.split(",")]


def _row(values: tuple) -> dict:
    return dict(zip(_REPORT_KEYS, values))


async def card_reports(db_path: str, advisory_id: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            f"SELECT {_REPORT_COLS} FROM partner_trade_reports WHERE advisory_id=? "
            "ORDER BY trade_at, report_id", (advisory_id,))).fetchall()
    return [_row(r) for r in rows]


async def reports_between(db_path: str, first_day: str, last_day: str) -> list[dict]:
    await init_partner_fill_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            f"SELECT {_REPORT_COLS} FROM partner_trade_reports "
            "WHERE session_date>=? AND session_date<=? ORDER BY trade_at, report_id",
            (first_day, last_day))).fetchall()
    return [_row(r) for r in rows]


async def insert_report(db_path: str, report: dict) -> Optional[int]:
    """Insert one report; ``None`` when its dedup key was already stored."""
    fields = {key: report.get(key) for key in (
        "dedup_key", "source", "received_at", "trade_at", "trade_at_basis", "action", "advisory_id",
        "session_date", "underlying", "tradingsymbol", "strike", "opt_type", "expiry", "exchange",
        "lots", "lot_size", "price", "price_basis", "quote_bid", "quote_ask", "quote_ltp",
        "corrects_report_id", "raw_text", "message_id", "note")}
    fields["status"] = "ACTIVE"
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            f"INSERT OR IGNORE INTO partner_trade_reports ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})", tuple(fields.values()))
        report_id = cur.lastrowid if cur.rowcount else None
        if report_id and fields.get("corrects_report_id"):
            await db.execute(
                "UPDATE partner_trade_reports SET status='VOIDED', note=? WHERE report_id=? AND status='ACTIVE'",
                (f"corrected by #{report_id}", fields["corrects_report_id"]))
        await db.commit()
    return report_id


async def void_report(db_path: str, report_id: int, note: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "UPDATE partner_trade_reports SET status='VOIDED', note=? WHERE report_id=? AND status='ACTIVE'",
            (note, int(report_id)))
        await db.commit()
        return bool(cur.rowcount)


async def _get_state(db_path: str, key: str) -> Optional[str]:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT value FROM partner_inbox_state WHERE state_key=?", (key,))).fetchone()
    return row[0] if row else None


async def _set_state(db_path: str, key: str, value: str, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO partner_inbox_state(state_key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(state_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, _iso(now)))
        await db.commit()


# ---------------------------------------------------------------------------
# cards and their Telegram messages
# ---------------------------------------------------------------------------

async def load_card(db_path: str, advisory_id: str) -> Optional[dict]:
    """The card's option, lot size and token from its stored payload."""
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT underlying, exchange, payload FROM partner_advisory_ideas WHERE advisory_id=?",
            (advisory_id,))).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row[2])
    except (TypeError, ValueError):
        return None
    view = payload.get("buyer_view") or {}
    buy_leg = next((leg for leg in payload.get("legs") or [] if leg.get("side") == "BUY"), {})
    if not view and not buy_leg:
        return None
    return {
        "advisory_id": advisory_id, "underlying": row[0],
        "session_date": payload.get("session_date"),
        "tradingsymbol": view.get("symbol") or buy_leg.get("tradingsymbol"),
        "strike": view.get("strike") or buy_leg.get("strike"),
        "opt_type": view.get("opt_type") or buy_leg.get("option_type"),
        "expiry": view.get("expiry") or buy_leg.get("expiry"),
        "exchange": view.get("fee_segment") or payload.get("segment") or "NFO",
        "lot_size": int(view.get("lot_size") or buy_leg.get("lot_size") or 0) or None,
        "token": buy_leg.get("instrument_token"),
        "ask": view.get("ask") or buy_leg.get("ask"),
        "tick_size": view.get("tick_size") or buy_leg.get("tick_size") or 0.05,
    }


async def delivered_messages(db_path: str, now: datetime) -> list[dict]:
    """Delivered cards/updates with their Telegram message ids (recent days)."""
    since = _iso(now - timedelta(days=MESSAGE_LOOKBACK_DAYS))
    async with aiosqlite.connect(db_path) as db:
        try:
            rows = await (await db.execute(
                "SELECT kind, dedup_key, sent_at, detail FROM partner_hedge_messages "
                "WHERE kind IN (?,?) AND delivered=1 AND sent_at>=?",
                (CARD_KIND, UPDATE_KIND, since))).fetchall()
        except aiosqlite.OperationalError:
            return []
    out = []
    for kind, key, sent_at, detail_json in rows:
        try:
            detail = json.loads(detail_json or "{}")
        except ValueError:
            continue
        message_id = (detail.get("delivery") or {}).get("message_id")
        if not isinstance(message_id, int):
            continue
        out.append({"kind": kind, "dedup_key": key, "sent_at": sent_at, "message_id": message_id,
                    "advisory_id": detail.get("advisory_id"), "event_type": detail.get("event_type")})
    return out


# ---------------------------------------------------------------------------
# Telegram calls
# ---------------------------------------------------------------------------

def _chat_id():
    return settings.PARTNER_TELEGRAM_CHAT_ID


async def _answer(callback_id: str, text: str) -> None:
    await partner_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})


async def _set_keyboard(message_id: int, markup: dict) -> None:
    await partner_api("editMessageReplyMarkup",
                      {"chat_id": _chat_id(), "message_id": message_id, "reply_markup": markup})


async def _react(message_id: int) -> None:
    await partner_api("setMessageReaction", {
        "chat_id": _chat_id(), "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": "👍"}]})


async def _reply(message_id: int, text: str) -> None:
    await partner_api("sendMessage", {
        "chat_id": _chat_id(), "text": text, "disable_web_page_preview": True,
        "reply_parameters": {"message_id": message_id, "allow_sending_without_reply": True}})


async def refresh_keyboards(db_path: str, advisory_id: str, now: datetime) -> None:
    """Show the recorded state on the card and on its exit updates."""
    state = position_state(await card_reports(db_path, advisory_id))
    for message in await delivered_messages(db_path, now):
        if message["advisory_id"] != advisory_id:
            continue
        if message["kind"] == UPDATE_KIND and message["event_type"] not in EXIT_EVENTS:
            continue
        await _set_keyboard(message["message_id"],
                            state_keyboard(advisory_id, state, is_card=message["kind"] == CARD_KIND))


# ---------------------------------------------------------------------------
# quotes at a tap
# ---------------------------------------------------------------------------

def _market_open(now: datetime) -> bool:
    minute = now.hour * 60 + now.minute
    return now.weekday() < 5 and 9 * 60 + 15 <= minute <= 15 * 60 + 40   # [O24-MC] F&O closes at 15:40


async def quote_at_tap(token, now: datetime) -> Optional[dict]:
    """bid/ask/ltp for one option from one management-lane quote."""
    if not token or not _market_open(now):
        return None
    try:
        import main as _main
        kite = _main.kite
        if not getattr(kite, "access_token", None):
            return None
        timed = getattr(type(kite), "get_quote_with_timing", None)
        if callable(timed):
            quotes, _timing = await asyncio.wait_for(timed(kite, [int(token)], priority="management"), 4.0)
        else:
            quotes = await asyncio.wait_for(kite.get_quote([int(token)]), 4.0)
    except Exception as exc:
        logger.warning("partner_fill_quote_failed err=%s", type(exc).__name__)
        return None
    quote = (quotes or {}).get(int(token)) or (quotes or {}).get(str(token)) or {}
    depth = quote.get("depth") or {}

    def top(side):
        levels = depth.get(side) or []
        price = float(levels[0].get("price") or 0) if levels else 0.0
        return price if price > 0 else None

    ltp = float(quote.get("last_price") or 0) or None
    bid, ask = top("buy"), top("sell")
    if bid is None and ask is None and ltp is None:
        return None
    return {"bid": bid, "ask": ask, "ltp": ltp}


def _estimate(action: str, quote: Optional[dict]) -> tuple[Optional[float], str]:
    if not quote:
        return None, "UNKNOWN"
    if action == "BUY" and quote.get("ask"):
        return quote["ask"], "ASK_AT_TAP"
    if action == "SELL" and quote.get("bid"):
        return quote["bid"], "BID_AT_TAP"
    if quote.get("ltp"):
        return quote["ltp"], "LTP_AT_TAP"
    return None, "UNKNOWN"


# ---------------------------------------------------------------------------
# applying taps and replies
# ---------------------------------------------------------------------------

def _base_report(card: dict, *, dedup_key: str, source: str, now: datetime,
                 trade_at: datetime, trade_at_basis: str, action: str) -> dict:
    return {
        "dedup_key": dedup_key, "source": source, "received_at": _iso(now),
        "trade_at": _iso(trade_at), "trade_at_basis": trade_at_basis, "action": action,
        "advisory_id": card.get("advisory_id"),
        "session_date": card.get("session_date") or trade_at.astimezone(IST).date().isoformat(),
        "underlying": card.get("underlying"), "tradingsymbol": card.get("tradingsymbol"),
        "strike": card.get("strike"), "opt_type": card.get("opt_type"), "expiry": card.get("expiry"),
        "exchange": card.get("exchange"), "lot_size": card.get("lot_size"),
    }


def _recent_same(reports: list[dict], action: str, now: datetime, seconds: int) -> bool:
    for report in reports:
        if report.get("status") != "ACTIVE" or report["action"] != action:
            continue
        try:
            age = (now - datetime.fromisoformat(report["received_at"])).total_seconds()
        except (TypeError, ValueError):
            continue
        if 0 <= age <= seconds:
            return True
    return False


def describe(report: dict) -> str:
    lots = report.get("lots")
    what = {"BUY": "bought", "SELL": "sold", "SKIP": "skipped"}.get(report["action"], report["action"])
    size = f" {lots} lot{'s' if lots != 1 else ''}" if lots else ""
    price = ""
    if report.get("price") is not None:
        price = " " + _price_text(report["price"], report.get("price_basis") in ESTIMATE_BASES)
    return f"{what}{size}{price} at {str(report['trade_at'])[11:16]}"


async def apply_tap(db_path: str, card: dict, code: str, *, dedup_key: str, now: datetime,
                    quote: Optional[dict] = None, quote_fn=None, source: str = "TELEGRAM_BUTTON") -> str:
    """Record one button tap; returns the toast text."""
    reports = await card_reports(db_path, card["advisory_id"])
    state = position_state(reports)
    if code == "nop":
        if state["skipped"]:
            return "Recorded as skipped. Tap Undo to change."
        if state["reports"] == 0:
            return "Nothing recorded yet."
        return (f"Recorded: bought {state['bought_lots']} lot(s) "
                f"{_price_text(state['avg_buy'], state['buy_estimated'])}"
                + (f", sold {_price_text(state['avg_sell'], state['sell_estimated'])}" if state["sold_lots"] else "")
                + ". Reply with a price to correct.")
    if code == "ud":
        active = [r for r in reports if r.get("status") == "ACTIVE"]
        if not active:
            return "Nothing to undo."
        last = max(active, key=lambda r: r["report_id"])
        await void_report(db_path, last["report_id"], "undo")
        return f"Removed: {describe(last)}."
    if code in ("b1", "b2"):
        if _recent_same(reports, "BUY", now, DOUBLE_TAP_SEC):
            return "Already noted."
        action, lots = "BUY", 1 if code == "b1" else 2
    elif code == "sk":
        if state["open_lots"] > 0:
            return f"You have {state['open_lots']} lot(s) open on this card. Tap Sold when you exit."
        if state["skipped"]:
            return "Already noted as skipped."
        action, lots = "SKIP", None
    elif code in ("sa", "s1"):
        if _recent_same(reports, "SELL", now, DOUBLE_TAP_SEC):
            return "Already noted."
        if state["closed"]:
            return "This card is already closed. Tap Undo to change it."
        action = "SELL"
        if state["open_lots"] > 0:
            lots = state["open_lots"] if code == "sa" else 1
        else:
            lots = 1 if code == "s1" else None
    else:
        return "Unknown button."
    report = _base_report(card, dedup_key=dedup_key, source=source, now=now,
                          trade_at=now, trade_at_basis="TAP_TIME", action=action)
    report["lots"] = lots
    price, basis = None, "NONE"
    if action in ("BUY", "SELL"):
        if quote is None and quote_fn is not None:
            quote = await quote_fn(card.get("token"), now)
        price, basis = _estimate(action, quote)
        if quote:
            report.update(quote_bid=quote.get("bid"), quote_ask=quote.get("ask"), quote_ltp=quote.get("ltp"))
    report.update(price=price, price_basis=basis)
    if action == "SELL" and state["bought_lots"] == 0:
        report["note"] = "no buy recorded"
    if await insert_report(db_path, report) is None:
        return "Already noted."
    tail = " Reply to the card with your price to correct." if action in ("BUY", "SELL") else ""
    if action == "SELL" and state["bought_lots"] == 0:
        tail = " Reply to the card with your buy price (e.g. b 518) to score it."
    if action in ("BUY", "SELL") and price is None:
        tail = " Reply to the card with your price (e.g. 518.5)."
    return f"Noted: {describe(report)}.{tail}"


def _stated_trade_at(parsed: ParsedReport, card: dict, reported_at: datetime) -> tuple[datetime, str]:
    if not parsed.stated_time:
        return reported_at, "REPORT_TIME"
    hh, mm = (int(x) for x in parsed.stated_time.split(":"))
    day = card.get("session_date") or reported_at.astimezone(IST).date().isoformat()
    stated = IST.localize(datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00"))
    return stated, "STATED"


def _latest(reports: list[dict], action: str) -> Optional[dict]:
    rows = [r for r in reports if r.get("status") == "ACTIVE" and r["action"] == action]
    return max(rows, key=lambda r: r["report_id"]) if rows else None


async def apply_text(db_path: str, card: dict, parsed: ParsedReport, *, dedup_key: str,
                     reported_at: datetime, now: datetime, raw_text: str, message_id: int,
                     quote_fn=None) -> tuple[bool, str]:
    """Record or correct from a typed reply. Returns (recorded, reason)."""
    reports = await card_reports(db_path, card["advisory_id"]) if card.get("advisory_id") else []
    state = position_state(reports)
    if parsed.action == "UNDO":
        last = max((r for r in reports if r.get("status") == "ACTIVE"), key=lambda r: r["report_id"], default=None)
        if last is None:
            return False, "nothing_to_undo"
        await void_report(db_path, last["report_id"], "undo")
        return True, "undone"
    if parsed.action == "SKIP":
        if state["open_lots"] > 0 or state["skipped"]:
            return False, "skip_conflicts"
        await apply_tap(db_path, card, "sk", dedup_key=dedup_key, now=now, source="TELEGRAM_TEXT")
        return True, "skipped"
    trade_at, basis = _stated_trade_at(parsed, card, reported_at)
    if trade_at > now + timedelta(minutes=1):
        return False, "time_in_future"
    ask = card.get("ask")
    if parsed.price is not None and ask and not (ask / 20 <= parsed.price <= ask * 20):
        return False, "price_far_from_option"
    action = parsed.action
    corrects = None
    last_buy, last_sell = _latest(reports, "BUY"), _latest(reports, "SELL")
    if action is None:
        # A bare price: correct a fresh Bought/Sold tap, else the next leg.
        def fresh_estimate(row):
            if row is None or row.get("price_basis") not in ESTIMATE_BASES + ("UNKNOWN",):
                return False
            age = (now - datetime.fromisoformat(row["received_at"])).total_seconds()
            return age <= CORRECTION_WINDOW_MIN * 60
        if last_sell is not None and fresh_estimate(last_sell):
            action, corrects = "SELL", last_sell
        elif last_buy is not None and fresh_estimate(last_buy) and state["sold_lots"] == 0:
            action, corrects = "BUY", last_buy
        elif state["closed"]:
            return False, "card_closed"
        else:
            action = "SELL" if state["open_lots"] > 0 else "BUY"
    elif parsed.price is not None:
        latest = last_buy if action == "BUY" else last_sell
        if latest is not None and latest.get("price_basis") in ESTIMATE_BASES + ("UNKNOWN",):
            corrects = latest
    report = _base_report(card, dedup_key=dedup_key, source="TELEGRAM_TEXT", now=now,
                          trade_at=trade_at, trade_at_basis=basis, action=action)
    report.update(raw_text=raw_text[:200], message_id=message_id)
    if corrects is not None:
        report["corrects_report_id"] = corrects["report_id"]
        report["lots"] = parsed.lots or corrects.get("lots")
        if not parsed.stated_time:
            report["trade_at"], report["trade_at_basis"] = corrects["trade_at"], corrects["trade_at_basis"]
    elif action == "SELL":
        report["lots"] = parsed.lots or (state["open_lots"] or None)
    else:
        report["lots"] = parsed.lots or 1
    if parsed.price is not None:
        report.update(price=parsed.price, price_basis="PARTNER_STATED")
    else:
        quote = await quote_fn(card.get("token"), now) if quote_fn else None
        price, price_basis = _estimate(action, quote)
        report.update(price=price, price_basis=price_basis)
    if action == "SELL" and state["bought_lots"] == 0 and corrects is None:
        report["note"] = "no buy recorded"
    recorded = await insert_report(db_path, report) is not None
    return recorded, "recorded" if recorded else "duplicate"


def off_card_contract(parsed: ParsedReport, lot_size: Optional[int]) -> Optional[dict]:
    if not (parsed.underlying and parsed.strike and parsed.opt_type):
        return None
    exchange = "BFO" if parsed.underlying == "SENSEX" else "NFO"
    return {"advisory_id": None, "underlying": parsed.underlying, "session_date": None,
            "tradingsymbol": f"{parsed.underlying} {parsed.strike:g} {parsed.opt_type}",
            "strike": parsed.strike, "opt_type": parsed.opt_type, "expiry": None,
            "exchange": exchange, "lot_size": lot_size, "token": None, "ask": None}


def _off_card_lot_size(underlying: str) -> Optional[int]:
    try:
        from fno_underlyings import get_instruments_for
        size = int(get_instruments_for(underlying).lot_size or 0)
        return size or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# the inbound tick
# ---------------------------------------------------------------------------

HELP_TEXT = ("Didn't catch that. Reply to the card with your price (518.5), "
             "'b 518.5 x2', 's 560 @14:42', 'skip' or 'undo'.")
_REASON_TEXT = {
    "price_far_from_option": "That price looks far from this option's. Send it again with b or s if it is right.",
    "time_in_future": "That time is still ahead. Send the time you traded, e.g. @12:10.",
    "card_closed": "This card is already closed. Send 'b 518' or 's 560' to add, or 'undo'.",
    "skip_conflicts": "This card already has an open buy or a skip. Tap Undo to change it.",
    "nothing_to_undo": "Nothing to undo on this card.",
}
_backoff_until: Optional[datetime] = None


def _in_partner_chat(chat: dict) -> bool:
    return str((chat or {}).get("id")) == str(settings.PARTNER_TELEGRAM_CHAT_ID)


async def _help_allowed(db_path: str, now: datetime) -> bool:
    last = await _get_state(db_path, "last_help_at")
    if last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < HELP_COOLDOWN_SEC:
                return False
        except ValueError:
            pass
    await _set_state(db_path, "last_help_at", _iso(now), now)
    return True


async def handle_update(db_path: str, update: dict, now: datetime, *, quote_fn=quote_at_tap) -> str:
    """Apply one Telegram update. Returns a short outcome label for logs."""
    update_id = update.get("update_id")
    callback = update.get("callback_query")
    if callback:
        message = callback.get("message") or {}
        if not _in_partner_chat(message.get("chat")):
            return "foreign_chat"
        # [O24-PW] The trade watch's "Quiet today" button.
        from partner_watch import handle_button as watch_button
        toast = await watch_button(db_path, str(callback.get("data") or ""), now)
        if toast is not None:
            await _answer(callback.get("id", ""), toast)
            return "watch_button"
        parts = str(callback.get("data") or "").split(":")
        if len(parts) != 3 or parts[0] != CALLBACK_PREFIX or not _ADVISORY_ID.match(parts[2]):
            await _answer(callback.get("id", ""), "Unknown button.")
            return "bad_callback"
        card = await load_card(db_path, parts[2])
        if card is None:
            await _answer(callback.get("id", ""), "That card is no longer on record.")
            return "unknown_card"
        toast = await apply_tap(db_path, card, parts[1], dedup_key=f"tg:{update_id}", now=now,
                                quote_fn=quote_fn)
        await _answer(callback.get("id", ""), toast)
        await refresh_keyboards(db_path, card["advisory_id"], now)
        logger.info("partner_fill_tap code=%s advisory=%s outcome=%s", parts[1], parts[2], toast[:60])
        return "tap"
    message = update.get("message")
    if not message:
        return "ignored"
    if not _in_partner_chat(message.get("chat")):
        return "foreign_chat"
    text = str(message.get("text") or "").strip()
    if not text:
        return "ignored"
    reported_at = datetime.fromtimestamp(int(message.get("date") or now.timestamp()), tz=IST)
    # [O24h] "check 22300 pe": the trade watch's plan before a buy; a reply, never a recorded trade.
    from partner_watch import answer_check
    checked = await answer_check(db_path, text, now, key=f"check:{update_id}", asked_at=reported_at)
    if checked != "not_check":
        return checked
    parsed = parse_report_text(text)
    reply_to = (message.get("reply_to_message") or {}).get("message_id")
    card = None
    if reply_to:
        target = next((m for m in await delivered_messages(db_path, now) if m["message_id"] == reply_to), None)
        if target is not None:
            card = await load_card(db_path, str(target["advisory_id"]))
    if card is None and parsed is not None:
        if parsed.underlying and parsed.strike and parsed.opt_type and parsed.action in ("BUY", "SELL"):
            card = off_card_contract(parsed, _off_card_lot_size(parsed.underlying))
    if card is None:
        # Ordinary chat stays unanswered; only a reply to a card or a
        # command-shaped message earns the one-line help.
        if (reply_to and parsed is None) or text.startswith("/"):
            if await _help_allowed(db_path, now):
                await _reply(message.get("message_id"), HELP_TEXT)
            return "help"
        return "ignored"
    if parsed is None:
        if await _help_allowed(db_path, now):
            await _reply(message.get("message_id"), HELP_TEXT)
        return "help"
    recorded, reason = await apply_text(
        db_path, card, parsed, dedup_key=f"tg:{update_id}", reported_at=reported_at, now=now,
        raw_text=text, message_id=int(message.get("message_id") or 0), quote_fn=quote_fn)
    if recorded:
        await _react(message.get("message_id"))
        if card.get("advisory_id"):
            await refresh_keyboards(db_path, card["advisory_id"], now)
    elif reason in _REASON_TEXT and await _help_allowed(db_path, now):
        await _reply(message.get("message_id"), _REASON_TEXT[reason])
    logger.info("partner_fill_text advisory=%s outcome=%s", card.get("advisory_id") or "off_card", reason)
    return reason


async def partner_inbox_tick(now: Optional[datetime] = None) -> dict:
    """Long-poll the partner bot once and apply what arrived."""
    global _backoff_until
    if not (partner_enabled() and settings.PARTNER_FILL_CAPTURE_ENABLED):
        return {"status": "SKIPPED", "reason": "disabled"}
    now = (now or datetime.now(IST)).astimezone(IST)
    minute = now.hour * 60 + now.minute
    if not CAPTURE_START_MIN <= minute <= CAPTURE_END_MIN:
        return {"status": "SKIPPED", "reason": "outside_window"}
    if _backoff_until is not None and now < _backoff_until:
        return {"status": "SKIPPED", "reason": "backoff"}
    db_path = settings.DB_PATH
    await init_partner_fill_db(db_path)
    offset = await _get_state(db_path, "telegram_offset")
    payload = {"timeout": int(settings.PARTNER_INBOX_LONG_POLL_SEC),
               "allowed_updates": ["message", "callback_query"]}
    if offset:
        payload["offset"] = int(offset)
    updates = await partner_api("getUpdates", payload,
                                timeout=float(settings.PARTNER_INBOX_LONG_POLL_SEC) + 10.0)
    if updates is None:
        # 409 (a webhook or another poller) or a network fault: back off so
        # a misconfiguration is one warning per 10 minutes, not every tick.
        _backoff_until = now + timedelta(minutes=10)
        return {"status": "FAILED", "reason": "get_updates_failed"}
    _backoff_until = None
    outcomes: dict = {}
    for update in updates if isinstance(updates, list) else []:
        update_id = update.get("update_id")
        try:
            outcome = await handle_update(db_path, update, datetime.now(IST))
        except Exception as exc:
            logger.error("partner_fill_update_failed update_id=%s err=%s", update_id, type(exc).__name__,
                         exc_info=True)
            outcome = "error"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if isinstance(update_id, int):
            await _set_state(db_path, "telegram_offset", str(update_id + 1), now)
    return {"status": "COMPLETED", "updates": sum(outcomes.values()), "outcomes": outcomes}


async def record_dashboard_report(db_path: str, *, advisory_id: Optional[str], action: str,
                                  price: Optional[float], lots: Optional[int], trade_at: datetime,
                                  note: Optional[str], underlying: Optional[str] = None,
                                  strike: Optional[float] = None, opt_type: Optional[str] = None,
                                  now: Optional[datetime] = None) -> int:
    """Owner-entered report from the dashboard (the partner told them)."""
    from uuid import uuid4
    now = (now or datetime.now(IST)).astimezone(IST)
    if trade_at.tzinfo is None:
        raise ValueError("trade_at must be timezone-aware")
    action = action.upper()
    if action not in ("BUY", "SELL", "SKIP"):
        raise ValueError("action must be BUY, SELL or SKIP")
    if price is not None and not 0.05 <= price <= 100000:
        raise ValueError("price out of range")
    if lots is not None and not 1 <= lots <= MAX_LOTS:
        raise ValueError("lots out of range")
    await init_partner_fill_db(db_path)
    if advisory_id:
        card = await load_card(db_path, advisory_id)
        if card is None:
            raise ValueError("unknown_advisory_id")
    else:
        parsed = ParsedReport(action=action, price=price, lots=lots,
                              underlying=(underlying or "").upper() or None, strike=strike,
                              opt_type=(opt_type or "").upper() or None)
        card = off_card_contract(parsed, _off_card_lot_size(parsed.underlying or ""))
        if card is None:
            raise ValueError("an off-card report needs underlying, strike and opt_type")
    report = _base_report(card, dedup_key=f"dash:{uuid4().hex}", source="DASHBOARD", now=now,
                          trade_at=trade_at, trade_at_basis="STATED", action=action)
    report.update(lots=lots if action != "SKIP" else None, price=price,
                  price_basis="PARTNER_STATED" if price is not None else "UNKNOWN", note=note)
    report_id = await insert_report(db_path, report)
    if report_id is None:
        raise ValueError("duplicate report")
    return report_id
