"""O30f - the books frozen for the one-time NIFTY 2024 test, and the 2024 setup. Research only.

What goes to 2024 (frozen in freeze-2024.json before the 2024 data is opened):
  * REF|LIVE (the live book), REF|LIVE+tpb_all_days (the O30c candidate), N|TPB|OWN (TPB alone), B|UNION and
    UNION_DRIVE (the book live until Oct 29), for reference;
  * ROBUST_CORE: the four strategies with distinct entry signals that were positive in both 2025 and 2026 (O30m
    persistence.json), ordered by their worse year: TPB, trend-pullback genome 4, SHIPPED, trend-pullback genome 5;
  * the 14 library strategies positive in both years, each alone (does "positive in both years" carry to a third?);
  * the O30m routers (FINAL and both cross-year ones), for information: they failed the cross-year check.
The rules (RULE_2024) are frozen with them. The 2024 data binding is recorded when its dataset is sealed, before any
replay. With O30F_YEAR=2024 this module points the machinery at the sealed 2024 data (mirror24 / export24 / warm24
once download2024.py has run); otherwise the year comes from O30C_YEAR as in O30c / O30m.
"""
from __future__ import annotations

import json
import os
import pickle
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
YEAR = os.environ.get("O30F_YEAR") or os.environ.get("O30C_YEAR", "2026")
if YEAR == "2024":
    os.environ["O30C_YEAR"] = "2026"         # import the 2026 machinery, then point it at 2024 below
import lab_m as M  # noqa: E402

C, Y, G, F = M.C, M.Y, M.G, M.C.F
LOCAL = M.LOCAL
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
CANDLES = """CREATE TABLE candles (
  kind TEXT, underlying TEXT, expiry TEXT, strike REAL, opt TEXT, interval TEXT, datetime TEXT,
  open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
  PRIMARY KEY (kind, underlying, expiry, strike, opt, interval, datetime))"""
MIRROR24, DATASET24, WARM24 = LOCAL / "mirror-2024.sqlite", LOCAL / "dataset-nifty-2024", LOCAL / "warm-parts-2024"
WINDOW24, END24, MUHURAT24 = ("2024-01-01", "2024-12-31"), "2025-01-01", "2024-11-01"
WINDOWS = {"2024": WINDOW24, **C.WINDOWS}
ROBUST_CORE = ("N|TPB|OWN", "L|TREND_PULLBACK|4", "N|SHIPPED|OWN", "L|TREND_PULLBACK|5")
POSITIVE_BOTH = ("N|TPB|OWN", "N|TPB|RUN", "L|TPB_O27F", "N|TPB|OWN|vwap", "N|TPB|LATE", "N|TPB|LOOSE",
                 "L|TREND_PULLBACK|4", "N|SHIPPED|OWN", "N|SHIPPED|LIVE", "L|TREND_PULLBACK|5", "L|PDL_BREAK|0",
                 "N|TPB|LIVE", "N|SHIPPED|OWN|vwap", "L|PDL_BREAK|7")

if YEAR == "2024":
    Y.YEAR = DATASET24
    Y.CACHES["year"] = LOCAL / "observations-2024"
    Y.LOCAL = LOCAL / "y2024"
    Y.EVALS = LOCAL / "evals"
    F.DOWNLOAD = MIRROR24
    F.DATASET = DATASET24
    C.WINDOW = WINDOW24

    def table24(source: str) -> dict:
        assert source == "year", source
        if source not in G._TABLE:
            manifest = json.loads((DATASET24 / "manifest.json").read_text(encoding="utf-8"))
            G._TABLE[source] = G.regime_rows(manifest["sessions"], Y.condition_table("year"),
                                             manifest["weekly_expiry_calendar"])
        return G._TABLE[source]

    C._base_table = table24
    C._CASE_TABLE.clear()
    G._TABLE.clear()
    Y.table = C.table


def books() -> dict:
    lib = M.library()
    routers = json.loads((HERE / "routers.json").read_text(encoding="utf-8"))["routers"]
    out = {**M.references(), "N|TPB|OWN": lib["N|TPB|OWN"], "B|UNION": lib["B|UNION"],
           "UNION_DRIVE": Y.FIXED["UNION_DRIVE"],
           "ROBUST_CORE": Y.book_of([lib[n]["members"][0] for n in ROBUST_CORE])}
    for n in POSITIVE_BOTH:
        out[f"ALONE|{n}"] = lib[n]
    for n, r in routers.items():
        out[f"ROUTER|{n}"] = M.router_book(r["cells"], lib)
    return out


