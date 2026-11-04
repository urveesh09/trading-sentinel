"""Post-exam diagnostics (2019-2022 is SEEN now; nothing here is a pass/fail).
Fixed-size null distribution, per-year ranked vs random, and the adverse-fill stress for post-close."""
import json, random, statistics as st, sys, hashlib
from copy import copy
from dataclasses import replace
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab, round2
from exam import FINALISTS, shuffled
from arms import MODELS
days = lab.load(HERE / "_local/days-yahoo.pkl")
S, E = "2019-04-01", "2022-12-30"
out = {}
for model in ("E36", "PC"):
    eb, xb = MODELS[model]
    nets, years = [], []
    for s in range(200):
        r = lab.run_book(shuffled(days, s), replace(lab.Arm("N", slots=2, sizing="equal"), entry_bps=eb, exit_bps=xb, compound=False), start=S, end=E, keep_trades=False)
        nets.append(r["summary"]["net"]); years.append(r["summary"]["by_year"])
    q = sorted(nets)
    tw = lab.run_book(days, replace(FINALISTS["TWO_NIGHT"], entry_bps=eb, exit_bps=xb, compound=False), start=S, end=E, keep_trades=False)["summary"]
    t2 = lab.run_book(days, replace(FINALISTS["TWO"], entry_bps=eb, exit_bps=xb, compound=False), start=S, end=E, keep_trades=False)["summary"]
    pct_tw = sum(n < tw["net"] for n in nets) / len(nets)
    pct_t2 = sum(n < t2["net"] for n in nets) / len(nets)
    yr = {y: (st.median(x.get(y, 0) for x in years)) for y in ("2019", "2020", "2021", "2022")}
    out[model] = {"null_fixed_2slot": {"p10": q[20], "p50": q[100], "p90": q[180]}, "TWO_NIGHT": tw["net"], "TWO": t2["net"],
                  "TWO_NIGHT_percentile": pct_tw, "TWO_percentile": pct_t2, "null_median_by_year": yr,
                  "TWO_NIGHT_by_year": tw["by_year"], "TWO_by_year": t2["by_year"]}
    print(model, json.dumps(out[model]))
# post-close adverse selection stress: fills only on half of the nights that end up (deterministic), all losers fill
def adverse(days, keep_frac):
    res = []
    for d in days:
        nd = copy(d); cs = []
        for c in d.cands:
            n = d.nxt.get(c.ticker)
            up = n is not None and n["open"] > d.bar[c.ticker]["close"]
            h = int(hashlib.md5(f"{c.ticker}{d.date}".encode()).hexdigest(), 16) % 1000 / 1000
            if up and h >= keep_frac:
                continue
            cs.append(c)
        nd.cands = cs; res.append(nd)
    return res
for frac in (1.0, 0.75, 0.5):
    ds = adverse(days, frac)
    for name in ("BASE", "TWO_NIGHT"):
        for win, (s, e) in (("exam", (S, E)), ("dev", ("2023-01-01", "2026-10-30"))):
            r = lab.run_book(ds, replace(FINALISTS[name], entry_bps=0, exit_bps=5, compound=False), start=s, end=e, keep_trades=False)["summary"]
            out.setdefault("pc_adverse", {}).setdefault(f"{frac}", {})[f"{name}_{win}"] = r["net"]
            print(f"PC adverse: winners filled {int(frac*100)}%, losers 100%: {name:10s} {win}: net={r['net']:,.0f} n={r['n']} mean={r['mean_pct']:+.2f}%")
(HERE / "after-exam.json").write_text(json.dumps(out, indent=1))
