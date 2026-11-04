"""Round 4 (development): bounded genome search over the shipped overnight book, judged by
walk-forward of the SEARCH PROCEDURE plus a null search on shuffled candidate order.

Genes: slots, sizing, night screen, clv floor, kinds, depth, max from_high, min rvol, price cap.
Fitness on the training fold: net per trade x sqrt(trades) (a t-like score, needs >= 150 trades).
Folds (Yahoo dev): A = 2023-07..2024-12, B = 2025-01..2026-10; Kite 2026 is a third check.
The search picks on A, is scored on B (and Kite); then the reverse (pick on B, score on A).
NULL: the same search on days whose shipped candidate order is shuffled (seeded).
Usage: python genome.py <model E36|PC>
"""
from __future__ import annotations
import json, math, random, sys
from copy import copy
from dataclasses import replace
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402
from arms import MODELS  # noqa: E402

POOL = {"slots": [1, 2, 3], "sizing": ["equal", "risk"], "night": [None, 0.0, 0.001, 0.002],
        "clv": [0.0, 0.5, 0.7], "kinds": ["noMRmid", "all", "MOonly", "MRonly"], "depth": [5, 10, 20],
        "from_high": [None, -0.003], "rvol": [0.0, 2.0, 5.0], "price_max": [None, 35.0]}
FOLDS = {"A": ("2023-07-03", "2024-12-31"), "B": ("2025-01-01", "2026-10-30")}
SHIP2 = {"slots": 2, "sizing": "equal", "night": None, "clv": 0.0, "kinds": "noMRmid", "depth": 10,
         "from_high": None, "rvol": 0.0, "price_max": None}


@lab.selector("genome")
def _sel(day, cands, p):
    out = []
    for c in cands:
        f = c.f
        if p["night"] is not None and f.get("night_mean", 0) < p["night"]:
            continue
        if f.get("clv", 1) < p["clv"]:
            continue
        if p["kinds"] == "MOonly" and c.stype != "MO" or p["kinds"] == "MRonly" and c.stype != "MR":
            continue
        if p["from_high"] is not None and f.get("from_high", 0) > p["from_high"]:
            continue
        if f.get("rvol", 0) < p["rvol"]:
            continue
        if p["price_max"] is not None and c.close > p["price_max"]:
            continue
        out.append(c)
    return out


def arm_of(g: dict, model: str) -> lab.Arm:
    eb, xb = MODELS[model]
    skip = ("MR_mid",) if g["kinds"] in ("noMRmid", "MOonly", "MRonly") else ()
    params = tuple(sorted(g.items()))
    return lab.Arm("G", slots=g["slots"], sizing=g["sizing"], kinds_skip=skip, select="genome", params=params,
                   depth=g["depth"], entry_bps=eb, exit_bps=xb, compound=False)


def score(days, g, model, window):
    r = lab.run_book(days, arm_of(g, model), start=window[0], end=window[1], keep_trades=False)
    s = r["summary"]
    fit = (s["net"] / s["n"]) * math.sqrt(s["n"]) if s["n"] >= 150 else -1e9
    return fit, s


def search(days, model, window, budget=60, seed=7):
    rng = random.Random(seed)
    seen, pop = set(), []
    def key(g): return tuple(sorted(g.items()))
    def add(g):
        if key(g) in seen: return
        seen.add(key(g)); f, s = score(days, g, model, window); pop.append((f, g, s))
    add(dict(SHIP2))
    while len(pop) < 20:
        add({k: rng.choice(v) for k, v in POOL.items()})
    while len(pop) < budget:
        pop.sort(key=lambda x: -x[0])
        a, b = rng.choice(pop[:6])[1], rng.choice(pop[:6])[1]
        child = {k: (a if rng.random() < .5 else b)[k] for k in POOL}
        if rng.random() < .5:
            k = rng.choice(list(POOL)); child[k] = rng.choice(POOL[k])
        add(child)
    pop.sort(key=lambda x: -x[0])
    return pop


def shuffled(days, seed):
    rng = random.Random(seed); out = []
    for d in days:
        nd = copy(d); cs = list(d.cands); rng.shuffle(cs); nd.cands = cs; out.append(nd)
    return out


def main(model):
    ydays = lab.load(HERE / "_local/days-yahoo.pkl")
    kdays = lab.load(HERE / "_local/days-kite.pkl")
    report = {"model": model, "folds": FOLDS, "pool": POOL, "runs": []}
    for train, test in (("A", "B"), ("B", "A")):
        for label, ds in (("REAL", ydays), ("NULL", shuffled(ydays, 11))):
            pop = search(ds, model, FOLDS[train])
            best = pop[0]
            _, s_test = score(ds, best[1], model, FOLDS[test])
            _, s_ship = score(ds, SHIP2, model, FOLDS[test])
            _, k_best = score(kdays if label == "REAL" else shuffled(kdays, 11), best[1], model, ("2025-07-01", "2026-09-30"))
            _, k_ship = score(kdays if label == "REAL" else shuffled(kdays, 11), SHIP2, model, ("2025-07-01", "2026-09-30"))
            ranks = sorted(pop, key=lambda x: -x[0])
            # does training rank predict test rank? (Spearman over the top 20 trained genomes)
            top = ranks[:20]
            test_nets = [score(ds, g, model, FOLDS[test])[1]["net"] for _, g, _ in top]
            order = sorted(range(len(top)), key=lambda i: -test_nets[i])
            rho = 1 - 6 * sum((i - order.index(i)) ** 2 for i in range(len(top))) / (len(top) * (len(top) ** 2 - 1))
            run = {"train": train, "test": test, "label": label, "best": best[1], "train_summary": best[2],
                   "test_summary": s_test, "ship2_test": s_ship, "kite_best": k_best, "kite_ship2": k_ship,
                   "spearman_top20": round(rho, 3), "evaluated": len(pop)}
            report["runs"].append(run)
            print(f"{model} {label} train {train} -> test {test}: best={best[1]}\n"
                  f"   train net={best[2]['net']:,.0f} n={best[2]['n']} | test net={s_test['net']:,.0f} n={s_test['n']} "
                  f"vs SHIP2 {s_ship['net']:,.0f} | kite {k_best['net']:,.0f} vs SHIP2 {k_ship['net']:,.0f} | spearman(top20)={rho:+.2f}",
                  flush=True)
    (HERE / f"_local/genome-{model}.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
