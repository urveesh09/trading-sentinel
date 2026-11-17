"""SN456 / SN458 / SN473 data step (separate from scoring): a sealed copy of NIFTY futures 1-minute bars.

Reads the Breeze history read-only (kind='future', underlying='NIFTY', interval='1minute'), every contract on every day from
2019-02-18 to 2026-10-28, and writes _local/fut.npz:
  days      (D,) ISO dates
  expiries  (D, K) ISO expiry per slot ('' = empty), contracts sorted by expiry
  ohlcv     (D, K, 390, 5) float32 open/high/low/close/volume for minute index i = bar starting 09:15 + i (NaN = no bar)
and _local/fut.json with the row count, the source file's size and mtime, and the npz sha256. Scorers assert that hash.
No return, feature or outcome is computed here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOC = HERE / "_local"
SRC = "C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
NM, K = 390, 4


def main():
    LOC.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    rows = c.execute("SELECT expiry, datetime, open, high, low, close, volume FROM candles WHERE kind='future' AND underlying='NIFTY' "
                     "AND interval='1minute' AND datetime>='2019-02-18 00:00' AND datetime<'2026-10-29 00:00'").fetchall()
    by = {}
    for e, t, o, h, lo, cl, v in rows:
        i = int(t[11:13]) * 60 + int(t[14:16]) - 555
        if 0 <= i < NM:
            by.setdefault(t[:10], {}).setdefault(e, []).append((i, o, h, lo, cl, v or 0.0))
    days = sorted(by)
    exps = np.full((len(days), K), "", dtype="<U10")
    arr = np.full((len(days), K, NM, 5), np.nan, dtype=np.float32)
    dropped = 0
    for a, d in enumerate(days):
        es = sorted(by[d])
        dropped += max(0, len(es) - K)
        for b, e in enumerate(es[:K]):
            exps[a, b] = e
            for i, o, h, lo, cl, v in by[d][e]:
                arr[a, b, i] = (o, h, lo, cl, v)
    out = LOC / "fut.npz"
    np.savez_compressed(out, days=np.array(days), expiries=exps, ohlcv=arr)
    st = os.stat(SRC)
    meta = {"rows": len(rows), "days": len(days), "first": days[0], "last": days[-1], "contracts_dropped_beyond_4": dropped,
            "source_size": st.st_size, "source_mtime": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "npz_sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
    (LOC / "fut.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
