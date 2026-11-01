"""A correction, disclosed in SOURCE_CORRECTION.md. PLAN.md says the noise member exits only by its own trail, the premium backstop, its hard stop and the 15:10
close. The frozen code left the shipped profit lock on, and most of its trades left by that lock. This reruns the three noise books as the plan describes,
in new keys, and scores them by the same six gates. The first results stay in results-panel.json. The frozen n09_lab.py isn't edited.

    N08_YEAR=<year> python noise_correction.py run --jobs 4
    python noise_correction.py score
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")
NAMES = ("ONE|NOISE_TEXTBOOK", "ONE|NOISE_HOUSE", "ONE|N08+NOISE")


def patch():
    import os
    if "N08_YEAR" not in os.environ:
        return None
    import n09_lab as Z
    Z.ROUTER._POLICIES["NOISE"] = Z.replay.ReplayPolicy(
        name="N09_NOISE_NO_LOCK", manage_every_observation=True,
        exit_overrides=tuple(sorted({"FNO_TIME_STOP_MIN": 1e6, "FNO_TRAIL_ATR_MULT": 1000.0, "FNO_PROFIT_LOCK_ENABLED": False}.items())))
    return Z


Z = patch()      # at module level: pool workers re-import this file


def books() -> dict:
    out = {}
    for name in NAMES:
        b = dict(Z.one_books()[name])
        b["n09"] = {**b["n09"], "noise_exit": "plan"}
        b["label"] = b["label"] + "|NO_LOCK"
        out[name] = b
    return out


def score() -> None:
    from analyze_panel import all_weeks, keys, load, pairing, part_gates, show
    weeks = all_weeks()
    base = {y: load(y, keys("diag", y)["DIAG"]) for y in YEARS}
    out = {}
    for name in NAMES:
        book = {y: load(y, keys("noise", y)[name]) for y in YEARS}
        out[name] = part_gates(book, base, weeks)
        out[name]["pairing"] = pairing(book, base)
        show(name, out[name])
        flat = [t for y in YEARS for t in book[y]]
        extra = sum(t.get("extra_cost") or 0 for t in flat)
        out[name]["extra_cost"] = round(extra)
        out[name]["before_extra_cost"] = round(sum(t["net_pnl"] for t in flat) + extra)
        out[name]["exits"] = dict(Counter(t["exit_reason"] for t in flat).most_common(6))
        print("    trades", [out[name]["by_year"][y]["trades"] for y in YEARS], "wins", [out[name]["by_year"][y]["wins"] for y in YEARS], "falls", [out[name]["by_year"][y]["fall_pct"] for y in YEARS], "before extra cost", out[name]["before_extra_cost"], "exits", out[name]["exits"], flush=True)
    alone = out["ONE|NOISE_HOUSE"]["by_year"]["2023"]["net"]
    joins = out["ONE|N08+NOISE"]["passes"] and alone > 0
    print("noise would join under the frozen rule:", joins, "alone in 2023:", alone, flush=True)
    (HERE / "results-noise-correction.json").write_text(json.dumps({"books": out, "joins": joins}, indent=1), encoding="utf-8")


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    if a.action == "score":
        score()
    else:
        Z.run_year_books("noise", books(), a.jobs)


if __name__ == "__main__":
    main()
