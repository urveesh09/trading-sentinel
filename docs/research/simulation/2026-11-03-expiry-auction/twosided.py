"""TWOSIDED_PLAN.md: the seller only on quiet afternoons, scored on a strict plateau. Research only.

    python twosided.py freeze    writes freeze-twosided.json once
    python twosided.py score     refuses unless the freeze is committed and every hash matches -> twosided-results.json
"""
from __future__ import annotations
import hashlib, json, statistics as st, subprocess, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "python-engine").is_dir())
import seller as S  # noqa: E402
LAB = S.LAB
from dataclasses import replace  # noqa: E402
E031 = replace(LAB.BASE, stop=.35, lock_arm=.5, lock_floor=1.1)
TIMES, WINGS, STOPS = (810, 825, 840, 855, 870), (2, 4), (1., None)
CENTRAL = dict(T=840, steps=4, stop=1.)
FREEZE, OUT = HERE / "freeze-twosided.json", HERE / "twosided-results.json"


def quiet(t, T, how, cache):
    """Is the afternoon quiet at decision time T? Reads completed bars up to the decision only."""
    i = int(np.searchsorted(t.minute, T))
    if how == "NOSIG":
        if id(t) not in cache:
            cache[id(t)] = LAB.directions(t, E031)
        lo = int(np.searchsorted(t.minute, 780))
        return not np.any(cache[id(t)][lo:i + 1])
    er = t.features[30][i, 2]
    return bool(np.isfinite(er) and abs(er) < .3)


def arms():
    return [dict(T=T, steps=w, stop=s) for T in TIMES for w in WINGS for s in STOPS]


def score_family(T_, how, cache):
    out = {}
    for a in arms():
        nm = S.name(a); row = {}
        for y in (2024, 2025):
            for sc in ("ordinary", "adverse", "catastrophe"):
                days = [(t, S.chain_day(t, a, sc)) for t in T_[y]]
                q = [r for t, r in days if quiet(t, a["T"], how, cache)]
                c = [r for t, r in days if not quiet(t, a["T"], how, cache)]
                row[f"{y}|{sc}|quiet"] = S.summarize(q)
                row[f"{y}|{sc}|trend"] = S.summarize(c)
                row[f"{y}|{sc}|all"] = S.summarize([r for _, r in days])
        out[nm] = row
    return out


def verdict(fam):
    pos = sum(all(fam[n][f"{y}|{sc}|quiet"].get("net", 0) > 0 for y in (2024, 2025) for sc in ("ordinary", "adverse")) for n in fam)
    beats = sum(all(fam[n][f"{y}|ordinary|quiet"].get("net", 0) > fam[n][f"{y}|ordinary|all"].get("net", 0) for y in (2024, 2025)) for n in fam)
    c = fam[S.name(CENTRAL)]
    central = all(c[f"{y}|ordinary|quiet"].get("without_best", 0) > 0 for y in (2024, 2025))
    trend_loses = all(sum(fam[n][f"{y}|ordinary|trend"].get("net", 0) for n in fam) < 0 for y in (2024, 2025))
    return dict(positive_arms=pos, beats_unconditional=beats, central_ex_best=central, trend_side_loses=trend_loses,
                passed=bool(pos >= 16 and beats >= 16 and central and trend_loses))


def combined(T_, how, cache):
    """E03.1's continuous book plus the central quiet-day seller, day by day (simple sum; no shared brakes)."""
    out = {}
    for sc in ("ordinary", "adverse", "catastrophe"):
        both = T_[2024] + T_[2025]
        e = LAB.run(both, E031, sc)["days"]
        s = [S.chain_day(t, CENTRAL, sc)["net"] if quiet(t, CENTRAL["T"], how, cache) else 0. for t in both]
        a = [d["net"] for d in e]; c = [x + y for x, y in zip(a, s)]
        def dd(v):
            cur = peak = m = 0.
            for x in v:
                cur += x; peak = max(peak, cur); m = max(m, peak - cur)
            return round(m, 2)
        traded = [(x, y) for x, y in zip(a, s) if x or y]
        corr = float(np.corrcoef([x for x, _ in traded], [y for _, y in traded])[0, 1]) if len(traded) > 2 else None
        out[sc] = dict(e031=round(sum(a), 2), seller=round(sum(s), 2), combined=round(sum(c), 2), worst_day=round(min(c), 2),
                       drawdown=dd(c), e031_drawdown=dd(a), seller_drawdown=dd(s), day_correlation=round(corr, 3) if corr is not None else None,
                       positive_days=sum(x > 0 for x in c), negative_days=sum(x < 0 for x in c))
    return out


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*x):
    return subprocess.run(["git", *x], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


FILES = [HERE / "twosided.py", HERE / "TWOSIDED_PLAN.md", *S.FILES]


def freeze():
    assert not FREEZE.exists()
    FREEZE.write_text(json.dumps(dict(head=git("rev-parse", "HEAD"), written_before_scoring=True, arms=[S.name(a) for a in arms()],
                                      files={str(p): sha(p) for p in FILES}), indent=2) + "\n", encoding="utf-8")
    print("FROZEN")


def score():
    fz = json.loads(FREEZE.read_text(encoding="utf-8"))
    for p, d in fz["files"].items():
        assert sha(p) == d, p
    rel = str(FREEZE.relative_to(REPO)).replace("\\", "/")
    assert git("log", "-1", "--format=%H", "--", rel) and not git("status", "--porcelain", "--", rel)
    T_ = LAB.tapes(); cache = {}; out = dict(freeze_head=fz["head"], families={}, verdict={}, combined={})
    for how in ("NOSIG", "LOWEFF"):
        fam = score_family(T_, how, cache)
        out["families"][how] = fam; out["verdict"][how] = verdict(fam)
        out["combined"][how] = combined(T_, how, cache)
        print(how, out["verdict"][how], flush=True)
        for n, r in fam.items():
            print("  ", n, {y: (r[f"{y}|ordinary|quiet"].get("net"), r[f"{y}|adverse|quiet"].get("net"), r[f"{y}|ordinary|trend"].get("net"),
                                r[f"{y}|ordinary|quiet"].get("traded")) for y in (2024, 2025)}, flush=True)
        print("  combined", out["combined"][how], flush=True)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
