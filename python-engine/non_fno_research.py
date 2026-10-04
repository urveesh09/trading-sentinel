"""Pure, broker-free N2/N3 candidate gates and executable lifecycle helpers.

These helpers are deliberately *not* wired into live scanners.  They make the
extra hypotheses falsifiable against the existing shipped evaluators without
changing a threshold, admission path, database table, account reservation, or
F&O dependency.  Every function consumes supplied, already-visible evidence
and returns a named reason instead of inventing unavailable market context.
"""
from __future__ import annotations

from dataclasses import replace
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
    anchor = max(row["high"] for row in parsed[:-1])
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


def penny_exit_thesis(
    *, entry: float, initial_stop: float, current_stop: float, current_price: float,
    structure_anchor: float, prior_reentry_consumed: bool,
) -> dict[str, Any]:
    """A non-widening Penny exit/re-entry diagnostic.

    It does not issue an exit.  A broken anchor invalidates the thesis; a later
    re-arm needs a fresh reclaim and may occur only once.  Stops never move
    lower, so the output is safe to compare with the baseline lifecycle.
    """
    values = (entry, initial_stop, current_stop, current_price, structure_anchor)
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in values):
        return {"action": "UNKNOWN", "reason": "invalid_price_evidence"}
    if current_stop < initial_stop:
        return {"action": "UNKNOWN", "reason": "stop_widening_forbidden"}
    if current_price <= current_stop:
        return {"action": "INVALIDATE", "reason": "protective_stop_reached"}
    if current_price < structure_anchor:
        return {"action": "INVALIDATE", "reason": "structure_anchor_lost"}
    if current_price > structure_anchor and not prior_reentry_consumed:
        return {"action": "HOLD_OR_ONE_REARM", "reason": "structure_intact_fresh_reclaim"}
    return {"action": "HOLD", "reason": "structure_intact_reentry_already_consumed" if prior_reentry_consumed else "structure_intact"}


def edge_next_open_lifecycle(position: Any, next_session_bars: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Execute an EDGE signal at the next observable session open, never close.

    The actual shipped ``simulate_position`` owns its stop/target/time ordering.
    A gap through the precomputed geometry is rejected rather than restating the
    discovery close as a fictitious fill.  Costs are reported separately because
    the engine simulator itself reports gross P&L.
    """
    from penny_edge_engine import simulate_position
    from penny_risk import calc_penny_costs

    bars = [dict(row) for row in next_session_bars]
    if not bars:
        return {"status": "UNRESOLVED", "reason": "no_next_session_evidence"}
    first = bars[0]
    entry = _number(first, "open")
    if entry is None or entry <= 0:
        return {"status": "UNRESOLVED", "reason": "invalid_next_open"}
    stop, target = float(position.stop_loss), float(position.target)
    if entry <= stop or entry >= target:
        return {"status": "NO_FILL", "reason": "next_open_invalidates_signal_geometry", "entry": round(entry, 6)}
    filled = replace(position, entry_price=entry, entry_date=str(first.get("date") or position.entry_date))
    simulated = simulate_position(filled, bars)
    status = "CLOSED" if simulated.get("exit_reason") not in {"eod_data_ended", "no_data"} else "OPEN_MARKED"
    exit_price = float(simulated["exit_price"])
    costs = calc_penny_costs(entry, exit_price, int(filled.shares), is_intraday=False)
    return {
        "status": status, "reason": simulated["exit_reason"], "signal_entry": round(float(position.entry_price), 6),
        "entry": round(entry, 6), "exit": round(exit_price, 6), "shares": int(filled.shares),
        "gross_pnl": round((exit_price - entry) * int(filled.shares), 6), "costs": costs,
        "net_pnl": round((exit_price - entry) * int(filled.shares) - costs, 6),
        "signal_subtype": filled.signal_subtype,
    }


def range_candidate_gate(
    bars: list[Mapping[str, Any]], *, next_open: float | None, shares: int,
    min_net_room_multiple: float = 1.25,
) -> dict[str, Any]:
    """Add executable net-room and thesis identity to shipped Range verdicts."""
    from engine import calc_zerodha_costs
    from range_reversion import EntrySignal, range_reversion_entry

    verdict = range_reversion_entry(bars)
    if verdict.signal is not EntrySignal.ENTER:
        return {"accepted": False, "reason": f"baseline_{verdict.signal.value.lower()}", "verdict": verdict.to_dict()}
    if next_open is None or not math.isfinite(float(next_open)) or float(next_open) <= 0:
        return {"accepted": False, "reason": "missing_next_open", "verdict": verdict.to_dict()}
    if shares < 1:
        return {"accepted": False, "reason": "zero_shares", "verdict": verdict.to_dict()}
    entry, stop, target = float(next_open), float(verdict.strict_stop), float(verdict.mean_target)
    if not stop < entry < target:
        return {"accepted": False, "reason": "next_open_invalidates_geometry", "verdict": verdict.to_dict()}
    costs = calc_zerodha_costs(entry, target, shares, is_intraday=False, for_gate=False)
    risk, gross_room = (entry - stop) * shares, (target - entry) * shares
    if gross_room - costs < risk * min_net_room_multiple:
        return {"accepted": False, "reason": "net_room_after_costs_insufficient", "verdict": verdict.to_dict(),
                "costs": costs, "net_room": round(gross_room - costs, 6), "risk": round(risk, 6)}
    identity = "range:" + ":".join(str(row.get("date", "")) for row in bars[-14:])
    return {"accepted": True, "reason": "range_intact_net_room", "thesis_id": identity,
            "entry": round(entry, 6), "stop": round(stop, 6), "target": round(target, 6),
            "costs": costs, "net_room": round(gross_room - costs, 6), "risk": round(risk, 6)}


def swing_candidate_gate(
    *, baseline_fired: bool, entry: float | None, stop: float | None, target: float | None,
    relative_strength: float | None, correlation_to_open: float | None,
    max_correlation: float = 0.80,
) -> dict[str, Any]:
    """Research-only Swing overlay: no stretch/chase or correlated duplication."""
    if not baseline_fired:
        return {"accepted": False, "reason": "baseline_rejected"}
    values = (entry, stop, target, relative_strength, correlation_to_open)
    if any(value is None or not math.isfinite(float(value)) for value in values):
        return {"accepted": False, "reason": "missing_relative_strength_or_correlation"}
    if not float(stop) < float(entry) < float(target):
        return {"accepted": False, "reason": "invalid_geometry"}
    if float(relative_strength) <= 0:
        return {"accepted": False, "reason": "relative_strength_not_positive"}
    if abs(float(correlation_to_open)) > max_correlation:
        return {"accepted": False, "reason": "correlated_exposure_cap"}
    return {"accepted": True, "reason": "baseline_plus_rs_and_correlation", "reward_r": round((float(target) - float(entry)) / (float(entry) - float(stop)), 6)}
