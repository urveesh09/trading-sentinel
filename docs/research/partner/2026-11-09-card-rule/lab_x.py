"""N09c card-rule study (Nov 9, 2026): does the partner's buy card make money on a year of NIFTY history?

The owner, Nov 9: "is there any way our system can help them earn profit ... even if we restrict them even small
losses are losses ... any and all suggestion that we receive are they also received from our own FNO strategy or from
something else? Can we improve it in any way" and then "Go on do it since you know what to do".

Why this rule: on Production (read-only, Oct 27 - Nov 9) the partner's trades in the direction of a live card won 48%
(62 trades) against 33% for all their other trades (271), and the cards reached their target 9 times in 18 since
Oct 1. That is 18 cards in a strongly rising month. Before the partner is coached to lean on the card, the card rule
itself, unchanged, is replayed on the history we hold.

The card rule as shipped (partner_orchestrator -> fno_signal_scan -> fno_engine_mom.evaluate_fno_mom; partner_buyer):
  - entry: the shipped opening-range break on the front future's 5-minute bars (the book's SHIPPED member signal);
  - stop: the card's SL order sits at the option price of the index stop (1.5 ATR); here the index stop itself;
  - target: "target reached ... Book profit" at the index target (1.8 R); here a sale at the target;
  - otherwise square off by the deadline (card 15:15; the replay's hard flat is 15:10).
  The replay buys the shipped book's option (delta 0.55, near expiry), one lot, with the book's costs. The card's
  own long leg can differ by a strike. NIFTY only: the year data has no SENSEX option minutes.

Exit settings: CARD = no time stop, no profit lock, a zero-width trail once the target is hit (sold at the target
observation). CARD_KEEP (informational) keeps a 1.5 ATR trail after the target instead of selling.

    python lab_x.py smoke                                     # plumbing check on January only (never a result)
    python lab_x.py freeze                                    # then commit freeze.json before any run
    python ../../fno/run_slice.py --env O30F_YEAR=2024 -- <this folder>/lab_x.py run --jobs 4    # repeat until DONE
    python ../../fno/run_slice.py --env O30C_YEAR=2025 -- <this folder>/lab_x.py run --jobs 4
    python ../../fno/run_slice.py --env O30C_YEAR=2026 -- <this folder>/lab_x.py run --jobs 4
    python analyze_x.py                                       # the frozen verdict -> results.json

Research only; no runtime module imports this file.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "docs/research/fno/2026-10-30-case-study"), str(ROOT / "docs/research/fno/2026-10-30-day-router")]
if os.environ.get("O30F_YEAR") == "2024":
    import lab_f  # noqa: E402,F401  (must come first: points the machinery below at the sealed 2024 data)
import lab_c as C  # noqa: E402  (year setup via O30C_YEAR)

Y, G, O27F = C.Y, C.G, C.O27F
YEAR = "2024" if os.environ.get("O30F_YEAR") == "2024" else C.YEAR
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"

# The card's exits, added to the named exit table at module level (spawned workers re-import this script).
CARD_EXIT = {"FNO_TIME_STOP_MIN": 10000.0, "FNO_PROFIT_LOCK_ENABLED": False, "FNO_TRAIL_ATR_MULT": 0.0}
KEEP_EXIT = {"FNO_TIME_STOP_MIN": 10000.0, "FNO_PROFIT_LOCK_ENABLED": False, "FNO_TRAIL_ATR_MULT": 1.5}
O27F.EXITS["CARD"] = CARD_EXIT
O27F.EXITS["CARD_KEEP"] = KEEP_EXIT

NULL_BOOKS = 20
NULL_SEED = "2026110901|CARD_NULL"
SHIPPED_GEOMETRY = {"rvol": 0.0, "htf": "OFF", "window": "ALL", "stop_atr": 1.5, "target_r": 1.8, "exit": "CARD",
                    "vwap_exit": "OFF"}


def null_books() -> list[dict]:
    """Random entries (the O27f NULL_RANDOM family) with the card's stop, target and exits: the luck yardstick."""
    rng = random.Random(NULL_SEED)
    out, seen = [], set()
    while len(out) < NULL_BOOKS:
        g = {"family": "NULL_RANDOM", "nr_p": rng.choice((0.02, 0.04, 0.08)), "nr_seed": rng.randrange(16),
             **SHIPPED_GEOMETRY}
        key = (g["nr_p"], g["nr_seed"])
        if key in seen:
            continue
        seen.add(key)
        out.append(Y.book_of([Y.lab(g)]))
    return out


