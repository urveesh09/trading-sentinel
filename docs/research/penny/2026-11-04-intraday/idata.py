"""Minute and daily bars for the Penny intraday study (research only; no broker, Breeze or Production).

Sources
  dev   docs/research/penny/2026-11-04-strategy-search/_local/research.sqlite
        (public Yahoo 1m, Sep 7 - Nov 3 2026, already seen by the strategy search)
        daily bars: .../_local/production-cash.sqlite (read-only export of Production's cache)
  exam  docs/research/kite/2026-10-05-penny-h1/_local/validated-kite.sqlite
        (Kite minute Jan 1 - Jul 31 2026, never scored); opened only by scripts/exam.py

A day is a list of bars (minute-of-day, open, high, low, close, volume), sorted, one per traded
minute. Minutes with no trade are absent (thin stocks), never forward-filled.
"""
from __future__ import annotations

import pickle
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SS = ROOT / "docs/research/penny/2026-11-04-strategy-search/_local"
DEV_MINUTE = SS / "research.sqlite"
DEV_DAILY = SS / "production-cash.sqlite"
EXAM_DB = ROOT / "docs/research/kite/2026-10-05-penny-h1/_local/validated-kite.sqlite"
LOCAL = HERE / "_local"

PRICE_MIN, PRICE_MAX = 1.0, 55.0
MIN_MEDIAN_VALUE = 500_000.0  # Rs 5 lakh 20-day median traded value (PENNY_MIN_20D_TV)


@dataclass
class Day:
    ticker: str
    date: str
    bars: list            # [(minute, o, h, l, c, v)]
    prev_close: float
    median_vol20: float   # median daily volume of the prior 20 sessions
    median_value20: float
    prev: list = field(default_factory=list)   # prior daily bars [(date,o,h,l,c,v)], oldest first, <= 60
    next_open: float | None = None
    next_date: str | None = None
    day_open: float | None = None    # official daily open (auction) from the daily bar
    day_close: float | None = None   # official daily close


def _minute(dt: str) -> int:
    hh, mm = int(dt[11:13]), int(dt[14:16])
    return hh * 60 + mm


def _daily(path: Path) -> dict:
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    out = defaultdict(list)
    for t, d, o, h, l, cl, v in c.execute("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache ORDER BY ticker,date"):
        if None in (o, h, l, cl, v) or min(o, h, l, cl) <= 0:
            continue
        out[t].append((d[:10], float(o), float(h), float(l), float(cl), float(v)))
    c.close()
    return out


def _minutes(path: Path, start: str, end: str) -> dict:
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    out = defaultdict(list)
    for t, dt, o, h, l, cl, v in c.execute(
            "SELECT ticker,datetime,open,high,low,close,volume FROM intraday_cache WHERE interval='minute' "
            "AND substr(datetime,1,10) BETWEEN ? AND ? ORDER BY ticker,datetime", (start, end)):
        if None in (o, h, l, cl, v) or min(o, h, l, cl) <= 0:
            continue
        m = _minute(dt)
        if m < 555 or m > 929:
            continue
        out[(t, dt[:10])].append((m, float(o), float(h), float(l), float(cl), float(v or 0.0)))
    c.close()
    return out


def build(minute_path: Path, daily_path: Path, start: str, end: str, min_bars: int = 30) -> list[Day]:
    daily = _daily(daily_path)
    mins = _minutes(minute_path, start, end)
    index = {t: {r[0]: i for i, r in enumerate(rows)} for t, rows in daily.items()}
    days = []
    for (t, d), bars in sorted(mins.items(), key=lambda x: (x[0][1], x[0][0])):
        rows = daily.get(t)
        if not rows or d not in index[t]:
            continue
        i = index[t][d]
        if i < 20 or len(bars) < min_bars:
            continue
        prior = rows[max(0, i - 60):i]
        vols = sorted(r[5] for r in prior[-20:])
        vals = sorted(r[5] * r[4] for r in prior[-20:])
        med = lambda xs: (xs[len(xs) // 2] + xs[(len(xs) - 1) // 2]) / 2
        prev_close = prior[-1][4]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        bars.sort()
        days.append(Day(t, d, bars, prev_close, med(vols), med(vals), prior,
                        nxt[1] if nxt else None, nxt[0] if nxt else None, rows[i][1], rows[i][4]))
    return days


def in_band(day: Day) -> bool:
    return PRICE_MIN <= day.prev_close <= PRICE_MAX and day.median_value20 >= MIN_MEDIAN_VALUE


def dev_days(cache: bool = True) -> list[Day]:
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / "dev-days.pkl"
    if cache and p.exists():
        return pickle.loads(p.read_bytes())
    days = build(DEV_MINUTE, DEV_DAILY, "2026-09-07", "2026-11-03")
    p.write_bytes(pickle.dumps(days))
    return days


def price_at(bars: list, minute: int) -> float | None:
    """Close of the last traded bar at or before `minute` (causal), None before the first trade."""
    last = None
    for b in bars:
        if b[0] > minute:
            break
        last = b[4]
    return last
