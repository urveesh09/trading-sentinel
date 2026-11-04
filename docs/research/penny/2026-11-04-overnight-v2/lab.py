"""Overnight-v2 research lab (research only; no broker, scheduler or Production import).

1. ``load_panel`` reads daily bars (Kite cache copy or the public Yahoo pull).
2. ``build_days`` scores, once per session, every ticker with the SHIPPED EDGE
   evaluators (penny_edge_engine MR/MO, the NIFTYBEES regime and rank_and_pick
   sizing), plus causal research features known at the decision close.
   Outcomes (next open etc.) are stored apart and are read only by the book.
3. ``run_book`` is a fast own-cash overnight book that mirrors
   edge_portfolio_replay.run_overnight_book(split_cash=True, refuse=runtime
   realism) exactly for the baseline arm (see parity.py), and adds declared
   arms: entry mode, exit mode, slots, sizing, selection and screens.

Every feature uses bars dated on or before the decision session. The only
next-session values are in ``Day.nxt`` and are consumed by the book's exit.
"""
from __future__ import annotations

import math
import pickle
import sqlite3
import statistics as st
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "python-engine"))

import penny_edge_engine as pee  # noqa: E402
from penny_edge_backtest import compute_nifty_regime  # noqa: E402

KITE = ROOT / "docs/research/2026-10-03-current-system/_local/stopped-production/cache.db"
YAHOO = HERE / "_local/yahoo/yahoo.sqlite"
PUBLIC_NIFTY = ROOT / "docs/research/penny/2026-11-04-strategy-search/_local/public/public.sqlite"
BAND = (4.0, 60.0)
RANK_DEPTH = 10
MIN_STRENGTH = 0.45


# --------------------------------------------------------------------------- data
def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def load_panel(source: str, start: str, end: str):
    """-> (bars: ticker -> list[dict] ascending, nifty: list[{date, close}]).

    Kite: tickers in BAND at least once in [start, end], with 120 days of
    warm-up. NIFTYBEES comes from the public Yahoo pull (identical closes on
    the 313 overlapping Kite days) so the shipped 60-bar regime is defined
    from the first session (the runtime has >= 60 bars today).
    """
    path = {"kite": KITE, "yahoo": YAHOO}[source]
    c = _ro(path)
    band = {t for (t,) in c.execute(
        "SELECT DISTINCT ticker FROM ohlcv_cache WHERE date BETWEEN ? AND ? AND close BETWEEN ? AND ?",
        (start, end, *BAND))}
    band.discard("NIFTYBEES")
    marks = ",".join("?" * len(band))
    bars = defaultdict(list)
    for t, d, o, h, l, cl, v in c.execute(
            f"SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache WHERE ticker IN ({marks}) "
            "AND date >= date(?, '-150 days') AND date <= date(?, '+10 days') ORDER BY ticker,date",
            (*sorted(band), start, end)):
        if None in (o, h, l, cl, v):
            continue
        bars[t].append({"ticker": t, "date": d, "open": float(o), "high": float(h), "low": float(l),
                        "close": float(cl), "volume": float(v)})
    n = _ro(PUBLIC_NIFTY)
    nifty = [{"date": d, "close": float(cl)} for d, cl in n.execute(
        "SELECT date, close FROM ohlcv_cache WHERE ticker='NIFTYBEES' AND close IS NOT NULL ORDER BY date")]
    return dict(bars), nifty


# --------------------------------------------------------------------------- features
@dataclass
class Cand:
    ticker: str
    kind: str            # shipped subtype, or "NONE" for a non-signal research row
    stype: str           # MR / MO / NONE
    strength: float      # raw
    adj: float           # regime adjusted
    close: float
    stop: float
    target: float
    f: dict              # causal research features
    shares_plan: int = 0  # filled per equity by the ranker


@dataclass
class Day:
    date: str
    regime: tuple
    cands: list          # shipped candidates (strength >= MIN_STRENGTH after regime), all of them
    bar: dict            # ticker -> today's bar (for refusal checks, capacity)
    prev_close: dict     # ticker -> previous session close
    nxt: dict            # ticker -> next bar for that ticker (date, open, high, low, close, volume)


