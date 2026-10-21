"""[O21-PC 2026-10-21] Partner coach and standard-capital views (read-mostly).

GET  /partner/coach                      the coach view (partner_coach.py)
POST /partner/coach/reports              owner-entered fill (the partner told them)
POST /partner/coach/reports/{id}/void    remove a wrong report
GET  /performance/standard-capital       every book on one capital (standard_capital.py)
POST /partner/broker/session             [O21-PK] the partner's Kite login (gateway callback)
GET  /partner/broker/status              whether a partner login is held (never the token)
POST /partner/broker/sync                read the partner's order book now (owner button)

All routes need the internal secret. None places an order or changes a card.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import main as _main
from config import settings

router = APIRouter()


class PartnerReportPayload(BaseModel):
    action: str = Field(pattern="^(BUY|SELL|SKIP|buy|sell|skip)$")
    trade_at: datetime
    advisory_id: Optional[str] = Field(default=None, max_length=40)
    price: Optional[float] = None
    lots: Optional[int] = None
    underlying: Optional[str] = Field(default=None, max_length=20)
    strike: Optional[float] = None
    opt_type: Optional[str] = Field(default=None, pattern="^(CE|PE|ce|pe)$")
    note: Optional[str] = Field(default=None, max_length=200)


class VoidPayload(BaseModel):
    note: str = Field(default="voided from dashboard", max_length=200)


class BrokerSessionPayload(BaseModel):
    request_token: str = Field(min_length=8, max_length=64, pattern="^[A-Za-z0-9]+$")


# BrokerError code -> HTTP status. Kite's own error types (TokenException,
# InputException, ...) are a failed login, so 502 unless listed.
_BROKER_STATUS = {"not_configured": 503, "bad_request_token": 400, "wrong_account": 403,
                  "not_connected": 409, "TokenException": 401}


def _broker_http_error(exc) -> HTTPException:
    return HTTPException(status_code=_BROKER_STATUS.get(exc.code, 502), detail={"code": exc.code})


@router.get("/partner/coach")
async def get_partner_coach(request: Request, days: int = 30):
    _main._check_internal_secret(request, "get_partner_coach")
    from partner_coach import load_partner_coach
    return await load_partner_coach(settings.DB_PATH, days=days)


@router.post("/partner/coach/reports")
async def post_partner_coach_report(request: Request, payload: PartnerReportPayload):
    _main._check_internal_secret(request, "post_partner_coach_report")
    from partner_fill_capture import record_dashboard_report
    try:
        report_id = await record_dashboard_report(
            settings.DB_PATH, advisory_id=payload.advisory_id, action=payload.action,
            price=payload.price, lots=payload.lots, trade_at=payload.trade_at, note=payload.note,
            underlying=payload.underlying, strike=payload.strike, opt_type=payload.opt_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "report_id": report_id, "automatic_execution": False}


@router.post("/partner/coach/reports/{report_id}/void")
async def post_partner_coach_report_void(report_id: int, request: Request, payload: VoidPayload):
    _main._check_internal_secret(request, "post_partner_coach_report_void")
    from partner_fill_capture import init_partner_fill_db, void_report
    await init_partner_fill_db(settings.DB_PATH)
    if not await void_report(settings.DB_PATH, report_id, payload.note):
        raise HTTPException(status_code=404, detail="no active report with that id")
    return {"voided": True, "report_id": report_id}


@router.post("/partner/broker/session")
async def post_partner_broker_session(request: Request, payload: BrokerSessionPayload):
    _main._check_internal_secret(request, "post_partner_broker_session")
    import partner_broker_sync as zerodha
    try:
        return await zerodha.on_login(payload.request_token)
    except zerodha.BrokerError as exc:
        raise _broker_http_error(exc) from exc


@router.get("/partner/broker/status")
async def get_partner_broker_status(request: Request):
    _main._check_internal_secret(request, "get_partner_broker_status")
    import partner_broker_sync as zerodha
    return zerodha.status()


@router.post("/partner/broker/sync")
async def post_partner_broker_sync(request: Request):
    _main._check_internal_secret(request, "post_partner_broker_sync")
    import partner_broker_sync as zerodha
    try:
        return await zerodha.sync_book()
    except zerodha.BrokerError as exc:
        raise _broker_http_error(exc) from exc


@router.get("/performance/standard-capital")
async def get_standard_capital(request: Request, capital: Optional[float] = None, since: Optional[str] = None):
    _main._check_internal_secret(request, "get_standard_capital")
    from standard_capital import load_standard_capital
    try:
        return await load_standard_capital(settings.DB_PATH, capital=capital, since=since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
