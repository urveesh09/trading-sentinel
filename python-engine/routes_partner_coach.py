"""[O21-PC 2026-10-21] Partner coach and standard-capital views (read-mostly).

GET  /partner/coach                      the coach view (partner_coach.py)
GET  /partner/review                     [O21-PL] the partner's day review + progress (partner_lessons.py)
GET  /partner/review/days                [O23-PH] every day with a review in the last 120 days
GET  /partner/review/pdf                 [O23-PD] one day's review as a PDF (partner_review_pdf.py)
POST /partner/coach/reports              owner-entered fill (the partner told them)
POST /partner/coach/reports/{id}/void    remove a wrong report
GET  /performance/standard-capital       every book on one capital (standard_capital.py)
POST /partner/broker/session             [O21-PK] the partner's Kite login (gateway callback)
GET  /partner/broker/status              whether a partner login is held (never the token)
POST /partner/broker/sync                read the partner's order book now (owner button)

All routes need the internal secret. None places an order or changes a card.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import main as _main
from config import settings

router = APIRouter()
logger = structlog.get_logger()
REVIEW_HISTORY_DAYS = 120     # the oldest review that opens, and how far the day list reaches
_DAY = r"^\d{4}-\d{2}-\d{2}$"


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


async def _review(day: Optional[str], days: int) -> dict:
    """One day's learnings (default: today, else the latest day with a card or
    trade) and progress over the window, as the page and the PDF read them."""
    from datetime import date
    from partner_coach import IST, load_partner_coach
    from partner_lessons import active_days, day_review, progress
    now = datetime.now(IST)
    today = now.date()
    try:
        asked = date.fromisoformat(day) if day else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="day must be a date") from exc
    if asked is not None and not (today - timedelta(days=REVIEW_HISTORY_DAYS - 1) <= asked <= today):
        raise HTTPException(status_code=422, detail="day must be within the last 120 days")
    window = max(14, min(int(days), REVIEW_HISTORY_DAYS))
    span = (today - asked).days + 1 if asked else 0
    view = await load_partner_coach(settings.DB_PATH, days=max(window, span), now=now)
    available = active_days(view)
    chosen = asked.isoformat() if asked else (today.isoformat() if today.isoformat() in available
                                              else (available[0] if available else today.isoformat()))
    # [O23-PH] Progress covers the last `window` days whichever day is open
    # (before, opening an old day widened it to reach that day).
    first = (today - timedelta(days=window - 1)).isoformat()
    recent = view if span <= window else {**view, "days": [r for r in view["days"] if r["day"] >= first]}
    from partner_broker_sync import review_sync
    from partner_watch import watch_status
    # [A22-P4] The login's background read (reading / enriching / done): the page refreshes until done.
    # [O23-PH] `newest`: the open day is today or the latest day with a review, so tomorrow's focus applies.
    # [O24-PW] `watch`: whether the trade watch is on now (the page says so after a morning login).
    return {"day": chosen, "today": today.isoformat(), "newest": chosen >= (available[0] if available else chosen),
            "days_available": available, "review": day_review(view, chosen, today.isoformat()),
            "progress": progress(recent, today.isoformat()), "zerodha": view["zerodha"], "window": view["window"],
            "as_of": view["as_of"], "sync": review_sync(now), "watch": await watch_status(now),
            "automatic_execution": False}


@router.get("/partner/review")
async def get_partner_review(request: Request, day: Optional[str] = Query(default=None, pattern=_DAY),
                             days: int = 30):
    """[O21-PL] The partner's own review: one day's learnings and progress."""
    _main._check_internal_secret(request, "get_partner_review")
    return await _review(day, days)


@router.get("/partner/review/days")
async def get_partner_review_days(request: Request):
    """[O23-PH] Every day with a card or a trade in the last 120 days, newest
    first: the page's day list (read once per page, not polled)."""
    _main._check_internal_secret(request, "get_partner_review_days")
    from partner_coach import IST, load_partner_coach
    from partner_lessons import active_days
    now = datetime.now(IST)
    view = await load_partner_coach(settings.DB_PATH, days=REVIEW_HISTORY_DAYS, now=now)
    return {"days": active_days(view), "today": now.date().isoformat(), "automatic_execution": False}


@router.get("/partner/review/pdf")
async def get_partner_review_pdf(request: Request, day: Optional[str] = Query(default=None, pattern=_DAY)):
    """[O23-PD] One day's review as a PDF, the same content as the page."""
    _main._check_internal_secret(request, "get_partner_review_pdf")
    try:
        from partner_review_pdf import render_review_pdf
    except ImportError as exc:      # an image built before reportlab was added
        raise HTTPException(status_code=503, detail={"code": "pdf_unavailable"}) from exc
    body = await _review(day, 30)
    document = {"day": body["day"], "today": body["today"], "review": body["review"], "as_of": body["as_of"],
                "focus": body["progress"]["focus"] if body["newest"] else None}
    try:
        pdf = await asyncio.to_thread(render_review_pdf, document)
    except Exception as exc:
        logger.error("partner_review_pdf_failed", day=body["day"], error=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail={"code": "pdf_failed"}) from exc
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="trading-review-{body["day"]}.pdf"',
        "Cache-Control": "no-store"})


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
