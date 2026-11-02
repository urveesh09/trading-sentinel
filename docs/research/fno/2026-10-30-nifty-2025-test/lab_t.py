"""O30 NIFTY 2025 clean test - research only. No runtime module imports this file.

Owner (Oct 30): "check if the nifty all 3585 are downloaded ... If it is then run our test simulation in that year
and this year together ... test for nifty".

The books found on Jan - Oct 2026 are replayed unchanged on NIFTY 2025, a year no rule was found on, through the same
shipped book (O29f BookReplay via O29g / O29i):
  * UNION_ADX (O29g / O29h, live since Oct 29): all four strategies when yesterday's NIFTY daily ADX(14) >= 25;
  * the O29i sideways entries on the days it sits out: the failed opening-range break FADE and the prior-day
    rejection PDL_FADE (both two-fold picks of each);
  * TPB at ADX >= 20 (O29g's most consistent shape), each strategy alone with and without the gate, UNION (no gate),
    UNION_DRIVE (live until Oct 29) and 20 random-entry books (always, under the ADX >= 25 gate, on sideways days).
The verdict rule (RULE) is frozen with the books before any 2025 replay. 2026 is read back from the stored O29f /
O29g / O29i replays (the engine files are checked unchanged), so "both years together" is 2025 + 2026 per lot.

Data: ICICI Breeze 1-minute NIFTY Dec 2 2024 - Dec 31 2025 (download2025.py, Oct 30), copied in short read-only
pieces into _local/mirror.sqlite (the downloader is still writing SENSEX into the same file), without
  * rows dated 2026 (the Jan 2026 future's Dec 2025 bars stay: it is Dec 31's front contract);
  * Oct 21 2025: Diwali, a holiday with a one-hour Muhurat session (Breeze fills the index at one price around it).
Daily NIFTY / NIFTY BANK bars up to Dec 31 2025 are kept as downloaded (Oct 21's Muhurat candle included, as a live
daily history holds it). Lot 65 (today's contract; the 2025 lot was 75), so a per-lot row is the real-money test's.
"""
from __future__ import annotations

import argparse
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
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
SIDE = ROOT / "docs/research/fno/2026-10-29-sideways-study"
sys.path[:0] = [str(SIDE), str(HERE)]

import lab_i  # noqa: E402  (O29i: the sideways families; imports O29g's lab_g and O29f's lab)

G, Y = lab_i.G, lab_i.Y
F = G.F
O27F = Y.O27F
LOCAL = HERE / "_local"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
MIRROR = LOCAL / "mirror.sqlite"
DATASET = LOCAL / "dataset-nifty-2025"
WARM = LOCAL / "warm-parts"
WINDOW = ("2025-01-01", "2025-12-31")
END, MUHURAT = "2026-01-01", "2025-10-21"
FREEZES = {"o29f": ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json",
           "o29g": ROOT / "docs/research/fno/2026-10-29-why-study/freeze.json",
           "o29i": SIDE / "freeze.json"}
SIDE_PICKS = {"FADE_MAIN": "FADE|level=OR20|stop=STRUCT|target_r=2.4|exit=LIVE",     # O29i H1 pick (shown to owner)
              "FADE_OTHER": "FADE|level=OR20|stop=STRUCT|target_r=2.4|exit=LATE",    # O29i H2 pick
              "PDL_MAIN": "PDL_FADE|stop=1.5|target_r=1.5|exit=LIVE",                # O29i H1 pick
              "PDL_OTHER": "PDL_FADE|stop=1.5|target_r=2.4|exit=LATE"}               # O29i H2 pick

# Point the O29f / O29g machinery at the 2025 data. Module level, so the spawned workers (which re-import this
# script) see the same paths.
Y.YEAR = DATASET
Y.CACHES["year"] = LOCAL / "observations-2025"
Y.LOCAL = LOCAL
Y.EVALS = LOCAL / "evals"
F.DOWNLOAD = MIRROR          # daily bars for the ADX side: the sealed copy, not the file being written
F.DATASET = DATASET


def table(source: str) -> dict:
    """O29g's regime table (O28 09:45 rows + the day-regime sides) over the 2025 sessions."""
    assert source == "year", source
    if source not in G._TABLE:
        manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
        G._TABLE[source] = G.regime_rows(manifest["sessions"], Y.condition_table("year"),
                                         manifest["weekly_expiry_calendar"])
    return G._TABLE[source]


Y.table = G.table = table


# ---- data ----------------------------------------------------------------------------------------------------------

