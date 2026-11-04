"""Candidate-level overnight surface on DEVELOPMENT windows only (hypotheses, not filters).

For every shipped candidate that passes the daily-bar realism refusals, gross
overnight = next open / close - 1. Buckets by causal features and by daily rank.
Usage: python surface.py kite|yahoo <start> <end>
"""
import sys, statistics as st
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab

def rows(days, start, end):
    out = []
    for d in days:
        if not start <= d.date <= end:
            continue
        rank = 0
        for c in d.cands[:lab.RANK_DEPTH]:
            b, pc, n = d.bar.get(c.ticker), d.prev_close.get(c.ticker), d.nxt.get(c.ticker)
            if c.ticker.endswith(("-SM", "-ST")) or c.kind == "MR_mid":
                continue
            if pc and b["close"] >= b["high"] * 0.999 and b["close"] / pc - 1 >= 0.019:
                continue
            if n is None:
                continue
            rank += 1
            r = n["open"] / b["close"] - 1
            out.append({**c.f, "kind": c.kind, "adj": c.adj, "rank": rank, "on": r,
                        "ph": n["open"] == b["close"], "nday": n["close"] / n["open"] - 1,
                        "regime": d.regime[2], "date": d.date})
    return out

def show(rs, key, edges):
    print(f"-- {key}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        g = [r["on"] for r in rs if lo <= r[key] < hi]
        if len(g) >= 30:
            print(f"  [{lo:>8.3g},{hi:>8.3g}) n={len(g):5d} mean={100*st.mean(g):+.2f}% med={100*st.median(g):+.2f}% "
                  f"win={100*sum(x>0 for x in g)/len(g):.0f}%")

def main(panel, start, end):
    days = lab.load(HERE / f"_local/days-{panel}.pkl")
    rs = rows(days, start, end)
    allr = [r["on"] for r in rs]
    print(f"{panel} {start}..{end} candidates={len(rs)} mean={100*st.mean(allr):+.2f}% med={100*st.median(allr):+.2f}% "
          f"ph={100*sum(r['ph'] for r in rs)/len(rs):.1f}% nextday(o->c) mean={100*st.mean(r['nday'] for r in rs):+.2f}%")
    for k in ("MO_strong", "MO_mid", "MR_strong", "MR_soft"):
        g = [r["on"] for r in rs if r["kind"] == k]
        if g: print(f"  kind {k:10s} n={len(g):5d} mean={100*st.mean(g):+.2f}% med={100*st.median(g):+.2f}%")
    for rg in ("MO", "MR", "BOTH"):
        g = [r["on"] for r in rs if r["regime"] == rg]
        if g: print(f"  regime {rg:5s} n={len(g):5d} mean={100*st.mean(g):+.2f}%")
    show(rs, "rank", [1, 2, 3, 4, 6, 11])
    show(rs, "ret", [-1, 0, .03, .05, .07, .09, .12, .2, 5])
    show(rs, "clv", [0, .3, .5, .7, .8, .9, .95, 1.01])
    show(rs, "from_high", [-1, -.06, -.04, -.025, -.015, -.008, -.003, .001])
    show(rs, "rvol", [0, 1, 1.5, 2, 3, 5, 10, 1e9])
    show(rs, "tv", [0, 2e5, 5e5, 1e6, 3e6, 1e7, 1e12])
    show(rs, "price", [4, 8, 12, 20, 35, 61])
    show(rs, "night_mean", [-1, -.002, 0, .001, .002, .004, 1])
    show(rs, "day_mean", [-1, -.006, -.003, 0, .003, 1])
    show(rs, "ph_rate", [0, .02, .05, .1, .2, 1.01])
    show(rs, "atrp", [0, .03, .05, .07, .1, 1])
    show(rs, "gap", [-1, -.02, 0, .01, .03, .06, 1])
    show(rs, "oc", [-1, 0, .02, .04, .06, .1, 1])
    show(rs, "ret5", [-1, 0, .05, .1, .2, .4, 10])
    show(rs, "near_hi20", [-1, -.15, -.08, -.03, -.0001, 1])
    show(rs, "prev_ret", [-1, -.03, 0, .03, .05, .1, 5])

if __name__ == "__main__":
    main(*sys.argv[1:4])
