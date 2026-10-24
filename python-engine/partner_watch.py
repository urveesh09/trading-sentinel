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

What it sends (live, loss first)
  PLAN     right after a buy fills: the stop that the system's own readings
           give, the loss if it is hit (with charges, against the day's cash),
           the target zone, and three facts: the option's normal 5-minute swing,
           its rise in the 15 minutes before the buy, and the system's 5-minute
           trend. Also, when they apply: a buy within 30 minutes of a losing
           exit, a bigger size after that loss, and from the 5th trade the
           day's trades and charges.
  NO_STOP  120 s after the buy with no stop order resting.
  LOWERED  a resting stop's trigger moved down: the result if it is hit, then
           and before. Told the first time in a trade, and after that only
           when the move puts the stop under the plan's stop or gives up a
           stop that was guarding the buy price. Oct 23 had 20 moves down,
           7 of them on one trade; every move is still in the evening review.
  REMOVED  a resting stop cancelled with no other stop left after 20 s (room
           for a replacement; a lower replacement is LOWERED).
  REFUSED  Zerodha refused an order: why, in plain words
           (partner_insights.refusal_plain), and whether the trade is still open.
  CLOSE    15:20 with an option still held: what the close does to it.
"Quiet today" (a button on PLAN and NO_STOP) mutes PLAN, NO_STOP and CLOSE.
LOWERED, REMOVED and REFUSED always go, because those are the moments a
loss grows.

The plan, computed once per buy (``build_plan``, pure)
  - Stop: the index level where the trade is wrong, as the F&O engine sets
    it (fno_engine_mom): the opposite opening-range edge once the 09:15-09:45
    range is complete and on the losing side, else 1.5 x ATR(14) of 5-minute
    futures bars, whichever is tighter. It is priced into the option with
    Black-76 at the option's own implied volatility (fno_chain's time to
    expiry). When that is inside the option's normal 5-minute swing W (the
    median 5-minute high-low of the 30 minutes before the buy), normal moves
    would take it out, so the stop is P - W and the message says so.
  - Loss at the stop: (P - stop) x qty plus the round trip's charges
    (partner_coach.round_trip_costs), as a share of the day's cash: a fact,
    not a limit. [O24-SZ] The partner sizes as they choose, so the message
    warns only when the money in this buy is much more than they usually put
    in (partner_insights.usual_size: 1.5 x the median share of their last 20
    buys, once there are 5).
  - Target zone: the index at 1.8 R (FNO_TARGET_R), priced the same way.
  - Without market data the plan says only what is known: the premium at
    risk, and "place a stop". It never invents a level.
Market data: the partner's own key when it has it (the paid plan; tried once
a day), else the owner's quotes (management lane) and candles.

Shadow (recorded, not sent)
  Every 15 s each open position's bid, ask and LTP and the front future go
  into ``partner_watch_looks``. The judgment messages (protect at a gain,
  trail, idea broken, target, trend, no progress) are scored on recorded days
  before any of them is switched on (owner rule: freeze, then score).

Never: an order, a change or a cancellation (partner_broker_sync's read-only
allowlist), a buy idea, or a prediction.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

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
REMOVAL_GRACE = timedelta(seconds=20)
PLAN_STALE = timedelta(minutes=5)          # a buy older than this when first seen (a restart) gets no PLAN message
LOOK_EVERY = timedelta(seconds=15)
CLOSE_WARN_MIN = 15 * 60 + 20
SWING_LOOKBACK_MIN = 30
SWING_WINDOW_MIN = 5
SWING_MIN_BARS = 10
RUN_LOOKBACK_MIN = 15
COUNT_FROM_TRADE = 5
FUTURE_BARS_DAYS = 21                      # as the F&O engine (fno_orchestrator.RVOL_FETCH_CALENDAR_DAYS)
TICK = 0.05
QUIET_KEEPS = ("LOWERED", "REMOVED", "REFUSED")
GUARD_TOLERANCE = 0.005                    # a stop within 0.5% under the buy price still guards it
QUIET_PREFIX = "watch"

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
CREATE TABLE IF NOT EXISTS partner_watch_plans (
  position_key TEXT PRIMARY KEY,
  session_date TEXT NOT NULL,
  exchange TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  plan_json TEXT NOT NULL
);
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


