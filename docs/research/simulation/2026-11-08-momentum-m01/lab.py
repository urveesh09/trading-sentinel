"""M01 momentum lab: shipped entries (exact evaluator), exit families, and an opening-range breakout on stocks in play.

Clock and fills (both windows, declared before any score):
  * decisions on completed 15-minute bars; market entries fill at the next bar's open + 5 bps;
  * a stop-buy (ORB) fills at max(level, bar open) + 5 bps when the bar trades through the level;
  * a resting stop fills at min(stop, bar open) - 5 bps; the stop wins any bar where both could happen,
    including the entry bar of a stop-buy;
  * the deadline exit is the 14:30 bar's open - 5 bps (Production's 15-minute cache ends with the 14:30 bar);
  * costs: momentum_replay._costs on the frozen shadow MIS schedule.
"""
from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE = Path(__file__).resolve().parents[4] / "python-engine"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SLIP = 5.0 / 10000.0
DEADLINE = "14:30"
POOL = 50000.0
INDEX = "NIFTY 50"


def costs(entry, exit_price, qty):
    from momentum_replay import _costs
    from momentum_shadow import momentum_shadow_execution_config
    return _costs(entry, exit_price, qty, momentum_shadow_execution_config())


def vwap(frame):
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    volume = frame["volume"]
    return (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)


def prior_daily(data, ticker, day, rows=30):
    daily = data["daily"].get(ticker)
    if daily is None:
        return None
    prior = daily[daily.index < pd.Timestamp(day)].tail(rows)
    return prior if len(prior) >= 14 else None


def atr14(prior):
    from engine import calc_atr
    return float(calc_atr(prior["high"], prior["low"], prior["close"]).iloc[-1])


# ---------------------------------------------------------------- shipped entries (exact evaluator)

def _shipped_one(args):
    """All bars of one ticker-day the shipped evaluator accepts, with the selective gate's verdict."""
    ticker, day, bars, prior, index_today = args
    from engine import evaluate_momentum_signal, calc_vwap
    from models import Regime
    from momentum_selective import selective_gate
    if prior is None or len(bars) < 4:
        return []
    vw = calc_vwap(bars)
    close, vol = bars["close"].to_numpy(), bars["volume"].to_numpy()
    out = []
    for i in range(4, len(bars) + 1):
        stamp = bars.index[i - 1]
        minutes = (stamp.hour - 9) * 60 + stamp.minute - 15
        if not 45 <= minutes <= 300:                      # MC0 (necessary)
            continue
        if close[i - 1] <= vw.iloc[i - 1]:                # MC2.1 (necessary)
            continue
        crossed = any(close[i - k - 1] <= vw.iloc[i - k - 1] and close[i - k] > vw.iloc[i - k]
                      for k in range(1, 4) if i - k - 1 >= 0)
        if not crossed:                                   # MC2 (necessary)
            continue
        look = min(i - 1, 10)
        avg = vol[i - 1 - look:i - 1].mean() if look else 0
        lunch = "11:30" <= stamp.strftime("%H:%M") <= "13:15"
        if not avg or vol[i - 1] / avg < (1.75 if lunch else 1.5) * 0.999:   # MC3 (necessary)
            continue
        fired, decision = evaluate_momentum_signal(
            ticker, bars.iloc[:i], float(prior["high"].iloc[-1]), POOL, POOL, 4, prior,
            1.75 if lunch else 1.5, "BULL", Regime.REGIME_2_ELEVATED)
        if not fired:
            continue
        passed, reason, _ = (selective_gate(bars.iloc[:i], index_today, float(prior["high"].iloc[-1]))
                             if index_today is not None else (False, "no_index", {}))
        out.append(dict(ticker=ticker, day=day, bar=i - 1, stamp=str(stamp), selective=passed,
                        selective_reason=reason, entry_ref=float(decision["entry_price"]),
                        stop=float(decision["stop_loss"]), target=float(decision["target_1"]),
                        shares=int(decision["shares"]), atr=decision.get("atr_at_entry"),
                        vwap=float(decision["vwap"])))
    return out


