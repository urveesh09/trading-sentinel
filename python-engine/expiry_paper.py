"""Expiry-day paper book: three pre-registered plays on the weekly index expiry.

Broker-free. It never imports an executor or places an order. Design, rules and
the reasoning behind them: docs/2026-10-05-expiry-day-paper-book.md.

The tick (``run_expiry_tick``) runs every 10 s from 12:59 to 15:40 IST. It acts
only for an underlying whose nearest option expiry is today according to the
instrument dump, so holiday shifts are handled by the exchange calendar: NIFTY
(NFO) on Tuesdays and SENSEX (BFO) on Thursdays. One quote batch per
underlying per tick (index, front future, ATM +/- 8 strikes of today's expiry
and every open leg) is logged with its timestamps and full five-level depth,
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
exit that cannot be filled stays latched and is retried every tick; a bank
that fills only partly keeps its unfilled lots pending. Whatever is
still open after 15:40 is settled by ``reconcile`` as an *assumed* valuation
(intrinsic at the post-auction index close, with exercise STT), or marked
UNRESOLVED at a full-premium loss; assumed values never mix with fills. Fills
from 15:15 are labelled AUCTION_WINDOW: continuous-market fills during the
closing auction are unverified (see cas_reachability_gate).

Clocks (execution contract ``EXECUTION_VERSION``): the tick's start time only
decides whether to run. Freshness, windows, fills and event times use the
decision time read after the quotes arrive, so limiter or network delay can
neither pass an old packet nor refuse a new one. Each tick row keeps both
times, the limiter/transport timing, the full five-level depth of every leg,
and the index/future packets with their refusal reason. An expiry whose index
never answers is still recorded, so it stays in the learning denominator.

Charges come from the contract's exchange schedule (NSE for NFO, BSE for BFO)
and are frozen on the position at entry, so exits and settlement use the
rates the ceiling was sized with.

Chain context (``CONTEXT_VERSION``) is recorded on every tick and read by no
rule: the ATM straddle (the expected absolute move to settlement) and the
volatility it implies, the index's realized volatility so far, OI and its change
per strike with the walls, max pain and PCR over the fetched window, and the
future's OI build-up. Snapshots at the A/C signals and the D and B entry times
let later expiries test whether the context separates winners from losers.

Every open entry is also marked on each tick at what selling all of it on the
visible depth would net after fees (``liquidation_net``). The summary prints
each entry's best and worst mark beside its finish. The marks are not fills,
and BP's pair target is the only rule that reads one. Shadow plays
(``SHADOW_VERSION``) run on the same quotes and are listed only in the summary.

Telegram lines go to an outbox in the same transaction as the tick and are
marked sent when a 2xx acknowledgement arrives (``flush_notices``); flushes
of one store are serialised, so delivery is at-least-once without concurrent
duplicates. State lives in ``<DB_PATH>.expiry-paper.db``; nothing touches the
operational ledger.
"""
from __future__ import annotations

import asyncio
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
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
RULES_VERSION = "expiry-v1"             # strategy thresholds, frozen for forward comparison
EXECUTION_VERSION = "expiry-exec-v2"    # clock/data/fill contract; v1 judged freshness at request start

INDEX_QUOTE_KEYS = {"NIFTY": "NSE:NIFTY 50", "SENSEX": "BSE:SENSEX"}
SPOT_KEY, FUT_KEY = -1, -2          # negative keys never collide with instrument tokens

TICK_START, SESSION_END = time(12, 59), time(15, 40)
BOX_START, BOX_END = time(13, 0), time(13, 30)
A_ENTRY_END, A_FLAT = time(15, 5), time(15, 13)
AUCTION_START, AUCTION_CLOSE_KNOWN = time(15, 15), time(15, 36)
B_ENTRY_START, B_ENTRY_END = time(15, 13, 30), time(15, 15)
FINAL_FLAT = time(15, 38)
TICK_SEC = 10
# Ten-second starts from 12:59:00 through 15:39:50: the scheduler's 15:40:00
# callback starts a fraction of a second after SESSION_END and never runs
# (Oct 8 audit T5: 925 ticks + 41 skips = 966, not 967).
EXPECTED_SLOTS = ((SESSION_END.hour - TICK_START.hour) * 3600
                  + (SESSION_END.minute - TICK_START.minute) * 60) // TICK_SEC
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

# Shadow plays, frozen on 2026-10-06 before their first expiry (October 8) and
# scored beside expiry-v1 after the same 20 expiries. They never send their own
# Telegram lines; the day summary reports them in a separate section.
#   BH    B's strangle held through the auction: no bank, no trail, sold at 15:38.
#   C500  C with a Rs 500 ceiling instead of the full budget.
#   D     Short iron condor held to cash settlement, entered 14:30-14:45: sell
#         the strikes two steps either side of ATM and buy the next strike out
#         as the wing; when that does not fit the ceiling, one step, then ATM
#         (an iron butterfly). NIFTY's 65-unit lot and 50-point step make a
#         50-point wing risk Rs 3,250 a lot less the credit, so it usually
#         needs a nearer short strike than SENSEX (20 units, 100 points).
#
# expiry-shadow-v2 adds two plays, frozen on 2026-10-08 after the first SENSEX
# expiry and scored only on expiries from October 13 (the two expiries already
# seen are not evidence for them). BH, C500 and D are unchanged.
#   AL    A whose one-lot position, unable to bank half, keeps half of its peak
#         gain once it reaches the bank level. Selling half at the bank level
#         locks half the gain; AL locks the same half as the peak rises. With
#         two or more lots it is A.
#   BP    B's strangle managed as one trade: no per-leg bank or trail; both
#         legs are sold once selling the pair on the visible bids would net
#         BP_TARGET of the premium paid, after all charges; else sold at 15:38.
SHADOW_VERSION = "expiry-shadow-v2"
MAIN_PLAYS, SHADOW_PLAYS = ("A", "B", "C"), ("BH", "C500", "D", "AL", "BP")
AL_LOCK_GAIN = 0.5                  # fraction of the peak gain a banked one-lot AL keeps
BP_TARGET = 0.20                    # pair liquidation net, as a fraction of the premium paid
C500_BUDGET = 500.0
D_ENTRY_START, D_ENTRY_END = time(14, 30), time(14, 45)
D_SHORT_STEPS, D_WING_STEPS, D_MAX_LOTS = 2, 1, 4  # widest sold strikes tried first
D_MIN_CREDIT_X_CHARGES = 2.0        # the credit must cover at least twice the entry charges
D_STT_RESERVE_MOVE = 0.05           # exercise STT reserved on a long wing up to 5% of spot in the money
# [EXPIRY-D-RESERVE 2026-10-07, audit T2] D's max_loss is a bound only for a
# settlement move inside that 5% domain: exercise STT on the long wing grows
# with its intrinsic, so a larger move (the audit's +20% stress: -Rs 3,000.43
# against a Rs 2,298.44 bound) costs more. Sizing is frozen (expiry-shadow-v1)
# and the loss is never capped; settlement records a RESERVE_BREACH event and
# the day summary prints the STT beyond the reserve.

# Chain context, record-only from 2026-10-07 (no rule reads it). Implied and
# realized volatility share one clock, the 375-minute NSE session year, so their
# ratio compares like with like. Max pain, walls and PCR cover only the fetched
# ATM +/- CHAIN_WINDOW strikes, where most same-day OI sits.
CONTEXT_VERSION = "expiry-context-v1.1"     # v1.1 (Oct 8): OI from fresh quotes only, with coverage
# The horizon of the implied volatility: our approximation of when the
# settlement price is fixed (the closing auction's end). It is not verified for
# BFO; IV is not computed after it.
SETTLE_AT = time(15, 35)
TRADING_YEAR_SEC = 252 * 375 * 60
RV_SAMPLE_SEC = 60.0                # index returns sampled at least a minute apart (less tick noise)
RV_MIN_SEC = 600.0                  # realized volatility needs ten minutes of samples
CONTEXT_MOMENTS = {"d_entry": D_ENTRY_START, "b_entry": B_ENTRY_START}

