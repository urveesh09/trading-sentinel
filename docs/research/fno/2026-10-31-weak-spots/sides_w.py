"""O31e - new descriptions of a day, every one known before the first entry at 09:45. Research only.

From yesterday's and earlier daily bars: the ADX band and whether it is rising, a +DI / -DI cross, a 20-day breakout, a seven-day
narrow range, an inside day, a narrow central pivot range. From today's open: a large gap. From the calendar: scheduled events
and the sessions left to the weekly expiry. From the option prices at 09:44: implied volatility (Brenner-Subrahmanyam: straddle
/ (0.8 x future x sqrt(T))), whether it is cheap against its last 60 sessions, and whether it is below recent realised volatility.

Scheduled events: RBI policy decisions, Union Budgets, the 2024 election count. The 2026 RBI dates are from RBI's calendar (press
release of Mar 23, 2026) and from reports of each meeting; the 2024 and 2025 dates are from memory of the published calendars and
were not checked against a source in this study.
"""
from __future__ import annotations

import math
import sqlite3
import statistics
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

RBI = ("2024-02-08", "2024-04-05", "2024-06-07", "2024-08-08", "2024-10-09", "2024-12-06",
       "2025-02-07", "2025-04-09", "2025-06-06", "2025-08-06", "2025-10-01", "2025-12-05",
       "2026-02-06", "2026-04-08", "2026-06-05", "2026-08-05", "2026-10-07")
BUDGET = ("2024-02-01", "2024-07-23", "2025-02-01", "2026-02-01")
ELECTION = ("2024-06-04",)
EVENTS = frozenset(RBI + BUDGET + ELECTION)
CPR_LOOKBACK = 60
IV_LOOKBACK = 60
IV_MIN_PRIOR = 20


