"""SN366 gate D: the 2022 (Jan - Dec) and late-2021 (Sep - Dec, paper evidence only) data points for N08's repointed stack
(n08_lab.POINTS["2022"] / ["2021L"]), from data already on this PC, following exam_2023.py's order. Counts and hashes
only: no price is read out or shown before the replays.

    python sn366_build.py mirror 2022|2021L     read-only copy of NIFTY index / future / option 1-minute rows (key-seek by
                                                request group), Muhurat evenings excluded (2022-10-24, 2021-11-04)
    python sn366_build.py daily 2022|2021L      daily bars: Breeze's own daily rows where they exist (2022 onward), else
                                                bars made from the 1-minute index (09:15 open, high, low, last close at or
                                                before 15:29), from Jan 2020; >= 250 bars before the window; a 2022
                                                overlap check compares made bars with Breeze's (written to the receipt)
    N08_YEAR=<p> python sn366_build.py export <p>   yeardata.export into the point's dataset
    N08_YEAR=<p> python sn366_build.py warm <p> --jobs 3
    N08_YEAR=<p> python sn366_build.py bind <p>     results-sn366-bind-<p>.json: committed before any replay
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import pickle
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
WINDOWS = {"2022": ("2022-01-01", "2022-12-31"), "2021L": ("2021-09-01", "2021-12-31")}
MUHURAT = ("2022-10-24", "2021-11-04")
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


def shift(day, n):
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def months(lo, hi):
    y, m = int(lo[:4]), int(lo[5:7])
    while f"{y}-{m:02d}-01" <= hi:
        a = f"{y}-{m:02d}-01"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        yield a, f"{y}-{m:02d}-01"


def mirror(p):
    lo, hi = WINDOWS[p]
    target = LOCAL / f"mirror-{p}.sqlite"
    if target.exists():
        raise SystemExit(f"{target} exists; a sealed copy is never rewritten")
    LOCAL.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    keys = [k for (k,) in src.execute("SELECT key FROM requests WHERE status IN ('ok','empty') AND (key LIKE 'future|NIFTY|%' OR key LIKE 'option|NIFTY|%')")]
    a, b = shift(lo, -31), shift(hi, 1)
    groups = sorted({(k.split("|")[0], k.split("|")[2]) for k in keys if shift(lo, -35) <= k.split("|")[2] <= shift(hi, 100)})
    part = target.with_name(target.name + ".part")
    part.unlink(missing_ok=True)
    dst = sqlite3.connect(part)
    dst.execute(CANDLES)
    keep = "datetime >= ? AND datetime < ? AND interval='1minute' AND substr(datetime, 1, 10) NOT IN (?, ?)"
    for kind, expiry in groups:
        rows = src.execute(f"SELECT * FROM candles WHERE kind=? AND underlying='NIFTY' AND expiry=? AND {keep}", (kind, expiry, a, b, *MUHURAT)).fetchall()
        dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        time.sleep(0.02)
    for m0, m1 in months(a, b):
        rows = src.execute("SELECT * FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' AND interval='1minute' "
                           "AND datetime >= ? AND datetime < ? AND substr(datetime, 1, 10) NOT IN (?, ?)", (max(m0, a), min(m1, b), *MUHURAT)).fetchall()
        dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    rows = src.execute("SELECT * FROM candles WHERE kind='daily' AND underlying IN ('NIFTY','BANKNIFTY') AND datetime < ?", (b,)).fetchall()
    dst.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    src.close()
    dst.commit()
    counts = dict(dst.execute("SELECT kind, COUNT(*) FROM candles GROUP BY kind").fetchall())
    dst.close()
    os.replace(part, target)
    rec = {"point": p, "rule": f"NIFTY 1-minute rows {a} .. {hi} (index / future / option groups with expiry {shift(lo, -35)} .. {shift(hi, 100)}), "
                               f"without the Muhurat evenings {MUHURAT}; daily bars before {b}", "groups": len(groups), "rows_by_kind": counts, "sha256": sha(target)}
    (HERE / f"results-sn366-mirror-{p}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print("mirror", json.dumps(rec), flush=True)


def daily(p):
    lo, hi = WINDOWS[p]
    target = LOCAL / f"daily-{p}.json"
    if target.exists():
        raise SystemExit(f"{target} exists")
    src = sqlite3.connect(f"file:{SOURCE.as_posix()}?mode=ro", uri=True, timeout=60)
    official = {r[0][:10]: tuple(map(float, r[1:])) for r in src.execute(
        "SELECT datetime, open, high, low, close FROM candles WHERE kind='daily' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' AND datetime < ?", (shift(hi, 1),))}
    made = {}
    for m0, m1 in months("2020-01-01", shift(hi, 1)):
        rows = src.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' "
                           "AND interval='1minute' AND datetime >= ? AND datetime < ? ORDER BY datetime", (m0, m1)).fetchall()
        by = {}
        for t, o, h, l, c in rows:
            if "09:15" <= t[11:16] <= "15:29" and t[:10] not in MUHURAT:
                by.setdefault(t[:10], []).append((t, o, h, l, c))
        for d, xs in by.items():
            if len(xs) >= 300:
                made[d] = (float(xs[0][1]), max(float(x[2]) for x in xs), min(float(x[3]) for x in xs), float(xs[-1][4]))
    src.close()
    first_official = min(official) if official else None
    days = sorted(set(made) | set(official))
    out, source = [], {"official": 0, "made": 0}
    for d in days:
        if d > hi:
            continue
        if d in official and d >= "2022-01-01":
            out.append([d, *official[d]])
            source["official"] += 1
        elif d in made and d < "2022-01-01":
            out.append([d, *made[d]])
            source["made"] += 1
    before = sum(1 for r in out if r[0] < lo)
    assert before >= 250, ("too little history before the window", before)
    both = sorted(d for d in made if d in official and d >= "2022-01-01")
    diffs = {k: max((abs(made[d][i] - official[d][i]) for d in both), default=None) for i, k in enumerate(("open", "high", "low", "close"))}
    mean_close = sum(abs(made[d][3] - official[d][3]) for d in both) / max(1, len(both))
    target.write_text(json.dumps({"rows": out}), encoding="utf-8")
    rec = {"point": p, "bars": len(out), "first": out[0][0], "last": out[-1][0], "bars_before_window": before, "by_source": source,
           "first_official_daily_row": first_official,
           "overlap_check_2022": {"days": len(both), "max_abs_diff_points": diffs, "mean_abs_close_diff_points": round(mean_close, 2)},
           "sha256": sha(target)}
    (HERE / f"results-sn366-daily-{p}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print("daily", json.dumps(rec), flush=True)


def lab(p):
    assert os.environ.get("N08_YEAR") == p, "set N08_YEAR to the point before export / warm / bind"
    sys.path.insert(0, str(HERE.parents[1] / "simulation" / "2026-11-01-fno-n08"))
    import n08_lab as N  # noqa: E402
    return N


def export(p):
    N = lab(p)
    point = N.POINTS[p]
    if (point["dataset"] / "manifest.json").exists():
        raise SystemExit("exported once")
    N.Y.yeardata.DOWNLOAD = point["mirror"]
    N.Y.yeardata.export("NIFTY", point["window"][0], point["window"][1], point["dataset"])
    print("exported", p, flush=True)


if os.environ.get("N08_YEAR") in WINDOWS and "warm" in sys.argv:
    _N = lab(os.environ["N08_YEAR"])
    _WARM = _N.POINTS[os.environ["N08_YEAR"]]["local"] / "warm-parts"


def _warm_day(day):
    _source, _day, part, bad = _N.Y.warm_day(("year", day))
    tmp = _WARM / f"{day}.{os.getpid()}.part"
    tmp.write_bytes(pickle.dumps((part, bad), protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, _WARM / f"{day}.pkl")
    return day


def warm(p, jobs):
    N = _N
    Y = N.Y
    point = N.POINTS[p]
    days = json.loads((point["dataset"] / "manifest.json").read_text(encoding="utf-8"))["sessions"]
    if Y.memo_file("year").is_file():
        print("warm: already done", flush=True)
        return
    _WARM.mkdir(parents=True, exist_ok=True)
    Y.memo_file("year").parent.mkdir(parents=True, exist_ok=True)
    todo = [d for d in days if not (_WARM / f"{d}.pkl").is_file()]
    with ProcessPoolExecutor(max_workers=Y.allowed_inflight(jobs)) as ex:
        list(ex.map(_warm_day, todo))
    memo, conflicts = {}, 0
    for d in days:
        part, bad = pickle.loads((_WARM / f"{d}.pkl").read_bytes())
        memo.update(part)
        conflicts += bad
    assert conflicts == 0, f"{conflicts} named signal(s) changed within a closed bar"
    Y.memo_file("year").write_bytes(pickle.dumps(memo, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"warm {p}: {len(memo)} named signals over {len(days)} sessions", flush=True)


def bind(p):
    N = lab(p)
    point = N.POINTS[p]
    manifest = json.loads((point["dataset"] / "manifest.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{(point['dataset'] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    bad = {"nonpositive_ohlc": 0, "incoherent_ohlc": 0, "negative_volume": 0, "negative_oi": 0, "invalid_timestamp": 0}
    by_kind = {}
    for kind, stamp, o, h, l, c, v, oi in con.execute("SELECT kind, datetime, open, high, low, close, volume, oi FROM candles"):
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if len(stamp) != 19:
            bad["invalid_timestamp"] += 1
        if any(x is None or not math.isfinite(x) or x <= 0 for x in (o, h, l, c)):
            bad["nonpositive_ohlc"] += 1
        elif not (l <= o <= h and l <= c <= h):
            bad["incoherent_ohlc"] += 1
        bad["negative_volume"] += v is not None and v < 0
        bad["negative_oi"] += oi is not None and oi < 0
    sessions = manifest["sessions"]
    index = dict(con.execute("SELECT substr(datetime,1,10), COUNT(*) FROM candles WHERE kind='index' GROUP BY 1"))
    no_options = [d for d in sessions if not con.execute("SELECT 1 FROM candles WHERE kind='option' AND substr(datetime,1,10)=? LIMIT 1", (d,)).fetchone()]
    con.close()
    frame = N.F.daily_bars()
    table = N.Y.table("year")
    closed = [d for d in sessions if table[d]["side"].get("adx_abs30") is None]
    out = {"point": p, "window": point["window"], "sessions": len(sessions), "first_last_session": [sessions[0], sessions[-1]],
           "sessions_with_options": len(sessions) - len(no_options), "sessions_without_any_option": no_options,
           "short_sessions": sorted(d for d in sessions if index.get(d, 0) < 300), "rows_by_kind": by_kind, "bad_rows": bad,
           "option_expiries": len(manifest.get("option_expiries", [])), "weekly_expiry_calendar_days": len(manifest.get("weekly_expiry_calendar", {})),
           "daily_bars": len(frame), "daily_first": str(frame.index[0].date()), "daily_last": str(frame.index[-1].date()),
           "bars_before_first_session": int((frame.index < sessions[0]).sum()), "sessions_with_no_trend_reading": closed,
           "gate_high": sum(table[d]["side"]["adx_abs30"] == "HIGH" for d in sessions if d not in closed),
           "gate_low": sum(table[d]["side"]["adx_abs30"] == "LOW" for d in sessions if d not in closed),
           "dataset_breeze_sqlite_sha256": sha(point["dataset"] / "breeze.sqlite"), "daily_sha256": sha(point["daily"]),
           "prices_shown": False}
    (HERE / f"results-sn366-bind-{p}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("sessions", "first_last_session", "sessions_with_options", "rows_by_kind", "bad_rows", "bars_before_first_session",
                                          "gate_high", "gate_low")} | {"no_trend": len(closed), "no_options": len(no_options), "short": len(out["short_sessions"])}), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("step", choices=("mirror", "daily", "export", "warm", "bind"))
    cli.add_argument("point", choices=tuple(WINDOWS))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    {"mirror": lambda: mirror(a.point), "daily": lambda: daily(a.point), "export": lambda: export(a.point),
     "warm": lambda: warm(a.point, a.jobs), "bind": lambda: bind(a.point)}[a.step]()
