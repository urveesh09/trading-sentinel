"""O30r sheet for the one-time NIFTY 2024 exam. Research only; frozen before any 2024 data exists.

A THIRD, separate sheet: the O30f and O30s sheets are not changed and are scored first. It asks one thing: does the risk
level chosen on 2025 and 2026 survive a year it never saw? Every book carries the O30r extra cost inside its money path.

After the O30f steps have sealed the 2024 data (FNO_YEAR_DATA_TESTING_METHOD.md section 14):

    python ../run_slice.py --env O30F_YEAR=2024 -- <folder>/exam_r.py run --jobs 3      # repeat until DONE
    python exam_r.py score                                                              # once

If the engine has changed by then, run from a worktree at this file's freeze commit.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-10-30-day-router")]
import lab_f as F24  # noqa: E402  (with O30F_YEAR=2024 this points the machinery at the sealed 2024 data)
import analyze_r as A  # noqa: E402
import lab_r as L  # noqa: E402

C, Y, ROOT = L.C, L.Y, L.ROOT
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals-2024"
WINDOW = F24.WINDOW24
PICK = "TPB+rule|R2|OFF|COST"
BOOKS = (PICK, "TPB+rule|SHIPPED|COST", "TPB+rule|R5|OFF|COST", "BEST+rule|R2|SCALED|COST", "LIVE+rule|R2|SCALED|COST",
         "LIVE+rule|SHIPPED|COST", "LIVE|SHIPPED|COST")
RULE = {
    "once": "NIFTY 2024 is scored once with these books and rules unchanged; nothing is tuned on it; the O30f and O30s "
            "sheets are scored first and independently",
    "pick": f"{PICK} holds if, over 2024 from Rs 2.5 lakh with the extra cost in the path: net > 0, largest fall <= 25% of "
            "the running peak, at least 40 trades, and net above LIVE|SHIPPED|COST (today's book)",
    "level": "the level is confirmed if R2 ends above the most-money level of 2025-26 (R5) per unit of fall, that is "
             "net / fall in rupees is higher at R2 than at R5, on 2024",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


def books() -> dict:
    all_books = L.year_books()
    return {n: all_books[n] for n in BOOKS}


def verdict(trades: dict) -> dict:
    """trades: book name -> stored trades of 2024."""
    s = {n: A.path(t) for n, t in trades.items()}
    pick, today, most = s[PICK], s["LIVE|SHIPPED|COST"], s["TPB+rule|R5|OFF|COST"]

    def per_fall(x: dict) -> float:
        return x["net"] / x["fall_rs"] if x["fall_rs"] > 0 else 0.0

    return {"pick_holds": pick["net"] > 0 and pick["fall_pct"] <= A.MAX_FALL and pick["trades"] >= 40 and pick["net"] > today["net"],
            "level_confirmed": per_fall(pick) > per_fall(most),
            "books": {n: A.pub(x) for n, x in s.items()}}


def freeze() -> None:
    sources = {p.relative_to(ROOT).as_posix(): Y.grid._sha(p) for p in
               [*sorted((ROOT / "python-engine").glob("*.py")), HERE / "lab_r.py", HERE / "analyze_r.py", HERE / "exam_r.py",
                HERE / "test_exam_r.py"]}
    Y.write_new(HERE / "freeze-2024.json", {"schema": "o30r_nifty_2024_v1", "rule": RULE, "sources": sources, "books": books(),
                                            "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(BOOKS), "books for the 2024 sheet")


def _committed() -> dict:
    frozen = json.loads((HERE / "freeze-2024.json").read_text(encoding="utf-8"))
    rel = (HERE / "freeze-2024.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    changed = [k for k, v in frozen["sources"].items() if Y.grid._sha(ROOT / k) != v]
    assert not changed, f"files changed since this freeze (run from a worktree at its commit): {changed}"
    return frozen


def run(jobs: int) -> None:
    assert F24.YEAR == "2024", "set O30F_YEAR=2024"
    assert F24.DATASET24.is_dir(), "the 2024 data is not sealed yet: follow FNO_YEAR_DATA_TESTING_METHOD.md section 14"
    frozen = _committed()
    assert {n: Y.digest(b) for n, b in frozen["books"].items()} == {n: Y.digest(b) for n, b in books().items()}
    L.O27F.deny_network()
    C.table("year")
    with ProcessPoolExecutor(max_workers=jobs, initializer=L._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(books().values()), source="year", window=WINDOW)
    L._atomic(LOCAL / "results-2024.json", {"books": {n: Y.task_key(b, "year", WINDOW) for n, b in books().items()},
                                            "trades": runner.trades})
    print("DONE 2024", len(BOOKS), flush=True)


def score() -> None:
    frozen = _committed()
    raw = json.loads((LOCAL / "results-2024.json").read_text(encoding="utf-8"))
    assert set(raw["books"]) == set(frozen["books"]), "a frozen book has no 2024 replay"
    out = {"schema": "o30r_results_2024_v1", "rule": frozen["rule"],
           "verdict": verdict({n: raw["trades"][k] for n, k in raw["books"].items()}),
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    with (HERE / "results-2024.json").open("x", encoding="utf-8", newline="\n") as f:      # written once
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out["verdict"].items() if k != "books"}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run", "score"])
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(a.jobs), "score": score}[a.action]()
