"""Deterministic Dev-only partner-account fixture adapter.

It deliberately uses the real position and accepted-snapshot interfaces while
never contacting a broker. External ids map to broker_order_id solely as a
stable fixture identity, not as evidence of an executed broker order.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from hedge_analytics import PartnerPosition, load_partner_positions, create_partner_position
from partner_input_refresh import apply_partner_input_snapshot


async def apply_fixture_account(db_path: str, fixture: dict[str, Any], *, received_at: datetime) -> dict:
    source, account_id = fixture["source"], fixture["account_id"]
    rows = fixture.get("positions")
    if not isinstance(rows, list) or not fixture.get("complete"):
        raise ValueError("fixture requires a complete positions list")
    existing = {p.broker_order_id: p for p in await load_partner_positions(db_path, include_closed=True)}
    snapshot_rows = []
    for raw in rows:
        external_id = str(raw.get("external_position_id") or "").strip()
        if not external_id:
            raise ValueError("external_position_id is required")
        position = existing.get(external_id)
        if position is None or position.status == "CLOSED":
            position = await create_partner_position(db_path, PartnerPosition(
                underlying=raw["underlying"], instrument_type=raw.get("instrument_type", "EQUITY"),
                tradingsymbol=raw["tradingsymbol"], signed_quantity=int(raw["quantity"]),
                lot_size=int(raw.get("lot_size", 1)), quantity_basis=raw.get("quantity_basis", "UNITS"),
                entry_price=float(raw["entry_price"]), current_price=float(raw["current_price"]),
                underlying_price=float(raw.get("underlying_price", raw["current_price"])), beta=float(raw.get("beta", 1)),
                price_as_of=received_at, opened_at=received_at, updated_at=received_at,
                source=source, broker_order_id=external_id, verification_status="PENDING_CONFIRMATION",
            ))
        snapshot_rows.append({"position_id": position.position_id, "observed_quantity": int(raw["quantity"]),
                              "current_price": float(raw["current_price"]), "underlying_price": float(raw.get("underlying_price", raw["current_price"])),
                              "price_as_of": received_at.isoformat()})
    return await apply_partner_input_snapshot(db_path, {**fixture, "positions": snapshot_rows}, received_at=received_at)
