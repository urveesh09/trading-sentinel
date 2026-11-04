"""Runtime penny_smart_v3.select against the research S1_THIN picks, day by day.

Same stock-days (Kite minute archive Jan-Jul 2026, now seen; and Production's Kite export Aug 10 -
Nov 3), the same capital path (from the research trades), thin estimates from the research 09:15
candle history (a name without 5 prior sessions is refused by both; the runtime's daily-share
fallback for its first sessions is not exercised here). Writes results/parity.json.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import idata  # noqa: E402
import minute_oar as mo  # noqa: E402
import penny_smart_v3 as sv3  # noqa: E402  (python-engine is on sys.path via oarsim)


def check(days, start, end):
    p = mo.MPolicy("S1_THIN_close", skip_thin=True)
    fvh = mo.first_volume_history(days)
    res = mo.simulate(days, p, start=start, end=end, bankroll=2000.0, keep=True, fvh=fvh)
    research = {t["date"]: t["ticker"] for t in res["trades"]}
    nets = defaultdict(float)
    for t in res["trades"]:
        nets[t["date"]] += t["net"]
    by = defaultdict(list)
    for d in days:
        if start <= d.date <= end and d.day_open and d.day_close and d.day_low:
            by[d.date].append(d)
    realized, mismatches, compared = 0.0, [], 0
    for date in sorted(by):
        cap = min(2000.0, 2000.0 + realized)
        cands = [sv3.Candidate(d.ticker, d.prev_close, d.day_open, d.median_value20, d.median_vol20) for d in by[date]]
        thin = {d.ticker: fvh.get((d.ticker, date)) for d in by[date] if fvh.get((d.ticker, date)) is not None}
        picks, _ = sv3.select(cands, capital=cap, thin=thin)
        got = picks[0].ticker if picks else None
        want = research.get(date)
        compared += 1
        if got != want:
            mismatches.append({"date": date, "runtime": got, "research": want})
        realized += nets.get(date, 0.0)
    return {"sessions": compared, "research_trades": len(research), "mismatches": mismatches}


def main():
    out = {
        "exam_kite_jan_jul": check(idata.build(idata.EXAM_DB, idata.EXAM_DB, "2025-12-01", "2026-07-31", min_bars=1),
                                   "2026-01-01", "2026-07-31"),
        "production_kite_aug_nov": check(idata.build(idata.DEV_DAILY, idata.DEV_DAILY, "2026-07-30", "2026-11-03", min_bars=1),
                                         "2026-08-10", "2026-11-03"),
    }
    for k, v in out.items():
        print(k, v["sessions"], "sessions", v["research_trades"], "trades", len(v["mismatches"]), "mismatches", v["mismatches"][:5])
    (HERE / "results/parity.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
