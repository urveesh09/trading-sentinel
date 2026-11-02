"""[N11 2026-11-02] The paper F&O main book's account rules: the owner's call after the N11 study ("take N11 as the main
strategy, the rest as shadows ... deploy it in production"). Research: docs/FNO_RESEARCH_N11.md, frozen at 43fa015.

fno_book holds N11's signals and exits. This module holds what sits around them:

  - size by volatility: two lots only when yesterday's daily ATR% is at or above its median of the last 250 sessions;
  - one lot after a realised loss today (never a refusal);
  - stand aside: real entries wait while yesterday's ATR% is below 0.9 of that median AND the last 20 closed one-lot
    paper trades sum to zero or less. The paper record keeps trading (``fno_n11_paper``), so it ends by itself;
  - the honest earned lot: one more lot on a two-lot trade at or past +1R and before 14:45, at the first look where what
    the held lots are expected to lose at their current stop, plus the new lot's whole 25% backstop, fits Rs 5,000. The
    held lots' stops are never touched. It is its own position (``N11_ADD``), leaving at the held lots' entry level, at
    its own backstop, or with them. Paper book only: the real-money test never adds.

Every number was seen in research: this is the owner's decision, not a proof. The real-money test is a separate switch
that this module never touches. Back to the Oct 31 book: FNO_BOOK=UNION_ADX. Rules here are pure where they can be and
match docs/research/simulation/2026-11-02-fno-n11/n11_rules.py. Nothing in ``tick`` may stop an exit: the caller guards it.
"""
from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timedelta
from statistics import median
from time import monotonic
from types import SimpleNamespace
from typing import Any, Callable, Optional, Sequence

import aiosqlite
import pandas as pd
import structlog

from config import settings
from fno_costs import calc_fno_costs, options_exchange_for

logger = structlog.get_logger()

PREFIX = "N11_"
ADD = "N11_ADD"
LOW = "N11_TPB_LOW"
ADD_BAR = "N11ADD:"
LOT_CAP = 2
ADD_AT_R = 1.0
PAPER_SOURCE = "N11_PAPER"
SEED_SOURCE = "research_seed"
VOL_WINDOW = 250
VOL_NEED = 120
VOL_READ_FROM_MIN = 9 * 60 + 30
VOL_HISTORY_CALENDAR_DAYS = 420
READ_RETRY_SEC = 60.0
SHADOW_REPORT_FROM_MIN = 15 * 60 + 15
# N08's one-lot, brakes-off paper results from research, oldest first: the record the stand-aside starts from. Their sum is
# +25,308. Research ends Oct 28, 2026, so nothing from Oct 29-30 is here: the live record starts on deployment.
SEED_NETS = (("2026-06-01T15:10:59+05:30", 5016.9), ("2026-06-12T13:28:59+05:30", -2538.25),
             ("2026-06-19T12:02:59+05:30", -1199.39), ("2026-07-22T15:10:59+05:30", 1381.59),
             ("2026-07-22T15:10:59+05:30", 839.74), ("2026-08-17T12:18:59+05:30", -1165.98),
             ("2026-08-19T14:06:59+05:30", -685.65), ("2026-08-27T15:10:59+05:30", 478.85),
             ("2026-08-27T15:10:59+05:30", -790.0), ("2026-09-07T13:53:59+05:30", -1665.21),
             ("2026-09-24T14:02:59+05:30", 6060.18), ("2026-09-28T11:10:59+05:30", -86.66),
             ("2026-09-28T11:30:59+05:30", 771.48), ("2026-09-28T14:46:59+05:30", 2126.65),
             ("2026-10-05T11:15:59+05:30", 2075.29), ("2026-10-07T10:17:59+05:30", -2033.39),
             ("2026-10-08T15:10:59+05:30", 8999.32), ("2026-10-09T12:30:59+05:30", -752.68),
             ("2026-10-09T15:10:59+05:30", 238.49), ("2026-10-14T14:25:59+05:30", -1660.19),
             ("2026-10-21T15:10:59+05:30", 11041.2), ("2026-10-23T15:10:59+05:30", 1334.28))

