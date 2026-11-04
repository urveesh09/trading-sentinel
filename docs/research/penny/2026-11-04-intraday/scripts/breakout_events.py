"""Classic MIS breakout events on development minutes (Yahoo 1m Sep 7 - Nov 3; seen data).

Event (approximating penny_engine_breakout): first minute in [10:30, 14:30) whose close is > 0.3% above
the day's prior high, cumulative volume >= 1.8x the pace-adjusted 20-day median, RSI(14) of minute
closes < 70. Entry next bar open; stop max(1.5% under entry, breakout bar low) i.e. the noise stop;
target 2R; else exit at the 15:00 last trade. Gross returns (no spread), split by the opening gap,
the move from open at the signal and the signal clock. Descriptive only.
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3] / "python-engine"))
import idata  # noqa: E402
from penny_engine_breakout import _rsi_14_wilder  # noqa: E402


def event(d):
    bars = d.bars
    cum = 0.0
    hi = None
    closes = []
    for i, (m, o, h, l, c, v) in enumerate(bars):
        cum += v
        closes.append(c)
        if 630 <= m < 870 and hi is not None and i + 1 < len(bars):
            elapsed = min(max(m - 555, 1), 375)
            if c > hi * 1.003 and cum >= 1.8 * d.median_vol20 * elapsed / 375 and _rsi_14_wilder(closes) < 70:
                return i, hi
        hi = h if hi is None else max(hi, h)
    return None


def walk(d, i):
    bars = d.bars
    entry = bars[i + 1][1]
    stop = min(bars[i][3], entry * (1 - 0.015))
    risk = entry - stop
    target = entry + 2 * risk
    for m, o, h, l, c, v in bars[i + 1:]:
        if m >= 900:
            return o / entry - 1, "TIME"
        if l <= stop:
            return min(o, stop) / entry - 1, "STOP"
        if h >= target:
            return max(o, target) / entry - 1, "TARGET"
    return bars[-1][4] / entry - 1, "LAST"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if src == "kite_jan_jul":   # opened by the Smart V3 exam; descriptive only for Classic
        days = idata.build(idata.EXAM_DB, idata.EXAM_DB, "2026-01-01", "2026-07-31", min_bars=1)
    else:
        days = idata.dev_days()
    days = [d for d in days if idata.in_band(d) and d.day_open]
    print(src, "stock-days", len(days))
    groups = defaultdict(list)
    for d in days:
        e = event(d)
        if not e:
            continue
        i, hi = e
        r, why = walk(d, i)
        gap = d.day_open / d.prev_close - 1
        mv = d.bars[i][4] / d.day_open - 1
        groups["all"].append(r)
        groups["exit " + why].append(r)
        groups["gap " + ("<=-2%" if gap <= -0.02 else ">=+2%" if gap >= 0.02 else "flat")].append(r)
        groups["from open " + ("<0" if mv < 0 else "0-3%" if mv < 0.03 else ">=3%")].append(r)
        groups["above prev close " + str(d.bars[i][4] > d.prev_close)].append(r)
        groups["clock " + ("10:30-11:30" if d.bars[i][0] < 690 else "11:30-13:00" if d.bars[i][0] < 780 else "13:00-14:30")].append(r)
    for k, xs in sorted(groups.items()):
        print(f"{k:28s} n={len(xs):4d} mean={100*statistics.fmean(xs):6.2f}% median={100*statistics.median(xs):6.2f}% win={100*sum(x>0 for x in xs)/len(xs):5.1f}%")


if __name__ == "__main__":
    main()
