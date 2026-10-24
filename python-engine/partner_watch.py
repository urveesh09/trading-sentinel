"""[O24-PW 2026-10-24] The partner's trade watch: a companion that only sends messages.

Owner's rule (Oct 24): the watch sends messages and never trades. The
partner follows a message or not. Its first job is cutting the partner's
losses; more profit comes second.

How it runs
  - 09:00 on a trading day: one Telegram message with the partner's Kite
    login button ("Start today's watch"), unless a login is already held.
  - After a login before the close (partner_broker_sync.on_login) the
    partner gets one "watch on" message. Until the 15:40 close, every
    PARTNER_WATCH_POLL_SEC (5 s) the watch reads the partner's order book
    (GET /orders with the partner's own read-only key) and compares it with
    the last read.
  - A restart loses the login (it is kept only in memory). During the
    session the watch then sends one "reconnect" button for each lost login.

[O24c] What is held (``fills_of``, ``trips_from_fills``, ``holdings_of``)
  - Each fill from Zerodha's trade book (GET /trades, read when a fill is
    new), one round trip per exchange, option and product. The part of an
    order the trade book has not shown yet counts as one fill at the order's
    last update.
  - A position carried in from yesterday starts at its overnight quantity;
    today's fills move it from there.
  - Zerodha's positions (GET /portfolio/positions: after a new fill, every
    30 s, and on each tick while they differ) confirm the count. When the
    two differ for longer than a fill can lag (POSITIONS_LAG), the messages
    use Zerodha's number and say so. With no positions read, they say the
    count comes from the orders.

[O24c] What protects it (``cover_of``): FULL / PARTIAL / ABSENT / UNKNOWN
  - Only stops of the holding's own product count (a stop of another
    product would not sell these units). The units they cover are:
    - SL orders waiting (TRIGGER PENDING, or a modify in flight);
    - active GTT stop legs.
  - A stop that fired and has not filled is "exiting": it has its own alarm.
  - GTTs are read only when the SL orders do not cover everything, and
    reused for 20 s.
  - An unreadable GTT list makes the state UNKNOWN: nothing is said, and the
    list is read again on the next tick.

What it sends (live, loss first)
  PLAN      right after a buy fills: the stop that the system's own readings
            give, the loss if it sells there (with charges, against the day's
            cash), the target zone, and three facts: the option's normal
            5-minute swing, its rise in the 15 minutes before the buy, and
            the future's 5-minute trend. Also, when they apply: a buy within
            30 minutes of a losing exit, a bigger size after that loss, and
            from the 5th trade the day's trades and charges.
  ADDED     a new buy order on a trade already open: the new size and
            average, and the loss at the plan stop now and before.
  NO_STOP   120 s after the buy with nothing protecting it.
  PARTIAL   stops cover only part of what is held, for 20 s, 120 s after
            the buy (a stop of another product is named).
  REMOVED   units that were covered are not any more, for 20 s: a stop
            cancelled, a GTT gone, or a stop that sold only part.
  UNFILLED  a stop that fired and still has not sold after 10 s: the
            trigger, the limit, the bid, and what selling at the bid gives.
  LOWERED   a resting stop moved down (modified, or replaced by a lower
            one): the result if it is hit, then and before. Told the first
            time in a trade, and after that only when the move puts the stop
            under the plan's stop or gives up a stop that was guarding the
            buy price. Oct 23 had 20 moves down, 7 of them on one trade; every
            move is still in the evening review.
  REFUSED   Zerodha refused an order: why, in plain words
            (partner_insights.refusal_plain), and whether the trade is still
            open.
  CLOSE     15:20 with an option still held: what the close does to it.
  "Quiet today" (a button on PLAN and NO_STOP) mutes PLAN, ADDED, NO_STOP,
  PARTIAL and CLOSE. LOWERED, REMOVED, UNFILLED and REFUSED always go,
  because those are the moments a loss grows.

[O24c] Every level in a message is checked against the price read just
before it (``level_state``). Kite refuses an SL sell whose trigger is at or
above the last price, so:
  - a plan stop the price is already under is said as that, with what
    selling at the bid would give, never as a stop to place;
  - a target already passed is said as passed;
  - a level that could not be checked says when it was set.

[O24c] Delivery (``_send``): each message has a key, and Telegram's own
answer is kept.
  - A message that provably did not leave is sent again within its useful
    life (LIFETIME_SEC), at most MAX_ATTEMPTS times, each time rebuilt from
    the book read then. "Provably" means: no connection, Telegram's rate
    limit, or a Telegram 5xx.
  - A timeout after the request left may have arrived, so it is not repeated.
  - The broker's event time, the detection time and Telegram's
    acknowledgement time are stored for each message.

[O24c] Timing
  - The tick reads the book and sends the protection alarms first. Each read
    is bounded by READ_TIMEOUT_SEC.
  - The plan's market reads (candles, quotes) run beside the tick within
    PLAN_DEADLINE_SEC; the tick waits at most PLAN_INLINE_SEC for them.
  - A plan that cannot be computed in time says only the premium at risk.

[O24c] Plans (``partner_watch_plan_versions``)
  - A trade's first plan is kept as it was computed (version 1).
  - Each later version (a new buy order, more fills, a partial sale) has its
    reason, quantity and average.
  - A restart loads the plan instead of computing it again.

The plan, computed once per buy (``build_plan``, pure)
  - Stop: the futures level where the trade is wrong, as the F&O engine
    sets it (fno_engine_mom). That is the tighter of:
    - the opposite opening-range edge, once the 09:15-09:45 range is
      complete and on the losing side;
    - 1.5 x ATR(14) of 5-minute futures bars.
    It is priced into the option with Black-76 at the option's own implied
    volatility (fno_chain's time to expiry).
  - When that stop is inside the option's normal 5-minute swing W (the
    median 5-minute high-low of the 30 minutes before the buy), normal moves
    would take it out. The stop is then P - W, and the message says so.
  - Loss at the stop: (P - stop) x qty plus the round trip's charges
    (partner_coach.round_trip_costs), as a share of the day's cash: a fact,
    not a limit. [O24-SZ] The partner sizes as they choose, so the message
    warns only when the money in this buy is much more than they usually put
    in (partner_insights.usual_size over partner_coach.size_history: 1.5 x
    the median share of their last 20 trades, once there are 5). The usual
    is their habit, not a safe size.
  - Target zone: the future at 1.8 R (FNO_TARGET_R), priced the same way.
  - Without market data the plan says only what is known: the premium at
    risk, and "place a stop". It never invents a level.
Market data: the partner's own key when it has it (the paid plan; tried once
a day), else the owner's quotes (management lane) and candles.

Shadow (recorded, not sent)
  - Every 15 s each holding's quote goes into ``partner_watch_looks``, with
    the front future:
    - bid and ask, with their quantities, and the LTP;
    - the exchange's quote and last-trade times, and our receipt time.
  - The judgment messages (protect at a gain, trail, idea broken, target,
    trend, no progress) are scored on recorded days before any of them is
    switched on (owner rule: freeze, then score).

Never: an order, a change or a cancellation (partner_broker_sync's read-only
allowlist), a buy idea, or a prediction.
"""
from __future__ import annotations

import asyncio
import json
import re
import statistics
import time as _time
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Optional

import aiosqlite
import pandas as pd
import pytz
import structlog

import partner_broker_sync as zerodha
from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

OPEN_MIN = 9 * 60 + 15
NO_STOP_AFTER = timedelta(seconds=120)
COVER_GRACE = timedelta(seconds=20)        # a loss of cover is told once it has lasted this long (room to replace)
UNFILLED_AFTER = timedelta(seconds=10)     # a fired stop still unsold this long is told
PLAN_STALE = timedelta(minutes=5)          # a buy older than this when first seen (a restart) gets no PLAN message
LOOK_EVERY = timedelta(seconds=15)
QUOTE_FRESH = timedelta(seconds=15)        # a quote this recent checks a level without a new read
POSITIONS_EVERY = timedelta(seconds=30)
POSITIONS_LAG = timedelta(seconds=10)      # a fill this recent may not be in Zerodha's positions yet
GTT_EVERY = timedelta(seconds=20)
READ_TIMEOUT_SEC = 4.0                     # one read of the partner's book
QUOTE_TIMEOUT_SEC = 3.0
PLAN_DEADLINE_SEC = 25.0                   # the plan's market reads
PLAN_INLINE_SEC = 1.5                      # how long a tick waits for a plan before going on
PLAN_TRIES = 3                             # a plan that failed (not timed out: that is the premium plan) is retried
TICK_BUDGET_SEC = 4.0                      # a longer tick is logged
CLOSE_WARN_MIN = 15 * 60 + 20
SWING_LOOKBACK_MIN = 30
SWING_WINDOW_MIN = 5
SWING_MIN_BARS = 10
RUN_LOOKBACK_MIN = 15
COUNT_FROM_TRADE = 5
FUTURE_BARS_DAYS = 21                      # as the F&O engine (fno_orchestrator.RVOL_FETCH_CALENDAR_DAYS)
TICK = 0.05
QUIET_KEEPS = ("LOWERED", "REMOVED", "UNFILLED", "REFUSED")
ALWAYS_SENT = ("WATCH_ON", "PROMPT", "RECONNECT")
GUARD_TOLERANCE = 0.005                    # a stop within 0.5% under the buy price still guards it
QUIET_PREFIX = "watch"
# Kite states in which an SL order still waits to protect (a modify in flight included).
WAITING = ("TRIGGER PENDING", "MODIFY PENDING", "MODIFY VALIDATION PENDING", "VALIDATION PENDING", "OPEN PENDING",
           "PUT ORDER REQ RECEIVED", "AMO REQ RECEIVED")
COVERED = ("FULL", "PARTIAL")
# How long a message is still worth sending again after a failed send (seconds).
LIFETIME_SEC = {"PLAN": 180, "ADDED": 180, "NO_STOP": 900, "PARTIAL": 900, "REMOVED": 900, "UNFILLED": 120,
                "LOWERED": 120, "REFUSED": 300, "CLOSE": 1200, "WATCH_ON": 600, "PROMPT": 1800, "RECONNECT": 1800}
MAX_ATTEMPTS = 4
RETRY_GAP = timedelta(seconds=10)
SENT, DONE, RETRY, MUTED = "SENT", "DONE", "RETRY", "MUTED"

_DDL = """
CREATE TABLE IF NOT EXISTS partner_watch_messages (
  message_key TEXT PRIMARY KEY,
  session_date TEXT NOT NULL,
  kind TEXT NOT NULL,
  exchange TEXT,
  tradingsymbol TEXT,
  position_key TEXT,
  created_at TEXT NOT NULL,
  sent INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  summary TEXT
);
CREATE INDEX IF NOT EXISTS ix_partner_watch_messages_day ON partner_watch_messages(session_date);
CREATE TABLE IF NOT EXISTS partner_watch_plan_versions (
  position_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  session_date TEXT NOT NULL,
  exchange TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  reason TEXT NOT NULL,
  qty INTEGER NOT NULL,
  entry REAL NOT NULL,
  bought INTEGER NOT NULL,
  sold INTEGER NOT NULL,
  buy_ids TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  PRIMARY KEY (position_key, version)
);
CREATE INDEX IF NOT EXISTS ix_partner_watch_plan_versions_day
  ON partner_watch_plan_versions(session_date, exchange, tradingsymbol);
CREATE TABLE IF NOT EXISTS partner_watch_looks (
  position_key TEXT NOT NULL,
  at TEXT NOT NULL,
  session_date TEXT NOT NULL,
  bid REAL,
  ask REAL,
  ltp REAL,
  fut REAL,
  PRIMARY KEY (position_key, at)
);
CREATE TABLE IF NOT EXISTS partner_watch_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""
# [O24c] Added in place to tables written by O24.
_ADDED_COLS = {
    "partner_watch_messages": (("attempts", "INTEGER NOT NULL DEFAULT 0"), ("outcome", "TEXT"), ("error", "TEXT"),
                               ("event_at", "TEXT"), ("detected_at", "TEXT"), ("last_attempt_at", "TEXT"),
                               ("sent_at", "TEXT"), ("message_id", "INTEGER")),
    "partner_watch_looks": (("bid_qty", "INTEGER"), ("ask_qty", "INTEGER"), ("quote_at", "TEXT"),
                            ("trade_at", "TEXT"), ("received_at", "TEXT")),
}


def enabled() -> bool:
    from partner_bot import partner_enabled
    return bool(settings.PARTNER_WATCH_ENABLED and settings.PARTNER_ZERODHA_SYNC_ENABLED and zerodha.configured()
                and partner_enabled())


_ready: set = set()      # databases whose watch tables exist (the tick runs every 5 s)


async def init_partner_watch_db(db_path: str) -> None:
    if db_path in _ready:
        return
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_DDL)
        for table, cols in _ADDED_COLS.items():
            have = {row[1] for row in await (await db.execute(f"PRAGMA table_info({table})")).fetchall()}
            for name, kind in cols:
                if name not in have:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        await db.commit()
    _ready.add(db_path)


def _dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed.astimezone(IST) if parsed.tzinfo else IST.localize(parsed)


def _px(value: Optional[float]) -> str:
    from partner_coach import _px as coach_px
    return coach_px(value)


def _amt(value: float) -> str:
    from partner_coach import _amt as coach_amt
    return coach_amt(value)


def _signed(value: float) -> str:
    return f"{'−' if value < 0 else '+'}{_amt(value)}"


def _hhmm(at: Optional[datetime]) -> str:
    return at.astimezone(IST).strftime("%H:%M") if at else "--:--"


def _hms(at: Optional[datetime]) -> str:
    return at.astimezone(IST).strftime("%H:%M:%S") if at else "--:--:--"


def _option(symbol: str) -> str:
    parsed = zerodha.parse_option_symbol(symbol)
    if parsed is None:
        return symbol
    return f"{parsed['underlying']} {parsed['strike']:g} {parsed['opt_type']}"


def _future_of(symbol: str) -> str:
    """[O24c] How a futures level is named: the plan's levels come from the front future, not the index."""
    parsed = zerodha.parse_option_symbol(symbol)
    return f"{parsed['underlying']} future" if parsed else "future"


