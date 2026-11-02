"""E01.1 lab: the expiry book's plays on recorded quotes, fast enough for a genome search.

It is not a second implementation of the money. Fills, fees, stops, the box, the signal, the strike pick and
sizing all call the engine's own functions in ``python-engine/expiry_paper.py``. What it drops is the store and
the record-only context, so one play on one session takes milliseconds instead of seconds.

``parity.py`` proves it: every leg of A, B, C and CE01 on all eight sessions, ordinary and adverse quotes, equal
to the native replay's stored results, to the paisa.

Sessions:
    Recorded  the eight archived October sessions, real depth, real clocks.
    Sept      the four September ten-second files. See sept.py; those are partial and labelled so.

Research only. No network, no broker, no Telegram. Nothing here reaches the engine.
"""
from __future__ import annotations

import json
import logging
import math
import pickle
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
LOCAL = HERE / "_local"
COMPACT = LOCAL / "compact"
SOURCE = ROOT / "docs/research/simulation/2026-11-02-expiry-e01/_local/export/expiry.sqlite"
sys.path.insert(0, str(ROOT / "python-engine"))
logging.disable(logging.CRITICAL)

import expiry_paper as EP  # noqa: E402
from fno_instruments import FnoInstruments  # noqa: E402
from fno_models import Contract  # noqa: E402

LOTS = {"NIFTY": 65, "SENSEX": 20}
EXCHANGE = {"NIFTY": "NFO", "SENSEX": "BFO"}
# One row per quote: present, bid count, ask count, 5 x (price, qty) each side, ltp, age seconds, oi.
N_COL = 26
ADVERSE_STEP = 0.05


def _read_db():
    c = sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def recorded_keys() -> list[tuple[str, str]]:
    with _read_db() as c:
        return [tuple(r) for r in c.execute("select distinct day, underlying from expiry_paper_ticks order by day")]


def _packet(raw, adverse: bool) -> dict:
    """The same packet the native replay hands the engine, from one logged leg."""
    if isinstance(raw, list):
        bid, bn, ask, an, ltp, stamp = raw
        bids, asks, oi = [[bid, bn]], [[ask, an]], None
    else:
        bids, asks, ltp, stamp, oi = raw["b"], raw["a"], raw["ltp"], raw["ts"], raw.get("oi")

    def levels(rows, buy):
        out = []
        for price, qty in rows:
            if price is None:
                continue
            new = round(float(price) + (ADVERSE_STEP if not buy else -ADVERSE_STEP), 8) if adverse else price
            if new > 0:
                out.append({"price": new, "quantity": qty})
        return out

    return {"last_price": ltp, "timestamp": stamp, "oi": oi,
            "depth": {"buy": levels(bids, True), "sell": levels(asks, False)}}


def prepare_session(day: str, underlying: str) -> dict:
    """Compact one recorded session, ordinary and adverse. Run once; every worker maps the result read-only."""
    with _read_db() as c:
        ticks = [dict(r) for r in c.execute(
            "select * from expiry_paper_ticks where day=? and underlying=? order by ts", (day, underlying))]
    names: set[str] = set()
    for t in ticks:
        t["quotes"] = json.loads(t["quotes"])
        names.update(t["quotes"]["legs"])
    names = sorted(names)
    index = {n: j for j, n in enumerate(names)}
    meta = {"day": day, "underlying": underlying, "names": names, "n": len(ticks), "now": [], "spot": [], "fut": [],
            "anchor": [], "hi_spot_ltp": []}
    arrays = {False: np.full((len(ticks), len(names), N_COL), np.nan), True: np.full((len(ticks), len(names), N_COL), np.nan)}
    last_spot = None
    for i, t in enumerate(ticks):
        now = datetime.fromisoformat(t["ts"])
        meta["now"].append(now)
        raw = t["quotes"]
        packets = {}
        for kind, column in (("index", "spot"), ("future", "fut")):
            q = raw.get(kind)
            if q is None:
                value = t[column]
                packets[kind] = {"last_price": value, "timestamp": t["ts"]} if value is not None else None
            elif q.get("status") != "MISSING":
                packets[kind] = {"last_price": q.get("ltp"), "timestamp": q.get("ts"), "oi": q.get("oi")}
            else:
                packets[kind] = None
        spot, _ = EP._observe(packets["index"], now)
        fut, _ = EP._observe(packets["future"], now)
        first = EP._positive((packets["index"] or {}).get("last_price"))
        meta["anchor"].append(last_spot if last_spot is not None else first)
        meta["spot"].append(spot)
        meta["fut"].append(fut)
        if spot is not None:
            last_spot = spot
        for symbol, leg in raw["legs"].items():
            j = index[symbol]
            for adverse in (False, True):
                q = EP.parse_quote(_packet(leg, adverse))
                row = arrays[adverse][i, j]
                row[0], row[1], row[2] = 1, len(q.bids), len(q.asks)
                for k, (price, qty) in enumerate(q.bids):
                    row[3 + 2 * k], row[4 + 2 * k] = price, qty
                for k, (price, qty) in enumerate(q.asks):
                    row[13 + 2 * k], row[14 + 2 * k] = price, qty
                row[23] = q.ltp if q.ltp is not None else np.nan
                row[24] = (now - q.ts).total_seconds() if q.ts is not None else np.nan
                row[25] = q.oi if q.oi is not None else np.nan
    COMPACT.mkdir(parents=True, exist_ok=True)
    for adverse, array in arrays.items():
        np.save(COMPACT / f"{day}-{underlying}-{'adverse' if adverse else 'ordinary'}.npy", array)
    (COMPACT / f"{day}-{underlying}.pkl").write_bytes(pickle.dumps(meta))
    return {"day": day, "underlying": underlying, "ticks": len(ticks), "symbols": len(names)}


