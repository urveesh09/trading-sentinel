"""All 256 orderings of whole years, on N09.1's causal one-lot proxy, with WATCH added. A proxy: fixed admissions, no regenerated market decisions.

Exits settle before entries at the same instant. Paper evidence reads only exits strictly before the entry being judged. An entry is refused when
its full premium can't be funded above the floor, and that refusal is what can call for a slice, as in the replay.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-01-fno-n091")]
import n091_rules as B  # noqa: E402
import n10b_rules as W  # noqa: E402
from n091_lab_free import simulate  # noqa: E402

YEARS = ("2023", "2024", "2025", "2026")
CAPITAL = 250000.0
WATCH = {"need": 20, "slice": 0.05, "deepest": 0.75}


def watch_path(sequence, streams, cfg=WATCH) -> dict:
    equity = peak = low = best = CAPITAL
    state = B.Budget(CAPITAL, CAPITAL, CAPITAL * 0.85)
    active: dict = {}
    paper: list = []
    last_at = None
    slices = trades = 0
    for block, year in enumerate(sequence):
        events = []
        for i, trade in enumerate(streams[year]):
            events += [(trade["entry_time"], 1, i, trade), (trade["exit_time"], 0, i, trade)]
        for at, kind, ident, trade in sorted(events, key=lambda e: e[:3]):
            stamp = (block, at)
            if kind == 0:
                paper.append((stamp, trade["net_pnl"]))
                if ident in active:
                    equity += trade["net_pnl"]
                    del active[ident]
                    low, peak, best = min(low, equity), max(peak, equity), max(best, equity)
                continue
            existing = sum(active.values())
            state = B.advance(state, equity, existing, 0.15)
            if not B.affordable(1, equity, state.floor, existing, {1: trade["full_reserve"]}):
                prior = [net for when, net in paper if when < stamp]
                since = sum(when < stamp for when, _ in paper) - (sum(when <= last_at for when, _ in paper) if last_at else 0)
                lower = W.lowered_floor(state.floor, best, cfg["slice"], cfg["deepest"]) if W.evidence_ok(prior, since, cfg["need"]) else None
                if lower is None:
                    continue
                state = B.Budget(state.anchor, equity, lower)
                last_at = stamp
                slices += 1
                if not B.affordable(1, equity, state.floor, existing, {1: trade["full_reserve"]}):
                    continue
            active[ident] = trade["full_reserve"]
            trades += 1
        assert not active
    return {"end": equity, "low": low, "trades": trades, "slices": slices, "floor": state.floor}


def table(streams: dict) -> dict:
    rows = {seq: {"NONE": simulate(seq, streams, "NONE")["end"], "CUSHION": simulate(seq, streams, "CUSHION")["end"], "WATCH": watch_path(seq, streams)} for seq in itertools.product(YEARS, repeat=4)}
    out = {}
    for rule in ("NONE", "CUSHION", "WATCH"):
        ends = sorted(r[rule]["end"] if rule == "WATCH" else r[rule] for r in rows.values())
        out[rule] = {"worst_end": round(ends[0]), "median_end": round((ends[127] + ends[128]) / 2), "best_end": round(ends[-1]), "below_start": sum(e < CAPITAL for e in ends)}
    ends_w = {s: r["WATCH"]["end"] for s, r in rows.items()}
    for other in ("NONE", "CUSHION"):
        diff = [ends_w[s] - rows[s][other] for s in rows]
        out[f"WATCH_vs_{other}"] = {"helps": sum(d > 0.01 for d in diff), "hurts": sum(d < -0.01 for d in diff), "same": sum(abs(d) <= 0.01 for d in diff), "largest_gain": round(max(diff)), "largest_cost": round(min(diff))}
    out["lowest_equity_with_watch"] = round(min(r["WATCH"]["low"] for r in rows.values()))
    out["most_slices"] = max(r["WATCH"]["slices"] for r in rows.values())
    named = {"2023,2024,2025,2026": ("2023", "2024", "2025", "2026"), "2023 twice,2024,2025": ("2023", "2023", "2024", "2025"), "2023 three times,2024": ("2023", "2023", "2023", "2024"), "2023 four times": ("2023",) * 4}
    out["named"] = {k: {"NONE": round(rows[v]["NONE"]), "CUSHION": round(rows[v]["CUSHION"]), "WATCH": round(rows[v]["WATCH"]["end"]), "slices": rows[v]["WATCH"]["slices"]} for k, v in named.items()}
    return out


def load_streams() -> dict:
    from fno_costs import calc_fno_costs
    n09 = HERE.parent / "2026-11-01-fno-n09" / "_local"
    out = {}
    for y in YEARS:
        key = json.loads((n09 / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        rows = json.loads((n09 / f"evals-{y}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
        out[y] = [{**t, "full_reserve": t["entry_premium"] * 65 + calc_fno_costs(t["entry_premium"], t["entry_premium"], 65) + 205.0} for t in rows]
    return out


def main() -> None:
    result = table(load_streams())
    (HERE / "stress-watch.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
