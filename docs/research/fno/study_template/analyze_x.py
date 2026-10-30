"""TEMPLATE analysis -> results.json: the frozen RULE applied per lot to both NIFTY years (EDIT with the RULE).

Freeze this file with lab_x.py before any replay; never change it after seeing a result.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_x as X  # noqa: E402

C, Y = X.C, X.Y
sys.path.insert(0, str(C.ROOT / "docs/research/fno/2026-10-29-why-study"))
sys.path.insert(0, str(C.ROOT / "docs/research/fno/2026-10-30-case-study"))
import analyze_c as A  # noqa: E402  (sessions per year)
import analyze_g as AG  # noqa: E402  (per_lot, one_lot_weeks)

YEARS = ("2025", "2026")


def main() -> None:
    sha = Y.grid._sha(HERE / "freeze.json")
    days = A.sessions()
    trades = {}
    for y in YEARS:
        raw = json.loads((X.LOCAL / f"results-raw-{y}.json").read_text(encoding="utf-8"))
        assert raw["freeze_sha256"] == sha, "replays are not from this freeze"
        trades[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    halves = {f"{y}_{h}": (y, s) for y in YEARS for h, s in zip(("H1", "H2"), C.HALVES[y])}
    m = {}
    for n in trades["2025"]:
        row = {y: AG.per_lot(trades[y][n], C.WINDOWS[y], days[y]) for y in YEARS}
        row.update({k: AG.per_lot(trades[y][n], s, days[y]) for k, (y, s) in halves.items()})
        row["both"] = AG.per_lot(trades["2025"][n] + trades["2026"][n], A.BOTH, days["2025"] + days["2026"])
        row["weeks"] = AG.one_lot_weeks(trades["2025"][n] + trades["2026"][n], days["2025"] + days["2026"])
        m[n] = row
    null = {y: statistics.median(m[f"NULL{i:02d}"][y]["net"] for i in range(20)) for y in YEARS}
    alone, added, live = m["CAND|alone"], m["CAND|added_to_live"], m["REF|LIVE"]
    verdict = {
        "alone_helps": all(alone[y]["net"] > 0 and alone[y]["trades"] >= 40 and alone[y]["net"] > null[y]
                           for y in YEARS) and sum(alone[k]["net"] < 0 for k in halves) <= 1,
        "added_helps": all(added[y]["net"] > live[y]["net"] for y in YEARS)
        and sum(added[k]["net"] >= live[k]["net"] for k in halves) >= 3,
    }
    Y.write_new(HERE / "results.json", {"schema": "template_results_v1", "freeze_sha256": sha, "rule": X.RULE,
                                        "verdict": verdict, "random_median": null, "metrics_per_lot": m})
    print("verdict:", verdict, "| random books, median per lot:", null)
    for n in sorted((n for n in m if not n.startswith("NULL")), key=lambda n: -m[n]["both"]["net"]):
        b = m[n]["both"]
        print(f"{n:28} 2025 {m[n]['2025']['net']:8} | 2026 {m[n]['2026']['net']:8} | both {b['net']:8} | trades "
              f"{b['trades']:4} | worst day {b['worst_day']:6} | max DD {b['dd']:6} | months {b['green_months']}/"
              f"{b['red_months']} | weeks {m[n]['weeks']}")


if __name__ == "__main__":
    main()