def books() -> dict:
    out = {"CARD|shipped": Y.book_of([Y.named("SHIPPED", "ALWAYS", "CARD")]),
           "REF|shipped_book_exits": Y.book_of([Y.named("SHIPPED", "ALWAYS", "OWN")]),
           "INFO|shipped_card_keep": Y.book_of([Y.named("SHIPPED", "ALWAYS", "CARD_KEEP")]),
           "INFO|live_union_adx": C.book(C.four(lambda c: C.ADX))}
    for i, b in enumerate(null_books()):
        out[f"NULL{i:02d}"] = b
    return out


RULE = {
    "question": "does the partner's card rule (shipped opening-range break, index stop, sell at the index target, "
                "else square off) make money per lot on NIFTY in 2024, 2025 and Jan - Oct 2026?",
    "card_passes": "CARD|shipped passes if, per lot after the replay's costs: net > 0 in each of 2024, 2025 and 2026; "
                   "net > 0 over the three years after an extra Rs 200 per trade; net > 0 over the three years without "
                   "its best day; not negative in more than 1 of the 6 half-years; at least 40 trades a year; and net "
                   "above the median of the 20 random-entry books (same stop, target and exits) in every year",
    "exits_question": "informational, decided in advance: the card's exits beat the book's own exits on the same "
                      "entries if CARD|shipped nets more than REF|shipped_book_exits in every year",
    "on_pass": "the card is a tested lead for the partner: build the card-led watch messages (messages only, a "
               "switch, never a block) and keep scoring the cards forward; profit is still not promised",
    "on_fail": "the partner is not coached to lean on the card; the finding is reported as it is",
    "status": "2024, 2025 and Jan - Oct 2026 are seen for F&O rules, but this rule is the shipped card, unchanged and "
              "not chosen on these years; Jan - May 2022 stays reserved for the N012 exam and is not read; no "
              "setting is tuned on this result",
}


# ---- freeze, run, smoke --------------------------------------------------------------------------------------------

def _bindings_2025() -> dict:
    """lab_t.bindings without its O29i comparison check; the sealed 2025 dataset's file hashes are still checked."""
    T = C.T
    g = T.G.bindings()
    sources = dict(g["sources"])
    for p in (T.SIDE / "lab_i.py", T.SIDE / "test_lab_i.py", T.HERE / "lab_t.py", T.HERE / "analyze_t.py",
              T.HERE / "test_lab_t.py"):
        sources[p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    manifest = json.loads((T.DATASET / "manifest.json").read_text(encoding="utf-8"))
    for rel, sha in manifest["files_sha256"].items():
        if Y.grid._sha(T.DATASET / rel) != sha:
            raise SystemExit(f"2025 dataset file changed: {rel}")
    return {"sources": sources, "settings": g["settings"], "daily_bars_sha256": g["daily_bars_sha256"],
            "dataset_manifest_sha256": Y.grid._sha(T.DATASET / "manifest.json"), "sessions": manifest["sessions"],
            "mirror": json.loads((T.LOCAL / "mirror.json").read_text(encoding="utf-8"))}


def year_bindings() -> dict:
    """The year's dataset and replay-stack fingerprints as they are today. lab_c.year_bindings refuses any engine file
    changed since the O29i freeze (Oct 29), a check for comparing with O29i's replays; this study replays the current
    engine's exit ladder and does not claim that comparison, so it binds the current files instead."""
    out = _bindings_2025() if C.YEAR == "2025" else C.lab_i.bindings()
    out = {**out, "sources": dict(out["sources"])}
    for p in (HERE / "lab_x.py", HERE / "analyze_x.py", HERE / "test_lab_x.py", C.HERE / "lab_c.py"):
        out["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    parts = {}
    clean = {k: v for k, v in os.environ.items() if k not in ("O30F_YEAR", "O30C_YEAR")}
    for year, env in (("2024", {"O30F_YEAR": "2024"}), ("2025", {"O30C_YEAR": "2025"}), ("2026", {"O30C_YEAR": "2026"})):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_x.py"), "bindings"], cwd=ROOT, env={**clean, **env})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "n09c_card_rule_v1", "bindings": parts, "books": books(),
                                       "exits": {"CARD": CARD_EXIT, "CARD_KEEP": KEEP_EXIT}, "rule": RULE,
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
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
    """The card alone over January of the chosen year: proves the plumbing and prints exit reasons, scores nothing."""
    O27F.deny_network()
    Y.EVALS = LOCAL / "smoke"
    Y.speedups()
    window = (f"{YEAR}-01-01", f"{YEAR}-01-31")
    for name in ("CARD|shipped", "REF|shipped_book_exits"):
        _key, trades = Y.evaluate((books()[name], "year", window))
        reasons = {}
        for t in trades:
            reasons[t.get("exit_reason")] = reasons.get(t.get("exit_reason"), 0) + 1
        print(f"smoke {YEAR} January {name}: {len(trades)} trades, exits {reasons} (plumbing check only, not a result)")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run", "smoke"])
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs), "smoke": smoke}[a.action]()
