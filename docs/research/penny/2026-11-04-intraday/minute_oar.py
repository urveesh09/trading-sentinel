"""Opening-auction reversal on minute days (idata.Day): official daily open/close plus minute bars.

Exits: "close" (official close, post-close session) or "1515" (last trade at or before 15:15, less
`exit_bps`). Capacity: "none", or "c915" = at most `c915_share` of the 09:15 candle's volume (Kite's
first candle carries the opening match). Same lock rule as oarsim: a stock that closes on its low
below the open cannot be sold that day; the sale carries to the next open (delivery charges).
Fixed bankroll, profits withheld, losses reduce the next day's capital.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import idata  # noqa: E402
import oarsim  # noqa: E402  (also puts python-engine on sys.path)
from penny_risk import calc_penny_costs  # noqa: E402


@dataclass(frozen=True)
class MPolicy:
    name: str
    slots: int = 1
    gap_max: float = -0.02
    exit: str = "close"          # close | 1515
    exit_bps: float = 0.0
    entry_bps: float = 0.0
    capacity: str = "none"       # none | c915
    c915_share: float = 0.10
    eq_only: bool = True
    skip_thin: bool = False      # skip (slot kept) names whose median 09:15 candle volume over the
                                 # prior 20 sessions x c915_share < a quarter of the ticket (causal)


def first_volume_history(days: list) -> dict:
    """(ticker, date) -> median 09:15 candle volume over that ticker's prior <= 20 sessions (None < 5)."""
    seq = defaultdict(list)
    for d in sorted(days, key=lambda x: (x.ticker, x.date)):
        seq[d.ticker].append(d)
    out = {}
    for t, xs in seq.items():
        vols = []
        for d in xs:
            prior = vols[-20:]
            out[(t, d.date)] = statistics.median(prior) if len(prior) >= 5 else None
            vols.append(d.bars[0][5] if d.bars and d.bars[0][0] == 555 else 0.0)
    return out


def simulate(days: list, p: MPolicy, *, start: str, end: str, bankroll: float, keep: bool = True, fvh=None):
    if p.skip_thin and fvh is None:
        fvh = first_volume_history(days)
    by = defaultdict(list)
    for d in days:
        if start <= d.date <= end and idata.in_band(d) and d.day_open and d.day_close and d.day_low:
            if p.eq_only and "-" in d.ticker:
                continue
            gap = d.day_open / d.prev_close - 1
            if gap <= p.gap_max:
                by[d.date].append((gap, d.ticker, d))
    realized, trades, curve, out = 0.0, [], [], Counter()
    for date in sorted(by):
        cap = min(bankroll, bankroll + realized)
        seen, entered, day_net = set(), 0, 0.0
        for gap, t, d in sorted(by[date], key=lambda x: (x[0], x[1])):
            if entered >= p.slots:
                break
            base = t.split("-")[0]
            if base in seen:
                continue
            seen.add(base)
            entry = d.day_open * (1 + p.entry_bps / 1e4)
            qty = int((cap / p.slots) // entry)
            plan = qty
            if p.skip_thin:
                h = fvh.get((t, date))
                if h is None or p.c915_share * h < 0.25 * plan:
                    out["SKIP_THIN"] += 1
                    continue
            if p.capacity == "c915":
                first = d.bars[0] if d.bars and d.bars[0][0] == 555 else None
                qty = min(qty, int(p.c915_share * (first[5] if first else 0.0)))
            entered += 1
            if qty < 1 or qty < 0.25 * plan:
                out["CAPACITY_OR_DUST"] += 1
                continue
            intraday, locked = True, False
            if d.day_close <= d.day_low * (1 + 1e-4) and d.day_close < d.day_open * (1 - 1e-4):
                locked, intraday = True, False
                if d.next_open is None:
                    ref = d.day_close * 0.95
                elif d.next_open <= d.next_low * (1 + 1e-4) and d.next_close <= d.next_low * (1 + 1e-4):
                    ref = d.next_close
                else:
                    ref = d.next_open
                exit_px = ref
            elif p.exit == "close":
                exit_px = d.day_close * (1 - p.exit_bps / 1e4)
            else:
                px = idata.price_at(d.bars, 915)
                if px is None:
                    out["NO_1515_PRICE"] += 1
                    px = d.day_close
                exit_px = px * (1 - p.exit_bps / 1e4)
            fees = float(calc_penny_costs(entry, exit_px, qty, is_intraday=intraday))
            net = (exit_px - entry) * qty - fees
            out["LOCKED" if locked else "FILLED"] += 1
            day_net += net
            tr = {"date": date, "ticker": t, "net": net}
            if keep:
                tr.update({"gap": gap, "entry": entry, "exit": exit_px, "qty": qty, "locked": locked,
                           "ret": exit_px / entry - 1})
            trades.append(tr)
        realized += day_net
        curve.append((date, bankroll + realized))
    s = oarsim.summarize(trades, curve, bankroll)
    months = defaultdict(float)
    for t in trades:
        months[t["date"][:7]] += t["net"]
    return {"policy": asdict(p), "summary": s, "months": {k: round(v, 2) for k, v in sorted(months.items())},
            "outcomes": dict(out), "trades": trades if keep else None}
