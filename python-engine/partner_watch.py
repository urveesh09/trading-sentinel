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
  - [O24g] One tick at a time. With PARTNER_WATCH_STREAM_ENABLED, Kite's
    order updates on the websocket (partner_watch_stream) wake a tick at once
    (``wake``, at least WAKE_GAP_SEC apart); the 5 s ticks go on regardless.
    Each message records whether a 5 s tick or a woken one found it
    (``detected_by``), and the day's tick timings are saved for
    partner_watch_report.

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
            from the 5th trade the day's trades and charges. [O24d] Its last
            line starts from the stops already in place (``stop_advice``).
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
            one): the result if it is hit, then and before ([O24e] for the
            units that stop sells, the rest said apart). Told the first
            time in a trade, and after that only when the move puts the stop
            under the plan's stop or gives up a stop that was guarding the
            buy price. Oct 23 had 20 moves down, 7 of them on one trade; every
            move is still in the evening review.
  REFUSED   Zerodha refused an order: why, in plain words
            (partner_insights.refusal_plain), and whether the trade is still
            open.
  EXCESS    [O24e] sell orders (SL, limit, GTT; an OCO once) that together
            would sell more than is held, for 20 s: the extra is a short sale.
  ORPHAN    [O24e] sell orders still waiting on an option no longer held.
            [O24f] "You hold none" only when Zerodha's positions show it;
            when they cannot be read, the order may protect a holding not
            seen (one from an earlier day), so it is "keep it if you hold it".
  PRODUCT   [O24f] sell orders of a product not held, on an option held as
            another (an MIS sell on NRML units opens an MIS short).
  CLOSE     15:20 with an option still held: what the close does to it.
  BLIND     [O24f] a read the watch needs has failed for a while: the orders
            (60 s), the positions while the overnight list is unknown
            (120 s), the GTTs while a holding's protection is unknown
            (120 s). BACK when that read works again.
  "Quiet today" (a button on PLAN and NO_STOP) mutes PLAN, ADDED, NO_STOP,
  PARTIAL and CLOSE. LOWERED, REMOVED, UNFILLED, REFUSED, EXCESS, ORPHAN,
  PRODUCT, BLIND and BACK always go, because those are the moments a loss
  grows (or the watch cannot see it).

[O24g] Every stop moved down in one read (SL orders modified, GTTs
modified, a stop replaced) is one LOWERED message, judged together
(``moves_reason``): none is dropped because another was looked at first. A
claim of no stop (NO_STOP, PARTIAL, REMOVED), or a sell-order claim that
counts a GTT (EXCESS, ORPHAN, PRODUCT), is made only from a GTT list read in
that tick, the first time it is due: the list is otherwise reused for 20 s
(60 s for the sell-order check), and a GTT placed or deleted since was not in
it.

[O24f] A stop replaced (``_track_stops``): stops taken away and stops placed
are kept for REPLACE_WINDOW (120 s), whether seen in one read or several,
in either order. One taken away and one placed lower is that stop moved, for
the units both sell; several are told as one change, never paired; a stop
taken away with nothing placed is not a move (REMOVED or PARTIAL tell it);
a GTT modified down (same id) is a move. "Placed" means new to every stop
the holding had, not new to what ``cover_of`` needed to read. One option
held as MIS and NRML is two holdings, named with the product; units Zerodha
shows in a product the orders did not buy look converted, and say so.

[O24c] Every level in a message is checked against the price read just
before it (``level_state``). Kite refuses an SL sell whose trigger is at or
above the last price, so:
  - a plan stop the price is already under is said as that, with what
    selling at the bid would give, never as a stop to place;
  - a target already passed is said as passed;
  - a level that could not be checked says when it was set.
[O24d] Only a fresh price checks a level: our read within QUOTE_FRESH (15 s)
and the exchange's last quote update within QUOTE_MAX_AGE (15 s, [O24e])
before we received it (else STALE). A level not checked is an earlier
reference to check first, never "place an SL now". What selling now gives
is priced against the bids' sizes: a best bid for fewer units than are held
is not the price of all of them.

[O24d] The stop advice (``stop_advice``) starts from what already protects
the units: a stop at or above the plan stop is enough (no second SL); a lower
one is compared with the plan stop (not called worse: [O24e] a tighter stop
is not a better one until scored); a part covered gets an SL for the rest
only; an unreadable GTT list says "if you have no stop yet". [O24e] Without
a plan stop (no market data, a swing as big as the price) the stop line
still starts from the stops in place (``_no_level_line``).

[O24d] The outbox (``partner_watch_messages``)
  - The tick finds what to say and stores it with its key and context; the
    text is built when it is sent, from the latest book read (``View``). A
    message no longer true then (the trade closed, a stop is back, the size
    changed) is "superseded" and not sent; with no fresh read it waits.
  - Keys name the trade (``_episode``: its opening buy's order id, or the
    carried position, with the day) and the incident (the size, or the
    stops lost): a later trade in the same option is warned too, a repeat
    within one incident is not. What covered each trade is kept in
    partner_watch_state, so a restart still knows it.
  - [O24e] A message is sent only if the view it was built from is still
    the latest after the build (and after its row is marked): building
    awaits prices and the database, and a newer read is built from again.
  - [O24e] A plan version and the message it owes (PLAN, ADDED) are written
    in one transaction, so a failed write leaves neither and is retried.
  - One sender (``_drain``), the most urgent first (PRIORITY). Telegram's
    own answer is kept. A message that provably did not leave (no
    connection, the rate limit, a Telegram 5xx) is sent again RETRY_GAP
    later, rebuilt, within LIFETIME_SEC and MAX_ATTEMPTS; this survives a
    restart, because the outbox is in the database. A timeout after the
    request left may have arrived, so it is not repeated.
  - The broker's event time, the detection time and Telegram's
    acknowledgement time are stored for each message.

[O24c] Timing
  - The tick reads the book and finds the protection alarms first. [O24d]
    Its reads and waits share TICK_BUDGET_SEC: each read is bounded by
    READ_TIMEOUT_SEC and by what is left; an optional read (the trade book,
    positions, GTTs, cash) with under MIN_READ_SEC left waits for the next
    tick, keeping the last one. Sending goes beside the tick.
  - The plan's market reads (candles, quotes) run beside the tick within
    PLAN_DEADLINE_SEC; the tick waits at most PLAN_INLINE_SEC for them.
  - A plan that cannot be computed in time says only the premium at risk.

[O24c] Plans (``partner_watch_plan_versions``)
  - A trade's first plan is kept as it was computed (version 1).
  - Each later version (a new buy order, more fills, a partial sale) has its
    reason, quantity and average.
  - A restart loads the plan instead of computing it again.
  - [O24d] The quantity and average are what is held (Zerodha's count when
    it differs from the orders'); bought and sold are the orders'. Every
    message about a position uses that one count, and says what was bought
    (and sold) apart from what is held.

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
from types import SimpleNamespace
from typing import Awaitable, Callable, Optional

import aiosqlite
import pandas as pd
import pytz
import structlog

import background_tasks
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
# [O24e] An exchange quote this much older than its receipt checks no level. The same 15 s as our own read: the
# partner's index options are quoted many times a second, so a quote unchanged this long is either a stalled feed
# or a contract too thin to place a level against. partner_watch_looks keeps both clocks to check it on live days.
QUOTE_MAX_AGE = timedelta(seconds=15)
POSITIONS_EVERY = timedelta(seconds=30)
POSITIONS_LAG = timedelta(seconds=10)      # a fill this recent may not be in Zerodha's positions yet
POSITIONS_MAX_AGE = timedelta(minutes=2)   # an older positions read (later reads failed) confirms nothing
GTT_EVERY = timedelta(seconds=20)
GTT_REFRESH = timedelta(seconds=60)        # [O24e] the GTT list for the exit-size check
REPLACE_WINDOW = timedelta(seconds=120)    # [O24f] a stop taken away and one placed this close together: a replacement
# [O24f] How long a read may fail before the partner is told the watch cannot see it.
BLIND_AFTER = {"orders": timedelta(seconds=60), "positions": timedelta(seconds=120), "gtts": timedelta(seconds=120)}
READ_TIMEOUT_SEC = 4.0                     # one read of the partner's book
MIN_READ_SEC = 0.5                         # an optional read with less of the tick's budget left waits a tick
QUOTE_TIMEOUT_SEC = 3.0
PLAN_DEADLINE_SEC = 25.0                   # the plan's market reads
PLAN_INLINE_SEC = 1.5                      # how long a tick waits for a plan before going on
PLAN_TRIES = 3                             # a plan that failed (not timed out: that is the premium plan) is retried
TICK_BUDGET_SEC = 4.0                      # the tick's reads and waits together (the cadence is 5 s)
DELIVERY_INLINE_SEC = 1.5                  # how long a tick (or a login) waits for its messages to go
VIEW_FRESH = timedelta(seconds=15)         # a message is built only from a book read this recent
CASH_TRIES = 3
BUILD_TRIES = 3                            # [O24e] builds of one message while newer book reads keep arriving
WAKE_GAP_SEC = 1.0                         # [O24g] ticks woken by the stream are at least this far apart
TICK_STATS_EVERY = timedelta(seconds=60)   # [O24g] the tick timings are saved this often (partner_watch_report)
TICK_SAMPLES = 6000                        # [O24g] timings kept per process and day (8 h of 5 s ticks)
CLOSE_WARN_MIN = 15 * 60 + 20
SWING_LOOKBACK_MIN = 30
SWING_WINDOW_MIN = 5
SWING_MIN_BARS = 10
RUN_LOOKBACK_MIN = 15
COUNT_FROM_TRADE = 5
FUTURE_BARS_DAYS = 21                      # as the F&O engine (fno_orchestrator.RVOL_FETCH_CALENDAR_DAYS)
TICK = 0.05
QUIET_KEEPS = ("LOWERED", "REMOVED", "UNFILLED", "REFUSED", "EXCESS", "ORPHAN", "PRODUCT")
ALWAYS_SENT = ("WATCH_ON", "PROMPT", "RECONNECT", "BLIND", "BACK")
GUARD_TOLERANCE = 0.005                    # a stop within 0.5% under the buy price still guards it
QUIET_PREFIX = "watch"
# Kite states in which an SL order still waits to protect (a modify in flight included).
WAITING = ("TRIGGER PENDING", "MODIFY PENDING", "MODIFY VALIDATION PENDING", "VALIDATION PENDING", "OPEN PENDING",
           "PUT ORDER REQ RECEIVED", "AMO REQ RECEIVED")
COVERED = ("FULL", "PARTIAL")
# How long a message is still worth sending again after a failed send (seconds).
LIFETIME_SEC = {"PLAN": 180, "ADDED": 180, "NO_STOP": 900, "PARTIAL": 900, "REMOVED": 900, "UNFILLED": 120,
                "LOWERED": 120, "REFUSED": 300, "CLOSE": 1200, "WATCH_ON": 600, "PROMPT": 1800, "RECONNECT": 1800,
                "EXCESS": 900, "ORPHAN": 900, "PRODUCT": 900, "BLIND": 600, "BACK": 300}
MAX_ATTEMPTS = 4
RETRY_GAP = timedelta(seconds=10)
# [O24d] The outbox sends the most urgent first.
PRIORITY = {"UNFILLED": 0, "REMOVED": 1, "LOWERED": 1, "REFUSED": 1, "EXCESS": 1, "ORPHAN": 1, "PRODUCT": 1,
            "BLIND": 1, "NO_STOP": 2, "PARTIAL": 2, "ADDED": 3,
            "PLAN": 3, "CLOSE": 4, "BACK": 4, "WATCH_ON": 5, "PROMPT": 5, "RECONNECT": 5}
SENT, DONE, RETRY, MUTED, WAIT, LATER = "SENT", "DONE", "RETRY", "MUTED", "WAIT", "LATER"
QUEUED = "queued"

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
                               ("sent_at", "TEXT"), ("message_id", "INTEGER"),
                               # [O24d] the outbox: what to build the text from, the trade, the order
                               ("context", "TEXT"), ("episode", "TEXT"), ("priority", "INTEGER NOT NULL DEFAULT 5"),
                               # [O24g] poll (the 5 s tick) | stream (a tick the order stream woke)
                               ("detected_by", "TEXT")),
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
        await db.execute("CREATE INDEX IF NOT EXISTS ix_partner_watch_messages_outbox "
                         "ON partner_watch_messages(session_date, sent, outcome)")
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


def _name(position) -> str:
    """[O24f] A holding's option, with its product when the option is held as two products."""
    name = _option(position.tradingsymbol)
    return f"{name} {position.product}" if getattr(position, "twin", False) else name


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


def _result_for(holding, price: float, qty: int) -> float:
    """The result after charges if ``qty`` of the holding sold at ``price`` (``holding``: a Trip or a Holding)."""
    from partner_coach import round_trip_costs
    return round((price - holding.entry) * qty - round_trip_costs(holding.entry, price, qty, holding.exchange), 2)


def _result_at(holding, price: float) -> float:
    """The trade's result after charges if all of it sold at ``price``."""
    return _result_for(holding, price, holding.open_qty)


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
    twin: bool = False               # [O24f] the same option is held as another product too (texts name the product)
    converted: Optional[str] = None  # [O24f] the product today's orders bought these units as (Zerodha shows them here)

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
        out = [Holding(*key, qty=t.open_qty, orders_qty=t.open_qty, broker_qty=None, basis="ORDERS", trip=t,
                       average=t.entry) for key, t in mine.items()]
        return _mark_holdings(out, mine, {})
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
    return _mark_holdings(out, mine, broker)


def _mark_holdings(out: list, mine: dict, broker: dict) -> list:
    """[O24f] One option held as two products is two holdings (``twin``: the
    texts name the product). Units Zerodha shows in a product today's orders
    did not buy, while the orders' own product shows fewer, look converted
    (``converted``: a conversion places no order)."""
    for holding in out:
        option = (holding.exchange, holding.tradingsymbol)
        holding.twin = any(h is not holding and (h.exchange, h.tradingsymbol) == option for h in out)
        if holding.basis == "ZERODHA" and holding.orders_qty < holding.qty:
            holding.converted = next((key[2] for key in sorted(mine) if key[:2] == option and key[2] != holding.product
                                      and mine[key].open_qty > int((broker.get(key) or {}).get("quantity") or 0)),
                                     None)
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


def stale(quote: Optional[dict], now: Optional[datetime] = None) -> bool:
    """[O24d] A price too old to check a level against: our read is older
    than QUOTE_FRESH, or the exchange's quote time is more than QUOTE_MAX_AGE
    before we received it (an option nobody has quoted for a minute)."""
    if not quote:
        return False
    looked = quote.get("looked_at")
    if now is not None and isinstance(looked, datetime) and now - looked > QUOTE_FRESH:
        return True
    exchange, received = _dt(quote.get("quote_at")), _dt(quote.get("received_at"))
    return bool(exchange and received and received - exchange > QUOTE_MAX_AGE)


def level_state(level: Optional[float], quote: Optional[dict], now: Optional[datetime] = None) -> str:
    """[O24c] A plan stop against the last price: VALID (an SL sell can be
    placed there: Kite needs the trigger under the last price), CROSSED (the
    price is at or under it), UNCHECKED (no price read), NONE (no stop).
    [O24d] STALE: the price read is too old to tell (``stale``)."""
    if level is None:
        return "NONE"
    ltp = (quote or {}).get("ltp")
    if not ltp:
        return "UNCHECKED"
    if stale(quote, now):
        return "STALE"
    return "CROSSED" if ltp <= level + 1e-9 else "VALID"


def _exit_price(quote: Optional[dict]) -> Optional[float]:
    """What selling now would get: the best bid, else the last price."""
    return (quote or {}).get("bid") or (quote or {}).get("ltp")


def exit_fill(quote: Optional[dict], qty: int) -> tuple:
    """[O24d] Selling ``qty`` now into the bids the quote shows: (average
    price, units they take, the best bid, the lowest bid used, whether the
    bids' sizes are known). Without sizes it is the best bid (or the last
    price) for all."""
    bids = [(float(p), int(q)) for p, q in (quote or {}).get("bids") or [] if p and q]
    if not bids:
        price = _exit_price(quote)
        return price, (qty if price else 0), price, price, False
    left, value, low = qty, 0.0, None
    for price, size in bids:
        take = min(left, size)
        value, left, low = value + take * price, left - take, price
        if not left:
            break
    taken = qty - left
    return (value / taken if taken else None), taken, bids[0][0], low, True