def _book(day: str, underlying: str, names: list[str]) -> FnoInstruments:
    lot = LOTS[underlying]
    contracts = []
    for i, name in enumerate(names):
        match = re.search(r"(\d{5})(CE|PE)$", name)
        assert match and name.startswith(underlying), (day, name)
        contracts.append(Contract(100000000 + i, name, underlying, date.fromisoformat(day), float(match[1]), match[2], lot))
    contracts.append(Contract(99999999, f"{underlying}_ARCHIVED_FUTURE", underlying, date(2026, 11, 30), 0, "FUT", lot, .1))
    book = FnoInstruments(underlying=underlying, segment=EXCHANGE[underlying], json_path=str(LOCAL / "unused.json"))
    book._load_contracts(contracts)
    book.refreshed_on = date.fromisoformat(day)
    return book


class Recorded:
    """One archived session. Quotes are rebuilt on demand from a read-only map, so workers share one copy."""

    partial = False

    def __init__(self, day: str, underlying: str, adverse: bool = False):
        meta = pickle.loads((COMPACT / f"{day}-{underlying}.pkl").read_bytes())
        self.day, self.underlying, self.adverse = day, underlying, adverse
        self.names, self.n = meta["names"], meta["n"]
        self.now, self.spot, self.fut, self.anchor = meta["now"], meta["spot"], meta["fut"], meta["anchor"]
        self.clock = [t.time() for t in self.now]
        self.index = {n: j for j, n in enumerate(self.names)}
        self.date = date.fromisoformat(day)
        self.exchange = EXCHANGE[underlying]
        self.schedule = EP.fee_schedule(self.exchange)
        self.book = _book(day, underlying, self.names)
        self.step = self.book.strike_step
        self.q = np.load(COMPACT / f"{day}-{underlying}-{'adverse' if adverse else 'ordinary'}.npy", mmap_mode="r")
        self._chain_memo: dict[float, dict] = {}
        self._signals: dict = {}

    def quote(self, i: int, symbol: str) -> Optional[EP.Quote]:
        j = self.index.get(symbol)
        if j is None:
            return None
        row = self.q[i, j]
        if not row[0] == 1:
            return None
        nb, na = int(row[1]), int(row[2])
        bids = tuple((float(row[3 + 2 * k]), int(row[4 + 2 * k])) for k in range(nb))
        asks = tuple((float(row[13 + 2 * k]), int(row[14 + 2 * k])) for k in range(na))
        ltp = None if math.isnan(row[23]) else float(row[23])
        ts = None if math.isnan(row[24]) else self.now[i] - timedelta(seconds=float(row[24]))
        return EP.Quote(bids=bids, asks=asks, ltp=ltp, ts=ts, oi=None)

    def contracts_near(self, i: int) -> dict:
        anchor = self.anchor[i]
        if anchor is None:
            return {}
        memo = self._chain_memo.get(anchor)
        if memo is None:
            memo = EP._chain(self.book, self.date, anchor)
            self._chain_memo[anchor] = memo
        return memo

    def quoted_chain(self, i: int) -> dict:
        out = {}
        for key, contract in self.contracts_near(i).items():
            q = self.quote(i, contract.tradingsymbol)
            if q is not None:
                out[key] = (contract, q)
        return out

    def atm(self, spot: float) -> float:
        return float(self.book.atm_strike(spot))

    def settlement_spot(self) -> Optional[float]:
        """The native reconcile's choice: the last fresh index at or after 15:36."""
        for i in range(self.n - 1, -1, -1):
            stamp = self.now[i].time().isoformat()[:8]
            if stamp < EP.AUCTION_CLOSE_KNOWN.isoformat():
                return None
            if self.spot[i] is not None:
                return float(self.spot[i])
        return None

    def contract(self, symbol: str):
        return self.book.by_symbol.get(symbol)