def _option(symbol: str) -> str:
    parsed = zerodha.parse_option_symbol(symbol)
    if parsed is None:
        return symbol
    return f"{parsed['underlying']} {parsed['strike']:g} {parsed['opt_type']}"


def _floor_tick(value: float) -> float:
    return round(int(value / TICK + 1e-9) * TICK, 2)


def _round_tick(value: float) -> float:
    return round(round(value / TICK) * TICK, 2)


# ---------------------------------------------------------------------------
# positions from the order book (pure)
# ---------------------------------------------------------------------------

@dataclass
class Trip:
    """One round trip on one option: from the buy that opened it to the sale that closed it."""
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


def trips_from_orders(rows: list, carried: Optional[list] = None, day: Optional[date] = None) -> list:
    """Round trips from the day's option orders (``option_orders`` rows), in
    fill order. ``carried``: positions held from an earlier day
    (``option_positions`` rows: the overnight quantity at the net average
    price, which Kite gives only for the whole position)."""
    by_symbol: dict = {}
    for row in rows or []:
        if int(row.get("filled_quantity") or 0) > 0 and (row.get("average_price") or 0) > 0 and _fill_at(row):
            by_symbol.setdefault((row["exchange"], row["tradingsymbol"]), []).append(row)
    trips: list = []
    for item in carried or []:
        qty = min(int(item.get("overnight_quantity") or 0), int(item.get("quantity") or 0))
        if qty > 0 and (item.get("average_price") or 0) > 0:
            midnight = datetime.combine(day or date.today(), datetime.min.time())
            trip = Trip(key=f"carry:{item['tradingsymbol']}", exchange=item["exchange"],
                        tradingsymbol=item["tradingsymbol"], product=str(item.get("product") or ""),
                        first_at=IST.localize(midnight + timedelta(minutes=OPEN_MIN)),
                        bought=qty, buy_value=qty * float(item["average_price"]), buy_orders=1, carried=True)
            by_symbol.setdefault((item["exchange"], item["tradingsymbol"]), [])
            trips.append(trip)
    for (exchange, symbol), fills in by_symbol.items():
        open_trip = next((t for t in trips if t.carried and t.tradingsymbol == symbol and t.exchange == exchange), None)
        for row in sorted(fills, key=lambda r: (_fill_at(r), str(r["order_id"]))):
            qty, price, at = int(row["filled_quantity"]), float(row["average_price"]), _fill_at(row)
            if row["transaction_type"] == "BUY":
                if open_trip is None or not open_trip.open_qty:
                    open_trip = Trip(key=str(row["order_id"]), exchange=exchange, tradingsymbol=symbol,
                                     product=str(row.get("product") or ""), first_at=at)
                    trips.append(open_trip)
                open_trip.bought += qty
                open_trip.buy_value += qty * price
                open_trip.buy_orders += 1
            elif open_trip is not None and open_trip.open_qty:
                take = min(qty, open_trip.open_qty)
                open_trip.sold += take
                open_trip.sell_value += take * price
                open_trip.sell_orders += 1
                if not open_trip.open_qty:
                    open_trip.closed_at = at
    return sorted(trips, key=lambda t: t.first_at)


def resting_stops(rows: list, exchange: str, symbol: str) -> list:
    """The stop orders waiting on one option now (SL / SL-M, trigger pending)."""
    return [r for r in rows or [] if r["exchange"] == exchange and r["tradingsymbol"] == symbol
            and str(r.get("status") or "").upper() == "TRIGGER PENDING" and zerodha.carries_trigger(r)]


# ---------------------------------------------------------------------------
# the plan (pure)
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    entry: float
    qty: int
    stop: Optional[float] = None
    stop_basis: str = "PREMIUM"        # INDEX | SWING | NONE (swing as big as the price) | PREMIUM (no market data)
    stop_index: Optional[float] = None
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
        # The index stop is inside the option's normal swing (or the index could not be read).
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


# ---------------------------------------------------------------------------
# message texts (pure)
# ---------------------------------------------------------------------------

