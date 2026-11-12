"""SN04 - an ACTIVE book for the Rs 15,000 wallet: SN01's entry families with N11-style exits (research only).

The owner (Nov 12): too many no-trade days (624 of 742 for the SN02 benchmark); trade actively and profitably.
SN01 tried active entries with premium-percentage exits and lost about Rs 200 a trade. It never tried the exits the
profitable N11 book uses: a stop and target on the INDEX measured in ATR, a trailing stop on the index, a time stop,
the 15:10 flat, and a 25% premium backstop. SN04 asks whether active entries + those exits can earn, and the NULL
(random entries + the same exits) says whether any edge is the entry's or the exit's.

Observation model as the year replays: one look per minute at the minute's close; an index-level exit sells at that
minute's option close bid; the premium backstop and the day loss limit are stop-markets on the option's minute low.
Wallet: Rs 15,000 fixed, one lot (the strike one step further out of the money when one lot costs more), one position
at a time, Rs 3,000 day loss limit, current Zerodha charges + Rs 205 per lot per trade.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn01")]

import sn01_search as S1  # noqa: E402
import sn01_sim as M  # noqa: E402

YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
EVALS = LOCAL / "evals.jsonl"
STRESS = 205.0
WALLET, LOSS = 15000.0, 3000.0
FLAT_MIN = 355             # 15:10
MIN_ACTIVE_SHARE = 0.50    # the owner wants activity: trades on at least half the sessions of every training year
POOL_REAL, POOL_NULL = 4000, 2000
GENS, CHILDREN, ELITE = 8, 120, 50
SEED = 20261113

EXIT_GENES = {
    "stop_k": [1.5, 2.0, 3.0, 4.0, 6.0],        # index stop distance in 1-minute ATRs
    "target_r": [0.0, 1.0, 1.5, 2.0, 3.0],       # index target in multiples of the stop distance (0 = none)
    "trail_r": [0.0, 0.5, 1.0, 1.5],             # start trailing once the index is this many R in favour (0 = never)
    "trail_k": [1.5, 2.0, 3.0, 4.0],             # trail distance in 1-minute ATRs
    "time": [15, 30, 45, 75, 120, 400],          # minutes (400 = to 15:10)
    "backstop": [0.15, 0.25, 0.35],              # premium backstop
}
DAY_GENES = {
    "bias": ["none", "with_daily", "against_daily", "puts", "calls"],
    "offset": [-1, 0, 1],
    "max_trades": [1, 2, 3, 5, 8],
    "start": [5, 15, 30, 45],
    "last_entry": [255, 300, 330],
}


def key(g: dict) -> str:
    return hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:20]


def random_genome(rng: random.Random, null: bool) -> dict:
    fams = [S1._family(rng, null)]
    if not null and rng.random() < 0.35:
        second = S1._family(rng, null)
        if second["kind"] != fams[0]["kind"]:
            fams.append(second)
    g = {"families": fams, "null": null}
    for space in (EXIT_GENES, DAY_GENES):
        for gene, values in space.items():
            g[gene] = rng.choice(values)
    if g["start"] >= g["last_entry"]:
        g["start"] = 5
    return g


def mutate(g: dict, rng: random.Random) -> dict:
    g = json.loads(json.dumps(g))
    for _ in range(rng.choice([1, 1, 2, 3])):
        r = rng.random()
        if r < 0.3:
            i = rng.randrange(len(g["families"]))
            fam = g["families"][i]
            space = (S1.NULL_GENES if g["null"] else S1.FAMILY_GENES)[fam["kind"]]
            gene = rng.choice(sorted(space))
            fam[gene] = rng.choice(space[gene])
            if rng.random() < 0.1:
                g["families"][i] = S1._family(rng, g["null"])
        else:
            space = EXIT_GENES if r < 0.7 else DAY_GENES
            gene = rng.choice(sorted(space))
            values = space[gene]
            if g[gene] in values and rng.random() < 0.7:
                j = values.index(g[gene]) + rng.choice([-1, 1])
                g[gene] = values[max(0, min(len(values) - 1, j))]
            else:
                g[gene] = rng.choice(values)
    if g["start"] >= g["last_entry"]:
        g["start"] = 5
    return g


def run_day(S: M.Session, g: dict, wallet: float = WALLET, loss: float = LOSS, stress: float = STRESS,
            sig: np.ndarray | None = None, record: bool = False) -> dict:
    F = S.F
    if sig is None:
        sig = M.signals(F, g, S.seed)
    c, atr = F["c"], F["atr"]
    idx = np.flatnonzero(sig[: g["last_entry"] + 1])
    idx = idx[idx >= g["start"]]
    realized, n, trades, i = 0.0, 0, [], g["start"]
    while n < g["max_trades"]:
        k = np.searchsorted(idx, i)
        if k >= len(idx):
            break
        i = int(idx[k])
        d = int(sig[i])
        opt = "CE" if d > 0 else "PE"
        strike = int(round(c[i] / M.STEP) * M.STEP) + d * g["offset"] * M.STEP
        rec, ask, lots = None, None, 0
        for attempt in range(2):
            rec = S.option(strike, opt)
            if rec is None or not rec[6][i]:
                rec = None
                break
            ask = M.ask_of(float(rec[0][3][i]))
            lots = 1 if ask * M.LOT <= wallet else 0
            if lots or attempt:
                break
            strike += M.STEP * d
        if rec is None or not lots:
            i += 1
            continue
        a, b_open, b_high, b_low, b_close, b_mark, traded = rec
        qty = M.LOT
        room = loss + realized
        est = M.charges(ask, ask, qty) + stress
        prem_stop = max(M._ceil_tick(ask * (1 - g["backstop"])), M._ceil_tick(ask - (room - est) / qty))
        if (ask - prem_stop) * qty + est > room + 1e-6:
            break
        risk = g["stop_k"] * atr[i]
        u0 = c[i]
        u_stop = u0 - d * risk
        u_tgt = u0 + d * g["target_r"] * risk if g["target_r"] > 0 else None
        best = u0
        trailing = False
        exit_px, reason, j = None, None, i
        for j in range(i + 1, M.EXIT_MIN + 1):
            if traded[j] and b_low[j] <= prem_stop:
                exit_px, reason = min(prem_stop, b_open[j]), "backstop"
                break
            u = c[j]
            fav = (u - u0) * d
            if g["trail_r"] > 0 and fav >= g["trail_r"] * risk:
                trailing = True
            best = max(best, u) if d > 0 else min(best, u)
            stop_level = u_stop
            if trailing:
                tr = best - d * g["trail_k"] * atr[j]
                stop_level = max(stop_level, tr) if d > 0 else min(stop_level, tr)
            bid = b_close[j] if traded[j] else b_mark[j]
            if (u - stop_level) * d <= 0:
                exit_px, reason = bid, "trail" if trailing else "index_stop"
                break
            if u_tgt is not None and (u - u_tgt) * d >= 0:
                exit_px, reason = bid, "index_target"
                break
            if j - i >= g["time"] or j >= FLAT_MIN:
                exit_px, reason = bid, "time" if j - i >= g["time"] else "flat_1510"
                break
        if exit_px is None or np.isnan(exit_px):
            exit_px, reason = float(b_mark[j]) if not np.isnan(b_mark[j]) else ask, "eod"
        exit_px = float(exit_px)
        net = (exit_px - ask) * qty - M.charges(ask, exit_px, qty) - stress
        realized += net
        n += 1
        if record:
            trades.append({"i": i, "j": j, "dir": d, "strike": strike, "entry": ask, "exit": exit_px,
                           "net": round(net, 2), "reason": reason})
        i = j + 1
        if loss + realized < loss * 0.05:
            break
    return {"day": S.day, "net": realized, "trades": n, "detail": trades}


# ---- search ----------------------------------------------------------------------------------------------------

_S = None


def _init(year: str) -> None:
    global _S
    import sn01_data as D
    _S = [M.Session(s) for s in D.load_year(year)["sessions"].values()]


def _eval(genomes: list[dict]) -> list[dict]:
    out = []
    for g in genomes:
        rs = [run_day(S, g) for S in _S]
        nets = [r["net"] for r in rs]
        out.append({"net": round(sum(nets), 2), "sessions": len(rs), "trades": sum(r["trades"] for r in rs),
                    "green": sum(1 for x in nets if x > 0), "red": sum(1 for x in nets if x < 0),
                    "active": sum(1 for r in rs if r["trades"]), "worst": round(min(nets), 2),
                    "refilled": round(sum(-x for x in nets if x < 0), 2)})
    return out


class Pool:
    def __init__(self):
        self.ex = {y: ProcessPoolExecutor(max_workers=1, initializer=_init, initargs=(y,)) for y in YEARS}

    def evaluate(self, genomes):
        futs = {y: self.ex[y].submit(_eval, genomes) for y in YEARS}
        per = {y: f.result() for y, f in futs.items()}
        return [{y: per[y][i] for y in YEARS} for i in range(len(genomes))]

    def close(self):
        for ex in self.ex.values():
            ex.shutdown()


def load_evals() -> dict:
    out = {}
    if EVALS.exists():
        for line in EVALS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["key"]] = r
    return out


def evaluate_new(pool, genomes, evals, origin):
    todo, seen = [], set()
    for g in genomes:
        k = key(g)
        if k not in evals and k not in seen:
            todo.append(g)
            seen.add(k)
    for s in range(0, len(todo), 300):
        part = todo[s:s + 300]
        res = pool.evaluate(part)
        with open(EVALS, "a", encoding="utf-8") as fh:
            for g, r in zip(part, res):
                rec = {"key": key(g), "genome": g, "origin": origin, "years": r}
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
                evals[rec["key"]] = rec
    return [evals[key(g)] for g in genomes]


def fitness(rec: dict, train) -> float:
    per = [rec["years"][y]["net"] / rec["years"][y]["sessions"] for y in train]
    active = all(rec["years"][y]["active"] / rec["years"][y]["sessions"] >= MIN_ACTIVE_SHARE for y in train)
    return min(per) if active else -1e6 + min(per)


def folds():
    out = {y: tuple(x for x in YEARS if x != y) for y in YEARS}
    out["ALL"] = YEARS
    return out


def main(cmd: str) -> None:
    LOCAL.mkdir(exist_ok=True)
    evals = load_evals()
    pool = Pool()
    try:
        if cmd == "pool":
            rng = random.Random(SEED)
            gs = [random_genome(rng, False) for _ in range(POOL_REAL)] + [random_genome(rng, True) for _ in range(POOL_NULL)]
            t = time.time()
            evaluate_new(pool, gs, evals, "pool")
            print("pool", len(evals), round(time.time() - t), "s", flush=True)
        elif cmd == "ga":
            for fold, train in folds().items():
                for null in (False, True):
                    tag = f"ga:{fold}:{'null' if null else 'real'}"
                    rng = random.Random(f"{SEED}|{tag}")
                    for gen in range(GENS):
                        if sum(1 for r in evals.values() if r["origin"] == f"{tag}:{gen}"):
                            continue
                        cands = [r for r in evals.values() if r["genome"]["null"] == null and
                                 (r["origin"] == "pool" or r["origin"].startswith(tag + ":"))]
                        cands.sort(key=lambda r: fitness(r, train), reverse=True)
                        elite = cands[:ELITE]
                        kids = []
                        while len(kids) < CHILDREN:
                            p = max(rng.sample(elite, 4), key=lambda r: fitness(r, train))
                            kids.append(mutate(p["genome"], rng))
                        evaluate_new(pool, kids, evals, f"{tag}:{gen}")
                    best = max((r for r in evals.values() if r["genome"]["null"] == null and
                                (r["origin"] == "pool" or r["origin"].startswith(tag + ":"))),
                               key=lambda r: fitness(r, train))
                    print(tag, "best training", round(fitness(best, train), 1), flush=True)
    finally:
        pool.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pool")