def _causal_features(tb: list, i: int) -> dict:
    b, p = tb[i], tb[i - 1]
    c, o, h, l, v = b["close"], b["open"], b["high"], b["low"], b["volume"]
    prior = tb[max(0, i - 20):i]
    tv20 = st.median([x["close"] * x["volume"] for x in prior]) if prior else 0.0
    nights, days, ph = [], [], 0
    for j in range(max(1, i - 59), i + 1):
        a, z = tb[j - 1], tb[j]
        nights.append(max(-.05, min(.05, z["open"] / a["close"] - 1)))
        days.append(max(-.05, min(.05, z["close"] / z["open"] - 1)))
        ph += z["open"] == a["close"]
    hi20 = max(x["high"] for x in tb[max(0, i - 19):i + 1])
    atr = st.mean(max(x["high"] - x["low"], abs(x["high"] - y["close"]), abs(x["low"] - y["close"]))
                  for y, x in zip(tb[max(0, i - 14):i], tb[max(1, i - 13):i + 1]))
    return {
        "ret": c / p["close"] - 1, "gap": o / p["close"] - 1, "oc": c / o - 1,
        "clv": (c - l) / (h - l) if h > l else 0.5, "from_high": c / h - 1, "bounce": (c - l) / c,
        "rvol": v / st.median([x["volume"] for x in prior]) if prior and st.median([x["volume"] for x in prior]) > 0 else 0.0,
        "tv": c * v, "tv20": tv20, "price": c, "atrp": atr / c,
        "night_mean": st.mean(nights) * len(nights) / (len(nights) + 20) if nights else 0.0,
        "day_mean": st.mean(days) if days else 0.0, "ph_rate": ph / max(1, len(nights)),
        "near_hi20": c / hi20 - 1, "ret5": c / tb[max(0, i - 5)]["close"] - 1,
        "prev_ret": p["close"] / tb[i - 2]["close"] - 1 if i >= 2 else 0.0,
        "n_hist": i,
    }


def build_days(bars: dict, nifty: list, start: str, end: str) -> list[Day]:
    nifty_idx = {r["date"]: k for k, r in enumerate(nifty)}
    calendar = [r["date"] for r in nifty if start <= r["date"] <= end]
    index = {t: {b["date"]: k for k, b in enumerate(tb)} for t, tb in bars.items()}
    out = []
    for day in calendar:
        k = nifty_idx[day]
        regime = compute_nifty_regime(nifty, k) if k >= 60 else pee.compute_regime(0.0, 0.5)
        cands, bar, prev_close, nxt = [], {}, {}, {}
        for t, tb in bars.items():
            i = index[t].get(day)
            if i is None:
                continue
            bar[t] = tb[i]
            if i >= 1:
                prev_close[t] = tb[i - 1]["close"]
            if i + 1 < len(tb):
                nxt[t] = tb[i + 1]
            # The shipped scan reads the last 60 bars; features need 20.
            window = tb[max(0, i - 59):i + 1]
            sigs, _ = pee.scan_single_ticker_with_reason(window, len(window) - 1)
            if not sigs:
                continue
            f = _causal_features(tb, i)
            best = None
            for s in sigs:
                adj = pee.adjust_strength_for_regime(s, regime)
                if adj >= MIN_STRENGTH and (best is None or adj > best[1]):
                    best = (s, adj)
            if best is None:
                continue
            s, adj = best
            cands.append(Cand(t, s.signal_subtype, s.signal_type, s.strength, adj, tb[i]["close"],
                              s.stop_loss, s.target, f))
        cands.sort(key=lambda x: -x.adj)   # stable: ties keep ticker order like the shipped dict order
        out.append(Day(day, (regime.trend_strength, regime.vol_percentile, regime.preferred_signal),
                       cands, bar, prev_close, nxt))
    return out


def save(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)


def load(path: Path):
    with open(path, "rb") as fh:
        return pickle.load(fh)


# --------------------------------------------------------------------------- costs
_S = None


