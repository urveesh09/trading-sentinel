"""The owner's genome search for the lottery ticket, on the eight seen sessions.

Winners breed, the worst are dropped, a little randomness keeps the search honest. It can only rank rules on these
eight days, one of which is most of the money, so a winner here is a candidate and nothing more. Two things stop
it fooling me: every leave-one-session-out fold reruns the whole search without that day, and September stays
closed until the candidates are frozen.

    python genome.py full  --seeds 3 --gens 30
    python genome.py folds --gens 25

Results are checkpointed under _local/ga/, so a slice that stops can resume.
"""
from __future__ import annotations

import argparse
import json
import random
import time as clock
from dataclasses import asdict, replace
from datetime import time
from multiprocessing import Pool
from pathlib import Path

import e011_lab as L

GA = L.LOCAL / "ga"
_S: dict = {}

SPACE = {
    "stop": [None, .15, .20, .25, .30, .35, .40, .50],
    "back": [.25, 0.0, .5, None],
    "bank_at": [1.0, 1.5, 2.0, 3.0, None],
    "bank": ["half", "recover"],
    "bank_floor": [None, 1.0, 1.5],
    "trails": [((4.0, .60),), ((2.0, .60), (4.0, .60)), ((1.0, .50), (4.0, .60)), ((1.0, .60), (4.0, .70)),
               ((2.0, .50),), ((3.0, .60),), ((4.0, .70),), ((0.5, .50), (2.0, .60), (4.0, .70))],
    "time_stop": [None, (300, .10), (600, .15), (900, .25), (1200, .25), (1200, .50), (1800, .50)],
    "flat_at": [time(15, 38), time(15, 28), time(15, 13)],
    "tickets": [1, 2, 3],
    "same_direction": [False, True],
    "prove": [None, (.10, 5), (.10, 10), (.20, 5), (.20, 10), (.20, 20), (.30, 10), (.30, 20), (.50, 20)],
    "band_hi": [1.0, .75, .65, .6, .55, .5, .45, .4, 1.25],
    "band_lo": [1.0, 2.0, 3.0],
    "budget": [1.0, .8, .6],
    "late": [None, (time(15, 0), .70), (time(15, 0), .85), (time(15, 15), .70)],
    "own_ratio": [None, .90, .95, 1.0, 1.05, 1.10, 1.20],
    "straddle_ratio": [None, .90, .925, .95, .975, 1.0],
    "pilot": [None, (.5, .10, 10), (.5, .10, 20), (.5, .20, 10), (.5, .20, 20), (.5, .30, 20), (.5, .50, 30),
              (.3, .20, 20), (.3, .50, 30), (.7, .20, 20)],
    "box_max_bp": [None, 20.0, 25.0, 30.0, 35.0, 45.0],
    "confirm": [2, 3, 6, 12],
    "buffer_width": [.15, .25, .50],
    "last_entry": [time(15, 5), time(14, 45), time(14, 30)],
}
SIGNAL_GENES = ("confirm", "buffer_width", "last_entry")


def to_ticket(g: dict) -> L.Ticket:
    signal = L.SignalGene(confirm=g["confirm"], buffer_width=g["buffer_width"], last_entry=g["last_entry"])
    fields = {k: v for k, v in g.items() if k not in SIGNAL_GENES}
    return L.Ticket(signal=signal, **fields)


def e01_genome() -> dict:
    t = L.E01
    return dict(stop=t.stop, back=t.back, bank_at=t.bank_at, bank=t.bank, bank_floor=t.bank_floor, trails=t.trails,
                time_stop=t.time_stop, flat_at=t.flat_at, tickets=t.tickets, same_direction=t.same_direction, prove=t.prove,
                band_hi=t.band_hi, band_lo=t.band_lo, budget=t.budget, late=t.late, own_ratio=t.own_ratio,
                straddle_ratio=t.straddle_ratio, pilot=t.pilot, box_max_bp=t.box_max_bp, confirm=t.signal.confirm,
                buffer_width=t.signal.buffer_width, last_entry=t.signal.last_entry)


def key(g: dict) -> str:
    return repr(sorted(g.items(), key=lambda kv: kv[0]))


def init():
    for day, u in L.recorded_keys():
        _S[day] = L.Recorded(day, u)