def _floor_tick(value: float) -> float:
    return round(int(value / TICK + 1e-9) * TICK, 2)


def _round_tick(value: float) -> float:
    return round(round(value / TICK) * TICK, 2)


def _result_at(holding, price: float) -> float:
    """The trade's result after charges if all of it sold at ``price`` (``holding``: a Trip or a Holding)."""
    from partner_coach import round_trip_costs
    qty = holding.open_qty
    return round((price - holding.entry) * qty - round_trip_costs(holding.entry, price, qty, holding.exchange), 2)


# ---------------------------------------------------------------------------
# what is held (pure)
# ---------------------------------------------------------------------------

@dataclass
class Fill:
    order_id: str
    exchange: str
    tradingsymbol: str
    product: str
    side: str
    qty: int
    price: float
    at: datetime
    exact: bool         # from Zerodha's trade book; False: the order's unshown part at its last update


@dataclass
class Trip:
    """One round trip on one option and product: from the buy that opened it to the sale that closed it."""
    key: str
    exchange: str
    tradingsymbol: str
    product: str
    first_at: datetime
    bought: int = 0
    sold: int = 0
    buy_value: float = 0.0
    sell_value: float = 0.0
    buy_orders: int = 0
    sell_orders: int = 0
    closed_at: Optional[datetime] = None
    carried: bool = False
    buys: dict = field(default_factory=dict)        # buy order id -> {"qty", "value", "at" (first fill)}, in fill order
    sell_ids: list = field(default_factory=list)
    last_fill_at: Optional[datetime] = None
    exact: bool = True                              # every fill from Zerodha's trade book

    @property
    def position_key(self) -> str:
        return self.key

    @property
    def open_qty(self) -> int:
        return max(self.bought - self.sold, 0)

    @property
    def entry(self) -> Optional[float]:
        return self.buy_value / self.bought if self.bought else None

    @property
    def exit(self) -> Optional[float]:
        return self.sell_value / self.sold if self.sold else None

    def realised(self) -> Optional[float]:
        """Net result of a closed trip after charges."""
        if self.open_qty or not self.sold or self.entry is None or self.exit is None:
            return None
        from partner_coach import round_trip_costs
        qty = min(self.bought, self.sold)
        return round((self.exit - self.entry) * qty - round_trip_costs(
            self.entry, self.exit, qty, self.exchange, orders=self.buy_orders + self.sell_orders), 2)


def _fill_at(row: dict) -> Optional[datetime]:
    return _dt(row.get("updated_at")) or _dt(row.get("placed_at"))


def fills_of(rows: list, trades: Optional[list] = None) -> list:
    """[O24c] Each fill of the day's option orders (``option_orders`` rows),
    oldest first (a buy before a sale in the same second).

    A fill comes from Zerodha's trade book (GET /trades rows) when the book
    has it. The part of an order it has not shown yet is one fill at the
    order's last update, priced so the order's average holds."""
    by_order: dict = {}
    for trade in trades or []:
        by_order.setdefault(str(trade.get("order_id") or ""), []).append(trade)
    fills = []
    for row in rows or []:
        filled = int(row.get("filled_quantity") or 0)
        side = row.get("transaction_type")
        if filled <= 0 or side not in ("BUY", "SELL"):
            continue
        own = []
        for trade in by_order.get(str(row["order_id"]), []):
            qty, price = int(trade.get("quantity") or 0), zerodha._num(trade.get("average_price")) or 0.0
            at = zerodha.kite_time(trade.get("fill_timestamp") or trade.get("exchange_timestamp"))
            if qty > 0 and price > 0 and at is not None:
                own.append((qty, price, at))
        base = {"order_id": str(row["order_id"]), "exchange": row["exchange"], "tradingsymbol": row["tradingsymbol"],
                "product": str(row.get("product") or ""), "side": side}
        for qty, price, at in own:
            fills.append(Fill(**base, qty=qty, price=price, at=at, exact=True))
        rest = filled - sum(q for q, _, _ in own)
        average, at = zerodha._num(row.get("average_price")) or 0.0, _fill_at(row)
        if rest > 0 and average > 0 and at is not None:
            value = average * filled - sum(q * p for q, p, _ in own)
            fills.append(Fill(**base, qty=rest, price=round(value / rest, 4) if value > 0 else average, at=at,
                              exact=False))
    return sorted(fills, key=lambda f: (f.at, 0 if f.side == "BUY" else 1, f.order_id))


def trips_from_fills(fills: list, carried: Optional[list] = None, day: Optional[date] = None) -> list:
    """[O24c] Round trips per exchange, option and product, in fill order.
    ``carried``: positions held from an earlier day (``option_positions``
    rows); each starts at its overnight quantity, at the position's average
    price (Kite gives only that one for the whole position)."""
    trips: list = []
    open_by: dict = {}
    keys: dict = {}
    for item in carried or []:
        qty = int(item.get("overnight_quantity") or 0)
        price = zerodha._num(item.get("average_price")) or 0.0
        if qty <= 0 or price <= 0:
            continue
        key3 = (item["exchange"], item["tradingsymbol"], str(item.get("product") or ""))
        midnight = datetime.combine(day or date.today(), datetime.min.time())
        trip = Trip(key=f"carry:{':'.join(key3)}", exchange=key3[0], tradingsymbol=key3[1], product=key3[2],
                    first_at=IST.localize(midnight + timedelta(minutes=OPEN_MIN)), bought=qty, buy_value=qty * price,
                    buy_orders=1, carried=True)
        trips.append(trip)
        open_by[key3] = trip
    for fill in fills or []:
        key3 = (fill.exchange, fill.tradingsymbol, fill.product)
        trip = open_by.get(key3)
        if fill.side == "BUY":
            if trip is None or not trip.open_qty:
                # The opening buy's order id; a later trip opened by the same order's later fill is "<id>#2".
                keys[fill.order_id] = keys.get(fill.order_id, 0) + 1
                key = fill.order_id if keys[fill.order_id] == 1 else f"{fill.order_id}#{keys[fill.order_id]}"
                trip = Trip(key=key, exchange=fill.exchange, tradingsymbol=fill.tradingsymbol,
                            product=fill.product, first_at=fill.at)
                trips.append(trip)
                open_by[key3] = trip
            trip.bought += fill.qty
            trip.buy_value += fill.qty * fill.price
            if fill.order_id not in trip.buys:
                trip.buys[fill.order_id] = {"qty": 0, "value": 0.0, "at": fill.at}
                trip.buy_orders += 1
            trip.buys[fill.order_id]["qty"] += fill.qty
            trip.buys[fill.order_id]["value"] += fill.qty * fill.price
        elif trip is not None and trip.open_qty:
            take = min(fill.qty, trip.open_qty)
            trip.sold += take
            trip.sell_value += take * fill.price
            if fill.order_id not in trip.sell_ids:
                trip.sell_ids.append(fill.order_id)
                trip.sell_orders += 1
            if not trip.open_qty:
                trip.closed_at = fill.at
        else:
            continue          # a sale with nothing held here: no round trip of this product
        trip.last_fill_at = fill.at
        trip.exact = trip.exact and fill.exact
    return sorted(trips, key=lambda t: t.first_at)


def trips_from_orders(rows: list, carried: Optional[list] = None, day: Optional[date] = None,
                      trades: Optional[list] = None) -> list:
    """Round trips from the day's option orders (and, when read, the trade book's fills)."""
    return trips_from_fills(fills_of(rows, trades), carried, day)


@dataclass
class Holding:
    """[O24c] What is held now in one option and product, and how sure the count is."""
    exchange: str
    tradingsymbol: str
    product: str
    qty: int
    orders_qty: int                  # what today's fills (from the overnight start) give
    broker_qty: Optional[int]        # Zerodha's positions; None: not read
    basis: str                       # CONFIRMED | ZERODHA (they differ: Zerodha's count) | ORDERS (orders only)
    trip: Optional[Trip] = None
    average: Optional[float] = None

    @property
    def hkey(self) -> str:
        return f"{self.exchange}:{self.tradingsymbol}:{self.product}"

    @property
    def position_key(self) -> Optional[str]:
        return self.trip.key if self.trip is not None else None

    @property
    def entry(self) -> Optional[float]:
        return self.average

    @property
    def open_qty(self) -> int:
        return self.qty

    @property
    def first_at(self) -> Optional[datetime]:
        return self.trip.first_at if self.trip is not None else None

    @property
    def carried(self) -> bool:
        return bool(self.trip is not None and self.trip.carried)


def holdings_of(trips: list, positions: Optional[list], positions_at: Optional[datetime] = None) -> list:
    """[O24c] Holdings from the round trips, checked against Zerodha's positions.

    Equal counts are CONFIRMED. A trip whose last fill is newer than the
    positions read (by POSITIONS_LAG) keeps its own count (ORDERS). Any other
    difference uses Zerodha's count (ZERODHA). Without positions every count
    is the orders' (ORDERS)."""
    mine = {(t.exchange, t.tradingsymbol, t.product): t for t in trips if t.open_qty}
    if positions is None:
        return [Holding(*key, qty=t.open_qty, orders_qty=t.open_qty, broker_qty=None, basis="ORDERS", trip=t,
                        average=t.entry) for key, t in mine.items()]
    broker = {(p["exchange"], p["tradingsymbol"], str(p.get("product") or "")): p for p in positions}
    out = []
    for key in sorted(set(mine) | {k for k, p in broker.items() if int(p.get("quantity") or 0) > 0}):
        trip, position = mine.get(key), broker.get(key)
        ours = trip.open_qty if trip is not None else 0
        theirs = int(position.get("quantity") or 0) if position else 0
        if ours == theirs:
            basis, qty = "CONFIRMED", ours
        elif (trip is not None and positions_at is not None and trip.last_fill_at is not None
              and trip.last_fill_at >= positions_at - POSITIONS_LAG):
            basis, qty = "ORDERS", ours
        else:
            basis, qty = "ZERODHA", theirs
        if qty <= 0:
            continue
        average = trip.entry if trip is not None and basis != "ZERODHA" else None
        if average is None:
            average = (zerodha._num(position.get("average_price")) if position else None) or (
                trip.entry if trip is not None else None)
        out.append(Holding(*key, qty=qty, orders_qty=ours, broker_qty=theirs, basis=basis, trip=trip,
                           average=average))
    return out


# ---------------------------------------------------------------------------
# what protects it (pure)
# ---------------------------------------------------------------------------

@dataclass
class Cover:
    state: str                  # FULL | PARTIAL | ABSENT | UNKNOWN (the GTTs could not be read)
    held: int
    covered: int                # units under a waiting stop of this product (at most held)
    exiting: int                # units a fired stop is still trying to sell
    stops: list                 # waiting stops of this product: {"id", "trigger", "units", "kind"}
    other_product: list         # waiting stops that would not sell these units: {"id", "trigger", "units", "product"}
    fired: list                 # fired, unfilled: {"order_id", "trigger", "limit", "pending", "kind"}


def _pending(row: dict) -> int:
    return max(int(row.get("quantity") or 0) - int(row.get("filled_quantity") or 0), 0)


def _same_product(product: Optional[str], holding: Holding) -> bool:
    return not product or str(product).upper() == holding.product


def gtt_legs(gtts: list, holding: Holding) -> tuple[list, list]:
    """The stop legs of the GTTs on this option: (waiting, fired). A GTT stop
    is an OCO's lower leg, or a single trigger set under the price at
    creation (a single one above it is a target). Waiting: active, with the
    leg's units and product. Fired: triggered, with the order it placed."""
    waiting, fired = [], []
    for gtt in gtts or []:
        condition = gtt.get("condition") or {}
        if (str(condition.get("exchange") or "").upper() != holding.exchange
                or str(condition.get("tradingsymbol") or "").upper() != holding.tradingsymbol):
            continue
        triggers = [float(v) for v in condition.get("trigger_values") or [] if v]
        orders = gtt.get("orders") or []
        if not triggers or not orders:
            continue
        if str(gtt.get("type") or "").lower() == "two-leg":
            index = triggers.index(min(triggers))
        else:
            last = float(condition.get("last_price") or 0)
            if not (last and triggers[0] < last):
                continue
            index = 0
        if index >= len(orders) or str(orders[index].get("transaction_type") or "").upper() != "SELL":
            continue
        leg, status = orders[index], str(gtt.get("status") or "").lower()
        units = int(leg.get("quantity") or 0)
        if status == "active" and units > 0:
            waiting.append({"id": f"gtt:{gtt.get('id')}", "trigger": triggers[index], "units": units,
                            "product": str(leg.get("product") or "").upper() or None, "kind": "GTT"})
        elif status == "triggered":
            placed = ((leg.get("result") or {}).get("order_result") or {}).get("order_id")
            if placed:
                fired.append((str(placed), triggers[index]))
    return waiting, fired