def shipped_signals(data, workers=4):
    index_days = {day: frame for (t, day), frame in data["bars"].items() if t == INDEX}
    jobs = [(t, day, frame, prior_daily(data, t, day), index_days.get(day))
            for (t, day), frame in sorted(data["bars"].items()) if t != INDEX]
    with ProcessPoolExecutor(workers) as pool:
        rows = [row for part in pool.map(_shipped_one, jobs, chunksize=64) for row in part]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- one trade on one session's bars

@dataclass(frozen=True)
class Exit:
    name: str
    target_r: float | None = None      # resting target in R (None: no target)
    breakeven_r: float | None = None   # after a close at +x R, the stop moves to entry
    trail_bars: bool = False           # after breakeven, trail under each completed bar's low
    vwap_exit: bool = False            # exit at the next open after a close under VWAP
    live: bool = False                 # the shipped lifecycle (momentum_exits.evaluate_momentum_exit)


def run_trade(bars, start, entry, stop, qty, rule: Exit, target_price=None, atr=None, vwap_entry=None):
    """Bars from index ``start`` (the entry bar, entry already filled at ``entry``). Returns a trade dict."""
    if rule.live:
        return _live_trade(bars, start, entry, stop, qty, target_price, atr, vwap_entry)
    risk = entry - stop
    level = stop
    target = entry + rule.target_r * risk if rule.target_r else None
    armed = False
    vw = vwap(bars) if rule.vwap_exit else None
    pending_exit = False
    for j in range(start, len(bars)):
        stamp = bars.index[j]
        o, h, l, c = (float(bars[k].iloc[j]) for k in ("open", "high", "low", "close"))
        if stamp.strftime("%H:%M") >= DEADLINE:
            return _close(entry, o * (1 - SLIP), qty, risk, "deadline", stamp)
        if pending_exit and j > start:
            return _close(entry, o * (1 - SLIP), qty, risk, "vwap_exit", stamp)
        if o <= level and j > start:
            return _close(entry, o * (1 - SLIP), qty, risk, "stop_gap", stamp)
        if l <= level:
            return _close(entry, min(level, o) * (1 - SLIP), qty, risk, "stop", stamp)
        if target and h >= target:
            return _close(entry, max(target, o if j > start else target) * (1 - SLIP), qty, risk, "target", stamp)
        if rule.breakeven_r is not None and not armed and c >= entry + rule.breakeven_r * risk:
            armed, level = True, max(level, entry)
        if armed and rule.trail_bars:
            level = max(level, l)
        if rule.vwap_exit and c < float(vw.iloc[j]):
            pending_exit = True
    return None                                            # no deadline bar: unresolved


def _live_trade(bars, start, entry, stop, qty, target, atr, vwap_entry):
    """The shipped partial/runner lifecycle through momentum_replay's OHLC diagnostic, deadline at 14:30."""
    from momentum_replay import _simulate_live_exit_lifecycle
    from momentum_shadow import momentum_shadow_execution_config
    execution = {**momentum_shadow_execution_config(), "time_exit_hour": 14, "time_exit_minute": 30,
                 "entry_slippage_bps": 0.0}
    stamp = bars.index[start]
    candidate = {"variant": "LIVE", "ticker": "X", "trading_date": stamp.date().isoformat(),
                 "bar_ts": stamp.isoformat(), "dataset_fingerprint": "", "regime_at_entry": "REGIME_2_ELEVATED",
                 "decision": {"entry_price": entry, "stop_loss": stop, "target_1": target, "shares": qty,
                              "atr_at_entry": atr, "vwap": vwap_entry}}
    trade = _simulate_live_exit_lifecycle(candidate, bars.iloc[start:], execution)
    if trade.get("status") != "CLOSED":
        return None
    return {"net": trade["net_pnl"], "gross": trade["gross_pnl"], "costs": trade["costs"],
            "r": trade["net_pnl"] / ((entry - stop) * qty), "reason": trade.get("exit_reason"),
            "exit_at": trade.get("exit_bar_ts")}


def _close(entry, exit_price, qty, risk, reason, stamp):
    gross = (exit_price - entry) * qty
    cost = costs(entry, exit_price, qty)
    return {"net": gross - cost, "gross": gross, "costs": cost, "r": (gross - cost) / (risk * qty),
            "reason": reason, "exit_at": str(stamp)}


def size(entry, stop, risk_rupees, cap):
    if entry <= stop:
        return 0
    return int(min(risk_rupees / (entry - stop), cap / entry))


