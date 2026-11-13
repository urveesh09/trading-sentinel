"""SN119 - is Gold's edge real after all the selection? (PLAN.md) Gold v5's whole machinery fed random entries:
N1 = Gold's own signal days and counts, random minute (09:30-14:00) and side, ATM strike, the real signal's holding
time; N2 = the same count per year on random sessions of that year, random minute / side / real holding time.
200 draws each; v5's percentile at Rs 15k, Rs 30k sized, growing from Rs 15k (stop 3) and Rs 30k growing (stop 3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pc  # noqa: E402

C, M, L = pc.C, pc.M, pc.L
WALLETS = (("A 15k 1 lot", 15000.0, "one", None), ("C 30k sized", 30000.0, "sized", None),
           ("G3 (Gold)", 15000.0, "grow", 3), ("30k grow stop 3", 30000.0, "grow", 3))
DRAWS = 200
_orig = L.sig_of


def sig_of_null(Y, day, v):
    if "null_sigs" in v:
        return v["null_sigs"].get(day, [])
    return _orig(Y, day, v)


def real_signals():
    Ys = C.years()
    out = {}
    for y in C.YEARS:
        Y = Ys[y]
        for S in Y.ordered():
            sg = _orig(Y, S.day, C.V5)
            if sg:
                out[S.day] = sg
    return out


def make(S, i, d, hold, n, tag):
    c = S.F["c"]
    return {"day": S.day, "i": int(i), "j": int(min(i + hold, 355)), "strike": int(round(c[i] / M.STEP) * M.STEP),
            "opt": "CE" if d > 0 else "PE", "expiry": S.s["expiry"], "reason": "null", "expert": "NULL", "gate": "",
            "book": "NULL", "sig_key": (f"{S.day}|{tag}|{n}", 0, d > 0)}


def null1(real, rng):
    Ys = C.years()
    out = {}
    for day, sgs in real.items():
        S = Ys[day[:4]].sessions[day]
        out[day] = [make(S, rng.integers(15, 286), 1 if rng.random() < 0.5 else -1, max(1, s["j"] - s["i"]), k, "n1")
                    for k, s in enumerate(sgs)]
    return out


def null2(real, rng):
    Ys = C.years()
    holds = [max(1, s["j"] - s["i"]) for sgs in real.values() for s in sgs]
    out = {}
    for y in C.YEARS:
        n = sum(len(sgs) for d, sgs in real.items() if d[:4] == y)
        days = [S.day for S in Ys[y].ordered()]
        for k in range(n):
            d = days[rng.integers(len(days))]
            S = Ys[y].sessions[d]
            out.setdefault(d, []).append(make(S, rng.integers(15, 286), 1 if rng.random() < 0.5 else -1, holds[rng.integers(len(holds))], k, "n2"))
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn119.json"
    if out_path.exists():
        raise SystemExit("SN119 is scored once")
    C.years()
    L.sig_of = sig_of_null
    real = real_signals()
    base = C.totals(C.run(C.V5, WALLETS))
    print("Gold v5", base, "| real signal days", len(real), "signals", sum(len(v) for v in real.values()), flush=True)
    res = {"v5": base, "nulls": {}}
    for name, fn, seed in (("N1 own days, random minute and side", null1, 1191), ("N2 random days, minute and side", null2, 1192)):
        rng = np.random.default_rng(seed)
        dist = {w[0]: [] for w in WALLETS}
        for k in range(DRAWS):
            t = C.totals(C.run({**C.V5, "null_sigs": fn(real, rng)}, WALLETS))
            for w in dist:
                dist[w].append(t[w])
            if (k + 1) % 50 == 0:
                print(f"   {name}: {k + 1} draws", flush=True)
        summ = {w: {"null_mean": round(float(np.mean(v))), "null_95th": round(float(np.percentile(v, 95))),
                    "null_max": round(float(np.max(v))), "v5": base[w], "v5_percentile": round(float(np.mean(np.array(v) < base[w])) * 100, 1)}
                for w, v in dist.items()}
        res["nulls"][name] = {"summary": summ, "draws": dist}
        print(f"=== {name}", json.dumps(summ), flush=True)
    s1, s2 = (res["nulls"][k]["summary"] for k in res["nulls"])
    res["reading"] = {w: ("entries are genuine edge" if base[w] > s1[w]["null_95th"] and base[w] > s2[w]["null_95th"]
                          else "day selection only" if base[w] > s2[w]["null_95th"] else "money management, not entries")
                      for w in base}
    print("READING", res["reading"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
