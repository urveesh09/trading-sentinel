"""[O25 2026-10-25] The owner's real-money F&O test: own cash, one lot, the paper book's trades.

The owner's decision (Oct 25): after a five-session paper proving week
(fno_proving_week.py), put FNO_LIVE_TEST_CAPITAL (₹12,500) of real money on the
pure intraday single-leg F&O book for about a week, with the investment and
risk guardrails relaxed, to see how the system trades with real fills. It is
one switch, FNO_LIVE_TEST_ENABLED; it is off unless the owner sets it.

What the test does
  - It never decides a trade. When the paper book buys an option, the test
    buys ONE lot of the same contract on the same signal bar (``mirror_entry``),
    so the signal, strike, gates, reward/risk, the paper book's own size tiers,
    loss brakes and drawdown halt all decide for both. Its exits are the same
    ladder on its own fill (fno_orchestrator: underlying stop and target from the
    same signal, the 25% premium stop, trail, profit lock, time stop, 15:10 hard
    flat), plus a resting broker stop-loss (fno_broker_backstop).
  - The buy is a LIMIT at the fresh ask plus FNO_LIVE_TEST_ENTRY_BUFFER_TICKS
    (it trades at the ask or better). It is skipped when that ask is more than
    FNO_LIVE_TEST_MAX_CHASE_PCT above the paper book's price, when the quote is
    stale or one-sided, or when its spread is over FNO_MAX_SPREAD_PCT; an
    unfilled order is cancelled after FNO_FILL_TIMEOUT_SEC (never chased).

What is relaxed, and only here
  - The 2%-of-pool risk per trade, the minimum-viable-pool and open-premium
    gates, and the live go-live bar (fno_risk.fno_go_live_check). One lot at
    the 25% stop risks about ₹1.5k-3.7k: 12-30% of ₹12,500 per losing trade.

What is kept
  - Own cash only: kite_client refuses a BUY that its own free cash in the
    account cannot pay (no margin, no leverage), and the shared F&O ledger
    reserves the trade's whole premium against the test's own equity.
  - NIFTY (NFO) only, never on its expiry day, one open position, at most
    FNO_MAX_TRADES_PER_DAY entries, MIS, LIMIT orders only.
  - The floor: no new entry while test equity (capital plus realised real P&L)
    is under FNO_LIVE_TEST_FLOOR; the owner is told once a day.

Switching it off stops new entries only: an open real position is still
managed to its exit (fno_orchestrator._live_leg_managed).

[O25b 2026-10-25] After the audit-agent review:
  - NIFTY is enforced here, in the admission itself (an NFO segment is not
    NIFTY: BANKNIFTY would have passed the orchestrator's check).
  - A run is bounded: FNO_LIVE_TEST_RUN names it. Its authorized start/end
    dates and session limit are persisted, so delayed startup or an environment
    change cannot extend it. Defaults are Nov 2-6, 2026 (five sessions).
    Legacy rows without an end date cannot admit entries. A new run needs a
    new name and explicit dates. Exits remain active after the entry window.
  - Every real execution step is kept (``fno_live_execution_events``), and the
    evening report shows decision-to-fill delay, slippage against the paper
    twin, refused price changes, the broker stop's state and outstanding work.
  - One-lot economics come from the fills and the full one-lot charges
    (``one_lot_pnl``), never a multi-lot P&L divided by its lots: the fixed
    brokerage is paid per order, whatever the size.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

import aiosqlite
import structlog

from config import settings
from fno_models import FnoSource

logger = structlog.get_logger()
SOURCE = FnoSource.FNO_LIVE.value
PAPER = FnoSource.FNO_PAPER.value
UNDERLYING = "NIFTY"
# fno_live_preflight's filled test buy is handed to the engine under this bar;
# fno_orchestrator sells such a position at once (exit reason preflight_flatten).
PREFLIGHT_BAR = "PREFLIGHT"
_FLOOR_TOLD: set = set()
_RUN_END_TOLD: set = set()
_EVENTS_DDL = ("CREATE TABLE IF NOT EXISTS fno_live_execution_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
               "position_id INTEGER, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT)")
_RUNS_DDL = ("CREATE TABLE IF NOT EXISTS fno_live_test_runs (label TEXT PRIMARY KEY, started_on TEXT NOT NULL, "
             "sessions INTEGER NOT NULL, capital REAL NOT NULL, floor REAL NOT NULL, release TEXT, "
             "created_at TEXT NOT NULL, ends_on TEXT)")


def one_lot_pnl(entry: float, exit_: float, lot_size: int, underlying: str = UNDERLYING) -> float:
    """One lot's net P&L from its two fills and its own full charges."""
    from fno_costs import calc_fno_costs, options_exchange_for
    qty = int(lot_size)
    return (float(exit_) - float(entry)) * qty - calc_fno_costs(
        float(entry), float(exit_), qty, exchange=options_exchange_for(underlying))


