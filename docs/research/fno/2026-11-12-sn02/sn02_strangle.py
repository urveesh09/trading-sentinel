"""SN02-B: long strangle / straddle - buy both sides, profit from the size of the move, not its direction (research only).
Descriptive grid over all four seen years first; a family that loses in-sample everywhere is dead without a test."""
import json, math, sys, itertools
import numpy as np
import sn02_ext as X
M = X.M

def leg(S, strike, opt, i):
    rec = S.option(strike, opt)
    if rec is None or not rec[6][i]:
        return None
    return rec, M.ask_of(float(rec[0][3][i]))

def play(S, m, off, tgt, stp, hold, stress, gate):
    F = S.F
    if gate == "narrow" and not F.get("narrow", False): return None
    if gate == "wide" and F.get("narrow", True): return None
    c = F["c"][m]; atm = int(round(c / 50) * 50)
    legs = [leg(S, atm + off * 50, "CE", m), leg(S, atm - off * 50, "PE", m)]
    if any(l is None for l in legs): return None
    cost = sum(a for _, a in legs) * 65
    if cost > 15000: return None
    ent = [a for _, a in legs]
    fixed = sum(M.charges(a, a, 65) for a in ent) + 2 * stress
    for j in range(m + 1, M.EXIT_MIN + 1):
        vals = []
        for (rec, a) in legs:
            vals.append(rec[4][j] if rec[6][j] else rec[5][j])   # close bid (or carried mark)
        pnl = sum((v - a) * 65 for v, a in zip(vals, ent)) - fixed
        if pnl >= tgt or pnl <= -stp or j - m >= hold or j == M.EXIT_MIN:
            return pnl
    return None

def narrow_flags(sessions):
    for S in sessions:
        pd = S.s.get("prev_days") or []
        if len(pd) >= 21:
            rng = [d[1] - d[2] for d in pd]
            S.F["narrow"] = rng[-1] < np.median(rng[-21:-1])

GRID = list(itertools.product((5, 15, 45, 90), (0, 1, 2), (750, 1500, 3000), (1500, 3000), (30, 90, 360), ("all", "narrow", "wide")))

if __name__ == "__main__":
    stress = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    res = {}
    for y in X.YEARS:
        Y = X.Year(y); ss = Y.ordered(); narrow_flags(ss)
        for g in GRID:
            vals = [p for S in ss if (p := play(S, *g[:5], stress, g[5])) is not None]
            res.setdefault(str(g), {})[y] = (round(sum(vals)), len(vals))
    tot = sorted(res.items(), key=lambda kv: -sum(v[0] for v in kv[1].values()))
    pos_all = sum(1 for k, v in res.items() if all(v[y][0] > 0 for y in X.YEARS))
    print("stress", stress, "combos", len(res), "positive in every year:", pos_all)
    for k, v in tot[:8]:
        print(k, v, sum(x[0] for x in v.values()))
    med = np.median([sum(x[0] for x in v.values()) for v in res.values()])
    print("median combo 4-year", round(med))
    (X.HERE / "_local").mkdir(exist_ok=True)
    (X.HERE / "_local" / f"strangle-{int(stress)}.json").write_text(json.dumps(res), encoding="utf-8")
