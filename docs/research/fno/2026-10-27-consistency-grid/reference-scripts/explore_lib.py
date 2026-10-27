"""Exploration on SEEN sessions (Sep 10 - Oct 23): (1) how often a small net profit "appears" on the chart,
(2) a few quick-trade designs at real bid/ask and charges. Development only; nothing here is a result."""
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, time

import pandas as pd

sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
from config import settings  # noqa: E402
from fno_chain import ChainSnapshot, _parity_forward, select_strike_by_delta, years_to_expiry  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402
from fno_models import OptionType  # noqa: E402
from fno_policy_replay import IST, ReplayData  # noqa: E402

ROOT = r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-24-entry-arms\_local"
data = ReplayData(ROOT)
calendar, _ = data.option_expiries()


def snapshot(obs, today):
    expiry = next((e for e in calendar if e >= today), None)
    quotes = {(q.contract.strike, q.contract.instrument_type): q for q in obs.options.values()
              if q.contract.expiry == expiry}
    if not quotes:
        return None
    fwd = obs.future.ltp
    strikes = sorted({k for k, _ in quotes})
    atm = min(strikes, key=lambda k: abs(k - fwd))
    return ChainSnapshot(taken_at=obs.at, expiry=expiry, forward=fwd,
                         parity_forward=_parity_forward(quotes, atm, years_to_expiry(expiry, obs.at)),
                         lot_size=obs.future.contract.lot_size, fut_quote=obs.future, quotes=quotes)


def pick(obs, today, direction):
    snap = snapshot(obs, today)
    if snap is None:
        return None
    got = select_strike_by_delta(snap, OptionType.CE if direction == "LONG" else OptionType.PE, obs.at)
    if got is None:
        return None
    q = got[0]
    if q.ask <= 0 or q.bid <= 0 or (q.spread_pct or 1) > settings.FNO_MAX_SPREAD_PCT:
        return None
    return q, got[2]


def net(entry, bid, qty):
    return (bid - entry) * qty - calc_fno_costs(entry, bid, qty)


def session(day):
    obs, _ = data.observations(day)
    if not obs:
        return None
    today = date.fromisoformat(day)
    frame = data.futures_frame(obs[0].future.contract.token, today)
    tr = pd.concat([frame["high"] - frame["low"], (frame["high"] - frame["close"].shift()).abs(),
                    (frame["low"] - frame["close"].shift()).abs()], axis=1).max(axis=1)
    frame = frame.assign(atr=tr.rolling(14).mean())
    bars = frame[frame.index.date == today]
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    bars = bars.assign(vwap=(tp * bars["volume"]).cumsum() / bars["volume"].cumsum())
    return obs, bars, today


def closes_with_obs(obs, bars):
    """(bar index i, first observation index at/after the bar's close)."""
    out, j = [], 0
    for i, start in enumerate(bars.index):
        close_at = IST.localize(start.to_pydatetime() + timedelta(minutes=5))
        while j < len(obs) and obs[j].at < close_at:
            j += 1
        if j < len(obs):
            out.append((i, j))
    return out



_SESSIONS = {}


def cached(day):
    if day not in _SESSIONS:
        _SESSIONS[day] = session(day)
    return _SESSIONS[day]
