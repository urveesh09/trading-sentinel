"""SN06 - N11's entry ingredients, rebuilt for the Rs 15,000 wallet without N11's big-money rules (research only).

SN04/SN05 showed N11's edge is its entry selection. N11's selection rests on (a) setups judged on closed 5-minute bars
(trend pullback above all), (b) the daily ADX gate, (c) trading with the daily trend. SN06 searches those ingredients
in the fast SN simulator, with N11-style exits (sn04.run_day), no stand-aside, no kill switches, no premium cap, and an
activity floor of 25% of sessions (N11 trades on ~16%). NULL = random entries behind the SAME gates and exits, so a pass
must come from the entry, not from the gate. Choose on three years, score the fourth. Wallet and costs as SN04.
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
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn04"), str(HERE.parent / "2026-11-12-sn01")]

import sn01_data as D  # noqa: E402
import sn01_search as S1  # noqa: E402
import sn01_sim as M  # noqa: E402
import sn04 as Q  # noqa: E402

YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
EVALS = LOCAL / "evals.jsonl"
DAILY = LOCAL / "daily.json"
MIN_ACTIVE = 0.25
POOL_REAL, POOL_NULL = 4000, 2000
GENS, CHILDREN, ELITE = 6, 120, 50
SEED = 20261114
GATES = ["none", "adx20:HIGH", "adx25:HIGH", "adx30:HIGH", "adx25:LOW", "adx30:LOW"]


# ---- daily ADX / DMI from the cached index minutes (yesterday's reading gates today) ----------------------------

def build_daily() -> None:
    import sqlite3
    seen = {}
    for y in YEARS:   # every index day of the sealed datasets, expiry days included
        con = sqlite3.connect(f"file:{(D.DATASETS[y] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
        for stamp, o, h, l, c in con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' "
                                             "ORDER BY datetime"):
            day = stamp[:10]
            if day not in seen:
                seen[day] = [day, o, h, l, c]
            else:
                b = seen[day]
                b[2], b[3], b[4] = max(b[2], h), min(b[3], l), c
        con.close()
    bars = [seen[d] for d in sorted(seen)]
    out, n = {}, 14
    tr_s = pdm_s = mdm_s = adx = None
    dx_hist = []
    for k in range(1, len(bars)):
        _, _, h, l, c = bars[k]
        _, _, ph, pl, pc = bars[k - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        if tr_s is None:
            tr_s, pdm_s, mdm_s = tr, pdm, mdm
        else:
            tr_s, pdm_s, mdm_s = tr_s - tr_s / n + tr, pdm_s - pdm_s / n + pdm, mdm_s - mdm_s / n + mdm
        pdi, mdi = 100 * pdm_s / tr_s, 100 * mdm_s / tr_s
        dx = 100 * abs(pdi - mdi) / max(pdi + mdi, 1e-9)
        dx_hist.append(dx)
        if len(dx_hist) == n:
            adx = sum(dx_hist) / n
        elif adx is not None:
            adx = (adx * (n - 1) + dx) / n
        # the reading after day k's close gates day k+1
        if k + 1 < len(bars) and k >= 2 * n:
            out[bars[k + 1][0]] = {"adx": round(adx, 2), "dir": 1 if pdi >= mdi else -1}
    LOCAL.mkdir(exist_ok=True)
    DAILY.write_text(json.dumps(out), encoding="utf-8")
    print("daily readings", len(out), "of", len(bars), flush=True)


_DAILY = None


def daily() -> dict:
    global _DAILY
    if _DAILY is None:
        _DAILY = json.loads(DAILY.read_text(encoding="utf-8"))
    return _DAILY


# ---- 5-minute setups ---------------------------------------------------------------------------------------------

def five_minute(S: M.Session) -> dict:
    if not hasattr(S, "_F5"):
        s = S.s
        idx, fut = np.asarray(s["index"]), np.asarray(s["future"])
        nb = idx.shape[1] // 5
        def agg(a, vol=False):
            blocks = a[:, : nb * 5].reshape(a.shape[0], nb, 5)
            out = np.vstack([blocks[0, :, 0], blocks[1].max(axis=1), blocks[2].min(axis=1), blocks[3, :, -1]])
            if vol:
                out = np.vstack([out, blocks[4].sum(axis=1)])
            return out
        s5 = {"index": agg(idx), "future": agg(fut, vol=True), "prev": s.get("prev"), "prev_days": s.get("prev_days")}
        S._F5 = M.features(s5)
    return S._F5


def signals(S: M.Session, g: dict) -> np.ndarray:
    n = len(S.F["c"])
    sig = np.zeros(n, dtype=np.int8)
    rd = daily().get(S.day)
    gate = g["gate"]
    if gate != "none":
        if rd is None:
            return sig
        thr = float(gate[3:5])
        if (rd["adx"] >= thr) != gate.endswith("HIGH"):
            return sig
    if g["tf"] == 5:
        F5 = five_minute(S)
        part = np.zeros(len(F5["c"]), dtype=np.int8)
        for fam in g["families"]:
            p = M._family(F5, fam, S.seed)
            part = np.where(part != 0, part, p).astype(np.int8)
        sig[4::5][: len(part)] = part        # a 5-minute bar is known at its last minute's close
    else:
        sig = M.signals(S.F, {"families": g["families"], "bias": "none"}, S.seed)
    if g["with_dmi"] and rd is not None:
        sig[sig == -rd["dir"]] = 0
    bias = g["bias"]
    if bias == "puts":
        sig[sig > 0] = 0
    elif bias == "calls":
        sig[sig < 0] = 0
    return sig


def random_genome(rng: random.Random, null: bool) -> dict:
    g = Q.random_genome(rng, null)
    g["bias"] = rng.choice(["none", "puts", "calls"])
    g["gate"] = rng.choice(GATES)
    g["tf"] = rng.choice([1, 5])
    g["with_dmi"] = rng.random() < 0.5
    return g


def mutate(g: dict, rng: random.Random) -> dict:
    out = Q.mutate(g, rng)
    if rng.random() < 0.3:
        out["gate"] = rng.choice(GATES)
    if rng.random() < 0.15:
        out["tf"] = 6 - out["tf"] if out["tf"] in (1, 5) else 1
    if rng.random() < 0.15:
        out["with_dmi"] = not out["with_dmi"]
    if out.get("bias") not in ("none", "puts", "calls"):
        out["bias"] = "none"
    return out


def key(g: dict) -> str:
    return hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:20]


def run_day(S, g, wallet=Q.WALLET, loss=Q.LOSS, stress=Q.STRESS, record=False):
    return Q.run_day(S, g, wallet, loss, stress, sig=signals(S, g), record=record)


# ---- search (as SN04) --------------------------------------------------------------------------------------------

_S = None


def _init(year):
    global _S
    _S = [M.Session(s) for s in D.load_year(year)["sessions"].values()]
    daily()


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
    active = all(rec["years"][y]["active"] / rec["years"][y]["sessions"] >= MIN_ACTIVE for y in train)
    return min(per) if active else -1e6 + min(per)


def main(cmd):
    LOCAL.mkdir(exist_ok=True)
    if cmd == "daily":
        build_daily()
        return
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
