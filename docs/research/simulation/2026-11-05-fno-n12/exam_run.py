"""Run the frozen N012 exam from a committed, prepared snapshot exactly once."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import exam_scoring


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = HERE / "_local/exam-2022-h1"
PRIOR = HERE.parent / "2026-11-05-fno-expiry-followup"
FREEZE = HERE / "exam-2022-h1-freeze.json"
REQUESTS = HERE / "exam-2022-h1-requests.json"
SNAPSHOT = HERE / "exam-2022-h1-snapshot.json"
INPUT_FILES = {"dataset/manifest.json", "dataset/breeze.sqlite", "daily.json"}
Q1, Q2 = "nifty-2022-q1-fno", "nifty-2022-q2-fno"


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def committed(path):
    tracked = subprocess.check_output(["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT)
    current = read(path)
    if json.loads(tracked) != current:
        raise ValueError(f"Uncommitted exam input: {path.name}")
    return current


def write_new(path, value):
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, sort_keys=True, default=str)
        file.write("\n")


def request_intervals(rows, window):
    shapes = {"daily": 4, "index": 4, "future": 5, "option": 7}
    intervals = defaultdict(list)
    warm_start = (date.fromisoformat(window[0]) - timedelta(days=21)).isoformat()
    for row in rows:
        kind, name, *terms = row["key"].split("|")
        if len(terms) + 2 != shapes.get(kind) or name not in {"NIFTY", "BANKNIFTY"} or (name == "BANKNIFTY" and kind != "daily"):
            raise ValueError(f"Invalid request scope: {row['key']}")
        first, last = terms[-2:]
        scope_start = warm_start if kind == "future" else "2022-01-01" if kind == "daily" else window[0]
        if (any(date.fromisoformat(day).isoformat() != day for day in (first, last))
                or first > last or first > window[1] or last < scope_start):
            raise ValueError(f"Request is outside the selected data scope: {row['key']}")
        expiry = terms[0] if kind in {"future", "option"} else ""
        if expiry and date.fromisoformat(expiry).isoformat() != expiry:
            raise ValueError(f"Invalid contract expiry: {row['key']}")
        right = terms[2] if kind == "option" else ""
        if kind == "option" and (right not in {"CE", "PE"} or Decimal(terms[1]) <= 0):
            raise ValueError(f"Invalid option contract: {row['key']}")
        if row["status"] == "ok" and row["rows"] > 0:
            intervals[kind, name, expiry, right].append((first, last))
    return intervals


def validate_metadata(freeze, requests, snapshot, request_sha):
    window = requests["window"]
    fallback = requests.get("q1_unavailability")
    if window == freeze["primary_window"]:
        expected_checks = {Q1: "CHECK CLEAN", Q2: "CHECK CLEAN"}
        if fallback:
            raise ValueError("The primary exam cannot use the Q1 fallback declaration")
    elif window == freeze["partial_window"] and isinstance(fallback, str) and fallback.strip():
        expected_checks = {Q2: "CHECK CLEAN"}
    else:
        raise ValueError("Unregistered window or missing prior Q1 unavailability declaration")
    if requests["target_checks"] != expected_checks:
        raise ValueError("The selected guarded targets do not have clean coverage")
    if snapshot["window"] != window or snapshot["request_manifest_sha256"] != request_sha:
        raise ValueError("Snapshot does not match the committed request manifest")
    keys = [row["key"] for row in requests["requests"]]
    if not keys or keys != sorted(set(keys)) or any(row["status"] not in {"ok", "empty"}
                                                   for row in requests["requests"]):
        raise ValueError("Request keys must be finished, unique and ordered")
    intervals = request_intervals(requests["requests"], window)
    sessions = requests["sessions"]
    if not sessions or sessions != sorted(set(sessions)) or any(
        date.fromisoformat(day).isoformat() != day or not window[0] <= day <= window[1] for day in sessions
    ):
        raise ValueError("Invalid requested session list")
    if set(sessions) != set(snapshot["coverage"]) or set(snapshot["files"]) != INPUT_FILES:
        raise ValueError("Snapshot omits expected coverage or files")
    option_sessions = []
    for day in sessions:
        row = snapshot["coverage"][day]
        future, weekly = row["front_future"], row["weekly_option"]
        if (row["index_missing_minutes"] or row["front_missing_minutes"] or
                date.fromisoformat(future).isoformat() != future or date.fromisoformat(weekly).isoformat() != weekly or
                min(future, weekly) < day):
            raise ValueError(f"Incomplete index, future or contract identity on {day}")
        if day != weekly:
            if sorted(row["option_rights"]) != ["CE", "PE"]:
                raise ValueError(f"Missing dated option rights on {day}")
            option_sessions.append(day)
        required = [("index", "NIFTY", "", ""), ("future", "NIFTY", future, ""),
                    ("daily", "NIFTY", "", ""), ("daily", "BANKNIFTY", "", "")]
        if day != weekly:
            required += [("option", "NIFTY", weekly, right) for right in ("CE", "PE")]
        if any(not any(first <= day <= last for first, last in intervals[scope]) for scope in required):
            raise ValueError(f"Missing completed request provenance on {day}")
    return option_sessions


def check_snapshot(work, requests, snapshot):
    for name, expected in snapshot["files"].items():
        if digest(work / name) != expected:
            raise ValueError(f"Changed snapshot file: {name}")
    manifest = read(work / "dataset/manifest.json")
    coverage = snapshot["coverage"]
    weeks = manifest["weekly_expiry_calendar"]
    futures = manifest["future_expiries"]
    if (manifest["underlying"] != "NIFTY" or manifest["lot_size"] != 65 or manifest["logged_regimes"] or
            manifest["window"] != requests["window"] or manifest["sessions"] != requests["sessions"] or
            manifest["files_sha256"]["breeze.sqlite"] != snapshot["files"]["dataset/breeze.sqlite"] or
            not set(manifest["option_expiries"]).issubset(weeks) or
            weeks != sorted(set(weeks)) or futures != sorted(set(futures))):
        raise ValueError("Wrong dataset, sessions, calendar or replay assumptions")
    for day, row in coverage.items():
        if (next((value for value in weeks if value >= day), None) != row["weekly_option"] or
                next((value for value in futures if value >= day), None) != row["front_future"]):
            raise ValueError(f"Dated expiry mismatch: {day}")


class ToleranceAudit:
    def _entry(self, book, obs, frame, day, now):
        before, ticket = self.notes["n11t_second_lots"], book.next_id
        result = super()._entry(book, obs, frame, day, now)
        if self.notes["n11t_second_lots"] != before:
            leg = book.open.get(ticket)
            if self.notes["n11t_second_lots"] != before + 1 or book.next_id != ticket + 1 or leg is None or leg.lots != 2:
                raise ValueError("Tolerance counter did not match a committed initial two-lot entry")
            self.tolerance_entries.append((leg.tradingsymbol, leg.entry_time))
        return result


def evaluator(arms, work, requests, freeze):
    f, y = arms.r.f, arms.Y
    prior = sys.modules["nifty_2022"]
    window, dataset, daily = tuple(requests["window"]), work / "dataset", work / "daily.json"
    warmup = prior.EXAM / "pre-2022-warmup.json"
    if digest(warmup) != freeze["warmup_sha256"]:
        raise ValueError("Changed pre-2022 daily warm-up")
    daily_rows = read(daily)["rows"]
    dates = [row[0] for row in daily_rows]
    if (dates != sorted(set(dates)) or [row for row in daily_rows if row[0] < "2022-01-01"] != read(warmup)["rows"]["NIFTY"] or
            dates[-1] > window[1] or not set(requests["sessions"]).issubset(dates)):
        raise ValueError("Daily gate data differs from the frozen warm-up or expected sessions")

    prior.lab.POINTS["TEST2025"].update(dataset=dataset, window=window, daily=daily)
    prior.lab.GAP.DAILY = daily
    prior.lab.C.WINDOW = window
    y.YEAR = dataset
    y.CACHES["year"] = work / "observations"
    y._DATA.clear()
    y._TABLES.clear()
    y._NAMED_MEMO["year"] = {}
    prior.lab.C._CASE_TABLE.clear()
    prior.lab.X.G._TABLE.clear()
    f.Z.DAILY_SOURCES = (daily,)
    f.Z.vol_table.cache_clear()
    f.L.U.paper_rows = tuple
    f.L.paper_stream.cache_clear()
    y.O27F.deny_network()
    y.speedups()
    from config import settings
    settings.FNO_PAPER_BANKROLL = freeze["historical_bankroll"]
    data, table = y.dataset("year"), y.table("year")
    if any((table.get(day, {}).get("side") or {}).get("adx_abs30") not in {"HIGH", "LOW"}
           for day in requests["sessions"]):
        raise ValueError("Missing daily gate readings")

    def run(name, model):
        base = arms.trend.TrendReplay if name == arms.A else y.BookReplay

        class AuditedReplay(ToleranceAudit, base):
            pass

        with y.ROUTER.dispatch():
            engine = AuditedReplay(data, model, table, "year")
            engine.tolerance_entries = []
            result = engine.run(*window)
        if result["notes"].get("start_equity") != freeze["historical_bankroll"]:
            raise ValueError("Exam arm did not start at its frozen allocation")
        for row in result["trades"]:
            row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
        if len(set(engine.tolerance_entries)) != result["notes"].get("n11t_second_lots", 0):
            raise ValueError("Tolerance entry audit differs from replay count")
        result["tolerance_entries"] = engine.tolerance_entries
        return result

    def bind_history(history):
        rows = tuple(sorted(((datetime.fromisoformat(row["exit_time"]), row) for row in history["trades"]
                             if row["status"] == "CLOSED"), key=lambda item: (item[0], item[1]["entry_time"])))
        f.L.U.paper_rows = lambda: rows
        f.L.paper_stream.cache_clear()

    return run, bind_history, prior.books()["paper_history"]


def run_arms(work, freeze, books, run, bind_history, history_model):
    history = run("paper_history", history_model)
    write_new(work / "paper_history.json", history)
    if any(row["status"] != "CLOSED" for row in history["trades"]):
        raise ValueError("Incomplete paper reference")
    bind_history(history)
    outputs = {}
    for name, stress in (("N11", False), ("N11T", False), ("N012-A", False), ("N11T", True), ("N012-A", True)):
        label = f"{name}-doubled" if stress else name
        cost = freeze["doubled_extra_cost"] if stress else freeze["standard_extra_cost"]
        model = {**books[name], "label": label, "cost": cost}
        outputs[label] = run(name, model)
        write_new(work / f"{label}.json", outputs[label])
    return outputs


def combined_2022(results, summaries, legacy, prior_option_sessions, option_sessions, legacy_freeze):
    count = len(results["N11T"]["tolerance_entries"]) + legacy["N11T"]["notes"].get("n11t_second_lots", 0)
    days = prior_option_sessions + len(option_sessions)
    return {
        "two_independent_windows_net": {
            name: summaries[name]["net"] + Decimal(str(legacy[key]["net"]))
            for name, key in (("N11", "N11"), ("N11T", "N11T"), ("N012-A", "TREND_ONLY"))
        },
        "reported_june_december_option_dates": prior_option_sessions,
        "exam_option_dates": len(option_sessions),
        "combined_reported_option_dates": days,
        "clears_200_using_reported_dates": days >= legacy_freeze["minimum_option_sessions"],
        "combined_n11t_tolerance_entries": count,
        "clears_10_tolerance_entries": count >= legacy_freeze["minimum_tolerance_trades"],
    }


def claim_once(work, window, request_sha, snapshot_sha, revision):
    work.mkdir(parents=True, exist_ok=True)
    write_new(work / "started.json", {"window": window, "request_sha256": request_sha,
                                     "snapshot_sha256": snapshot_sha, "commit": revision})


def main():
    freeze, requests, snapshot = (committed(path) for path in (FREEZE, REQUESTS, SNAPSHOT))
    for path in (Path(__file__), HERE / "exam_scoring.py"):
        if digest(path) != requests["sources"][path.name]:
            raise ValueError(f"Changed runner source: {path.name}")
    request_sha = digest(REQUESTS)
    dates = validate_metadata(freeze, requests, snapshot, request_sha)
    os.environ["N12_YEAR"] = "2022"
    import n012_ab as arms

    arms.validate_freeze()
    legacy = committed(HERE / "round30-2022.json")
    legacy_result = committed(PRIOR / "nifty-2022-results.json")
    legacy_freeze = committed(PRIOR / "nifty-2022-freeze.json")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    claim_once(WORK, requests["window"], request_sha, digest(SNAPSHOT), revision)
    check_snapshot(WORK, requests, snapshot)
    run, bind_history, history = evaluator(arms, WORK, requests, freeze)
    results = run_arms(WORK, freeze, arms.frozen_models(), run, bind_history, history)
    scores = exam_scoring.score(*(results[name]["trades"] for name in
                                  ("N11T", "N012-A", "N11T-doubled", "N012-A-doubled")), freeze)
    summaries = {"N11": exam_scoring.summarize(results["N11"]["trades"], Decimal(freeze["historical_bankroll"])),
                 "N11T": scores["summaries"]["control"], "N012-A": scores["summaries"]["candidate"]}
    report = {"window": requests["window"], "n11": summaries["N11"], "score": scores,
              "option_sessions": dates, "combined_2022": combined_2022(
                  results, summaries, legacy, legacy_result["options_sessions"], dates, legacy_freeze)}
    write_new(WORK / "result.json", report)
    print(scores["verdict"], "delta", scores["net_delta"], "doubled delta", scores["doubled_cost_delta"])


if __name__ == "__main__":
    main()
