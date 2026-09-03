"""Authenticated intake and observability for partner hedge advisory data."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

import main as _main
from config import settings
from hedge_advisory import (
    init_hedge_advisory_db, load_vix_observations, record_vix_observation,
)
from hedge_analytics import (
    Greeks, PartnerPosition, close_partner_position, create_partner_position,
    load_partner_positions, load_reconciled_open_partner_positions,
    reconcile_partner_position,
)
from hedge_readiness import assess_hedge_readiness, record_gate_evidence

router = APIRouter()


class GreeksPayload(BaseModel):
    delta: float
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    def value(self) -> Greeks:
        return Greeks(self.delta, self.gamma, self.theta, self.vega)


class PartnerPositionPayload(BaseModel):
    underlying: str = Field(min_length=1, max_length=30)
    instrument_type: str
    tradingsymbol: str = Field(min_length=1, max_length=120)
    signed_quantity: int
    lot_size: int = Field(gt=0)
    quantity_basis: Optional[str] = None
    entry_price: float = Field(gt=0)
    opened_at: datetime
    source: str = Field(min_length=1, max_length=80)
    expiry: Optional[date] = None
    strike: Optional[float] = None
    current_price: Optional[float] = None
    underlying_price: Optional[float] = None
    beta: float = Field(default=1.0, gt=0)
    greeks: Optional[GreeksPayload] = None
    price_as_of: Optional[datetime] = None
    broker_order_id: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)
    deliverable_quantity: Optional[int] = Field(default=None, ge=0)
    deliverable_as_of: Optional[datetime] = None
    deliverable_source: Optional[str] = Field(default=None, max_length=80)


class ReconcilePayload(BaseModel):
    observed_quantity: int
    quantity_basis: Optional[str] = None
    reconciled_at: datetime
    source: str = Field(min_length=1, max_length=80)
    current_price: Optional[float] = None
    underlying_price: Optional[float] = None
    price_as_of: Optional[datetime] = None
    greeks: Optional[GreeksPayload] = None
    notes: Optional[str] = Field(default=None, max_length=1000)
    deliverable_quantity: Optional[int] = Field(default=None, ge=0)
    deliverable_as_of: Optional[datetime] = None
    deliverable_source: Optional[str] = Field(default=None, max_length=80)


class ClosePayload(BaseModel):
    closed_at: datetime
    source: str = Field(min_length=1, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=1000)


class VixPayload(BaseModel):
    spot: float = Field(gt=0)
    observed_at: datetime
    source: str = Field(min_length=1, max_length=80)


class HedgeGateEvidencePayload(BaseModel):
    """Operator evidence only; it cannot mutate a feature switch."""

    evidence_type: str = Field(min_length=1, max_length=80)
    phase: str = Field(min_length=1, max_length=20)
    observed_on: date
    source: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="", max_length=80)
    evidence_ref: str = Field(default="", max_length=160)
    note: Optional[str] = Field(default=None, max_length=1000)
    observed_at: Optional[datetime] = None


def _position_json(position: PartnerPosition) -> dict:
    return jsonable_encoder(asdict(position))


@router.post("/partner/hedge/positions")
async def add_partner_hedge_position(request: Request, payload: PartnerPositionPayload):
    _main._check_internal_secret(request, "add_partner_hedge_position")
    try:
        instrument_type = payload.instrument_type.strip().upper()
        quantity_basis = (
            payload.quantity_basis.strip().upper() if payload.quantity_basis else None
        )
        if instrument_type in {"FUT", "CE", "PE"} and quantity_basis != "UNITS":
            raise ValueError("F&O intake requires explicit quantity_basis=UNITS")
        position = PartnerPosition(
            underlying=payload.underlying,
            instrument_type=instrument_type,
            tradingsymbol=payload.tradingsymbol,
            signed_quantity=payload.signed_quantity,
            lot_size=payload.lot_size,
            quantity_basis=quantity_basis or "UNITS",
            entry_price=payload.entry_price,
            opened_at=payload.opened_at,
            source=payload.source,
            expiry=payload.expiry,
            strike=payload.strike,
            current_price=payload.current_price,
            underlying_price=payload.underlying_price,
            beta=payload.beta,
            greeks=payload.greeks.value() if payload.greeks else None,
            price_as_of=payload.price_as_of,
            broker_order_id=payload.broker_order_id,
            notes=payload.notes,
            deliverable_quantity=payload.deliverable_quantity,
            deliverable_as_of=payload.deliverable_as_of,
            deliverable_source=payload.deliverable_source,
            verification_status="PENDING_CONFIRMATION",
        )
        stored = await create_partner_position(settings.DB_PATH, position)
    except ValueError as exc:
        if "broker_order_id" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _position_json(stored)


@router.post("/partner/hedge/positions/{position_id}/reconcile")
async def reconcile_partner_hedge_position(
    position_id: int, request: Request, payload: ReconcilePayload,
):
    _main._check_internal_secret(request, "reconcile_partner_hedge_position")
    try:
        position = await reconcile_partner_position(
            settings.DB_PATH, position_id,
            observed_quantity=payload.observed_quantity,
            quantity_basis=payload.quantity_basis,
            reconciled_at=payload.reconciled_at,
            source=payload.source,
            current_price=payload.current_price,
            underlying_price=payload.underlying_price,
            price_as_of=payload.price_as_of,
            greeks=payload.greeks.value() if payload.greeks else None,
            notes=payload.notes,
            deliverable_quantity=payload.deliverable_quantity,
            deliverable_as_of=payload.deliverable_as_of,
            deliverable_source=payload.deliverable_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"position": _position_json(position) if position else None}


@router.post("/partner/hedge/positions/{position_id}/close")
async def close_partner_hedge_position(
    position_id: int, request: Request, payload: ClosePayload,
):
    _main._check_internal_secret(request, "close_partner_hedge_position")
    position = await close_partner_position(
        settings.DB_PATH, position_id, closed_at=payload.closed_at,
        source=payload.source, notes=payload.notes,
    )
    return {"position": _position_json(position) if position else None}


@router.get("/partner/hedge/positions")
async def get_partner_hedge_positions(request: Request, include_closed: bool = False):
    _main._check_internal_secret(request, "get_partner_hedge_positions")
    rows = await load_partner_positions(settings.DB_PATH, include_closed=include_closed)
    return {"positions": [_position_json(row) for row in rows]}


@router.post("/partner/hedge/vix")
async def add_partner_vix_observation(request: Request, payload: VixPayload):
    _main._check_internal_secret(request, "add_partner_vix_observation")
    try:
        await record_vix_observation(
            settings.DB_PATH, spot=payload.spot,
            observed_at=payload.observed_at, source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "recorded"}


@router.get("/partner/hedge/status")
async def get_partner_hedge_status(request: Request):
    _main._check_internal_secret(request, "get_partner_hedge_status")
    await init_hedge_advisory_db(settings.DB_PATH)
    all_open = await load_partner_positions(settings.DB_PATH)
    reconciled = await load_reconciled_open_partner_positions(settings.DB_PATH)
    vix = await load_vix_observations(settings.DB_PATH, 1)
    readiness = await assess_hedge_readiness(settings.DB_PATH)
    return {
        "enabled": settings.PARTNER_HEDGE_ENABLED,
        "phase2_enabled": settings.PARTNER_HEDGE_PHASE2_ENABLED,
        "phase3_enabled": settings.PARTNER_HEDGE_PHASE3_ENABLED,
        "open_positions": len(all_open),
        "reconciled_open_positions": len(reconciled),
        "latest_vix": jsonable_encoder(vix[-1]) if vix else None,
        "readiness": readiness,
        "automatic_execution": False,
    }


@router.get("/partner/hedge/readiness")
async def get_partner_hedge_readiness(request: Request):
    """Return fail-closed Phase 2/3 go-live evidence; never authorizes orders."""
    _main._check_internal_secret(request, "get_partner_hedge_readiness")
    return await assess_hedge_readiness(settings.DB_PATH)


@router.post("/partner/hedge/readiness/evidence")
async def add_partner_hedge_gate_evidence(
    request: Request, payload: HedgeGateEvidencePayload,
):
    """Record a dated operator attestation for the go-live checklist.

    This endpoint intentionally has no companion endpoint that enables a
    phase.  Configuration changes remain a reviewed deployment operation.
    """
    _main._check_internal_secret(request, "add_partner_hedge_gate_evidence")
    try:
        evidence = await record_gate_evidence(
            settings.DB_PATH,
            evidence_type=payload.evidence_type,
            phase=payload.phase,
            kind=payload.kind,
            evidence_ref=payload.evidence_ref,
            observed_on=payload.observed_on,
            observed_at=payload.observed_at,
            source=payload.source,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": evidence, "configuration_changed": False}


__all__ = ["router"]
