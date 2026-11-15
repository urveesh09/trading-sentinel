"""[Gold v6 / v7 WK-H 2026-11-15] The hedged weekly NIFTY straddle: the gap-day leg of Gold v6 / Gold v7 (= SN Gold v5,
unchanged, in sn_gold.py + this module), run on PAPER. It never places an order. Gold v7 (SN245, the Dev default) is the
same leg with SN_WKH_BAND = 0.8 instead of Gold v6's 0.6 (docs/research/fno/2026-11-15-sn231).

Owner, Nov 15: "That gold v5 + wk-h is the new gold v6 ... I allow you to do that in Dev right now ... this will be our
baseline, and we will be calling this Gold V6."
Research: docs/research/fno/2026-11-15-sn221 (SN227's frozen pick ("STRADDLE", "M", "settle", "H15x2"), SN228's unseen
NIFTY Oct 2020 - Nov 2021 exam passed: +Rs 61,511 per option lot, worst month -Rs 6,251) and
docs/SN_WEEKLY_SELLER_AND_GOLD_V6.md section 0.

The rules, as the research replayed them (docs/research/fno/2026-11-15-sn221/wk3.py), on live quotes:
  * entry: 15:15 on the first session after the last weekend or holiday before the nearest weekly expiry (every calendar
    day from today to the expiry is a session and yesterday was not), so no weekend is ever held;
  * the position: sell the ATM call and put (the strike whose call and put mids are closest), 2 lots per Rs 5 lakh unit,
    at the bid;
  * the hedge: from the next session's 09:15, at each 15-minute mark (09:15 ... 15:15; on expiry day up to 14:15),
    net = lots x the straddle's Black-Scholes delta + futures lots; when |net| > the band (SN_WKH_BAND: Gold v7 0.8,
    Gold v6 0.6) the futures are reset to
    -round(lots x delta) (bought at the ask, sold at the bid). Sigma is fixed at entry from the straddle
    (Q = 0.7979 S sigma sqrt(T)); time runs in sessions (the rest of today / 375 + each full session + 360/375 for
    expiry day + 0.15 a night). The contract is the first NIFTY future expiring on or after the option expiry;
  * expiry day: no new hedge orders from 14:30; the futures close at the mean of their 15:00-15:25 quotes (the tick's
    last minutes); the options settle at intrinsic value against the official closing index, read at the next session's
    first tick (Kite's previous close), and are charged as a round trip, as the research charged them;
  * money: real bid / ask, Zerodha charges (options from fno_costs, futures from the schedule below); the research's
    Rs 100 per option leg-lot and per futures lot-order (+Rs 100 before 09:20) stay beside it as net_stressed;
  * the wallet: Rs 5 lakh (one unit, an unverified margin proxy); each week's result is banked or refilled.
The caller guards every call: nothing here can stop an N11, SN Gold or main-book step.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

import aiosqlite
import structlog

from config import settings
from fno_costs import calc_fno_costs

logger = structlog.get_logger()

SOURCE = "GOLD_V6_WKH_PAPER"
ENTRY_MIN = 15 * 60 + 15           # the research entered at the 15:15 close
ENTRY_LAST_MIN = 15 * 60 + 19      # a late tick may still enter until 15:19
OPEN_MIN = 9 * 60 + 15
OPEN_PENALTY_BEFORE = 9 * 60 + 20
TWAP_FROM = 15 * 60
HEDGE_CLOSE_MIN = 15 * 60 + 24     # the F&O tick runs to 15:25; the hedge closes at its last minutes
SPOT_KEY, FUT_KEY = -1, -2         # negative keys never collide with instrument tokens
SPOT_QUOTE = "NSE:NIFTY 50"
WINDOW = 4                         # strikes each side of the forward ATM read at entry

_DDL = (
    """CREATE TABLE IF NOT EXISTS gold_v6_wkh_weeks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expiry TEXT NOT NULL UNIQUE,
  entry_day TEXT NOT NULL,
  entry_time TEXT NOT NULL,
  strike REAL NOT NULL,
  ce_symbol TEXT NOT NULL, ce_token INTEGER NOT NULL,
  pe_symbol TEXT NOT NULL, pe_token INTEGER NOT NULL,
  lot_size INTEGER NOT NULL,
  lots INTEGER NOT NULL,
  ce_bid REAL NOT NULL, pe_bid REAL NOT NULL,
  straddle_mid REAL NOT NULL,
  spot0 REAL NOT NULL,
  sigma REAL NOT NULL,
  t0 REAL NOT NULL,
  fut_symbol TEXT NOT NULL, fut_token INTEGER NOT NULL,
  hedge_lots INTEGER NOT NULL DEFAULT 0,
  hedge_cash REAL NOT NULL DEFAULT 0,
  hedge_costs REAL NOT NULL DEFAULT 0,
  hedge_stress REAL NOT NULL DEFAULT 0,
  hedge_orders INTEGER NOT NULL DEFAULT 0,
  last_slot TEXT,
  hedge_closed INTEGER NOT NULL DEFAULT 0,
  twap TEXT,
  status TEXT NOT NULL,
  settle_spot REAL,
  option_net REAL,
  hedge_net REAL,
  net REAL,
  net_stressed REAL,
  closed_at TEXT,
  reason TEXT
)""",
    """CREATE TABLE IF NOT EXISTS gold_v6_wkh_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_id INTEGER NOT NULL,
  at TEXT NOT NULL,
  side TEXT NOT NULL,
  lots INTEGER NOT NULL,
  price REAL NOT NULL,
  costs REAL NOT NULL,
  spot REAL,
  delta REAL,
  hedge_after INTEGER NOT NULL,
  reason TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS gold_v6_wkh_marks (
  week_id INTEGER NOT NULL,
  session_date TEXT NOT NULL,
  at TEXT NOT NULL,
  spot REAL,
  option_value REAL,
  hedge_value REAL,
  total REAL,
  PRIMARY KEY (week_id, session_date)
)""",
    """CREATE TABLE IF NOT EXISTS gold_v6_wkh_wallet (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  wallet REAL NOT NULL,
  banked REAL NOT NULL,
  refilled REAL NOT NULL,
  weeks INTEGER NOT NULL,
  started TEXT NOT NULL
)""",
)


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        for ddl in _DDL:
            await db.execute(ddl)
        await db.commit()


# ---- pure rules (each one is wk3.py's rule) ------------------------------------------------------------------------------

def lots_for(wallet: float) -> int:
    units = int(float(wallet) // float(settings.SN_WKH_UNIT_MARGIN))
    return units * int(settings.SN_WKH_LOTS_PER_UNIT)


def entry_day_ok(today: date, expiry: Optional[date], is_session: Callable[[date], bool]) -> bool:
    """wk3.k_of("M"): today is the earliest session from which no calendar gap remains before the expiry."""
    if expiry is None or today >= expiry or not is_session(today):
        return False
    d = today
    while d <= expiry:
        if not is_session(d):
            return False
        d += timedelta(days=1)
    return not is_session(today - timedelta(days=1))


def session_time(day: date, minute: int, expiry: date) -> float:
    """wk3.hedge_path's clock in session units; minute = hour * 60 + minute (09:15 = 555)."""
    j = minute - OPEN_MIN
    night = float(settings.SN_WKH_NIGHT)
    if day >= expiry:
        return max(1e-4, (360 - j) / 375.0)
    n_after = (expiry - day).days - 1          # every calendar day to the expiry is a session (entry_day_ok)
    return (375 - j) / 375.0 + n_after + 360 / 375.0 + night * (n_after + 1)


