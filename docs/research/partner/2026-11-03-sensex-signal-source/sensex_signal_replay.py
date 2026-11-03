"""Replay evaluate_fno_mom on SENSEX 5-min bars from (a) the front future and (b) the index plus today's opening
basis (median fut - index over 09:15-09:45, known by the first decision at 09:45), both with NIFTY futures volume
for RVOL (as the shipped book). Compares the first signal of each direction per day. Seen data only (Dec 2025 -
Oct 2026); read-only on the Breeze history."""
import sqlite3
import sys
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import pytz

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
from fno_engine_mom import evaluate_fno_mom  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
DB = r"C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\data\breeze-history.sqlite"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=1)
q = ("select kind, expiry, datetime, open, high, low, close, volume from candles where underlying=? and kind in "
     "('index','future') and datetime >= '2025-12-01'")
raw = {u: pd.read_sql(q, c, params=(u,), parse_dates=["datetime"]) for u in ("SENSEX", "NIFTY")}
c.close()


def front_future(df):
    f = df[df.kind == "future"].copy()
    f["day"] = f.datetime.dt.date
    f["exp"] = pd.to_datetime(f.expiry).dt.date
    f = f[f.exp >= f.day]
    f = f[f.exp == f.groupby("day").exp.transform("min")]
    return f


def bars5(df):
    df = df.set_index("datetime").sort_index()
    b = df.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
    m = b.index.hour * 60 + b.index.minute
    return b[(m >= 555) & (m <= 925)]


sx_fut = bars5(front_future(raw["SENSEX"]))
sx_idx = bars5(raw["SENSEX"][raw["SENSEX"].kind == "index"])
nf_fut = bars5(front_future(raw["NIFTY"]))
days = sorted(set(sx_fut.index.date) & set(sx_idx.index.date) & set(nf_fut.index.date))

# Index bars on the future's level: + today's opening basis (09:15-09:45 median), known at 09:45.
open_basis = {}
j = sx_idx[["close"]].join(sx_fut[["close"]], lsuffix="_i", rsuffix="_f", how="inner")
for d in days:
    o = j[(j.index.date == d) & (j.index.time < time(9, 45))]
    open_basis[d] = float((o.close_f - o.close_i).median()) if len(o) else np.nan
sx_syn = sx_idx.copy()
shift = pd.Series([open_basis.get(t.date(), np.nan) for t in sx_syn.index], index=sx_syn.index)
for col in ("open", "high", "low", "close"):
    sx_syn[col] = sx_syn[col] + shift
sx_syn = sx_syn.dropna(subset=["close"])

results = []
for d in days[15:]:
    start = pd.Timestamp(d) - pd.Timedelta(days=21)
    frames = {"FUT": sx_fut[(sx_fut.index >= start) & (sx_fut.index.date <= d)],
              "INDEX": sx_syn[(sx_syn.index >= start) & (sx_syn.index.date <= d)]}
    rvol = nf_fut[(nf_fut.index >= start) & (nf_fut.index.date <= d)]
    first = {"FUT": {}, "INDEX": {}}
    for minute in range(9 * 60 + 50, 14 * 60 + 50, 5):
        now = IST.localize(datetime.combine(d, time(minute // 60, minute % 60, 8)))
        for src, frame in frames.items():
            sig = evaluate_fno_mom(frame, "REGIME_1_NORMAL", now, rvol_bars=rvol)
            if sig.direction is not None:
                first[src].setdefault(sig.direction.value, (now.strftime("%H:%M"), sig.close))
    results.append((d, first["FUT"], first["INDEX"]))

both = only_fut = only_idx = same_time = 0
lags = []
for d, fut, idx in results:
    for direction in ("LONG", "SHORT"):
        a, b = fut.get(direction), idx.get(direction)
        if a and b:
            both += 1
            same_time += a[0] == b[0]
            lags.append((datetime.strptime(a[0], "%H:%M") - datetime.strptime(b[0], "%H:%M")).seconds // 60
                        if a[0] >= b[0] else -((datetime.strptime(b[0], "%H:%M") - datetime.strptime(a[0], "%H:%M")).seconds // 60))
        elif a:
            only_fut += 1
        elif b:
            only_idx += 1
print("days", len(results))
print("first signals per direction-day: both", both, "(same bar", same_time, ") | only futures", only_fut,
      "| only index", only_idx)
if lags:
    print("futures minus index first-signal time, minutes: median", float(np.median(lags)), "mean",
          round(float(np.mean(lags)), 1))

# Follow-through on the INDEX (what the options track), signed in the signal's direction, in points.
iclose = sx_idx["close"]
def forward(d, hhmm, direction, minutes):
    t0 = pd.Timestamp(datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time())) - pd.Timedelta(minutes=5)
    t1 = t0 + pd.Timedelta(minutes=minutes)
    if t0 not in iclose.index or t1 not in iclose.index:
        return None
    move = float(iclose[t1] - iclose[t0])
    return move if direction == "LONG" else -move
groups = {"both (futures time)": [], "both (index time)": [], "futures only": [], "index only": []}
for d, fut, idx in results:
    for direction in ("LONG", "SHORT"):
        a, b = fut.get(direction), idx.get(direction)
        if a and b:
            groups["both (futures time)"].append((d, a[0], direction)); groups["both (index time)"].append((d, b[0], direction))
        elif a:
            groups["futures only"].append((d, a[0], direction))
        elif b:
            groups["index only"].append((d, b[0], direction))
for name, sigs in groups.items():
    for minutes in (30, 60):
        moves = [m for m in (forward(d, t, di, minutes) for d, t, di in sigs) if m is not None]
        if moves:
            print(f"{name:22s} +{minutes}m: n={len(moves):3d} mean {np.mean(moves):6.1f} pts  median {np.median(moves):6.1f}"
                  f"  share>0 {np.mean([m > 0 for m in moves]):.2f}")
