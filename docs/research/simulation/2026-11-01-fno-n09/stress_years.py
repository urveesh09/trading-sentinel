"""After the supplement, and not part of any frozen rule: the month reshuffle hardly ever used a restart, because shuffled months break up a bad stretch.

This keeps each year whole. All 256 ways to draw four years with repetition, N08 at one lot, so a 2023-type year can come twice or more.
One-lot streams only: sizes aren't replayed, so read the differences between rules, not the rupee level. Also prints the readings the report quotes.
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze_panel import YEARS, keys, load, paired_t, all_weeks, stats  # noqa: E402

LOCAL = HERE / "_local"


def path_end(sequence, stream, rule) -> dict:
    equity = low = 250000.0
    floor = 212500.0
    halted, halted_block, paper, restarts = False, None, [], 0
    for block, year in enumerate(sequence):
        if rule == "ANNUAL" and halted and block > halted_block:
            halted, floor, restarts = False, equity * 0.85, restarts + 1
        for net in stream[year]:
            paper.append(net)
            if rule == "SHADOW" and halted and len(paper) >= 20 and sum(paper[-20:]) > 0:
                halted, floor, restarts = False, equity * 0.85, restarts + 1
            if not halted:
                equity += net
                low = min(low, equity)
                if equity < floor:
                    halted, halted_block = True, block
    return {"end": round(equity), "low": round(low), "restarts": restarts}


def main() -> None:
    stream = {y: [float(t["net_pnl"]) for t in load(y, keys("diag", y)["DIAG"])] for y in YEARS}
    rows = {}
    for sequence in itertools.product(YEARS, repeat=4):
        rows[sequence] = {rule: path_end(sequence, stream, rule) for rule in ("NONE", "ANNUAL", "SHADOW")}
    summary = {}
    for rule in ("NONE", "ANNUAL", "SHADOW"):
        ends = np.array([r[rule]["end"] for r in rows.values()])
        summary[rule] = {"median_end": round(float(np.median(ends))), "worst_end": int(ends.min()), "best_end": int(ends.max()), "below_start": int((ends < 250000).sum()), "lowest_equity_seen": min(r[rule]["low"] for r in rows.values())}
    compare = {}
    for rule in ("ANNUAL", "SHADOW"):
        gaps = np.array([r[rule]["end"] - r["NONE"]["end"] for r in rows.values()])
        compare[rule] = {"helps": int((gaps > 0).sum()), "hurts": int((gaps < 0).sum()), "same": int((gaps == 0).sum()), "largest_gain": int(gaps.max()), "largest_cost": int(gaps.min()), "mean_gap": round(float(gaps.mean()))}
    named = {" ".join(s): rows[s] for s in (("2023", "2024", "2025", "2026"), ("2023", "2023", "2024", "2025"), ("2023", "2023", "2023", "2024"), ("2023", "2023", "2023", "2023"), ("2024", "2023", "2023", "2025"), ("2025", "2023", "2023", "2023"))}
    print(json.dumps({"paths": len(rows), "summary": summary, "restart_against_none": compare, "named": named}, indent=1), flush=True)

    # Readings the report quotes.
    import n09_lab as Z
    table = Z.vol_table()
    two = {}
    for y in YEARS:
        days = [d for d in table if d.startswith(y) and table[d][1] is not None]
        two[y] = {"sessions": len(days), "share_two_lots": round(sum(table[d][0] >= table[d][1] for d in days) / len(days), 3)}
    print("share of sessions with the volatility reading at or above its usual level:", two, flush=True)
    lots = {}
    for y in YEARS:
        trades = load(y, keys("panel", y)["CASH|S_VOL"])
        lots[y] = dict(Counter(int(t["entry_qty"]) // 65 for t in trades))
    print("S_VOL trades by lots:", lots, flush=True)
    nb = {y: keys("supp", y) for y in YEARS}
    weeks = all_weeks()
    a = [t for y in YEARS for t in load(y, nb[y]["NOBRAKE|S_VOL"])]
    b = [t for y in YEARS for t in load(y, nb[y]["NOBRAKE|N08"])]
    print("brakes off, S_VOL against N08, paired weekly t:", round(paired_t(a, b, weeks), 2), flush=True)
    panel = {y: keys("panel", y) for y in YEARS}
    for name in ("ONE|NOISE_TEXTBOOK", "ONE|NOISE_HOUSE"):
        trades = [t for y in YEARS for t in load(y, panel[y][name])]
        extra = sum(t.get("extra_cost") or 0 for t in trades)
        print(name, "trades", len(trades), "net", round(sum(t["net_pnl"] for t in trades)), "assumed extra cost", round(extra), "before that", round(sum(t["net_pnl"] for t in trades) + extra), "exits", dict(Counter(t["exit_reason"] for t in trades).most_common(5)), flush=True)
    for name in ("ONE|D65", "ONE|D75", "ONE|CONFIRM"):
        print(name, "trades", [len(load(y, panel[y][name])) for y in YEARS], "falls", [stats(load(y, panel[y][name]))["fall_pct"] for y in YEARS], flush=True)
    (HERE / "results-stress.json").write_text(json.dumps({"schema": "n09_stress_v1", "note": "added after the supplement's results; not a frozen rule", "paths": len(rows), "summary": summary, "restart_against_none": compare, "named": named, "two_lot_share": two, "s_vol_lots": lots}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