async def record_event(db_path: str, position_id: Optional[int], kind: str, detail: Optional[dict] = None) -> None:
    """Keep one real execution step as evidence; never raises (evidence never blocks an order)."""
    import json
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(_EVENTS_DDL)
            await db.execute("INSERT INTO fno_live_execution_events(position_id, at, kind, detail) VALUES(?,?,?,?)",
                             (position_id, datetime.now().astimezone().isoformat(), kind,
                              json.dumps(detail or {}, default=str, sort_keys=True)[:2000]))
            await db.commit()
    except Exception as exc:
        logger.error("fno_live_execution_event_failed kind=%s err=%s", kind, str(exc))


async def current_run(db_path: str, today) -> Optional[dict]:
    """The named run's frozen authorization, independent of first observation.

    Legacy rows without an end date remain unavailable for new entries. A
    new name and explicit dates are required to authorize another run.
    """
    if not armed():
        return None
    from market_calendar import is_trading_day_sync
    from release_identity import release_identity
    from datetime import date, timedelta
    label = str(getattr(settings, "FNO_LIVE_TEST_RUN", "1") or "1")
    # [O25f] A malformed authorization never raises: raising here lost the 09:25 message and the whole
    # 15:50 report (the proving-week verdict with it). The run is reported as unavailable instead, and
    # mirror_entry refuses on that (live_test_run_window_unavailable). Nothing is written for it.
    try:
        start = date.fromisoformat(str(settings.FNO_LIVE_TEST_START_DATE))
        end = date.fromisoformat(str(settings.FNO_LIVE_TEST_END_DATE))
        limit = int(settings.FNO_LIVE_TEST_SESSIONS)
        invalid = None if start <= end and limit >= 1 else "the end is before the start, or no sessions"
    except (TypeError, ValueError) as exc:
        invalid = f"unreadable ({exc})"
    if invalid:
        logger.error("fno_live_test_run_authorization_invalid label=%s reason=%s", label, invalid)
        return {"label": label, "started_on": str(settings.FNO_LIVE_TEST_START_DATE), "capital": 0.0,
                "floor": 0.0, "release": "", "sessions": 0, "session": 0,
                "ends_on": str(settings.FNO_LIVE_TEST_END_DATE), "window_available": False,
                "invalid": f"FNO_LIVE_TEST_START_DATE/END_DATE/SESSIONS {invalid}",
                "not_started": False, "ended": False}
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(_RUNS_DDL)
        columns = {r[1] for r in await (await db.execute("PRAGMA table_info(fno_live_test_runs)")).fetchall()}
        if "ends_on" not in columns:
            await db.execute("ALTER TABLE fno_live_test_runs ADD COLUMN ends_on TEXT")
        await db.execute(
            "INSERT OR IGNORE INTO fno_live_test_runs(label, started_on, sessions, capital, floor, release, "
            "created_at, ends_on) VALUES(?,?,?,?,?,?,?,?)",
            (label, start.isoformat(), int(settings.FNO_LIVE_TEST_SESSIONS), float(settings.FNO_LIVE_TEST_CAPITAL),
             float(settings.FNO_LIVE_TEST_FLOOR), str(release_identity()["revision"]),
             datetime.now().astimezone().isoformat(), end.isoformat()))
        row = await (await db.execute(
            "SELECT started_on, capital, floor, release, sessions, ends_on "
            "FROM fno_live_test_runs WHERE label=?", (label,))).fetchone()
        await db.commit()
    started = date.fromisoformat(row[0])
    ends = date.fromisoformat(row[5]) if row[5] else None
    session, day = 0, started
    while day <= today:
        if is_trading_day_sync(day, db_path):
            session += 1
        day += timedelta(days=1)
    sessions = int(row[4])
    return {"label": label, "started_on": row[0], "capital": float(row[1]), "floor": float(row[2]),
            "release": row[3], "sessions": sessions, "session": session, "ends_on": row[5],
            "window_available": ends is not None and ends >= started and sessions > 0,
            "not_started": today < started, "ended": session > sessions or (ends is not None and today > ends)}


async def _tell_run_ended_once(run: dict) -> None:
    if run["label"] in _RUN_END_TOLD:
        return
    try:
        from operator_alert import notify_operator
        told = await notify_operator(
            f"🏁 REAL-money F&O test run {run['label']} has ended: {run['sessions']} sessions from "
            f"{run['started_on']}. No new real trades. To run again, set FNO_LIVE_TEST_RUN to a new name; to stop, "
            "set FNO_LIVE_TEST_ENABLED=false.", event="fno_live_test_run_ended")
        if told:
            _RUN_END_TOLD.add(run["label"])
    except Exception as exc:
        logger.error("fno_live_test_run_end_notice_failed err=%s", str(exc))


def armed() -> bool:
    return bool(getattr(settings, "FNO_LIVE_TEST_ENABLED", False))


def live_pool() -> float:
    """The live leg's allocation: the test capital while the test is on."""
    return float(settings.FNO_LIVE_TEST_CAPITAL) if armed() else float(settings.FNO_LIVE_BANKROLL)


