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
    init_hedge_advisory_db, load_hedge_service_state, load_vix_observations,
    load_hedge_delivery_backlog, load_partner_hedge_cards, record_vix_observation,
    resolve_hedge_delivery_backlog,
)
from hedge_analytics import (
    Greeks, PartnerPosition, close_partner_position, create_partner_position,
    load_partner_positions, load_reconciled_open_partner_positions,
    reconcile_partner_position,
)
from hedge_readiness import assess_hedge_readiness, record_gate_evidence
from partner_manual_advisory import (
    ManualDecision, PartnerAdvisoryProfile, load_advisory_cards, load_advisory_diagnostics,
    StrategyEvidence, load_partner_profile, record_manual_feedback,
    record_research_artifact, record_strategy_qualification, save_partner_profile,
)

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


class HedgeDeliveryResolutionPayload(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    resolved_by: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ref: str = Field(min_length=1, max_length=300)


class PartnerAdvisoryProfilePayload(BaseModel):
    version: int = Field(ge=1)
    enabled_scopes: list[str] = Field(default=["MARKET_SETUP"])
    instruments: list[str] = Field(default=["NIFTY", "SENSEX"])
    holding_period: Optional[str] = Field(default=None, max_length=80)
    timezone: str = Field(default="Asia/Kolkata", max_length=80)
    delivery_start_minute: int = Field(default=560, ge=0, le=1439)
    delivery_end_minute: int = Field(default=915, ge=0, le=1439)
    permitted_structures: list[str] = Field(default=["DIRECTIONAL_DEBIT_SPREAD"])
    preference: str = Field(default="ACTIONABLE", max_length=40)
    capital_limit_rs: Optional[float] = Field(default=None, gt=0)
    risk_limit_rs: Optional[float] = Field(default=None, gt=0)
    confirmed_holdings_revision: Optional[int] = Field(default=None, ge=0)
    conditional_exposure_assumption: Optional[str] = Field(default=None, min_length=8, max_length=500)
    conditional_coverage_units: Optional[int] = Field(default=None, ge=1)

    def value(self, profile_id: str) -> PartnerAdvisoryProfile:
        return PartnerAdvisoryProfile(
            profile_id=profile_id, version=self.version,
            enabled_scopes=tuple(item.strip().upper() for item in self.enabled_scopes),
            instruments=tuple(item.strip().upper() for item in self.instruments),
            holding_period=self.holding_period, timezone=self.timezone,
            delivery_start_minute=self.delivery_start_minute,
            delivery_end_minute=self.delivery_end_minute,
            permitted_structures=tuple(item.strip().upper() for item in self.permitted_structures),
            preference=self.preference.strip().upper(), capital_limit_rs=self.capital_limit_rs,
            risk_limit_rs=self.risk_limit_rs,
            confirmed_holdings_revision=self.confirmed_holdings_revision,
            conditional_exposure_assumption=self.conditional_exposure_assumption,
            conditional_coverage_units=self.conditional_coverage_units,
        )


class PartnerAdvisoryFeedbackPayload(BaseModel):
    decision: str = Field(min_length=1, max_length=30)
    reported_at: datetime
    note: Optional[str] = Field(default=None, max_length=1000)


class PartnerAdvisoryQualificationPayload(BaseModel):
    underlying: str = Field(min_length=3, max_length=20)
    structure_kind: str = Field(min_length=3, max_length=80)
    horizon: str = Field(min_length=3, max_length=80)
    policy_version: str = Field(min_length=3, max_length=80)
    dataset_ref: str = Field(min_length=3, max_length=300)
    reviewed_at: datetime
    status: str = Field(default="QUALIFIED_FOR_ADVISORY", max_length=40)


class PartnerAdvisoryResearchArtifactPayload(BaseModel):
    dataset_ref: str = Field(min_length=3, max_length=300)
    content_sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime
    description: str = Field(min_length=10, max_length=1000)


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
    service_state = await load_hedge_service_state(settings.DB_PATH)
    return {
        "enabled": settings.PARTNER_HEDGE_ENABLED,
        "phase2_enabled": settings.PARTNER_HEDGE_PHASE2_ENABLED,
        "phase3_enabled": settings.PARTNER_HEDGE_PHASE3_ENABLED,
        "phase2_shadow_enabled": settings.PARTNER_HEDGE_PHASE2_SHADOW_ENABLED,
        "phase3_shadow_enabled": settings.PARTNER_HEDGE_PHASE3_SHADOW_ENABLED,
        "open_positions": len(all_open),
        "reconciled_open_positions": len(reconciled),
        "latest_vix": jsonable_encoder(vix[-1]) if vix else None,
        "readiness": readiness,
        "service_state": service_state,
        "automatic_execution": False,
    }


@router.get("/partner/advisory/profile")
async def get_partner_advisory_profile(request: Request, profile_id: str = "default"):
    _main._check_internal_secret(request, "get_partner_advisory_profile")
    return jsonable_encoder(await load_partner_profile(settings.DB_PATH, profile_id))


@router.put("/partner/advisory/profile")
async def put_partner_advisory_profile(
    request: Request, payload: PartnerAdvisoryProfilePayload, profile_id: str = "default",
):
    _main._check_internal_secret(request, "put_partner_advisory_profile")
    try:
        profile = await save_partner_profile(settings.DB_PATH, payload.value(profile_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"profile": jsonable_encoder(profile), "delivery_authority": False, "automatic_execution": False}


@router.post("/partner/advisory/qualifications")
async def put_partner_advisory_qualification(
    request: Request, payload: PartnerAdvisoryQualificationPayload,
):
    """Record a reviewable strategy decision; this is the only promotion path."""
    _main._check_internal_secret(request, "put_partner_advisory_qualification")
    try:
        await record_strategy_qualification(
            settings.DB_PATH,
            underlying=payload.underlying.strip().upper(),
            structure_kind=payload.structure_kind.strip().upper(),
            horizon=payload.horizon.strip(),
            policy_version=payload.policy_version.strip(),
            dataset_ref=payload.dataset_ref.strip(),
            reviewed_at=payload.reviewed_at,
            status=StrategyEvidence(payload.status.strip().upper()),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "automatic_execution": False, "delivery_authority": False}


@router.post("/partner/advisory/research-artifacts")
async def post_partner_advisory_research_artifact(request: Request, payload: PartnerAdvisoryResearchArtifactPayload):
    _main._check_internal_secret(request, "post_partner_advisory_research_artifact")
    try:
        await record_research_artifact(settings.DB_PATH, dataset_ref=payload.dataset_ref,
                                       content_sha256=payload.content_sha256, created_at=payload.created_at,
                                       description=payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "automatic_execution": False}


@router.get("/partner/advisory/effective-settings")
async def get_partner_advisory_effective_settings(request: Request, profile_id: str = "default"):
    """Expose effective non-secret gates so operators can diagnose silence."""
    _main._check_internal_secret(request, "get_partner_advisory_effective_settings")
    profile = await load_partner_profile(settings.DB_PATH, profile_id)
    return {
        "profile": jsonable_encoder(profile),
        "profile_state": "SAVED_INTRADAY" if profile.holding_period == "INTRADAY" else (
            "IMPLICIT_DEFAULT_PROFILE" if profile.holding_period is None else "HORIZON_MISMATCH"
        ),
        "policy_version": "partner-manual-intraday-v1",
        "manual_advisory_enabled": bool(settings.PARTNER_MANUAL_ADVISORY_ENABLED),
        "shadow_enabled": bool(settings.PARTNER_MANUAL_ADVISORY_SHADOW_ENABLED),
        "delivery_enabled": bool(settings.PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED),
        "daily_delivery_cap": settings.PARTNER_MANUAL_ADVISORY_DAILY_CAP,
        "daily_update_cap": settings.PARTNER_MANUAL_ADVISORY_UPDATE_DAILY_CAP,
        "quote_ttl_seconds": settings.PARTNER_MANUAL_ADVISORY_QUOTE_TTL_SEC,
        "max_quote_age_seconds": settings.PARTNER_MANUAL_ADVISORY_MAX_QUOTE_AGE_SEC,
        "entry_window_ist": [settings.PARTNER_MANUAL_ADVISORY_ENTRY_START_MINUTE, settings.PARTNER_MANUAL_ADVISORY_ENTRY_END_MINUTE],
        "exit_reminder_minute_ist": settings.PARTNER_MANUAL_ADVISORY_EXIT_REMINDER_MINUTE,
        "management_end_minute_ist": settings.PARTNER_MANUAL_ADVISORY_MANAGEMENT_END_MINUTE,
        "manual_order_execution": False,
        "delivery_requires": ["fresh_quotes", "profile", "strategy_qualification", "delivery_ledger_authorization"],
    }


@router.get("/partner/advisory/cards")
async def get_partner_advisory_cards(request: Request, limit: int = 20):
    _main._check_internal_secret(request, "get_partner_advisory_cards")
    return await load_advisory_cards(settings.DB_PATH, limit=limit)


@router.get("/partner/advisory/diagnostics")
async def get_partner_advisory_diagnostics(request: Request):
    _main._check_internal_secret(request, "get_partner_advisory_diagnostics")
    return await load_advisory_diagnostics(settings.DB_PATH)


@router.post("/partner/advisory/cards/{advisory_id}/feedback")
async def post_partner_advisory_feedback(
    advisory_id: str, request: Request, payload: PartnerAdvisoryFeedbackPayload,
):
    _main._check_internal_secret(request, "post_partner_advisory_feedback")
    try:
        decision = ManualDecision(payload.decision.strip().upper())
        await record_manual_feedback(
            settings.DB_PATH, advisory_id, decision, reported_at=payload.reported_at, note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "inferred_fill": False, "automatic_execution": False}


@router.get("/partner/hedge/delivery-backlog")
async def get_partner_hedge_delivery_backlog(request: Request):
    """Read manual delivery/migration holds; it does not release anything."""
    _main._check_internal_secret(request, "get_partner_hedge_delivery_backlog")
    return await load_hedge_delivery_backlog(settings.DB_PATH)


@router.get("/partner/hedge/cards")
async def get_partner_hedge_cards(request: Request, limit: int = 20):
    _main._check_internal_secret(request, "get_partner_hedge_cards")
    try:
        return await load_partner_hedge_cards(settings.DB_PATH, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/partner/hedge/delivery-backlog/{kind}/{dedup_key}/resolve")
async def resolve_partner_hedge_delivery_backlog(
    kind: str, dedup_key: str, request: Request, payload: HedgeDeliveryResolutionPayload,
):
    _main._check_internal_secret(request, "resolve_partner_hedge_delivery_backlog")
    try:
        return await resolve_hedge_delivery_backlog(
            settings.DB_PATH, kind=kind, dedup_key=dedup_key,
            action=payload.action, resolved_by=payload.resolved_by,
            reason=payload.reason, evidence_ref=payload.evidence_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