def sigma_from(straddle: float, spot: float, t0: float) -> float:
    return float(straddle) / (0.7979 * float(spot) * math.sqrt(float(t0)))


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def straddle_delta(strike: float, spot: float, t: float, sigma: float) -> float:
    """Delta of one short call + one short put at the strike (per lot, in lots), as wk3._delta."""
    st = sigma * math.sqrt(max(t, 1e-6))
    d1 = (math.log(spot / strike) + 0.5 * st * st) / st
    n = _ncdf(d1)
    return -n - (n - 1.0)


def hedge_target(lots: int, delta: float, hedge_lots: int, band: float) -> Optional[int]:
    """The futures position after a check, or None when the net delta is inside the band."""
    net = lots * delta + hedge_lots
    if abs(net) <= band:
        return None
    target = -int(round(lots * delta))
    return None if target == hedge_lots else target


def fut_charges(price: float, lots: int, side: str, lot_size: int) -> float:
    """Zerodha futures charges for one order (Nov 2026 schedule: Rs 20 or 0.03%, STT 0.02% on the sell, NSE 0.00173%,
    SEBI Rs 10 a crore, stamp 0.002% on the buy, GST 18% on brokerage + exchange + SEBI)."""
    v = abs(float(price)) * int(lot_size) * abs(int(lots))
    brk = min(20.0, 0.0003 * v)
    exch = 0.0000173 * v
    sebi = 1e-6 * v
    stt = 0.0002 * v if side == "SELL" else 0.0
    stamp = 0.00002 * v if side == "BUY" else 0.0
    return brk + stt + exch + sebi + stamp + 0.18 * (brk + exch + sebi)