def entry_limit(ask: float, tick: float, buffer_ticks: int, cap: float) -> Optional[float]:
    """The buy LIMIT: the ask on the tick grid plus the buffer, never over ``cap``
    (the chase limit) and never under the ask; None when the ask is over the cap."""
    if ask <= 0 or tick <= 0:
        return None
    on_grid = math.ceil(round(ask / tick, 6)) * tick
    if on_grid > cap + 1e-9:
        return None
    capped = math.floor(round(cap / tick, 6)) * tick
    return round(max(on_grid, min(on_grid + buffer_ticks * tick, capped)), 2)


async def live_equity(db_path: str) -> Optional[float]:
    """Capital plus realised real P&L; None when the ledger cannot be read (fail closed)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            exists = await (await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bankroll_ledger'")).fetchone()
            if exists is None:
                return live_pool()
            row = await (await db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger WHERE source=?", (SOURCE,))).fetchone()
        return live_pool() + float(row[0] or 0.0)
    except Exception as exc:
        logger.error("fno_live_test_equity_unreadable err=%s", str(exc))
        return None


async def _paper_row(db_path: str, bar_ts: str, symbol: str, underlying: str) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM fno_positions WHERE source=? AND bar_ts=? AND tradingsymbol=? AND underlying=? "
            "ORDER BY id DESC LIMIT 1", (PAPER, bar_ts, symbol, underlying))).fetchone()
    return dict(row) if row else None


async def _fresh_quote(kite, contract):
    """The contract's quote right now (management lane); None when unreadable."""
    from fno_chain import _parse_quote_entry
    from kite_client import provider_lane
    try:
        with provider_lane("management"):
            observed = getattr(type(kite), "get_quote_with_timing", None)
            if callable(observed):
                raw, _timing = await observed(kite, [contract.token], priority="management")
            else:
                raw = await kite.get_quote([contract.token])
    except Exception as exc:
        logger.error("fno_live_test_quote_failed symbol=%s err=%s", contract.tradingsymbol, str(exc))
        return None
    q = (raw or {}).get(contract.token)
    return _parse_quote_entry(contract, q) if q else None


def _contract_for(row: dict, instruments):
    from datetime import date
    from fno_models import Contract, OptionType
    expiry = date.fromisoformat(row["expiry"])
    found = None
    try:
        found = instruments.option(expiry, float(row["strike"]), OptionType(row["opt_type"]))
    except Exception:
        found = None
    if found is not None and found.tradingsymbol == row["tradingsymbol"]:
        return found
    return Contract(token=int(row["token"]), tradingsymbol=row["tradingsymbol"], name=row["underlying"],
                    expiry=expiry, strike=float(row["strike"]), instrument_type=row["opt_type"],
                    lot_size=int(row["lot_size"]), tick_size=float(settings.FNO_TICK_SIZE))


async def _tell_floor_once(now_ist: datetime, equity: float) -> None:
    day = now_ist.date().isoformat()
    if day in _FLOOR_TOLD:
        return
    try:
        from operator_alert import notify_operator
        told = await notify_operator(
            f"🛑 REAL-money F&O test: equity ₹{equity:,.0f} is under its floor "
            f"₹{settings.FNO_LIVE_TEST_FLOOR:,.0f} (it started with ₹{live_pool():,.0f}). No new real trades; the "
            "paper book carries on. Lowering the floor, adding capital or ending the test is your decision.",
            event="fno_live_test_floor")
        if told:                       # an undelivered notice is tried again on the next refusal
            _FLOOR_TOLD.add(day)
    except Exception as exc:
        logger.error("fno_live_test_floor_notice_failed err=%s", str(exc))


