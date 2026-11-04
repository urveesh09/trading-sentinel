"""Overnight surface on ALL band rows, dev windows only. ret x clv grid; day-high locks excluded."""
import sys, pickle, statistics as st
from pathlib import Path
HERE = Path(__file__).resolve().parent
src, start, end = sys.argv[1:4]
rows = [r for r in pickle.load(open(HERE / f"_local/allrows-{src}.pkl", "rb")) if start <= r[1] <= end]
def locked(f):
    return f["from_high"] >= -0.001 and f["ret"] >= 0.019
rs = [r for r in rows if not locked(r[2])]
print(f"{src} {start}..{end} rows={len(rows)} unlocked={len(rs)} mean on={100*st.mean(r[3] for r in rs):+.3f}%")
retb = [-1, -.03, -.01, 0, .01, .02, .03, .05, .08, .12, 5]
clvb = [0, .5, .8, .9, 1.01]
print("ret \ clv      " + "".join(f"[{a},{b})".ljust(22) for a, b in zip(clvb, clvb[1:])))
for a, b in zip(retb, retb[1:]):
    cells = []
    for c, d in zip(clvb, clvb[1:]):
        g = [r[3] for r in rs if a <= r[2]["ret"] < b and c <= r[2]["clv"] < d and r[2]["tv"] >= 5e5]
        cells.append(f"{100*st.mean(g):+.2f}% n={len(g)}".ljust(22) if len(g) >= 40 else "-".ljust(22))
    print(f"[{a:+.2f},{b:+.2f})".ljust(15) + "".join(cells))
