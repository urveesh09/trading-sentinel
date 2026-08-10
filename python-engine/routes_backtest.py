"""Authenticated, research-only Backtest Lab HTTP surface."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backtest_lab import get_run, list_runs, list_strategies, submit_run
from config import settings
from engine_auth import _check_internal_secret


router = APIRouter(prefix="/backtests", tags=["backtests"])


class SubmitBacktest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=80)
    start_date: str
    end_date: str
    config: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)


@router.get("/strategies")
async def strategies(request: Request):
    _check_internal_secret(request, "backtest_strategies")
    return {"research_only": True, "can_place_orders": False,
            "strategies": await list_strategies(settings.DB_PATH)}


@router.post("/runs", status_code=202)
async def create_run(payload: SubmitBacktest, request: Request):
    _check_internal_secret(request, "backtest_submit")
    try:
        item = await submit_run(
            settings.DB_PATH, payload.strategy_id, payload.start_date, payload.end_date,
            payload.config, payload.assumptions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"research_only": True, "can_place_orders": False, **item}


@router.get("/runs")
async def runs(request: Request, limit: int = Query(50, ge=1, le=200),
               strategy_id: str | None = None, status: str | None = None):
    _check_internal_secret(request, "backtest_runs")
    try:
        items = await list_runs(settings.DB_PATH, limit, strategy_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"research_only": True, "runs": items}


@router.get("/runs/{run_id}")
async def run_detail(run_id: str, request: Request):
    _check_internal_secret(request, "backtest_run_detail")
    item = await get_run(settings.DB_PATH, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return {"research_only": True, "can_place_orders": False, "run": item}
