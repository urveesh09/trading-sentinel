"""Source-neutral recurring refresh for approved partner hedge adapters.

The adapter is deliberately outside Sentinel: account mapping and credentials
belong to the partner-approved connector. Sentinel consumes one complete,
timestamped snapshot and reconciles only already-known position identities.
Fresh marks therefore never impersonate a fresh account reconciliation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytz
import structlog

from config import settings
from hedge_advisory import _set_service_state, record_vix_observation
from hedge_analytics import (
    Greeks, close_partner_position, get_partner_position,
    load_partner_positions, reconcile_partner_position,
)

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(IST)


def _greeks(raw: object) -> Greeks | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("greeks must be an object")
    return Greeks(
        float(raw["delta"]), float(raw.get("gamma", 0)),
        float(raw.get("theta", 0)), float(raw.get("vega", 0)),
    )


async def apply_partner_input_snapshot(db_path: str, snapshot: dict[str, Any]) -> dict:
    """Apply one complete adapter snapshot with explicit source ownership.

    The `complete` assertion is material: only a complete snapshot may close
    an absent position, and only rows owned by the named source are affected.
    """
    source = str(snapshot.get("source") or "").strip()
    if not source:
        raise ValueError("snapshot source is required")
    observed_at = _timestamp(snapshot.get("observed_at"), "observed_at")
    complete = snapshot.get("complete")
    if not isinstance(complete, bool):
        raise ValueError("complete must be boolean")
    rows = snapshot.get("positions")
    if not isinstance(rows, list):
        raise ValueError("positions must be a list")
    seen: set[int] = set()
    reconciled = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("position rows must be objects")
        position_id = row.get("position_id")
        quantity = row.get("observed_quantity")
        if (not isinstance(position_id, int) or isinstance(position_id, bool)
                or not isinstance(quantity, int) or isinstance(quantity, bool)):
            raise ValueError("position_id and observed_quantity must be integers")
        if position_id in seen:
            raise ValueError("snapshot contains duplicate position_id")
        seen.add(position_id)
        existing = await get_partner_position(db_path, position_id)
        if existing is None:
            raise ValueError(f"unknown position_id {position_id}")
        if existing.source != source:
            raise ValueError("snapshot source does not own position_id")
        price_as_of = (_timestamp(row["price_as_of"], "price_as_of")
                       if row.get("price_as_of") is not None else None)
        result = await reconcile_partner_position(
            db_path, position_id, observed_quantity=quantity,
            quantity_basis=row.get("quantity_basis"), reconciled_at=observed_at,
            source=source, current_price=row.get("current_price"),
            underlying_price=row.get("underlying_price"), price_as_of=price_as_of,
            greeks=_greeks(row.get("greeks")), notes=row.get("notes"),
        )
        reconciled += 1
    closed = 0
    if complete:
        for position in await load_partner_positions(db_path):
            if position.source == source and position.position_id not in seen:
                await close_partner_position(
                    db_path, position.position_id, closed_at=observed_at,
                    source=source, notes="closed_by_complete_adapter_snapshot",
                )
                closed += 1
    vix = snapshot.get("vix")
    if vix is not None:
        if not isinstance(vix, dict):
            raise ValueError("vix must be an object")
        await record_vix_observation(
            db_path, spot=float(vix["spot"]),
            observed_at=_timestamp(vix.get("observed_at"), "vix.observed_at"),
            source=str(vix.get("source") or source),
        )
    outcome = {
        "source": source, "observed_at": observed_at.isoformat(),
        "complete": complete, "reconciled": reconciled, "closed": closed,
        "vix_recorded": vix is not None,
    }
    await _set_service_state(db_path, "last_input_refresh", {
        **outcome, "state": "COMPLETE_SNAPSHOT" if complete else "PARTIAL_SNAPSHOT",
    }, now=observed_at)
    return outcome


async def refresh_partner_input_once(db_path: str | None = None) -> dict:
    """Fetch an approved adapter snapshot, or expose an explicit blocker."""
    db_path = db_path or settings.DB_PATH
    url = str(settings.PARTNER_HEDGE_INPUT_ADAPTER_URL or "").strip()
    now = datetime.now(IST)
    if not url:
        state = {"state": "INPUT_ADAPTER_UNCONFIGURED"}
        await _set_service_state(db_path, "partner_input_adapter", state, now=now)
        return state
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET or ""},
                timeout=float(settings.PARTNER_HEDGE_INPUT_REFRESH_TIMEOUT_SEC),
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("adapter response must be an object")
        outcome = await apply_partner_input_snapshot(db_path, payload)
        await _set_service_state(db_path, "partner_input_adapter", {
            "state": "REFRESHED", **outcome,
        }, now=now)
        return outcome
    except Exception as exc:
        state = {"state": "INPUT_ADAPTER_FAILED", "error": type(exc).__name__}
        await _set_service_state(db_path, "partner_input_adapter", state, now=now)
        logger.warning("partner_input_refresh_failed err=%s", str(exc))
        return state
