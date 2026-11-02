"""The overfitting estimate (Bailey et al.'s CSCV, weekly results, 16 blocks, 12,870 splits), from saved replays only, exact duplicates removed. Writes pbo.json.

Two panels: N11's own family, and everything since N08, with every N11 screen counted. Cost-stress runs aren't strategies, so they stay out.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026-11-01-fno-n10"
N09 = HERE.parent / "2026-11-01-fno-n09"
sys.path[:0] = [str(OLD), str(N09), str(HERE.parent / "2026-11-01-fno-n091")]
import score as S  # noqa: E402
from after_verdict import run  # noqa: E402
from analyze_panel import N08_LOCAL, all_weeks, keys, load, weekly  # noqa: E402

YEARS = S.YEARS
LOCAL = HERE / "_local"
N101 = HERE.parent / "2026-11-02-fno-n101" / "_local"
N091 = HERE.parent / "2026-11-01-fno-n091" / "_local"
PHASES = ("screen", "screen2", "screen3", "screen4", "screen5", "panel")
NOT_STRATEGIES = ("DOUBLE", "C_DOUBLE", "NOOP")


def own(name: str, phase: str) -> list:
    rows = []
    for y in YEARS:
        key = json.loads((LOCAL / f"keys-{phase}-{y}.json").read_text(encoding="utf-8"))[name]
        rows += json.loads((LOCAL / "evals" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
    return rows


def main() -> None:
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    series: dict = {}

    def add(name, trades):
        row = np.zeros(len(weeks))
        for w, v in weekly(trades).items():
            if w in index:
                row[index[w]] += v
        series[name] = row

    for phase in PHASES:
        for name in json.loads((LOCAL / f"keys-{phase}-2024.json").read_text(encoding="utf-8")):
            if name not in NOT_STRATEGIES:
                add(f"{phase}|{name}", own(name, phase))
    add("N08", [t for y in YEARS for t in S.n08_trades(y)])
    add("N09.1", [t for y in YEARS for t in S.n091_trades("primary", y, "CUSHION")])
    add("N10 retry", [t for y in YEARS for t in S.trades_of("panel2", y, "R2_THIRD_CW")])
    family = run(dict(series), "screen5|HONEST")
    round_one = [*("EARN_N", "EARN_W", "EARN_WV", "EARN_WC", "EARN_WVC", "LADDER_WC", "HYBRID_C"), *(f"{n}@{x}" for n in S.CUSHION_BOOKS for x in ("0.75", "1.25"))]
    for name in round_one:
        add(name, [t for y in YEARS for t in S.trades_of("panel", y, name)])
    for name in ("R2_THIRD_CW@0.75", "R2_THIRD_CW@1.25", "R2_CW"):
        add(name, [t for y in YEARS for t in S.trades_of("panel2", y, name)])
    add("STRICT", [t for y in YEARS for t in S.trades_of("strict-annual", y, "STRICT")])
    add("N09.1 VOL_CLOCK", [t for y in YEARS for t in S.n091_trades("primary", y, "VOL_CLOCK")])
    for name in ("PREMIUM_LOCK|200",):
        rows = []
        for y in YEARS:
            key = json.loads((N101 / f"keys-annual-{y}.json").read_text(encoding="utf-8"))[name]
            rows += json.loads((N101 / "evals" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
        add("N10.1 " + name, rows)
    k23 = keys("screens", "2023")
    screens = {}
    for y in ("2024", "2025", "2026"):
        merged = {}
        for phase in ("screen", "screen2", "screen3", "screen4"):
            merged.update(json.loads((N08_LOCAL / f"keys-{phase}-{y}.json").read_text(encoding="utf-8")))
        screens[y] = merged
    for name in sorted(k23):
        if "COST|" in name:
            continue
        rows = load("2023", k23[name])
        for y in ("2024", "2025", "2026"):
            rows = rows + load(y, screens[y][name], N08_LOCAL / "evals")
        add("SCREEN|" + name, rows)
    p = {y: keys("panel", y) for y in YEARS}
    for name in ("CASH|NO_E", "CASH|S_VOL"):
        add(name, [t for y in YEARS for t in load(y, p[y][name])])
    everything = run(series, "screen5|HONEST")
    out = {"n11_family": family, "everything_since_n08": everything, "check_17_family_at_most_0_5": family["pbo"] <= 0.5 if "pbo" in family else None,
           "reading": "On pure noise this estimator averages 0.51 to 0.55 with a standard deviation of about 0.18. All data seen, and each screen was designed after reading the last, so a low score isn't independent evidence."}
    (HERE / "pbo.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