async def mirror_entry(kite, db_path: str, executor, *, sig, paper_entry: dict, underlying: str, instruments,
                       regime: str, now_ist: datetime, scan_id: str, action_clock=None) -> Optional[dict]:
    """Buy one real lot of the contract the paper book just bought; the entry
    record, or None (every refusal is logged as a FNO_LIVE signal row)."""
    from fno_costs import calc_fno_costs
    from fno_models import Leg, OptionType
    from fno_risk import validate_position
    from fno_signal_log import log_fno_signal
    import fno_positions as fpos

    if not armed():
        return None
    symbol = paper_entry.get("symbol") or ""

    async def _log(accepted: bool, reason: str, **extra):
        try:
            await log_fno_signal(db_path, scan_id=scan_id, leg=SOURCE, accepted=accepted, reject_reason=reason,
                                 bar_ts=sig.bar_ts, underlying=underlying,
                                 direction=sig.direction.value if sig.direction else None, regime=regime,
                                 tradingsymbol=symbol, **extra)
        except Exception as exc:
            logger.error("fno_live_test_signal_log_failed err=%s", str(exc))
        if not accepted:
            logger.warning("fno_live_test_skip symbol=%s reason=%s", symbol, reason)

    if str(underlying or "").upper() != UNDERLYING:
        await _log(False, "live_test_not_nifty")
        return None
    if getattr(executor, "paper_mode", True):
        await _log(False, "live_test_executor_not_live")
        return None
    today = now_ist.date()
    run = await current_run(db_path, today)
    if run is not None and not run["window_available"]:
        await _log(False, "live_test_run_window_unavailable")
        return None
    if run is not None and run["not_started"]:
        await _log(False, "live_test_run_not_started")
        return None
    if run is None or run["ended"]:
        await _log(False, "live_test_run_ended")
        if run is not None:
            await _tell_run_ended_once(run)
        return None
    if instruments.is_expiry_day(today):
        # The owner excluded expiry trading from this test; held even if
        # FNO_EXPIRY_DAY_ENTRIES is ever switched on for paper.
        await _log(False, "live_test_expiry_day")
        return None
    row = await _paper_row(db_path, sig.bar_ts, symbol, underlying)
    if row is None:
        await _log(False, "live_test_paper_row_missing")
        return None
    if await fpos.already_entered_bar(db_path, SOURCE, sig.bar_ts, underlying=underlying):
        return None
    if await fpos.open_positions(db_path, SOURCE):
        await _log(False, "live_test_position_open")
        return None
    if await fpos.trades_today(db_path, SOURCE, today.isoformat()) >= int(settings.FNO_MAX_TRADES_PER_DAY):
        await _log(False, "live_test_trades_per_day")
        return None
    equity = await live_equity(db_path)
    if equity is None:
        await _log(False, "live_test_equity_unreadable")
        return None
    if equity < float(settings.FNO_LIVE_TEST_FLOOR):
        await _log(False, "live_test_floor")
        await _tell_floor_once(now_ist, equity)
        return None

    contract = _contract_for(row, instruments)
    quote = await _fresh_quote(kite, contract)
    clock = action_clock() if action_clock is not None else now_ist
    paper_price = float(row["entry_premium"])
    if quote is None or quote.bid <= 0 or quote.ask <= 0:
        await _log(False, "live_test_no_two_sided_quote")
        return None
    age = (clock - quote.last_trade_time).total_seconds() if quote.last_trade_time else float("inf")
    if age > settings.FNO_MAX_QUOTE_AGE_SEC:
        await _log(False, "live_test_quote_stale", premium=quote.ask)
        return None
    if quote.spread_pct > settings.FNO_MAX_SPREAD_PCT:
        await _log(False, "live_test_spread", premium=quote.ask, spread_pct=quote.spread_pct)
        return None
    tick = float(contract.tick_size or settings.FNO_TICK_SIZE)
    limit = entry_limit(quote.ask, tick, int(settings.FNO_LIVE_TEST_ENTRY_BUFFER_TICKS),
                        paper_price * (1.0 + float(settings.FNO_LIVE_TEST_MAX_CHASE_PCT)))
    if limit is None:
        await _log(False, "live_test_price_ran", premium=quote.ask)
        return None
    lot_size = int(row["lot_size"])
    qty = lot_size                                   # one lot, always
    opt_type = OptionType(row["opt_type"])
    ok, reason, max_loss = validate_position(
        [Leg(opt_type=opt_type, strike=float(row["strike"]), quantity=1, premium=limit)], lot_size)
    if not ok:
        await _log(False, reason, premium=limit, lots=1, max_loss_rupees=max_loss)
        return None
    fields = dict(strike=float(row["strike"]), opt_type=opt_type.value, expiry=row["expiry"], premium=limit,
                  iv=row.get("iv_at_entry"), delta=row.get("delta_at_entry"), spread_pct=quote.spread_pct, lots=1,
                  max_loss_rupees=max_loss, pool_at_eval=round(equity, 2))

    # The same reservation, single dispatch claim and outcome protocol as the
    # paper/live legs (fno_orchestrator._try_entry_for_leg): the whole premium
    # plus exit costs is reserved against the test's own equity first.
    from performance import init_ledger
    import fno_dr_book as _dr
    from fno_shared_risk import (DISPATCH_RELEASE_OUTCOMES, DISPATCH_RETAIN_OUTCOMES, EntryOccupancy,
                                 claim_shared_fno_entry_dispatch, init_shared_fno_risk_db,
                                 reserve_shared_fno_risk, resolve_shared_fno_entry_dispatch)
    await init_ledger(db_path)
    await fpos.init_fno_positions_db(db_path)
    await _dr.init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)
    exchange = instruments.segment
    key = f"single:{SOURCE}:{contract.token}:{sig.bar_ts}"
    admission = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=live_pool(), reservation_key=key, book="SINGLE_LEG",
        worst_case_cash_rs=max_loss + calc_fno_costs(limit, 0.0, qty, exchange=exchange),
        entry_day_ist=None, policy=None,
    )
    if not admission.allowed:
        await _log(False, f"live_test_{admission.reason}", **fields)
        return None
    claim = await claim_shared_fno_entry_dispatch(
        db_path, reservation_key=key, source=SOURCE, book="SINGLE_LEG", pool_rs=live_pool(), entry_day_ist=None,
        policy=None, occupancy=EntryOccupancy(
            entry_day=today, max_open=1, tradingsymbol=symbol, planned_premium_rs=limit * qty,
            max_trades_per_day=int(settings.FNO_MAX_TRADES_PER_DAY), max_open_premium_rs=live_pool(),
            no_pyramid=True),
    )
    if not claim.granted:
        await _log(False, f"dispatch_claim_denied:{claim.reason}", **fields)
        return None
    if action_clock is not None:
        late = action_clock()
        minute = late.hour * 60 + late.minute
        stale = (late - quote.last_trade_time).total_seconds() if quote.last_trade_time else float("inf")
        reason = ("run_window" if late.date() != today
                  else "entry_window" if not settings.FNO_ENTRY_START_MIN <= minute < settings.FNO_ENTRY_END_MIN
                  else "quote_freshness" if stale > settings.FNO_MAX_QUOTE_AGE_SEC else None)
        if reason:
            await resolve_shared_fno_entry_dispatch(
                db_path, reservation_key=key, owner=claim.owner, outcome="no_dispatch",
                evidence={"dispatch_certainty": "NOT_SENT", "order_id": None, "reason": f"post_admission_{reason}"})
            await _log(False, f"post_admission_{reason}", **fields)
            return None

    result = await executor.execute_entry(symbol, qty, limit,
                                          **({} if exchange == "NFO" else {"exchange": exchange}))
    status = result["status"]
    if status != "filled":
        outcome = status if status in DISPATCH_RELEASE_OUTCOMES | DISPATCH_RETAIN_OUTCOMES else "unknown"
        applied = await resolve_shared_fno_entry_dispatch(
            db_path, reservation_key=key, owner=claim.owner, outcome=outcome,
            evidence=result.get("evidence") or {"status": status})
        await _log(False, f"entry_{status}", **fields)
        if applied not in DISPATCH_RELEASE_OUTCOMES:
            logger.critical("fno_live_test_entry_unresolved symbol=%s status=%s applied=%s reservation=%s",
                            symbol, status, applied, key)
            await _page(f"⚠️ REAL F&O buy unclear: {symbol} order status {status}. Check Kite: if you hold it, "
                        "sell it there; the system will not trade it.", "fno_live_test_entry_unclear")
        return None

    fill = float(result["fill_price"])
    _ok, _reason, filled_loss = validate_position(
        [Leg(opt_type=opt_type, strike=float(row["strike"]), quantity=1, premium=fill)], lot_size)
    try:
        position_id = await fpos.insert_position_with_risk_reservation(
            db_path, reservation_key=key,
            source=SOURCE, tradingsymbol=symbol, token=contract.token, underlying=underlying,
            expiry=row["expiry"], strike=float(row["strike"]), opt_type=opt_type.value,
            direction=row["direction"], lots=1, lot_size=lot_size, qty=qty,
            entry_time=clock.isoformat(), entry_date=clock.date().isoformat(), entry_premium=fill,
            entry_underlying=row["entry_underlying"], delta_at_entry=row.get("delta_at_entry"),
            iv_at_entry=row.get("iv_at_entry"), atr_at_entry=row.get("atr_at_entry"),
            stop_underlying=row["stop_underlying"], target_underlying=row["target_underlying"],
            premium_stop=round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2),
            trail_active=0, trail_stop_underlying=None, best_underlying=row["entry_underlying"],
            max_loss_rupees=filled_loss, status="OPEN", entry_order_id=result.get("order_id"),
            bar_ts=sig.bar_ts, strategy=getattr(sig, "strategy", "") or None,   # [O29c] the paper trade's exits
        )
    except Exception as exc:
        await resolve_shared_fno_entry_dispatch(
            db_path, reservation_key=key, owner=claim.owner, outcome="filled_unrecorded",
            evidence={**(result.get("evidence") or {}), "dispatch_certainty": "ACCEPTED",
                      "order_id": result.get("order_id"), "receipt": "position_insert_failed"})
        logger.critical("fno_live_test_fill_unrecorded symbol=%s order_id=%s err=%s", symbol,
                        result.get("order_id"), str(exc))
        await _page(f"🔴 REAL F&O buy filled but NOT recorded: {symbol} x{qty} at ₹{fill:.2f} (order "
                    f"{result.get('order_id')}). The system cannot manage it: sell it in Kite.",
                    "fno_live_test_fill_unrecorded")
        return None
    filled_at = action_clock() if action_clock is not None else now_ist
    try:
        decided = datetime.fromisoformat(str(row["entry_time"]))
        delay = round((filled_at - decided).total_seconds(), 1)
    except (TypeError, ValueError):
        delay = None
    await record_event(db_path, position_id, "entry_filled", {
        "order_id": result.get("order_id"), "limit": limit, "fill": fill, "ask": quote.ask, "paper": paper_price,
        "slippage_per_unit": round(fill - paper_price, 2), "decision_to_fill_sec": delay, "run": run["label"]})
    import fno_broker_backstop
    backstop = await fno_broker_backstop.arm(db_path, executor, position_id=position_id, source=SOURCE,
                                             tradingsymbol=symbol, exchange=exchange, qty=qty, fill=fill,
                                             tick=settings.FNO_TICK_SIZE)
    await record_event(db_path, position_id, "backstop_armed", {"state": backstop.get("state"),
                                                                "trigger": backstop.get("trigger")})
    await _log(True, "", **{**fields, "premium": fill, "max_loss_rupees": filled_loss})
    logger.info("fno_live_test_entry symbol=%s qty=%d fill=%.2f paper=%.2f limit=%.2f order_id=%s", symbol, qty,
                fill, paper_price, limit, result.get("order_id"))
    return {"symbol": symbol, "direction": row["direction"], "lots": 1, "fill": fill,
            "delta": round(float(row.get("delta_at_entry") or 0.0), 2),
            "iv": round(float(row.get("iv_at_entry") or 0.0), 3), "source": SOURCE, "paper_fill": paper_price}


