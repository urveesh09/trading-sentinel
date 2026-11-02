"""After the verdict, from saved replays only. Changes no verdict and no book. Writes after-verdict.json.

1. Hide each year in turn: would each part still have been chosen on the other three, and what did it then do on the hidden year?
2. Is the family's overfitting score of 0.893 a plateau effect? The same 71 books with the weeks shuffled jointly, which destroys time and keeps the plateau.
3. Head to head over the same 12,870 splits: how often does N11 beat N10 retry on the half it wasn't chosen on?
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026-11-01-fno-n10"
N09 = HERE.parent / "2026-11-01-fno-n09"
sys.path[:0] = [str(HERE), str(N09)]
import screen_view as V  # noqa: E402
from analyze_panel import all_weeks, cscv, weekly  # noqa: E402

LOCAL = HERE / "_local"
YEARS = V.YEARS
PHASES = ("screen", "screen2", "screen3", "screen4", "screen5", "panel")
NOT_STRATEGIES = ("DOUBLE", "C_DOUBLE", "NOOP")


def rows_of(phase: str, name: str) -> list:
    return [t for y in YEARS for t in V.load(LOCAL, phase, y, name)["trades"]]


def hidden_year() -> dict:
    results = json.loads((HERE / "overfit.json").read_text(encoding="utf-8"))["parts_by_year"]["what_each_part_adds"]
    out = {}
    for part, by in results.items():
        out[part] = {}
        for y in YEARS:
            seen = sum(v for k, v in by.items() if k != y)
            out[part][y] = {"sum_on_the_other_three": seen, "would_be_chosen": seen > 0, "on_the_hidden_year": by[y], "result_if_followed": by[y] if seen > 0 else 0}
        out[part]["four_years_if_followed"] = sum(out[part][y]["result_if_followed"] for y in YEARS)
        out[part]["four_years_as_built"] = sum(by.values())
    return out


def family_matrix() -> tuple:
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    seen, names, columns = set(), [], []
    for phase in PHASES:
        for name in json.loads((LOCAL / f"keys-{phase}-2024.json").read_text(encoding="utf-8")):
            if name in NOT_STRATEGIES:
                continue
            row = np.zeros(len(weeks))
            for w, v in weekly(rows_of(phase, name)).items():
                if w in index:
                    row[index[w]] += v
            key = row.round(2).tobytes()
            if key not in seen:
                seen.add(key)
                names.append(f"{phase}|{name}")
                columns.append(row)
    return names, np.array(columns).T, weeks


def plateau_test(matrix: np.ndarray, draws: int = 20) -> dict:
    rng = np.random.default_rng(23)
    actual = cscv(matrix, blocks=16)["pbo"]
    shuffled = [cscv(matrix[rng.permutation(matrix.shape[0])], blocks=16)["pbo"] for _ in range(draws)]
    totals = matrix.sum(axis=0)
    return {"actual": round(actual, 3), "weeks_shuffled_jointly": {"draws": draws, "median": round(float(np.median(shuffled)), 3), "low": round(min(shuffled), 3), "high": round(max(shuffled), 3)},
            "family_totals": {"lowest": round(float(totals.min())), "median": round(float(np.median(totals))), "highest": round(float(totals.max()))},
            "reading": "If the shuffled score stays near the actual one, time order isn't what produces it: in a family with close totals, whatever does best on one half must do worse on the other. The check still failed as written."}


def head_to_head(weeks: list) -> dict:
    index = {w: i for i, w in enumerate(weeks)}

    def vector(rows):
        v = np.zeros(len(weeks))
        for w, x in weekly(rows).items():
            if w in index:
                v[index[w]] += x
        return v

    a = vector(rows_of("panel", "N11"))
    out = {}
    for label, other in (("N10 retry", rows_of("controls", "N10")), ("N08", rows_of("controls", "N08"))):
        d = a - vector(other)
        blocks = np.array_split(d, 16)
        wins = total = 0
        for half in itertools.combinations(range(16), 8):
            rest = [i for i in range(16) if i not in half]
            total += 1
            wins += sum(blocks[i].sum() for i in rest) > 0
        sums = [round(float(b.sum())) for b in blocks]
        out[label] = {"splits": total, "share_where_n11_wins_the_other_half": round(wins / total, 3), "blocks_better": sum(s > 0 for s in sums), "blocks_worse": sum(s < 0 for s in sums), "blocks_same": sum(s == 0 for s in sums), "block_differences": sums}
    return out


def main() -> None:
    names, matrix, weeks = family_matrix()
    assert "screen5|HONEST" in names
    totals = matrix.sum(axis=0)
    out = {"note": "Added after the verdict. All data seen.", "hidden_year": hidden_year(), "plateau": plateau_test(matrix), "head_to_head": head_to_head(weeks),
           "n11_rank_in_its_family": {"name_after_removing_duplicates": "screen5|HONEST", "rank": int((totals > totals[names.index("screen5|HONEST")]).sum()) + 1, "of": len(names)}}
    (HERE / "after-verdict.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
