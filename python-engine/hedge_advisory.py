"""Hedge-first partner advisory orchestration.

Only reconciled positions and live, two-sided exchange quotes can produce a
review.  This module has no execution path.  Missing positions, stale prices,
unsupported expiries and incomplete volatility data all fail closed.
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
import weakref
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Optional

import aiosqlite
import pytz
import structlog

import fno_analytics
from config import settings
from fno_chain import ChainSnapshot, take_chain_snapshot, years_to_expiry
from fno_underlyings import get_instruments_for
from hedge_analytics import (
    PartnerPosition, aggregate_portfolio, assess_quote_freshness, init_hedge_db,
    iv_percentile, load_chain_iv_history,
    load_reconciled_open_partner_positions, position_is_actionable,
    size_futures_hedge, vix_regime_reading, gamma_exposure_at_expiry,
    classify_event_window, classify_range_regime, iv_term_structure,
    load_aligned_ohlcv_closes, portfolio_market_stress,
    PortfolioMarketStressReading,
)
from hedge_formatters import (
    format_bear_call_spread, format_bull_put_spread,
    format_collar_recommendation, format_covered_call_recommendation,
    format_delta_hedge_rebalance, format_futures_hedge_size,
    format_iron_condor, format_protective_put_alert, format_vix_hedge_alert,
    format_long_vol_review, format_iron_butterfly,
    format_calendar_diary_spread, format_gamma_exposure_alert,
    format_earnings_event_hedge, format_portfolio_corruption_overlay,
)
from hedge_strategies import (
    bear_call_spread, bull_put_spread, collar_recommendation,
    covered_call_recommendation, delta_hedge_rebalance, futures_hedge_size,
    iron_condor, protective_put_alert,
    iron_butterfly, long_straddle, long_strangle, calendar_diary_spread,
)
from partner_bot import partner_enabled, send_partner

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")
Phase2MarketMode = Literal[
    "BULL_TREND", "BEAR_TREND", "RANGE", "CRISIS", "UNKNOWN"
]
_VERIFIED_DELIVERABLE_SOURCES = frozenset({
    "broker_holding_snapshot", "kite_holdings",
})


@dataclass(frozen=True)
class Phase2MarketContext:
    """Verified inputs that gate premium-selling Phase 2 reviews."""

    mode: Phase2MarketMode
    atm_iv: Optional[float]
    realized_vol: Optional[float]
    iv_rank: Optional[float]
    support: Optional[float]
    resistance: Optional[float]
    expected_move: Optional[float]
    as_of: datetime

    def __post_init__(self) -> None:
        if self.mode not in {"BULL_TREND", "BEAR_TREND", "RANGE", "CRISIS", "UNKNOWN"}:
            raise ValueError("unsupported Phase 2 market mode")
        _aware(self.as_of, "context as_of")
        for name in ("atm_iv", "realized_vol", "support", "resistance", "expected_move"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(float(value)) or float(value) <= 0):
                raise ValueError(f"{name} must be positive and finite")
        if self.iv_rank is not None and (
            not math.isfinite(float(self.iv_rank)) or not 0 <= float(self.iv_rank) <= 1
        ):
            raise ValueError("iv_rank must be within [0, 1]")


@dataclass(frozen=True)
class Phase3MarketContext:
    """Explicit Phase-3 inputs; unknown event/correlation values suppress output."""

    phase2: Phase2MarketContext
    event_window: str = "UNKNOWN"
    correlation: Optional[float] = None
    gamma_exposure: Optional[float] = None
    back_atm_iv: Optional[float] = None
    portfolio_stress: Optional[PortfolioMarketStressReading] = None

_ADVISORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS partner_vix_history (
    observed_at TEXT PRIMARY KEY,
    spot REAL NOT NULL,
    source TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_hedge_messages (
    kind TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    delivered INTEGER NOT NULL,
    detail TEXT,
    claim_token TEXT,
    PRIMARY KEY (kind, dedup_key)
);
"""
_ADVISORY_INIT_LOCKS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


async def init_hedge_advisory_db(db_path: str) -> None:
    loop = asyncio.get_running_loop()
    loop_locks = _ADVISORY_INIT_LOCKS.setdefault(loop, {})
    lock = loop_locks.setdefault(str(db_path), asyncio.Lock())
    async with lock:
        await init_hedge_db(db_path)
        async with aiosqlite.connect(db_path, timeout=30) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.executescript(_ADVISORY_SCHEMA)
            cur = await db.execute("PRAGMA table_info(partner_hedge_messages)")
            columns = {row[1] for row in await cur.fetchall()}
            if "claim_token" not in columns:
                await db.execute(
                    "ALTER TABLE partner_hedge_messages ADD COLUMN claim_token TEXT"
                )
            await db.commit()


async def record_vix_observation(
    db_path: str, *, spot: float, observed_at: datetime, source: str,
) -> None:
    """Persist a timestamped VIX observation supplied by a named source.

    The source is deliberately external to this module: Sentinel currently has
    no verified live India-VIX feed and must not manufacture one.
    """
    _aware(observed_at, "observed_at")
    if not math.isfinite(float(spot)) or float(spot) <= 0:
        raise ValueError("spot must be positive and finite")
    source = str(source).strip()
    if not source:
        raise ValueError("source is required")
    await init_hedge_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO partner_vix_history "
            "(observed_at, spot, source, ingested_at) VALUES (?,?,?,?)",
            (observed_at.isoformat(), float(spot), source,
             datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def load_vix_observations(db_path: str, limit: int = 252) -> list[dict]:
    if limit <= 0:
        return []
    await init_hedge_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT observed_at, spot, source FROM partner_vix_history "
            "ORDER BY observed_at DESC LIMIT ?", (int(limit),),
        )
        rows = await cur.fetchall()
    return [
        {"observed_at": datetime.fromisoformat(row[0]), "spot": float(row[1]),
         "source": row[2]}
        for row in reversed(rows)
    ]


