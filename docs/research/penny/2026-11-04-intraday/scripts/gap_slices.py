"""Gap-down open->close by liquidity, price, previous-day move and series (descriptive, seen daily).

Jan-Jul 2026 excluded (sealed exam). Penny band as in gap_daily.
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "scripts"))
import gap_daily as g  # noqa: E402


def main():
    bars = g.load()
    rows = defaultdict(list)
    for t, seq in bars.items():
        for i in range(21, len(seq) - 1):
            d, (o, h, l, c, v) = seq[i]
            if g.RESERVED[0] <= d <= g.RESERVED[1]:
                continue
            pd_, (po, ph, pl, pc, pv) = seq[i - 1]
            vals = sorted(x[1][3] * x[1][4] for x in seq[i - 20:i])
            med = vals[10]
            if not (1 <= pc <= 55) or med < 500_000:
                continue
            gap = o / pc - 1
            if gap > -0.02:
                continue
            oc = c / o - 1
            yday = pc / seq[i - 2][1][3] - 1
            rows["liq " + ("5-20L" if med < 2e6 else "20L-1cr" if med < 1e7 else ">1cr")].append(oc)
            rows["price " + ("1-5" if pc < 5 else "5-15" if pc < 15 else "15-55")].append(oc)
            rows["yday " + ("down>3%" if yday < -0.03 else "up>3%" if yday > 0.03 else "flat")].append(oc)
            rows["series " + ("-BE/BZ" if "-" in t else "EQ")].append(oc)
            rows["era " + ("2010-18" if d < "2019" else "2019-26")].append(oc)
            rows["gap " + ("-2..-3" if gap > -0.03 else "-3..-5" if gap > -0.05 else "-5..-10" if gap > -0.10 else "<-10")].append(oc)
            rows["dayvalue_vs_med " + ("<0.5x" if v * c < 0.5 * med else "0.5-2x" if v * c < 2 * med else ">2x")].append(oc)
            lowcirc = abs(o - l) / o < 1e-4
            rows["open_is_low " + str(lowcirc)].append(oc)
            rows["all"].append(oc)
    for k in sorted(rows):
        xs = rows[k]
        pos = sum(x > 0 for x in xs) / len(xs)
        print(f"{k:28s} n={len(xs):6d} mean={100*statistics.fmean(xs):6.2f}% median={100*statistics.median(xs):6.2f}% win={100*pos:5.1f}%")


if __name__ == "__main__":
    main()
