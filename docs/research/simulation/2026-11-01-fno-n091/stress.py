"""Causal fixed-one-lot admission/exit proxy; not a replacement market replay."""
from __future__ import annotations
import itertools
import json
from pathlib import Path

import n091_rules as R

HERE = Path(__file__).resolve().parent
YEARS = ("2023", "2024", "2025", "2026")


def simulate(sequence, streams, rule, need=20):
    """Paper labels become available at EXIT, strictly before a restart's ENTRY.

    Existing actual positions always close even when new entries are halted.
    Same-instant actual exits settle before entries; shadow labels at that same
    instant are excluded. No entry decision consumes that trade's future P&L.
    """
    equity = peak = low = 250000.
    floor = 212500.
    state = R.Budget(equity, equity, floor)
    halted = False
    halted_block = None
    active = {}
    paper = []
    count = restarts = 0
    floor_min = floor
    for block, year in enumerate(sequence):
        if rule == "ANNUAL" and halted and block > halted_block:
            halted, floor, restarts = False, equity * .85, restarts + 1
        events = []
        for i, trade in enumerate(streams[year]):
            events += [(trade["entry_time"], 1, i, trade), (trade["exit_time"], 0, i, trade)]
        for at, kind, ident, trade in sorted(events, key=lambda e: e[:3]):
            if kind == 0:
                paper.append(((block, at), trade["net_pnl"]))
                if ident in active:
                    equity += trade["net_pnl"]
                    del active[ident]
                    low, peak = min(low, equity), max(peak, equity)
                    if equity < floor:
                        halted, halted_block = True, block
                continue
            if rule == "SHADOW" and halted:
                prior = [net for stamp, net in paper if stamp < (block, at)]
                if len(prior) >= need and sum(prior[-need:]) > 0:
                    halted, floor, restarts = False, equity * .85, restarts + 1
            if halted:
                continue
            if rule == "CUSHION":
                existing = sum(active.values())
                state = R.advance(state, equity, existing, .15)
                floor = state.floor
                if not R.affordable(1, equity, floor, existing, {1: trade["full_reserve"]}):
                    continue
            active[ident] = trade["full_reserve"]
            count += 1
            floor_min = min(floor_min, floor)
        assert not active, "proxy must retain unresolved exposure, not drop it at a year boundary"
    return {"end": equity, "low": low, "trades": count, "restarts": restarts,
            "floor_min": floor_min, "peak": peak}


def main():
    import sys
    sys.path.insert(0, str(HERE))
    import n091_lab as L
    L.verify()
    old = HERE.parent / "2026-11-01-fno-n09/_local"
    streams = {}
    for y in YEARS:
        key = json.loads((old / f"keys-diag-{y}.json").read_text())["DIAG"]
        rows = json.loads((old / f"evals-{y}/{key}.json").read_text())["trades"]
        streams[y] = [{**t, "full_reserve": L.full_reserve(t["entry_premium"], 65, 1, [200., 5.])} for t in rows]
    rows = {}
    rules = ("NONE", "ANNUAL", "SHADOW", "CUSHION")
    for sequence in itertools.product(YEARS, repeat=4):
        rows["/".join(sequence)] = {rule: simulate(sequence, streams, rule) for rule in rules}
    out = {"schema": "n091_causal_proxy_v1", "fidelity": "PORTFOLIO_PROXY", "paths": 256,
           "note": "fixed one-lot N08 admission universe; no new sizing/signals/native-brake or market replay; shadow exits strictly precede admission",
           "rules": {}, "versus_none": {}, "all_paths": rows}
    for rule in rules:
        ends = sorted(row[rule]["end"] for row in rows.values())
        out["rules"][rule] = {"worst_end": ends[0], "median_end": (ends[127] + ends[128]) / 2,
            "lowest_equity": min(row[rule]["low"] for row in rows.values()),
            "below_start": sum(e < 250000 for e in ends)}
        diff = [row[rule]["end"] - row["NONE"]["end"] for row in rows.values()]
        out["versus_none"][rule] = {"helps": sum(d > .01 for d in diff), "hurts": sum(d < -.01 for d in diff),
            "same": sum(abs(d) <= .01 for d in diff), "largest_gain": max(diff), "largest_cost": min(diff)}
    L.write(HERE / "stress-results.json", out)
    print(json.dumps({k: v for k, v in out.items() if k != "all_paths"}, indent=2))


if __name__ == "__main__":
    main()
