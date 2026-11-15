"""SN221 - seal the data (PLAN.md). Read-only mirrors from the Breeze history database (opened mode=ro, short queries,
never written) into _local:
  EXAM lean  - NIFTY index 1-minute 2020-06-01 .. 2021-11-30; option rows 14:55-15:29 of expiries 2020-10-01 .. 2021-11-25;
  EXAM full  - option rows at every minute of those expiries (sessions before expiry);
  futures    - NIFTY 2020-06-01 .. 2021-11-30 (EXAM), NIFTY 2021-11-20 .. 2022-03-31 (N2122), SENSEX 2024-09-25 .. 2026-04-30.
The audit is counts and hashes only; no price is read into a result or printed."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk3  # noqa: E402

wk = wk3.wk
sys.path.insert(0, str(wk.HERE))
import sn201  # noqa: E402

INS = "INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
FUT_SPECS = {"EXAM": ("NIFTY", "2020-06-01", "2021-12-01"), "N2122": ("NIFTY", "2021-11-20", "2022-04-01"),
             "SENSEX": ("SENSEX", "2024-09-25", "2026-05-01")}


def _open(path):
    part = path.with_name(path.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(sn201.CANDLES)
    return part, dst


def _close(part, dst, path):
    dst.commit()
    dst.close()
    os.replace(part, path)


def exam_expiries(src):
    return [r[0] for r in src.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying='NIFTY' "
                                      "AND expiry >= ? AND expiry <= ? ORDER BY 1", wk3.EXAM_EXPIRY)]


def mirror_exam(src):
    if not wk3.EXAM_LEAN.exists():
        part, dst = _open(wk3.EXAM_LEAN)
        for lo, hi in sn201.months(*wk3.EXAM_INDEX):
            dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND "
                                             "interval='1minute' AND datetime >= ? AND datetime < ?", (lo, hi)).fetchall())
            time.sleep(0.02)
        for e in exam_expiries(src):
            dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND "
                                             "interval='1minute' AND substr(datetime,12,5) BETWEEN ? AND ?",
                                             (e, wk.OPT_LO, wk.OPT_HI)).fetchall())
            time.sleep(0.02)
        _close(part, dst, wk3.EXAM_LEAN)
    if not wk3.EXAM_FULL.exists():
        part, dst = _open(wk3.EXAM_FULL)
        for e in exam_expiries(src):
            dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND "
                                             "interval='1minute' AND substr(datetime,1,10) < substr(expiry,1,10)", (e,)).fetchall())
            time.sleep(0.02)
        _close(part, dst, wk3.EXAM_FULL)


def mirror_fut(src, name):
    path = wk3.FUT_MIRROR[name]
    if path.exists():
        return
    und, lo, hi = FUT_SPECS[name]
    part, dst = _open(path)
    for a, b in sn201.months(lo, hi):
        dst.executemany(INS, src.execute("SELECT * FROM candles WHERE kind='future' AND underlying=? AND interval='1minute' "
                                         "AND datetime >= ? AND datetime < ?", (und, a, b)).fetchall())
        time.sleep(0.02)
    _close(part, dst, path)


def audit_exam():
    con = sqlite3.connect(f"file:{wk3.EXAM_LEAN.as_posix()}?mode=ro", uri=True)
    rows = dict(con.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    idx_days = sorted(r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index'"))
    per = con.execute("SELECT substr(expiry,1,10), substr(datetime,1,10), COUNT(DISTINCT strike||opt) FROM candles WHERE "
                      "kind='option' AND substr(datetime,12,5)='15:15' AND substr(datetime,1,10) < substr(expiry,1,10) "
                      "GROUP BY 1, 2").fetchall()
    con.close()
    sess = {}
    for e, d, n in per:
        sess.setdefault(e, []).append(n)
    series = sorted(n for _e, _d, n in per)
    con = sqlite3.connect(f"file:{wk3.EXAM_FULL.as_posix()}?mode=ro", uri=True)
    nf, nfe = con.execute("SELECT COUNT(*), COUNT(DISTINCT expiry) FROM candles").fetchone()
    con.close()
    return {"lean_rows_by_kind": rows, "index_sessions": len(idx_days), "index_first": idx_days[0], "index_last": idx_days[-1],
            "expiries": len(sess), "first_expiry": min(sess), "last_expiry": max(sess),
            "expiries_with_expiry_day_index": sum(e in set(idx_days) for e in sess),
            "sessions_per_expiry_at_1515": {str(n): sum(len(v) == n for v in sess.values()) for n in range(1, 9)},
            "series_at_1515": {"min": series[0], "median": series[len(series) // 2], "max": series[-1]},
            "full_rows": nf, "full_expiries": nfe,
            "sha256": {"lean": sn201.sha(wk3.EXAM_LEAN), "full": sn201.sha(wk3.EXAM_FULL)}}


def audit_fut(name):
    p = wk3.FUT_MIRROR[name]
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    n, nd, ne = con.execute("SELECT COUNT(*), COUNT(DISTINCT substr(datetime,1,10)), COUNT(DISTINCT expiry) FROM candles").fetchone()
    con.close()
    return {"rows": n, "sessions": nd, "contracts": ne, "sha256": sn201.sha(p)}


if __name__ == "__main__":
    out_path = HERE / "results-sn221.json"
    if out_path.exists():
        raise SystemExit("SN221 is run once")
    wk3.LOCAL.mkdir(exist_ok=True)
    src = sqlite3.connect(f"file:{wk3.SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    mirror_exam(src)
    for name in FUT_SPECS:
        mirror_fut(src, name)
    src.close()
    res = {"source": str(wk3.SOURCE).replace(str(Path.home()), "~"), "exam_expiry_range": wk3.EXAM_EXPIRY,
           "exam_index_range": wk3.EXAM_INDEX, "EXAM": audit_exam()}
    print("SN221 EXAM", json.dumps(res["EXAM"]), flush=True)
    for name in FUT_SPECS:
        res[f"futures {name}"] = audit_fut(name)
        print("SN221 futures", name, json.dumps(res[f"futures {name}"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