_DDL = """
CREATE TABLE IF NOT EXISTS fno_n11_paper (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  underlying TEXT NOT NULL,
  bar_ts TEXT NOT NULL,
  strategy TEXT NOT NULL,
  direction TEXT,
  tradingsymbol TEXT,
  token INTEGER,
  lot_size INTEGER,
  entry_time TEXT,
  entry_premium REAL,
  entry_underlying REAL,
  stop_underlying REAL,
  target_underlying REAL,
  premium_stop REAL,
  atr_at_entry REAL,
  delta_at_entry REAL,
  trail_active INTEGER NOT NULL DEFAULT 0,
  trail_stop_underlying REAL,
  best_underlying REAL,
  best_premium REAL,
  native_lots INTEGER,
  vol_lots INTEGER,
  stood_aside INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  exit_time TEXT,
  exit_premium REAL,
  exit_reason TEXT,
  net REAL,
  source TEXT NOT NULL,
  UNIQUE (underlying, bar_ts)
)"""
_GATE_DDL = """
CREATE TABLE IF NOT EXISTS fno_n11_gate (
  session_date TEXT PRIMARY KEY,
  atr_pct REAL,
  usual REAL,
  vol_up INTEGER NOT NULL,
  above_line INTEGER NOT NULL,
  recorded_at TEXT NOT NULL,
  shadow_reported_at TEXT
)"""


def _num(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def extra_cost(lots: int) -> float:
    """The research's declared stress per trade. Never charged to the paper ledger: it enters the risk charge and the paper record."""
    return (200.0 + 5.0 * lots) * lots


# ---- pure rules ---------------------------------------------------------------------------------------------------------

def vol_reading(daily: Optional[pd.DataFrame], day: date) -> tuple:
    """(yesterday's daily ATR as % of close, its median over the 250 sessions before that) from daily bars strictly before
    ``day``. (None, None) without enough bars; the usual level is None with fewer than 120 earlier readings."""
    if daily is None or daily.empty:
        return None, None
    frame = daily.copy()
    if "date" in frame.columns:
        frame = frame.set_index("date")
    frame.index = pd.to_datetime(frame.index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame[frame.index.date < day]
    atr, previous = None, None
    readings: list = []
    for i, (high, low, close) in enumerate(zip(frame["high"], frame["low"], frame["close"])):
        high, low, close = float(high), float(low), float(close)
        tr = high - low if previous is None else max(high - low, abs(high - previous), abs(low - previous))
        atr = tr if atr is None else atr + (tr - atr) / 14
        if i >= 14:
            readings.append(atr / close * 100)
        previous = close
    if not readings:
        return None, None
    earlier = [v for v in readings[:-1] if _num(v)][-VOL_WINDOW:]
    return readings[-1], (median(earlier) if len(earlier) >= VOL_NEED else None)


def vol_up(atr_pct: Optional[float], usual: Optional[float], ratio: float = 1.0) -> bool:
    """At or above the usual level times ``ratio``. With no reading: False, which means one lot and no comfort for the stand-aside."""
    return _num(atr_pct) and _num(usual) and atr_pct >= usual * ratio


def stand_aside(above_line: bool, nets: Sequence[float], need: int = 20) -> bool:
    """Real entries wait while BOTH readings are against the book. With too little history nothing is known, and nothing waits."""
    return (not above_line) and len(nets) >= need and sum(nets[-need:]) <= 0


def lot_ceiling(strategy: Optional[str], minute: int, is_vol_up: bool, realised: float) -> int:
    """The most this trade may take before the planner's own budget. Size only: it never refuses a trade."""
    if not is_vol_up or realised < 0:
        return 1
    if strategy == LOW and minute >= int(settings.FNO_N11_LOW_TWO_LOTS_BEFORE_MIN):
        return 1
    return LOT_CAP


def eff_clock(age_min: float, trail_active: Any, bid: float, entry_premium: float, qty: int, lots: int, progress_r: float,
              exchange: str = "NFO") -> float:
    """EFF's soft clock (research N04-N07): 30 minutes when, between 30 and 60 minutes in, an untrailed trade with under half a
    stop's progress is losing after costs and its option has not gained. Otherwise its usual 60."""
    if not 30 <= age_min < 60 or trail_active or not _num(bid) or bid <= 0 or not _num(progress_r) or progress_r >= 0.5:
        return 60.0
    net = (bid - entry_premium) * qty - calc_fno_costs(entry_premium, bid, qty, exchange=exchange) - extra_cost(lots)
    return 30.0 if net <= 0 and bid <= entry_premium else 60.0


def budget(pool: float, multiplier: float) -> float:
    """The most an add may plan to lose: the planner's two limits and the owner's flat limit, scaled down in a drawdown, never up."""
    scale = max(0.0, float(multiplier))
    return min(pool * float(settings.FNO_MAX_RISK_PCT) * scale, float(settings.FNO_MAX_LOSS_PER_TRADE) * scale,
               float(settings.FNO_N11_ADD_MAX_RUPEES) * min(1.0, scale))


def adverse_distance(direction: str, future: float, level: float) -> float:
    return max(0.0, (1 if direction == "LONG" else -1) * (future - level))


def parent_loss_at_stop(direction: str, future: float, bid: float, delta: float, level: float, entry: float, premium_stop: float,
                        qty: int, extra: float, fees: Callable) -> float:
    """What the held lots are expected to lose if the underlying reaches their current stop. An estimate, not a guarantee: stops can gap."""
    value = max(bid - abs(delta) * adverse_distance(direction, future, level), premium_stop, 0.0)
    return max(0.0, (entry - value) * qty + fees(entry, value, qty) + extra)


def child_full_loss(ask: float, stop_pct: float, qty: int, extra: float, fees: Callable) -> float:
    stop = ask * (1.0 - stop_pct)
    return (ask - stop) * qty + fees(ask, stop, qty) + extra


def is_parent(position: Any) -> bool:
    strategy = position.strategy or ""
    return strategy.startswith(PREFIX) and strategy != ADD


# ---- storage ------------------------------------------------------------------------------------------------------------

_READY: set = set()


async def init_db(db_path: str) -> None:
    if db_path in _READY:
        return
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.execute(_GATE_DDL)
        await db.executemany(
            "INSERT OR IGNORE INTO fno_n11_paper(underlying,bar_ts,strategy,status,exit_time,net,source) "
            "VALUES('NIFTY', ?, 'N08_RESEARCH', 'CLOSED', ?, ?, ?)",
            [(f"seed:{i:02d}", at, net, SEED_SOURCE) for i, (at, net) in enumerate(SEED_NETS)])
        await db.commit()
    _READY.add(db_path)


async def paper_nets(db_path: str, before: datetime) -> list:
    """Closed paper results with exits strictly before ``before``, oldest first."""
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT net FROM fno_n11_paper WHERE status='CLOSED' AND net IS NOT NULL AND exit_time < ? ORDER BY exit_time, id",
            (before.isoformat(),))).fetchall()
    return [float(r[0]) for r in rows]


