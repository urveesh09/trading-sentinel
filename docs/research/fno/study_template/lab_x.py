"""TEMPLATE year-data study - copy this folder to docs/research/fno/<yyyy-mm-dd>-<name>/, rename, and edit the parts
marked EDIT. Research only; no runtime module imports this file. Method: docs/FNO_YEAR_DATA_TESTING_METHOD.md.

<EDIT: the owner's question, verbatim, and what this study tests.>

Example strategy (EDIT or replace): EXAMPLE_ORB15, a 15-minute opening-range breakout - the first close beyond the
09:15-09:30 range (plus a buffer of ATR) buys the option in that direction, at most one entry per side per day, no
entry after `last_entry_min`; stop `stop_atr` x ATR, target `target_r` x risk, exits from `exit`.

Declared before any replay (freeze.json): the books, RULE and analyze_x.py. Scored on NIFTY 2024, 2025 and Jan - Oct 2026
through the shipped single-leg book (O29f BookReplay), per lot. The year is chosen by O30F_YEAR=2024 or O30C_YEAR=2025 | 2026.

    O30C_YEAR=2025 python lab_x.py smoke                 # plumbing check on January only (never a result)
    python lab_x.py freeze                               # then commit and push freeze.json alone
    python ../run_slice.py --env O30F_YEAR=2024 -- <this folder>/lab_x.py run --jobs 4      # repeat until DONE
    python ../run_slice.py --env O30C_YEAR=2025 -- <this folder>/lab_x.py run --jobs 4
    python ../run_slice.py --env O30C_YEAR=2026 -- <this folder>/lab_x.py run --jobs 4
    python analyze_x.py                                  # the frozen verdict -> results.json
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
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "docs/research/fno/2026-10-30-case-study"), str(ROOT / "docs/research/fno/2026-10-30-day-router")]
if os.environ.get("O30F_YEAR") == "2024":
    import lab_f  # noqa: E402,F401  (must come first: points the machinery below at the sealed 2024 data)
import lab_c as C  # noqa: E402  (year setup via O30C_YEAR; regime table with DMI / EMA sides; case routing)

Y, G, O27F = C.Y, C.G, C.O27F
YEAR = "2024" if os.environ.get("O30F_YEAR") == "2024" else C.YEAR
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
FAMILY = "EXAMPLE_ORB15"                                   # EDIT


# ---- 1. the entry signal (causal: the answer for bar i reads only bars <= i and earlier sessions) ---------------------

_TABLE: dict = {}


def entries(m: dict, f: dict) -> dict:
    """bar_ts -> direction (+1 buy calls / -1 buy puts) for one member on one session."""             # EDIT
    key = (G.digest(m), f["day"].isoformat(), f["stamps"][-1], len(f["stamps"]))
    if key in _TABLE:
        return _TABLE[key]
    t = f["t"]
    c, h, l, atr, mins = (t["close"].values, t["high"].values, t["low"].values, t["atr"].values,
                          t["minute"].values)
    out, done, n = {}, set(), 3                                # three 5-minute bars: 09:15-09:30
    if len(t) > n and mins[0] == 555:
        hi, lo = float(h[:n].max()), float(l[:n].min())
        for i in range(n, len(t)):
            if mins[i] + 5 > m["last_entry_min"] or not atr[i] > 0:
                continue
            for d, hit in ((1, c[i] > hi + m["buffer_atr"] * atr[i]), (-1, c[i] < lo - m["buffer_atr"] * atr[i])):
                if hit and d not in done:
                    out[f["stamps"][i]] = d
                    done.add(d)
    _TABLE[key] = out
    while len(_TABLE) > 6000:
        _TABLE.pop(next(iter(_TABLE)))
    return out


def signal(m: dict, frame, regime: str, now):
    naive = now.replace(tzinfo=None)
    f = O27F.day_features(frame, naive.date())
    bar_ts = O27F.last_closed_bar(f, now) if f is not None else Y.replay._last_closed_bar(frame, now)
    if bar_ts is None or f is None or not f["complete_open"]:
        return G.MomSignal(bar_ts=bar_ts or "", reject_reason="example:no_features")
    return G._signal(frame, regime, now, m, entries(m, f).get(bar_ts), bar_ts, f)


_prev_signal = G.new_signal


def new_signal(m, frame, regime, now):
    return signal(m, frame, regime, now) if m["family"] == FAMILY else _prev_signal(m, frame, regime, now)


G.new_signal = new_signal          # module level: spawned workers re-import this script and get the same patch


def member(gate: str = "ALWAYS", **genes) -> dict:
    return G.new_member(FAMILY, gate, **{"buffer_atr": 0.1, "last_entry_min": 720, "stop_atr": 1.0, "target_r": 2.0,
                                         "exit": "LIVE", **genes})


# ---- 2. the books (EDIT), the references and the luck yardstick ---------------------------------------------------

def books() -> dict:
    live = C.book(C.four(lambda c: C.ADX))
    out = {"REF|LIVE": live,
           "REF|LIVE+tpb_all_days": C.book(C.four(lambda c: "ALWAYS" if c == "TPB" else C.ADX)),
           "CAND|alone": Y.book_of([member()]),
           # added after the live book's four strategies (a book can hold more than four members if built directly)
           "CAND|added_to_live": {"members": [*live["members"], Y.canonical_member(member())]}}
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}"] = b
    return out


RULE = {                                                    # EDIT, before any replay
    "question": "does EXAMPLE_ORB15 make money per lot in all three NIFTY years, and does adding it improve the live book?",
    "alone": "CAND|alone helps if it nets > 0 in 2024, 2025 AND 2026, is not negative in more than 1 of the 6 half-years, "
             "makes >= 40 trades a year and beats the median of the 20 random-entry books in every year",
    "added": "CAND|added_to_live helps if it beats REF|LIVE in every year and is not worse in 4 of the 6 half-years",
    "status": "2024, 2025 and 2026 are all seen; a pass is a candidate for the unseen checks (the forward panel, real "
              "fills), never a go-live on this replay",
}


# ---- 3. freeze, run, smoke --------------------------------------------------------------------------------------------

def year_bindings() -> dict:
    out = C.year_bindings()
    for p in (HERE / "lab_x.py", HERE / "analyze_x.py", HERE / "test_lab_x.py"):
        out["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    parts = {}
    clean = {k: v for k, v in os.environ.items() if k not in ("O30F_YEAR", "O30C_YEAR")}
    for year, env in (("2024", {"O30F_YEAR": "2024"}), ("2025", {"O30C_YEAR": "2025"}), ("2026", {"O30C_YEAR": "2026"})):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_x.py"), "bindings"], cwd=ROOT, env={**clean, **env})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "template_year_study_v1", "bindings": parts, "books": books(),
                                       "rule": RULE, "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "books")


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"][YEAR] == json.loads(json.dumps(year_bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    O27F.deny_network()
    C.table("year")
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=C._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    Y.write_new(LOCAL / f"results-raw-{YEAR}.json", {
        "freeze_sha256": Y.grid._sha(HERE / "freeze.json"), "year": YEAR,
        "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()}, "trades": runner.trades})
    print("DONE", YEAR, len(runner.trades), flush=True)


def smoke() -> None:
    """The candidate alone over January of the chosen year: proves the plumbing, scores nothing."""
    O27F.deny_network()
    Y.EVALS = LOCAL / "smoke"
    Y.speedups()
    window = (f"{YEAR}-01-01", f"{YEAR}-01-31")
    _key, trades = Y.evaluate((books()["CAND|alone"], "year", window))
    print(f"smoke {YEAR} January: {len(trades)} trades (plumbing check only, not a result)")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run", "smoke"])
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs), "smoke": smoke}[a.action]()
