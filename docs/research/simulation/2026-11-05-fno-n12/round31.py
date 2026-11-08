"""A fixed-clock directional screen on known RBI policy decision days."""

from collections import Counter
from contextlib import closing
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from anatomy import DATASETS
from round25 import digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MARKS = ("09:59:00", "10:09:00", "10:11:00", "11:00:00")
HURDLE = 15.
MODES = {"FOLLOW": 1, "FADE": -1}


def observation(db, manifest, day):
    option = next((d for d in manifest["weekly_expiry_calendar"] if d >= day), None)
    future = next((d for d in manifest["future_expiries"] if d >= day), None)
    if option is None or future is None or day in (option, future):
        return "calendar", None
    quotes = {r[0][11:]: r[1:] for r in db.execute(
        "SELECT datetime,close,volume FROM candles WHERE kind='future' AND expiry=? AND strike=0 AND opt='' "
        "AND datetime IN (?,?,?,?)", (future, *(f"{day} {at}" for at in MARKS)))}
    if any(at not in quotes or any(v is None or not math.isfinite(v) or v <= 0 for v in quotes[at]) for at in MARKS):
        return "missing_clock", None
    opening, decision, entry, exit_ = (quotes[at][0] for at in MARKS)
    if opening == decision:
        return "flat_signal", None
    side = 1 if decision > opening else -1
    return "eligible", {"day": day, "impulse": decision - opening, "points": side * (exit_ - entry)}


def placebo_dates(sessions, excluded, day):
    weekday = date.fromisoformat(day).weekday()
    return [d for d in reversed(sessions) if d < day and d not in excluded and date.fromisoformat(d).weekday() == weekday][:2]


def collect(db, manifest, events):
    sessions = sorted(manifest["sessions"])
    pairs, counts = [], Counter()
    for day in sorted(events):
        if day not in sessions:
            counts["outside_panel"] += 1
            continue
        reason, event = observation(db, manifest, day)
        if event is None:
            counts[reason] += 1
            continue
        controls = (observation(db, manifest, d)[1] for d in placebo_dates(sessions, events, day))
        control = next((candidate for candidate in controls if candidate is not None), None)
        if control is None:
            counts["missing_placebo"] += 1
            continue
        counts["paired"] += 1
        pairs.append((event, control))
    return {"counts": counts, "pairs": pairs}


def after_five(points):
    return sum(points) - sum(sorted((p for p in points if p > 0.), reverse=True)[:5])


def score(panels, sign):
    per_year = {}
    signed, paired = [], []
    for year, panel in panels.items():
        event_points = [sign * e["points"] - HURDLE for e, _ in panel["pairs"]]
        placebo_points = [sign * p["points"] - HURDLE for _, p in panel["pairs"]]
        per_year[year] = {"event": sum(event_points), "placebo": sum(placebo_points), "n": len(event_points)}
        signed.extend(event_points)
        paired.extend(a - b for a, b in zip(event_points, placebo_points))
    count = len(signed)
    after = after_five(signed)
    increment = after_five(paired)
    return {"paired_events": count, "event_after_hurdle": sum(signed), "event_ex_best_five": after,
            "paired_increment": sum(paired), "paired_increment_ex_best_five": increment, "annual": per_year,
            "advance_to_options": count >= 20 and sum(v["event"] > 0. for v in per_year.values()) >= 4
            and after > 0. and increment > 0.}


def main():
    freeze = HERE / "round31-freeze.json"
    spec = json.loads(freeze.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{freeze.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for name, sha in spec["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha
    calendar = json.loads((HERE / "round31-calendar.json").read_bytes())
    dates = {row["date"] for row in calendar}
    assert len(dates) == len(calendar) and all(row["source"].startswith("https://") for row in calendar)
    panels = {}
    for year, folder in DATASETS.items():
        manifest, database = folder / "manifest.json", folder / "breeze.sqlite"
        assert digest(manifest) == spec["manifest"][year]
        info = json.loads(manifest.read_bytes())
        assert digest(database) == info["files_sha256"]["breeze.sqlite"]
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            panels[year] = collect(db, info, {d for d in dates if d.startswith(year)})
    out = {"arms": {mode: score(panels, side) for mode, side in MODES.items()}, "annual_evidence": panels,
           "november_5_calendar_member": "2026-11-05" in dates}
    with (HERE / "round31-results.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(out["arms"], indent=2), flush=True)


if __name__ == "__main__":
    main()
