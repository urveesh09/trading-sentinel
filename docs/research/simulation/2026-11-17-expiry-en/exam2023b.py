"""EN07: the NIFTY 2023 E03-family exam re-scored ONCE with the coverage rule the frozen exam actually states.

The first scoring (exam2023.py -> exam2023-results.json, kept as recorded) tested strike membership over the
whole day. EXAM_E03_FAMILY.md says a decision is available only if every strike from the first OTM strike to
200 points on its side is among the downloaded legs AT THAT MINUTE. The auditor (docs/EXPIRY_RESEARCH_EN06_EN15.md)
also found the unavailable counters pooled across arms and sides, and the random control drawing minutes and
sides outside the available set. This file fixes only those three things:

  available_at(t, i, d)   every required strike has a valid bar at minute i (no bar = unavailable)
  counters                per arm, per day, per side
  random control          (minute, side) drawn only from the available pairs in the 13:00-15:00 window

Arms, labs, fills, brakes and tests 1-8 are unchanged (imported from exam2023.py). No candidate rule changes
after viewing 2023. check() validates on SEEN 2024 and on a synthetic hole; score() runs once, under a hashed
freeze of every imported file, the data binding and the owner's word, with a start receipt and a completion
receipt."""
from __future__ import annotations
import hashlib, json, math, random, statistics as st, sys, time as _time
from dataclasses import replace
from pathlib import Path
import numpy as np
import exam2023 as A

HERE = A.HERE
N, R, L, X, E, D = A.N, A.R, A.L, A.X, A.E, A.D
SIM = HERE.parent
HASHED = {
    "exam2023b.py": HERE / "exam2023b.py", "exam2023.py": HERE / "exam2023.py", "en_lab.py": HERE / "en_lab.py",
    "en_base.py": HERE / "en_base.py", "OWNER_WORD.md": HERE / "OWNER_WORD.md", "EXAM_EN_ADDENDUM.md": HERE / "EXAM_EN_ADDENDUM.md",
    "r8b_lab.py": SIM / "2026-11-03-expiry-round8/r8b_lab.py", "e031_lab.py": SIM / "2026-11-03-expiry-e031/lab.py",
    "e03_lab.py": SIM / "2026-11-03-expiry-e03/e03_lab.py", "e02_lab.py": SIM / "2026-11-03-expiry-e02/e02_lab.py",
    "data.py": SIM / "2026-11-03-expiry-e02/data.py", "riskdial.py": SIM / "2026-11-03-expiry-auction/riskdial.py",
    "expiry_paper.py": A.HERE.parents[3] / "python-engine/expiry_paper.py",
    "cost_schedules.py": A.HERE.parents[3] / "python-engine/cost_schedules.py",
    "data-binding.json": A.BINDING,
}
RESULTS = HERE / "exam2023b-results.json"
START = HERE / "exam2023b-started.json"
ARM = {"name": None}
UNAV = {}          # (arm, day, side) -> minutes refused
ORIGINAL = A.ORIGINAL


def required(t, i, d):
    c = float(t.close[i])
    first = math.floor(c / 50) * 50 + 50 if d > 0 else math.ceil(c / 50) * 50 - 50
    return [first + d * 50 * n for n in range(5) if 0 < d * (first + d * 50 * n - c) <= 200]


def available_at(t, i, d):
    cols = {(float(k), int(kind)): j for j, (k, kind) in enumerate(zip(t.strikes, t.kinds))}
    for k in required(t, i, d):
        j = cols.get((float(k), d))
        if j is None or not np.isfinite(t.q[i, j, :4]).all():
            return False
    return True


def masked(t, rule):
    out = ORIGINAL(t, rule).copy()
    for i in np.flatnonzero(out):
        d = int(out[i])
        if not available_at(t, int(i), d):
            UNAV.setdefault((ARM["name"], t.day, "C" if d > 0 else "P"), set()).add(int(i)); out[i] = 0
    return out


def random_directions(seed):
    def directions(t, rule):
        real = masked(t, rule)
        rng = random.Random(f"{seed}-{t.day}")
        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
        pool = [(i, d) for i in range(lo, hi) for d in (1, -1) if np.isfinite(t.close[i]) and available_at(t, i, d)]
        out = np.zeros(t.n, dtype=np.int8)
        for i, d in rng.sample(pool, min(len(pool), int(np.count_nonzero(real)))):
            out[i] = d
        return out
    return directions


