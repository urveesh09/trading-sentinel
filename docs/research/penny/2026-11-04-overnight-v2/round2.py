"""Round 2 (development only): selection inside one execution model.

Arms (all two equal slots unless named otherwise, fixed Rs 25k sizing):
  SHIP2        shipped EDGE order (Round 1 winner TWO_EQ)
  NIGHT2       shipped order, G05 screen night_mean >= 0.1% (earlier study's finalist idea)
  EVEDGE2      shipped candidates re-ranked by the walk-forward EV model, expected net > 0
  EVALL1/2/3   whole unlocked band ranked by the EV model, expected net > 0
  RAND_EDGE2   null: random order among shipped candidates (seeded, 50 books)
  RAND_HOT2    null: random order among unlocked band rows up >= 5% on rvol >= 1 (50 books)
Usage: python round2.py kite|yahoo <model E36|PC>
"""
from __future__ import annotations
import json, random, statistics as st, sys
from copy import copy
from dataclasses import replace
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab, ev  # noqa: E402
from arms import MODELS, line  # noqa: E402

WINDOWS = {"kite": ("2025-07-01", "2026-01-01", "2026-09-30"),
           "yahoo": ("2023-01-01", "2023-07-03", "2026-10-30")}


def cost_frac(model, slots, bankroll=25000.0):
    eb, xb = MODELS[model]
    return (eb + xb) / 1e4 + 0.00222 + 15.34 / (bankroll / slots)


@lab.selector("net_hurdle")
def _net_hurdle(day, cands, p):
    return [c for c in cands if c.adj - p["cost"] > p.get("min_edge", 0.0)]


@lab.selector("night_screen")
def _night(day, cands, p):
    return [c for c in cands if c.f.get("night_mean", 0) >= p["min"]]


def shuffled(days, seed, pool):
    rng = random.Random(seed)
    out = []
    for d in days:
        nd = copy(d)
        if pool == "edge":
            cs = list(d.cands[:lab.RANK_DEPTH])
        else:
            cs = [lab.Cand(t, "RND", "RND", 0.5, 0.5, b["close"], b["close"] * .9, b["close"] * 1.1, {})
                  for t, b in d.bar.items() if d.hot.get(t)]
        rng.shuffle(cs)
        nd.cands = cs
        out.append(nd)
    return out


def main(panel, model):
    train_from, start, end = WINDOWS[panel]
    days = lab.load(HERE / f"_local/days-{panel}.pkl")
    pred, models = ev.walk_forward(panel, train_from=train_from, predict_from=start, predict_to=end)
    eb, xb = MODELS[model]
    base = dict(entry_bps=eb, exit_bps=xb, compound=False)
    res = {}

    def go(name, ds, arm):
        r = lab.run_book(ds, replace(arm, **base), start=start, end=end, keep_trades=False)
        res[name] = r["summary"]
        print(line(name, r["summary"]), flush=True)

    print(f"[{panel} {start}..{end} model={model} fixed; EV refits={len(models)}]")
    go("SHIP3", days, lab.Arm("SHIP3"))
    go("SHIP2", days, lab.Arm("SHIP2", slots=2, sizing="equal"))
    go("NIGHT2", days, lab.Arm("NIGHT2", slots=2, sizing="equal", select="night_screen", params=(("min", .001),)))
    edge_days = ev.ev_days(days, pred, pool="edge")
    all_days = ev.ev_days(days, pred, pool="all")
    for slots in (1, 2, 3):
        c = cost_frac(model, slots)
        if slots == 2:
            go("EVEDGE2", edge_days, lab.Arm("EVEDGE2", slots=2, sizing="equal", kinds_skip=(),
                                              select="net_hurdle", params=(("cost", c),)))
        go(f"EVALL{slots}", all_days, lab.Arm(f"EVALL{slots}", slots=slots, sizing="equal", kinds_skip=(),
                                              select="net_hurdle", params=(("cost", c),)))
    # nulls
    for d in days:
        d.hot = {t: (d.prev_close.get(t) and b["close"] / d.prev_close[t] - 1 >= .05
                     and not (b["close"] >= b["high"] * .999)) for t, b in d.bar.items()
                 if 5 <= b["close"] <= 55 and not t.endswith(("-SM", "-ST"))}
    for pool in ("edge", "hot"):
        nets = []
        for s in range(50):
            r = lab.run_book(shuffled(days, s, pool), replace(lab.Arm("R", slots=2, sizing="equal", kinds_skip=()), **base),
                             start=start, end=end, keep_trades=False)
            nets.append(r["summary"]["net"])
        q = sorted(nets)
        res[f"RAND_{pool.upper()}2"] = {"p10": q[5], "p50": q[25], "p90": q[45], "max": q[-1]}
        print(f"RAND_{pool.upper()}2 (50 books) net p10={q[5]:,.0f} p50={q[25]:,.0f} p90={q[45]:,.0f} max={q[-1]:,.0f}", flush=True)
    (HERE / f"_local/round2-{panel}-{model}.json").write_text(json.dumps({"results": res, "models": models}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
