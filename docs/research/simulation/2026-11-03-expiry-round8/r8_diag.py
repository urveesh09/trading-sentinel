"""Post-score robustness of the put/call asymmetry (IN-SAMPLE diagnostics, never a pass), -> diagnostics.json.

  hero        which side the best day's ticket was, and every arm without its best day per year
  quarters    E03.1's call and put tickets by quarter
  variants    the same side split for E02 (one lot, four-strike) and E03
  random      40 random-entry seeds (signal-count per day kept, minute and side drawn): calls against puts
  flipped     E03.1's signal minutes with the side reversed: calls against puts
  flat        PUT2 and E03.1 selling everything at 15:14 instead of 15:28 (the closing-auction question)
r8b_lab.py is generated from r8_lab.py (the frozen lab) with one added field, `flat`.
"""
from __future__ import annotations
import json, random, statistics as st
from dataclasses import replace
from pathlib import Path
import numpy as np
import r8b_lab as R

HERE = Path(__file__).resolve().parent
L = R.L


def sides(days):
    ps = [p for d in days for p in d["positions"]]
    return {s: dict(tickets=len([p for p in ps if p["direction"] == g]), net=round(sum(p["net"] for p in ps if p["direction"] == g), 2))
            for s, g in (("CE", 1), ("PE", -1))}


def main():
    T = L.tapes(); both = T[2024] + T[2025]; out = {}
    base = R.Rule(**{**R.asdict(R.E031)})
    arms = {"E031": base, "PUT2": replace(base, put_mult=2.), "PE_ONLY": replace(base, call_mult=0.), "PE2_ONLY": replace(base, put_mult=2., call_mult=0.)}
    r = R.run(both, base, details=True)
    best = max(r["days"], key=lambda d: d["net"])
    out["hero"] = dict(day=best["day"], net=best["net"], sides=[("CE" if p["direction"] == 1 else "PE", p["symbol"], p["net"]) for p in best["positions"]])
    out["arms"] = {}
    for n, rule in arms.items():
        row = {}
        for y in (2024, 2025):
            for sc in ("ordinary", "adverse", "catastrophe"):
                s = R.run(T[y], rule, sc)["summary"]; row[f"{y}|{sc}"] = dict(net=s["net"], without_best=s["without_best"], worst=s["worst"], drawdown=s["drawdown"])
        s = R.run(both, rule)["summary"]; row["both|ordinary"] = dict(net=s["net"], without_best=s["without_best"], worst=s["worst"], drawdown=s["drawdown"])
        out["arms"][n] = row
    q = {}
    for d in r["days"]:
        for p in d["positions"]:
            k = f"{d['day'][:4]}Q{(int(d['day'][5:7]) - 1) // 3 + 1}|{'CE' if p['direction'] == 1 else 'PE'}"
            q.setdefault(k, []).append(p["net"])
    out["quarters"] = {k: dict(tickets=len(v), net=round(sum(v), 2)) for k, v in sorted(q.items())}
    e02 = R.Rule(**{**R.asdict(R.E031), "stop": .4, "lock_arm": 0., "lock_floor": 1., "max_lots": 1, "split": False})
    e03 = R.Rule(**R.asdict(L.BASE))
    out["variants"] = {n: {y: sides(R.run(T[y], rule, details=True)["days"]) for y in (2024, 2025)} for n, rule in (("E02", e02), ("E03", e03))}
    real = L.directions
    try:
        for label, maker in (("random", None), ("flipped", None)):
            res = {}
            for y in (2024, 2025):
                ce, pe = [], []
                for seed in range(40 if label == "random" else 1):
                    def fn(t, rule, seed=seed):
                        d = real(t, rule)
                        if label == "flipped":
                            return -d
                        rng = random.Random(f"{seed}-{t.day}"); n = int(np.count_nonzero(d))
                        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
                        o = np.zeros(t.n, dtype=np.int8)
                        for i in rng.sample(range(lo, hi), min(n, hi - lo)):
                            o[i] = rng.choice((1, -1))
                        return o
                    L.directions = fn
                    s = sides(R.run(T[y], base, details=True)["days"]); ce.append(s["CE"]["net"]); pe.append(s["PE"]["net"])
                L.directions = real
                res[str(y)] = dict(CE_mean=round(st.mean(ce), 2), PE_mean=round(st.mean(pe), 2),
                                   PE_beats_CE_share=round(sum(p > c for p, c in zip(pe, ce)) / len(ce), 3))
            out[label] = res
    finally:
        L.directions = real
    out["flat"] = {}
    for n, rule in (("E031", base), ("PUT2", replace(base, put_mult=2.))):
        for fl in (928, 914):
            out["flat"][f"{n}|{fl}"] = {f"{y}|{sc}": R.run(T[y], replace(rule, flat=fl), sc)["summary"]["net"] for y in (2024, 2025) for sc in ("ordinary", "adverse")}
    (HERE / "diagnostics.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1)[:6000])


if __name__ == "__main__":
    main()
