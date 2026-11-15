"""SN195 - NIFTY 2022 sealed (PLAN.md). The owner (Nov 13): use every dataset on the device. NIFTY Apr - Dec 2022
(ICICI Breeze targets nifty-2022-q2/q3/q4, finished) is mirrored read-only, in short pieces, from the Breeze history
database into _local/mirror-2022.sqlite (index / future / option 1-minute rows from 2022-02-01 to 2022-12-31, every
NIFTY / BANKNIFTY daily bar before 2023), exported with the house year-dataset tool (O29f yeardata.export) to
_local/dataset-nifty-2022 and hashed. This script audits the data only (sessions, option strikes per session, minute
coverage); no strategy reads 2022 before SN196's freeze."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
LOCAL = HERE / "_local"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
MIRROR = LOCAL / "mirror-2022.sqlite"
DATASET = LOCAL / "dataset-nifty-2022"
WINDOW = ("2022-04-01", "2022-12-31")
CANDLES = """CREATE TABLE candles (
  kind TEXT, underlying TEXT, expiry TEXT, strike REAL, opt TEXT, interval TEXT, datetime TEXT,
  open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
  PRIMARY KEY (kind, underlying, expiry, strike, opt, interval, datetime))"""


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def mirror():
    if MIRROR.exists():
        return
    LOCAL.mkdir(exist_ok=True)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    part = MIRROR.with_name(MIRROR.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    for m in range(2, 13):
        lo, hi = f"2022-{m:02d}-01", (f"2022-{m + 1:02d}-01" if m < 12 else "2023-01-01")
        for kind in ("index", "future", "option"):
            rows = src.execute("SELECT * FROM candles WHERE kind=? AND underlying='NIFTY' AND datetime >= ? AND datetime < ?",
                               (kind, lo, hi)).fetchall()
            dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            time.sleep(0.02)
    rows = src.execute("SELECT * FROM candles WHERE kind='daily' AND underlying IN ('NIFTY','BANKNIFTY') AND datetime < '2023-01-01'").fetchall()
    dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    src.close()
    dst.commit()
    dst.close()
    os.replace(part, MIRROR)


def export():
    if (DATASET / "manifest.json").exists():
        return
    sys.path.insert(0, str(FNO / "2026-10-29-year-genome"))
    import yeardata
    yeardata.DOWNLOAD = MIRROR
    yeardata.export("NIFTY", WINDOW[0], WINDOW[1], DATASET)


if __name__ == "__main__":
    out_path = HERE / "results-sn195.json"
    if out_path.exists():
        raise SystemExit("SN195 is scored once")
    mirror()
    export()
    con = sqlite3.connect(f"file:{MIRROR.as_posix()}?mode=ro", uri=True)
    counts = dict(con.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    con.close()
    man = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(FNO / "2026-11-12-sn01"))
    import sn01_data as D
    D.DATASETS["2022"] = DATASET
    built = D.build_year("2022")["sessions"]
    import numpy as np
    strikes = [len(s["options"]) for s in built.values()]
    cover = [float((~np.isnan(s["index"][3])).mean()) for s in built.values()]
    res = {"mirror_rows_by_kind": counts, "mirror_sha256": sha(MIRROR), "dataset_manifest_sha256": sha(DATASET / "manifest.json"),
           "dataset_files_sha256": man["files_sha256"], "export_sessions": len(man["sessions"]),
           "lab_sessions_non_expiry_with_options": len(built), "first": min(built), "last": max(built),
           "option_series_per_session": {"min": int(min(strikes)), "median": float(np.median(strikes)), "max": int(max(strikes))},
           "index_minute_coverage_median": round(float(np.median(cover)), 4)}
    print("SN195", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
