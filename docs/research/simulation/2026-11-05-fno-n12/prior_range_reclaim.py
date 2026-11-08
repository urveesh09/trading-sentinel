"""Signal-only count for the prior-session NIFTY futures range reclaim."""

from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from math import isfinite
from pathlib import Path
import sqlite3
import subprocess

from anatomy import DATASETS


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
YEARS = ("2023", "2024", "2025", "2026")
START, FIRST, LAST, REFERENCE_END = 555, 600, 840, 930
MIN_SIGNALS = 30
TICK = .05


@dataclass(frozen=True)
class Bar:
    open: float
    high: float
    low: float
    close: float

    def valid(self) -> bool:
        return (all(value is not None and isfinite(value) for value in (self.open, self.high, self.low, self.close))
                and 0 < self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high)


@dataclass(frozen=True)
class Signal:
    minute: int
    direction: str
    close: float
    stop: float
    target: float


def geometry(low, high, inside, sweep, reclaim, minute):
    if not low < inside.close < high or not low < reclaim.close < high:
        return None
    sweep_middle = (sweep.high + sweep.low) / 2
    if sweep.close < low and reclaim.close > sweep_middle and max(sweep.high, reclaim.high) <= high:
        direction, sign = "LONG", 1
        stop = min(sweep.low, reclaim.low) - TICK
    elif sweep.close > high and reclaim.close < sweep_middle and min(sweep.low, reclaim.low) >= low:
        direction, sign = "SHORT", -1
        stop = max(sweep.high, reclaim.high) + TICK
    else:
        return None
    width = high - low
    target = (low + high) / 2
    risk = sign * (reclaim.close - stop)
    if width * .05 <= risk <= width * .25 and sign * (target - reclaim.close) >= 1.5 * risk:
        return Signal(minute, direction, reclaim.close, stop, target)
    return None


def decision(prior, current):
    reference = [prior.get(minute) for minute in range(START, REFERENCE_END)]
    if any(bar is None or not bar.valid() for bar in reference):
        return "missing_prior_same_contract", None
    low, high = min(bar.low for bar in reference), max(bar.high for bar in reference)
    opening = current.get(START)
    if opening is None or not opening.valid():
        return "missing_current_before_decision", None
    if not low < opening.open < high:
        return "open_outside_prior_range", None
    bars = []
    for slot in range(START, LAST, 5):
        rows = [current.get(minute) for minute in range(slot, slot + 5)]
        if any(bar is None or not bar.valid() for bar in rows):
            return "missing_current_before_decision", None
        bars.append(Bar(rows[0].open, max(row.high for row in rows),
                        min(row.low for row in rows), rows[-1].close))
        when = slot + 5
        if when >= FIRST:
            signal = geometry(low, high, *bars[-3:], when)
            if signal is not None:
                return "signal", signal
    return "no_setup", None


def clock(minute):
    return f"{minute // 60:02d}:{minute % 60:02d}:00"


def day_rows(db, expiry, day, end):
    result = {}
    for at, *row in db.execute(
        "SELECT datetime,open,high,low,close FROM candles WHERE kind='future' AND expiry=? "
        "AND strike=0 AND opt='' AND datetime>=? AND datetime<? ORDER BY datetime",
        (expiry, f"{day} {clock(START)}", f"{day} {clock(end)}"),
    ):
        minute = int(at[11:13]) * 60 + int(at[14:16])
        if at != f"{day} {clock(minute)}" or minute in result:
            raise ValueError(f"duplicate or unaligned futures clock: {at}")
        result[minute] = Bar(*row)
    return result


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_freeze():
    path = HERE / "prior-range-freeze.json"
    content = json.loads(path.read_bytes())
    committed = subprocess.check_output(["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT)
    if content != json.loads(committed) or tuple(content["input_manifests"]) != YEARS:
        raise ValueError("prior range freeze differs")
    for name, expected in content["source"].items():
        actual = hashlib.sha256((HERE / name).read_text(encoding="utf-8-sig").encode()).hexdigest()
        if actual != expected:
            raise ValueError(f"changed frozen strategy input: {name}")
    return content


def count():
    spec = verify_freeze()
    result = {}
    for year in YEARS:
        folder = DATASETS[year]
        manifest_path = folder / "manifest.json"
        db_path = folder / "breeze.sqlite"
        manifest = json.loads(manifest_path.read_bytes())
        if digest(manifest_path) != spec["input_manifests"][year] or digest(db_path) != manifest["files_sha256"]["breeze.sqlite"]:
            raise ValueError(f"changed frozen development input: {year}")
        sessions = manifest["sessions"]
        if sessions != sorted(set(sessions)) or any(not day.startswith(year) for day in sessions):
            raise ValueError(f"unexpected development session scope: {year}")
        coverage = Counter()
        firings = []
        days = {}
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            for i, day in enumerate(sessions):
                expiry = next((value for value in manifest["weekly_expiry_calendar"] if value >= day), None)
                future = next((value for value in manifest["future_expiries"] if value >= day), None)
                previous = sessions[i - 1] if i else None
                signal = None
                if expiry is None or future is None or day in (expiry, future):
                    reason = "expiry_or_missing_calendar"
                elif previous is None or (date.fromisoformat(day) - date.fromisoformat(previous)).days > 4:
                    reason = "prior_session_unavailable"
                else:
                    reason, signal = decision(day_rows(db, future, previous, REFERENCE_END),
                                              day_rows(db, future, day, LAST))
                coverage[reason] += 1
                days[day] = reason
                if signal is not None:
                    firings.append({"day": day, "clock": clock(signal.minute), "direction": signal.direction})
        result[year] = {"counts": dict(coverage), "firings": firings, "session_status": days}
    total = sum(len(window["firings"]) for window in result.values())
    return {"signal_count": total, "frequency_gate_passed": total >= MIN_SIGNALS,
            "minimum_signals": MIN_SIGNALS, "windows": result, "scope": "signal inputs only"}


if __name__ == "__main__":
    print(json.dumps(count(), indent=2, sort_keys=True))
