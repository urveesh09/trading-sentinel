"""Opening-auction reversal (OAR) day-trade simulator on daily bars (research only).

Buy a penny stock in the pre-open auction when it opens below the previous close, sell the same
day (official close in the post-close session, or near 15:15 at a modelled bid). Fixed bankroll:
profits are withheld, losses reduce the next day's capital (same accounting as overnight v3).
Same-day round trips use intraday charges (calc_penny_costs(is_intraday=True)).

Panels (daily Yahoo, split cuts as overnight v2; Jan 1 - Jul 31 2026 is reserved for the sealed
exam and is never built here):
  1014 2011-2014, 1518 2015-2018, 1922 2019-2022, 2325 2023-2025, 26b Aug 1 - Nov 3 2026
No broker, Breeze, scheduler or Production access.
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import random
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "python-engine"))
from penny_risk import calc_penny_costs  # noqa: E402

V2 = ROOT / "docs/research/penny/2026-11-04-overnight-v2/_local"
OLD = ROOT / "docs/research/penny/2026-11-04-overnight-enrichment/_local/older/yahoo.sqlite"
LOCAL = HERE / "_local"
RESERVED = ("2026-01-01", "2026-07-31")
PANELS = {"1014": ("2011-01-01", "2014-12-31"), "1518": ("2015-01-01", "2018-12-31"),
          "1922": ("2019-01-01", "2022-12-31"), "2325": ("2023-01-01", "2025-12-31"),
          "26b": ("2026-08-01", "2026-11-03")}
MIN_GAP_STORED = -0.01


def _sha(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def load_bars(paths=None, cuts_path=None, reserved=RESERVED) -> dict:
    cuts = json.loads((cuts_path or V2 / "yahoo-split-cuts.json").read_text())
    bars = defaultdict(dict)
    for path in paths or (OLD, V2 / "yahoo/yahoo.sqlite"):
        c = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
        for t, d, o, h, l, cl, v in c.execute("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache"):
            if None in (o, h, l, cl, v) or min(o, h, l, cl) <= 0 or v <= 0:
                continue
            d = d[:10]
            if d < cuts.get(t, "") or (reserved and reserved[0] <= d <= reserved[1]):
                continue
            if l > min(o, cl) * (1 + 1e-7) or h < max(o, cl) * (1 - 1e-7):
                continue
            bars[t][d] = (float(o), float(h), float(l), float(cl), float(v))
        c.close()
    return {t: sorted(x.items()) for t, x in bars.items() if t not in ("NIFTYBEES", "NIFTY 50")}


def _rsi2(closes):
    if len(closes) < 3:
        return 50.0
    ch = [closes[-2] - closes[-3], closes[-1] - closes[-2]]
    g = sum(max(x, 0) for x in ch) / 2
    l = sum(max(-x, 0) for x in ch) / 2
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


@dataclass
class Cand:
    ticker: str
    date: str
    prev_close: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    gap: float
    med_value20: float
    med_vol20: float
    above50: bool
    above200: bool
    rsi2: float
    yday_ret: float
    yday_clv: float
    ret5: float
    hist_rev: float     # shrunk mean of this stock's past open->close on its gap<=-2% days (before today)
    hist_n: int
    next_open: float | None
    next_low: float | None = None
    next_close: float | None = None
    at_band: bool = False   # auction price on a circuit-band level (-2/-5/-10/-20% of the previous close)


BANDS = (0.02, 0.05, 0.10, 0.20)


def at_band(o, pc):
    return any(abs(o - pc * (1 - b)) <= 0.0101 + 1e-9 for b in BANDS)


def build_rows(bars: dict, start: str, end: str, min_gap=MIN_GAP_STORED) -> dict:
    """date -> [Cand] for band names opening at least |min_gap| below the previous close."""
    out = defaultdict(list)
    for t, seq in bars.items():
        closes = [x[1][3] for x in seq]
        rev_hist = []   # past gap-down open->close returns (dates strictly before)
        for i in range(1, len(seq)):
            d, (o, h, l, c, v) = seq[i]
            pc = closes[i - 1]
            gap = o / pc - 1
            if i >= 21 and start <= d <= end and gap <= min_gap and 1 <= pc <= 55:
                window = seq[i - 20:i]
                vals = sorted(x[1][3] * x[1][4] for x in window)
                vols = sorted(x[1][4] for x in window)
                medv = (vals[9] + vals[10]) / 2
                if medv >= 500_000:
                    pc2 = closes[i - 2]
                    po, ph, pl, _, _ = seq[i - 1][1]
                    sma = lambda n: (sum(closes[i - n:i]) / n) if i >= n else None
                    s50, s200 = sma(50), sma(200)
                    k = len(rev_hist[-40:])
                    hist = sum(rev_hist[-40:]) / (k + 20) if k else 0.0
                    nb = seq[i + 1][1] if i + 1 < len(seq) else None
                    out[d].append(Cand(t, d, pc, o, h, l, c, v, gap, medv, (vols[9] + vols[10]) / 2,
                                       bool(s50 and pc > s50), bool(s200 and pc > s200), _rsi2(closes[:i]),
                                       pc / pc2 - 1, (pc - pl) / (ph - pl) if ph > pl else 0.5,
                                       pc / closes[i - 6] - 1 if i >= 6 else 0.0, hist, k,
                                       nb[0] if nb else None, nb[2] if nb else None, nb[3] if nb else None,
                                       at_band(o, pc)))
            if gap <= -0.02 and 1 <= pc <= 55:
                rev_hist.append(c / o - 1)
    return dict(out)


def panels(cache=True) -> dict:
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / "oar-panels.pkl"
    if cache and p.exists():
        return pickle.loads(p.read_bytes())
    bars = load_bars()
    out = {}
    for name, (s, e) in PANELS.items():
        out[name] = build_rows(bars, s, e)
    cal = sorted({d for seq in bars.values() for d, _ in seq})
    p.write_bytes(pickle.dumps({"rows": out, "calendar": cal}))
    return {"rows": out, "calendar": cal}


@dataclass(frozen=True)
class Policy:
    name: str
    slots: int = 2
    gap_max: float = -0.02          # take gaps at or below this
    gap_min: float = -1.0           # and above this (e.g. -0.10 excludes crashes)
    rank: str = "gap"               # gap | value | hist | random | gap_value
    min_value: float = 500_000.0    # 20-day median traded value floor
    trend: str = ""                 # "" | "above50" | "above200"
    rsi2_max: float | None = None
    hist_min: float | None = None
    yday: str = ""                  # "" | "not_down3" | "down3"
    exit: str = "close"             # close | next_open
    eq_only: bool = False
    skip_band: bool = False         # skip auction prices on a circuit-band level (lower circuit)
    cap_filter: float = 0.0         # skip names whose cap_filter x 20-day median volume < a quarter of the ticket
    hist_ok: bool = False           # skip names whose own shrunk gap-down history is < 0 after 3+ such days
    extra: tuple = ()


@dataclass(frozen=True)
class Fill:
    name: str
    entry_bps: float = 0.0          # paid over the auction price
    exit_bps: float = 0.0           # received under the official close
    win_fill: float = 1.0           # share of winning tickets that fill
    correlated: bool = False
    kappa: float | None = None      # max shares = kappa x 20-day median volume


MODELS = {
    "M1": Fill("M1"),
    "M2": Fill("M2", win_fill=0.75),
    "M3": Fill("M3", win_fill=0.5),
    "M4": Fill("M4", win_fill=0.5, correlated=True),
    "M5": Fill("M5", kappa=0.001),
    "M6": Fill("M6", kappa=0.001, win_fill=0.5),
    "M7": Fill("M7", entry_bps=50, exit_bps=50),
    "M8": Fill("M8", entry_bps=100, exit_bps=50),
}
SEEDS = list(range(20261104, 20261114))


def eligible(c: Cand, p: Policy) -> bool:
    if not (p.gap_min < c.gap <= p.gap_max) or c.med_value20 < p.min_value:
        return False
    if p.eq_only and "-" in c.ticker:
        return False
    if p.trend == "above50" and not c.above50:
        return False
    if p.trend == "above200" and not c.above200:
        return False
    if p.rsi2_max is not None and c.rsi2 > p.rsi2_max:
        return False
    if p.hist_min is not None and (c.hist_n < 3 or c.hist_rev < p.hist_min):
        return False
    if p.yday == "not_down3" and c.yday_ret < -0.03:
        return False
    if p.yday == "down3" and c.yday_ret >= -0.03:
        return False
    if p.exit == "next_open" and not c.next_open:
        return False
    if p.skip_band and c.at_band:
        return False
    if p.hist_ok and c.hist_n >= 3 and c.hist_rev < 0:
        return False
    return True


def ranked(cands, p: Policy, date: str):
    xs = [c for c in cands if eligible(c, p)]
    key = {
        "gap": lambda c: (c.gap, c.ticker),
        "value": lambda c: (-c.med_value20, c.ticker),
        "hist": lambda c: (-c.hist_rev, c.gap, c.ticker),
        "random": lambda c: (_sha("rank", p.extra, date, c.ticker), c.ticker),
        "gap_value": lambda c: (c.gap * math.log10(max(c.med_value20, 1e5)), c.ticker),
    }[p.rank]
    xs.sort(key=key)
    seen, out = set(), []
    for c in xs:
        base = c.ticker.split("-")[0]
        if base in seen:
            continue
        seen.add(base)
        out.append(c)
    return out


def simulate(panel: dict, p: Policy, fm: Fill, *, start, end, bankroll=25000.0, seed=SEEDS[0], keep=False):
    realized = 0.0
    trades, curve = [], []
    out = Counter()
    for d in sorted(panel):
        if not (start <= d <= end):
            continue
        cap = min(bankroll, bankroll + realized)
        night_u = _sha(seed, "day", d)
        entered = 0
        day_net = 0.0
        for c in ranked(panel[d], p, d):
            if entered >= p.slots:
                break
            budget = cap / p.slots
            if p.cap_filter and p.cap_filter * c.med_vol20 < 0.25 * (budget // c.open):
                out["CAP_FILTERED"] += 1
                continue      # causal: the 20-day median volume is known before the auction
            entry = c.open * (1 + fm.entry_bps / 1e4)
            intraday = p.exit == "close"
            locked = False
            if p.exit == "close":
                exit_ref = c.close
                if c.close <= c.low * (1 + 1e-4) and c.close < c.open * (1 - 1e-4):
                    # Closed on its low below the open: a lower-circuit lock has no buyers, so the
                    # sale carries to the next session (delivery charges): its open, or its close if
                    # it opens and stays locked; no next bar -> 5% under the close.
                    locked, intraday = True, False
                    if c.next_open is None:
                        exit_ref = c.close * 0.95
                    elif c.next_open <= c.next_low * (1 + 1e-4) and c.next_close <= c.next_low * (1 + 1e-4):
                        exit_ref = c.next_close
                    else:
                        exit_ref = c.next_open
            else:
                exit_ref = c.next_open
            exit_px = exit_ref * (1 - fm.exit_bps / 1e4)
            qty = int(budget // entry)
            if fm.kappa is not None:
                qty = min(qty, int(fm.kappa * c.med_vol20))
            plan = int(budget // entry)
            if qty < 1 or qty < 0.25 * plan:
                out["CAPACITY_OR_DUST"] += 1
                entered += 1     # the slot was used by an order that could not fill
                continue
            fees = float(calc_penny_costs(entry, exit_px, qty, is_intraday=intraday))
            if locked:
                out["LOCKED_EXIT"] += 1
            net = (exit_px - entry) * qty - fees
            if net > 0 and fm.win_fill < 1:
                u = night_u if fm.correlated else _sha(seed, d, c.ticker)
                if u >= fm.win_fill:
                    out["DENIED_WINNER"] += 1
                    entered += 1
                    continue
            entered += 1
            out["FILLED"] += 1
            day_net += net
            tr = {"date": d, "ticker": c.ticker, "net": net}
            if keep:
                tr.update({"gap": c.gap, "locked": locked, "at_band": c.at_band, "entry": entry, "exit": exit_px, "qty": qty, "fees": fees,
                           "value": qty * entry, "med_value20": c.med_value20, "ret": exit_px / entry - 1})
            trades.append(tr)
        realized += day_net
        curve.append((d, bankroll + realized))
    return {"policy": asdict(p), "fill": asdict(fm), "summary": summarize(trades, curve, bankroll),
            "outcomes": dict(out), "trades": trades if keep else None}


def summarize(trades, curve, bankroll):
    nets = [t["net"] for t in trades]
    peak, dd = bankroll, 0.0
    for _, eq in curve:
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    gains = sum(x for x in nets if x > 0)
    losses = -sum(x for x in nets if x < 0)
    return {"n": len(nets), "net": round(sum(nets), 2), "ex_best": round(sum(nets) - max([0.0, *nets]), 2),
            "dd": round(dd, 2), "pf": round(gains / losses, 3) if losses else None,
            "win": round(sum(x > 0 for x in nets) / len(nets), 3) if nets else None,
            "mean": round(statistics.fmean(nets), 3) if nets else None,
            "days": len({t["date"] for t in trades})}


def by_year(trades):
    out = defaultdict(float)
    for t in trades:
        out[t["date"][:4]] += t["net"]
    return {k: round(v, 2) for k, v in sorted(out.items())}


def score(panel_rows, p: Policy, start, end, bankroll=25000.0, models=None):
    row = {}
    for m, fm in (models or MODELS).items():
        seeds = SEEDS if fm.win_fill < 1 else [SEEDS[0]]
        runs = [simulate(panel_rows, p, fm, start=start, end=end, bankroll=bankroll, seed=s, keep=(m == "M1")) for s in seeds]
        nets = [r["summary"]["net"] for r in runs]
        row[m] = {"net": round(statistics.fmean(nets), 2), "dd": max(r["summary"]["dd"] for r in runs),
                  "n": runs[0]["summary"]["n"]}
        if m == "M1":
            row["M1"].update({k: runs[0]["summary"][k] for k in ("ex_best", "pf", "win", "mean", "days")})
            row["years"] = by_year(runs[0]["trades"])
    row["robust"] = min(row[m]["net"] for m in (models or MODELS))
    return row