async def realised_today(db_path: str, source: str, today_iso: str) -> float:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM fno_positions WHERE source=? AND status='CLOSED' AND exit_date=?",
            (source, today_iso))).fetchone()
    return float(row[0] or 0.0)


async def child_counts(db_path: str, source: str, today_iso: str) -> tuple:
    """(earned lots open now, earned lots entered today): they don't count as trades or positions, as in the research."""
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT COALESCE(SUM(status='OPEN'),0), COALESCE(SUM(entry_date=?),0) FROM fno_positions WHERE source=? AND strategy=?",
            (today_iso, source, ADD))).fetchone()
    return int(row[0]), int(row[1])


async def parent_open(db_path: str, source: str, bar_ts: Optional[str]) -> bool:
    """An earned lot leaves with its held lots. Unreadable link: treated as still open, so its own stops keep protecting it."""
    if not str(bar_ts or "").startswith(ADD_BAR):
        return True
    try:
        parent = int(str(bar_ts)[len(ADD_BAR):])
    except ValueError:
        return True
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT status FROM fno_positions WHERE id=? AND source=?", (parent, source))).fetchone()
    return row is None or row[0] != "CLOSED"


async def _has_child(db_path: str, source: str, parent_id: int) -> bool:
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT 1 FROM fno_positions WHERE source=? AND bar_ts=? LIMIT 1",
                                      (source, f"{ADD_BAR}{parent_id}"))).fetchone()
    return row is not None


# ---- today's gate -------------------------------------------------------------------------------------------------------

_VOL: dict = {}
_VOL_RETRY: dict = {}


