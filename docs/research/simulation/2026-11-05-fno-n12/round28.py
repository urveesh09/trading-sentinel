"""Paired walk-forward screen of fixed-strike NIFTY option activity."""

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
from round25 import digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ACTIVITY = tuple(f"09:{minute:02d}:00" for minute in range(29, 60))
FUTURE_MARKS = (ACTIVITY[0], ACTIVITY[-1], "10:01:00", "11:00:00")


def strikes_at(future):
    atm = 50 * math.floor(future / 50 + .5)
    return atm - 50, atm, atm + 50


def activity(rows, strikes):
    totals = {}
    for right in ("CE", "PE"):
        start = end = turnover = 0.
        for strike in strikes:
            for i, at in enumerate(ACTIVITY):
                cell = rows.get((at, strike, right))
                if cell is None:
                    return None
                price, volume, oi = cell
                if volume is None or not math.isfinite(volume) or volume < 0:
                    return None
                if i in (0, len(ACTIVITY) - 1):
                    if not all(v is not None and math.isfinite(v) and v > 0 for v in (price, volume, oi)):
                        return None
                    if i == 0:
                        start += oi
                    else:
                        end += oi
                if i > 0:
                    turnover += volume
        totals[right] = start, end, turnover
    cs, ce, cv = totals["CE"]
    ps, pe, pv = totals["PE"]
    return math.log(ce / pe) - math.log(cs / ps), math.log(cv / pv)


def extract(db, manifest):
    counts, rows = Counter(), []
    for day in manifest["sessions"]:
        expiry = next((d for d in manifest["weekly_expiry_calendar"] if d >= day), None)
        future = next((d for d in manifest["future_expiries"] if d >= day), None)
        if expiry is None or future is None or expiry == day or future == day:
            counts["calendar"] += 1
            continue
        prices = {r[0][11:]: r[1:] for r in db.execute(
            "SELECT datetime,close,volume FROM candles WHERE kind='future' AND expiry=? AND strike=0 AND opt='' "
            "AND datetime IN (?,?,?,?)", (future, *(f"{day} {at}" for at in FUTURE_MARKS)))}
        if any(at not in prices or any(v is None or not math.isfinite(v) or v <= 0 for v in prices[at])
               for at in FUTURE_MARKS):
            counts["missing_future_clock"] += 1
            continue
        opening, current, entry, exit_ = (prices[at][0] for at in FUTURE_MARKS)
        strikes = strikes_at(opening)
        chain = {(r[0][11:], r[1], r[2]): r[3:] for r in db.execute(
            "SELECT datetime,strike,opt,close,volume,oi FROM candles WHERE kind='option' AND expiry=? "
            "AND strike IN (?,?,?) AND opt IN ('CE','PE') AND datetime BETWEEN ? AND ?",
            (expiry, *strikes, f"{day} {ACTIVITY[0]}", f"{day} {ACTIVITY[-1]}"))}
        features = activity(chain, strikes)
        if features is None:
            counts["missing_chain_clock_or_oi"] += 1
            continue
        counts["complete"] += 1
        rows.append((day, (1., math.log(current / opening), *features), math.log(exit_ / entry), exit_ - entry, entry))
    return rows, counts


def walk(rows):
    history, predictions = [], defaultdict(list)
    assert [row[0] for row in rows] == sorted({row[0] for row in rows})
    for day, features, target, points, entry in rows:
        if len(history) >= 60:
            selected = history[-252:]
            x = np.array([row[0] for row in selected])
            y = np.array([row[1] for row in selected])
            base, model = (float(np.array(features[:n]) @ np.linalg.lstsq(x[:, :n], y, rcond=None)[0]) for n in (2, 4))
            predictions[day[:4]].append((day, target, points, entry, base, model))
        history.append((features, target))
    return predictions


def ex_best_five(points):
    return sum(points) - sum(sorted((p for p in points if p > 0), reverse=True)[:5])


def metrics(rows):
    if not rows:
        return {"predictions": 0, "advance_to_options": False}
    actual, points, entry, base, model = np.array([r[1:] for r in rows]).T
    base_mse, model_mse = (float(np.mean((pred - actual) ** 2)) for pred in (base, model))
    mse = 100. * (1 - model_mse / base_mse) if base_mse > 0 else 0.
    accuracy = float(100. * (np.mean(np.sign(model) == np.sign(actual)) - np.mean(np.sign(base) == np.sign(actual))))
    incremental = float(ex_best_five(points * (np.sign(model) - np.sign(base))))
    strong = abs(model) * entry >= 25.
    strong_points = np.sign(model[strong]) * points[strong] - 15.
    strong_count = int(sum(strong))
    strong_ex_five = float(ex_best_five(strong_points))
    return {"predictions": len(rows), "reference_mse": base_mse, "activity_mse": model_mse, "mse_improvement_pct": mse,
            "sign_accuracy_delta_pp": accuracy, "incremental_points_ex_best_five": incremental,
            "strong_count": strong_count, "strong_points_after_hurdle": float(sum(strong_points)),
            "strong_points_after_hurdle_ex_best_five": strong_ex_five,
            "advance_to_options": len(rows) >= 200 and mse >= 2. and accuracy >= 2. and incremental > 0
            and strong_count >= 20 and strong_ex_five > 0}


def main():
    freeze = HERE / "round28-freeze.json"
    spec = json.loads(freeze.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{freeze.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for name, sha in spec["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha
    records, coverage = [], {}
    for year, folder in DATASETS.items():
        manifest, database = folder / "manifest.json", folder / "breeze.sqlite"
        assert digest(manifest) == spec["manifest"][year]
        info = json.loads(manifest.read_bytes())
        assert digest(database) == info["files_sha256"]["breeze.sqlite"]
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            eligible, coverage[year] = extract(db, info)
        records.extend(eligible)
    paired = walk(records)
    value = {"aggregate": metrics([p for rows in paired.values() for p in rows]),
             "annual": {y: metrics(paired.get(y, [])) for y in DATASETS}, "coverage": coverage,
             "paired_fields": ["day", "actual_log", "points", "entry", "reference_log", "activity_log"], "paired": paired}
    with (HERE / "round28-results.json").open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    print(json.dumps({k: v for k, v in value.items() if k != "paired"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