def run(name, kind, tapes, rule, sc, details=False):
    ARM["name"] = name
    return A.run(kind, tapes, rule, sc, details)


def evaluate(T):
    res = dict(arms={}, tickets={})
    for name, (kind, rule) in A.arms().items():
        row = {}
        for sc in A.SC:
            r = run(name, kind, T, rule, sc, details=(sc == "ordinary"))
            row[sc] = A.brief(r["summary"])
            if sc == "ordinary":
                res["tickets"][name] = [dict(day=p["day"], side="P" if p["direction"] < 0 else "C", lots=p["lots"], entry=p["entry"], net=p["net"],
                                             exits=[e.get("reason") for e in p["events"][1:]]) for d in r["days"] for p in d["positions"]]
            if sc == "adverse":
                row["skeptical"] = A.RD.bootstrap(A.RD.skeptical([d["net"] for d in r["days"]]), random.Random(A.RD.SEED))
        res["arms"][name] = row
        print(name, {sc: (row[sc]["net"], row[sc]["trades"]) for sc in A.SC}, flush=True)
    nets = []
    try:
        for s in range(A.SEEDS):
            E.directions = random_directions(s)
            nets.append(run("E031_random", "r", T, R.E031, "ordinary")["summary"]["net"])
    finally:
        E.directions = masked
    res["random_E031"] = dict(seeds=A.SEEDS, median=round(st.median(nets), 2), mean=round(st.mean(nets), 2),
                              share_at_or_above=round(sum(n >= res["arms"]["E031"]["ordinary"]["net"] for n in nets) / A.SEEDS, 3))
    res["unavailable"] = {f"{a}|{d}|{s}": len(v) for (a, d, s), v in sorted(UNAV.items(), key=lambda kv: str(kv[0])) if a != "E031_random"}
    return res


def tests(res):
    a = res["arms"]; o, v, sv = "ordinary", "adverse", "catastrophe"; t = {}
    t["1_E031_stands"] = dict(ordinary=a["E031"][o]["net"] > 0, adverse=a["E031"][v]["net"] > 0, without_best=a["E031"][o]["without_best"] > 0,
                              worst=a["E031"][o]["worst"] >= -1250, above_random_median=a["E031"][o]["net"] > res["random_E031"]["median"])
    t["2_E031_vs_E03"] = dict(ordinary=a["E031"][o]["net"] >= a["E03"][o]["net"], adverse=a["E031"][v]["net"] >= a["E03"][v]["net"])
    t["3_L8_vs_E031"] = dict(severe_better=a["E031_L8"][sv]["net"] > a["E031"][sv]["net"], ordinary=a["E031_L8"][o]["net"] >= a["E031"][o]["net"],
                             adverse=a["E031_L8"][v]["net"] >= a["E031"][v]["net"])
    t["5_E032_vs_E031"] = dict(ordinary=a["E032"][o]["net"] > a["E031"][o]["net"], adverse=a["E032"][v]["net"] > a["E031"][v]["net"],
                               without_best=a["E032"][o]["without_best"] > a["E031"][o]["without_best"], worst=a["E032"][o]["worst"] >= 2 * a["E031"][o]["worst"])
    pe = [x["net"] for x in res["tickets"]["E031"] if x["side"] == "P"]; ce = [x["net"] for x in res["tickets"]["E031"] if x["side"] == "C"]
    t["6_asymmetry"] = dict(puts_per_ticket=round(st.mean(pe), 2) if pe else None, calls_per_ticket=round(st.mean(ce), 2) if ce else None,
                            holds=bool(pe and ce and st.mean(pe) > st.mean(ce)))
    t["7_E032_stands"] = dict(ordinary=a["E032"][o]["net"] > 0, adverse=a["E032"][v]["net"] > 0, without_best=a["E032"][o]["without_best"] > 0,
                              worst=a["E032"][o]["worst"] >= -2500)
    p3 = a["EN04_put3x"]; sk = p3["skeptical"]
    t["8_PUT3"] = dict(ordinary=p3[o]["net"] >= a["E032"][o]["net"], adverse=p3[v]["net"] >= a["E032"][v]["net"],
                       without_best=p3[o]["without_best"] >= a["E032"][o]["without_best"], loss_year=sk["loss_year_chance"] <= .30,
                       drawdown=sk["drawdown_p95"] <= 5000, severe=p3[sv]["net"] >= -6250,
                       neighbours_positive=all(a[k][s]["net"] > 0 for k in ("EN04_put2.5x", "EN04_put3.5x") for s in (o, v)))
    return {k: dict(x, passed=all(y for y in x.values() if isinstance(y, bool))) for k, x in t.items()}