def plan_text(trip: Trip, plan: Plan, *, lots: Optional[int], after_loss: Optional[dict] = None,
              day_line: Optional[str] = None, usual: Optional[float] = None) -> str:
    from partner_insights import USUAL_SIZE_MULT
    name = _option(trip.tradingsymbol)
    size = f"{lots} lot{'s' if lots != 1 else ''} ({plan.qty})" if lots else f"{plan.qty}"
    lines = [f"🟢 You bought {name} · {size} at {_px(plan.entry)}"]
    share = (f", {plan.loss_pct:.0%} of your cash" if plan.loss_pct is not None else "")
    if plan.stop_basis == "INDEX":
        lines.append(f"🛑 Plan stop {_px(plan.stop)} (index {plan.stop_index:,.0f}). If it is hit: about "
                     f"−{_amt(plan.loss)} with charges{share}.")
    elif plan.stop_basis == "SWING":
        inside = (f"The index stop ({plan.stop_index:,.0f} → {_px(plan.index_stop_option)}) sits inside that swing. "
                  if plan.stop_index is not None and plan.index_stop_option is not None else "")
        lines.append(f"🛑 Plan stop {_px(plan.stop)}: one normal 5-minute swing ({_px(plan.swing)}) under your "
                     f"price. {inside}If it is hit: about −{_amt(plan.loss)} with charges{share}.")
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
        lines.append(f"🎯 Target zone {_px(plan.target)} (index {plan.target_index:,.0f}).")
    facts = []
    if plan.stop_basis in ("INDEX", "SWING") and plan.swing:
        facts.append(f"normal 5-min swing {_px(plan.swing)}")
    if plan.run_pct is not None and plan.run_from:
        facts.append(f"up {plan.run_pct:.0%} in the 15 min before you bought (from {_px(plan.run_from)})"
                     if plan.run_pct >= 0 else
                     f"down {abs(plan.run_pct):.0%} in the 15 min before you bought")
    if plan.trend:
        facts.append("the 5-min trend is with you" if plan.trend == "WITH" else "the 5-min trend is against you")
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
    if plan.stop is not None:
        lines.append(f"Place the SL order now: trigger {_px(plan.stop)}. A fast fall can fill a little lower.")
    return "\n".join(lines)


def plan_summary(plan: Plan) -> str:
    if plan.stop is not None:
        return f"plan stop {_px(plan.stop)}, loss if hit about −{_amt(plan.loss)}"
    return f"at risk: the whole {_amt(plan.loss)}"


def no_stop_text(trip: Trip, plan: Optional[Plan]) -> str:
    line = f"⏰ {_option(trip.tradingsymbol)}: no stop order yet (bought {_hhmm(trip.first_at)})."
    if plan is not None and plan.stop is not None:
        line += f" Plan stop {_px(plan.stop)}; if it is hit, about −{_amt(plan.loss)} with charges."
    return line


def _result_at(trip: Trip, trigger: float) -> float:
    from partner_coach import round_trip_costs
    qty = trip.open_qty
    return round((trigger - trip.entry) * qty - round_trip_costs(trip.entry, trigger, qty, trip.exchange), 2)


def lowered_reason(trip: Trip, old: float, new: float, plan: Optional[Plan], first: bool) -> Optional[str]:
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


def lowered_text(trip: Trip, old: float, new: float, reason: str = "FIRST", plan: Optional[Plan] = None) -> str:
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


def removed_text(trip: Trip, trigger: float, plan: Optional[Plan]) -> str:
    line = (f"⚠️ {_option(trip.tradingsymbol)}: your stop at {_px(trigger)} is cancelled and no other stop is in "
            f"Zerodha. Nothing limits this trade's loss now.")
    if plan is not None and plan.stop is not None:
        line += f" Plan stop {_px(plan.stop)}; if it is hit, about −{_amt(plan.loss)} with charges."
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


def close_text(trip: Trip, *, expiry_today: bool, theta_day: Optional[float]) -> str:
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


WATCH_ON_TEXT = ("✅ Trade watch on until {close}. I'll message you when a buy has no stop, when a stop is moved "
                 "down or cancelled, when Zerodha refuses an order, and before the close. Messages only: nothing "
                 "is ever placed, changed or cancelled for you.")
