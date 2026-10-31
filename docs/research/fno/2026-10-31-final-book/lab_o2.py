"""O31c - is the final book on a plateau or a lucky spike? Research only. No runtime module imports this file.

FOUND BY LOOKING at O31b's results (results.json, committed before this was written):
  * no change improved BASE; choosing among changes lost on every held-out year;
  * the stretched-entry rule at its limit 0.5 makes +51,919 over the three years, but limits 0.25 and 0.75 make -9,007 and
    -15,264, and no rule makes -10,733. A real effect should not depend on the exact limit, so it may be a spike. It may also
    be the brakes: with two-strike and size cuts, one changed trade changes which trades follow;
  * ADX >= 30 makes the same money as ADX >= 25 (+52,621) with much smaller falls, on 25 to 50 trades a year.

Three questions, all fixed here before any of these replays:
  SURFACE: the four strategies, one lot, brakes off (so one changed trade cannot change the rest), ADX level x rule limit, all
           three years, per lot after Rs 200 a trade. Does either setting sit on a plateau?
  EXACT:   at today's limits with the cost in the path: ADX 27, 28, 32, 35 and rule limits 0.35, 0.65; ADX 30 without the extra
           cost, and ADX 30 as one continuous account.
  RANDOM:  20 random-entry books, one lot, brakes off, with the rule, at ADX 25 and at ADX 30. Is a strict filter a skill of
           these strategies, or does it lift any entry?

    python lab_o2.py freeze                                                  # commit and push freeze-c.json alone
    python ../run_slice.py --env O30F_YEAR=2024 -- <folder>/lab_o2.py run --jobs 6    # repeat until DONE, then 2025, 2026
    python analyze_o2.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_o as X  # noqa: E402

L, T, S, C, Y, G, F, O27F = X.L, X.T, X.S, X.C, X.Y, X.G, X.F, X.O27F
YEAR, LOCAL, ROOT = X.YEAR, X.LOCAL, X.ROOT
Y.EVALS = LOCAL / "evals"
ADX_SURFACE = (20, 25, 27, 30, 32, 35)
SKIP_SURFACE = (None, 0.25, 0.35, 0.5, 0.65, 0.75)
ADX_EXACT = (27, 28, 32, 35)
SKIP_EXACT = (0.35, 0.65)
RANDOM_ADX = (25, 30)
NEW_SIDES = (27, 28, 32, 35)
_prev_table = C.table
_done: set = set()


def adx_sides(rows: dict, adx) -> None:
    import pandas as pd
    for day, row in rows.items():
        prior = adx.index[adx.index < pd.Timestamp(day)]
        for level in NEW_SIDES:
            row.setdefault("side", {})[f"adx_abs{level}"] = (None if len(prior) < 60 else
                                                             ("HIGH" if float(adx.loc[prior[-1]]) >= level else "LOW"))


def table(source: str) -> dict:
    rows = _prev_table(source)
    if source not in _done:
        adx_sides(rows, F.adx(F.daily_bars()))
        _done.add(source)
    return rows


C.table = table
Y.table = table


def skip_name(s) -> str:
    return "none" if s is None else f"{int(s * 100)}"


def books() -> dict:
    out = {}
    for a in ADX_SURFACE:
        for s in SKIP_SURFACE:
            name = f"SURFACE|A{a}|S{skip_name(s)}"
            out[name] = X.book(name, members=X.gated(f"adx_abs{a}:HIGH"), cfg=dict(S.RAW), skip=s, cost=False)
    for a in ADX_EXACT:
        out[f"EXACT|A{a}"] = X.book(f"EXACT|A{a}", members=X.gated(f"adx_abs{a}:HIGH"))
    for s in SKIP_EXACT:
        out[f"EXACT|S{skip_name(s)}"] = X.book(f"EXACT|S{skip_name(s)}", skip=s)
    out["EXACT|A30|AS"] = X.book("EXACT|A30|AS", members=X.gated("adx_abs30:HIGH"), cost=False)
    for i, b in enumerate(Y.null_fixed()):
        for a in RANDOM_ADX:
            name = f"RANDOM|{i:02d}|A{a}"
            out[name] = X.book(name, members=[{**m, "gate": f"adx_abs{a}:HIGH"} for m in b["members"]], cfg=dict(S.RAW), cost=False)
    return out


RULE = {
    "status": "Found by looking at O31b on three seen years. Nothing here can be proof, and it is decided by the rules below, "
              "fixed before these replays",
    "rule_plateau": "The rule is on a plateau if, on the surface at ADX 25, per lot after Rs 200 a trade over the three years, "
                    "limits 0.35, 0.5 and 0.65 ALL beat no rule. If not, it is fragile: it stays off the real-money test and "
                    "goes to paper only, whatever the 2024 exam said",
    "adx_plateau": "ADX 30 is on a plateau if, at today's limits with the cost in the path, ADX 28, 30 and 32 are each positive in "
                   "all three years, and on the surface (limit 0.5, after Rs 200) ADX 27, 30 and 32 each beat ADX 25 on the "
                   "three-year fall. If so, ADX 30 is recommended as the consistency setting",
    "random": "The strict filter is reported as a market effect, not a skill, if the 20 random books gain as much from ADX 30 as "
              "the four strategies do. Either way it can still reduce losses. Random books are one lot, brakes off",
    "final": "If the rule is on a plateau and ADX 30 is: four strategies + rule + ADX 30 at today's limits. If only the rule: four "
             "strategies + rule + ADX 25. If only ADX 30: four strategies + ADX 30, rule on paper. If neither: the book as live today",
    "no_change": "Nothing in the system changes on this result; the owner decides.",
}


def sources() -> dict:
    return {p.relative_to(ROOT).as_posix(): Y.grid._sha(p) for p in
            [*sorted((ROOT / "python-engine").glob("*.py")), HERE / "lab_o.py", HERE / "lab_o2.py", HERE / "analyze_o2.py", HERE / "test_lab_o2.py"]}


def freeze() -> None:
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    Y.write_new(HERE / "freeze-c.json", {"schema": "o31c_plateau_v1", "books": json.loads(json.dumps(books())), "rule": RULE,
                                         "after_results_sha256": Y.grid._sha(HERE / "results.json"), "base": results["base"]["2024"]["net"],
                                         "sources": sources(), "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "books per year")


def carried(all_books: dict) -> dict:
    if YEAR == "2024":
        return {}
    keys = json.loads((LOCAL / "keys-2024.json").read_text(encoding="utf-8"))
    first = {"BASE30": keys["ADX|30"], "BASE30|AS": json.loads((LOCAL / "keys-c-2024.json").read_text(encoding="utf-8"))["EXACT|A30|AS"]}
    middle = json.loads((LOCAL / "keys-c-2025.json").read_text(encoding="utf-8")) if YEAR == "2026" else None
    src = {"BASE30": X.books()["ADX|30"], "BASE30|AS": all_books["EXACT|A30|AS"]}
    return {f"{n}|carry": {**b, "carry": [first[n]] + ([middle[f"{n}|carry"]] if middle else [])} for n, b in src.items()}


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze-c.json").read_text(encoding="utf-8"))
    rel = (HERE / "freeze-c.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    changed = [k for k, v in frozen["sources"].items() if Y.grid._sha(ROOT / k) != v]
    assert not changed, f"files changed since the freeze: {changed}"
    all_books = books()
    assert {n: Y.digest(b) for n, b in frozen["books"].items()} == {n: Y.digest(b) for n, b in all_books.items()}
    assert 1 <= jobs <= 7
    O27F.deny_network()
    C.table("year")
    all_books.update(carried(all_books))
    with ProcessPoolExecutor(max_workers=jobs, initializer=L._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    L._atomic(LOCAL / f"keys-c-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()})
    print("DONE", YEAR, len(all_books), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run"])
    cli.add_argument("--jobs", type=int, default=6)
    a = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(a.jobs)}[a.action]()