# ---------------------------------------------------------------------------
# message texts (pure)
# ---------------------------------------------------------------------------

def _share(loss: Optional[float], cash: Optional[float]) -> str:
    return f", {loss / cash:.0%} of your cash" if loss is not None and cash else ""


def _sell_now(holding, quote: Optional[dict], cash: Optional[float] = None) -> str:
    """What selling everything now gives. [O24d] Against the bids' sizes when
    the quote has them: a best bid for fewer units than are held is not the
    price of all of them."""
    qty = holding.open_qty
    average, taken, best, low, sized = exit_fill(quote, qty)
    if not average or holding.entry is None or not qty:
        return ""
    if not sized or (taken >= qty and abs(low - best) < 1e-9):
        price = best if sized else average
        result = _result_at(holding, price)
        where = "at the bid" if sized or (quote or {}).get("bid") else "at the last price"
        share = _share(-result, cash) if result < 0 else ""
        return f" Selling {where} {_px(price)} now: about {_signed(result)} with charges{share}."
    if taken >= qty:
        result = _result_at(holding, average)
        share = _share(-result, cash) if result < 0 else ""
        return (f" Selling all {qty} now into the bids ({_px(best)} down to {_px(low)}): about {_signed(result)} with "
                f"charges{share}.")
    # The bids shown take only part: the rest would sell at the lowest shown or under it.
    result = _result_at(holding, (average * taken + low * (qty - taken)) / qty)
    share = _share(-result, cash) if result < 0 else ""
    return (f" The bids shown take only {taken} of your {qty} ({_px(best)} down to {_px(low)}); selling all now: "
            f"about {_signed(result)} or worse with charges{share}.")


def _upper(text: str) -> str:
    return text[:1].upper() + text[1:]


def _checked(quote: Optional[dict]) -> str:
    """When the price a level was checked against was read ("" without the read time)."""
    if not quote or not quote.get("looked_at") or not quote.get("ltp"):
        return ""
    return f"; the price was {_px(quote['ltp'])} at {_hms(quote['looked_at'])}"


def _unchecked(stop: float, quote: Optional[dict], set_at: Optional[datetime]) -> str:
    """[O24d] A plan stop that could not be checked against a current price:
    an earlier reference, not an instruction."""
    since = f" is from {_hms(set_at)}" if set_at else ""
    exchange = _dt((quote or {}).get("quote_at"))
    if quote and quote.get("ltp") and exchange:
        why = f"the last price update I have is from {_hms(exchange)}"
    elif quote and quote.get("ltp") and quote.get("looked_at"):
        why = f"the last price I read was at {_hms(quote['looked_at'])}"
    else:
        why = "the price could not be read now"
    return (f"the plan stop {_px(stop)}{since}, and {why}: check the option is still above {_px(stop)} before "
            f"placing an SL there (Zerodha refuses an SL sell at or above the price).")


def _triggers(stops: list) -> str:
    levels = sorted({round(s["trigger"], 2) for s in stops}, reverse=True)
    names = [_px(level) for level in levels]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _result_at_stops(position, stops: list) -> float:
    """The result if the waiting stops sell at their triggers (the highest
    first, for the units held)."""
    left, value = position.open_qty, 0.0
    for stop in sorted(stops, key=lambda s: -s["trigger"]):
        take = min(left, int(stop["units"]))
        value, left = value + take * stop["trigger"], left - take
    sold = position.open_qty - left
    return _result_at(position, value / sold if sold else min(s["trigger"] for s in stops))


def stop_advice(position, plan: Optional[Plan], cover: Optional[Cover], quote: Optional[dict], *,
                now: Optional[datetime] = None, set_at: Optional[datetime] = None) -> str:
    """[O24d] The PLAN's last line: what to do about a stop, given what
    already protects these units and how fresh the price is.

    - FULL: never a second SL. A stop at or above the plan stop is said to
      be enough; a lower one is compared with the plan stop. [O24e] Raising
      it is not suggested: a tighter stop is not a better one until scored.
    - PARTIAL: an SL for the units left only.
    - UNKNOWN (the GTTs could not be read): "if you have no stop yet".
    - ABSENT: "Place an SL sell now", only against a fresh price; otherwise
      the plan stop is an earlier reference to check first.
    "" when the price is already under the plan stop (the stop line says it)
    or there is no plan stop."""
    if plan is None or plan.stop is None:
        return ""
    state = level_state(plan.stop, quote, now)
    if state == "CROSSED":
        return ""
    held = position.open_qty
    fresh = state == "VALID"
    order = f"an SL sell, trigger {_px(plan.stop)}, limit a little under it{_checked(quote)}."
    unsure = _unchecked(plan.stop, quote, set_at)
    if cover is not None and cover.state == "FULL":
        if not cover.stops:
            return "Your stop has triggered and is selling."
        yours = _triggers(cover.stops)
        if min(s["trigger"] for s in cover.stops) >= plan.stop - 1e-9:
            return (f"Your SL at {yours} already covers all {held}. The plan stop {_px(plan.stop)} is lower than "
                    f"yours: no second SL is needed.")
        # [O24e] A comparison, not a call to tighten: a tighter stop is not a better one until it is scored.
        return (f"Your SL at {yours} covers all {held}, under the plan stop {_px(plan.stop)}: if it sells there, "
                f"about {_signed(_result_at_stops(position, cover.stops))} with charges, against "
                f"{_signed(_result_at(position, plan.stop))} at the plan stop.")
    if cover is not None and cover.state == "PARTIAL":
        protected = cover.covered + cover.exiting
        whose = f"Your SL at {_triggers(cover.stops)}" if cover.stops else "A stop"
        head = f"{whose} covers {protected} of your {held}. For the other {held - protected}: "
        return head + (order if fresh else unsure)
    if cover is not None and cover.state == "UNKNOWN":
        return "Your GTTs could not be read. If you have no stop yet: " + (order if fresh else unsure)
    if fresh:
        return (f"Place an SL sell now: trigger {_px(plan.stop)}, limit a little under it{_checked(quote)}. In a fast "
                f"fall an SL order can trigger and still not fill.")
    return _upper(unsure)


def _held_line(position, bought: int) -> Optional[str]:
    """[O24d] When what is held now is not what was bought: the count the
    lines below use, apart from what was bought (and sold)."""
    held = position.open_qty
    note = _count_note(position).strip()
    if held == bought and not note:
        return None
    trip = getattr(position, "trip", position if isinstance(position, Trip) else None)
    if getattr(position, "basis", "") == "ZERODHA" or held == bought:
        line = note
    elif held < bought:
        line = f"{held} still held"
        if trip is not None and trip.sold and trip.exit is not None and trip.entry is not None:
            from partner_coach import round_trip_costs
            done = round((trip.exit - trip.entry) * trip.sold
                         - round_trip_costs(trip.entry, trip.exit, trip.sold, trip.exchange), 2)
            line += f": you sold {trip.sold} at {_px(trip.exit)}, {_signed(done)} with charges"
        line += "." + (f" {note}" if note else "")
    else:
        line = f"{held} held now, with your later buys." + (f" {note}" if note else "")
    return f"• {line} The lines below are for the {held} held."


def _no_level_line(position, plan: Plan, cover: Optional[Cover], share: str) -> str:
    """[O24e] The stop line without a plan stop (no market data, or a swing
    as big as the price), from what already protects the units: never
    "place it now" over a stop already in place. A stop is a level an order
    waits at, not a floor under the loss."""
    held = position.open_qty
    if plan.stop_basis == "NONE":
        why = (f"This option's normal 5-minute swing ({_px(plan.swing)}) is as big as its price: any stop sits inside "
               f"the noise.")
    else:
        why = "I could not work out a fresh reference level (no market data)."
    if cover is not None and cover.state == "FULL":
        if not cover.stops:
            return f"Your stop has triggered and is selling. {why}"
        return (f"Your SL at {_triggers(cover.stops)} covers all {held}. {why} If it sells there: about "
                f"{_signed(_result_at_stops(position, cover.stops))} with charges; in a fast fall an SL order can "
                f"trigger and still not fill.")
    if cover is not None and cover.state == "PARTIAL":
        protected = cover.covered + cover.exiting
        rest = held - protected
        whose = f"Your SL at {_triggers(cover.stops)}" if cover.stops else "A stop"
        return (f"{whose} covers {protected} of your {held}; the other {rest} have none: "
                f"{_amt((position.entry or 0.0) * rest)} of what you paid is at risk on them. {why}")
    unread = cover is not None and cover.state == "UNKNOWN"
    if plan.stop_basis == "NONE":
        return (f"{why} At risk: the whole {_amt(plan.loss)}{share}"
                + (", unless a GTT covers it (your GTTs could not be read)." if unread else "."))
    if unread:
        return (f"At risk: the whole {_amt(plan.loss)} you paid{share}, unless a GTT covers it (your GTTs could not be "
                f"read). {why} If you have no stop yet, decide it and place it now.")
    return f"At risk: the whole {_amt(plan.loss)} you paid{share}. Decide your stop and place it now."


def plan_text(position, plan: Plan, *, lots: Optional[int], bought: Optional[tuple] = None,
              cover: Optional[Cover] = None, after_loss: Optional[dict] = None, day_line: Optional[str] = None,
              usual: Optional[float] = None, quote: Optional[dict] = None, now: Optional[datetime] = None,
              set_at: Optional[datetime] = None) -> str:
    """The PLAN message. ``position``: what is held now (a Holding; a Trip
    in the pure tests), with ``plan`` for that size. ``bought``: (qty, price)
    of the buy the plan is for (the plan's own by default). ``quote``: the
    option's price read just before sending; a stop the price is already
    under is never offered as a stop. [O24d] ``cover``: what already
    protects the units (``stop_advice``)."""
    from partner_insights import USUAL_SIZE_MULT
    name = _name(position)
    future = _future_of(position.tradingsymbol)
    bought_qty, bought_px = bought or (plan.qty, plan.entry)
    size = f"{lots} lot{'s' if lots != 1 else ''} ({bought_qty})" if lots else f"{bought_qty}"
    lines = [f"🟢 You bought {name} · {size} at {_px(bought_px)}"]
    held = _held_line(position, bought_qty)
    if held:
        lines.append(held)
    share = _share(plan.loss, plan.cash)
    stop_now = level_state(plan.stop, quote, now)
    if stop_now == "CROSSED":
        lines.append(f"🛑 The price ({_px(quote['ltp'])}) is already under the plan stop {_px(plan.stop)}, the level "
                     f"where this trade is wrong.{_sell_now(position, quote, plan.cash)}")
    elif plan.stop_basis == "INDEX":
        lines.append(f"🛑 Plan stop {_px(plan.stop)} ({future} {plan.stop_index:,.0f}). If it sells there: about "
                     f"−{_amt(plan.loss)} with charges{share}.")
    elif plan.stop_basis == "SWING":
        inside = (f"The futures stop ({plan.stop_index:,.0f} → {_px(plan.index_stop_option)}) sits inside that "
                  f"swing. " if plan.stop_index is not None and plan.index_stop_option is not None else "")
        lines.append(f"🛑 Plan stop {_px(plan.stop)}: one normal 5-minute swing ({_px(plan.swing)}) under your "
                     f"price. {inside}If it sells there: about −{_amt(plan.loss)} with charges{share}.")
    else:
        lines.append("🛑 " + _no_level_line(position, plan, cover, share))
    paid = bought_px * bought_qty
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
    advice = stop_advice(position, plan, cover, quote, now=now, set_at=set_at)
    if advice:
        lines.append(advice)
    return "\n".join(lines)


def plan_summary(plan: Plan, quote: Optional[dict] = None, cover: Optional[Cover] = None,
                 now: Optional[datetime] = None) -> str:
    if level_state(plan.stop, quote, now) == "CROSSED":
        return f"the price was already under the plan stop {_px(plan.stop)}"
    if (plan.stop is not None and cover is not None and cover.state == "FULL" and cover.stops
            and min(s["trigger"] for s in cover.stops) >= plan.stop - 1e-9):
        return f"plan stop {_px(plan.stop)}; your SL at {_triggers(cover.stops)} already covered it"
    if plan.stop is not None:
        return f"plan stop {_px(plan.stop)}, loss if it sells there about −{_amt(plan.loss)}"
    if cover is not None and cover.state == "FULL" and cover.stops:
        return f"no plan stop; your SL at {_triggers(cover.stops)} covered all {cover.held}"
    return f"at risk: the whole {_amt(plan.loss)}"


def _count_note(holding) -> str:
    """[O24c] Where the count comes from when Zerodha's positions do not confirm it ("" when they do)."""
    if getattr(holding, "basis", "CONFIRMED") == "ZERODHA" and getattr(holding, "converted", None):
        return (f" Zerodha's positions show {holding.qty} held as {holding.product}; your orders today bought them "
                f"as {holding.converted}, so they look converted. The count is Zerodha's.")
    if getattr(holding, "basis", "CONFIRMED") == "ZERODHA":
        return (f" Zerodha's positions show {holding.qty} held; your orders today give {holding.orders_qty}, so the "
                f"count is Zerodha's.")
    if getattr(holding, "basis", "CONFIRMED") == "ORDERS" and getattr(holding, "broker_qty", 0) is None:
        return " The count is from your orders: Zerodha's positions could not be read."
    return ""


def plan_stop_line(holding, plan: Optional[Plan], quote: Optional[dict], *, set_at: Optional[datetime] = None,
                   now: Optional[datetime] = None) -> str:
    """[O24c] The plan stop for the units held now, checked against the price
    just read; "" without a plan stop."""
    if plan is None or plan.stop is None or holding.entry is None:
        return ""
    state = level_state(plan.stop, quote, now)
    read = f" at {_hms(quote['looked_at'])}" if quote and quote.get("looked_at") else ""
    if state == "CROSSED":
        return (f" The price ({_px(quote['ltp'])}{read}) is already under the plan stop {_px(plan.stop)}."
                f"{_sell_now(holding, quote, plan.cash)}")
    loss = -_result_at(holding, plan.stop)
    if state == "VALID":
        return (f" Plan stop {_px(plan.stop)} (price {_px(quote['ltp'])}{read}); if it sells there, about "
                f"−{_amt(loss)} with charges.")
    since = f"set at {_hhmm(set_at)}; " if set_at else ""
    exchange = _dt((quote or {}).get("quote_at"))
    why = (f"the last price update was {_hms(exchange)}" if state == "STALE" and exchange else
           "the price could not be read now")
    return (f" Plan stop {_px(plan.stop)} ({since}{why}); if it sells there, about −{_amt(loss)} with charges.")


def _product_note(cover: Optional[Cover], holding) -> str:
    if cover is None or not cover.other_product:
        return ""
    stop = cover.other_product[0]
    return (f" Your stop for {stop['units']} is {stop.get('product') or 'another product'} and these are "
            f"{holding.product}: it would not sell them.")


def no_stop_text(holding, plan: Optional[Plan], quote: Optional[dict] = None, cover: Optional[Cover] = None,
                 set_at: Optional[datetime] = None, *, now: Optional[datetime] = None) -> str:
    when = "held from yesterday" if holding.carried else (
        f"bought {_hhmm(holding.first_at)}" if holding.first_at else "held")
    line = f"⏰ {_name(holding)} ({holding.open_qty}): no stop order yet ({when})."
    return line + _count_note(holding) + _product_note(cover, holding) + plan_stop_line(holding, plan, quote,
                                                                                       set_at=set_at, now=now)


def partial_text(holding, cover: Cover, plan: Optional[Plan], quote: Optional[dict] = None,
                 set_at: Optional[datetime] = None, *, now: Optional[datetime] = None) -> str:
    protected = cover.covered + cover.exiting
    line = (f"⚠️ {_name(holding)}: protection incomplete. A stop covers {protected} of your "
            f"{cover.held}; the other {cover.held - protected} have none.")
    return line + _count_note(holding) + _product_note(cover, holding) + plan_stop_line(holding, plan, quote,
                                                                                       set_at=set_at, now=now)