def cover_of(holding: Holding, rows: list, gtts: Optional[list]) -> Cover:
    """[O24c] What protects the holding now. ``gtts``: the GTT list, or None
    when it was not read; the GTTs are needed only when the SL orders leave
    units uncovered, and without them that is UNKNOWN."""
    stops, other, fired = [], [], []
    by_id = {str(r["order_id"]): r for r in rows or []}
    for row in rows or []:
        if (row["exchange"] != holding.exchange or row["tradingsymbol"] != holding.tradingsymbol
                or not zerodha.carries_trigger(row)):
            continue
        status, units = str(row.get("status") or "").upper(), _pending(row)
        trigger = zerodha._num(row.get("trigger_price")) or 0.0
        if status in WAITING and units:
            stop = {"id": f"kite:{row['order_id']}", "trigger": trigger, "units": units, "kind": "SL",
                    "product": row.get("product") or None}
            (stops if _same_product(row.get("product"), holding) else other).append(stop)
        elif status == "OPEN" and units and _same_product(row.get("product"), holding):
            fired.append({"order_id": str(row["order_id"]), "trigger": trigger, "limit": zerodha._num(row.get("price")),
                          "pending": units, "kind": "SL"})

    def totals():
        return sum(s["units"] for s in stops), sum(f["pending"] for f in fired)

    covered, exiting = totals()
    if covered + exiting < holding.qty and gtts is not None:
        waiting, gtt_fired = gtt_legs(gtts, holding)
        for leg in waiting:
            (stops if _same_product(leg["product"], holding) else other).append(leg)
        for order_id, trigger in gtt_fired:
            row = by_id.get(order_id)
            if (row is not None and str(row.get("status") or "").upper() == "OPEN" and _pending(row)
                    and _same_product(row.get("product"), holding)
                    and not any(f["order_id"] == order_id for f in fired)):
                fired.append({"order_id": order_id, "trigger": trigger, "limit": zerodha._num(row.get("price")),
                              "pending": _pending(row), "kind": "GTT"})
        covered, exiting = totals()
    covered = min(covered, holding.qty)
    exiting = min(exiting, holding.qty - covered)
    if covered + exiting >= holding.qty:
        state = "FULL"
    elif gtts is None:
        state = "UNKNOWN"
    else:
        state = "PARTIAL" if covered + exiting > 0 else "ABSENT"
    return Cover(state=state, held=holding.qty, covered=covered, exiting=exiting, stops=stops, other_product=other,
                 fired=fired)


# ---------------------------------------------------------------------------
# the plan (pure)
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    entry: float
    qty: int
    stop: Optional[float] = None
    stop_basis: str = "PREMIUM"        # INDEX (the future's level) | SWING | NONE (swing as big as the price) | PREMIUM
    stop_index: Optional[float] = None     # the future's level (named so before O24c)
    index_stop_option: Optional[float] = None
    swing: Optional[float] = None
    loss: Optional[float] = None       # at the stop with charges; the whole premium without a stop
    cash: Optional[float] = None
    loss_pct: Optional[float] = None
    target: Optional[float] = None
    target_index: Optional[float] = None
    run_pct: Optional[float] = None
    run_from: Optional[float] = None
    trend: Optional[str] = None        # WITH | AGAINST
    fut: Optional[float] = None
    atr: Optional[float] = None
    range_edge: Optional[float] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    theta_day: Optional[float] = None  # per unit, per calendar day (negative)
    expiry: Optional[str] = None


def option_swing(bars: list, bought_at: datetime) -> tuple[Optional[float], Optional[float]]:
    """(W, low) from 1-minute bars [(ts naive IST, o, h, l, c)]: W = the
    median high-low of the 5-minute windows in the 30 minutes before the
    buy's minute (None under 10 bars); low = the lowest low in the 15 minutes
    before it, the start of the run to the buy."""
    start = bought_at.astimezone(IST).replace(tzinfo=None, second=0, microsecond=0)
    prior = [b for b in bars if start - timedelta(minutes=SWING_LOOKBACK_MIN) <= b[0] < start]
    swing = None
    if len(prior) >= SWING_MIN_BARS:
        windows = [prior[i:i + SWING_WINDOW_MIN] for i in range(0, len(prior), SWING_WINDOW_MIN)]
        ranges = [max(b[2] for b in w) - min(b[3] for b in w) for w in windows if len(w) == SWING_WINDOW_MIN]
        swing = round(statistics.median(ranges), 2) if ranges else None
    recent = [b for b in bars if start - timedelta(minutes=RUN_LOOKBACK_MIN) <= b[0] < start]
    low = min((b[3] for b in recent), default=None)
    return swing, low if low and low > 0 else None


def build_plan(*, entry: float, qty: int, exchange: str, opt_type: str, strike: float, expiry: Optional[date],
               now: datetime, bought_at: datetime, cash: Optional[float], option_bars: Optional[list],
               fut_bars: Optional[pd.DataFrame], fut_price: Optional[float], option_mid: Optional[float]) -> Plan:
    """The plan for one buy from the system's own readings (see the module doc)."""
    import options_math as om
    from fno_chain import RISK_FREE_RATE, years_to_expiry
    from fno_engine_mom import SESSION_OPEN_MIN, wilder_atr
    from partner_coach import round_trip_costs
    plan = Plan(entry=entry, qty=qty, cash=cash, expiry=expiry.isoformat() if expiry else None)
    is_call = opt_type == "CE"
    if option_bars:
        plan.swing, low = option_swing(option_bars, bought_at)
        if low:
            plan.run_from, plan.run_pct = low, round((entry - low) / low, 4)
    naive_now = now.astimezone(IST).replace(tzinfo=None)
    closed = None
    if fut_bars is not None and not fut_bars.empty:
        closed = fut_bars[fut_bars.index + timedelta(minutes=5) <= naive_now]
    if closed is not None and len(closed):
        plan.atr = wilder_atr(closed, settings.FNO_ATR_LEN)
        if len(closed) > settings.FNO_EMA_SLOW:
            fast = float(closed["close"].ewm(span=settings.FNO_EMA_FAST, adjust=False).mean().iloc[-1])
            slow = float(closed["close"].ewm(span=settings.FNO_EMA_SLOW, adjust=False).mean().iloc[-1])
            rising = fast > slow
            plan.trend = "WITH" if rising == is_call else "AGAINST"
        today = [t for t in closed.index if t.date() == naive_now.date()]
        or_end = SESSION_OPEN_MIN + settings.FNO_OR_MINUTES
        or_rows = closed.loc[[t for t in today if SESSION_OPEN_MIN <= t.hour * 60 + t.minute < or_end]]
        complete = len(or_rows) >= settings.FNO_OR_MINUTES // 5
        plan.fut = float(fut_price) if fut_price else float(closed["close"].iloc[-1])
        if complete:
            edge = float(or_rows["low"].min()) if is_call else float(or_rows["high"].max())
            if (is_call and edge < plan.fut) or (not is_call and edge > plan.fut):
                plan.range_edge = edge
    price_now = option_mid or entry
    if plan.fut and plan.atr and expiry is not None:
        years = years_to_expiry(expiry, now.astimezone(IST))
        plan.iv = om.implied_vol(price_now, plan.fut, strike, years, RISK_FREE_RATE, is_call) if years > 0 else None
        if plan.iv:
            plan.delta = round(om.delta(plan.fut, strike, years, plan.iv, RISK_FREE_RATE, is_call), 3)
            plan.theta_day = round(om.theta(plan.fut, strike, years, plan.iv, RISK_FREE_RATE, is_call), 2)
            room = settings.FNO_STOP_ATR_MULT * plan.atr
            vol_stop = plan.fut - room if is_call else plan.fut + room
            if plan.range_edge is not None:
                index_stop = max(plan.range_edge, vol_stop) if is_call else min(plan.range_edge, vol_stop)
            else:
                index_stop = vol_stop
            r_points = abs(plan.fut - index_stop)
            target_index = plan.fut + settings.FNO_TARGET_R * r_points * (1 if is_call else -1)
            plan.stop_index, plan.target_index = round(index_stop, 1), round(target_index, 1)
            plan.index_stop_option = _floor_tick(om.black76_price(index_stop, strike, years, plan.iv, RISK_FREE_RATE,
                                                                  is_call))
            plan.target = _round_tick(om.black76_price(target_index, strike, years, plan.iv, RISK_FREE_RATE, is_call))
            if plan.index_stop_option < entry:      # a jump since the fill can price it above the buy: no stop then
                plan.stop, plan.stop_basis = plan.index_stop_option, "INDEX"
    if plan.swing and (plan.stop is None or entry - plan.stop < plan.swing):
        # The futures stop is inside the option's normal swing (or the future could not be read).
        plan.stop, plan.stop_basis = _floor_tick(entry - plan.swing), "SWING"
    if plan.stop is not None and plan.stop < TICK:
        plan.stop, plan.stop_basis = None, ("NONE" if plan.swing else "PREMIUM")
    if plan.stop is not None:
        plan.loss = round((entry - plan.stop) * qty + round_trip_costs(entry, plan.stop, qty, exchange), 2)
    else:
        plan.loss = round(entry * qty, 2)
    if cash:
        plan.loss_pct = round(plan.loss / cash, 4)
    return plan


def revised(plan: Plan, *, entry: float, qty: int, exchange: str) -> Plan:
    """[O24c] The same plan levels for a new size and average: the loss at the stop moves with them."""
    from partner_coach import round_trip_costs
    out = replace(plan, entry=entry, qty=qty)
    if plan.stop is not None:
        out.loss = round((entry - plan.stop) * qty + round_trip_costs(entry, plan.stop, qty, exchange), 2)
    else:
        out.loss = round(entry * qty, 2)
    out.loss_pct = round(out.loss / plan.cash, 4) if plan.cash else None
    return out


def level_state(level: Optional[float], quote: Optional[dict]) -> str:
    """[O24c] A plan stop against the last price: VALID (an SL sell can be
    placed there: Kite needs the trigger under the last price), CROSSED (the
    price is at or under it), UNCHECKED (no price read), NONE (no stop)."""
    if level is None:
        return "NONE"
    ltp = (quote or {}).get("ltp")
    if not ltp:
        return "UNCHECKED"
    return "CROSSED" if ltp <= level + 1e-9 else "VALID"


def _exit_price(quote: Optional[dict]) -> Optional[float]:
    """What selling now would get: the best bid, else the last price."""
    return (quote or {}).get("bid") or (quote or {}).get("ltp")


# ---------------------------------------------------------------------------
# message texts (pure)
# ---------------------------------------------------------------------------

def _share(loss: Optional[float], cash: Optional[float]) -> str:
    return f", {loss / cash:.0%} of your cash" if loss is not None and cash else ""


def _sell_now(holding, quote: Optional[dict], cash: Optional[float] = None) -> str:
    price = _exit_price(quote)
    if not price or holding.entry is None:
        return ""
    result = _result_at(holding, price)
    where = "at the bid" if (quote or {}).get("bid") else "at the last price"
    share = _share(-result, cash) if result < 0 else ""
    return f" Selling {where} {_px(price)} now: about {_signed(result)} with charges{share}."