# ---------------------------------------------------------------------------
# the signal: the engine's box and confirmation, unchanged unless a gene asks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalGene:
    box_end: time = EP.BOX_END
    confirm: int = EP.CONFIRM_TICKS
    buffer_width: float = EP.BREAK_BUFFER_WIDTH
    last_entry: time = EP.A_ENTRY_END


NATIVE_SIGNAL = SignalGene()


def signal_stream(S, gene: SignalGene = NATIVE_SIGNAL) -> tuple[dict, list[tuple[int, str]]]:
    """The final day state (its box) and every confirmed break: (tick, direction)."""
    memo = S._signals.get(gene)
    if memo is not None:
        return memo
    state = EP.new_day_state()
    out = []
    native = gene == NATIVE_SIGNAL
    saved = (EP.BOX_END, EP.CONFIRM_TICKS, EP.BREAK_BUFFER_WIDTH, EP.A_ENTRY_END)
    try:
        if not native:
            EP.BOX_END, EP.CONFIRM_TICKS, EP.BREAK_BUFFER_WIDTH, EP.A_ENTRY_END = \
                gene.box_end, gene.confirm, gene.buffer_width, gene.last_entry
        snapshots = []
        for i in range(S.n):
            if S.anchor[i] is None:
                EP.update_box(state, S.clock[i], None, None)
                snapshots.append(None)
                continue
            EP.update_box(state, S.clock[i], S.spot[i], S.fut[i])
            d = EP.breakout_signal(state, S.now[i], S.spot[i], S.fut[i])
            if d is not None:
                out.append((i, d))
    finally:
        EP.BOX_END, EP.CONFIRM_TICKS, EP.BREAK_BUFFER_WIDTH, EP.A_ENTRY_END = saved
    S._signals[gene] = (state, out)
    return state, out


# ---------------------------------------------------------------------------
# managing an open leg: the native tick's exit block
# ---------------------------------------------------------------------------

def _realized(positions: list[dict]) -> float:
    return sum(p["net_pnl"] + (p.get("assumed_pnl") or 0.0) for p in positions)


def manage_leg(S, i: int, pos: dict, policy: EP.ExitPolicy, back: Optional[float], state: dict, manager=None):
    """The native exit block for one leg at one tick. ``manager`` replaces manage_position for a candidate."""
    now, spot = S.now[i], S.spot[i]
    quote = S.quote(i, pos["symbol"])
    if pos["exit_pending"]:
        return EP._try_exit(pos, quote, pos["lots_open"], pos["exit_pending"], now)
    if quote is not None and quote.fresh(now) and quote.bid is not None:
        structure = back is not None and EP.failed_break(state, pos["opt_type"], spot, back)
        action = (manager or EP.manage_position)(pos, policy, quote.bid, now, structure_broken=structure)
        return EP._try_exit(pos, quote, *action, now) if action else None
    if S.clock[i] >= policy.flat_at:
        return EP._try_exit(pos, None, pos["lots_open"], "FLAT_TIME", now)
    return None


