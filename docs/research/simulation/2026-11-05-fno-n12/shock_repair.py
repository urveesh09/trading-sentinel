"""Count completed futures shock repairs without reading option outcomes."""

from collections import Counter
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
import sqlite3
from statistics import median

from exam_run import committed
from prior_range_reclaim import Bar, DATASETS, HERE, Signal, START, TICK, YEARS, clock, digest


FIRST, LAST = 630, 840
LOOKBACK = 12
MINIMUM_SIGNALS = 30
FREEZE = HERE / "shock-repair-freeze.json"


@dataclass(frozen=True)
class VolumeBar(Bar):
    volume: float

    def valid(self) -> bool:
        return super().valid() and self.volume is not None and isfinite(self.volume) and self.volume >= 0


def shock_signal(bars, minute):
    context = bars[-(LOOKBACK + 3):-2]
    shock, repair = bars[-2:]
    moves = [abs(right.close - left.close) for left, right in zip(context, context[1:])]
    normal_move = median(moves)
    normal_volume = median(bar.volume for bar in context[1:])
    anchor = context[-1].close
    distance = abs(anchor - shock.close)
    if normal_move <= 0 or normal_volume <= 0 or distance < 3 * normal_move or shock.volume < 2 * normal_volume:
        return None

    side = 1 if anchor > shock.close else -1
    span = shock.high - shock.low
    if span <= 0:
        return None
    if side == 1:
        if shock.close - shock.low > span / 3 or repair.low < shock.low:
            return None
        stop = shock.low - TICK
    else:
        if shock.high - shock.close > span / 3 or repair.high > shock.high:
            return None
        stop = shock.high + TICK

    recovery = side * (repair.close - shock.close)
    risk = side * (repair.close - stop)
    reward = side * (anchor - repair.close)
    if .20 * distance <= recovery <= .40 * distance and risk > 0 and reward >= 1.5 * risk:
        return Signal(minute, "LONG" if side == 1 else "SHORT", repair.close, stop, anchor)
    return None


def decision(minutes):
    bars = []
    for start in range(START, LAST, 5):
        rows = [minutes.get(minute) for minute in range(start, start + 5)]
        if any(bar is None or not bar.valid() for bar in rows):
            return "missing_or_invalid_clock", None
        volume = sum(bar.volume for bar in rows)
        if volume <= 0:
            return "no_traded_volume", None
        bars.append(VolumeBar(rows[0].open, max(bar.high for bar in rows), min(bar.low for bar in rows),
                              rows[-1].close, volume))
        end = start + 5
        if end >= FIRST:
            signal = shock_signal(bars, end)
            if signal is not None:
                return "signal", signal
    return "no_setup", None


def day_rows(db, future, day):
    result = {}
    for at, *row in db.execute(
        "SELECT datetime,open,high,low,close,volume FROM candles WHERE kind='future' AND expiry=? "
        "AND strike=0 AND opt='' AND datetime>=? AND datetime<? ORDER BY datetime",
        (future, f"{day} {clock(START)}", f"{day} {clock(LAST)}"),
    ):
        minute = int(at[11:13]) * 60 + int(at[14:16])
        if at != f"{day} {clock(minute)}" or minute in result:
            raise ValueError(f"duplicate or unaligned futures clock: {at}")
        result[minute] = VolumeBar(*row)
    return result


def count():
    frozen = committed(FREEZE)
    if tuple(frozen["input_manifests"]) != YEARS:
        raise ValueError("unexpected frozen signal years")
    for name, expected in frozen["sources"].items():
        actual = hashlib.sha256((HERE / name).read_text(encoding="utf-8-sig").encode()).hexdigest()
        if actual != expected:
            raise ValueError(f"changed frozen signal source: {name}")

    result = {}
    for year in YEARS:
        folder = DATASETS[year]
        manifest_path, db_path = folder / "manifest.json", folder / "breeze.sqlite"
        manifest = json.loads(manifest_path.read_bytes())
        if (digest(manifest_path) != frozen["input_manifests"][year]
                or digest(db_path) != manifest["files_sha256"]["breeze.sqlite"]):
            raise ValueError(f"changed frozen development input: {year}")
        sessions = manifest["sessions"]
        if sessions != sorted(set(sessions)) or any(not day.startswith(year) for day in sessions):
            raise ValueError(f"unexpected development session scope: {year}")
        days, firings = {}, []
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            for day in sessions:
                expiry = next((value for value in manifest["weekly_expiry_calendar"] if value >= day), None)
                front = next((value for value in manifest["future_expiries"] if value >= day), None)
                signal = None
                if expiry is None or front is None or day in (expiry, front):
                    reason = "expiry_or_missing_calendar"
                else:
                    reason, signal = decision(day_rows(db, front, day))
                days[day] = reason
                if signal is not None:
                    firings.append({"day": day, "clock": clock(signal.minute), "direction": signal.direction})
        result[year] = {"counts": dict(Counter(days.values())), "firings": firings, "session_status": days}
    total = sum(len(window["firings"]) for window in result.values())
    return {"scope": "futures signal inputs only", "signal_count": total, "minimum_signals": MINIMUM_SIGNALS,
            "frequency_gate_passed": total >= MINIMUM_SIGNALS, "windows": result}


if __name__ == "__main__":
    print(json.dumps(count(), indent=2, sort_keys=True))
