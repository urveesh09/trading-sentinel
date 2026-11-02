"""O30m day-type router - research only. No runtime module imports this file.

Owner (Oct 30, after O30c): the system has to identify what kind of day is happening (the market on a macro level)
and what the trade is doing (micro), and deploy the strategy that suits it; search widely (genome allowed), counter as
many sessions as possible, without over-tuning; 2024 is the test.

Method, declared before any library replay (freeze.json):
  1. a LIBRARY of single strategies, each replayed always-on over NIFTY 2025 and Jan - Oct 2026 through the same
     shipped book: the four named strategies with five exits (+ VWAP exit), 8 seeded genomes of each O27f lab
     family + the O27f trend-pullback genome, NOISE_BAND / LATE_MOMO (O29g), every O29i range-day variant, the four
     strategies together (UNION) and 20 random-entry books;
  2. a day is described before trading by its macro type (yesterday's daily bars: trend strength ADX >= 25, trend
     direction DMI, 20-day volatility, the O29g trend regime) and its 09:45 micro type (opening drive); six declared
     PARTITIONS combine them into 2-8 kinds of day;
  3. for each kind of day the ROUTER takes the library strategy (in any direction, only with the daily trend, or only
     against it) whose WORST half-year in that kind of day is best, if that is positive with enough trades; else it
     sits that kind of day out (analyze_m.py, by slicing each strategy's own trades);
  4. the method must work on a year it did not see: chosen on 2025 and scored on 2026, and chosen on 2026 and scored on
     2025, it must beat the live book, the live book + TPB on closed days (O30c) and the median random router, both
     ways; only a partition that passes gives the router frozen for the one-time NIFTY 2024 test;
  5. the routers are then replayed exactly (route() below) to confirm the slicing estimate.
The year is chosen by O30C_YEAR (2025: the sealed O30 data; 2026: the O29f data), as in O30c.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
CASE = ROOT / "docs/research/fno/2026-10-30-case-study"
sys.path.insert(0, str(CASE))
import lab_c as C  # noqa: E402  (year setup, the DMI / EMA direction sides, Tier 1 routing)
import lab_i  # noqa: E402

Y, G, ROUTER, replay = C.Y, C.G, C.ROUTER, C.replay
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
SEED_DIRS = [C.LOCAL / "evals", C.O30 / "_local/evals"] + [
    ROOT / f"docs/research/fno/{s}/_local/evals"
    for s in ("2026-10-29-sideways-study", "2026-10-29-why-study", "2026-10-29-year-genome")]
PARTITIONS = {"P1_trend": ("adx_abs25",), "P2_trend_dir": ("adx_abs25", "dmi_dir"),
              "P3_trend_dir_vol": ("adx_abs25", "dmi_dir", "rv20"), "P4_regime_dir": ("trend_regime", "dmi_dir"),
              "P5_trend_drive": ("adx_abs25", "open_drive"), "P6_trend_dir_drive": ("adx_abs25", "dmi_dir", "open_drive")}
MODES = ("any", "with", "against")
RANDOM_ROUTERS = 200
SELECT = {"cv_min_trades_per_half": 5, "final_min_trades_per_half": 4}


# ---- routing: member gate "cond&cond&dir=with|against" ---------------------------------------------------------------

def _conds(gate: str) -> list[str]:
    return [t for t in gate.split("&") if not t.startswith("dir=")]


def _dir(gate: str):
    return next((t[4:] for t in gate.split("&") if t.startswith("dir=")), None)


_prev_route = Y.BookReplay.route


def route(self, frame, regime, now):
    if self.book.get("router") != "o30m" or self.warm:
        return _prev_route(self, frame, regime, now)
    bar_ts = replay._last_closed_bar(frame, now)
    row = self.table.get(now.date().isoformat())
    trend = C.wanted("dmi", row)
    for i, m in enumerate(self.members):
        if not all(ROUTER.allowed(t, row) for t in _conds(m["gate"])):
            continue
        sig = self._signal(i, frame, regime, now, bar_ts)
        if sig.direction is None:
            continue
        d = _dir(m["gate"])
        if (d == "with" and sig.direction != trend) or (d == "against" and (trend is None or sig.direction == trend)):
            self.notes["router_direction_pass"] += 1
            continue
        self._fired = i
        return sig
    return G.MomSignal(bar_ts=bar_ts or "", reject_reason="router:no_member")


Y.BookReplay.route = route


# ---- the library -----------------------------------------------------------------------------------------------------

def library() -> dict:
    out = {}
    for c in Y.NAMED:
        for ex in Y.NAMED_EXITS:
            out[f"N|{c}|{ex}"] = Y.book_of([Y.named(c, "ALWAYS", ex)])
        out[f"N|{c}|OWN|vwap"] = Y.book_of([Y.named(c, "ALWAYS", "OWN", "ON")])
    rng = random.Random("o30m-library-2026-10-30")
    for fam in Y.LAB_FAMILIES:
        for k in range(8):
            out[f"L|{fam}|{k}"] = Y.book_of([Y.lab(Y.random_lab_genome(fam, rng))])
    out["L|TPB_O27F"] = Y.seeds()[-2]
    for k in (1.0, 1.5):
        for check in ("30m", "5m"):
            out[f"X|NOISE_BAND|k{k}|{check}"] = Y.book_of([G.new_member("NOISE_BAND", k=k, check=check)])
    for mode in ("FHH", "DAY"):
        for x in (0.003, 0.006):
            out[f"X|LATE_MOMO|{mode}|{x}"] = Y.book_of([G.new_member("LATE_MOMO", mode=mode, x=x)])
    for fam, genes in lab_i.GRID.items():
        for values in itertools.product(*genes.values()):
            g = dict(zip(genes, values))
            out[f"S|{fam}|" + "|".join(f"{k}={v}" for k, v in g.items())] = Y.book_of(
                [lab_i.side_member(fam, gate="ALWAYS", **g)])
    out["B|UNION"] = Y.FIXED["UNION"]
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}"] = b
    return out


def references() -> dict:
    """The live book and the O30c candidate, replayed with the library for the comparison."""
    tpb_days = C.four(lambda c: "ALWAYS" if c == "TPB" else C.ADX)
    return {"REF|LIVE": C.book(C.four(lambda c: C.ADX)), "REF|LIVE+tpb_all_days": C.book(tpb_days)}


def router_book(cells: list[dict], lib: dict) -> dict:
    """Members in cell order; each library member keeps its strategy and exits and takes the cell's gate."""
    members = []
    for cell in cells:
        gate = "&".join(f"{f}:{v}" for f, v in cell["cell"].items())
        if cell["mode"] != "any":
            gate += f"&dir={cell['mode']}"
        for m in lib[cell["pick"]]["members"]:
            members.append({**m, "gate": gate})
    return {"members": members, "router": "o30m"}


