"""[DECAY 2026-08-05] Per-division health, with hysteresis.

THE PROBLEM
-----------
This system has two failure modes around strategy lifecycle and it has hit both:

  * A book stops trading and nobody notices. Penny breakout and Connors have
    each gone months at zero fills; both were found by an audit, not by the
    system, and the 2026-07-20 audit put penny breakout at 0 accepts from
    533,000 evaluations.
  * A book keeps trading after its edge is gone. Nothing measures decay, so the
    only signal is the bankroll, by which point the money is spent.

A status field alone does not fix this, because a single bad reading is not
decay -- it is Tuesday. What is needed is a state machine with memory.

THE MACHINE
-----------
Borrowed from HKUDS/Vibe-Trading's `strategy_store/decay.py` (MIT), adapted from
factor IC metrics to the trade statistics we actually have:

    ACTIVE ──3 consecutive non-healthy──▶ MONITORING
    MONITORING ──2 consecutive decayed/critical──▶ DECAYED
    MONITORING ──1 healthy──▶ ACTIVE          (recovery is fast on purpose)
    DECAYED ──3 consecutive critical──▶ DISABLED

The asymmetry is deliberate and is the whole design. Demotion needs repetition
because a strategy that is merely unlucky must not be switched off; promotion
needs one good reading because a strategy held down by stale history is a
strategy nobody re-enables. The cost of a slow demotion is a few more losing
trades. The cost of a slow promotion is that the system ratchets itself shut,
which is exactly what the regime ratchet did.

STATUS IS ADVISORY UNTIL SOMEONE WIRES IT
-----------------------------------------
`DISABLED` here does NOT stop trading by itself. That would be a second kill
switch with different semantics from halt_switch, and two kill switches is one
too many. The intended path is: this reports, the operator (or a later job)
trips the channel sentinel. Said plainly so nobody assumes protection that is
not there -- the same mistake as `check_circuit_breakers` returning a `halted`
boolean nothing read.

Pure functions: no DB, no clock, no config.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence


class Health(str, Enum):
    """One reading's verdict."""

    HEALTHY = "healthy"
    WARNING = "warning"
    DECAYED = "decayed"
    CRITICAL = "critical"


class Status(str, Enum):
    """A division's standing, accumulated over readings."""

    ACTIVE = "active"
    MONITORING = "monitoring"
    DECAYED = "decayed"
    DISABLED = "disabled"


#: Worst-first, for aggregating several metrics into one reading.
_SEVERITY = [Health.CRITICAL, Health.DECAYED, Health.WARNING, Health.HEALTHY]


@dataclass(frozen=True)
class Thresholds:
    """Where each metric turns from healthy to critical.

    Expectancy is in R, so it is size-independent and comparable across books
    whose pools differ by two orders of magnitude (momentum runs on ~Rs 2.4k,
    F&O paper on a notional 250k).

    `activity_ratio` is fills divided by expected fills over the window. It is
    here because the loudest failure this system has had was not a losing
    strategy but a SILENT one, and expectancy says nothing at all about a book
    that took no trades.
    """

    expectancy_r_healthy: float = 0.10
    expectancy_r_warning: float = 0.0
    expectancy_r_decayed: float = -0.15

    profit_factor_healthy: float = 1.20
    profit_factor_warning: float = 1.00
    profit_factor_decayed: float = 0.80

    activity_ratio_healthy: float = 0.50
    activity_ratio_warning: float = 0.20
    activity_ratio_decayed: float = 0.05

    #: Consecutive readings needed for each transition.
    readings_to_monitor: int = 3
    readings_to_decay: int = 2
    readings_to_disable: int = 3


def _classify(value: float, healthy: float, warning: float,
              decayed: float) -> Health:
    """Bucket one metric against three descending thresholds."""
    if value >= healthy:
        return Health.HEALTHY
    if value >= warning:
        return Health.WARNING
    if value >= decayed:
        return Health.DECAYED
    return Health.CRITICAL


def _worst(a: Health, b: Health) -> Health:
    return a if _SEVERITY.index(a) <= _SEVERITY.index(b) else b


