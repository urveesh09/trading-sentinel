"""Run the matched 2021 NIFTY validation from a committed archive binding."""

from contextlib import closing
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from math import isfinite
from pathlib import Path
import sqlite3
import subprocess
import sys

from exam_run import HERE, INPUT_FILES, PRIOR, ROOT, ToleranceAudit, committed, digest, read, write_new
from exam_scoring import summarize


WINDOW = ("2021-08-02", "2021-12-31")
SEED = "2021-07-30"
HOLIDAYS = {"2021-08-19", "2021-09-10", "2021-10-15", "2021-11-04", "2021-11-05", "2021-11-19"}
FUTURES = ("2021-08-26", "2021-09-30", "2021-10-28", "2021-11-25", "2021-12-30", "2022-01-27")
BANKROLL = 250_000
MINIMUM_TRADES = 15
WORK = HERE / "_local/prior-range-2021"
BINDING = HERE / "prior-range-2021-inputs.json"
PROTOCOL = HERE / "PRIOR_RANGE_2021.md"
COSTS = {"standard": [200., 5.], "doubled": [400., 10.]}


def calendar():
    first, last = map(date.fromisoformat, WINDOW)
    dates = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    sessions = [day.isoformat() for day in dates if day.weekday() < 5 and day.isoformat() not in HOLIDAYS]
    weekly = [(day - timedelta(days=day.isoformat() in HOLIDAYS)).isoformat()
              for day in dates if day.weekday() == 3]
    return tuple(sessions), (*weekly, "2022-01-06")


def validate_inputs(work, binding):
    if (binding.get("window") != list(WINDOW) or binding.get("prior_session") != SEED
            or not binding.get("provenance") or set(binding.get("files", ())) != INPUT_FILES):
        raise ValueError("Input binding differs from the frozen 2021 scope or lacks provenance")
    for name, expected in binding["files"].items():
        if digest(work / name) != expected:
            raise ValueError(f"Changed 2021 snapshot input: {name}")
    db = work / "dataset/breeze.sqlite"
    if any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("The archive must be a standalone SQLite file")
    sessions, weekly = calendar()
    manifest = read(work / "dataset/manifest.json")
    if (manifest.get("underlying") != "NIFTY" or manifest.get("lot_size") != 50
            or manifest.get("sessions") != list(sessions) or manifest.get("weekly_expiry_calendar") != list(weekly)
            or manifest.get("option_expiries") != list(weekly)
            or manifest.get("future_expiries") != list(FUTURES) or manifest.get("logged_regimes") != {}):
        raise ValueError("Archive calendar, contract lot, or regime provenance differs from frozen scope")
    return sessions


