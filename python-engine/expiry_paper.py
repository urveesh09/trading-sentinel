"""Expiry-day paper book: three pre-registered plays on the weekly index expiry.

Broker-free. It never imports an executor or places an order. Design, rules and
the reasoning behind them: docs/2026-10-05-expiry-day-paper-book.md.

The tick (``run_expiry_tick``) runs every 10 s from 12:59 to 15:40 IST. It acts
only for an underlying whose nearest option expiry is today according to the
instrument dump, so holiday shifts are handled by the exchange calendar: NIFTY
(NFO) on Tuesdays and SENSEX (BFO) on Thursdays. One quote batch per
underlying per tick (index, front future, ATM +/- 8 strikes of today's expiry
and every open leg) is logged with its timestamps and top-of-book quantities,
so the 15:15-15:40 auction window is recorded too.

A  Gamma breakout: the 13:00-13:30 index and futures range is the box. Two
   fresh observations no more than 25 s apart, both beyond the box with the
   future agreeing, buy the ATM option (or the next OTM strike if one ATM lot
   does not fit). Planned exits: -30% stop, failed-break and 8-minute time
   stops, bank half at +40% (a stop raised to entry x1.05), trails that
   tighten with gain and after 15:00. Flat from 15:13.
B  Auction strangle: at 15:13:30-15:15 buy the strikes either side of spot and
   hold through the closing auction; a leg that doubles banks half and trails;
   sold from 15:38.
C  Lottery ticket: on A's signal, the nearest strike priced 0.004%-0.03% of
   spot in that direction, held into the auction; bank half at 3x, trail after
   5x; sold from 15:38.

Loss ceiling: every entry is sized so that losing the whole premium plus its
charges fits the play's remaining ``EXPIRY_PAPER_BUDGET`` for the day. Stops are
planned exits only: a gap can fill below them, but never below zero premium.

Executable fills only: a buy walks the five-level ask depth of a quote no older
than ``QUOTE_MAX_AGE_SEC``, a sell walks the bid depth; whole lots only. An
exit that cannot be filled stays latched and is retried every tick. Whatever is
still open after 15:40 is settled by ``reconcile`` as an *assumed* valuation
(intrinsic at the post-auction index close, with exercise STT), or marked
UNRESOLVED at a full-premium loss; assumed values never mix with fills. Fills
from 15:15 are labelled AUCTION_WINDOW: continuous-market fills during the
closing auction are unverified (see cas_reachability_gate).

Telegram lines go to an outbox in the same transaction as the tick and are
marked sent only after a 2xx response (``flush_notices``). State lives in
``<DB_PATH>.expiry-paper.db``; nothing touches the operational ledger.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
import json
import logging
import math
import sqlite3
from typing import Awaitable, Callable, Optional

from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
RULES_VERSION = "expiry-v1"

INDEX_QUOTE_KEYS = {"NIFTY": "NSE:NIFTY 50", "SENSEX": "BSE:SENSEX"}
SPOT_KEY, FUT_KEY = -1, -2          # negative keys never collide with instrument tokens

TICK_START, SESSION_END = time(12, 59), time(15, 40)
BOX_START, BOX_END = time(13, 0), time(13, 30)
A_ENTRY_END, A_FLAT = time(15, 5), time(15, 13)
AUCTION_START, AUCTION_CLOSE_KNOWN = time(15, 15), time(15, 36)
B_ENTRY_START, B_ENTRY_END = time(15, 13, 30), time(15, 15)
FINAL_FLAT = time(15, 38)
CHAIN_WINDOW = 8
QUOTE_MAX_AGE_SEC, CLOCK_SKEW_SEC = 20.0, 5.0
MIN_BOX_SAMPLES = 30
BREAK_BUFFER_WIDTH, BREAK_BUFFER_SPOT = 0.15, 0.0002
CONFIRM_TICKS, CONFIRM_MAX_GAP_SEC = 2, 25.0
FAIL_BACK_WIDTH = 0.25
A_MAX_TRADES, A_MAX_LOTS = 2, 4
A_MAX_SPREAD, BC_MAX_SPREAD = 0.06, 0.10
B_MAX_LOTS, C_MAX_LOTS = 4, 10
C_PREMIUM_BAND = (0.00004, 0.0003)  # ask as a fraction of spot (NIFTY ~1.0-7.5)
EXERCISE_STT_PCT = 0.0015           # STT on the settlement value of an exercised ITM option
OPEN_STATUSES = ("OPEN",)


@dataclass(frozen=True)
class ExitPolicy:
    hard_stop: Optional[float]                  # planned stop: fraction of entry premium lost
    bank_at: Optional[float]                    # gain on the bid that sells half
    bank_stop: Optional[float]                  # stop as a multiple of entry once banked
    trails: tuple[tuple[float, float], ...]     # (peak gain reached, fraction of peak kept)
    late: Optional[tuple[time, float]]          # from this time, keep this fraction of a profitable peak
    time_stop: Optional[tuple[int, float]]      # (seconds, peak gain still not reached) closes the leg
    flat_at: time


POLICIES = {
    "A": ExitPolicy(hard_stop=0.30, bank_at=0.40, bank_stop=1.05, trails=((1.0, 0.70), (2.0, 0.80)),
                    late=(time(15, 0), 0.85), time_stop=(480, 0.15), flat_at=A_FLAT),
    "B": ExitPolicy(hard_stop=None, bank_at=1.0, bank_stop=None, trails=((1.0, 0.65),),
                    late=(time(15, 30), 0.80), time_stop=None, flat_at=FINAL_FLAT),
    "C": ExitPolicy(hard_stop=None, bank_at=2.0, bank_stop=None, trails=((4.0, 0.60),),
                    late=None, time_stop=None, flat_at=FINAL_FLAT),
}

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS expiry_paper_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, underlying TEXT NOT NULL, play TEXT NOT NULL,
        exchange TEXT NOT NULL, symbol TEXT NOT NULL, token INTEGER NOT NULL, strike REAL NOT NULL,
        opt_type TEXT NOT NULL, lot_size INTEGER NOT NULL, lots INTEGER NOT NULL, lots_open INTEGER NOT NULL,
        entry_ts TEXT NOT NULL, entry_price REAL NOT NULL, max_loss REAL NOT NULL, peak REAL NOT NULL,
        stop REAL NOT NULL, banked INTEGER NOT NULL DEFAULT 0, exit_pending TEXT, status TEXT NOT NULL,
        gross REAL NOT NULL DEFAULT 0, costs REAL NOT NULL DEFAULT 0, net_pnl REAL NOT NULL DEFAULT 0,
        assumed_pnl REAL, events TEXT NOT NULL DEFAULT '[]')""",
    """CREATE TABLE IF NOT EXISTS expiry_paper_days (
        day TEXT NOT NULL, underlying TEXT NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (day, underlying))""",
    """CREATE TABLE IF NOT EXISTS expiry_paper_ticks (
        day TEXT NOT NULL, underlying TEXT NOT NULL, ts TEXT NOT NULL, spot REAL, fut REAL,
        quotes TEXT NOT NULL, PRIMARY KEY (day, underlying, ts))""",
    """CREATE TABLE IF NOT EXISTS expiry_paper_notices (
        key TEXT PRIMARY KEY, message TEXT NOT NULL, created_at TEXT NOT NULL, sent_at TEXT,
        attempts INTEGER NOT NULL DEFAULT 0)""",
)


