"""N10.1 price-denominated arithmetic; no market/history access."""
from __future__ import annotations

import math
from statistics import median


def finite_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def net_at(entry, exit_price, qty, extra, fees):
    if not all(finite_positive(x) for x in (entry, qty)) or not math.isfinite(exit_price) or exit_price < 0:
        raise ValueError("invalid premium/quantity")
    if not math.isfinite(extra) or extra < 0:
        raise ValueError("invalid stress")
    return (exit_price - entry) * qty - fees(entry, exit_price, qty) - extra


def funded_stop(entry, qty, extra, required_net, fees, tick=0.05):
    """Smallest tick-rounded premium whose NET covers required_net. Not a fill promise."""
    if not finite_positive(entry) or not finite_positive(qty) or not math.isfinite(extra) or extra < 0:
        raise ValueError("invalid premium/quantity/stress")
    if not finite_positive(tick) or not math.isfinite(required_net) or required_net < 0:
        raise ValueError("invalid tick/required net")
    low, high = 0.0, entry + (extra + required_net + fees(entry, entry, qty)) / qty + 1.0
    for _ in range(32):
        if net_at(entry, high, qty, extra, fees) >= required_net:
            break
        high *= 2.0
    else:
        raise ValueError("non-monotone/unbounded fee schedule")
    for _ in range(64):
        mid = (low + high) / 2.0
        if net_at(entry, mid, qty, extra, fees) >= required_net:
            high = mid
        else:
            low = mid
    answer = math.ceil(high / tick - 1e-10) * tick
    if net_at(entry, answer, qty, extra, fees) < required_net - 1e-8:
        answer += tick
    return round(answer, 8)


def genuinely_stuck(equity, floor, open_count, current_reserve, earlier_reserves, need=20):
    """Require a flat book and an affordable-typical contract, not an expensive outlier."""
    if open_count or len(earlier_reserves) < need:
        return False, None
    recent = list(earlier_reserves[-need:])
    if not all(finite_positive(v) for v in (*recent, equity, floor, current_reserve)):
        return False, None
    typical = float(median(recent))
    headroom = equity - floor
    return headroom < current_reserve <= typical and headroom < typical, typical