def validate_sources(revision):
    # Pin the strategy, native controls, and their imports to the evaluated Dev source.
    if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
        raise ValueError("A full frozen Dev commit is required")
    paths = ["python-engine", "docs/research/fno", ":(glob)docs/research/simulation/**/*.py",
             ":(glob)docs/research/simulation/**/*.json", PROTOCOL.relative_to(ROOT).as_posix(),
             ":(exclude)" + BINDING.relative_to(ROOT).as_posix()]
    subprocess.run(["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=ROOT, check=True)
    subprocess.run(["git", "diff", "--exit-code", revision, "--", *paths], cwd=ROOT, check=True)


def settings_fingerprint():
    sys.path.insert(0, str(ROOT / "python-engine"))
    from config import settings

    fields = {key: value for key, value in settings.model_dump(mode="json").items() if key.startswith("FNO_")}
    fields["FNO_PAPER_BANKROLL"] = BANKROLL
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def qualify_data(data, daily, sessions, seed):
    rows = read(daily)["rows"]
    dates = [row[0] for row in rows]
    if (dates != sorted(set(dates)) or not set(sessions).issubset(dates) or dates[-1] != sessions[-1]
            or sum(day < sessions[0] for day in dates) < 150
            or any(len(row) != 5 or any(not isfinite(value) or value <= 0 for value in row[1:]) for row in rows)):
        raise ValueError("Daily series lacks the frozen session scope or 150 prior NIFTY bars")
    with closing(data._connect()) as db:
        for previous, day in zip((seed, *sessions[:-1]), sessions):
            front = data.front_expiry(date.fromisoformat(day)).isoformat()
            expiry = next(value.isoformat() for value in data.option_expiries()[0] if value.isoformat() >= day)
            history_start = (date.fromisoformat(day) - timedelta(days=21)).isoformat()
            history, = db.execute("SELECT COUNT(DISTINCT substr(datetime,1,10)) FROM candles WHERE kind='future' "
                                  "AND expiry=? AND datetime>=? AND datetime<? AND volume>0",
                                  (front, history_start, day)).fetchone()
            if history < 5:
                raise ValueError(f"Fewer than five dated-future warm-up sessions: {front} {day}")
            for kind, contract, session in (("index", "", day), ("future", front, day), ("future", front, previous)):
                clocks = db.execute("SELECT datetime FROM candles WHERE kind=? AND expiry=? "
                                    "AND datetime BETWEEN ? AND ?", (kind, contract, f"{session} 09:15:00",
                                                                      f"{session} 15:29:00"))
                expected = datetime.fromisoformat(f"{session} 09:15:00")
                if sorted(stamp for stamp, in clocks) != [(expected + timedelta(minutes=i)).isoformat(sep=" ")
                                                          for i in range(375)]:
                    raise ValueError(f"Incomplete minute clocks: {kind} {contract} {session}")
            rights = db.execute("SELECT DISTINCT opt FROM candles WHERE kind='option' AND expiry=? "
                                "AND datetime BETWEEN ? AND ? AND volume>0", (expiry, f"{day} 09:15:00", f"{day} 15:29:00"))
            if {right for right, in rights} != {"CE", "PE"}:
                raise ValueError(f"Incomplete option sides: {expiry} {day}")


def controls(work, cache, sessions, seed):
    # Start in a fresh process. These legacy replay modules patch research globals.
    sys.path.insert(0, str(PRIOR))
    import nifty_2022 as prior
    from config import settings

    f, y = prior.final, prior.final.Y
    window, dataset, daily = (sessions[0], sessions[-1]), work / "dataset", work / "daily.json"
    prior.lab.POINTS["TEST2025"].update(dataset=dataset, window=window, daily=daily)
    prior.lab.GAP.DAILY = daily
    prior.lab.C.WINDOW = window
    y.YEAR = dataset
    y.CACHES["year"] = cache
    y._DATA.clear()
    y._TABLES.clear()
    y._NAMED_MEMO["year"] = {}
    prior.lab.C._CASE_TABLE.clear()
    prior.lab.X.G._TABLE.clear()
    f.Z.DAILY_SOURCES = (daily,)
    f.Z.vol_table.cache_clear()
    f.L.U.paper_rows = tuple
    f.L.paper_stream.cache_clear()
    settings.FNO_PAPER_BANKROLL = BANKROLL
    y.O27F.deny_network()
    y.speedups()
    data = y.dataset("year")
    qualify_data(data, daily, sessions, seed)
    table = y.table("year")
    if any((table.get(day, {}).get("side") or {}).get("adx_abs30") not in {"HIGH", "LOW"} for day in sessions):
        raise ValueError("Missing native daily ADX gate readings")

    class AuditedReplay(ToleranceAudit, y.BookReplay):
        pass

    def run(name, model, stress):
        with y.ROUTER.dispatch():
            engine = AuditedReplay(data, {**model, "label": name, "cost": COSTS[stress]}, table, "year")
            engine.tolerance_entries = []
            result = engine.run(*window)
        if (result["notes"].get("start_equity") != BANKROLL or result["sessions"] != len(sessions)
                or result["notes"].get("session_without_observations", 0)):
            raise ValueError(f"{name} did not replay the funded session scope")
        for row in result["trades"]:
            row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
        if len(set(engine.tolerance_entries)) != result["notes"].get("n11t_second_lots", 0):
            raise ValueError(f"{name} tolerance audit differs from replay count")
        result["tolerance_entries"] = engine.tolerance_entries
        return result

    books = prior.books()
    history = run("paper_history", books["paper_history"], "standard")
    if any(row["status"] != "CLOSED" for row in history["trades"]):
        raise ValueError("Incomplete native paper reference")
    rows = tuple(sorted(((datetime.fromisoformat(row["exit_time"]), row) for row in history["trades"]),
                        key=lambda item: (item[0], item[1]["entry_time"])))
    f.L.U.paper_rows = lambda: rows
    f.L.paper_stream.cache_clear()
    outputs = {stress: {name: run(name, books[name], stress) for name in ("N11", "N11T")} for stress in COSTS}
    return data, history, outputs


def score(native, sleeve):
    all_native = [book for costs in native.values() for book in costs.values()]
    if (any(row["status"] != "CLOSED" for book in all_native for row in book["trades"])
            or any(not book["complete"] for book in sleeve.values())):
        return {"verdict": "incomplete"}
    summaries = {}
    for stress, books in native.items():
        rows = [{**row, "status": "CLOSED"} for row in sleeve[stress]["days"].values() if row["status"] == "closed"]
        summaries[stress] = {name: summarize(book["trades"], Decimal(BANKROLL)) for name, book in books.items()}
        summaries[stress]["reclaim"] = summarize(rows, Decimal(BANKROLL))
    reclaim, n11t = (summaries["standard"][name] for name in ("reclaim", "N11T"))
    without_best = reclaim["net"] - max(0, max(reclaim["daily"].values(), default=0))
    gates = {"positive_net": reclaim["net"] > 0, "positive_without_best_day": without_best > 0,
             "positive_doubled_cost_net": summaries["doubled"]["reclaim"]["net"] > 0,
             "worst_day": n11t["worst_day"] - reclaim["worst_day"] <= 1000,
             "closed_drawdown": reclaim["drawdown_pct"] - n11t["drawdown_pct"] <= 1}
    verdict = "insufficient" if reclaim["closed"] < MINIMUM_TRADES else ("pass" if all(gates.values()) else "fail")
    deltas = {stress: {name: arms["reclaim"]["net"] - arms[name]["net"] for name in ("N11", "N11T")}
              for stress, arms in summaries.items()}
    return {"verdict": verdict, "gates": gates, "net_excluding_best_day": without_best,
            "standalone_net_deltas": deltas, "summaries": summaries}


def main():
    if sys.argv[1:] == ["--settings-fingerprint"]:
        print(settings_fingerprint())
        return
    if sys.argv[1:]:
        raise SystemExit("Usage: reclaim_2021.py [--settings-fingerprint]")
    if not BINDING.is_file():
        raise SystemExit(f"2021 archive awaits a committed input binding at {BINDING}")
    binding = committed(BINDING)
    validate_sources(binding["source_revision"])
    if binding.get("settings_sha256") != settings_fingerprint():
        raise ValueError("Effective F&O settings differ from the committed fingerprint")
    sessions = validate_inputs(WORK, binding)
    output = WORK / "evaluation"
    output.mkdir()  # Exclusive one-shot claim. Even an interrupted exam leaves the directory behind.
    write_new(output / "started.json", {"binding_sha256": digest(BINDING), "source_revision": binding["source_revision"]})
    data, history, native = controls(WORK, output / "observations", sessions, SEED)
    from reclaim_minute import replay_stresses

    sleeve = replay_stresses(data, (SEED, *sessions), allocation=BANKROLL)
    validate_inputs(WORK, binding)
    write_new(output / "controls.json", {"paper_history": history, "arms": native})
    write_new(output / "reclaim.json", sleeve)
    write_new(output / "score.json", score(native, sleeve))


if __name__ == "__main__":
    main()
