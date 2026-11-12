"""SN09 - option open-interest entries for N11's empty days, Rs 15,000 wallet (research only).

No SN or N book has used option OI. Option writers (sellers) carry most index option OI, so where they add positions is
a reading of where they expect price NOT to go. Four families, on N11's empty days only (N11 keeps its own days):
  PCRD    the put/call OI ratio near the price rises (put writing: bullish) or falls (call writing: bearish) by x over k min
  FLOW    put OI added minus call OI added near the price over k minutes, as a share of the OI there; optional price agreement
  WALLB   breakout through the strike with the most call OI above (long) or most put OI below (short), last minute's walls
  WALLR   rebound off the most-put-OI strike below (long) / rejection at the most-call-OI strike above (short)
Exits: SN04's index exits; gates: SN06's daily ADX / DMI. NULL: random entries behind the same gates and exits.
OI snapshots move every third minute; every reading at minute i uses snapshots at or before i. Leave one year out.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for _p in ("2026-11-12-sn01", "2026-11-12-sn03", "2026-11-12-sn04", "2026-11-12-sn06"):
    sys.path.insert(0, str(HERE.parent / _p))
sys.path.insert(0, str(HERE))

import sn01_data as D  # noqa: E402
import sn01_search as S1  # noqa: E402
import sn01_sim as M  # noqa: E402
import sn03 as B  # noqa: E402
import sn04 as Q  # noqa: E402
import sn06 as G  # noqa: E402
import sn09_oi as O  # noqa: E402

YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
EVALS = LOCAL / "evals.jsonl"
MIN_ACTIVE = 0.20
POOL_REAL, POOL_NULL = 3000, 1500
GENS, CHILDREN, ELITE = 6, 100, 50
SEED = 20261115
OI_GENES = {
    "PCRD": {"k": [3, 6, 15, 30], "x": [0.02, 0.05, 0.10, 0.20], "w": [150, 300]},
    "FLOW": {"k": [3, 6, 15, 30], "thr": [0.005, 0.01, 0.02, 0.04], "w": [150, 300], "price": [False, True]},
    "WALLB": {"buf": [0.0, 0.5, 1.0], "w": [300, 600]},
    "WALLR": {"buf": [0.5, 1.0, 2.0], "w": [300, 600]},
}


def n11_days(year: str) -> set:
    return {t["day"] for t in B.stream(year, "N11")}


def oi_mats(S, w):
    key = f"_oi{w}"
    if not hasattr(S, key):
        oi = S.oi
        strikes = sorted({k for k, _ in oi})
        K = np.array(strikes, dtype=float)
        n = len(S.F["c"])
        CE = np.vstack([oi.get((k, "CE"), np.zeros(n)) for k in strikes]).astype(float)
        PE = np.vstack([oi.get((k, "PE"), np.zeros(n)) for k in strikes]).astype(float)
        CE, PE = np.nan_to_num(CE), np.nan_to_num(PE)
        mask = np.abs(K[:, None] - S.F["c"][None, :]) <= w
        setattr(S, key, (K, CE, PE, mask))
    return getattr(S, key)


def family(S, fam) -> np.ndarray:
    cache = S.__dict__.setdefault("_fam", {})
    fk = json.dumps(fam, sort_keys=True)
    if fk not in cache:
        cache[fk] = _family(S, fam)
    return cache[fk]


def _family(S, fam) -> np.ndarray:
    F = S.F
    c, o, l, h, atr = F["c"], F["o"], F["l"], F["h"], F["atr"]
    n = len(c)
    up = np.zeros(n, bool)
    dn = np.zeros(n, bool)
    kind = fam["kind"]
    if kind in ("PCRD", "FLOW"):
        K, CE, PE, mask = oi_mats(S, fam["w"])
        k = fam["k"]
        ce_now = (CE * mask).sum(axis=0)
        pe_now = (PE * mask).sum(axis=0)
        ce_then = np.zeros(n)
        pe_then = np.zeros(n)
        ce_then[k:] = (CE[:, :-k] * mask[:, k:]).sum(axis=0)
        pe_then[k:] = (PE[:, :-k] * mask[:, k:]).sum(axis=0)
        valid = np.arange(n) >= k
        if kind == "PCRD":
            with np.errstate(divide="ignore", invalid="ignore"):
                pcr_now = pe_now / ce_now
                pcr_then = pe_then / ce_then
                rel = pcr_now / pcr_then - 1
            rel = np.nan_to_num(rel)
            up = valid & (rel >= fam["x"])
            dn = valid & (rel <= -fam["x"])
        else:
            tot = ce_then + pe_then
            with np.errstate(divide="ignore", invalid="ignore"):
                flow = np.nan_to_num(((pe_now - pe_then) - (ce_now - ce_then)) / tot)
            up = valid & (flow >= fam["thr"])
            dn = valid & (flow <= -fam["thr"])
            if fam["price"]:
                mv = np.zeros(n)
                mv[k:] = c[k:] - c[:-k]
                up &= mv > 0
                dn &= mv < 0
    else:
        K, CE, PE, _ = oi_mats(S, 300)
        w = fam["w"]
        res = np.full(n, np.nan)
        sup = np.full(n, np.nan)
        for i in range(1, n):
            p = c[i - 1]
            above = (K >= p) & (K <= p + w)
            below = (K <= p) & (K >= p - w)
            if above.any():
                res[i] = K[above][np.argmax(CE[above, i - 1])]
            if below.any():
                sup[i] = K[below][np.argmax(PE[below, i - 1])]
        with np.errstate(invalid="ignore"):
            if kind == "WALLB":
                up = c > res + fam["buf"] * atr
                dn = c < sup - fam["buf"] * atr
            else:
                up = (l <= sup + fam["buf"] * atr) & (c > sup) & (c > o)
                dn = (h >= res - fam["buf"] * atr) & (c < res) & (c < o)
    out = np.zeros(n, dtype=np.int8)
    out[M._fresh(up)] = 1
    out[M._fresh(dn) & (out == 0)] = -1
    return out


def signals(S, g) -> np.ndarray:
    n = len(S.F["c"])
    sig = np.zeros(n, dtype=np.int8)
    rd = G.daily().get(S.day)
    gate = g["gate"]
    if gate != "none":
        if rd is None:
            return sig
        if (rd["adx"] >= float(gate[3:5])) != gate.endswith("HIGH"):
            return sig
    for fam in g["families"]:
        p = M._family(S.F, fam, S.seed) if fam["kind"] == "RANDOM" else family(S, fam)
        sig = np.where(sig != 0, sig, p).astype(np.int8)
    if g["with_dmi"] and rd is not None:
        sig[sig == -rd["dir"]] = 0
    if g["bias"] == "puts":
        sig[sig > 0] = 0
    elif g["bias"] == "calls":
        sig[sig < 0] = 0
    return sig


def run_day(S, g, wallet=Q.WALLET, loss=Q.LOSS, stress=Q.STRESS, record=False):
    return Q.run_day(S, g, wallet, loss, stress, sig=signals(S, g), record=record)


def _oi_family(rng, null):
    if null:
        return S1._family(rng, True)
    kind = rng.choice(sorted(OI_GENES))
    return {"kind": kind, **{k: rng.choice(v) for k, v in OI_GENES[kind].items()}}


def random_genome(rng, null):
    g = {"families": [_oi_family(rng, null)], "null": null}
    for space in (Q.EXIT_GENES, Q.DAY_GENES):
        for gene, values in space.items():
            g[gene] = rng.choice(values)
    if g["start"] < 15:
        g["start"] = 15
    if g["start"] >= g["last_entry"]:
        g["start"] = 15
    g["bias"] = rng.choice(["none", "puts", "calls"])
    g["gate"] = rng.choice(G.GATES)
    g["with_dmi"] = rng.random() < 0.5
    return g


def mutate(g, rng):
    g = json.loads(json.dumps(g))
    for _ in range(rng.choice([1, 1, 2, 3])):
        r = rng.random()
        if r < 0.35:
            fam = g["families"][0]
            if g["null"]:
                fam["p"] = rng.choice(S1.NULL_GENES["RANDOM"]["p"])
            else:
                gene = rng.choice(sorted(OI_GENES[fam["kind"]]))
                fam[gene] = rng.choice(OI_GENES[fam["kind"]][gene])
                if rng.random() < 0.1:
                    g["families"][0] = _oi_family(rng, False)
        elif r < 0.75:
            gene = rng.choice(sorted(Q.EXIT_GENES))
            g[gene] = rng.choice(Q.EXIT_GENES[gene])
        elif r < 0.9:
            gene = rng.choice(sorted(Q.DAY_GENES))
            g[gene] = rng.choice(Q.DAY_GENES[gene])
        else:
            g["gate"] = rng.choice(G.GATES)
            g["with_dmi"] = rng.random() < 0.5
    if g["start"] < 15 or g["start"] >= g["last_entry"]:
        g["start"] = 15
    if g["bias"] not in ("none", "puts", "calls"):
        g["bias"] = "none"
    return g


def key(g):
    return hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:20]


_S = None


def sessions(year: str, empty_only: bool = True) -> list:
    oi = O.load(year)
    skip = n11_days(year) if empty_only else set()
    out = []
    for day, s in sorted(D.load_year(year)["sessions"].items()):
        if day in skip:
            continue
        S = M.Session(s)
        S.oi = oi.get(day, {})
        out.append(S)
    return out


def _init(year):
    global _S
    _S = sessions(year)
    G.daily()


def _eval(genomes):
    out = []
    for g in genomes:
        rs = [run_day(S, g) for S in _S]
        nets = [r["net"] for r in rs]
        out.append({"net": round(sum(nets), 2), "sessions": len(rs), "trades": sum(r["trades"] for r in rs),
                    "green": sum(1 for x in nets if x > 0), "red": sum(1 for x in nets if x < 0),
                    "active": sum(1 for r in rs if r["trades"]), "worst": round(min(nets), 2),
                    "refilled": round(sum(-x for x in nets if x < 0), 2)})
    return out


def load_evals():
    out = {}
    if EVALS.exists():
        for line in EVALS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["key"]] = r
    return out


def fitness(rec, train):
    per = [rec["years"][y]["net"] / rec["years"][y]["sessions"] for y in train]
    act = all(rec["years"][y]["active"] / rec["years"][y]["sessions"] >= MIN_ACTIVE for y in train)
    return min(per) if act else -1e6 + min(per)


def main(cmd):
    LOCAL.mkdir(exist_ok=True)
    evals = load_evals()
    ex = {y: ProcessPoolExecutor(max_workers=1, initializer=_init, initargs=(y,)) for y in YEARS}

    def evaluate(gs, origin):
        todo, seen = [], set()
        for g in gs:
            k = key(g)
            if k not in evals and k not in seen:
                todo.append(g)
                seen.add(k)
        for s in range(0, len(todo), 300):
            part = todo[s:s + 300]
            futs = {y: ex[y].submit(_eval, part) for y in YEARS}
            per = {y: f.result() for y, f in futs.items()}
            with open(EVALS, "a", encoding="utf-8") as fh:
                for i, g in enumerate(part):
                    rec = {"key": key(g), "genome": g, "origin": origin, "years": {y: per[y][i] for y in YEARS}}
                    fh.write(json.dumps(rec, sort_keys=True) + "\n")
                    evals[rec["key"]] = rec
    try:
        if cmd == "pool":
            rng = random.Random(SEED)
            t = time.time()
            evaluate([random_genome(rng, False) for _ in range(POOL_REAL)] +
                     [random_genome(rng, True) for _ in range(POOL_NULL)], "pool")
            print("pool", len(evals), round(time.time() - t), "s", flush=True)
        elif cmd == "ga":
            folds = {**{y: tuple(x for x in YEARS if x != y) for y in YEARS}, "ALL": YEARS}
            for fold, train in folds.items():
                for null in (False, True):
                    tag = f"ga:{fold}:{'null' if null else 'real'}"
                    rng = random.Random(f"{SEED}|{tag}")
                    for gen in range(GENS):
                        if any(r["origin"] == f"{tag}:{gen}" for r in evals.values()):
                            continue
                        cands = sorted((r for r in evals.values() if r["genome"]["null"] == null and
                                        (r["origin"] == "pool" or r["origin"].startswith(tag + ":"))),
                                       key=lambda r: fitness(r, train), reverse=True)[:ELITE]
                        evaluate([mutate(max(rng.sample(cands, 4), key=lambda r: fitness(r, train))["genome"], rng)
                                  for _ in range(CHILDREN)], f"{tag}:{gen}")
                    best = max((r for r in evals.values() if r["genome"]["null"] == null and
                                (r["origin"] == "pool" or r["origin"].startswith(tag + ":"))), key=lambda r: fitness(r, train))
                    print(tag, "best training", round(fitness(best, train), 1), flush=True)
    finally:
        for e in ex.values():
            e.shutdown()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pool")