async def _page(text: str, event: str) -> None:
    try:
        from operator_alert import notify_operator
        await notify_operator(text, event=event)
    except Exception as exc:
        logger.error("fno_live_test_page_failed event=%s err=%s", event, str(exc))


def _rs(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}₹{abs(value):,.0f}"


async def _rows(db, sql: str, params: tuple = ()) -> list:
    try:
        return [dict(r) for r in await (await db.execute(sql, params)).fetchall()]
    except aiosqlite.OperationalError as exc:
        if "no such" in str(exc).lower():
            return []
        raise


async def day_report(db_path: str, day_iso: str) -> Optional[str]:
    """The day's real trades beside the paper trade each mirrored, with how
    they were executed and what is still open; None when there is nothing to say."""
    import json
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            trades = await _rows(db,
                "SELECT l.id, l.tradingsymbol, l.status, l.entry_premium, l.exit_premium, l.exit_reason, l.pnl, "
                "l.lot_size, l.underlying, p.entry_premium AS paper_entry, p.exit_premium AS paper_exit, "
                "p.status AS paper_status FROM fno_positions l LEFT JOIN fno_positions p ON p.source=? "
                "AND p.bar_ts=l.bar_ts AND p.tradingsymbol=l.tradingsymbol "
                "WHERE l.source=? AND l.entry_date=? ORDER BY l.id", (PAPER, SOURCE, day_iso))
            ids = [t["id"] for t in trades]
            events = await _rows(db, "SELECT position_id, kind, detail FROM fno_live_execution_events WHERE "
                                     f"position_id IN ({','.join('?' for _ in ids) or 'NULL'}) ORDER BY id", tuple(ids))
            stops = {r["position_id"]: r["state"] for r in await _rows(
                db, "SELECT position_id, state FROM fno_broker_backstops WHERE source=?", (SOURCE,))}
            skipped = await _rows(db, "SELECT reject_reason, COUNT(*) AS n FROM fno_signals WHERE leg=? AND "
                                      "accepted=0 AND bar_ts LIKE ? GROUP BY reject_reason ORDER BY n DESC",
                                  (SOURCE, f"{day_iso}%"))
            open_rows = await _rows(db, "SELECT COUNT(*) AS n FROM fno_positions WHERE source=? AND status='OPEN'",
                                    (SOURCE,))
            claims = await _rows(db, "SELECT COUNT(*) AS n, SUM(order_id IS NOT NULL) AS working FROM "
                                     "fno_exit_intents WHERE source=?", (SOURCE,))
            reserved = await _rows(db, "SELECT COUNT(*) AS n FROM fno_risk_reservations WHERE source=? AND "
                                       "state='RESERVED'", (SOURCE,))
    except Exception as exc:
        logger.error("fno_live_test_day_report_failed err=%s", str(exc))
        return None
    outstanding = {"open": (open_rows[0]["n"] if open_rows else 0) or 0,
                   "claims": (claims[0]["n"] if claims else 0) or 0,
                   "working": (claims[0]["working"] if claims else 0) or 0,
                   "reserved": (reserved[0]["n"] if reserved else 0) or 0}
    if not (trades or skipped or any(outstanding.values()) or armed()):
        return None
    from datetime import date
    try:
        run = await current_run(db_path, date.fromisoformat(day_iso))
    except Exception as exc:             # [O25f] the trades are still reported, and the proving week with them
        logger.error("fno_live_test_day_report_run_failed err=%s", str(exc))
        run = None
    equity = await live_equity(db_path)
    head = f"💰 REAL-money F&O test, {day_iso}: {len(trades)} real trade(s)"
    if run is not None and run.get("invalid"):
        head += f" -- run {run['label']} cannot buy: {run['invalid']}"
    elif run is not None:
        head += (f" -- run {run['label']}, session {min(run['session'], run['sessions'])} of {run['sessions']}"
                 f" (from {run['started_on']}, release {str(run['release'])[:7]})")
    lines = [head]
    by_id: dict = {}
    for e in events:
        by_id.setdefault(e["position_id"], []).append((e["kind"], json.loads(e["detail"] or "{}")))
    real_total = paper_total = 0.0
    for t in trades:
        steps = by_id.get(t["id"], [])
        entry = next((d for k, d in steps if k == "entry_filled"), {})
        refused = sum(1 for k, _ in steps if k == "exit_modify_refused")
        moved = sum(1 for k, _ in steps if k == "exit_modified")
        delay = entry.get("decision_to_fill_sec")
        quality = (f"bought {_slip(t['entry_premium'], t['paper_entry'])} vs paper"
                   + (f", {delay:.0f}s after the paper decision" if isinstance(delay, (int, float)) else ""))
        if t["status"] != "CLOSED":
            lines.append(f"- {t['tradingsymbol']}: real ₹{t['entry_premium']:.2f} (paper ₹{(t['paper_entry'] or 0):.2f}); "
                         f"still {t['status'].lower()}; {quality}; broker stop {stops.get(t['id'], 'none')}")
            continue
        paper_one_lot = (one_lot_pnl(t["paper_entry"], t["paper_exit"], t["lot_size"], t["underlying"])
                         if t["paper_entry"] and t["paper_exit"] else None)
        real_total += float(t["pnl"] or 0.0)
        paper_total += paper_one_lot or 0.0
        lines.append(
            f"- {t['tradingsymbol']}: real ₹{t['entry_premium']:.2f} → ₹{t['exit_premium']:.2f} ({t['exit_reason']}) "
            f"= {_rs(t['pnl'] or 0.0)}; paper ₹{(t['paper_entry'] or 0):.2f} → ₹{(t['paper_exit'] or 0):.2f} = "
            + (f"{_rs(paper_one_lot)} a lot" if paper_one_lot is not None else "still open")
            + f"; {quality}; sold {_slip(t['exit_premium'], t['paper_exit'], selling=True)} vs paper"
            + (f"; exit price moved {moved}x" if moved else "")
            + (f", {refused} change(s) refused" if refused else ""))
    if trades:
        lines.append(f"Real {_rs(real_total)} against paper {_rs(paper_total)} (one lot each, after its own "
                     "charges); the gap is real fills and timing.")
    if skipped:
        lines.append("Paper trades not bought for real: " + ", ".join(f"{r['reject_reason']} x{r['n']}"
                                                                      for r in skipped) + ".")
    if any(outstanding.values()):
        lines.append(f"Outstanding: {outstanding['open']} open real position(s), {outstanding['claims']} exit(s) "
                     f"claimed ({outstanding['working']} still working), {outstanding['reserved']} reservation(s) held.")
    else:
        lines.append("Outstanding: nothing (no open real position, no exit or reservation pending).")
    if equity is not None:
        lines.append(f"Test equity ₹{equity:,.0f} of ₹{live_pool():,.0f} (floor ₹{settings.FNO_LIVE_TEST_FLOOR:,.0f}; "
                     "the floor stops new entries, it cannot cap an open position's loss).")
    return "\n".join(lines)