def exits_of(rows: list, gtts: Optional[list], exchange: str, symbol: str, product: Optional[str]) -> list:
    """[O24e] The sell orders waiting to sell one option and product: SL
    orders waiting, sells open (a limit, or a stop that fired) and active
    GTT sells. An OCO GTT counts once, for its bigger leg: only one leg can
    fire. ``product`` None: any product. Each: {"id", "kind" (SL | SELL |
    GTT | OCO), "price", "units", "product"} (an OCO also "low" and "high")."""
    def same(value) -> bool:
        return product is None or str(value or "").upper() in ("", product)

    out = []
    for row in rows or []:
        if (row["exchange"] != exchange or row["tradingsymbol"] != symbol or row["transaction_type"] != "SELL"
                or not same(row.get("product"))):
            continue
        status, units = str(row.get("status") or "").upper(), _pending(row)
        if not units:
            continue
        prod = str(row.get("product") or "").upper()
        if status in WAITING and zerodha.carries_trigger(row):
            out.append({"id": f"kite:{row['order_id']}", "kind": "SL", "units": units,
                        "price": zerodha._num(row.get("trigger_price")) or 0.0, "product": prod})
        elif status == "OPEN" or status in WAITING:          # a limit, a fired stop, or an after-market sell
            out.append({"id": f"kite:{row['order_id']}", "kind": "SELL", "units": units,
                        "price": zerodha._num(row.get("price")) or 0.0, "product": prod})
    for gtt in gtts or []:
        condition = gtt.get("condition") or {}
        if (str(gtt.get("status") or "").lower() != "active"
                or str(condition.get("exchange") or "").upper() != exchange
                or str(condition.get("tradingsymbol") or "").upper() != symbol):
            continue
        legs = [leg for leg in gtt.get("orders") or [] if str(leg.get("transaction_type") or "").upper() == "SELL"
                and same(leg.get("product")) and int(leg.get("quantity") or 0) > 0]
        triggers = [float(v) for v in condition.get("trigger_values") or [] if v]
        if not legs or not triggers:
            continue
        big = max(legs, key=lambda leg: int(leg.get("quantity") or 0))
        units, prod = int(big.get("quantity") or 0), str(big.get("product") or "").upper()
        if str(gtt.get("type") or "").lower() == "two-leg" and len(triggers) > 1:
            out.append({"id": f"gtt:{gtt.get('id')}", "kind": "OCO", "units": units, "price": min(triggers),
                        "low": min(triggers), "high": max(triggers), "product": prod})
        else:
            out.append({"id": f"gtt:{gtt.get('id')}", "kind": "GTT", "units": units, "price": triggers[0],
                        "product": prod})
    return out


def _exit_list(exits: list) -> str:
    names = {"SL": "SL", "SELL": "sell", "GTT": "GTT"}
    parts = []
    for item in exits:
        if item["kind"] == "OCO":
            parts.append(f"OCO GTT {_px(item['low'])}/{_px(item['high'])} for {item['units']}")
        else:
            at = f" {_px(item['price'])}" if item.get("price") else ""
            parts.append(f"{names[item['kind']]}{at} for {item['units']}")
    return ", ".join(parts)


def excess_text(holding, exits: list) -> str:
    """[O24e] Sell orders that together would sell more than is held. [O24f]
    With where the count comes from when Zerodha's positions do not confirm it."""
    total, held = sum(e["units"] for e in exits), holding.open_qty
    return (f"⚠️ {_name(holding)}: your sell orders add up to {total} but you hold {held} "
            f"({_exit_list(exits)}).{_count_note(holding)} If more than {held} fill, the extra {total - held} is a new "
            f"short sale: Zerodha needs margin for it, and a short option can lose far more than its premium. An OCO "
            f"GTT links a stop and a target so that only one of them can fill.")


def none_held(positions: Optional[list], carried_known: bool) -> str:
    """[O24f] How sure "none held" is, for an option and product with no
    holding: ZERODHA (Zerodha's positions, read within POSITIONS_MAX_AGE,
    show none); ORDERS (they cannot be read now; today's orders, from the
    overnight list read earlier today, show none); UNREAD (they were not read
    today, so a position from an earlier day would not show)."""
    if positions is not None:
        return "ZERODHA"
    return "ORDERS" if carried_known else "UNREAD"


def _unverified(basis: str, held: str = "none held now") -> str:
    if basis == "UNREAD":
        return "Zerodha's positions could not be read today, so a position from an earlier day does not show."
    return f"Zerodha's positions could not be read just now, and your orders today show {held}."


def orphan_text(symbol: str, exits: list, basis: str = "ZERODHA") -> str:
    """[O24e] Sell orders still waiting on an option no longer held. [O24f]
    Said as fact only when Zerodha's positions show none (``none_held``);
    otherwise the order may be the protection of a holding not seen, so it is
    never "cancel it"."""
    total, many = sum(e["units"] for e in exits), len(exits) > 1
    orders = "these sell orders are" if many else "this sell order is"
    if basis == "ZERODHA":
        return (f"⚠️ {_option(symbol)}: Zerodha shows you hold none now, but {orders} still waiting: "
                f"{_exit_list(exits)}. If {'they trigger they sell' if many else 'it triggers it sells'} {total} you "
                f"do not have: a short sale. Cancel {'them' if many else 'it'} if the trade is over.")
    return (f"⚠️ {_option(symbol)}: {orders} waiting: {_exit_list(exits)}, and I could not check whether you hold "
            f"this option: {_unverified(basis)} If you hold it, "
            f"{'these orders are' if many else 'this order is'} its protection: keep {'them' if many else 'it'}. If "
            f"you don't, {'they' if many else 'it'} would sell {total} you do not have: a short sale.")


def product_text(symbol: str, product: str, exits: list, held: list, basis: str = "ZERODHA") -> str:
    """[O24f] Sell orders of a product that is not held, on an option held as
    another product (``held``: those holdings). Kite keeps a position per
    product: an MIS sell does not sell NRML units, it opens an MIS short."""
    total, many = sum(e["units"] for e in exits), len(exits) > 1
    other = held[0].product
    qty = sum(h.qty for h in held)
    line = (f"⚠️ {_option(symbol)}: {'these sell orders are' if many else 'this sell order is'} {product}: "
            f"{_exit_list(exits)}, but your {qty} are {other}. {'They' if many else 'It'} would not sell them")
    trigger = "if they trigger, they open" if many else "if it triggers, it opens"
    if basis == "ZERODHA":
        line += (f": {trigger} a new {product} short of {total} (Zerodha needs margin for it) and your {other} units "
                 f"stay as they are.")
    else:
        line += (f". {_unverified(basis, f'no {product} units held')} Unless you hold {product} units of it, "
                 f"{trigger} a new {product} short of {total}, and your {other} units stay as they are.")
    return line + f" A stop for them has to be {other}."


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


def _rest_note(cover: Optional[Cover], stop_id, rest: int) -> str:
    """[O24e] After a stop for part of a holding moved: what the other units
    have. [O24g] ``stop_id``: the stop moved, or the ids of several."""
    if cover is None or rest <= 0:
        return ""
    moved = {stop_id} if stop_id is None or isinstance(stop_id, str) else set(stop_id)
    others = [s for s in cover.stops if s["id"] not in moved]
    covered = min(sum(int(s["units"]) for s in others), rest)
    if covered >= rest:
        return f" The other {rest} keep their stop at {_triggers(others)}."
    if covered:
        return f" Of the other {rest}, {covered} have a stop at {_triggers(others)} and {rest - covered} have none."
    return f" The other {rest} have no stop."


def lowered_text(trip, old: float, new: float, reason: str = "FIRST", plan: Optional[Plan] = None, *,
                 units: Optional[int] = None, cover: Optional[Cover] = None, stop_id: Optional[str] = None) -> str:
    """A stop moved down and what it changes if it is hit. [O24e] ``units``:
    what that stop sells (when it covers only part of the holding, the
    result is for those units, and the rest is said apart)."""
    held = trip.open_qty
    part = units is not None and 0 < units < held
    qty = units if part else held
    before, after = _result_for(trip, old, qty), _result_for(trip, new, qty)
    name = _name(trip)
    if part:
        line = (f"⚠️ {name}: you moved your stop for {units} of your {held} down {_px(old)} → {_px(new)}. If it is "
                f"hit, on those {units}: {_signed(after)} instead of {_signed(before)}."
                + _rest_note(cover, stop_id, held - units))
    else:
        line = (f"⚠️ {name}: you moved your stop down {_px(old)} → {_px(new)}. If it is hit: "
                f"{_signed(after)} instead of {_signed(before)}.")
    return line + _lowered_why(reason, plan, units if part else None)


def _lowered_why(reason: str, plan: Optional[Plan], units: Optional[int] = None) -> str:
    if reason == "GUARD":
        return (f" It was guarding your buy price; now those {units} can end in a loss." if units else
                " It was guarding your buy price; now this trade can end in a loss.")
    if reason == "BELOW_PLAN" and plan is not None and plan.stop is not None:
        return f" That is under your plan stop {_px(plan.stop)}: the loss can now be bigger than planned."
    return " A stop moved down adds to the loss you chose when you placed it."


def moves_reason(trip, moves: list, plan: Optional[Plan], first: bool) -> Optional[str]:
    """[O24g] Why the stops moved down in one read are worth a message: the
    most serious of their reasons (GUARD, then BELOW_PLAN, then FIRST). The
    read is judged as one change, so a move is never dropped because another
    in the same read was looked at first. ``moves``: {"old", "new"}."""
    reasons = {lowered_reason(trip, m["old"], m["new"], plan, first) for m in moves}
    return next((r for r in ("GUARD", "BELOW_PLAN", "FIRST") if r in reasons), None)


def _held_moves(trip, moves: list) -> list:
    """(move, units) for the units held: each stop's units, at most what is left."""
    left, used = trip.open_qty, []
    for move in moves:
        take = min(int(move["units"]), left)
        if take > 0:
            used.append((move, take))
            left -= take
    return used


def _moves_why(reason: str, plan: Optional[Plan], used: list, trip) -> str:
    """[O24g] ``_lowered_why`` for several moves: which of them gave up the buy price, or went under the plan stop."""
    held = trip.open_qty
    if reason == "GUARD":
        guard = (trip.entry or 0.0) * (1 - GUARD_TOLERANCE)
        gave = [(m, u) for m, u in used if m["old"] >= guard > m["new"]]
        units = sum(u for _m, u in gave)
        many = len(gave) > 1
        return (f" Your stop{'s' if many else ''} at {_triggers([{'trigger': m['old']} for m, _u in gave])} "
                f"{'were' if many else 'was'} guarding your buy price; now "
                f"{'this trade' if units >= held else f'those {units}'} can end in a loss.")
    if reason == "BELOW_PLAN" and plan is not None and plan.stop is not None:
        below = [m for m, _u in used if m["new"] < plan.stop - 1e-9]
        return (f" {_triggers([{'trigger': m['new']} for m in below])} {'are' if len(below) > 1 else 'is'} under your "
                f"plan stop {_px(plan.stop)}: the loss can now be bigger than planned.")
    return " Stops moved down add to the loss you chose when you placed them."


def moved_text(trip, moves: list, reason: str = "FIRST", plan: Optional[Plan] = None, *,
               cover: Optional[Cover] = None) -> str:
    """[O24g] Stops moved down in one read (modified, a GTT changed, or one
    replaced): every move, and the result if they are hit, on the units they
    sell (each stop's own units, at most what is held). ``moves``: {"id",
    "old", "new", "units"}."""
    used = _held_moves(trip, moves)
    if len(used) == 1:
        move, units = used[0]
        return lowered_text(trip, move["old"], move["new"], reason, plan, units=units, cover=cover, stop_id=move["id"])
    held = trip.open_qty
    qty = sum(u for _m, u in used)
    old = sum(m["old"] * u for m, u in used) / qty
    new = sum(m["new"] * u for m, u in used) / qty
    before, after = _result_for(trip, old, qty), _result_for(trip, new, qty)
    each = [f"{_px(m['old'])} → {_px(m['new'])} for {u}" for m, u in used]
    on = f"on your {held}" if qty >= held else f"on those {qty} of your {held}"
    line = (f"⚠️ {_name(trip)}: you moved {len(used)} stops down: {', '.join(each[:-1])} and {each[-1]}. If they are "
            f"hit, {on}: {_signed(after)} instead of {_signed(before)}.")
    if qty < held:
        line += _rest_note(cover, [m["id"] for m, _u in used], held - qty)
    return line + _moves_why(reason, plan, used, trip)


def _average_trigger(stops: list) -> float:
    units = sum(int(s["units"]) for s in stops)
    return sum(s["trigger"] * int(s["units"]) for s in stops) / units if units else min(s["trigger"] for s in stops)


def changed_text(trip, gone: list, added: list, reason: str = "FIRST", plan: Optional[Plan] = None) -> str:
    """[O24f] Several stops taken away and new ones placed within
    REPLACE_WINDOW, lower on average: the change they make together. No new
    stop is paired with an old one (that would be a guess); the results are
    at each set's average trigger (by units), on the units both cover."""
    held = trip.open_qty
    qty = min(sum(int(s["units"]) for s in gone), sum(int(s["units"]) for s in added), held)
    before = _result_for(trip, _average_trigger(gone), qty)
    after = _result_for(trip, _average_trigger(added), qty)
    on = f"on your {held}" if qty >= held else f"on {qty} of your {held}"
    new = f"new ones at {_triggers(added)}" if len(added) > 1 else f"a new one at {_triggers(added)}"
    return (f"⚠️ {_name(trip)}: your stops changed: {_triggers(gone)} cancelled, {new}. If they are "
            f"hit, {on}: about {_signed(after)} instead of about {_signed(before)}."
            + _lowered_why(reason, plan, qty if qty < held else None))


def removed_text(holding, why: dict, plan: Optional[Plan], quote: Optional[dict] = None,
                 set_at: Optional[datetime] = None, *, now: Optional[datetime] = None) -> str:
    """[O24c] Units that had a stop and no longer have one. ``why``: {"kind":
    CANCELLED | SOLD | GTT_GONE | FIRED_CANCELLED | GONE, "trigger", "sold",
    "via" (GTT: [O24f] a GTT that fired)}."""
    name, trigger = _name(holding), why.get("trigger")
    kind = why.get("kind")
    if kind == "SOLD" and why.get("via") == "GTT":
        line = (f"⚠️ {name}: your GTT at {_px(trigger)} fired and sold {why.get('sold')}; the other "
                f"{holding.open_qty} have no stop now.")
    elif kind == "SOLD":
        line = (f"⚠️ {name}: your stop at {_px(trigger)} sold {why.get('sold')}; the {holding.open_qty} still held "
                f"have no stop.")
    elif kind == "FIRED_CANCELLED":
        line = (f"⚠️ {name}: your GTT at {_px(trigger)} fired, but its sell order was cancelled before it sold. No "
                f"other stop is in Zerodha: nothing limits this trade's loss now.")
    elif kind == "GTT_GONE":
        line = (f"⚠️ {name}: your GTT at {_px(trigger)} is no longer active and no other stop is in Zerodha. "
                f"Nothing limits this trade's loss now.")
    elif kind == "CANCELLED":
        line = (f"⚠️ {name}: your stop at {_px(trigger)} is cancelled and no other stop is in Zerodha. Nothing "
                f"limits this trade's loss now.")
    else:
        line = (f"⚠️ {name}: your stop at {_px(trigger)} is no longer waiting and no other stop is in Zerodha. "
                f"Nothing limits this trade's loss now.")
    return line + _count_note(holding) + plan_stop_line(holding, plan, quote, set_at=set_at, now=now)