PROMPT_TEXT = ("🌅 Good morning. Log in to Zerodha to switch on today's trade watch: I'll message you when a buy "
               "has no stop, when a stop is moved down or cancelled, and when Zerodha refuses an order. "
               "Messages only: nothing is ever placed for you.")
RECONNECT_TEXT = ("🔌 The trade watch stopped (the system restarted) and needs your Zerodha login again. "
                  "Your orders are untouched.")
QUIET_TOAST = ("Quiet for today. You will still hear when a stop is moved down or cancelled, or Zerodha "
               "refuses an order.")


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
        """{tradingsymbol: {"bid", "ask", "ltp"}}."""
        out: dict = {}
        names = {f"{c.segment}:{c.tradingsymbol}": c for c in contracts}
        try:
            data = await self._partner("/quote", {"i": list(names)})
        except zerodha.BrokerError as exc:
            logger.warning("partner_watch_quote_failed source=partner code=%s", exc.code)
            data = None
        if data:
            for name, quote in (data or {}).items():
                if name in names:
                    out[names[name].tradingsymbol] = _top(quote)
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
        for contract in contracts:
            quote = (quotes or {}).get(int(contract.token)) or (quotes or {}).get(str(contract.token))
            if quote:
                out[contract.tradingsymbol] = _top(quote)
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


def _top(quote: dict) -> dict:
    depth = quote.get("depth") or {}

    def best(side):
        levels = depth.get(side) or []
        price = float(levels[0].get("price") or 0) if levels else 0.0
        return price if price > 0 else None

    return {"bid": best("buy"), "ask": best("sell"), "ltp": float(quote.get("last_price") or 0) or None}


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

async def _claim(db_path: str, key: str, day: str, kind: str, trip: Optional[Trip], text: str,
                 summary: Optional[str], now: datetime) -> bool:
    """Record a message once; False when it was already recorded."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO partner_watch_messages(message_key,session_date,kind,exchange,tradingsymbol,"
            "position_key,created_at,sent,text,summary) VALUES(?,?,?,?,?,?,?,0,?,?)",
            (key, day, kind, trip.exchange if trip else None, trip.tradingsymbol if trip else None,
             trip.key if trip else None, now.isoformat(), text, summary))
        await db.commit()
    return cur.rowcount == 1


async def _mark_sent(db_path: str, key: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_watch_messages SET sent=1 WHERE message_key=?", (key,))
        await db.commit()


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


async def _send(db_path: str, key: str, day: str, kind: str, trip: Optional[Trip], text: str, now: datetime, *,
                summary: Optional[str] = None, keyboard: Optional[dict] = None) -> bool:
    """Claim, check quiet, send. Returns True when sent."""
    if kind not in QUIET_KEEPS and kind not in ("WATCH_ON", "PROMPT", "RECONNECT") and await quiet(db_path, day):
        return False
    if not await _claim(db_path, key, day, kind, trip, text, summary, now):
        return False
    from partner_bot import send_partner_result
    result = await send_partner_result(text, kind=f"watch_{kind.lower()}", reply_markup=keyboard)
    if result.delivered:
        await _mark_sent(db_path, key)
    logger.info("partner_watch_message kind=%s key=%s delivered=%s", kind, key, result.delivered)
    return result.delivered


async def _save_plan(db_path: str, trip: Trip, plan: Plan, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR REPLACE INTO partner_watch_plans(position_key,session_date,exchange,tradingsymbol,"
                         "computed_at,plan_json) VALUES(?,?,?,?,?,?)",
                         (trip.key, now.date().isoformat(), trip.exchange, trip.tradingsymbol, now.isoformat(),
                          json.dumps(asdict(plan))))
        await db.commit()


async def _load_plan(db_path: str, key: str) -> Optional[Plan]:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT plan_json FROM partner_watch_plans WHERE position_key=?",
                                      (key,))).fetchone()
    return Plan(**json.loads(row[0])) if row else None


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
class _State:
    day: Optional[str] = None
    trading_day: Optional[bool] = None
    login_at: Optional[str] = None
    seeded: bool = False
    orders: dict = field(default_factory=dict)     # order_id -> (status, trigger, filled)
    removals: dict = field(default_factory=dict)   # order_id -> (deadline, trigger, exchange, symbol)
    carried: list = field(default_factory=list)
    cash: Optional[float] = None
    looks_at: Optional[datetime] = None
    planned: set = field(default_factory=set)
    no_stop_checked: set = field(default_factory=set)
    lowered_told: set = field(default_factory=set)    # trips whose first stop move down was told
    close_checked: set = field(default_factory=set)


_state = _State()
_market = Market()


def reset() -> None:
    """Forget the in-memory watch (tests; a new day; a new login)."""
    global _state
    _state = _State()


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
    """The first read after a login: positions carried in and the day's cash."""
    try:
        positions = zerodha.option_positions(await zerodha._read("/portfolio/positions"))
        _state.carried = [p for p in positions if p["overnight_quantity"] > 0 and p["quantity"] > 0]
    except zerodha.BrokerError as exc:
        if exc.code == "TokenException":
            raise
        _state.carried = []
    try:
        account = zerodha.account_row(await zerodha._read("/user/margins/equity"))
        from partner_insights import cash_of
        _state.cash = cash_of(account) if account else None
    except zerodha.BrokerError as exc:
        if exc.code == "TokenException":
            raise
        _state.cash = None


