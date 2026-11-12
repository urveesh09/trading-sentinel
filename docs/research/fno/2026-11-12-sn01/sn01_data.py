"""SN01 data - per-session minute arrays from the four sealed NIFTY year datasets (research only, read-only).

The sealed datasets (FNO_YEAR_DATA_TESTING_METHOD.md section 2) hold ICICI Breeze 1-minute candles of the NIFTY index,
the front future and the nearest weekly options. This module copies one session at a time into plain numpy arrays on
a fixed 375-minute grid (09:15 .. 15:29) and pickles them per year under ``_local/``. Nothing here writes to a
dataset, calls a broker or touches Production.

Grid rules (declared before any strategy is scored):
  * minute i covers [09:15 + i, 09:15 + i + 1); its close is the observation at the minute's last second;
  * index and future prices are carried forward through a minute with no candle;
  * option arrays keep NaN where the contract did not trade; ``mark`` carries the last close forward for valuation,
    but a fill needs a candle in that minute (``traded``);
  * the session's option expiry is the single weekly expiry present that day (the export holds only the nearest);
    expiry days have no options in these datasets, so SN01 never trades them.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
LOCAL = HERE / "_local"

DATASETS = {
    "2023": ROOT / "docs/research/simulation/2026-11-01-fno-n08/_local/dataset-nifty-2023",
    "2024": ROOT / "docs/research/fno/2026-10-30-day-router/_local/dataset-nifty-2024",
    "2025": ROOT / "docs/research/fno/2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
    "2026": ROOT / "docs/research/fno/2026-10-29-year-genome/_local/dataset-nifty",
}
N_MIN = 375  # 09:15 .. 15:29
LOT = 65
STEP = 50


def minute_index(stamp: str) -> int:
    hh, mm = int(stamp[11:13]), int(stamp[14:16])
    return hh * 60 + mm - (9 * 60 + 15)


def manifest_sha(year: str) -> str:
    return hashlib.sha256((DATASETS[year] / "manifest.json").read_bytes()).hexdigest()


def _ffill(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    # leading NaN: back-fill with the first value so a late first candle does not leave holes
    first = np.flatnonzero(~np.isnan(out))
    if len(first):
        out[: first[0]] = out[first[0]]
    return out


def build_year(year: str) -> dict:
    root = DATASETS[year]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{(root / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    fut_exp = sorted(manifest["future_expiries"])
    # every index day (including December of the previous year where present) for prior-day levels
    idx_days = [r[0] for r in con.execute(
        "SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index' ORDER BY 1")]
    daily = {}
    for d in idx_days:
        rows = con.execute("SELECT open, high, low, close FROM candles WHERE kind='index' AND datetime >= ? AND "
                           "datetime < ? ORDER BY datetime", (d, d + "~")).fetchall()
        if rows:
            daily[d] = (rows[0][0], max(r[1] for r in rows), min(r[2] for r in rows), rows[-1][3])
    sessions = {}
    for day in manifest["sessions"]:
        exp = con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND datetime >= ? AND datetime < ?",
                          (day, day + "~")).fetchall()
        if not exp:
            continue
        assert len(exp) == 1, (day, exp)
        expiry = exp[0][0]
        if expiry <= day:
            continue
        front = next(e for e in fut_exp if e >= day)
        s = {"day": day, "expiry": expiry}
        for kind, args in (("index", ("index", "")), ("future", ("future", front))):
            arr = np.full((5, N_MIN), np.nan)
            q = ("SELECT datetime, open, high, low, close, volume FROM candles WHERE kind=? AND datetime >= ? AND "
                 "datetime < ?" + (" AND expiry=?" if kind == "future" else "") + " ORDER BY datetime")
            params = (args[0], day, day + "~") + ((args[1],) if kind == "future" else ())
            for stamp, o, h, l, c, v in con.execute(q, params):
                i = minute_index(stamp)
                if 0 <= i < N_MIN:
                    arr[:, i] = (o, h, l, c, v or 0.0)
            traded = ~np.isnan(arr[3])
            for k in range(4):
                arr[k] = _ffill(arr[k])
            arr[4] = np.nan_to_num(arr[4])
            s[kind] = arr.astype(np.float64)
            s[kind + "_traded"] = traded
        opts = {}
        for stamp, strike, opt, o, h, l, c, v, oi in con.execute(
                "SELECT datetime, strike, opt, open, high, low, close, volume, oi FROM candles WHERE kind='option' "
                "AND expiry=? AND datetime >= ? AND datetime < ? ORDER BY datetime", (expiry, day, day + "~")):
            i = minute_index(stamp)
            if not (0 <= i < N_MIN):
                continue
            key = (int(round(strike)), opt)
            if key not in opts:
                opts[key] = np.full((5, N_MIN), np.nan)
            opts[key][:, i] = (o, h, l, c, v or 0.0)
        s["options"] = {k: v.astype(np.float32) for k, v in opts.items()}
        if np.isnan(s["index"][3]).all():
            continue
        prev = [d for d in daily if d < day]
        s["prev"] = daily[prev[-1]] if prev else None
        s["prev_days"] = [daily[d] for d in prev[-25:]]
        sessions[day] = s
    con.close()
    return {"year": year, "manifest_sha256": manifest_sha(year), "sessions": sessions}


def load_year(year: str) -> dict:
    path = LOCAL / f"cache-{year}.pkl"
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    if data["manifest_sha256"] != manifest_sha(year):
        raise SystemExit(f"cache-{year} does not match its sealed dataset")
    return data


def main(argv: list[str]) -> None:
    LOCAL.mkdir(exist_ok=True)
    for year in (argv or list(DATASETS)):
        data = build_year(year)
        tmp = LOCAL / f"cache-{year}.pkl.tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(LOCAL / f"cache-{year}.pkl")
        print(year, len(data["sessions"]), "sessions", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
