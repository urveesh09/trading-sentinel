"""After the verdict, from saved replays only: the overfitting estimate with exact duplicates removed, on round two's panel and on everything since N08. Changes no verdict. Writes pbo-after.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
N09 = HERE.parent / "2026-11-01-fno-n09"
sys.path[:0] = [str(HERE), str(N09), str(HERE.parent / "2026-11-01-fno-n091")]
import score as S  # noqa: E402
from analyze_panel import N08_LOCAL, all_weeks, cscv, keys, load, weekly  # noqa: E402

YEARS = S.YEARS


def unique(series: dict) -> dict:
    seen, out = {}, {}
    for name, row in series.items():
        key = row.round(2).tobytes()
        if key not in seen:
            seen[key] = name
            out[name] = row
    return out


def run(series: dict, watch: str) -> dict:
    series = unique(series)
    names = list(series)
    matrix = np.array([series[k] for k in names]).T
    out = cscv(matrix, blocks=16)
    picks = {names[int(k)]: v for k, v in sorted(out.pop("picks").items(), key=lambda kv: -kv[1])[:6]}
    totals = matrix.sum(axis=0)
    return {**out, "most_chosen": picks, "books_after_removing_duplicates": len(names), "rank_by_total": int((totals > totals[names.index(watch)]).sum()) + 1 if watch in names else None, "total": round(float(totals[names.index(watch)])) if watch in names else None}


def main() -> None:
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    series: dict = {}

    def add(name, trades):
        row = np.zeros(len(weeks))
        for w, v in weekly(trades).items():
            row[index[w]] += v
        series[name] = row

    round_one = [*("EARN_N", "EARN_W", "EARN_WV", "EARN_WC", "EARN_WVC", "LADDER_WC", "HYBRID_C"), *(f"{n}@{x}" for n in S.CUSHION_BOOKS for x in ("0.75", "1.25"))]
    for name in round_one:
        add(name, [t for y in YEARS for t in S.trades_of("panel", y, name)])
    for name in ("R2_THIRD_CW", "R2_THIRD_CW@0.75", "R2_THIRD_CW@1.25", "R2_CW"):
        add(name, [t for y in YEARS for t in S.trades_of("panel2", y, name)])
    add("STRICT", [t for y in YEARS for t in S.trades_of("strict-annual", y, "STRICT")])
    add("N08", [t for y in YEARS for t in S.n08_trades(y)])
    n10_only = run(dict(series), "R2_THIRD_CW")
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
    everything = run(series, "R2_THIRD_CW")
    out = {"n10_panel": n10_only, "everything_since_n08": everything, "reading": "On pure noise this estimator averages 0.51 to 0.55 with a standard deviation of about 0.18. All data seen; rounds were designed after reading earlier rounds, so a low score isn't independent evidence."}
    (HERE / "pbo-after.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