def expiry_db_path(db_path: str) -> str:
    return f"{db_path}.expiry-paper.db"


@contextmanager
def _store(path: str):
    """One transaction on the paper store; the handle is always closed."""
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        for statement in _SCHEMA:
            conn.execute(statement)
        with conn:
            yield conn


def _notice(conn, key: str, message: str, now: datetime) -> None:
    conn.execute("INSERT OR IGNORE INTO expiry_paper_notices (key, message, created_at) VALUES (?,?,?)",
                 (key, message, now.isoformat()))


async def flush_notices(send: Callable[[str], Awaitable[None]], db_path: Optional[str] = None,
                        now: Optional[datetime] = None) -> int:
    """Send unsent notices oldest first; ``send`` raises on failure, which stops the flush."""
    store = expiry_db_path(db_path or settings.DB_PATH)
    now = now or datetime.now(IST)
    with _store(store) as conn:
        pending = conn.execute("SELECT key, message, attempts FROM expiry_paper_notices WHERE sent_at IS NULL "
                               "ORDER BY created_at, key").fetchall()
    sent = 0
    for row in pending:
        try:
            await send(row["message"])
        except Exception as exc:
            if row["attempts"] % 30 == 0:
                logger.warning("expiry_paper_notice_failed key=%s attempts=%d err=%s",
                               row["key"], row["attempts"], type(exc).__name__)
            with _store(store) as conn:
                conn.execute("UPDATE expiry_paper_notices SET attempts = attempts + 1 WHERE key=?", (row["key"],))
            break
        with _store(store) as conn:
            conn.execute("UPDATE expiry_paper_notices SET sent_at=?, attempts = attempts + 1 WHERE key=?",
                         (now.isoformat(), row["key"]))
        sent += 1
    return sent


# ---------------------------------------------------------------------------
# quotes and fills
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Quote:
    bids: tuple[tuple[float, int], ...]         # (price, quantity), best first
    asks: tuple[tuple[float, int], ...]
    ltp: Optional[float]
    ts: Optional[datetime]

    @property
    def bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    def fresh(self, now: datetime) -> bool:
        if self.ts is None:
            return False
        age = (now - self.ts).total_seconds()
        return -CLOCK_SKEW_SEC <= age <= QUOTE_MAX_AGE_SEC

    def spread_ok(self, max_fraction: float) -> bool:
        return self.bid is not None and self.ask is not None and self.ask >= self.bid \
            and (self.ask - self.bid) <= max_fraction * self.ask

    def logged(self) -> list:
        return [self.bid, self.bids[0][1] if self.bids else None, self.ask,
                self.asks[0][1] if self.asks else None, self.ltp, self.ts.isoformat() if self.ts else None]


