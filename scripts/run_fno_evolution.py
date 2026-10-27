"""Pre-registered evolution round for the NIFTY single-leg F&O book (research only, O27b).

python scripts/run_fno_evolution.py freeze --out docs/research/fno/<dated>
python scripts/run_fno_evolution.py run --out docs/research/fno/<dated> --jobs 10

The owner's request (Oct 27): breed the good strategies like genes. Keep the parts that worked, drop the worst, mix
them, add new parameters from the opening-range literature and a variation of our own, and test again.

* A genome is 17 genes: 13 entry genes (FnoShadowVariant fields) and 4 exit genes (the exit ladder's parameters).
  Every arm is still the whole live book through fno_policy_replay.
* The population is seeded from the O27 grid's eligible arms (the losing alleles, the 30-minute time stop and the
  continuation entry, are not in the gene pool) and filled with random genomes.
* Evolution sees only the selection window A (Sep 10 - Oct 9): tournament selection, uniform crossover,
  one-step mutation, elites and random immigrants, a fixed random seed.
* Finalists are the best genomes; each is ranked by the median fitness of itself and its one-step neighbours on A.
  Then, once, the finalists and the shipped book are replayed over the whole window and checked on B (Oct 12 - 26),
  which evolution never saw.

``freeze`` binds all of that into ``freeze.json``; commit it before ``run``. No network, broker or Production.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import date
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_fno_consistency_grid as grid  # noqa: E402
from fno_policy_replay import ReplayPolicy, run_replay  # noqa: E402
from fno_shadow import FnoShadowVariant  # noqa: E402

SOURCES = grid.SOURCES[:-1] + ("scripts/run_fno_consistency_grid.py", "scripts/run_fno_evolution.py")
DATASET = "docs/research/fno/2026-10-27-consistency-grid/_local/dataset"
SEEDS_FROM = "docs/research/fno/2026-10-27-consistency-grid/results.json"
FULL = ("2026-09-10", "2026-10-26")
A = ("2026-09-10", "2026-10-09")
A_HALVES = (("2026-09-10", "2026-09-24"), ("2026-09-25", "2026-10-09"))
B = ("2026-10-12", "2026-10-26")
B_MOTIVATING_DAYS = ("2026-10-21", "2026-10-23", "2026-10-26")   # the days that prompted the no-EMA idea

# name, alleles in neighbour order (a mutation step moves to an adjacent allele).
GENES = (
    ("or_minutes", (15, 20, 30, 45)),
    ("freshness", ("crossing", "first_confirmation")),
    ("trend", ("ema_21_50", "ema_9_21", "off")),
    ("buffer", (0.10, 0.25, 0.40, "stretch")),
    ("min_rvol", (0.8, 1.0, 1.2, 1.5)),
    ("vwap_side", (False, True)),
    ("or_bias", ("with", None, "against")),
    ("gap_align", (False, True)),
    ("or_width_ratio", (None, 1.25, 1.0, 0.8)),
    ("narrow_prior_days", (None, 4, 7)),
    ("latest_entry", (720, 810, 885)),
    ("stop_atr", (1.0, 1.5, 2.0)),
    ("target_r", (1.2, 1.8, 2.5)),
    ("lock", ("LOCK_TIGHT", "LOCK_LIVE", "LOCK_LATE", "LOCK_OFF")),
    ("time_stop", (45, 60, 75, 90, 375)),
    ("time_min_r", (0.25, 0.5)),
    ("trail", (0.6, 1.0, 1.5, 2.0)),
)
NAMES = tuple(name for name, _ in GENES)
ALLELES = dict(GENES)
SHIPPED = (30, "crossing", "ema_21_50", 0.25, 1.2, False, None, False, None, None, 885, 1.5, 1.8, "LOCK_LIVE", 45,
           0.5, 1.0)
GA = {"population": 40, "generations": 10, "elites": 4, "immigrants": 4, "tournament": 3, "mutation_rate": 0.12,
      "adjacent_step_share": 0.7, "seed": 20261027, "finalists": 5}
FITNESS = {
    "min_trades": 8, "drawdown_floor": 1000, "half_penalty": 0.5,
    "definition": "on A: (net - max(best day, 0)) / max(max drawdown, 1000) - 0.5 x (number of A halves with "
                  "net < 0); fewer than 8 trades: -5 + trades / 8",
}
CHECK = {"window": "B", "min_trades": 3, "net_pnl_ge": 0, "max_drawdown_le": "max(1.5 * SHIPPED B max_drawdown, 5000)",
         "drawdown_floor": 5000,
         "report_only": "B without Oct 21, 23 and 26 (the days that motivated the no-EMA idea)",
         "recommend": "the first finalist, by plateau fitness, that passes; none passes -> keep the shipped book",
         "if_recommended": "forward-only replay from Oct 28 beside the shipped book; no paper or live change in the "
                           "proving week; promotion is the owner's call on forward evidence"}


def key(genome: tuple) -> str:
    return "|".join(f"{name}={value}" for name, value in zip(NAMES, genome))


def digest(genome: tuple) -> str:
    return hashlib.sha256(key(genome).encode()).hexdigest()[:16]


def policy(genome: tuple) -> ReplayPolicy:
    g = dict(zip(NAMES, genome))
    confirm = g["freshness"] == "first_confirmation"
    variant = FnoShadowVariant(
        name="EVO", opening_range_minutes=g["or_minutes"], freshness=g["freshness"],
        confirmation_bars=1 if confirm else 0, max_extension_atr=0.35 if confirm else None,
        ema_filter=g["trend"] != "off", ema_spans=(9, 21) if g["trend"] == "ema_9_21" else None,
        buffer_atr=None if g["buffer"] == "stretch" else g["buffer"], stretch_buffer=g["buffer"] == "stretch",
        min_rvol=g["min_rvol"], vwap_side=g["vwap_side"], or_bias=g["or_bias"], gap_align=g["gap_align"],
        max_or_width_ratio=g["or_width_ratio"], narrow_prior_days=g["narrow_prior_days"],
        latest_entry_min=None if g["latest_entry"] >= 885 else g["latest_entry"],
        stop_atr_mult=g["stop_atr"], target_r=g["target_r"])
    exits = {**grid.LOCKS[g["lock"]], "FNO_TIME_STOP_MIN": float(g["time_stop"]),
             "FNO_TIME_STOP_MIN_R": float(g["time_min_r"]), "FNO_TRAIL_ATR_MULT": float(g["trail"])}
    return ReplayPolicy(name=digest(genome), manage_every_observation=True,
                        exit_overrides=tuple(sorted(exits.items())), signal_variant=variant)


def seeds(o27_results: dict) -> list[tuple]:
    """The O27 grid's eligible arms as genomes (new genes at the shipped values). Arms whose alleles left the pool
    (the 30-minute time stop, the continuation entry) are dropped."""
    families = {"OR20": (20, "crossing", "ema_21_50"), "OR30": (30, "crossing", "ema_21_50"),
                "OR45": (45, "crossing", "ema_21_50"), "CONFIRM1": (30, "first_confirmation", "ema_21_50")}
    out = []
    for arm in o27_results["decision"]["rank"]:
        entry, lock, minutes, trail = arm.split("|")
        family, _, noema = entry.partition("_")
        if family not in families or minutes == "T30":
            continue
        or_minutes, freshness, trend = families[family]
        genome = list(SHIPPED)
        genome[:3] = [or_minutes, freshness, "off" if noema else trend]
        genome[NAMES.index("lock")] = lock
        genome[NAMES.index("time_stop")] = int(minutes[1:])
        genome[NAMES.index("trail")] = float(trail[2:])
        if tuple(genome) not in out:
            out.append(tuple(genome))
    return out


def random_genome(rng: random.Random) -> tuple:
    return tuple(rng.choice(alleles) for _, alleles in GENES)


def mutate(genome: tuple, rng: random.Random, force: bool = False) -> tuple:
    out = list(genome)
    forced = rng.randrange(len(GENES)) if force else None
    for i, (_, alleles) in enumerate(GENES):
        if i != forced and rng.random() >= GA["mutation_rate"]:
            continue
        at = alleles.index(out[i])
        if rng.random() < GA["adjacent_step_share"]:
            steps = [j for j in (at - 1, at + 1) if 0 <= j < len(alleles)]
            out[i] = alleles[rng.choice(steps)]
        else:
            out[i] = rng.choice([a for a in alleles if a != out[i]])
    return tuple(out)


def crossover(a: tuple, b: tuple, rng: random.Random) -> tuple:
    return tuple(x if rng.random() < 0.5 else y for x, y in zip(a, b))


def neighbours(genome: tuple) -> list[tuple]:
    out = []
    for i, (_, alleles) in enumerate(GENES):
        at = alleles.index(genome[i])
        for j in (at - 1, at + 1):
            if 0 <= j < len(alleles):
                out.append(genome[:i] + (alleles[j],) + genome[i + 1:])
    return out


def _sessions(days: list[str], window: tuple) -> list[str]:
    return [d for d in days if window[0] <= d <= window[1]]


def fitness(trades: list[dict], days: list[str]) -> tuple[float, dict]:
    """The frozen fitness on A (see FITNESS) and the window metrics behind it."""
    m = grid.window_metrics(trades, _sessions(days, A))
    if m["trades"] < FITNESS["min_trades"]:
        return -5.0 + m["trades"] / FITNESS["min_trades"], m
    by_day: dict = defaultdict(float)
    for t in trades:
        if "net_pnl" in t and A[0] <= t["entry_time"][:10] <= A[1]:
            by_day[t["entry_time"][:10]] += t["net_pnl"]
    halves = [sum(v for d, v in by_day.items() if lo <= d <= hi) for lo, hi in A_HALVES]
    value = (m["net_pnl"] - max(max(by_day.values()), 0.0)) / max(m["max_drawdown"], FITNESS["drawdown_floor"]) \
        - FITNESS["half_penalty"] * sum(h < 0 for h in halves)
    m["halves"] = [round(h, 2) for h in halves]
    return round(value, 4), m


def _bound() -> dict:
    return {"sources": {rel: grid._sha(ROOT / rel) for rel in SOURCES},
            "dataset": grid._verify_dataset(ROOT / DATASET), "seeds_from_sha256": grid._sha(ROOT / SEEDS_FROM),
            "settings": _settings_check()}


def _settings_check() -> dict:
    """SHIPPED must be the live book: the generic variant path equals evaluate_fno_mom (O27 parity) only when every
    gene sits at the live value."""
    from config import settings
    live = {"FNO_OR_MINUTES": settings.FNO_OR_MINUTES, "FNO_OR_BUFFER_ATR": settings.FNO_OR_BUFFER_ATR,
            "FNO_MIN_RVOL": settings.FNO_MIN_RVOL, "FNO_ENTRY_END_MIN": settings.FNO_ENTRY_END_MIN,
            "FNO_STOP_ATR_MULT": settings.FNO_STOP_ATR_MULT, "FNO_TARGET_R": settings.FNO_TARGET_R,
            "FNO_TIME_STOP_MIN": settings.FNO_TIME_STOP_MIN, "FNO_TIME_STOP_MIN_R": settings.FNO_TIME_STOP_MIN_R,
            "FNO_TRAIL_ATR_MULT": settings.FNO_TRAIL_ATR_MULT}
    g = dict(zip(NAMES, SHIPPED))
    shipped = {"FNO_OR_MINUTES": g["or_minutes"], "FNO_OR_BUFFER_ATR": g["buffer"], "FNO_MIN_RVOL": g["min_rvol"],
               "FNO_ENTRY_END_MIN": g["latest_entry"], "FNO_STOP_ATR_MULT": g["stop_atr"],
               "FNO_TARGET_R": g["target_r"], "FNO_TIME_STOP_MIN": g["time_stop"],
               "FNO_TIME_STOP_MIN_R": g["time_min_r"], "FNO_TRAIL_ATR_MULT": g["trail"]}
    if live != shipped or grid._settings_check()["current_arm"] != grid.CURRENT_ARM:
        raise SystemExit(f"live settings no longer match the SHIPPED genome: {live} != {shipped}")
    return grid._settings_check()


def freeze(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    seeded = seeds(json.loads((ROOT / SEEDS_FROM).read_text(encoding="utf-8")))
    grid._write_new(out / "freeze.json", {
        "schema": "fno_evolution_freeze_v1", "bound": _bound(), "dataset_folder": DATASET, "seeds_from": SEEDS_FROM,
        "windows": {"FULL": FULL, "A": A, "A_halves": A_HALVES, "B": B, "B_motivating_days": B_MOTIVATING_DAYS},
        "genes": {name: list(alleles) for name, alleles in GENES}, "shipped": list(SHIPPED), "ga": GA,
        "fitness": FITNESS, "check": CHECK, "seed_genomes": [list(g) for g in seeded],
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print(f"frozen: {len(seeded)} seed genomes, {len(GENES)} genes:", out / "freeze.json")


def _evaluate(task: tuple) -> str:
    """Process-pool entry point: one genome replayed over one window, its trades written once."""
    genome, window, dataset, cache, target = task
    if Path(target).exists():
        return target
    data = grid.CachedReplayData(Path(dataset), Path(cache))
    result = run_replay(dataset, start=window[0], end=window[1], policy=policy(tuple(genome)), data=data)
    grid._write_new(Path(target), {"genome": list(genome), "window": list(window), "trades": result["trades"],
                                   "funnel": result["funnel"], "notes": result["notes"]})
    return target


class Lab:
    """Runs and caches evaluations; one process pool for the whole round."""

    def __init__(self, out: Path, jobs: int, days: list[str]):
        self.out, self.days = out, days
        self.local = out / "_local"
        frozen = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
        self.cache = self.local / "observations" / frozen["bound"]["dataset"]["manifest_sha256"][:16]
        for folder in (self.cache, self.local / "A", self.local / "FULL"):
            folder.mkdir(parents=True, exist_ok=True)
        self.pool = ProcessPoolExecutor(max_workers=jobs) if jobs > 1 else None
        self.scores: dict[tuple, dict] = {}

    def _file(self, genome: tuple, window_name: str) -> Path:
        return self.local / window_name / f"{digest(genome)}.json"

    def run(self, genomes: list[tuple], window_name: str) -> None:
        window = {"A": A, "FULL": FULL}[window_name]
        tasks = [(list(g), window, str(ROOT / DATASET), str(self.cache), str(self._file(g, window_name)))
                 for g in dict.fromkeys(genomes) if not self._file(g, window_name).exists()]
        mapper = self.pool.map if self.pool else map
        for _ in mapper(_evaluate, tasks):
            pass

    def trades(self, genome: tuple, window_name: str) -> list[dict]:
        return json.loads(self._file(genome, window_name).read_text(encoding="utf-8"))["trades"]

    def score(self, genomes: list[tuple], generation: int) -> None:
        self.run(genomes, "A")
        for g in genomes:
            if g not in self.scores:
                value, metrics = fitness(self.trades(g, "A"), self.days)
                self.scores[g] = {"fitness": value, "metrics": metrics, "generation": generation}

    def close(self) -> None:
        if self.pool:
            self.pool.shutdown()


def _tournament(population: list[tuple], scores: dict, rng: random.Random) -> tuple:
    return max(rng.sample(population, GA["tournament"]), key=lambda g: (scores[g]["fitness"], key(g)))


def evolve(lab: Lab, seeded: list[tuple], rng: random.Random) -> list[dict]:
    population = list(dict.fromkeys(seeded))[:GA["population"]]
    while len(population) < GA["population"]:
        candidate = random_genome(rng)
        if candidate not in population:
            population.append(candidate)
    history = []
    for generation in range(GA["generations"] + 1):
        lab.score(population, generation)
        ranked = sorted(population, key=lambda g: (-lab.scores[g]["fitness"], key(g)))
        best = lab.scores[ranked[0]]
        history.append({"generation": generation, "evaluated_total": len(lab.scores),
                        "best_fitness": best["fitness"], "best": key(ranked[0]),
                        "median_fitness": statistics.median(lab.scores[g]["fitness"] for g in population)})
        print(f"gen {generation:2}: best {best['fitness']:7.3f} median {history[-1]['median_fitness']:7.3f} "
              f"evaluated {len(lab.scores)}", flush=True)
        if generation == GA["generations"]:
            break
        nxt = ranked[:GA["elites"]]
        while len(nxt) < GA["elites"] + GA["immigrants"]:
            candidate = random_genome(rng)
            if candidate not in lab.scores and candidate not in nxt:
                nxt.append(candidate)
        while len(nxt) < GA["population"]:
            child = mutate(crossover(_tournament(population, lab.scores, rng),
                                     _tournament(population, lab.scores, rng), rng), rng)
            tries = 0
            while (child in lab.scores or child in nxt) and tries < 20:
                child, tries = mutate(child, rng, force=True), tries + 1
            if child not in nxt:
                nxt.append(child)
        population = nxt
    return history


def allele_effects(scores: dict) -> dict:
    out = {}
    for i, (name, alleles) in enumerate(GENES):
        out[name] = {}
        for allele in alleles:
            values = [s["fitness"] for g, s in scores.items() if g[i] == allele]
            if values:
                out[name][str(allele)] = {"n": len(values), "median_fitness": round(statistics.median(values), 4),
                                          "best_fitness": max(values),
                                          "feasible_share": round(sum(v > -4 for v in values) / len(values), 3)}
    return out


def run(out: Path, jobs: int) -> None:
    frozen = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed since freeze; refusing to score")
    days = [d for d in frozen["bound"]["dataset"]["quote_days"] if FULL[0] <= d <= FULL[1]]
    lab = Lab(out, jobs, days)
    try:
        lab.run([SHIPPED], "A")
        current = run_replay(ROOT / DATASET, start=A[0], end=A[1], policy="CURRENT",
                             data=grid.CachedReplayData(ROOT / DATASET, lab.cache))["trades"]
        shipped_parity = [_trade_key(t) for t in lab.trades(SHIPPED, "A")] == [_trade_key(t) for t in current]
        print("shipped genome == CURRENT on A:", shipped_parity, flush=True)
        rng = random.Random(GA["seed"])
        seeded = [tuple(g) for g in frozen["seed_genomes"]]
        history = evolve(lab, seeded, rng)
        finalists = sorted(lab.scores, key=lambda g: (-lab.scores[g]["fitness"], key(g)))[:GA["finalists"]]
        lab.score([n for g in finalists for n in neighbours(g)], generation=-1)
        plateau = {g: statistics.median([lab.scores[g]["fitness"], *[lab.scores[n]["fitness"] for n in neighbours(g)]])
                   for g in finalists}
        finalists.sort(key=lambda g: (-plateau[g], key(g)))
        o27_pick = seeds({"decision": {"rank": [json.loads((ROOT / SEEDS_FROM).read_text(encoding="utf-8"))[
            "decision"]["recommended"]]}})
        checked = list(dict.fromkeys([*finalists, SHIPPED, *o27_pick]))
        lab.run(checked, "FULL")
        sessions = {"A": _sessions(days, A), "B": _sessions(days, B),
                    "B_without_motivating_days": [d for d in _sessions(days, B) if d not in B_MOTIVATING_DAYS],
                    "FULL": days}
        holdout = {}
        for g in checked:
            trades = lab.trades(g, "FULL")
            holdout[g] = {w: grid.window_metrics(trades, s) for w, s in sessions.items()}
            holdout[g]["a_matches_evolution"] = (
                [_trade_key(t) for t in trades if A[0] <= t["entry_time"][:10] <= A[1]]
                == [_trade_key(t) for t in lab.trades(g, "A")] if g in lab.scores else None)
        limit = max(1.5 * holdout[SHIPPED]["B"]["max_drawdown"], CHECK["drawdown_floor"])
        checks = {g: {"trades_ge_3": holdout[g]["B"]["trades"] >= CHECK["min_trades"],
                      "net_ge_0": holdout[g]["B"]["net_pnl"] >= 0,
                      "drawdown_within": holdout[g]["B"]["max_drawdown"] <= limit} for g in finalists}
        passed = [g for g in finalists if all(checks[g].values())]
        decision = {"shipped_genome_equals_current_on_A": shipped_parity, "b_drawdown_limit": round(limit, 2),
                    "finalists": [key(g) for g in finalists],
                    "plateau_fitness": {key(g): round(plateau[g], 4) for g in finalists},
                    "checks": {key(g): c for g, c in checks.items()},
                    "recommended": key(passed[0]) if passed else None,
                    "verdict": "SHADOW_CANDIDATE" if passed else "NONE_PASSED_KEEP_SHIPPED",
                    "qualification": "NOT_ASSESSED"}
    finally:
        lab.close()
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed during scoring; refusing results")
    grid._write_new(out / "results.json", {
        "schema": "fno_evolution_results_v1", "freeze_sha256": grid._sha(out / "freeze.json"), "history": history,
        "decision": decision, "shipped": key(SHIPPED), "o27_pick": [key(g) for g in o27_pick],
        "holdout": {key(g): v for g, v in holdout.items()},
        "fitness_shipped": lab.scores.get(SHIPPED, {}).get("fitness"),
        "evaluations": {key(g): s for g, s in lab.scores.items()}, "allele_effects": allele_effects(lab.scores),
        "bound_verified_after_scoring": True})
    print(json.dumps({k: decision[k] for k in ("verdict", "recommended", "shipped_genome_equals_current_on_A",
                                               "b_drawdown_limit")}, indent=1))
    for g in finalists:
        h = holdout[g]
        print(f"plateau {plateau[g]:6.3f} fit {lab.scores[g]['fitness']:6.3f} | A {h['A']['trades']}t "
              f"{h['A']['net_pnl']:.0f} dd {h['A']['max_drawdown']:.0f} | B {h['B']['trades']}t {h['B']['net_pnl']:.0f} "
              f"dd {h['B']['max_drawdown']:.0f} {'PASS' if all(checks[g].values()) else 'fail'} | {key(g)}")


def _trade_key(t: dict) -> tuple:
    return (t.get("bar_ts"), t.get("tradingsymbol"), t.get("entry_time"), t.get("exit_reason"), t.get("net_pnl"))


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--jobs", type=int, default=4)
    args = cli.parse_args()
    if args.action == "freeze":
        freeze(args.out.resolve())
    else:
        run(args.out.resolve(), max(1, args.jobs))


if __name__ == "__main__":
    main()