# ---------------------------------------------------------------- stocks-in-play opening-range breakout

@dataclass(frozen=True)
class Orb:
    name: str
    top: int = 5                       # stocks in play: highest first-bar volume / 20-day average daily volume
    min_rel: float = 0.0               # and at least this ratio
    stop: str = "or_low"               # "or_low" or "atr:<m>" (m daily ATRs under the entry)
    last_entry: str = "10:15"          # the stop-buy is live from the 09:30 bar to this bar
    market: bool = False               # NIFTY's first bar closed up
    exit: Exit = Exit("deadline")


def orb_universe(data, day, min_price=50.0, min_value=5e7):
    """(ticker, first bar, rel volume) for one session, from facts known at 09:30."""
    rows = []
    for (ticker, d), bars in data["bars"].items():
        if d != day or ticker == INDEX or len(bars) < 3 or bars.index[0].strftime("%H:%M") != "09:15":
            continue
        prior = prior_daily(data, ticker, day, 30)
        if prior is None:
            continue
        adv = float(prior["volume"].tail(20).mean())
        value = float((prior["close"] * prior["volume"]).tail(20).median())
        first = bars.iloc[0]
        if adv <= 0 or value < min_value or float(first["close"]) < min_price:
            continue
        rows.append((ticker, bars, float(first["volume"]) / adv, prior))
    return rows


_UNIVERSE = {}


def day_universe(data, day):
    key = (data["window"], day)
    if key not in _UNIVERSE:
        _UNIVERSE[key] = [(t, b, rel, prior, atr14(prior)) for t, b, rel, prior in orb_universe(data, day)]
    return _UNIVERSE[key]


def orb_day(data, day, arm: Orb, risk_rupees, cap, rng=None):
    """Trades of one session: the top ``arm.top`` stocks in play with a green first bar."""
    universe = day_universe(data, day)
    if arm.market:
        index = data["bars"].get((INDEX, day))
        if index is None or float(index["close"].iloc[0]) <= float(index["open"].iloc[0]):
            return []
    if rng is not None:                                     # NULL: random liquid names, same rules otherwise
        picks = [universe[i] for i in rng.permutation(len(universe))[:arm.top]] if universe else []
    else:
        green = [u for u in universe if float(u[1]["close"].iloc[0]) > float(u[1]["open"].iloc[0])
                 and u[2] >= arm.min_rel]
        picks = sorted(green, key=lambda u: -u[2])[:arm.top]
    trades = []
    for ticker, bars, rel, prior, atr in picks:
        first = bars.iloc[0]
        level = float(first["high"])
        for j in range(1, len(bars)):
            stamp = bars.index[j]
            if stamp.strftime("%H:%M") > arm.last_entry:
                break
            if float(bars["high"].iloc[j]) <= level:
                continue
            entry = max(level, float(bars["open"].iloc[j])) * (1 + SLIP)
            if arm.stop == "or_low":
                stop = float(first["low"])
            else:
                stop = entry - float(arm.stop.split(":")[1]) * atr
            qty = size(entry, stop, risk_rupees, cap)
            if qty < 1:
                break
            result = run_trade(bars, j, entry, stop, qty, arm.exit)
            if result:
                trades.append({"ticker": ticker, "day": day, "entry_at": str(stamp), "entry": entry,
                               "stop": stop, "qty": qty, "rel": rel, **result})
            break
    return trades


def summary(trades):
    if not len(trades):
        return {"trades": 0, "net": 0.0}
    frame = pd.DataFrame(trades)
    by_day = frame.groupby("day")["net"].sum().sort_index()
    equity = by_day.cumsum()
    best_day = by_day.max()
    return {"trades": len(frame), "net": round(frame["net"].sum(), 1), "gross": round(frame["gross"].sum(), 1),
            "costs": round(frame["costs"].sum(), 1), "win": round((frame["net"] > 0).mean(), 3),
            "avg_r": round(frame["r"].mean(), 3), "net_ex_best_day": round(by_day.sum() - max(best_day, 0), 1),
            "worst_day": round(by_day.min(), 1), "max_dd": round((equity.cummax().clip(lower=0) - equity).max(), 1),
            "days": int(by_day.size)}
