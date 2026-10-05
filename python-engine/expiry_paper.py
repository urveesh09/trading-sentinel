"""Expiry-day paper book: three pre-registered plays on the weekly index expiry.

Broker-free. It never imports an executor or places an order. Design, rules and
the reasoning behind them: docs/2026-10-05-expiry-day-paper-book.md.

The tick (``run_expiry_tick``) runs every 10 s from 12:59 to 15:40 IST. It acts
only for an underlying whose nearest option expiry is today according to the
instrument dump, so holiday shifts are handled by the exchange calendar: NIFTY
(NFO) on Tuesdays and SENSEX (BFO) on Thursdays. One quote batch per
underlying per tick (index, front future, ATM +/- 8 strikes of today's expiry
and every open leg) is logged in full, so the 15:15-15:40 auction window is
recorded too.

A  Gamma breakout: the 13:00-13:30 index range is the box. Two consecutive
   ticks beyond it (futures agreeing) buy the ATM option in that direction.
   Adaptive exits: -30% stop, failed-break and 8-minute time stops, bank half
   at +40% with the rest at breakeven, then trails that tighten with gain and
   after 15:00. Flat by 15:13, before the index freezes for the auction.
B  Auction strangle: at 15:13:30-15:15 buy the strikes either side of spot and
   hold through the closing auction. A leg that doubles banks half and trails;
   everything is sold by 15:38.
C  Lottery ticket: on A's breakout signal, buy the nearest strike priced
   0.004%-0.03% of spot in that direction, held through the auction for the
   repricing; bank half at 3x, trail after 5x, sold by 15:38.

Each play risks at most ``EXPIRY_PAPER_BUDGET`` per expiry day: A sizes from its
-30% stop and shrinks after a loss; B and C size so the whole premium fits.
Fills: buys at the best ask, sells at the best bid; costs use ``calc_fno_costs``
(each exit slice is charged a full round trip, a slight overstatement). State
lives in ``<DB_PATH>.expiry-paper.db``; nothing touches the operational ledger.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
import json
import logging
import math
import sqlite3
from typing import Optional

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
B_ENTRY_START, B_ENTRY_END = time(15, 13, 30), time(15, 15)
FINAL_FLAT = time(15, 38)
CHAIN_WINDOW = 8
MIN_BOX_SAMPLES = 30
BREAK_BUFFER_WIDTH, BREAK_BUFFER_SPOT = 0.15, 0.0002
CONFIRM_TICKS = 2
FAIL_BACK_WIDTH = 0.25
A_MAX_TRADES, A_MAX_LOTS, A_MAX_OUTLAY = 2, 4, 20000.0
A_MAX_SPREAD, BC_MAX_SPREAD = 0.06, 0.10
B_MAX_LOTS, C_MAX_LOTS = 4, 10
C_PREMIUM_BAND = (0.00004, 0.0003)  # ask as a fraction of spot (NIFTY ~1.0-7.5)


@dataclass(frozen=True)
class ExitPolicy:
    hard_stop: Optional[float]                  # fraction of entry premium lost
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
        entry_ts TEXT NOT NULL, entry_price REAL NOT NULL, peak REAL NOT NULL, stop REAL NOT NULL,
        banked INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, gross REAL NOT NULL DEFAULT 0,
        costs REAL NOT NULL DEFAULT 0, net_pnl REAL NOT NULL DEFAULT 0, events TEXT NOT NULL DEFAULT '[]')""",
    """CREATE TABLE IF NOT EXISTS expiry_paper_days (
        day TEXT NOT NULL, underlying TEXT NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (day, underlying))""",
    """CREATE TABLE IF NOT EXISTS expiry_paper_ticks (
        day TEXT NOT NULL, underlying TEXT NOT NULL, ts TEXT NOT NULL, spot REAL, fut REAL,
        quotes TEXT NOT NULL, PRIMARY KEY (day, underlying, ts))""",
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


# ---------------------------------------------------------------------------
# quotes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Quote:
    bid: Optional[float]
    ask: Optional[float]
    ltp: Optional[float]

    def spread_ok(self, max_fraction: float) -> bool:
        return self.bid is not None and self.ask is not None and self.ask >= self.bid \
            and (self.ask - self.bid) <= max_fraction * self.ask

    def sell_price(self) -> float:
        """What a market sell would get: the bid, else 2% under the last trade, else nothing."""
        if self.bid is not None:
            return self.bid
        return round(self.ltp * 0.98, 2) if self.ltp is not None else 0.0


