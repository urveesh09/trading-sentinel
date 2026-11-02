"""O30s sheet for the one-time NIFTY 2024 exam. Research only; frozen before any 2024 data exists.

This is a SECOND, separate sheet. The O30f list (2026-10-30-day-router/freeze-2024.json) is not changed and is scored
first. This one asks only what O30s left open: does the pass-over-stretched rule, found by looking at 2025 and 2026, hold
on a year it never saw, and do the sized candidates survive there?

After the O30f steps have sealed the 2024 data and warmed its memo (FNO_YEAR_DATA_TESTING_METHOD.md section 14):

    python ../run_slice.py --env O30F_YEAR=2024 --env O30S2_MODE=shipped -- <folder>/exam_s.py run --jobs 3   # until DONE
    python ../run_slice.py --env O30F_YEAR=2024 --env O30S2_MODE=raw -- <folder>/exam_s.py run --jobs 3       # until DONE
    python exam_s.py score                                                                                    # once

If the engine has changed by then, run from a worktree at this file's freeze commit.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-10-30-day-router")]
import lab_f as F24  # noqa: E402  (with O30F_YEAR=2024 this points the machinery at the sealed 2024 data)
import analyze_s as A  # noqa: E402
import lab_s as S  # noqa: E402
import lab_s2 as T  # noqa: E402

C, Y, ROOT = S.C, S.Y, S.ROOT
MODE = T.MODE
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / f"evals-2024-{MODE}"
WINDOW = F24.WINDOW24
HALVES = {"H1": ("2024-01-01", "2024-06-30"), "H2": ("2024-07-01", "2024-12-31")}
SHIPPED = ("LIVE", "LIVE|skip", "BEST", "BEST|skip", "TPB", "TPB|skip")

RULE = {
    "once": "NIFTY 2024 is scored once with these books and rules unchanged; nothing is tuned on it, and the O30f sheet "
            "is scored first and independently",
    "stretch_rule_holds": "per lot at the shipped size and brakes, the rule beats the same book without it on at least 2 "
                          "of LIVE, BEST and TPB over 2024, AND the median of the 20 random books (one lot, no brakes) "
                          "is higher with the rule than without it",
    "tpb_skip_candidate": "TPB|skip at 3 lots, no brakes, Rs 200 extra per lot per trade: net > 0 over 2024 and largest "
                          "fall <= 25% of the running peak",
    "best_skip_candidate": "BEST|skip at 3 lots on the same terms",
    "live_skip_candidate": "LIVE|skip at 3 lots on the same terms",
    "pick_candidate": "the O30s frozen pick (TPB|HOUSE, 3 lots, half size when stretched) on the same terms",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


def books(mode: str = MODE) -> dict:
    if mode == "shipped":
        return {n: T.books("shipped")[n] for n in SHIPPED}
    plain = S.books()
    out = {n: plain[n] for n in ("TPB", "TPB|HOUSE")}
    out.update({n: b for n, b in plain.items() if n.startswith("NULL")})
    out.update(T.books("raw"))
    return out


def per_lot_net(trades: list) -> float:
    return sum(float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) for t in trades if t.get("net_pnl") is not None)


def verdict(shipped: dict, raw: dict) -> dict:
    """shipped / raw: book name -> trades, as the replays stored them."""
    net = {n: per_lot_net(t) for n, t in shipped.items()}
    prep = {n: A.prep(t) for n, t in raw.items()}
    nulls = sorted(n for n in prep if n.startswith("NULL") and "|" not in n)
    med = {tag: statistics.median(A.sim(prep[n + suffix], ("fixed", 1))["net"] for n in nulls)
           for tag, suffix in (("without", ""), ("with", "|skip"))}
    beaten = [b for b in ("LIVE", "BEST", "TPB") if net[f"{b}|skip"] > net[b]]

    def candidate(name: str, half: bool = False) -> dict:
        s = A.sim(prep[name], ("fixed", 3), "NONE", A.STRESS, half, reserve=2 if "HOUSE" in name else 1)
        return {"net_plus_200": s["net"], "fall_pct": s["fall_pct"], "worst_day": s["worst_day"], "trades": s["trades"],
                "as_replayed": A.sim(prep[name], ("fixed", 3), "NONE", 0.0, half, reserve=2 if "HOUSE" in name else 1)["net"],
                "passes": s["net"] > 0 and s["fall_pct"] <= A.MAX_FALL}

    return {"stretch_rule_holds": len(beaten) >= 2 and med["with"] > med["without"], "rule_beat_on": beaten,
            "per_lot": {n: round(v) for n, v in net.items()}, "random_median": {k: round(v) for k, v in med.items()},
            "halves_per_lot": {n: {h: round(per_lot_net([t for t in shipped[n] if first <= t["entry_time"][:10] <= last]))
                                   for h, (first, last) in HALVES.items()} for n in shipped},
            "TPB|skip": candidate("TPB|skip"), "BEST|skip": candidate("BEST|skip"), "LIVE|skip": candidate("LIVE|skip"),
            "pick": candidate("TPB|HOUSE", True)}


def freeze() -> None:
    sources = {p.relative_to(ROOT).as_posix(): Y.grid._sha(p) for p in
               [*sorted((ROOT / "python-engine").glob("*.py")), HERE / "lab_s.py", HERE / "lab_s2.py", HERE / "analyze_s.py",
                HERE / "exam_s.py", HERE / "test_exam_s.py"]}
    Y.write_new(HERE / "freeze-2024.json", {"schema": "o30s_nifty_2024_v1", "rule": RULE, "sources": sources,
                                            "books": {m: books(m) for m in ("shipped", "raw")},
                                            "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", sum(len(books(m)) for m in ("shipped", "raw")), "books for the 2024 sheet")


def _committed() -> dict:
    frozen = json.loads((HERE / "freeze-2024.json").read_text(encoding="utf-8"))
    rel = (HERE / "freeze-2024.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    changed = [k for k, v in frozen["sources"].items() if Y.grid._sha(ROOT / k) != v]
    assert not changed, f"files changed since this freeze (run from a worktree at its commit): {changed}"
    return frozen


def _init() -> None:
    if MODE == "raw":
        S.apply_raw()
    C._init()


def run(jobs: int) -> None:
    assert F24.YEAR == "2024", "set O30F_YEAR=2024"
    assert F24.DATASET24.is_dir(), "the 2024 data is not sealed yet: follow FNO_YEAR_DATA_TESTING_METHOD.md section 14"
    frozen = _committed()
    assert {n: Y.digest(b) for n, b in frozen["books"][MODE].items()} == {n: Y.digest(b) for n, b in books().items()}
    S.O27F.deny_network()
    C.table("year")
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=WINDOW)
    target = LOCAL / f"results-2024-{MODE}.json"
    tmp = target.with_name(target.name + f".{os.getpid()}.part")     # a stopped slice must not leave half a file
    tmp.write_text(json.dumps({"mode": MODE, "books": {n: Y.task_key(b, "year", WINDOW) for n, b in all_books.items()},
                               "trades": runner.trades}), encoding="utf-8")
    os.replace(tmp, target)
    print("DONE 2024", MODE, len(runner.trades), flush=True)


def score() -> None:
    frozen = _committed()
    trades = {}
    for mode in ("shipped", "raw"):
        raw = json.loads((LOCAL / f"results-2024-{mode}.json").read_text(encoding="utf-8"))
        assert set(raw["books"]) == set(frozen["books"][mode]), "a frozen book has no 2024 replay"
        trades[mode] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    out = {"schema": "o30s_results_2024_v1", "rule": frozen["rule"], "verdict": verdict(trades["shipped"], trades["raw"]),
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    with (HERE / "results-2024.json").open("x", encoding="utf-8", newline="\n") as f:      # written once
        json.dump(out, f, indent=1)
    print(json.dumps(out["verdict"], indent=1))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run", "score"])
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(a.jobs), "score": score}[a.action]()