# The owner's decision rule, set on 2026-10-08 after two losing expiries
# (October 6 NIFTY, October 8 SENSEX): observe up to OWNER_REVIEW_EXPIRIES
# expiries in all. If the main book loses on every one, expiry-day F&O trading
# stops; a play that keeps losing is dropped on its own. Every day summary
# prints the tally (``owner_rule_lines``) so the rule cannot be missed.
OWNER_RULE_SET, OWNER_REVIEW_EXPIRIES = "2026-10-08", 10


@dataclass(frozen=True)
class ExitPolicy:
    hard_stop: Optional[float]                  # planned stop: fraction of entry premium lost
    bank_at: Optional[float]                    # gain on the bid that sells half
    bank_stop: Optional[float]                  # stop as a multiple of entry once banked
    trails: tuple[tuple[float, float], ...]     # (peak gain reached, fraction of peak kept)
    late: Optional[tuple[time, float]]          # from this time, keep this fraction of a profitable peak
    time_stop: Optional[tuple[int, float]]      # (seconds, peak gain still not reached) closes the leg
    flat_at: time
    lock_gain: Optional[float] = None           # once banked, a one-lot position keeps this share of its peak gain


POLICIES = {
    "A": ExitPolicy(hard_stop=0.30, bank_at=0.40, bank_stop=1.05, trails=((1.0, 0.70), (2.0, 0.80)),
                    late=(time(15, 0), 0.85), time_stop=(480, 0.15), flat_at=A_FLAT),
    "B": ExitPolicy(hard_stop=None, bank_at=1.0, bank_stop=None, trails=((1.0, 0.65),),
                    late=(time(15, 30), 0.80), time_stop=None, flat_at=FINAL_FLAT),
    "C": ExitPolicy(hard_stop=None, bank_at=2.0, bank_stop=None, trails=((4.0, 0.60),),
                    late=None, time_stop=None, flat_at=FINAL_FLAT),
    "BH": ExitPolicy(hard_stop=None, bank_at=None, bank_stop=None, trails=(),
                     late=None, time_stop=None, flat_at=FINAL_FLAT),
}
POLICIES["C500"] = POLICIES["C"]
POLICIES["AL"] = replace(POLICIES["A"], lock_gain=AL_LOCK_GAIN)
POLICIES["BP"] = POLICIES["BH"]                 # its exits are the pair's (see _pair_target)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS expiry_paper_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, underlying TEXT NOT NULL, play TEXT NOT NULL,
        exchange TEXT NOT NULL, symbol TEXT NOT NULL, token INTEGER NOT NULL, strike REAL NOT NULL,
        opt_type TEXT NOT NULL, lot_size INTEGER NOT NULL, lots INTEGER NOT NULL, lots_open INTEGER NOT NULL,
        entry_ts TEXT NOT NULL, entry_price REAL NOT NULL, max_loss REAL NOT NULL, peak REAL NOT NULL,
        stop REAL NOT NULL, banked INTEGER NOT NULL DEFAULT 0, exit_pending TEXT, status TEXT NOT NULL,
        gross REAL NOT NULL DEFAULT 0, costs REAL NOT NULL DEFAULT 0, net_pnl REAL NOT NULL DEFAULT 0,
        assumed_pnl REAL, events TEXT NOT NULL DEFAULT '[]', bank_pending INTEGER NOT NULL DEFAULT 0,
        fee_snapshot TEXT, execution TEXT, side TEXT NOT NULL DEFAULT 'LONG', width REAL)""",
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


# Columns added after the first Production day. Older stores gain them in
# place; their rows keep NULL fee_snapshot/execution (the legacy contract).
# ``side`` is SHORT only for D's sold legs; ``width`` is D's strike gap.
_ADDED_POSITION_COLUMNS = {"bank_pending": "INTEGER NOT NULL DEFAULT 0", "fee_snapshot": "TEXT",
                           "execution": "TEXT", "side": "TEXT NOT NULL DEFAULT 'LONG'", "width": "REAL"}


def expiry_db_path(db_path: str) -> str:
    return f"{db_path}.expiry-paper.db"


@contextmanager
def _store(path: str):
    """One transaction on the paper store; the handle is always closed."""
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        for statement in _SCHEMA:
            conn.execute(statement)
        present = {row[1] for row in conn.execute("PRAGMA table_info(expiry_paper_positions)")}
        for column, ddl in _ADDED_POSITION_COLUMNS.items():
            if column not in present:
                conn.execute(f"ALTER TABLE expiry_paper_positions ADD COLUMN {column} {ddl}")
        with conn:
            yield conn


def _notice(conn, key: str, message: str, now: datetime) -> None:
    conn.execute("INSERT OR IGNORE INTO expiry_paper_notices (key, message, created_at) VALUES (?,?,?)",
                 (key, message, now.isoformat()))


_FLUSH_LOCKS: dict[str, asyncio.Lock] = {}


async def flush_notices(send: Callable[[str], Awaitable[None]], db_path: Optional[str] = None,
                        now: Optional[datetime] = None) -> int:
    """Send unsent notices oldest first; ``send`` raises on failure, which stops the flush.

    The tick, the flush job and the reconcile all call this; a per-store lock
    keeps two flushes from sending the same row. ``sent_at`` is when the 2xx
    acknowledgement arrived. A crash between that response and the mark sends
    the notice again: at-least-once, never silently dropped.
    """
    store = expiry_db_path(db_path or settings.DB_PATH)
    async with _FLUSH_LOCKS.setdefault(store, asyncio.Lock()):
        with _store(store) as conn:
            pending = conn.execute("SELECT key, message, attempts FROM expiry_paper_notices "
                                   "WHERE sent_at IS NULL ORDER BY created_at, key").fetchall()
        sent = 0
        for row in pending:
            try:
                await send(row["message"])
            except Exception as exc:
                if row["attempts"] % 30 == 0:
                    logger.warning("expiry_paper_notice_failed key=%s attempts=%d err=%s",
                                   row["key"], row["attempts"], type(exc).__name__)
                with _store(store) as conn:
                    conn.execute("UPDATE expiry_paper_notices SET attempts = attempts + 1 WHERE key=?",
                                 (row["key"],))
                break
            acked = now or datetime.now(IST)
            with _store(store) as conn:
                conn.execute("UPDATE expiry_paper_notices SET sent_at=?, attempts = attempts + 1 WHERE key=?",
                             (acked.isoformat(), row["key"]))
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
    oi: Optional[float] = None                  # open interest; record-only context

    @property
    def bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    def age_status(self, now: datetime) -> str:
        """FRESH, or why the provider time is unusable at decision time ``now``."""
        if self.ts is None:
            return "NO_TIMESTAMP"
        age = (now - self.ts).total_seconds()
        if age < -CLOCK_SKEW_SEC:
            return "AHEAD"
        return "STALE" if age > QUOTE_MAX_AGE_SEC else "FRESH"

    def fresh(self, now: datetime) -> bool:
        return self.age_status(now) == "FRESH"

    def spread_ok(self, max_fraction: float) -> bool:
        return self.bid is not None and self.ask is not None and self.ask >= self.bid \
            and (self.ask - self.bid) <= max_fraction * self.ask

    def logged(self) -> dict:
        """What a fill can use: every depth level, the LTP and the provider time (and the OI)."""
        return {"b": [list(level) for level in self.bids], "a": [list(level) for level in self.asks],
                "ltp": self.ltp, "ts": self.ts.isoformat() if self.ts else None, "oi": self.oi}


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

    oi = packet.get("oi")
    return Quote(bids=levels("buy"), asks=levels("sell"), ltp=_positive(packet.get("last_price")),
                 ts=_provider_time(packet), oi=float(oi) if isinstance(oi, (int, float)) and oi >= 0 else None)


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


def fee_schedule(exchange: str = "NFO") -> dict:
    """Current options charge schedule of an F&O segment (NFO: NSE, BFO: BSE)."""
    from cost_schedules import options_cost_snapshot

    return options_cost_snapshot(exchange)


def _charges(entry: float, exit_price: float, qty: int, schedule: Optional[dict]) -> float:
    from fno_costs import calc_fno_costs_from_snapshot

    return calc_fno_costs_from_snapshot(entry, exit_price, qty, schedule or fee_schedule())


def order_fee(schedule: Optional[dict] = None) -> float:
    """Charges of one order that do not scale with premium (flat brokerage and its GST)."""
    return _charges(0.0, 0.0, 1, schedule) / 2.0


def buy_charges(price: float, qty: int, schedule: Optional[dict] = None) -> float:
    """Charges of the single buy order, booked once at entry."""
    return _charges(price, 0.0, qty, schedule) - order_fee(schedule)


def sell_charges(price: float, qty: int, schedule: Optional[dict] = None) -> float:
    """Charges of one sell order (an exit slice)."""
    return _charges(0.0, price, qty, schedule) - order_fee(schedule)


def worst_case_loss(price: float, lots: int, lot_size: int, schedule: Optional[dict] = None) -> float:
    """Hard loss bound: the whole premium, the buy's charges, and one order fee per lot.

    An exit can be sliced into at most ``lots`` sell orders (each fills at
    least one whole lot), and a sell's proceeds always exceed its ad-valorem
    charges, so each slice costs at most one order fee net. Expiring
    worthless or exercising costs no more (exercise STT is under 1% of
    intrinsic).
    """
    qty = lots * lot_size
    return price * qty + buy_charges(price, qty, schedule) + lots * order_fee(schedule)


def affordable_fill(quotes: list[tuple[Quote, int]], budget: float, cap: int,
                    schedule: Optional[dict] = None) -> tuple[int, list[float]]:
    """Largest common lot count (<= cap) whose worst-case loss over all legs fits ``budget``."""
    for lots in range(cap, 0, -1):
        prices, loss = [], 0.0
        for quote, lot_size in quotes:
            filled, price = walk(quote.asks, lots, lot_size)
            if filled < lots:
                break
            prices.append(price)
            loss += worst_case_loss(price, lots, lot_size, schedule)
        else:
            if loss <= budget:
                return lots, prices
    return 0, []


def condor_fill(legs: list[tuple[Quote, str]], lot_size: int, width: float, spot: float, budget: float,
                schedule: Optional[dict] = None) -> tuple[int, list[float], float, Optional[str]]:
    """D's sizing: (lots, prices, max_loss, refusal) for SHORT/LONG legs of one iron condor.

    Sold legs walk the bids and wings walk the asks. Held to cash settlement,
    only one side can finish in the money and a side loses at most its strike
    gap, so the loss is bounded by (width - credit) x qty plus the entry
    charges and exercise STT on a wing up to ``D_STT_RESERVE_MOVE`` of spot in
    the money. The credit must cover ``D_MIN_CREDIT_X_CHARGES`` x the charges.
    That bound holds only inside the reserve's move domain; beyond it the
    wing's exercise STT is uncapped (see ``reconcile``'s RESERVE_BREACH).
    """
    for lots in range(D_MAX_LOTS, 0, -1):
        qty, prices = lots * lot_size, []
        for quote, side in legs:
            filled, price = walk(quote.bids if side == "SHORT" else quote.asks, lots, lot_size)
            if filled < lots:
                break
            prices.append(price)
        else:
            credit = sum(p if side == "SHORT" else -p for p, (_, side) in zip(prices, legs))
            charges = sum(sell_charges(p, qty, schedule) if side == "SHORT" else buy_charges(p, qty, schedule)
                          for p, (_, side) in zip(prices, legs))
            stt = EXERCISE_STT_PCT * D_STT_RESERVE_MOVE * spot * qty
            max_loss = (width - credit) * qty + charges + stt
            if max_loss > budget:
                continue
            if credit * qty < D_MIN_CREDIT_X_CHARGES * charges:
                return 0, [], 0.0, "CREDIT_TOO_SMALL"       # fewer lots only worsens the ratio
            return lots, prices, max_loss, None
    return 0, [], 0.0, "DEPTH_OR_BUDGET"


def fill_model(clock: time) -> str:
    return "AUCTION_WINDOW" if clock >= AUCTION_START else "CONTINUOUS"


# ---------------------------------------------------------------------------
# pure rules
# ---------------------------------------------------------------------------

def new_day_state() -> dict:
    return {"rules": RULES_VERSION, "shadow": SHADOW_VERSION, "execution": EXECUTION_VERSION,
            "context": CONTEXT_VERSION, "box": None, "box_samples": [], "box_status": "BUILDING",
            "pending": None, "armed": {"UP": True, "DOWN": True}, "signals": [],
            "trades": {play: 0 for play in MAIN_PLAYS + SHADOW_PLAYS}, "last_spot": None,
            "summary_queued": False}


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


def _bank_floor(pos: dict, policy: ExitPolicy) -> float:
    """The stop a banked position keeps: entry x ``bank_stop`` and, for a one-lot
    position under a ``lock_gain`` policy (AL), that share of its peak gain."""
    entry = pos["entry_price"]
    floor = entry * policy.bank_stop if policy.bank_stop is not None else 0.0
    if policy.lock_gain is not None and pos.get("lots", pos["lots_open"]) == 1:
        floor = max(floor, entry + policy.lock_gain * (pos["peak"] - entry))
    return floor


def manage_position(pos: dict, policy: ExitPolicy, bid: float, now: datetime,
                    structure_broken: bool = False) -> Optional[tuple[int, str]]:
    """Update peak/stop in ``pos`` and return the planned (lots to sell, reason) or None.

    Stops are checked on each observed bid; a gap between checks can fill
    below the stop. A one-lot position cannot bank half: it only raises its
    stop (to ``_bank_floor``). Reaching the bank level sets ``bank_pending`` to
    half the lots; lots the bid depth could not take stay pending and are
    offered again while the bid holds the bank level (stops, failed breaks and
    flat time come first).
    """
    entry = pos["entry_price"]
    pos["peak"] = max(pos["peak"], bid)
    peak_gain = pos["peak"] / entry - 1.0
    stop = pos["stop"]
    if pos["banked"]:
        stop = max(stop, _bank_floor(pos, policy))
    for threshold, keep in policy.trails:
        if peak_gain >= threshold:
            stop = max(stop, pos["peak"] * keep)
    if policy.late and now.time() >= policy.late[0]:
        profit_stage = policy.bank_at if policy.bank_at is not None else policy.trails[0][0]
        if peak_gain >= profit_stage:
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
    if policy.bank_at is None or bid < entry * (1.0 + policy.bank_at):
        return None
    if not pos["banked"]:
        pos["banked"], pos["bank_pending"] = 1, lots // 2
        pos["stop"] = round(max(pos["stop"], _bank_floor(pos, policy)), 2)
    pending = min(pos.get("bank_pending", 0), lots)
    return (pending, "BANK_HALF") if pending else None


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


def _position_schedule(pos: dict) -> dict:
    """The charge schedule frozen at entry (rows from before it was stored: the exchange's current one)."""
    return json.loads(pos["fee_snapshot"]) if pos.get("fee_snapshot") else fee_schedule(pos["exchange"])


def _sell(pos: dict, lots: int, price: float, reason: str, now: datetime) -> dict:
    """Book one exit slice: its gross and its own sell-order charges (the buy was charged at entry)."""
    qty = lots * pos["lot_size"]
    gross = (price - pos["entry_price"]) * qty
    costs = sell_charges(price, qty, _position_schedule(pos))
    pos["lots_open"] -= lots
    if reason == "BANK_HALF":
        pos["bank_pending"] = max(0, pos.get("bank_pending", 0) - lots)
    pos["gross"] = round(pos["gross"] + gross, 2)
    pos["costs"] = round(pos["costs"] + costs, 2)
    pos["net_pnl"] = round(pos["gross"] - pos["costs"], 2)
    if pos["lots_open"] == 0:
        pos["status"], pos["exit_pending"], pos["bank_pending"] = "CLOSED", None, 0
    event = {"ts": now.isoformat(), "action": reason, "lots": lots, "price": price,
             "gross": round(gross, 2), "charges": round(costs, 2), "net": round(gross - costs, 2),
             "fill_model": fill_model(now.time())}
    pos["_events"].append(event)
    return event


def _new_position(day: str, underlying: str, play: str, exchange: str, contract, price: float,
                  lots: int, now: datetime, schedule: Optional[dict] = None) -> dict:
    policy = POLICIES.get(play)                     # D is held to settlement: no exit policy
    schedule = schedule or fee_schedule(exchange)
    charges = round(buy_charges(price, lots * contract.lot_size, schedule), 2)
    return {"id": None, "day": day, "underlying": underlying, "play": play, "exchange": exchange,
            "symbol": contract.tradingsymbol, "token": contract.token, "strike": contract.strike,
            "opt_type": contract.instrument_type, "lot_size": contract.lot_size, "lots": lots,
            "lots_open": lots, "entry_ts": now.isoformat(), "entry_price": price,
            "max_loss": round(worst_case_loss(price, lots, contract.lot_size, schedule), 2), "peak": price,
            "stop": round(price * (1 - policy.hard_stop), 2) if policy and policy.hard_stop else 0.0,
            "banked": 0, "exit_pending": None, "status": "OPEN", "gross": 0.0, "costs": charges,
            "net_pnl": -charges, "assumed_pnl": None, "bank_pending": 0,
            "fee_snapshot": json.dumps(schedule, sort_keys=True), "execution": EXECUTION_VERSION,
            "side": "LONG", "width": None,
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
    """Sell what the fresh bid depth can fill now; latch the rest.

    A closing exit latches as ``exit_pending`` and is retried every tick,
    whatever the bid. Unfilled bank lots stay in ``bank_pending`` and are
    retried while the bid holds the bank level (see ``manage_position``).
    """
    if quote is not None and quote.fresh(now):
        filled, price = walk(quote.bids, lots, pos["lot_size"])
        if filled:
            event = _sell(pos, filled, price, reason, now)
            if pos["status"] == "OPEN" and reason != "BANK_HALF":
                pos["exit_pending"] = reason
            return event
    if reason != "BANK_HALF":
        pos["exit_pending"] = reason
    return None


def liquidation_net(legs: list[dict], quotes: dict, now: datetime) -> Optional[float]:
    """Whole-trade net if every open leg were closed now, plus what its legs already booked.

    Bought legs sell into the fresh bids and D's sold legs buy back on the
    fresh asks, whole quantity, each paying its own order charges. None when
    any open leg lacks a fresh quote deep enough: a missing price is never
    read as zero or as the last trade. A mark, never a fill.
    """
    total = 0.0
    for leg in legs:
        total += leg["net_pnl"] + (leg.get("assumed_pnl") or 0.0)
        if leg["status"] != "OPEN" or not leg["lots_open"]:
            continue
        quote = quotes.get(leg["token"])
        if quote is None or not quote.fresh(now):
            return None
        short = leg.get("side") == "SHORT"
        filled, price = walk(quote.asks if short else quote.bids, leg["lots_open"], leg["lot_size"])
        if filled < leg["lots_open"]:
            return None
        qty, schedule = leg["lots_open"] * leg["lot_size"], _position_schedule(leg)
        total += ((leg["entry_price"] - price) * qty - buy_charges(price, qty, schedule)) if short \
            else ((price - leg["entry_price"]) * qty - sell_charges(price, qty, schedule))
    return round(total, 2)


def _pair_target(pair: list[dict], quotes: dict, now: datetime) -> bool:
    """BP: both legs open and the pair, sold now on the visible bids, nets BP_TARGET of its premium."""
    if len(pair) != 2 or any(leg["exit_pending"] or leg["status"] != "OPEN" for leg in pair):
        return False
    value = liquidation_net(pair, quotes, now)
    paid = sum(leg["entry_price"] * leg["lots"] * leg["lot_size"] for leg in pair)
    return value is not None and value >= BP_TARGET * paid


def _mark_paths(conn, state: dict, day: str, underlying: str, quotes: dict, now: datetime,
                was_open: set[str]) -> None:
    """Record each open entry's best and worst liquidation mark (record-only, read by no rule).

    An entry is a play's legs bought together (one A or C leg, a B strangle,
    a D condor), so a pair is marked as one trade at one moment. An entry in
    ``was_open`` (open when the tick began) that closed this tick is marked at
    its fills.
    """
    entries: dict[str, list[dict]] = {}
    for leg in _rows(conn, "SELECT * FROM expiry_paper_positions WHERE day=? AND underlying=?", (day, underlying)):
        entries.setdefault(f"{leg['play']} {leg['entry_ts']}", []).append(leg)
    marks = state.setdefault("marks", {})
    for key, legs in entries.items():
        if key not in was_open and not any(leg["status"] == "OPEN" for leg in legs):
            continue
        value = liquidation_net(legs, quotes, now)
        if value is None:
            continue
        mark = marks.setdefault(key, {"n": 0, "best": value, "best_ts": now.isoformat(),
                                      "worst": value, "worst_ts": now.isoformat()})
        mark["n"] += 1
        if value > mark["best"]:
            mark["best"], mark["best_ts"] = value, now.isoformat()
        if value < mark["worst"]:
            mark["worst"], mark["worst_ts"] = value, now.isoformat()


# ---------------------------------------------------------------------------
# chain context: recorded on every tick, read by no rule
# ---------------------------------------------------------------------------

def update_realized(state: dict, now: datetime, spot: Optional[float]) -> None:
    """Add the squared index log return since the last sample at least ``RV_SAMPLE_SEC`` old."""
    if spot is None:
        return
    rv = state.setdefault("rv", {"sum_sq": 0.0, "secs": 0.0, "ts": None, "spot": None})
    if rv["ts"] is not None:
        elapsed = (now - datetime.fromisoformat(rv["ts"])).total_seconds()
        if elapsed < RV_SAMPLE_SEC:
            return
        rv["sum_sq"] += math.log(spot / rv["spot"]) ** 2
        rv["secs"] += elapsed
    rv["ts"], rv["spot"] = now.isoformat(), spot


def realized_vol(state: dict) -> Optional[float]:
    """Annualised volatility of today's sampled index returns on the session clock, once there is enough."""
    rv = state.get("rv") or {}
    if rv.get("secs", 0.0) < RV_MIN_SEC:
        return None
    return math.sqrt(rv["sum_sq"] / rv["secs"] * TRADING_YEAR_SEC)


def max_pain(oi: dict) -> Optional[float]:
    """The strike at which the in-window option holders would collect least at settlement."""
    if not oi or not sum(oi.values()):
        return None

    def payout(settle: float) -> float:
        return sum(units * max(0.0, settle - strike if kind == "CE" else strike - settle)
                   for (strike, kind), units in oi.items())

    return min(sorted({strike for strike, _ in oi}), key=payout)


def chain_context(state: dict, quoted_chain: dict, spot: Optional[float], step: float,
                  fut: Optional[float], fut_oi: Optional[float], now: datetime) -> dict:
    """The chain read at decision time, for the record only.

    Updates today's realized-volatility samples and the OI baselines (each
    strike's first OI seen today, so a strike entering the window is not an OI
    change). The ATM straddle mid is the expected absolute move to settlement;
    ``iv`` is the volatility it implies on the session clock
    (straddle = sqrt(2/pi) * spot * iv * sqrt(T)).
    """
    update_realized(state, now, spot)
    if spot is None:
        return {"status": "NO_FRESH_INDEX", "ts": now.isoformat()}
    ctx: dict = {"status": "OK", "ts": now.isoformat(), "spot": spot}
    atm = float(round(spot / step) * step)
    mids = []
    for kind in ("CE", "PE"):
        quote = (quoted_chain.get((atm, kind)) or (None, None))[1]
        if quote is None or not quote.fresh(now) or not quote.spread_ok(1.0):   # fresh and two-sided
            break
        mids.append((quote.bid + quote.ask) / 2.0)
    if len(mids) == 2:
        ctx["atm"], ctx["straddle"] = atm, round(sum(mids), 2)
        left = (datetime.combine(now.date(), SETTLE_AT, tzinfo=now.tzinfo) - now).total_seconds()
        if left > 0:
            ctx["iv"] = round(sum(mids) / (math.sqrt(2.0 / math.pi) * spot
                                           * math.sqrt(left / TRADING_YEAR_SEC)), 4)
    rv = realized_vol(state)
    if rv:
        ctx["rv"] = round(rv, 4)
        if "iv" in ctx:
            ctx["iv_rv"] = round(ctx["iv"] / rv, 3)

    # Only fresh quotes count (Oct 8 audit T4: a stale OI used to reach the walls
    # and PCR under an OK status); the coverage says how much of the window did.
    oi = {key: q.oi for key, (_, q) in quoted_chain.items() if q.oi is not None and q.fresh(now)}
    ctx["oi_fresh"], ctx["oi_window"] = len(oi), len(quoted_chain)
    if oi:
        base = state.setdefault("oi_base", {})
        change = {}
        for (strike, kind), units in oi.items():
            change[(strike, kind)] = units - base.setdefault(f"{strike:g}{kind}", units)
        side = {kind: {k: v for (k, t), v in oi.items() if t == kind} for kind in ("CE", "PE")}
        added = {kind: {k: v for (k, t), v in change.items() if t == kind} for kind in ("CE", "PE")}
        calls = sum(side["CE"].values())
        ctx.update(
            call_wall=max((k for k in side["CE"] if k >= spot), key=side["CE"].get, default=None),
            put_wall=max((k for k in side["PE"] if k <= spot), key=side["PE"].get, default=None),
            max_pain=max_pain(oi),
            pcr=round(sum(side["PE"].values()) / calls, 3) if calls else None,
            ce_oi_chg=sum(added["CE"].values()), pe_oi_chg=sum(added["PE"].values()),
            top_ce_add=max(added["CE"], key=added["CE"].get, default=None),
            top_pe_add=max(added["PE"], key=added["PE"].get, default=None))
    if fut is not None and fut_oi is not None:
        from fno_analytics import classify_buildup

        first_px, first_oi = state.setdefault("fut_base", [fut, fut_oi])
        ctx["fut_oi_chg"] = fut_oi - first_oi
        ctx["fut_buildup"] = classify_buildup(fut - first_px, fut_oi - first_oi)
    return ctx


def _context_text(ctx: dict) -> str:
    def pct(value):
        return f"{value * 100:.1f}%" if value is not None else "n/a"

    def strike(value):
        return f"{value:,.0f}" if value is not None else "n/a"

    ratio = f" (x{ctx['iv_rv']:.2f})" if ctx.get("iv_rv") is not None else ""
    straddle = f"{ctx['straddle']:.1f} pts" if ctx.get("straddle") is not None else "n/a"
    coverage = f" from {ctx['oi_fresh']}/{ctx['oi_window']} fresh quotes" if "oi_window" in ctx else ""
    return (f"IV {pct(ctx.get('iv'))} vs realized {pct(ctx.get('rv'))}{ratio}, straddle {straddle}, "
            f"walls {strike(ctx.get('put_wall'))} PE / {strike(ctx.get('call_wall'))} CE, "
            f"max pain {strike(ctx.get('max_pain'))}, PCR {ctx.get('pcr') if ctx.get('pcr') is not None else 'n/a'}"
            f"{coverage}, future {ctx.get('fut_buildup', 'n/a')}")


def _moment(name: str, at: time, ctx: Optional[dict]) -> str:
    """A snapshot's label with the time it was actually read (the first tick at or after ``at``)."""
    label = f"{name.split('_')[0].upper()} entry {at:%H:%M:%S}"
    return f"{label}, read {datetime.fromisoformat(ctx['ts']):%H:%M:%S}" if ctx else label


def context_lines(state: dict, settle: Optional[float]) -> list[str]:
    """The record-only chain context at the D and B entry times, and how the close met it."""
    snaps = state.get("context_at") or {}
    lines = [f"  context ({state.get('context', CONTEXT_VERSION)}, record-only, no rule uses it):"]
    for moment, at in CONTEXT_MOMENTS.items():
        ctx = snaps.get(moment)
        lines.append(f"    {_moment(moment, at, ctx)}: " + (_context_text(ctx) if ctx else "not recorded"))
    first = snaps.get("d_entry")
    if settle is not None and first:
        walls = (first.get("put_wall"), first.get("call_wall"))
        inside = "n/a" if None in walls else ("yes" if walls[0] <= settle <= walls[1] else "no")
        pain = f"{abs(settle - first['max_pain']):,.0f} pts" if first.get("max_pain") is not None else "n/a"
        move = f"{abs(settle - first['spot']):,.1f} pts"
        implied = f" against straddle {first['straddle']:.1f}" if first.get("straddle") is not None else ""
        lines.append(f"    close {settle:,.2f} (our sample) vs {_moment('d_entry', D_ENTRY_START, first)}: "
                     f"inside the walls {inside}, "
                     f"{pain} from max pain, moved {move}{implied}")
    return lines


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
    intrinsic, less exercise STT on a bought leg (SETTLED_ASSUMED); without
    one it is UNRESOLVED at its remaining worst case. For D's sold legs that
    worst case is half the strike gap each, so a whole condor is valued at its
    maximum settlement loss. Entry charges were booked at entry. Both are
    assumed valuations kept in ``assumed_pnl``, never executable fills. Day
    summaries are queued here.
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
            short = pos["side"] == "SHORT"
            if spot is None:
                pos["status"] = "UNRESOLVED"
                if short:
                    value = (pos["entry_price"] - pos["width"] / 2.0) * qty
                elif pos["play"] == "D":                        # a wing is held, never sold
                    value = -pos["entry_price"] * qty
                else:
                    value = -(pos["entry_price"] * qty + pos["lots_open"] * order_fee(_position_schedule(pos)))
            else:
                intrinsic = max(0.0, spot - pos["strike"]) if pos["opt_type"] == "CE" \
                    else max(0.0, pos["strike"] - spot)
                pos["status"] = "SETTLED_ASSUMED"
                value = (pos["entry_price"] - intrinsic) * qty if short \
                    else (intrinsic * (1 - EXERCISE_STT_PCT) - pos["entry_price"]) * qty
            pos["assumed_pnl"] = round(value, 2)
            event = {"ts": now.isoformat(), "action": pos["status"], "lots": pos["lots_open"],
                     "settlement_spot": spot, "settlement_source": "SAMPLED_INDEX_QUOTE",
                     "assumed_pnl": pos["assumed_pnl"]}
            if pos["play"] == "D" and not short and spot is not None:
                # The entry event stores the reserved intrinsic; rows from
                # before that field fall back to the settlement spot.
                stored = (json.loads(pos.get("events") or "[]") or [{}])[0]
                reserved = stored.get("reserve_intrinsic") or D_STT_RESERVE_MOVE * spot
            if pos["play"] == "D" and not short and spot is not None and intrinsic > reserved:
                beyond = EXERCISE_STT_PCT * (intrinsic - reserved) * qty
                event["reserve_breach"] = {"reserved_move": D_STT_RESERVE_MOVE, "intrinsic": round(intrinsic, 2),
                                           "stt_beyond_reserve": round(beyond, 2)}
                logger.warning("expiry_d_reserve_breach day=%s symbol=%s intrinsic=%.2f stt_beyond=%.2f",
                               pos["day"], pos["symbol"], intrinsic, beyond)
            pos["_events"].append(event)
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
    if row is None:
        return new_day_state()
    state = json.loads(row["state"])
    contract = state.get("execution", "expiry-exec-v1")
    if not contract.endswith(EXECUTION_VERSION):        # a day begun under an older contract
        state["execution"] = f"{contract}+{EXECUTION_VERSION}"
    shadow = state.setdefault("shadow", f"{SHADOW_VERSION} joined mid-day")
    if SHADOW_VERSION not in shadow:                    # newer shadow plays join a day already begun
        state["shadow"] = f"{shadow}+{SHADOW_VERSION} joined mid-day"
    state.setdefault("context", f"{CONTEXT_VERSION} joined mid-day")
    for play in MAIN_PLAYS + SHADOW_PLAYS:
        state["trades"].setdefault(play, 0)
    return state


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


async def _fetch(kite, underlying: str, exchange: str, contracts: list, future) -> tuple[dict, Optional[dict]]:
    """One quote batch and, when the client measures it, its limiter/transport timing.

    The batch waits in the shared limiter's management lane: the tick manages
    open exits every 10 s, and on October 8 its p99 limiter wait was 18.3 s
    behind other modules' reads (max 28.9 s; transport max 0.4 s). The lane
    changes only the order of admission, never the rate, and its burst bound
    keeps the other lanes from starving.
    """
    from kite_client import provider_lane

    request = {SPOT_KEY: INDEX_QUOTE_KEYS[underlying]}
    if future is not None:
        request[FUT_KEY] = f"{exchange}:{future.tradingsymbol}"
    request.update({c.token: f"{exchange}:{c.tradingsymbol}" for c in contracts})
    timed = getattr(kite, "get_quote_by_instruments_with_timing", None)
    with provider_lane("management"):
        if timed is not None:
            return await timed(request)
        return await kite.get_quote_by_instruments(request), None


def _observe(packet, now: datetime) -> tuple[Optional[float], dict]:
    """A fresh LTP (else None) and the logged packet with its status (and the future's OI) at decision time."""
    if not isinstance(packet, dict):
        return None, {"status": "MISSING"}
    quote = parse_quote(packet)
    status = "NO_PRICE" if quote.ltp is None else quote.age_status(now)
    logged = {"ltp": quote.ltp, "ts": quote.ts.isoformat() if quote.ts else None, "status": status}
    if quote.oi is not None:
        logged["oi"] = quote.oi
    return (quote.ltp if status == "FRESH" else None), logged


def _bump(state: dict, counter: str, key: str) -> None:
    bucket = state.setdefault(counter, {})
    bucket[key] = bucket.get(key, 0) + 1


def _record_tick(conn, state: dict, day: str, underlying: str, started: datetime, now: datetime,
                 spot: Optional[float], fut: Optional[float], payload: dict) -> None:
    """Count the tick and its data quality in the day state and store its full packet."""
    state["ticks"] = state.get("ticks", 0) + 1
    for name, value, observation in (("spot", spot, payload["index"]), ("fut", fut, payload["future"])):
        if value is None:
            state[f"stale_{name}"] = state.get(f"stale_{name}", 0) + 1
            _bump(state, f"{name}_refusals", observation["status"])
    previous = state.get("last_tick_ts")
    if previous is not None:
        gap = (now - datetime.fromisoformat(previous)).total_seconds()
        state["max_gap_sec"] = round(max(state.get("max_gap_sec", 0.0), gap), 3)
        if gap > CONFIRM_MAX_GAP_SEC:
            state["gaps_over_confirm"] = state.get("gaps_over_confirm", 0) + 1
    state["last_tick_ts"] = now.isoformat()
    state["max_decision_lag_sec"] = round(max(state.get("max_decision_lag_sec", 0.0),
                                              (now - started).total_seconds()), 3)
    conn.execute("INSERT OR REPLACE INTO expiry_paper_ticks VALUES (?,?,?,?,?,?)", (
        day, underlying, now.isoformat(), spot, fut,
        json.dumps({"execution": EXECUTION_VERSION, "started": started.isoformat(),
                    "fill_model": fill_model(now.time()), **payload}, separators=(",", ":"))))


def _save_state(conn, day: str, underlying: str, state: dict, now: datetime) -> None:
    conn.execute("INSERT OR REPLACE INTO expiry_paper_days VALUES (?,?,?,?)",
                 (day, underlying, json.dumps(state), now.isoformat()))


def _quote_refusal(candidate, now: datetime, max_spread: float) -> Optional[str]:
    """Why a chain leg cannot be bought now, or None."""
    if not candidate:
        return "NO_QUOTE"
    quote = candidate[1]
    status = quote.age_status(now)
    if status != "FRESH":
        return f"QUOTE_{status}"
    return None if quote.spread_ok(max_spread) else "SPREAD"


def _buy_text(pos: dict, detail: str) -> str:
    return (f"BUY {pos['lots']} lot {pos['symbol']} @ {pos['entry_price']:.2f} ({detail}, "
            f"buy fees Rs {pos['costs']:,.2f}, max loss Rs {pos['max_loss']:,.2f})")


def _sell_text(pos: dict, event: dict) -> str:
    auction = ", auction window" if event["fill_model"] == "AUCTION_WINDOW" else ""
    text = (f"SELL {event['lots']} lot {pos['symbol']} @ {event['price']:.2f} ({event['action']}{auction}): "
            f"slice gross Rs {event['gross']:+,.2f} less sell fees Rs {event['charges']:,.2f}")
    if pos["status"] == "CLOSED":
        return text + f"; trade closed, net Rs {pos['net_pnl']:+,.2f} after buy and sell fees"
    return text + f"; {pos['lots_open']} lot still open, net so far Rs {pos['net_pnl']:+,.2f} after all fees"


async def _tick_underlying(kite, conn, book, underlying: str, exchange: str, started: datetime,
                           clock: Callable[[], datetime]) -> None:
    """One step for one underlying. ``started`` picks the day; ``clock()`` after the quotes decides."""
    day = started.date().isoformat()
    state = _load_state(conn, day, underlying)
    positions = _rows(conn, "SELECT * FROM expiry_paper_positions WHERE day=? AND underlying=? AND status='OPEN'",
                      (day, underlying))
    was_open = {f"{pos['play']} {pos['entry_ts']}" for pos in positions}
    future = book.front_future(started.date())
    timings = []

    anchor = state["last_spot"]
    if anchor is None:
        first, timing = await _fetch(kite, underlying, exchange, [], future)
        timings.append(timing)
        anchor = _positive((first.get(SPOT_KEY) or {}).get("last_price"))
        if anchor is None:
            # Keep the expiry in the record: an outage day is evidence, not a missing row.
            now = clock()
            _record_tick(conn, state, day, underlying, started, now, None, None,
                         {"timing": timings, "index": _observe(first.get(SPOT_KEY), now)[1],
                          "future": _observe(first.get(FUT_KEY), now)[1], "legs": {}})
            update_box(state, now.time(), None, None)
            _save_state(conn, day, underlying, state, now)
            return
    chain = _chain(book, started.date(), anchor)
    held = [book.by_symbol.get(pos["symbol"]) for pos in positions]
    contracts = {c.token: c for c in [*chain.values(), *(c for c in held if c is not None)]}
    raw, timing = await _fetch(kite, underlying, exchange, list(contracts.values()), future)
    timings.append(timing)
    now = clock()                               # decision time: after the quotes arrived
    clock_now = now.time()
    spot, index_seen = _observe(raw.get(SPOT_KEY), now)
    fut, future_seen = _observe(raw.get(FUT_KEY), now)
    quotes = {token: parse_quote(raw[token]) for token in contracts if isinstance(raw.get(token), dict)}
    quoted_chain = {key: (c, quotes[c.token]) for key, c in chain.items() if c.token in quotes}
    if spot is not None:
        state["last_spot"] = spot
    fut_oi = parse_quote(raw[FUT_KEY]).oi if isinstance(raw.get(FUT_KEY), dict) else None
    try:                                        # record-only: it must never cost a tick
        context = chain_context(state, quoted_chain, spot, book.strike_step, fut, fut_oi, now)
    except Exception as exc:
        logger.warning("expiry chain context failed: %s", type(exc).__name__)
        context = {"status": "ERROR", "ts": now.isoformat(), "error": type(exc).__name__}
    snaps = state.setdefault("context_at", {})
    for moment, at in CONTEXT_MOMENTS.items():
        if clock_now >= at and moment not in snaps and context["status"] == "OK":
            snaps[moment] = context
    _record_tick(conn, state, day, underlying, started, now, spot, fut,
                 {"timing": timings, "index": index_seen, "future": future_seen, "context": context,
                  "legs": {contracts[t].tradingsymbol: q.logged() for t, q in quotes.items()}})

    label = f"Expiry paper {underlying}"
    schedule = fee_schedule(exchange)

    def notify(pos: dict, text: str) -> None:
        if pos["play"] not in MAIN_PLAYS:                # shadow plays report only in the summary
            return
        _notice(conn, f"{day}:{underlying}:{pos['id']}:{now.isoformat()}", f"{label} {pos['play']}: {text}", now)

    def open_position(play: str, contract, price: float, lots: int) -> dict:
        pos = _new_position(day, underlying, play, exchange, contract, price, lots, now, schedule)
        _save_position(conn, pos)
        state["trades"][play] += 1
        return pos

    # 1. manage what is open (D's legs are held to cash settlement). BP sells
    #    both legs together once the pair reaches its target; the latched exit
    #    is then retried leg by leg like any other.
    if clock_now < FINAL_FLAT and _pair_target([p for p in positions if p["play"] == "BP"], quotes, now):
        for pos in positions:
            if pos["play"] == "BP":
                pos["exit_pending"] = "PAIR_TARGET"
    for pos in positions:
        if pos["play"] == "D":
            continue
        quote = quotes.get(pos["token"])
        if pos["exit_pending"]:
            event = _try_exit(pos, quote, pos["lots_open"], pos["exit_pending"], now)
        elif quote is not None and quote.fresh(now) and quote.bid is not None:
            structure = pos["play"] in ("A", "AL") and failed_break(state, pos["opt_type"], spot)
            action = manage_position(pos, POLICIES[pos["play"]], quote.bid, now, structure_broken=structure)
            event = _try_exit(pos, quote, *action, now) if action else None
        elif clock_now >= POLICIES[pos["play"]].flat_at:
            event = _try_exit(pos, None, pos["lots_open"], "FLAT_TIME", now)
        else:
            event = None
        _save_position(conn, pos)
        if event is not None:
            notify(pos, _sell_text(pos, event))

    # 2. the afternoon box and A/C entries
    update_box(state, clock_now, spot, fut)
    direction = breakout_signal(state, now, spot, fut)
    budget = float(settings.EXPIRY_PAPER_BUDGET)
    if direction is not None:
        state["signals"].append({"ts": now.isoformat(), "dir": direction, "spot": spot, "fut": fut,
                                 "context": context})
        kind = "CE" if direction == "UP" else "PE"
        for play in ("A", "AL"):                    # AL: A's entries, its own exits and ceiling
            remaining = budget + min(0.0, _realized(conn, day, underlying, play))
            if state["trades"][play] >= A_MAX_TRADES:
                _bump(state, "refusals", f"{play}:MAX_TRADES")
                continue
            if any(p["play"] == play and p["status"] == "OPEN" for p in positions):
                _bump(state, "refusals", f"{play}:POSITION_OPEN")
                continue
            if remaining <= 0:
                _bump(state, "refusals", f"{play}:BUDGET_SPENT")
                continue
            atm = book.atm_strike(spot)
            step = book.strike_step if kind == "CE" else -book.strike_step
            reason = None
            for strike in (float(atm), float(atm + step)):          # ATM, else one strike OTM
                candidate = quoted_chain.get((strike, kind))
                reason = _quote_refusal(candidate, now, A_MAX_SPREAD)
                if reason:
                    continue
                contract, quote = candidate
                lots, prices = affordable_fill([(quote, contract.lot_size)], remaining, A_MAX_LOTS, schedule)
                if not lots:
                    reason = "DEPTH_OR_BUDGET"
                    continue
                pos = open_position(play, contract, prices[0], lots)
                notify(pos, _buy_text(pos, f"break {direction}, spot {spot:,.1f}, planned stop {pos['stop']:.2f}"))
                break
            if reason:
                _bump(state, "refusals", f"{play}:{reason}")
        for play, ceiling in (("C", budget), ("C500", C500_BUDGET)):
            if state["trades"][play] >= 1:
                continue
            strike = pick_lottery_strike(quoted_chain, direction, spot, now)
            if strike is None:
                _bump(state, "refusals", f"{play}:NO_STRIKE_IN_BAND")
                continue
            contract, quote = quoted_chain[(strike, kind)]
            lots, prices = affordable_fill([(quote, contract.lot_size)], ceiling, C_MAX_LOTS, schedule)
            if lots:
                pos = open_position(play, contract, prices[0], lots)
                notify(pos, _buy_text(pos, f"lottery {direction}, held into the auction"))
            else:
                _bump(state, "refusals", f"{play}:DEPTH_OR_BUDGET")

    # 3. B and its shadows BH and BP: the same auction strangle, managed differently
    for play in ("B", "BH", "BP"):
        if state["trades"][play] or not B_ENTRY_START <= clock_now < B_ENTRY_END:
            continue
        if spot is None:
            _bump(state, "refusals", f"{play}:NO_FRESH_INDEX")
            continue
        step = book.strike_step
        legs = [quoted_chain.get((float(math.ceil(spot / step) * step), "CE")),
                quoted_chain.get((float(math.floor(spot / step) * step), "PE"))]
        reason = next((r for r in (_quote_refusal(leg, now, BC_MAX_SPREAD) for leg in legs) if r), None)
        lots, prices = (0, []) if reason else affordable_fill(
            [(q, c.lot_size) for c, q in legs], budget, B_MAX_LOTS, schedule)
        if not lots:
            _bump(state, "refusals", f"{play}:{reason or 'DEPTH_OR_BUDGET'}")
            continue
        opened = [_new_position(day, underlying, play, exchange, contract, price, lots, now, schedule)
                  for (contract, _), price in zip(legs, prices)]
        for pos in opened:
            _save_position(conn, pos)
        state["trades"][play] = 1
        notify(opened[0], f"BUY {lots} lot strangle "
                          + " + ".join(f"{p['symbol']} @ {p['entry_price']:.2f}" for p in opened)
                          + f" (buy fees Rs {sum(p['costs'] for p in opened):,.2f}, "
                          + f"max loss Rs {sum(p['max_loss'] for p in opened):,.2f})")

    # 4. D (shadow): a short iron condor held to cash settlement
    if not state["trades"]["D"] and D_ENTRY_START <= clock_now < D_ENTRY_END:
        if spot is None:
            _bump(state, "refusals", "D:NO_FRESH_INDEX")
        else:
            step = book.strike_step
            atm = float(book.atm_strike(spot))
            width = D_WING_STEPS * step
            for short_steps in range(D_SHORT_STEPS, -1, -1):        # the farthest sold strikes that fit
                plan = [(atm + short_steps * step, "CE", "SHORT"),
                        (atm + short_steps * step + width, "CE", "LONG"),
                        (atm - short_steps * step, "PE", "SHORT"),
                        (atm - short_steps * step - width, "PE", "LONG")]
                candidates = [quoted_chain.get((strike, kind)) for strike, kind, _ in plan]
                reason = next((r for r in (_quote_refusal(c, now, BC_MAX_SPREAD) for c in candidates) if r), None)
                if reason is None:
                    lot_size = candidates[0][0].lot_size
                    lots, prices, max_loss, reason = condor_fill(
                        [(q, side) for (_, q), (_, _, side) in zip(candidates, plan)], lot_size, width, spot,
                        budget, schedule)
                if reason is None:
                    break
            if reason is None:
                for (contract, _), price, (_, _, side) in zip(candidates, prices, plan):
                    pos = _new_position(day, underlying, "D", exchange, contract, price, lots, now, schedule)
                    if side == "SHORT":
                        charges = round(sell_charges(price, lots * lot_size, schedule), 2)
                        pos["costs"], pos["net_pnl"] = charges, -charges
                        pos["_events"][0].update(action="SELL", charges=charges)
                    pos["side"], pos["width"] = side, width
                    pos["_events"][0]["short_steps"] = short_steps
                    pos["_events"][0]["reserve_intrinsic"] = round(D_STT_RESERVE_MOVE * spot, 2)
                    pos["max_loss"] = round(max_loss / len(plan), 2)
                    _save_position(conn, pos)
                state["trades"]["D"] = 1
            else:
                _bump(state, "refusals", f"D:{reason}")

    # 5. every open entry's liquidation mark, for the summary's path lines
    _mark_paths(conn, state, day, underlying, quotes, now, was_open)
    _save_state(conn, day, underlying, state, now)


def format_day_summary(conn, day: str, underlying: str, state: dict) -> str:
    """The day's ledger in rupees and paise: fees, filled net and assumed values each shown.

    Whole modeled = filled + assumed; assumed values are our own valuation of
    unfilled legs, never fills, so they are always shown beside it.
    """
    index_why = ", ".join(f"{k} {v}" for k, v in sorted(state.get("spot_refusals", {}).items()))
    lines = [f"Expiry paper {underlying} {day} (rules {RULES_VERSION}, execution "
             f"{state.get('execution', 'expiry-exec-v1')}), box {state['box_status']}, "
             f"signals {len(state['signals'])}",
             f"  data: ticks {state.get('ticks', 0)} of {EXPECTED_SLOTS} slots, max gap "
             f"{state.get('max_gap_sec', 0):.0f}s, gaps over {CONFIRM_MAX_GAP_SEC:.0f}s "
             f"{state.get('gaps_over_confirm', 0)}, slowest decision {state.get('max_decision_lag_sec', 0):.1f}s "
             f"after start, index refused {state.get('stale_spot', 0)}"
             + (f" ({index_why})" if index_why else "")
             + f", future refused {state.get('stale_fut', 0)}"]
    lines += context_lines(state, _settlement_spot(conn, day, underlying))
    lines.append("  path per entry: best and worst net if sold on the visible depth at a tick, after all fees "
                 "(marks, not fills); finished = filled + assumed")
    refusals, marks = state.get("refusals", {}), state.get("marks", {})

    def clock(stamp: str) -> str:
        return f"{datetime.fromisoformat(stamp):%H:%M:%S}"

    def section(plays: tuple[str, ...]) -> tuple[float, float, float]:
        total_filled = total_assumed = total_fees = 0.0
        for play in plays:
            rows = conn.execute("SELECT symbol, status, side, costs, net_pnl, assumed_pnl, events, entry_ts "
                                "FROM expiry_paper_positions WHERE day=? AND underlying=? AND play=?",
                                (day, underlying, play)).fetchall()
            why = ", ".join(f"{k.split(':', 1)[1]} {v}" for k, v in sorted(refusals.items())
                            if k.startswith(f"{play}:"))
            if not rows:
                lines.append(f"  {play}: no trade" + (f" (refused: {why})" if why else ""))
                continue
            fees = sum(r["costs"] for r in rows)
            filled = sum(r["net_pnl"] for r in rows)
            assumed = sum(r["assumed_pnl"] or 0.0 for r in rows)
            total_filled, total_assumed, total_fees = total_filled + filled, total_assumed + assumed, total_fees + fees
            auction = any(e.get("fill_model") == "AUCTION_WINDOW" for r in rows for e in json.loads(r["events"]))
            detail = ", ".join(f"{'sold ' if r['side'] == 'SHORT' else ''}{r['symbol']} {r['status']}" for r in rows)
            line = f"  {play}: filled net Rs {filled:+,.2f} after fees Rs {fees:,.2f}"
            if any(r["assumed_pnl"] is not None for r in rows):
                line += (f", assumed Rs {assumed:+,.2f} [our sampled index, not the official settlement], "
                         f"whole modeled Rs {filled + assumed:+,.2f}")
            breach = sum(e["reserve_breach"]["stt_beyond_reserve"] for r in rows
                         for e in json.loads(r["events"]) if e.get("reserve_breach"))
            if breach:
                line += (f", RESERVE BREACH: exercise STT Rs {breach:,.2f} beyond the "
                         f"{D_STT_RESERVE_MOVE:.0%}-move reserve")
            lines.append(line + f" ({detail}{'; auction-window fills unverified' if auction else ''})")
            for entry_ts in sorted({r["entry_ts"] for r in rows}):
                mark = marks.get(f"{play} {entry_ts}")
                if mark is None:
                    continue
                finished = sum(r["net_pnl"] + (r["assumed_pnl"] or 0.0) for r in rows if r["entry_ts"] == entry_ts)
                lines.append(f"    entry {clock(entry_ts)}: best Rs {mark['best']:+,.2f} at {clock(mark['best_ts'])}, "
                             f"worst Rs {mark['worst']:+,.2f} at {clock(mark['worst_ts'])} ({mark['n']} marks), "
                             f"finished Rs {finished:+,.2f}")
        return total_filled, total_assumed, total_fees

    day_filled, day_assumed, day_fees = section(MAIN_PLAYS)
    lines.append(f"  day: filled net Rs {day_filled:+,.2f} + assumed Rs {day_assumed:+,.2f} = whole modeled "
                 f"Rs {day_filled + day_assumed:+,.2f} (fees Rs {day_fees:,.2f})")
    lines.append(f"  shadow plays ({state.get('shadow', SHADOW_VERSION)}, frozen, no Telegram trades):")
    section(SHADOW_PLAYS)
    totals = conn.execute(
        "SELECT play, COALESCE(SUM(net_pnl), 0), COALESCE(SUM(assumed_pnl), 0) FROM expiry_paper_positions "
        "WHERE underlying=? AND status != 'OPEN' GROUP BY play", (underlying,)).fetchall()
    main = [r for r in totals if r[0] in MAIN_PLAYS]
    shadow = [r for r in totals if r[0] in SHADOW_PLAYS]
    expiries = conn.execute("SELECT COUNT(*) FROM expiry_paper_days WHERE underlying=?", (underlying,)).fetchone()[0]
    if main:
        lines.append(f"  {underlying} to date over {expiries} expiries, filled: " + ", ".join(
            f"{r[0]} Rs {r[1]:+,.2f}" for r in main))
        if any(r[2] for r in main):
            lines.append("  assumed settlements, kept apart: " + ", ".join(
                f"{r[0]} Rs {r[2]:+,.2f}" for r in main if r[2]))
        lines.append(f"  whole modeled to date: Rs {sum(r[1] + r[2] for r in main):+,.2f}")
    if shadow:
        lines.append("  shadow whole modeled to date (filled + assumed): " + ", ".join(
            f"{r[0]} Rs {r[1] + r[2]:+,.2f}" for r in shadow))
    lines += owner_rule_lines(conn, day)
    return "\n".join(lines)


def owner_rule_lines(conn, through: str) -> list[str]:
    """The owner's stop-rule tally over every expiry (all underlyings) up to ``through``.

    An expiry's main-book result is the whole modeled (filled + assumed) of
    A, B and C; a day without a main trade is not a loss. Per play it counts
    the expiries the play traded and how many of them it lost.
    """
    days = conn.execute("SELECT day, underlying FROM expiry_paper_days WHERE day <= ? ORDER BY day, underlying",
                        (through,)).fetchall()
    whole = {(r[0], r[1], r[2]): r[3] for r in conn.execute(
        "SELECT day, underlying, play, SUM(net_pnl + COALESCE(assumed_pnl, 0)) FROM expiry_paper_positions "
        "WHERE day <= ? AND status != 'OPEN' GROUP BY day, underlying, play", (through,))}
    results = [sum(whole.get((d, u, play), 0.0) for play in MAIN_PLAYS) for d, u in days]
    lost = sum(result < 0 for result in results)
    streak = 0
    for result in reversed(results):
        if result >= 0:
            break
        streak += 1
    per_play = []
    for play in MAIN_PLAYS + SHADOW_PLAYS:
        traded = [value for (_, _, p), value in whole.items() if p == play]
        if traded:
            per_play.append(f"{play} {sum(value < 0 for value in traded)}/{len(traded)}")
    met = len(results) >= OWNER_REVIEW_EXPIRIES and lost == len(results)
    verdict = "RULE MET: every expiry lost, stop expiry-day F&O" if met else \
        f"{max(0, OWNER_REVIEW_EXPIRIES - len(results))} expiries left to observe"
    return [f"  owner rule ({OWNER_RULE_SET}): expiry {len(results)} of {OWNER_REVIEW_EXPIRIES}, main book lost "
            f"{lost} of {len(results)}, losing streak {streak}; {verdict}",
            "  losing expiries / expiries traded, per play (a play that keeps losing is dropped): "
            + (", ".join(per_play) or "none")]


async def run_expiry_tick(kite, db_path: Optional[str] = None, now: Optional[datetime] = None,
                          books: Optional[dict] = None, clock: Optional[Callable[[], datetime]] = None) -> None:
    """One 10-second step for every underlying expiring today (notices go to the outbox).

    ``now`` is the start time (it decides whether to run); ``clock`` gives the
    decision time after each quote batch. A test passing only ``now`` gets a
    clock frozen at it.
    """
    started = now or datetime.now(IST)
    if clock is None:
        clock = (lambda: now) if now is not None else (lambda: datetime.now(IST))
    if not TICK_START <= started.time() < SESSION_END:
        return
    from fno_underlyings import SPECS, get_instruments_for

    path = db_path or settings.DB_PATH
    reconcile(path, started)                # anything left from an earlier expiry
    names = [n.strip().upper() for n in settings.EXPIRY_PAPER_UNDERLYINGS.split(",") if n.strip()]
    for name in names:
        if name not in INDEX_QUOTE_KEYS or name not in SPECS:
            continue
        book = (books or {}).get(name) or get_instruments_for(name)
        if not book.ready(started.date()) or not book.is_expiry_day(started.date()):
            continue
        with _store(expiry_db_path(path)) as conn:
            await _tick_underlying(kite, conn, book, name, SPECS[name].segment, started, clock)
