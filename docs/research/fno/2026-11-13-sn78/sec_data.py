"""SN78 data: the sealed 1-second archive (copy of the download agent's nifty-daily-1second-20261113.zip, sha256 in
_local/zip.sha256) as per-day arrays on a 22,500-second grid (09:15:00 .. 15:29:59). Read-only; never the download.

Per day: index OHLC, the opening-ATM call and put OHLC (NaN where Breeze had no second), their strike and expiry.
Prices carry forward only for marks; a fill needs a printed second.
"""
from __future__ import annotations

import csv
import hashlib
import io
import pickle
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ZIP = HERE / "_local" / "nifty-daily-1second-20261113.zip"
CACHE = HERE / "_local" / "seconds.pkl"
N = 22500


def sec_index(stamp: str) -> int:
    return (int(stamp[11:13]) * 60 + int(stamp[14:16]) - 555) * 60 + int(stamp[17:19])


def build() -> dict:
    sha = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    assert sha == (HERE / "_local" / "zip.sha256").read_text().strip(), "the sealed copy changed"
    z = zipfile.ZipFile(ZIP)
    days = {}
    for name in sorted(n for n in z.namelist() if n.endswith(".csv")):
        arr = {}
        meta = {}
        with z.open(name) as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                s = r["series"].strip().upper()
                k = sec_index(r["datetime_ist"])
                if not 0 <= k < N:
                    continue
                a = arr.setdefault(s, np.full((4, N), np.nan, dtype=np.float32))
                a[:, k] = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
                if s != "INDEX":
                    meta[s] = (float(r["strike"]), r["expiry"])
        days[name[:-4]] = {"series": arr, "meta": meta}
    out = {"sha256": sha, "days": days}
    with open(CACHE, "wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return out


def load() -> dict:
    with open(CACHE, "rb") as fh:
        return pickle.load(fh)


if __name__ == "__main__":
    d = build()
    for day, v in list(d["days"].items())[:3] + list(d["days"].items())[-2:]:
        print(day, {s: int(np.isfinite(a[3]).sum()) for s, a in v["series"].items()}, v["meta"])
    print("days", len(d["days"]))
