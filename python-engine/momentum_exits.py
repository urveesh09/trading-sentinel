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
      {"action": "hold"|"exit"|"trail",
       "reason": str,
       "new_stop": float|None}   # only set when action == "trail"

    Ordering matters: target first (a trade that reached its target should book,
    even if it also qualifies for a trail), then the time stop, then the ratchet.
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

    # 2. Time stop -- a momentum trade that has gone nowhere is a failed thesis.
    #    Only fires while the trade is still below the min-R bar; a runner is
    #    never cut on the clock.
    elapsed = _elapsed_minutes(pos.get("entry_date"), now)
    if (
        elapsed is not None
        and elapsed >= settings.MOMENTUM_TIME_STOP_MIN
        and r_now < settings.MOMENTUM_TIME_STOP_MIN_R
    ):
        return {
            "action": ACTION_EXIT,
            "reason": f"time_stop_{int(elapsed)}min_at_{r_now:.2f}R",
            "new_stop": None,
        }

    # 3. Breakeven ratchet + trail. Nothing moves until the trade has paid for
    #    itself (+1R by default) -- ratcheting earlier just converts noise into
    #    stop-outs at breakeven.
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
