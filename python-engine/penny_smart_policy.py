"""Causal Penny strength, setup timing and winner management; no I/O or orders.

Reuses the shipped adaptive setup machine. Evidence scores rank opportunities,
never represent calibrated probabilities. The paper controller and replay call
these same functions. No benchmark is invented when its observations are absent.
"""

from dataclasses import dataclass, replace
from datetime import datetime
import math

from adaptive_penny_policy import (
    DEFAULT_PARAMS,
    CompletedBar,
    ManageOutcome,
    SetupOutcome,
    ThesisPosition,
    advance_setup,
    detect_breakout,
)
from penny_prices import quantize_price

SMART_VERSION = "PEN_SMART_V1"
# Freeze these before scoring. Keep the current scanner clock/provider budget;
# one thesis entry per ticker/day, no compulsory +1R breakeven or partials.
SMART_PARAMS = replace(
    DEFAULT_PARAMS,
    policy_version=SMART_VERSION,
    entry_start_minute=630,
    max_entries_per_ticker_day=1,
    cooldown_minutes=30,
    fast_entry_score=0.85,
    fast_entry_max_chase_atr=0.35,
)


def visible_bars(bars, decision_at):
    """Fail closed on unordered, duplicate, future or cross-session observations."""
    if decision_at.tzinfo is None:
        raise ValueError("decision clock must be timezone-aware")
    previous = None
    ids = set()
    for bar in bars:
        if (
            bar.available_at > decision_at
            or bar.observed_at.date() != decision_at.date()
            or (previous is not None and bar.observed_at <= previous)
            or bar.observation_id in ids
        ):
            raise ValueError("non-causal or duplicate bars")
        previous = bar.observed_at
        ids.add(bar.observation_id)
    return bars


def strength_evidence(bars, *, decision_at, benchmark_bars=()):
    visible_bars(bars, decision_at)
    if len(bars) < 16 or bars[0].observed_at.hour * 60 + bars[0].observed_at.minute != 555:
        return {
            "available": False,
            "reason": "opening_prefix_or_history_unavailable",
            "score": None,
            "benchmark_status": "UNAVAILABLE",
        }
    recent = bars[-11:]
    day_return = bars[-1].close / bars[0].open - 1
    rolling_return = recent[-1].close / recent[0].close - 1
    persistence = sum(b.close >= a.close for a, b in zip(recent, recent[1:])) / (len(recent) - 1)
    volume = sum(b.volume for b in bars)
    vwap = sum(b.close * b.volume for b in bars) / volume if volume > 0 else None
    excess = None
    status = "UNAVAILABLE"
    if benchmark_bars:
        visible_bars(benchmark_bars, decision_at)
        if (
            benchmark_bars[0].observed_at.hour * 60 + benchmark_bars[0].observed_at.minute == 555
            and 0
            <= (bars[-1].available_at - benchmark_bars[-1].available_at).total_seconds()
            <= 120
        ):
            excess = day_return - (benchmark_bars[-1].close / benchmark_bars[0].open - 1)
            status = "OBSERVED"
    # Equal bounded components; absent benchmark is excluded, not filled with 0.
    components = {
        "absolute": max(0.0, min(1.0, day_return / 0.03)),
        "persistence": persistence,
        "progress": max(0.0, min(1.0, rolling_return / 0.01)),
        "vwap_support": float(vwap is not None and bars[-1].close >= vwap),
    }
    if excess is not None:
        components["relative"] = max(0.0, min(1.0, excess / 0.03))
    return {
        "available": True,
        "score": sum(components.values()) / len(components),
        "positive_momentum": day_return > 0 and rolling_return > 0,
        "day_return": day_return,
        "rolling_return": rolling_return,
        "persistence": persistence,
        "vwap": vwap,
        "excess_return": excess,
        "benchmark_status": status,
        "components": components,
    }


def smart_setup(
    ticker, bars, *, median_volume, decision_at, setup=None, benchmark_bars=(), params=SMART_PARAMS
):
    evidence = strength_evidence(bars, decision_at=decision_at, benchmark_bars=benchmark_bars)
    if not evidence["available"]:
        return SetupOutcome(setup, "NO_ACTION", evidence["reason"], evidence={"strength": evidence})
    # A long momentum thesis needs positive absolute progress; relative strength
    # alone could otherwise buy a stock simply falling less than the index.
    if not evidence["positive_momentum"]:
        if setup is not None:
            return SetupOutcome(
                None, "INVALIDATED", "absolute_momentum_lost", evidence={"strength": evidence}
            )
        return SetupOutcome(
            None, "NO_SETUP", "no_positive_absolute_momentum", evidence={"strength": evidence}
        )
    outcome = (
        advance_setup(setup, bars[-1], decision_at=decision_at, params=params)
        if setup
        else detect_breakout(
            ticker=ticker,
            bars=bars,
            median_vol_20d=median_volume,
            decision_at=decision_at,
            params=params,
        )
    )
    merged = {**outcome.evidence, "strength": evidence}
    if outcome.setup is None:
        return replace(outcome, evidence=merged)
    score = 0.5 * (outcome.setup.score or 0.0) + 0.5 * evidence["score"]
    return replace(
        outcome,
        setup=replace(outcome.setup, score=score),
        intent=replace(outcome.intent, score=score) if outcome.intent else None,
        evidence=merged,
    )


def affordable_intent(intent, *, executable_price, atr, params=SMART_PARAMS):
    """A setup is one-shot; a quote outside its frozen price budget expires it."""
    return math.isfinite(
        executable_price
    ) and intent.stop < executable_price <= intent.intended_price + min(
        params.max_chase_atr * atr, intent.intended_price * 0.005
    )


def manage_smart(position: ThesisPosition, bar: CompletedBar, *, decision_at, params=SMART_PARAMS):
    """Completed-close trail; no wick breakeven, no partial or risk widening."""
    visible_bars([bar], decision_at)
    if bar.observed_at < position.entry_at:
        return ManageOutcome(position)
    risk = position.risk_per_share
    if risk <= 0:
        raise ValueError("invalid admitted risk")
    highest = max(position.highest_high, bar.close)  # confirmed closes, not wicks
    below = position.closes_below_anchor + 1 if bar.close < position.anchor else 0
    updated = replace(position, highest_high=highest, closes_below_anchor=below)
    minute = decision_at.hour * 60 + decision_at.minute
    if minute >= 900:
        return ManageOutcome(updated, exit_reason="SMART_SESSION_DEADLINE")
    if below >= params.failed_breakout_closes and bar.close < position.entry_price:
        return ManageOutcome(updated, exit_reason="SMART_THESIS_FAILED")
    held = (decision_at - position.entry_at).total_seconds() / 60
    if (
        held >= params.stall_minutes
        and updated.mfe_r() < params.stall_max_mfe_r
        and bar.close < position.entry_price
    ):
        return ManageOutcome(updated, exit_reason="SMART_THESIS_STALLED")
    if minute >= params.eod_loss_cut_minute and bar.close < position.entry_price:
        return ManageOutcome(updated, exit_reason="SMART_EOD_LOSS_CUT")
    if (highest - position.entry_price) / risk >= params.trail_start_r:
        distance = max(params.trail_atr_mult * position.atr, params.trail_min_r * risk)
        stop = max(position.stop, quantize_price(highest - distance, -1, params.tick))
        if stop > position.stop:
            # This close's trail applies to subsequent prices. If the current
            # executable quote is below it, the controller exits at that quote.
            return ManageOutcome(replace(updated, stop=stop), new_stop=stop)
    return ManageOutcome(updated)
