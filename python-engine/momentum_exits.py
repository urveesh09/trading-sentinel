"""
[TIER0-0.1 2026-07-14] Intraday exit management for MIS momentum positions.

WHY THIS FILE EXISTS
--------------------
Until today, a momentum position had no stop and no target -- not in the engine,
not at the broker:

  * Broker side: node-gateway/server/services/executor.js guarded GTT placement
    with `if (!isIntraday)`. Zerodha GTT is CNC/NRML-only, so MIS positions got
    no protective order at all, and nothing took its place.
  * Engine side: the only scheduled jobs that touched a momentum position were
    momentum_eod_warning (15:10) and auto_square_momentum (15:15). Nothing
    evaluated the stop or the target in between.

So the stop_loss and target_1 computed by evaluate_momentum_signal -- the numbers
that GATE the trade, SIZE the position (risk = shares * (entry - stop)), and are
shown to the operator on the EXEC button -- were enforced by nothing. Every
position was held blind until 15:15 and squared at whatever the market gave.

The live record was unambiguous: all 7 momentum trades exited via auto_square at
15:15. Not one hit its target. Not one hit its stop.

That is both an alpha leak (winners hand their gains back before the close) and a
risk hole (sizing assumes a stop that does not exist, so the real intraday
downside is unbounded).

THE SPLIT
---------
The STOP rests at the broker as an SL-M (placed by executor.js), so it survives a
scheduler freeze -- the 2026-07-07 incident was 6h32m of a dead loop, which is
exactly when a software-only stop is worthless.

This module owns everything the broker cannot do for us:
  * target       -- cancel the SL-M, then sell
  * breakeven    -- ratchet the SL-M trigger to cost-adjusted breakeven at +1R
  * trail        -- ratchet the SL-M trigger up behind the price
  * time stop    -- cut a trade that has gone nowhere

There is deliberately NO resting target order. Zerodha has no OCO for MIS, so a
resting stop AND a resting target could both fill and leave us short. The monitor
always cancels the SL-M before it sells.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from config import settings
from engine import calc_zerodha_costs

logger = structlog.get_logger()

# Actions returned by evaluate_momentum_exit()
ACTION_HOLD = "hold"
ACTION_EXIT = "exit"
ACTION_TRAIL = "trail"
# [SCALE-OUT 2026-08-04] Sell part of the position and de-risk the rest.
# Carries "scale_shares" (how many to sell) and "new_stop" (where the runner's
# stop goes) in the same decision.
ACTION_SCALE_OUT = "scale_out"


def momentum_exit_status(reason: str) -> str:
    """Map an ACTION_EXIT reason to the TERMINAL position status to persist.

    Momentum is a single-leg MIS strategy: an ACTION_EXIT squares off the
    whole position, so its status must be terminal. The old code hard-coded
    "CLOSED_T1" here, but get_open_positions() deliberately treats CLOSED_T1
    as still-open (the penny/swing runner keeps managing the remaining 50%
    after T1). A momentum trade has no runner, so a "CLOSED_T1" label left
    every fully-closed momentum position counted as open forever
    (t1_fired=0 yet status=CLOSED_T1). Return a status the open-position
    query excludes.

    Reasons come from evaluate_momentum_exit(): "target_hit",
    "time_stop_<n>min_at_<r>R" and "time_stop_fast_<n>min_at_<r>R". Broker-side
    stop fills are closed separately as STOPPED_OUT and never reach here.
    """
    if reason == "target_hit":
        return "CLOSED_T2"
    if reason.startswith("time_stop"):
        return "CLOSED_TIME"
    return "CLOSED_MANUAL"


def cost_adjusted_breakeven(entry_price: float, shares: int) -> float:
    """
    The price at which this position is actually flat -- entry plus the round-trip
    cost per share.

    Naive breakeven (== entry_price) is a lie: a position exited at entry has paid
    brokerage, STT, GST and exchange fees, so it is a LOSS. The live EDGE book made
    exactly this mistake -- every position force-closed at its entry price, and
    every one of those "flat" trades was a real loss of pure cost drag.

    for_gate=False on purpose: we want the REAL cost here, not the gate's
    optimistic zeroed one (see engine.calc_zerodha_costs).
    """
    if shares <= 0:
        return entry_price
    costs = calc_zerodha_costs(
        entry_price, entry_price, shares, is_intraday=True, for_gate=False
    )
    return entry_price + (costs / shares)


def _regime_time_mult(regime_at_entry: Optional[str]) -> float:
    """Scale the slow time-stop window by the regime the trade was entered in.

    [TIME-STOP-V2 2026-07-31] A trending market gives a momentum trade room to
    develop; chop does not. Rather than one window for every condition, the
    runway stretches in calm/normal conditions and shortens as volatility
    rises -- which is also when holding a losing intraday position costs most.
    Unknown/NULL regime falls back to the R1 multiplier (the historical
    behaviour of a single fixed window)."""
    name = str(regime_at_entry or "")
    if "REGIME_3" in name or "CRISIS" in name:
        return float(settings.MOMENTUM_TIME_STOP_R3_MULT)
    if "REGIME_2" in name or "ELEVATED" in name:
        return float(settings.MOMENTUM_TIME_STOP_R2_MULT)
    return float(settings.MOMENTUM_TIME_STOP_R1_MULT)


def _elapsed_minutes(entry_date: str, now: datetime) -> Optional[float]:
    """Minutes since entry. None if entry_date is unparseable."""
    try:
        entry_dt = datetime.fromisoformat(str(entry_date).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if entry_dt.tzinfo is None:
        entry_dt = entry_dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - entry_dt).total_seconds() / 60.0


def evaluate_momentum_exit(pos: dict, ltp: float, now: datetime) -> dict:
    """
    Pure decision function -- no I/O, so it is directly testable and falsifiable.

    Returns:
      {"action": "hold"|"exit"|"scale_out"|"trail",
       "reason": str,
       "new_stop": float|None,      # set on "trail" and "scale_out"
       "scale_shares": int}         # "scale_out" only: how many to sell now

    Ordering matters: target first (a trade that reached its target should book,
    even if it also qualifies for a trail), then the partial, then the time
    stop, then the ratchet.
    """
    entry = pos["entry_price"]
    initial_stop = pos["stop_loss_initial"]
    current_stop = pos.get("trailing_stop_current") or initial_stop
    target = pos.get("target_1")
    shares = pos.get("shares") or 0
    atr = pos.get("atr_14_at_entry")

    r_per_share = entry - initial_stop
    if r_per_share <= 0:
        # A non-positive R means the signal was malformed (stop at or above entry).
        # We cannot reason about R-multiples, so manage nothing and let the broker
        # SL-M and the 15:15 square-off handle it. Loud, because sizing divided by
        # this number.
        logger.error(
            "momentum_exit_invalid_r ticker=%s entry=%s stop=%s",
            pos.get("ticker"), entry, initial_stop,
        )
        return {"action": ACTION_HOLD, "reason": "invalid_r", "new_stop": None}

    r_now = (ltp - entry) / r_per_share

    # 1. Target -- book it.
    if target is not None and ltp >= target:
        return {"action": ACTION_EXIT, "reason": "target_hit", "new_stop": None}

    # 2. Scale out -- bank a real gain on part of the size, de-risk the rest.
    #
    # [SCALE-OUT 2026-08-04] Momentum was all-or-nothing: the trade reached the
    # target in full or it did not, and in practice it almost never did. Across
    # 27-31 Jul and 03 Aug, every closed momentum trade exited on the clock or
    # on a ratcheted stop between -0.71R and +0.49R -- the target was reached
    # once in thirteen. The strategy kept being RIGHT about direction and
    # collecting nothing for it: on 2026-08-03 SUMICHEM was stopped at
    # breakeven at 11:27 and printed its target at 12:00.
    #
    # Taking part of the position off at +1R and moving the remainder's stop to
    # cost-adjusted breakeven converts that pattern into a booked gain plus a
    # free runner. It is the standard institutional shape for a reason: it
    # stops the outcome depending on whether one specific price prints before
    # the clock runs out.
    #
    # This is NOT free -- it caps the good tail. A trade that would have run to
    # +2R now collects roughly 1.5R. That trade is rare here; the +0.4R that
    # decays back to breakeven is not.
    #
    # Ordered before the time stop deliberately: at 45 minutes and +1.2R the
    # time stop cannot fire anyway (it requires r_now < MOMENTUM_TIME_STOP_MIN_R),
    # but if the thresholds are ever retuned so the windows overlap, banking the
    # partial should win over closing the lot on the clock.
    if (
        settings.MOMENTUM_USE_SCALE_OUT
        and not pos.get("t1_fired")
        and r_now >= settings.MOMENTUM_SCALE_OUT_R
    ):
        scale_shares = int(shares * settings.MOMENTUM_SCALE_OUT_FRAC)
        if scale_shares >= 1 and scale_shares < shares:
            # De-risk the runner in the same decision. Below this price the
            # trade can no longer lose money net of the round trip.
            runner_stop = cost_adjusted_breakeven(entry, shares)
            if runner_stop >= ltp:
                # The stop would trigger the moment we set it (thin position,
                # costs larger than the move). Bank nothing; let the trade keep
                # working under the existing stop.
                return {
                    "action": ACTION_HOLD,
                    "reason": f"scale_out_stop_would_trigger_at_{r_now:.2f}R",
                    "new_stop": None,
                }
            return {
                "action": ACTION_SCALE_OUT,
                "reason": f"scale_out_at_{r_now:.2f}R",
                "scale_shares": scale_shares,
                "new_stop": round(max(runner_stop, current_stop), 2),
            }
        # shares == 1 is the common case on this bankroll: a 2,428 momentum
        # pool buys one share of a 1,600-rupee stock, and half of one share is
        # nothing. Say so rather than silently skipping -- it is the clearest
        # signal that position size, not exit logic, is the binding constraint.
        logger.info(
            "momentum_scale_out_skipped_size ticker=%s shares=%s r=%.2f",
            pos.get("ticker"), shares, r_now,
        )

    # 3. Time stop -- two-tier, regime-aware. A runner is never cut on the clock.
    #
    # [TIME-STOP-V2 2026-07-31] The old single 45-min / +0.5R rule fired on 8 of
    # 8 live trades (27-30 Jul), every one landing between -0.71R and +0.49R.
    # It cut failures too late and winners far too early. Tier one cuts a trade
    # that has already gone negative; tier two gives a merely-flat trade real
    # runway, scaled by regime, against a bar that is reachable.
    elapsed = _elapsed_minutes(pos.get("entry_date"), now)
    if elapsed is not None:
        if (
            elapsed >= settings.MOMENTUM_TIME_STOP_FAST_MIN
            and r_now < settings.MOMENTUM_TIME_STOP_FAST_R
        ):
            return {
                "action": ACTION_EXIT,
                "reason": f"time_stop_fast_{int(elapsed)}min_at_{r_now:.2f}R",
                "new_stop": None,
            }
        slow_min = settings.MOMENTUM_TIME_STOP_MIN * _regime_time_mult(
            pos.get("regime_at_entry")
        )
        if elapsed >= slow_min and r_now < settings.MOMENTUM_TIME_STOP_MIN_R:
            return {
                "action": ACTION_EXIT,
                "reason": f"time_stop_{int(elapsed)}min_at_{r_now:.2f}R",
                "new_stop": None,
            }

    # 4. Breakeven ratchet + trail. Nothing moves until the trade has paid for
    #    itself (MOMENTUM_BREAKEVEN_R, +0.6R by default) -- ratcheting earlier
    #    just converts noise into stop-outs at breakeven.
    #    [BREAKEVEN 2026-07-31] The bar was +1.0R and never engaged: the best of
    #    the 27-30 Jul trades peaked at +0.49R, so every one gave back what it
    #    had and paid costs on the exit. 0.6R sits above the noise band the ATR
    #    stop floor now establishes, and it is actually reachable.
    if r_now < settings.MOMENTUM_BREAKEVEN_R:
        return {"action": ACTION_HOLD, "reason": f"below_breakeven_r_{r_now:.2f}R", "new_stop": None}

    candidate = cost_adjusted_breakeven(entry, shares)

    if settings.MOMENTUM_USE_TRAIL and atr and atr > 0:
        # Trail behind the price. `atr` is NULL (never 0.0) when the entry could
        # not compute one -- a 0 ATR would put the trail AT the last price and
        # stop us out on the next tick.
        candidate = max(candidate, ltp - (settings.MOMENTUM_TRAIL_ATR_MULT * atr))

    # The stop only ever ratchets up, and must stay strictly below the last price
    # or the SL-M triggers immediately on modification.
    new_stop = max(candidate, current_stop)
    if new_stop >= ltp:
        return {"action": ACTION_HOLD, "reason": "trail_would_trigger_at_ltp", "new_stop": None}
    if new_stop <= current_stop:
        return {"action": ACTION_HOLD, "reason": "trail_not_improved", "new_stop": None}

    return {
        "action": ACTION_TRAIL,
        "reason": f"ratchet_at_{r_now:.2f}R",
        "new_stop": round(new_stop, 2),
    }
