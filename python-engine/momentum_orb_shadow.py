"""[M01] Stocks-in-play opening-range breakout: a paper shadow of the Momentum book. Never places orders.

The frozen M01 arm A3_ORB_TOP5_VWAP (docs/research/simulation/2026-11-08-momentum-m01). It passed the sealed
Jan-Jul 2026 exam (+Rs 4,759 net over 357 trades; random names -Rs 9,365) but lost on Aug 11 - Nov 6 (-Rs 2,531),
so it is only "promising": this module collects forward evidence, nothing else.

The rule, on completed 15-minute bars of the Momentum universe:
  * stocks in play at 09:30: first bar (09:15) volume / 20-day average daily volume, highest first; price >= Rs 50,
    20-day median traded value >= Rs 5 crore, a green first bar; the top 5;
  * a stop-buy at the first bar's high, live on the 09:30 to 10:15 bars; fill max(high, bar open) + 5 bps;
  * stop at the first bar's low (it wins any bar that could hit both); risk Rs 600, at most Rs 10,000 a trade;
  * exit at the next bar's open after a close under the session VWAP, or at the 14:30 bar's open; 5 bps slippage;
  * costs: the frozen Momentum shadow MIS schedule (momentum_replay._costs).

It runs once a day after the last scan (15:05), on the bars the scans already cached (intraday_cache, interval
'15minute') and the daily cache: no Kite call. Each decision reads only bars up to its own time. Store:
``<DB_PATH>.momentum-orb-shadow.db``.
"""
from __future__ import annotations

from contextlib import closing
import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

TOP = 5
MIN_PRICE = 50.0
MIN_VALUE = 5e7
LAST_ENTRY = "10:15"
DEADLINE = "14:30"
SLIP = 5.0 / 10000.0
RISK = 600.0
CAP = 10000.0


def enabled() -> bool:
    return bool(getattr(settings, "MOMENTUM_ORB_SHADOW_ENABLED", True))


def store_path(db_path: str) -> str:
    return f"{db_path}.momentum-orb-shadow.db"


def costs(entry: float, exit_price: float, qty: int) -> float:
    from momentum_replay import _costs
    from momentum_shadow import momentum_shadow_execution_config
    return _costs(entry, exit_price, qty, momentum_shadow_execution_config())


def vwap(frame: pd.DataFrame) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    return (typical * frame["volume"]).cumsum() / frame["volume"].cumsum().replace(0, np.nan)


def in_play(bars: dict, prior: dict) -> list:
    """(ticker, bars, relative first-bar volume) for the session's eligible names, in ticker order."""
    rows = []
    for ticker in sorted(bars):
        day_bars, daily = bars[ticker], prior.get(ticker)
        if daily is None or len(daily) < 14 or len(day_bars) < 3 or day_bars.index[0].strftime("%H:%M") != "09:15":
            continue
        adv = float(daily["volume"].tail(20).mean())
        value = float((daily["close"] * daily["volume"]).tail(20).median())
        first = day_bars.iloc[0]
        if adv <= 0 or value < MIN_VALUE or float(first["close"]) < MIN_PRICE:
            continue
        rows.append((ticker, day_bars, float(first["volume"]) / adv))
    return rows


def _close(entry, exit_price, qty, risk, reason, stamp):
    gross = (exit_price - entry) * qty
    cost = costs(entry, exit_price, qty)
    return {"net": gross - cost, "gross": gross, "costs": cost, "r": (gross - cost) / (risk * qty),
            "reason": reason, "exit_at": str(stamp)}


def manage(bars: pd.DataFrame, start: int, entry: float, stop: float, qty: int) -> Optional[dict]:
    """The held trade from bar ``start`` (its entry bar): stop first, VWAP exit next open, 14:30 open deadline."""
    risk, vw, pending = entry - stop, vwap(bars), False
    for j in range(start, len(bars)):
        stamp = bars.index[j]
        o, l, c = (float(bars[k].iloc[j]) for k in ("open", "low", "close"))
        if stamp.strftime("%H:%M") >= DEADLINE:
            return _close(entry, o * (1 - SLIP), qty, risk, "deadline", stamp)
        if pending and j > start:
            return _close(entry, o * (1 - SLIP), qty, risk, "vwap_exit", stamp)
        if o <= stop and j > start:
            return _close(entry, o * (1 - SLIP), qty, risk, "stop_gap", stamp)
        if l <= stop:
            return _close(entry, min(stop, o) * (1 - SLIP), qty, risk, "stop", stamp)
        if c < float(vw.iloc[j]):
            pending = True
    return None                                  # no 14:30 bar yet: unresolved


def session_trades(day: str, bars: dict, prior: dict) -> dict:
    """{"picks": [...], "trades": [...], "unresolved": [...]} for one session."""
    universe = in_play(bars, prior)
    green = [u for u in universe if float(u[1]["close"].iloc[0]) > float(u[1]["open"].iloc[0])]
    picks = sorted(green, key=lambda u: -u[2])[:TOP]
    trades, unresolved = [], []
    for ticker, day_bars, rel in picks:
        first = day_bars.iloc[0]
        level, stop = float(first["high"]), float(first["low"])
        for j in range(1, len(day_bars)):
            stamp = day_bars.index[j]
            if stamp.strftime("%H:%M") > LAST_ENTRY:
                break
            if float(day_bars["high"].iloc[j]) <= level:
                continue
            entry = max(level, float(day_bars["open"].iloc[j])) * (1 + SLIP)
            qty = int(min(RISK / (entry - stop), CAP / entry)) if entry > stop else 0
            if qty < 1:
                break
            result = manage(day_bars, j, entry, stop, qty)
            row = {"day": day, "ticker": ticker, "entry_at": str(stamp), "entry": entry, "stop": stop,
                   "qty": qty, "rel": rel}
            (trades.append({**row, **result}) if result else unresolved.append(row))
            break
    return {"universe": len(universe), "picks": [(t, round(r, 4)) for t, _b, r in picks],
            "trades": trades, "unresolved": unresolved}


