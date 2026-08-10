"""Authenticated, read-only endpoints for F&O paper-shadow evidence."""
from fastapi import APIRouter, Request

import main as _main
from config import settings
from fno_shadow import VARIANTS, fno_shadow_comparison


router = APIRouter()


@router.get("/experiments/fno-opening-range")
async def get_fno_opening_range_experiment(request: Request):
    _main._check_internal_secret(request, "get_fno_opening_range_experiment")
    enabled = bool(getattr(settings, "FNO_SHADOW_ENABLED", True))
    registry = {
        name: {
            "opening_range_minutes": variant.opening_range_minutes,
            "freshness": variant.freshness,
            "confirmation_bars": variant.confirmation_bars,
            "max_extension_atr": variant.max_extension_atr,
            "research_only": True,
            "can_place_orders": False,
        }
        for name, variant in VARIANTS.items()
    }
    response = {
        "enabled": enabled,
        "status": "empty" if enabled else "disabled",
        "config": {"enabled": enabled},
        "research_only": True,
        "can_place_orders": False,
        "registry": registry,
        "comparison": {"research_only": True, "can_place_orders": False, "variants": []},
        "limitations": [
            "Variants observe already-fetched futures bars and never request broker data.",
            "Post-cost values are one-lot target scenarios only when a chain was already resolved.",
            "No candidate, estimate, or comparison can size or place an order.",
        ],
    }
    if not enabled:
        return response
    try:
        response["comparison"] = await fno_shadow_comparison(settings.DB_PATH)
    except Exception as exc:
        _main.logger.warning("fno_shadow_comparison_failed", error=str(exc))
        response["status"] = "unavailable"
        response["warning"] = "F&O shadow evidence is temporarily unavailable"
        return response
    if response["comparison"].get("variants") and any(
        row.get("evaluations", 0) for row in response["comparison"]["variants"]
    ):
        response["status"] = "ready"
    return response