def unfilled_text(holding, fired: dict, quote: Optional[dict] = None) -> str:
    """[O24c] A stop that fired and has not sold: the price is under its limit."""
    what = "GTT" if fired.get("kind") == "GTT" else "stop"
    limit = fired.get("limit")
    line = (f"🚨 {_name(holding)}: your {what} triggered at {_px(fired['trigger'])}, but its sell "
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


def _cover_note(cover: Optional[Cover], held: int) -> str:
    """[O24d] After an add: how much of the new size a stop covers ("" when all of it, or unknown)."""
    if cover is None or cover.state not in ("PARTIAL", "ABSENT"):
        return ""
    protected = cover.covered + cover.exiting
    return f" A stop covers {protected} of the {held} now held." if protected else " No stop order covers them yet."


def added_text(holding, *, added: int, added_px: float, first_px: Optional[float], plan: Optional[Plan],
               loss_before: Optional[float], quote: Optional[dict] = None, cover: Optional[Cover] = None,
               now: Optional[datetime] = None) -> str:
    """[O24c] A new buy order on an open trade: the new size and what the plan stop now costs."""
    under = (f", under your first buy at {_px(first_px)}" if first_px and added_px < first_px - 1e-9 else "")
    line = (f"➕ You added {added} to {_name(holding)} at {_px(added_px)}{under}: now "
            f"{holding.open_qty} at {_px(holding.entry)}.{_count_note(holding)}")
    covers = _cover_note(cover, holding.open_qty)
    if (plan is None or plan.stop is None) and cover is not None and cover.state == "FULL" and cover.stops:
        return line + (f" Your SL at {_triggers(cover.stops)} covers all {holding.open_qty}: if it sells there, about "
                       f"{_signed(_result_at_stops(holding, cover.stops))} with charges.")
    if plan is None or plan.stop is None:
        paid = (holding.entry or 0.0) * holding.open_qty
        line += f" At risk now: the whole {_amt(paid)}" + (f" (it was {_amt(loss_before)})." if loss_before else ".")
        return line + covers
    if level_state(plan.stop, quote, now) == "CROSSED":
        return line + plan_stop_line(holding, plan, quote, now=now) + covers
    loss = -_result_at(holding, plan.stop)
    line += f" If the plan stop {_px(plan.stop)} sells: about −{_amt(loss)} with charges"
    line += f" (it was −{_amt(loss_before)})." if loss_before is not None else "."
    if under:
        line += " Buying more of a falling option makes the loss at the stop bigger."
    return line + covers


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
    line = (f"⏳ 20 minutes to the {close} close and you still hold {_name(trip)} "
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
                 "Zerodha refuses an order, when sell orders could sell more than you hold, and before the close; "
                 "and if I cannot read your account for a while. Messages only: nothing is ever placed, changed "
                 "or cancelled for you.")
PROMPT_TEXT = ("🌅 Good morning. Log in to Zerodha to switch on today's trade watch: I'll message you when a buy "
               "has no stop, when a stop is moved down, cancelled or does not sell, and when Zerodha refuses an "
               "order. Messages only: nothing is ever placed for you.")
RECONNECT_TEXT = ("🔌 The trade watch stopped (the system restarted) and needs your Zerodha login again. "
                  "Your orders are untouched.")
QUIET_TOAST = ("Quiet for today. You will still hear when a stop is moved down, cancelled or does not sell, when "
               "Zerodha refuses an order, or when sell orders could sell more than you hold.")
# [O24f] The watch cannot see part of the book (``_health``), and then can again.
BLIND_TEXT = {
    "orders": ("⚠️ The trade watch cannot read your Zerodha orders since {since} (it tries every 5 s). Until it can, "
               "it cannot warn you about your trades. Your orders at Zerodha are not affected."),
    "positions": ("⚠️ The trade watch cannot read your Zerodha positions since {since}. Until it can, an option you "
                  "hold from an earlier day is not watched, and what you hold is counted from today's orders."),
    "gtts": ("⚠️ The trade watch cannot read your GTTs since {since}, so it cannot tell whether {names} {has} a stop: "
             "your SL orders do not cover all of {it}. Until it can, it does not warn you about {it}."),
}
READ_NAMES = {"orders": "Zerodha orders", "positions": "Zerodha positions", "gtts": "GTTs"}
BACK_TEXT = ("✅ The trade watch can read your {what} again (it could not from {since} to {now}). It checks what "
             "changed meanwhile now.")


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
    quote and last-trade times, and when we received it. [O24d] Also the
    bids shown ([price, quantity], best first), for what selling a whole
    holding would get."""
    depth = quote.get("depth") or {}

    def best(side):
        levels = depth.get(side) or []
        price = float(levels[0].get("price") or 0) if levels else 0.0
        qty = int(levels[0].get("quantity") or 0) if levels else 0
        return (price, qty) if price > 0 else (None, None)

    bid, bid_qty = best("buy")
    ask, ask_qty = best("sell")
    bids = [[float(level.get("price") or 0), int(level.get("quantity") or 0)] for level in depth.get("buy") or []]
    return {"bid": bid, "ask": ask, "ltp": float(quote.get("last_price") or 0) or None, "bid_qty": bid_qty,
            "ask_qty": ask_qty, "bids": [b for b in bids if b[0] > 0 and b[1] > 0],
            "quote_at": _stamp(quote.get("timestamp")), "trade_at": _stamp(quote.get("last_trade_time")),
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


@dataclass
class _Entry:
    """[O24d] One message in the outbox, as read for sending."""
    key: str
    kind: str
    context: Optional[str]
    attempts: int
    outcome: Optional[str]
    error: Optional[str]
    created_at: str
    last_attempt_at: Optional[str]
    episode: Optional[str]
    detected_at: Optional[str]
    event_at: Optional[str]


# [O24d] The sender: one at a time. ``pending``: something may still be due
# (True after a start, so what a restart left is looked at).
_outbox: dict = {"task": None, "again": False, "pending": True}


def _now() -> datetime:
    """The watch's clock: the last tick's time plus the time since (the
    tests drive the tick's time)."""
    if _state.clock is None:
        return datetime.now(IST)
    at, mono = _state.clock
    return at + timedelta(seconds=max(_time.monotonic() - mono, 0.0))


async def _enqueue_many(db_path: str, day: str, items: list, now: datetime, by: Optional[str] = None) -> int:
    """[O24d] Put messages in the outbox, each once: its key is its identity
    (the trade, the order, the incident). ``items``: (key, kind, subject,
    context, event_at, episode). The text is built when it is sent, from the
    book read then (``_build``). Returns how many were new."""
    fresh = [item for item in items if item[0] not in _state.enqueued]
    if not fresh:
        return 0
    async with aiosqlite.connect(db_path) as db:
        new = await _insert_outbox(db, day, fresh, now, by)
        await db.commit()
    _noted(fresh, new)
    return len(new)


async def _insert_outbox(db, day: str, items: list, now: datetime, by: Optional[str] = None) -> list:
    """[O24e] Write outbox rows on an open connection; the caller commits
    (so a plan version and its message go in one transaction). The keys
    that were new. [O24g] ``by``: the tick that found them (poll | stream)."""
    new = []
    for key, kind, subject, context, event_at, episode in items:
        exchange, symbol, position = _who(subject)
        cursor = await db.execute(
            "INSERT OR IGNORE INTO partner_watch_messages(message_key,session_date,kind,exchange,tradingsymbol,"
            "position_key,created_at,sent,text,summary,attempts,outcome,event_at,detected_at,context,episode,"
            "priority,detected_by) VALUES(?,?,?,?,?,?,?,0,'',NULL,0,?,?,?,?,?,?,?)",
            (key, day, kind, exchange, symbol, position, now.isoformat(), QUEUED,
             event_at.isoformat() if event_at else None, now.isoformat(), json.dumps(context, default=str),
             episode, PRIORITY.get(kind, 5), by))
        if cursor.rowcount == 1:
            new.append(key)
    return new


def _noted(items: list, new: list) -> None:
    """After a commit: the keys are in the outbox; new ones wake the sender."""
    _state.enqueued.update(item[0] for item in items)
    if new:
        _outbox["pending"] = _outbox["again"] = True


async def _enqueue(db_path: str, key: str, day: str, kind: str, subject, now: datetime, *, context: dict,
                   event_at: Optional[datetime] = None, episode: Optional[str] = None) -> bool:
    return bool(await _enqueue_many(db_path, day, [(key, kind, subject, context, event_at, episode)], now))


def _kick() -> asyncio.Task:
    """[O24d] Start sending what is due. A sender already running takes
    another look before it stops."""
    loop = asyncio.get_running_loop()
    task = _outbox["task"]
    if task is not None and not task.done() and task.get_loop() is loop:
        _outbox["again"] = True
        return task
    _outbox["again"] = False
    task = background_tasks.spawn(_drain(settings.DB_PATH), name="partner_watch_outbox", loop=loop)
    task.add_done_callback(_drain_done)
    _outbox["task"] = task
    return task


def _flush() -> None:
    """[O24d] A tick that reads no book (outside the session, no login, a
    failed read) still sends what is due: a login prompt to retry, or what a
    restart left. A message about a trade waits for a fresh book read
    (``_build``). A tick that reads the book starts the sender only after its
    view is built, so nothing due goes out on the read before it."""
    if _outbox["pending"]:
        _kick()


def _drain_done(task: asyncio.Task) -> None:
    if task.cancelled():
        _outbox["pending"] = True         # stopped part-way (a shutdown): look again on the next start or tick
    elif task.exception() is not None:
        _outbox["pending"] = True
        logger.error("partner_watch_delivery_failed err=%s", type(task.exception()).__name__)


async def _drain(db_path: str) -> int:
    """[O24d] Send what is due, most urgent first. A retry not due yet, or a
    message waiting for a fresh book read, keeps the outbox pending: the next
    tick (every 5 s, all day) looks again."""
    sent = 0
    for _round in range(MAX_ATTEMPTS + 2):
        _outbox["again"] = False
        entries = await _due(db_path, _now())
        await _prefetch(entries, _now())
        waiting = again = False
        for entry in entries:
            status = await _deliver(db_path, entry, _now())
            sent += status == SENT
            waiting = waiting or status in (WAIT, LATER, RETRY)
            again = again or (status == RETRY and RETRY_GAP <= timedelta(0))
        if not (_outbox["again"] or again):
            _outbox["pending"] = waiting
            return sent
    _outbox["pending"] = True
    return sent


async def _due(db_path: str, now: datetime) -> list:
    """Today's messages that may still go: queued, or provably unsent with tries left."""
    await init_partner_watch_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT message_key, kind, context, attempts, outcome, error, created_at, last_attempt_at, episode, "
            "detected_at, event_at FROM partner_watch_messages WHERE session_date=? AND sent=0 AND outcome IN "
            "('queued','unsent_connect','rate_limited','rejected') AND attempts<? ORDER BY priority, created_at",
            (now.date().isoformat(), MAX_ATTEMPTS))).fetchall()
    entries = [_Entry(*row) for row in rows]
    return [e for e in entries if e.outcome == QUEUED or _retryable(e.outcome, e.error)]


async def _close(db_path: str, key: str, outcome: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_watch_messages SET outcome=? WHERE message_key=?", (outcome, key))
        await db.commit()


async def _deliver(db_path: str, entry: _Entry, now: datetime) -> str:
    """[O24d] One message: expired (past LIFETIME_SEC), muted (quiet today),
    WAIT (no fresh book read to build it from), superseded (no longer true:
    not sent), or sent with the text built now. Telegram's own outcome is
    kept; a provably unsent one is tried again RETRY_GAP later, rebuilt."""
    created, last = _dt(entry.created_at), _dt(entry.last_attempt_at)
    if created is not None and now - created > timedelta(seconds=LIFETIME_SEC.get(entry.kind, 300)):
        await _close(db_path, entry.key, "expired")
        logger.info("partner_watch_expired kind=%s key=%s attempts=%d", entry.kind, entry.key, entry.attempts)
        return DONE
    if entry.outcome != QUEUED and last is not None and now - last < RETRY_GAP:
        return LATER
    if (entry.kind not in QUIET_KEEPS and entry.kind not in ALWAYS_SENT
            and await quiet(db_path, now.date().isoformat())):
        await _close(db_path, entry.key, "muted")
        return MUTED
    # [O24e] Building awaits prices and the database, and a newer book read can arrive meanwhile: the message is
    # sent only if the view it was built from is still the latest, checked after the build and again after the
    # row is marked; otherwise it is built again from the newer view.
    for _try in range(BUILD_TRIES):
        view = _state.view
        try:
            built = await _build(db_path, entry, now, view)
        except Exception as exc:      # a message that cannot be built now waits (and expires); never the tick
            logger.warning("partner_watch_build_failed kind=%s key=%s err=%s", entry.kind, entry.key,
                           type(exc).__name__)
            return WAIT
        if built == WAIT:
            return WAIT
        if not _still(entry, view):
            now = _now()
            continue
        if built is None:
            await _close(db_path, entry.key, "superseded")
            logger.info("partner_watch_superseded kind=%s key=%s", entry.kind, entry.key)
            return DONE
        text, summary, keyboard = built
        await _mark(db_path, entry, text, summary, now)
        if _still(entry, view):
            break
        await _unmark(db_path, entry)
        now = _now()
    else:
        logger.info("partner_watch_build_again_later kind=%s key=%s", entry.kind, entry.key)
        return WAIT                   # the book kept changing while it was built: the next tick tries again
    from partner_bot import send_partner_result
    result = await send_partner_result(text, kind=f"watch_{entry.kind.lower()}", reply_markup=keyboard)
    delivered = bool(result.delivered)
    state = getattr(result, "state", None) or ("acknowledged" if delivered else "failed")
    error = getattr(result, "error", None)
    acked = datetime.now(IST)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_watch_messages SET sent=?, outcome=?, error=?, sent_at=?, message_id=? "
                         "WHERE message_key=?",
                         (int(delivered), state, error, acked.isoformat() if delivered else None,
                          getattr(result, "message_id", None), entry.key))
        await db.commit()
    event, detected = _dt(entry.event_at), _dt(entry.detected_at)
    logger.info("partner_watch_message kind=%s key=%s state=%s detect_s=%s queue_s=%s", entry.kind, entry.key, state,
                f"{(detected - event).total_seconds():.1f}" if event and detected else "-",
                f"{(now - detected).total_seconds():.1f}" if detected else "-")
    if delivered:
        _state.delivered += 1
        return SENT
    return RETRY if _retryable(state, error) else DONE


def _still(entry: _Entry, view) -> bool:
    """[O24e] Whether the view a message was built from is still the latest (fixed texts need none)."""
    return entry.kind in ALWAYS_SENT or _state.view is view


async def _mark(db_path: str, entry: _Entry, text: str, summary: Optional[str], now: datetime) -> None:
    """The row is "attempting" (with its text) before the send: a crash after it is never repeated."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_watch_messages SET attempts=attempts+1, outcome='attempting', text=?, "
                         "summary=?, last_attempt_at=? WHERE message_key=?",
                         (text, summary, now.isoformat(), entry.key))
        await db.commit()


async def _unmark(db_path: str, entry: _Entry) -> None:
    """[O24e] Not sent after all (a newer view came): the row as it was."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_watch_messages SET attempts=?, outcome=?, last_attempt_at=? "
                         "WHERE message_key=?", (entry.attempts, entry.outcome, entry.last_attempt_at, entry.key))
        await db.commit()


async def _build(db_path: str, entry: _Entry, now: datetime, view=None):
    """[O24d] The message from a book read (``view``, the latest when the
    build starts): (text, summary, keyboard); None when it is no longer true
    (the trade closed, a stop is back, the size changed...); WAIT when there
    is no fresh read to build it from."""
    try:
        context = json.loads(entry.context or "null")
    except ValueError:
        context = None
    if not isinstance(context, dict):
        return None
    if entry.kind in ALWAYS_SENT:
        return context.get("text") or "", context.get("summary"), context.get("keyboard")
    if (view is None or view.day != now.date().isoformat() or now - view.at > VIEW_FRESH
            or (_state.tick_at is not None and view.at < _state.tick_at)):
        return WAIT                       # no book read, or the last tick's is still being read
    builder = _BUILDERS.get(entry.kind)
    return await builder(db_path, context, view, now) if builder else None


_QUOTED = ("PLAN", "ADDED", "NO_STOP", "PARTIAL", "REMOVED", "UNFILLED")


async def _prefetch(entries: list, now: datetime) -> None:
    """[O24d] One quote read for the holdings the due messages are about (a
    quote from the last 15 s is used as it is)."""
    view, market = _state.view, _state.market
    if view is None or market is None:
        return
    wanted: dict = {}
    for entry in entries:
        holding = view.holding(entry.episode) if entry.kind in _QUOTED and entry.episode else None
        if holding is None or holding.tradingsymbol in wanted:
            continue
        cached = _state.quotes.get(holding.tradingsymbol)
        if cached and now - cached["looked_at"] <= QUOTE_FRESH:
            continue
        contract = contract_of(holding.exchange, holding.tradingsymbol)
        if contract is not None:
            wanted[holding.tradingsymbol] = contract
    if wanted:
        await _quotes(market, list(wanted.values()), now)


def _meta(row) -> dict:
    version, computed_at, reason, qty, entry, bought, sold, buy_ids, plan_json = row
    return {"version": version, "computed_at": computed_at, "reason": reason, "qty": qty, "entry": entry,
            "bought": bought, "sold": sold, "buy_ids": json.loads(buy_ids), "plan": Plan(**json.loads(plan_json))}


_META_COLS = "version, computed_at, reason, qty, entry, bought, sold, buy_ids, plan_json"


