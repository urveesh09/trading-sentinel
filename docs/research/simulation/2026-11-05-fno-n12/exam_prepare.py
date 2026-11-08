"""Capture the guarded request ledger, then export the committed one-shot scope."""

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess

import exam_run as exam


ARCHIVE = Path.home() / "sentinel-operations/breeze-history-20261029"
SOURCE = ARCHIVE / "data/breeze-history.sqlite"
GUARD = Path.home() / ".agents/skills/breeze-history-download/scripts/breeze.cmd"
WARMUP = exam.PRIOR / "_local/nifty-2022/pre-2022-warmup.json"
FALLBACK = exam.HERE / "exam-2022-q1-unavailable.json"
MINUTES = {f"{n // 60:02d}:{n % 60:02d}:00" for n in range(9 * 60 + 15, 15 * 60 + 11)}
MONEY_FIELDS = "open,high,low,close,volume,oi"


def no_downloader():
    if os.environ.get("BREEZE_WORKSPACE"):
        raise ValueError("The exam requires the standard guarded history workspace")
    result = subprocess.run(["cmd.exe", "/d", "/c", str(GUARD), "status"], check=True,
                            capture_output=True, text=True, timeout=30)
    if "lock held: False" not in result.stdout:
        raise ValueError("Stop snapshot work while the guarded downloader is active or its status is unclear")


def guarded_checks(logs, targets):
    checks = {}
    for target in targets:
        path = logs / f"check-{target}-latest.json"
        if not path.is_file():
            raise ValueError(f"{target} has no saved full guarded coverage check")
        receipt = exam.read(path)
        structural = receipt.get("structural") or {}
        if (receipt["target"] != target or receipt["clean"] is not True or receipt["incomplete"] is not False
                or structural.get("sqlite_quick_check") != "ok" or structural.get("new_issues") != {}):
            raise ValueError(f"{target} requires a completed clean full guarded check")
        checks[target] = {"at": receipt["at"], "sha256": exam.digest(path),
                          "sqlite_quick_check": structural["sqlite_quick_check"], "new_issues": {}}
    return checks


def date_range(first, last):
    first, last = date.fromisoformat(first), date.fromisoformat(last)
    return {(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)}


def scope(calendar, window):
    first, last = window
    daily = [day for day in calendar["sessions"] if day <= last]
    trading_days = set(daily)
    sessions = [day for day in daily if day >= first]
    allowed = {("index", "NIFTY", ""): set(sessions), ("daily", "NIFTY", ""): set(daily),
               ("daily", "BANKNIFTY", ""): set(daily)}
    coverage = {}
    for day in sessions:
        front = exam.nearest(calendar["front_future_expiries"], day)
        week = exam.nearest(calendar["weekly_expiry_calendar"], day)
        if front is None or week is None:
            raise ValueError(f"Incomplete dated NSE calendar: {day}")
        before = (date.fromisoformat(day) - timedelta(days=21)).isoformat()
        prior_days = {value for value in date_range(before, day) if value in trading_days or
                      (value < "2022-01-01" and date.fromisoformat(value).weekday() < 5)}
        allowed.setdefault(("future", "NIFTY", front), set()).update(prior_days)
        if day < week:
            allowed.setdefault(("option", "NIFTY", week), set()).add(day)
        coverage[day] = {"front_future": front, "weekly_option": week}
    return sessions, allowed, coverage


def parse_key(key):
    kind, name, *terms = key.split("|")
    expiry = terms[0] if kind in {"future", "option"} else ""
    strike, right = (float(terms[1]), terms[2]) if kind == "option" else (0., "")
    return (kind, name, expiry, strike, right, "1day" if kind == "daily" else "1minute"), terms[-2:]


def selected_requests(source, allowed):
    rows = []
    groups = defaultdict(set)
    for key, status, count, returned, at in source.execute(
        "SELECT key,status,rows,returned_expiry,at FROM requests "
        "WHERE key LIKE '%|NIFTY|%' OR key LIKE 'daily|BANKNIFTY|%' ORDER BY key"
    ):
        series, (first, last) = parse_key(key)
        days = {day for day in allowed.get(series[:3], ()) if first <= day <= last}
        if not days:
            continue
        if status not in {"ok", "empty"}:
            raise ValueError(f"Unfinished scoped request: {key}")
        rows.append({"key": key, "status": status, "rows": count, "returned_expiry": returned, "at": at})
        if status == "ok" and count > 0:
            groups[series].update(days)
    return rows, groups


