"""N09c analysis -> results.json: the frozen RULE (lab_x.RULE) applied per lot to NIFTY 2024, 2025 and Jan - Oct 2026.

Frozen with lab_x.py before any replay; never changed after a result is seen.
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
import analyze_g as AG  # noqa: E402  (per_lot)

YEARS = ("2024", "2025", "2026")
DATA_2024 = C.ROOT / "docs/research/fno/2026-10-30-day-router/_local/dataset-nifty-2024/manifest.json"
WINDOWS = {"2024": ("2024-01-01", "2024-12-31"), **C.WINDOWS}
HALVES = {"2024": (("2024-01-01", "2024-06-30"), ("2024-07-01", "2024-12-31")), **C.HALVES}
EXTRA_COST = 200          # Rs per trade per lot, the method's stress


def exit_reasons(trades: list) -> dict:
    out = {}
    for t in trades:
        out[t.get("exit_reason")] = out.get(t.get("exit_reason"), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main() -> None:
    sha = Y.grid._sha(HERE / "freeze.json")
    days = {"2024": json.loads(DATA_2024.read_text(encoding="utf-8"))["sessions"], **A.sessions()}
    trades = {}
    for y in YEARS:
        raw = json.loads((X.LOCAL / f"results-raw-{y}.json").read_text(encoding="utf-8"))
        assert raw["freeze_sha256"] == sha, "replays are not from this freeze"
        trades[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    halves = {f"{y}_{h}": (y, s) for y in YEARS for h, s in zip(("H1", "H2"), HALVES[y])}
    every_day = [d for y in YEARS for d in days[y]]
    m = {}
    for n in trades["2025"]:
        joined = [t for y in YEARS for t in trades[y][n]]
        row = {y: AG.per_lot(trades[y][n], WINDOWS[y], days[y]) for y in YEARS}
        row.update({k: AG.per_lot(trades[y][n], s, days[y]) for k, (y, s) in halves.items()})
        row["all"] = AG.per_lot(joined, (every_day[0], every_day[-1]), every_day)
        row["all"]["stressed"] = row["all"]["net"] - EXTRA_COST * row["all"]["trades"]
        row["exit_reasons"] = exit_reasons(joined)
        m[n] = row
    null = {y: statistics.median(m[f"NULL{i:02d}"][y]["net"] for i in range(X.NULL_BOOKS)) for y in YEARS}
    card, ref = m["CARD|shipped"], m["REF|shipped_book_exits"]
    checks = {
        "net_positive_each_year": all(card[y]["net"] > 0 for y in YEARS),
        "stressed_positive": card["all"]["stressed"] > 0,
        "positive_without_best_day": card["all"]["without_best_day"] > 0,
        "at_most_one_red_half": sum(card[k]["net"] < 0 for k in halves) <= 1,
        "forty_trades_a_year": all(card[y]["trades"] >= 40 for y in YEARS),
        "beats_random_median_each_year": all(card[y]["net"] > null[y] for y in YEARS),
    }
    verdict = {"card_passes": all(checks.values()), "checks": checks,
               "card_exits_beat_book_exits": all(card[y]["net"] > ref[y]["net"] for y in YEARS)}
    Y.write_new(HERE / "results.json", {"schema": "n09c_card_results_v1", "freeze_sha256": sha, "rule": X.RULE,
                                        "verdict": verdict, "random_median": null, "metrics_per_lot": m})
    print("verdict:", json.dumps(verdict), "| random books, median per lot:", null)
    for n in sorted((n for n in m if not n.startswith("NULL")), key=lambda n: -m[n]["all"]["net"]):
        b = m[n]["all"]
        print(f"{n:24} 2024 {m[n]['2024']['net']:8} | 2025 {m[n]['2025']['net']:8} | 2026 {m[n]['2026']['net']:8} | all "
              f"{b['net']:8} | +200 {b['stressed']:8} | w/o best {b['without_best_day']:8} | trades {b['trades']:4} | "
              f"worst day {b['worst_day']:6} | max DD {b['dd']:6} | months {b['green_months']}/{b['red_months']}")
        print(f"{'':24} halves " + " ".join(f"{k} {m[n][k]['net']}" for k in halves) + f" | exits {m[n]['exit_reasons']}")


if __name__ == "__main__":
    main()