def _positive(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _provider_time(packet: dict) -> Optional[datetime]:
    raw = packet.get("timestamp") or packet.get("last_trade_time")
    if isinstance(raw, datetime):
        stamp = raw
    else:
        try:
            stamp = datetime.fromisoformat(str(raw).strip())
        except ValueError:
            return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=IST)


def parse_quote(packet: dict) -> Quote:
    depth = packet.get("depth") if isinstance(packet.get("depth"), dict) else {}

    def levels(side: str) -> tuple[tuple[float, int], ...]:
        out = []
        for level in depth.get(side) or []:
            if not isinstance(level, dict):
                break
            price, qty = _positive(level.get("price")), _positive(level.get("quantity"))
            if price is None or qty is None:
                break
            out.append((price, int(qty)))
        return tuple(out[:5])

    return Quote(bids=levels("buy"), asks=levels("sell"), ltp=_positive(packet.get("last_price")),
                 ts=_provider_time(packet))


def walk(levels: tuple[tuple[float, int], ...], lots: int, lot_size: int) -> tuple[int, Optional[float]]:
    """Whole lots the visible depth can fill (up to ``lots``) and their average price."""
    whole = min(lots * lot_size, sum(qty for _, qty in levels)) // lot_size
    if whole == 0:
        return 0, None
    qty, remaining, value = whole * lot_size, whole * lot_size, 0.0
    for price, level_qty in levels:
        take = min(level_qty, remaining)
        value += take * price
        remaining -= take
        if remaining == 0:
            break
    return whole, round(value / qty, 4)


def order_fee() -> float:
    """Charges of one order that do not scale with premium (flat brokerage and its GST)."""
    from fno_costs import calc_fno_costs

    return calc_fno_costs(0.0, 0.0, 1) / 2.0


def buy_charges(price: float, qty: int) -> float:
    """Charges of the single buy order, booked once at entry."""
    from fno_costs import calc_fno_costs

    return calc_fno_costs(price, 0.0, qty) - order_fee()


def sell_charges(price: float, qty: int) -> float:
    """Charges of one sell order (an exit slice)."""
    from fno_costs import calc_fno_costs

    return calc_fno_costs(0.0, price, qty) - order_fee()


def worst_case_loss(price: float, lots: int, lot_size: int) -> float:
    """Hard loss bound: the whole premium, the buy's charges, and one order fee per lot.

    An exit can be sliced into at most ``lots`` sell orders (each fills at
    least one whole lot), and a sell's proceeds always exceed its ad-valorem
    charges, so each slice costs at most one order fee net. Expiring
    worthless or exercising costs no more (exercise STT is under 1% of
    intrinsic).
    """
    qty = lots * lot_size
    return price * qty + buy_charges(price, qty) + lots * order_fee()


def affordable_fill(quotes: list[tuple[Quote, int]], budget: float, cap: int) -> tuple[int, list[float]]:
    """Largest common lot count (<= cap) whose worst-case loss over all legs fits ``budget``."""
    for lots in range(cap, 0, -1):
        prices, loss = [], 0.0
        for quote, lot_size in quotes:
            filled, price = walk(quote.asks, lots, lot_size)
            if filled < lots:
                break
            prices.append(price)
            loss += worst_case_loss(price, lots, lot_size)
        else:
            if loss <= budget:
                return lots, prices
    return 0, []


def fill_model(clock: time) -> str:
    return "AUCTION_WINDOW" if clock >= AUCTION_START else "CONTINUOUS"


# ---------------------------------------------------------------------------
# pure rules
# ---------------------------------------------------------------------------

def new_day_state() -> dict:
    return {"rules": RULES_VERSION, "box": None, "box_samples": [], "box_status": "BUILDING",
            "pending": None, "armed": {"UP": True, "DOWN": True}, "signals": [],
            "trades": {"A": 0, "B": 0, "C": 0}, "last_spot": None, "summary_queued": False}


def update_box(state: dict, now: time, spot: Optional[float], fut: Optional[float]) -> None:
    """Collect fresh 13:00-13:30 samples, then freeze the box once (or mark it unusable)."""
    if state["box_status"] != "BUILDING":
        return
    if BOX_START <= now < BOX_END:
        if spot is not None and fut is not None:
            state["box_samples"].append([spot, fut])
        return
    if now < BOX_END:
        return
    samples, state["box_samples"] = state["box_samples"], []
    if len(samples) < MIN_BOX_SAMPLES:
        state["box_status"] = f"UNUSABLE_{len(samples)}_SAMPLES"
        return
    state["box"] = {"hi": max(s for s, _ in samples), "lo": min(s for s, _ in samples),
                    "fut_hi": max(f for _, f in samples), "fut_lo": min(f for _, f in samples),
                    "n": len(samples)}
    state["box_status"] = "READY"