def plan_text(trip, plan: Plan, *, lots: Optional[int], after_loss: Optional[dict] = None,
              day_line: Optional[str] = None, usual: Optional[float] = None, quote: Optional[dict] = None) -> str:
    """The PLAN message. ``quote``: the option's price read just before
    sending; a stop the price is already under is never offered as a stop."""
    from partner_insights import USUAL_SIZE_MULT
    name = _option(trip.tradingsymbol)
    future = _future_of(trip.tradingsymbol)
    size = f"{lots} lot{'s' if lots != 1 else ''} ({plan.qty})" if lots else f"{plan.qty}"
    lines = [f"🟢 You bought {name} · {size} at {_px(plan.entry)}"]
    share = _share(plan.loss, plan.cash)
    stop_now = level_state(plan.stop, quote)
    if stop_now == "CROSSED":
        lines.append(f"🛑 The price ({_px(quote['ltp'])}) is already under the plan stop {_px(plan.stop)}, the level "
                     f"where this trade is wrong.{_sell_now(trip, quote, plan.cash)}")
    elif plan.stop_basis == "INDEX":
        lines.append(f"🛑 Plan stop {_px(plan.stop)} ({future} {plan.stop_index:,.0f}). If it sells there: about "
                     f"−{_amt(plan.loss)} with charges{share}.")
    elif plan.stop_basis == "SWING":
        inside = (f"The futures stop ({plan.stop_index:,.0f} → {_px(plan.index_stop_option)}) sits inside that "
                  f"swing. " if plan.stop_index is not None and plan.index_stop_option is not None else "")
        lines.append(f"🛑 Plan stop {_px(plan.stop)}: one normal 5-minute swing ({_px(plan.swing)}) under your "
                     f"price. {inside}If it sells there: about −{_amt(plan.loss)} with charges{share}.")
    elif plan.stop_basis == "NONE":
        lines.append(f"🛑 This option's normal 5-minute swing ({_px(plan.swing)}) is as big as its price: any stop "
                     f"sits inside the noise. At risk: the whole {_amt(plan.loss)}{share}.")
    else:
        lines.append(f"🛑 At risk: the whole {_amt(plan.loss)} you paid{share}. Decide your stop and place it now.")
    paid = plan.entry * plan.qty
    if usual and plan.cash and paid / plan.cash > USUAL_SIZE_MULT * usual:
        lines.append(f"⚠️ {_amt(paid)} in this trade, {paid / plan.cash:.0%} of your cash: much bigger than your "
                     f"usual {usual:.0%}.")
    if plan.target is not None and plan.target_index is not None:
        ltp = (quote or {}).get("ltp")
        if ltp and ltp >= plan.target:
            lines.append(f"🎯 Already above the target zone {_px(plan.target)} (price {_px(ltp)}).")
        else:
            lines.append(f"🎯 Target zone {_px(plan.target)} ({future} {plan.target_index:,.0f}).")
    facts = []
    if plan.stop_basis in ("INDEX", "SWING") and plan.swing:
        facts.append(f"normal 5-min swing {_px(plan.swing)}")
    if plan.run_pct is not None and plan.run_from:
        facts.append(f"up {plan.run_pct:.0%} in the 15 min before you bought (from {_px(plan.run_from)})"
                     if plan.run_pct >= 0 else
                     f"down {abs(plan.run_pct):.0%} in the 15 min before you bought")
    if plan.trend:
        facts.append(f"the {future}'s 5-min trend is with you" if plan.trend == "WITH" else
                     f"the {future}'s 5-min trend is against you")
    if facts:
        lines.append("• " + "; ".join(facts) + ".")
    if after_loss:
        line = (f"⚠️ Your last trade closed −{_amt(after_loss['loss'])} at {after_loss['at']}, "
                f"{after_loss['minutes']} min before this buy.")
        if after_loss.get("bigger"):
            line += f" This is {after_loss['bigger']}."
        lines.append(line)
    if day_line:
        lines.append(day_line)
    if plan.stop is not None and stop_now != "CROSSED":
        lines.append(f"Place an SL sell now: trigger {_px(plan.stop)}, limit a little under it. In a fast fall an SL "
                     f"order can trigger and still not fill.")
    return "\n".join(lines)


def plan_summary(plan: Plan, quote: Optional[dict] = None) -> str:
    if level_state(plan.stop, quote) == "CROSSED":
        return f"the price was already under the plan stop {_px(plan.stop)}"
    if plan.stop is not None:
        return f"plan stop {_px(plan.stop)}, loss if it sells there about −{_amt(plan.loss)}"
    return f"at risk: the whole {_amt(plan.loss)}"


def _count_note(holding) -> str:
    """[O24c] Where the count comes from when Zerodha's positions do not confirm it ("" when they do)."""
    if getattr(holding, "basis", "CONFIRMED") == "ZERODHA":
        return (f" Zerodha's positions show {holding.qty} held; your orders today give {holding.orders_qty}, so the "
                f"count is Zerodha's.")
    if getattr(holding, "basis", "CONFIRMED") == "ORDERS" and getattr(holding, "broker_qty", 0) is None:
        return " The count is from your orders: Zerodha's positions could not be read."
    return ""


def plan_stop_line(holding, plan: Optional[Plan], quote: Optional[dict], *, set_at: Optional[datetime] = None) -> str:
    """[O24c] The plan stop for the units held now, checked against the price
    just read; "" without a plan stop."""
    if plan is None or plan.stop is None or holding.entry is None:
        return ""
    state = level_state(plan.stop, quote)
    read = f" at {_hms(quote['looked_at'])}" if quote and quote.get("looked_at") else ""
    if state == "CROSSED":
        return (f" The price ({_px(quote['ltp'])}{read}) is already under the plan stop {_px(plan.stop)}."
                f"{_sell_now(holding, quote, plan.cash)}")
    loss = -_result_at(holding, plan.stop)
    if state == "VALID":
        return (f" Plan stop {_px(plan.stop)} (price {_px(quote['ltp'])}{read}); if it sells there, about "
                f"−{_amt(loss)} with charges.")
    since = f"set at {_hhmm(set_at)}; " if set_at else ""
    return (f" Plan stop {_px(plan.stop)} ({since}the price could not be read now); if it sells there, about "
            f"−{_amt(loss)} with charges.")


def _product_note(cover: Optional[Cover], holding) -> str:
    if cover is None or not cover.other_product:
        return ""
    stop = cover.other_product[0]
    return (f" Your stop for {stop['units']} is {stop.get('product') or 'another product'} and these are "
            f"{holding.product}: it would not sell them.")


def no_stop_text(holding, plan: Optional[Plan], quote: Optional[dict] = None, cover: Optional[Cover] = None,
                 set_at: Optional[datetime] = None) -> str:
    when = "held from yesterday" if holding.carried else (
        f"bought {_hhmm(holding.first_at)}" if holding.first_at else "held")
    line = f"⏰ {_option(holding.tradingsymbol)} ({holding.open_qty}): no stop order yet ({when})."
    return line + _count_note(holding) + _product_note(cover, holding) + plan_stop_line(holding, plan, quote,
                                                                                       set_at=set_at)


def partial_text(holding, cover: Cover, plan: Optional[Plan], quote: Optional[dict] = None,
                 set_at: Optional[datetime] = None) -> str:
    protected = cover.covered + cover.exiting
    line = (f"⚠️ {_option(holding.tradingsymbol)}: protection incomplete. A stop covers {protected} of your "
            f"{cover.held}; the other {cover.held - protected} have none.")
    return line + _count_note(holding) + _product_note(cover, holding) + plan_stop_line(holding, plan, quote,
                                                                                       set_at=set_at)


def lowered_reason(trip, old: float, new: float, plan: Optional[Plan], first: bool) -> Optional[str]:
    """Why a stop moved down is worth a message now: FIRST in this trade,
    BELOW_PLAN (under the plan's stop), GUARD (it guarded the buy price and
    no longer does); None: still within the plan, already told once."""
    entry = trip.entry or 0.0
    guard = entry * (1 - GUARD_TOLERANCE)
    if entry and old >= guard > new:
        return "GUARD"
    if plan is not None and plan.stop is not None and new < plan.stop - 1e-9:
        return "BELOW_PLAN"
    return "FIRST" if first else None


def lowered_text(trip, old: float, new: float, reason: str = "FIRST", plan: Optional[Plan] = None) -> str:
    before, after = _result_at(trip, old), _result_at(trip, new)
    line = (f"⚠️ {_option(trip.tradingsymbol)}: you moved your stop down {_px(old)} → {_px(new)}. If it is hit: "
            f"{_signed(after)} instead of {_signed(before)}.")
    if reason == "GUARD":
        line += " It was guarding your buy price; now this trade can end in a loss."
    elif reason == "BELOW_PLAN" and plan is not None and plan.stop is not None:
        line += f" That is under your plan stop {_px(plan.stop)}: the loss can now be bigger than planned."
    else:
        line += " A stop moved down adds to the loss you chose when you placed it."
    return line


def removed_text(holding, why: dict, plan: Optional[Plan], quote: Optional[dict] = None,
                 set_at: Optional[datetime] = None) -> str:
    """[O24c] Units that had a stop and no longer have one. ``why``: {"kind":
    CANCELLED | SOLD | GTT_GONE | GONE, "trigger", "sold"}."""
    name, trigger = _option(holding.tradingsymbol), why.get("trigger")
    kind = why.get("kind")
    if kind == "SOLD":
        line = (f"⚠️ {name}: your stop at {_px(trigger)} sold {why.get('sold')}; the {holding.open_qty} still held "
                f"have no stop.")
    elif kind == "GTT_GONE":
        line = (f"⚠️ {name}: your GTT at {_px(trigger)} is no longer active and no other stop is in Zerodha. "
                f"Nothing limits this trade's loss now.")
    elif kind == "CANCELLED":
        line = (f"⚠️ {name}: your stop at {_px(trigger)} is cancelled and no other stop is in Zerodha. Nothing "
                f"limits this trade's loss now.")
    else:
        line = (f"⚠️ {name}: your stop at {_px(trigger)} is no longer waiting and no other stop is in Zerodha. "
                f"Nothing limits this trade's loss now.")
    return line + _count_note(holding) + plan_stop_line(holding, plan, quote, set_at=set_at)


def unfilled_text(holding, fired: dict, quote: Optional[dict] = None) -> str:
    """[O24c] A stop that fired and has not sold: the price is under its limit."""
    what = "GTT" if fired.get("kind") == "GTT" else "stop"
    limit = fired.get("limit")
    line = (f"🚨 {_option(holding.tradingsymbol)}: your {what} triggered at {_px(fired['trigger'])}, but its sell "
            f"order{f' (limit {_px(limit)})' if limit else ''} has not filled: {fired['pending']} of "
            f"{holding.open_qty} still to sell.")
    bid = (quote or {}).get("bid")
    if bid and limit and bid < limit:
        line += (f" The bid is {_px(bid)}, under your limit: it sells only at {_px(limit)} or better."
                 f"{_sell_now(holding, quote)} To sell now, the limit has to come down to the bid.")
    elif bid:
        line += f" The bid is {_px(bid)}."
    else:
        line += " The price could not be read now."
    return line


def added_text(holding, *, added: int, added_px: float, first_px: Optional[float], plan: Optional[Plan],
               loss_before: Optional[float], quote: Optional[dict] = None) -> str:
    """[O24c] A new buy order on an open trade: the new size and what the plan stop now costs."""
    under = (f", under your first buy at {_px(first_px)}" if first_px and added_px < first_px - 1e-9 else "")
    line = (f"➕ You added {added} to {_option(holding.tradingsymbol)} at {_px(added_px)}{under}: now "
            f"{holding.open_qty} at {_px(holding.entry)}.{_count_note(holding)}")
    if plan is None or plan.stop is None:
        paid = (holding.entry or 0.0) * holding.open_qty
        line += f" At risk now: the whole {_amt(paid)}" + (f" (it was {_amt(loss_before)})." if loss_before else ".")
        return line
    if level_state(plan.stop, quote) == "CROSSED":
        return line + plan_stop_line(holding, plan, quote)
    loss = -_result_at(holding, plan.stop)
    line += f" If the plan stop {_px(plan.stop)} sells: about −{_amt(loss)} with charges"
    line += f" (it was −{_amt(loss_before)})." if loss_before is not None else "."
    if under:
        line += " Buying more of a falling option makes the loss at the stop bigger."
    return line


def refused_text(row: dict, rows: list, still_open: Optional[int]) -> str:
    from partner_insights import refusal_plain
    side = "buy" if row["transaction_type"] == "BUY" else "sell"
    why = refusal_plain(row, rows) or (row.get("status_message") or "no reason given").strip()
    line = f"❗ Zerodha refused your {side} order on {_option(row['tradingsymbol'])}: {why}"
    if not line.endswith("."):
        line += "."
    if side == "sell" and still_open:
        line += f" The trade ({still_open}) is still open."
    return line


def close_text(trip, *, expiry_today: bool, theta_day: Optional[float]) -> str:
    from partner_broker_sync import CLOSE_MIN
    close = f"{CLOSE_MIN // 60}:{CLOSE_MIN % 60:02d}"
    line = (f"⏳ 20 minutes to the {close} close and you still hold {_option(trip.tradingsymbol)} "
            f"({trip.open_qty}).")
    if expiry_today:
        line += (" It expires today: after the close it is settled in cash at its in-the-money value, "
                 "and an option out of the money ends at zero.")
    elif trip.product == "MIS":
        line += " As MIS, Zerodha squares it off near the close and charges for it."
    else:
        line += " As NRML it stays open overnight"
        line += (f": time decay is about {_amt(abs(theta_day) * trip.open_qty)} a day on it." if theta_day else ".")
    return line


WATCH_ON_TEXT = ("✅ Trade watch on until {close}. I'll message you when a buy has no stop or only part of it is "
                 "covered, when a stop is moved down or cancelled, when a stop fires and does not sell, when "
                 "Zerodha refuses an order, and before the close. Messages only: nothing is ever placed, changed "
                 "or cancelled for you.")
PROMPT_TEXT = ("🌅 Good morning. Log in to Zerodha to switch on today's trade watch: I'll message you when a buy "
               "has no stop, when a stop is moved down, cancelled or does not sell, and when Zerodha refuses an "
               "order. Messages only: nothing is ever placed for you.")
RECONNECT_TEXT = ("🔌 The trade watch stopped (the system restarted) and needs your Zerodha login again. "
                  "Your orders are untouched.")
QUIET_TOAST = ("Quiet for today. You will still hear when a stop is moved down, cancelled or does not sell, or "
               "Zerodha refuses an order.")


