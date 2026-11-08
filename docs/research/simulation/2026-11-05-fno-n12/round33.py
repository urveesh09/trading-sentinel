"""Paired prior-only forecast of NIFTY future returns with and without basis."""

from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from statistics import median
import subprocess

import numpy as np

from anatomy import DATASETS
from round25 import digest
from round28 import metrics


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MARKS = tuple(f"{m // 60:02d}:{m % 60:02d}:00" for m in range(589, 660, 5))
OUTCOME = ("11:01:00", "11:10:00")


def feature_row(cash, future):
    assert len(cash) == len(future) == len(MARKS)
    basis = [math.log(f / s) for s, f in zip(cash, future)]
    return (1., math.log(future[-1] / future[0]), math.log(future[-1] / future[-2]),
            basis[-1] - median(basis[:-1]), basis[-1] - basis[-2])


def marks(db, day, kind, expiry, clocks):
    params = ",".join("?" for _ in clocks)
    rows = {row[0][11:]: row[1:] for row in db.execute(
        "SELECT datetime,close,volume FROM candles WHERE kind=? AND expiry=? AND strike=0 AND opt='' "
        f"AND datetime IN ({params})", (kind, expiry, *(f"{day} {at}" for at in clocks)))}
    values = []
    for clock in clocks:
        price, volume = rows.get(clock, (None, None))
        if price is None or not math.isfinite(price) or price <= 0:
            return None
        if kind == "future" and (volume is None or not math.isfinite(volume) or volume <= 0):
            return None
        values.append(price)
    return values


def extract(db, manifest):
    rows, counts = [], Counter()
    for day in manifest["sessions"]:
        expiry = next((d for d in manifest["weekly_expiry_calendar"] if d >= day), None)
        future = next((d for d in manifest["future_expiries"] if d >= day), None)
        if expiry is None or future is None or day in (expiry, future):
            counts["calendar"] += 1
            continue
        spot = marks(db, day, "index", "", MARKS)
        if spot is None:
            counts["missing_cash_prefix"] += 1
            continue
        prices = marks(db, day, "future", future, (*MARKS, *OUTCOME))
        if prices is None:
            counts["missing_future_clock"] += 1
            continue
        before, entry, exit_ = prices[:-2], prices[-2], prices[-1]
        rows.append((day, feature_row(spot, before), math.log(exit_ / entry), exit_ - entry, before[-1]))
        counts["complete"] += 1
    return rows, counts


def walk(rows):
    history, predictions = [], defaultdict(list)
    assert [row[0] for row in rows] == sorted({row[0] for row in rows})
    for day, features, target, points, decision_price in rows:
        if len(history) >= 60:
            samples = history[-252:]
            x = np.array([row[0] for row in samples])
            y = np.array([row[1] for row in samples])
            base, candidate = (float(np.array(features[:n]) @ np.linalg.lstsq(x[:, :n], y, rcond=None)[0]) for n in (3, 5))
            predictions[day[:4]].append((day, target, points, decision_price, base, candidate))
        history.append((features, target))
    return predictions


def main():
    frozen = HERE / "round33-freeze.json"
    spec = json.loads(frozen.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{frozen.relative_to(ROOT).as_posix()}"], cwd=ROOT))
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
            rows, coverage[year] = extract(db, info)
        records.extend(rows)
    paired = walk(records)
    output = {"aggregate": metrics([p for rows in paired.values() for p in rows]),
              "annual": {y: metrics(paired.get(y, [])) for y in DATASETS}, "coverage": coverage,
              "fields": ["day", "actual_log", "points", "decision_price", "reference_log", "basis_log"],
              "paired": paired}
    # Round 28's metric math is shared. Rename its model label for this receipt.
    for summary in [output["aggregate"], *output["annual"].values()]:
        if "activity_mse" in summary:
            summary["basis_mse"] = summary.pop("activity_mse")
    with (HERE / "round33-results.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    print(json.dumps({k: v for k, v in output.items() if k != "paired"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