def selected_candles(source, groups, *, prices):
    columns = MONEY_FIELDS if prices else "volume"
    for series, days in sorted(groups.items()):
        for clock, *fields in source.execute(
            f"SELECT datetime,{columns} FROM candles WHERE kind=? AND underlying=? AND expiry=? AND strike=? "
            "AND opt=? AND interval=? AND datetime>=? AND datetime<? ORDER BY datetime",
            (*series, min(days), max(days) + "z"),
        ):
            stamp = clock[11:]
            if clock[:10] not in days:
                continue
            if series[0] != "daily" and not ("09:15:00" <= stamp <= "15:29:00" and stamp.endswith(":00")):
                continue
            yield series, clock, fields


def observed_coverage(rows, expected, allowed):
    times, options, preroll = defaultdict(set), defaultdict(set), defaultdict(set)
    fingerprint = hashlib.sha256()
    for series, clock, (volume,) in rows:
        kind, name, expiry, _strike, right, _ = series
        fingerprint.update(repr((series, clock, volume)).encode("ascii") + b"\n")
        day, time = clock[:10], clock[11:]
        if kind == "daily":
            times[kind, name].add(day)
        elif kind == "future":
            times[kind, expiry, day].add(time)
            preroll[expiry].add(day)
        elif kind == "index":
            times[kind, "", day].add(time)
        elif "09:45:00" <= time < "14:45:00" and volume > 0:
            options[day].add(right)
    for name in ("NIFTY", "BANKNIFTY"):
        if times["daily", name] != allowed["daily", name, ""]:
            raise ValueError(f"Missing scoped 2022 daily dates for {name}")
    coverage = {day: {
        **row,
        "index_missing_minutes": len(MINUTES - times["index", "", day]),
        "front_missing_minutes": len(MINUTES - times["future", row["front_future"], day]),
        "front_prior_sessions": sum(day > earlier >= (date.fromisoformat(day) - timedelta(days=21)).isoformat()
                                    for earlier in preroll[row["front_future"]]),
        "option_rights": sorted(options[day]),
    } for day, row in expected.items()}
    return coverage, fingerprint.hexdigest()


def verify_capture(freeze, requests, calendar, coverage):
    metadata = {"window": requests["window"], "request_manifest_sha256": "pending",
                "coverage": coverage, "files": dict.fromkeys(exam.INPUT_FILES)}
    exam.validate_metadata(freeze, requests, metadata, "pending")
    exam.validate_calendar(requests, metadata, calendar)


def validate_check_times(rows, checks):
    for row in rows:
        end = row["key"].split("|")[-1]
        target = exam.Q1 if exam.Q1 in checks and end <= "2022-03-31" else exam.Q2
        if datetime.fromisoformat(row["at"]) > datetime.fromisoformat(checks[target]["at"]):
            raise ValueError(f"Guarded coverage predates a scoped request for {target}")


def prepare_metadata(source, freeze, calendar, window, checks, unavailable):
    sessions, allowed, expected = scope(calendar, window)
    rows, groups = selected_requests(source, allowed)
    validate_check_times(rows, checks)
    coverage, fingerprint = observed_coverage(selected_candles(source, groups, prices=False), expected, allowed)
    requests = {
        "window": window, "sessions": sessions, "requests": rows, "coverage": coverage, "coverage_sha256": fingerprint,
        "q1_unavailability": unavailable,
        "target_checks": dict.fromkeys(checks, "CHECK CLEAN"), "guard_evidence": checks,
    }
    verify_capture(freeze, requests, calendar, coverage)
    return requests


def export_data(source, work, requests, calendar, warmup):
    sessions, allowed, expected = scope(calendar, requests["window"])
    current, groups = selected_requests(source, allowed)
    if current != requests["requests"]:
        raise ValueError("Scoped request ledger changed after the capture")
    checks, fingerprint = observed_coverage(selected_candles(source, groups, prices=False), expected, allowed)
    if checks != requests["coverage"] or fingerprint != requests["coverage_sha256"]:
        raise ValueError("Scoped minute or daily coverage changed after the capture")

    dataset = work / "dataset"
    dataset.mkdir()
    db = dataset / "breeze.sqlite"
    daily = {name: list(values) for name, values in warmup["rows"].items()}
    option_expiries = set()

    def output_rows():
        for (kind, name, expiry, strike, right, _), clock, fields in selected_candles(source, groups, prices=True):
            if kind == "daily":
                daily[name].append([clock[:10], *fields[:4]])
                continue
            if kind == "option":
                option_expiries.add(expiry)
            yield kind, expiry, strike, right, clock, *fields

    with closing(sqlite3.connect(db)) as dest, dest:
        dest.execute("CREATE TABLE candles(kind TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,"
                     "open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL,"
                     "PRIMARY KEY(kind,expiry,strike,opt,datetime))")
        dest.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)", output_rows())
        dest.execute("CREATE INDEX candles_clock ON candles(kind,expiry,datetime)")
        if dest.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("Prepared SQLite file failed its integrity check")
    exam.write_new(work / "daily.json", {"rows": daily["NIFTY"], "bank_rows": daily["BANKNIFTY"]})
    exam.write_new(dataset / "manifest.json", {
        "window": requests["window"], "sessions": sessions, "underlying": "NIFTY", "lot_size": 65,
        "option_expiries": sorted(option_expiries), "weekly_expiry_calendar": calendar["weekly_expiry_calendar"],
        "future_expiries": sorted({row["front_future"] for row in expected.values()}), "logged_regimes": {},
        "files_sha256": {"breeze.sqlite": exam.digest(db)},
    })
    return {"window": requests["window"], "coverage": checks, "coverage_sha256": fingerprint,
            "files": {name: exam.digest(work / name) for name in sorted(exam.INPUT_FILES)}}