async def _volatility(db_path: str, kite, now: datetime) -> Optional[tuple]:
    """(atr_pct, usual) for today, read once a day from 09:30 from the daily candles. A failed read isn't kept: None, retried after a minute."""
    key = (db_path, now.date().isoformat())
    if key in _VOL:
        return _VOL[key]
    if now.hour * 60 + now.minute < VOL_READ_FROM_MIN or monotonic() < _VOL_RETRY.get(key, 0.0):
        return None
    _VOL_RETRY[key] = monotonic() + READ_RETRY_SEC
    day = now.date()
    try:
        daily = await kite.get_historical("NIFTY 50", (day - timedelta(days=VOL_HISTORY_CALENDAR_DAYS)).isoformat(), day.isoformat())
    except Exception as exc:
        logger.warning("fno_n11_vol_read_failed", err=str(exc))
        return None
    atr_pct, usual = vol_reading(daily, day)
    if atr_pct is None or usual is None:
        logger.warning("fno_n11_vol_unavailable", bars=0 if daily is None else len(daily))
        return None
    for stale in [k for k in _VOL if k[1] != day.isoformat()]:
        del _VOL[stale]
    _VOL[key] = (atr_pct, usual)
    try:
        await _record_gate(db_path, now, atr_pct, usual)
    except Exception as exc:      # the day's note, not the reading: the reading stands
        logger.error("fno_n11_gate_note_failed", err=str(exc), exc_info=True)
    return _VOL[key]


async def _record_gate(db_path: str, now: datetime, atr_pct: float, usual: float) -> None:
    await init_db(db_path)
    up, above = vol_up(atr_pct, usual), vol_up(atr_pct, usual, float(settings.FNO_N11_STAND_RATIO))
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("INSERT OR IGNORE INTO fno_n11_gate(session_date,atr_pct,usual,vol_up,above_line,recorded_at) VALUES(?,?,?,?,?,?)",
                               (now.date().isoformat(), atr_pct, usual, int(up), int(above), now.isoformat()))
        first = cur.rowcount == 1
        await db.commit()
    if not first:
        return
    nets = await paper_nets(db_path, now)
    need = int(settings.FNO_N11_STAND_NEED)
    waiting = stand_aside(above, nets, need)
    from operator_alert import notify_operator
    await notify_operator(
        f"🧭 N11 today: volatility {atr_pct / usual:.2f} of usual, so {'two lots allowed' if up else 'one lot'}. "
        f"Last {min(need, len(nets))} paper trades: Rs {sum(nets[-need:]):+,.0f}. "
        f"{'Real paper entries WAIT today until a reading turns.' if waiting else 'Entries are open.'} "
        "Paper only. Nothing here touches real money.", event="fno_n11_gate")


async def gate(db_path: str, kite, now: datetime) -> dict:
    """Today's readings. An unknown volatility reading means one lot, and it counts as below the line."""
    reading = await _volatility(db_path, kite, now)
    atr_pct, usual = reading if reading else (None, None)
    above = vol_up(atr_pct, usual, float(settings.FNO_N11_STAND_RATIO))
    nets = await paper_nets(db_path, now)
    need = int(settings.FNO_N11_STAND_NEED)
    return {"atr_pct": atr_pct, "usual": usual, "vol_up": vol_up(atr_pct, usual), "above_line": above, "paper_sum": sum(nets[-need:]) if nets else 0.0,
            "paper_count": len(nets), "stand": stand_aside(above, nets, need)}


# ---- the paper record: every N11 signal on NIFTY at one lot, brakes off -------------------------------------------------------