def breakout_signal(state: dict, now: datetime, spot: Optional[float], fut: Optional[float]) -> Optional[str]:
    """'UP'/'DOWN' when a confirmed, armed break fires in the entry window, else None.

    ``spot`` and ``fut`` must be fresh observations (None otherwise). A missing
    observation, a futures disagreement or a gap over CONFIRM_MAX_GAP_SEC
    restarts the confirmation count.
    """
    box = state["box"]
    if state["box_status"] != "READY":
        return None
    if spot is None or fut is None:
        state["pending"] = None
        return None
    width = box["hi"] - box["lo"]
    buffer = max(BREAK_BUFFER_WIDTH * width, BREAK_BUFFER_SPOT * spot)
    if box["lo"] <= spot <= box["hi"]:
        state["armed"] = {"UP": True, "DOWN": True}
    direction = None
    if spot > box["hi"] + buffer and fut > box["fut_hi"]:
        direction = "UP"
    elif spot < box["lo"] - buffer and fut < box["fut_lo"]:
        direction = "DOWN"
    if direction is None:
        state["pending"] = None
        return None
    pending = state["pending"]
    close_enough = pending is not None and pending["dir"] == direction and \
        0 < (now - datetime.fromisoformat(pending["ts"])).total_seconds() <= CONFIRM_MAX_GAP_SEC
    count = pending["count"] + 1 if close_enough else 1
    state["pending"] = {"dir": direction, "count": count, "ts": now.isoformat()}
    if count < CONFIRM_TICKS or not state["armed"][direction] or not BOX_END <= now.time() < A_ENTRY_END:
        return None
    state["armed"][direction] = False
    return direction


def failed_break(state: dict, opt_type: str, spot: Optional[float]) -> bool:
    """A's structure stop: the index is back inside the box by a quarter of its width."""
    box = state["box"]
    if box is None or spot is None:
        return False
    width = box["hi"] - box["lo"]
    if opt_type == "CE":
        return spot < box["hi"] - FAIL_BACK_WIDTH * width
    return spot > box["lo"] + FAIL_BACK_WIDTH * width


def manage_position(pos: dict, policy: ExitPolicy, bid: float, now: datetime,
                    structure_broken: bool = False) -> Optional[tuple[int, str]]:
    """Update peak/stop in ``pos`` and return the planned (lots to sell, reason) or None.

    Stops are checked on each observed bid; a gap between checks can fill
    below the stop. A one-lot position cannot bank half: it only raises its stop.
    """
    entry = pos["entry_price"]
    pos["peak"] = max(pos["peak"], bid)
    peak_gain = pos["peak"] / entry - 1.0
    stop = pos["stop"]
    if pos["banked"] and policy.bank_stop is not None:
        stop = max(stop, entry * policy.bank_stop)
    for threshold, keep in policy.trails:
        if peak_gain >= threshold:
            stop = max(stop, pos["peak"] * keep)
    profit_stage = policy.bank_at if policy.bank_at is not None else policy.trails[0][0]
    if policy.late and now.time() >= policy.late[0] and peak_gain >= profit_stage:
        stop = max(stop, pos["peak"] * policy.late[1])
    pos["stop"] = round(stop, 2)

    lots = pos["lots_open"]
    if now.time() >= policy.flat_at:
        return lots, "FLAT_TIME"
    if pos["stop"] > 0 and bid <= pos["stop"]:
        return lots, "TRAIL" if pos["stop"] >= entry else "STOP"
    if structure_broken:
        return lots, "FAILED_BREAK"
    if policy.time_stop and not pos["banked"]:
        seconds, needed = policy.time_stop
        held = (now - datetime.fromisoformat(pos["entry_ts"])).total_seconds()
        if held >= seconds and peak_gain < needed:
            return lots, "TIME_STOP"
    if policy.bank_at is not None and not pos["banked"] and bid >= entry * (1.0 + policy.bank_at):
        pos["banked"] = 1
        if policy.bank_stop is not None:
            pos["stop"] = round(max(pos["stop"], entry * policy.bank_stop), 2)
        if lots >= 2:
            return lots // 2, "BANK_HALF"
    return None


