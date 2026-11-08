"""M01 momentum lab: load 15-minute and daily bars into one shape for both windows.

DEV  = Production intraday_cache (interval='15minute'), Aug 11 - Nov 6 2026, exported read-only.
EXAM = the Oct 5 Kite snapshot (docs/research/kite/2026-10-05-momentum-h1/_local/raw), Jan 1 - Jul 31 2026,
       never used to score momentum. Loaded only by exam.py after the freeze.

Output (cached as a pickle in _local): {"bars": {(ticker, day): DataFrame[open,high,low,close,volume] indexed
by bar start}, "daily": {ticker: DataFrame[date-indexed open,high,low,close,volume]}, "index": "NIFTY 50"}.
"""
from __future__ import annotations

import csv
import gzip
import json
import pickle
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
RAW = HERE.parents[1] / "kite" / "2026-10-05-momentum-h1" / "_local" / "raw"
INDEX = "NIFTY 50"


def _frames(rows):
    frame = pd.DataFrame(rows, columns=["stamp", "open", "high", "low", "close", "volume"])
    frame["stamp"] = pd.to_datetime(frame["stamp"])
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = frame[col].astype(float)
    return frame.drop_duplicates("stamp").sort_values("stamp").set_index("stamp")


def _split_days(ticker, frame, out):
    for day, group in frame.groupby(frame.index.date):
        group = group[(group.index.time >= pd.Timestamp("09:15").time())
                      & (group.index.time <= pd.Timestamp("15:15").time())]
        if len(group):
            out[(ticker, day.isoformat())] = group


def load_dev():
    cache = LOCAL / "dev.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    intra, daily = {}, {}
    with gzip.open(LOCAL / "prod_15m_aug_nov.csv.gz", "rt", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        for kind, ticker, stamp, *values in reader:
            (intra if kind == "I" else daily).setdefault(ticker, []).append([stamp, *values])
    bars = {}
    for ticker, rows in intra.items():
        _split_days(ticker, _frames(rows), bars)
    days = {t: _frames(rows) for t, rows in daily.items()}
    data = {"bars": bars, "daily": days, "index": INDEX, "window": "DEV"}
    cache.write_bytes(pickle.dumps(data))
    return data


def _kite_rows(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    candles = payload.get("candles") if isinstance(payload, dict) else payload
    if isinstance(payload, dict) and "data" in payload:
        candles = payload["data"].get("candles", candles)
    rows = []
    for candle in candles or []:
        if isinstance(candle, dict):
            stamp = candle.get("date") or candle.get("datetime")
            values = [candle.get(k) for k in ("open", "high", "low", "close", "volume")]
        else:
            stamp, values = candle[0], list(candle[1:6])
        rows.append([str(stamp)[:19].replace("T", " "), *values])
    return rows


def load_exam():
    cache = LOCAL / "exam.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    intra, daily = {}, {}
    for path in sorted(RAW.glob("*.json")):
        name = path.name.replace("%20", " ")
        ticker, kind = name.split("_")[0], name.split("_")[1]
        rows = _kite_rows(path)
        (intra if kind == "15minute" else daily).setdefault(ticker, []).extend(rows)
    bars = {}
    for ticker, rows in intra.items():
        _split_days(ticker, _frames(rows), bars)
    days = {t: _frames(rows) for t, rows in daily.items()}
    data = {"bars": bars, "daily": days, "index": INDEX, "window": "EXAM"}
    cache.write_bytes(pickle.dumps(data))
    return data
