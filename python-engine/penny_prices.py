"""Exact Penny price quantization and locally cached instrument tick metadata.

No broker calls. New live entries require dated metadata; exits may retain the
previous conservative tick when metadata is missing so recovery stays usable.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from functools import lru_cache
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def decimal_price(value: float) -> Decimal:
    price = Decimal(str(value))
    if not price.is_finite() or price <= 0:
        raise ValueError("price/tick must be positive and finite")
    return price


def quantize_price(price: float, direction: int, tick_size: float) -> float:
    value, tick = decimal_price(price), decimal_price(tick_size)
    rounding = ROUND_CEILING if direction >= 0 else ROUND_FLOOR
    return float((value / tick).to_integral_value(rounding=rounding) * tick)


@lru_cache(maxsize=4)
def _tick_rows(path: str, modified_ns: int) -> dict:
    del modified_ns  # cache identity invalidates when the universe is refreshed
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("tickers"), list):
        raise ValueError("invalid instrument metadata")
    return {str(row.get("symbol", "")).upper(): row for row in payload["tickers"]
            if isinstance(row, dict)}


def instrument_tick_size(ticker: str, *, require_today: bool = False) -> float | None:
    """Read the existing Penny universe, never download instruments per order."""
    from config import settings
    try:
        path = Path(settings.PENNY_UNIVERSE_JSON_PATH)
        row = _tick_rows(str(path.resolve()), path.stat().st_mtime_ns).get(ticker.upper(), {})
        tick = float(decimal_price(row["tick_size"]))
        if require_today:
            today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
            if row.get("tick_size_as_of") != today:
                return None
        return tick
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        return None