def quiet_keyboard(day: str) -> dict:
    data = f"{QUIET_PREFIX}:quiet:{day.replace('-', '')}"
    return {"inline_keyboard": [[{"text": "🔕 Quiet today", "callback_data": data}]]}


def login_keyboard(label: str) -> Optional[dict]:
    return zerodha.review_keyboard(label)


# ---------------------------------------------------------------------------
# market data: the partner's key when it has it, else the owner's
# ---------------------------------------------------------------------------

class Market:
    """Quotes and candles for the watch (injected in tests)."""

    def __init__(self) -> None:
        self.partner_ok: Optional[bool] = None     # None: not tried today
        self.day: Optional[str] = None

    def roll(self, day: str) -> None:
        if day != self.day:
            self.day, self.partner_ok = day, None

    async def _partner(self, path: str, params: dict):
        if self.partner_ok is False:
            return None
        try:
            data = await zerodha._read(path, params=params)
        except zerodha.BrokerError as exc:
            if exc.code in ("PermissionException", "http_403", "InputException"):
                logger.info("partner_watch_partner_market_data_unavailable code=%s", exc.code)
                self.partner_ok = False
                return None
            raise
        self.partner_ok = True
        return data

    async def quote(self, contracts: list) -> dict:
        """{tradingsymbol: {"bid", "ask", "ltp", "bid_qty", "ask_qty", "quote_at", "trade_at", "received_at"}}."""
        out: dict = {}
        names = {f"{c.segment}:{c.tradingsymbol}": c for c in contracts}
        try:
            data = await self._partner("/quote", {"i": list(names)})
        except zerodha.BrokerError as exc:
            logger.warning("partner_watch_quote_failed source=partner code=%s", exc.code)
            data = None
        if data:
            received = datetime.now(IST)
            for name, quote in (data or {}).items():
                if name in names:
                    out[names[name].tradingsymbol] = _top(quote, received)
            return out
        try:
            import main as _main
            kite = _main.kite
            if not getattr(kite, "access_token", None):
                return out
            quotes, _timing = await kite.get_quote_with_timing([c.token for c in contracts], priority="management")
        except Exception as exc:
            logger.warning("partner_watch_quote_failed source=owner err=%s", type(exc).__name__)
            return out
        received = datetime.now(IST)
        for contract in contracts:
            quote = (quotes or {}).get(int(contract.token)) or (quotes or {}).get(str(contract.token))
            if quote:
                out[contract.tradingsymbol] = _top(quote, received)
        return out

    async def candles(self, contract, interval: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        """Candles indexed by naive IST bar start (open, high, low, close, volume)."""
        fmt = "%Y-%m-%d %H:%M:%S"
        start_s, end_s = start.astimezone(IST).strftime(fmt), end.astimezone(IST).strftime(fmt)
        try:
            data = await self._partner(f"/instruments/historical/{int(contract.token)}/{interval}",
                                       {"from": start_s, "to": end_s})
        except zerodha.BrokerError as exc:
            logger.warning("partner_watch_candles_failed source=partner code=%s", exc.code)
            data = None
        if data and data.get("candles"):
            frame = pd.DataFrame([row[:6] for row in data["candles"]],
                                 columns=["ts", "open", "high", "low", "close", "volume"])
            stamps = pd.to_datetime(frame.pop("ts"))
            if stamps.dt.tz is not None:
                stamps = stamps.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            frame.index = stamps
            return frame.astype(float)
        try:
            import main as _main
            frame = await _main.kite.get_intraday_by_token(int(contract.token), start_s, end_s, interval=interval)
        except Exception as exc:
            logger.warning("partner_watch_candles_failed source=owner err=%s", type(exc).__name__)
            return None
        if frame is None or frame.empty:
            return None
        frame = frame.copy()
        index = pd.DatetimeIndex(frame.index)
        if index.tz is not None:
            index = index.tz_convert("Asia/Kolkata").tz_localize(None)
        frame.index = index
        return frame


def _stamp(value) -> Optional[str]:
    if isinstance(value, datetime):
        return (value.astimezone(IST) if value.tzinfo else IST.localize(value)).isoformat()
    parsed = zerodha.kite_time(value) if value else None
    return parsed.isoformat() if parsed else None


def _top(quote: dict, received: Optional[datetime] = None) -> dict:
    """[O24c] Best bid and ask with their quantities, the LTP, the exchange's
    quote and last-trade times, and when we received it."""
    depth = quote.get("depth") or {}

    def best(side):
        levels = depth.get(side) or []
        price = float(levels[0].get("price") or 0) if levels else 0.0
        qty = int(levels[0].get("quantity") or 0) if levels else 0
        return (price, qty) if price > 0 else (None, None)

    bid, bid_qty = best("buy")
    ask, ask_qty = best("sell")
    return {"bid": bid, "ask": ask, "ltp": float(quote.get("last_price") or 0) or None, "bid_qty": bid_qty,
            "ask_qty": ask_qty, "quote_at": _stamp(quote.get("timestamp")),
            "trade_at": _stamp(quote.get("last_trade_time")),
            "received_at": (received or datetime.now(IST)).isoformat()}


def _mid(quote: Optional[dict]) -> Optional[float]:
    if not quote:
        return None
    if quote.get("bid") and quote.get("ask"):
        return (quote["bid"] + quote["ask"]) / 2
    return quote.get("ltp")


def contract_of(exchange: str, symbol: str):
    """The option's contract from the morning books, with its segment."""
    try:
        from fno_underlyings import SPECS, get_instruments_for
        for name, spec in SPECS.items():
            if spec.segment != exchange:
                continue
            contract = get_instruments_for(name).by_symbol.get(symbol)
            if contract is not None:
                return _Contract(contract, spec.segment, get_instruments_for(name))
    except Exception as exc:
        logger.warning("partner_watch_book_lookup_failed err=%s", type(exc).__name__)
    return None


class _Contract:
    """A book contract with its segment (quote names are SEGMENT:SYMBOL)."""

    def __init__(self, contract, segment: str, book) -> None:
        self._c, self.segment, self.book = contract, segment, book

    def __getattr__(self, name):
        return getattr(self._c, name)

    def front_future(self, today: date) -> Optional["_Contract"]:
        future = self.book.front_future(today)
        return _Contract(future, self.segment, self.book) if future is not None else None


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def _retryable(state: Optional[str], error: Optional[str]) -> bool:
    """[O24c] Provably not delivered, so safe to send again: no connection was
    made, Telegram's rate limit, or a Telegram 5xx. A timeout after the
    request left may have arrived."""
    if state in ("unsent_connect", "rate_limited"):
        return True
    return state == "rejected" and bool(re.fullmatch(r"telegram_http_5\d\d", str(error or "")))


def _who(subject) -> tuple:
    if subject is None:
        return None, None, None
    return subject.exchange, subject.tradingsymbol, getattr(subject, "position_key", None)


async def _get_state(db_path: str, key: str) -> Optional[str]:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT value FROM partner_watch_state WHERE key=?", (key,))).fetchone()
    return row[0] if row else None


async def _set_state(db_path: str, key: str, value: str, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO partner_watch_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO "
                         "UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                         (key, value, now.isoformat()))
        await db.commit()


async def quiet(db_path: str, day: str) -> bool:
    await init_partner_watch_db(db_path)
    return (await _get_state(db_path, f"quiet:{day}")) == "1"


async def _send(db_path: str, key: str, day: str, kind: str, subject, text: str, now: datetime, *,
                summary: Optional[str] = None, keyboard: Optional[dict] = None,
                event_at: Optional[datetime] = None) -> str:
    """[O24c] Send one message once: SENT, DONE (sent before, or it failed in
    a way not worth repeating), RETRY (provably unsent; call again with fresh
    text) or MUTED (quiet today)."""
    if key in _state.final_keys:
        return DONE
    if kind not in QUIET_KEEPS and kind not in ALWAYS_SENT and await quiet(db_path, day):
        _state.final_keys.add(key)    # quiet lasts the day
        return MUTED
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT sent, outcome, error, attempts, created_at, last_attempt_at FROM partner_watch_messages "
            "WHERE message_key=?", (key,))).fetchone()
        if row is None:
            exchange, symbol, position = _who(subject)
            await db.execute(
                "INSERT INTO partner_watch_messages(message_key,session_date,kind,exchange,tradingsymbol,position_key,"
                "created_at,sent,text,summary,attempts,outcome,event_at,detected_at,last_attempt_at) "
                "VALUES(?,?,?,?,?,?,?,0,?,?,1,'attempting',?,?,?)",
                (key, day, kind, exchange, symbol, position, now.isoformat(), text, summary,
                 event_at.isoformat() if event_at else None, now.isoformat(), now.isoformat()))
        else:
            sent, outcome, error, attempts, created, last = row
            life = timedelta(seconds=LIFETIME_SEC.get(kind, 300))
            if (sent or not _retryable(outcome, error) or attempts >= MAX_ATTEMPTS
                    or now - (_dt(created) or now) > life):
                _state.final_keys.add(key)
                return DONE
            if now - (_dt(last) or now) < RETRY_GAP:
                return RETRY
            await db.execute("UPDATE partner_watch_messages SET attempts=attempts+1, outcome='attempting', text=?, "
                             "summary=?, last_attempt_at=? WHERE message_key=?",
                             (text, summary, now.isoformat(), key))
        await db.commit()
    from partner_bot import send_partner_result
    result = await send_partner_result(text, kind=f"watch_{kind.lower()}", reply_markup=keyboard)
    delivered = bool(result.delivered)
    state = getattr(result, "state", None) or ("acknowledged" if delivered else "failed")
    error = getattr(result, "error", None)
    acked = datetime.now(IST)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_watch_messages SET sent=?, outcome=?, error=?, sent_at=?, message_id=? "
                         "WHERE message_key=?",
                         (int(delivered), state, error, acked.isoformat() if delivered else None,
                          getattr(result, "message_id", None), key))
        await db.commit()
    detect = f"{(now - event_at).total_seconds():.1f}" if event_at else "-"
    logger.info("partner_watch_message kind=%s key=%s state=%s detect_s=%s", kind, key, state, detect)
    if delivered:
        _state.final_keys.add(key)
        return SENT
    if _retryable(state, error):
        return RETRY
    _state.final_keys.add(key)
    return DONE


def _meta(row) -> dict:
    version, computed_at, reason, qty, entry, bought, sold, buy_ids, plan_json = row
    return {"version": version, "computed_at": computed_at, "reason": reason, "qty": qty, "entry": entry,
            "bought": bought, "sold": sold, "buy_ids": json.loads(buy_ids), "plan": Plan(**json.loads(plan_json))}


_META_COLS = "version, computed_at, reason, qty, entry, bought, sold, buy_ids, plan_json"


async def _store_plan(db_path: str, trip: Trip, plan: Plan, now: datetime, reason: str) -> dict:
    """[O24c] Add a plan version. The first ("BUY") is never replaced: when
    one is stored already, it is returned instead."""
    async with aiosqlite.connect(db_path) as db:
        latest = await (await db.execute(
            f"SELECT {_META_COLS} FROM partner_watch_plan_versions WHERE position_key=? ORDER BY version DESC LIMIT 1",
            (trip.key,))).fetchone()
        if latest is not None and reason == "BUY":
            return _meta(latest)
        version = (latest[0] if latest else 0) + 1
        values = (trip.key, version, now.date().isoformat(), trip.exchange, trip.tradingsymbol, now.isoformat(),
                  reason, plan.qty, plan.entry, trip.bought, trip.sold, json.dumps(list(trip.buys)),
                  json.dumps(asdict(plan)))
        await db.execute("INSERT INTO partner_watch_plan_versions(position_key,version,session_date,exchange,"
                         "tradingsymbol,computed_at,reason,qty,entry,bought,sold,buy_ids,plan_json) "
                         "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        await db.commit()
    return _meta(values[1:2] + values[5:])


async def _load_meta(db_path: str, key: str) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            f"SELECT {_META_COLS} FROM partner_watch_plan_versions WHERE position_key=? ORDER BY version DESC LIMIT 1",
            (key,))).fetchone()
    return _meta(row) if row else None


async def plan_versions(db_path: str, key: str) -> list:
    """Every version of a trade's plan, the first first."""
    await init_partner_watch_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            f"SELECT {_META_COLS} FROM partner_watch_plan_versions WHERE position_key=? ORDER BY version",
            (key,))).fetchall()
    return [_meta(row) for row in rows]


async def _plan_for(db_path: str, holding, day: str) -> tuple[Optional[Plan], Optional[datetime]]:
    """The latest plan for a holding (its trade's, else the day's latest on that option) and when it was set."""
    meta = _state.planned.get(holding.position_key) if holding.position_key else None
    if meta is None and holding.position_key:
        meta = await _load_meta(db_path, holding.position_key)
    if meta is None:
        async with aiosqlite.connect(db_path) as db:
            row = await (await db.execute(
                f"SELECT {_META_COLS} FROM partner_watch_plan_versions WHERE session_date=? AND exchange=? AND "
                "tradingsymbol=? ORDER BY computed_at DESC, version DESC LIMIT 1",
                (day, holding.exchange, holding.tradingsymbol))).fetchone()
        meta = _meta(row) if row else None
    if meta is None:
        return None, None
    return meta["plan"], _dt(meta["computed_at"])