def pick_atm(chain: dict, spot: float) -> Optional[float]:
    """chain {strike: (ce_bid, ce_ask, pe_bid, pe_ask)} -> the strike whose call and put mids are closest, ties to the
    strike nearer the index (wk.atm_of); both sides must be quoted."""
    best = None
    for k in sorted(chain):
        cb, ca, pb, pa = chain[k]
        if min(cb, ca, pb, pa) <= 0:
            continue
        key = (abs((cb + ca) / 2 - (pb + pa) / 2), abs(k - spot))
        if best is None or key < best[0]:
            best = (key, k)
    return None if best is None else best[1]


def option_settle_net(strike: float, ce_bid: float, pe_bid: float, settle: float, qty: int) -> float:
    """The short straddle at settlement: intrinsic charged as a round trip (wk._settle_value without the stress)."""
    ce_iv, pe_iv = max(0.0, settle - strike), max(0.0, strike - settle)
    return ((ce_bid - ce_iv) * qty - calc_fno_costs(ce_iv, ce_bid, qty)
            + (pe_bid - pe_iv) * qty - calc_fno_costs(pe_iv, pe_bid, qty))


def option_close_value(strike: float, ce_bid: float, pe_bid: float, ce_ask_now: float, pe_ask_now: float, qty: int) -> float:
    """The short straddle if bought back now at the asks (a mark)."""
    return ((ce_bid - ce_ask_now) * qty - calc_fno_costs(ce_ask_now, ce_bid, qty)
            + (pe_bid - pe_ask_now) * qty - calc_fno_costs(pe_ask_now, pe_bid, qty))


def hedge_close_value(hedge_lots: int, cash: float, bid: float, ask: float, lot_size: int) -> float:
    """The futures hedge if closed now (a long sold at the bid, a short bought at the ask), after its charges."""
    if hedge_lots == 0:
        return cash
    if hedge_lots > 0:
        return cash + hedge_lots * lot_size * bid - fut_charges(bid, hedge_lots, "SELL", lot_size)
    return cash + hedge_lots * lot_size * ask - fut_charges(ask, -hedge_lots, "BUY", lot_size)


def slot_of(minute: int) -> int:
    return (minute - OPEN_MIN) // int(settings.SN_WKH_EVERY_MIN)


# ---- quotes ----------------------------------------------------------------------------------------------------------

def _book(packet: dict) -> tuple:
    depth = (packet or {}).get("depth") or {}
    buys, sells = depth.get("buy") or [], depth.get("sell") or []
    bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
    ask = float(sells[0]["price"]) if sells and sells[0].get("price") else 0.0
    return bid, ask