def pick_lottery_strike(chain: dict, direction: str, spot: float, now: datetime) -> Optional[float]:
    """Nearest-to-money OTM strike whose fresh ask sits inside the lottery band."""
    lo, hi = (spot * f for f in C_PREMIUM_BAND)
    opt_type = "CE" if direction == "UP" else "PE"
    eligible = [strike for (strike, kind), (_, q) in chain.items()
                if kind == opt_type and (strike > spot if kind == "CE" else strike < spot)
                and q.fresh(now) and q.ask is not None and lo <= q.ask <= hi and q.spread_ok(BC_MAX_SPREAD)]
    if not eligible:
        return None
    return min(eligible) if opt_type == "CE" else max(eligible)


# ---------------------------------------------------------------------------
# positions
# ---------------------------------------------------------------------------

def _rows(conn, sql: str, args: tuple) -> list[dict]:
    positions = [dict(row) for row in conn.execute(sql, args).fetchall()]
    for pos in positions:
        pos["_events"] = []
    return positions


def _realized(conn, day: str, underlying: str, play: str) -> float:
    return float(conn.execute(
        "SELECT COALESCE(SUM(net_pnl + COALESCE(assumed_pnl, 0)), 0) FROM expiry_paper_positions "
        "WHERE day=? AND underlying=? AND play=?", (day, underlying, play)).fetchone()[0])


def _sell(pos: dict, lots: int, price: float, reason: str, now: datetime) -> dict:
    """Book one exit slice: its gross and its own sell-order charges (the buy was charged at entry)."""
    qty = lots * pos["lot_size"]
    gross = (price - pos["entry_price"]) * qty
    costs = sell_charges(price, qty)
    pos["lots_open"] -= lots
    pos["gross"] = round(pos["gross"] + gross, 2)
    pos["costs"] = round(pos["costs"] + costs, 2)
    pos["net_pnl"] = round(pos["gross"] - pos["costs"], 2)
    if pos["lots_open"] == 0:
        pos["status"], pos["exit_pending"] = "CLOSED", None
    event = {"ts": now.isoformat(), "action": reason, "lots": lots, "price": price,
             "net": round(gross - costs, 2), "fill_model": fill_model(now.time())}
    pos["_events"].append(event)
    return event


def _new_position(day: str, underlying: str, play: str, exchange: str, contract, price: float,
                  lots: int, now: datetime) -> dict:
    policy = POLICIES[play]
    charges = round(buy_charges(price, lots * contract.lot_size), 2)
    return {"id": None, "day": day, "underlying": underlying, "play": play, "exchange": exchange,
            "symbol": contract.tradingsymbol, "token": contract.token, "strike": contract.strike,
            "opt_type": contract.instrument_type, "lot_size": contract.lot_size, "lots": lots,
            "lots_open": lots, "entry_ts": now.isoformat(), "entry_price": price,
            "max_loss": round(worst_case_loss(price, lots, contract.lot_size), 2), "peak": price,
            "stop": round(price * (1 - policy.hard_stop), 2) if policy.hard_stop else 0.0,
            "banked": 0, "exit_pending": None, "status": "OPEN", "gross": 0.0, "costs": charges,
            "net_pnl": -charges, "assumed_pnl": None,
            "_events": [{"ts": now.isoformat(), "action": "BUY", "lots": lots, "price": price,
                         "charges": charges, "fill_model": fill_model(now.time())}]}


def _save_position(conn, pos: dict) -> None:
    columns = [c for c in pos if not c.startswith("_") and c not in ("id", "events")]
    if pos["id"] is None:
        cursor = conn.execute(
            f"INSERT INTO expiry_paper_positions ({', '.join(columns)}, events) "
            f"VALUES ({', '.join('?' for _ in columns)}, ?)",
            [pos[c] for c in columns] + [json.dumps(pos["_events"])])
        pos["id"] = cursor.lastrowid
    else:
        prior = json.loads(conn.execute("SELECT events FROM expiry_paper_positions WHERE id=?",
                                        (pos["id"],)).fetchone()[0])
        conn.execute(f"UPDATE expiry_paper_positions SET {', '.join(f'{c}=?' for c in columns)}, events=? "
                     "WHERE id=?", [pos[c] for c in columns] + [json.dumps(prior + pos["_events"]), pos["id"]])
    pos["_events"] = []


def _try_exit(pos: dict, quote: Optional[Quote], lots: int, reason: str, now: datetime) -> Optional[dict]:
    """Sell what the fresh bid depth can fill now; latch the rest as a pending exit."""
    if quote is not None and quote.fresh(now):
        filled, price = walk(quote.bids, lots, pos["lot_size"])
        if filled:
            event = _sell(pos, filled, price, reason, now)
            if pos["status"] == "OPEN" and reason != "BANK_HALF":
                pos["exit_pending"] = reason
            return event
    if reason == "BANK_HALF":
        pos["banked"] = 0                   # retry the bank on the next observation
    else:
        pos["exit_pending"] = reason
    return None


# ---------------------------------------------------------------------------
# settlement of anything still open after the session
# ---------------------------------------------------------------------------