def _slip(real, paper, *, selling: bool = False) -> str:
    """Real against paper per unit, signed so that positive is worse for us."""
    if not real or not paper:
        return "n/a"
    worse = (float(paper) - float(real)) if selling else (float(real) - float(paper))
    return f"{'+' if worse >= 0 else '-'}₹{abs(worse):.2f}/unit ({worse / float(paper):+.1%} worse)" if worse \
        else "at the same price"


async def hand_off_preflight_fill(db_path: str, *, contract, qty: int, fill: float, order_id: str,
                                  forward: float, now: datetime) -> int:
    """[O25b] Record fno_live_preflight's filled test buy as a real FNO_LIVE
    position, so the engine sells it at once (exit reason preflight_flatten)
    through its full exit path (claim, tag, ladder, follow-up, restart
    recovery), and the owner is told. Returns the position id."""
    import fno_positions as fpos
    from performance import init_ledger
    await init_ledger(db_path)                 # its exit settles into the FNO_LIVE ledger
    await fpos.init_fno_positions_db(db_path)
    position_id = await fpos.insert_position(
        db_path, source=SOURCE, tradingsymbol=contract.tradingsymbol, token=contract.token, underlying=UNDERLYING,
        expiry=contract.expiry.isoformat(), strike=float(contract.strike), opt_type=contract.instrument_type,
        direction="LONG", lots=max(1, qty // int(contract.lot_size)), lot_size=int(contract.lot_size), qty=qty,
        entry_time=now.isoformat(), entry_date=now.date().isoformat(), entry_premium=fill,
        entry_underlying=forward, delta_at_entry=0.0, iv_at_entry=0.0, atr_at_entry=0.0,
        stop_underlying=0.0, target_underlying=forward * 10.0, premium_stop=round(0.75 * fill, 2),
        max_loss_rupees=fill * qty, bar_ts=f"{PREFLIGHT_BAR}-{order_id}", entry_order_id=order_id,
    )
    await record_event(db_path, position_id, "preflight_fill_handed_off", {"order_id": order_id, "fill": fill})
    await _page(f"⚠️ The preflight test BUY filled: {contract.tradingsymbol} x{qty} at ₹{fill:.2f} (order {order_id}). "
                "It is recorded as a real position and the engine sells it now; you will see its exit. If it is "
                "still held in Kite in a few minutes, sell it there.", "fno_live_preflight_filled")
    return position_id


async def typical_lot_cost(db_path: str, last: int = 20) -> Optional[float]:
    """The median cost of one lot over the paper book's last ``last`` single-leg buys."""
    try:
        async with aiosqlite.connect(db_path) as db:
            rows = await (await db.execute(
                "SELECT entry_premium * lot_size FROM fno_positions WHERE source=? AND underlying=? "
                "ORDER BY entry_time DESC LIMIT ?", (PAPER, UNDERLYING, last))).fetchall()
    except aiosqlite.OperationalError:
        return None
    costs = sorted(float(r[0]) for r in rows if r[0])
    return costs[len(costs) // 2] if costs else None


async def morning_check(kite, db_path: str, now: datetime) -> Optional[str]:
    """[O25b] 09:25 on a trading day while the test is on: is it ready to trade
    real money today? One owner message, so nothing has to be run by hand."""
    if not armed():
        return None
    from fno_live_preflight import order_route
    from kite_client import own_uncommitted_cash
    problems, facts = [], []
    route, encrypted, route_problem = order_route()
    if route_problem:
        problems.append(route_problem)
    else:
        facts.append("orders via " + ("an encrypted tunnel" if encrypted else "the relay (plain HTTP)"))
    logged_in = bool(getattr(kite, "access_token", "")) and getattr(kite, "token_set_ist_date", None) == now.date()
    if not logged_in:
        problems.append("no Kite login for today yet: no real trade until you log in")
    else:
        async def read(name):
            method = getattr(type(kite), name, None)
            return await method(kite) if callable(method) else None
        # [O25c] The route itself, not only its setting: an authenticated read through the order client.
        if not route_problem and callable(getattr(type(kite), "probe_order_route", None)):
            try:
                unreachable = await read("probe_order_route")
            except Exception as exc:
                unreachable = f"{type(exc).__name__}"
            if unreachable:
                problems.append(f"the order route does not answer ({unreachable}): check the tunnel on the VM")
        try:
            margins, positions, orders = (await read("get_funds_margins"), await read("get_broker_positions"),
                                          await read("orders_snapshot"))
        except Exception as exc:
            margins = positions = orders = None
            logger.error("fno_live_readiness_read_failed err=%s", str(exc))
        own = own_uncommitted_cash(margins, positions, orders)
        lot = await typical_lot_cost(db_path)
        if own is None:
            problems.append("free cash could not be read")
        else:
            facts.append(f"free cash ₹{own:,.0f}" + (f" (a lot has cost about ₹{lot:,.0f})" if lot else ""))
            if lot and own < lot:
                problems.append(f"free cash ₹{own:,.0f} is under a typical lot (₹{lot:,.0f}): most buys would be "
                                "refused")
        held = [p for p in ((positions or {}).get("net") or []) if isinstance(p, dict)
                and p.get("exchange") in ("NFO", "BFO") and p.get("quantity")]
        if held:
            problems.append("the broker holds F&O positions this morning: " +
                            ", ".join(f"{p.get('tradingsymbol')} {p.get('product')} {p.get('quantity')}" for p in held))
    try:
        run = await current_run(db_path, now.date())
    except Exception as exc:             # [O25f] say so, rather than send no morning message at all
        logger.error("fno_live_readiness_run_failed err=%s", str(exc))
        run = {"label": str(getattr(settings, "FNO_LIVE_TEST_RUN", "1") or "1"), "window_available": False,
               "invalid": f"its record could not be read ({type(exc).__name__})"}
    if not run["window_available"]:
        problems.append(f"run {run['label']}: {run['invalid']}" if run.get("invalid") else
                        "this run has no authorized end date: use a new run name with explicit dates")
    elif run["not_started"]:
        problems.append(f"run {run['label']} starts on {run['started_on']}; no real entry before then")
    elif run["ended"]:
        problems.append(f"run {run['label']} has ended ({run['sessions']} sessions from {run['started_on']})")
    else:
        facts.append(f"run {run['label']}, session {run['session']} of {run['sessions']}")
    equity = await live_equity(db_path)
    if equity is None:
        problems.append("test equity could not be read")
    elif equity < float(settings.FNO_LIVE_TEST_FLOOR):
        problems.append(f"equity ₹{equity:,.0f} is under the floor ₹{settings.FNO_LIVE_TEST_FLOOR:,.0f}")
    else:
        facts.append(f"equity ₹{equity:,.0f} (floor ₹{settings.FNO_LIVE_TEST_FLOOR:,.0f})")
    try:
        async with aiosqlite.connect(db_path) as db:
            carried = (await (await db.execute(
                "SELECT COUNT(*) FROM fno_positions WHERE source=? AND status='OPEN'", (SOURCE,))).fetchone())[0]
            claimed = (await (await db.execute(
                "SELECT COUNT(*) FROM fno_exit_intents WHERE source=?", (SOURCE,))).fetchone())[0]
    except aiosqlite.OperationalError:
        carried = claimed = 0
    if carried or claimed:
        problems.append(f"{carried} real position(s) still open and {claimed} exit(s) claimed from before today: "
                        "reconcile them first")
    if problems:
        return ("⚠️ REAL-money F&O test NOT ready today: " + "; ".join(problems) + "."
                + (" Fine: " + "; ".join(facts) + "." if facts else ""))
    return "✅ REAL-money F&O test ready today: " + "; ".join(facts) + "."
