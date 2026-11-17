"""SN316: seal the new history by permitted use (PLAN.md, frozen). Counts and hashes only; no price is printed or used.

Copies, read-only from the history database, in month or day slices (the earlier full-scan ran out of memory):
  2019   _local/mirror-nifty-2019.sqlite  index + futures 1-minute May 15 - Dec 31 2019 (ADX warm-up), options Jul - Dec 2019
  2020   sn248.mirror() into sn231/_local (its own frozen copy), plus per-week counts for the WK-H entry and hedge marks
  2026   _local/seconds-2026q1.sqlite     index + option 1-second rows Jan 16 - Apr 2 2026
and writes seal-sn316.json: sessions, expiries, missing at-the-money pairs (as the download reported), minutes or seconds
per session, the 09:30 halt day, expected-but-empty expiries, lot sizes by date (an exchange fact), SHA-256 of each copy."""
from __future__ import annotations

import collections
import datetime as dt
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
M2019 = LOCAL / "mirror-nifty-2019.sqlite"
S2026 = LOCAL / "seconds-2026q1.sqlite"
CANDLES = """CREATE TABLE candles (
  kind TEXT, underlying TEXT, expiry TEXT, strike REAL, opt TEXT, interval TEXT, datetime TEXT,
  open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
  PRIMARY KEY (kind, underlying, expiry, strike, opt, interval, datetime))"""
INS = "INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
LOTS = {"NIFTY 2019-07..2020-09": 75, "NIFTY 2026": 65}       # NSE contract lot sizes in force on those dates


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def months(lo, hi):
    d = dt.date.fromisoformat(lo)
    end = dt.date.fromisoformat(hi)
    while d < end:
        nxt = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        yield d.isoformat(), min(nxt, end).isoformat()
        d = nxt


def days(lo, hi):
    d = dt.date.fromisoformat(lo)
    end = dt.date.fromisoformat(hi)
    while d < end:
        yield d.isoformat(), (d + dt.timedelta(days=1)).isoformat()
        d += dt.timedelta(days=1)


def copy(dst_path, pieces):
    if dst_path.exists():
        return
    LOCAL.mkdir(parents=True, exist_ok=True)
    part = dst_path.with_name(dst_path.name + ".part")
    part.unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    for sql, args in pieces:
        dst.executemany(INS, src.execute(sql, args).fetchall())
        time.sleep(0.02)
    dst.commit()
    dst.close()
    src.close()
    os.replace(part, dst_path)


def mirror_2019():
    pieces = []
    for kind in ("index", "future"):
        for a, b in months("2019-05-15", "2020-01-01"):
            pieces.append(("SELECT * FROM candles WHERE kind=? AND underlying='NIFTY' AND interval='1minute' AND datetime>=? AND datetime<?", (kind, a, b)))
    for a, b in months("2019-07-01", "2020-01-01"):
        pieces.append(("SELECT * FROM candles WHERE kind='option' AND underlying='NIFTY' AND interval='1minute' AND datetime>=? AND datetime<?", (a, b)))
    copy(M2019, pieces)


def seconds_keys():
    """(day, expiry, strike, CE/PE) of every finished one-second option job Jan 16 - Apr 2 2026, from the downloader's own
    receipts (no price). [Fix before any price: the first version filtered candles by interval and datetime, which the
    table's key cannot seek, so each day scanned the whole 8.6 GB database; it was stopped after ~15 minutes.]"""
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    out = set()
    for (k,) in src.execute("SELECT key FROM seconds_receipts WHERE status='ok'"):
        p = k.split("|")
        if len(p) >= 7 and p[0] == "seconds" and p[1] == "NIFTY" and p[4] in ("CE", "PE") and "2026-01-16" <= p[5][:10] <= "2026-04-02":
            out.add((p[5][:10], p[2], float(p[3]), p[4]))
    src.close()
    return sorted(out)


def mirror_seconds():
    keys = seconds_keys()
    pieces = [("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' AND interval='1second' "
               "AND datetime>=? AND datetime<?", (d + " 09:15:00", d + " 15:31:00")) for d in sorted({k[0] for k in keys})]
    pieces += [("SELECT * FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND strike=? AND opt=? AND interval='1second' "
                "AND datetime>=? AND datetime<?", (e, k, o, d + " 09:15:00", d + " 15:31:00")) for d, e, k, o in keys]
    copy(S2026, pieces)