RULE_2024 = {
    "once": "NIFTY 2024 is scored once with these books unchanged; nothing is tuned on it",
    "candidate": "REF|LIVE+tpb_all_days (O30c) is confirmed if, per lot on 2024, it beats REF|LIVE over the year and "
                 "is not worse in either half (Jan-Jun, Jul-Dec)",
    "robust_core": "ROBUST_CORE is a candidate if it nets > 0 on 2024 and beats REF|LIVE there",
    "persistence": "'positive in both years' carries to a third if at least 9 of the 14 ALONE books are positive on "
                   "2024 and their median beats the median of the other 100 library strategies on 2024",
    "routers": "the O30m routers are reported for information; they failed the cross-year check",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


# ---- the 2024 data (run after download2024.py; a sealed copy, then a sealed dataset) ---------------------------------

def mirror24() -> None:
    if MIRROR24.exists():
        raise SystemExit(f"{MIRROR24} exists; a sealed copy is never rewritten")
    LOCAL.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    keys = [k for (k,) in src.execute("SELECT key FROM requests WHERE status IN ('ok','empty') AND "
                                      "(key LIKE 'future|NIFTY|%' OR key LIKE 'option|NIFTY|%')")]
    groups = sorted({(k.split("|")[0], k.split("|")[2]) for k in keys})
    part = MIRROR24.with_name(MIRROR24.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    keep = "datetime < ? AND substr(datetime, 1, 10) != ?"
    pieces = [("SELECT * FROM candles WHERE kind=? AND underlying='NIFTY' AND expiry=? AND " + keep,
               (kind, expiry, END24, MUHURAT24)) for kind, expiry in groups]
    for year, month in [(2023, 12)] + [(2024, m) for m in range(1, 13)]:
        lo, hi = f"{year}-{month:02d}-01", f"{year + (month == 12)}-{month % 12 + 1:02d}-01"
        pieces.append(("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND "
                       "datetime >= ? AND datetime < ? AND " + keep, (lo, hi, END24, MUHURAT24)))
    pieces.append(("SELECT * FROM candles WHERE kind='daily' AND underlying IN ('NIFTY','BANKNIFTY') AND "
                   "datetime < ?", (END24,)))
    for sql, args in pieces:
        dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        src.execute(sql, args).fetchall())
        time.sleep(0.02)
    src.close()
    dst.commit()
    counts = dict(dst.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    dst.close()
    os.replace(part, MIRROR24)
    Y.write_new(LOCAL / "mirror-2024.json", {"rule": f"NIFTY rows before {END24}, without {MUHURAT24} (index/future/"
                                                     f"option)", "rows_by_kind": counts, "sha256": Y.grid._sha(MIRROR24)})
    print("mirror 2024:", counts, flush=True)


def export24() -> None:
    Y.yeardata.DOWNLOAD = MIRROR24
    Y.yeardata.export("NIFTY", WINDOW24[0], WINDOW24[1], DATASET24)


def _warm_day(day: str) -> str:
    _source, _day, part, bad = Y.warm_day(("year", day))
    tmp = WARM24 / f"{day}.{os.getpid()}.part"
    tmp.write_bytes(pickle.dumps((part, bad), protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, WARM24 / f"{day}.pkl")
    return day


def warm24(jobs: int) -> None:
    days = json.loads((DATASET24 / "manifest.json").read_text(encoding="utf-8"))["sessions"]
    if Y.memo_file("year").is_file():
        return
    WARM24.mkdir(parents=True, exist_ok=True)
    Y.memo_file("year").parent.mkdir(parents=True, exist_ok=True)
    todo = [d for d in days if not (WARM24 / f"{d}.pkl").is_file()]
    with ProcessPoolExecutor(max_workers=Y.allowed_inflight(jobs)) as ex:
        list(ex.map(_warm_day, todo))
    memo, conflicts = {}, 0
    for d in days:
        part, bad = pickle.loads((WARM24 / f"{d}.pkl").read_bytes())
        memo.update(part)
        conflicts += bad
    assert conflicts == 0, f"{conflicts} named signal(s) changed within a closed bar"
    Y.memo_file("year").write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"warm 2024: {len(memo)} named signals over {len(days)} sessions", flush=True)


# ---- freeze and run -------------------------------------------------------------------------------------------------

def freeze() -> None:
    assert YEAR != "2024"
    Y.write_new(HERE / "freeze-2024.json", {"schema": "o30f_nifty_2024_v1", "books": books(), "rule": RULE_2024,
                                            "robust_core": ROBUST_CORE, "positive_both": POSITIVE_BOTH,
                                            "sources": {p.relative_to(C.ROOT).as_posix(): Y.grid._sha(p) for p in
                                                        (HERE / "lab_f.py", HERE / "lab_m.py", C.HERE / "lab_c.py")},
                                            "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "books for 2024")


def run(jobs: int, which: str) -> None:
    frozen = M._committed("freeze-2024.json")
    assert {n: Y.digest(b) for n, b in frozen["books"].items()} == {n: Y.digest(b) for n, b in books().items()}
    o29i = json.loads((C.SIDE / "freeze.json").read_text(encoding="utf-8"))["bindings"]["sources"]
    changed = [k for k, v in o29i.items() if k.startswith("python-engine/") and Y.grid._sha(C.ROOT / k) != v]
    assert not changed, f"engine files changed since O29i (run from a worktree at the freeze commit): {changed}"
    C.O27F.deny_network()
    if YEAR == "2024":
        warm24(jobs)
    C.table("year")
    todo = frozen["books"] if which == "all" else {n: frozen["books"][n] for n in which.split(",")}
    if YEAR == "2024":
        todo = {**todo, **{n: b for n, b in M.library().items()}}      # the persistence rule needs the library
    print("reused", M._seed(todo), "earlier replays", flush=True)
    window = WINDOWS[YEAR]
    with ProcessPoolExecutor(max_workers=jobs, initializer=C._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(todo.values()), source="year", window=window)
    Y.write_new(LOCAL / f"results-raw-2024test-{YEAR}-{int(time.time())}.json", {
        "year": YEAR, "books": {n: Y.task_key(b, "year", window) for n, b in todo.items()}, "trades": runner.trades})
    print("DONE", YEAR, len(runner.trades), flush=True)


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run", "mirror24", "export24"])
    cli.add_argument("--jobs", type=int, default=4)
    cli.add_argument("--books", default="all")
    a = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(a.jobs, a.books), "mirror24": mirror24, "export24": export24}[a.action]()