async def _read(kite, request: dict) -> dict:
    from kite_client import provider_lane
    with provider_lane("management"):
        return await asyncio.wait_for(kite.get_quote_by_instruments(request), timeout=float(settings.FNO_EXIT_QUOTE_READ_MAX_SEC))


def _instruments():
    from fno_instruments import get_fno_instruments
    return get_fno_instruments()


def hedge_future(inst, expiry: date):
    """The first NIFTY future expiring on or after the option expiry (wk3.Fut.series)."""
    for e in inst.future_expiries:
        if e >= expiry:
            return inst.by_key.get((inst.underlying, e.isoformat(), 0.0, "FUT"))
    return None


# ---- state -----------------------------------------------------------------------------------------------------------

async def wallet_state(db_path: str, now: datetime) -> dict:
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM gold_v6_wkh_wallet WHERE id=1")).fetchone()
        if row is None:
            await db.execute("INSERT OR IGNORE INTO gold_v6_wkh_wallet(id,wallet,banked,refilled,weeks,started) VALUES(1,?,?,?,?,?)",
                             (float(settings.SN_WKH_WALLET), 0.0, 0.0, 0, now.date().isoformat()))
            await db.commit()
            row = await (await db.execute("SELECT * FROM gold_v6_wkh_wallet WHERE id=1")).fetchone()
    return dict(row)


async def _open_week(db_path: str) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM gold_v6_wkh_weeks WHERE status IN ('OPEN','SETTLING') ORDER BY id LIMIT 1")).fetchone()
    return dict(row) if row else None


# ---- the tick: every F&O management tick, after SN Gold ------------------------------------------------------------

async def tick(kite, db_path: str, *, now: datetime,
               is_session: Optional[Callable[[date], Awaitable[bool]]] = None) -> str:
    """One look. Returns what it did ("entered", "hedged", "marked", "hedge_closed", "settled", or "")."""
    if not settings.SN_WKH_ENABLED or kite is None:
        return ""
    await init_db(db_path)
    minute = now.hour * 60 + now.minute
    today = now.date()
    week = await _open_week(db_path)
    if week is not None:
        expiry = date.fromisoformat(week["expiry"])
        if today > expiry and week["status"] in ("OPEN", "SETTLING"):
            checker = is_session or _default_is_session(db_path)
            prev = today - timedelta(days=1)
            while prev > expiry and not await checker(prev):
                prev -= timedelta(days=1)
            return await _settle(kite, db_path, week, now, previous_close_is_expiry=(prev == expiry))
        if week["status"] == "OPEN":
            return await _manage(kite, db_path, week, now, minute, expiry)
        return ""
    if not (ENTRY_MIN <= minute <= ENTRY_LAST_MIN):
        return ""
    inst = _instruments()
    expiry = inst.nearest_option_expiry(today)
    checker = is_session or _default_is_session(db_path)
    sessions = {}
    d = today - timedelta(days=1)
    while expiry is not None and d <= expiry:
        sessions[d] = await checker(d)
        d += timedelta(days=1)
    if not entry_day_ok(today, expiry, lambda x: sessions.get(x, False)):
        return ""
    async with aiosqlite.connect(db_path) as db:
        if await (await db.execute("SELECT 1 FROM gold_v6_wkh_weeks WHERE expiry=?", (expiry.isoformat(),))).fetchone():
            return ""
    return await _enter(kite, db_path, inst, expiry, now)


def _default_is_session(db_path: str):
    async def check(d: date) -> bool:
        from market_calendar import is_trading_day
        return await is_trading_day(d, db_path)
    return check