async def _claim(
    db_path: str,
    kind: str,
    key: str,
    *,
    now: datetime,
    underlying: Optional[str] = None,
    min_gap: Optional[timedelta] = None,
    daily_cap: Optional[int] = None,
    lease: timedelta = timedelta(hours=1),
) -> Optional[str]:
    """Atomically reserve one send and enforce delivered-message limits."""
    now = _aware(now, "now").astimezone(IST)
    await init_hedge_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT sent_at, delivered FROM partner_hedge_messages "
            "WHERE kind=? AND dedup_key=?", (kind, key),
        )
        existing = await cur.fetchone()
        if existing is not None:
            try:
                claimed_at = datetime.fromisoformat(existing[0]).astimezone(IST)
            except (TypeError, ValueError):
                claimed_at = now
            if bool(existing[1]) or now - claimed_at < lease:
                await db.rollback()
                return None

        cur = await db.execute(
            "SELECT dedup_key, sent_at FROM partner_hedge_messages "
            "WHERE kind=? AND delivered=1", (kind,),
        )
        delivered_rows = await cur.fetchall()
        applicable: list[datetime] = []
        for prior_key, raw_stamp in delivered_rows:
            if underlying and not str(prior_key).startswith(f"{underlying}:"):
                continue
            try:
                applicable.append(datetime.fromisoformat(raw_stamp).astimezone(IST))
            except (TypeError, ValueError):
                continue
        today_rows = [stamp for stamp in applicable if stamp.date() == now.date()]
        if daily_cap is not None and daily_cap >= 0 and len(today_rows) >= daily_cap:
            await db.rollback()
            return None
        if min_gap is not None and applicable and now - max(applicable) < min_gap:
            await db.rollback()
            return None

        token = uuid.uuid4().hex
        await db.execute(
            "INSERT OR REPLACE INTO partner_hedge_messages "
            "(kind, dedup_key, sent_at, delivered, detail, claim_token) "
            "VALUES (?,?,?,?,?,?)",
            (kind, key, now.isoformat(), 0,
             json.dumps({"state": "claimed"}, sort_keys=True), token),
        )
        await db.commit()
        return token


async def _record(
    db_path: str, kind: str, key: str, delivered: bool,
    *, detail: Optional[dict] = None, now: Optional[datetime] = None,
) -> None:
    now = _aware(now or datetime.now(IST), "now")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO partner_hedge_messages "
            "(kind, dedup_key, sent_at, delivered, detail) VALUES (?,?,?,?,?)",
            (kind, key, now.isoformat(), int(delivered),
             json.dumps(detail or {}, sort_keys=True, default=str)),
        )
        await db.commit()


async def _complete_claim(
    db_path: str, kind: str, key: str, token: str, *, detail: dict, now: datetime,
) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "UPDATE partner_hedge_messages SET sent_at=?, delivered=1, detail=?, "
            "claim_token=NULL WHERE kind=? AND dedup_key=? AND delivered=0 "
            "AND claim_token=?",
            (now.isoformat(), json.dumps(detail, sort_keys=True, default=str),
             kind, key, token),
        )
        await db.commit()
        return cur.rowcount == 1


