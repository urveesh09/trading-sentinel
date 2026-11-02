"""N11T final: the amount the owner left to the agent, on the plan's wording. PLAN_FINAL.md says why Rs 6,250 at k 1.75. The first freeze's files aren't edited.

    N08_YEAR=<year> python driver_final.py fpanel --jobs 3
    N08_YEAR=<year> python driver_final.py fcarry --jobs 3      (years in order: each carries the last)
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n11t_strict as S  # noqa: E402  (its import patches the second lot and the entry)

Q, L, T, Y, Z, X, B = S.Q, S.L, S.T, S.Y, S.Z, S.X, S.B
YEAR, YEARS, LOCAL = Q.YEAR, Q.YEARS, Q.LOCAL
LIMIT, K = 6250.0, 1.75
FREEZE = HERE / "freeze-final.json"
SOURCES = ("n11t_final.py", "PLAN_FINAL.md", "driver_final.py", "test_n11t_final.py")


def book(label: str, when: tuple = Q.VE, k: float = K, limit: float = LIMIT) -> dict:
    out = copy.deepcopy(Q.n11t_book(f"F|{label}", when=when, k=k, limit=limit))
    out["n11t"]["strict"] = True
    return out


def fpanel_books() -> dict:
    double = book("DOUBLE")
    double["cost"] = [400.0, 10.0]
    return {"FINAL": book("FINAL"), "N11": L.n11_book("T|BASE"), "K1.5": book("K1.5", k=1.5), "K2.0": book("K2.0", k=2.0), "L5500": book("L5500", limit=5500.0), "L7000": book("L7000", limit=7000.0),
            "NO_READING": book("NO_READING", when=("VOL",)), "REVERSED": book("REVERSED", when=("VOL", "EV_NOT")), "DOUBLE": double}


def fcarry_books() -> dict:
    earlier = YEARS[:YEARS.index(YEAR)]
    out = {}
    for tag, cost in L.COSTS.items():
        b = book("FINAL")
        b["cost"] = cost
        b["label"] = f"N091|CARRY|N11TF|{tag}"
        if earlier:
            saved = [json.loads((LOCAL / f"keys-fcarry-{y}.json").read_text(encoding="utf-8"))[tag] for y in earlier]
            b["carry"] = saved
            b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        out[tag] = b
    return out


PHASES = {"fpanel": fpanel_books, "fcarry": fcarry_books}


def freeze() -> None:
    assert not FREEZE.exists(), "already frozen"
    X.write(FREEZE, {"schema": "n11t_final_freeze_v1", "sources": {s: T.sha(HERE / s) for s in SOURCES}, "books": {"fpanel": fpanel_books()}, "limit": LIMIT, "k": K,
                     "note": "Written after the first freeze's run and its map were read, before this book's run. Discipline, not an exam."})


def require_freeze() -> None:
    assert json.loads(T.committed(FREEZE)) == json.loads(FREEZE.read_text(encoding="utf-8")), "freeze-final.json is not committed"
    for name, value in json.loads(FREEZE.read_text(encoding="utf-8"))["sources"].items():
        assert T.sha(HERE / name) == value, f"{name} changed after the freeze"


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("phase", choices=(*PHASES, "freeze"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    assert 1 <= a.jobs <= 4, "Production comes first"
    if a.phase == "freeze":
        freeze()
        print("FROZEN", flush=True)
        return
    require_freeze()
    books = PHASES[a.phase]()
    Z.N.run_books(books, a.jobs)
    X.write(LOCAL / f"keys-{a.phase}-{YEAR}.json", {n: Y.task_key(b, "year", B.C.WINDOW) for n, b in books.items()})
    print("DONE", a.phase, YEAR, len(books), flush=True)
