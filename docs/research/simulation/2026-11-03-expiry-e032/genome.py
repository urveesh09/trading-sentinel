"""Leave-one-year-out genome: can a broad search over every E03/E03.1/E03.2 mechanism beat E03.1 on the year it
did not see? Fit on 2024 and score 2025, then the reverse. Every evaluation is appended to genome-trials.csv.

    python genome.py        both directions, two seeds each, population 40, six generations (<= 480 per direction)

The fitness on the fit year is E02's own: the worse of ordinary and adverse, each without its best day, minus half
the drawdown, with E02's penalties for too few tickets and a day worse than Rs 1,250. Both years were seen before,
so the held-out year is held out from THIS search only, not from the earlier studies.
"""
from __future__ import annotations
import csv, json, random, sys, time
from dataclasses import asdict, replace
from pathlib import Path
import e032_lab as Z

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "genome-trials.csv"
SPACE = {
    "efficiency": (.65, .7, .75, .8), "stretch": (3., 4., 5.), "premium_low": (4., 5., 6.), "premium_high": (15., 20., 25.),
    "reach": (.8, 1., 1.2), "stop": (.3, .35, .4), "arm": (.3, .4, .6), "keep": (.5, .6, .7), "target": (.8, 1., 1.5),
    "hold": (6, 8, 10, 12), "underlying_stop": (1.5, 2., 2.5), "max_lots": (2, 3, 4), "runner_keep": (.4, .5, .6),
    "runner_floor": (1., 1.2), "hero_target": (4., 9., 0.), "lock_arm": (0., .5, .75), "lock_floor": (1., 1.1, 1.2),
    "chase": (.06, .08, .1), "roll_share": (0., .25),
}
FIELDS = ["direction", "seed", "generation", "key", "params", "fit_score", "fit_o", "fit_a", "test_o", "test_a", "test_exb_o", "at"]


def fitness(rule, tapes):
    out = []
    for sc in ("ordinary", "adverse"):
        s = Z.run(tapes, rule, sc)["summary"]
        v = s["without_best"] - .5 * s["drawdown"] - max(0, 15 - s["trades"]) * 500 - max(0, -1250 - s["worst"]) * 2
        out.append((v, s))
    return min(v for v, _ in out), out[0][1], out[1][1]


def random_genes(rng):
    return {k: rng.choice(v) for k, v in SPACE.items()}


def mutate(g, rng, n=2):
    g = dict(g)
    for k in rng.sample(list(SPACE), n):
        g[k] = rng.choice(SPACE[k])
    return g


def search(fit, test, direction, seed, writer, population=40, generations=6):
    rng = random.Random(seed); seen = {}
    pop = [random_genes(rng) for _ in range(population - 1)] + [{k: getattr(Z.E031, k) for k in SPACE}]
    for gen in range(generations):
        scored = []
        for g in pop:
            key = json.dumps(g, sort_keys=True)
            if key not in seen:
                rule = replace(Z.E031, roll_on="base", **g)
                f, so, sa = fitness(rule, fit)
                to, ta = Z.run(test, rule, "ordinary")["summary"], Z.run(test, rule, "adverse")["summary"]
                seen[key] = (f, rule)
                writer.writerow(dict(direction=direction, seed=seed, generation=gen, key=rule.key, params=key, fit_score=round(f, 2),
                                     fit_o=so["net"], fit_a=sa["net"], test_o=to["net"], test_a=ta["net"], test_exb_o=to["without_best"],
                                     at=time.strftime("%Y-%m-%dT%H:%M:%S")))
            scored.append((seen[key][0], g))
        scored.sort(key=lambda x: -x[0])
        elite = [g for _, g in scored[:population // 4]]
        pop = elite + [mutate(rng.choice(elite), rng) for _ in range(population - len(elite))]
    return sorted(((f, json.loads(k)) for k, (f, _) in seen.items()), key=lambda x: -x[0])


def main():
    T = Z.L.tapes(); out = {}
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        for fit_y, test_y in ((2024, 2025), (2025, 2024)):
            direction = f"fit{fit_y}_test{test_y}"
            base = {sc: Z.run(T[test_y], Z.E031, sc)["summary"]["net"] for sc in ("ordinary", "adverse")}
            for seed in (7, 29):
                ranked = search(T[fit_y], T[test_y], direction, seed, w)
                picks = []
                for fscore, g in ranked[:5]:
                    rule = replace(Z.E031, roll_on="base", **g)
                    picks.append(dict(fit_score=round(fscore, 2), genes=g,
                                      test={sc: Z.run(T[test_y], rule, sc)["summary"]["net"] for sc in ("ordinary", "adverse")}))
                out[f"{direction}|{seed}"] = dict(e031_test=base, top5=picks, evaluated=len(ranked))
                print(direction, seed, "E03.1 on test", base, "top-1 on test", picks[0]["test"],
                      "top-5 mean ordinary", round(sum(p["test"]["ordinary"] for p in picks) / 5, 2), flush=True)
    (HERE / "genome-results.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
