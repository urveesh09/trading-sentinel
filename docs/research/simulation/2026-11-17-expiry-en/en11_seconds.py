"""EN11's 1-second measurement (PLAN3.md), descriptive only. NIFTY 1-second trade candles, Jan 16 - Apr 2 2026
(docs/research/fno/2026-11-16-sn316/_local/seconds-2026q1.sqlite, read-only): on each expiry day the file holds the
expiring weekly's open-ATM call and put. Prices are last trades (a bid would sit about a tick lower).

Every 5 minutes from 13:00:00 to 14:55:00, a contract trading within Rs 5-20 gets a synthetic entry at that second's
last trade p0 with a stop at 0.65 x p0. At the first trade at or below the stop (before 15:14:00) we record the last
trade 1, 3, 10 and 60 seconds later; and what the minute-bar cadence would have got: the first completed minute whose
close is at or below the stop, sold at the next minute's first trade (if no minute closes there before the 8-minute
clock, the minute cadence holds and sells at the clock instead). The hold-to-clock price is reported alongside."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
DB = HERE.parents[1] / "fno/2026-11-16-sn316/_local/seconds-2026q1.sqlite"
S0, S1 = 9 * 3600 + 15 * 60, 15 * 3600 + 30 * 60


def sec(stamp):
    return int(stamp[11:13]) * 3600 + int(stamp[14:16]) * 60 + int(stamp[17:19]) - S0


def contracts():
    c = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    keys = c.execute("SELECT DISTINCT expiry, strike, opt FROM candles WHERE kind='option' AND substr(datetime,1,10)=expiry ORDER BY 1,3").fetchall()
    out = []
    for e, k, o in keys:
        raw = np.full(S1 - S0 + 1, np.nan)
        for stamp, cl in c.execute("SELECT datetime, close FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND substr(datetime,1,10)=?",
                                   (e, k, o, e)):
            s = sec(stamp)
            if 0 <= s < len(raw) and cl is not None and cl > 0:
                raw[s] = cl
        ff = raw.copy()
        for s in range(1, len(ff)):
            if np.isnan(ff[s]):
                ff[s] = ff[s - 1]
        out.append((e, k, o, raw, ff))
    c.close()
    return out


def first_trade_at_or_after(raw, s):
    for x in range(s, len(raw)):
        if not np.isnan(raw[x]):
            return float(raw[x])
    return float("nan")


def measure():
    rows = []
    for e, k, o, raw, ff in contracts():
        for n in range(24):
            s0 = (13 * 3600 - S0) + n * 300
            p0 = ff[s0]
            if not 5 <= p0 <= 20:
                continue
            stop = .65 * p0; end = 15 * 3600 + 14 * 60 - S0; clock = s0 + 480
            hit = next((s for s in range(s0 + 1, end) if not np.isnan(raw[s]) and raw[s] <= stop), None)
            row = dict(day=e, strike=k, opt=o, s0=s0, p0=float(p0), stopped=hit is not None, clock=float(ff[min(clock, end)]) / p0)
            if hit is not None:
                row.update({f"d{d}": float(ff[min(hit + d, len(ff) - 1)]) / p0 for d in (1, 3, 10, 60)})
                row["recovered60"] = bool(ff[min(hit + 60, len(ff) - 1)] > stop)
                m = hit // 60; mfill = None
                while (m + 1) * 60 <= min(clock, end):
                    if ff[m * 60 + 59] <= stop:
                        mfill = first_trade_at_or_after(raw, (m + 1) * 60) / p0; break
                    m += 1
                row["minute"] = mfill if mfill is not None else float(ff[min(clock, end)]) / p0
                row["minute_triggered"] = mfill is not None
                row["before_clock"] = hit < clock
            rows.append(row)
    return rows


def score():
    rows = measure(); st = [r for r in rows if r["stopped"] and r["before_clock"]]
    agg = lambda k, rs: dict(median=round(float(np.median([r[k] for r in rs])), 4), mean=round(float(np.mean([r[k] for r in rs])), 4)) if rs else None
    out = dict(entries=len(rows), stopped_before_clock=len(st), contract_days=len({(r["day"], r["opt"]) for r in rows}),
               after={f"{d}s": agg(f"d{d}", st) for d in (1, 3, 10, 60)}, minute_cadence=agg("minute", st),
               minute_never_triggered=sum(not r["minute_triggered"] for r in st), recovered_within_60s=sum(r["recovered60"] for r in st),
               hold_to_clock_on_stopped=agg("clock", st),
               fast1_minus_minute=round(float(np.mean([r["d1"] - r["minute"] for r in st])), 4) if st else None,
               fast10_minus_minute=round(float(np.mean([r["d10"] - r["minute"] for r in st])), 4) if st else None)
    return out


def check():
    cs = contracts()
    assert len(cs) == 22, len(cs)
    print("CHECK_OK seconds:", len(cs), "expiry-day contracts (11 expiries x CE/PE), 1-second trades loaded")


if __name__ == "__main__":
    check()
