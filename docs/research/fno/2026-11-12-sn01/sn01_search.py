"""SN01 search - random pool + genetic refinement, scored leave-one-year-out against a random-entry NULL (research only).

Commands (run from this folder with the repo's winvenv python):
  pool    evaluate the seeded random pool of REAL and NULL genomes on all four years at the +Rs 100 stress
  ga      genetic refinement per fold (held-out year 2023 / 2024 / 2025 / 2026, and ALL for the final pick),
          separately for REAL and NULL; selection reads only the fold's training years
  status  counts

Every evaluation is saved to _local/evals.jsonl (genome key -> per-year metrics), so a stopped run resumes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
EVALS = LOCAL / "evals.jsonl"
SEARCH_STRESS = 100.0
WALLET, TARGET, LOSS = 15000.0, 1500.0, 3000.0
MIN_TRADES_PER_SESSION = 0.75
POOL_REAL, POOL_NULL = 6000, 3000
GA_GENERATIONS, GA_CHILDREN, GA_ELITE = 10, 150, 60
SEED = 20261112

FAMILY_GENES = {
    "ORB": {"n": [5, 10, 15, 30], "buf": [0.0, 0.25, 0.5, 1.0]},
    "MOMO": {"k": [1, 2, 3, 5, 10], "z": [0.8, 1.0, 1.5, 2.0, 2.5, 3.0], "vwap": [False, True]},
    "TPB": {"fast": [5, 9, 13], "slow": [21, 34, 50], "look": [3, 5, 10], "touch": [0.0, 0.25, 0.5]},
    "VWAPX": {"fast": [5, 9, 13], "buf": [0.0, 0.25, 0.5, 1.0]},
    "EMAX": {"fast": [5, 9, 13], "slow": [21, 34, 50]},
    "FADE": {"z": [2.0, 3.0, 4.0, 6.0, 8.0]},
    "PDX": {"buf": [0.0, 0.5]},
}
NULL_GENES = {"RANDOM": {"p": [0.005, 0.01, 0.02, 0.05, 0.1]}}
DAY_GENES = {
    "bias": ["none", "with_daily", "against_daily", "puts", "calls"],
    "offset": [-1, 0, 1, 2],
    "max_lots": [1, 2, 3],
    "cash": [0.5, 0.8, 1.0],
    "stop": [0.05, 0.08, 0.10, 0.15, 0.20, 0.30],
    "target": [0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 1.00],
    "hold": [2, 3, 5, 10, 15, 30, 60, 120],
    "trail": [(0.0, 0.5), (0.05, 0.3), (0.05, 0.5), (0.10, 0.3), (0.10, 0.5), (0.20, 0.5)],
    "max_trades": [1, 2, 3, 5, 8, 12, 20],
    "start": [1, 5, 15, 30, 45],
    "last_entry": [255, 300, 330, 345],
    "lock": [0.0, 0.0, 0.25, 0.5, 1.0],
}


def key(g: dict) -> str:
    return hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:20]


def _family(rng: random.Random, null: bool) -> dict:
    space = NULL_GENES if null else FAMILY_GENES
    kind = rng.choice(sorted(space))
    fam = {"kind": kind}
    for gene, values in space[kind].items():
        fam[gene] = rng.choice(values)
    if kind == "RANDOM":
        fam["seed"] = rng.randrange(1, 1_000_000)
    return fam


def random_genome(rng: random.Random, null: bool) -> dict:
    fams = [_family(rng, null)]
    if not null and rng.random() < 0.35:
        second = _family(rng, null)
        if second["kind"] != fams[0]["kind"]:
            fams.append(second)
    g = {"families": fams, "null": null}
    for gene, values in DAY_GENES.items():
        g[gene] = rng.choice(values)
    return normalise(g)


def normalise(g: dict) -> dict:
    g = json.loads(json.dumps(g))
    act, give = g.pop("trail") if "trail" in g else (g.get("trail_act", 0.0), g.get("trail_give", 0.5))
    g["trail_act"], g["trail_give"] = act, give
    if g["start"] >= g["last_entry"]:
        g["start"] = 1
    return g


def mutate(g: dict, rng: random.Random) -> dict:
    g = json.loads(json.dumps(g))
    g["trail"] = (g.pop("trail_act"), g.pop("trail_give"))
    null = g["null"]
    for _ in range(rng.choice([1, 1, 2, 3])):
        if rng.random() < 0.3:
            i = rng.randrange(len(g["families"]))
            fam = g["families"][i]
            space = (NULL_GENES if null else FAMILY_GENES)[fam["kind"]]
            gene = rng.choice(sorted(space))
            fam[gene] = rng.choice(space[gene])
            if rng.random() < 0.1:
                g["families"][i] = _family(rng, null)
        elif not null and rng.random() < 0.08:
            if len(g["families"]) == 2:
                g["families"].pop(rng.randrange(2))
            else:
                extra = _family(rng, null)
                if extra["kind"] != g["families"][0]["kind"]:
                    g["families"].append(extra)
        else:
            gene = rng.choice(sorted(DAY_GENES))
            values = DAY_GENES[gene]
            cur = g[gene]
            if cur in values and rng.random() < 0.7:
                j = values.index(cur) + rng.choice([-1, 1])
                g[gene] = values[max(0, min(len(values) - 1, j))]
            else:
                g[gene] = rng.choice(values)
    return normalise(g)


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    child = {"null": a["null"], "families": json.loads(json.dumps(rng.choice([a, b])["families"]))}
    for gene in DAY_GENES:
        if gene == "trail":
            src = rng.choice([a, b])
            child["trail"] = (src["trail_act"], src["trail_give"])
        else:
            child[gene] = rng.choice([a, b])[gene]
    return normalise(child)


# ---- workers ---------------------------------------------------------------------------------------------------

_SESSIONS = None
_YEAR = None


def _init(year: str) -> None:
    global _SESSIONS, _YEAR
    import sn01_data as D
    import sn01_sim as M
    _YEAR = year
    data = D.load_year(year)
    _SESSIONS = [M.Session(s) for s in data["sessions"].values()]


def metrics(results: list[dict]) -> dict:
    nets = [r["net"] for r in results]
    return {"net": round(sum(nets), 2), "sessions": len(results), "trades": sum(r["trades"] for r in results),
            "target_days": sum(1 for r in results if r["end"] == "target"),
            "loss_days": sum(1 for r in results if r["end"] == "loss_limit"),
            "red_days": sum(1 for n in nets if n < 0), "green_days": sum(1 for n in nets if n > 0),
            "worst_day": round(min(nets), 2), "best_day": round(max(nets), 2)}


def _eval(genomes: list[dict], stress: float) -> list[dict]:
    import sn01_sim as M
    out = []
    for g in genomes:
        out.append(metrics([M.run_day(S, g, WALLET, TARGET, LOSS, stress) for S in _SESSIONS]))
    return out


class Pool:
    def __init__(self):
        self.ex = {y: ProcessPoolExecutor(max_workers=1, initializer=_init, initargs=(y,)) for y in YEARS}

    def evaluate(self, genomes: list[dict], stress: float = SEARCH_STRESS) -> list[dict]:
        futs = {y: self.ex[y].submit(_eval, genomes, stress) for y in YEARS}
        per_year = {y: f.result() for y, f in futs.items()}
        return [{y: per_year[y][i] for y in YEARS} for i in range(len(genomes))]

    def close(self):
        for ex in self.ex.values():
            ex.shutdown()


def load_evals() -> dict:
    out = {}
    if EVALS.exists():
        for line in EVALS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["key"]] = rec
    return out


def save(records: list[dict]) -> None:
    with open(EVALS, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")


def evaluate_new(pool: Pool, genomes: list[dict], evals: dict, origin: str) -> list[dict]:
    todo, seen = [], set()
    for g in genomes:
        k = key(g)
        if k not in evals and k not in seen:
            todo.append(g)
            seen.add(k)
    for start in range(0, len(todo), 300):
        part = todo[start:start + 300]
        res = pool.evaluate(part)
        recs = [{"key": key(g), "genome": g, "origin": origin, "years": r} for g, r in zip(part, res)]
        save(recs)
        for rec in recs:
            evals[rec["key"]] = rec
    return [evals[key(g)] for g in genomes]


def fitness(rec: dict, train: tuple[str, ...]) -> float:
    """Worst training year's net per session at the +Rs 100 stress; inactive books rank below every active one."""
    per = [rec["years"][y]["net"] / rec["years"][y]["sessions"] for y in train]
    active = all(rec["years"][y]["trades"] / rec["years"][y]["sessions"] >= MIN_TRADES_PER_SESSION for y in train)
    return min(per) if active else -1e6 + min(per)