def cnc_costs(entry: float, exit_price: float, shares: int, dp: Optional[float] = None) -> float:
    """Delivery round trip, same arithmetic as penny_risk.calc_penny_costs(is_intraday=False)
    at the runtime settings (checked in parity.py); ``dp`` lets a stress vary the DP charge."""
    global _S
    if _S is None:
        from config import settings
        _S = settings
    s = _S
    buy, sell = entry * shares, exit_price * shares
    exch = (buy + sell) * s.PENNY_EXCHANGE_PCT
    sebi = (buy + sell) * s.PENNY_SEBI_PCT
    ipft = (buy + sell) * s.PENNY_IPFT_PCT
    stt = (buy + sell) * s.PENNY_STT_CNC
    stamp = buy * s.PENNY_CNC_STAMP_DUTY_PCT
    gst = (exch + sebi + ipft) * s.PENNY_GST_PCT
    dpc = (s.PENNY_CNC_DP_CHARGE if dp is None else dp) if shares > 0 else 0.0
    return round(exch + sebi + ipft + stt + stamp + gst + dpc, 4)


# --------------------------------------------------------------------------- book
@dataclass(frozen=True)
class Arm:
    name: str
    slots: int = 3
    entry_bps: float = 25.0          # over the decision close
    exit_bps: float = 5.0            # under the next open
    sizing: str = "risk"             # "risk" = shipped rank_and_pick plan, "equal" = equity/slots
    kinds_skip: tuple = ("MR_mid",)
    select: Optional[str] = None     # name in SELECTORS (re-rank/screen); None = shipped order
    min_ticket: float = 0.0          # refuse a fill smaller than this (fee economics)
    participation: float = 0.01
    placeholder: str = "open"        # exit when next open == close: "open" | "pess" (low-mid) | "skip"
    dp: Optional[float] = None
    bankroll: float = 25000.0
    depth: int = RANK_DEPTH
    params: tuple = ()               # selector parameters as (key, value) pairs


SELECTORS: dict[str, Callable] = {}


def selector(name):
    def deco(fn):
        SELECTORS[name] = fn
        return fn
    return deco


def _ranked(day: Day, arm: Arm, equity: float) -> list[Cand]:
    """Shipped scan order (regime-adjusted strength, top RANK_DEPTH) then the
    arm's selector, then shipped risk sizing (rank_and_pick arithmetic)."""
    cands = day.cands
    if arm.select:
        cands = SELECTORS[arm.select](day, cands, dict(arm.params))
    top = cands[: arm.depth]
    out = []
    for c in top:
        s_norm = max(0.0, min(1.0, (c.adj - MIN_STRENGTH) / (1.0 - MIN_STRENGTH)))
        risk_pct = min(0.020 * 0.5 + 0.020 * 0.5 * s_norm, 0.025)
        rps = c.close - c.stop
        if rps <= 0:
            continue
        sh = int(equity * risk_pct / rps)
        if sh < 1:
            continue
        out.append(replace(c, shares_plan=sh))
    return out


def _base(t: str) -> str:
    return t.split("-")[0]


