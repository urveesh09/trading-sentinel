"""Classic CNC (Connors RSI(2)) setups on daily bars: where the return comes from (descriptive, seen).

Setup at day t's close: penny band, 20-day median value >= Rs 5 lakh, close > SMA200 and SMA50,
RSI(2) < 10. Variants: + the shipped 'RSI rising two bars' confirmation; + below/above SMA200 etc.
Returns decomposed: night1 = open(t+1)/close(t), day1 = close(t+1)/open(t+1), and close(t)->close(t+3).
Jan-Jul 2026 excluded.
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import oarsim as o  # noqa: E402


def rsi2(c):
    return o._rsi2(c)


def main():
    bars = o.load_bars()
    ev = defaultdict(list)
    for t, seq in bars.items():
        closes = [x[1][3] for x in seq]
        for i in range(250, len(seq) - 4):
            d = seq[i][0]
            c = closes[i]
            if not (1 <= c <= 55):
                continue
            vals = sorted(x[1][3] * x[1][4] for x in seq[i - 19:i + 1])
            if vals[10] < 500_000:
                continue
            s200 = sum(closes[i - 199:i + 1]) / 200
            s50 = sum(closes[i - 49:i + 1]) / 50
            r = rsi2(closes[:i + 1])
            if r >= 10:
                continue
            o1, h1, l1, c1, v1 = seq[i + 1][1]
            c3 = seq[i + 3][1][3]
            rec = (o1 / c - 1, c1 / o1 - 1, c3 / c - 1, c1 / c - 1)
            up = c > s200 and c > s50
            rising = r > rsi2(closes[:i]) > rsi2(closes[:i - 1])
            ev["all RSI2<10"].append(rec)
            ev[("uptrend" if up else "not uptrend")].append(rec)
            if up and rising:
                ev["shipped (uptrend + rising)"].append(rec)
            if up:
                ev["uptrend " + ("2011-18" if d < "2019" else "2019-26")].append(rec)
                g = o1 / c - 1
                ev["uptrend next gap " + ("<=-2%" if g <= -0.02 else ">=+2%" if g >= 0.02 else "flat")].append(rec)
    print(f"{'setup':32s} {'n':>6s} {'night1%':>8s} {'day1%':>8s} {'c->c+1%':>8s} {'c->c+3%':>8s}")
    for k, xs in sorted(ev.items()):
        print(f"{k:32s} {len(xs):6d} {100*statistics.fmean(x[0] for x in xs):8.3f} {100*statistics.fmean(x[1] for x in xs):8.3f} "
              f"{100*statistics.fmean(x[3] for x in xs):8.3f} {100*statistics.fmean(x[2] for x in xs):8.3f}")


if __name__ == "__main__":
    main()
