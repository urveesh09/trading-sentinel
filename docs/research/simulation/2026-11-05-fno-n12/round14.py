"""Causal cross-index coverage and directional catch-up feasibility."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median
import sqlite3
import subprocess

from anatomy import DATASETS, trades

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SENSEX = HERE / "_local/round9/breeze.sqlite"
REQUIRED = {f"09:{minute:02d}:00" for minute in range(15, 60)} | {"10:01:00", "10:44:00"}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def connect(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def marks(conn, expiry, day):
    rows = conn.execute(
        "SELECT datetime,open,high,low,close FROM candles WHERE kind='future' AND expiry=? "
        "AND strike=0 AND opt='' AND datetime BETWEEN ? AND ? ORDER BY datetime",
        (expiry, day + " 09:15:00", day + " 10:44:00"),
    ).fetchall()
    return {stamp[11:]: (opened, high, low, close) for stamp, opened, high, low, close in rows}


def opening(tape):
    window = [bar for at, bar in tape.items() if at < "10:00:00"]
    width = max(bar[1] for bar in window) - min(bar[2] for bar in window)
    return tape["09:59:00"][3] - tape["09:15:00"][0], width


def run_year(nifty, sensex, sensex_expiries, manifest, controls, bounds):
    earlier = set()
    later = set()
    for trade in controls["trades"]:
        at = datetime.fromisoformat(trade["entry_time"])
        clock = at.strftime("%H:%M:%S")
        day = at.date().isoformat()
        if clock <= "10:00:00":
            earlier.add(day)
        if "10:00:00" < clock <= "10:44:59":
            later.add(day)
    counts = Counter()
    rows = []
    for day in manifest["sessions"]:
        if not bounds[0] <= day <= bounds[1]:
            continue
        counts["sessions_in_source_span"] += 1
        option = next((x for x in manifest["weekly_expiry_calendar"] if x >= day), None)
        futures_n = next((x for x in manifest["future_expiries"] if x >= day), None)
        futures_s = next((x for x in sensex_expiries if x >= day), None)
        if not option or not futures_n or not futures_s or day in (option, futures_n, futures_s):
            counts["expiry_or_identity_excluded"] += 1
            continue
        n = marks(nifty, futures_n, day)
        s = marks(sensex, futures_s, day)
        if not REQUIRED <= n.keys() or not REQUIRED <= s.keys():
            counts["nifty_missing_clock"] += not REQUIRED <= n.keys()
            counts["sensex_missing_clock"] += not REQUIRED <= s.keys()
            continue
        counts["paired_complete"] += 1
        if day in earlier:
            counts["n11t_already_entered"] += 1
            continue
        move_n, width_n = opening(n)
        move_s, width_s = opening(s)
        if min(width_n, width_s) <= 0 or abs(move_s) < .6 * width_s:
            continue
        side = 1 if move_s > 0 else -1
        if not 0 < side * move_n <= .3 * width_n:
            continue
        change_n = side * (n["10:44:00"][3] - n["10:01:00"][3])
        change_s = side * (s["10:44:00"][3] - s["10:01:00"][3])
        rows.append(dict(day=day, side=side, nifty_expiry=futures_n, sensex_expiry=futures_s,
                         option_expiry=option, signed_nifty_points=round(change_n, 4),
                         signed_sensex_points=round(change_s, 4),
                         catchup_range_units=round(change_n / width_n - change_s / width_s, 6),
                         competing_n11t_entry=day in later))
    counts["signals"] = len(rows)
    changes = [row["signed_nifty_points"] for row in rows]
    return dict(counts=counts, signed_nifty_points=round(sum(changes), 4),
                median_nifty_points=median(changes) if changes else None, rows=rows)


def main():
    path = HERE / "round14-freeze.json"
    freeze = json.loads(path.read_bytes())
    assert freeze == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for name, expected in freeze["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == expected
    assert digest(SENSEX) == freeze["sensex"]
    result = {}
    with connect(SENSEX) as sensex:
        expiries = [row[0] for row in sensex.execute("SELECT DISTINCT expiry FROM candles WHERE kind='future' ORDER BY expiry")]
        bounds = sensex.execute("SELECT min(substr(datetime,1,10)),max(substr(datetime,1,10)) "
                                "FROM candles WHERE kind='future'").fetchone()
        for year, expected in freeze["nifty"].items():
            manifest = DATASETS[year] / "manifest.json"
            db = DATASETS[year] / "breeze.sqlite"
            receipt, control = trades(year, "N11T")
            assert [digest(x) for x in (manifest, db, receipt)] == expected
            with connect(db) as nifty:
                result[year] = run_year(nifty, sensex, expiries, json.loads(manifest.read_bytes()), control, bounds)
    changes = sorted(row["signed_nifty_points"] for year in result.values() for row in year["rows"])
    result["aggregate"] = dict(source_bounds=bounds, screened_points=round(sum(x - 5 for x in changes[:-5]), 4))
    with (HERE / "round14-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    for year, row in result.items():
        print(year, {k: v for k, v in row.items() if k != "rows"}, flush=True)


if __name__ == "__main__":
    main()