RULE = {
    "selection": "per kind of day: the (strategy, direction mode) whose worst half-year net per lot inside that kind of "
                 "day is highest, if > 0 and with at least the declared trades in every half used; else sit out",
    "cv": "choose on 2025 (its two halves) and score on 2026, and choose on 2026 and score on 2025",
    "pass": "a partition passes if, in both directions, the chosen router's net on the unseen year beats the live book, "
            "the live book + TPB on closed days and the median of 200 random routers (a random library choice per "
            "kind of day) on that year",
    "final": "the passing partition with the best worse-direction result is chosen on both years (four halves) and "
             "frozen for the one-time NIFTY 2024 test with the live book and the O30c candidate; if none passes, no "
             "router goes to 2024",
    "exact": "chosen routers are replayed exactly; the slicing numbers are estimates",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


# ---- freeze and run --------------------------------------------------------------------------------------------------

def year_bindings() -> dict:
    out = C.year_bindings()
    for p in (HERE / "lab_m.py", HERE / "analyze_m.py", HERE / "test_lab_m.py"):
        out["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    parts = {}
    for year in ("2025", "2026"):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_m.py"), "bindings"], cwd=ROOT,
                                      env={**C.os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    lib = library()
    Y.write_new(HERE / "freeze.json", {"schema": "o30m_day_router_v1", "bindings": parts, "library": lib,
                                       "references": references(), "partitions": PARTITIONS, "modes": MODES,
                                       "random_routers": RANDOM_ROUTERS, "select": SELECT, "rule": RULE,
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(lib), "library books")


def _committed(name: str) -> dict:
    frozen = json.loads((HERE / name).read_text(encoding="utf-8"))
    rel = (HERE / name).relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, f"{name} not committed"
    return frozen


def _seed(books: dict) -> int:
    """Replays already made by earlier studies (same book, same data, same key) are reused, not run again."""
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    n = 0
    for b in books.values():
        key = Y.task_key(b, "year", C.WINDOW) + ".json"
        if (Y.EVALS / key).is_file():
            continue
        src = next((d / key for d in SEED_DIRS if (d / key).is_file()), None)
        if src:
            shutil.copyfile(src, Y.EVALS / key)
            n += 1
    return n


def run(what: str, jobs: int) -> None:
    frozen = _committed("freeze.json")
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(year_bindings(), default=str)), "inputs changed"
    C.O27F.deny_network()
    rows = C.table("year")
    target = LOCAL / f"table-{C.YEAR}.json"
    if not target.is_file():
        Y.write_new(target, {d: {"side": r.get("side")} for d, r in rows.items()})
    if what == "library":
        books = {**library(), **references()}
    else:
        routers = _committed("routers.json")
        lib = library()
        books = {name: router_book(r["cells"], lib) for name, r in routers["routers"].items()}
    print("reused", _seed(books), "earlier replays", flush=True)
    with ProcessPoolExecutor(max_workers=jobs, initializer=C._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(books.values()), source="year", window=C.WINDOW)
    Y.write_new(LOCAL / f"results-raw-{what}-{C.YEAR}.json", {
        "year": C.YEAR, "what": what, "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()},
        "trades": runner.trades})
    print("DONE", what, C.YEAR, len(runner.trades), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run"])
    cli.add_argument("--what", choices=["library", "routers"], default="library")
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    elif a.action == "freeze":
        freeze()
    else:
        run(a.what, a.jobs)
