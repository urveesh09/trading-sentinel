"""[SN Gold V8 shadow 2026-11-16, + SN337 own inventory] The real-money Gold V8's orders and holdings, kept beside SN Gold
v5's paper book. NEVER places an order: there is no broker call in this module.

Owner, Nov 16: "Gold V8 ... should be something that we are focusing to develop in real life". Research:
docs/research/fno/2026-11-16-sn316/GOLD_V8.md (V8 = Gold v5's rules, executed for real money), gate 3: for every paper
action, the exact order V8 would send, so the tick recorder's packets can later show whether it would have filled.

SN337 (auditor, Nov 16): the shadow keeps V8's OWN inventory (table sn_gold_v8_positions). V8 can hold fewer lots than paper
(its entry must fit the wallet in cash actually paid), so every later add is computed on V8's holdings and cash, and every
exit sells exactly what V8 holds; a running V8 net sits beside the paper net. V8 follows Gold's signals and exit timing; its
fills are assumed at its limit prices (the fill-realism check against packets is SN346).

The order contract (GOLD_V8.md section 2):
  entry    BUY LIMIT at the ask + 2 ticks, valid 3 s; the cash actually paid (price x quantity + buy-side charges) must
           fit the wallet (lots reduced to what fits); a stop-loss order (SL) for V8's position at the day-stop trigger,
           limit 5% below it;
  scale-in on Gold's 1-ATR trigger: Gold's rule on V8's own holdings (added = max(1, wallet // (ask x lot) - held) if
           (held + added) x ask x lot <= wallet), then reduced until the cash paid for V8's lots + the new lots fits
           the wallet (SN311's G1), and only if the whole V8 position's stop still sits below the bid;
  exit     SELL V8's whole holding: LIMIT at the bid - 2 ticks, retried each second for 10 s, then MARKET; the 15:15
           failsafe and a day-stop exit are MARKET.
Off: SN_GOLD_V8_SHADOW_ENABLED=false (default). The callers guard every call: nothing here can change a paper step.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Optional

import aiosqlite

from config import settings
from fno_costs import calc_fno_costs

TICK = 0.05
LIMIT_TICKS = 2
STOP_LIMIT_SHARE = 0.05

_DDL = (
    """CREATE TABLE IF NOT EXISTS sn_gold_v8_intents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_date TEXT NOT NULL,
  position_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  at TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  token INTEGER NOT NULL,
  side TEXT NOT NULL,
  qty INTEGER NOT NULL,
  order_type TEXT NOT NULL,
  limit_price REAL,
  stop_trigger REAL,
  stop_limit REAL,
  ref_bid REAL,
  ref_ask REAL,
  cash REAL,
  wallet REAL,
  fits INTEGER NOT NULL,
  paper_price REAL,
  paper_qty INTEGER,
  note TEXT,
  UNIQUE (position_id, kind, at)
)""",
    """CREATE TABLE IF NOT EXISTS sn_gold_v8_positions (
  position_id INTEGER PRIMARY KEY,
  session_date TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  token INTEGER NOT NULL,
  lot_size INTEGER NOT NULL,
  wallet REAL NOT NULL,
  pieces TEXT NOT NULL,
  status TEXT NOT NULL,
  exit_price REAL,
  net REAL,
  paper_net REAL,
  updated_at TEXT NOT NULL
)""",
)


def enabled() -> bool:
    return bool(getattr(settings, "SN_GOLD_V8_SHADOW_ENABLED", False))


def ceil_tick(x: float) -> float:
    return round(math.ceil(x / TICK - 1e-9) * TICK, 2)


def floor_tick(x: float) -> float:
    return round(max(TICK, math.floor(x / TICK + 1e-9) * TICK), 2)


def buy_fees(price: float, qty: int) -> float:
    return float(calc_fno_costs(price, 0.0, qty))


def paid(pieces: list, lot_size: int) -> float:
    return sum(e * n * lot_size + buy_fees(e, n * lot_size) for e, n in pieces)


def held(pieces: list) -> int:
    return sum(n for _e, n in pieces)


def stop_for(pieces: list, lot_size: int, room: float) -> float:
    q = held(pieces) * lot_size
    avg = sum(e * n for e, n in pieces) * lot_size / q
    fees = sum(calc_fno_costs(e, e, n * lot_size) for e, n in pieces)
    return ceil_tick(avg - (room - fees) / q)


def entry_order(ask: float, lots: int, lot_size: int, wallet: float, stop: float) -> dict:
    """V8's entry for the paper position: lots reduced until the cash actually paid fits the wallet (0 = no entry)."""
    price = ceil_tick(ask + LIMIT_TICKS * TICK)
    n = lots
    while n > 0 and price * n * lot_size + buy_fees(price, n * lot_size) > wallet:
        n -= 1
    qty = n * lot_size
    cash = price * qty + (buy_fees(price, qty) if n else 0.0)
    note = "" if n == lots else (f"lots {lots}->{n} to fit the wallet's cash" if n else "one lot does not fit the wallet's cash")
    return {"side": "BUY", "order_type": "LIMIT" if n else "NONE", "limit_price": price, "qty": qty, "lots": n, "cash": round(cash, 2),
            "fits": n > 0, "stop_trigger": round(stop, 2), "stop_limit": floor_tick(stop * (1 - STOP_LIMIT_SHARE)), "note": note}