async def _enter(kite, db_path: str, inst, expiry: date, now: datetime) -> str:
    from fno_models import OptionType
    w = await wallet_state(db_path, now)
    lots = lots_for(float(w["wallet"]))
    if lots <= 0:
        return ""
    fut = hedge_future(inst, expiry)
    if fut is None:
        logger.warning("gold_v6_wkh_no_future", expiry=expiry.isoformat())
        return ""
    front = inst.front_future(now.date())
    probe = await _read(kite, {SPOT_KEY: SPOT_QUOTE, FUT_KEY: f"NFO:{fut.tradingsymbol}"})
    spot = float((probe.get(SPOT_KEY) or {}).get("last_price") or 0.0)
    if spot <= 0:
        logger.warning("gold_v6_wkh_no_spot")
        return ""
    contracts = {}
    for k in inst.strikes_window(spot, WINDOW):
        ce, pe = inst.option(expiry, k, OptionType.CE), inst.option(expiry, k, OptionType.PE)
        if ce is not None and pe is not None:
            contracts[k] = (ce, pe)
    if not contracts:
        return ""
    req = {SPOT_KEY: SPOT_QUOTE, FUT_KEY: f"NFO:{fut.tradingsymbol}"}
    for ce, pe in contracts.values():
        req[int(ce.token)] = f"NFO:{ce.tradingsymbol}"
        req[int(pe.token)] = f"NFO:{pe.tradingsymbol}"
    got = await _read(kite, req)
    spot = float((got.get(SPOT_KEY) or {}).get("last_price") or spot)
    chain = {}
    for k, (ce, pe) in contracts.items():
        cb, ca = _book(got.get(int(ce.token)))
        pb, pa = _book(got.get(int(pe.token)))
        chain[k] = (cb, ca, pb, pa)
    strike = pick_atm(chain, spot)
    if strike is None:
        logger.warning("gold_v6_wkh_no_two_sided_atm")
        return ""
    cb, ca, pb, pa = chain[strike]
    ce, pe = contracts[strike]
    lot_size = int(inst.lot_size or ce.lot_size)
    mid = (cb + ca) / 2 + (pb + pa) / 2
    t0 = session_time(now.date(), ENTRY_MIN, expiry)
    sig = sigma_from(mid, spot, t0)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO gold_v6_wkh_weeks(expiry,entry_day,entry_time,strike,ce_symbol,ce_token,pe_symbol,pe_token,lot_size,lots,"
            "ce_bid,pe_bid,straddle_mid,spot0,sigma,t0,fut_symbol,fut_token,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'OPEN')",
            (expiry.isoformat(), now.date().isoformat(), now.isoformat(), float(strike), ce.tradingsymbol, int(ce.token), pe.tradingsymbol,
             int(pe.token), lot_size, lots, cb, pb, mid, spot, sig, t0, fut.tradingsymbol, int(fut.token)))
        await db.commit()
        if cur.rowcount != 1:
            return ""
    credit = (cb + pb) * lot_size * lots
    logger.info("gold_v6_wkh_entry", expiry=expiry.isoformat(), strike=strike, lots=lots, ce_bid=cb, pe_bid=pb, spot=spot, sigma=round(sig, 6),
                front_future=getattr(front, "tradingsymbol", None), hedge_future=fut.tradingsymbol)
    _tell(f"🥇 {settings.SN_WKH_LABEL} · WK-H (paper): sold the NIFTY {int(strike)} straddle for {expiry:%d %b}, {lots} lots, call Rs {cb:.2f} + put Rs {pb:.2f} "
          f"(credit Rs {credit:,.0f}). NIFTY futures will hedge its direction every 15 minutes from the next open. Paper only, no orders.")
    return "entered"