def settle(S, positions: list[dict]) -> None:
    """The native reconcile's value for whatever is still open after the session."""
    if S.partial:
        import sept
        sept.settle_partial(S, positions)
        return
    spot = S.settlement_spot()
    for pos in positions:
        if pos["status"] != "OPEN":
            continue
        qty = pos["lots_open"] * pos["lot_size"]
        if spot is None:
            pos["status"] = "UNRESOLVED"
            value = -(pos["entry_price"] * qty + pos["lots_open"] * EP.order_fee(EP._position_schedule(pos)))
        else:
            intrinsic = max(0.0, spot - pos["strike"]) if pos["opt_type"] == "CE" else max(0.0, pos["strike"] - spot)
            pos["status"] = "SETTLED_ASSUMED"
            value = (intrinsic * (1 - EP.EXERCISE_STT_PCT) - pos["entry_price"]) * qty
        pos["assumed_pnl"] = round(value, 2)


def _open(S, i: int, play: str, contract, price: float, lots: int, policy: Optional[EP.ExitPolicy] = None) -> dict:
    """The engine's entry. ``_new_position`` reads the first stop from POLICIES by play name, so a candidate's own
    hard stop has to be written here, by the same formula, or the candidate silently has no stop."""
    pos = EP._new_position(S.day, S.underlying, play, S.exchange, contract, price, lots, S.now[i], S.schedule)
    if policy is not None:
        pos["stop"] = round(price * (1 - policy.hard_stop), 2) if policy.hard_stop else 0.0
    return pos


# ---------------------------------------------------------------------------
# the three native plays
# ---------------------------------------------------------------------------

def run_a(S, policy: Optional[EP.ExitPolicy] = None, back: Optional[float] = EP.FAIL_BACK_WIDTH,
          max_trades: int = EP.A_MAX_TRADES, signal: SignalGene = NATIVE_SIGNAL, play: str = "A",
          budget: float = 2500.0) -> list[dict]:
    """A: the ATM option on the break, or one strike OTM when one ATM lot doesn't fit."""
    policy = policy or EP.POLICIES["A"]
    state, signals = signal_stream(S, signal)
    if not signals:
        return []
    fire = {i: d for i, d in signals}
    positions: list[dict] = []
    opened = 0
    for i in range(signals[0][0], S.n):
        live = [p for p in positions if p["status"] == "OPEN"]
        if live:
            for pos in live:
                manage_leg(S, i, pos, policy, back, state)
        elif opened >= max_trades:
            break
        direction = fire.get(i)
        if direction is None:
            continue
        if opened >= max_trades or any(p["status"] == "OPEN" for p in positions):
            continue
        remaining = budget + min(0.0, _realized(positions))
        if remaining <= 0:
            continue
        spot = S.spot[i]
        kind = "CE" if direction == "UP" else "PE"
        atm = S.atm(spot)
        step = S.step if kind == "CE" else -S.step
        chain = S.quoted_chain(i)
        now = S.now[i]
        for strike in (float(atm), float(atm + step)):
            candidate = chain.get((strike, kind))
            if EP._quote_refusal(candidate, now, EP.A_MAX_SPREAD):
                continue
            contract, quote = candidate
            lots, prices = EP.affordable_fill([(quote, contract.lot_size)], remaining, EP.A_MAX_LOTS, S.schedule)
            if not lots:
                continue
            positions.append(_open(S, i, play, contract, prices[0], lots, policy))
            opened += 1
            break
    settle(S, positions)
    return positions


def run_b(S, budget: float = 2500.0, target: float = EP.PAIR_TARGET, flat_at: time = EP.FINAL_FLAT,
          play: str = "B") -> list[dict]:
    """B: the late strangle, sold as one trade at the pair target, else held into the auction."""
    policy = EP.POLICIES["B"]
    if flat_at != EP.FINAL_FLAT:
        from dataclasses import replace
        policy = replace(policy, flat_at=flat_at)
    state: dict = {"box": None}
    pair: list[dict] = []
    for i in range(S.n):
        clock_now, now = S.clock[i], S.now[i]
        if clock_now < EP.B_ENTRY_START:
            continue
        if pair:
            live = [p for p in pair if p["status"] == "OPEN"]
            if not live:
                break
            quotes = {}
            for leg in pair:
                q = S.quote(i, leg["symbol"])
                if q is not None:
                    quotes[leg["token"]] = q
            if clock_now < EP.FINAL_FLAT and len(pair) == 2 and all(not leg["exit_pending"] and leg["status"] == "OPEN" for leg in pair):
                value = EP.liquidation_net(pair, quotes, now)
                paid = sum(leg["entry_price"] * leg["lots"] * leg["lot_size"] for leg in pair)
                if value is not None and value >= target * paid:
                    for leg in pair:
                        leg["exit_pending"] = "PAIR_TARGET"
            for pos in live:
                manage_leg(S, i, pos, policy, None, state)
            continue
        if not EP.B_ENTRY_START <= clock_now < EP.B_ENTRY_END:
            if clock_now >= EP.B_ENTRY_END:
                break
            continue
        spot = S.spot[i]
        if spot is None:
            continue
        chain = S.quoted_chain(i)
        legs = [chain.get((float(math.ceil(spot / S.step) * S.step), "CE")),
                chain.get((float(math.floor(spot / S.step) * S.step), "PE"))]
        reason = next((r for r in (EP._quote_refusal(leg, now, EP.BC_MAX_SPREAD) for leg in legs) if r), None)
        if reason:
            continue
        lots, prices = EP.affordable_fill([(q, c.lot_size) for c, q in legs], budget, EP.B_MAX_LOTS, S.schedule)
        if not lots:
            continue
        pair = [_open(S, i, play, contract, price, lots) for (contract, _), price in zip(legs, prices)]
    settle(S, pair)
    return pair


