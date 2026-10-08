"""
[FNO-ORCHESTRATOR 2026-07-10] Dual-leg tick runner for the F&O subsystem
(spec §10.4).

Reuses the EDGE_PAPER / EDGE_LIVE shape from penny_edge_orchestrator:
one candidate scan, two legs, bankroll scales the sizing, separate
source tags (FNO_PAPER / FNO_LIVE) so the legs cannot see each other's
rows. In P1 the live leg is structurally disarmed three ways:
FNO_DISABLE_LIVE=True, FNO_LIVE_TRADING=False, FNO_LIVE_BANKROLL=0 --
and even with all three flipped it still refuses unless
fno_go_live_check() returns [].

run_fno_tick() fires every FNO_SCAN_INTERVAL_SEC during market hours:
  1. manage open positions (stops / target+trail / time stop / 15:10
     hard flat) -- exits are checked BEFORE entries so a stop and a
     same-tick new signal can't double the book
  2. evaluate the FNO-MOM entry on the newest closed 5-min futures bar
     (once per bar per leg -- restart-safe via the bar_ts column)
  3. write EVERY evaluation to the signal log, §9.2

Breadcrumb layers (ops rules 55/56): the main.py wrapper logs
fno_tick_invoked; this module logs fno_orchestrator_tick first-line;
every engine call is wrapped with a distinct log tag.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from time import monotonic
from typing import Callable, List, Optional
from uuid import uuid4

import pytz
import structlog

import fno_positions as fpos
from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
import fno_shadow
from config import settings
from fno_chain import ChainSnapshot, take_chain_snapshot
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_adaptive_risk import policy_from_settings as adaptive_policy, read_book_closes, risk_stance
from fno_entry_plan import EntryState, plan_single_leg_entry
from fno_executor import FnoExecutor
from fno_gates import evaluate_entry_gates_with_trace
from fno_instruments import get_fno_instruments
from fno_models import FnoSource
from fno_risk import kill_switch_status
from fno_shared_risk import (
    DISPATCH_RELEASE_OUTCOMES, DISPATCH_RETAIN_OUTCOMES, EntryOccupancy,
    claim_shared_fno_entry_dispatch,
    init_shared_fno_risk_db, policy_from_settings, reserve_shared_fno_risk,
    resolve_shared_fno_entry_dispatch, shared_fno_entry_policy,
)
from fno_signal_log import log_fno_signal
from fno_underlyings import SPECS, get_instruments_for, trading_underlyings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

RVOL_FETCH_CALENDAR_DAYS = 21   # ~14 sessions of 5-min bars for EMA/RVOL
_SHADOW_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fno-shadow")
_SHADOW_TASKS: set[Future] = set()


def _now_min(now_ist: datetime) -> int:
    return now_ist.hour * 60 + now_ist.minute


def _read_cap(value: float) -> float:
    """Defend a management deadline from an invalid runtime setting."""
    return max(0.1, float(value))


def _record_management_read(
    observations: Optional[dict], name: str, state: str, started: float, cap_sec: float,
    *, provider_timing: Optional[dict] = None, timeout_partial: bool = False,
) -> None:
    """Retain bounded, non-sensitive evidence for one provider read."""
    if observations is not None:
        observation = {
            "state": state,
            "elapsed_sec": round(monotonic() - started, 3),
            "cap_sec": round(cap_sec, 3),
        }
        if provider_timing is None:
            observation["provider_timing_status"] = (
                "PARTIAL_UNAVAILABLE_AFTER_CANCELLATION" if timeout_partial
                else "UNAVAILABLE_CLIENT_INTERFACE"
            )
            if timeout_partial:
                observation["timeout_stage"] = "provider_or_limiter_or_retry_unknown"
        else:
            observation["provider_timing_status"] = "PRESENT"
            for field in (
                "limiter_wait_sec", "transport_sec", "parse_sec", "retry_backoff_sec",
                "attempt_count", "retry_count",
            ):
                value = provider_timing.get(field)
                if isinstance(value, (int, float)) and value >= 0:
                    observation[field] = round(float(value), 6)
        observations[name] = observation


async def _timed_database_operation(timing: Optional[dict], stage: str, operation):
    """Measure an awaited DB stage without changing its cancellation semantics.

    SQLite does not expose lock wait separately from statement execution.  The
    recorded elapsed value therefore deliberately includes both, making a
    contention-induced stall visible without claiming a false exact split.
    This helper never adds a timeout around a mutation.
    """
    started = monotonic()
    try:
        return await operation
    finally:
        if timing is not None:
            stages = timing.setdefault("stages", {})
            current = stages.setdefault(stage, {"calls": 0, "elapsed_sec": 0.0})
            current["calls"] += 1
            current["elapsed_sec"] = round(
                current["elapsed_sec"] + monotonic() - started, 3
            )


async def _management_quote(kite, tokens) -> tuple[dict, Optional[dict]]:
    """Use detailed provider timing when the concrete client exposes it.

    Test/replay adapters deliberately need not implement the observability
    extension.  Their timing is labelled unavailable rather than simulated.
    """
    # Check the concrete type, not an instance attribute: loose test/broker
    # doubles can synthesize arbitrary AsyncMock attributes that are not the
    # tuple-returning observability contract.
    observed = getattr(type(kite), "get_quote_with_timing", None)
    if callable(observed):
        result, timing = await observed(kite, tokens, priority="management")
        return result, timing if isinstance(timing, dict) else None
    return await kite.get_quote(tokens), None


def _oldest_quote_age_sec(quotes: dict, tokens: list[int], now_ist: datetime) -> Optional[float]:
    """Return a conservative exact-leg quote-age observation when supplied."""
    ages: list[float] = []
    for token in tokens:
        raw = (quotes.get(token) or {}).get("last_trade_time")
        if not raw:
            return None
        try:
            observed = datetime.fromisoformat(str(raw))
            if observed.tzinfo is None:
                observed = IST.localize(observed)
            ages.append(max(0.0, (now_ist - observed.astimezone(IST)).total_seconds()))
        except (TypeError, ValueError):
            return None
    return round(max(ages), 3) if ages else None


async def _settle_exit_receipt(
    db_path: str, position, receipt: dict,
) -> Optional[dict]:
    """Commit an acknowledged exit without calling the broker again.

    A receipt is written immediately after an executor reports a fill.  This
    helper consumes it only as part of the atomic position/ledger commit, so
    any local accounting error leaves a durable recovery record.
    """
    try:
        outcome = await fpos.settle_position_close_idempotent(
            db_path,
            position.id,
            int(receipt["settlement_generation"]),
            exit_time_ist=datetime.fromisoformat(receipt["exit_time"]),
            exit_premium=float(receipt["exit_premium"]),
            exit_underlying=float(receipt["exit_underlying"]),
            exit_reason=receipt["exit_reason"],
            gross_pnl=float(receipt["gross_pnl"]),
            costs=float(receipt["costs"]),
            pnl=float(receipt["pnl"]),
            r_multiple=float(receipt["r_multiple"]),
            exit_order_id=receipt["exit_order_id"],
            source=receipt["source"],
            ticker=receipt["ticker"],
            notes=receipt["notes"],
            execution_receipt_id=int(receipt["id"]),
        )
    except Exception as exc:
        logger.error(
            "fno_settle_receipt_failed id=%d symbol=%s receipt_id=%s err=%s "
            "-- broker exit will not be resubmitted; recovery remains pending",
            position.id, position.tradingsymbol, receipt.get("id"), str(exc),
        )
        return None

    if not outcome["settled"]:
        logger.info(
            "fno_settle_receipt_already_applied id=%d symbol=%s receipt_id=%s",
            position.id, position.tradingsymbol, receipt.get("id"),
        )
        return None

    logger.info(
        "fno_position_closed source=%s symbol=%s reason=%s entry=%.2f "
        "exit=%.2f pnl=%.0f r=%.2f receipt_id=%s",
        receipt["source"], position.tradingsymbol, receipt["exit_reason"],
        position.entry_premium, float(receipt["exit_premium"]),
        float(receipt["pnl"]), float(receipt["r_multiple"]), receipt["id"],
    )
    return {
        "symbol": position.tradingsymbol,
        "reason": receipt["exit_reason"],
        "entry": position.entry_premium,
        "exit": float(receipt["exit_premium"]),
        "pnl": float(receipt["pnl"]),
        "r": float(receipt["r_multiple"]),
        "source": receipt["source"],
    }


def _fno_pool_paper() -> float:
    """Static allocation. Prefer `_fno_equity()` -- it adds realised P&L."""
    return float(settings.FNO_PAPER_BANKROLL)


def _fno_pool_live() -> float:
    """Static allocation. Prefer `_fno_equity()` -- it adds realised P&L."""
    return float(settings.FNO_LIVE_BANKROLL)


# A book that has surrendered ``settings.FNO_MAX_DRAWDOWN_PCT`` of its pool
# stops trading. The directional F&O leg ran 2W/10L to -15,474 without
# anything noticing, because sizing read a constant and the ledger was posting
# the damage against an unrelated pool.


async def _load_dr_entry_inputs(
    kite, instruments, fut_token: int, regime: str, now_ist: datetime,
    snapshot: Optional[ChainSnapshot] = None,
) -> tuple[Optional[ChainSnapshot], Optional[object], Optional[MomSignal], str]:
    """Load only the cancellable inputs needed to *open* a paper DR idea.

    This deliberately does not wrap ``maybe_open_dr_structure`` or DR
    lifecycle management.  An entry-input deadline may safely cancel a quote
    or historical-bars request before it mutates a position, order-intent, or
    ledger state; cancelling an admission mutation would make its outcome
    ambiguous. Existing DR structures are managed by the caller before this
    helper is considered.

    The budget is shared by the optional chain snapshot and futures-history
    download.  That prevents the experimental paper-entry branch from using
    two independent full waits and crowding out the next 90-second tick.
    ``asyncio.wait_for`` waits for cancellation to finish, so this never
    detaches a late request onto the shared Kite client.
    """
    budget = max(0.1, float(settings.FNO_DR_ENTRY_MARKET_DATA_MAX_SEC))
    deadline = monotonic() + budget

    def _remaining() -> float:
        return max(0.001, deadline - monotonic())

    if snapshot is None:
        try:
            snapshot = await asyncio.wait_for(
                take_chain_snapshot(kite, instruments, now_ist),
                timeout=_remaining(),
            )
        except asyncio.TimeoutError:
            return None, None, None, "chain_snapshot_deadline"
        except Exception as exc:
            logger.error("fno_dr_entry_snapshot_failed err=%s", str(exc))
            return None, None, None, "chain_snapshot_failed"
    if snapshot is None:
        return None, None, None, "chain_snapshot_unavailable"

    try:
        bars = await asyncio.wait_for(
            _fetch_futures_bars(kite, fut_token, now_ist),
            timeout=_remaining(),
        )
    except asyncio.TimeoutError:
        return snapshot, None, None, "futures_history_deadline"
    except Exception as exc:
        logger.error("fno_dr_entry_bars_failed err=%s", str(exc))
        return snapshot, None, None, "futures_history_failed"

    return snapshot, bars, evaluate_fno_mom(bars, regime, now_ist), ""


async def _fno_equity(db_path: str, source: str) -> float:
    """[POOL-TRUTH 2026-07-31] Live F&O equity: allocation + realised P&L."""
    from performance import division_equity
    return await division_equity(db_path, source)


def _fno_halted(equity: float, allocation: float, source: str) -> bool:
    """True when a leg has drawn down past its limit or gone non-positive."""
    if allocation <= 0:
        return False
    if equity <= 0:
        logger.critical(
            "fno_leg_halted source=%s equity=%.2f -- NON-POSITIVE equity",
            source, equity,
        )
        return True
    limit = float(settings.FNO_MAX_DRAWDOWN_PCT)
    if equity < allocation * (1.0 - limit):
        logger.critical(
            "fno_leg_halted source=%s equity=%.2f allocation=%.2f "
            "drawdown=%.1f%% limit=%.0f%%",
            source, equity, allocation,
            (1 - equity / allocation) * 100, limit * 100,
        )
        return True
    return False


async def _fetch_futures_bars(kite, fut_token: int, now_ist: datetime):
    frm = (now_ist - timedelta(days=RVOL_FETCH_CALENDAR_DAYS)).strftime(
        "%Y-%m-%d 09:15:00"
    )
    to = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    return await kite.get_intraday_by_token(fut_token, frm, to, interval="5minute")


async def _record_shadow_observation(
    db_path: str, bars, regime: str, now_ist: datetime,
    snapshot: Optional[ChainSnapshot] = None,
) -> int:
    """Best-effort research sidecar; failure can never change the live path."""
    try:
        rows = fno_shadow.evaluate_fno_shadows(
            bars, regime, now_ist, underlying=settings.FNO_UNDERLYING,
        )
        if snapshot is not None:
            fno_shadow.attach_resolved_cost_estimates(rows, snapshot, now_ist)
        return await fno_shadow.persist_fno_shadow_results(db_path, rows)
    except Exception as exc:
        logger.warning("fno_shadow_observation_failed err=%s", str(exc), exc_info=True)
        return 0


def _schedule_shadow_observation(
    db_path: str, bars, regime: str, now_ist: datetime,
    snapshot: Optional[ChainSnapshot] = None,
) -> Optional[Future]:
    """Supervise a best-effort write without blocking any trading path."""
    if not bool(getattr(settings, "FNO_SHADOW_ENABLED", True)):
        return None

    def _worker() -> int:
        try:
            rows = fno_shadow.evaluate_fno_shadows(
                bars, regime, now_ist, underlying=settings.FNO_UNDERLYING,
            )
            if snapshot is not None:
                fno_shadow.attach_resolved_cost_estimates(rows, snapshot, now_ist)
            return fno_shadow.persist_fno_shadow_results_sync(db_path, rows)
        except Exception as exc:
            logger.warning("fno_shadow_observation_failed err=%s", str(exc), exc_info=True)
            return 0

    task = _SHADOW_EXECUTOR.submit(_worker)
    _SHADOW_TASKS.add(task)
    task.add_done_callback(_SHADOW_TASKS.discard)
    return task


# ---------------------------------------------------------------------------
# position management (exits)
# ---------------------------------------------------------------------------

async def _manage_open_positions(
    kite, db_path: str, source: str, executor: FnoExecutor,
    now_ist: datetime, fut_price: Optional[float], *, read_observations: Optional[dict] = None,
    db_timing: Optional[dict] = None,
    action_clock: Optional[Callable[[], datetime]] = None,
    fut_prices: Optional[dict] = None,
) -> List[dict]:
    """Check every OPEN position for this leg against the §8.4/§8.5 exit
    ladder. Returns records of closed positions.

    ``fut_prices`` maps underlying -> its front-future price; a position is
    never priced with another index's future (a missing entry means no
    futures quote this tick). Without it every position uses ``fut_price``.
    """
    evaluation_started_at = datetime.now(pytz.UTC)
    positions = await _timed_database_operation(
        db_timing, f"open_positions:{source}", fpos.open_positions(db_path, source),
    )
    if not positions:
        return []

    # First settle previously acknowledged exits.  These positions remain OPEN
    # after a local accounting fault, but their broker fill is already durable
    # in the receipt table; do not price or submit them again.
    closed: List[dict] = []
    positions_needing_exit_evaluation = []
    for p in positions:
        receipt = await _timed_database_operation(
            db_timing, f"exit_receipt_read:{source}",
            fpos.exit_execution_receipt(db_path, p.id, source),
        )
        if receipt is None:
            positions_needing_exit_evaluation.append(p)
            continue
        recovered = await _timed_database_operation(
            db_timing, f"exit_settlement:{source}",
            _settle_exit_receipt(db_path, p, receipt),
        )
        if recovered is not None:
            closed.append(recovered)

    if not positions_needing_exit_evaluation:
        return closed

    # One batched quote for every held contract. This is a cancellable provider
    # read, so it gets a total budget. A timeout joins cancellation and falls
    # through to the existing unpriced/hard-flat path; no mutation is wrapped.
    tokens = [p.token for p in positions_needing_exit_evaluation if p.token]
    quotes = {}
    if tokens:
        quote_cap = _read_cap(settings.FNO_EXIT_QUOTE_READ_MAX_SEC)
        quote_started = monotonic()
        try:
            quotes, provider_timing = await asyncio.wait_for(
                _management_quote(kite, tokens), timeout=quote_cap,
            )
            _record_management_read(
                read_observations, f"exit_quotes:{source}", "COMPLETED", quote_started, quote_cap,
                provider_timing=provider_timing,
            )
        except asyncio.TimeoutError:
            _record_management_read(
                read_observations, f"exit_quotes:{source}", "DEADLINE_EXCEEDED", quote_started, quote_cap,
                timeout_partial=True,
            )
            logger.warning("fno_exit_quote_deadline_exceeded source=%s cap_sec=%.3f", source, quote_cap)
        except Exception as exc:
            _record_management_read(
                read_observations, f"exit_quotes:{source}", "FAILED", quote_started, quote_cap,
            )
            logger.error("fno_exit_quote_failed source=%s err=%s", source, str(exc))

    if action_clock is not None:
        now_ist = action_clock()
    if read_observations is not None and tokens:
        observation = read_observations.get(f"exit_quotes:{source}")
        if observation is not None:
            age = _oldest_quote_age_sec(quotes, tokens, now_ist)
            observation["oldest_exact_leg_quote_age_sec"] = age
            observation["quote_age_status"] = "PRESENT" if age is not None else "UNAVAILABLE"

    for p in positions_needing_exit_evaluation:
        if action_clock is not None:
            now_ist = action_clock()
        hard_flat = _now_min(now_ist) >= settings.FNO_HARD_FLAT_MIN
        q = quotes.get(p.token) or {}
        depth = q.get("depth") or {}
        buys = depth.get("buy") or []
        bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
        ltp = float(q.get("last_price") or 0.0)
        exit_px_basis = bid if bid > 0 else ltp

        # [S6b 2026-10-02] The exit ladder is the pure, shared
        # ``fno_exit_rules.evaluate_single_leg_exit`` (extracted verbatim so
        # research replays the identical rules).  Logging and trail
        # persistence remain here.  The time-stop premium deferral is OFF
        # since the Oct 8 put-sign fix; see config.FNO_TIME_STOP_RESPECTS_PREMIUM.
        position_fut = (fut_prices.get((p.underlying or "NIFTY").upper()) if fut_prices is not None
                        else fut_price)
        decision = evaluate_single_leg_exit(
            p, now_ist=now_ist, fut_price=position_fut, exit_px_basis=exit_px_basis,
            hard_flat=hard_flat, params=live_single_leg_exit_params(settings),
        )
        exit_reason = decision.exit_reason
        if decision.trail_newly_armed:
            logger.info(
                "fno_trail_armed id=%d symbol=%s fut=%.1f target=%.1f",
                p.id, p.tradingsymbol, position_fut, p.target_underlying,
            )
        if decision.entry_time_unparseable:
            # [AUDIT-FIX-PHASE1 2026-07-11] Loud-but-non-blocking.
            logger.warning(
                "fno_time_stop_age_parse_failed id=%d entry_time=%r "
                "-- age_min defaulted to 0; time stop DEFEATED for "
                "this position (operator must patch entry_time "
                "to force the exit)",
                p.id, p.entry_time,
            )
        if decision.time_stop_deferred is not None:
            deferred = decision.time_stop_deferred
            logger.info(
                "fno_time_stop_deferred_in_profit id=%d age=%.0f "
                "underlying_progress=%.1f needed=%.1f "
                "premium_pnl_per_unit=%.2f",
                p.id, deferred["age_min"], deferred["underlying_progress"],
                deferred["needed"], deferred["premium_pnl_per_unit"],
            )
        # persist trail state even when not exiting (futures quote present)
        if decision.persist_trail:
            await _timed_database_operation(
                db_timing, f"trail_update:{source}", fpos.update_trail(
                    db_path, p.id, 1 if decision.trail_active else 0,
                    decision.trail_stop, decision.best_underlying, decision.best_premium,
                ),
            )
        elif (not exit_reason and decision.best_premium is not None
              and (p.best_premium is None or decision.best_premium > p.best_premium)):
            # No futures quote: the trail stays put, but a new option peak
            # must still be kept or the profit lock can never arm (O8-F1).
            await _timed_database_operation(
                db_timing, f"best_premium_update:{source}", fpos.update_best_premium(
                    db_path, p.id, decision.best_premium,
                ),
            )

        if not exit_reason:
            continue

        if exit_px_basis <= 0:
            # [AUDIT-FIX-PHASE1 2026-07-11] Loud-but-non-blocking: a hard
            # flat with no quote would otherwise silently `continue` and
            # leave the position open through the weekend (MIS auto-sq-off
            # at 15:30 is the broker safety net, not a guarantee). On a
            # non-trading-day next-tick the carry is real -> page the
            # operator so they can reconcile broker exposure and local ledger.
            msg = (
                f"⚠️ *F&O hard flat blocked by no quote*\n"
                f"id={p.id} symbol={p.tradingsymbol} reason={exit_reason}\n"
                f"The 15:10 hard flat could not price -- position may "
                f"carry into the next session. Action required: manual "
                f"inspect broker exposure and use authenticated F&O exit "
                f"recovery for id={p.id}; preserve ledger evidence."
            )
            try:
                from operator_alert import notify_operator
                await notify_operator(msg, event="fno_hard_flat_no_quote")
            except Exception as notify_exc:
                logger.error(
                    "fno_operator_page_failed id=%d err=%s",
                    p.id, notify_exc,
                )
            logger.critical(
                "fno_exit_no_quote id=%d symbol=%s reason=%s -- cannot price "
                "the exit; position will carry into next session (operator paged)",
                p.id, p.tradingsymbol, exit_reason,
            )
            continue

        claimed = await _timed_database_operation(
            db_timing, f"exit_intent_claim:{source}", fpos.claim_exit_intent(
                db_path, p.id, source, evaluation_started_at=evaluation_started_at,
            ),
        )
        if not claimed:
            logger.critical("fno_exit_reconciliation_required id=%s source=%s", p.id, source)
            continue
        try:
            spec = SPECS.get((p.underlying or "NIFTY").upper())
            exchange_kw = {} if spec is None or spec.segment == "NFO" else {"exchange": spec.segment}
            result = await executor.execute_exit(
                p.tradingsymbol, p.qty, exit_px_basis,
                tick_size=settings.FNO_TICK_SIZE,
                hard_flat=exit_reason.startswith("hard_flat"),
                **exchange_kw,
            )
        except Exception:
            logger.exception("fno_exit_dispatch_ambiguous id=%s; reconcile before retry", p.id)
            continue
        if result["status"] not in ("paper", "filled"):
            logger.warning(
                "fno_exit_not_filled id=%d symbol=%s status=%s -- reconcile before retry",
                p.id, p.tradingsymbol, result["status"],
            )
            continue

        fill = float(result["fill_price"])
        gross = (fill - p.entry_premium) * p.qty
        costs = calc_fno_costs(p.entry_premium, fill, p.qty)
        pnl = gross - costs
        risk_rupees = p.entry_premium * settings.FNO_STOP_PREMIUM_PCT * p.qty
        r_mult = pnl / risk_rupees if risk_rupees > 0 else 0.0
        try:
            receipt = await _timed_database_operation(
                db_timing, f"exit_receipt_write:{source}", fpos.record_exit_execution_receipt(
                    db_path, p.id,
                    exit_time_ist=now_ist, exit_premium=fill,
                    exit_underlying=position_fut or 0.0, exit_reason=exit_reason,
                    gross_pnl=gross, costs=costs, pnl=pnl, r_multiple=r_mult,
                    exit_order_id=result.get("order_id"),
                    source=source, ticker=p.tradingsymbol,
                    settlement_generation=p.settlement_generation + 1,
                    notes=f"fno_exit {exit_reason}",
                ),
            )
        except Exception as exc:
            # A broker fill without a durable local receipt is an uncertain
            # external state.  Do not turn it into a normal retry: a later
            # pass could submit a second exit.  The operator must reconcile
            # the returned order id before reopening this position locally.
            logger.critical(
                "fno_filled_exit_receipt_failed id=%d symbol=%s order_id=%s err=%s "
                "-- local retry blocked pending broker reconciliation",
                p.id, p.tradingsymbol, result.get("order_id"), str(exc),
            )
            continue
        settled = await _timed_database_operation(
            db_timing, f"exit_settlement:{source}",
            _settle_exit_receipt(db_path, p, receipt),
        )
        if settled is not None:
            closed.append(settled)
    return closed


# ---------------------------------------------------------------------------
# entry (one leg)
# ---------------------------------------------------------------------------

async def _try_entry_for_leg(
    kite, db_path: str, source: str, pool: float, executor: FnoExecutor,
    sig: MomSignal, snap: ChainSnapshot, regime: str,
    now_ist: datetime, scan_id: str, is_trading_day: bool,
    *, action_clock: Optional[Callable[[], datetime]] = None,
    shared_pool_rs: Optional[float] = None,
    underlying: Optional[str] = None, underlying_book=None,
) -> Optional[dict]:
    """Run the §7 gate ladder + §4 constitution + sizing for ONE leg and,
    if everything passes, place the entry. Logs the evaluation either way."""
    underlying = (underlying or settings.FNO_UNDERLYING).upper()
    instruments = underlying_book or get_fno_instruments()
    today_iso = now_ist.date().isoformat()

    async def _log(accepted: bool, reason: str, **extra):
        await log_fno_signal(
            db_path, scan_id=scan_id, leg=source, accepted=accepted,
            reject_reason=reason, bar_ts=sig.bar_ts,
            underlying=underlying,
            direction=sig.direction.value if sig.direction else None,
            regime=regime, fut_price=snap.forward,
            or_high=sig.or_high, or_low=sig.or_low, atr=sig.atr,
            rvol=sig.rvol, ema_fast=sig.ema_fast, ema_slow=sig.ema_slow,
            **extra,
        )

    # One vehicle per directional idea (FNO_VEHICLE_BY_IV): when premium is
    # rich the capped-loss book expresses it as a debit spread, so the naked
    # leg stands aside -- unless a structure is already open (one at a time),
    # in which case the spread cannot be taken and the naked leg may trade.
    if source == FnoSource.FNO_PAPER.value:
        import fno_dr_book as _dr
        if (_dr.vehicle_by_iv_active()
                and _dr.choose_directional_vehicle(snap, now_ist) == _dr.VEHICLE_SPREAD
                and not await _dr.open_structures(db_path, source)):
            await _log(False, "vehicle_spread_preferred")
            return None

    # Book state is read here; the decision itself is the pure, shared
    # ``fno_entry_plan.plan_single_leg_entry`` (strike pick, §7 gates,
    # no-pyramid, sizing, §4 max loss, net reward/risk) so research replays
    # evaluate exactly this logic.
    open_prem = await fpos.open_premium_committed(db_path, source)
    open_rows = await fpos.open_positions(db_path, source)
    n_today = await fpos.trades_today(db_path, source, today_iso)
    # F0-C makes the paper books share one ledger-bound entry-policy receipt.
    # Initialise only the additive local evidence schemas; exits/management do
    # not depend on this branch and remain available when an entry is halted.
    shared_policy = None
    if shared_pool_rs is not None and source == FnoSource.FNO_PAPER.value:
        from performance import init_ledger
        import fno_dr_book as _dr
        await init_ledger(db_path)
        await fpos.init_fno_positions_db(db_path)
        await _dr.init_dr_db(db_path)
        await init_shared_fno_risk_db(db_path)
        shared_policy = policy_from_settings()
        shared_decision = await shared_fno_entry_policy(
            db_path, source=source, pool_rs=shared_pool_rs,
            today_ist=now_ist.date(), policy=shared_policy,
        )
        switches = list(shared_decision.active_halts)
    else:
        switches = await kill_switch_status(db_path, source, pool, now_ist.date())
    # Adaptive risk: size shrinks in a drawdown, grows only on proven evidence,
    # and two losing single-leg closes end the day's single-leg entries.
    stance = risk_stance(await read_book_closes(db_path, source), allocation=shared_pool_rs or pool,
                         now=now_ist, policy=adaptive_policy())
    if stance.single_leg_halted_today:
        switches = [*switches, f"two_strike_day_halt losses={stance.single_leg_losses_today}"]
    if switches:
        # Rule 72: a halted leg is a WARNING, never an INFO.
        logger.warning("fno_kill_switch_active source=%s switches=%s", source, switches)
    if stance.multiplier != 1.0:
        logger.info("fno_adaptive_risk source=%s multiplier=%.2f reason=%s drawdown=%.4f trades=%d pf=%s",
                    source, stance.multiplier, stance.reason, stance.drawdown_pct, stance.closed_trades,
                    stance.profit_factor)

    reentry_levels = None
    if settings.FNO_REENTRY_REQUIRES_CONFIRMATION:
        from fno_entry_plan import REENTRY_STOP_REASONS
        reentry_levels = await fpos.stopped_entry_levels_today(
            db_path, source, underlying, today_iso, REENTRY_STOP_REASONS,
            float(settings.FNO_REENTRY_MARGIN_R))
    plan = plan_single_leg_entry(sig, snap, regime, now_ist, EntryState(
        pool=pool, open_premium=open_prem, open_positions=len(open_rows), trades_today=n_today,
        active_kill_switches=tuple(switches),
        held_symbols=frozenset(p.tradingsymbol for p in open_rows),
        correlated_open_directions=frozenset(
            p.direction for p in open_rows if (p.underlying or "NIFTY").upper() != underlying),
        is_trading_day=is_trading_day, is_expiry_day=instruments.is_expiry_day(now_ist.date()),
        risk_multiplier=stance.multiplier, reentry_levels=reentry_levels,
    ))
    if not plan.accepted:
        await _log(False, plan.reject_reason, **plan.log_fields)
        if plan.reject_reason == "already_holding_this_contract":
            logger.info(
                "fno_entry_skip source=%s reason=already_holding_this_contract symbol=%s open_lots=%d",
                source, plan.quote.contract.tradingsymbol,
                sum(p.lots for p in open_rows if p.tradingsymbol == plan.quote.contract.tradingsymbol),
            )
        elif plan.reject_reason == "reward_risk_below_min":
            terms = plan.rr_terms
            logger.info(
                "fno_entry_skip source=%s reason=reward_risk_below_min symbol=%s "
                "rr=%.2f min=%.2f reward=%.0f risk=%.0f spread=%.0f "
                "stop_pts=%.1f target_pts=%.1f delta=%.2f",
                source, plan.quote.contract.tradingsymbol, plan.reward_risk, settings.FNO_MIN_REWARD_RISK,
                terms["reward"], terms["risk"], terms["spread"], terms["stop_pts"], terms["target_pts"],
                terms["delta"],
            )
        return None
    quote, iv, delta_val = plan.quote, plan.iv, plan.delta
    contract, opt_type = quote.contract, plan.opt_type
    ask, lot_size, lots, ml = quote.ask, plan.lot_size, plan.lots, plan.max_loss_rupees
    ctx = plan.gate_context
    contract_fields = {key: value for key, value in plan.log_fields.items()
                       if key not in ("lots", "max_loss_rupees", "passed_gates", "active_kill_switches")}
    gate_audit_fields = {"passed_gates": plan.log_fields["passed_gates"], "active_kill_switches": switches}

    # Database/limiter waits must not turn an earlier valid evaluation into
    # authority to enter after cutoff or with a now-stale quote. Replay callers
    # retain their supplied clock; broker dispatch itself is never cancelled.
    if action_clock is not None:
        now_ist = action_clock()
        ctx.now_min = _now_min(now_ist)
        ctx.quote_age_sec = (
            (now_ist - quote.last_trade_time).total_seconds()
            if quote.last_trade_time else float("inf")
        )
        ctx.chain_age_sec = snap.age_sec(now_ist)
        ok, reject, passed_gates = evaluate_entry_gates_with_trace(ctx)
        if not ok:
            await _log(False, reject, **contract_fields,
                       passed_gates=passed_gates, active_kill_switches=switches)
            return None
        today_iso = now_ist.date().isoformat()
    qty = lots * lot_size
    # F0-B: reserve the full structural premium loss plus a zero-premium exit
    # cost before dispatch.  This preserves feasible admissions: it uses the
    # existing per-trade sizing and adds no arbitrary threshold, but prevents
    # the DR and directional books from spending the same worst-case cash.
    reservation_key = None
    if shared_pool_rs is not None:
        from performance import init_ledger
        await init_ledger(db_path)
        await fpos.init_fno_positions_db(db_path)
        import fno_dr_book as _dr
        await _dr.init_dr_db(db_path)
        reservation_key = f"single:{source}:{contract.token}:{sig.bar_ts}"
        worst_case_cash = ml + calc_fno_costs(ask, 0.0, qty)
        admission = await reserve_shared_fno_risk(
            db_path, source=source, pool_rs=shared_pool_rs,
            reservation_key=reservation_key, book="SINGLE_LEG",
            worst_case_cash_rs=worst_case_cash,
            entry_day_ist=now_ist.date() if shared_policy is not None else None,
            policy=shared_policy,
        )
        if not admission.allowed:
            await _log(False, admission.reason, **contract_fields, lots=lots,
                       max_loss_rupees=ml, **gate_audit_fields)
            logger.warning("fno_entry_skip source=%s reason=%s", source, admission.reason)
            return None
        # F0-R2: a reservation (even an identical retry's) is not authority
        # to dispatch. Exactly one claim per reservation is granted, after the
        # same entry policy is re-read; a now-halted retry never dispatches.
        # F0-R5: the existing concurrency, trades/day, open-premium and
        # no-pyramid limits are re-applied atomically here, counting in-flight
        # claims, so concurrent admissions cannot each pass a stale pre-read.
        claim = await claim_shared_fno_entry_dispatch(
            db_path, reservation_key=reservation_key, source=source, book="SINGLE_LEG",
            pool_rs=shared_pool_rs,
            entry_day_ist=now_ist.date() if shared_policy is not None else None,
            policy=shared_policy,
            occupancy=EntryOccupancy(
                entry_day=now_ist.date(), max_open=int(settings.FNO_MAX_CONCURRENT),
                tradingsymbol=contract.tradingsymbol, planned_premium_rs=ask * qty,
                max_trades_per_day=int(settings.FNO_MAX_TRADES_PER_DAY),
                max_open_premium_rs=float(settings.FNO_MAX_OPEN_PREMIUM_PCT) * pool,
                no_pyramid=True,
            ),
        )
        if not claim.granted:
            await _log(False, f"dispatch_claim_denied:{claim.reason}", **contract_fields,
                       lots=lots, max_loss_rupees=ml, **gate_audit_fields)
            logger.warning("fno_entry_skip source=%s reason=dispatch_claim_denied:%s",
                           source, claim.reason)
            return None
        # F0-R5: the claim was the last DB wait before dispatch; a live caller
        # re-reads the real clock so a delay cannot carry a stale admission
        # past the entry cutoff or quote/chain freshness.
        if action_clock is not None:
            late = post_admission_entry_reject(action_clock(), quote, snap)
            if late:
                await resolve_shared_fno_entry_dispatch(
                    db_path, reservation_key=reservation_key, owner=claim.owner,
                    outcome="no_dispatch",
                    evidence={"dispatch_certainty": "NOT_SENT", "order_id": None,
                              "reason": f"post_admission_{late}"},
                )
                await _log(False, f"post_admission_{late}", **contract_fields, lots=lots,
                           max_loss_rupees=ml, **gate_audit_fields)
                logger.warning("fno_entry_skip source=%s reason=post_admission_%s", source, late)
                return None
    # NFO orders keep the original call; another segment names its exchange.
    exchange_kw = {} if instruments.segment == "NFO" else {"exchange": instruments.segment}
    result = await executor.execute_entry(contract.tradingsymbol, qty, ask, **exchange_kw)
    if result["status"] not in ("paper", "filled"):
        status = result["status"]
        if reservation_key:
            outcome = status if status in DISPATCH_RELEASE_OUTCOMES | DISPATCH_RETAIN_OUTCOMES \
                else "unknown"
            applied = await resolve_shared_fno_entry_dispatch(
                db_path, reservation_key=reservation_key, owner=claim.owner,
                outcome=outcome, evidence=result.get("evidence") or {"status": status},
            )
            if applied not in DISPATCH_RELEASE_OUTCOMES:
                logger.critical(
                    "fno_entry_outcome_unresolved source=%s symbol=%s status=%s applied=%s "
                    "reservation=%s -- reserved capital retained; reconcile with "
                    "reconcile_shared_fno_entry_dispatch or record the fill",
                    source, contract.tradingsymbol, status, applied, reservation_key,
                )
        await _log(
            False, f"entry_{status}", **contract_fields, lots=lots,
            **gate_audit_fields,
        )
        return None
    fill = float(result["fill_price"])

    premium_stop = round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2)
    inserter = fpos.insert_position_with_risk_reservation if reservation_key else fpos.insert_position
    try:
        await _insert_entry_position(inserter, db_path, reservation_key, dict(
        source=source,
        tradingsymbol=contract.tradingsymbol,
        token=contract.token,
        underlying=underlying,
        expiry=contract.expiry.isoformat(),
        strike=contract.strike,
        opt_type=opt_type.value,
        direction=sig.direction.value,
        lots=lots, lot_size=lot_size, qty=qty,
        entry_time=now_ist.isoformat(),
        entry_date=today_iso,
        entry_premium=fill,
        entry_underlying=snap.forward,
        delta_at_entry=delta_val, iv_at_entry=iv, atr_at_entry=sig.atr,
        stop_underlying=sig.stop_underlying,
        target_underlying=sig.target_underlying,
        premium_stop=premium_stop,
        trail_active=0, trail_stop_underlying=None,
        best_underlying=snap.forward,
        max_loss_rupees=ml,
        status="OPEN",
        entry_order_id=result.get("order_id"),
        bar_ts=sig.bar_ts,
    ))
    except Exception:
        if reservation_key:
            # Paper fills exist only in this process: a failed receipt means no
            # exposure. A live fill without its receipt keeps the reservation.
            paper = result["status"] == "paper"
            await resolve_shared_fno_entry_dispatch(
                db_path, reservation_key=reservation_key, owner=claim.owner,
                outcome="no_dispatch" if paper else "filled_unrecorded",
                evidence={**(result.get("evidence") or {}),
                          "dispatch_certainty": "NOT_SENT" if paper else "ACCEPTED",
                          "order_id": None if paper else result.get("order_id"),
                          "receipt": "position_insert_failed"},
            )
        raise
    await _log(
        True, "", **contract_fields, lots=lots, max_loss_rupees=ml,
        **gate_audit_fields,
    )
    logger.info(
        "fno_entry_submitted source=%s symbol=%s dir=%s lots=%d fill=%.2f "
        "delta=%.2f iv=%.2f stop_u=%.1f target_u=%.1f prem_stop=%.2f max_loss=%.0f",
        source, contract.tradingsymbol, sig.direction.value, lots, fill,
        delta_val, iv, sig.stop_underlying, sig.target_underlying,
        premium_stop, ml,
    )
    return {
        "symbol": contract.tradingsymbol, "direction": sig.direction.value,
        "lots": lots, "fill": fill, "delta": round(delta_val, 2),
        "iv": round(iv, 3), "source": source,
    }


def post_admission_entry_reject(now_ist: datetime, quote, snap) -> Optional[str]:
    """[F0-R5] Re-check the real clock after the admission DB waits.

    Same thresholds as the entry gates (entry window, contract quote and chain
    freshness); returns the first failing gate name, or ``None``.
    """
    now_min = _now_min(now_ist)
    if not settings.FNO_ENTRY_START_MIN <= now_min < settings.FNO_ENTRY_END_MIN:
        return "entry_window"
    age = ((now_ist - quote.last_trade_time).total_seconds()
           if quote.last_trade_time else float("inf"))
    if age > settings.FNO_MAX_QUOTE_AGE_SEC:
        return "quote_freshness"
    if snap.age_sec(now_ist) > settings.FNO_MAX_CHAIN_AGE_SEC:
        return "chain_freshness"
    return None


async def _insert_entry_position(inserter, db_path: str, reservation_key, fields: dict) -> int:
    """Insert the filled entry, consuming its reservation and claim when bound."""
    if reservation_key:
        return await inserter(db_path, reservation_key=reservation_key, **fields)
    return await inserter(db_path, **fields)


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

async def _manage_single_leg_books(
    kite, db_path: str, fut, summary: dict, paper_exec: FnoExecutor, live_exec: FnoExecutor, *,
    now_ist: datetime, supplied_now_ist: Optional[datetime], tick_started: float,
    action_clock: Optional[Callable[[], datetime]],
) -> tuple[Optional[float], datetime]:
    """Futures quote, then the single-leg exit ladder for every enabled leg.

    Shared by the scheduled tick and the fast exit loop so both manage open
    positions through exactly the same reads, ladder and settlement path.
    Returns the futures price (None when unavailable) and the action clock.
    """
    # ---- futures price for exit management ---------------------------
    stage_started = monotonic()
    fut_quote = {}
    fut_quote_cap = _read_cap(settings.FNO_EXIT_QUOTE_READ_MAX_SEC)
    try:
        fut_quote, provider_timing = await asyncio.wait_for(
            _management_quote(kite, [fut.token]), timeout=fut_quote_cap,
        )
        _record_management_read(
            summary["management_read_outcomes"], "futures_quote", "COMPLETED",
            stage_started, fut_quote_cap, provider_timing=provider_timing,
        )
    except asyncio.TimeoutError:
        _record_management_read(
            summary["management_read_outcomes"], "futures_quote", "DEADLINE_EXCEEDED",
            stage_started, fut_quote_cap, timeout_partial=True,
        )
        logger.warning("fno_futures_quote_deadline_exceeded cap_sec=%.3f", fut_quote_cap)
    except Exception as exc:
        _record_management_read(
            summary["management_read_outcomes"], "futures_quote", "FAILED",
            stage_started, fut_quote_cap,
        )
        logger.error("fno_futures_quote_failed err=%s", str(exc))
    summary["stage_durations_sec"]["futures_quote"] = round(
        monotonic() - stage_started, 3
    )
    fut_price = None
    fq = fut_quote.get(fut.token)
    if fq and fq.get("last_price"):
        fut_price = float(fq["last_price"])

    # A real scheduler tick can cross hard-flat while queued on a provider.
    # The completed-bar/signal timestamp remains frozen in ``sig`` later, but
    # management, session cutoffs and admission decisions use a fresh action
    # clock. Explicit caller clocks are retained for deterministic replay/tests.
    if supplied_now_ist is None:
        now_ist = datetime.now(IST)
    summary["action_clock_ist"] = now_ist.isoformat()
    summary["management_lag_sec"] = round(monotonic() - tick_started, 3)

    # Other underlyings' futures are quoted only when a position on them is
    # open (per-underlying batches: mixed NFO+BFO batches are unverified).
    fut_prices = {"NIFTY": fut_price}
    held = set()
    for source in ([] if settings.FNO_DISABLE_PAPER else [FnoSource.FNO_PAPER.value]) + \
            ([] if settings.FNO_DISABLE_LIVE else [FnoSource.FNO_LIVE.value]):
        held |= {(p.underlying or "NIFTY").upper() for p in await fpos.open_positions(db_path, source)}
    for name in sorted(held - {"NIFTY"}):
        other = get_instruments_for(name).front_future(now_ist.date()) if name in SPECS else None
        if other is None:
            fut_prices[name] = None
            continue
        try:
            quote, _timing = await asyncio.wait_for(_management_quote(kite, [other.token]),
                                                    timeout=fut_quote_cap)
            fut_prices[name] = float((quote.get(other.token) or {}).get("last_price") or 0.0) or None
        except Exception as exc:
            logger.error("fno_futures_quote_failed underlying=%s err=%s", name, str(exc))
            fut_prices[name] = None

    # ---- 1) exits first ----------------------------------------------
    stage_started = monotonic()
    try:
        if not settings.FNO_DISABLE_PAPER:
            summary["exits"] += await _manage_open_positions(
                kite, db_path, FnoSource.FNO_PAPER.value, paper_exec, now_ist, fut_price,
                read_observations=summary["management_read_outcomes"],
                db_timing=summary["database_stage_timing"],
                action_clock=action_clock, fut_prices=fut_prices,
            )
        if not settings.FNO_DISABLE_LIVE:
            summary["exits"] += await _manage_open_positions(
                kite, db_path, FnoSource.FNO_LIVE.value, live_exec, now_ist, fut_price,
                read_observations=summary["management_read_outcomes"],
                db_timing=summary["database_stage_timing"],
                action_clock=action_clock, fut_prices=fut_prices,
            )
    except Exception as exc:
        logger.error("fno_exit_management_failed err=%s", str(exc), exc_info=True)
    finally:
        summary["stage_durations_sec"]["exit_management"] = round(
            monotonic() - stage_started, 3
        )

    return fut_price, now_ist


async def run_fno_tick(
    kite, db_path: Optional[str] = None,
    regime: str = "UNKNOWN",
    is_trading_day: bool = True,
    now_ist: Optional[datetime] = None,
) -> dict:
    """One scan tick. Called by the main.py cron wrapper (which owns the
    calendar gate + no-token guard + Telegram delivery)."""
    db_path = db_path or settings.DB_PATH
    supplied_now_ist = now_ist
    now_ist = now_ist or datetime.now(IST)
    evaluation_now_ist = now_ist
    action_clock = (lambda: datetime.now(IST)) if supplied_now_ist is None else None
    tick_started = monotonic()
    scan_id = f"FNO-{now_ist.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    summary: dict = {
        "scan_id": scan_id, "entries": [], "exits": [], "note": "",
        "stage_durations_sec": {},
        "management_read_outcomes": {},
        "database_stage_timing": {
            "measurement": "operation_elapsed_includes_sqlite_lock_wait",
            "stages": {},
        },
    }

    # Rule 56: first-line orchestrator breadcrumb.
    logger.info(
        "fno_orchestrator_tick scan_id=%s now_ist=%s regime=%s",
        scan_id, now_ist.strftime("%H:%M:%S"), regime,
    )

    instruments = get_fno_instruments()
    if not instruments.ready(now_ist.date()):
        # Try disk rehydrate once per tick; the 08:00 cron owns refresh.
        if not instruments.load_from_disk():
            logger.warning(
                "fno_tick_skip reason=instruments_not_ready "
                "FIX=wait for 08:00 refresh or check kite auth"
            )
            summary["note"] = "instruments_not_ready"
            return summary

    fut = instruments.front_future(now_ist.date())
    if fut is None:
        logger.warning("fno_tick_skip reason=no_front_future")
        summary["note"] = "no_front_future"
        return summary

    paper_exec = FnoExecutor(kite, paper_mode=True, source_tag=FnoSource.FNO_PAPER.value)
    # Live leg is paper-forced unless every arming condition holds; in P1
    # FNO_DISABLE_LIVE=True short-circuits it entirely below.
    live_master = bool(settings.FNO_LIVE_TRADING)
    live_exec = FnoExecutor(
        kite, paper_mode=not live_master, source_tag=FnoSource.FNO_LIVE.value,
    )

    # A tick can feed both the defined-risk book and the directional ORB book.
    # Keep their market-data inputs tick-local so the second consumer reuses
    # exactly the same closed bars/snapshot.  Besides avoiding a redundant
    # 21-calendar-day historical fetch, this prevents the two books from making
    # decisions from slightly different bars when a five-minute candle closes
    # between their requests.
    bars = None
    sig = None
    snap = None

    fut_price, now_ist = await _manage_single_leg_books(
        kite, db_path, fut, summary, paper_exec, live_exec, now_ist=now_ist,
        supplied_now_ist=supplied_now_ist, tick_started=tick_started, action_clock=action_clock,
    )

    # ---- 1b) defined-risk paper book (Phase 2) -----------------------
    # Rides this same tick: manage any open structure to current mids, then
    # (if flat + in-window) open one -- a debit spread on a directional signal,
    # an iron condor on a rich-IV range day (which the single-leg engine's
    # no-signal early-return below would never reach). Fully self-contained and
    # guarded: nothing here can disturb the single-leg engine above or below.
    stage_started = monotonic()
    if not settings.FNO_DISABLE_PAPER and not settings.FNO_DR_DISABLE_PAPER:
        try:
            import fno_dr_book as _dr
            await _timed_database_operation(
                summary["database_stage_timing"], "defined_risk_init", _dr.init_dr_db(db_path),
            )
            open_dr = await _timed_database_operation(
                summary["database_stage_timing"], "defined_risk_open_read", _dr.open_structures(db_path),
            )
            if supplied_now_ist is None:
                now_ist = datetime.now(IST)
                summary["action_clock_ist"] = now_ist.isoformat()
            nm_dr = _now_min(now_ist)
            in_dr_window = _dr._entry_lo_min() <= nm_dr <= _dr._entry_hi_min()

            # An existing structure is risk-management work.  It remains
            # outside the paper-entry deadline, including a hard-flat close
            # when a chain quote is unavailable.  This split also makes the
            # next Production trace able to distinguish an exit delay from a
            # speculative-entry delay.
            if open_dr:
                snapshot_started = monotonic()
                management_cap = _read_cap(settings.FNO_DR_MANAGEMENT_READ_MAX_SEC)
                try:
                    exact_tokens = _dr.exact_open_leg_tokens(open_dr)
                    if exact_tokens:
                        raw_quotes, provider_timing = await asyncio.wait_for(
                            _management_quote(kite, exact_tokens), timeout=management_cap,
                        )
                        dr_snap = _dr.exact_leg_snapshot_from_quotes(
                            open_dr, raw_quotes, now_ist, fut_price,
                        )
                        read_name = "defined_risk_snapshot"
                    else:
                        # Never rebuild a nearest-expiry ladder for legacy or
                        # malformed rows: that could price different contracts.
                        # ``manage_dr_structures`` receives None and keeps the
                        # lifecycle unresolved (or records a no-cash hard-flat).
                        dr_snap = None
                        provider_timing = None
                        read_name = "defined_risk_snapshot"
                    _record_management_read(
                        summary["management_read_outcomes"], read_name,
                        "COMPLETED" if dr_snap is not None else "UNAVAILABLE",
                        snapshot_started, management_cap, provider_timing=provider_timing,
                    )
                except asyncio.TimeoutError:
                    logger.warning("fno_dr_management_snapshot_deadline_exceeded cap_sec=%.3f", management_cap)
                    _record_management_read(
                        summary["management_read_outcomes"], "defined_risk_snapshot", "DEADLINE_EXCEEDED",
                        snapshot_started, management_cap, timeout_partial=True,
                    )
                    dr_snap = None
                except Exception as exc:
                    logger.error("fno_dr_management_snapshot_failed err=%s", str(exc))
                    _record_management_read(
                        summary["management_read_outcomes"], "defined_risk_snapshot", "FAILED",
                        snapshot_started, management_cap,
                    )
                    dr_snap = None
                finally:
                    summary["stage_durations_sec"]["defined_risk_snapshot"] = round(
                        monotonic() - snapshot_started, 3
                    )

                management_started = monotonic()
                if action_clock is not None:
                    now_ist = action_clock()
                    summary["action_clock_ist"] = now_ist.isoformat()
                # manage_dr_structures intentionally accepts ``None`` and
                # fail-closes a hard-flat structure even without a quote.
                summary["dr_exits"] = summary.get("dr_exits", 0) + \
                    await _dr.manage_dr_structures(db_path, dr_snap, now_ist)
                summary["stage_durations_sec"]["defined_risk_management"] = round(
                    monotonic() - management_started, 3
                )

            remaining_open_dr = await _timed_database_operation(
                summary["database_stage_timing"], "defined_risk_open_read", _dr.open_structures(db_path),
            )
            if in_dr_window and not remaining_open_dr:
                entry_inputs_started = monotonic()
                entry_snap, entry_bars, entry_sig, entry_skip_reason = await _load_dr_entry_inputs(
                    kite, instruments, fut.token, regime, evaluation_now_ist, snap,
                )
                summary["stage_durations_sec"]["defined_risk_entry_inputs"] = round(
                    monotonic() - entry_inputs_started, 3
                )
                if entry_skip_reason:
                    summary["dr_entry_skip_reason"] = entry_skip_reason
                    logger.warning(
                        "fno_dr_entry_skipped reason=%s budget_sec=%.3f",
                        entry_skip_reason,
                        float(settings.FNO_DR_ENTRY_MARKET_DATA_MAX_SEC),
                    )
                elif entry_snap is not None and entry_sig is not None:
                    # Preserve the original tick-local reuse contract: a
                    # successful DR entry read is the directional engine's
                    # exact same closed-bar and chain view.
                    snap, bars, sig = entry_snap, entry_bars, entry_sig
                    # Mutating paper-book admission runs only after all
                    # deadline-cancellable reads succeed.  Do not place it
                    # under ``wait_for``: a cancelled write would make the
                    # admission outcome ambiguous.
                    entry_started = monotonic()
                    if action_clock is not None:
                        now_ist = action_clock()
                        summary["action_clock_ist"] = now_ist.isoformat()
                    try:
                        opened = await _dr.maybe_open_dr_structure(
                            db_path, entry_snap,
                            entry_sig.direction is not None,
                            entry_sig.direction, now_ist,
                            action_clock=action_clock,
                        )
                        if opened:
                            summary.setdefault("dr_opened", []).append(opened)
                    except Exception as exc:
                        logger.error("fno_dr_entry_failed err=%s", str(exc))
                    finally:
                        summary["stage_durations_sec"]["defined_risk_entry_admission"] = round(
                            monotonic() - entry_started, 3
                        )
        except Exception as exc:
            logger.error("fno_dr_block_failed err=%s", str(exc), exc_info=True)
    summary["stage_durations_sec"]["defined_risk"] = round(
        monotonic() - stage_started, 3
    )

    # ---- 2) entries ----------------------------------------------------
    if supplied_now_ist is None:
        now_ist = datetime.now(IST)
        summary["action_clock_ist"] = now_ist.isoformat()
    nm = _now_min(now_ist)
    if not (settings.FNO_ENTRY_START_MIN <= nm < settings.FNO_ENTRY_END_MIN):
        summary["note"] = "outside_entry_window"
        return summary

    nifty_bars = bars
    for spec in trading_underlyings():
        name = spec.name
        if name == settings.FNO_UNDERLYING.upper():
            note, nifty_bars = await _single_leg_entries(
                kite, db_path, name, instruments, fut, summary, bars=bars, sig=sig, snap=snap, rvol_bars=None,
                regime=regime, now_ist=now_ist, evaluation_now_ist=evaluation_now_ist, scan_id=scan_id,
                is_trading_day=is_trading_day, action_clock=action_clock,
                paper_exec=paper_exec, live_exec=live_exec,
            )
            summary["note"] = note
            continue
        book = get_instruments_for(name)
        other_fut = book.front_future(now_ist.date()) if book.ready(now_ist.date()) else None
        if other_fut is None:
            summary.setdefault("notes_by_underlying", {})[name] = "instruments_not_ready"
            continue
        rvol_bars = None
        if spec.rvol_source:
            if nifty_bars is None:
                try:
                    nifty_bars = await _fetch_futures_bars(kite, fut.token, evaluation_now_ist)
                except Exception as exc:
                    logger.error("fno_futures_bars_failed underlying=NIFTY err=%s", str(exc))
                    summary.setdefault("notes_by_underlying", {})[name] = "rvol_source_unavailable"
                    continue
            rvol_bars = nifty_bars
        note, _ = await _single_leg_entries(
            kite, db_path, name, book, other_fut, summary, bars=None, sig=None, snap=None, rvol_bars=rvol_bars,
            regime=regime, now_ist=now_ist, evaluation_now_ist=evaluation_now_ist, scan_id=scan_id,
            is_trading_day=is_trading_day, action_clock=action_clock, paper_exec=paper_exec, live_exec=live_exec,
        )
        summary.setdefault("notes_by_underlying", {})[name] = note
    return summary


async def _single_leg_entries(
    kite, db_path: str, name: str, book, fut, summary: dict, *, bars, sig, snap, rvol_bars,
    regime: str, now_ist: datetime, evaluation_now_ist: datetime, scan_id: str, is_trading_day: bool,
    action_clock: Optional[Callable[[], datetime]], paper_exec: FnoExecutor, live_exec: FnoExecutor,
) -> tuple[str, object]:
    """One underlying's single-leg entry pass; returns (note, futures bars).

    ``bars``/``sig``/``snap`` may arrive tick-local (NIFTY shares them with the
    capped-loss book). ``rvol_bars`` is the participation frame for an
    underlying whose own futures volume is unusable (SENSEX -> NIFTY).
    """
    stages = (summary["stage_durations_sec"] if name == settings.FNO_UNDERLYING.upper()
              else summary.setdefault("stage_durations_by_underlying", {}).setdefault(name, {}))
    shadow = _schedule_shadow_observation if name == settings.FNO_UNDERLYING.upper() else (lambda *a, **k: None)
    if bars is None:
        stage_started = monotonic()
        try:
            bars = await _fetch_futures_bars(kite, fut.token, evaluation_now_ist)
        except Exception as exc:
            logger.error("fno_futures_bars_failed err=%s", str(exc))
            return "futures_bars_failed", bars
        finally:
            stages["futures_history"] = round(
                monotonic() - stage_started, 3
            )

    if sig is None:
        stage_started = monotonic()
        # The NIFTY call is unchanged; only a borrowed participation frame
        # (SENSEX -> NIFTY) adds the keyword.
        sig = (evaluate_fno_mom(bars, regime, evaluation_now_ist) if rvol_bars is None
               else evaluate_fno_mom(bars, regime, evaluation_now_ist, rvol_bars=rvol_bars))
        stages["entry_evaluation"] = round(
            monotonic() - stage_started, 3
        )
    if not sig.bar_ts:
        return f"engine:{sig.reject_reason}", bars

    # One evaluation per closed bar per leg (restart-safe): if this leg
    # already recorded an entry for the bar, or the engine says no signal,
    # log at most one no-signal row per bar.
    if sig.direction is None:
        shadow(db_path, bars, regime, now_ist)
        # Only log the no-signal outcome once per bar (the tick fires
        # every 60s; a 5-min bar would otherwise produce 5 duplicates).
        if not await _bar_already_logged(db_path, sig.bar_ts, underlying=name):
            await log_fno_signal(
                db_path, scan_id=scan_id, leg="ENGINE", accepted=False,
                reject_reason=sig.reject_reason, bar_ts=sig.bar_ts,
                underlying=name, regime=regime,
                fut_price=sig.close, or_high=sig.or_high, or_low=sig.or_low,
                atr=sig.atr, rvol=sig.rvol,
                ema_fast=sig.ema_fast, ema_slow=sig.ema_slow,
            )
        return f"no_signal:{sig.reject_reason}", bars

    # Signal fired: snapshot the chain once, then run both legs off it.
    if snap is None:
        snap = await take_chain_snapshot(kite, book, now_ist)
    if snap is None:
        shadow(db_path, bars, regime, now_ist)
        await log_fno_signal(
            db_path, scan_id=scan_id, leg="ENGINE", accepted=False,
            reject_reason="chain_unavailable", bar_ts=sig.bar_ts,
            underlying=name,
            direction=sig.direction.value, regime=regime,
        )
        return "chain_unavailable", bars

    stage_started = monotonic()
    if not settings.FNO_DISABLE_PAPER:
        paper_equity = await _fno_equity(db_path, FnoSource.FNO_PAPER.value)
        if await fpos.already_entered_bar(db_path, FnoSource.FNO_PAPER.value, sig.bar_ts, underlying=name):
            logger.info("fno_entry_skip source=FNO_PAPER reason=bar_already_entered")
        else:
            try:
                entry = await _try_entry_for_leg(
                    kite, db_path, FnoSource.FNO_PAPER.value, paper_equity,
                    paper_exec, sig, snap, regime, now_ist, scan_id, is_trading_day,
                    action_clock=action_clock, shared_pool_rs=_fno_pool_paper(),
                    underlying=name, underlying_book=book,
                )
                if entry:
                    summary["entries"].append(entry)
            except Exception as exc:
                logger.error("fno_paper_entry_failed err=%s", str(exc), exc_info=True)

    if not settings.FNO_DISABLE_LIVE and book.segment == "NFO":
        # Live exit evidence/recovery accept NFO packets only, so the live
        # leg trades NFO underlyings only.
        # The live leg refuses to arm unless the go-live function returns
        # clean (spec §11) -- and it runs paper-forced unless the master
        # switch is on.
        from fno_risk import fno_go_live_check
        unmet = await fno_go_live_check(db_path)
        # [AFFORDABILITY-SEAM 2026-09-13] The number of rupees a growth
        # path would request is computed here, currently always 0 because
        # live growth is not implemented in this orchestrator. When the
        # operator enables live-growth via the promotion-bridge contract
        # (see ``docs/2026-09-13-workflow-g-promotion-bridge.md``), the
        # wire-up lives at this exact site: take the growth request, call
        # ``affordability.assert_live_entry_safety(db_path=db_path,
        # live_source=FnoSource.FNO_LIVE.value,
        # paper_source=FnoSource.FNO_PAPER.value, proposed_delta_inr=delta)``
        # and refuse if it raises ``AffordabilityRefusal``. The guard
        # module is *pure* and ledger-bound; no live trading will ever
        # go through without consulting it.
        _pending_live_growth_inr = 0.0
        if _pending_live_growth_inr > 0:
            try:
                from affordability import AffordabilityRefusal, assert_live_entry_safety
                await assert_live_entry_safety(
                    db_path=db_path,
                    live_source=FnoSource.FNO_LIVE.value,
                    paper_source=FnoSource.FNO_PAPER.value,
                    proposed_delta_inr=_pending_live_growth_inr,
                )
            except AffordabilityRefusal as refusal:
                logger.critical(
                    "fno_live_growth_refused delta=%.2f reason=%s",
                    _pending_live_growth_inr, refusal.result.summary(),
                )
                unmet = list(unmet) + ["affordability_guard_refused"]
        live_equity = await _fno_equity(db_path, FnoSource.FNO_LIVE.value)
        if unmet:
            logger.warning("fno_live_leg_refused_to_arm unmet=%s", unmet)
        elif _fno_halted(live_equity, _fno_pool_live(), FnoSource.FNO_LIVE.value):
            logger.info("fno_entry_skip source=FNO_LIVE reason=drawdown_halt")
        elif await fpos.already_entered_bar(db_path, FnoSource.FNO_LIVE.value, sig.bar_ts, underlying=name):
            logger.info("fno_entry_skip source=FNO_LIVE reason=bar_already_entered")
        else:
            try:
                entry = await _try_entry_for_leg(
                    kite, db_path, FnoSource.FNO_LIVE.value, live_equity,
                    live_exec, sig, snap, regime, now_ist, scan_id, is_trading_day,
                    action_clock=action_clock, shared_pool_rs=_fno_pool_live(),
                    underlying=name, underlying_book=book,
                )
                if entry:
                    summary["entries"].append(entry)
            except Exception as exc:
                logger.error("fno_live_entry_failed err=%s", str(exc), exc_info=True)
    stages["entry_management"] = round(
        monotonic() - stage_started, 3
    )

    # Only after both trading legs have completed, and never awaited: a
    # slow/locked research DB cannot delay quote selection, sizing, an entry,
    # or the tick return. Reuse the baseline's already-resolved chain.
    shadow(db_path, bars, regime, now_ist, snap)
    return "", bars


async def run_fno_fast_exit(kite, db_path: Optional[str] = None, now_ist: Optional[datetime] = None) -> dict:
    """[FAST-EXIT 2026-10-04] Manage open single-leg positions between ticks.

    Options cannot carry an exchange stop order, so the underlying/premium
    stops are only as fast as the loop that checks them. This entry point does
    nothing but the shared single-leg management (no entries, no defined-risk
    work) and returns after one database read when no position is open. It is
    scheduled only when FNO_FAST_EXIT_ENABLED is on and is serialised with the
    regular tick by the scheduler's F&O lock.
    """
    db_path = db_path or settings.DB_PATH
    supplied_now_ist = now_ist
    now_ist = now_ist or datetime.now(IST)
    action_clock = (lambda: datetime.now(IST)) if supplied_now_ist is None else None
    tick_started = monotonic()
    summary: dict = {"scan_id": f"FNOX-{now_ist.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}",
                     "entries": [], "exits": [], "note": "", "stage_durations_sec": {},
                     "management_read_outcomes": {},
                     "database_stage_timing": {"measurement": "operation_elapsed_includes_sqlite_lock_wait",
                                               "stages": {}}}
    sources = [] if settings.FNO_DISABLE_PAPER else [FnoSource.FNO_PAPER.value]
    if not settings.FNO_DISABLE_LIVE:
        sources.append(FnoSource.FNO_LIVE.value)
    open_count = 0
    for source in sources:
        open_count += len(await fpos.open_positions(db_path, source))
    if not open_count:
        summary["note"] = "no_open_positions"
        return summary
    instruments = get_fno_instruments()
    if not instruments.ready(now_ist.date()) and not instruments.load_from_disk():
        summary["note"] = "instruments_not_ready"
        return summary
    fut = instruments.front_future(now_ist.date())
    if fut is None:
        summary["note"] = "no_front_future"
        return summary
    paper_exec = FnoExecutor(kite, paper_mode=True, source_tag=FnoSource.FNO_PAPER.value)
    live_exec = FnoExecutor(kite, paper_mode=not bool(settings.FNO_LIVE_TRADING),
                            source_tag=FnoSource.FNO_LIVE.value)
    await _manage_single_leg_books(
        kite, db_path, fut, summary, paper_exec, live_exec, now_ist=now_ist,
        supplied_now_ist=supplied_now_ist, tick_started=tick_started, action_clock=action_clock,
    )
    summary["note"] = "managed"
    return summary


async def _bar_already_logged(db_path: str, bar_ts: str, underlying: Optional[str] = None) -> bool:
    import aiosqlite
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_signals'"
            ) as cur:
                if await cur.fetchone() is None:
                    return False
            sql, params = "SELECT 1 FROM fno_signals WHERE bar_ts=?", [bar_ts]
            if underlying is not None:
                sql, params = sql + " AND underlying=?", params + [underlying]
            async with db.execute(sql + " LIMIT 1", params) as cur:
                return (await cur.fetchone()) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Telegram formatting (delivery owned by main.py, like penny edge)
# ---------------------------------------------------------------------------

def format_fno_telegram(summary: dict) -> str:
    """[PAPER-MARKING 2026-08-04] Every rupee figure here is tagged paper or
    live via performance.fmt_money.

    This book has never held real capital, yet its exits rendered exactly like
    the live momentum book's: on 2026-08-03 it reported `pnl=Rs -730` beside a
    genuine live loss of Rs 8.41 the same day. Two numbers 87x apart,
    identically formatted, distinguished only by a bracketed source tag in the
    middle of the line.
    """
    from performance import fmt_money, is_paper_source

    out = [f"*F&O tick* `{summary.get('scan_id', '?')}`"]
    for e in summary.get("entries", []):
        tag = " (paper)" if is_paper_source(e["source"]) else ""
        out.append(
            f"ENTRY [{e['source']}]{tag} `{e['symbol']}` {e['direction']} "
            f"lots={e['lots']} @ {e['fill']:.2f} delta={e['delta']} iv={e['iv']}"
        )
    for x in summary.get("exits", []):
        out.append(
            f"EXIT [{x['source']}] `{x['symbol']}` {x['reason']} "
            f"{x['entry']:.2f} -> {x['exit']:.2f} "
            f"pnl={fmt_money(x['pnl'], x['source'])} ({x['r']:+.2f}R)"
        )
    # Defined-risk (DR) structures live in a separate, paper-only ledger.
    # They must still make an immediate notification eligible even when no
    # single-leg entry/exit occurred in the same tick.
    for structure_id in summary.get("dr_opened", []):
        out.append(f"DR OPEN [FNO_DR_PAPER] structure_id={structure_id}")
    dr_exits = int(summary.get("dr_exits") or 0)
    if dr_exits:
        out.append(f"DR CLOSE [FNO_DR_PAPER] count={dr_exits}; detailed lifecycle records are in fno_dr structures")
    if len(out) == 1:
        out.append("No activity.")
    return "\n".join(out)
