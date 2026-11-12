"""SN09 data: per-session option open interest on the SN01 minute grid (read-only from the sealed year datasets).

OI in these candles moves every third minute (the exchange's snapshot rhythm), so a minute's OI is the last snapshot
at or before that minute; minutes before the first print carry the first print (back-filled only inside the first
minutes of the session, where no signal may fire anyway: SN09 entries start at 09:30).
"""
from __future__ import annotations

import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-12-sn01"))
import sn01_data as D  # noqa: E402

LOCAL = HERE / "_local"


def build(year: str) -> None:
    cache = D.load_year(year)["sessions"]
    con = sqlite3.connect(f"file:{(D.DATASETS[year] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    out = {}
    for day, s in cache.items():
        arrs = {}
        for stamp, strike, opt, oi in con.execute(
                "SELECT datetime, strike, opt, oi FROM candles WHERE kind='option' AND expiry=? AND datetime >= ? AND "
                "datetime < ? ORDER BY datetime", (s["expiry"], day, day + "~")):
            i = D.minute_index(stamp)
            if 0 <= i < D.N_MIN and oi is not None:
                arrs.setdefault((int(round(strike)), opt), np.full(D.N_MIN, np.nan))[i] = oi
        out[day] = {k: D._ffill(v).astype(np.float32) for k, v in arrs.items()}
    con.close()
    LOCAL.mkdir(exist_ok=True)
    with open(LOCAL / f"oi-{year}.pkl", "wb") as fh:
        pickle.dump({"manifest_sha256": D.manifest_sha(year), "oi": out}, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(year, len(out), flush=True)


def load(year: str) -> dict:
    with open(LOCAL / f"oi-{year}.pkl", "rb") as fh:
        d = pickle.load(fh)
    assert d["manifest_sha256"] == D.manifest_sha(year)
    return d["oi"]


if __name__ == "__main__":
    for y in (sys.argv[1:] or list(D.DATASETS)):
        build(y)