def read_health(
    *,
    expectancy_r: Optional[float] = None,
    profit_factor: Optional[float] = None,
    activity_ratio: Optional[float] = None,
    n_trades: int = 0,
    min_trades: int = 10,
    thresholds: Thresholds = Thresholds(),
) -> Health:
    """One reading, from whichever metrics are available.

    The WORST metric wins. A book with fine expectancy that has stopped taking
    trades is not healthy, and averaging would hide that.

    Below `min_trades` the expectancy and profit-factor readings are ignored as
    noise -- but activity is still read, because "too few trades to judge" is
    itself the activity finding.
    """
    readings: list[Health] = []

    if n_trades >= min_trades:
        if expectancy_r is not None:
            readings.append(_classify(
                expectancy_r, thresholds.expectancy_r_healthy,
                thresholds.expectancy_r_warning, thresholds.expectancy_r_decayed))
        if profit_factor is not None:
            readings.append(_classify(
                profit_factor, thresholds.profit_factor_healthy,
                thresholds.profit_factor_warning, thresholds.profit_factor_decayed))

    if activity_ratio is not None:
        readings.append(_classify(
            activity_ratio, thresholds.activity_ratio_healthy,
            thresholds.activity_ratio_warning, thresholds.activity_ratio_decayed))

    if not readings:
        # Nothing measurable. Not healthy -- unknown. WARNING keeps it visible
        # without starting a demotion clock on the strength of no evidence.
        return Health.WARNING

    worst = readings[0]
    for r in readings[1:]:
        worst = _worst(worst, r)
    return worst


def next_status(
    current: Status,
    readings: Sequence[Health],
    thresholds: Thresholds = Thresholds(),
) -> Optional[Status]:
    """The status this division should move to, or None to stay put.

    Args:
        current: Where it is now.
        readings: Recent health readings, OLDEST FIRST. Only the tail matters.
        thresholds: Transition counts.
    """
    if not readings:
        return None

    if current is Status.ACTIVE:
        need = thresholds.readings_to_monitor
        tail = readings[-need:]
        if len(tail) >= need and all(r is not Health.HEALTHY for r in tail):
            return Status.MONITORING
        return None

    if current is Status.MONITORING:
        # Recovery on a single healthy reading. Fast on purpose: a book held
        # down by stale history is a book nobody turns back on.
        if readings[-1] is Health.HEALTHY:
            return Status.ACTIVE
        need = thresholds.readings_to_decay
        tail = readings[-need:]
        if len(tail) >= need and all(
                r in (Health.DECAYED, Health.CRITICAL) for r in tail):
            return Status.DECAYED
        return None

    if current is Status.DECAYED:
        if readings[-1] is Health.HEALTHY:
            return Status.MONITORING          # climbing back, one rung at a time
        need = thresholds.readings_to_disable
        tail = readings[-need:]
        if len(tail) >= need and all(r is Health.CRITICAL for r in tail):
            return Status.DISABLED
        return None

    # DISABLED is terminal for the machine: coming back is an operator
    # decision, not an automatic one. Turning a book back on by itself after
    # the machine judged it dead is not a call code should make.
    return None


def evaluate(
    current: Status,
    prior_readings: Sequence[Health],
    *,
    expectancy_r: Optional[float] = None,
    profit_factor: Optional[float] = None,
    activity_ratio: Optional[float] = None,
    n_trades: int = 0,
    min_trades: int = 10,
    thresholds: Thresholds = Thresholds(),
) -> tuple[Health, Optional[Status]]:
    """Take a reading and decide the transition in one call.

    Returns:
        (this reading, new status or None if unchanged).
    """
    reading = read_health(
        expectancy_r=expectancy_r, profit_factor=profit_factor,
        activity_ratio=activity_ratio, n_trades=n_trades,
        min_trades=min_trades, thresholds=thresholds)
    history = list(prior_readings) + [reading]
    return reading, next_status(current, history, thresholds)


def describe(division: str, status: Status, reading: Health,
             transition: Optional[Status] = None) -> str:
    """One line for /divisions."""
    arrow = f"  ->  {transition.value.upper()}" if transition else ""
    return f"{division:<12} {status.value:<11} (latest reading: {reading.value}){arrow}"


def explain(status: Status) -> str:
    """What a status means for the operator, including what it does NOT do."""
    return {
        Status.ACTIVE: "Trading normally.",
        Status.MONITORING: "Readings have been off for a while. Watching; "
                           "nothing is blocked. One healthy reading restores it.",
        Status.DECAYED: "Sustained poor readings. Worth halting this channel "
                        "by hand (/halt <channel> <reason>) while you look.",
        Status.DISABLED: "The machine judged this book dead. It does NOT stop "
                         "trading on its own -- trip the channel sentinel if "
                         "you want it stopped.",
    }.get(status, "")