async def _manage(kite, db_path: str, week: dict, now: datetime, minute: int, expiry: date) -> str:
    today = now.date()
    entry_day = date.fromisoformat(week["entry_day"])
    if today == entry_day:
        return ""                                  # the research's first check is the next session's 09:15
    lot_size, lots = int(week["lot_size"]), int(week["lots"])
    expiry_day = today >= expiry
    if expiry_day and minute >= HEDGE_CLOSE_MIN and not int(week["hedge_closed"]):
        return await _close_hedge(kite, db_path, week, now)
    if expiry_day and int(week["hedge_closed"]):
        return ""
    slot = f"{today.isoformat()}:{slot_of(minute)}"
    # the first tick in each 15-minute slot from 09:15 checks (the last slot starts 15:15); none from 14:30 on expiry day
    is_check = OPEN_MIN <= minute < 15 * 60 + 30 and not (expiry_day and minute >= int(settings.SN_WKH_FREEZE_MIN))
    want_mark = not expiry_day and minute >= ENTRY_MIN
    async with aiosqlite.connect(db_path) as db:
        marked = await (await db.execute("SELECT 1 FROM gold_v6_wkh_marks WHERE week_id=? AND session_date=?", (week["id"], today.isoformat()))).fetchone()
    tw_prev = json.loads(week["twap"] or "[]")
    want_twap = expiry_day and minute >= TWAP_FROM and (not tw_prev or tw_prev[-1][0] != minute)   # one sample a minute
    if not ((is_check and slot != week["last_slot"]) or (want_mark and not marked) or want_twap):
        return ""
    req = {SPOT_KEY: SPOT_QUOTE, FUT_KEY: f"NFO:{week['fut_symbol']}"}
    if want_mark and not marked:
        req[int(week["ce_token"])] = f"NFO:{week['ce_symbol']}"
        req[int(week["pe_token"])] = f"NFO:{week['pe_symbol']}"
    got = await _read(kite, req)
    spot = float((got.get(SPOT_KEY) or {}).get("last_price") or 0.0)
    fbid, fask = _book(got.get(FUT_KEY))
    did = ""
    hedge_lots, cash, costs, stress, orders = int(week["hedge_lots"]), float(week["hedge_cash"]), float(week["hedge_costs"]), float(week["hedge_stress"]), int(week["hedge_orders"])
    if want_twap and fbid > 0 and fask > 0:
        tw_prev.append([minute, fbid, fask])
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE gold_v6_wkh_weeks SET twap=? WHERE id=?", (json.dumps(tw_prev), week["id"]))
            await db.commit()
    if is_check and slot != week["last_slot"] and spot > 0 and fbid > 0 and fask > 0:
        t = session_time(today, minute, expiry)
        delta = straddle_delta(float(week["strike"]), spot, t, float(week["sigma"]))
        target = hedge_target(lots, delta, hedge_lots, float(settings.SN_WKH_BAND))
        if target is not None:
            q = target - hedge_lots
            side = "BUY" if q > 0 else "SELL"
            px = fask if q > 0 else fbid
            c = fut_charges(px, abs(q), side, lot_size)
            st = float(settings.SN_WKH_FUT_STRESS_PER_LOT) * abs(q) + (float(settings.SN_WKH_OPEN_PENALTY) * abs(q) if minute < OPEN_PENALTY_BEFORE else 0.0)
            cash -= q * lot_size * px + c
            costs += c
            stress += st
            orders += 1
            hedge_lots = target
            async with aiosqlite.connect(db_path) as db:
                await db.execute("INSERT INTO gold_v6_wkh_orders(week_id,at,side,lots,price,costs,spot,delta,hedge_after,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 (week["id"], now.isoformat(), side, abs(q), px, c, spot, delta, hedge_lots, "band"))
                await db.commit()
            logger.info("gold_v6_wkh_hedge", week=week["id"], side=side, lots=abs(q), price=px, spot=spot, delta=round(delta, 3), hedge=hedge_lots)
            _tell(f"🥇 {settings.SN_WKH_LABEL} · WK-H (paper): {'bought' if q > 0 else 'sold'} {abs(q)} NIFTY futures lot{'s' if abs(q) > 1 else ''} at Rs {px:,.2f} "
                  f"(NIFTY {spot:,.2f}); the hedge is now {hedge_lots:+d} lots. Paper only.")
            did = "hedged"
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE gold_v6_wkh_weeks SET hedge_lots=?, hedge_cash=?, hedge_costs=?, hedge_stress=?, hedge_orders=?, last_slot=? WHERE id=?",
                             (hedge_lots, cash, costs, stress, orders, slot, week["id"]))
            await db.commit()
    if want_mark and not marked:
        cb, ca = _book(got.get(int(week["ce_token"])))
        pb, pa = _book(got.get(int(week["pe_token"])))
        if ca > 0 and pa > 0 and fbid > 0 and fask > 0:
            qty = lot_size * lots
            ov = option_close_value(float(week["strike"]), float(week["ce_bid"]), float(week["pe_bid"]), ca, pa, qty)
            hv = hedge_close_value(hedge_lots, cash, fbid, fask, lot_size)
            async with aiosqlite.connect(db_path) as db:
                await db.execute("INSERT OR IGNORE INTO gold_v6_wkh_marks(week_id,session_date,at,spot,option_value,hedge_value,total) VALUES(?,?,?,?,?,?,?)",
                                 (week["id"], today.isoformat(), now.isoformat(), spot, ov, hv, ov + hv))
                await db.commit()
            _tell(f"🥇 {settings.SN_WKH_LABEL} · WK-H (paper) at 15:15: the {int(week['strike'])} straddle is worth Rs {ov + hv:+,.0f} if closed now "
                  f"(options {ov:+,.0f}, futures hedge {hv:+,.0f}, {hedge_lots:+d} lots). It settles on {expiry:%d %b}. Paper only.")
            did = did or "marked"
    return did


