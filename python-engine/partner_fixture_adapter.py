"""Deterministic Dev-only partner-account fixture adapter.

It deliberately uses the real position and accepted-snapshot interfaces while
never contacting a broker. External ids map to broker_order_id solely as a
stable fixture identity, not as evidence of an executed broker order.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from typing import Any

from hedge_analytics import Greeks, PartnerPosition, load_partner_positions
from partner_input_refresh import apply_partner_input_snapshot


def _source_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _fixture_position_metadata(raw: dict[str, Any], *, observed_at: datetime) -> dict[str, Any]:
    """Parse fields that must be known before a fixture position is staged.

    Fixture rows use the same unit/Greek requirements as a real partner
    adapter.  In particular, an option cannot gain a fictional zero Greek just
    because it is only an offline Dev fixture.
    """
    instrument_type = str(raw.get("instrument_type", "EQUITY")).upper()
    expiry_raw = raw.get("expiry")
    try:
        expiry = date.fromisoformat(str(expiry_raw)) if expiry_raw is not None else None
    except ValueError as exc:
        raise ValueError("invalid fixture position") from exc
    metadata: dict[str, Any] = {
        "instrument_type": instrument_type,
        "expiry": expiry,
        "strike": raw.get("strike"),
        "greeks": None,
        "snapshot_greeks": None,
        "deliverable_quantity": raw.get("deliverable_quantity"),
        "deliverable_as_of": None,
        "deliverable_source": raw.get("deliverable_source"),
    }
    if raw.get("deliverable_as_of") is not None:
        metadata["deliverable_as_of"] = _source_timestamp(
            raw["deliverable_as_of"], "deliverable_as_of"
        )
    elif metadata["deliverable_quantity"] is not None:
        metadata["deliverable_as_of"] = observed_at
    if metadata["deliverable_quantity"] is not None and not metadata["deliverable_source"]:
        metadata["deliverable_source"] = "fixture"
    if instrument_type in {"CE", "PE"}:
        raw_greeks = raw.get("greeks")
        if not isinstance(raw_greeks, dict):
            raise ValueError("invalid fixture position")
        try:
            values = {name: float(raw_greeks[name]) for name in ("delta", "gamma", "theta", "vega")}
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError
            metadata["greeks"] = Greeks(**values)
            metadata["snapshot_greeks"] = values
            metadata["strike"] = float(raw["strike"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid fixture position") from exc
    return metadata


async def apply_fixture_account(db_path: str, fixture: dict[str, Any], *, received_at: datetime) -> dict:
    source, account_id = str(fixture["source"]), str(fixture["account_id"])
    observed_at = _source_timestamp(fixture.get("observed_at"), "observed_at")
    rows = fixture.get("positions")
    if not isinstance(rows, list) or not fixture.get("complete"):
        raise ValueError("fixture requires a complete positions list")
    prepared = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("fixture positions must be objects")
        external_id = str(raw.get("external_position_id") or "").strip()
        if not external_id or external_id in seen:
            raise ValueError("fixture external_position_id must be unique")
        seen.add(external_id)
        try:
            quantity, lot_size = raw["quantity"], raw.get("lot_size", 1)
            if not isinstance(quantity, int) or isinstance(quantity, bool) or not isinstance(lot_size, int) or isinstance(lot_size, bool) or lot_size <= 0:
                raise ValueError
            values = [float(raw["entry_price"]), float(raw["current_price"]), float(raw.get("underlying_price", raw["current_price"])), float(raw.get("beta", 1))]
            if not all(math.isfinite(value) and value > 0 for value in values):
                raise ValueError
            if not str(raw["underlying"]).strip() or not str(raw["tradingsymbol"]).strip():
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid fixture position") from exc
        prepared.append((external_id, raw, quantity, lot_size, values, _fixture_position_metadata(raw, observed_at=observed_at)))
    existing = list(await load_partner_positions(db_path, include_closed=True))
    snapshot_rows = []
    new_positions: dict[str, PartnerPosition] = {}
    for external_id, raw, quantity, lot_size, values, metadata in prepared:
        prefix = f"fixture:{source}:{account_id}:{external_id}:"
        lifecycles = [p for p in existing if (p.broker_order_id or "").startswith(prefix)]
        position = next((p for p in lifecycles if p.status == "OPEN"), None)
        if position is None:
            lifecycle = len(lifecycles) + 1
            try:
                new_positions[external_id] = PartnerPosition(
                    underlying=raw["underlying"], instrument_type=metadata["instrument_type"],
                    tradingsymbol=raw["tradingsymbol"], signed_quantity=quantity,
                    lot_size=lot_size, quantity_basis=raw.get("quantity_basis", "UNITS"),
                    entry_price=values[0], current_price=values[1],
                    underlying_price=values[2], beta=values[3], expiry=metadata["expiry"],
                    strike=metadata["strike"], greeks=metadata["greeks"],
                    price_as_of=observed_at, opened_at=observed_at, updated_at=observed_at,
                    source=source, broker_order_id=f"{prefix}{lifecycle}", verification_status="PENDING_CONFIRMATION",
                    deliverable_quantity=metadata["deliverable_quantity"],
                    deliverable_as_of=metadata["deliverable_as_of"],
                    deliverable_source=metadata["deliverable_source"],
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid fixture position") from exc
            snapshot_rows.append(_fixture_snapshot_row(
                {"position_key": external_id}, quantity=quantity, values=values,
                observed_at=observed_at, raw=raw, metadata=metadata,
            ))
            continue
        snapshot_rows.append(_fixture_snapshot_row(
            {"position_id": position.position_id}, quantity=quantity, values=values,
            observed_at=observed_at, raw=raw, metadata=metadata,
        ))
    return await apply_partner_input_snapshot(
        db_path, {**fixture, "positions": snapshot_rows}, received_at=received_at,
        new_positions=new_positions,
        source_payload_hash=hashlib.sha256(
            json.dumps(fixture, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
    )


def _fixture_snapshot_row(
    identity: dict[str, object], *, quantity: int, values: list[float], observed_at: datetime,
    raw: dict[str, Any], metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build a reconciliation row without substituting local receipt time."""
    return {
        **identity, "observed_quantity": quantity,
        "quantity_basis": raw.get("quantity_basis", "UNITS"),
        "current_price": values[1], "underlying_price": values[2],
        "price_as_of": observed_at.isoformat(), "greeks": metadata["snapshot_greeks"],
        "deliverable_quantity": metadata["deliverable_quantity"],
        "deliverable_as_of": (metadata["deliverable_as_of"].isoformat()
                              if metadata["deliverable_as_of"] is not None else None),
        "deliverable_source": metadata["deliverable_source"],
    }
