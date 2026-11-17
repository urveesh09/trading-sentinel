"""SN482 exam replays (PLAN.md SN482): the house chain unchanged (N08 -> N09 -> N09.1 -> N10 -> N10b -> N101 -> N11), n08_lab loaded
through n08_shim2 with this slot's points, following sn366_exam.py's diag / exam modes line for line where they apply.

Set the environment (Windows workers re-import this file and inherit it):
  SN482_MODE=diag  N08_YEAR=2020|2021E   N09's diag books (N08 and its one-lot brakes-off paper twin) into _local/n09
  SN482_MODE=exam  N08_YEAR=2020|2021E   N11's panel books N11, R0.85 (Gold's DEPLOYED feed) and NO_STAND into
                                         _local/exam-evals-<point>; paper evidence = the DIAG paper trades of 2020 (for 2020) and
                                         2020 + 2021E (for 2021E), exits strictly before each decision (the house rule)
N09's volatility reading is repointed to the point's own daily file (SN366's SOURCE_CORRECTION_2022 trap).
Prints counts only; Gold scores the trades in sn482_gold.py.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
MODE = os.environ.get("SN482_MODE")
POINT = os.environ.get("N08_YEAR")
assert MODE in ("diag", "exam") and POINT in ("2020", "2021E"), (MODE, POINT)
sys.path.insert(0, str(HERE))
import n08_shim2  # noqa: E402

N = n08_shim2.install()
SIM = HERE.parents[1] / "simulation"
sys.path.insert(0, str(SIM / "2026-11-02-fno-n11"))
import n11_lab as L  # noqa: E402

U = L.U
Bb = U.B
T, M, Z, Y = Bb.T, Bb.M, Bb.Z, Bb.Y
N09_MINE = LOCAL / "n09"
PAPER_YEARS = {"2020": ("2020",), "2021E": ("2020", "2021E")}


def paper_rows_from(folder, years):
    rows = []
    for y in years:
        key = json.loads((folder / f"keys-diag-{y}.json").read_text())["DIAG"]
        for t in json.loads((folder / f"evals-{y}" / f"{key}.json").read_text())["trades"]:
            rows.append((datetime.fromisoformat(t["exit_time"]), t))
    return tuple(sorted(rows, key=lambda r: (r[0], r[1]["entry_time"], r[1]["tradingsymbol"])))


def install_evidence(folder, n11_years, watch_years):
    Z.LOCAL = folder
    cache = {}

    def paper_rows():
        if "p" not in cache:
            cache["p"] = paper_rows_from(folder, n11_years)
        return cache["p"]

    def shadow_names():
        return tuple(f"evals-{y}/{json.loads((folder / f'keys-diag-{y}.json').read_text(encoding='utf-8'))['DIAG']}.json" for y in watch_years)
    U.paper_rows = paper_rows
    Bb.shadow_names = shadow_names
    L.paper_stream.cache_clear()


if MODE == "diag":
    Z.LOCAL = N09_MINE
    Y.EVALS = N09_MINE / f"evals-{POINT}"
else:
    install_evidence(N09_MINE, PAPER_YEARS[POINT], (POINT,))
    Y.EVALS = LOCAL / f"exam-evals-{POINT}"
Y.EVALS.mkdir(parents=True, exist_ok=True)
Z.DAILY_SOURCES = (LOCAL / f"daily-{POINT}.json",)
Z.vol_table.cache_clear()


def key_of(b):
    return Y.task_key(b, "year", N.C.WINDOW)


def run(books, jobs=3):
    assert not any(Y.EVALS.glob("*.json")) or MODE == "diag", "must start from an empty results folder"
    N.run_books(books, jobs)
    return {n: key_of(b) for n, b in books.items()}


def diag():
    keys = run(Z.diag_books())
    (N09_MINE / f"keys-diag-{POINT}.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    print("DIAG", POINT, json.dumps({n: len(T.load(k, Y.EVALS)) for n, k in keys.items()}), flush=True)


def exam():
    out = LOCAL / f"keys-exam-{POINT}.json"
    assert not out.exists(), "the exam replays run once"
    pb = L.panel_books()
    keys = run({f"panel|{k}": pb[k] for k in ("N11", "R0.85", "NO_STAND")})
    out.write_text(json.dumps(keys, indent=1), encoding="utf-8")
    print("EXAM", POINT, json.dumps({n: len(T.load(k, Y.EVALS)) for n, k in keys.items()}), flush=True)


if __name__ == "__main__":
    {"diag": diag, "exam": exam}[MODE]()