def run_book(days: list[Day], arm: Arm, *, start: str, end: str, keep_trades: bool = True) -> dict:
    """Own-cash overnight book. Mirrors run_overnight_book(split_cash=True)."""
    eslip, xslip = arm.entry_bps / 1e4, arm.exit_bps / 1e4
    cash, realized = arm.bankroll, 0.0
    held: dict[str, dict] = {}
    trades, curve, outcomes = [], [], Counter()
    for day in days:
        if day.date < start:
            continue
        # 1. sell at this session's open
        for t in sorted(held):
            pos = held[t]
            b = day.bar.get(t)
            if b is None or b["volume"] <= 0:
                pos["delayed"] = True
                continue
            o = b["open"]
            placeholder = o == pos["entry_close"] and pos["entry_date"] == pos.get("prev_session")
            basis = o
            if placeholder and arm.placeholder == "pess":
                basis = (b["low"] + min(b["open"], b["close"])) / 2
            xp = basis * (1 - xslip)
            cost = cnc_costs(pos["entry"], xp, pos["shares"], arm.dp)
            net = (xp - pos["entry"]) * pos["shares"] - cost
            cash += xp * pos["shares"] - cost
            realized += net
            if keep_trades:
                trades.append({"ticker": t, "entry_date": pos["entry_date"], "exit_date": day.date,
                               "entry": pos["entry"], "exit": xp, "shares": pos["shares"], "net": net,
                               "cost": cost, "kind": pos["kind"], "notional": pos["entry"] * pos["shares"],
                               "placeholder": placeholder, "delayed": pos.get("delayed", False),
                               "close": pos["entry_close"], "open": o, "f": pos["f"]})
            else:
                trades.append({"net": net, "entry_date": pos["entry_date"], "notional": pos["entry"] * pos["shares"]})
            del held[t]
        # 2. entries at the close
        if day.date <= end:
            equity = arm.bankroll + realized
            entered = 0
            for c in _ranked(day, arm, equity):
                if entered >= arm.slots:
                    outcomes["DAILY_ENTRY_CAP"] += 1
                    continue
                if c.ticker in held:
                    outcomes["ALREADY_HELD"] += 1
                    continue
                b = day.bar.get(c.ticker)
                if b is None or b["volume"] <= 0:
                    outcomes["NO_BAR"] += 1
                    continue
                # runtime realism (series + weak kind + day-high-after-rise)
                if c.ticker.endswith(("-SM", "-ST")):
                    outcomes["REALISM_sme_series"] += 1
                    continue
                if _base(c.ticker) in {_base(x) for x in held}:
                    outcomes["REALISM_duplicate_series"] += 1
                    continue
                if c.kind in arm.kinds_skip:
                    outcomes[f"REALISM_weak_kind_{c.kind}"] += 1
                    continue
                pc = day.prev_close.get(c.ticker)
                if pc and pc > 0 and b["close"] >= b["high"] * 0.999 and b["close"] / pc - 1 >= 0.019:
                    outcomes["REALISM_at_day_high_after_rise"] += 1
                    continue
                ep = b["close"] * (1 + eslip)
                if c.stop >= ep:
                    outcomes["STOP_ALREADY_BREACHED"] += 1
                    continue
                capacity = int(arm.participation * b["close"] * b["volume"] // ep)
                eq_share = int(equity / arm.slots // ep)
                planned = eq_share if arm.sizing == "equal" else c.shares_plan
                plan = min(planned, eq_share)
                wanted = min(planned, capacity)
                budget = cash / (arm.slots - entered)
                affordable = int(budget // (ep * 1.002))
                shares = min(wanted, affordable)
                if shares < 1 or shares < 0.25 * plan:
                    outcomes["CASH_REJECTED_DUST" if affordable < wanted else "LIQUIDITY_REJECTED"] += 1
                    continue
                if shares * ep < arm.min_ticket:
                    outcomes["SMALL_TICKET"] += 1
                    continue
                cash -= ep * shares
                entered += 1
                outcomes["FILLED"] += 1
                held[c.ticker] = {"entry": ep, "shares": shares, "entry_date": day.date, "kind": c.kind,
                                  "entry_close": b["close"], "f": c.f}
        # mark
        marked = cash + sum((day.bar[t]["close"] if t in day.bar else p["entry"]) * p["shares"]
                            for t, p in held.items())
        curve.append((day.date, marked))
        for p in held.values():
            p["prev_session"] = day.date
        if day.date > end and not held:
            break
    return {"arm": asdict(arm), "trades": trades, "curve": curve, "outcomes": dict(outcomes),
            "open_at_end": len(held), "summary": summarize(trades, curve, arm.bankroll)}


def summarize(trades: list, curve: list, bankroll: float) -> dict:
    nets = [t["net"] for t in trades]
    peak, dd, ddp = bankroll, 0.0, 0.0
    for _, e in curve:
        peak = max(peak, e)
        dd = max(dd, peak - e)
        ddp = max(ddp, (peak - e) / peak if peak > 0 else 0)
    gains, losses = sum(x for x in nets if x > 0), -sum(x for x in nets if x < 0)
    by_year = defaultdict(float)
    for t in trades:
        by_year[t["entry_date"][:4]] += t["net"]
    pct = [t["net"] / t["notional"] for t in trades if t.get("notional")]
    return {"n": len(nets), "net": round(sum(nets), 2), "ex_best": round(sum(nets) - max([0.0, *nets]), 2),
            "dd": round(dd, 2), "dd_pct_peak": round(100 * ddp, 2),
            "pf": round(gains / losses, 3) if losses else None,
            "win": round(100 * sum(x > 0 for x in nets) / len(nets), 1) if nets else None,
            "mean_pct": round(100 * st.mean(pct), 3) if pct else None,
            "median_pct": round(100 * st.median(pct), 3) if pct else None,
            "final": round(curve[-1][1], 2) if curve else bankroll,
            "by_year": {k: round(v, 2) for k, v in sorted(by_year.items())}}