# ---------------------------------------------------------------------------
# the lottery ticket: C, CE01 and every candidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ticket:
    """A lottery ticket's rules. The defaults are expiry-v3's C; E01 is ``Ticket(stop=0.30)``."""
    stop: Optional[float] = None              # planned stop, share of entry premium lost
    back: Optional[float] = EP.FAIL_BACK_WIDTH  # the failed-break line, share of the box inside its edge
    bank_at: Optional[float] = 2.0            # gain on the bid that banks
    bank: str = "half"                        # half | recover (just enough lots to take the ticket's cost back)
    bank_floor: Optional[float] = None        # once banked, the runner's stop as a multiple of entry
    trails: tuple = ((4.0, 0.60),)            # (peak gain reached, share of peak kept)
    time_stop: Optional[tuple] = None         # (seconds, peak gain still not reached): sell an idle ticket
    flat_at: time = EP.FINAL_FLAT
    tickets: int = 1                          # a later confirmed break may buy again, from what the day has left
    same_direction: bool = False              # the later ticket only in the first ticket's direction
    prove: Optional[tuple] = None             # (gain, minutes): buy only after the ticket itself has risen this much
    band_hi: float = 1.0                      # multiple of the band's upper edge
    band_lo: float = 1.0                      # multiple of the band's lower edge
    budget: float = 1.0                       # share of the play's ceiling this ticket may spend
    signal: SignalGene = NATIVE_SIGNAL
    late: Optional[tuple] = None              # from this time, keep this share of a profitable peak
    own_ratio: Optional[float] = None         # the ticket's ask now, over its ask LOOKBACK ago, must be at least this
    straddle_ratio: Optional[float] = None    # the ATM straddle now, over LOOKBACK ago, must be at least this
    pilot: Optional[tuple] = None             # (share, gain, minutes): buy this share at the break, the rest once
                                              # the ticket's own ask has risen by ``gain``, within ``minutes``
    box_max_bp: Optional[float] = None        # no ticket when the box is wider than this, in basis points of its top
    delay: int = 0                            # stress: the entry happens this many ticks after the break

    @property
    def policy(self) -> EP.ExitPolicy:
        return EP.ExitPolicy(hard_stop=self.stop, bank_at=self.bank_at, bank_stop=self.bank_floor, trails=self.trails,
                             late=self.late, time_stop=self.time_stop, flat_at=self.flat_at)


C_NATIVE = Ticket()
E01 = Ticket(stop=EP.E01_PREMIUM_STOP)
LOOKBACK_SEC = 600.0


def tick_before(S, i: int, seconds: float = LOOKBACK_SEC) -> Optional[int]:
    """The last tick at least ``seconds`` before tick ``i``, or None if the record doesn't reach back that far."""
    target = S.now[i] - timedelta(seconds=seconds)
    if S.now[0] > target:
        return None
    lo, hi = 0, i
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if S.now[mid] <= target:
            lo = mid
        else:
            hi = mid - 1
    return lo


def own_ratio(S, i: int, symbol: str) -> Optional[float]:
    """The ticket's ask now over its ask ten minutes ago. None when either isn't known: no reading, no verdict."""
    k = tick_before(S, i)
    if k is None:
        return None
    a, b = S.quote(i, symbol), S.quote(k, symbol)
    if a is None or b is None or a.ask is None or b.ask is None:
        return None
    return a.ask / b.ask