async def _store_plan(db_path: str, trip: Trip, plan: Plan, now: datetime, reason: str, *,
                      announce: Optional[tuple] = None, day: Optional[str] = None, by: Optional[str] = None) -> dict:
    """[O24c] Add a plan version. The first ("BUY") is never replaced: when
    one is stored already, it is returned instead. [O24e] ``announce``: its
    message (an outbox item), written in the same transaction, so a plan is
    never stored without the message it owes (a failed write leaves
    neither, and the plan is tried again)."""
    async with aiosqlite.connect(db_path) as db:
        latest = await (await db.execute(
            f"SELECT {_META_COLS} FROM partner_watch_plan_versions WHERE position_key=? ORDER BY version DESC LIMIT 1",
            (trip.key,))).fetchone()
        if latest is not None and reason == "BUY":
            meta = _meta(latest)
        else:
            version = (latest[0] if latest else 0) + 1
            values = (trip.key, version, now.date().isoformat(), trip.exchange, trip.tradingsymbol, now.isoformat(),
                      reason, plan.qty, plan.entry, trip.bought, trip.sold, json.dumps(list(trip.buys)),
                      json.dumps(asdict(plan)))
            await db.execute("INSERT INTO partner_watch_plan_versions(position_key,version,session_date,exchange,"
                             "tradingsymbol,computed_at,reason,qty,entry,bought,sold,buy_ids,plan_json) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            meta = _meta(values[1:2] + values[5:])
        new = await _insert_outbox(db, day or now.date().isoformat(), [announce], _now(), by) if announce else []
        await db.commit()
    if announce:
        _noted([announce], new)
    return meta


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
    """[O24c] One holding's protection over time. [O24d] One per trade (its
    episode), remembered in partner_watch_state so that a restart still knows
    what covered it."""
    since: datetime                 # from when the units held need a stop (the newest buy order's first fill)
    held: int
    state: Optional[str] = None
    state_at: Optional[datetime] = None
    covered_once: bool = False
    full_once: bool = False
    stops: list = field(default_factory=list)      # the waiting stops when it was last covered
    full_ids: list = field(default_factory=list)   # their ids when it was last fully covered
    lowered_told: bool = False                     # its first stop move down was told
    saved: Optional[str] = None                    # what partner_watch_state holds for it
    # [O24f] For replacements (``_track_stops``): the stops at the last look, and within REPLACE_WINDOW the stops
    # taken away and the stops placed (each with "at"). ``tracked``: ``seen`` is a real look (not a new guard's).
    seen: list = field(default_factory=list)
    withdrawn: list = field(default_factory=list)
    fresh: list = field(default_factory=list)
    tracked: bool = False

    def memory(self) -> str:
        return json.dumps({"covered_once": self.covered_once, "full_once": self.full_once, "stops": self.stops,
                           "full_ids": self.full_ids, "lowered_told": self.lowered_told, "seen": self.seen,
                           "withdrawn": self.withdrawn, "fresh": self.fresh, "tracked": self.tracked},
                          sort_keys=True)


@dataclass
class View:
    """[O24d] One tick's reconciled book. Every message is built from the
    latest one just before it is sent."""
    day: str
    at: datetime
    rows: list
    trips: list
    holdings: list
    covers: dict = field(default_factory=dict)     # holding key -> Cover
    gtts: Optional[list] = None                    # [O24e] the GTT list when read within GTT_REFRESH, else None
    positions: Optional[list] = None               # [O24f] Zerodha's positions (None: not read within POSITIONS_MAX_AGE)
    carried_known: bool = False                    # [O24f] the overnight positions were read today

    def holding(self, episode: Optional[str]) -> Optional[Holding]:
        return next((h for h in self.holdings if _episode(self.day, h) == episode), None)


def _episode(day: str, holding) -> str:
    """[O24d] The trade a message is about: its round trip (keyed by the
    opening buy's order id), else the holding Zerodha shows; with the day, so
    a position carried in is a new one each day."""
    key = getattr(holding, "position_key", None)
    return f"{day}:{key}" if key else f"{day}:zerodha:{holding.hkey}"


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
    cash_tries: int = 0
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
    looks_task: Optional[asyncio.Task] = None
    planned: dict = field(default_factory=dict)       # trip key -> the latest plan version (``_meta``)
    plan_tasks: dict = field(default_factory=dict)    # trip key -> the task computing its first plan
    plan_tries: dict = field(default_factory=dict)    # trip key -> plans started
    guards: dict = field(default_factory=dict)        # episode -> _Guard
    fired_seen: dict = field(default_factory=dict)    # order_id -> when it was first seen fired and unfilled
    exit_seen: dict = field(default_factory=dict)     # [O24e] exit-size message key -> when first seen
    close_checked: set = field(default_factory=set)   # episodes
    enqueued: set = field(default_factory=set)        # message keys already in the outbox
    view: Optional[View] = None
    market: Optional[Market] = None
    clock: Optional[tuple] = None                     # (the last tick's time, its monotonic time)
    tick_at: Optional[datetime] = None                # the last tick (its view is the one to build from)
    delivered: int = 0
    size_shares: Optional[list] = None                # the usual-size history before today
    last_tick_ms: Optional[float] = None
    unread: dict = field(default_factory=dict)        # [O24f] read -> its first failure since it last worked
    detected_by: Optional[str] = None                 # [O24g] the tick now running: poll | stream
    blind: dict = field(default_factory=dict)         # [O24f] read -> the failure the partner was told of (BLIND)


_state = _State()
_market = Market()


def reset() -> None:
    """Forget the in-memory watch (tests; a new day; a new login). [O24d]
    The outbox is in the database: what is still due is sent from the next
    book read, rebuilt."""
    global _state
    for task in [*_state.plan_tasks.values(), _state.looks_task]:
        if task is not None and not task.done():
            try:
                task.cancel()
            except RuntimeError:          # its loop is gone (tests)
                pass
    _state = _State()
    _outbox["pending"] = True


async def settle() -> None:
    """Wait for the plans being computed, the looks being recorded and the
    messages being sent (tests, shutdown)."""
    loop = asyncio.get_running_loop()
    for _round in range(20):
        tasks = [t for t in [*_state.plan_tasks.values(), _state.looks_task, _outbox["task"]]
                 if t is not None and not t.done() and t.get_loop() is loop]
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)


async def _wait_within(tasks: list, cap: float, deadline: float) -> None:
    """Wait for tasks up to ``cap`` seconds, never past the tick's deadline."""
    loop = asyncio.get_running_loop()
    tasks = [t for t in tasks if t is not None and not t.done() and t.get_loop() is loop]
    left = min(cap, deadline - _time.monotonic())
    if tasks and left > 0:
        await asyncio.wait(tasks, timeout=left)


async def _book(path: str, deadline: Optional[float] = None):
    """[O24c] One read of the partner's book, bounded by READ_TIMEOUT_SEC.
    [O24d] And by what is left of the tick's budget: with less than
    MIN_READ_SEC left, an optional read waits for the next tick."""
    timeout = READ_TIMEOUT_SEC
    if deadline is not None:
        timeout = min(timeout, deadline - _time.monotonic())
        if timeout < MIN_READ_SEC:
            raise zerodha.BrokerError("budget", path)
    try:
        return await asyncio.wait_for(zerodha._read(path), timeout)
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


async def _seed_cash(deadline: Optional[float] = None) -> None:
    """The day's cash, read after the book; tried again (CASH_TRIES) while unknown."""
    if _state.cash is not None or _state.cash_tries >= CASH_TRIES:
        return
    try:
        account = zerodha.account_row(await _book("/user/margins/equity", deadline))
    except zerodha.BrokerError as exc:
        if exc.code == "TokenException":
            raise
        if exc.code != "budget":
            _state.cash_tries += 1
            logger.warning("partner_watch_cash_unread code=%s", exc.code)
        return
    _state.cash_tries += 1
    from partner_insights import cash_of
    _state.cash = cash_of(account) if account else None


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


async def _refresh_book(rows: list, now: datetime, deadline: Optional[float] = None) -> None:
    """[O24c] The trade book when a fill is new or not shown yet; Zerodha's
    positions after a new fill, every 30 s and while they differ.

    [O24d] A read that fails, or finds no budget left, keeps the last one and
    is tried on the next tick: the trade book only grows, and a fill newer
    than a positions read keeps the orders' count over it (``holdings_of``).
    A positions read older than POSITIONS_MAX_AGE confirms nothing."""
    sig = tuple(sorted((str(r["order_id"]), int(r.get("filled_quantity") or 0)) for r in rows
                       if int(r.get("filled_quantity") or 0) > 0))
    new_fill = sig != _state.fills_sig
    _state.fills_sig = sig
    if sig and (new_fill or not _state.trades_complete):
        try:
            _state.trades = list(await _book("/trades", deadline) or [])
            _state.trades_complete = _trades_cover(rows, _state.trades)
        except zerodha.BrokerError as exc:
            if exc.code == "TokenException":
                raise
            logger.warning("partner_watch_trades_unread code=%s", exc.code)
            _state.trades_complete = False
    if (new_fill or _state.differs or not _state.carried_known or _state.positions_at is None
            or now - _state.positions_at >= POSITIONS_EVERY):
        try:
            positions = zerodha.option_positions(await _book("/portfolio/positions", deadline))
        except zerodha.BrokerError as exc:
            if exc.code == "TokenException":
                raise
            logger.warning("partner_watch_positions_unread code=%s", exc.code)
            _read_failed("positions", exc.code, now)
        else:
            _state.positions, _state.positions_at = positions, now
            _state.unread.pop("positions", None)
            if not _state.carried_known:
                _state.carried = [p for p in positions if p["overnight_quantity"] > 0]
                _state.carried_known = True
    if _state.positions_at is not None and now - _state.positions_at > POSITIONS_MAX_AGE:
        _state.positions, _state.positions_at = None, None


# [O24g] One tick at a time: the scheduler's (every PARTNER_WATCH_POLL_SEC) skips while another runs; one the
# order stream wakes waits for it. ``again``: a wake came while the woken tick was running.
_tick: dict = {"lock": None, "loop": None, "woken": None, "again": False, "last": 0.0}


def _tick_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if _tick["lock"] is None or _tick["loop"] is not loop:
        _tick["lock"], _tick["loop"] = asyncio.Lock(), loop
    return _tick["lock"]


async def watch_tick(now: Optional[datetime] = None, *, market: Optional[Market] = None,
                     woken: Optional[str] = None) -> dict:
    """One look at the partner's book (see the module doc). [O24d] Its reads
    and waits share TICK_BUDGET_SEC. It finds what to say and puts it in the
    outbox; the sender goes beside it, and the tick waits for it only within
    the budget. [O24g] One at a time (``_tick_lock``); ``woken``: the order
    stream asked for it (``wake``). Each tick's timing goes to the day's tick
    statistics (``_ticks``)."""
    lock = _tick_lock()
    if lock.locked() and woken is None:
        _ticks.note(_state.day, "SKIPPED", "busy", None, None)
        return {"status": "SKIPPED", "reason": "busy"}
    async with lock:
        _tick["last"] = _time.monotonic()
        result = await _watch_tick(now, market=market, woken=woken)
    if result.get("status") != "SKIPPED" or result.get("reason") not in ("disabled", "outside_session", "holiday"):
        _ticks.note(_state.day, result.get("status"), result.get("reason"), result.get("ms"), woken)
        await _ticks.save(settings.DB_PATH, _now())
    return result


def wake(reason: str = "order") -> None:
    """[O24g] Something changed at Zerodha (an order update on the stream):
    read the book now, not at the next 5 s tick. Wakes arriving while a
    woken tick runs are one more tick after it; woken ticks are WAKE_GAP_SEC
    apart (Kite's read limits)."""
    if not enabled():
        return
    _tick["again"] = True
    task = _tick["woken"]
    if task is not None and not task.done() and task.get_loop() is asyncio.get_running_loop():
        return
    _tick["woken"] = background_tasks.spawn(_woken(reason), name="partner_watch_woken")


async def _woken(reason: str) -> None:
    while _tick["again"]:
        _tick["again"] = False
        gap = WAKE_GAP_SEC - (_time.monotonic() - _tick["last"])
        if gap > 0:
            await asyncio.sleep(gap)
        try:
            await watch_tick(_now(), woken=reason)
        except Exception as exc:          # the 5 s tick goes on regardless
            logger.warning("partner_watch_woken_tick_failed err=%s", type(exc).__name__)


async def _watch_tick(now: Optional[datetime] = None, *, market: Optional[Market] = None,
                      woken: Optional[str] = None) -> dict:
    started = _time.monotonic()
    deadline = started + TICK_BUDGET_SEC
    now = (now or datetime.now(IST)).astimezone(IST)
    if not enabled():
        return {"status": "SKIPPED", "reason": "disabled"}
    db_path = settings.DB_PATH
    await init_partner_watch_db(db_path)
    day = now.date().isoformat()
    if _state.day != day:
        reset()
        _state.day = day
    _state.clock, _state.tick_at = (now, started), now
    market = market or (_state.market if woken else None) or _market
    market.roll(day)
    minute = now.hour * 60 + now.minute
    if not OPEN_MIN <= minute <= zerodha.CLOSE_MIN:
        _flush()
        return {"status": "SKIPPED", "reason": "outside_session"}
    if not await _is_trading_day(now):
        _flush()
        return {"status": "SKIPPED", "reason": "holiday"}
    if not zerodha.connected(now):
        await _reconnect_prompt(db_path, day, now)
        _flush()
        return {"status": "SKIPPED", "reason": "not_connected"}
    login = zerodha.status(now).get("login_at")
    if login != _state.login_at:
        reset()
        _state.day, _state.login_at, _state.clock, _state.tick_at = day, login, (now, started), now
    _state.market = market
    _state.detected_by = "stream" if woken else "poll"
    import partner_watch_stream
    partner_watch_stream.ensure()
    before = _state.delivered
    try:
        try:
            read_at = _time.monotonic()
            rows = zerodha.option_orders(await _book("/orders", deadline))
        except zerodha.BrokerError as exc:
            _read_failed("orders", exc.code, now)
            raise
        _ticks.orders_ms(_state.day, (_time.monotonic() - read_at) * 1000)
        _state.unread.pop("orders", None)
        await _refresh_book(rows, now, deadline)
        await _seed_cash(deadline)
    except zerodha.BrokerError as exc:
        logger.warning("partner_watch_read_failed code=%s", exc.code)
        await _enqueue_many(db_path, day, await _health(db_path, day, now), now)
        _flush()
        await _wait_within([_outbox["task"]], DELIVERY_INLINE_SEC, deadline)
        return {"status": "FAILED", "reason": exc.code}
    plans = await _events(db_path, day, rows, now, market, deadline)
    _state.seeded = True
    _state.orders = {r["order_id"]: (str(r.get("status") or "").upper(), zerodha._num(r.get("trigger_price")) or 0.0,
                                     int(r.get("filled_quantity") or 0)) for r in rows}
    await _wait_within(plans, PLAN_INLINE_SEC, deadline)
    await _wait_within([_outbox["task"]], DELIVERY_INLINE_SEC, deadline)
    await _wait_within([_state.looks_task], TICK_BUDGET_SEC, deadline)      # shadow only: whatever budget is left
    elapsed = (_time.monotonic() - started) * 1000
    _state.last_tick_ms = round(elapsed, 1)
    if elapsed > TICK_BUDGET_SEC * 1000 + 250:
        logger.warning("partner_watch_tick_slow ms=%.0f", elapsed)
    return {"status": "COMPLETED", "sent": _state.delivered - before, "ms": _state.last_tick_ms}