async def watch_tick(now: Optional[datetime] = None, *, market: Optional[Market] = None) -> dict:
    """One look at the partner's book (see the module doc)."""
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
        rows = zerodha.option_orders(await zerodha._read("/orders"))
    except zerodha.BrokerError as exc:
        logger.warning("partner_watch_read_failed code=%s", exc.code)
        return {"status": "FAILED", "reason": exc.code}
    sent = await _events(db_path, day, rows, now, market)
    _state.seeded = True
    _state.orders = {r["order_id"]: (str(r.get("status") or "").upper(), zerodha._num(r.get("trigger_price")) or 0.0,
                                     int(r.get("filled_quantity") or 0)) for r in rows}
    return {"status": "COMPLETED", "sent": sent}


async def _events(db_path: str, day: str, rows: list, now: datetime, market: Market) -> int:
    trips = trips_from_orders(rows, _state.carried, now.date())
    open_trips = {(t.exchange, t.tradingsymbol): t for t in trips if t.open_qty}
    sent = 0
    seeded = _state.seeded
    # Refusals and stop moves are told only when seen happening (not from a book read after a restart).
    for row in rows:
        before = _state.orders.get(row["order_id"])
        status = str(row.get("status") or "").upper()
        trip = open_trips.get((row["exchange"], row["tradingsymbol"]))
        if status == "REJECTED" and seeded and (before is None or before[0] != "REJECTED"):
            trip_for_text = trip or Trip(key=str(row["order_id"]), exchange=row["exchange"],
                                         tradingsymbol=row["tradingsymbol"], product="", first_at=now)
            text = refused_text(row, rows, trip.open_qty if trip else None)
            sent += await _send(db_path, f"refused:{row['order_id']}", day, "REFUSED", trip_for_text, text, now,
                                summary="explained Zerodha's refusal")
        if before is None or row["transaction_type"] != "SELL":
            continue
        trigger = zerodha._num(row.get("trigger_price")) or 0.0
        if (trip is not None and before[0] == "TRIGGER PENDING" and status == "TRIGGER PENDING"
                and 0 < trigger < before[1] - 1e-6):
            sent += await _lowered(db_path, day, trip, row["order_id"], before[1], trigger, now)
        if (trip is not None and before[0] == "TRIGGER PENDING" and status == "CANCELLED"
                and not int(row.get("filled_quantity") or 0)):
            _state.removals[row["order_id"]] = (now + REMOVAL_GRACE, before[1], row["exchange"], row["tradingsymbol"])
    for order_id, (deadline, trigger, exchange, symbol) in list(_state.removals.items()):
        if now < deadline:
            continue
        del _state.removals[order_id]
        trip = open_trips.get((exchange, symbol))
        if trip is None:
            continue
        waiting = resting_stops(rows, exchange, symbol)
        if not waiting:
            plan = await _load_plan(db_path, trip.key)
            sent += await _send(db_path, f"removed:{order_id}", day, "REMOVED", trip,
                                removed_text(trip, trigger, plan), now, summary="stop cancelled, nothing in its place")
        else:
            new = max(zerodha._num(r.get("trigger_price")) or 0.0 for r in waiting)
            if new < trigger - 1e-6:
                sent += await _lowered(db_path, day, trip, order_id, trigger, new, now)
    for trip in trips:
        if not trip.open_qty or trip.carried:
            continue
        if trip.key not in _state.planned:
            _state.planned.add(trip.key)
            sent += await _plan(db_path, day, trip, trips, now, market, announce=now - trip.first_at <= PLAN_STALE)
        if (now - trip.first_at >= NO_STOP_AFTER and trip.key not in _state.no_stop_checked
                and not resting_stops(rows, trip.exchange, trip.tradingsymbol)):
            _state.no_stop_checked.add(trip.key)
            if await _gtt_protects(trip):
                continue
            plan = await _load_plan(db_path, trip.key)
            sent += await _send(db_path, f"nostop:{trip.key}", day, "NO_STOP", trip, no_stop_text(trip, plan), now,
                                summary="no stop order yet", keyboard=quiet_keyboard(day))
    if now.hour * 60 + now.minute >= CLOSE_WARN_MIN:
        for trip in open_trips.values():
            if trip.key not in _state.close_checked:
                _state.close_checked.add(trip.key)
                sent += await _close_warning(db_path, day, trip, now, market)
    if open_trips and (_state.looks_at is None or now - _state.looks_at >= LOOK_EVERY):
        _state.looks_at = now
        await _record_looks(db_path, day, list(open_trips.values()), now, market)
    return sent