def nets(g: dict) -> dict:
    t = to_ticket(g)
    out = {}
    for day, S in _S.items():
        rows = L.run_c(S, t, "X")
        out[day] = (L.net(rows), len(rows))
    return out


def fitness(per: dict, days: list[str]) -> float:
    """Half the best day, all of the rest. A rule must still trade: it may not simply refuse."""
    values = [per[d][0] for d in days]
    tickets = sum(per[d][1] for d in days)
    best, total = max(values), sum(values)
    score = (total - best) + .5 * best
    worst = min(values)
    if worst < -1000:
        score -= 2 * (-1000 - worst)
    if tickets < .6 * len(days):
        score -= 2000
    return score


def evolve(days: list[str], pool, seed: int, gens: int, size: int, cache: dict, tag: str) -> list[dict]:
    rng = random.Random(seed)
    names = list(SPACE)

    def random_one():
        g = e01_genome()
        for name in rng.sample(names, rng.randint(1, len(names))):
            g[name] = rng.choice(SPACE[name])
        return g

    def score_all(group):
        fresh, seen = [], set()
        for g in group:
            k = key(g)
            if k not in cache and k not in seen:
                fresh.append(g)
                seen.add(k)
        for g, per in zip(fresh, pool.map(nets, fresh, chunksize=4)):
            cache[key(g)] = per
        return [(fitness(cache[key(g)], days), g) for g in group]

    population = [e01_genome()] + [random_one() for _ in range(size - 1)]
    best = []
    for gen in range(gens):
        scored = sorted(score_all(population), key=lambda r: -r[0])
        best = scored[:20]
        keep = [g for _, g in scored[:max(4, size // 10)]]
        survivors = [g for _, g in scored[:size // 2]]     # the worst half don't breed
        children = list(keep)
        while len(children) < size:
            if rng.random() < .10:
                children.append(random_one())              # a little randomness
                continue
            a, b = rng.sample(survivors, 2)
            child = {n: (a if rng.random() < .5 else b)[n] for n in names}
            for n in names:
                if rng.random() < .08:
                    child[n] = rng.choice(SPACE[n])
            children.append(child)
        population = children
        if gen == gens - 1:
            print(f"{tag} seed {seed} gen {gen} best {scored[0][0]:.0f} cache {len(cache)}", flush=True)
    return [dict(score=s, genome=g) for s, g in best]


def describe(g: dict) -> dict:
    base = e01_genome()
    return {k: (str(v)) for k, v in g.items() if v != base[k]}


def run_full(args, pool):
    days = [d for d, _ in L.recorded_keys()]
    cache: dict = {}
    results = []
    for seed in range(args.seeds):
        target = GA / f"full-seed{seed}.json"
        if target.exists():
            continue
        started = clock.time()
        top = evolve(days, pool, seed, args.gens, args.size, cache, "full")
        rows = [dict(score=r["score"], diff=describe(r["genome"]), per={d: cache[key(r["genome"])][d] for d in days}) for r in top]
        GA.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rows, indent=1) + "\n")
        (GA / f"full-seed{seed}.pkl").write_bytes(__import__("pickle").dumps([r["genome"] for r in top]))
        print("seed", seed, "seconds", round(clock.time() - started), flush=True)
        results.append(rows[0])
    print(json.dumps(results, indent=1))


def run_folds(args, pool):
    days = [d for d, _ in L.recorded_keys()]
    cache: dict = {}
    for held in days:
        target = GA / f"fold-{held}.json"
        if target.exists():
            continue
        train = [d for d in days if d != held]
        top = evolve(train, pool, 7, args.gens, args.size, cache, f"fold {held}")
        pick = top[0]["genome"]
        per = cache[key(pick)]
        GA.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(dict(held=held, diff=describe(pick), train=sum(per[d][0] for d in train),
                                          held_net=per[held][0], held_tickets=per[held][1]), indent=1) + "\n")
        print("fold", held, "held net", per[held], flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("mode", choices=("full", "folds"))
    cli.add_argument("--seeds", type=int, default=3)
    cli.add_argument("--gens", type=int, default=30)
    cli.add_argument("--size", type=int, default=120)
    cli.add_argument("--workers", type=int, default=6)
    a = cli.parse_args()
    with Pool(a.workers, initializer=init) as p:
        (run_full if a.mode == "full" else run_folds)(a, p)
