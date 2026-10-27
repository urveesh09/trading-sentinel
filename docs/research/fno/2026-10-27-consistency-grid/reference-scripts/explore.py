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
START, END = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2026-09-10", "2026-10-23")


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


# ---- (1) hindsight availability ----------------------------------------------------------
avail = Counter()
per_day_avail = {}
for day in data.days:
    if not (START <= day <= END) or date.fromisoformat(day) in calendar:
        continue
    got = session(day)
    if got is None:
        continue
    obs, bars, today = got
    d = Counter()
    for i, j in closes_with_obs(obs, bars):
        start = bars.index[i]
        minute = (start + timedelta(minutes=5)).hour * 60 + (start + timedelta(minutes=5)).minute
        if not (settings.FNO_ENTRY_START_MIN <= minute < settings.FNO_ENTRY_END_MIN):
            continue
        seen_any = False
        for direction in ("LONG", "SHORT"):
            p = pick(obs[j], today, direction)
            if p is None:
                continue
            q, _delta = p
            qty = q.contract.lot_size
            entry = q.ask
            first, best, worst = None, -1e9, 1e9
            for o in obs[j + 1:]:
                if o.at > obs[j].at + timedelta(minutes=15):
                    break
                cq = o.options.get(q.contract.token)
                if not cq or cq.bid <= 0:
                    continue
                n = net(entry, cq.bid, qty)
                best, worst = max(best, n), min(worst, n)
                if first is None and n >= 200:
                    first = "WIN"
                if first is None and n <= -300:
                    first = "LOSS"
            d["side_moments"] += 1
            d[f"first_{first}"] += 1
            if best >= 200:
                d["side_reached_200"] += 1
                seen_any = True
        d["moments"] += 1
        d["either_side_200"] += seen_any
    per_day_avail[day] = dict(d)
    avail.update(d)
print("== (1) hindsight: at each 5-min close 09:45-14:45, buy the delta-0.55 CE and PE at the ask, next 15 min")
print(dict(avail))
print(f"moments where CE or PE reached +Rs200 net within 15 min: {avail['either_side_200']}/{avail['moments']}")
print(f"a side picked in advance: +200 first {avail['first_WIN']}, -300 first {avail['first_LOSS']}, "
      f"neither {avail['first_None']} of {avail['side_moments']}")
json.dump(per_day_avail, open(sys.argv[3] if len(sys.argv) > 3 else "avail.json", "w"), indent=1)