async def _lowered(db_path: str, day: str, trip: Trip, order_id: str, old: float, new: float, now: datetime) -> int:
    plan = await _load_plan(db_path, trip.key)
    reason = lowered_reason(trip, old, new, plan, first=trip.key not in _state.lowered_told)
    _state.lowered_told.add(trip.key)
    if reason is None:
        logger.info("partner_watch_lowered_within_plan key=%s old=%.2f new=%.2f", trip.key, old, new)
        return 0
    return int(await _send(db_path, f"lowered:{order_id}:{new:.2f}", day, "LOWERED", trip,
                           lowered_text(trip, old, new, reason, plan), now,
                           summary=f"stop moved down {_px(old)} → {_px(new)}"))


async def _usual_share(db_path: str, trip: Trip, trips: list, now: datetime) -> Optional[float]:
    """[O24-SZ] The share of cash the partner usually puts into a buy: their
    Zerodha buys on earlier days (each against that day's cash), then today's
    trips before this one."""
    from partner_insights import USUAL_SIZE_LOOKBACK, usual_size
    day = now.date().isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            rows = await (await db.execute(
                "SELECT r.price, r.lots, r.lot_size, a.opening_balance, a.intraday_payin FROM partner_trade_reports r "
                "JOIN partner_account_days a ON a.session_date=r.session_date WHERE r.source='ZERODHA' "
                "AND r.action='BUY' AND r.status='ACTIVE' AND r.session_date<? ORDER BY r.trade_at DESC LIMIT ?",
                (day, USUAL_SIZE_LOOKBACK))).fetchall()
    except aiosqlite.OperationalError:
        rows = []
    shares = []
    for price, lots, lot_size, opening, payin in reversed(rows):
        cash = float(opening or 0) + float(payin or 0)
        if price and lots and lot_size and cash > 0:
            shares.append(float(price) * int(lots) * int(lot_size) / cash)
    if _state.cash:
        shares += [t.entry * t.bought / _state.cash for t in trips
                   if not t.carried and t.first_at < trip.first_at and t.entry]
    return usual_size(shares)


async def _gtt_protects(trip: Trip) -> bool:
    """A sell GTT waiting on the option also protects it. When the GTT list
    cannot be read nothing is claimed (True: no message)."""
    try:
        gtts = zerodha.stops_from_gtts(await zerodha._read("/gtt/triggers"))
    except zerodha.BrokerError as exc:
        logger.warning("partner_watch_gtts_unavailable code=%s", exc.code)
        return True
    return any(g["status"] == "PENDING" and g["exchange"] == trip.exchange and g["tradingsymbol"] == trip.tradingsymbol
               for g in gtts)


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