def _settlement_spot(conn, day: str, underlying: str) -> Optional[float]:
    """The last index quote we sampled after the closing auction (15:36-15:40), if any.

    This is our own sample, not the exchange's published settlement price.
    """
    row = conn.execute("SELECT spot FROM expiry_paper_ticks WHERE day=? AND underlying=? AND spot IS NOT NULL "
                       "AND substr(ts, 12, 8) >= ? ORDER BY ts DESC LIMIT 1",
                       (day, underlying, AUCTION_CLOSE_KNOWN.isoformat())).fetchone()
    return float(row["spot"]) if row else None


def reconcile(db_path: Optional[str] = None, now: Optional[datetime] = None) -> int:
    """Settle every leg still open after its expiry session; returns the number settled.

    With a sampled post-auction index quote the residual is valued at
    intrinsic less exercise STT (SETTLED_ASSUMED); without one it is
    UNRESOLVED at its remaining worst case. The buy's charges were booked at
    entry. Both are assumed valuations kept in ``assumed_pnl``, never
    executable fills. Day summaries are queued here.
    """
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    after_session = now.time() >= SESSION_END
    settled = 0
    with _store(expiry_db_path(db_path or settings.DB_PATH)) as conn:
        stale = _rows(conn, "SELECT * FROM expiry_paper_positions WHERE status='OPEN' AND (day < ? OR "
                            "(day = ? AND ?))", (today, today, int(after_session)))
        for pos in stale:
            qty = pos["lots_open"] * pos["lot_size"]
            spot = _settlement_spot(conn, pos["day"], pos["underlying"])
            if spot is None:
                pos["status"] = "UNRESOLVED"
                pos["assumed_pnl"] = round(-(pos["entry_price"] * qty + pos["lots_open"] * order_fee()), 2)
            else:
                intrinsic = max(0.0, spot - pos["strike"]) if pos["opt_type"] == "CE" \
                    else max(0.0, pos["strike"] - spot)
                pos["status"] = "SETTLED_ASSUMED"
                pos["assumed_pnl"] = round((intrinsic * (1 - EXERCISE_STT_PCT) - pos["entry_price"]) * qty, 2)
            pos["_events"].append({"ts": now.isoformat(), "action": pos["status"], "lots": pos["lots_open"],
                                   "settlement_spot": spot, "settlement_source": "SAMPLED_INDEX_QUOTE",
                                   "assumed_pnl": pos["assumed_pnl"]})
            _save_position(conn, pos)
            settled += 1
        days = conn.execute("SELECT day, underlying, state FROM expiry_paper_days WHERE day < ? OR (day = ? AND ?)",
                            (today, today, int(after_session))).fetchall()
        for row in days:
            state = json.loads(row["state"])
            if state["summary_queued"]:
                continue
            state["summary_queued"] = True
            _notice(conn, f"{row['day']}:{row['underlying']}:summary",
                    format_day_summary(conn, row["day"], row["underlying"], state), now)
            conn.execute("UPDATE expiry_paper_days SET state=?, updated_at=? WHERE day=? AND underlying=?",
                         (json.dumps(state), now.isoformat(), row["day"], row["underlying"]))
    return settled


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

def _load_state(conn, day: str, underlying: str) -> dict:
    row = conn.execute("SELECT state FROM expiry_paper_days WHERE day=? AND underlying=?",
                       (day, underlying)).fetchone()
    return json.loads(row["state"]) if row else new_day_state()


def _chain(book, expiry: date, spot: float) -> dict:
    """{(strike, 'CE'|'PE'): Contract} for today's expiry around spot."""
    from fno_models import OptionType

    out = {}
    for strike in book.strikes_window(spot, CHAIN_WINDOW):
        for kind in (OptionType.CE, OptionType.PE):
            contract = book.option(expiry, strike, kind)
            if contract is not None:
                out[(float(strike), kind.value)] = contract
    return out


async def _fetch(kite, underlying: str, exchange: str, contracts: list, future) -> dict:
    request = {SPOT_KEY: INDEX_QUOTE_KEYS[underlying]}
    if future is not None:
        request[FUT_KEY] = f"{exchange}:{future.tradingsymbol}"
    request.update({c.token: f"{exchange}:{c.tradingsymbol}" for c in contracts})
    return await kite.get_quote_by_instruments(request)


def _fresh_price(packet: Optional[dict], now: datetime) -> Optional[float]:
    if not isinstance(packet, dict):
        return None
    quote = parse_quote(packet)
    return quote.ltp if quote.fresh(now) else None


