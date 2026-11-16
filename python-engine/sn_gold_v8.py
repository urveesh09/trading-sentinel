"""[SN Gold V8 shadow 2026-11-16] The real-money Gold V8's orders, recorded beside SN Gold v5's paper book. NEVER places an
order: there is no broker call in this module.

Owner, Nov 16: "Gold V8 ... should be something that we are focusing to develop in real life". Research:
docs/research/fno/2026-11-16-sn316/GOLD_V8.md (V8 = Gold v5's rules, executed for real money). This is gate 3 of that
document: for every paper action, the exact order V8 would send, so that the tick recorder's packets can later show
whether it would have filled, at what price, and how far from the paper fill.

The order contract (GOLD_V8.md section 2):
  entry    BUY LIMIT at the ask + 2 ticks, valid 3 s; the cash actually paid (price x quantity + buy-side charges) must
           fit the wallet; a stop-loss order (SL) for the whole position at the day-stop trigger, limit 5% below it;
  scale-in BUY LIMIT at the ask + 2 ticks; cash paid for the open lots + the new lots + charges must fit the wallet (SN311's
           G1 rule), lots reduced to what fits; the stop order is replaced for the whole position first;
  exit     SELL LIMIT at the bid - 2 ticks, retried each second for 10 s, then MARKET; the 15:15 failsafe and a day-stop exit
           are MARKET.
Off: SN_GOLD_V8_SHADOW_ENABLED=false (default). Every call is guarded by the caller: nothing here can change a paper step.
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

_DDL = """CREATE TABLE IF NOT EXISTS sn_gold_v8_intents (
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
  note TEXT,
  UNIQUE (position_id, kind, at)
)"""


def enabled() -> bool:
    return bool(getattr(settings, "SN_GOLD_V8_SHADOW_ENABLED", False))


def ceil_tick(x: float) -> float:
    return round(math.ceil(x / TICK - 1e-9) * TICK, 2)


def floor_tick(x: float) -> float:
    return round(max(TICK, math.floor(x / TICK + 1e-9) * TICK), 2)


def buy_fees(price: float, qty: int) -> float:
    return float(calc_fno_costs(price, 0.0, qty))


def entry_order(ask: float, lots: int, lot_size: int, wallet: float, stop: float) -> dict:
    """V8's entry for the paper position: lots reduced until the cash actually paid fits the wallet."""
    price = ceil_tick(ask + LIMIT_TICKS * TICK)
    n = lots
    while n > 1 and price * n * lot_size + buy_fees(price, n * lot_size) > wallet:
        n -= 1
    qty = n * lot_size
    cash = price * qty + buy_fees(price, qty)
    return {"side": "BUY", "order_type": "LIMIT", "limit_price": price, "qty": qty, "lots": n, "cash": round(cash, 2),
            "fits": cash <= wallet, "stop_trigger": round(stop, 2), "stop_limit": floor_tick(stop * (1 - STOP_LIMIT_SHARE)),
            "note": "" if n == lots else f"lots {lots}->{n} to fit the wallet's cash"}


def add_order(pieces: list, ask: float, n_new: int, lot_size: int, wallet: float, stop: float) -> dict:
    """V8's scale-in: SN311's G1 rule, the cash paid for the open lots plus the new lots fits the wallet."""
    price = ceil_tick(ask + LIMIT_TICKS * TICK)
    paid = sum(e * n * lot_size + buy_fees(e, n * lot_size) for e, n in pieces)
    n = n_new
    while n > 0 and paid + price * n * lot_size + buy_fees(price, n * lot_size) > wallet:
        n -= 1
    qty = n * lot_size
    cash = paid + (price * qty + buy_fees(price, qty) if n else 0.0)
    return {"side": "BUY", "order_type": "LIMIT" if n else "NONE", "limit_price": price, "qty": qty, "lots": n, "cash": round(cash, 2),
            "fits": n > 0, "stop_trigger": round(stop, 2), "stop_limit": floor_tick(stop * (1 - STOP_LIMIT_SHARE)),
            "note": "" if n == n_new else f"add {n_new}->{n} lots to fit the wallet's cash"}


def exit_order(bid: float, qty: int, reason: str) -> dict:
    market = reason in ("day_loss_stop", "failsafe_1515")
    return {"side": "SELL", "order_type": "MARKET" if market else "LIMIT_THEN_MARKET",
            "limit_price": None if market else floor_tick(bid - LIMIT_TICKS * TICK), "qty": qty, "lots": None, "cash": None,
            "fits": True, "stop_trigger": None, "stop_limit": None, "note": reason}


async def record(db_path: str, *, kind: str, position_id: int, now: datetime, symbol: str, token: int, order: dict,
                 ref_bid: Optional[float], ref_ask: Optional[float], wallet: Optional[float], paper_price: Optional[float]) -> None:
    if not enabled():
        return
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.execute(
            "INSERT OR IGNORE INTO sn_gold_v8_intents(session_date,position_id,kind,at,tradingsymbol,token,side,qty,order_type,limit_price,"
            "stop_trigger,stop_limit,ref_bid,ref_ask,cash,wallet,fits,paper_price,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now.date().isoformat(), int(position_id), kind, now.isoformat(), symbol, int(token), order["side"], int(order["qty"]),
             order["order_type"], order["limit_price"], order["stop_trigger"], order["stop_limit"], ref_bid, ref_ask, order["cash"],
             wallet, int(bool(order["fits"])), paper_price, json.dumps(order.get("note") or "")))
        await db.commit()