async def record_paper_signal(db_path: str, kite, sig, snap, regime: str, now: datetime, *, is_trading_day: bool, is_expiry_day: bool, pool: float) -> bool:
    """Open one paper lot for this signal, through the same planner with no brakes. Never touches a real or paper-book position."""
    from fno_entry_plan import REENTRY_STOP_REASONS, EntryState, plan_single_leg_entry, reentry_level
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if await (await db.execute("SELECT 1 FROM fno_n11_paper WHERE underlying='NIFTY' AND bar_ts=?", (sig.bar_ts,))).fetchone():
            return False
        rows = await (await db.execute("SELECT tradingsymbol,direction,entry_underlying,stop_underlying,status,exit_reason,entry_time "
                                       "FROM fno_n11_paper WHERE source=? AND entry_time >= ?", (PAPER_SOURCE, now.date().isoformat()))).fetchall()
    held = [r for r in rows if r["status"] == "OPEN"]
    levels = {}
    if settings.FNO_REENTRY_REQUIRES_CONFIRMATION:
        for r in rows:
            if r["status"] == "CLOSED" and r["exit_reason"] in REENTRY_STOP_REASONS:
                levels[r["direction"]] = reentry_level(r["direction"], float(r["entry_underlying"]), float(r["stop_underlying"]), float(settings.FNO_REENTRY_MARGIN_R))

    def state(ceiling: int) -> EntryState:
        return EntryState(pool=pool, open_premium=0.0, open_positions=len(held), trades_today=len(rows), active_kill_switches=(),
                          held_symbols=frozenset(r["tradingsymbol"] for r in held), is_trading_day=is_trading_day, is_expiry_day=is_expiry_day,
                          risk_multiplier=1.0, reentry_levels=levels, lot_ceiling=ceiling)

    plan = plan_single_leg_entry(sig, snap, regime, now, state(1))
    if not plan.accepted:
        return False
    minute = now.hour * 60 + now.minute
    two_before = int(settings.FNO_N11_LOW_TWO_LOTS_BEFORE_MIN)
    wider = plan_single_leg_entry(sig, snap, regime, now, state(1 if sig.strategy == LOW and minute >= two_before else LOT_CAP))
    today = await gate(db_path, kite, now)
    quote, ask = plan.quote, plan.quote.ask
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO fno_n11_paper(underlying,bar_ts,strategy,direction,tradingsymbol,token,lot_size,entry_time,entry_premium,entry_underlying,"
            "stop_underlying,target_underlying,premium_stop,atr_at_entry,delta_at_entry,best_underlying,native_lots,vol_lots,stood_aside,status,source) "
            "VALUES('NIFTY',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'OPEN',?)",
            (sig.bar_ts, sig.strategy, sig.direction.value, quote.contract.tradingsymbol, quote.contract.token, plan.lot_size, now.isoformat(), ask,
             float(snap.forward), float(sig.stop_underlying), float(sig.target_underlying), round((1.0 - float(settings.FNO_STOP_PREMIUM_PCT)) * ask, 2),
             float(sig.atr), float(plan.delta), float(snap.forward), int(wider.lots) if wider.accepted else 1, 2 if today["vol_up"] else 1, int(today["stand"]), PAPER_SOURCE))
        await db.commit()
    return True


_PAPER_LOCK: dict = {}
_PAPER_LAST: dict = {}


