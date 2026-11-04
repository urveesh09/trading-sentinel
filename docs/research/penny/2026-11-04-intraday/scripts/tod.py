"""Time-of-day return profile of penny-band stocks on the development minutes (seen data).

Equal-weight mean of returns between clock checkpoints (last traded price at or before each),
plus open (official daily open) and the next official open. Also split by the day's move at 10:30
and by EDGE-like strength (close near high yesterday). Descriptive only; nothing is selected here.
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import idata  # noqa: E402

CHECK = [555, 570, 585, 600, 630, 660, 720, 780, 840, 870, 900, 920, 929]
LABEL = {m: f"{m//60:02d}:{m%60:02d}" for m in CHECK}


def main():
    days = [d for d in idata.dev_days() if idata.in_band(d) and d.day_open and d.day_close]
    print("stock-days", len(days), "tickers", len({d.ticker for d in days}), "dates", len({d.date for d in days}))
    seg = defaultdict(list)
    groups = defaultdict(lambda: defaultdict(list))
    for d in days:
        px = {m: idata.price_at(d.bars, m) for m in CHECK}
        pts = [("open", d.day_open)] + [(LABEL[m], px[m]) for m in CHECK[1:]] + [("close", d.day_close)]
        if d.next_open:
            pts.append(("next_open", d.next_open))
        for (a, pa), (b, pb) in zip(pts, pts[1:]):
            if pa and pb:
                seg[f"{a}->{b}"].append(pb / pa - 1)
        # condition on the morning: move from open to 10:30
        if px[630] and d.day_open:
            mv = px[630] / d.day_open - 1
            g = "up>2%" if mv > 0.02 else "down<-2%" if mv < -0.02 else "flat"
            if px[900]:
                groups["10:30->15:00 by open->10:30"][g].append(px[900] / px[630] - 1)
            groups["close->next_open by open->10:30"][g].append((d.next_open / d.day_close - 1) if d.next_open else None)
        # gap
        gap = d.day_open / d.prev_close - 1
        g = "gap>+2%" if gap > 0.02 else "gap<-2%" if gap < -0.02 else "gap flat"
        groups["open->close by gap"][g].append(d.day_close / d.day_open - 1)
        if px[630]:
            groups["open->10:30 by gap"][g].append(px[630] / d.day_open - 1)
            if px[900]:
                groups["10:30->15:00 by gap"][g].append(px[900] / px[630] - 1)
    out = {"segments": {}, "groups": {}}
    print(f"{'segment':22s} {'n':>6s} {'mean%':>8s} {'median%':>8s}")
    for k, xs in seg.items():
        out["segments"][k] = {"n": len(xs), "mean_pct": round(100 * statistics.fmean(xs), 3), "median_pct": round(100 * statistics.median(xs), 3)}
        print(f"{k:22s} {len(xs):6d} {100*statistics.fmean(xs):8.3f} {100*statistics.median(xs):8.3f}")
    for name, gg in groups.items():
        print(name)
        out["groups"][name] = {}
        for g, xs in sorted(gg.items()):
            xs = [x for x in xs if x is not None]
            if xs:
                out["groups"][name][g] = {"n": len(xs), "mean_pct": round(100 * statistics.fmean(xs), 3)}
                print(f"   {g:10s} n={len(xs):5d} mean={100*statistics.fmean(xs):7.3f}%")
    (HERE / "results/tod-dev.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