async def _plan(db_path: str, day: str, trip: Trip, trips: list, now: datetime, market: Market, *,
                announce: bool) -> int:
    contract = contract_of(trip.exchange, trip.tradingsymbol)
    option_bars, fut_bars, fut_price, mid = None, None, None, None
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
            quotes = await market.quote([c for c in (contract, future) if c is not None])
            mid = _mid(quotes.get(contract.tradingsymbol))
            fut_price = (quotes.get(future.tradingsymbol) or {}).get("ltp") if future is not None else None
        except Exception as exc:          # the plan says less, it never fails the tick
            logger.warning("partner_watch_market_failed err=%s", type(exc).__name__)
    plan = build_plan(entry=round(trip.entry, 2), qty=trip.open_qty, exchange=trip.exchange,
                      opt_type=getattr(contract, "instrument_type", None) or trip.tradingsymbol[-2:],
                      strike=float(getattr(contract, "strike", 0.0) or 0.0),
                      expiry=getattr(contract, "expiry", None), now=now, bought_at=trip.first_at, cash=_state.cash,
                      option_bars=option_bars, fut_bars=fut_bars, fut_price=fut_price, option_mid=mid)
    await _save_plan(db_path, trip, plan, now)
    if not announce:
        return 0
    lot = int(getattr(contract, "lot_size", 0) or 0)
    lots = trip.open_qty // lot if lot and trip.open_qty % lot == 0 else None
    text = plan_text(trip, plan, lots=lots, after_loss=_after_loss(trip, trips), day_line=_day_line(trip, trips),
                     usual=await _usual_share(db_path, trip, trips, now))
    return int(await _send(db_path, f"plan:{trip.key}", day, "PLAN", trip, text, now, summary=plan_summary(plan),
                           keyboard=quiet_keyboard(day)))


async def _close_warning(db_path: str, day: str, trip: Trip, now: datetime, market: Market) -> int:
    contract = contract_of(trip.exchange, trip.tradingsymbol)
    expiry_today = bool(contract is not None and getattr(contract, "expiry", None) == now.date())
    plan = await _load_plan(db_path, trip.key)
    text = close_text(trip, expiry_today=expiry_today, theta_day=plan.theta_day if plan else None)
    return int(await _send(db_path, f"close:{day}:{trip.tradingsymbol}", day, "CLOSE", trip, text, now,
                           summary="20 minutes to the close"))


async def _record_looks(db_path: str, day: str, trips: list, now: datetime, market: Market) -> None:
    contracts = {t.key: contract_of(t.exchange, t.tradingsymbol) for t in trips}
    wanted = [c for c in contracts.values() if c is not None]
    futures = {}
    for contract in wanted:
        future = contract.front_future(now.date())
        if future is not None:
            futures[contract.tradingsymbol] = future
    if not wanted:
        return
    try:
        quotes = await market.quote(wanted + list({f.tradingsymbol: f for f in futures.values()}.values()))
    except Exception as exc:
        logger.warning("partner_watch_looks_failed err=%s", type(exc).__name__)
        return
    async with aiosqlite.connect(db_path) as db:
        for key, contract in contracts.items():
            if contract is None or contract.tradingsymbol not in quotes:
                continue
            quote = quotes[contract.tradingsymbol]
            future = futures.get(contract.tradingsymbol)
            fut = (quotes.get(future.tradingsymbol) or {}).get("ltp") if future is not None else None
            await db.execute("INSERT OR IGNORE INTO partner_watch_looks(position_key,at,session_date,bid,ask,ltp,fut) "
                             "VALUES(?,?,?,?,?,?,?)", (key, now.isoformat(), day, quote.get("bid"), quote.get("ask"),
                                                       quote.get("ltp"), fut))
        await db.commit()


# ---------------------------------------------------------------------------
# login, morning prompt, reconnect, the quiet button
# ---------------------------------------------------------------------------

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
        await _send(db_path, f"on:{day}:{now.isoformat()}", day, "WATCH_ON", None,
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
    ok = await _send(db_path, f"prompt:{day}", day, "PROMPT", None, PROMPT_TEXT, now, keyboard=keyboard)
    return {"status": "COMPLETED", "sent": ok}


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
