"""Frozen directional viability screen for a midday rotation on dated futures."""

from collections import Counter
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from statistics import median
import subprocess

from anatomy import DATASETS
from round25 import digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INPUTS = tuple(f"{minute // 60:02d}:{minute % 60:02d}:00" for minute in range(555, 780))
MORNING = INPUTS[:195]
MARKS = ("13:01:00", "14:15:00")
HURDLE = 15.


def direction(rows):
    """Rows are indexed by completed minute start and hold high, low, close, volume."""
    if any(at not in rows for at in INPUTS):
        return None, "missing_input"
    morning = [rows[at] for at in MORNING]
    if any(any(v is None or not math.isfinite(v) for v in row) or not 0 < row[1] <= row[2] <= row[0]
           or row[3] < 0 for row in morning):
        return None, "invalid_input"
    spread = max(row[0] for row in morning) - min(row[1] for row in morning)
    volume = sum(row[3] for row in morning)
    clocks = [rows[at][2] for at in ("12:44:00", "12:54:00", "12:59:00")]
    if spread <= 0 or volume <= 0 or not all(p is not None and math.isfinite(p) and p > 0 for p in clocks):
        return None, "invalid_input"
    value = sum(c * v for _, _, c, v in morning) / volume
    first, middle, last = clocks
    displacement = first - value
    if abs(displacement) < max(30., .55 * spread):
        return None, "unstretched"
    side = -1 if displacement > 0 else 1
    repair = side * (last - first) / abs(displacement)
    if not (.15 <= repair <= .50 and side * (middle - first) > 0):
        return None, "unconfirmed"
    return {"side": side, "morning_value": value, "morning_range": spread, "repair": repair}, "signal"


def observe(rows):
    setup, reason = direction(rows)
    if setup is None:
        return reason, None
    quotes = [rows.get(at) for at in MARKS]
    if any(row is None or not row[3] or row[3] <= 0 or not row[2] or row[2] <= 0 for row in quotes):
        return "missing_outcome", setup
    entry, exit_ = (row[2] for row in quotes)
    return reason, {**setup, "entry": entry, "exit": exit_, "points": setup["side"] * (exit_ - entry)}


def report(windows):
    rows = [trade for window in windows.values() for trade in window["trades"]]
    points = [r["points"] for r in rows]
    adjusted = [p - HURDLE for p in points]
    best = sorted((p for p in adjusted if p > 0), reverse=True)[:5]
    annual = {y: sum(t["points"] - HURDLE for t in p["trades"]) for y, p in windows.items()}
    after = sum(adjusted) - sum(best)
    return {"priced_signals": len(points), "mean_points": sum(points) / len(points) if points else None,
            "median_points": median(points) if points else None, "after_hurdle": sum(adjusted),
            "annual_after_hurdle": annual, "after_hurdle_without_best_five": after,
            "passes_for_option_test": len(points) >= 20 and sum(v > 0 for v in annual.values()) >= 4
            and after > 0 and all(not p["coverage"].get("missing_outcome") for p in windows.values())}


def main():
    spec = HERE / "round26-freeze.json"
    frozen = json.loads(spec.read_bytes())
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for file, sha in frozen["source"].items():
        assert hashlib.sha256((HERE / file).read_text(encoding="utf-8").encode()).hexdigest() == sha
    windows = {}
    for year, folder in DATASETS.items():
        manifest_path = folder / "manifest.json"
        assert digest(manifest_path) == frozen["manifest"][year]
        manifest = json.loads(manifest_path.read_bytes())
        db = folder / "breeze.sqlite"
        assert digest(db) == manifest["files_sha256"]["breeze.sqlite"]
        results, coverage = [], Counter()
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            con.execute("PRAGMA query_only=ON")
            for day in manifest["sessions"]:
                expiry = next((d for d in manifest["weekly_expiry_calendar"] if d >= day), None)
                future = next((d for d in manifest["future_expiries"] if d >= day), None)
                if expiry is None or future is None or expiry == day or future == day:
                    coverage["calendar"] += 1
                    continue
                data = {row[0][11:]: row[1:] for row in con.execute(
                    "SELECT datetime,high,low,close,volume FROM candles WHERE kind='future' AND expiry=? AND strike=0 "
                    "AND opt='' AND datetime BETWEEN ? AND ?", (future, f"{day} {INPUTS[0]}", f"{day} {MARKS[-1]}"))}
                reason, trade = observe(data)
                coverage[reason] += 1
                if reason == "signal":
                    results.append({"day": day, **trade})
        windows[year] = {"coverage": coverage, "trades": results}
    result = {"summary": report(windows), "windows": windows}
    with (HERE / "round26-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"summary": result["summary"], "coverage": {y: p["coverage"] for y, p in windows.items()}}, indent=2))


if __name__ == "__main__":
    main()