def _dmi(d: pd.DataFrame, n: int = 14) -> tuple:
    up, down = d["high"].diff(), -d["low"].diff()
    plus = ((up > down) & (up > 0)) * up
    minus = ((down > up) & (down > 0)) * down
    tr = pd.concat([d["high"] - d["low"], (d["high"] - d["close"].shift()).abs(), (d["low"] - d["close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, float("nan"))
    return pdi, mdi, dx.ewm(alpha=1 / n, adjust=False).mean(), atr


def band(adx: float) -> str:
    for hi, name in ((15, "LT15"), (20, "15_20"), (25, "20_25"), (30, "25_30"), (35, "30_35")):
        if adx < hi:
            return name
    return "35P"


def daily_sides(daily: pd.DataFrame, days: list) -> dict:
    """day -> sides, from daily bars strictly before the day (and, for the gap, the day's own open)."""
    d = daily[~daily.index.duplicated(keep="last")].sort_index()
    pdi, mdi, adx, atr = _dmi(d)
    rng = d["high"] - d["low"]
    pivot = (d["high"] + d["low"] + d["close"]) / 3
    base = (d["high"] + d["low"]) / 2
    cpr = (2 * (pivot - base)).abs() / pivot
    out = {}
    for s in days:
        day = pd.Timestamp(s)
        prior = d.index[d.index < day]
        if len(prior) < 60:
            continue
        y, p = prior[-1], prior[-2]
        i = d.index.get_loc(y)
        up_now = float(pdi.loc[y]) > float(mdi.loc[y])
        crossed = any((float(pdi.iloc[i - k]) > float(mdi.iloc[i - k])) != up_now for k in range(1, 4))
        high20, low20 = float(d["high"].iloc[i - 20:i].max()), float(d["low"].iloc[i - 20:i].min())
        close = float(d["close"].loc[y])
        hist = cpr.iloc[i - CPR_LOOKBACK:i].dropna()
        row = {"adx_value": round(float(adx.loc[y]), 2), "adx_band": band(float(adx.loc[y])),
               "adx_rising": "HIGH" if float(adx.iloc[i]) > float(adx.iloc[i - 5]) else "LOW",
               "di_cross": ("UP" if up_now else "DOWN") if crossed else "NONE",
               "don20": "UP" if close > high20 else "DOWN" if close < low20 else "NONE",
               "nr7": "HIGH" if float(rng.loc[y]) <= float(rng.iloc[i - 6:i + 1].min()) else "LOW",
               "inside": "HIGH" if float(d["high"].loc[y]) <= float(d["high"].loc[p]) and float(d["low"].loc[y]) >= float(d["low"].loc[p]) else "LOW",
               "cpr_narrow": ("HIGH" if float(cpr.loc[y]) <= float(hist.quantile(0.25)) else "LOW") if len(hist) >= 20 else None,
               "event": "HIGH" if s in EVENTS else "LOW"}
        if day in d.index:
            gap = float(d["open"].loc[day]) - close
            row["gap_big"] = "HIGH" if abs(gap) >= 0.5 * float(atr.loc[y]) else "LOW"
            row["gap_dir"] = "UP" if gap > 0 else "DOWN"
            row["gap_points"] = round(gap, 2)
            row["prev_close"] = round(close, 2)
        out[s] = row
    return out


def dte_sides(sessions: list, expiries: list) -> dict:
    """Sessions left to the weekly expiry, from the data's own calendar (an expiry beyond the data counts as 3+)."""
    order = {d: i for i, d in enumerate(sessions)}
    out = {}
    for s in sessions:
        e = next((x for x in expiries if x >= s), None)
        n = order[e] - order[s] if e in order else 3
        out[s] = {"dte": n, "dte_band": "0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3P"}
    return out


def _iv(straddle: float, future: float, expiry: str, day: str) -> float:
    end = datetime.combine(date.fromisoformat(expiry), time(15, 30))
    years = (end - datetime.combine(date.fromisoformat(day), time(9, 45))).total_seconds() / (365 * 86400)
    return straddle / (0.8 * future * math.sqrt(years))


def iv_readings(db: Path, sessions: list, expiries: list, futures: list) -> dict:
    """day -> the 09:44 implied volatility; expiry sessions have no same-day options, so no reading."""
    out = {}
    con = sqlite3.connect(f"file:{Path(db).resolve().as_posix()}?mode=ro", uri=True)
    for s in sessions:
        e = next((x for x in expiries if x >= s), None)
        front = next((x for x in futures if x >= s), None)
        if e is None or front is None or e == s:
            continue
        row = con.execute("SELECT close FROM candles WHERE kind='future' AND expiry=? AND datetime<=? AND datetime>=? ORDER BY datetime DESC LIMIT 1",
                          (front, f"{s} 09:44:00", f"{s} 09:30:00")).fetchone()
        if not row:
            continue
        future = float(row[0])
        strike = round(future / 50) * 50.0
        legs = []
        for opt in ("CE", "PE"):
            leg = con.execute("SELECT close FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime<=? AND datetime>=? "
                              "ORDER BY datetime DESC LIMIT 1", (e, strike, opt, f"{s} 09:44:00", f"{s} 09:30:00")).fetchone()
            if leg:
                legs.append(float(leg[0]))
        if len(legs) == 2:
            out[s] = round(_iv(sum(legs), future, e, s), 4)
    con.close()
    return out


def iv_sides(iv: dict, daily: pd.DataFrame, sessions: list) -> dict:
    """iv_cheap: below the median of the previous 60 readings (at least 20). rv_over_iv: the last 10 daily closes' realised
    volatility (annualised) above today's implied."""
    d = daily[~daily.index.duplicated(keep="last")].sort_index()
    returns = (d["close"] / d["close"].shift()).apply(lambda v: math.log(v) if v and v > 0 else float("nan"))
    out, seen = {}, []
    for s in sessions:
        value = iv.get(s)
        row = {"iv": value, "iv_cheap": None, "rv_over_iv": None}
        if value is not None:
            prior = returns[returns.index < pd.Timestamp(s)].dropna().iloc[-10:]
            if len(seen) >= IV_MIN_PRIOR:
                row["iv_cheap"] = "HIGH" if value < statistics.median(seen[-IV_LOOKBACK:]) else "LOW"
            if len(prior) == 10:
                rv = float(prior.std() * math.sqrt(252))
                row["rv10"] = round(rv, 4)
                row["rv_over_iv"] = "HIGH" if rv > value else "LOW"
            seen.append(value)
        out[s] = row
    return out
