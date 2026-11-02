"""O30s Tier 2: do not buy a stretched entry - research only. No runtime module imports this file.

FOUND BY LOOKING. The O30q review noticed that entries far from VWAP lose more often on the live book. The O30s frozen
run (045351b) then showed half-size-when-stretched lifting every book, and report_s.py showed stretched TPB entries
losing in all four half-years. So this idea was shaped by both years: it cannot be proved on them, only checked for
whether it survives the real book, and it goes to the one-time 2024 check and forward data.

The rule, one setting, the O30q limit: a signal is passed over when the last closed 5-minute close already stands at
least half of the first 30 minutes' range beyond VWAP, in the trade's direction. A later bar may still enter at a better
place. Why this is not a loss-reaction block: it reads the price at entry, never the results of earlier trades.

Two modes, chosen by O30S2_MODE:
  shipped  the shipped sizing and brakes, exact: the numbers comparable with every earlier study;
  raw      one lot, brakes off, as O30s, so the sizing simulator can size it (with the random books as the control).
Limits 0.25 and 0.75 are a sensitivity on shipped mode only and can never be chosen.

    python lab_s2.py freeze
    python ../run_slice.py --env O30C_YEAR=2025 --env O30S2_MODE=shipped -- <folder>/lab_s2.py run --jobs 3   # until DONE
    (the same for O30C_YEAR=2026, and for O30S2_MODE=raw)
    python analyze_s2.py
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
sys.path.insert(0, str(HERE))
import lab_s as S  # noqa: E402

C, Y, G, O27F, ROOT = S.C, S.Y, S.G, S.O27F, S.ROOT
MODE = os.environ.get("O30S2_MODE", "shipped")
assert MODE in ("shipped", "raw"), MODE
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / f"evals-t2-{MODE}"
LIMIT = 0.5
SENSITIVITY = (0.25, 0.75)

_prev_route = Y.BookReplay.route


def route(self, frame, regime, now):
    sig = _prev_route(self, frame, regime, now)
    limit = self.book.get("skip")
    if limit is None or self.warm or sig.direction is None:
        return sig
    stretch = S.stretch_at(frame, now, sig.direction.value)
    if stretch is not None and stretch >= limit:
        self.notes["o30s2_stretched"] += 1
        return G.MomSignal(bar_ts=sig.bar_ts, reject_reason="o30s2:stretched")
    return sig


Y.BookReplay.route = route


def _base(name: str) -> list[dict]:
    return Y.FIXED["UNION_DRIVE"]["members"] if name == "DRIVE" else S._members(name)


def books(mode: str = MODE) -> dict:
    out = {}
    tag = {"o30s2": mode}
    if mode == "shipped":
        for name in ("LIVE", "BEST", "TPB", "UNION", "DRIVE"):
            out[name] = {"members": [Y.canonical_member(m) for m in _base(name)], **tag}
            out[f"{name}|skip"] = {**out[name], "skip": LIMIT}
        for name in ("LIVE", "BEST", "TPB"):
            for limit in SENSITIVITY:
                out[f"{name}|skip{int(limit * 100)}"] = {**out[name], "skip": limit}
    else:
        for name in ("LIVE", "BEST", "TPB"):
            out[f"{name}|skip"] = {"members": [Y.canonical_member(m) for m in _base(name)], **tag, "skip": LIMIT}
        for i, b in enumerate(Y.null_fixed()):
            out[f"NULL{i:02d}|skip"] = {"members": [Y.canonical_member(m) for m in b["members"]], **tag, "skip": LIMIT}
    return out


RULE = {
    "status": "Tier 2: found by looking at 2025 and 2026. A pass here is a candidate for the 2024 check and forward data, "
              "never proof and never a go-live.",
    "helps": "in shipped mode, per lot, a book with the rule helps if it beats the same book without it in 2025 AND in "
             "2026, is not worse in at least 3 of the 4 half-years, makes at least 40 trades a year, and stays above 0 "
             "after Rs 200 per trade in both years",
    "control": "the rule is a market effect, not a strategy effect, if the 20 random books gain from it too: reported",
    "one_day": "every book's 2026 is also shown without Feb 1 (the Budget Sunday): it was 58% of the live book's 2026",
    "sensitivity": "limits 0.25 and 0.75 are shown, never chosen; a real effect should not depend on the exact limit",
    "reference_parity": "LIVE, BEST and TPB in shipped mode must reproduce +271 / +80,912, +34,517 / +80,232 and "
                        "+36,694 / +42,056 per lot, or the setup differs and nothing here counts",
}


def year_bindings() -> dict:
    out = C.year_bindings()
    for p in (HERE / "lab_s.py", HERE / "lab_s2.py", HERE / "analyze_s.py", HERE / "analyze_s2.py", HERE / "test_lab_s2.py"):
        out["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    parts = {}
    for year in ("2025", "2026"):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_s2.py"), "bindings"], cwd=ROOT,
                                      env={**os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    Y.write_new(HERE / "freeze-t2.json", {"schema": "o30s_tier2_v1", "bindings": parts, "limit": LIMIT, "sensitivity": SENSITIVITY,
                                          "books": {m: books(m) for m in ("shipped", "raw")}, "rule": RULE,
                                          "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", sum(len(books(m)) for m in ("shipped", "raw")), "books x 2 years")


def _init() -> None:
    if MODE == "raw":
        S.apply_raw()
    C._init()


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze-t2.json").read_text(encoding="utf-8"))
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(year_bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze-t2.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    assert 1 <= jobs <= 6
    O27F.deny_network()
    C.table("year")
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    Y.write_new(LOCAL / f"results-t2-{MODE}-{C.YEAR}.json", {
        "freeze_sha256": Y.grid._sha(HERE / "freeze-t2.json"), "year": C.YEAR, "mode": MODE,
        "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()}, "trades": runner.trades})
    print("DONE", C.YEAR, MODE, len(runner.trades), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs)}[a.action]()
