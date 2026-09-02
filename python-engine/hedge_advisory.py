"""Hedge-first partner advisory orchestration.

Only reconciled positions and live, two-sided exchange quotes can produce a
review.  This module has no execution path.  Missing positions, stale prices,
unsupported expiries and incomplete volatility data all fail closed.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import aiosqlite
import pytz
import structlog

from config import settings
from fno_chain import ChainSnapshot, take_chain_snapshot
from fno_underlyings import get_instruments_for
from hedge_analytics import (
    PartnerPosition, aggregate_portfolio, init_hedge_db,
    load_reconciled_open_partner_positions, position_is_actionable,
    size_futures_hedge, vix_regime_reading,
)
from hedge_formatters import (
    format_collar_recommendation, format_futures_hedge_size,
    format_protective_put_alert, format_vix_hedge_alert,
)
from hedge_strategies import (
    collar_recommendation, futures_hedge_size, protective_put_alert,
)
from partner_bot import partner_enabled, send_partner

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

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
    PRIMARY KEY (kind, dedup_key)
);
"""


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


async def init_hedge_advisory_db(db_path: str) -> None:
    await init_hedge_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(_ADVISORY_SCHEMA)
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


async def _seen(db_path: str, kind: str, key: str) -> bool:
    await init_hedge_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM partner_hedge_messages "
            "WHERE kind=? AND dedup_key=? AND delivered=1",
            (kind, key),
        )
        return await cur.fetchone() is not None


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
        aligned = (
            position.instrument_type == "EQUITY"
            and position.signed_quantity > 0
            and position.signed_quantity % snapshot.lot_size == 0
            and position.current_price is not None
            and abs(position.current_price - snapshot.forward) / snapshot.forward <= .01
        )
        if aligned:
            plan = collar_recommendation(
                snapshot, position.signed_quantity, now,
                put_delta=settings.PARTNER_HEDGE_PUT_DELTA,
                call_delta=settings.PARTNER_HEDGE_CALL_DELTA, **common,
            )
            if plan is not None:
                reviews.append(("collar_recommendation", plan, exposure))
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
    if await _seen(db_path, "vix_hedge_alert", key):
        return
    text = format_vix_hedge_alert(reading, as_of=latest["observed_at"])
    delivered = await send_partner(text, kind="vix_hedge_alert")
    await _record(db_path, "vix_hedge_alert", key, delivered,
                  detail={"source": latest["source"], "spot": latest["spot"]}, now=now)


async def partner_hedge_tick(now: Optional[datetime] = None) -> None:
    """Periodic Phase-1 advisory job. Disabled and zero-cost by default."""
    now = _aware(now or datetime.now(IST), "now")
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
                if await _seen(settings.DB_PATH, kind, key):
                    continue
                text = _format_review(kind, plan, context)
                delivered = await send_partner(text, kind=kind)
                await _record(
                    settings.DB_PATH, kind, key, delivered,
                    detail={"underlying": underlying, "expiry": snapshot.expiry,
                            "contracts": [leg.tradingsymbol for leg in plan.legs]},
                    now=now,
                )
        except Exception as exc:
            logger.error(
                "partner_hedge_tick_failed underlying=%s err=%s",
                underlying, str(exc), exc_info=True,
            )


__all__ = [
    "init_hedge_advisory_db", "record_vix_observation",
    "load_vix_observations", "build_hedge_reviews", "partner_hedge_tick",
]
