"""O30c analysis -> results.json: each Tier 1 case against its base, per lot, in both years and all four half-years.

Written and frozen before any case replay.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_c as C  # noqa: E402

Y = C.Y
sys.path.insert(0, str(C.ROOT / "docs/research/fno/2026-10-29-why-study"))
import analyze_g as AG  # noqa: E402

YEARS = ("2025", "2026")
BOTH = ("2025-01-01", "2026-10-28")


def sessions() -> dict:
    return {"2025": json.loads((C.O30 / "freeze.json").read_text(encoding="utf-8"))["bindings"]["sessions"],
            "2026": json.loads((C.ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json").read_text(
                encoding="utf-8"))["bindings"]["year_sessions"]}


def load() -> tuple[dict, dict]:
    frozen_sha = Y.grid._sha(HERE / "freeze.json")
    trades = {}
    for y in YEARS:
        raw = json.loads((C.LOCAL / f"results-raw-{y}.json").read_text(encoding="utf-8"))
        assert raw["freeze_sha256"] == frozen_sha and raw["year"] == y
        trades[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    return trades, sessions()


def main() -> None:
    trades, days = load()
    names = list(trades["2025"])
    spans = {f"{y}_{h}": (y, span) for y in YEARS for h, span in zip(("H1", "H2"), C.HALVES[y])}
    m = {}
    for n in names:
        row = {y: AG.per_lot(trades[y][n], C.WINDOWS[y], days[y]) for y in YEARS}
        row.update({k: AG.per_lot(trades[y][n], span, days[y]) for k, (y, span) in spans.items()})
        row["both"] = AG.per_lot(trades["2025"][n] + trades["2026"][n], BOTH, days["2025"] + days["2026"])
        m[n] = row
    weeks = {n: AG.one_lot_weeks(trades["2025"][n] + trades["2026"][n], days["2025"] + days["2026"])
             for n in names if not n.startswith("NULL")}

    cases = {}
    for n in names:
        if n.startswith(("NULL", "BASE")):
            continue
        base = C.base_of(n)
        delta = {y: m[n][y]["net"] - m[base][y]["net"] for y in YEARS}
        halves_ok = sum(m[n][k]["net"] >= m[base][k]["net"] for k in spans)
        trades_ok = all(m[n][y]["trades"] >= 40 for y in YEARS)
        cases[n] = {"base": base, "delta": delta, "halves_not_worse": halves_ok, "trades_ok": trades_ok,
                    "helps": delta["2025"] > 0 and delta["2026"] > 0 and halves_ok >= 3 and trades_ok,
                    "vs_UNION_ADX": {y: m[n][y]["net"] - m["BASE|UNION_ADX"][y]["net"] for y in YEARS}}

    luck = {}
    for y in YEARS:
        diffs = [m[f"NULL{i:02d}|dir_dmi"][y]["net"] - m[f"NULL{i:02d}|ALWAYS"][y]["net"] for i in range(20)]
        luck[y] = {"median_change": round(statistics.median(diffs)), "improved": sum(d > 0 for d in diffs),
                   "median_with_dmi": round(statistics.median(m[f"NULL{i:02d}|dir_dmi"][y]["net"] for i in range(20))),
                   "median_without": round(statistics.median(m[f"NULL{i:02d}|ALWAYS"][y]["net"] for i in range(20)))}

    out = {"schema": "o30c_results_v1", "freeze_sha256": Y.grid._sha(HERE / "freeze.json"), "rule": C.RULE,
           "metrics_per_lot": m, "cases": cases, "random_books_dmi": luck, "one_lot_weeks_both": weeks}
    Y.write_new(HERE / "results.json", out)

    print(f"{'book (per lot)':42} {'2025':>7} {'2026':>7} {'both':>7} {'t25':>4} {'t26':>4} {'worst':>6} {'dd':>6} "
          f"{'mo g/r':>6}  {'d25':>7} {'d26':>7} halves helps")
    for n in sorted((n for n in names if not n.startswith("NULL")), key=lambda n: -m[n]["both"]["net"]):
        b, c = m[n]["both"], cases.get(n)
        tail = (f"{c['delta']['2025']:7} {c['delta']['2026']:7} {c['halves_not_worse']}/4 {c['helps']}" if c else "base")
        print(f"{n:42} {m[n]['2025']['net']:7} {m[n]['2026']['net']:7} {b['net']:7} {m[n]['2025']['trades']:4} "
              f"{m[n]['2026']['trades']:4} {b['worst_day']:6} {b['dd']:6} {b['green_months']:2}/{b['red_months']:<2}  {tail}")
    print("random books with the dmi direction case:", luck)
    print("one-lot weeks (both years, from Rs 15,000):")
    for n in sorted(weeks, key=lambda n: -m[n]["both"]["net"])[:8]:
        print(f"  {n:42} {weeks[n]}")


if __name__ == "__main__":
    main()
