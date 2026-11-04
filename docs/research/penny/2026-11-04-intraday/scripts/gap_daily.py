"""Daily-bar check of the opening-gap pattern by year (descriptive, seen daily history).

Penny band (prev close Rs 1-55, 20-day median value >= Rs 5 lakh). Open -> close and
open -> next open by gap bucket. Jan 1 - Jul 31 2026 is EXCLUDED (reserved for the sealed
minute exam). Histories before each ticker's latest split are dropped (overnight-v2 cuts).
"""
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
V2 = ROOT / "docs/research/penny/2026-11-04-overnight-v2/_local"
OLD = ROOT / "docs/research/penny/2026-11-04-overnight-enrichment/_local/older/yahoo.sqlite"
RESERVED = ("2026-01-01", "2026-07-31")


def load():
    cuts = json.loads((V2 / "yahoo-split-cuts.json").read_text())
    bars = defaultdict(dict)
    for path in (OLD, V2 / "yahoo/yahoo.sqlite"):
        c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        for t, d, o, h, l, cl, v in c.execute("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache"):
            if None in (o, h, l, cl, v) or min(o, h, l, cl) <= 0 or v <= 0:
                continue
            d = d[:10]
            if d < cuts.get(t, ""):
                continue
            bars[t][d] = (float(o), float(h), float(l), float(cl), float(v))
        c.close()
    return {t: sorted(x.items()) for t, x in bars.items() if t != "NIFTYBEES"}


def rows(bars):
    for t, seq in bars.items():
        for i in range(21, len(seq) - 1):
            d, (o, h, l, c, v) = seq[i]
            if RESERVED[0] <= d <= RESERVED[1]:
                continue
            pc = seq[i - 1][1][3]
            vals = sorted(x[1][3] * x[1][4] for x in seq[i - 20:i])
            if not (1 <= pc <= 55) or vals[10] < 500_000:
                continue
            nd, (no, *_r) = seq[i + 1]
            yield t, d, o / pc - 1, c / o - 1, no / c - 1, (c - l) / (h - l) if h > l else 0.5


def bucket(g):
    for lo, name in ((-0.10, "<-10%"), (-0.05, "-10..-5%"), (-0.03, "-5..-3%"), (-0.02, "-3..-2%"), (-0.01, "-2..-1%"),
                     (0.01, "-1..+1%"), (0.02, "+1..+2%"), (0.05, "+2..+5%")):
        if g < lo:
            return name
    return ">+5%"


def main():
    bars = load()
    by = defaultdict(lambda: defaultdict(list))
    allb = defaultdict(list)
    for t, d, gap, oc, cn, clv in rows(bars):
        y = d[:4]
        b = bucket(gap)
        by[b][y].append(oc)
        allb[b].append((oc, cn))
    years = sorted({y for b in by.values() for y in b})
    out = {}
    print("open->close mean % by gap bucket and year (n in brackets)")
    print(f"{'bucket':10s}" + "".join(f"{y:>9s}" for y in years) + f"{'all':>9s}{'n':>7s}{'next-night':>11s}")
    order = ["<-10%", "-10..-5%", "-5..-3%", "-3..-2%", "-2..-1%", "-1..+1%", "+1..+2%", "+2..+5%", ">+5%"]
    for b in order:
        xs = allb[b]
        line = f"{b:10s}"
        out[b] = {"years": {}, "all": None}
        for y in years:
            v = by[b].get(y, [])
            line += f"{100*statistics.fmean(v):9.2f}" if len(v) >= 20 else f"{'':9s}"
            if v:
                out[b]["years"][y] = {"n": len(v), "mean_pct": round(100 * statistics.fmean(v), 3)}
        out[b]["all"] = {"n": len(xs), "oc_mean_pct": round(100 * statistics.fmean(x[0] for x in xs), 3),
                         "oc_median_pct": round(100 * statistics.median(x[0] for x in xs), 3),
                         "night_mean_pct": round(100 * statistics.fmean(x[1] for x in xs), 3)}
        line += f"{100*statistics.fmean(x[0] for x in xs):9.2f}{len(xs):7d}{100*statistics.fmean(x[1] for x in xs):11.2f}"
        print(line)
    (HERE / "results/gap-daily.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
