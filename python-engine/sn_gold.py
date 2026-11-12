"""[SN Gold v5 2026-11-13] The owner's small-wallet F&O book, run on PAPER beside the main book. Never places an order.

Owner, Nov 13: "whatever configuration ... of the best Gold that we have, set it up to run tomorrow as an independent module".
Research: docs/research/fno/sn-gold/SN_GOLD_V5.json (frozen harness gold_v5.py, verify_gold_v5.py, tag sn-gold-v5).

What it does, in the research's words, on live quotes:
  * entries: N11's live paper record (fno_n11_paper, NIFTY). Each new record is offered here at the moment N11 records it,
    with the same chain snapshot. SN Gold also takes the signals of N11's sister book R0.85, which stands aside a little
    less: a signal waits only when yesterday's volatility is below 0.85 of usual AND N11's last 20 paper trades sum <= 0;
  * one position at a time; lots = floor(wallet / 15,000), halved (min 1) when N11's volatility reading is not up;
  * the strike: the deepest in-the-money strike (1 below Rs 17,500 of wallet per lot, 2 below Rs 20,000, else 3) where
    every lot fits the wallet, else N11's strike, else one strike further out of the money; bought at the snapshot ask;
  * day loss limit 20% of the wallet: a stop on the option at the price where the day would lose it;
  * scale-in once: when the NIFTY future has moved 1 x its 1-minute ATR in the trade's favour, buy as many lots as the
    wallet still carries, only if the whole position's stop still fits the day's room;
  * exits: with N11's paper lot (the same exit ladder the research replayed); a winner up >= 25% on its first fill at
    that moment is kept with a trail 3 x the 1-minute ATR behind the best future price, until 15:10;
  * the wallet: Rs 15,000 at the start; profits are banked, a losing day is "refilled" (the next day starts at the full
    wallet again and the loss is counted as a refill); after net profit equal to the wallet, the wallet grows 50%,
    at most 3 times (Rs 50,625);
  * money: real bid / ask and the shipped charges; the research's +Rs 205 per lot stress is kept beside it as net_stressed.
The callers guard every call: nothing here can stop an N11 or main-book step.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import aiosqlite
import structlog

import fno_n11
from config import settings
from fno_costs import calc_fno_costs

logger = structlog.get_logger()

SOURCE = "SN_GOLD_PAPER"
STEP = 50
TICK = 0.05
LOT_RUPEES = 15000.0
STRESS_PER_LOT = 205.0
FLAT_MIN = 15 * 60 + 10          # extended winners leave by 15:10
FAILSAFE_MIN = 15 * 60 + 15      # anything still open leaves here
DAY_CLOSE_FROM_MIN = 15 * 60 + 20

_DDL = (
    """CREATE TABLE IF NOT EXISTS sn_gold_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_date TEXT NOT NULL,
  n11_paper_id INTEGER NOT NULL UNIQUE,
  strategy TEXT,
  direction TEXT NOT NULL,
  tradingsymbol TEXT NOT NULL,
  token INTEGER NOT NULL,
  strike REAL NOT NULL,
  opt TEXT NOT NULL,
  lot_size INTEGER NOT NULL,
  wallet REAL NOT NULL,
  first_ask REAL NOT NULL,
  pieces TEXT NOT NULL,
  entry_time TEXT NOT NULL,
  entry_future REAL NOT NULL,
  atr1 REAL,
  stop_price REAL NOT NULL,
  scaled INTEGER NOT NULL DEFAULT 0,
  extended INTEGER NOT NULL DEFAULT 0,
  best_future REAL,
  status TEXT NOT NULL,
  exit_time TEXT,
  exit_bid REAL,
  exit_reason TEXT,
  net REAL,
  net_stressed REAL
)""",
    """CREATE TABLE IF NOT EXISTS sn_gold_days (
  session_date TEXT PRIMARY KEY,
  trades INTEGER NOT NULL,
  net REAL NOT NULL,
  net_stressed REAL NOT NULL,
  refill REAL NOT NULL,
  wallet_before REAL NOT NULL,
  wallet_after REAL NOT NULL,
  steps_after INTEGER NOT NULL,
  closed_at TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS sn_gold_wallet (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  wallet REAL NOT NULL,
  steps INTEGER NOT NULL,
  progress REAL NOT NULL,
  banked REAL NOT NULL,
  refilled REAL NOT NULL,
  started TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS sn_gold_bars (
  session_date TEXT NOT NULL,
  minute INTEGER NOT NULL,
  open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
  PRIMARY KEY (session_date, minute)
)""",
    """CREATE TABLE IF NOT EXISTS sn_gold_skips (
  n11_paper_id INTEGER PRIMARY KEY,
  session_date TEXT NOT NULL,
  reason TEXT NOT NULL,
  at TEXT NOT NULL
)""",
)


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        for ddl in _DDL:
            await db.execute(ddl)
        await db.commit()


# ---- pure rules (each one is the research harness's rule, docs/research/fno/sn-gold/gold_v5.py) ----------------------

def ceil_tick(x: float) -> float:
    return round(math.ceil(x / TICK - 1e-9) * TICK, 2)


def lots_for(wallet: float, vol_day: bool) -> int:
    full = max(1, int(wallet // LOT_RUPEES))
    return full if vol_day else max(1, full // 2)


def itm_depth(per_lot: float) -> int:
    lo, hi = float(settings.SN_GOLD_ITM_PER_LOT_1), float(settings.SN_GOLD_ITM_PER_LOT_2)
    return 1 if per_lot < lo else (2 if per_lot < hi else 3)


def pick_contract(quotes: dict, n11_strike: float, opt: str, lots: int, wallet: float, lot_size: int) -> Optional[tuple]:
    """(strike, quote, lots) from a chain snapshot's {(strike, opt): ContractQuote}: the deepest in-the-money strike where
    every lot fits, else N11's strike, else one strike further out of the money, which one lot must fit."""
    sign = 1 if opt == "CE" else -1
    usable = lambda q: q is not None and q.bid > 0 and q.ask > 0      # noqa: E731
    strike = float(n11_strike)
    for dep in range(itm_depth(wallet / max(1, lots)), 0, -1):
        k = float(n11_strike) - sign * dep * STEP
        q = quotes.get((k, opt))
        if usable(q) and q.ask * lot_size * lots <= wallet:
            strike = k
            break
    for attempt in range(2):
        q = quotes.get((strike, opt))
        if not usable(q):
            return None
        if q.ask * lot_size <= wallet:
            return strike, q, min(lots, max(1, int(wallet // (q.ask * lot_size))))
        if attempt:
            return None
        strike += sign * STEP


def day_stop(ask: float, qty: int, room: float) -> float:
    """The option price at which this position would use up the day's remaining loss room after its own charges."""
    return ceil_tick(ask - (room - calc_fno_costs(ask, ask, qty)) / qty)


def scale_in_stop(pieces: list, lot_size: int, room: float) -> float:
    q = sum(n for _e, n in pieces) * lot_size
    avg = sum(e * n for e, n in pieces) * lot_size / q
    fees = sum(calc_fno_costs(e, e, n * lot_size) for e, n in pieces)
    return ceil_tick(avg - (room - fees) / q)


def position_net(pieces: list, exit_px: float, lot_size: int) -> tuple:
    net = sum((exit_px - e) * n * lot_size - calc_fno_costs(e, exit_px, n * lot_size) for e, n in pieces)
    return net, net - STRESS_PER_LOT * sum(n for _e, n in pieces)


def grow(wallet: float, steps: int, progress: float, day_net: float) -> tuple:
    """The owner's wallet rule after a day: net profit since the last step >= the wallet -> the wallet grows 50%."""
    progress += day_net
    trigger = float(settings.SN_GOLD_STEP_TRIGGER)
    while progress >= trigger * wallet and steps < int(settings.SN_GOLD_MAX_STEPS):
        progress -= trigger * wallet
        wallet *= 1.5
        steps += 1
    return wallet, steps, progress


def atr_from_bars(bars: list) -> Optional[float]:
    """Wilder ATR(14) over 1-minute (open, high, low, close) bars, seeded as the research seeded it."""
    if len(bars) < 5:
        return None
    trs, prev = [], None
    for o, h, l, c in bars:
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    acc = max(sum(trs[:5]) / 5, 1.0)
    for tr in trs:
        acc += (tr - acc) / 14.0
    return acc


async def minute_atr(kite, now: datetime) -> Optional[float]:
    """The research's 1-minute ATR(14) from today's completed 1-minute candles of the NIFTY front future (Kite). None when
    they can't be read; the caller then falls back to bars sampled from the ticks this module saw."""
    if kite is None:
        return None
    try:
        from fno_instruments import get_fno_instruments
        fut = get_fno_instruments().front_future(now.date())
        if fut is None:
            return None
        frame = await asyncio.wait_for(kite.get_intraday_by_token(int(fut.token), now.strftime("%Y-%m-%d 09:15:00"),
                                                                  now.strftime("%Y-%m-%d %H:%M:%S"), interval="minute"), timeout=8.0)
    except Exception as exc:
        logger.warning("sn_gold_minute_candles_failed", err=str(exc))
        return None
    if frame is None or len(frame) == 0:
        return None
    try:
        stamps = frame.index if "datetime" not in frame.columns else frame["datetime"]
        bars = []
        for ts, o, h, l, c in zip(stamps, frame["open"], frame["high"], frame["low"], frame["close"]):
            ts = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
            if ts.date() == now.date() and ts.hour * 60 + ts.minute < now.hour * 60 + now.minute:     # completed minutes only
                bars.append((float(o), float(h), float(l), float(c)))
    except Exception as exc:
        logger.warning("sn_gold_minute_candles_unreadable", err=str(exc))
        return None
    return atr_from_bars(bars)


# ---- state ------------------------------------------------------------------------------------------------------------

_BARS: dict = {}          # (db_path, day) -> {minute: [o, h, l, c]}
_LAST_LOOK: dict = {}


async def wallet_state(db_path: str, now: datetime) -> dict:
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM sn_gold_wallet WHERE id=1")).fetchone()
        if row is None:
            await db.execute("INSERT OR IGNORE INTO sn_gold_wallet(id,wallet,steps,progress,banked,refilled,started) VALUES(1,?,?,?,?,?,?)",
                             (float(settings.SN_GOLD_START_WALLET), 0, 0.0, 0.0, 0.0, now.date().isoformat()))
            await db.commit()
            row = await (await db.execute("SELECT * FROM sn_gold_wallet WHERE id=1")).fetchone()
    return dict(row)


async def _realized_today(db: aiosqlite.Connection, day: str) -> float:
    row = await (await db.execute("SELECT COALESCE(SUM(net),0) FROM sn_gold_positions WHERE session_date=? AND status='CLOSED'", (day,))).fetchone()
    return float(row[0])


def _record_price(db_path: str, now: datetime, price: Optional[float]) -> None:
    if not price or price <= 0:
        return
    key = (db_path, now.date().isoformat())
    bars = _BARS.setdefault(key, {})
    m = now.hour * 60 + now.minute
    b = bars.get(m)
    if b is None:
        bars[m] = [price, price, price, price]
    else:
        b[1], b[2], b[3] = max(b[1], price), min(b[2], price), price


async def _bars(db_path: str, day: str) -> list:
    """Completed and current 1-minute bars of today's NIFTY future (memory first, the table after a restart)."""
    mem = _BARS.get((db_path, day), {})
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT minute, open, high, low, close FROM sn_gold_bars WHERE session_date=? ORDER BY minute", (day,))).fetchall()
    merged = {int(r[0]): [r[1], r[2], r[3], r[4]] for r in rows}
    merged.update(mem)
    return [tuple(merged[m]) for m in sorted(merged)]


async def _flush_bars(db_path: str, now: datetime) -> None:
    day = now.date().isoformat()
    mem = _BARS.get((db_path, day), {})
    current = now.hour * 60 + now.minute
    done = [(day, m, *b) for m, b in mem.items() if m < current]
    if done:
        async with aiosqlite.connect(db_path) as db:
            await db.executemany("INSERT OR REPLACE INTO sn_gold_bars(session_date,minute,open,high,low,close) VALUES(?,?,?,?,?,?)", done)
            await db.commit()
    for stale in [k for k in _BARS if k[0] == db_path and k[1] != day]:
        del _BARS[stale]


async def _skip(db_path: str, paper_id: int, day: str, reason: str, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO sn_gold_skips(n11_paper_id,session_date,reason,at) VALUES(?,?,?,?)", (paper_id, day, reason, now.isoformat()))
        await db.commit()
    logger.info("sn_gold_skip", paper_id=paper_id, reason=reason)


# ---- entry: offered by the orchestrator right after N11 records a paper signal ---------------------------------------

async def on_paper_signal(db_path: str, sig: Any, snap: Any, now: datetime, kite=None) -> Optional[int]:
    if not settings.SN_GOLD_ENABLED:
        return None
    await init_db(db_path)
    day = now.date().isoformat()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        paper = await (await db.execute("SELECT * FROM fno_n11_paper WHERE underlying='NIFTY' AND bar_ts=? AND source=?",
                                        (sig.bar_ts, fno_n11.PAPER_SOURCE))).fetchone()
        if paper is None or paper["status"] != "OPEN":
            return None
        if await (await db.execute("SELECT 1 FROM sn_gold_positions WHERE n11_paper_id=?", (paper["id"],))).fetchone():
            return None
        open_row = await (await db.execute("SELECT 1 FROM sn_gold_positions WHERE status='OPEN'")).fetchone()
        gate_row = await (await db.execute("SELECT atr_pct, usual, vol_up FROM fno_n11_gate WHERE session_date=?", (day,))).fetchone()
        realized = await _realized_today(db, day)
    if open_row:
        await _skip(db_path, paper["id"], day, "position_open", now)
        return None
    atr_pct = float(gate_row["atr_pct"]) if gate_row and gate_row["atr_pct"] is not None else None
    usual = float(gate_row["usual"]) if gate_row and gate_row["usual"] is not None else None
    nets = await fno_n11.paper_nets(db_path, now)
    if fno_n11.stand_aside(fno_n11.vol_up(atr_pct, usual, float(settings.SN_GOLD_STAND_RATIO)), nets, int(settings.FNO_N11_STAND_NEED)):
        await _skip(db_path, paper["id"], day, "stand_aside_0.85", now)
        return None
    w = await wallet_state(db_path, now)
    wallet = float(w["wallet"])
    loss = float(settings.SN_GOLD_DAY_LOSS_SHARE) * wallet
    room = loss + realized
    if room < 0.05 * loss:
        await _skip(db_path, paper["id"], day, "day_loss_limit_used", now)
        return None
    n11_quote = next((q for q in snap.quotes.values() if int(q.contract.token) == int(paper["token"])), None)
    if n11_quote is None:
        await _skip(db_path, paper["id"], day, "n11_contract_not_in_snapshot", now)
        return None
    opt = n11_quote.contract.instrument_type
    lot_size = int(snap.lot_size)
    vol_day = bool(gate_row["vol_up"]) if gate_row else False
    picked = pick_contract(snap.quotes, float(n11_quote.contract.strike), opt, lots_for(wallet, vol_day), wallet, lot_size)
    if picked is None:
        await _skip(db_path, paper["id"], day, "no_affordable_contract", now)
        return None
    strike, q, lots = picked
    ask = float(q.ask)
    stop = day_stop(ask, lots * lot_size, room)
    while lots > 1 and stop >= ask:
        lots -= 1
        stop = day_stop(ask, lots * lot_size, room)
    if stop >= ask:      # the day's remaining room can't carry even one lot's charges
        await _skip(db_path, paper["id"], day, "stop_does_not_fit_room", now)
        return None
    future = float(snap.forward)
    _record_price(db_path, now, future)
    atr1 = await minute_atr(kite, now) or atr_from_bars(await _bars(db_path, day))
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO sn_gold_positions(session_date,n11_paper_id,strategy,direction,tradingsymbol,token,strike,opt,lot_size,wallet,"
            "first_ask,pieces,entry_time,entry_future,atr1,stop_price,best_future,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'OPEN')",
            (day, paper["id"], paper["strategy"], paper["direction"], q.contract.tradingsymbol, int(q.contract.token), strike, opt, lot_size,
             wallet, ask, json.dumps([[ask, lots]]), now.isoformat(), future, atr1, max(stop, TICK), future))
        await db.commit()
        pid = cur.lastrowid if cur.rowcount == 1 else None
    if pid:
        logger.info("sn_gold_entry", id=pid, symbol=q.contract.tradingsymbol, lots=lots, ask=ask, stop=stop, wallet=wallet)
        _tell(f"🥇 SN Gold (paper): bought {lots} lot{'s' if lots > 1 else ''} of {q.contract.tradingsymbol} at Rs {ask:.2f} "
                    f"with N11's {paper['strategy']} signal. Wallet Rs {wallet:,.0f}; today's loss limit Rs {loss:,.0f}. Paper only.")
    return pid


# ---- management: every F&O management tick (it acts about once a minute) ---------------------------------------------

async def tick(kite, db_path: str, *, now: datetime, fut_prices: dict, read_quote: Callable) -> int:
    if not settings.SN_GOLD_ENABLED:
        return 0
    await init_db(db_path)
    future = fut_prices.get("NIFTY")
    _record_price(db_path, now, future)
    minute = now.hour * 60 + now.minute
    closed = 0
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM sn_gold_positions WHERE status='OPEN'")).fetchall()
    today = now.date().isoformat()
    stale = [r for r in rows if r["session_date"] != today]
    if stale:      # the engine was down at the close: no price to book
        async with aiosqlite.connect(db_path) as db:
            await db.executemany("UPDATE sn_gold_positions SET status='UNRESOLVED', exit_reason='engine_down_at_close' WHERE id=?", [(r["id"],) for r in stale])
            await db.commit()
        rows = [r for r in rows if r["session_date"] == today]
    n11_moved = False
    if rows:
        async with aiosqlite.connect(db_path) as db:
            ids = [int(r["n11_paper_id"]) for r in rows]
            got = await (await db.execute(f"SELECT COUNT(*) FROM fno_n11_paper WHERE status='OPEN' AND id IN ({','.join('?' * len(ids))})", ids)).fetchone()
            n11_moved = int(got[0]) < len(ids) and not all(int(r["extended"]) for r in rows)
    if rows and (minute >= FAILSAFE_MIN or n11_moved or now.timestamp() - _LAST_LOOK.get(db_path, 0.0) >= 55.0):
        _LAST_LOOK[db_path] = now.timestamp()
        await _flush_bars(db_path, now)
        closed = await _manage(kite, db_path, rows, now, future, read_quote)
    elif minute % 5 == 0:
        await _flush_bars(db_path, now)
    if minute >= DAY_CLOSE_FROM_MIN:
        await close_day(db_path, now)
    return closed


async def _manage(kite, db_path: str, rows: list, now: datetime, future: Optional[float], read_quote: Callable) -> int:
    tokens = sorted({int(r["token"]) for r in rows})
    quotes, _timing = await asyncio.wait_for(read_quote(kite, tokens), timeout=float(settings.FNO_EXIT_QUOTE_READ_MAX_SEC))
    day = now.date().isoformat()
    minute = now.hour * 60 + now.minute
    paper_open = {}
    async with aiosqlite.connect(db_path) as db:
        for r in rows:
            got = await (await db.execute("SELECT status FROM fno_n11_paper WHERE id=?", (r["n11_paper_id"],))).fetchone()
            paper_open[r["id"]] = bool(got) and got[0] == "OPEN"
    # the trail needs today's ATR only while a kept winner runs, or when one may be kept: read the candles only then
    needs_atr = any(int(r["extended"]) or not paper_open[r["id"]] for r in rows)
    atr_now = ((await minute_atr(kite, now)) or atr_from_bars(await _bars(db_path, day))) if needs_atr else None
    closed = 0
    for r in rows:
        raw = quotes.get(int(r["token"])) or {}
        depth = raw.get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
        ask_now = float(sells[0]["price"]) if sells and sells[0].get("price") else 0.0
        if bid <= 0:
            if minute >= FAILSAFE_MIN:
                bid = float(raw.get("last_price") or 0.0)
            if bid <= 0:
                continue
        pieces = json.loads(r["pieces"])
        d = 1 if r["direction"] == "LONG" else -1
        lot_size = int(r["lot_size"])
        stop = float(r["stop_price"])
        reason = None
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            paper = await (await db.execute("SELECT status, exit_reason FROM fno_n11_paper WHERE id=?", (r["n11_paper_id"],))).fetchone()
            realized = await _realized_today(db, day)
        best = float(r["best_future"] or r["entry_future"])
        scaled, extended = int(r["scaled"]), int(r["extended"])
        if bid <= stop:
            reason = "day_loss_stop"
        else:
            # the scale-in, once: the future 1 x the entry's 1-minute ATR in the trade's favour
            atr1 = r["atr1"]
            if not scaled and future and atr1 and (future - (float(r["entry_future"]) + d * float(settings.SN_GOLD_SCALE_ATR) * float(atr1))) * d >= 0:
                scaled = 1
                if ask_now > 0:
                    open_lots = sum(n for _e, n in pieces)
                    wallet = float(r["wallet"])
                    n_new = max(1, int(wallet // (ask_now * lot_size)) - open_lots)
                    if (open_lots + n_new) * ask_now * lot_size <= wallet:
                        room = float(settings.SN_GOLD_DAY_LOSS_SHARE) * wallet + realized
                        new_stop = scale_in_stop(pieces + [[ask_now, n_new]], lot_size, room)
                        if new_stop < bid:
                            pieces.append([ask_now, n_new])
                            stop = max(stop, new_stop)
                            logger.info("sn_gold_scale_in", id=r["id"], lots=n_new, ask=ask_now, stop=stop)
            if future:
                best = max(best, future) if d > 0 else min(best, future)
            if extended:
                trail = best - d * float(settings.SN_GOLD_EXTEND_ATR) * float(atr_now or r["atr1"] or 0.0)
                if (future is not None and (future - trail) * d <= 0) or minute >= FLAT_MIN:
                    reason = "extended_trail" if minute < FLAT_MIN else "extended_1510"
            elif paper is None or paper["status"] != "OPEN":
                if bid >= float(r["first_ask"]) * (1 + float(settings.SN_GOLD_EXTEND_AT)) and minute < FLAT_MIN and atr_now:
                    extended = 1
                else:
                    reason = "n11:" + str(paper["exit_reason"] if paper else "missing")
            if reason is None and minute >= FAILSAFE_MIN:
                reason = "failsafe_1515"
        async with aiosqlite.connect(db_path) as db:
            if reason:
                net, stressed = position_net(pieces, bid, lot_size)
                await db.execute("UPDATE sn_gold_positions SET status='CLOSED', exit_time=?, exit_bid=?, exit_reason=?, net=?, net_stressed=?, "
                                 "pieces=?, scaled=?, extended=?, best_future=? WHERE id=? AND status='OPEN'",
                                 (now.isoformat(), bid, reason, net, stressed, json.dumps(pieces), scaled, extended, best, r["id"]))
                closed += 1
            else:
                await db.execute("UPDATE sn_gold_positions SET pieces=?, stop_price=?, scaled=?, extended=?, best_future=? WHERE id=?",
                                 (json.dumps(pieces), stop, scaled, extended, best, r["id"]))
            await db.commit()
        if reason:
            lots = sum(n for _e, n in pieces)
            logger.info("sn_gold_exit", id=r["id"], reason=reason, bid=bid, net=round(net, 2))
            _tell(f"🥇 SN Gold (paper): sold {lots} lot{'s' if lots > 1 else ''} of {r['tradingsymbol']} at Rs {bid:.2f} "
                        f"({reason.replace('_', ' ')}): Rs {net:+,.0f} after charges. Paper only.")
    return closed


async def close_day(db_path: str, now: datetime) -> bool:
    """Once a day after the close, with nothing open: book the day, refill a loss, grow the wallet, tell the owner."""
    day = now.date().isoformat()
    async with aiosqlite.connect(db_path) as db:
        if await (await db.execute("SELECT 1 FROM sn_gold_days WHERE session_date=?", (day,))).fetchone():
            return False
        if await (await db.execute("SELECT 1 FROM sn_gold_positions WHERE status='OPEN'")).fetchone():
            return False
        row = await (await db.execute("SELECT COUNT(*), COALESCE(SUM(net),0), COALESCE(SUM(net_stressed),0) FROM sn_gold_positions "
                                      "WHERE session_date=? AND status='CLOSED'", (day,))).fetchone()
    trades, net, stressed = int(row[0]), float(row[1]), float(row[2])
    w = await wallet_state(db_path, now)
    before = float(w["wallet"])
    wallet, steps, progress = grow(before, int(w["steps"]), float(w["progress"]), net)
    refill = max(0.0, -net)
    banked, refilled = float(w["banked"]) + max(0.0, net), float(w["refilled"]) + refill
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("INSERT OR IGNORE INTO sn_gold_days(session_date,trades,net,net_stressed,refill,wallet_before,wallet_after,steps_after,closed_at) "
                               "VALUES(?,?,?,?,?,?,?,?,?)", (day, trades, net, stressed, refill, before, wallet, steps, now.isoformat()))
        if cur.rowcount != 1:
            return False
        await db.execute("UPDATE sn_gold_wallet SET wallet=?, steps=?, progress=?, banked=?, refilled=? WHERE id=1",
                         (wallet, steps, progress, banked, refilled))
        await db.commit()
    if trades:
        grew = f" The wallet grew to Rs {wallet:,.0f} (step {steps} of {int(settings.SN_GOLD_MAX_STEPS)})." if wallet > before else ""
        _tell(f"🥇 SN Gold (paper) today: Rs {net:+,.0f} on {trades} trade{'s' if trades > 1 else ''}"
                    f"{f', refill Rs {refill:,.0f}' if refill else ''}.{grew} Since the start: won Rs {banked:,.0f}, refilled Rs {refilled:,.0f}, "
                    f"net Rs {banked - refilled:+,.0f}. Wallet Rs {wallet:,.0f}. Paper only, no orders.")
    return True


_PENDING: set = set()


def _tell(text: str) -> None:
    """Send the owner a line without waiting for it: a message must never delay N11's or the main book's next step."""
    async def send() -> None:
        try:
            from operator_alert import notify_operator
            await notify_operator(text, event="sn_gold")
        except Exception as exc:
            logger.error("sn_gold_notify_failed", err=str(exc))
    try:
        task = asyncio.get_running_loop().create_task(send())
    except RuntimeError:
        return
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
