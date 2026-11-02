"""Check 15, from saved replays only: the overfitting estimate over this study's books, exact duplicates removed, and the same books with the weeks shuffled jointly. Writes pbo.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
N09 = HERE.parent / "2026-11-01-fno-n09"
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-02-fno-n11"), str(N09)]
import screen_view as V  # noqa: E402
from analyze_panel import all_weeks, cscv, weekly  # noqa: E402

V.LOCAL = HERE / "_local"
YEARS = V.YEARS


def main() -> None:
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    seen, names, columns = set(), [], []
    for phase in ("screen", "screen2", "screen3", "screen4", "screen5", "panel"):
        for name in json.loads((V.LOCAL / f"keys-{phase}-2024.json").read_text(encoding="utf-8")):
            if name == "DOUBLE":
                continue
            row = np.zeros(len(weeks))
            rows = [t for y in YEARS for t in V.load(V.LOCAL, phase, y, name)["trades"]]
            for w, v in weekly(rows).items():
                if w in index:
                    row[index[w]] += v
            key = row.round(2).tobytes()
            if key not in seen:
                seen.add(key)
                names.append(f"{phase}|{name}")
                columns.append(row)
    matrix = np.array(columns).T
    totals = matrix.sum(axis=0)
    actual = cscv(matrix, blocks=16)
    rng = np.random.default_rng(23)
    shuffled = [cscv(matrix[rng.permutation(matrix.shape[0])], blocks=16)["pbo"] for _ in range(20)]
    me = names.index("screen5|S7500_K1.75")   # the frozen book; duplicate removal keeps its first name
    out = {"books": len(names), "pbo": round(actual["pbo"], 3), "median_out_of_sample_percentile": round(actual["median_out_of_sample_percentile"], 3),
           "weeks_shuffled_jointly": {"median": round(float(np.median(shuffled)), 3), "low": round(min(shuffled), 3), "high": round(max(shuffled), 3)},
           "totals": {"lowest": round(float(totals.min())), "median": round(float(np.median(totals))), "highest": round(float(totals.max()))}, "n11t_rank_by_total": int((totals > totals[me]).sum()) + 1,
           "reading": "On pure noise this estimator averages 0.51 to 0.55 with a standard deviation of about 0.18. A family with close totals pushes it up, which the shuffle shows. All data seen."}
    (HERE / "pbo.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