async def messages_between(db_path: str, first_day: str, last_day: str) -> list:
    """The watch's recorded messages in the window (for the review), oldest first."""
    await init_partner_watch_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT message_key, session_date, kind, exchange, tradingsymbol, position_key, created_at, sent, summary "
            "FROM partner_watch_messages WHERE session_date>=? AND session_date<=? AND sent=1 ORDER BY created_at",
            (first_day, last_day))).fetchall()
    cols = ("message_key", "session_date", "kind", "exchange", "tradingsymbol", "position_key", "created_at", "sent",
            "summary")
    return [dict(zip(cols, row)) for row in rows]


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

@dataclass
class _Guard:
    """[O24c] One holding's protection over time."""
    since: datetime                 # from when the units held need a stop (the newest buy order's first fill)
    held: int
    state: Optional[str] = None
    state_at: Optional[datetime] = None
    covered_once: bool = False
    stops: list = field(default_factory=list)     # the waiting stops when it was last covered
    lost: int = 0                                  # how many times cover was lost


@dataclass
class _State:
    day: Optional[str] = None
    trading_day: Optional[bool] = None
    login_at: Optional[str] = None
    seeded: bool = False
    orders: dict = field(default_factory=dict)        # order_id -> (status, trigger, filled)
    stop_trigger: dict = field(default_factory=dict)  # order_id -> its trigger while it waited
    carried: list = field(default_factory=list)
    carried_known: bool = False
    cash: Optional[float] = None
    trades: Optional[list] = None
    fills_sig: Optional[tuple] = None
    trades_complete: bool = False
    positions: Optional[list] = None
    positions_at: Optional[datetime] = None
    differs: set = field(default_factory=set)         # holdings whose count Zerodha does not confirm
    gtts: Optional[list] = None
    gtts_at: Optional[datetime] = None
    gtts_tried_at: Optional[datetime] = None
    quotes: dict = field(default_factory=dict)        # tradingsymbol -> the last quote (with "looked_at")
    looks_at: Optional[datetime] = None
    planned: dict = field(default_factory=dict)       # trip key -> the latest plan version (``_meta``)
    plan_tasks: dict = field(default_factory=dict)    # trip key -> the task computing its first plan
    plan_tries: dict = field(default_factory=dict)    # trip key -> plans started
    guards: dict = field(default_factory=dict)        # holding key -> _Guard
    fired_seen: dict = field(default_factory=dict)    # order_id -> when it was first seen fired and unfilled
    lowered_told: set = field(default_factory=set)    # holdings whose first stop move down was told
    close_checked: set = field(default_factory=set)
    final_keys: set = field(default_factory=set)      # messages sent, or not worth sending again
    retry: dict = field(default_factory=dict)         # key -> (kind, subject, summary, keyboard, build)
    size_shares: Optional[list] = None                # the usual-size history before today
    last_tick_ms: Optional[float] = None


_state = _State()
_market = Market()


def reset() -> None:
    """Forget the in-memory watch (tests; a new day; a new login)."""
    global _state
    for task in _state.plan_tasks.values():
        if not task.done():
            task.cancel()
    _state = _State()


