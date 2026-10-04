"""PEN_CONTEXT research gate (N2), retained for its archived receipts.

Not wired into live scanners. The other N2/N3 subset-only helpers and the
independent-trial EDGE proxy were removed after T1/T2 replaced them with
complete trader candidates (``adaptive_penny_policy``, ``daily_portfolio``
replays). The gate consumes supplied, already-visible evidence and returns a
named reason instead of inventing unavailable market context.
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any, Iterable, Mapping


def _number(row: Mapping[str, Any], key: str) -> float | None:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def penny_context_gate(
    baseline_decision: Mapping[str, Any], completed_bars: Iterable[Mapping[str, Any]],
    prior_cumulative_volumes: Iterable[float], *, min_relative_volume: float = 1.0,
) -> dict[str, Any]:
    """Test a causal Penny MIS context hypothesis without replacing baseline.

    ``prior_cumulative_volumes`` must be each prior valid session's cumulative
    volume at the **same completed-minute boundary**.  A daily median is not a
    substitute.  The gate accepts either a first fresh reclaim above the prior
    completed high or a bounded retest that closes back above that anchor.
    """
    if not baseline_decision.get("accept"):
        return {"accepted": False, "reason": "baseline_rejected"}
    rows = list(completed_bars)
    if len(rows) < 3:
        return {"accepted": False, "reason": "insufficient_completed_bars"}
    parsed = []
    for row in rows:
        values = {key: _number(row, key) for key in ("open", "high", "low", "close", "volume")}
        if any(value is None or (key != "volume" and value <= 0) or (key == "volume" and value < 0)
               for key, value in values.items()):
            return {"accepted": False, "reason": "invalid_completed_bar"}
        parsed.append(values)
    history = [float(value) for value in prior_cumulative_volumes
               if isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0]
    if len(history) < 5:
        return {"accepted": False, "reason": "missing_same_minute_volume_profile"}
    baseline = float(median(history))
    cumulative = sum(row["volume"] for row in parsed)
    relative_volume = cumulative / baseline
    if relative_volume < min_relative_volume:
        return {"accepted": False, "reason": "relative_volume_below_profile", "relative_volume": round(relative_volume, 6)}
    # Freeze structure before both confirmation candles. Including the prior
    # candle's high makes prior close > anchor impossible for a valid candle.
    anchor = max(row["high"] for row in parsed[:-2])
    previous, current = parsed[-2], parsed[-1]
    fresh = previous["close"] <= anchor and current["close"] > anchor
    # A retest is bounded: the completed bar touches the prior structure but
    # finishes above it.  It is not a catch-all for any red bar after a break.
    retest = (previous["close"] > anchor and current["low"] <= anchor
              and current["close"] > anchor)
    if not (fresh or retest):
        return {"accepted": False, "reason": "no_fresh_breakout_or_bounded_retest",
                "relative_volume": round(relative_volume, 6), "anchor": round(anchor, 6)}
    return {"accepted": True, "reason": "fresh_breakout" if fresh else "bounded_retest",
            "anchor": round(anchor, 6), "relative_volume": round(relative_volume, 6),
            "profile_sessions": len(history)}