def add_order(pieces: list, ask: float, lot_size: int, wallet: float, bid: float, room: float) -> dict:
    """V8's scale-in on its own holdings: Gold's rule, then the cash fit (SN311's G1), then the whole-position stop."""
    price = ceil_tick(ask + LIMIT_TICKS * TICK)
    have = held(pieces)
    n = max(1, int(wallet // (ask * lot_size)) - have)
    why = ""
    if (have + n) * ask * lot_size > wallet:
        n, why = 0, "Gold's add rule: no room on V8's holdings"
    cash0 = paid(pieces, lot_size)
    while n > 0 and cash0 + price * n * lot_size + buy_fees(price, n * lot_size) > wallet:
        n -= 1
        why = "reduced to fit the wallet's cash"
    stop = None
    if n > 0:
        stop = stop_for(pieces + [[price, n]], lot_size, room)
        if stop >= bid:
            n, why, stop = 0, "the whole position's stop would not sit below the bid", None
    qty = n * lot_size
    cash = cash0 + (price * qty + buy_fees(price, qty) if n else 0.0)
    return {"side": "BUY", "order_type": "LIMIT" if n else "NONE", "limit_price": price, "qty": qty, "lots": n, "cash": round(cash, 2),
            "fits": n > 0, "stop_trigger": stop, "stop_limit": floor_tick(stop * (1 - STOP_LIMIT_SHARE)) if stop else None, "note": why}


def exit_order(bid: float, qty: int, reason: str) -> dict:
    market = reason in ("day_loss_stop", "failsafe_1515")
    return {"side": "SELL", "order_type": "MARKET" if market else "LIMIT_THEN_MARKET",
            "limit_price": None if market else floor_tick(bid - LIMIT_TICKS * TICK), "qty": qty, "lots": None, "cash": None,
            "fits": qty > 0, "stop_trigger": None, "stop_limit": None, "note": reason}


def net_of(pieces: list, exit_px: float, lot_size: int) -> float:
    return sum((exit_px - e) * n * lot_size - calc_fno_costs(e, exit_px, n * lot_size) for e, n in pieces)


# ---- the shadow book -------------------------------------------------------------------------------------------------
async def _init(db) -> None:
    for ddl in _DDL:
        await db.execute(ddl)


async def _intent(db, kind, pid, now, symbol, token, order, ref_bid, ref_ask, wallet, paper_price, paper_qty) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO sn_gold_v8_intents(session_date,position_id,kind,at,tradingsymbol,token,side,qty,order_type,limit_price,"
        "stop_trigger,stop_limit,ref_bid,ref_ask,cash,wallet,fits,paper_price,paper_qty,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now.date().isoformat(), int(pid), kind, now.isoformat(), symbol, int(token), order["side"], int(order["qty"]), order["order_type"],
         order["limit_price"], order["stop_trigger"], order["stop_limit"], ref_bid, ref_ask, order["cash"], wallet, int(bool(order["fits"])),
         paper_price, paper_qty, json.dumps(order.get("note") or "")))


async def on_entry(db_path: str, *, position_id: int, now: datetime, symbol: str, token: int, ask: float, bid: Optional[float],
                   lots: int, lot_size: int, wallet: float, stop: float) -> dict:
    order = entry_order(ask, lots, lot_size, wallet, stop)
    async with aiosqlite.connect(db_path) as db:
        await _init(db)
        await _intent(db, "ENTRY", position_id, now, symbol, token, order, bid, ask, wallet, ask, lots * lot_size)
        await db.execute("INSERT OR IGNORE INTO sn_gold_v8_positions(position_id,session_date,tradingsymbol,token,lot_size,wallet,pieces,status,updated_at)"
                         " VALUES(?,?,?,?,?,?,?,?,?)",
                         (int(position_id), now.date().isoformat(), symbol, int(token), int(lot_size), float(wallet),
                          json.dumps([[order["limit_price"], order["lots"]]] if order["lots"] else []),
                          "OPEN" if order["lots"] else "NOT_ENTERED", now.isoformat()))
        await db.commit()
    return order


async def _position(db, pid):
    db.row_factory = aiosqlite.Row
    return await (await db.execute("SELECT * FROM sn_gold_v8_positions WHERE position_id=?", (int(pid),))).fetchone()


async def on_add_trigger(db_path: str, *, position_id: int, now: datetime, ask: float, bid: float, room: float,
                         paper_added_lots: int) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        await _init(db)
        p = await _position(db, position_id)
        if p is None or p["status"] != "OPEN":
            return None
        pieces = json.loads(p["pieces"])
        order = add_order(pieces, ask, int(p["lot_size"]), float(p["wallet"]), bid, room)
        await _intent(db, "ADD", position_id, now, p["tradingsymbol"], p["token"], order, bid, ask, float(p["wallet"]), ask,
                      paper_added_lots * int(p["lot_size"]))
        if order["lots"]:
            pieces.append([order["limit_price"], order["lots"]])
            await db.execute("UPDATE sn_gold_v8_positions SET pieces=?, updated_at=? WHERE position_id=?",
                             (json.dumps(pieces), now.isoformat(), int(position_id)))
        await db.commit()
    return order


async def on_exit(db_path: str, *, position_id: int, now: datetime, bid: float, ask: Optional[float], reason: str,
                  paper_qty: int, paper_net: float) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        await _init(db)
        p = await _position(db, position_id)
        if p is None or p["status"] != "OPEN":
            return None
        pieces = json.loads(p["pieces"])
        lot_size = int(p["lot_size"])
        order = exit_order(bid, held(pieces) * lot_size, reason)
        px = order["limit_price"] if order["limit_price"] is not None else bid
        net = net_of(pieces, px, lot_size)
        await _intent(db, "EXIT", position_id, now, p["tradingsymbol"], p["token"], order, bid, ask, float(p["wallet"]), bid, paper_qty)
        await db.execute("UPDATE sn_gold_v8_positions SET status='CLOSED', exit_price=?, net=?, paper_net=?, updated_at=? WHERE position_id=?",
                         (px, round(net, 2), round(paper_net, 2), now.isoformat(), int(position_id)))
        await db.commit()
    return order