def _positive(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def parse_quote(packet: dict) -> Quote:
    depth = packet.get("depth") if isinstance(packet.get("depth"), dict) else {}

    def best(side: str) -> Optional[float]:
        levels = depth.get(side)
        if isinstance(levels, list) and levels and isinstance(levels[0], dict):
            if _positive(levels[0].get("quantity")):
                return _positive(levels[0].get("price"))
        return None

    return Quote(bid=best("buy"), ask=best("sell"), ltp=_positive(packet.get("last_price")))


# ---------------------------------------------------------------------------
# pure rules
# ---------------------------------------------------------------------------

def new_day_state() -> dict:
    return {"rules": RULES_VERSION, "box": None, "box_samples": [], "box_status": "BUILDING",
            "pending": None, "armed": {"UP": True, "DOWN": True}, "signals": [],
            "trades": {"A": 0, "B": 0, "C": 0}, "last_spot": None, "summary_sent": False}


def update_box(state: dict, now: time, spot: Optional[float], fut: Optional[float]) -> None:
    """Collect 13:00-13:30 samples, then freeze the box once (or mark it unusable)."""
    if state["box_status"] != "BUILDING":
        return
    if BOX_START <= now < BOX_END:
        if spot is not None:
            state["box_samples"].append([spot, fut])
        return
    if now < BOX_END:
        return
    samples, state["box_samples"] = state["box_samples"], []
    if len(samples) < MIN_BOX_SAMPLES:
        state["box_status"] = f"UNUSABLE_{len(samples)}_SAMPLES"
        return
    futs = [f for _, f in samples if f is not None]
    state["box"] = {"hi": max(s for s, _ in samples), "lo": min(s for s, _ in samples),
                    "fut_hi": max(futs) if futs else None, "fut_lo": min(futs) if futs else None,
                    "n": len(samples)}
    state["box_status"] = "READY"


def breakout_signal(state: dict, now: time, spot: Optional[float], fut: Optional[float]) -> Optional[str]:
    """'UP'/'DOWN' when a confirmed, armed break fires in the entry window, else None."""
    box = state["box"]
    if state["box_status"] != "READY" or spot is None:
        return None
    width = box["hi"] - box["lo"]
    buffer = max(BREAK_BUFFER_WIDTH * width, BREAK_BUFFER_SPOT * spot)
    if box["lo"] <= spot <= box["hi"]:
        state["armed"] = {"UP": True, "DOWN": True}
    direction = None
    if spot > box["hi"] + buffer and (fut is None or box["fut_hi"] is None or fut > box["fut_hi"]):
        direction = "UP"
    elif spot < box["lo"] - buffer and (fut is None or box["fut_lo"] is None or fut < box["fut_lo"]):
        direction = "DOWN"
    if direction is None:
        state["pending"] = None
        return None
    pending = state["pending"]
    count = pending["count"] + 1 if pending and pending["dir"] == direction else 1
    state["pending"] = {"dir": direction, "count": count}
    if count < CONFIRM_TICKS or not state["armed"][direction] or not BOX_END <= now < A_ENTRY_END:
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
    """Update peak/stop in ``pos`` and return (lots to sell, reason) or None."""
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


def a_lots(ask: float, lot_size: int, remaining_budget: float) -> int:
    risk_per_lot = ask * POLICIES["A"].hard_stop * lot_size
    by_risk = int(remaining_budget // risk_per_lot) if risk_per_lot > 0 else 0
    by_outlay = int(A_MAX_OUTLAY // (ask * lot_size)) if ask > 0 else 0
    return max(0, min(A_MAX_LOTS, by_risk, by_outlay))


def premium_lots(cost_per_lot: float, budget: float, cap: int) -> int:
    return max(0, min(cap, int(budget // cost_per_lot))) if cost_per_lot > 0 else 0


def pick_lottery_strike(chain: dict, direction: str, spot: float) -> Optional[float]:
    """Nearest-to-money OTM strike whose ask sits inside the lottery band."""
    lo, hi = (spot * f for f in C_PREMIUM_BAND)
    opt_type = "CE" if direction == "UP" else "PE"
    eligible = [strike for (strike, kind), (_, q) in chain.items()
                if kind == opt_type and (strike > spot if kind == "CE" else strike < spot)
                and q.ask is not None and lo <= q.ask <= hi and q.spread_ok(BC_MAX_SPREAD)]
    if not eligible:
        return None
    return min(eligible) if opt_type == "CE" else max(eligible)


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

def _load_state(conn, day: str, underlying: str) -> dict:
    row = conn.execute("SELECT state FROM expiry_paper_days WHERE day=? AND underlying=?",
                       (day, underlying)).fetchone()
    return json.loads(row["state"]) if row else new_day_state()


def _open_positions(conn, day: str, underlying: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM expiry_paper_positions WHERE day=? AND underlying=? AND status='OPEN'",
                        (day, underlying)).fetchall()
    return [dict(row) for row in rows]


def _realized(conn, day: str, underlying: str, play: str) -> float:
    return float(conn.execute(
        "SELECT COALESCE(SUM(net_pnl), 0) FROM expiry_paper_positions WHERE day=? AND underlying=? AND play=?",
        (day, underlying, play)).fetchone()[0])


def _last_logged_quote(conn, day: str, underlying: str, symbol: str) -> Quote:
    """Most recent logged quote for a leg missing from this tick (flat-time fallback)."""
    for row in conn.execute("SELECT quotes FROM expiry_paper_ticks WHERE day=? AND underlying=? "
                            "ORDER BY ts DESC LIMIT 30", (day, underlying)):
        logged = json.loads(row["quotes"]).get(symbol)
        if logged is not None:
            return Quote(*logged)
    return Quote(None, None, None)


def _sell(pos: dict, lots: int, price: float, reason: str, now: datetime) -> dict:
    from fno_costs import calc_fno_costs

    qty = lots * pos["lot_size"]
    gross = (price - pos["entry_price"]) * qty
    costs = calc_fno_costs(pos["entry_price"], price, qty)
    pos["lots_open"] -= lots
    pos["gross"] = round(pos["gross"] + gross, 2)
    pos["costs"] = round(pos["costs"] + costs, 2)
    pos["net_pnl"] = round(pos["gross"] - pos["costs"], 2)
    if pos["lots_open"] == 0:
        pos["status"] = "CLOSED"
    event = {"ts": now.isoformat(), "action": reason, "lots": lots, "price": price,
             "net": round(gross - costs, 2)}
    pos["_events"].append(event)
    return event


def _new_position(day: str, underlying: str, play: str, exchange: str, contract, quote: Quote,
                  lots: int, now: datetime) -> dict:
    policy = POLICIES[play]
    entry = quote.ask
    return {"id": None, "day": day, "underlying": underlying, "play": play, "exchange": exchange,
            "symbol": contract.tradingsymbol, "token": contract.token, "strike": contract.strike,
            "opt_type": contract.instrument_type, "lot_size": contract.lot_size, "lots": lots,
            "lots_open": lots, "entry_ts": now.isoformat(), "entry_price": entry, "peak": entry,
            "stop": round(entry * (1 - policy.hard_stop), 2) if policy.hard_stop else 0.0,
            "banked": 0, "status": "OPEN", "gross": 0.0, "costs": 0.0, "net_pnl": 0.0,
            "_events": [{"ts": now.isoformat(), "action": "BUY", "lots": lots, "price": entry}]}


def _save_position(conn, pos: dict) -> None:
    columns = [c for c in pos if not c.startswith("_") and c not in ("id", "events")]
    if pos["id"] is None:
        cursor = conn.execute(
            f"INSERT INTO expiry_paper_positions ({', '.join(columns)}, events) "
            f"VALUES ({', '.join('?' for _ in columns)}, ?)",
            [pos[c] for c in columns] + [json.dumps(pos["_events"])])
        pos["id"] = cursor.lastrowid
        return
    prior = json.loads(conn.execute("SELECT events FROM expiry_paper_positions WHERE id=?",
                                    (pos["id"],)).fetchone()[0])
    conn.execute(f"UPDATE expiry_paper_positions SET {', '.join(f'{c}=?' for c in columns)}, events=? "
                 "WHERE id=?", [pos[c] for c in columns] + [json.dumps(prior + pos["_events"]), pos["id"]])


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


async def _tick_underlying(kite, conn, book, underlying: str, exchange: str, now: datetime) -> list[str]:
    day = now.date().isoformat()
    clock = now.time()
    state = _load_state(conn, day, underlying)
    positions = _open_positions(conn, day, underlying)
    for pos in positions:
        pos["_events"] = []
    future = book.front_future(now.date())
    expiry = now.date()

    anchor = state["last_spot"]
    if anchor is None:
        first = await _fetch(kite, underlying, exchange, [], future)
        anchor = (_positive((first.get(SPOT_KEY) or {}).get("last_price"))
                  or _positive((first.get(FUT_KEY) or {}).get("last_price")))
        if anchor is None:
            return []
    chain = _chain(book, expiry, anchor)
    held = {pos["token"]: book.by_symbol.get(pos["symbol"]) for pos in positions}
    contracts = {c.token: c for c in [*chain.values(), *(c for c in held.values() if c is not None)]}
    raw = await _fetch(kite, underlying, exchange, list(contracts.values()), future)
    spot = _positive((raw.get(SPOT_KEY) or {}).get("last_price"))
    fut = _positive((raw.get(FUT_KEY) or {}).get("last_price"))
    quotes = {token: parse_quote(raw[token]) for token in contracts if isinstance(raw.get(token), dict)}
    quoted_chain = {key: (c, quotes[c.token]) for key, c in chain.items() if c.token in quotes}
    if spot is not None:
        state["last_spot"] = spot
    conn.execute("INSERT OR REPLACE INTO expiry_paper_ticks VALUES (?,?,?,?,?,?)", (
        day, underlying, now.isoformat(), spot, fut,
        json.dumps({contracts[t].tradingsymbol: [q.bid, q.ask, q.ltp] for t, q in quotes.items()},
                   separators=(",", ":"))))

    messages: list[str] = []
    label = f"Expiry paper {underlying}"

    # 1. manage what is open
    for pos in positions:
        quote = quotes.get(pos["token"])
        if quote is None:
            if clock < POLICIES[pos["play"]].flat_at:
                continue
            quote = _last_logged_quote(conn, day, underlying, pos["symbol"])
        bid = quote.sell_price()
        structure = pos["play"] == "A" and failed_break(state, pos["opt_type"], spot)
        action = manage_position(pos, POLICIES[pos["play"]], bid, now, structure_broken=structure)
        if action is not None:
            lots, reason = action
            event = _sell(pos, lots, bid, reason, now)
            messages.append(f"{label} {pos['play']}: SELL {lots} lot {pos['symbol']} @ {bid:.2f} ({reason}), "
                            f"slice net Rs {event['net']:+,.0f}")
        _save_position(conn, pos)

    # 2. the afternoon box and A/C entries
    update_box(state, clock, spot, fut)
    direction = breakout_signal(state, clock, spot, fut)
    if direction is not None and spot is not None:
        state["signals"].append({"ts": now.isoformat(), "dir": direction, "spot": spot, "fut": fut})
        kind = "CE" if direction == "UP" else "PE"
        open_a = any(p["play"] == "A" and p["status"] == "OPEN" for p in positions)
        budget = float(settings.EXPIRY_PAPER_BUDGET)
        remaining = budget + min(0.0, _realized(conn, day, underlying, "A"))
        atm = book.atm_strike(spot)
        candidate = quoted_chain.get((float(atm), kind))
        if state["trades"]["A"] < A_MAX_TRADES and not open_a and remaining > 0 and candidate:
            contract, quote = candidate
            lots = a_lots(quote.ask, contract.lot_size, remaining) if quote.spread_ok(A_MAX_SPREAD) else 0
            if lots:
                pos = _new_position(day, underlying, "A", exchange, contract, quote, lots, now)
                _save_position(conn, pos)
                state["trades"]["A"] += 1
                messages.append(f"{label} A: BUY {lots} lot {contract.tradingsymbol} @ {quote.ask:.2f} "
                                f"(break {direction}, spot {spot:,.1f}, stop {pos['stop']:.2f})")
        if state["trades"]["C"] < 1:
            strike = pick_lottery_strike(quoted_chain, direction, spot)
            if strike is not None:
                contract, quote = quoted_chain[(strike, kind)]
                lots = premium_lots(quote.ask * contract.lot_size, budget, C_MAX_LOTS)
                if lots:
                    pos = _new_position(day, underlying, "C", exchange, contract, quote, lots, now)
                    _save_position(conn, pos)
                    state["trades"]["C"] += 1
                    messages.append(f"{label} C: BUY {lots} lot {contract.tradingsymbol} @ {quote.ask:.2f} "
                                    f"(lottery {direction}, held into the auction)")

    # 3. B: the auction strangle
    if state["trades"]["B"] == 0 and B_ENTRY_START <= clock < B_ENTRY_END and spot is not None:
        step = book.strike_step
        legs = [quoted_chain.get((float(math.ceil(spot / step) * step), "CE")),
                quoted_chain.get((float(math.floor(spot / step) * step), "PE"))]
        if all(leg and leg[1].spread_ok(BC_MAX_SPREAD) for leg in legs):
            cost = sum(q.ask * c.lot_size for c, q in legs)
            lots = premium_lots(cost, float(settings.EXPIRY_PAPER_BUDGET), B_MAX_LOTS)
            if lots:
                for contract, quote in legs:
                    _save_position(conn, _new_position(day, underlying, "B", exchange, contract, quote, lots, now))
                state["trades"]["B"] = 1
                messages.append(f"{label} B: BUY {lots} lot strangle "
                                + " + ".join(f"{c.tradingsymbol} @ {q.ask:.2f}" for c, q in legs))

    # 4. end-of-day summary once everything is flat
    if clock >= FINAL_FLAT and not state["summary_sent"] and not _open_positions(conn, day, underlying):
        state["summary_sent"] = True
        messages.append(format_day_summary(conn, day, underlying, state))

    conn.execute("INSERT OR REPLACE INTO expiry_paper_days VALUES (?,?,?,?)",
                 (day, underlying, json.dumps(state), now.isoformat()))
    return messages


def format_day_summary(conn, day: str, underlying: str, state: dict) -> str:
    lines = [f"Expiry paper {underlying} {day} ({RULES_VERSION}), box {state['box_status']}, "
             f"signals {len(state['signals'])}"]
    for play in ("A", "B", "C"):
        rows = conn.execute("SELECT symbol, net_pnl FROM expiry_paper_positions WHERE day=? AND underlying=? "
                            "AND play=?", (day, underlying, play)).fetchall()
        total = sum(r["net_pnl"] for r in rows)
        detail = ", ".join(f"{r['symbol']} {r['net_pnl']:+,.0f}" for r in rows) or "no trade"
        lines.append(f"  {play}: Rs {total:+,.0f} ({detail})")
    book = conn.execute("SELECT play, COALESCE(SUM(net_pnl), 0), COUNT(DISTINCT day || underlying) "
                        "FROM expiry_paper_positions WHERE status='CLOSED' GROUP BY play").fetchall()
    if book:
        lines.append("  to date: " + ", ".join(f"{r[0]} Rs {r[1]:+,.0f} over {r[2]} expiries" for r in book))
    return "\n".join(lines)


async def run_expiry_tick(kite, db_path: Optional[str] = None, now: Optional[datetime] = None,
                          books: Optional[dict] = None) -> list[str]:
    """One 10-second step for every underlying expiring today; returns Telegram lines."""
    now = now or datetime.now(IST)
    if not TICK_START <= now.time() <= SESSION_END:
        return []
    from fno_underlyings import SPECS, get_instruments_for

    names = [n.strip().upper() for n in settings.EXPIRY_PAPER_UNDERLYINGS.split(",") if n.strip()]
    messages: list[str] = []
    for name in names:
        if name not in INDEX_QUOTE_KEYS or name not in SPECS:
            continue
        book = (books or {}).get(name) or get_instruments_for(name)
        if not book.ready(now.date()) or not book.is_expiry_day(now.date()):
            continue
        with _store(expiry_db_path(db_path or settings.DB_PATH)) as conn:
            messages += await _tick_underlying(kite, conn, book, name, SPECS[name].segment, now)
    return messages