def source_open():
    source = sqlite3.connect(SOURCE.as_uri() + "?mode=ro", uri=True, timeout=3)
    source.execute("PRAGMA query_only=ON")
    source.execute("BEGIN")
    return source


def metadata_only(action, table, column, *_):
    if action == sqlite3.SQLITE_READ and table == "candles" and column in {"open", "high", "low", "close", "oi"}:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def sources():
    return {path.name: exam.digest(path) for path in (Path(__file__), exam.HERE / "exam_run.py",
                                                       exam.HERE / "exam_scoring.py")}


def capture(freeze, calendar, april_may):
    fallback = exam.committed(FALLBACK)["q1_unavailability"] if april_may else None
    if exam.REQUESTS.exists() or (exam.WORK / "started.json").exists():
        raise FileExistsError("Exam request or scoring record already exists")
    window = freeze["partial_window" if april_may else "primary_window"]
    checks = guarded_checks(ARCHIVE / "run-logs", (exam.Q2,) if april_may else (exam.Q1, exam.Q2))
    no_downloader()
    with closing(source_open()) as source:
        source.set_authorizer(metadata_only)
        requests = prepare_metadata(source, freeze, calendar, window, checks, fallback)
    exam.write_new(exam.REQUESTS, {**requests, "calendar_sha256": exam.digest(exam.CALENDAR),
                                  "freeze_sha256": exam.digest(exam.FREEZE), "sources": sources()})
    print(f"Captured {len(requests['requests'])} finished requests for {len(requests['sessions'])} sessions.")


def snapshot(freeze, calendar):
    requests = exam.committed(exam.REQUESTS)
    if (requests["sources"] != sources() or requests["calendar_sha256"] != exam.digest(exam.CALENDAR)
            or requests["freeze_sha256"] != exam.digest(exam.FREEZE) or exam.digest(WARMUP) != freeze["warmup_sha256"]):
        raise ValueError("Captured source, calendar, strategy freeze or warm-up changed")
    if requests.get("q1_unavailability") and exam.committed(FALLBACK)["q1_unavailability"] != requests["q1_unavailability"]:
        raise ValueError("The prior Q1 unavailability declaration changed")
    if exam.SNAPSHOT.exists() or (exam.WORK / "started.json").exists():
        raise FileExistsError("Exam snapshot or scoring record already exists")
    verify_capture(freeze, requests, calendar, requests["coverage"])
    no_downloader()
    exam.WORK.mkdir(parents=True, exist_ok=True)
    request_sha = exam.digest(exam.REQUESTS)
    exam.write_new(exam.WORK / "prepare-started.json", {"request_sha256": request_sha})
    with closing(source_open()) as source:
        result = export_data(source, exam.WORK, requests, calendar, exam.read(WARMUP))
    result["request_manifest_sha256"] = request_sha
    exam.check_snapshot(exam.WORK, requests, result)
    exam.write_new(exam.SNAPSHOT, result)
    print(f"Prepared {len(result['coverage'])} sessions and verified {len(result['files'])} local files.")


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("action", choices=("capture", "snapshot"))
    parser.add_argument("--april-may", action="store_true")
    args = parser.parse_args()
    if args.april_may and args.action != "capture":
        parser.error("The fallback can be selected only at metadata capture")
    freeze, calendar = exam.committed(exam.FREEZE), exam.committed(exam.CALENDAR)
    if args.action == "capture":
        capture(freeze, calendar, args.april_may)
    else:
        snapshot(freeze, calendar)


if __name__ == "__main__":
    main()
