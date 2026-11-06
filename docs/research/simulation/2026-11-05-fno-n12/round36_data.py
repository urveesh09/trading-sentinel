"""Inventory and bind ordinary SENSEX sessions before looking at trade outcomes."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import urllib.request

from anatomy import DATASETS, read
from round9_data import BSE, parse, relative
from round25 import digest


HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local/round36"
OLD = HERE / "_local/round9"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
FIRST, LAST = "2025-07-01", "2026-10-28"
START, FINISH = "09:15:00", "15:10:00"
TAIL = "15:29:00"
MINUTES = 356
COLS = "kind,expiry,strike,opt,datetime,open,high,low,close,volume,oi"


def write(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def at_or_after(expiries, day):
    return next((value for value in expiries if value >= day), None)


def plan():
    manifests = {y: read(DATASETS[y] / "manifest.json") for y in ("2025", "2026")}
    days = sorted({d for info in manifests.values() for d in info["sessions"]})
    with closing(sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True, timeout=15)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        counts = defaultdict(dict)
        for day, expiry, n in db.execute(
            "SELECT substr(datetime,1,10),expiry,count(DISTINCT substr(datetime,12,5)) FROM candles "
            "WHERE underlying='SENSEX' AND interval='1minute' AND kind='future' "
            "AND datetime>=? AND datetime<? AND substr(datetime,12) BETWEEN ? AND ? "
            "AND substr(datetime,18,2)='00' AND close>0 "
            "GROUP BY 1,2", (FIRST, LAST + "z", START, FINISH),
        ):
            counts[day][expiry] = n
        pairs = defaultdict(list)
        for day, expiry, n in db.execute(
            "SELECT substr(datetime,1,10),expiry,count(DISTINCT opt) FROM candles "
            "WHERE underlying='SENSEX' AND interval='1minute' AND kind='option' "
            "AND datetime>=? AND datetime<? AND substr(datetime,12) BETWEEN ? AND ? "
            "AND opt IN ('CE','PE') AND volume>0 GROUP BY 1,2", (FIRST, LAST + "z", START, FINISH),
        ):
            if n == 2 and expiry > day:
                pairs[day].append(expiry)
    dates, exclusions = {}, Counter()
    for day in days:
        if not FIRST <= day <= LAST:
            continue
        manifest = manifests[day[:4]]
        own_option = at_or_after(manifest["weekly_expiry_calendar"], day)
        own_future = at_or_after(manifest["future_expiries"], day)
        if not own_option or not own_future or day in (own_option, own_future):
            exclusions["nifty_calendar"] += 1
            continue
        full = sorted(exp for exp, count in counts[day].items() if count == MINUTES and exp > day)
        if not full:
            exclusions["no_complete_sensex_future"] += 1
            continue
        if not pairs[day]:
            exclusions["no_two_sensex_option_rights"] += 1
            continue
        previous = days[bisect_left(days, day) - 1]
        assert previous < day
        dates[day] = {"prior": previous, "full_futures": full, "option_pairs": sorted(pairs[day])}
    return {"dates": dates, "exclusions": exclusions, "window": [FIRST, LAST],
            "nifty_manifest_sha256": {y: digest(DATASETS[y] / "manifest.json") for y in manifests}}


def source_report(day):
    filename = relative("BSE", day)
    cached = OLD / filename
    return cached if cached.is_file() else LOCAL / filename


def get(previous):
    target = source_report(previous)
    if target.is_file():
        return previous, "cached"
    url = BSE.format(date=previous.replace("-", ""))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(6_000_001)
        if len(data) > 6_000_000 or not data.startswith(b"Market Summary Date,"):
            return previous, "invalid_file_format"
        with target.open("xb") as handle:
            handle.write(data)
        return previous, "downloaded"
    except OSError as exc:
        return previous, f"{type(exc).__name__}: {exc}"


def catalogue(dates):
    output = {}
    for day, entry in dates.items():
        previous = entry["prior"]
        path = source_report(previous)
        if not path.is_file():
            output[day] = {"status": "missing_prior_bse_report"}
            continue
        try:
            sha, options, futures = parse("BSE", path, previous)
        except (AssertionError, KeyError, ValueError, UnicodeError) as exc:
            output[day] = {"status": "invalid_prior_bse_report", "error": type(exc).__name__}
            continue
        opt, fut = at_or_after(options, day), at_or_after(futures, day)
        if opt is None or fut is None or day in (opt, fut):
            status = "sensex_calendar"
        elif opt not in entry["option_pairs"] or fut not in entry["full_futures"]:
            status = "dated_series_clock_missing"
        else:
            status = "eligible"
        output[day] = {"status": status, "option": opt, "future": fut, "prior": previous, "prior_sha256": sha}
    return output


def registered_plan():
    path = LOCAL / "plan.json"
    freeze = read(HERE / "round36-data-inputs.json")
    assert digest(path) == freeze["plan_sha256"]
    return read(path)


def snapshot():
    registered_plan()
    items = {d: row for d, row in read(LOCAL / "catalogue.json").items() if row["status"] == "eligible"}
    assert items and all(FIRST <= day <= LAST for day in items)
    assert all(digest(source_report(row["prior"])) == row["prior_sha256"] for row in items.values())
    path, pending = LOCAL / "breeze.sqlite", LOCAL / "breeze.sqlite.part"
    assert not path.exists() and not pending.exists()
    futures = defaultdict(list)
    for day, row in items.items():
        futures[row["future"]].append(day)
    with closing(sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True, timeout=15)) as src, \
            closing(sqlite3.connect(pending)) as out:
        src.execute("PRAGMA query_only=ON")
        src.execute("BEGIN")
        out.execute("CREATE TABLE candles(kind TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,"
                    "low REAL,close REAL,volume REAL,oi REAL,PRIMARY KEY(kind,expiry,strike,opt,datetime))")
        insert = "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        for expiry, days in futures.items():
            warm = (date.fromisoformat(min(days)) - timedelta(days=30)).isoformat()
            rows = src.execute(f"SELECT {COLS} FROM candles WHERE underlying='SENSEX' AND interval='1minute' "
                               "AND kind='future' AND expiry=? AND datetime>=? AND datetime<? AND close>0 "
                               "AND substr(datetime,12) BETWEEN ? AND ?", (expiry, warm, max(days) + "z", START, TAIL))
            out.executemany(insert, rows)
        counts = {}
        for day, row in items.items():
            lower, upper = f"{day} {START}", f"{day} {FINISH}"
            marks = out.execute("SELECT count(*) FROM candles WHERE kind='future' AND expiry=? "
                                "AND datetime BETWEEN ? AND ?", (row["future"], lower, upper)).fetchone()[0]
            assert marks == MINUTES, (day, marks)
            candles = src.execute(f"SELECT {COLS} FROM candles WHERE underlying='SENSEX' AND interval='1minute' "
                                  "AND kind='option' AND expiry=? AND datetime BETWEEN ? AND ? AND close>0 "
                                  "AND volume>0 AND opt IN ('CE','PE')", (row["option"], lower, f"{day} {TAIL}"))
            inserted = out.executemany(insert, candles).rowcount
            assert inserted > 0, day
            counts[day] = {"future_rows": marks, "option_rows": inserted}
        out.execute("CREATE INDEX candles_clock ON candles(kind,expiry,datetime)")
        out.commit()
        assert out.execute("PRAGMA quick_check").fetchone() == ("ok",)
    pending.rename(path)
    spreads = read(HERE / "cross-index-coverage.json")["spread"]["quotes_by_premium_bin"]
    manifest = {"underlying": "SENSEX", "lot_size": 20, "sessions": sorted(items), "logged_regimes": {},
                "weekly_expiry_calendar": sorted({row["option"] for row in items.values()}),
                "future_expiries": sorted(futures), "day_contracts": items, "counts": counts,
                "data_sha256": digest(path), "catalogue_sha256": digest(LOCAL / "catalogue.json"),
                "spread": {key.split(":")[-1]: val for key, val in spreads.items() if key.startswith("SENSEX:")}}
    write(LOCAL / "manifest.json", manifest)
    print("snapshot sessions", len(items), "options", sum(row["option_rows"] for row in counts.values()), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("plan", "fetch", "catalogue", "snapshot"))
    args = parser.parse_args()
    LOCAL.mkdir(parents=True, exist_ok=True)
    if args.phase == "plan":
        output = plan()
        write(LOCAL / "plan.json", output)
        dates = output["dates"]
        print("metadata candidates", len(dates), "prior reports cached",
              sum(source_report(v["prior"]).is_file() for v in dates.values()), output["exclusions"], flush=True)
    elif args.phase == "fetch":
        dates = registered_plan()["dates"]
        previous = sorted({d["prior"] for d in dates.values()})
        assert len(previous) <= 245 and all("2025-06-01" <= day <= LAST for day in previous)
        (LOCAL / "exchange").mkdir(exist_ok=True)
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = dict(executor.map(get, previous))
        write(LOCAL / "acquisition.json", results)
        print("BSE reports", Counter(results.values()), flush=True)
    elif args.phase == "catalogue":
        output = catalogue(registered_plan()["dates"])
        write(LOCAL / "catalogue.json", output)
        print("dated verification", Counter(row["status"] for row in output.values()), flush=True)
    else:
        snapshot()


if __name__ == "__main__":
    main()
