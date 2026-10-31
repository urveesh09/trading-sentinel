"""O30m after the verdict (descriptive): do the library's winners of one year win the next? -> persistence.json

Written after the cross-year check failed, to explain it; it selects nothing. For each library strategy, its per-lot
net in 2025 and 2026 (always on, and inside each kind of day of P2), the rank correlation between the years, and how
often a strategy is positive in both years against the random-entry books.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_m as AM  # noqa: E402

M, Y, AG = AM.M, AM.Y, AM.AG


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    for r, i in enumerate(order):
        out[i] = float(r)
    return out


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return round(cov / (va * vb) ** 0.5, 3)


def main() -> None:
    lib = AM.load("library")
    days = AM.A.sessions()
    sl = AM.Slices(lib, days)
    net = {n: {y: AG.per_lot(lib[y][n], M.C.WINDOWS[y], days[y])["net"] for y in AM.YEARS} for n in lib["2025"]}
    real = [n for n in net if not n.startswith(("NULL", "REF"))]
    nulls = [n for n in net if n.startswith("NULL")]
    both = sorted((n for n in real if net[n]["2025"] > 0 and net[n]["2026"] > 0), key=lambda n: -min(net[n].values()))
    out = {"always_on": {"rank_correlation_2025_vs_2026": spearman([net[n]["2025"] for n in real],
                                                                    [net[n]["2026"] for n in real]),
                         "strategies": len(real), "positive_both_years": len(both),
                         "random_books_positive_both_years": sum(net[n]["2025"] > 0 and net[n]["2026"] > 0
                                                                 for n in nulls),
                         "random_books": len(nulls),
                         "positive_both_list": {n: net[n] for n in both},
                         "top10_2025_in_2026": {n: net[n] for n in sorted(real, key=lambda n: -net[n]["2025"])[:10]},
                         "top10_2026_in_2025": {n: net[n] for n in sorted(real, key=lambda n: -net[n]["2026"])[:10]}}}
    features = M.PARTITIONS["P2_trend_dir"]
    cells = {}
    for cell in AM.cells_of(features):
        a = [sl.value(n, "any", "2025", M.C.WINDOWS["2025"], features, cell)[0] for n in real]
        b = [sl.value(n, "any", "2026", M.C.WINDOWS["2026"], features, cell)[0] for n in real]
        cells["|".join(cell)] = {"rank_correlation": spearman(a, b), "positive_both": sum(x > 0 and y > 0 for x, y in
                                                                                            zip(a, b))}
    out["P2_kinds_of_day"] = cells
    Y.write_new(HERE / "persistence.json", out)
    s = out["always_on"]
    print("always on: rank correlation 2025 vs 2026 =", s["rank_correlation_2025_vs_2026"], "| positive both years:",
          s["positive_both_years"], "of", s["strategies"], "| random books positive both:",
          s["random_books_positive_both_years"], "of", s["random_books"])
    print("positive in both years:", json.dumps(s["positive_both_list"]))
    print("2025's top 10 -> 2026:", json.dumps(s["top10_2025_in_2026"]))
    print("2026's top 10 -> 2025:", json.dumps(s["top10_2026_in_2025"]))
    print("inside each kind of day (P2):", cells)


if __name__ == "__main__":
    main()