def straddle_mid(S, i: int) -> Optional[float]:
    """The ATM straddle's mid at tick ``i`` on the engine's own context rule, or None without a fresh two-sided pair."""
    spot = S.spot[i]
    if spot is None:
        return None
    atm = float(round(spot / S.step) * S.step)
    chain = S.contracts_near(i)
    total = 0.0
    for kind in ("CE", "PE"):
        contract = chain.get((atm, kind))
        q = S.quote(i, contract.tradingsymbol) if contract is not None else None
        if q is None or not q.fresh(S.now[i]) or not q.spread_ok(1.0):
            return None
        total += (q.bid + q.ask) / 2.0
    return total


def straddle_ratio(S, i: int) -> Optional[float]:
    k = tick_before(S, i)
    if k is None:
        return None
    a, b = straddle_mid(S, i), straddle_mid(S, k)
    return a / b if a and b else None


def recover_lots(pos: dict, bid: float) -> int:
    """The fewest whole lots whose sale at ``bid`` takes back the ticket's whole cost, leaving at least one to run."""
    schedule = EP._position_schedule(pos)
    lots, lot_size = pos["lots_open"], pos["lot_size"]
    paid = pos["entry_price"] * pos["lots"] * lot_size + EP.buy_charges(pos["entry_price"], pos["lots"] * lot_size, schedule)
    fee = EP.order_fee(schedule)
    for take in range(1, lots):
        qty = take * lot_size
        # Every lot may later sell in its own order; a free roll must pay for those too.
        if bid * qty - EP.sell_charges(bid, qty, schedule) - (lots - take) * fee >= paid:
            return take
    return lots // 2


def _bank_manager(ticket: Ticket):
    """manage_position with the banked quantity replaced. Native when the ticket banks half."""
    if ticket.bank == "half":
        return None

    def manage(pos, policy, bid, now, structure_broken=False):
        was_banked = pos["banked"]
        action = EP.manage_position(pos, policy, bid, now, structure_broken=structure_broken)
        if not was_banked and pos["banked"] and action is not None and action[1] == "BANK_HALF":
            take = recover_lots(pos, bid)
            pos["bank_pending"] = take
            return take, "BANK_HALF"
        if not was_banked and pos["banked"] and action is None and pos["bank_pending"]:
            pos["bank_pending"] = 0
        return action
    return manage


def _pick(S, i: int, direction: str, ticket: Ticket):
    """The engine's strike pick, with the band scaled when a gene asks."""
    if ticket.band_hi == 1.0 and ticket.band_lo == 1.0:
        return EP.pick_lottery_strike(S.quoted_chain(i), direction, S.spot[i], S.now[i])
    saved = EP.C_PREMIUM_BAND
    try:
        EP.C_PREMIUM_BAND = (saved[0] * ticket.band_lo, saved[1] * ticket.band_hi)
        return EP.pick_lottery_strike(S.quoted_chain(i), direction, S.spot[i], S.now[i])
    finally:
        EP.C_PREMIUM_BAND = saved


