"""Runtime edge_overnight_paper.night_means == lab night_mean on real cached bars (Kite copy)."""
import json, random, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab
import edge_overnight_paper as eop
days = lab.load(HERE / "_local/days-kite.pkl")
rng = random.Random(5)
sample = [(d, c) for d in days for c in d.cands if d.date >= "2025-10-01"]
sample = rng.sample(sample, 400)
mism, worst = 0, 0.0
for d, c in sample:
    got = eop.night_means(str(lab.KITE), [c.ticker], d.date, {c.ticker: d.bar[c.ticker]["open"]})[c.ticker]
    diff = abs(got - c.f["night_mean"])
    worst = max(worst, diff); mism += diff > 1e-12
out = {"checked": len(sample), "mismatches": mism, "max_abs_diff": worst}
print(out); (HERE / "night-parity.json").write_text(json.dumps(out, indent=1))