def folds() -> dict:
    out = {y: tuple(x for x in YEARS if x != y) for y in YEARS}
    out["ALL"] = YEARS
    return out


def cmd_pool() -> None:
    evals = load_evals()
    rng = random.Random(SEED)
    genomes = [random_genome(rng, False) for _ in range(POOL_REAL)] + [random_genome(rng, True) for _ in range(POOL_NULL)]
    pool = Pool()
    t = time.time()
    try:
        evaluate_new(pool, genomes, evals, "pool")
    finally:
        pool.close()
    print(f"pool: {len(evals)} evaluations, {time.time() - t:.0f}s", flush=True)


def cmd_ga(only: list[str]) -> None:
    evals = load_evals()
    pool = Pool()
    try:
        for fold, train in folds().items():
            if only and fold not in only:
                continue
            for null in (False, True):
                tag = f"ga:{fold}:{'null' if null else 'real'}"
                rng = random.Random(f"{SEED}|{tag}")
                done = sum(1 for r in evals.values() if r["origin"].startswith(tag + ":"))
                for gen in range(GA_GENERATIONS):
                    if done >= (gen + 1) * GA_CHILDREN * 0.9:
                        continue
                    cands = [r for r in evals.values() if r["genome"]["null"] == null and
                             (r["origin"] == "pool" or r["origin"].startswith(tag + ":"))]
                    cands.sort(key=lambda r: fitness(r, train), reverse=True)
                    elite = cands[:GA_ELITE]
                    children = []
                    while len(children) < GA_CHILDREN:
                        if rng.random() < 0.3:
                            a, b = rng.sample(elite[:30], 2)
                            child = mutate(crossover(a["genome"], b["genome"], rng), rng) if rng.random() < 0.5 \
                                else crossover(a["genome"], b["genome"], rng)
                        else:
                            parent = max(rng.sample(elite, 4), key=lambda r: fitness(r, train))
                            child = mutate(parent["genome"], rng)
                        children.append(child)
                    evaluate_new(pool, children, evals, f"{tag}:{gen}")
                    best = max((r for r in evals.values() if r["genome"]["null"] == null and
                                (r["origin"] == "pool" or r["origin"].startswith(tag + ":"))),
                               key=lambda r: fitness(r, train))
                    print(f"{tag} gen {gen}: best training fitness {fitness(best, train):.1f}/session", flush=True)
    finally:
        pool.close()


def cmd_status() -> None:
    evals = load_evals()
    from collections import Counter
    print(len(evals), Counter(r["origin"].rsplit(":", 1)[0] for r in evals.values()))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    LOCAL.mkdir(exist_ok=True)
    if cmd == "pool":
        cmd_pool()
    elif cmd == "ga":
        cmd_ga(sys.argv[2:])
    else:
        cmd_status()
