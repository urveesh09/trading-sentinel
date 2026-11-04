"""Round 3 (development): learn from R2. The unconstrained EV model drifted into thin,
weak-closing names (bid-ask bounce a flat cost cannot price). Constrain liquidity.

  EVL2_50L / EVL2_1CR : EV whole band, today's traded value >= Rs 50 lakh / 1 crore
  EVL2_SPR            : EV whole band, tv >= 50 lakh, cost += Abdi-Ranaldo half-spread estimate
  SHIPL2_1CR          : shipped order with tv >= 1 crore (does liquidity alone change the shipped book?)
  NIGHT2 / SHIP2      : Round-2 references
Usage: python round3.py kite|yahoo E36|PC
"""
import json, math, statistics as st, sys
from dataclasses import replace
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab, ev, round2
from arms import MODELS, line

@lab.selector("liq_hurdle")
def _liq(day, cands, p):
    out = []
    for c in cands:
        b = day.bar[c.ticker]
        tv = b["close"] * b["volume"]
        if tv < p["tv"]:
            continue
        extra = p.get("spr", 0) * day.spread.get(c.ticker, 0.0) if p.get("spr") else 0.0
        if p.get("cost") is not None and c.adj - p["cost"] - extra <= 0:
            continue
        out.append(c)
    return out

def spreads(days):
    """Abdi-Ranaldo (2017) close-high-low estimator over the prior 20 sessions (causal)."""
    hist = {}
    for d in days:
        d.spread = {}
        for t, b in d.bar.items():
            h = hist.setdefault(t, [])
            if len(h) >= 21:
                vals = []
                for (c0, e0), (_, e1) in zip(h[-21:-1], h[-20:]):
                    vals.append((c0 - e0) * (c0 - e1))
                s2 = 4 * st.mean(vals)
                d.spread[t] = math.sqrt(max(s2, 0.0)) / 2   # half-spread
            h.append((math.log(b["close"]), (math.log(b["high"]) + math.log(b["low"])) / 2))

def main(panel, model):
    tf, s, e = round2.WINDOWS[panel]
    days = lab.load(HERE / f"_local/days-{panel}.pkl")
    spreads(days)
    pred, _ = ev.walk_forward(panel, train_from=tf, predict_from=s, predict_to=e)
    alld = ev.ev_days(days, pred, "all")
    eb, xb = MODELS[model]
    base = dict(entry_bps=eb, exit_bps=xb, compound=False)
    c2 = round2.cost_frac(model, 2)
    res = {}
    def go(name, ds, arm):
        r = lab.run_book(ds, replace(arm, **base), start=s, end=e, keep_trades=True)
        res[name] = r["summary"]
        tr = r["trades"]
        tv = st.median(t["close"] * 0 + t["notional"] for t in tr) if tr else 0
        spr = st.median(days_by[t["entry_date"]].spread.get(t["ticker"], float('nan')) for t in tr) if tr else 0
        print(line(name, r["summary"]), f"| med half-spread est {100*spr:.2f}%", flush=True)
    days_by = {d.date: d for d in days}
    print(f"[{panel} {s}..{e} model={model} fixed]")
    go("SHIP2", days, lab.Arm("SHIP2", slots=2, sizing="equal"))
    go("NIGHT2", days, lab.Arm("NIGHT2", slots=2, sizing="equal", select="night_screen", params=(("min", .001),)))
    go("SHIPL2_1CR", days, lab.Arm("SHIPL2_1CR", slots=2, sizing="equal", select="liq_hurdle", params=(("tv", 1e7), ("cost", None))))
    go("EVALL2", alld, lab.Arm("EVALL2", slots=2, sizing="equal", kinds_skip=(), select="net_hurdle", params=(("cost", c2),)))
    go("EVL2_50L", alld, lab.Arm("EVL2_50L", slots=2, sizing="equal", kinds_skip=(), select="liq_hurdle", params=(("tv", 5e6), ("cost", c2))))
    go("EVL2_1CR", alld, lab.Arm("EVL2_1CR", slots=2, sizing="equal", kinds_skip=(), select="liq_hurdle", params=(("tv", 1e7), ("cost", c2))))
    go("EVL2_SPR", alld, lab.Arm("EVL2_SPR", slots=2, sizing="equal", kinds_skip=(), select="liq_hurdle", params=(("tv", 5e6), ("cost", c2), ("spr", 1.0))))
    go("EVL1_1CR", alld, lab.Arm("EVL1_1CR", slots=1, sizing="equal", kinds_skip=(), select="liq_hurdle", params=(("tv", 1e7), ("cost", round2.cost_frac(model, 1)))))
    sh = [d.spread.get(c.ticker) for d in days if s <= d.date <= e for c in d.cands[:3] if d.spread.get(c.ticker) is not None]
    print(f"shipped top-3 candidates' half-spread estimate: med {100*st.median(sh):.2f}%  mean {100*st.mean(sh):.2f}%")
    (HERE / f"_local/round3-{panel}-{model}.json").write_text(json.dumps(res, indent=1))

if __name__ == "__main__":
    main(*sys.argv[1:3])
