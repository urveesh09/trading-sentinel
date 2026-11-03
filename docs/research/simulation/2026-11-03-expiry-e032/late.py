"""Phase 1b: E02's frozen entry in the never-scored late slice (15:00-15:15), scored once (same rules and pass test as the morning).

    python late.py freeze   writes freeze-late.json (refuses to overwrite)
    python late.py score    refuses unless the freeze is committed and every hash matches

Arms, rules and the pass test are fixed in PLAN_LATE.md and freeze-late.json before any late entry is scored.
The afternoon reproduction (seen) runs first, so a broken lab can never produce a late score.
"""
from __future__ import annotations
import hashlib, json, random, subprocess, sys
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path.insert(0, str(SIM / "2026-11-03-expiry-e031"))
import lab as L  # noqa: E402  (E03.1's lab: E03's run_day plus E03.1's mechanisms)
X, E = L.X, L.E

MORNING = dict(start=900, end=915)  # the late slice; name kept from morning.py
ARMS = {
    "L_E02": L.Candidate(**{**X.R3, **MORNING}),
    "L_E03": replace(L.BASE, **MORNING),
    "L_E031": replace(L.BASE, stop=.35, lock_arm=.5, lock_floor=1.1, **MORNING),
}
AFTERNOON_CHECK = {  # seen figures every arm must reproduce before the morning is opened
    ("E02", 2024, "ordinary"): 3514.0, ("E03", 2024, "ordinary"): 8567.0, ("E03", 2025, "ordinary"): 3389.0,
    ("E03", "both", "ordinary"): 11956.35, ("E031", "both", "ordinary"): 12426.71,
}
SCENARIOS = ("ordinary", "adverse", "catastrophe")
SEEDS = 40
FROZEN_FILES = [HERE / "late.py", HERE / "PLAN.md", HERE / "PLAN_LATE.md", HERE / "morning-results.json", SIM / "2026-11-03-expiry-e031/lab.py",
                SIM / "2026-11-03-expiry-e03/e03_lab.py", SIM / "2026-11-03-expiry-e02/e02_lab.py",
                SIM / "2026-11-03-expiry-e02/data.py"]
FREEZE = HERE / "freeze-late.json"
OUT = HERE / "late-results.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def freeze():
    assert not FREEZE.exists(), "the late freeze is written once"
    tapes = sorted(str(p.name) for p in (SIM / "2026-11-03-expiry-e02/_local").glob("tapes-*.pkl"))
    FREEZE.write_text(json.dumps(dict(
        written_before_any_late_score=True, head=git("rev-parse", "HEAD"),
        files={str(p.relative_to(REPO)).replace("\\", "/"): sha(p) for p in FROZEN_FILES},
        tapes={n: sha(SIM / "2026-11-03-expiry-e02/_local" / n) for n in tapes},
        arms={k: asdict(v) for k, v in ARMS.items()}, scenarios=SCENARIOS, random_seeds=SEEDS,
        passes="L_E03 net > 0 each year at ordinary AND adverse; ordinary net without best day > 0 each year; "
               "worst day >= -1250 in every year/scenario except severe; actual > median of the random seeds each year",
        phase2="if it passes, the main book's entry window ends at 15:15 instead of 15:00 (same two tickets, same Rs 2,500 a day)"), indent=2) + "\n", encoding="utf-8")
    print("FROZEN", FREEZE)


def verify():
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    for rel, digest in frozen["files"].items():
        assert sha(REPO / rel) == digest, f"changed after the freeze: {rel}"
    rel = str(FREEZE.relative_to(REPO)).replace("\\", "/")
    assert git("log", "-1", "--format=%H", "--", rel), "commit the freeze before scoring"
    assert not git("status", "--porcelain", "--", rel, str((HERE / "late.py").relative_to(REPO))), "freeze/script not clean"
    return frozen


