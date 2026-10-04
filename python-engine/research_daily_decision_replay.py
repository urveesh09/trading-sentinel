"""Daily decision replays that call the shipped Swing and EDGE code paths.

This is deliberately an evaluator study, not a fill or portfolio simulator.
Daily cache bars are only visible after their session, so each decision for
session D is made from bars strictly before D.  Missing market context is a
data failure, never a reason to substitute the traded ticker as an index.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import math
import os
import sqlite3
import tempfile
from typing import Iterable

import numpy as np
import pandas as pd


class DailyReplayUnavailable(RuntimeError):
    """Required frozen daily evidence is absent or invalid."""


def _frame(rows: Iterable[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").reset_index(drop=True)


def _by_ticker(rows: Iterable[tuple]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for ticker, group in _frame(rows).groupby("ticker", sort=True):
        out[str(ticker).upper()] = group.drop(columns=["ticker"]).set_index("date")
    return out


class SwingDecisionClock:
    """Shipped Swing decisions, one before-open regime update per session.

    Live scheduling can call the regime engine more than once per session. That
    historical scheduler clock is not archived, so the clock freezes a single
    update per session and must be stepped in session order. Each decision for
    session D uses only bars strictly before D.
    """

    def __init__(self, frames: dict[str, pd.DataFrame], *, tickers: tuple[str, ...], nifty_ticker: str,
                 banknifty_ticker: str, bankroll: float):
        from regime import RegimeEngine
        required = {nifty_ticker, banknifty_ticker, *tickers}
        missing = sorted(t for t in required if t not in frames or frames[t].empty)
        if missing:
            raise DailyReplayUnavailable("missing required daily history: " + ", ".join(missing))
        if bankroll <= 0 or not math.isfinite(bankroll):
            raise ValueError("bankroll must be a positive finite number")
        self.frames, self.tickers, self.bankroll = frames, tickers, bankroll
        self.nifty, self.bank = frames[nifty_ticker], frames[banknifty_ticker]
        self.regime_engine = RegimeEngine()
        self.last_day: date | None = None

    def decide(self, day: date, skips: Counter, bankroll: float | None = None) -> list[dict]:
        from engine import calc_atr, calc_ema, calc_rsi_series, evaluate_signal
        if self.last_day is not None and day <= self.last_day:
            raise ValueError("SwingDecisionClock must be stepped in increasing session order")
        self.last_day = day
        cutoff = pd.Timestamp(day)
        # The scan is before the D session. A D daily bar is never included.
        n = self.nifty[self.nifty.index < cutoff]
        b = self.bank[self.bank.index < cutoff]
        if len(n) < 214 or len(b) < 60:
            skips["market_context_warmup"] += len(self.tickers)
            return []
        aligned_b = b.reindex(n.index).dropna()
        if len(aligned_b) < 60:
            skips["banknifty_alignment_missing"] += len(self.tickers)
            return []
        n = n.loc[aligned_b.index]
        atr = calc_atr(n["high"], n["low"], n["close"])
        baseline = atr.rolling(200).mean().iloc[-1]
        if not math.isfinite(float(baseline)) or float(baseline) <= 0:
            skips["market_context_warmup"] += len(self.tickers)
            return []
        close = float(n["close"].iloc[-1])
        ema20 = float(calc_ema(20, n["close"]).iloc[-1])
        ema50 = float(calc_ema(50, n["close"]).iloc[-1])
        returns = np.diff(np.log(n["close"].to_numpy(dtype=float)))
        realized_vol = float(np.std(returns[-20:]) * np.sqrt(252)) if len(returns) >= 20 else 0.18
        ratios = (n["close"] / aligned_b["close"]).tail(60).astype(float).tolist()
        breadth = max(0.30, min(0.70, 0.30 + (close / ema50 - 0.98) * 10.0)) if ema50 > 0 else 0.50
        state = self.regime_engine.update_regime(
            nifty_atr_current=float(atr.iloc[-1]), nifty_atr_baseline=float(baseline),
            realized_vol=realized_vol, nifty_close=close, nifty_ema20=ema20,
            banknifty_close=float(aligned_b["close"].iloc[-1]), nb_ratio_history=ratios,
            breadth=breadth, vix=None, nifty_50=close,
        )
        market_regime = "BEAR_RS_ONLY" if close < ema50 else "CAUTION" if close < ema50 * 1.02 else "BULL"
        nifty_return = float(close / n["close"].iloc[-2] - 1)
        decisions = []
        for ticker in self.tickers:
            stock = self.frames[ticker]
            history = stock[stock.index < cutoff]
            if len(history) < 200:
                skips["stock_warmup"] += 1
                continue
            fired, detail = evaluate_signal(
                ticker, history, self.bankroll if bankroll is None else bankroll,
                self.regime_engine.get_risk_pct(), regime=state.regime,
                market_regime=market_regime, nifty_50_current=close, nifty_ema20=ema20,
                nifty_return_1d=nifty_return, rsi_history=calc_rsi_series(history["close"]),
                # Full point-in-time constituent breadth is not persisted. Do not invent it.
                breadth_rank=None, breadth_pct_above_sma50=None,
            )
            decisions.append({"decision_date": day.isoformat(), "ticker": ticker, "fired": bool(fired),
                              "regime": state.regime.value, "market_regime": market_regime,
                              "detail": detail})
        return decisions


def swing_evaluator_replay(
    rows: list[tuple], *, start: str, end: str, tickers: tuple[str, ...],
    nifty_ticker: str, banknifty_ticker: str, bankroll: float,
) -> dict:
    """Replay `engine.evaluate_signal` through the declared once-per-session clock."""
    frames = _by_ticker(rows)
    clock = SwingDecisionClock(frames, tickers=tickers, nifty_ticker=nifty_ticker,
                               banknifty_ticker=banknifty_ticker, bankroll=bankroll)
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    all_days = sorted({stamp.date() for stamp in clock.nifty.index if start_day <= stamp.date() <= end_day})
    if not all_days:
        raise DailyReplayUnavailable("NIFTY has no requested sessions")
    decisions: list[dict] = []
    skips: Counter[str] = Counter()
    for day in all_days:
        decisions.extend(clock.decide(day, skips))
    if not decisions:
        raise DailyReplayUnavailable("no evaluable sessions after point-in-time warm-up")
    return {"scope": "EVALUATOR", "clock": "one_before_open_regime_update_per_session",
            "decisions": decisions, "fired": sum(row["fired"] for row in decisions),
            "rejected": sum(not row["fired"] for row in decisions), "skips": dict(sorted(skips.items()))}


def edge_evaluator_replay(
    rows: list[tuple], *, start: str, end: str, tickers: tuple[str, ...],
    nifty_ticker: str, bankroll: float, max_positions: int, min_strength: float,
) -> dict:
    """Call the shipped `penny_edge_live.scan_today` over a frozen mini-cache.

    The scanner itself defines the 60-bar window, NIFTY regime proxy, candidate
    features and rank.  We intentionally do not simulate a later fill or exit.
    """
    from penny_edge_live import scan_today

    required = {nifty_ticker, *tickers}
    have = {str(row[0]).upper() for row in rows}
    missing = sorted(required - have)
    if missing:
        raise DailyReplayUnavailable("missing required daily history: " + ", ".join(missing))
    if not tickers:
        raise ValueError("EDGE evaluator requires an explicit universe")
    fd, path = tempfile.mkstemp(prefix="sentinel-edge-evaluator-", suffix=".sqlite")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit(); conn.close()
        days = sorted({str(row[1]) for row in rows if start <= str(row[1]) <= end})
        scans = []
        for day in days:
            scan = scan_today(bankroll=bankroll, max_positions=max_positions,
                              min_strength=min_strength, db_path=path,
                              as_of_date=day, nifty_ticker=nifty_ticker)
            scans.append({"decision_date": day, "eligible_tickers": scan["eligible_tickers"],
                          "n_candidates": scan["n_candidates"], "n_positions": scan["n_positions"],
                          "rejected_below_threshold": scan["rejected_below_threshold"],
                          "no_signal_reasons": scan.get("no_signal_reasons", {}),
                          "regime": {"trend_strength": scan["regime"].trend_strength,
                                     "vol_percentile": scan["regime"].vol_percentile,
                                     "preferred_signal": scan["regime"].preferred_signal},
                          "positions": [{"ticker": p.ticker, "shares": p.shares,
                                         "entry_price": p.entry_price, "stop_loss": p.stop_loss,
                                         "target": p.target, "signal_subtype": p.signal_subtype,
                                         "adjusted_strength": p.adjusted_strength} for p in scan["positions"]]})
        if not scans:
            raise DailyReplayUnavailable("no daily sessions in requested window")
        return {"scope": "EVALUATOR", "clock": "daily_bar_known_after_session",
                "scans": scans, "candidates": sum(row["n_candidates"] for row in scans),
                "selected": sum(row["n_positions"] for row in scans)}
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
