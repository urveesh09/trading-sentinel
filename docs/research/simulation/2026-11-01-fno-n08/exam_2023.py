"""The one-time 2023 test of N08. Order is the protection: freeze and commit, then seal the data with no prices shown, then replay once.

    N08_YEAR=2023 <venv python> exam_2023.py mirror      # copies 2023's rows in short read-only pieces; refuses before the freeze is committed
    N08_YEAR=2023 <venv python> exam_2023.py export      # the sealed dataset
    N08_YEAR=2023 <venv python> exam_2023.py warm --jobs 5
    N08_YEAR=2023 <venv python> exam_2023.py bind        # data-binding-2023.json, counts only: commit it before any replay
    N08_YEAR=2023 <venv python> exam_2023.py run --jobs 5

The same steps with N08_YEAR=TEST2025 aim the wiring at sealed 2025 data with known results, which is how it was checked first.
Windows workers re-import this file, so everything they need sits at module level.
"""
from __future__ import annotations

import argparse
import json
import math
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
YEAR = os.environ.get("N08_YEAR")
assert YEAR in ("2023", "TEST2025"), "this file only serves the sealed exam and its wiring test"
import n08_lab as N  # noqa: E402

Y, X, F, C, B = N.Y, N.X, N.F, N.C, N.B
POINT = N.POINTS[YEAR]
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
END, MUHURAT = "2024-01-01", "2023-11-12"
WARM = POINT["local"] / "warm-parts"
CANDLES = """CREATE TABLE candles (
  kind TEXT, underlying TEXT, expiry TEXT, strike REAL, opt TEXT, interval TEXT, datetime TEXT,
  open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
  PRIMARY KEY (kind, underlying, expiry, strike, opt, interval, datetime))"""


def sha(path: Path) -> str:
    return B.P.sha(path)


def require_freeze() -> None:
    frozen = json.loads((HERE / "freeze-v2.json").read_text(encoding="utf-8"))
    rel = (HERE / "freeze-v2.json").relative_to(N.ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=N.ROOT)) == frozen, "freeze-v2.json is not committed"
    first = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["books"] == first["books"] and frozen["rule"] == first["rule"], "the correction may not change a book or a rule"
    changed = [k for k, v in frozen["sources"].items() if sha(N.ROOT / k) != v]
    assert not changed, f"files changed since the freeze: {changed}"
    books = N.exam_books()
    assert {n: b["digest"] for n, b in frozen["books"].items()} == {n: Y.digest(b) for n, b in books.items()}, "a frozen book changed"


SOURCES = ("docs/research/simulation/2026-11-01-fno-n08/" + n for n in ("n08_lab.py", "n08_rules.py", "exam_2023.py", "test_n08.py", "PLAN.md", "analyze_screen.py", "heldout_check.py"))
PARENTS = ("docs/research/simulation/2026-11-01-fno-failure-anatomy/anatomy_lab.py", "docs/research/simulation/2026-11-01-fno-failure-anatomy/anatomy_rules.py",
           "docs/research/simulation/2026-11-01-fno-stall-refinement/refine_lab.py", "docs/research/simulation/2026-11-01-fno-exit-ablation/exit_lab.py",
           "docs/research/simulation/2026-11-01-fno-eff-improvement/eff_lab.py", "docs/research/simulation/2026-11-01-fno-core-selector/core_lab.py",
           "docs/research/fno/2026-10-31-weak-spots/freeze-2023.json", "python-engine/fno_policy_replay.py", "python-engine/fno_exit_rules.py", "python-engine/fno_entry_plan.py")
RULE = {
    "once": "NIFTY 2023 is opened once, by this commit's books. Nothing is tuned on it. The data is sealed and fingerprinted before any replay.",
    "measure": "Fresh Rs 2.5 lakh each year, today's brakes, lot 65, modeled candle quotes, current fees and the extra (200 + 5 x lots) x lots in the money path. 2026 runs to Oct 28.",
    "n08_passes_2023": "N08's 2023 net is above zero and at or above N07's, and its largest closed fall on 2023 is no larger than N07's.",
    "n08_passes_four_years": "N08 is positive in every year, and its four-year total is above each of N03, N04, N05 and N07.",
    "verdict": "N08 is the lead research candidate only if it passes both. Otherwise it stays a seen-year lead and the result is reported as it is.",
    "o31e_exam": "The EXAM| books are scored by the rule in docs/research/fno/2026-10-31-weak-spots/freeze-2023.json, unchanged.",
    "parts": "PART| and ONE| books only explain the result. They can't become N08 after 2023 is open.",
    "no_change": "Nothing changes in the system on this. The owner decides. Real money needs shadow evidence and real fills first.",
}


