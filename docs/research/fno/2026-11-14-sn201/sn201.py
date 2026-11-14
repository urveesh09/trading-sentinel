"""SN201 - seal the new data (PLAN.md). Lean read-only mirrors from the Breeze history database (opened read-only,
short queries, never written) into _local:
  NIFTY exam  - index 1-minute rows 2021-09-01 .. 2022-03-31; option rows 14:55-15:29 of weekly expiries
                2021-12-02 .. 2022-03-24 (the weeks with complete option days; Oct-Nov 2021 options not downloaded yet);
  SENSEX exam - index 1-minute rows 2024-01-01 .. 2026-04-30; option rows 14:55-15:29 of expiries 2024-10-01 .. 2026-04-30.
Audit = counts only (rows, sessions, expiries, strikes per session, expiry days with an index for settlement). No price
is read or printed; the exams are opened once by SN209."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk  # noqa: E402

SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
SPECS = {
    "NIFTY": {"path": wk.EXAM_NIFTY, "index": ("2021-09-01", "2022-04-01"), "expiry": ("2021-12-02", "2022-03-24")},
    "SENSEX": {"path": wk.EXAM_SENSEX, "index": ("2024-01-01", "2026-05-01"), "expiry": ("2024-10-01", "2026-04-30")},
}
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


def months(lo, hi):
    y, m = int(lo[:4]), int(lo[5:7])
    while f"{y:04d}-{m:02d}-01" < hi:
        nxt = (y + (m == 12), 1 if m == 12 else m + 1)
        yield f"{y:04d}-{m:02d}-01", min(hi, f"{nxt[0]:04d}-{nxt[1]:02d}-01")
        y, m = nxt


def mirror(und, spec):
    path = spec["path"]
    if path.exists():
        return
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    part = path.with_name(path.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    ins = "INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for lo, hi in months(*spec["index"]):
        rows = src.execute("SELECT * FROM candles WHERE kind='index' AND underlying=? AND interval='1minute' "
                           "AND datetime >= ? AND datetime < ?", (und, lo, hi)).fetchall()
        dst.executemany(ins, rows)
        time.sleep(0.02)
    exps = [r[0] for r in src.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying=? "
                                      "AND expiry >= ? AND expiry <= ?", (und, *spec["expiry"]))]
    for e in exps:
        rows = src.execute("SELECT * FROM candles WHERE kind='option' AND underlying=? AND expiry=? AND interval='1minute' "
                           "AND substr(datetime,12,5) BETWEEN ? AND ?", (und, e, wk.OPT_LO, wk.OPT_HI)).fetchall()
        dst.executemany(ins, rows)
        time.sleep(0.02)
    src.close()
    dst.commit()
    dst.close()
    os.replace(part, path)


def audit(und, spec):
    con = sqlite3.connect(f"file:{spec['path'].as_posix()}?mode=ro", uri=True)
    rows = dict(con.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    idx_days = {r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index'")}
    per = con.execute("SELECT expiry, substr(datetime,1,10), COUNT(DISTINCT strike||opt) FROM candles WHERE kind='option' "
                      "AND substr(datetime,1,10) < substr(expiry,1,10) GROUP BY 1, 2").fetchall()
    con.close()
    exps = sorted({e[:10] for e, _d, _n in per})
    series = sorted(n for _e, _d, n in per)
    sess = {}
    for e, d, _n in per:
        sess.setdefault(e[:10], set()).add(d)
    return {"rows_by_kind": rows, "index_sessions": len(idx_days), "index_first": min(idx_days), "index_last": max(idx_days),
            "expiries": len(exps), "first_expiry": exps[0], "last_expiry": exps[-1],
            "expiries_with_settlement_day_index": sum(e in idx_days for e in exps),
            "option_sessions_per_expiry": {str(n): sum(len(v) == n for v in sess.values()) for n in range(1, 7)},
            "series_per_session": {"min": series[0], "median": series[len(series) // 2], "max": series[-1]},
            "sha256": sha(spec["path"])}


if __name__ == "__main__":
    out_path = HERE / "results-sn201.json"
    if out_path.exists():
        raise SystemExit("SN201 is run once")
    wk.LOCAL.mkdir(exist_ok=True)
    res = {"source": str(SOURCE).replace(str(Path.home()), "~"), "specs": {k: {x: y for x, y in v.items() if x != "path"} for k, v in SPECS.items()}}
    for und, spec in SPECS.items():
        mirror(und, spec)
        res[und] = audit(und, spec)
        print("SN201", und, json.dumps(res[und]), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