async def _close_hedge(kite, db_path: str, week: dict, now: datetime) -> str:
    """Expiry day, the tick's last minutes: close the futures at the mean of their 15:00-15:25 quotes."""
    lot_size, h = int(week["lot_size"]), int(week["hedge_lots"])
    tw = json.loads(week["twap"] or "[]")
    if not tw:
        got = await _read(kite, {FUT_KEY: f"NFO:{week['fut_symbol']}"})
        b, a = _book(got.get(FUT_KEY))
        if b > 0 and a > 0:
            tw = [[now.hour * 60 + now.minute, b, a]]
    if h != 0 and not tw:
        return ""
    bid = sum(x[1] for x in tw) / len(tw) if tw else 0.0
    ask = sum(x[2] for x in tw) / len(tw) if tw else 0.0
    cash, costs, stress, orders = float(week["hedge_cash"]), float(week["hedge_costs"]), float(week["hedge_stress"]), int(week["hedge_orders"])
    if h != 0:
        side = "SELL" if h > 0 else "BUY"
        px = bid if h > 0 else ask
        c = fut_charges(px, abs(h), side, lot_size)
        cash += h * lot_size * px - c
        costs += c
        stress += float(settings.SN_WKH_FUT_STRESS_PER_LOT) * abs(h)
        orders += 1
        async with aiosqlite.connect(db_path) as db:
            await db.execute("INSERT INTO gold_v6_wkh_orders(week_id,at,side,lots,price,costs,spot,delta,hedge_after,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                             (week["id"], now.isoformat(), side, abs(h), px, c, None, None, 0, "expiry_close_twap"))
            await db.commit()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE gold_v6_wkh_weeks SET hedge_lots=0, hedge_cash=?, hedge_costs=?, hedge_stress=?, hedge_orders=?, hedge_closed=1, "
                         "status='SETTLING' WHERE id=?", (cash, costs, stress, orders, week["id"]))
        await db.commit()
    _tell(f"🥇 {settings.SN_WKH_LABEL} · WK-H (paper): expiry day, the futures hedge is closed (Rs {cash:+,.0f} after Rs {costs:,.0f} of charges, {orders} orders "
          f"this week). The {int(week['strike'])} straddle settles at today's official NIFTY close; the week's result comes at the next open. Paper only.")
    return "hedge_closed"


