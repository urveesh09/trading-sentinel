"""O30f scoring of the one-time NIFTY 2024 exam -> results-2024.json, by RULE_2024 in freeze-2024.json.

Written and committed on Oct 30, 2026, before any 2024 data existed. Run once, after
`O30F_YEAR=2024 lab_f.py run` has finished; never change a book or a rule after seeing its output.
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0] / "2026-10-29-why-study"))
import analyze_g as AG  # noqa: E402

WINDOW = ("2024-01-01", "2024-12-31")
HALVES = {"H1": ("2024-01-01", "2024-06-30"), "H2": ("2024-07-01", "2024-12-31")}


def main() -> None:
    frozen = json.loads((HERE / "freeze-2024.json").read_text(encoding="utf-8"))
    files = sorted(glob.glob(str(HERE / "_local" / "results-raw-2024test-2024-*.json")))
    if not files:
        raise SystemExit("no 2024 replays yet: run O30F_YEAR=2024 lab_f.py run first")
    raw = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    days = json.loads((HERE / "_local/dataset-nifty-2024/manifest.json").read_text(encoding="utf-8"))["sessions"]
    trades = {n: raw["trades"][k] for n, k in raw["books"].items()}
    missing = sorted(set(frozen["books"]) - set(trades))
    assert not missing, f"frozen books without a 2024 replay: {missing}"
    m = {n: {"year": AG.per_lot(t, WINDOW, days), **{h: AG.per_lot(t, s, days) for h, s in HALVES.items()},
             "weeks": AG.one_lot_weeks(t, days)} for n, t in trades.items()}
    net = {n: m[n]["year"]["net"] for n in m}
    live, cand = "REF|LIVE", "REF|LIVE+tpb_all_days"
    alone = [f"ALONE|{n}" for n in frozen["positive_both"]]
    others = [n for n in trades if not n.startswith(("NULL", "REF", "ALONE", "ROUTER", "ROBUST", "UNION_DRIVE"))
              and n not in frozen["positive_both"]]
    verdict = {
        "candidate_confirmed": net[cand] > net[live] and all(m[cand][h]["net"] >= m[live][h]["net"] for h in HALVES),
        "robust_core_candidate": net["ROBUST_CORE"] > 0 and net["ROBUST_CORE"] > net[live],
        "positive_both_carries": sum(net[n] > 0 for n in alone) >= 9 and
        statistics.median(net[n] for n in alone) > statistics.median(net[n] for n in others),
        "positive_both_count": f"{sum(net[n] > 0 for n in alone)} of {len(alone)}",
        "medians": {"positive_both": round(statistics.median(net[n] for n in alone)),
                    "other_library": round(statistics.median(net[n] for n in others)), "others": len(others)},
        "random_books_median": round(statistics.median(net[n] for n in trades if n.startswith("NULL"))),
    }
    out = {"schema": "o30f_results_2024_v1", "rule": frozen["rule"], "verdict": verdict,
           "metrics_per_lot": {n: m[n] for n in frozen["books"]},
           "library_net": {n: net[n] for n in trades if n not in frozen["books"]}}
    target = HERE / "results-2024.json"
    with target.open("x", encoding="utf-8", newline="\n") as f:     # written once
        json.dump(out, f, indent=1, default=str)
    print("verdict:", json.dumps(verdict))
    for n in frozen["books"]:
        y = m[n]["year"]
        print(f"{n:45} 2024 {y['net']:8} (H1 {m[n]['H1']['net']:7}, H2 {m[n]['H2']['net']:7}) trades {y['trades']:4} "
              f"worst {y['worst_day']:6} dd {y['dd']:6} weeks {m[n]['weeks']}")


if __name__ == "__main__":
    main()