class _TickStats:
    """[O24g] This process's ticks for the day: how many, how they ended,
    how long they and the order-book read took, and the order stream's own
    numbers. Saved every TICK_STATS_EVERY to partner_watch_state as
    ``ticks:<day>:<process start>`` (a restart starts a new part), for
    partner_watch_report. Timings are kept up to TICK_SAMPLES."""

    def __init__(self) -> None:
        self.day: Optional[str] = None
        self.started = datetime.now(IST).isoformat()
        self.counts: dict = {}
        self.tick_ms: list = []
        self.read_ms: list = []
        self.saved_at: Optional[datetime] = None

    def _for(self, day: Optional[str]) -> bool:
        if day is None:
            return False
        if day != self.day:
            self.day, self.counts, self.tick_ms, self.read_ms, self.saved_at = day, {}, [], [], None
        return True

    def note(self, day: Optional[str], status: Optional[str], reason: Optional[str], ms: Optional[float],
             woken: Optional[str]) -> None:
        if not self._for(day):
            return
        name = f"{status}:{reason}" if reason else str(status)
        self.counts[name] = self.counts.get(name, 0) + 1
        if woken:
            self.counts["woken"] = self.counts.get("woken", 0) + 1
        if ms is not None and len(self.tick_ms) < TICK_SAMPLES:
            self.tick_ms.append(round(ms))

    def orders_ms(self, day: Optional[str], ms: float) -> None:
        if self._for(day) and len(self.read_ms) < TICK_SAMPLES:
            self.read_ms.append(round(ms))

    async def save(self, db_path: str, now: datetime, force: bool = False) -> None:
        if self.day is None or self.day != _state.day or (
                not force and self.saved_at is not None and now - self.saved_at < TICK_STATS_EVERY):
            return
        import partner_watch_stream
        value = json.dumps({"started": self.started, "counts": self.counts, "tick_ms": self.tick_ms,
                            "read_ms": self.read_ms, "stream": partner_watch_stream.stats()}, sort_keys=True)
        try:
            await _set_state(db_path, f"ticks:{self.day}:{self.started}", value, now)
            self.saved_at = now
        except Exception as exc:          # statistics never fail a tick
            logger.warning("partner_watch_tick_stats_failed err=%s", type(exc).__name__)


_ticks = _TickStats()


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


async def _events(db_path: str, day: str, rows: list, now: datetime, market: Market, deadline: float) -> list:
    """What this book read has to say. Protection first; then the view the
    messages are built from and the outbox; then the plans (returned: the
    tasks started) and the shadow looks."""
    trips = trips_from_fills(fills_of(rows, _state.trades), _state.carried, now.date())
    holdings = holdings_of(trips, _state.positions, _state.positions_at)
    _note_differences(holdings)
    seeded = _state.seeded
    out: list = []
    moves: dict = {}          # [O24g] holding key -> its SL orders modified down in this read (told with the guard)
    # 1. Refusals and stop moves are told only when seen happening (not from a book read after a restart).
    for row in rows:
        before = _state.orders.get(row["order_id"])
        status = str(row.get("status") or "").upper()
        if status == "REJECTED" and seeded and (before is None or before[0] != "REJECTED"):
            out.append(_refused(day, row, holdings, trips))
        trigger = zerodha._num(row.get("trigger_price")) or 0.0
        if row["transaction_type"] != "SELL" or status not in WAITING or trigger <= 0:
            continue
        old = _state.stop_trigger.get(row["order_id"])
        _state.stop_trigger[row["order_id"]] = trigger
        holding = _holding_for(holdings, row)
        if seeded and old is not None and trigger < old - 1e-6 and holding is not None:
            moves.setdefault(holding.hkey, []).append(
                {"id": f"kite:{row['order_id']}", "old": old, "new": trigger,
                 "units": min(_pending(row), holding.qty), "at": row.get("updated_at")})
    # 2. Protection, trade by trade; then [O24e] sell orders bigger than what is held, or with nothing held.
    if not _gtts_fresh(now, GTT_REFRESH) and _state.gtts_tried_at != now:
        await _read_gtts(now, deadline)
    covers = {}
    for holding in holdings:
        covers[holding.hkey] = await _guard(db_path, day, holding, rows, now, deadline, seeded, out,
                                            moves.get(holding.hkey))
    found: list = []
    _exits(day, rows, _state.gtts if _gtts_fresh(now, GTT_REFRESH) else None, holdings, now, found)
    if _state.gtts_at != now and any(_counts_gtt(item) for item in found):
        # [O24g] A sell-order claim that counts a GTT is made only from a GTT list read in this tick (it is reused
        # for GTT_REFRESH, and a GTT deleted since was still in it). Without that read, those claims wait a tick.
        if _state.gtts_tried_at != now:
            await _read_gtts(now, deadline)
        if _state.gtts_at == now:
            found = []
            _exits(day, rows, _state.gtts, holdings, now, found)
        else:
            found = [item for item in found if not _counts_gtt(item)]
    out.extend(found)
    out.extend(await _health(db_path, day, now, holdings, covers))
    live = {_episode(day, h) for h in holdings}
    for key in [k for k in _state.guards if k not in live]:
        del _state.guards[key]
    # 3. The close.
    if now.hour * 60 + now.minute >= CLOSE_WARN_MIN:
        for holding in holdings:
            episode = _episode(day, holding)
            if episode not in _state.close_checked:
                _state.close_checked.add(episode)
                out.append((f"close:{episode}", "CLOSE", holding, {"episode": episode}, None, episode))
    # The view every message is built from; then the outbox goes.
    _state.view = View(day=day, at=now, rows=rows, trips=trips, holdings=holdings, covers=covers,
                       gtts=_state.gtts if _gtts_fresh(now, GTT_REFRESH) else None, positions=_state.positions,
                       carried_known=_state.carried_known)
    await _enqueue_many(db_path, day, out, now, _state.detected_by)
    if _outbox["pending"]:
        _kick()
    # 4. Plans: a new trade's first plan beside the tick; later versions here.
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
            try:
                meta = await _load_meta(db_path, trip.key)
            except Exception as exc:  # [O24e] read again next tick; the tick goes on
                logger.warning("partner_watch_plan_read_failed key=%s err=%s", trip.key, type(exc).__name__)
                continue
            if meta is not None:
                _state.planned[trip.key] = meta          # a restart: the plan stored before it
            else:
                holding = next((h for h in holdings if h.position_key == trip.key), None)
                started.append(_start_plan(db_path, day, trip, holding, trips, now, market))
                continue
        if meta is not None:
            try:
                await _revise(db_path, day, trip, meta, holdings, now)
            except Exception as exc:  # [O24e] nothing stored: the change is seen again next tick; the tick goes on
                logger.warning("partner_watch_revise_failed key=%s err=%s", trip.key, type(exc).__name__)
    # 5. The shadow looks, beside the tick.
    if (holdings and (_state.looks_at is None or now - _state.looks_at >= LOOK_EVERY)
            and (_state.looks_task is None or _state.looks_task.done())):
        _state.looks_at = now
        _state.looks_task = background_tasks.spawn(_record_looks(db_path, day, holdings, now, market),
                                                   name="partner_watch_looks")
    return started


def _refused(day: str, row: dict, holdings: list, trips: list) -> tuple:
    holding = _holding_for(holdings, row)
    subject = holding or next((t for t in reversed(trips) if t.exchange == row["exchange"]
                               and t.tradingsymbol == row["tradingsymbol"]), None) or Trip(
        key=str(row["order_id"]), exchange=row["exchange"], tradingsymbol=row["tradingsymbol"], product="",
        first_at=_dt(row.get("placed_at")) or _now())
    episode = _episode(day, holding) if holding is not None else None
    return (f"refused:{row['order_id']}", "REFUSED", subject, {"order_id": str(row["order_id"])},
            _dt(row.get("updated_at")) or _dt(row.get("placed_at")), episode)


async def _quotes(market: Market, contracts: list, now: datetime) -> dict:
    try:
        got = await asyncio.wait_for(market.quote(contracts), QUOTE_TIMEOUT_SEC)
    except Exception as exc:          # a missing price leaves levels unchecked; it never fails the tick
        logger.warning("partner_watch_quote_unread err=%s", type(exc).__name__)
        _state.unread.setdefault("quotes", now)
        return {}
    _state.unread.pop("quotes", None)
    for symbol, quote in (got or {}).items():
        _state.quotes[symbol] = dict(quote, looked_at=now)
    return {symbol: _state.quotes[symbol] for symbol in got or {}}


async def _price_now(holding, now: datetime) -> Optional[dict]:
    """[O24c] The option's quote, read now unless one from the last 15 s is
    at hand; None when it cannot be read (an older one is not used)."""
    cached = _state.quotes.get(holding.tradingsymbol)
    if cached and now - cached["looked_at"] <= QUOTE_FRESH:
        return cached
    market = _state.market
    contract = contract_of(holding.exchange, holding.tradingsymbol) if market is not None else None
    if contract is None:
        return None
    return (await _quotes(market, [contract], now)).get(holding.tradingsymbol)


async def _guard_for(db_path: str, episode: str, holding: Holding, now: datetime) -> _Guard:
    """The trade's guard: in memory, else what partner_watch_state kept of it (a restart), else new."""
    since = _since(holding, now)
    guard = _state.guards.get(episode)
    if guard is None:
        guard = _Guard(since=since, held=holding.qty)
        saved = await _get_state(db_path, f"guard:{episode}")
        try:
            kept = json.loads(saved) if saved else {}
        except ValueError:
            kept = {}
        if isinstance(kept, dict):
            guard.covered_once = bool(kept.get("covered_once"))
            guard.full_once = bool(kept.get("full_once"))
            guard.stops = list(kept.get("stops") or [])
            guard.full_ids = list(kept.get("full_ids") or [])
            guard.lowered_told = bool(kept.get("lowered_told"))
            guard.seen = list(kept.get("seen") or [])
            guard.withdrawn = list(kept.get("withdrawn") or [])
            guard.fresh = list(kept.get("fresh") or [])
            guard.tracked = bool(kept.get("tracked"))
            guard.saved = saved
        _state.guards[episode] = guard
    elif holding.qty > guard.held:
        guard.since, guard.held = max(guard.since, since), holding.qty     # new units need their own stop
    else:
        guard.held = holding.qty
    return guard


async def _save_guard(db_path: str, episode: str, guard: _Guard, now: datetime) -> None:
    memory = guard.memory()
    if memory != guard.saved:
        await _set_state(db_path, f"guard:{episode}", memory, now)
        guard.saved = memory


def _plain(values: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in values.items()}


async def _guard(db_path: str, day: str, holding: Holding, rows: list, now: datetime, deadline: float,
                 seeded: bool, out: list, moves: Optional[list] = None) -> Cover:
    """[O24c] One holding's protection: told when it is missing, partial,
    lost, lowered by a replacement, or fired without filling.

    [O24d] Per trade. Each message's key names the trade and the incident
    (the size, or the stops lost), so a later trade in the same option, or a
    second loss of cover in one trade, is told too; a repeat within one
    incident is not. Returns the cover (for the view).

    [O24g] ``moves``: the holding's SL orders modified down in this read.
    With its GTTs modified down and a stop replaced lower, they are told in
    one message (``_lowered``)."""
    episode = _episode(day, holding)
    guard = await _guard_for(db_path, episode, holding, now)
    moves = list(moves or [])
    fresh = _state.gtts_at is not None and now - _state.gtts_at < GTT_EVERY
    cover = cover_of(holding, rows, _state.gtts if fresh else None)
    if cover.state == "UNKNOWN" and not fresh and _state.gtts_tried_at != now:
        await _read_gtts(now, deadline)           # once a tick, shared by the holdings
        cover = cover_of(holding, rows, _state.gtts)
    _unfilled(episode, holding, cover, now, out)
    if cover.state == "UNKNOWN":
        if moves:                     # an SL order moved down is seen in the orders alone
            item = await _lowered(db_path, day, holding, moves, now)
            if item is not None:
                out.append(item)
        return cover                  # the GTTs could not be read: nothing is claimed; read again next tick
    if cover.state != guard.state:
        guard.state, guard.state_at = cover.state, now
    moved = _track_stops(guard, holding, cover, rows, now, baseline=not seeded)
    if seeded:
        first = not guard.lowered_told            # every move of this read is part of the trade's first, or none is
        moves += [{"id": after["id"], "old": before["trigger"], "new": after["trigger"],
                   "units": min(int(after["units"]), holding.qty)} for before, after in moved]
        found = _replacement(guard, holding)
        if found is not None and found[0] == "MOVE":
            moves.append(found[1])
        items = [await _lowered(db_path, day, holding, moves, now, first=first) if moves else None,
                 await _changed(db_path, day, holding, found[1], found[2], now, first=first)
                 if found is not None and found[0] == "CHANGED" else None]
        out.extend(item for item in items if item is not None)
    if cover.state in COVERED:
        guard.covered_once = True
        if cover.stops:
            guard.stops = [dict(s) for s in cover.stops]
        if cover.state == "FULL":
            guard.full_once, guard.full_ids = True, sorted(s["id"] for s in cover.stops)
    await _save_guard(db_path, episode, guard, now)
    if now - guard.state_at < COVER_GRACE:
        return cover
    claim = _cover_claim(episode, holding, guard, cover, rows, now)
    if claim is not None and claim[0] not in _state.enqueued and _state.gtts_at != now:
        # [O24g] "No stop" is claimed only from a GTT list read in this tick: the list is reused for GTT_EVERY, and a
        # GTT placed since the last read was not in it. One read a tick; without it the claim waits for the next.
        if _state.gtts_tried_at != now:
            await _read_gtts(now, deadline)
        if _state.gtts_at != now:
            return cover
        fresh = cover_of(holding, rows, _state.gtts)
        if fresh.state != cover.state:
            return fresh                  # a GTT changed it: the next read goes on from there
        cover, claim = fresh, _cover_claim(episode, holding, guard, fresh, rows, now)
    if claim is not None:
        out.append(claim)
    return cover


def _cover_claim(episode: str, holding: Holding, guard: _Guard, cover: Cover, rows: list,
                 now: datetime) -> Optional[tuple]:
    """The REMOVED, NO_STOP or PARTIAL message a lasting loss of cover owes (an outbox item), or None."""
    held, protected = holding.qty, cover.covered + cover.exiting
    base = {"episode": episode, "held": held}
    if cover.state == "ABSENT" and guard.covered_once:
        lost = ",".join(sorted(s["id"] for s in guard.stops)) or "stop"
        why = _lost_why(guard.stops, rows, holding, _state.gtts)
        return (f"removed:{episode}:{lost}", "REMOVED", holding, base | {"why": _plain(why)}, why.get("at"),
                episode)
    if cover.state == "ABSENT" and now - guard.since >= NO_STOP_AFTER:
        return f"nostop:{episode}:{held}", "NO_STOP", holding, base, guard.since + NO_STOP_AFTER, episode
    if cover.state == "PARTIAL" and now - guard.since >= NO_STOP_AFTER:
        now_ids = {s["id"] for s in cover.stops}
        lost = [i for i in guard.full_ids if i not in now_ids] if guard.full_once else []
        tail = f"lost:{','.join(lost)}" if lost else str(protected)
        return (f"partial:{episode}:{held}:{tail}", "PARTIAL", holding, base,
                max(guard.since + NO_STOP_AFTER, guard.state_at), episode)
    return None


def _gtts_fresh(now: datetime, within: timedelta) -> bool:
    return _state.gtts_at is not None and now - _state.gtts_at < within


def _sell_products(rows: list, gtts: Optional[list]) -> set:
    """[O24f] (exchange, option, product) of every sell order waiting: SL
    orders, open sells, and active GTT sell legs."""
    out = set()
    for row in rows:
        status = str(row.get("status") or "").upper()
        if row["transaction_type"] == "SELL" and _pending(row) and (status in WAITING or status == "OPEN"):
            out.add((row["exchange"], row["tradingsymbol"], str(row.get("product") or "").upper()))
    for gtt in gtts or []:
        condition = gtt.get("condition") or {}
        if str(gtt.get("status") or "").lower() != "active":
            continue
        for leg in gtt.get("orders") or []:
            if str(leg.get("transaction_type") or "").upper() == "SELL":
                out.add((str(condition.get("exchange") or "").upper(), str(condition.get("tradingsymbol") or "").upper(),
                         str(leg.get("product") or "").upper()))
    return out


