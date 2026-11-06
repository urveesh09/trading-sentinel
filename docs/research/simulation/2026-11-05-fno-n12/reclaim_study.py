"""Fixed cost and decision rules for the paired reclaim quote study."""

from dataclasses import dataclass
from decimal import Decimal

from paired_reclaim import BASELINE, CHALLENGER, ReclaimPairResult, compare_reclaim


BANKROLL = 250_000
MINIMUM_CHANGES = 15
EXTRA_WORST_DAY_RS = Decimal(1000)
EXTRA_CLOSED_DRAWDOWN_PP = Decimal(1)
ZERO = Decimal(0)


@dataclass(frozen=True)
class Decision:
    verdict: str
    gates: dict[str, bool]
    changed_executions: int | None = None
    best_incremental_day: str | None = None
    best_day_delta: Decimal | None = None
    ex_best_day_delta: Decimal | None = None


@dataclass(frozen=True)
class Study:
    standard: ReclaimPairResult
    doubled: ReclaimPairResult
    decision: Decision


def _decide(standard: ReclaimPairResult, doubled: ReclaimPairResult) -> Decision:
    if standard.pair.summaries is None or doubled.pair.summaries is None:
        return Decision("incomplete", {})
    baseline = standard.pair.summaries[BASELINE]
    challenger = standard.pair.summaries[CHALLENGER]
    days = baseline["daily"].keys() | challenger["daily"].keys()
    increments = {day: challenger["daily"].get(day, ZERO) - baseline["daily"].get(day, ZERO)
                  for day in sorted(days)}
    best = max(increments, key=increments.get, default=None)
    best_delta = increments.get(best, ZERO)
    ex_best = standard.pair.net_delta - best_delta
    native_signals = {(row.ticket.venue, row.ticket.signal_bar) for row in standard.native_trades}
    changes = len(native_signals) + len(standard.reclaim_exits)
    gates = {
        "positive_net": standard.pair.net_delta > ZERO,
        "positive_ex_best_day": ex_best > ZERO,
        "worst_day": baseline["worst_day"] - challenger["worst_day"] <= EXTRA_WORST_DAY_RS,
        "closed_drawdown": challenger["drawdown_pct"] - baseline["drawdown_pct"] <= EXTRA_CLOSED_DRAWDOWN_PP,
        "positive_doubled_cost_net": doubled.pair.net_delta > ZERO,
    }
    if changes < MINIMUM_CHANGES:
        verdict = "insufficient"
    else:
        verdict = "pass" if all(gates.values()) else "fail"
    return Decision(verdict, gates, changes, best, best_delta, ex_best)


def run_study(ticks, expected_scans, *, signals, quotes, gate_tape=None) -> Study:
    """Replay two fresh books per cost case on exactly the supplied frozen tape."""
    tape, scans = tuple(ticks), tuple(expected_scans)
    inputs = {"signals": dict(signals), "quotes": tuple(quotes), "allocation": BANKROLL, "gate_tape": gate_tape}
    standard = compare_reclaim(tape, scans, stress_multiple=1, **inputs)
    doubled = compare_reclaim(tape, scans, stress_multiple=2, **inputs)
    return Study(standard, doubled, _decide(standard, doubled))
