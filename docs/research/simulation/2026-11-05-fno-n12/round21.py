"""Walk-forward check of breadth information for a fixed regular futures window."""
from bisect import bisect_left
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

import numpy as np

from anatomy import DATASETS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INPUT = HERE / "_local/breadth/breadth-closes.json"
MARKS = ("09:15:00", "09:44:00", "09:46:00", "11:15:00")


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def prior_return(closes, dates, day):
    idx = bisect_left(dates, day)
    if idx < 6:
        return None
    prior = dates[idx - 6:idx]
    if any(d not in closes["equal"] for d in prior):
        return None
    previous, end = prior[0], prior[-1]
    nifty = math.log(closes["nifty"][end] / closes["nifty"][previous])
    equal = math.log(closes["equal"][end] / closes["equal"][previous])
    return nifty, equal - nifty


def observations(db, manifest, closes, days):
    marks = ",".join("?" for _ in MARKS)
    counts, rows = Counter(), []
    for day in manifest["sessions"]:
        counts["sessions"] += 1
        expiry = next((date for date in manifest["weekly_expiry_calendar"] if date >= day), None)
        if expiry is None or expiry == day:
            counts["excluded_calendar"] += 1
            continue
        future = next((date for date in manifest["future_expiries"] if date >= day), None)
        raw = db.execute(
            "SELECT substr(datetime,12),open,close FROM candles WHERE kind='future' AND expiry=? "
            f"AND strike=0 AND opt='' AND datetime IN ({marks})", (future, *(f"{day} {mark}" for mark in MARKS)),
        ).fetchall()
        by_mark = {mark: (opened, close) for mark, opened, close in raw}
        if not set(MARKS) <= by_mark.keys():
            counts["missing_future_clock"] += 1
            continue
        opening, signal, entry, exit_price = (by_mark[MARKS[0]][0], *(by_mark[mark][1] for mark in MARKS[1:]))
        if min(opening, signal, entry, exit_price) <= 0:
            counts["invalid_future_price"] += 1
            continue
        prior = prior_return(closes, days, day)
        if prior is None:
            counts["missing_prior_inputs"] += 1
            continue
        market, breadth = prior
        rows.append((day, (1., math.log(signal / opening), market, breadth), math.log(exit_price / entry), exit_price - entry))
    return rows, counts


def scores(rows):
    history, results = [], defaultdict(list)
    for day, inputs, actual, points in rows:
        if len(history) >= 60:
            samples = history[-252:]
            x = np.array([previous for previous, _ in samples])
            y = np.array([target for _, target in samples])
            baseline_coef = np.linalg.lstsq(x[:, :-1], y, rcond=None)[0]
            candidate_coef = np.linalg.lstsq(x, y, rcond=None)[0]
            baseline = float(np.array(inputs[:-1]) @ baseline_coef)
            candidate = float(np.array(inputs) @ candidate_coef)
            delta = float(points * (np.sign(candidate) - np.sign(baseline)))
            results[day[:4]].append((day, actual, baseline, candidate, points, delta))
        history.append((inputs, actual))
    return results


def metrics(rows):
    actual, native, candidate, points, delta = np.array([r[1:] for r in rows]).T
    out = {"predictions": len(rows)}
    for name, predicted in (("reference", native), ("breadth", candidate)):
        out[name] = {"mse": float(np.mean((actual - predicted) ** 2)),
                     "sign_accuracy_pct": float(100. * np.mean(np.sign(actual) == np.sign(predicted))),
                     "signed_futures_points": float(np.sum(np.sign(predicted) * points))}
    out["mse_improvement_pct"] = 100. * (1. - out["breadth"]["mse"] / out["reference"]["mse"])
    out["direction_accuracy_delta_pp"] = out["breadth"]["sign_accuracy_pct"] - out["reference"]["sign_accuracy_pct"]
    out["incremental_points_ex_best_five"] = float(np.sum(np.sort(delta)[:-5]))
    return out


def main():
    path = HERE / "round21-freeze.json"
    spec = json.loads(path.read_bytes())
    assert spec == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    assert sha(INPUT) == spec["breadth_sha256"]
    for name, expected in spec["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == expected
    closes = json.loads(INPUT.read_bytes())
    days = sorted(closes["nifty"])
    records, counts = [], {}
    for year, folder in DATASETS.items():
        database, manifest = folder / "breeze.sqlite", folder / "manifest.json"
        assert [sha(database), sha(manifest)] == spec["data"][year]
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            rows, counts[year] = observations(db, json.loads(manifest.read_bytes()), closes, days)
        records.extend(rows)
    assert [row[0] for row in records] == sorted(set(row[0] for row in records))
    paired = scores(records)
    annual = {year: metrics(rows) for year, rows in paired.items()}
    aggregate = metrics([row for rows in paired.values() for row in rows])
    result = {"aggregate": aggregate, "annual": annual, "coverage": counts,
              "paired_fields": ["day", "actual_log_return", "reference_prediction", "breadth_prediction", "future_points", "incremental_points"],
              "paired": paired}
    with (HERE / "round21-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    print(json.dumps({"aggregate": aggregate, "annual": annual, "coverage": counts}, indent=2), flush=True)


if __name__ == "__main__":
    main()
