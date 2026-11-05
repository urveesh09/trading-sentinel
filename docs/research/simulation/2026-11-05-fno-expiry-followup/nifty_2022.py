"""Run the unchanged N11 and final N11T replay books on sealed NIFTY 2022 data."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = HERE / "_local"
EXAM = LOCAL / "nifty-2022"
WINDOW = ("2022-06-01", "2022-12-31")
MIRROR = EXAM / "mirror.sqlite"
DAILY = EXAM / "daily.json"
DATASET = EXAM / "dataset"
FREEZE = HERE / "nifty-2022-freeze.json"
BINDING = HERE / "nifty-2022-inputs.json"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")


def committed(path):
    name = path.relative_to(ROOT).as_posix()
    frozen = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=ROOT)
    if json.loads(frozen) != json.loads(path.read_bytes()):
        raise ValueError(f"Uncommitted changes to {name}")
    return json.loads(frozen)


os.environ["N08_YEAR"] = "TEST2025"
os.environ.pop("N09_CARRY", None)
sys.path.insert(0, str(HERE.parent / "2026-11-02-fno-n11-tolerance"))
import n11t_final as final

lab = final.Z.N
lab.POINTS["TEST2025"].update(dataset=DATASET, mirror=MIRROR, window=WINDOW,
                             cache=EXAM / "observations", local=EXAM, daily=DAILY)
lab.GAP.DAILY = DAILY
final.Y.YEAR = lab.F.DATASET = DATASET
final.Y.LOCAL = EXAM
final.Y.CACHES["year"] = EXAM / "observations"
lab.F.DOWNLOAD = MIRROR
lab.C.WINDOW = WINDOW
lab.B.YEAR = "2022"
final.Z.DAILY_SOURCES = (DAILY,)
final.Y.EVALS = EXAM / "evals"
final.X.LOCAL = EXAM


def books():
    return {
        "paper_history": final.Z.diag_books()["DIAG"],
        "N11": final.L.n11_book("T|BASE"),
        "N11T": final.book("FINAL"),
    }


def freeze():
    paths = set()
    for name, module in tuple(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if file and Path(file).is_relative_to(ROOT):
            path = Path(file)
            if path.suffix == ".py" and ("docs" in path.parts or path.parent == ROOT / "python-engine"):
                paths.add(path.relative_to(ROOT).as_posix())
    paths.update([Path(__file__).relative_to(ROOT).as_posix(),
                  (HERE / "PLAN.md").relative_to(ROOT).as_posix()])
    write(FREEZE, {"window": WINDOW, "books": books(), "allocation": 250000,
                   "minimum_option_sessions": 200, "minimum_tolerance_trades": 10,
                   "test": "Final frozen N11T versus unchanged N11; do not tune on 2022.",
                   "warmup": "NSE public daily index OHLC, or Yahoo unadjusted NIFTY 50 and NIFTY BANK OHLC if NSE unavailable, strictly before 2022.",
                   "sources": {p: digest(ROOT / p) for p in sorted(paths)}})


def require_freeze():
    spec = committed(FREEZE)
    if spec["books"] != json.loads(json.dumps(books())):
        raise ValueError("Frozen books changed")
    for name, fingerprint in spec["sources"].items():
        if digest(ROOT / name) != fingerprint:
            raise ValueError(f"Source changed: {name}")


def prepare():
    require_freeze()
    EXAM.mkdir(parents=True, exist_ok=True)
    warm = json.loads((EXAM / "pre-2022-warmup.json").read_bytes())
    src = sqlite3.connect(SOURCE.as_uri() + "?mode=ro", uri=True, timeout=20)
    if MIRROR.exists():
        raise FileExistsError(MIRROR)
    dst = sqlite3.connect(MIRROR)
    schema = src.execute("select sql from sqlite_master where name='candles'").fetchone()[0]
    dst.execute(schema)
    write_rows = "insert into candles values(?,?,?,?,?,?,?,?,?,?,?,?,?)"
    dst.executemany(write_rows, (
        ("daily", u, "", 0, "", "1day", row[0] + " 00:00:00", *row[1:], 0, 0)
        for u, bars in warm["rows"].items() for row in bars
    ))
    groups = src.execute("""select distinct kind,expiry from candles
        where kind in ('future','option') and underlying='NIFTY'
        and expiry>='2022-04-01' and expiry<'2023-02-01'""").fetchall()
    for kind, expiry in [("index", ""), *groups]:
        start = "2022-04-01"
        rs = src.execute("""select * from candles where kind=? and underlying='NIFTY' and expiry=?
            and interval='1minute' and datetime>=? and datetime<'2023-01-01'
            and substr(datetime,1,10)!='2022-10-24'""", (kind, expiry, start))
        dst.executemany(write_rows, rs)
    dst.executemany(write_rows, src.execute("""select * from candles where kind='daily'
        and underlying in ('NIFTY','BANKNIFTY') and datetime>='2022-01-01' and datetime<'2023-01-01'"""))
    daily = dst.execute("""select substr(datetime,1,10),open,high,low,close from candles
        where kind='daily' and underlying='NIFTY' order by datetime""").fetchall()
    assert len({r[0] for r in daily}) == len(daily)
    assert sum(r[0]<WINDOW[0] for r in daily) >= 265
    assert all(0 < r[3] <= min(r[1],r[4]) <= max(r[1],r[4]) <= r[2] for r in daily)
    write(DAILY, {"rows": daily})
    counts = dict(dst.execute("select kind,count(*) from candles group by kind"))
    coverage = dst.execute("""select substr(datetime,1,10),count(*),count(distinct expiry)
        from candles where kind='option' group by 1 order by 1""").fetchall()
    dst.commit()
    dst.close()
    src.close()
    final.Y.yeardata.DOWNLOAD = MIRROR
    final.Y.yeardata.export("NIFTY", *WINDOW, DATASET)
    paths = [EXAM / "pre-2022-warmup.json", MIRROR, DAILY, DATASET / "breeze.sqlite", DATASET / "manifest.json"]
    write(BINDING, {"rows": counts, "option_sessions": len(coverage), "option_coverage": coverage,
                    "daily_preroll": sum(r[0]<WINDOW[0] for r in daily),
                    "files": {p.relative_to(HERE).as_posix(): digest(p) for p in paths}})


def stats(raw):
    equity = peak = 250000.0
    drawdown = 0.0
    days = defaultdict(float)
    reasons = Counter()
    closed = [t for t in raw["trades"] if t["status"] == "CLOSED"]
    for t in sorted(closed, key=lambda t: t["exit_time"]):
        net = float(t["net_pnl"])
        equity += net
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        days[t["exit_time"][:10]] += net
        reasons[t["exit_reason"]] += 1
    net = equity - 250000
    return {"net": round(net, 2), "closed": len(closed), "unresolved": len(raw["trades"]) - len(closed),
            "worst_day": round(min(0, *days.values()), 2), "closed_drawdown": round(drawdown, 2),
            "net_ex_best": round(net - max([0] + [float(t["net_pnl"]) for t in closed]), 2),
            "daily": {d: round(n, 4) for d, n in sorted(days.items())}, "exit_reasons": reasons,
            "funnel": raw["funnel"], "notes": raw["notes"]}


def run():
    require_freeze()
    binding = committed(BINDING)
    for name, fingerprint in binding["files"].items():
        if digest(HERE / name) != fingerprint:
            raise ValueError(f"Input changed: {name}")
    result_path = HERE / "nifty-2022-results.json"
    if result_path.exists():
        raise FileExistsError(result_path)
    # The 2022 paper record may never read any result from later years.
    history = books()["paper_history"]
    final.Y.EVALS.mkdir(parents=True, exist_ok=True)
    final.Z.N.run_books({"DIAG": history}, 2)
    key = final.Y.task_key(history, "year", WINDOW)
    raw = json.loads((final.Y.EVALS / f"{key}.json").read_bytes())
    from datetime import datetime
    final.L.U.paper_rows = lambda: tuple(sorted(
        ((datetime.fromisoformat(t["exit_time"]), t) for t in raw["trades"] if t["status"] == "CLOSED"),
        key=lambda x: (x[0], x[1]["entry_time"])))
    # Evaluate sequentially in this process so the isolated evidence binding is also used by every book.
    final.Y.speedups()
    out = {}
    for name in ("N11", "N11T"):
        key, _ = final.Y.evaluate((books()[name], "year", WINDOW))
        out[name] = stats(json.loads((final.Y.EVALS / f"{key}.json").read_bytes()))
        print(name, out[name]["net"], out[name]["closed"], flush=True)
    delta = {d: out["N11T"]["daily"].get(d, 0) - out["N11"]["daily"].get(d, 0)
             for d in sorted(set(out["N11"]["daily"]) | set(out["N11T"]["daily"]))}
    out.update(window=WINDOW, options_sessions=binding["option_sessions"], paper_history=stats(raw),
               incremental_net=round(sum(delta.values()), 2),
               incremental_ex_best_day=round(sum(delta.values()) - max([0]+list(delta.values())), 2),
               status="PARTIAL_BELOW_200_SESSIONS" if binding["option_sessions"] < 200 else "SCORED")
    write(result_path, out)


if __name__ == "__main__":
    {"freeze": freeze, "prepare": prepare, "run": run}[sys.argv[1]]()
