"""Authenticated read-only surface for classic Penny paper experiments."""
from fastapi import APIRouter, Request
import importlib

from config import settings


router = APIRouter()


@router.get("/experiments/penny")
async def get_penny_experiment(request: Request):
    # Resolve at call time: tests and operational reload tooling may replace
    # the main module object while this router remains cached.
    _main = importlib.import_module("main")
    _main._check_internal_secret(request, "get_penny_experiment")
    enabled = bool(getattr(settings, "PENNY_SHADOW_ENABLED", True))
    registry = {
        name: {
            "time_start_min": variant.time_start_min,
            "volume_multiplier": variant.volume_multiplier,
        }
        for name, variant in _main.PENNY_SHADOW_VARIANTS.items()
    }
    response = {
        "enabled": enabled,
        "status": "disabled" if not enabled else "empty",
        "config": {"enabled": enabled},
        "registry": registry,
        "comparison": {"variants": []},
    }
    if not enabled:
        return response
    try:
        comparison = await _main.penny_shadow_comparison(settings.DB_PATH)
    except Exception as exc:
        _main.logger.warning("penny_shadow_comparison_failed", error=str(exc))
        response["status"] = "unavailable"
        response["warning"] = "Penny shadow evidence is temporarily unavailable"
        return response
    response["comparison"] = comparison
    if sum(row.get("evaluations", 0) for row in comparison.get("variants", [])):
        response["status"] = "ready"
    return response
