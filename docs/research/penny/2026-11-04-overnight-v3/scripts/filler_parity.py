"""Runtime ON_V3 filler features (edge_overnight_paper.overnight_features / filler_rule) vs the research
filler table (v3sim.filler_table) on the Kite daily cache, for every 5th session Aug-Sep 2026."""
import json, sqlite3, sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "python-engine"))
import v3sim as v
import edge_overnight_paper as eop
KITE = v.lab.KITE
days = v.lab.load(v.DAYS["kite"][0])
table = v.filler_table(days)
c = sqlite3.connect(Path(KITE).as_uri() + "?mode=ro", uri=True)
dates = [d.date for d in days if "2026-08-01" <= d.date <= "2026-09-30"][::5]
checks = mism_rule = 0; worst = {}
for D in dates:
    bars = {t: (o, h, l, cl, vol) for t, o, h, l, cl, vol in c.execute(
        "SELECT ticker, open, high, low, close, volume FROM ohlcv_cache WHERE date=? AND volume > 0", (D,))}
    rt = eop.overnight_features(str(KITE), bars, D)
    research = {f.ticker: f.f for f in table[D]}
    def refused(f): return f["near_hi20"] is None
    for t, rf in research.items():
        if t not in rt: continue
        r = rt[t]
        checks += 1
        for k in ("ret", "clv", "rvol", "night_mean", "near_hi20"):
            worst[k] = max(worst.get(k, 0), abs(rf[k] - r[k]))
        rr = v.FILL_RULES["F3"](rf) and not (rf["from_high"] >= -.001 and rf["ret"] >= .019)
        ru = eop.filler_rule(r) and not (r["price"] >= bars[t][1] * .999 and r["ret"] >= .019)
        mism_rule += rr != ru
out = {"dates": len(dates), "ticker_checks": checks, "rule_mismatches": mism_rule,
       "max_abs_difference": {k: float(f"{x:.3g}") for k, x in worst.items()}}
print(out)
json.dump(out, open(HERE / "results/filler-parity.json", "w"), indent=1)
