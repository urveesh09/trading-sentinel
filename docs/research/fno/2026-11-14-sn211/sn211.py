"""SN211 - engine and data (PLAN.md). Full-minute read-only mirrors of the NIFTY and SENSEX exam expiries' option rows
(sessions before expiry; from the Breeze history database, short read-only queries) into _local; counts and hashes.
Parity: wk2.simulate with a rule that cannot fire (breach 99) reproduces wk.trade for both bases, trade by trade, on
development and on the second-look samples (only differences and counts are printed, no net)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk2  # noqa: E402

wk = wk2.wk
sys.path.insert(0, str(wk.HERE))
import sn201  # noqa: E402

NEVER = {"breach": 99.0}


def mirror(und, path, lo, hi):
    if path.exists():
        return
    src = sqlite3.connect(f"file:{sn201.SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    part = path.with_name(path.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(sn201.CANDLES)
    exps = [r[0] for r in src.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying=? AND expiry >= ? "
                                      "AND expiry <= ?", (und, lo, hi))]
    for e in exps:
        rows = src.execute("SELECT * FROM candles WHERE kind='option' AND underlying=? AND expiry=? AND interval='1minute' "
                           "AND substr(datetime,1,10) < substr(expiry,1,10)", (und, e)).fetchall()
        dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        time.sleep(0.02)
    src.close()
    dst.commit()
    dst.close()
    os.replace(part, path)


def parity(mk, data, mins, weeks):
    out = {}
    for tag, base in wk2.BASES.items():
        a = {t["expiry"]: t["net"] for t in wk.book(mk, data, weeks, base)}
        b = {t["expiry"]: t["net"] for t in wk2.book2(mk, data, mins, weeks, base, NEVER)}
        out[tag] = {"trades_wk": len(a), "trades_wk2": len(b), "same_weeks": set(a) == set(b),
                    "max_abs_diff_rs": round(max((abs(a[e] - b[e]) for e in a if e in b), default=0.0), 6)}
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn211.json"
    if out_path.exists():
        raise SystemExit("SN211 is run once")
    wk2.LOCAL.mkdir(exist_ok=True)
    res = {}
    for und, (lo, hi) in (("NIFTY", ("2021-12-02", "2022-03-24")), ("SENSEX", ("2024-10-01", "2026-04-30"))):
        p = wk2.EXAM_FULL[und]
        mirror(und, p, lo, hi)
        con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
        n, ne, nd = con.execute("SELECT COUNT(*), COUNT(DISTINCT expiry), COUNT(DISTINCT substr(datetime,1,10)) FROM candles").fetchone()
        con.close()
        res[f"mirror {und}"] = {"rows": n, "expiries": ne, "sessions": nd, "sha256": sn201.sha(p)}
        print("SN211", und, json.dumps(res[f"mirror {und}"]), flush=True)
    D = wk.dev_data()
    W = wk.expiries(D)
    res["parity development"] = parity(wk.NIFTY, D, wk2.Minutes("dev"), wk.split(W, "dev"))
    res["parity TEST"] = parity(wk.NIFTY, D, wk2.Minutes("dev"), wk.split(W, "test"))
    for und, mk in (("NIFTY", wk.NIFTY), ("SENSEX", wk.SENSEX)):
        E = wk.exam_data(und)
        res[f"parity {und}"] = parity(mk, E, wk2.Minutes(und), wk.expiries(E))
    print("SN211 parity", json.dumps({k: v for k, v in res.items() if k.startswith("parity")}), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