def random_directions(seed):
    real = X.directions

    def directions(t, rule):
        n = int(np.count_nonzero(real(t, rule)))
        rng = random.Random(f"{seed}-{t.day}")
        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
        out = np.zeros(t.n, dtype=np.int8)
        for i in rng.sample(range(lo, hi), min(n, hi - lo)):
            out[i] = rng.choice((1, -1))
        return out
    return directions


def brief(s):
    return {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades", "profit_factor", "wins", "loss_days",
                              "quarters", "first_half", "second_half", "fees", "unresolved")}


def tickets(run):
    rows = []
    for d in run["days"]:
        for p in d["positions"]:
            rows.append(dict(day=d["day"], symbol=p["symbol"], entry_minute=int(p["entry_i"]) + 556, entry=p["entry"], lots=p["lots"],
                             peak=p["peak"], net=p["net"], exits=[(e.get("reason"), e["price"], e["lots"]) for e in p["events"][1:]]))
    return rows


def score():
    frozen = verify()
    T = L.tapes(); both = T[2024] + T[2025]
    e02 = L.Candidate(**X.R3); e031 = replace(L.BASE, stop=.35, lock_arm=.5, lock_floor=1.1)
    seen = {("E02", 2024, "ordinary"): L.run(T[2024], e02)["summary"]["net"],
            ("E03", 2024, "ordinary"): L.run(T[2024], L.BASE)["summary"]["net"],
            ("E03", 2025, "ordinary"): L.run(T[2025], L.BASE)["summary"]["net"],
            ("E03", "both", "ordinary"): L.run(both, L.BASE)["summary"]["net"],
            ("E031", "both", "ordinary"): L.run(both, e031)["summary"]["net"]}
    for key, want in AFTERNOON_CHECK.items():
        assert abs(seen[key] - want) < 1.0, (key, seen[key], want)
    print("AFTERNOON_REPRODUCED", flush=True)
    out = dict(freeze_head=frozen["head"], arms={}, random={}, tickets={}, verdict={})
    for name, rule in ARMS.items():
        for scope, tape in (("2024", T[2024]), ("2025", T[2025]), ("both", both)):
            for sc in SCENARIOS:
                r = L.run(tape, rule, sc, details=True)
                out["arms"][f"{name}|{scope}|{sc}"] = brief(r["summary"])
                if scope == "both" and sc in ("ordinary", "adverse"):
                    out["tickets"][f"{name}|{sc}"] = tickets(r)
                print(name, scope, sc, brief(r["summary"]), flush=True)
    saved = L.directions
    try:
        for y in (2024, 2025):
            nets = []
            for s in range(SEEDS):
                L.directions = random_directions(s)
                nets.append(L.run(T[y], ARMS["L_E03"])["summary"]["net"])
            L.directions = saved
            nets = np.array(nets); actual = out["arms"][f"L_E03|{y}|ordinary"]["net"]
            out["random"][str(y)] = dict(actual=actual, median=round(float(np.median(nets)), 2), mean=round(float(nets.mean()), 2),
                                         p95=round(float(np.percentile(nets, 95)), 2), share_at_or_above=float((nets >= actual).mean()))
            print("random", y, out["random"][str(y)], flush=True)
    finally:
        L.directions = saved
    a = out["arms"]
    checks = {}
    for y in ("2024", "2025"):
        checks[f"positive_ordinary_{y}"] = a[f"L_E03|{y}|ordinary"]["net"] > 0
        checks[f"positive_adverse_{y}"] = a[f"L_E03|{y}|adverse"]["net"] > 0
        checks[f"ex_best_ordinary_{y}"] = a[f"L_E03|{y}|ordinary"]["without_best"] > 0
        checks[f"worst_day_{y}"] = min(a[f"L_E03|{y}|{sc}"]["worst"] for sc in ("ordinary", "adverse")) >= -1250
        checks[f"beats_random_median_{y}"] = out["random"][y]["actual"] > out["random"][y]["median"]
    out["verdict"] = dict(checks=checks, passed=all(checks.values()))
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print("VERDICT", out["verdict"], flush=True)


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