def check():
    """SEEN 2024: a synthetic hole is refused; every arm runs; per-arm/side counters and the matched pool work."""
    T, _ = A.build_tapes(2024)
    t, i, d = next((x, int(i), int(ORIGINAL(x, N.E032)[i])) for x in T for i in np.flatnonzero(ORIGINAL(x, N.E032))
                   if available_at(x, int(i), int(ORIGINAL(x, N.E032)[i])))
    k = required(t, i, d)[-1]; j = next(j for j, (s, kind) in enumerate(zip(t.strikes, t.kinds)) if float(s) == k and kind == d)
    saved = t.q[i, j].copy(); t.q[i, j] = np.nan
    assert not available_at(t, i, d), "a missing bar at the decision minute must be unavailable"
    t.q[i, j] = saved; assert available_at(t, i, d)
    E.directions = masked
    try:
        out = {name: run(name, kind, T, rule, "ordinary")["summary"]["net"] for name, (kind, rule) in A.arms().items()}
        E.directions = random_directions(0)
        rnd = run("E031_random", "r", T, R.E031, "ordinary")["summary"]["net"]
    finally:
        E.directions = ORIGINAL
    by = {}
    for (a, dd, s), v in UNAV.items():
        by.setdefault(a, 0); by[a] += len(v)
    print("CHECK_OK synthetic hole refused; 2024 under the minute rule:", out, "random seed 0:", rnd, "unavailable per arm:", by)


def freeze():
    assert not RESULTS.exists() and not START.exists()
    (HERE / "freeze-examb.json").write_text(json.dumps(dict(files={k: A.sha(p) for k, p in HASHED.items()}, head=A.git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", len(HASHED), "files")


def score():
    fz = json.loads((HERE / "freeze-examb.json").read_text())
    assert set(fz["files"]) == set(HASHED) and all(A.sha(HASHED[k]) == h for k, h in fz["files"].items()), "frozen files changed"
    assert not A.git("status", "--porcelain", "--", "exam2023b.py", "freeze-examb.json"), "freeze not committed"
    assert not RESULTS.exists() and not START.exists(), "scored once"
    assert A.sha(A.SEALED) == json.loads(A.BINDING.read_text())["files_sha256"]["data.sqlite"]
    run_id = hashlib.sha256((HERE / "freeze-examb.json").read_bytes()).hexdigest()[:16]
    with START.open("x") as f:
        json.dump(dict(run_id=run_id, started=_time.strftime("%Y-%m-%dT%H:%M:%S"), head=A.git("rev-parse", "HEAD")), f)
    E.directions = masked
    try:
        T, coverage = A.tapes2023()
        res = evaluate(T); res.update(run_id=run_id, freeze=fz, coverage=coverage, tests=tests(res))
    finally:
        E.directions = ORIGINAL
    first = json.loads((HERE / "exam2023-results.json").read_text())
    res["vs_first_scoring"] = {k: dict(first=first["arms"][k]["ordinary"]["net"], corrected=res["arms"][k]["ordinary"]["net"]) for k in res["arms"]}
    res["tests_first"] = {k: v["passed"] for k, v in first["tests"].items()}
    res["completed"] = _time.strftime("%Y-%m-%dT%H:%M:%S")
    with RESULTS.open("x", encoding="utf-8") as f:
        json.dump(res, f, indent=2, default=str)
    print("TESTS", json.dumps({k: v["passed"] for k, v in res["tests"].items()}), "FIRST", json.dumps(res["tests_first"]))


if __name__ == "__main__":
    {"check": check, "freeze": freeze, "score": score}[sys.argv[1]]()