def run_c(S, ticket: Ticket = C_NATIVE, play: str = "C", budget: float = 2500.0) -> list[dict]:
    """The lottery ticket under ``ticket``'s rules."""
    state, signals = signal_stream(S, ticket.signal)
    if not signals:
        return []
    fire = {i + ticket.delay: d for i, d in signals if i + ticket.delay < S.n and S.spot[i + ticket.delay] is not None}
    box = state.get("box")
    if ticket.box_max_bp is not None and box and (box["hi"] - box["lo"]) / box["hi"] * 1e4 > ticket.box_max_bp:
        return []
    policy, manager = ticket.policy, _bank_manager(ticket)
    positions: list[dict] = []
    waiting = None
    first_direction = None
    add = None        # a scaled-in ticket's second part: (symbol, ask at the break, until, lots, budget, kind)
    bought = 0        # tickets bought; a scaled-in ticket's two parts are one ticket
    for i in range(signals[0][0], S.n):
        live = [p for p in positions if p["status"] == "OPEN"]
        for pos in live:
            manage_leg(S, i, pos, policy, ticket.back, state, manager)
        spent = bought
        if add is not None:
            symbol, ask0, until, lots_left, room, kind = add
            now, spot = S.now[i], S.spot[i]
            alive = any(p["status"] == "OPEN" and p["symbol"] == symbol and not p["exit_pending"] for p in positions)
            if S.clock[i] >= until or not alive or (ticket.back is not None and EP.failed_break(state, kind, spot, ticket.back)):
                add = None
            else:
                quote = S.quote(i, symbol)
                if quote is not None and quote.fresh(now) and quote.ask is not None and quote.spread_ok(EP.BC_MAX_SPREAD) \
                        and quote.ask >= ask0 * (1 + ticket.pilot[1]):
                    contract = S.contract(symbol)
                    lots, prices = EP.affordable_fill([(quote, contract.lot_size)], room, lots_left, S.schedule)
                    if lots:
                        positions.append(_open(S, i, play, contract, prices[0], lots, policy))
                    add = None
        if not live and spent >= ticket.tickets and waiting is None and add is None:
            break
        if waiting is not None:
            # A ticket chosen at the break waits to prove itself. It never buys a break that has already failed.
            strike, kind, symbol, ask0, until, direction = waiting
            now, spot = S.now[i], S.spot[i]
            if S.clock[i] >= until or EP.failed_break(state, kind, spot, ticket.back if ticket.back is not None else EP.FAIL_BACK_WIDTH):
                waiting = None
            else:
                quote = S.quote(i, symbol)
                if quote is not None and quote.fresh(now) and quote.ask is not None and quote.spread_ok(EP.BC_MAX_SPREAD) \
                        and quote.ask >= ask0 * (1 + ticket.prove[0]):
                    remaining = budget * ticket.budget + min(0.0, _realized(positions))
                    if remaining > 0:
                        lots, prices = EP.affordable_fill([(quote, S.contract(symbol).lot_size)], remaining, EP.C_MAX_LOTS, S.schedule)
                        if lots:
                            positions.append(_open(S, i, play, S.contract(symbol), prices[0], lots, policy))
                            bought += 1
                            waiting = None
        direction = fire.get(i)
        if direction is None or live or waiting is not None or spent >= ticket.tickets:
            continue
        if spent and ticket.same_direction and first_direction != direction:
            continue
        if S.clock[i] >= ticket.signal.last_entry:
            continue
        remaining = budget * ticket.budget + min(0.0, _realized(positions))
        if remaining <= 0:
            continue
        if ticket.straddle_ratio is not None:
            ratio = straddle_ratio(S, i)
            if ratio is not None and ratio < ticket.straddle_ratio:
                continue
        strike = _pick(S, i, direction, ticket)
        if strike is None:
            continue
        kind = "CE" if direction == "UP" else "PE"
        contract, quote = S.quoted_chain(i)[(strike, kind)]
        if ticket.own_ratio is not None:
            ratio = own_ratio(S, i, contract.tradingsymbol)
            if ratio is not None and ratio < ticket.own_ratio:
                continue
        if ticket.prove is not None:
            waiting = (strike, kind, contract.tradingsymbol, quote.ask,
                       (S.now[i] + timedelta(minutes=ticket.prove[1])).time(), direction)
            first_direction = first_direction or direction
            continue
        lots, prices = EP.affordable_fill([(quote, contract.lot_size)], remaining, EP.C_MAX_LOTS, S.schedule)
        if lots and ticket.pilot is not None and lots >= 2:
            # Scale in: part now, the rest only if the ticket proves itself. The whole ticket stays inside what
            # one undivided ticket could have spent, so the day's ceiling is the same.
            first = max(1, int(lots * ticket.pilot[0]))
            filled, part = EP.affordable_fill([(quote, contract.lot_size)], remaining, first, S.schedule)
            if filled:
                pos = _open(S, i, play, contract, part[0], filled, policy)
                positions.append(pos)
                bought += 1
                first_direction = first_direction or direction
                add = (contract.tradingsymbol, quote.ask, (S.now[i] + timedelta(minutes=ticket.pilot[2])).time(),
                       lots - filled, remaining - pos["max_loss"], kind)
        elif lots:
            positions.append(_open(S, i, play, contract, prices[0], lots, policy))
            bought += 1
            first_direction = first_direction or direction
    settle(S, positions)
    return positions


def net(positions: list[dict]) -> float:
    return round(sum(p["net_pnl"] + (p.get("assumed_pnl") or 0.0) for p in positions), 2)