def _exits(day: str, rows: list, gtts: Optional[list], holdings: list, now: datetime, out: list) -> None:
    """[O24e] Sell orders that together would sell more than is held
    (EXCESS), or that wait on an option not held at all (ORPHAN): what is
    sold beyond the holding is a new short sale. Told once it has lasted
    COVER_GRACE (a stop replaced by placing the new one first is not told).
    Without a fresh GTT list only the orders are counted.

    [O24f] By exchange, option and product throughout: Kite keeps a position
    per product, so a holding of one product never hides a sell of another
    (PRODUCT: an MIS sell on NRML units opens an MIS short). An option with
    no holding of any product is one ORPHAN message for all its sells."""
    held = {(h.exchange, h.tradingsymbol, h.product) for h in holdings}
    held_options = {(h.exchange, h.tradingsymbol) for h in holdings}
    sells = _sell_products(rows, gtts)
    live = set()

    def due(key: str) -> Optional[datetime]:
        live.add(key)
        seen = _state.exit_seen.setdefault(key, now)
        return seen if now - seen >= COVER_GRACE else None

    for holding in holdings:
        exits = exits_of(rows, gtts, holding.exchange, holding.tradingsymbol, holding.product)
        if sum(e["units"] for e in exits) <= holding.qty:
            continue
        episode = _episode(day, holding)
        ids = ",".join(sorted(e["id"] for e in exits))
        key = f"excess:{episode}:{holding.qty}:{ids}"
        if (seen := due(key)) is not None:
            out.append((key, "EXCESS", holding, {"episode": episode, "held": holding.qty, "ids": ids}, seen,
                        episode))
    for exchange, symbol in sorted({(e, s) for e, s, _p in sells} - held_options):
        exits = exits_of(rows, gtts, exchange, symbol, None)
        if not exits:
            continue
        ids = ",".join(sorted(e["id"] for e in exits))
        key = f"orphan:{day}:{exchange}:{symbol}:{ids}"
        if (seen := due(key)) is not None:
            subject = SimpleNamespace(exchange=exchange, tradingsymbol=symbol, position_key=None)
            out.append((key, "ORPHAN", subject, {"option": [exchange, symbol], "ids": ids}, seen, None))
    for exchange, symbol, product in sorted(sells):
        if not product or (exchange, symbol) not in held_options or (exchange, symbol, product) in held:
            continue
        exits = [e for e in exits_of(rows, gtts, exchange, symbol, product) if e.get("product") == product]
        if not exits:
            continue
        ids = ",".join(sorted(e["id"] for e in exits))
        key = f"product:{day}:{exchange}:{symbol}:{product}:{ids}"
        if (seen := due(key)) is not None:
            subject = SimpleNamespace(exchange=exchange, tradingsymbol=symbol, position_key=None)
            out.append((key, "PRODUCT", subject, {"option": [exchange, symbol, product], "ids": ids}, seen, None))
    for key in [k for k in _state.exit_seen if k not in live]:
        del _state.exit_seen[key]


def _counts_gtt(item: tuple) -> bool:
    """[O24g] An EXCESS, ORPHAN or PRODUCT claim, new to the outbox, that counts a GTT."""
    return item[0] not in _state.enqueued and "gtt:" in str((item[3] or {}).get("ids") or "")


def _since(holding: Holding, now: datetime) -> datetime:
    """From when the units held need a stop: the newest buy order's first fill (now for a carried or unmatched holding)."""
    trip = holding.trip
    if trip is None or trip.carried or not trip.buys:
        return now
    return max(b["at"] for b in trip.buys.values())


async def _read_gtts(now: datetime, deadline: Optional[float] = None) -> None:
    """The GTT list. [O24f] A read skipped for want of the tick's budget keeps
    the last list (its age still decides what it can confirm)."""
    _state.gtts_tried_at = now
    try:
        _state.gtts = list(await _book("/gtt/triggers", deadline) or [])
        _state.gtts_at = now
        _state.unread.pop("gtts", None)
    except zerodha.BrokerError as exc:
        if exc.code == "budget":
            return
        logger.warning("partner_watch_gtts_unavailable code=%s", exc.code)
        _state.gtts, _state.gtts_at = None, None
        _read_failed("gtts", exc.code, now)


def _read_failed(read: str, code: Optional[str], now: datetime) -> None:
    """[O24f] A read that failed (not one skipped for the budget, nor a lost
    login: that has its own message): from when it has been failing."""
    if code not in ("budget", "TokenException", "not_connected"):
        _state.unread.setdefault(read, now)


async def _health(db_path: str, day: str, now: datetime, holdings: Optional[list] = None,
                  covers: Optional[dict] = None) -> list:
    """[O24f] What the partner should know about the watch itself (outbox
    items, fixed texts): BLIND once a read it needs has failed for
    BLIND_AFTER (the orders always; the positions while the overnight list
    is unknown; the GTTs while a holding's protection is UNKNOWN), and BACK
    when a read that BLIND was sent for works again. A short failure is not
    told. ``holdings`` None: the orders could not be read, so only they are
    looked at."""
    items = []
    for read, told in list(_state.blind.items()):
        if read in _state.unread:
            continue
        del _state.blind[read]
        key = f"blind:{day}:{read}:{told.isoformat()}"
        async with aiosqlite.connect(db_path) as db:
            row = await (await db.execute("SELECT sent FROM partner_watch_messages WHERE message_key=?",
                                          (key,))).fetchone()
        if row and row[0]:
            text = BACK_TEXT.format(what=READ_NAMES[read], since=_hms(told), now=_hms(now))
            items.append((f"back:{day}:{read}:{told.isoformat()}", "BACK", None, {"text": text}, now, None))
    for read, since in _state.unread.items():
        if (read not in BLIND_TEXT or read in _state.blind or now - since < BLIND_AFTER[read]
                or (holdings is None and read != "orders")):
            continue
        fields = {"since": _hms(since)}
        if read == "positions" and _state.carried_known:
            continue                      # the overnight list is known: the messages say the count is the orders'
        if read == "gtts":
            unknown = [h for h in holdings or [] if (covers or {}).get(h.hkey) is not None
                       and covers[h.hkey].state == "UNKNOWN"]
            if not unknown:
                continue                  # every holding's SL orders cover it: the GTTs are not needed
            names = [f"{_name(h)} ({h.qty})" for h in unknown]
            many = len(names) > 1
            fields |= {"names": f"{', '.join(names[:-1])} and {names[-1]}" if many else names[0],
                       "has": "have" if many else "has", "it": "them" if many else "it"}
        _state.blind[read] = since
        items.append((f"blind:{day}:{read}:{since.isoformat()}", "BLIND", None,
                      {"text": BLIND_TEXT[read].format(**fields)}, since, None))
    return items


def _lost_why(stops: list, rows: list, holding: Holding, gtts: Optional[list] = None) -> dict:
    """Why the last covering stops no longer cover: the first one's fate.
    [O24f] A GTT that fired is told by its order's fate (sold part, or
    cancelled unsold), not as a GTT no longer active."""
    by_id = {f"kite:{r['order_id']}": r for r in rows}
    for stop in stops:
        row = by_id.get(stop["id"])
        if stop["kind"] == "GTT":
            gtt = next((g for g in gtts or [] if f"gtt:{g.get('id')}" == stop["id"]), None)
            placed = None
            if gtt is not None and str(gtt.get("status") or "").lower() == "triggered":
                for leg in gtt.get("orders") or []:
                    placed = placed or ((leg.get("result") or {}).get("order_result") or {}).get("order_id")
            row = by_id.get(f"kite:{placed}") if placed else None
            if row is None:
                return {"kind": "GTT_GONE", "trigger": stop["trigger"]}
            filled, at = int(row.get("filled_quantity") or 0), _dt(row.get("updated_at"))
            if filled > 0:
                return {"kind": "SOLD", "trigger": stop["trigger"], "sold": filled, "at": at, "via": "GTT"}
            return {"kind": "FIRED_CANCELLED", "trigger": stop["trigger"], "at": at}
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


def _unfilled(episode: str, holding: Holding, cover: Cover, now: datetime, out: list) -> None:
    for fired in cover.fired:
        seen = _state.fired_seen.setdefault(fired["order_id"], now)
        if now - seen >= UNFILLED_AFTER:
            out.append((f"unfilled:{fired['order_id']}", "UNFILLED", holding,
                        {"episode": episode, "order_id": fired["order_id"]}, seen, episode))


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


def _all_stops(holding, cover: Optional[Cover], gtts: Optional[list], last: Optional[list] = None) -> list:
    """[O24f] Every waiting stop of the holding's product, whatever
    ``cover_of`` needed to look at (it reads the GTTs only when the SL orders
    leave units uncovered): its SL orders, and the GTT stop legs of ``gtts``
    (a list read within GTT_REFRESH); without one, the GTTs in ``last``."""
    stops = [s for s in (cover.stops if cover else []) if s["kind"] == "SL"]
    if gtts is not None:
        waiting, _fired = gtt_legs(gtts, holding)
        return stops + [leg for leg in waiting if _same_product(leg["product"], holding)]
    if last is not None:
        return stops + [s for s in last if s["kind"] == "GTT"]
    return list(cover.stops if cover else [])


def _track_stops(guard: _Guard, holding: Holding, cover: Cover, rows: list, now: datetime, *,
                 baseline: bool = False) -> list:
    """[O24f] Stops taken away (``_withdrawn``) and stops placed, kept for
    REPLACE_WINDOW: a replacement is seen in one read or across several, the
    new stop placed before or after the old one goes. A stop is placed when
    it is new to every stop the holding had (``_all_stops``), not when
    ``cover_of`` first needed it. ``baseline`` (a new guard, the first read
    after a restart): this read is only remembered. Returns the GTTs
    modified down (same id, lower trigger) as (before, now)."""
    gtts = _state.gtts if _gtts_fresh(now, GTT_REFRESH) else None
    now_by = {s["id"]: s for s in _all_stops(holding, cover, gtts, guard.seen)}
    moved = []
    if guard.tracked and not baseline:
        seen = {s["id"]: s for s in guard.seen}
        for stop_id, stop in seen.items():
            if stop_id not in now_by and _withdrawn(stop_id, rows, gtts):
                guard.withdrawn.append(dict(stop, at=now.isoformat()))
            elif stop_id in now_by and stop["kind"] == "GTT" and now_by[stop_id]["trigger"] < stop["trigger"] - 1e-6:
                moved.append((stop, now_by[stop_id]))
        guard.fresh.extend(dict(s, at=now.isoformat()) for i, s in now_by.items() if i not in seen)
    else:
        guard.withdrawn, guard.fresh = [], []
    cutoff = now - REPLACE_WINDOW
    guard.withdrawn = [s for s in guard.withdrawn if (_dt(s.get("at")) or now) >= cutoff]
    guard.fresh = [s for s in guard.fresh if (_dt(s.get("at")) or now) >= cutoff and s["id"] in now_by]
    guard.seen, guard.tracked = [dict(s) for s in now_by.values()], True
    return moved


def _replacement(guard: _Guard, holding: Holding) -> Optional[tuple]:
    """A stop cancelled and replaced by a lower one is a stop moved down (a
    stop that fired, leaving a lower one, is not).

    [O24f] The new stop is matched to the one it replaced, never to a stop
    that stayed: one taken away and one placed within REPLACE_WINDOW are a
    move of that stop, for the units both sell (("MOVE", move)); several are
    told as the change they make together, without pairing them (("CHANGED",
    gone, added): ``changed_text``). A stop taken away with nothing placed is
    not a move (REMOVED and PARTIAL tell it). None: nothing to tell."""
    if not guard.withdrawn or not guard.fresh:
        return None
    gone, added = guard.withdrawn, guard.fresh
    guard.withdrawn, guard.fresh = [], []
    if _average_trigger(added) >= _average_trigger(gone) - 1e-6:
        return None                       # replaced at the same level or higher
    if len(gone) == 1 and len(added) == 1:
        units = min(int(added[0]["units"]), int(gone[0]["units"]), holding.qty)
        return "MOVE", {"id": added[0]["id"], "old": gone[0]["trigger"], "new": added[0]["trigger"], "units": units}

    def plain(stops: list) -> list:
        return [{"id": s["id"], "trigger": s["trigger"], "units": s["units"]} for s in stops]

    return "CHANGED", plain(gone), plain(added)


async def _lowered(db_path: str, day: str, holding: Holding, moves: list, now: datetime, *,
                   first: Optional[bool] = None) -> Optional[tuple]:
    """Stops moved down, worth a message. [O24e] Each is bound to the stop now
    at its new level (``id``) and what it sells (``units``). [O24g] Every
    stop moved down in one read goes in one message, judged together
    (``moves_reason``): before, two GTTs moved together told only the first
    one found, and of two SL orders modified together the other was dropped
    as "within the plan" even when it was the bigger move. ``moves``: {"id",
    "old", "new", "units", "at" (the broker's update time, when known)}."""
    episode = _episode(day, holding)
    guard = await _guard_for(db_path, episode, holding, now)
    plan, _set_at = await _plan_for(db_path, holding, day)
    first = not guard.lowered_told if first is None else first
    reason = moves_reason(holding, moves, plan, first)
    guard.lowered_told = True
    if reason is None:
        logger.info("partner_watch_lowered_within_plan key=%s moves=%s", episode,
                    ",".join(f"{m['id']}:{m['old']:.2f}>{m['new']:.2f}" for m in moves))
        return None
    plain = sorted(({"id": m["id"], "old": m["old"], "new": m["new"], "units": m["units"]} for m in moves),
                   key=lambda m: m["id"])
    key = "lowered:" + "+".join(f"{m['id']}@{m['new']:.2f}" for m in plain)
    at = min((t for t in (_dt(m.get("at")) for m in moves) if t is not None), default=None)
    return key, "LOWERED", holding, {"episode": episode, "moves": plain, "first": first, "reason": reason}, at, episode


async def _changed(db_path: str, day: str, holding: Holding, gone: list, added: list, now: datetime, *,
                   first: Optional[bool] = None) -> Optional[tuple]:
    """[O24f] Several stops taken away and new ones placed lower within
    REPLACE_WINDOW: told as one change at the average triggers (``changed_text``)."""
    episode = _episode(day, holding)
    guard = await _guard_for(db_path, episode, holding, now)
    plan, _set_at = await _plan_for(db_path, holding, day)
    old, new = _average_trigger(gone), _average_trigger(added)
    first = not guard.lowered_told if first is None else first
    reason = lowered_reason(holding, old, new, plan, first)
    guard.lowered_told = True
    if reason is None:
        logger.info("partner_watch_lowered_within_plan key=%s old=%.2f new=%.2f", episode, old, new)
        return None
    key = f"lowered:{'+'.join(sorted(s['id'] for s in gone))}:{new:.2f}"
    return (key, "LOWERED", holding, {"episode": episode, "gone": gone, "added": added, "reason": reason,
                                      "first": first}, None, episode)


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


def _start_plan(db_path: str, day: str, trip: Trip, holding: Optional[Holding], trips: list, now: datetime,
                market: Market) -> asyncio.Task:
    """[O24d] The plan is for what is held (Zerodha's count and average
    when they differ from the orders'), the buy's own price kept apart."""
    snapshot = replace(trip, buys={k: dict(v) for k, v in trip.buys.items()}, sell_ids=list(trip.sell_ids))
    size = ((holding.qty, holding.entry) if holding is not None and holding.entry and holding.qty
            else (trip.open_qty, trip.entry))
    task = background_tasks.spawn(_plan_job(db_path, day, snapshot, list(trips), now, market, size=size,
                                            announce=now - trip.first_at <= PLAN_STALE, owner=_state,
                                            by=_state.detected_by),
                                  name="partner_watch_plan")
    task.add_done_callback(_plan_done)
    _state.plan_tasks[trip.key] = task
    _state.plan_tries[trip.key] = _state.plan_tries.get(trip.key, 0) + 1
    return task


