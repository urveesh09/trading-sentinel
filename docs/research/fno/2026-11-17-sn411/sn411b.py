"""SN411 B: the live decision chain (PLAN.md section 1, frozen at e5cc95b7; details fixed here before any number).
Production's sealed export (read only, hash-checked): fno_positions (FNO_PAPER entries) and fno_signals (scans).

  bar length   the most common gap between consecutive distinct bar_ts of the engine's scans on a day (expected 300 s)
  per entry    bar_end = bar_ts + bar length; scan = the latest fno_signals row for the same underlying and bar_ts
               evaluated at or before the entry (evaluated_at is UTC); latency = entry_time - bar_end; scan_lag =
               evaluated_at - bar_end; scan_to_entry = entry_time - evaluated_at; the entry's second within its minute
  replay       N11's 2026 replay trades (the panel evals Gold reads): entry_time - bar_end for the same strategies, so
               live and replay clocks can be compared (SN409: one minute of latency costs Gold ~7.7%)
Reported per strategy family and overall: medians, p90, share of entries > 60 s after the bar end.
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results-sn411b.json"
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
              r"\_local\exports\20261116T103002Z")
N11L = HERE.parents[1] / "simulation" / "2026-11-02-fno-n11" / "_local"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ts(s):
    s = s.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=IST)


def q(xs):
    xs = np.array([x for x in xs if x is not None], float)
    if not len(xs):
        return {"n": 0}
    return {"n": int(len(xs)), "median": round(float(np.median(xs)), 1), "p10": round(float(np.percentile(xs, 10)), 1),
            "p90": round(float(np.percentile(xs, 90)), 1), "share_over_60s": round(float((xs > 60).mean()), 3)}


def main():
    if OUT.exists():
        raise SystemExit("SN411 B is run once")
    man = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
    dbp = EXPORT / "fno-replay.sqlite"
    want = (man.get("files_sha256") or {}).get("fno-replay.sqlite")
    if want:
        h = hashlib.sha256(dbp.read_bytes()).hexdigest()
        assert h == want, "fno-replay.sqlite hash mismatch"
    con = sqlite3.connect(f"file:{dbp.as_posix()}?mode=ro", uri=True)
    scans = collections.defaultdict(list)
    for sid, ev, bar, und in con.execute("SELECT scan_id, evaluated_at, bar_ts, underlying FROM fno_signals"):
        scans[(und, bar)].append(ts(ev))
    gaps = collections.Counter()
    by_day = collections.defaultdict(set)
    for (und, bar) in scans:
        by_day[(und, bar[:10])].add(bar)
    for bars in by_day.values():
        b = sorted(dt.datetime.fromisoformat(x) for x in bars)
        for a, c in zip(b, b[1:]):
            gaps[int((c - a).total_seconds())] += 1
    bar_len = gaps.most_common(1)[0][0] if gaps else 300
    rows = []
    for strat, und, bar, et, src in con.execute("SELECT strategy, underlying, bar_ts, entry_time, source FROM fno_positions WHERE source='FNO_PAPER'"):
        if not bar or not et:
            continue
        b_end = dt.datetime.fromisoformat(bar).replace(tzinfo=IST) + dt.timedelta(seconds=bar_len)
        e = ts(et)
        sc = [x for x in scans.get((und, bar), []) if x <= e]
        s = max(sc) if sc else None
        rows.append({"strategy": strat or "?", "underlying": und, "day": bar[:10], "latency_s": (e - b_end).total_seconds(),
                     "scan_lag_s": None if s is None else (s - b_end).total_seconds(), "scan_to_entry_s": None if s is None else (e - s).total_seconds(),
                     "entry_second": e.astimezone(IST).second + e.microsecond / 1e6})
    fam = lambda s: "N11" if s.startswith("N11") else s.split("_")[0]  # noqa: E731
    res = {"bar_length_s": bar_len, "bar_gap_counts": dict(gaps.most_common(5)), "entries": len(rows),
           "by_family": {}, "overall": {k: q([r[k] for r in rows]) for k in ("latency_s", "scan_lag_s", "scan_to_entry_s", "entry_second")}}
    for f in sorted({fam(r["strategy"]) for r in rows}):
        rs = [r for r in rows if fam(r["strategy"]) == f]
        res["by_family"][f] = {"entries": len(rs), "days": [min(r["day"] for r in rs), max(r["day"] for r in rs)],
                               **{k: q([r[k] for r in rs]) for k in ("latency_s", "scan_lag_s", "scan_to_entry_s", "entry_second")}}
    rep = []
    key = json.loads((N11L / "keys-panel-2026.json").read_text(encoding="utf-8"))["N11"]
    data = json.loads((N11L / "evals" / f"{key}.json").read_text(encoding="utf-8"))
    for t in data["trades"]:
        bar = t.get("signal_bar") or t.get("bar_ts")
        if not bar:
            continue
        b_end = dt.datetime.fromisoformat(bar).replace(tzinfo=IST) + dt.timedelta(seconds=bar_len)
        e = ts(t["entry_time"])
        rep.append({"latency_s": (e - b_end).total_seconds(), "entry_second": e.second})
    res["replay_N11_2026"] = {k: q([r[k] for r in rep]) for k in ("latency_s", "entry_second")}
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=str))


if __name__ == "__main__":
    main()