async def _settle(kite, db_path: str, week: dict, now: datetime, previous_close_is_expiry: bool = True) -> str:
    """The next session's first tick: settle the options at the expiry day's official close (Kite's previous close)."""
    why = None
    if not int(week["hedge_closed"]) and int(week["hedge_lots"]) != 0:
        why = "engine_down_at_expiry"                  # no fair price for the open futures hedge
    elif not previous_close_is_expiry:
        why = "engine_down_after_expiry"               # Kite's previous close is no longer the expiry day's close
    if why:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE gold_v6_wkh_weeks SET status='UNRESOLVED', reason=?, closed_at=? WHERE id=?",
                             (why, now.isoformat(), week["id"]))
            await db.commit()
        _tell(f"🥇 {settings.SN_WKH_LABEL} · WK-H (paper): the {week['expiry']} week could not be booked (the engine was not running at the expiry close). Paper only.")
        return "unresolved"
    got = await _read(kite, {SPOT_KEY: SPOT_QUOTE})
    pk = got.get(SPOT_KEY) or {}
    settle = float(((pk.get("ohlc") or {}).get("close")) or 0.0)
    if settle <= 0:
        return ""
    lot_size, lots = int(week["lot_size"]), int(week["lots"])
    qty = lot_size * lots
    opt = option_settle_net(float(week["strike"]), float(week["ce_bid"]), float(week["pe_bid"]), settle, qty)
    hedge = float(week["hedge_cash"])
    net = opt + hedge
    stressed = net - float(settings.SN_WKH_STRESS_PER_LEG_LOT) * 2 * lots - float(week["hedge_stress"])
    w = await wallet_state(db_path, now)
    banked = float(w["banked"]) + max(0.0, net)
    refilled = float(w["refilled"]) + max(0.0, -net)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("UPDATE gold_v6_wkh_weeks SET status='CLOSED', settle_spot=?, option_net=?, hedge_net=?, net=?, net_stressed=?, closed_at=?, "
                               "reason='settled' WHERE id=? AND status IN ('OPEN','SETTLING')", (settle, opt, hedge, net, stressed, now.isoformat(), week["id"]))
        if cur.rowcount != 1:
            return ""
        await db.execute("UPDATE gold_v6_wkh_wallet SET banked=?, refilled=?, weeks=weeks+1 WHERE id=1", (banked, refilled))
        await db.commit()
    logger.info("gold_v6_wkh_settled", expiry=week["expiry"], settle=settle, option_net=round(opt, 2), hedge_net=round(hedge, 2), net=round(net, 2))
    _tell(f"🥇 {settings.SN_WKH_LABEL} · WK-H (paper), the {date.fromisoformat(week['expiry']):%d %b} week: NIFTY settled at {settle:,.2f} against the {int(week['strike'])} "
          f"straddle. Options Rs {opt:+,.0f}, futures hedge Rs {hedge:+,.0f}: Rs {net:+,.0f} after charges"
          f"{f', refill Rs {-net:,.0f}' if net < 0 else ''}. Since the start: won Rs {banked:,.0f}, refilled Rs {refilled:,.0f}, "
          f"net Rs {banked - refilled:+,.0f}. Paper only, no orders.")
    return "settled"


async def summary(db_path: str) -> dict:
    """Gold v6's two legs for a report: SN Gold v5's wallet ledger and WK-H's weekly ledger."""
    await init_db(db_path)
    out: dict[str, Any] = {}
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        w = await (await db.execute("SELECT * FROM gold_v6_wkh_wallet WHERE id=1")).fetchone()
        out["wkh"] = dict(w) if w else None
        try:
            g = await (await db.execute("SELECT * FROM sn_gold_wallet WHERE id=1")).fetchone()
            out["gold_v5"] = dict(g) if g else None
        except Exception:
            out["gold_v5"] = None
    return out


_PENDING: set = set()


def _tell(text: str) -> None:
    """Send the owner a line without waiting for it: a message must never delay the next F&O step."""
    async def send() -> None:
        try:
            from operator_alert import notify_operator
            await notify_operator(text, event="gold_v6_wkh")
        except Exception as exc:
            logger.error("gold_v6_wkh_notify_failed", err=str(exc))
    try:
        task = asyncio.get_running_loop().create_task(send())
    except RuntimeError:
        return
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
