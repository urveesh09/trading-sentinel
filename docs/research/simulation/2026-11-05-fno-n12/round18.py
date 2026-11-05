"""Causal benchmark for incremental volatility information on regular NIFTY sessions."""
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
INPUT = HERE / "_local/india-vix/india-vol-closes.json"
MARKS = tuple(f"{m//60:02d}:{m%60:02d}:00" for m in range(599, 910, 5))


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def official_features(closes, days, day):
    index = bisect_left(days, day)
    if index < 21:
        return None
    window = [closes[d] for d in days[index - 21:index]]
    vix = window[-1]["vix"]
    prices = [row["nifty"] for row in window]
    if vix is None or any(price is None for price in prices):
        return None
    # Annualize the mean squared log return, with no demeaning of daily returns.
    realized = 252. * float(np.mean(np.diff(np.log(prices)) ** 2))
    implied = (float(vix) / 100.) ** 2
    if realized <= 0 or implied <= 0:
        return None
    return math.log(realized), math.log(implied / realized)


def observation(con, expiry, day):
    rows = con.execute(
        "SELECT datetime, close FROM candles WHERE kind='future' AND expiry=? AND strike=0 AND opt='' "
        "AND datetime BETWEEN ? AND ?",
        (expiry, f"{day} {MARKS[0]}", f"{day} {MARKS[-1]}"),
    ).fetchall()
    by_clock = {at[11:]: close for at, close in rows}
    prices = [by_clock.get(at) for at in MARKS]
    if any(price is None or not math.isfinite(price) or price <= 0 for price in prices):
        return None
    realized = 252. * float(np.sum(np.diff(np.log(prices)) ** 2))
    return realized if realized > 0 else None


def observations(manifest, con, closes, days):
    counters = Counter()
    records = []
    for day in manifest["sessions"]:
        counters["sessions"] += 1
        option = next((d for d in manifest["weekly_expiry_calendar"] if d >= day), None)
        if option is None or option == day:
            counters["excluded_calendar"] += 1
            continue
        future = next((d for d in manifest["future_expiries"] if d >= day), None)
        realized = observation(con, future, day) if future is not None else None
        if realized is None:
            counters["missing_future_clock"] += 1
            continue
        inputs = official_features(closes, days, day)
        if inputs is None:
            counters["missing_prior_input"] += 1
        records.append((day, realized, inputs))
    return records, counters


def predict(history, row, with_implied):
    columns = slice(None) if with_implied else slice(0, -1)
    features = np.array([x for x, _ in history], dtype=float)[:, columns]
    actuals = np.log([v for _, v in history])
    coef, *_ = np.linalg.lstsq(features, actuals, rcond=None)
    return float(np.array(row, dtype=float)[columns] @ coef)


def score(records):
    training, trail, daily = [], [], defaultdict(list)
    for day, actual, inputs in records:
        if inputs is not None and len(trail) >= 20:
            historical, ratio = inputs
            current = (1., historical, math.log(mean_trailing(trail)), ratio)
            if len(training) >= 60:
                rows = training[-252:]
                native, implied = (predict(rows, current, which) for which in (False, True))
                daily[day[:4]].append({"day": day, "realized": actual,
                                       "realized_only_log_forecast": native, "implied_log_forecast": implied})
            training.append((current, actual))
        trail.append(actual)
    return daily


def mean_trailing(values):
    return sum(values[-20:]) / 20.


def metrics(rows):
    actual = np.array([r["realized"] for r in rows])
    out = {"forecast_count": len(rows)}
    for name in ("realized_only", "implied"):
        predicted_log = np.array([r[f"{name}_log_forecast"] for r in rows])
        out[name] = {"log_mse": float(np.mean((np.log(actual) - predicted_log) ** 2)),
                     "qlike": float(np.mean(actual / np.exp(predicted_log) + predicted_log))}
    out["log_mse_improvement_pct"] = 100. * (1. - out["implied"]["log_mse"] / out["realized_only"]["log_mse"])
    return out


def main():
    frozen = HERE / "round18-freeze.json"
    manifest = json.loads(frozen.read_bytes())
    assert manifest == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{frozen.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for name, digest in manifest["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == digest
    assert sha(INPUT) == manifest["official_closes"]
    closes = json.loads(INPUT.read_bytes())["closes"]
    days = sorted(closes)
    records, coverage = [], {}
    for year, dataset in DATASETS.items():
        sealed = dataset / "manifest.json"
        db = dataset / "breeze.sqlite"
        assert [sha(sealed), sha(db)] == manifest["futures"][year]
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            rows, coverage[year] = observations(json.loads(sealed.read_bytes()), con, closes, days)
        records.extend(rows)
    assert [r[0] for r in records] == sorted(set(r[0] for r in records))
    scored = score(records)
    result = {"coverage": coverage, "metrics": {year: metrics(rows) for year, rows in scored.items()},
              "aggregate": metrics([row for rows in scored.values() for row in rows]), "paired": scored}
    with (HERE / "round18-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "paired"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
