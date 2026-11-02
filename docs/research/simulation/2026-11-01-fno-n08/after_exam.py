"""After the 2023 result: controls that explain it. They change no verdict and no frozen book. Windows workers re-import this file.

    N08_YEAR=<year> python after_exam.py nobrake --jobs 5     # the same books with every brake off, so the 15% halt can't hide a difference
    N08_YEAR=<year> python after_exam.py random --jobs 5      # 20 random-entry books, one lot, brakes off: how hard was the year for any option buyer?
    N08_YEAR=<year> N08_CARRY=1 python after_exam.py carry    # one account across the years, brakes on (2023 first)
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n08_lab as N  # noqa: E402

Y, X, C, B, L = N.Y, N.X, N.C, N.B, N.B.L
YEAR = N.B.YEAR
CARRY = os.environ.get("N08_CARRY") == "1"
if CARRY:
    Y.EVALS = N.LOCAL / "evals-carry"      # the first opening's 2023 files share these keys, so the account has a folder of its own


def main_books() -> dict:
    refs = N.references()
    return {"N03": refs["NORMAL|BASE"], "N04": refs["NORMAL|STALL30"], "N05": refs["NORMAL|STRUCT30"], "N07": refs["NORMAL|PREMIUM_STALL"], "N08": N.n08_book()}


def nobrake_books() -> dict:
    out = {}
    for name, book in main_books().items():
        b = copy.deepcopy(book)
        b["cfg"] = {**b.get("cfg", {}), **L.BRAKES_OFF}
        b["label"] = f"AFTER|NOBRAKE|{name}"
        out[f"NOBRAKE|{name}"] = b
    return out


def random_books() -> dict:
    out = {}
    for i, b in enumerate(Y.null_fixed()):
        out[f"RANDOM|{i:02d}"] = B.W.X.book(f"AFTER|RANDOM|{i:02d}", members=[{**m, "gate": "ALWAYS"} for m in b["members"]], cfg=dict(B.W.S.RAW), cost=False)
    return out


def carry_books() -> dict:
    order = ["2023", "2024", "2025", "2026"]
    earlier = order[:order.index(YEAR)]
    out = {}
    for name, book in main_books().items():
        keys = []
        for y in earlier:
            saved = json.loads((N.LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8"))
            keys.append(saved[name])
        out[name] = {**book, "carry": keys} if keys else book
    return out


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("nobrake", "random", "carry"))
    cli.add_argument("--jobs", type=int, default=5)
    a = cli.parse_args()
    if a.action == "carry":
        assert CARRY
        Y.EVALS.mkdir(parents=True, exist_ok=True)
        books = carry_books()
        if YEAR == "2023":
            for book in books.values():      # the corrected 2023 replays, unchanged
                name = f"{Y.task_key(book, 'year', C.WINDOW)}.json"
                shutil.copy2(N.POINTS["2023"]["evals"] / name, Y.EVALS / name)
        else:
            N.run_books(books, a.jobs)
        X.write(N.LOCAL / f"keys-carry-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()})
    else:
        books = nobrake_books() if a.action == "nobrake" else random_books()
        N.run_books(books, a.jobs)
        X.write(N.LOCAL / f"keys-{a.action}-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()})
    print("DONE", a.action, YEAR, len(books), flush=True)


if __name__ == "__main__":
    main()