async def settle() -> None:
    """Wait for the plans being computed (tests, shutdown)."""
    tasks = [t for t in _state.plan_tasks.values() if not t.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _book(path: str):
    """[O24c] One read of the partner's book, bounded by READ_TIMEOUT_SEC."""
    try:
        return await asyncio.wait_for(zerodha._read(path), READ_TIMEOUT_SEC)
    except asyncio.TimeoutError as exc:
        raise zerodha.BrokerError("timeout", path) from exc


async def _is_trading_day(now: datetime) -> bool:
    if _state.trading_day is None:
        try:
            import main as _main
            _state.trading_day = bool(await _main.is_trading_day(now.date(), settings.DB_PATH))
        except Exception as exc:     # fail closed: no watch on an unknown day
            logger.warning("partner_watch_calendar_failed err=%s", type(exc).__name__)
            return False
    return _state.trading_day


async def _seed(now: datetime) -> None:
    """The first read after a login: the day's cash."""
    try:
        account = zerodha.account_row(await _book("/user/margins/equity"))
        from partner_insights import cash_of
        _state.cash = cash_of(account) if account else None
    except zerodha.BrokerError as exc:
        if exc.code == "TokenException":
            raise
        _state.cash = None


def _trades_cover(rows: list, trades: Optional[list]) -> bool:
    """Whether the trade book shows every filled unit of the orders."""
    if trades is None:
        return False
    shown: dict = {}
    for trade in trades:
        shown[str(trade.get("order_id") or "")] = shown.get(str(trade.get("order_id") or ""), 0) + int(
            trade.get("quantity") or 0)
    return all(shown.get(str(r["order_id"]), 0) >= int(r.get("filled_quantity") or 0) for r in rows
               if int(r.get("filled_quantity") or 0) > 0)


async def _refresh_book(rows: list, now: datetime) -> None:
    """[O24c] The trade book when a fill is new or not shown yet; Zerodha's
    positions after a new fill, every 30 s and while they differ. A failed
    read leaves that part unknown for this tick; it is read again."""
    sig = tuple(sorted((str(r["order_id"]), int(r.get("filled_quantity") or 0)) for r in rows
                       if int(r.get("filled_quantity") or 0) > 0))
    new_fill = sig != _state.fills_sig
    if sig and (new_fill or not _state.trades_complete):
        try:
            _state.trades = list(await _book("/trades") or [])
        except zerodha.BrokerError as exc:
            if exc.code == "TokenException":
                raise
            logger.warning("partner_watch_trades_unread code=%s", exc.code)
            _state.trades = None
        _state.trades_complete = _trades_cover(rows, _state.trades)
    _state.fills_sig = sig
    if (new_fill or _state.differs or not _state.carried_known or _state.positions_at is None
            or now - _state.positions_at >= POSITIONS_EVERY):
        try:
            _state.positions = zerodha.option_positions(await _book("/portfolio/positions"))
            _state.positions_at = now
            if not _state.carried_known:
                _state.carried = [p for p in _state.positions if p["overnight_quantity"] > 0]
                _state.carried_known = True
        except zerodha.BrokerError as exc:
            if exc.code == "TokenException":
                raise
            logger.warning("partner_watch_positions_unread code=%s", exc.code)
            _state.positions, _state.positions_at = None, None


async def watch_tick(now: Optional[datetime] = None, *, market: Optional[Market] = None) -> dict:
    """One look at the partner's book (see the module doc)."""
    started = _time.monotonic()
    now = (now or datetime.now(IST)).astimezone(IST)
    if not enabled():
        return {"status": "SKIPPED", "reason": "disabled"}
    day = now.date().isoformat()
    if _state.day != day:
        reset()
        _state.day = day
    market = market or _market
    market.roll(day)
    minute = now.hour * 60 + now.minute
    if not OPEN_MIN <= minute <= zerodha.CLOSE_MIN:
        return {"status": "SKIPPED", "reason": "outside_session"}
    if not await _is_trading_day(now):
        return {"status": "SKIPPED", "reason": "holiday"}
    db_path = settings.DB_PATH
    await init_partner_watch_db(db_path)
    if not zerodha.connected(now):
        await _reconnect_prompt(db_path, day, now)
        return {"status": "SKIPPED", "reason": "not_connected"}
    login = zerodha.status(now).get("login_at")
    if login != _state.login_at:
        reset()
        _state.day, _state.login_at = day, login
    try:
        if not _state.seeded:
            await _seed(now)
        rows = zerodha.option_orders(await _book("/orders"))
        await _refresh_book(rows, now)
    except zerodha.BrokerError as exc:
        logger.warning("partner_watch_read_failed code=%s", exc.code)
        return {"status": "FAILED", "reason": exc.code}
    sent = await _events(db_path, day, rows, now, market)
    _state.seeded = True
    _state.orders = {r["order_id"]: (str(r.get("status") or "").upper(), zerodha._num(r.get("trigger_price")) or 0.0,
                                     int(r.get("filled_quantity") or 0)) for r in rows}
    elapsed = (_time.monotonic() - started) * 1000
    _state.last_tick_ms = round(elapsed, 1)
    if elapsed > TICK_BUDGET_SEC * 1000:
        logger.warning("partner_watch_tick_slow ms=%.0f", elapsed)
    return {"status": "COMPLETED", "sent": sent, "ms": _state.last_tick_ms}


def _note_differences(holdings: list) -> None:
    """Remember (and log once) the holdings whose count Zerodha's positions do
    not confirm; the positions are read again on each tick while any differ."""
    differs = set()
    for holding in holdings:
        if holding.broker_qty is not None and holding.broker_qty != holding.orders_qty:
            seen = (holding.hkey, holding.orders_qty, holding.broker_qty)
            if seen not in _state.differs:
                logger.warning("partner_watch_holding_differs key=%s orders=%d zerodha=%d basis=%s", holding.hkey,
                               holding.orders_qty, holding.broker_qty, holding.basis)
            differs.add(seen)
    _state.differs = differs


def _holding_for(holdings: list, row: dict) -> Optional[Holding]:
    same = [h for h in holdings if h.exchange == row["exchange"] and h.tradingsymbol == row["tradingsymbol"]]
    return next((h for h in same if _same_product(row.get("product"), h)), None)


async def _events(db_path: str, day: str, rows: list, now: datetime, market: Market) -> int:
    trips = trips_from_fills(fills_of(rows, _state.trades), _state.carried, now.date())
    holdings = holdings_of(trips, _state.positions, _state.positions_at)
    _note_differences(holdings)
    sent = 0
    seeded = _state.seeded
    # 1. Refusals and stop moves are told only when seen happening (not from a book read after a restart).
    for row in rows:
        before = _state.orders.get(row["order_id"])
        status = str(row.get("status") or "").upper()
        if status == "REJECTED" and seeded and (before is None or before[0] != "REJECTED"):
            sent += await _refused(db_path, day, row, rows, holdings, trips, now)
        trigger = zerodha._num(row.get("trigger_price")) or 0.0
        if row["transaction_type"] != "SELL" or status not in WAITING or trigger <= 0:
            continue
        old = _state.stop_trigger.get(row["order_id"])
        _state.stop_trigger[row["order_id"]] = trigger
        holding = _holding_for(holdings, row)
        if seeded and old is not None and trigger < old - 1e-6 and holding is not None:
            sent += await _lowered(db_path, day, holding, row["order_id"], old, trigger, now,
                                   event_at=_dt(row.get("updated_at")))
    # 2. Protection, holding by holding.
    for holding in holdings:
        sent += await _guard(db_path, day, holding, rows, now, market)
    live = {h.hkey for h in holdings}
    for key in [k for k in _state.guards if k not in live]:
        del _state.guards[key]
    # 3. Plans: a new trade's first plan beside the tick; later versions here.
    started = []
    held = {(h.exchange, h.tradingsymbol, h.product) for h in holdings}
    for trip in trips:
        if not trip.open_qty or trip.carried or (trip.exchange, trip.tradingsymbol, trip.product) not in held:
            continue
        meta = _state.planned.get(trip.key)
        task = _state.plan_tasks.get(trip.key)
        if (meta is None and task is not None and task.done() and not task.cancelled()
                and _state.plan_tries.get(trip.key, 0) < PLAN_TRIES):
            del _state.plan_tasks[trip.key]               # it failed (a database error): start it again
        if meta is None and trip.key not in _state.plan_tasks:
            meta = await _load_meta(db_path, trip.key)
            if meta is not None:
                _state.planned[trip.key] = meta          # a restart: the plan stored before it
            else:
                started.append(_start_plan(db_path, day, trip, trips, now, market))
                continue
        if meta is not None:
            sent += await _revise(db_path, day, trip, meta, holdings, now, market)
    if started:
        done, _pending_tasks = await asyncio.wait(started, timeout=PLAN_INLINE_SEC)
        sent += sum(t.result() for t in done if not t.cancelled() and t.exception() is None)
    # 4. The close, retries of messages that did not leave, and the shadow looks.
    if now.hour * 60 + now.minute >= CLOSE_WARN_MIN:
        for holding in holdings:
            if holding.hkey not in _state.close_checked:
                _state.close_checked.add(holding.hkey)
                sent += await _close_warning(db_path, day, holding, now)
    sent += await _retry_pending(db_path, day, rows, now)
    if holdings and (_state.looks_at is None or now - _state.looks_at >= LOOK_EVERY):
        _state.looks_at = now
        await _record_looks(db_path, day, holdings, now, market)
    return sent


async def _refused(db_path: str, day: str, row: dict, rows: list, holdings: list, trips: list,
                   now: datetime) -> int:
    holding = _holding_for(holdings, row)
    same = [h for h in holdings if h.exchange == row["exchange"] and h.tradingsymbol == row["tradingsymbol"]]
    still_open = sum(h.qty for h in same) or None
    subject = holding or next((t for t in reversed(trips) if t.exchange == row["exchange"]
                               and t.tradingsymbol == row["tradingsymbol"]), None) or Trip(
        key=str(row["order_id"]), exchange=row["exchange"], tradingsymbol=row["tradingsymbol"], product="",
        first_at=now)
    text = refused_text(row, rows, still_open)
    key = f"refused:{row['order_id']}"
    status = await _send(db_path, key, day, "REFUSED", subject, text, now, summary="explained Zerodha's refusal",
                         event_at=_dt(row.get("updated_at")) or _dt(row.get("placed_at")))
    if status == RETRY:
        async def build(_rows):
            return text
        _state.retry[key] = ("REFUSED", subject, "explained Zerodha's refusal", None, build)
    return int(status == SENT)


async def _price(market: Market, holding, now: datetime) -> Optional[dict]:
    """[O24c] The option's quote, read now unless one from the last 15 s is at hand."""
    cached = _state.quotes.get(holding.tradingsymbol)
    if cached and now - cached["looked_at"] <= QUOTE_FRESH:
        return cached
    contract = contract_of(holding.exchange, holding.tradingsymbol)
    if contract is None:
        return None
    return (await _quotes(market, [contract], now)).get(holding.tradingsymbol)


async def _quotes(market: Market, contracts: list, now: datetime) -> dict:
    try:
        got = await asyncio.wait_for(market.quote(contracts), QUOTE_TIMEOUT_SEC)
    except Exception as exc:          # a missing price leaves levels unchecked; it never fails the tick
        logger.warning("partner_watch_quote_unread err=%s", type(exc).__name__)
        return {}
    for symbol, quote in (got or {}).items():
        _state.quotes[symbol] = dict(quote, looked_at=now)
    return {symbol: _state.quotes[symbol] for symbol in got or {}}


async def _guard(db_path: str, day: str, holding: Holding, rows: list, now: datetime, market: Market) -> int:
    """[O24c] One holding's protection: told when it is missing, partial,
    lost, lowered by a replacement, or fired without filling."""
    since = _since(holding, now)
    guard = _state.guards.get(holding.hkey)
    if guard is None:
        guard = _state.guards[holding.hkey] = _Guard(since=since, held=holding.qty)
    elif holding.qty > guard.held:
        guard.since, guard.held = max(guard.since, since), holding.qty     # new units need their own stop
    else:
        guard.held = holding.qty
    fresh = _state.gtts_at is not None and now - _state.gtts_at < GTT_EVERY
    cover = cover_of(holding, rows, _state.gtts if fresh else None)
    if cover.state == "UNKNOWN" and not fresh and _state.gtts_tried_at != now:
        await _read_gtts(now)           # once a tick, shared by the holdings
        cover = cover_of(holding, rows, _state.gtts)
    sent = await _unfilled(db_path, day, holding, cover, now, market)
    if cover.state == "UNKNOWN":
        return sent                   # the GTTs could not be read: nothing is claimed; read again next tick
    previous = guard.state
    if cover.state != previous:
        guard.state, guard.state_at = cover.state, now
    if cover.state in COVERED:
        sent += await _replaced_lower(db_path, day, holding, guard, cover, rows, now)
        if previous == "ABSENT" and guard.covered_once:
            guard.lost += 1           # covered again: a later loss of cover is a new message
        guard.covered_once, guard.stops = True, list(cover.stops)
    if now - guard.state_at < COVER_GRACE:
        return sent
    protected = cover.covered + cover.exiting
    if cover.state == "ABSENT" and guard.covered_once:
        kind, key = "REMOVED", f"removed:{holding.hkey}:{guard.lost}"
    elif cover.state == "ABSENT" and now - guard.since >= NO_STOP_AFTER:
        kind, key = "NO_STOP", f"nostop:{holding.position_key or holding.hkey}:{holding.qty}"
    elif cover.state == "PARTIAL" and now - guard.since >= NO_STOP_AFTER:
        kind, key = "PARTIAL", f"partial:{holding.hkey}:{holding.qty}:{protected}"
    else:
        return sent
    if key in _state.final_keys:
        return sent
    plan, set_at = await _plan_for(db_path, holding, day)
    quote = await _price(market, holding, now)
    if kind == "REMOVED":
        why = _lost_why(guard.stops, rows, holding)
        text, keyboard, event_at = removed_text(holding, why, plan, quote, set_at), None, why.get("at")
        summary = "stop sold part, the rest has none" if why["kind"] == "SOLD" else "stop gone, nothing in its place"
    elif kind == "NO_STOP":
        text, summary = no_stop_text(holding, plan, quote, cover, set_at), "no stop order yet"
        keyboard, event_at = quiet_keyboard(day), guard.since + NO_STOP_AFTER
    else:
        text, summary = partial_text(holding, cover, plan, quote, set_at), f"a stop covered {protected} of {holding.qty}"
        keyboard, event_at = quiet_keyboard(day), max(guard.since + NO_STOP_AFTER, guard.state_at)
    status = await _send(db_path, key, day, kind, holding, text, now, summary=summary, keyboard=keyboard,
                         event_at=event_at)
    return sent + (status == SENT)


def _since(holding: Holding, now: datetime) -> datetime:
    """From when the units held need a stop: the newest buy order's first fill (now for a carried or unmatched holding)."""
    trip = holding.trip
    if trip is None or trip.carried or not trip.buys:
        return now
    return max(b["at"] for b in trip.buys.values())


async def _read_gtts(now: datetime) -> None:
    _state.gtts_tried_at = now
    try:
        _state.gtts = list(await _book("/gtt/triggers") or [])
        _state.gtts_at = now
    except zerodha.BrokerError as exc:
        logger.warning("partner_watch_gtts_unavailable code=%s", exc.code)
        _state.gtts, _state.gtts_at = None, None


def _lost_why(stops: list, rows: list, holding: Holding) -> dict:
    """Why the last covering stops no longer cover: the first one's fate."""
    by_id = {f"kite:{r['order_id']}": r for r in rows}
    for stop in stops:
        row = by_id.get(stop["id"])
        if stop["kind"] == "GTT":
            return {"kind": "GTT_GONE", "trigger": stop["trigger"]}
        if row is None:
            continue
        status, filled = str(row.get("status") or "").upper(), int(row.get("filled_quantity") or 0)
        at = _dt(row.get("updated_at"))
        if filled > 0 and status in ("COMPLETE", "CANCELLED"):
            return {"kind": "SOLD", "trigger": stop["trigger"], "sold": filled, "at": at}
        if status == "CANCELLED":
            return {"kind": "CANCELLED", "trigger": stop["trigger"], "at": at}
        return {"kind": "GONE", "trigger": stop["trigger"], "at": at}
    first = stops[0] if stops else {}
    return {"kind": "GONE", "trigger": first.get("trigger")}


async def _unfilled(db_path: str, day: str, holding: Holding, cover: Cover, now: datetime, market: Market) -> int:
    sent = 0
    for fired in cover.fired:
        seen = _state.fired_seen.setdefault(fired["order_id"], now)
        key = f"unfilled:{fired['order_id']}"
        if now - seen < UNFILLED_AFTER or key in _state.final_keys:
            continue
        quote = await _price(market, holding, now)
        status = await _send(db_path, key, day, "UNFILLED", holding, unfilled_text(holding, fired, quote), now,
                             summary="your stop fired and had not sold", event_at=seen)
        sent += status == SENT
    return sent


def _withdrawn(stop_id: str, rows: list, gtts: Optional[list]) -> bool:
    """A stop taken away by the partner: an SL order cancelled with nothing
    sold, or a GTT no longer listed (or cancelled or deleted). A stop that
    fired or sold was not taken away."""
    kind, _sep, ident = stop_id.partition(":")
    if kind == "kite":
        row = next((r for r in rows if str(r["order_id"]) == ident), None)
        return (row is not None and str(row.get("status") or "").upper() == "CANCELLED"
                and not int(row.get("filled_quantity") or 0))
    if gtts is None:
        return False
    gtt = next((g for g in gtts if str(g.get("id")) == ident), None)
    return gtt is None or str(gtt.get("status") or "").lower() in ("cancelled", "deleted", "disabled")


async def _replaced_lower(db_path: str, day: str, holding: Holding, guard: _Guard, cover: Cover, rows: list,
                          now: datetime) -> int:
    """A stop cancelled and replaced by a lower one is a stop moved down (a
    stop that fired, leaving a lower one, is not)."""
    before = {s["id"]: s for s in guard.stops}
    now_ids = {s["id"] for s in cover.stops}
    gone = sorted(i for i in before if i not in now_ids and _withdrawn(i, rows, _state.gtts))
    if not gone or not cover.stops:
        return 0
    old, new = max(s["trigger"] for s in before.values()), max(s["trigger"] for s in cover.stops)
    if new >= old - 1e-6:
        return 0
    return await _lowered(db_path, day, holding, gone[0].split(":", 1)[1], old, new, now)


async def _lowered(db_path: str, day: str, holding: Holding, order_id: str, old: float, new: float, now: datetime,
                   *, event_at: Optional[datetime] = None) -> int:
    plan, _set_at = await _plan_for(db_path, holding, day)
    reason = lowered_reason(holding, old, new, plan, first=holding.hkey not in _state.lowered_told)
    _state.lowered_told.add(holding.hkey)
    if reason is None:
        logger.info("partner_watch_lowered_within_plan key=%s old=%.2f new=%.2f", holding.hkey, old, new)
        return 0
    key = f"lowered:{order_id}:{new:.2f}"
    text = lowered_text(holding, old, new, reason, plan)
    summary = f"stop moved down {_px(old)} → {_px(new)}"
    status = await _send(db_path, key, day, "LOWERED", holding, text, now, summary=summary, event_at=event_at)
    if status == RETRY:
        async def build(rows):
            # Still worth saying while a stop on this option waits at the new level.
            waiting = [r for r in rows if r["exchange"] == holding.exchange and r["tradingsymbol"] == holding.tradingsymbol
                       and str(r.get("status") or "").upper() in WAITING
                       and abs((zerodha._num(r.get("trigger_price")) or 0.0) - new) < 1e-6]
            return text if waiting else None
        _state.retry[key] = ("LOWERED", holding, summary, None, build)
    return int(status == SENT)


async def _retry_pending(db_path: str, day: str, rows: list, now: datetime) -> int:
    """[O24c] Messages told once (a refusal, a stop moved down, a plan, an
    add) that provably did not leave: sent again while still true."""
    sent = 0
    for key, (kind, subject, summary, keyboard, build) in list(_state.retry.items()):
        if key in _state.final_keys:
            del _state.retry[key]
            continue
        text = await build(rows)
        if text is None:
            del _state.retry[key]
            continue
        status = await _send(db_path, key, day, kind, subject, text, now, summary=summary, keyboard=keyboard)
        if status != RETRY:
            del _state.retry[key]
        sent += status == SENT
    return sent


async def _usual_share(db_path: str, trip: Trip, trips: list, now: datetime) -> Optional[float]:
    """[O24-SZ] The share of cash the partner usually puts into a trade:
    their earlier trades as the review counts them
    (partner_coach.size_history), then today's trips before this one."""
    from partner_coach import size_history
    from partner_insights import usual_size
    if _state.size_shares is None:
        try:
            _state.size_shares = await size_history(db_path, now.date().isoformat())
        except Exception as exc:     # no usual known: no size warning
            logger.warning("partner_watch_size_history_failed err=%s", type(exc).__name__)
            return None
    shares = list(_state.size_shares)
    if _state.cash:
        shares += [round(t.entry * t.bought / _state.cash, 4) for t in trips
                   if not t.carried and t.first_at < trip.first_at and t.entry]
    return usual_size(shares)


def _after_loss(trip: Trip, trips: list) -> Optional[dict]:
    from partner_coach import REENTRY_WINDOW_MIN
    closed = [t for t in trips if t.closed_at is not None and t.closed_at <= trip.first_at and t is not trip]
    if not closed:
        return None
    last = max(closed, key=lambda t: t.closed_at)
    result = last.realised()
    minutes = int((trip.first_at - last.closed_at).total_seconds() // 60)
    if result is None or result >= 0 or minutes >= REENTRY_WINDOW_MIN:
        return None
    out = {"loss": -result, "at": _hhmm(last.closed_at), "minutes": minutes}
    if trip.bought > last.bought:
        out["bigger"] = f"{trip.bought} after {last.bought}"
    return out


def _day_line(trip: Trip, trips: list) -> Optional[str]:
    from partner_coach import round_trip_costs
    today = [t for t in trips if not t.carried and t.first_at <= trip.first_at]
    if len(today) < COUNT_FROM_TRADE:
        return None
    charges = 0.0
    for t in today:
        if t is trip or t.exit is None or t.entry is None:
            continue
        qty = min(t.bought, t.sold)
        charges += round_trip_costs(t.entry, t.exit, qty, t.exchange, orders=t.buy_orders + t.sell_orders)
    return f"Trade {len(today)} today · {_amt(charges)} in charges so far."


def _start_plan(db_path: str, day: str, trip: Trip, trips: list, now: datetime, market: Market) -> asyncio.Task:
    snapshot = replace(trip, buys={k: dict(v) for k, v in trip.buys.items()}, sell_ids=list(trip.sell_ids))
    task = asyncio.ensure_future(_plan_job(db_path, day, snapshot, list(trips), now, market,
                                           announce=now - trip.first_at <= PLAN_STALE, owner=_state))
    task.add_done_callback(_plan_done)
    _state.plan_tasks[trip.key] = task
    _state.plan_tries[trip.key] = _state.plan_tries.get(trip.key, 0) + 1
    return task


def _plan_done(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("partner_watch_plan_failed err=%s", type(task.exception()).__name__)


async def _market_plan(trip: Trip, now: datetime, market: Market) -> tuple:
    """The plan from the option's and the front future's candles and quotes."""
    contract = contract_of(trip.exchange, trip.tradingsymbol)
    option_bars, fut_bars, fut_price, quote = None, None, None, None
    if contract is not None:
        future = contract.front_future(now.date())
        try:
            frame = await market.candles(contract, "minute", trip.first_at - timedelta(minutes=SWING_LOOKBACK_MIN + 5),
                                         now)
            if frame is not None:
                option_bars = [(ts.to_pydatetime(), float(r["open"]), float(r["high"]), float(r["low"]),
                                float(r["close"])) for ts, r in frame.iterrows()]
            if future is not None:
                start = (now - timedelta(days=FUTURE_BARS_DAYS)).replace(hour=9, minute=15, second=0, microsecond=0)
                fut_bars = await market.candles(future, "5minute", start, now)
            quotes = await _quotes(market, [c for c in (contract, future) if c is not None], now)
            quote = quotes.get(contract.tradingsymbol)
            fut_price = (quotes.get(future.tradingsymbol) or {}).get("ltp") if future is not None else None
        except Exception as exc:          # the plan says less, it never fails the tick
            logger.warning("partner_watch_market_failed err=%s", type(exc).__name__)
    plan = _plan_of(trip, contract, now, option_bars=option_bars, fut_bars=fut_bars, fut_price=fut_price,
                    mid=_mid(quote))
    lot = int(getattr(contract, "lot_size", 0) or 0)
    return plan, quote, lot


def _plan_of(trip: Trip, contract, now: datetime, *, option_bars=None, fut_bars=None, fut_price=None,
             mid=None) -> Plan:
    return build_plan(entry=round(trip.entry, 2), qty=trip.open_qty, exchange=trip.exchange,
                      opt_type=getattr(contract, "instrument_type", None) or trip.tradingsymbol[-2:],
                      strike=float(getattr(contract, "strike", 0.0) or 0.0),
                      expiry=getattr(contract, "expiry", None), now=now, bought_at=trip.first_at, cash=_state.cash,
                      option_bars=option_bars, fut_bars=fut_bars, fut_price=fut_price, option_mid=mid)


async def _plan_job(db_path: str, day: str, trip: Trip, trips: list, now: datetime, market: Market, *,
                    announce: bool, owner: _State) -> int:
    """A new trade's first plan: computed within PLAN_DEADLINE_SEC (else only
    the premium at risk), stored as version 1, then the PLAN message."""
    try:
        plan, quote, lot = await asyncio.wait_for(_market_plan(trip, now, market), PLAN_DEADLINE_SEC)
    except asyncio.TimeoutError:
        logger.warning("partner_watch_plan_slow key=%s", trip.key)
        plan, quote, lot = _plan_of(trip, None, now), None, 0
    except Exception as exc:          # odd market data: the plan says only the premium at risk
        logger.warning("partner_watch_plan_market_failed key=%s err=%s", trip.key, type(exc).__name__)
        plan, quote, lot = _plan_of(trip, None, now), None, 0
    if owner is not _state:
        return 0                      # a new day or login started meanwhile
    meta = await _store_plan(db_path, trip, plan, now, "BUY")
    _state.planned[trip.key] = meta
    plan = meta["plan"]
    if not announce:
        return 0
    lots = trip.open_qty // lot if lot and trip.open_qty % lot == 0 else None
    after, line = _after_loss(trip, trips), _day_line(trip, trips)
    usual = await _usual_share(db_path, trip, trips, now)
    key = f"plan:{trip.key}"
    status = await _send(db_path, key, day, "PLAN", trip,
                         plan_text(trip, plan, lots=lots, after_loss=after, day_line=line, usual=usual, quote=quote),
                         now, summary=plan_summary(plan, quote), keyboard=quiet_keyboard(day),
                         event_at=trip.first_at)
    if status == RETRY:
        async def build(rows):
            current = trips_from_fills(fills_of(rows, _state.trades), _state.carried, now.date())
            if not any(t.key == trip.key and t.open_qty for t in current):
                return None
            fresh = await _price(market, trip, datetime.now(IST))
            return plan_text(trip, plan, lots=lots, after_loss=after, day_line=line, usual=usual, quote=fresh)
        _state.retry[key] = ("PLAN", trip, plan_summary(plan, quote), quiet_keyboard(day), build)
    return int(status == SENT)


async def _revise(db_path: str, day: str, trip: Trip, meta: dict, holdings: list, now: datetime,
                  market: Market) -> int:
    """[O24c] A later plan version when the trade's size changed: a new buy
    order (ADDED, told while fresh), more fills of a known one (FILLED) or a
    partial sale (TRIMMED)."""
    new_ids = [i for i in trip.buys if i not in meta["buy_ids"]]
    if new_ids:
        reason = "ADDED"
    elif trip.bought != meta["bought"]:
        reason = "FILLED"
    elif trip.sold != meta["sold"]:
        reason = "TRIMMED"
    else:
        return 0
    plan = revised(meta["plan"], entry=round(trip.entry, 2), qty=trip.open_qty, exchange=trip.exchange)
    _state.planned[trip.key] = await _store_plan(db_path, trip, plan, now, reason)
    holding = next((h for h in holdings if h.position_key == trip.key), None)
    first_new = min(trip.buys[i]["at"] for i in new_ids) if new_ids else None
    if reason != "ADDED" or holding is None or now - first_new > PLAN_STALE:
        return 0
    added = sum(trip.buys[i]["qty"] for i in new_ids)
    added_px = sum(trip.buys[i]["value"] for i in new_ids) / added
    first = trip.buys[next(iter(trip.buys))]
    old = meta["plan"]
    loss_before = (round((meta["entry"] - old.stop) * meta["qty"] + _costs(meta["entry"], old.stop, meta["qty"],
                                                                          trip.exchange), 2)
                   if old.stop is not None else round(meta["entry"] * meta["qty"], 2))
    quote = await _price(market, holding, now)
    key = f"added:{trip.key}:{new_ids[-1]}"
    summary = f"you added {added}: the plan stop now costs about −{_amt(-_result_at(holding, plan.stop))}" \
        if plan.stop is not None else f"you added {added}"

    def text_with(price_quote):
        return added_text(holding, added=added, added_px=added_px, first_px=first["value"] / first["qty"], plan=plan,
                          loss_before=loss_before, quote=price_quote)

    status = await _send(db_path, key, day, "ADDED", holding, text_with(quote), now, summary=summary,
                         keyboard=quiet_keyboard(day), event_at=first_new)
    if status == RETRY:
        async def build(rows):
            return text_with(await _price(market, holding, datetime.now(IST)))
        _state.retry[key] = ("ADDED", holding, summary, quiet_keyboard(day), build)
    return int(status == SENT)


def _costs(entry: float, exit_: float, qty: int, exchange: str) -> float:
    from partner_coach import round_trip_costs
    return round_trip_costs(entry, exit_, qty, exchange)


async def _close_warning(db_path: str, day: str, holding: Holding, now: datetime) -> int:
    contract = contract_of(holding.exchange, holding.tradingsymbol)
    expiry_today = bool(contract is not None and getattr(contract, "expiry", None) == now.date())
    plan, _set_at = await _plan_for(db_path, holding, day)
    text = close_text(holding, expiry_today=expiry_today, theta_day=plan.theta_day if plan else None)
    status = await _send(db_path, f"close:{day}:{holding.hkey}", day, "CLOSE", holding, text, now,
                         summary="20 minutes to the close")
    return int(status == SENT)


async def _record_looks(db_path: str, day: str, holdings: list, now: datetime, market: Market) -> None:
    contracts = {h.position_key or h.hkey: contract_of(h.exchange, h.tradingsymbol) for h in holdings}
    wanted = [c for c in contracts.values() if c is not None]
    futures = {}
    for contract in wanted:
        future = contract.front_future(now.date())
        if future is not None:
            futures[contract.tradingsymbol] = future
    if not wanted:
        return
    quotes = await _quotes(market, wanted + list({f.tradingsymbol: f for f in futures.values()}.values()), now)
    if not quotes:
        return
    async with aiosqlite.connect(db_path) as db:
        for key, contract in contracts.items():
            if contract is None or contract.tradingsymbol not in quotes:
                continue
            quote = quotes[contract.tradingsymbol]
            future = futures.get(contract.tradingsymbol)
            fut = (quotes.get(future.tradingsymbol) or {}).get("ltp") if future is not None else None
            await db.execute(
                "INSERT OR IGNORE INTO partner_watch_looks(position_key,at,session_date,bid,ask,ltp,fut,bid_qty,ask_qty,"
                "quote_at,trade_at,received_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, now.isoformat(), day, quote.get("bid"), quote.get("ask"), quote.get("ltp"), fut,
                 quote.get("bid_qty"), quote.get("ask_qty"), quote.get("quote_at"), quote.get("trade_at"),
                 quote.get("received_at")))
        await db.commit()


# ---------------------------------------------------------------------------
# login, morning prompt, reconnect, the quiet button
# ---------------------------------------------------------------------------

async def _send_until_done(db_path: str, key: str, day: str, kind: str, text: str, now: datetime, *,
                           keyboard: Optional[dict] = None) -> str:
    """[O24c] For the one-off messages outside the tick: a provably unsent
    send is tried again after RETRY_GAP, up to MAX_ATTEMPTS."""
    status = DONE
    for attempt in range(MAX_ATTEMPTS):
        status = await _send(db_path, key, day, kind, None, text, now + attempt * RETRY_GAP, keyboard=keyboard)
        if status != RETRY:
            return status
        await asyncio.sleep(RETRY_GAP.total_seconds())
    return status


async def on_login(now: Optional[datetime] = None) -> None:
    """After the partner's Kite login: remember it, and before the close say the watch is on."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not enabled():
        return
    db_path = settings.DB_PATH
    await init_partner_watch_db(db_path)
    day = now.date().isoformat()
    await _set_state(db_path, f"login:{day}", now.isoformat(), now)
    minute = now.hour * 60 + now.minute
    if minute < zerodha.CLOSE_MIN and await _is_trading_day(now):
        close = f"{zerodha.CLOSE_MIN // 60}:{zerodha.CLOSE_MIN % 60:02d}"
        await _send_until_done(db_path, f"on:{day}:{now.isoformat()}", day, "WATCH_ON",
                               WATCH_ON_TEXT.format(close=close), now)


async def watch_prompt(now: Optional[datetime] = None) -> dict:
    """09:00: the login button for today's watch, unless a login is held."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not enabled():
        return {"status": "SKIPPED", "reason": "disabled"}
    if zerodha.connected(now):
        return {"status": "SKIPPED", "reason": "connected"}
    if not await _is_trading_day(now):
        return {"status": "SKIPPED", "reason": "holiday"}
    db_path = settings.DB_PATH
    await init_partner_watch_db(db_path)
    day = now.date().isoformat()
    keyboard = login_keyboard("🔐 Start today's watch")
    if keyboard is None:
        return {"status": "SKIPPED", "reason": "no_login_url"}
    status = await _send_until_done(db_path, f"prompt:{day}", day, "PROMPT", PROMPT_TEXT, now, keyboard=keyboard)
    return {"status": "COMPLETED", "sent": status == SENT}


async def _reconnect_prompt(db_path: str, day: str, now: datetime) -> None:
    login = await _get_state(db_path, f"login:{day}")
    if not login:
        return
    keyboard = login_keyboard("🔐 Reconnect the watch")
    if keyboard is None:
        return
    await _send(db_path, f"reconnect:{day}:{login}", day, "RECONNECT", None, RECONNECT_TEXT, now, keyboard=keyboard)


async def handle_button(db_path: str, data: str, now: datetime) -> Optional[str]:
    """The quiet button (``watch:quiet:YYYYMMDD``): the toast, or None when not ours."""
    parts = str(data or "").split(":")
    if len(parts) != 3 or parts[0] != QUIET_PREFIX or parts[1] != "quiet" or not parts[2].isdigit():
        return None
    day = f"{parts[2][:4]}-{parts[2][4:6]}-{parts[2][6:]}"
    if day != now.astimezone(IST).date().isoformat():
        return "That was for an earlier day."
    await init_partner_watch_db(db_path)
    await _set_state(db_path, f"quiet:{day}", "1", now)
    logger.info("partner_watch_quiet day=%s", day)
    return QUIET_TOAST


async def watch_status(now: Optional[datetime] = None) -> dict:
    """For the review page: is the watch on now, and quiet?"""
    now = (now or datetime.now(IST)).astimezone(IST)
    minute = now.hour * 60 + now.minute
    on = enabled() and zerodha.connected(now) and OPEN_MIN - 15 <= minute < zerodha.CLOSE_MIN
    close = f"{zerodha.CLOSE_MIN // 60}:{zerodha.CLOSE_MIN % 60:02d}"
    return {"on": bool(on), "until": close,
            "quiet": await quiet(settings.DB_PATH, now.date().isoformat()) if on else False}