def freeze() -> None:
    assert YEAR == "2023"
    target = HERE / "freeze.json"
    assert not target.exists(), "frozen once"
    assert not POINT["mirror"].exists() and not POINT["dataset"].exists(), "the freeze must come before the 2023 data is sealed"
    books = N.exam_books()
    X.write(target, {"schema": "n08_freeze_v1", "status": "Fixed before any NIFTY 2023 replay. Written with 2023 unopened by any rule, screen or diagnosis in this study.",
                     "sources": {p: sha(N.ROOT / p) for p in (*SOURCES, *PARENTS)}, "books": {n: {"digest": Y.digest(b), "label": b.get("label") or b.get("o31")} for n, b in books.items()},
                     "n08": {k: books["N08"][k] for k in ("n08", "cfg", "n07_mode", "n02_profile", "cost")}, "rule": RULE, "qualified": False, "can_place_orders": False})
    print("frozen", len(books), "books", flush=True)


def freeze2() -> None:
    """The correction: same books, same rule, new source hashes. The original freeze.json stays."""
    assert YEAR == "2023"
    target = HERE / "freeze-v2.json"
    assert not target.exists(), "frozen once"
    first = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    books = N.exam_books()
    assert {n: b["digest"] for n, b in first["books"].items()} == {n: Y.digest(b) for n, b in books.items()}, "the correction may not change a book"
    sources = {p: sha(N.ROOT / p) for p in (*SOURCES, *PARENTS)}
    X.write(target, {**first, "schema": "n08_freeze_v2_source_correction", "status": "Same books and rule as freeze.json. Only the wiring that reads daily bars changed. See SOURCE_CORRECTION.md.",
                     "original_freeze_sha256": sha(HERE / "freeze.json"), "source_correction_sha256": sha(HERE / "SOURCE_CORRECTION.md"), "sources": sources})
    print("frozen v2", len(books), "books", flush=True)


def write_daily() -> None:
    """2023's own daily bars, from the sealed mirror, in the same file format every other year uses. Nothing is shown."""
    assert YEAR == "2023"
    target = POINT["daily"]
    assert not target.exists(), "written once"
    frame = N.GAP._original_daily()
    assert frame.index[-1].isoformat()[:10] <= POINT["window"][1], "a daily bar after the year"
    assert (frame.index < "2023-01-01").sum() >= 200, "too little history before the year"
    Y.write_new(target, {"rows": [[str(i.date()), *map(float, row)] for i, row in frame.iterrows()]})
    print("daily 2023:", len(frame), "bars", str(frame.index[0].date()), str(frame.index[-1].date()), flush=True)


def check_inputs() -> dict:
    """What the first opening lacked: proof that the gate reads this year's bars. It refuses to run otherwise."""
    frame = F.daily_bars()
    sessions = json.loads((POINT["dataset"] / "manifest.json").read_text(encoding="utf-8"))["sessions"]
    table = Y.table("year")
    assert frame.index[-1].isoformat()[:10] <= POINT["window"][1] and frame.index[-1].isoformat()[:10] >= sessions[-1], ("daily bars do not end with this year", frame.index[-1])
    closed = [d for d in sessions if table[d]["side"].get("adx_abs30") is None]
    assert not closed, ("sessions with no trend reading", closed[:5], len(closed))
    return {"daily_bars": len(frame), "first": str(frame.index[0].date()), "last": str(frame.index[-1].date()), "bars_before_first_session": int((frame.index < sessions[0]).sum()),
            "sessions": len(sessions), "gate_high": sum(table[d]["side"]["adx_abs30"] == "HIGH" for d in sessions), "gate_low": sum(table[d]["side"]["adx_abs30"] == "LOW" for d in sessions)}


