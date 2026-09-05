"""Source-neutral recurring refresh for approved partner hedge adapters.

The adapter is deliberately outside Sentinel: account mapping and credentials
belong to the partner-approved connector. Sentinel consumes one complete,
timestamped snapshot and reconciles only already-known position identities.
Fresh marks therefore never impersonate a fresh account reconciliation.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytz
import structlog

from config import settings
from hedge_advisory import _set_service_state, record_vix_observation
from hedge_analytics import (
    Greeks, apply_partner_snapshot_transaction,
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
    required = ("delta", "gamma", "theta", "vega")
    if any(name not in raw for name in required):
        raise ValueError("greeks must include delta, gamma, theta and vega")
    return Greeks(*(float(raw[name]) for name in required))


def _finite_positive(value: object, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return parsed


def _normalise_snapshot(snapshot: dict[str, Any], *, received_at: datetime) -> tuple[dict, list[dict], dict | None]:
    """Validate the adapter envelope before its atomic portfolio promotion."""
    source = str(snapshot.get("source") or "").strip()
    account_id = str(snapshot.get("account_id") or "").strip()
    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    if not source or not account_id or not snapshot_id:
        raise ValueError("snapshot source, account_id and snapshot_id are required")
    expected_source = str(settings.PARTNER_HEDGE_INPUT_EXPECTED_SOURCE or "").strip()
    expected_account = str(settings.PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID or "").strip()
    if expected_source and source != expected_source:
        raise ValueError("snapshot source is not the configured approved source")
    if expected_account and account_id != expected_account:
        raise ValueError("snapshot account_id is not the configured approved account")
    sequence = snapshot.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("snapshot sequence must be a non-negative integer")
    observed_at = _timestamp(snapshot.get("observed_at"), "observed_at")
    if observed_at > received_at + timedelta(seconds=settings.PARTNER_HEDGE_INPUT_MAX_FUTURE_SKEW_SEC):
        raise ValueError("snapshot observed_at exceeds permitted future skew")
    if received_at - observed_at > timedelta(minutes=settings.PARTNER_HEDGE_INPUT_MAX_AGE_MIN):
        raise ValueError("snapshot observed_at is stale")
    complete = snapshot.get("complete")
    if not isinstance(complete, bool):
        raise ValueError("complete must be boolean")
    raw_rows = snapshot.get("positions")
    if not isinstance(raw_rows, list):
        raise ValueError("positions must be a list")
    rows: list[dict] = []
    seen: set[int] = set()
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ValueError("position rows must be objects")
        position_id, quantity = row.get("position_id"), row.get("observed_quantity")
        if (not isinstance(position_id, int) or isinstance(position_id, bool)
                or not isinstance(quantity, int) or isinstance(quantity, bool)):
            raise ValueError("position_id and observed_quantity must be integers")
        if position_id in seen:
            raise ValueError("snapshot contains duplicate position_id")
        seen.add(position_id)
        current_price = row.get("current_price")
        price_as_of = row.get("price_as_of")
        if current_price is not None:
            _finite_positive(current_price, "current_price")
            if price_as_of is None:
                raise ValueError("price_as_of is required with current_price")
        parsed_price_as_of = (_timestamp(price_as_of, "price_as_of")
                               if price_as_of is not None else None)
        deliverable_quantity = row.get("deliverable_quantity")
        if deliverable_quantity is not None and (
            not isinstance(deliverable_quantity, int) or isinstance(deliverable_quantity, bool)
        ):
            raise ValueError("deliverable_quantity must be an integer")
        rows.append({
            "position_id": position_id, "observed_quantity": quantity,
            "quantity_basis": row.get("quantity_basis"),
            "current_price": current_price, "underlying_price": row.get("underlying_price"),
            "price_as_of": parsed_price_as_of, "greeks": _greeks(row.get("greeks")),
            "notes": row.get("notes"), "deliverable_quantity": deliverable_quantity,
            "deliverable_as_of": (_timestamp(row.get("deliverable_as_of"), "deliverable_as_of")
                                  if row.get("deliverable_as_of") is not None else None),
            "deliverable_source": row.get("deliverable_source"),
        })
    vix_raw = snapshot.get("vix")
    vix: dict | None = None
    if vix_raw is not None:
        if not isinstance(vix_raw, dict):
            raise ValueError("vix must be an object")
        vix = {"spot": _finite_positive(vix_raw.get("spot"), "vix.spot"),
               "observed_at": _timestamp(vix_raw.get("observed_at"), "vix.observed_at"),
               "source": str(vix_raw.get("source") or source).strip()}
        if not vix["source"]:
            raise ValueError("vix.source is required")
    envelope = {"source": source, "account_id": account_id,
                "snapshot_id": snapshot_id, "sequence": sequence,
                "observed_at": observed_at, "complete": complete}
    return envelope, rows, vix


async def apply_partner_input_snapshot(
    db_path: str, snapshot: dict[str, Any], *, received_at: datetime | None = None,
) -> dict:
    """Apply one complete adapter snapshot with explicit source ownership.

    The `complete` assertion is material: only a complete snapshot may close
    an absent position, and only rows owned by the named source are affected.
    """
    received_at = _timestamp((received_at or datetime.now(IST)).isoformat(), "received_at")
    envelope, rows, vix = _normalise_snapshot(snapshot, received_at=received_at)
    payload_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                             default=str).encode("utf-8")).hexdigest()
    result = await apply_partner_snapshot_transaction(
        db_path, **envelope, received_at=received_at, payload_hash=payload_hash, rows=rows,
    )
    outcome = {
        "source": envelope["source"], "account_id": envelope["account_id"],
        "snapshot_id": envelope["snapshot_id"], "sequence": envelope["sequence"],
        "observed_at": envelope["observed_at"].isoformat(), "complete": envelope["complete"],
        "reconciled": result["reconciled"], "closed": result["closed"],
        "accepted": result["accepted"], "idempotent": result["idempotent"],
        "vix_recorded": False,
    }
    if result["accepted"] and vix is not None:
        # VIX is a separately consumable market-data stream. It is fully
        # validated before portfolio promotion, but its later write is reported
        # independently instead of misreporting a committed portfolio as failed.
        try:
            await record_vix_observation(db_path, **vix)
            outcome["vix_recorded"] = True
        except Exception as exc:
            outcome["vix_error"] = type(exc).__name__
    await _set_service_state(db_path, "last_input_refresh", {
        **outcome, "state": "COMPLETE_SNAPSHOT" if envelope["complete"] else "PARTIAL_SNAPSHOT",
    }, now=received_at)
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
    if not settings.PARTNER_HEDGE_INPUT_REFRESH_ENABLED:
        state = {"state": "INPUT_ADAPTER_DISABLED"}
        await _set_service_state(db_path, "partner_input_adapter", state, now=now)
        return state
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers={"Authorization": f"Bearer {settings.PARTNER_HEDGE_INPUT_ADAPTER_TOKEN}"},
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