async def _release_claim(
    db_path: str, kind: str, key: str, token: Optional[str] = None,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        if token is None:
            await db.execute(
                "DELETE FROM partner_hedge_messages "
                "WHERE kind=? AND dedup_key=? AND delivered=0", (kind, key),
            )
        else:
            await db.execute(
                "DELETE FROM partner_hedge_messages WHERE kind=? AND dedup_key=? "
                "AND delivered=0 AND claim_token=?", (kind, key, token),
            )
        await db.commit()


async def _send_claimed_review(
    db_path: str, kind: str, key: str, text: str, *,
    detail: dict, now: datetime, underlying: Optional[str] = None,
    min_gap: Optional[timedelta] = None, daily_cap: Optional[int] = None,
) -> bool:
    token = await _claim(
        db_path, kind, key, now=now, underlying=underlying,
        min_gap=min_gap, daily_cap=daily_cap,
    )
    if token is None:
        return False
    try:
        delivered = bool(await send_partner(text, kind=kind))
        if delivered:
            return await _complete_claim(
                db_path, kind, key, token, detail=detail, now=now,
            )
        else:
            await _release_claim(db_path, kind, key, token)
        return False
    except Exception:
        await _release_claim(db_path, kind, key, token)
        raise


def _settings_kwargs() -> dict:
    return {
        "max_spread_pct": settings.PARTNER_HEDGE_MAX_SPREAD_PCT,
        "max_age_sec": settings.PARTNER_HEDGE_MAX_QUOTE_AGE_SEC,
        "min_oi": settings.PARTNER_HEDGE_MIN_OI,
        "min_volume": settings.PARTNER_HEDGE_MIN_VOLUME,
    }


def build_hedge_reviews(
    positions: Iterable[PartnerPosition], snapshot: ChainSnapshot,
    *, now: datetime,
) -> list[tuple[str, object, Optional[object]]]:
    """Build approved Phase-1 reviews for one hedge underlying.

    Returns ``(kind, plan, sizing_context)``. No message is produced when any
    position is stale or unreconciled.
    """
    _aware(now, "now")
    positions = tuple(positions)
    max_age = timedelta(minutes=settings.PARTNER_HEDGE_POSITION_MAX_AGE_MIN)
    if not positions or any(
        not position_is_actionable(p, now=now, max_quote_age=max_age)
        for p in positions
    ):
        return []
    exposure = aggregate_portfolio(positions)
    if not exposure.valid or exposure.underlyings != (positions[0].underlying,):
        return []
    if snapshot.forward <= 0 or positions[0].underlying != (
        snapshot.fut_quote.contract.name if snapshot.fut_quote else positions[0].underlying
    ):
        return []

    reviews: list[tuple[str, object, Optional[object]]] = []
    unhedged_notional = max(exposure.net_delta_notional, 0.0)
    equivalent_units = int(unhedged_notional // snapshot.forward)
    common = _settings_kwargs()
    if settings.PARTNER_HEDGE_PROTECTIVE_PUT and equivalent_units >= snapshot.lot_size:
        plan = protective_put_alert(
            snapshot, equivalent_units, now,
            put_delta=settings.PARTNER_HEDGE_PUT_DELTA, **common,
        )
        if plan is not None:
            reviews.append(("protective_put_alert", plan, exposure))

    if settings.PARTNER_HEDGE_FUTURES:
        sizing = size_futures_hedge(
            exposure, futures_underlying=positions[0].underlying,
            lot_size=(snapshot.fut_quote.contract.lot_size
                      if snapshot.fut_quote else snapshot.lot_size),
            futures_price=snapshot.forward,
            target_hedge_ratio=settings.PARTNER_HEDGE_TARGET_RATIO,
        )
        if sizing.valid and sizing.contracts_rounded:
            additional_notional = (
                abs(sizing.contracts_rounded) * sizing.lot_size * snapshot.forward
            )
            plan = futures_hedge_size(
                snapshot, additional_notional, beta=1.0, hedge_ratio=1.0,
                now_ist=now, **common,
            )
            if plan is not None:
                reviews.append(("futures_hedge_size", plan, sizing))

    # A collar writes a call. It is only admitted automatically when a single
    # verified deliverable holding exactly matches the option underlying units.
    if settings.PARTNER_HEDGE_COLLAR and len(positions) == 1:
        position = positions[0]
        covered_units = _verified_deliverable_units(
            positions, position.underlying, now,
        )
        aligned = (
            position.instrument_type == "EQUITY"
            and covered_units == position.signed_quantity
            and covered_units > 0
            and covered_units % snapshot.lot_size == 0
        )
        if aligned:
            plan = collar_recommendation(
                snapshot, covered_units, now,
                put_delta=settings.PARTNER_HEDGE_PUT_DELTA,
                call_delta=settings.PARTNER_HEDGE_CALL_DELTA, **common,
            )
            if plan is not None:
                reviews.append(("collar_recommendation", plan, exposure))
    return reviews


def _snapshot_underlying(snapshot: ChainSnapshot) -> Optional[str]:
    names = {
        str(q.contract.name).strip().upper()
        for q in snapshot.quotes.values() if q is not None
    }
    if snapshot.fut_quote is not None:
        names.add(str(snapshot.fut_quote.contract.name).strip().upper())
    return next(iter(names)) if len(names) == 1 and next(iter(names), "") else None


def _phase2_positions_valid(
    positions: tuple[PartnerPosition, ...], snapshot: ChainSnapshot, now: datetime,
) -> bool:
    if not positions:
        return False
    max_age = timedelta(minutes=settings.PARTNER_HEDGE_POSITION_MAX_AGE_MIN)
    if any(not position_is_actionable(p, now=now, max_quote_age=max_age) for p in positions):
        return False
    name = _snapshot_underlying(snapshot)
    return bool(name and all(p.underlying == name for p in positions))


def _verified_deliverable_units(
    positions: tuple[PartnerPosition, ...], underlying: str, now: datetime,
) -> int:
    """Return exact covered units only for a current, direct cash holding."""
    if len(positions) != 1:
        return 0
    position = positions[0]
    symbol = position.tradingsymbol.strip().upper().removeprefix("NSE:")
    if (
        position.instrument_type != "EQUITY"
        or position.underlying != underlying
        or symbol != underlying
        or position.signed_quantity <= 0
        or position.deliverable_quantity is None
        or position.deliverable_as_of is None
        or str(position.deliverable_source).strip().lower()
        not in _VERIFIED_DELIVERABLE_SOURCES
        or position.deliverable_as_of.astimezone(IST).date() != now.astimezone(IST).date()
        or position.deliverable_as_of > now + timedelta(seconds=60)
        or now - position.deliverable_as_of
        > timedelta(minutes=settings.PARTNER_HEDGE_DELIVERABLE_MAX_AGE_MIN)
        or position.updated_at is None
        or position.updated_at < position.deliverable_as_of
    ):
        return 0
    return min(position.signed_quantity, position.deliverable_quantity)


def build_phase2_hedge_reviews(
    positions: Iterable[PartnerPosition],
    snapshot: ChainSnapshot,
    context: Phase2MarketContext,
    *,
    now: datetime,
) -> list[tuple[str, object, object]]:
    """Build Phase 2 reviews from verified holdings and market context.

    Premium strategies require their exact volatility/regime/level evidence.
    Delta rebalance is independent of those signals but still uses only a live
    future and whole lots. Missing inputs always produce no recommendation.
    """
    _aware(now, "now")
    if not isinstance(context, Phase2MarketContext):
        return []
    now = now.astimezone(IST)
    positions = tuple(positions)
    if not _phase2_positions_valid(positions, snapshot, now):
        return []
    exposure = aggregate_portfolio(positions)
    underlying = _snapshot_underlying(snapshot)
    if (
        not exposure.valid or underlying is None
        or exposure.underlyings != (underlying,)
        or snapshot.fut_quote is None
        or abs((context.as_of - snapshot.taken_at).total_seconds()) > 1
    ):
        return []

    reviews: list[tuple[str, object, object]] = []
    common = _settings_kwargs()
    iv_rank = context.iv_rank

    if (
        settings.PARTNER_HEDGE_COVERED_CALL
        and iv_rank is not None
        and iv_rank >= settings.PARTNER_HEDGE_COVERED_CALL_IV_RANK
        and context.resistance is not None
    ):
        covered_units = _verified_deliverable_units(positions, underlying, now)
        if covered_units >= snapshot.lot_size:
            plan = covered_call_recommendation(
                snapshot, covered_units, now,
                short_call_delta=settings.PARTNER_HEDGE_COVERED_CALL_DELTA,
                min_dte=7, **common,
            )
            # Never cap the holding below the verified resistance wall.
            if plan is not None and plan.call_strike >= context.resistance:
                reviews.append(("covered_call_recommendation", plan, context))

    if (
        settings.PARTNER_HEDGE_BULL_PUT_SPREAD
        and exposure.net_delta_notional < 0
        and context.mode == "BULL_TREND"
        and iv_rank is not None
        and iv_rank >= settings.PARTNER_HEDGE_SPREAD_IV_RANK
        and context.support is not None
    ):
        plan = bull_put_spread(
            snapshot, now,
            short_delta=settings.PARTNER_HEDGE_SPREAD_SHORT_DELTA,
            width=settings.PARTNER_HEDGE_SPREAD_WIDTH,
            min_credit=settings.PARTNER_HEDGE_MIN_CREDIT_POINTS,
            **common,
        )
        if plan is not None and plan.short_strike <= context.support:
            reviews.append(("bull_put_spread", plan, context))

    if (
        settings.PARTNER_HEDGE_BEAR_CALL_SPREAD
        and exposure.net_delta_notional > 0
        and context.mode in {"BEAR_TREND", "RANGE"}
        and iv_rank is not None
        and iv_rank >= settings.PARTNER_HEDGE_SPREAD_IV_RANK
        and context.resistance is not None
    ):
        plan = bear_call_spread(
            snapshot, now,
            short_delta=settings.PARTNER_HEDGE_SPREAD_SHORT_DELTA,
            width=settings.PARTNER_HEDGE_SPREAD_WIDTH,
            min_credit=settings.PARTNER_HEDGE_MIN_CREDIT_POINTS,
            **common,
        )
        if plan is not None and plan.short_strike >= context.resistance:
            reviews.append(("bear_call_spread", plan, context))

    if (
        settings.PARTNER_HEDGE_IRON_CONDOR
        and context.mode == "RANGE"
        and iv_rank is not None
        and iv_rank >= settings.PARTNER_HEDGE_CONDOR_IV_RANK
        and context.atm_iv is not None
        and context.realized_vol is not None
        and context.atm_iv > context.realized_vol
        and context.support is not None
        and context.resistance is not None
        and context.expected_move is not None
        and context.resistance - context.support >= 2 * context.expected_move
    ):
        plan = iron_condor(
            snapshot, now,
            short_put_delta=settings.PARTNER_HEDGE_CONDOR_SHORT_DELTA,
            short_call_delta=settings.PARTNER_HEDGE_CONDOR_SHORT_DELTA,
            wing_width=settings.PARTNER_HEDGE_CONDOR_WING_WIDTH,
            min_credit=settings.PARTNER_HEDGE_MIN_CREDIT_POINTS,
            **common,
        )
        if (
            plan is not None
            and plan.short_put_strike <= context.support
            and plan.short_call_strike >= context.resistance
        ):
            reviews.append(("iron_condor", plan, context))

    if settings.PARTNER_HEDGE_DELTA_REBALANCE:
        lot_size = snapshot.fut_quote.contract.lot_size
        if lot_size > 0:
            plan = delta_hedge_rebalance(
                snapshot,
                exposure.net_greeks.delta / lot_size,
                target_net_delta=0.0,
                now_ist=now,
                delta_threshold=settings.PARTNER_HEDGE_DELTA_THRESHOLD_LOTS,
                **common,
            )
            if plan is not None:
                reviews.append(("delta_hedge_rebalance", plan, context))
    return reviews


def _format_review(kind: str, plan: object, context: Optional[object]) -> str:
    if kind == "protective_put_alert":
        return format_protective_put_alert(plan)
    if kind == "collar_recommendation":
        return format_collar_recommendation(
            plan, existing_hedge_pct=getattr(context, "hedged_pct", None),
        )
    if kind == "futures_hedge_size":
        return format_futures_hedge_size(
            plan,
            existing_hedge_pct=getattr(context, "existing_hedge_pct", None),
            post_hedge_pct=getattr(context, "post_trade_hedge_pct", None),
        )
    raise ValueError(f"unsupported hedge review kind: {kind}")


def build_phase3_hedge_reviews(
    positions: Iterable[PartnerPosition], snapshot: ChainSnapshot,
    context: Phase3MarketContext, *, now: datetime,
    back_snapshot: Optional[ChainSnapshot] = None,
) -> list[tuple[str, object, object]]:
    """Build only Phase-3 reviews supported by explicit, current evidence."""
    _aware(now, "now")
    positions = tuple(positions)
    if not isinstance(context, Phase3MarketContext) or not _phase2_positions_valid(positions, snapshot, now):
        return []
    result: list[tuple[str, object, object]] = []
    common = _settings_kwargs()
    p2 = context.phase2
    if (settings.PARTNER_HEDGE_GAMMA_ALERT and context.gamma_exposure is not None
            and abs(context.gamma_exposure) >= settings.PARTNER_HEDGE_PHASE3_GAMMA_THRESHOLD):
        result.append(("gamma_exposure_alert", context.gamma_exposure, context))
    if (p2.iv_rank is not None and p2.iv_rank <= settings.PARTNER_HEDGE_PHASE3_LOW_IV_RANK
            and context.event_window in {"EARNINGS_TODAY", "EARNINGS_TOMORROW", "MACRO_HOUR"}):
        if settings.PARTNER_HEDGE_LONG_STRADDLE:
            plan = long_straddle(snapshot, now, **common)
            if plan is not None:
                result.append(("long_straddle", plan, context))
        if settings.PARTNER_HEDGE_LONG_STRANGLE:
            plan = long_strangle(snapshot, now,
                target_delta=settings.PARTNER_HEDGE_PHASE3_LONG_DELTA, **common)
            if plan is not None:
                result.append(("long_strangle", plan, context))
    dte = (snapshot.expiry - now.astimezone(IST).date()).days
    if (settings.PARTNER_HEDGE_IRON_BUTTERFLY and p2.mode == "RANGE"
            and 1 <= dte <= settings.PARTNER_HEDGE_BUTTERFLY_MAX_DTE
            and p2.iv_rank is not None and p2.iv_rank >= settings.PARTNER_HEDGE_BUTTERFLY_IV_RANK):
        plan = iron_butterfly(snapshot, now,
            wing_width=settings.PARTNER_HEDGE_PHASE3_WING_WIDTH,
            min_credit=settings.PARTNER_HEDGE_MIN_CREDIT_POINTS, **common)
        if plan is not None:
            result.append(("iron_butterfly", plan, context))
    if (settings.PARTNER_HEDGE_CALENDAR_SPREAD and back_snapshot is not None
            and p2.atm_iv is not None and context.back_atm_iv is not None
            and p2.atm_iv - context.back_atm_iv
            >= settings.PARTNER_HEDGE_CALENDAR_MIN_IV_GAP):
        plan = calendar_diary_spread(snapshot, back_snapshot, now, **common)
        if plan is not None:
            result.append(("calendar_diary_spread", plan, context))
    # Ratio spreads are intentionally not emitted: their naked 1x2 tail is
    # unbounded. The research builder requires an explicit opt-in unavailable
    # to this runtime.
    if (settings.PARTNER_HEDGE_EARNINGS_EVENT
            and context.event_window in {"EARNINGS_TODAY", "EARNINGS_TOMORROW"}):
        plan = long_strangle(snapshot, now,
            target_delta=settings.PARTNER_HEDGE_PHASE3_LONG_DELTA, **common)
        if plan is not None:
            result.append(("earnings_event_hedge", plan, context))
    if (
        settings.PARTNER_HEDGE_PORTFOLIO_OVERLAY
        and context.portfolio_stress is not None
        and context.portfolio_stress.correlation_breadth_valid
        and context.portfolio_stress.should_review_overlay
        and context.correlation is not None
    ):
        exposure = aggregate_portfolio(positions)
        if exposure.valid and exposure.long_delta_notional > 0:
            plan = futures_hedge_size(snapshot, exposure.long_delta_notional,
                                      hedge_ratio=.5, now_ist=now, **common)
            if plan is not None:
                result.append(("portfolio_corruption_overlay", plan, context))
    return result


def _phase2_trigger_quote_current(quote, snapshot: ChainSnapshot, now: datetime) -> bool:
    if quote is None or not quote.two_sided:
        return False
    contract = quote.contract
    key = (float(contract.strike), str(contract.instrument_type))
    if (
        snapshot.quotes.get(key) is not quote
        or contract.expiry != snapshot.expiry
        or contract.lot_size != snapshot.lot_size
        or contract.token <= 0
        or quote.spread_pct > settings.PARTNER_HEDGE_MAX_SPREAD_PCT
        or quote.oi < settings.PARTNER_HEDGE_MIN_OI
        or quote.volume < settings.PARTNER_HEDGE_MIN_VOLUME
    ):
        return False
    return assess_quote_freshness(
        quote.last_trade_time, now=now,
        max_age=timedelta(seconds=settings.PARTNER_HEDGE_MAX_QUOTE_AGE_SEC),
    ).fresh


def _fresh_oi_walls(
    snapshot: ChainSnapshot, now: datetime,
) -> tuple[Optional[float], Optional[float]]:
    support: Optional[float] = None
    resistance: Optional[float] = None
    support_oi = resistance_oi = 0
    for (strike, kind), quote in snapshot.quotes.items():
        if not _phase2_trigger_quote_current(quote, snapshot, now):
            continue
        if kind == "PE" and strike <= snapshot.forward and quote.oi > support_oi:
            support, support_oi = strike, quote.oi
        if kind == "CE" and strike >= snapshot.forward and quote.oi > resistance_oi:
            resistance, resistance_oi = strike, quote.oi
    return support, resistance


async def _phase2_market_context(
    db_path: str, snapshot: ChainSnapshot, now: datetime,
) -> Phase2MarketContext:
    """Assemble only auditable market inputs; unknown modes stay unknown."""
    import main as _main
    import partner_orchestrator as _legacy

    last_run = getattr(_main, "last_run", None)
    regime_current = bool(
        isinstance(last_run, datetime)
        and last_run.tzinfo is not None
        and last_run.utcoffset() is not None
        and last_run.astimezone(IST).date() == now.date()
        and timedelta(0) <= now - last_run.astimezone(IST) <= timedelta(hours=8)
    )
    broad_regime = str(_main._fno_regime_str() or "UNKNOWN") if regime_current else "UNKNOWN"
    directional = (
        str(getattr(_main, "market_regime", "UNKNOWN") or "UNKNOWN")
        if regime_current else "UNKNOWN"
    )
    if broad_regime == "REGIME_3_CRISIS":
        mode: Phase2MarketMode = "CRISIS"
    elif directional == "BULL":
        mode = "BULL_TREND"
    elif directional == "BEAR_RS_ONLY":
        mode = "BEAR_TREND"
    else:
        # A quiet/caution label is not evidence of a range. A separate,
        # current price-and-OI-wall classifier may promote this below.
        mode = "UNKNOWN"

    strikes = sorted({strike for strike, _ in snapshot.quotes})
    atm = min(strikes, key=lambda strike: abs(strike - snapshot.forward)) if strikes else None
    atm_quotes = (
        [snapshot.quotes.get((atm, kind)) for kind in ("CE", "PE")]
        if atm is not None else []
    )
    trigger_quotes_current = bool(
        len(atm_quotes) == 2
        and all(_phase2_trigger_quote_current(q, snapshot, now) for q in atm_quotes)
    )
    skew = fno_analytics.atm_iv_skew(snapshot, now) if trigger_quotes_current else None
    atm_iv = sum(skew) / 2 if skew is not None else None
    history = await load_chain_iv_history(
        db_path, _snapshot_underlying(snapshot) or "UNKNOWN",
        lookback_days=settings.PARTNER_HEDGE_IV_HISTORY_DAYS, now=now,
    )
    rank = (
        iv_percentile(
            atm_iv, [value for _, value in history],
            min_observations=settings.PARTNER_HEDGE_IV_MIN_OBSERVATIONS,
        )
        if atm_iv is not None else None
    )
    support, resistance = _fresh_oi_walls(snapshot, now)
    underlying = _snapshot_underlying(snapshot)
    rv = (
        _legacy._rv_cache.get(underlying)
        if underlying and _legacy._rv_as_of.get(underlying) == now.date()
        else None
    )
    t = years_to_expiry(snapshot.expiry, now)
    expected_move = (
        snapshot.forward * atm_iv * math.sqrt(t)
        if atm_iv is not None and t > 0 else None
    )
    minute = now.astimezone(IST).hour * 60 + now.astimezone(IST).minute
    if mode == "UNKNOWN" and regime_current and minute >= 9 * 60 + 45 and underlying:
        import fno_oi_store

        opening = await fno_oi_store.first_fut_row_today(
            db_path, underlying, now.astimezone(IST).date().isoformat(),
        )
        opening_ltp = opening.get("fut_ltp") if opening else None
        opening_oi = opening.get("fut_oi") if opening else None
        current_oi = snapshot.fut_quote.oi if snapshot.fut_quote else None
        if (
            isinstance(opening_ltp, (int, float)) and opening_ltp > 0
            and abs(snapshot.forward / opening_ltp - 1.0)
            <= settings.PARTNER_HEDGE_RANGE_MAX_MOVE_PCT
        ):
            buildup = "NEUTRAL"
        elif (
            isinstance(opening_ltp, (int, float)) and opening_ltp > 0
            and isinstance(opening_oi, (int, float))
            and isinstance(current_oi, (int, float))
        ):
            buildup = fno_analytics.classify_buildup(
                snapshot.forward - opening_ltp, current_oi - opening_oi,
            )
        else:
            buildup = None
        range_read = classify_range_regime(
            spot=snapshot.forward,
            support=support,
            resistance=resistance,
            expected_move=expected_move,
            futures_buildup=buildup,
            observed_at=snapshot.taken_at,
            now=now,
            max_age=timedelta(seconds=settings.PARTNER_HEDGE_MAX_QUOTE_AGE_SEC),
        )
        if range_read.regime == "RANGE":
            mode = "RANGE"
    return Phase2MarketContext(
        mode=mode, atm_iv=atm_iv, realized_vol=rv, iv_rank=rank,
        support=support, resistance=resistance, expected_move=expected_move,
        as_of=snapshot.taken_at,
    )


def _phase2_context_text(context: Phase2MarketContext) -> str:
    fields = [f"mode={context.mode}"]
    if context.iv_rank is not None:
        fields.append(f"IV rank={context.iv_rank:.0%}")
    if context.atm_iv is not None:
        fields.append(f"ATM IV={context.atm_iv:.1%}")
    if context.realized_vol is not None:
        fields.append(f"20d RV={context.realized_vol:.1%}")
    if context.support is not None:
        fields.append(f"support={context.support:,.0f}")
    if context.resistance is not None:
        fields.append(f"resistance={context.resistance:,.0f}")
    return "; ".join(fields)


def _format_phase2_review(kind: str, plan: object, context: Phase2MarketContext) -> str:
    detail = _phase2_context_text(context)
    if kind == "covered_call_recommendation":
        return format_covered_call_recommendation(plan, context=detail)
    if kind == "bull_put_spread":
        return format_bull_put_spread(plan, context=detail)
    if kind == "bear_call_spread":
        return format_bear_call_spread(plan, context=detail)
    if kind == "iron_condor":
        return format_iron_condor(plan, context=detail)
    if kind == "delta_hedge_rebalance":
        return format_delta_hedge_rebalance(plan, context=detail)
    raise ValueError(f"unsupported Phase 2 review kind: {kind}")


def _format_phase3_review(kind: str, value: object, context: Phase3MarketContext, now: datetime) -> str:
    detail = _phase2_context_text(context.phase2) + f"; event={context.event_window}"
    if context.portfolio_stress is not None:
        stress = context.portfolio_stress
        if stress.breadth_pct_above_sma is not None:
            detail += f"; breadth={stress.breadth_pct_above_sma:.0%}"
        if stress.drawdown_pct is not None:
            detail += f"; drawdown={stress.drawdown_pct:.1%}"
    if kind in {"long_straddle", "long_strangle"}:
        return format_long_vol_review(value, context=detail)
    if kind == "iron_butterfly":
        return format_iron_butterfly(value, context=detail)
    if kind == "calendar_diary_spread":
        return format_calendar_diary_spread(value, context=detail)
    if kind == "gamma_exposure_alert":
        hours = max(0.0, (context.phase2.as_of.replace(hour=15, minute=30)-now).total_seconds()/3600)
        return format_gamma_exposure_alert("PORTFOLIO", value, hours, as_of=now)
    if kind == "earnings_event_hedge":
        return format_earnings_event_hedge(value, context.event_window, context=detail)
    if kind == "portfolio_corruption_overlay":
        return format_portfolio_corruption_overlay(value, context.correlation, context=detail)
    raise ValueError(f"unsupported Phase 3 review kind: {kind}")


def _phase2_dedup_key(kind: str, underlying: str, plan: object, now: datetime) -> str:
    day = now.astimezone(IST).date().isoformat()
    expiry = plan.expiry.isoformat()
    strikes = [f"{leg.strike:g}" for leg in plan.legs if leg.opt_type != "FUT"]
    if kind == "delta_hedge_rebalance":
        return f"{underlying}:{day}:{now:%H:%M}"
    if kind == "covered_call_recommendation":
        return f"{underlying}:{day}:{strikes[0]}:{expiry}"
    if kind in {"bull_put_spread", "bear_call_spread"}:
        return f"{underlying}:{day}:{strikes[0]}:{strikes[1]}:{expiry}"
    if kind == "iron_condor":
        return f"{underlying}:{day}:{':'.join(strikes)}:{expiry}"
    raise ValueError(f"unsupported Phase 2 dedup kind: {kind}")


async def _send_vix_review(db_path: str, now: datetime) -> None:
    rows = await load_vix_observations(db_path, 252)
    if not rows:
        return
    latest = rows[-1]
    previous = rows[-2]["spot"] if len(rows) >= 2 else None
    reading = vix_regime_reading(
        latest["spot"], previous, history=[row["spot"] for row in rows[:-1]],
        observed_at=latest["observed_at"], now=now,
        max_age=timedelta(minutes=settings.PARTNER_HEDGE_VIX_MAX_AGE_MIN),
    )
    if not reading.data_fresh:
        return
    key = f"{now.date().isoformat()}:{reading.regime}"
    text = format_vix_hedge_alert(reading, as_of=latest["observed_at"])
    await _send_claimed_review(
        db_path, "vix_hedge_alert", key, text,
        detail={"source": latest["source"], "spot": latest["spot"]}, now=now,
    )


async def partner_hedge_tick(now: Optional[datetime] = None) -> None:
    """Periodic Phase-1 advisory job. Disabled and zero-cost by default."""
    now = _aware(now or datetime.now(IST), "now").astimezone(IST)
    if not settings.PARTNER_HEDGE_ENABLED or not partner_enabled():
        return
    minute = now.hour * 60 + now.minute
    if not (9 * 60 + 25 <= minute <= 15 * 60 + 15):
        return
    import main as _main
    if not await _main.is_trading_day(now.date(), settings.DB_PATH):
        return
    if not getattr(_main.kite, "access_token", None):
        return

    await init_hedge_advisory_db(settings.DB_PATH)
    await _send_vix_review(settings.DB_PATH, now)
    positions = await load_reconciled_open_partner_positions(settings.DB_PATH)
    grouped: dict[str, list[PartnerPosition]] = defaultdict(list)
    for position in positions:
        grouped[position.underlying].append(position)

    for underlying, group in grouped.items():
        try:
            book = get_instruments_for(underlying)
            if not book.ready(now.date()):
                continue
            expiry = next((
                value for value in book.option_expiries
                if settings.PARTNER_HEDGE_MIN_DTE
                <= (value - now.date()).days
                <= settings.PARTNER_HEDGE_MAX_DTE
            ), None)
            if expiry is None:
                continue
            snapshot = await take_chain_snapshot(
                _main.kite, book, now,
                strike_window=settings.FNO_ANALYTICS_STRIKE_WINDOW,
                option_expiry=expiry,
            )
            if snapshot is None:
                continue
            for kind, plan, context in build_hedge_reviews(group, snapshot, now=now):
                key = f"{underlying}:{snapshot.expiry.isoformat()}:{now.date().isoformat()}"
                text = _format_review(kind, plan, context)
                await _send_claimed_review(
                    settings.DB_PATH, kind, key, text,
                    detail={"underlying": underlying, "expiry": snapshot.expiry,
                            "contracts": [leg.tradingsymbol for leg in plan.legs]},
                    now=now,
                )
        except Exception as exc:
            logger.error(
                "partner_hedge_tick_failed underlying=%s err=%s",
                underlying, str(exc), exc_info=True,
            )


async def partner_hedge_phase2_tick(now: Optional[datetime] = None) -> None:
    """Phase 2 review cadence; enabled and confined to NSE market hours."""
    now = _aware(now or datetime.now(IST), "now").astimezone(IST)
    if (
        not settings.PARTNER_HEDGE_ENABLED
        or not settings.PARTNER_HEDGE_PHASE2_ENABLED
        or not partner_enabled()
    ):
        return
    minute = now.hour * 60 + now.minute
    if not (9 * 60 + 30 <= minute <= 15 * 60 + 25):
        return
    import main as _main
    if not await _main.is_trading_day(now.date(), settings.DB_PATH):
        return
    if not getattr(_main.kite, "access_token", None):
        return

    await init_hedge_advisory_db(settings.DB_PATH)
    positions = await load_reconciled_open_partner_positions(settings.DB_PATH)
    grouped: dict[str, list[PartnerPosition]] = defaultdict(list)
    for position in positions:
        grouped[position.underlying].append(position)

    for underlying, group in grouped.items():
        try:
            book = get_instruments_for(underlying)
            if not book.ready(now.date()):
                continue
            expiry = next((
                value for value in book.option_expiries
                if settings.PARTNER_HEDGE_PHASE2_MIN_DTE
                <= (value - now.date()).days
                <= settings.PARTNER_HEDGE_PHASE2_MAX_DTE
            ), None)
            if expiry is None:
                continue
            snapshot = await take_chain_snapshot(
                _main.kite, book, now,
                strike_window=settings.FNO_ANALYTICS_STRIKE_WINDOW,
                option_expiry=expiry,
            )
            if snapshot is None:
                continue
            context = await _phase2_market_context(settings.DB_PATH, snapshot, now)
            reviews = build_phase2_hedge_reviews(group, snapshot, context, now=now)
            for kind, plan, review_context in reviews:
                is_delta = kind == "delta_hedge_rebalance"
                if is_delta:
                    gap = timedelta(minutes=settings.PARTNER_HEDGE_PHASE2_DELTA_GAP_MIN)
                    cap = settings.PARTNER_HEDGE_PHASE2_DELTA_DAILY_CAP
                else:
                    gap = timedelta(minutes=settings.PARTNER_HEDGE_PHASE2_PREMIUM_GAP_MIN)
                    cap = settings.PARTNER_HEDGE_PHASE2_PREMIUM_DAILY_CAP
                key = _phase2_dedup_key(kind, underlying, plan, now)
                text = _format_phase2_review(kind, plan, review_context)
                await _send_claimed_review(
                    settings.DB_PATH, kind, key, text,
                    detail={
                        "underlying": underlying,
                        "expiry": snapshot.expiry,
                        "contracts": [leg.tradingsymbol for leg in plan.legs],
                        "mode": context.mode,
                        "iv_rank": context.iv_rank,
                    },
                    now=now, underlying=underlying, min_gap=gap, daily_cap=cap,
                )
        except Exception as exc:
            logger.error(
                "partner_hedge_phase2_tick_failed underlying=%s err=%s",
                underlying, str(exc), exc_info=True,
            )


async def partner_hedge_phase3_tick(now: Optional[datetime] = None) -> None:
    """Phase-3 Greeks/term/event review; enabled and market-hours only."""
    now = _aware(now or datetime.now(IST), "now").astimezone(IST)
    if (not settings.PARTNER_HEDGE_ENABLED or not settings.PARTNER_HEDGE_PHASE3_ENABLED
            or not partner_enabled() or not (9*60+20 <= now.hour*60+now.minute <= 15*60+20)):
        return
    import main as _main
    from event_calendar import load_event_map
    from macro_events import event_note_for
    if not await _main.is_trading_day(now.date(), settings.DB_PATH):
        return
    if not getattr(_main.kite, "access_token", None):
        return
    await init_hedge_advisory_db(settings.DB_PATH)
    positions = await load_reconciled_open_partner_positions(settings.DB_PATH)
    equity_tickers = sorted({
        position.tradingsymbol.strip().upper()
        for position in positions
        if position.instrument_type == "EQUITY" and position.tradingsymbol.strip()
    })
    stress = None
    if len(equity_tickers) >= 2:
        close_matrix = await load_aligned_ohlcv_closes(
            settings.DB_PATH, equity_tickers, as_of=now.date(),
            lookback_rows=settings.PARTNER_HEDGE_OVERLAY_LOOKBACK_ROWS,
        )
        if close_matrix is not None:
            stress = portfolio_market_stress(
                close_matrix,
                min_return_observations=(
                    settings.PARTNER_HEDGE_OVERLAY_LOOKBACK_ROWS - 1
                ),
                sma_lookback=(
                    settings.PARTNER_HEDGE_OVERLAY_LOOKBACK_ROWS - 1
                ),
                correlation_threshold=(
                    settings.PARTNER_HEDGE_OVERLAY_CORRELATION_MIN
                ),
                breadth_threshold=settings.PARTNER_HEDGE_OVERLAY_BREADTH_MAX,
                drawdown_threshold=settings.PARTNER_HEDGE_OVERLAY_DRAWDOWN_MIN,
            )
    grouped: dict[str, list[PartnerPosition]] = defaultdict(list)
    for position in positions:
        grouped[position.underlying].append(position)
    for underlying, group in grouped.items():
        try:
            book = get_instruments_for(underlying)
            if not book.ready(now.date()):
                continue
            expiries = [e for e in book.option_expiries if 0 <= (e-now.date()).days <= settings.PARTNER_HEDGE_PHASE2_MAX_DTE]
            if not expiries:
                continue
            front = await take_chain_snapshot(_main.kite, book, now,
                strike_window=settings.FNO_ANALYTICS_STRIKE_WINDOW, option_expiry=expiries[0])
            if front is None:
                continue
            p2 = await _phase2_market_context(settings.DB_PATH, front, now)
            back = None; back_iv = None
            if len(expiries) >= 2:
                back = await take_chain_snapshot(_main.kite, book, now,
                    strike_window=settings.FNO_ANALYTICS_STRIKE_WINDOW, option_expiry=expiries[1])
                if back is not None:
                    back_iv = fno_analytics.atm_iv(back, now)
                    curve = iv_term_structure(((front.expiry, p2.atm_iv), (back.expiry, back_iv)), today=now.date()) if p2.atm_iv and back_iv else None
                    if curve is None:
                        back = None; back_iv = None
            expiry_close = IST.localize(datetime(front.expiry.year, front.expiry.month,
                                                  front.expiry.day, 15, 30))
            hours = (expiry_close-now).total_seconds()/3600
            gamma = gamma_exposure_at_expiry(group, hours, now=now) if 0 < hours <= 24 else None
            events = load_event_map(settings.EVENT_CALENDAR_CSV_PATH)
            earnings = next((event_day for event_day, event_type in events.get(underlying, ())
                             if event_type in {"RESULTS", "EARNINGS"}
                             and now.date() <= event_day <= now.date()+timedelta(days=1)), None)
            macro_note = event_note_for(now.date())
            context = Phase3MarketContext(
                phase2=p2, event_window=classify_event_window(earnings, macro_note or None,
                    (front.expiry-now.date()).days, today=now.date()),
                correlation=(stress.average_pairwise_correlation if stress else None),
                gamma_exposure=gamma, back_atm_iv=back_iv,
                portfolio_stress=stress,
            )
            for kind, value, review_context in build_phase3_hedge_reviews(
                    group, front, context, now=now, back_snapshot=back):
                key = f"{underlying}:{now.date().isoformat()}:{kind}:{front.expiry.isoformat()}"
                text = _format_phase3_review(kind, value, review_context, now)
                contracts = [leg.tradingsymbol for leg in getattr(value, "legs", ())]
                await _send_claimed_review(settings.DB_PATH, kind, key, text,
                    detail={"underlying": underlying, "contracts": contracts,
                            "event_window": context.event_window,
                            "portfolio_breadth": (
                                context.portfolio_stress.breadth_pct_above_sma
                                if context.portfolio_stress else None
                            ),
                            "portfolio_drawdown": (
                                context.portfolio_stress.drawdown_pct
                                if context.portfolio_stress else None
                            )}, now=now,
                    underlying=underlying,
                    min_gap=timedelta(minutes=settings.PARTNER_HEDGE_PHASE3_GAP_MIN),
                    daily_cap=settings.PARTNER_HEDGE_PHASE3_DAILY_CAP)
        except Exception as exc:
            logger.error("partner_hedge_phase3_tick_failed underlying=%s err=%s",
                         underlying, str(exc), exc_info=True)


__all__ = [
    "init_hedge_advisory_db", "record_vix_observation",
    "load_vix_observations", "Phase2MarketContext", "build_hedge_reviews",
    "build_phase2_hedge_reviews", "partner_hedge_tick",
    "partner_hedge_phase2_tick", "Phase3MarketContext",
    "build_phase3_hedge_reviews", "partner_hedge_phase3_tick",
]
