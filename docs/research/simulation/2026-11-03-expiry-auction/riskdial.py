"""RISK_PLAN.md: E03.1 at size k on the same Rs 25,000, exact replays plus a skeptical year bootstrap.

    python riskdial.py freeze    writes freeze-riskdial.json once
    python riskdial.py score     refuses unless the freeze is committed and every hash matches -> riskdial-results.json
"""
from __future__ import annotations
import hashlib, json, math, random, statistics as st, subprocess, sys
from dataclasses import replace
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "python-engine").is_dir())
import seller as S  # noqa: E402  (for LAB and the frozen file list)
LAB = S.LAB; E = LAB.E
E031 = replace(LAB.BASE, stop=.35, lock_arm=.5, lock_floor=1.1)
KS = (1., 1.5, 2., 2.5, 3., 4.)
CASH, YEARS, BLOCK, SEED = 25000., 20000, 4, 20261103
FREEZE, OUT = HERE / "freeze-riskdial.json", HERE / "riskdial-results.json"


def replay(tapes, k, scenario):
    rule = replace(E031, max_lots=int(round(3 * k)))
    cash = peak = CASH; days = []
    saved = E.BUDGET
    try:
        E.BUDGET = 2500. * k
        for t in tapes:
            dd = peak - cash
            scale = 0. if dd >= 4000 * k else .25 if dd >= 3000 * k else .5 if dd >= 1500 * k else 1.
            row = LAB.run_day(t, rule, scenario, cash, min(E.BUDGET * scale, cash))
            cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
            row.update(cash_after=cash, scale=scale); days.append(row)
    finally:
        E.BUDGET = saved
    return days


def drawdown(v):
    cur = peak = m = 0.
    for x in v:
        cur += x; peak = max(peak, cur); m = max(m, peak - cur)
    return m


def skeptical(nets):
    v = list(nets); v.remove(max(v)); mu = st.mean(v)
    return [x - .5 * mu for x in v]


def bootstrap(series, rng):
    n = len(series); starts = list(range(n - BLOCK + 1))
    finals, dds, logs = [], [], []
    for _ in range(YEARS):
        year = []
        while len(year) < 52:
            s0 = rng.choice(starts); year.extend(series[s0:s0 + BLOCK])
        year = year[:52]; total = sum(year)
        finals.append(total); dds.append(drawdown(year))
        logs.append(math.log(max(1e-9, (CASH + total) / CASH)))
    finals.sort(); dds.sort()
    return dict(loss_year_chance=round(sum(x < 0 for x in finals) / YEARS, 4), year_p5=round(finals[int(.05 * YEARS)], 2),
                year_median=round(finals[YEARS // 2], 2), drawdown_p95=round(dds[int(.95 * YEARS)], 2),
                median_log_growth=round(sorted(logs)[YEARS // 2], 5))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*x):
    return subprocess.run(["git", *x], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


FILES = [HERE / "riskdial.py", HERE / "RISK_PLAN.md", *S.FILES]


def freeze():
    assert not FREEZE.exists()
    FREEZE.write_text(json.dumps(dict(head=git("rev-parse", "HEAD"), written_before_scoring=True, ks=KS, years=YEARS, block=BLOCK, seed=SEED,
                                      files={str(p): sha(p) for p in FILES}), indent=2) + "\n", encoding="utf-8")
    print("FROZEN")


def score():
    fz = json.loads(FREEZE.read_text(encoding="utf-8"))
    for p, d in fz["files"].items():
        assert sha(p) == d, p
    rel = str(FREEZE.relative_to(REPO)).replace("\\", "/")
    assert git("log", "-1", "--format=%H", "--", rel) and not git("status", "--porcelain", "--", rel)
    T = LAB.tapes(); both = T[2024] + T[2025]; out = dict(freeze_head=fz["head"], sizes={})
    base = replay(both, 1., "ordinary"); assert abs(sum(d["net"] for d in base) - 12426.71) < .01, "E03.1 must reproduce at k=1"
    for k in KS:
        row = {}
        for sc in ("ordinary", "adverse", "catastrophe"):
            days = replay(both, k, sc); nets = [d["net"] for d in days]
            row[sc] = dict(net=round(sum(nets), 2), worst_day=round(min(nets), 2), drawdown=round(drawdown(nets), 2),
                           tickets=sum(d["trades"] for d in days), braked_days=sum(d["scale"] < 1 for d in days),
                           year_2024=round(sum(n for d, n in zip(days, nets) if d["day"] < "2025"), 2),
                           year_2025=round(sum(n for d, n in zip(days, nets) if d["day"] >= "2025"), 2))
            if sc == "adverse":
                row["skeptical"] = bootstrap(skeptical(nets), random.Random(SEED))
                row["plain_adverse"] = bootstrap(nets, random.Random(SEED))
        o = row["ordinary"]
        row["per_rupee"] = dict(net_per_worst_day=round(o["net"] / -o["worst_day"], 2) if o["worst_day"] < 0 else None,
                                net_per_drawdown=round(o["net"] / o["drawdown"], 2) if o["drawdown"] else None)
        row["passes"] = dict(loss_year=row["skeptical"]["loss_year_chance"] <= .30, drawdown=row["skeptical"]["drawdown_p95"] <= 5000,
                             severe=row["catastrophe"]["net"] >= -6250)
        out["sizes"][str(k)] = row
        print(k, json.dumps(dict(o=o, a=row["adverse"]["net"], sev=row["catastrophe"]["net"], skeptical=row["skeptical"],
                                 per_rupee=row["per_rupee"], passes=row["passes"])), flush=True)
    ok = [k for k in KS if all(out["sizes"][str(k)]["passes"].values())]
    out["recommended_k"] = max(ok) if ok else 1.
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("RECOMMENDED", out["recommended_k"])


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