async def manage_paper(kite, db_path: str, now: datetime, fut_prices: dict, read_quote: Callable) -> int:
    """Walk the open paper lots through the same exit ladder, about once a minute, as the research did. Closes what the ladder closes."""
    from fno_book import exit_overrides
    from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT * FROM fno_n11_paper WHERE status='OPEN' AND source=?", (PAPER_SOURCE,))).fetchall()
    if not rows:
        return 0
    today = now.date().isoformat()
    stale = [r["id"] for r in rows if str(r["entry_time"])[:10] != today]
    if stale:      # the engine was down at the close: no price to book, so these never enter the record
        async with aiosqlite.connect(db_path) as db:
            await db.executemany("UPDATE fno_n11_paper SET status='UNRESOLVED', exit_reason='engine_down_at_close' WHERE id=?", [(i,) for i in stale])
            await db.commit()
        rows = [r for r in rows if r["id"] not in stale]
        if not rows:
            return 0
    hard_flat = now.hour * 60 + now.minute >= settings.FNO_HARD_FLAT_MIN
    if not hard_flat and monotonic() - _PAPER_LAST.get(db_path, -1e9) < 55.0:
        return 0
    _PAPER_LAST[db_path] = monotonic()
    tokens = sorted({int(r["token"]) for r in rows})
    quotes, _timing = await asyncio.wait_for(read_quote(kite, tokens), timeout=float(settings.FNO_EXIT_QUOTE_READ_MAX_SEC))
    future = fut_prices.get("NIFTY")
    closed = 0
    for r in rows:
        q = quotes.get(int(r["token"])) or {}
        buys = (q.get("depth") or {}).get("buy") or []
        bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
        basis = bid if bid > 0 else float(q.get("last_price") or 0.0)
        p = SimpleNamespace(**{k: r[k] for k in ("direction", "entry_underlying", "stop_underlying", "target_underlying", "atr_at_entry", "entry_premium",
                                                 "premium_stop", "entry_time", "trail_active", "trail_stop_underlying", "best_underlying", "best_premium")})
        params = {**live_single_leg_exit_params(settings), **exit_overrides(r["strategy"])}
        if r["strategy"] == "N11_EFF" and future:
            risk = abs(p.entry_underlying - p.stop_underlying)
            progress = (1 if p.direction == "LONG" else -1) * (future - p.entry_underlying) / risk if risk > 0 else 0.0
            age = (now - datetime.fromisoformat(p.entry_time)).total_seconds() / 60.0
            params["FNO_TIME_STOP_MIN"] = eff_clock(age, p.trail_active, bid, p.entry_premium, int(r["lot_size"]), 1, progress)
        decision = evaluate_single_leg_exit(p, now_ist=now, fut_price=future, exit_px_basis=basis, hard_flat=hard_flat, params=params,
                                            lock_breach_since=_PAPER_LOCK.get(r["id"]))
        if decision.lock_breach_since is not None and not decision.exit_reason:
            _PAPER_LOCK[r["id"]] = decision.lock_breach_since
        else:
            _PAPER_LOCK.pop(r["id"], None)
        async with aiosqlite.connect(db_path) as db:
            if decision.exit_reason and basis > 0:
                qty = int(r["lot_size"])
                net = (basis - p.entry_premium) * qty - calc_fno_costs(p.entry_premium, basis, qty) - extra_cost(1)
                await db.execute("UPDATE fno_n11_paper SET status='CLOSED', exit_time=?, exit_premium=?, exit_reason=?, net=? WHERE id=? AND status='OPEN'",
                                 (now.isoformat(), basis, decision.exit_reason, net, r["id"]))
                closed += 1
            elif decision.persist_trail:
                await db.execute("UPDATE fno_n11_paper SET trail_active=?, trail_stop_underlying=?, best_underlying=?, best_premium=? WHERE id=?",
                                 (1 if decision.trail_active else 0, decision.trail_stop, decision.best_underlying, decision.best_premium, r["id"]))
            await db.commit()
    return closed


# ---- the honest earned lot --------------------------------------------------------------------------------------------------

