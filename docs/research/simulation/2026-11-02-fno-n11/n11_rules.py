"""N11's rules as pure arithmetic. No data access, no dates, nothing here reads a future bar."""
from __future__ import annotations

import math
from typing import Callable, Optional, Sequence, Tuple


def _num(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def budget(pool: float, risk_pct: float, max_rupees: float, flat: float, multiplier: float) -> float:
    """The most this trade may plan to lose: the planner's two limits, the owner's flat limit, all scaled down in a drawdown and never scaled up by a winning streak."""
    scale = max(0.0, float(multiplier))
    return min(pool * risk_pct * scale, max_rupees * scale, flat * min(1.0, scale))


def backstop_points(limit: float, ask: float, qty: int, extra: float, fees: Callable[[float, float, int], float]) -> Optional[float]:
    """How many premium points this size can fall from entry and still lose no more than the limit, fees and declared stress included."""
    if not all(_num(v) for v in (limit, ask, extra)) or qty <= 0 or ask <= 0:
        return None
    room = limit - fees(ask, ask, qty) - extra
    return room / qty if room > 0 else None


def true_risk_lots(native: int, ceiling: int, ask: float, delta: float, stop_points: float, lot_size: int, limit: float, k: float, stop_pct: float,
                   fees: Callable[[float, float, int], float], extra: Callable[[int], float]) -> Tuple[int, Optional[float]]:
    """The size the trade's own stop allows, and the premium points its backstop must sit at.

    The native planner charges every lot 25% of premium, so an expensive option gets one lot however close its own stop is. Here a lot is
    charged what the trade's stop is expected to cost: k x delta x the stop's distance. A size is allowed only if that fits inside the limit,
    so the strategy's own stop acts before the tightened backstop. The backstop then keeps the whole trade inside the limit if the stop fails.
    Returns (native, None) when nothing larger fits: the native trade is unchanged.
    """
    if native < 1 or ceiling <= native or not all(_num(v) and v > 0 for v in (ask, stop_points, limit, k, stop_pct)) or not _num(delta) or lot_size <= 0:
        return native, None
    expected = k * abs(delta) * stop_points
    for lots in range(ceiling, native, -1):
        points = backstop_points(limit, ask, lots * lot_size, extra(lots), fees)
        if points is not None and expected <= points:
            return lots, min(points, ask * stop_pct)
    return native, None


def stop_price(ask: float, points: float, tick: float = 0.05) -> float:
    """The tightened backstop, rounded up to the option's tick so the planned loss never exceeds the limit."""
    return round(math.ceil((ask - points) / tick - 1e-9) * tick, 2)


def adverse_distance(direction: str, future: float, level: float) -> float:
    """How far the future must travel against the trade to reach this level. Zero if it is already there."""
    side = 1 if direction == "LONG" else -1
    return max(0.0, side * (future - level))


def parent_loss_at_stop(direction: str, future: float, bid: float, delta: float, level: float, entry: float, premium_stop: float, qty: int, extra: float,
                        fees: Callable[[float, float, int], float]) -> float:
    """What the held lots are expected to lose if the underlying reaches their current stop: the option today, less delta times that distance,
    no lower than their premium backstop. Zero when they would still be in profit there. An estimate, not a guarantee: stops can gap."""
    value = max(bid - abs(delta) * adverse_distance(direction, future, level), premium_stop, 0.0)
    return max(0.0, (entry - value) * qty + fees(entry, value, qty) + extra)


def child_full_loss(ask: float, stop_pct: float, qty: int, extra: float, fees: Callable[[float, float, int], float]) -> float:
    """The earned lot's whole planned loss: its 25% backstop, fees and declared stress."""
    stop = ask * (1.0 - stop_pct)
    return (ask - stop) * qty + fees(ask, stop, qty) + extra


def open_net(entry: float, bid: float, qty: int, extra: float, fees: Callable[[float, float, int], float]) -> float:
    """What the held lots would bank if sold now, fees and declared stress included."""
    return (bid - entry) * qty - fees(entry, bid, qty) - extra


def evidence_positive(nets: Sequence[float], need: int = 20) -> bool:
    """The same reading WATCH uses: the last 20 closed paper trades, strictly before now, together made money."""
    return len(nets) >= need and sum(nets[-need:]) > 0


def evidence_negative(nets: Sequence[float], need: int = 20) -> bool:
    """Known and not positive. With too little history nothing is known, and an unknown never stands the book aside."""
    return len(nets) >= need and sum(nets[-need:]) <= 0


def stand_aside(vol_up: bool, nets: Sequence[float], need: int = 20) -> bool:
    """Real entries wait while BOTH readings are against the book: a below-usual-volatility day and a losing paper record.
    The paper book keeps trading, so this ends by itself the moment either reading turns."""
    return (not vol_up) and evidence_negative(nets, need)


def noise_stop(stop_points: float, atr: float, limit: float) -> bool:
    """A stop closer than this many five-minute ATRs sits inside ordinary movement."""
    return _num(stop_points) and _num(atr) and atr > 0 and stop_points < limit * atr
