"""Advisory profit floor, the give-back stop and causal futures context for the partner watch."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import math


def floor_for(best: float, cash: float, chosen: float | None = None) -> float | None:
    """A chosen floor arms when reached. The suggested floor trails material booked gains."""
    if not math.isfinite(best) or not math.isfinite(cash) or cash <= 0:
        return None
    if chosen is not None:
        return chosen if math.isfinite(chosen) and 0 < chosen <= best else None
    return round(best * 0.90, 2) if best >= max(5000, cash * 0.20) else None


def futures_direction(bars, price: float, now: datetime) -> str:
    """Assess the last three closed five-minute bars and a verified live price.

    The clock and bar starts are naive IST. Exact recent slots matter: stale
    or missing bars must not become a directional claim.
    """
    if bars is None or not math.isfinite(price) or price <= 0 or not bars.index.is_unique:
        return "UNKNOWN"
    end = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
    starts = [end - timedelta(minutes=i) for i in (15, 10, 5)]
    if starts[0].date() != end.date() or starts[0].time() < time(9, 15):
        return "UNKNOWN"
    if any(at not in bars.index for at in starts):
        return "UNKNOWN"
    high, low, close = (list(bars.loc[starts, col]) for col in ("high", "low", "close"))
    if any(not all(math.isfinite(v) for v in (h, l, c)) or not 0 < l <= c <= h
           for h, l, c in zip(high, low, close)):
        return "UNKNOWN"
    if min(close[-1], price) > max(high[:2]):
        return "UP"
    if max(close[-1], price) < min(low[:2]):
        return "DOWN"
    if low[0] < low[1] < low[2] and close[0] < close[1] < close[2] and price >= max(low[2], close[1]):
        return "UP"
    if high[0] > high[1] > high[2] and close[0] > close[1] > close[2] and price <= min(high[2], close[1]):
        return "DOWN"
    return "MIXED"


def trend_note(direction: str, underlying: str, side: str, *, advise: bool = True) -> str:
    """Relate observed futures direction to the specific option being assessed."""
    if direction == "UNKNOWN" or side not in ("CE", "PE"):
        return "Current trend unverified."
    if direction == "MIXED":
        return f"{underlying} futures are mixed."
    move = "rising" if direction == "UP" else "falling"
    option = "calls" if side == "CE" else "puts"
    if (direction == "UP") == (side == "CE"):
        text = f"{underlying} futures are {move}, supporting {option}."
        return text + " Continue cautiously." if advise else text
    text = f"{underlying} futures are {move}, against {option}."
    return text + " Protect profit. Reduce risk or pause new buys." if advise else text


# [SN121 2026-11-13] The give-back stop. On the partner's 7 recorded sessions (Oct 27 - Nov 4) the day's best was
# >= +20% of their cash on 5 days, yet only 3 ended green, after a median of 22 more trades. Stopping once a day that
# had been up >= 5% of the cash fell back 30% from its best cut the 7-day loss by ~71% (docs/research/fno/
# 2026-11-13-sn121). Advice only: the partner decides.
GIVEBACK_ARM_SHARE = 0.05
GIVEBACK_STOP_SHARE = 0.30


def giveback_stop(best: float, now_value: float, cash: float, arm: float = GIVEBACK_ARM_SHARE,
                  give: float = GIVEBACK_STOP_SHARE) -> bool:
    """True when the day's best (booked plus open trades at their bids) reached ``arm`` of the cash and the day now
    stands at or under ``1 - give`` of that best."""
    if not all(math.isfinite(x) for x in (best, now_value, cash)) or cash <= 0 or best <= 0:
        return False
    return best >= arm * cash and now_value <= (1.0 - give) * best


def _rs(x: float) -> str:
    sign = "+" if x >= 0 else "-"
    return f"{sign}₹{abs(x):,.0f}"


def giveback_stop_text(best: float, now_value: float) -> str:
    """The partner's message: short, concrete, their call."""
    given = max(0.0, best - now_value) / best if best > 0 else 0.0
    if now_value > 0:
        head, part = "🛑 Stop for today and keep your profit.", f"{given:.0%} of it given back"
    else:
        head, part = "🛑 Stop for today.", "all of it given back"
    return (f"{head}\nBest today {_rs(best)}, now {_rs(now_value)}: {part}.\n"
            f"On your recent days, trading on from here gave the rest back. Your call.")