def _read_session(db_path: str, day: str) -> tuple[dict, dict]:
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        intra = pd.read_sql_query(
            "SELECT ticker, datetime, open, high, low, close, volume FROM intraday_cache "
            "WHERE interval='15minute' AND substr(datetime,1,10)=? ORDER BY ticker, datetime", conn, params=(day,))
        tickers = sorted(set(intra["ticker"]) - {"NIFTY 50"})
        daily = pd.read_sql_query(
            "SELECT ticker, date, open, high, low, close, volume FROM ohlcv_cache WHERE date < ? AND date >= date(?, '-60 days') "
            f"AND ticker IN ({','.join('?' * len(tickers))}) ORDER BY ticker, date", conn,
            params=(day, day, *tickers)) if tickers else pd.DataFrame()
    bars = {}
    for ticker, group in intra.groupby("ticker"):
        if ticker == "NIFTY 50":
            continue
        frame = group.assign(datetime=pd.to_datetime(group["datetime"])).drop_duplicates("datetime")
        frame = frame.set_index("datetime")[["open", "high", "low", "close", "volume"]].astype(float)
        frame = frame[(frame.index.strftime("%H:%M") >= "09:15") & (frame.index.strftime("%H:%M") <= "15:15")]
        if len(frame):
            bars[ticker] = frame
    prior = {t: g.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float).tail(30)
             for t, g in daily.groupby("ticker")} if len(daily) else {}
    return bars, prior


def _store(db_path: str):
    conn = sqlite3.connect(store_path(db_path), timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS orb_runs (day TEXT PRIMARY KEY, summary TEXT NOT NULL, at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS orb_trades (day TEXT, ticker TEXT, payload TEXT, PRIMARY KEY(day, ticker))")
    return conn


def run_day(db_path: str, day: str, now: Optional[datetime] = None) -> dict:
    """Replay one session's frozen rule on the cached bars and record it once (paper evidence only)."""
    if not enabled():
        return {"status": "disabled"}
    bars, prior = _read_session(db_path, day)
    if not bars:
        return {"status": "no_bars", "day": day}
    result = session_trades(day, bars, prior)
    summary = {"day": day, "universe": result["universe"], "picks": result["picks"],
               "trades": len(result["trades"]), "unresolved": len(result["unresolved"]),
               "net": round(sum(t["net"] for t in result["trades"]), 2), "actual_fill": "UNKNOWN"}
    with closing(_store(db_path)) as conn, conn:
        if conn.execute("SELECT 1 FROM orb_runs WHERE day=?", (day,)).fetchone():
            return {"status": "repeat", "day": day}
        for trade in result["trades"]:
            conn.execute("INSERT INTO orb_trades VALUES (?,?,?)", (day, trade["ticker"], json.dumps(trade, default=str)))
        conn.execute("INSERT INTO orb_runs VALUES (?,?,?)",
                     (day, json.dumps({**summary, "unresolved_rows": result["unresolved"]}, default=str),
                      (now or datetime.now()).isoformat()))
    logger.info("momentum_orb_shadow day=%s trades=%d net=%.2f", day, summary["trades"], summary["net"])
    return {"status": "recorded", **summary}


def comparison(db_path: str) -> dict:
    """Forward paper evidence, read-only; a missing store is not created."""
    out = {"enabled": enabled(), "status": "not_collected", "rule": "M01_A3_ORB_TOP5_VWAP",
           "scope": "PAPER_SHADOW_FROM_CACHED_BARS", "actual_fill": "UNKNOWN"}
    import os
    path = store_path(db_path)
    if not os.path.exists(path):
        return out
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            days = conn.execute("SELECT COUNT(*) FROM orb_runs").fetchone()[0]
            trades = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM orb_trades ORDER BY day, ticker")]
    except sqlite3.Error:
        return {**out, "status": "unavailable"}
    by_day = pd.Series({t["day"]: 0.0 for t in trades}, dtype=float)
    for t in trades:
        by_day[t["day"]] += t["net"]
    net = float(sum(t["net"] for t in trades))
    return {**out, "status": "observed", "sessions": days, "trades": len(trades), "net": round(net, 2),
            "gross": round(float(sum(t["gross"] for t in trades)), 2),
            "costs": round(float(sum(t["costs"] for t in trades)), 2),
            "wins": sum(t["net"] > 0 for t in trades),
            "net_ex_best_day": round(net - max([0.0, *by_day.tolist()]), 2),
            "worst_day": round(float(by_day.min()), 2) if len(by_day) else None,
            "recent": trades[-20:]}


async def run_momentum_orb_shadow(now: Optional[datetime] = None) -> Optional[dict]:
    """15:05 Mon-Fri job: today's session, after the last Momentum scan has cached the 14:30 bar."""
    if not enabled():
        return None
    import asyncio
    from zoneinfo import ZoneInfo
    import main as _main
    now = (now or datetime.now(ZoneInfo("Asia/Kolkata")))
    if not await _main.is_trading_day(now.date(), settings.DB_PATH):
        return None
    try:
        return await asyncio.to_thread(run_day, settings.DB_PATH, now.date().isoformat(), now)
    except Exception as exc:                     # evidence only: never breaks the scheduler
        logger.warning("momentum_orb_shadow_failed err=%s", type(exc).__name__)
        return None


__all__ = ["enabled", "store_path", "in_play", "manage", "session_trades", "run_day", "comparison", "run_momentum_orb_shadow"]