async def maybe_add(kite, db_path: str, source: str, executor, now: datetime, fut_prices: dict, pool_rs: float, equity_reader: Callable, read_quote: Callable) -> list:
    """One more lot on a working two-lot paper trade, under the written charge. A refused look changes nothing and is asked again at the next one."""
    import fno_positions as fpos
    from fno_adaptive_risk import policy_from_settings as adaptive_policy, read_book_closes, risk_stance
    from fno_shared_risk import (EntryOccupancy, claim_shared_fno_entry_dispatch, policy_from_settings, reserve_shared_fno_risk,
                                 resolve_shared_fno_entry_dispatch, shared_fno_entry_policy)
    if now.hour * 60 + now.minute >= settings.FNO_ENTRY_END_MIN:
        return []
    rows = await fpos.open_positions(db_path, source)
    added: list = []
    for p in rows:
        if not is_parent(p) or int(p.lots) < 2:
            continue
        future = fut_prices.get((p.underlying or "NIFTY").upper())
        risk_points = abs(p.entry_underlying - p.stop_underlying)
        if not future or risk_points <= 0:
            continue
        if (1 if p.direction == "LONG" else -1) * (future - p.entry_underlying) / risk_points < ADD_AT_R:
            continue
        if await _has_child(db_path, source, p.id):
            continue
        quotes, _timing = await asyncio.wait_for(read_quote(kite, [p.token]), timeout=float(settings.FNO_EXIT_QUOTE_READ_MAX_SEC))
        depth = (quotes.get(p.token) or {}).get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
        ask = float(sells[0]["price"]) if sells and sells[0].get("price") else 0.0
        if bid <= 0 or ask <= 0:
            continue
        policy = policy_from_settings()
        halted = await shared_fno_entry_policy(db_path, source=source, pool_rs=pool_rs, today_ist=now.date(), policy=policy)
        stance = risk_stance(await read_book_closes(db_path, source), allocation=pool_rs, now=now, policy=adaptive_policy())
        if halted.active_halts or stance.single_leg_halted_today:
            continue
        equity = await equity_reader()
        qty = int(p.lot_size)
        open_premium = await fpos.open_premium_committed(db_path, source)
        if open_premium + ask * qty > float(settings.FNO_MAX_OPEN_PREMIUM_PCT) * equity:
            continue
        exchange = options_exchange_for(p.underlying or "NIFTY")
        fees = lambda a, b, n: calc_fno_costs(a, b, n, exchange=exchange)  # noqa: E731
        level = p.trail_stop_underlying if p.trail_active and p.trail_stop_underlying is not None else p.stop_underlying
        stop_pct = float(settings.FNO_STOP_PREMIUM_PCT)
        held = parent_loss_at_stop(p.direction, future, bid, p.delta_at_entry or 0.0, level, p.entry_premium, p.premium_stop, int(p.qty), extra_cost(int(p.lots)), fees)
        child = child_full_loss(ask, stop_pct, qty, extra_cost(1), fees)
        limit = budget(equity, stance.multiplier)
        if held + child > limit:
            continue
        key = f"single:{source}:{p.token}:{ADD_BAR}{p.id}"
        worst = ask * qty + calc_fno_costs(ask, 0.0, qty, exchange=exchange)
        admission = await reserve_shared_fno_risk(db_path, source=source, pool_rs=pool_rs, reservation_key=key, book="SINGLE_LEG",
                                                  worst_case_cash_rs=worst, entry_day_ist=now.date(), policy=policy)
        if not admission.allowed:
            logger.info("fno_n11_add_skip", id=p.id, reason=admission.reason)
            continue
        claim = await claim_shared_fno_entry_dispatch(
            db_path, reservation_key=key, source=source, book="SINGLE_LEG", pool_rs=pool_rs, entry_day_ist=now.date(), policy=policy,
            occupancy=EntryOccupancy(entry_day=now.date(), max_open=1000, tradingsymbol=p.tradingsymbol, planned_premium_rs=ask * qty, max_trades_per_day=1000,
                                     max_open_premium_rs=float(settings.FNO_MAX_OPEN_PREMIUM_PCT) * equity, no_pyramid=False))
        if not claim.granted:
            logger.info("fno_n11_add_skip", id=p.id, reason=claim.reason)
            continue
        exchange_kw = {} if exchange == "NFO" else {"exchange": exchange}
        result = await executor.execute_entry(p.tradingsymbol, qty, ask, **exchange_kw)
        if result["status"] != "paper":
            await resolve_shared_fno_entry_dispatch(db_path, reservation_key=key, owner=claim.owner, outcome="no_dispatch",
                                                    evidence={"dispatch_certainty": "NOT_SENT", "order_id": None, "reason": "n11_add_paper_only"})
            logger.critical("fno_n11_add_not_paper", id=p.id, status=result["status"])
            continue
        fill = float(result["fill_price"])
        now_iso = now.isoformat()
        far = 1e7 * (1 if p.direction == "LONG" else -1)
        await fpos.insert_position_with_risk_reservation(
            db_path, reservation_key=key, source=source, tradingsymbol=p.tradingsymbol, token=p.token, underlying=p.underlying, expiry=p.expiry, strike=p.strike,
            opt_type=p.opt_type, direction=p.direction, lots=1, lot_size=qty, qty=qty, entry_time=now_iso, entry_date=now.date().isoformat(), entry_premium=fill,
            entry_underlying=future, delta_at_entry=p.delta_at_entry, iv_at_entry=p.iv_at_entry, atr_at_entry=p.atr_at_entry, stop_underlying=p.entry_underlying,
            target_underlying=p.entry_underlying + far, premium_stop=round((1.0 - stop_pct) * fill, 2), trail_active=0, trail_stop_underlying=None,
            best_underlying=future, max_loss_rupees=fill * qty, status="OPEN", entry_order_id=result.get("order_id"), bar_ts=f"{ADD_BAR}{p.id}", strategy=ADD)
        logger.info("fno_n11_earned_lot", parent=p.id, symbol=p.tradingsymbol, ask=fill, held_charge=round(held, 2), child_charge=round(child, 2), limit=round(limit, 2))
        added.append({"symbol": p.tradingsymbol, "direction": p.direction, "lots": 1, "fill": fill, "source": source, "strategy": ADD})
    return added


