"""Random-entry control and the severe-fill scenario for E02 R3 and E03.

Random entries keep each day's signal count, the 13:00-15:00 window and every exit, cash and
brake rule; only the minute and direction are drawn (seeded). If E03's exits made the money
by themselves, random entries would earn too.
"""
import json, random, sys
import numpy as np
import e03_lab as X
E = X.E

E03 = dict(max_lots=3, split=True, runner_floor=1.0, runner_keep=0.5, hero_target=9.0)
ORIGINAL = E.directions


def random_directions(seed):
    def directions(t, rule):
        real = ORIGINAL(t, rule)
        rng = random.Random(f"{seed}-{t.day}")
        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
        out = np.zeros(t.n, dtype=np.int8)
        for i in rng.sample(range(lo, hi), int(np.count_nonzero(real))):
            out[i] = rng.choice((1, -1))
        return out
    return directions


def main(n=100):
    res = {}
    for name, extra in (("E02_R3", {}), ("E03", E03)):
        rule = X.Hero(**{**X.R3, **extra})
        for y in (2024, 2025):
            actual = X.run_year(X.tapes(y), rule)["summary"]["net"]
            nets = []
            try:
                for s in range(n):
                    E.directions = random_directions(s)
                    nets.append(X.run_year(X.tapes(y), rule)["summary"]["net"])
            finally:
                E.directions = ORIGINAL
            nets = np.array(nets)
            res[f"{name}_{y}"] = dict(actual=actual, random_mean=round(float(nets.mean()), 2),
                                      random_p95=round(float(np.percentile(nets, 95)), 2),
                                      share_random_at_or_above=float((nets >= actual).mean()))
            print(name, y, res[f"{name}_{y}"], flush=True)
        for y in (2024, 2025):
            cat = X.run_year(X.tapes(y), rule, "catastrophe")["summary"]
            res[f"{name}_{y}_catastrophe"] = X.brief(cat)
            print(name, y, "catastrophe", X.brief(cat), flush=True)
    X.D.dump(X.HERE / "controls.json", res)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