CANDLES = """CREATE TABLE candles (
  kind TEXT, underlying TEXT, expiry TEXT, strike REAL, opt TEXT, interval TEXT, datetime TEXT,
  open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
  PRIMARY KEY (kind, underlying, expiry, strike, opt, interval, datetime))"""


def mirror() -> None:
    """NIFTY 2025 out of the live download in short read-only pieces (each read finishes in well under a second, so
    the downloader's writes are never held up)."""
    if MIRROR.exists():
        raise SystemExit(f"{MIRROR} exists; a sealed copy is never rewritten")
    LOCAL.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    keys = [k for (k,) in src.execute("SELECT key FROM requests WHERE status IN ('ok','empty') AND "
                                      "(key LIKE 'future|NIFTY|%' OR key LIKE 'option|NIFTY|%')")]
    groups = sorted({(k.split("|")[0], k.split("|")[2]) for k in keys})
    part = MIRROR.with_name(MIRROR.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    keep = "datetime < ? AND substr(datetime, 1, 10) != ?"
    pieces = [("SELECT * FROM candles WHERE kind=? AND underlying='NIFTY' AND expiry=? AND " + keep,
               (kind, expiry, END, MUHURAT)) for kind, expiry in groups]
    for year, month in [(2024, 12)] + [(2025, m) for m in range(1, 13)]:
        lo, hi = f"{year}-{month:02d}-01", f"{year + (month == 12)}-{month % 12 + 1:02d}-01"
        pieces.append(("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND "
                       "datetime >= ? AND datetime < ? AND " + keep, (lo, hi, END, MUHURAT)))
    pieces.append(("SELECT * FROM candles WHERE kind='daily' AND underlying IN ('NIFTY','BANKNIFTY') AND "
                   "datetime < ?", (END,)))
    for sql, args in pieces:
        rows = src.execute(sql, args).fetchall()
        dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        time.sleep(0.02)
    requests = {kind: dict(src.execute("SELECT status, COUNT(*) FROM requests WHERE key LIKE ? AND "
                                       "substr(key, length(key) - 20, 10) BETWEEN '2024-12-01' AND '2025-12-31' "
                                       "GROUP BY status", (f"{kind}|NIFTY|%",)).fetchall())
                for kind in ("index", "future", "option")}
    src.close()
    dst.commit()
    counts = dict(dst.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    dst.close()
    os.replace(part, MIRROR)
    Y.write_new(LOCAL / "mirror.json", {"source": "breeze-history.sqlite (download2025.py, Oct 30)",
                                        "rule": f"NIFTY rows before {END}, without {MUHURAT} (index/future/option)",
                                        "rows_by_kind": counts, "source_requests_2025": requests,
                                        "sha256": Y.grid._sha(MIRROR)})
    print("mirror:", counts, requests, flush=True)


def export() -> None:
    Y.yeardata.DOWNLOAD = MIRROR
    Y.yeardata.export("NIFTY", WINDOW[0], WINDOW[1], DATASET)


# ---- books and the rule ----------------------------------------------------------------------------------------------

def books() -> dict:
    side, why = lab_i.books(), G.books()
    out = {"UNION_ADX": side["UNION_ADX"], "UNION": Y.FIXED["UNION"], "UNION_DRIVE": Y.FIXED["UNION_DRIVE"],
           "TPB|adx_abs20:HIGH": why["TPB|adx_abs20:HIGH"]}
    for c in Y.NAMED:
        for g in ("ALWAYS", "adx_abs25:HIGH"):
            out[f"{c}|{g}"] = why[f"{c}|{g}"]
    for name in SIDE_PICKS.values():
        out[name] = side[name]
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}|ALWAYS"] = b
        out[f"NULL{i:02d}|adx_abs25:HIGH"] = G.gated(b, "adx_abs25:HIGH")
        out[f"NULL{i:02d}|sideways"] = side[f"NULL{i:02d}|sideways"]
    return out


RULE = {
    "status": "CLEAN: no rule, gate, variant or threshold here was chosen on 2025; the books and this rule are frozen "
              "before any 2025 replay and are not changed after it",
    "trend_book": "UNION_ADX holds on 2025 if its per-lot net > 0 AND it beats UNION (the same four, no gate) AND "
                  "UNION_DRIVE (the book live until Oct 29) AND the median of the 20 random-entry books under the same "
                  "ADX >= 25 gate",
    "sideways": "FADE (and PDL_FADE) holds if its main variant (the O29i H1 pick, the one shown to the owner) nets > 0 "
                "on 2025's sideways days AND beats the median of the 20 random sideways books; the other pick is "
                "reported beside it",
    "combo": "UNION_ADX + main FADE (trade lists joined; the two gates never trade the same day) against UNION_ADX "
             "alone; adding the fade can be recommended only if FADE holds AND the combo nets more than UNION_ADX alone",
    "tpb20": "TPB at ADX >= 20 holds if > 0 and it beats TPB always",
    "reported": "worst day, max drawdown, green / red months, halves (Jan-Jun, Jul-Dec), quarters, one-lot weeks from "
                "Rs 15,000 with the Rs 7,000 floor",
    "both_years": "2026 per lot from the stored O29f / O29g / O29i replays (in-sample, not re-scored) + 2025 = 22 months",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


def bindings() -> dict:
    g = G.bindings()   # the engine and O29f / O29g files; its manifest and daily-bar hashes are of the 2025 data here
    sources = dict(g["sources"])
    for p in (SIDE / "lab_i.py", SIDE / "test_lab_i.py", HERE / "lab_t.py", HERE / "analyze_t.py",
              HERE / "test_lab_t.py"):
        sources[p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    o29i = json.loads(FREEZES["o29i"].read_text(encoding="utf-8"))["bindings"]["sources"]
    changed = sorted(k for k, v in o29i.items() if sources.get(k) != v)
    if changed:
        raise SystemExit(f"files changed since the O29i freeze (the 2026 replays would not be comparable): {changed}")
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    for rel, sha in manifest["files_sha256"].items():
        if Y.grid._sha(DATASET / rel) != sha:
            raise SystemExit(f"2025 dataset file changed: {rel}")
    return {"sources": sources, "settings": g["settings"], "daily_bars_sha256": g["daily_bars_sha256"],
            "dataset_manifest_sha256": Y.grid._sha(DATASET / "manifest.json"), "sessions": manifest["sessions"],
            "mirror": json.loads((LOCAL / "mirror.json").read_text(encoding="utf-8")),
            "freezes": {k: Y.grid._sha(p) for k, p in FREEZES.items()}}


def freeze() -> None:
    O27F.deny_network()
    b = books()
    Y.write_new(HERE / "freeze.json", {"schema": "o30_nifty_2025_test_v1", "bindings": bindings(), "window": WINDOW,
                                       "side_picks": SIDE_PICKS, "books": b, "rule": RULE,
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(b), "books over", len(bindings()["sessions"]), "sessions")


# ---- run -------------------------------------------------------------------------------------------------------------

def _init() -> None:
    Y._worker_init()


def _warm_day(day: str) -> str:
    _source, _day, part, bad = Y.warm_day(("year", day))
    path = WARM / f"{day}.pkl"
    tmp = path.with_name(f"{day}.{os.getpid()}.part")
    tmp.write_bytes(pickle.dumps((part, bad), protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, path)
    return day


def warm(jobs: int, days: list[str]) -> None:
    """Y.warm, resumable: one saved part per session, merged once all are in."""
    if Y.memo_file("year").is_file():
        return
    WARM.mkdir(parents=True, exist_ok=True)
    todo = [d for d in days if not (WARM / f"{d}.pkl").is_file()]
    with ProcessPoolExecutor(max_workers=Y.allowed_inflight(jobs)) as ex:
        for n, _day in enumerate(ex.map(_warm_day, todo), 1):
            if n % 50 == 0:
                print(f"warm {n}/{len(todo)}", flush=True)
    memo, conflicts = {}, 0
    for d in days:
        part, bad = pickle.loads((WARM / f"{d}.pkl").read_bytes())
        memo.update(part)
        conflicts += bad
    assert conflicts == 0, f"{conflicts} named signal(s) changed within a closed bar; the memo is unsafe"
    Y.memo_file("year").write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"warm 2025: {len(memo)} named signals over {len(days)} sessions", flush=True)


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"] == bindings(), "bound inputs changed since the freeze"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "freeze not committed"
    assert 1 <= jobs <= 10
    O27F.deny_network()
    days = frozen["bindings"]["sessions"]
    for p in (Y.EVALS, Y.CACHES["year"]):
        p.mkdir(parents=True, exist_ok=True)
    warm(jobs, days)
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=WINDOW)
    assert frozen["bindings"] == bindings(), "bound inputs changed during scoring"
    Y.write_new(LOCAL / "results-raw.json", {"freeze_sha256": Y.grid._sha(HERE / "freeze.json"),
                                             "books": {n: Y.task_key(b, "year", WINDOW) for n, b in all_books.items()},
                                             "trades": runner.trades, "memory_pauses": runner.paused})
    print("DONE", len(runner.trades), "replays", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["mirror", "export", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=4)
    args = cli.parse_args()
    {"mirror": mirror, "export": export, "freeze": freeze, "run": lambda: run(args.jobs)}[args.action]()
