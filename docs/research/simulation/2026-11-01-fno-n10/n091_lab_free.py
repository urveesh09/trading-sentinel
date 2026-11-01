"""N09.1's causal whole-year proxy, unchanged in logic, without importing its replay stack. Its one dependency is the pure budget rule."""
from __future__ import annotations

import n091_rules as R


def simulate(sequence, streams, rule):
    """Exits settle before entries at the same instant. Rules here: NONE (the permanent 15% stop) and CUSHION (the funded floor). No restart rule is used by N10."""
    assert rule in ("NONE", "CUSHION")
    equity = peak = low = 250000.0
    floor = 212500.0
    state = R.Budget(equity, equity, floor)
    halted = False
    active: dict = {}
    count = 0
    for block, year in enumerate(sequence):
        events = []
        for i, trade in enumerate(streams[year]):
            events += [(trade["entry_time"], 1, i, trade), (trade["exit_time"], 0, i, trade)]
        for _at, kind, ident, trade in sorted(events, key=lambda e: e[:3]):
            if kind == 0:
                if ident in active:
                    equity += trade["net_pnl"]
                    del active[ident]
                    low, peak = min(low, equity), max(peak, equity)
                    if equity < floor:
                        halted = True
                continue
            if halted:
                continue
            if rule == "CUSHION":
                existing = sum(active.values())
                state = R.advance(state, equity, existing, 0.15)
                floor = state.floor
                if not R.affordable(1, equity, floor, existing, {1: trade["full_reserve"]}):
                    continue
            active[ident] = trade["full_reserve"]
            count += 1
        assert not active
    return {"end": equity, "low": low, "trades": count, "peak": peak}