def count_minutes(path, lo, hi):
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    idx = dict(con.execute("SELECT substr(datetime,1,10), COUNT(*) FROM candles WHERE kind='index' AND interval='1minute' AND datetime>=? AND datetime<? GROUP BY 1", (lo, hi)).fetchall())
    fut = dict(con.execute("SELECT substr(datetime,1,10), COUNT(*) FROM candles WHERE kind='future' AND interval='1minute' AND datetime>=? AND datetime<? GROUP BY 1", (lo, hi)).fetchall())
    exps = [r[0][:10] for r in con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND datetime>=? AND datetime<?", (lo, hi))]
    ser = dict(con.execute("SELECT substr(datetime,1,10), COUNT(DISTINCT strike || opt || expiry) FROM candles WHERE kind='option' AND datetime>=? AND datetime<? GROUP BY 1", (lo, hi)).fetchall())
    halts = sorted(d for d in idx if not con.execute("SELECT 1 FROM candles WHERE kind='index' AND datetime=?", (d + " 09:30:00",)).fetchone())
    con.close()
    q = collections.defaultdict(list)
    for d in idx:
        q[f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}"].append(d)
    return {"quarters": {k: {"sessions": len(v), "index_minutes_min": min(idx[d] for d in v), "index_minutes_median": sorted(idx[d] for d in v)[len(v) // 2],
                             "sessions_without_futures": sum(1 for d in v if d not in fut), "sessions_without_options": sum(1 for d in v if d not in ser),
                             "option_series_median": sorted(ser.get(d, 0) for d in v)[len(v) // 2]} for k, v in sorted(q.items())},
            "expiries": len(sorted(set(exps))), "sessions_without_0930_index_bar": halts}


def week_counts_2020():
    """Per weekly expiry Jan 2 - Sep 24 2020: WK-H's entry day (the first session after the last weekend or holiday before
    the expiry), the option series printing at 15:15 that day, and futures minutes at the 15-minute marks to expiry."""
    sys.path.insert(0, str(FNO / "2026-11-15-sn231"))
    import sn248
    sn248.mirror()
    cov = sn248.coverage()
    con = sqlite3.connect(f"file:{sn248.LEAN.as_posix()}?mode=ro", uri=True)
    fcon = sqlite3.connect(f"file:{sn248.FUT.as_posix()}?mode=ro", uri=True)
    sess = sorted(r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index'"))
    exps = sorted(r[0][:10] for r in con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option'"))
    out = []
    for e in exps:
        if not ("2020-01-02" <= e <= "2020-09-24"):
            continue
        before = [d for d in sess if d < e]
        gap_after = [d for k, d in enumerate(before[1:], 1) if (dt.date.fromisoformat(d) - dt.date.fromisoformat(before[k - 1])).days > 1]
        entry = gap_after[-1] if gap_after else None
        n1515 = con.execute("SELECT COUNT(*) FROM candles WHERE kind='option' AND expiry LIKE ? AND datetime=?", (e + "%", f"{entry} 15:15:00")).fetchone()[0] if entry else 0
        marks = [d for d in sess if entry and entry < d <= e]
        fut_marks = sum(1 for d in marks for hm in ("09:15", "10:15", "11:15", "12:15", "13:15", "14:15")
                        if fcon.execute("SELECT 1 FROM candles WHERE kind='future' AND datetime=?", (f"{d} {hm}:00",)).fetchone())
        out.append({"expiry": e, "entry_day": entry, "series_at_1515": n1515, "sessions_to_expiry": len(marks),
                    "futures_marks_present": fut_marks, "futures_marks_expected": 6 * len(marks)})
    expected = []
    d = dt.date(2020, 1, 2)
    while d <= dt.date(2020, 9, 24):
        expected.append(d.isoformat())
        d += dt.timedelta(days=7)
    missing = [x for x in expected if not any(abs((dt.date.fromisoformat(x) - dt.date.fromisoformat(e)).days) <= 2 for e in exps)]
    con.close()
    fcon.close()
    return {"sn248_coverage": cov, "weeks": out, "thursday_expiries_without_options": missing,
            "lean_sha256": sha(sn248.LEAN), "fut_sha256": sha(sn248.FUT)}


def seconds_counts():
    con = sqlite3.connect(f"file:{S2026.as_posix()}?mode=ro", uri=True)
    per = collections.defaultdict(dict)
    for d, kind, opt, n, k in con.execute("SELECT substr(datetime,1,10), kind, opt, COUNT(*), COUNT(DISTINCT strike || expiry) FROM candles GROUP BY 1, 2, 3"):
        per[d][f"{kind}{opt or ''}"] = (n, k)
    con.close()
    full = [d for d, v in per.items() if v.get("index", (0, 0))[0] >= 20000 and "optionCE" in v and "optionPE" in v]
    return {"days": len(per), "days_with_index_and_both_options": len(full),
            "index_seconds_median": sorted(v.get("index", (0, 0))[0] for v in per.values())[len(per) // 2] if per else 0,
            "days_with_more_than_one_strike": sorted(d for d, v in per.items() if v.get("optionCE", (0, 1))[1] > 1 or v.get("optionPE", (0, 1))[1] > 1),
            "short_days": sorted(d for d, v in per.items() if d not in full), "sha256": sha(S2026)}


if __name__ == "__main__":
    out = HERE / "seal-sn316.json"
    if out.exists():
        raise SystemExit("SN316's seal is written once")
    assert SOURCE.exists(), SOURCE
    mirror_2019()
    mirror_seconds()
    seal = {"written": dt.datetime.now().isoformat(timespec="seconds"), "lots": LOTS,
            "download_reports": {"2019Q3": "Jul 30 without the ATM pair", "2019Q4": "Nov 6 without the ATM pair",
                                 "2020Q1": "Feb 1 (Budget Saturday) in daily bars only; Mar 13 no 09:30 index bar (market-wide halt); options for the Apr 2 expiry empty (it moved to Apr 1)",
                                 "2020Q2": "Apr 1 without the ATM pair", "2020Q3": "clean"},
            "nifty_2019": {**count_minutes(M2019, "2019-07-01", "2020-01-01"), "sha256": sha(M2019)},
            "nifty_2020_wkh": week_counts_2020(),
            "seconds_2026q1": seconds_counts(),
            "uses": {"2019": "SN318 only", "2020": "SN317 (frozen SN248) only", "seconds 2026 Jan 16 - Apr 2": "SN78's discharge, then SN319-SN322's test"}}
    out.write_text(json.dumps(seal, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in seal.items() if k != "nifty_2020_wkh"}, indent=1)[:4000])
    print("2020 weeks", len(seal["nifty_2020_wkh"]["weeks"]), "missing thursdays", seal["nifty_2020_wkh"]["thursday_expiries_without_options"])
    print("2020 weeks short", [w for w in seal["nifty_2020_wkh"]["weeks"] if w["series_at_1515"] < 2 or w["futures_marks_present"] < w["futures_marks_expected"]])
