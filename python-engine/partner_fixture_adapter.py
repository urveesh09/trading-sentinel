"""Deterministic Dev-only partner-account fixture adapter.

It deliberately uses the real position and accepted-snapshot interfaces while
never contacting a broker. External ids map to broker_order_id solely as a
stable fixture identity, not as evidence of an executed broker order.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from hedge_analytics import PartnerPosition, load_partner_positions, create_partner_position
from partner_input_refresh import apply_partner_input_snapshot


async def apply_fixture_account(db_path: str, fixture: dict[str, Any], *, received_at: datetime) -> dict:
    source, account_id = str(fixture["source"]), str(fixture["account_id"])
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
        prepared.append((external_id, raw, quantity, lot_size, values))
    existing = list(await load_partner_positions(db_path, include_closed=True))
    snapshot_rows = []
    for external_id, raw, quantity, lot_size, values in prepared:
        prefix = f"fixture:{source}:{account_id}:{external_id}:"
        lifecycles = [p for p in existing if (p.broker_order_id or "").startswith(prefix)]
        position = next((p for p in lifecycles if p.status == "OPEN"), None)
        if position is None:
            lifecycle = len(lifecycles) + 1
            position = await create_partner_position(db_path, PartnerPosition(
                underlying=raw["underlying"], instrument_type=raw.get("instrument_type", "EQUITY"),
                tradingsymbol=raw["tradingsymbol"], signed_quantity=quantity,
                lot_size=lot_size, quantity_basis=raw.get("quantity_basis", "UNITS"),
                entry_price=values[0], current_price=values[1],
                underlying_price=values[2], beta=values[3],
                price_as_of=received_at, opened_at=received_at, updated_at=received_at,
                source=source, broker_order_id=f"{prefix}{lifecycle}", verification_status="PENDING_CONFIRMATION",
            ))
        snapshot_rows.append({"position_id": position.position_id, "observed_quantity": quantity,
                              "current_price": values[1], "underlying_price": values[2],
                              "price_as_of": received_at.isoformat()})
    return await apply_partner_input_snapshot(db_path, {**fixture, "positions": snapshot_rows}, received_at=received_at)