async def _tick_underlying(kite, conn, book, underlying: str, exchange: str, now: datetime) -> None:
    day = now.date().isoformat()
    clock = now.time()
    state = _load_state(conn, day, underlying)
    positions = _rows(conn, "SELECT * FROM expiry_paper_positions WHERE day=? AND underlying=? AND status='OPEN'",
                      (day, underlying))
    future = book.front_future(now.date())

    anchor = state["last_spot"]
    if anchor is None:
        first = await _fetch(kite, underlying, exchange, [], future)
        anchor = _positive((first.get(SPOT_KEY) or {}).get("last_price"))
        if anchor is None:
            return
    chain = _chain(book, now.date(), anchor)
    held = [book.by_symbol.get(pos["symbol"]) for pos in positions]
    contracts = {c.token: c for c in [*chain.values(), *(c for c in held if c is not None)]}
    raw = await _fetch(kite, underlying, exchange, list(contracts.values()), future)
    spot = _fresh_price(raw.get(SPOT_KEY), now)
    fut = _fresh_price(raw.get(FUT_KEY), now)
    quotes = {token: parse_quote(raw[token]) for token in contracts if isinstance(raw.get(token), dict)}
    quoted_chain = {key: (c, quotes[c.token]) for key, c in chain.items() if c.token in quotes}
    if spot is not None:
        state["last_spot"] = spot
    state["ticks"] = state.get("ticks", 0) + 1
    for name, value in (("stale_spot", spot), ("stale_fut", fut)):
        if value is None:
            state[name] = state.get(name, 0) + 1
    conn.execute("INSERT OR REPLACE INTO expiry_paper_ticks VALUES (?,?,?,?,?,?)", (
        day, underlying, now.isoformat(), spot, fut,
        json.dumps({"fill_model": fill_model(clock),
                    "legs": {contracts[t].tradingsymbol: q.logged() for t, q in quotes.items()}},
                   separators=(",", ":"))))

    label = f"Expiry paper {underlying}"

    def notify(pos: dict, text: str) -> None:
        _notice(conn, f"{day}:{underlying}:{pos['id']}:{now.isoformat()}", f"{label} {pos['play']}: {text}", now)

    # 1. manage what is open
    for pos in positions:
        quote = quotes.get(pos["token"])
        if pos["exit_pending"]:
            event = _try_exit(pos, quote, pos["lots_open"], pos["exit_pending"], now)
        elif quote is not None and quote.fresh(now) and quote.bid is not None:
            structure = pos["play"] == "A" and failed_break(state, pos["opt_type"], spot)
            action = manage_position(pos, POLICIES[pos["play"]], quote.bid, now, structure_broken=structure)
            event = _try_exit(pos, quote, *action, now) if action else None
        elif clock >= POLICIES[pos["play"]].flat_at:
            event = _try_exit(pos, None, pos["lots_open"], "FLAT_TIME", now)
        else:
            event = None
        _save_position(conn, pos)
        if event is not None:
            notify(pos, f"SELL {event['lots']} lot {pos['symbol']} @ {event['price']:.2f} ({event['action']}"
                        f"{', auction window' if event['fill_model'] == 'AUCTION_WINDOW' else ''}), "
                        f"slice net Rs {event['net']:+,.0f}")

    # 2. the afternoon box and A/C entries
    update_box(state, clock, spot, fut)
    direction = breakout_signal(state, now, spot, fut)
    budget = float(settings.EXPIRY_PAPER_BUDGET)
    if direction is not None:
        state["signals"].append({"ts": now.isoformat(), "dir": direction, "spot": spot, "fut": fut})
        kind = "CE" if direction == "UP" else "PE"
        open_a = any(p["play"] == "A" and p["status"] == "OPEN" for p in positions)
        remaining = budget + min(0.0, _realized(conn, day, underlying, "A"))
        if state["trades"]["A"] < A_MAX_TRADES and not open_a and remaining > 0:
            atm = book.atm_strike(spot)
            step = book.strike_step if kind == "CE" else -book.strike_step
            for strike in (float(atm), float(atm + step)):          # ATM, else one strike OTM
                candidate = quoted_chain.get((strike, kind))
                if not candidate or not candidate[1].fresh(now) or not candidate[1].spread_ok(A_MAX_SPREAD):
                    continue
                contract, quote = candidate
                lots, prices = affordable_fill([(quote, contract.lot_size)], remaining, A_MAX_LOTS)
                if lots:
                    pos = _new_position(day, underlying, "A", exchange, contract, prices[0], lots, now)
                    _save_position(conn, pos)
                    state["trades"]["A"] += 1
                    notify(pos, f"BUY {lots} lot {contract.tradingsymbol} @ {prices[0]:.2f} (break {direction}, "
                                f"spot {spot:,.1f}, planned stop {pos['stop']:.2f}, max loss Rs {pos['max_loss']:,.0f})")
                    break
        if state["trades"]["C"] < 1:
            strike = pick_lottery_strike(quoted_chain, direction, spot, now)
            if strike is not None:
                contract, quote = quoted_chain[(strike, kind)]
                lots, prices = affordable_fill([(quote, contract.lot_size)], budget, C_MAX_LOTS)
                if lots:
                    pos = _new_position(day, underlying, "C", exchange, contract, prices[0], lots, now)
                    _save_position(conn, pos)
                    state["trades"]["C"] += 1
                    notify(pos, f"BUY {lots} lot {contract.tradingsymbol} @ {prices[0]:.2f} (lottery {direction}, "
                                f"held into the auction, max loss Rs {pos['max_loss']:,.0f})")

    # 3. B: the auction strangle
    if state["trades"]["B"] == 0 and B_ENTRY_START <= clock < B_ENTRY_END and spot is not None:
        step = book.strike_step
        legs = [quoted_chain.get((float(math.ceil(spot / step) * step), "CE")),
                quoted_chain.get((float(math.floor(spot / step) * step), "PE"))]
        if all(leg and leg[1].fresh(now) and leg[1].spread_ok(BC_MAX_SPREAD) for leg in legs):
            lots, prices = affordable_fill([(q, c.lot_size) for c, q in legs], budget, B_MAX_LOTS)
            if lots:
                opened = []
                for (contract, _), price in zip(legs, prices):
                    pos = _new_position(day, underlying, "B", exchange, contract, price, lots, now)
                    _save_position(conn, pos)
                    opened.append(pos)
                state["trades"]["B"] = 1
                notify(opened[0], f"BUY {lots} lot strangle "
                                  + " + ".join(f"{p['symbol']} @ {p['entry_price']:.2f}" for p in opened)
                                  + f", max loss Rs {sum(p['max_loss'] for p in opened):,.0f}")

    conn.execute("INSERT OR REPLACE INTO expiry_paper_days VALUES (?,?,?,?)",
                 (day, underlying, json.dumps(state), now.isoformat()))