def _plan_done(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("partner_watch_plan_failed err=%s", type(task.exception()).__name__)


async def _market_plan(trip: Trip, now: datetime, market: Market, size: Optional[tuple] = None) -> tuple:
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
    plan = _plan_of(trip, contract, now, size=size, option_bars=option_bars, fut_bars=fut_bars, fut_price=fut_price,
                    mid=_mid(quote))
    lot = int(getattr(contract, "lot_size", 0) or 0)
    return plan, quote, lot


def _plan_of(trip: Trip, contract, now: datetime, *, size: Optional[tuple] = None, option_bars=None, fut_bars=None,
             fut_price=None, mid=None) -> Plan:
    qty, entry = size or (trip.open_qty, trip.entry)
    return build_plan(entry=round(entry, 2), qty=qty, exchange=trip.exchange,
                      opt_type=getattr(contract, "instrument_type", None) or trip.tradingsymbol[-2:],
                      strike=float(getattr(contract, "strike", 0.0) or 0.0),
                      expiry=getattr(contract, "expiry", None), now=now, bought_at=trip.first_at, cash=_state.cash,
                      option_bars=option_bars, fut_bars=fut_bars, fut_price=fut_price, option_mid=mid)


async def _plan_job(db_path: str, day: str, trip: Trip, trips: list, now: datetime, market: Market, *,
                    announce: bool, owner: _State, size: Optional[tuple] = None, by: Optional[str] = None) -> int:
    """A new trade's first plan: computed within PLAN_DEADLINE_SEC (else only
    the premium at risk) and stored as version 1; then the PLAN message goes
    to the outbox. [O24d] Its text is built when it is sent, from the book
    read then: nothing for a trade closed meanwhile, and the risk of what is
    held then."""
    try:
        plan, _quote, lot = await asyncio.wait_for(_market_plan(trip, now, market, size), PLAN_DEADLINE_SEC)
    except asyncio.TimeoutError:
        logger.warning("partner_watch_plan_slow key=%s", trip.key)
        plan, lot = _plan_of(trip, None, now, size=size), 0
    except Exception as exc:          # odd market data: the plan says only the premium at risk
        logger.warning("partner_watch_plan_market_failed key=%s err=%s", trip.key, type(exc).__name__)
        plan, lot = _plan_of(trip, None, now, size=size), 0
    if owner is not _state:
        return 0                      # a new day or login started meanwhile
    item = None
    if announce:
        bought = int(trip.bought)
        lots = bought // lot if lot and bought % lot == 0 else None
        after, line = _after_loss(trip, trips), _day_line(trip, trips)
        usual = await _usual_share(db_path, trip, trips, now)
        if owner is not _state:
            return 0
        episode = _episode(day, trip)
        context = {"episode": episode, "lots": lots, "bought": bought, "bought_px": round(trip.entry, 2),
                   "after_loss": after, "day_line": line, "usual": usual}
        item = (f"plan:{episode}", "PLAN", trip, context, trip.first_at, episode)
    # [O24e] Version 1 and its PLAN message in one transaction: a failed write leaves neither, and the plan
    # (still missing) is started again on the next tick.
    meta = await _store_plan(db_path, trip, plan, now, "BUY", announce=item, day=day, by=by)
    if owner is not _state:
        return 0
    _state.planned[trip.key] = meta
    if item is not None:
        _kick()
    return int(item is not None)


async def _revise(db_path: str, day: str, trip: Trip, meta: dict, holdings: list, now: datetime) -> None:
    """[O24c] A later plan version when the trade's size changed: a new buy
    order (ADDED, told while fresh), more fills of a known one (FILLED) or a
    partial sale (TRIMMED). [O24d] The version's size and average are what
    is held (Zerodha's count when it differs); its bought and sold, the
    orders'."""
    new_ids = [i for i in trip.buys if i not in meta["buy_ids"]]
    if new_ids:
        reason = "ADDED"
    elif trip.bought != meta["bought"]:
        reason = "FILLED"
    elif trip.sold != meta["sold"]:
        reason = "TRIMMED"
    else:
        return
    holding = next((h for h in holdings if h.position_key == trip.key), None)
    current = holding if holding is not None and holding.entry else trip
    plan = revised(meta["plan"], entry=round(current.entry, 2), qty=current.open_qty, exchange=trip.exchange)
    first_new = min(trip.buys[i]["at"] for i in new_ids) if new_ids else None
    item = None
    if reason == "ADDED" and holding is not None and now - first_new <= PLAN_STALE:
        added = sum(trip.buys[i]["qty"] for i in new_ids)
        first = trip.buys[next(iter(trip.buys))]
        old = meta["plan"]
        loss_before = (round((meta["entry"] - old.stop) * meta["qty"]
                             + _costs(meta["entry"], old.stop, meta["qty"], trip.exchange), 2)
                       if old.stop is not None else round(meta["entry"] * meta["qty"], 2))
        episode = _episode(day, holding)
        context = {"episode": episode, "added": added,
                   "added_px": round(sum(trip.buys[i]["value"] for i in new_ids) / added, 4),
                   "first_px": round(first["value"] / first["qty"], 4), "loss_before": loss_before}
        item = (f"added:{episode}:{new_ids[-1]}", "ADDED", holding, context, first_new, episode)
    # [O24e] The version and its ADDED message in one transaction: a failed write leaves neither, and the change
    # is seen again on the next tick.
    _state.planned[trip.key] = await _store_plan(db_path, trip, plan, now, reason, announce=item, day=day,
                                                 by=_state.detected_by)
    if item is not None:
        _kick()


def _costs(entry: float, exit_: float, qty: int, exchange: str) -> float:
    from partner_coach import round_trip_costs
    return round_trip_costs(entry, exit_, qty, exchange)


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
# [O24d] the messages, built from the latest book read just before sending
# ---------------------------------------------------------------------------

def _current(plan: Optional[Plan], holding) -> Optional[Plan]:
    """The plan's levels for what is held now: the loss at the stop moves with the size and average."""
    if plan is None or holding.entry is None or not holding.open_qty:
        return plan
    entry = round(holding.entry, 2)
    if plan.qty == holding.open_qty and abs(plan.entry - entry) < 1e-9:
        return plan
    return revised(plan, entry=entry, qty=holding.open_qty, exchange=holding.exchange)


async def _b_plan(db_path: str, context: dict, view: View, now: datetime):
    holding = view.holding(context.get("episode"))
    if holding is None:
        return None                       # sold before the plan was ready
    plan, set_at = await _plan_for(db_path, holding, view.day)
    if plan is None:
        return None
    plan = _current(plan, holding)
    cover = view.covers.get(holding.hkey)
    quote = await _price_now(holding, now)
    text = plan_text(holding, plan, lots=context.get("lots"), bought=(context["bought"], context["bought_px"]),
                     cover=cover, after_loss=context.get("after_loss"), day_line=context.get("day_line"),
                     usual=context.get("usual"), quote=quote, now=now, set_at=set_at)
    return text, plan_summary(plan, quote, cover, now), quiet_keyboard(view.day)


async def _b_added(db_path: str, context: dict, view: View, now: datetime):
    holding = view.holding(context.get("episode"))
    if holding is None:
        return None
    plan, _set_at = await _plan_for(db_path, holding, view.day)
    plan = _current(plan, holding)
    added = int(context["added"])
    text = added_text(holding, added=added, added_px=context["added_px"], first_px=context.get("first_px"), plan=plan,
                      loss_before=context.get("loss_before"), quote=await _price_now(holding, now),
                      cover=view.covers.get(holding.hkey), now=now)
    summary = (f"you added {added}: the plan stop now costs about −{_amt(-_result_at(holding, plan.stop))}"
               if plan is not None and plan.stop is not None else f"you added {added}")
    return text, summary, quiet_keyboard(view.day)


async def _b_cover(kind: str, db_path: str, context: dict, view: View, now: datetime):
    """NO_STOP, PARTIAL and REMOVED: only while still true, for the units held then."""
    holding = view.holding(context.get("episode"))
    if holding is None:
        return None
    cover = view.covers.get(holding.hkey)
    if cover is None or cover.state == "UNKNOWN":
        return WAIT
    if cover.state != ("PARTIAL" if kind == "PARTIAL" else "ABSENT"):
        return None                       # a stop is back (or this is now another incident)
    if kind != "REMOVED" and holding.qty != context.get("held"):
        return None                       # the size changed: that has its own message
    plan, set_at = await _plan_for(db_path, holding, view.day)
    plan = _current(plan, holding)
    quote = await _price_now(holding, now)
    if kind == "NO_STOP":
        return (no_stop_text(holding, plan, quote, cover, set_at, now=now), "no stop order yet",
                quiet_keyboard(view.day))
    if kind == "PARTIAL":
        return (partial_text(holding, cover, plan, quote, set_at, now=now),
                f"a stop covered {cover.covered + cover.exiting} of {holding.qty}", quiet_keyboard(view.day))
    why = context.get("why") or {}
    summary = "stop sold part, the rest has none" if why.get("kind") == "SOLD" else "stop gone, nothing in its place"
    return removed_text(holding, why, plan, quote, set_at, now=now), summary, None


async def _b_unfilled(db_path: str, context: dict, view: View, now: datetime):
    holding = view.holding(context.get("episode"))
    cover = view.covers.get(holding.hkey) if holding is not None else None
    fired = next((f for f in (cover.fired if cover else []) if f["order_id"] == context.get("order_id")), None)
    if fired is None:
        return None                       # it sold, or it was changed or cancelled
    return unfilled_text(holding, fired, await _price_now(holding, now)), "your stop fired and had not sold", None


async def _b_lowered(db_path: str, context: dict, view: View, now: datetime):
    """LOWERED, rebuilt from the latest read: only the moves whose stop still
    waits at its new level (a retry is never about a stop changed since), for
    the units it sells now; judged again on what is left."""
    holding = view.holding(context.get("episode"))
    if holding is None:
        return None
    cover = view.covers.get(holding.hkey)
    stops = {s["id"]: s for s in _all_stops(holding, cover, view.gtts)}
    plan, _set_at = await _plan_for(db_path, holding, view.day)
    if context.get("added"):              # [O24f] several stops changed together: all the new ones still wait
        added, gone = context["added"], context.get("gone") or []
        if any(s["id"] not in stops or abs(stops[s["id"]]["trigger"] - s["trigger"]) > 1e-6 for s in added):
            return None
        return (changed_text(holding, gone, added, context.get("reason") or "FIRST", plan),
                f"stops changed {_triggers(gone)} → {_triggers(added)}", None)
    valid = []
    for move in context.get("moves") or []:
        stop = stops.get(move["id"])
        if stop is None or abs(stop["trigger"] - float(move["new"])) > 1e-6:
            continue                      # that stop no longer waits at the new level
        # [O24f] A replacement is told for the units both stops sell, never more than the stop has now.
        valid.append(dict(move, units=min(int(stop["units"]), holding.qty, int(move.get("units") or holding.qty))))
    reason = moves_reason(holding, valid, plan, bool(context.get("first"))) if valid else None
    if reason is None:
        return None
    if len(valid) == 1:
        move = valid[0]
        part = f" for {move['units']} of {holding.qty}" if move["units"] < holding.qty else ""
        return (lowered_text(holding, move["old"], move["new"], reason, plan, units=move["units"], cover=cover,
                             stop_id=move["id"]), f"stop moved down {_px(move['old'])} → {_px(move['new'])}{part}", None)
    return moved_text(holding, valid, reason, plan, cover=cover), f"{len(valid)} stops moved down", None


async def _b_refused(db_path: str, context: dict, view: View, now: datetime):
    row = next((r for r in view.rows if str(r["order_id"]) == context.get("order_id")), None)
    if row is None:
        return None
    same = [h for h in view.holdings if h.exchange == row["exchange"] and h.tradingsymbol == row["tradingsymbol"]]
    return refused_text(row, view.rows, sum(h.qty for h in same) or None), "explained Zerodha's refusal", None


async def _b_close(db_path: str, context: dict, view: View, now: datetime):
    holding = view.holding(context.get("episode"))
    if holding is None:
        return None
    contract = contract_of(holding.exchange, holding.tradingsymbol)
    expiry_today = bool(contract is not None and getattr(contract, "expiry", None) == now.date())
    plan, _set_at = await _plan_for(db_path, holding, view.day)
    return (close_text(holding, expiry_today=expiry_today, theta_day=plan.theta_day if plan else None),
            "20 minutes to the close", None)


async def _b_excess(db_path: str, context: dict, view: View, now: datetime):
    holding = view.holding(context.get("episode"))
    if holding is None or holding.qty != context.get("held"):
        return None                       # the size changed: counted again from the next read
    if view.gtts is None and "gtt:" in str(context.get("ids") or ""):
        return WAIT                       # a GTT was counted: wait for the list
    exits = exits_of(view.rows, view.gtts, holding.exchange, holding.tradingsymbol, holding.product)
    total = sum(e["units"] for e in exits)
    if total <= holding.qty:
        return None
    return excess_text(holding, exits), f"sell orders for {total} with {holding.qty} held", None


async def _b_orphan(db_path: str, context: dict, view: View, now: datetime):
    exchange, symbol = context["option"]
    if any(h.exchange == exchange and h.tradingsymbol == symbol for h in view.holdings):
        return None                       # held again
    if view.gtts is None and "gtt:" in str(context.get("ids") or ""):
        return WAIT
    exits = exits_of(view.rows, view.gtts, exchange, symbol, None)
    if not exits:
        return None
    basis = none_held(view.positions, view.carried_known)
    summary = ("sell orders waiting with nothing held" if basis == "ZERODHA" else
               "sell orders waiting; whether anything is held could not be checked")
    return orphan_text(symbol, exits, basis), summary, None


async def _b_product(db_path: str, context: dict, view: View, now: datetime):
    """[O24f] Sells of a product not held, on an option held as another product: only while still so."""
    exchange, symbol, product = context["option"]
    same = [h for h in view.holdings if h.exchange == exchange and h.tradingsymbol == symbol]
    if not same or any(h.product == product for h in same):
        return None                       # nothing held any more (ORPHAN's), or that product is held now
    if view.gtts is None and "gtt:" in str(context.get("ids") or ""):
        return WAIT
    exits = [e for e in exits_of(view.rows, view.gtts, exchange, symbol, product) if e.get("product") == product]
    if not exits:
        return None
    return (product_text(symbol, product, exits, same, none_held(view.positions, view.carried_known)),
            f"{product} sell orders on {same[0].product} units", None)


_BUILDERS = {
    "PLAN": _b_plan, "ADDED": _b_added, "UNFILLED": _b_unfilled, "LOWERED": _b_lowered, "REFUSED": _b_refused,
    "CLOSE": _b_close, "EXCESS": _b_excess, "ORPHAN": _b_orphan, "PRODUCT": _b_product,
    "NO_STOP": lambda *args: _b_cover("NO_STOP", *args),
    "PARTIAL": lambda *args: _b_cover("PARTIAL", *args),
    "REMOVED": lambda *args: _b_cover("REMOVED", *args),
}


# ---------------------------------------------------------------------------
# login, morning prompt, reconnect, the quiet button
# ---------------------------------------------------------------------------

async def _say(db_path: str, key: str, day: str, kind: str, text: str, now: datetime, *,
               keyboard: Optional[dict] = None) -> bool:
    """[O24d] A fixed-text message (WATCH_ON, PROMPT, RECONNECT) through the
    outbox: sent at once when it can be; one that provably did not leave is
    tried again from the later ticks. Whether it went now."""
    deadline = _time.monotonic() + DELIVERY_INLINE_SEC
    if not await _enqueue(db_path, key, day, kind, None, now, context={"text": text, "keyboard": keyboard}):
        return False
    await _wait_within([_kick()], DELIVERY_INLINE_SEC, deadline)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT sent FROM partner_watch_messages WHERE message_key=?",
                                      (key,))).fetchone()
    return bool(row and row[0])


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
        _state.clock = (now, _time.monotonic())
        await _say(db_path, f"on:{day}:{now.isoformat()}", day, "WATCH_ON", WATCH_ON_TEXT.format(close=close), now)


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
    _state.clock = (now, _time.monotonic())
    sent = await _say(db_path, f"prompt:{day}", day, "PROMPT", PROMPT_TEXT, now, keyboard=keyboard)
    return {"status": "COMPLETED", "sent": sent}


async def _reconnect_prompt(db_path: str, day: str, now: datetime) -> None:
    login = await _get_state(db_path, f"login:{day}")
    if not login:
        return
    keyboard = login_keyboard("🔐 Reconnect the watch")
    if keyboard is None:
        return
    await _say(db_path, f"reconnect:{day}:{login}", day, "RECONNECT", RECONNECT_TEXT, now, keyboard=keyboard)


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
    """For the review page: is the watch on now, and quiet? [O24f] ``unread``:
    the reads failing now, each since when (a lasting one is also told on
    Telegram: BLIND)."""
    now = (now or datetime.now(IST)).astimezone(IST)
    minute = now.hour * 60 + now.minute
    on = enabled() and zerodha.connected(now) and OPEN_MIN - 15 <= minute < zerodha.CLOSE_MIN
    close = f"{zerodha.CLOSE_MIN // 60}:{zerodha.CLOSE_MIN % 60:02d}"
    return {"on": bool(on), "until": close,
            "quiet": await quiet(settings.DB_PATH, now.date().isoformat()) if on else False,
            "unread": {read: since.isoformat() for read, since in sorted(_state.unread.items())} if on else {},
            "stream": _stream_state() if on else None}


def _stream_state() -> Optional[str]:
    """[O24g] The order stream's state (OFF | CONNECTING | LIVE | DOWN | REFUSED), or None when it is not enabled."""
    import partner_watch_stream
    return partner_watch_stream.stats()["state"] if partner_watch_stream.enabled() else None