# ---- the shadows: the same paper trades at each earlier book's sizes -----------------------------------------------------------

def shadow_table(rows: Sequence[Any]) -> dict:
    """Today's paper trades at each earlier book's size. N08 takes its own lots; the others also size by volatility. Reserve, floor, stand-aside and
    earned lots aren't modelled here: same trades, different size, a plain comparison."""
    def net(r, lots: int) -> float:
        qty = int(r["lot_size"]) * lots
        return (r["exit_premium"] - r["entry_premium"]) * qty - calc_fno_costs(r["entry_premium"], r["exit_premium"], qty) - extra_cost(lots)
    done = [r for r in rows if r["net"] is not None and r["exit_premium"] is not None]
    return {"trades": len(done), "one_lot": sum(net(r, 1) for r in done), "N08": sum(net(r, int(r["native_lots"] or 1)) for r in done),
            "size_by_volatility": sum(net(r, min(int(r["native_lots"] or 1), int(r["vol_lots"] or 1))) for r in done)}


async def send_shadow_report_once(db_path: str, now: datetime) -> bool:
    """Once a day after the close of F&O entries and exits: what N11 did, and the shadows beside it."""
    if now.hour * 60 + now.minute < SHADOW_REPORT_FROM_MIN:
        return False
    day = now.date().isoformat()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        gate_row = await (await db.execute("SELECT shadow_reported_at FROM fno_n11_gate WHERE session_date=?", (day,))).fetchone()
        if gate_row is None or gate_row["shadow_reported_at"]:
            return False
        rows = await (await db.execute("SELECT * FROM fno_n11_paper WHERE source=? AND entry_time >= ? AND entry_time < ?",
                                       (PAPER_SOURCE, day, (now.date() + timedelta(days=1)).isoformat()))).fetchall()
        if any(r["status"] == "OPEN" for r in rows):
            return False
        real = await (await db.execute("SELECT COALESCE(SUM(pnl),0), COUNT(*) FROM fno_positions WHERE source='FNO_PAPER' AND entry_date=? AND strategy LIKE 'N11_%' AND status='CLOSED'", (day,))).fetchone()
        await db.execute("UPDATE fno_n11_gate SET shadow_reported_at=? WHERE session_date=?", (now.isoformat(), day))
        await db.commit()
    table = shadow_table(rows)
    waited = sum(int(r["stood_aside"]) for r in rows)
    from operator_alert import notify_operator
    await notify_operator(
        f"📊 N11 paper today: Rs {float(real[0]):+,.0f} on {int(real[1])} positions, before the research's assumed extra cost. "
        f"Shadows, the same {table['trades']} paper signals with that cost included: one lot Rs {table['one_lot']:+,.0f}, N08's sizes Rs {table['N08']:+,.0f}, "
        f"size by volatility (N09 to N10.1) Rs {table['size_by_volatility']:+,.0f}. {waited} signal(s) stood aside. "
        "Their reserves, floors and earned lots aren't modelled in this line.", event="fno_n11_shadow_report")
    return True


async def tick(kite, db_path: str, *, executor, now: datetime, fut_prices: dict, pool_rs: float, equity_reader: Callable, read_quote: Callable, source: str = "FNO_PAPER") -> list:
    """Everything N11 does on a management tick. The caller guards it: nothing here can stop an exit. Each step guards itself too, so one failing step can't stop the others."""
    await init_db(db_path)
    try:
        await _volatility(db_path, kite, now)
    except Exception as exc:
        logger.error("fno_n11_gate_failed", err=str(exc), exc_info=True)
    try:
        await manage_paper(kite, db_path, now, fut_prices, read_quote)
    except Exception as exc:
        logger.error("fno_n11_paper_failed", err=str(exc), exc_info=True)
    added: list = []
    try:
        added = await maybe_add(kite, db_path, source, executor, now, fut_prices, pool_rs, equity_reader, read_quote)
    except Exception as exc:
        logger.error("fno_n11_add_failed", err=str(exc), exc_info=True)
    try:
        await send_shadow_report_once(db_path, now)
    except Exception as exc:
        logger.error("fno_n11_shadow_report_failed", err=str(exc), exc_info=True)
    return added