def format_day_summary(conn, day: str, underlying: str, state: dict) -> str:
    lines = [f"Expiry paper {underlying} {day} ({RULES_VERSION}), box {state['box_status']}, "
             f"signals {len(state['signals'])}, ticks {state.get('ticks', 0)} "
             f"(stale index {state.get('stale_spot', 0)}, stale future {state.get('stale_fut', 0)})"]
    for play in ("A", "B", "C"):
        rows = conn.execute("SELECT symbol, status, net_pnl, assumed_pnl, events FROM expiry_paper_positions "
                            "WHERE day=? AND underlying=? AND play=?", (day, underlying, play)).fetchall()
        if not rows:
            lines.append(f"  {play}: no trade")
            continue
        filled = sum(r["net_pnl"] for r in rows)
        assumed = sum(r["assumed_pnl"] or 0.0 for r in rows)
        auction = any(e.get("fill_model") == "AUCTION_WINDOW" for r in rows for e in json.loads(r["events"]))
        detail = ", ".join(f"{r['symbol']} {r['status']}" for r in rows)
        line = f"  {play}: filled Rs {filled:+,.0f}"
        if any(r["assumed_pnl"] is not None for r in rows):
            line += f", assumed Rs {assumed:+,.0f} [our sampled index, not the official settlement]"
        lines.append(line + f" ({detail}{'; auction-window fills unverified' if auction else ''})")
    totals = conn.execute(
        "SELECT play, COALESCE(SUM(net_pnl), 0), COALESCE(SUM(assumed_pnl), 0) FROM expiry_paper_positions "
        "WHERE underlying=? AND status != 'OPEN' GROUP BY play", (underlying,)).fetchall()
    expiries = conn.execute("SELECT COUNT(*) FROM expiry_paper_days WHERE underlying=?", (underlying,)).fetchone()[0]
    if totals:
        lines.append(f"  {underlying} to date over {expiries} expiries, filled: " + ", ".join(
            f"{r[0]} Rs {r[1]:+,.0f}" for r in totals))
        if any(r[2] for r in totals):
            lines.append("  assumed settlements, kept apart: " + ", ".join(
                f"{r[0]} Rs {r[2]:+,.0f}" for r in totals if r[2]))
    return "\n".join(lines)


async def run_expiry_tick(kite, db_path: Optional[str] = None, now: Optional[datetime] = None,
                          books: Optional[dict] = None) -> None:
    """One 10-second step for every underlying expiring today (notices go to the outbox)."""
    now = now or datetime.now(IST)
    if not TICK_START <= now.time() <= SESSION_END:
        return
    from fno_underlyings import SPECS, get_instruments_for

    path = db_path or settings.DB_PATH
    reconcile(path, now)                    # anything left from an earlier expiry
    names = [n.strip().upper() for n in settings.EXPIRY_PAPER_UNDERLYINGS.split(",") if n.strip()]
    for name in names:
        if name not in INDEX_QUOTE_KEYS or name not in SPECS:
            continue
        book = (books or {}).get(name) or get_instruments_for(name)
        if not book.ready(now.date()) or not book.is_expiry_day(now.date()):
            continue
        with _store(expiry_db_path(path)) as conn:
            await _tick_underlying(kite, conn, book, name, SPECS[name].segment, now)