def mirror() -> None:
    assert YEAR == "2023"
    require_freeze()
    target = POINT["mirror"]
    if target.exists():
        raise SystemExit(f"{target} exists; a sealed copy is never rewritten")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    keys = [k for (k,) in src.execute("SELECT key FROM requests WHERE status IN ('ok','empty') AND (key LIKE 'future|NIFTY|%' OR key LIKE 'option|NIFTY|%')")]
    groups = sorted({(k.split("|")[0], k.split("|")[2]) for k in keys})
    part = target.with_name(target.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    keep = "datetime < ? AND substr(datetime, 1, 10) != ?"
    pieces = [("SELECT * FROM candles WHERE kind=? AND underlying='NIFTY' AND expiry=? AND " + keep, (kind, expiry, END, MUHURAT)) for kind, expiry in groups]
    for year, month in [(2022, 12)] + [(2023, m) for m in range(1, 13)]:
        lo, hi = f"{year}-{month:02d}-01", f"{year + (month == 12)}-{month % 12 + 1:02d}-01"
        pieces.append(("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND datetime >= ? AND datetime < ? AND " + keep, (lo, hi, END, MUHURAT)))
    pieces.append(("SELECT * FROM candles WHERE kind='daily' AND underlying IN ('NIFTY','BANKNIFTY') AND datetime < ?", (END,)))
    for sql, args in pieces:
        dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", src.execute(sql, args).fetchall())
        time.sleep(0.02)
    src.close()
    dst.commit()
    counts = dict(dst.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    dst.close()
    os.replace(part, target)
    Y.write_new(N.LOCAL / "mirror-2023.json", {"rule": f"NIFTY rows before {END}, without {MUHURAT} (index/future/option); daily bars before {END}", "rows_by_kind": counts, "sha256": sha(target)})
    print("mirror 2023:", counts, flush=True)


def export() -> None:
    assert YEAR == "2023"
    require_freeze()
    Y.yeardata.DOWNLOAD = POINT["mirror"]
    Y.yeardata.export("NIFTY", POINT["window"][0], POINT["window"][1], POINT["dataset"])


def _warm_day(day: str) -> str:
    _source, _day, part, bad = Y.warm_day(("year", day))
    tmp = WARM / f"{day}.{os.getpid()}.part"
    tmp.write_bytes(pickle.dumps((part, bad), protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, WARM / f"{day}.pkl")
    return day


def warm(jobs: int) -> None:
    if YEAR == "2023":
        require_freeze()
    days = json.loads((POINT["dataset"] / "manifest.json").read_text(encoding="utf-8"))["sessions"]
    if Y.memo_file("year").is_file():
        print("warm: already done", flush=True)
        return
    WARM.mkdir(parents=True, exist_ok=True)
    Y.memo_file("year").parent.mkdir(parents=True, exist_ok=True)
    todo = [d for d in days if not (WARM / f"{d}.pkl").is_file()]
    with ProcessPoolExecutor(max_workers=Y.allowed_inflight(jobs)) as ex:
        list(ex.map(_warm_day, todo))
    memo, conflicts = {}, 0
    for d in days:
        part, bad = pickle.loads((WARM / f"{d}.pkl").read_bytes())
        memo.update(part)
        conflicts += bad
    assert conflicts == 0, f"{conflicts} named signal(s) changed within a closed bar"
    Y.memo_file("year").write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"warm {YEAR}: {len(memo)} named signals over {len(days)} sessions", flush=True)


def bind() -> None:
    """Hashes, counts and written decisions, before any replay. Counts only: no price is read out or shown."""
    assert YEAR == "2023"
    require_freeze()
    manifest = json.loads((POINT["dataset"] / "manifest.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{(POINT['dataset'] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    bad = {"nonpositive_ohlc": 0, "incoherent_ohlc": 0, "negative_volume": 0, "negative_oi": 0, "invalid_timestamp": 0}
    by_kind: dict = {}
    for kind, stamp, o, h, l, c, v, oi in con.execute("SELECT kind, datetime, open, high, low, close, volume, oi FROM candles"):
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if len(stamp) != 19:
            bad["invalid_timestamp"] += 1
        if any(x is None or not math.isfinite(x) or x <= 0 for x in (o, h, l, c)):
            bad["nonpositive_ohlc"] += 1
        elif not (l <= o <= h and l <= c <= h):
            bad["incoherent_ohlc"] += 1
        bad["negative_volume"] += v is not None and v < 0
        bad["negative_oi"] += oi is not None and oi < 0
    index = dict(con.execute("SELECT substr(datetime,1,10), COUNT(*) FROM candles WHERE kind='index' GROUP BY 1"))
    sessions = manifest["sessions"]
    no_options = [d for d in sessions if not con.execute("SELECT 1 FROM candles WHERE kind='option' AND substr(datetime,1,10)=? LIMIT 1", (d,)).fetchone()]
    short = sorted((d, index[d]) for d in sessions if index.get(d, 0) < 300)
    con.close()
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    ceiling = src.execute("SELECT COUNT(*) FROM requests WHERE rows>=1000 AND (key LIKE 'index|NIFTY|2023%' OR key LIKE 'future|NIFTY|%|2023-%' OR key LIKE 'option|NIFTY|%|2023-%')").fetchone()[0]
    src.close()
    expiries = sorted(manifest["option_expiries"])
    out = {
        "schema": "n08_nifty_2023_data_binding_v1", "recorded_before_any_2023_replay": True,
        "repo_head_when_sealed": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=N.ROOT).decode().strip(),
        "freeze_sha256": sha(HERE / "freeze.json"), "source_database_sha256": sha(SOURCE), "mirror": json.loads((N.LOCAL / "mirror-2023.json").read_text(encoding="utf-8")),
        "dataset_breeze_sqlite_sha256": sha(POINT["dataset"] / "breeze.sqlite"), "dataset_manifest_sha256": sha(POINT["dataset"] / "manifest.json"),
        "sessions": len(sessions), "first_last_session": [sessions[0], sessions[-1]], "option_expiries": len(expiries), "first_last_option_expiry": [expiries[0], expiries[-1]],
        "future_expiries": manifest["future_expiries"], "rows_by_kind": by_kind, "bad_rows": bad, "sessions_without_any_option": no_options, "short_sessions": short,
        "requests_at_the_candle_ceiling": ceiling, "lot_size_used": manifest["lot_size"],
        "decisions": {
            "2023-03-01": "ICICI returned no option candle for this whole session: 23 two-day requests held only Feb 28 and 4 one-day requests were empty. The session stays and the book cannot enter on it. No candle is invented.",
            "2023-11-12": "The Muhurat hour is not a session here, as in 2024 and 2025.",
            "bad rows": "Kept as they are, as in the other years: replays read the bid and ask derived from each close, and a negative volume only matters to volume readings.",
            "lot": "65, today's contract, as in every other year, although 2023's real lot was 50. Rupee figures are comparable across years, not what 2023's traders earned.",
            "candles": "The same declared candle model as 2024-26: bid and ask from the archive's p75 spread, about Rs 100-200 per trade per lot optimistic, with the extra cost in the money path.",
            "stray bars": "Index bars from 09:15 to 15:39 kept as exported, as in the other years.",
            "expiries": "Thursday all year, holiday shifts worked out from the real sessions. The probe proved Jan 25, 2023 and the year-end Jan 4 and Jan 25, 2024.",
        },
        "prices_shown": False,
    }
    Y.write_new(HERE / "data-binding-2023.json", out)
    print(json.dumps({k: out[k] for k in ("sessions", "first_last_session", "option_expiries", "rows_by_kind", "bad_rows", "sessions_without_any_option", "short_sessions", "requests_at_the_candle_ceiling")}), flush=True)


def run(jobs: int) -> None:
    N.B.O27F.deny_network()
    inputs = check_inputs()
    print("inputs:", inputs, flush=True)
    if YEAR == "2023":
        require_freeze()
        binding = json.loads(subprocess.check_output(["git", "show", "HEAD:" + (HERE / "data-binding-2023.json").relative_to(N.ROOT).as_posix()], cwd=N.ROOT))
        assert binding["dataset_breeze_sqlite_sha256"] == sha(POINT["dataset"] / "breeze.sqlite"), "the sealed 2023 data changed"
        books = N.exam_books()
    else:
        books = {**N.references(), "NOOP": N.noop_book()}
        already = {f.name for f in Y.EVALS.glob("*.json")} if Y.EVALS.is_dir() else set()
        assert not already, "the wiring test must start empty, or it proves nothing"
    N.run_books(books, jobs)
    if YEAR == "2023":
        X.write(N.LOCAL / "keys-exam-2023-v2.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()})
        X.write(HERE / "exam-inputs-2023.json", inputs)
    else:
        result = N.parity()
        result["inputs"] = inputs
        result["replayed_here_seconds"] = {f.stem[-8:]: json.loads(f.read_text(encoding="utf-8"))["seconds"] for f in Y.EVALS.glob("*.json")}
        assert all(v > 1 for v in result["replayed_here_seconds"].values()), "a result was not really replayed"
        X.write(HERE / "parity-repoint-test.json", result)
        print("REPOINT PARITY", {k: v for k, v in result.items() if k.startswith("NORMAL")}, flush=True)
    print("DONE exam", YEAR, len(books), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("freeze", "freeze2", "daily", "mirror", "export", "warm", "bind", "run"))
    cli.add_argument("--jobs", type=int, default=5)
    a = cli.parse_args()
    {"freeze": freeze, "freeze2": freeze2, "daily": write_daily, "mirror": mirror, "export": export, "warm": lambda: warm(a.jobs), "bind": bind, "run": lambda: run(a.jobs)}[a.action]()
