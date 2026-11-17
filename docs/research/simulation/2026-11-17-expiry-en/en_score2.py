"""EN08-EN10 scorer: PLAN2.md's frozen rules, applied mechanically -> results2.json (once).
`freeze` hashes the plan, labs and scorer; `score` refuses unless the freeze is committed and unchanged."""
from __future__ import annotations
import hashlib, json, random, statistics as st, subprocess, sys
from dataclasses import replace
from pathlib import Path
import numpy as np
import en_lab2 as M
import exam2023b as C

HERE = Path(__file__).resolve().parent
FILES = ("PLAN2.md", "en_lab2.py", "en_score2.py", "en_lab.py", "en_base.py", "exam2023b.py", "exam2023.py")
SC = ("ordinary", "adverse", "catastrophe"); YEARS = (2023, 2024, 2025)
E = M.E


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def freeze():
    assert not (HERE / "results2.json").exists()
    (HERE / "freeze2.json").write_text(json.dumps(dict(files={f: sha(HERE / f) for f in FILES}, head=git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


def measure(rule, T, details=True):
    out = {}
    for y in YEARS:
        for sc in SC:
            r = M.run(T[y], rule, sc, details=details and sc == "ordinary")
            s = r["summary"]; out[f"{y}|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades")}
            if details and sc == "ordinary":
                out[f"{y}|tickets"] = [dict(day=p["day"], side="P" if p["direction"] < 0 else "C", lots=p["lots"], entry=p["entry"], net=p["net"],
                                            origin=p.get("origin"), exits=[e["reason"] for e in p["events"][1:]]) for d in r["days"] for p in d["positions"]]
    return out


def robust(a, c):
    ch = {}
    for y in YEARS:
        ch[f"{y}_ordinary"] = a[f"{y}|ordinary"]["net"] >= c[f"{y}|ordinary"]["net"]
        ch[f"{y}_adverse"] = a[f"{y}|adverse"]["net"] >= c[f"{y}|adverse"]["net"]
        ch[f"{y}_without_best"] = a[f"{y}|ordinary"]["without_best"] >= c[f"{y}|ordinary"]["without_best"]
    ch["severe_sum"] = sum(a[f"{y}|catastrophe"]["net"] for y in YEARS) >= sum(c[f"{y}|catastrophe"]["net"] for y in YEARS) - 1000
    ch["worst_day"] = min(a[f"{y}|ordinary"]["worst"] for y in YEARS) >= -2500
    return all(ch.values()), ch


def straddle_ratio(t):
    i = int(np.searchsorted(t.minute, 780)); s = float(t.close[i])
    if not np.isfinite(s): return float("nan")
    best = None
    for j, (k, kind) in enumerate(zip(t.strikes, t.kinds)):
        if kind != 1 or not np.isfinite(t.q[i, j, 3]): continue
        jp = next((jj for jj, (kk, kd) in enumerate(zip(t.strikes, t.kinds)) if kk == k and kd == -1), None)
        if jp is None or not np.isfinite(t.q[i, jp, 3]): continue
        if best is None or abs(k - s) < best[0]: best = (abs(k - s), float(t.q[i, j, 3] + t.q[i, jp, 3]))
    return best[1] / s * 100 if best else float("nan")


def score():
    fz = json.loads((HERE / "freeze2.json").read_text())
    assert all(sha(HERE / f) == h for f, h in fz["files"].items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *FILES, "freeze2.json"), "freeze not committed"
    assert not (HERE / "results2.json").exists(), "scored once"
    E.directions = C.masked; M.AVAIL = C.available_at
    try:
        T = M.tapes(); res = dict(freeze_head=fz["head"])
        control = measure(M.E032, T); res["E032"] = control
        # ---- EN08
        mr = {t.day: M.morning_range(t) for y in YEARS for t in T[y]}
        vals = sorted(v for v in mr.values() if np.isfinite(v)); t1 = vals[len(vals) // 3]; t2 = vals[2 * len(vals) // 3]
        tier = lambda v: "calm" if not v >= t1 else "active" if v >= t2 else "mid"
        table = {}
        for y in YEARS:
            for tk in control[f"{y}|tickets"]:
                k = f"{y}|{tier(mr[tk['day']])}"; table.setdefault(k, [0, 0., 0]); table[k][0] += 1; table[k][1] = round(table[k][1] + tk["net"], 2); table[k][2] += tk["net"] > 0
            for tr in ("calm", "mid", "active"):
                table.setdefault(f"{y}|{tr}", [0, 0., 0])
                table[f"{y}|{tr}"].append(sum(1 for t in T[y] if tier(mr[t.day]) == tr))      # days in the tier
        sr = {t.day: straddle_ratio(t) for y in YEARS for t in T[y]}
        sv = sorted(v for v in sr.values() if np.isfinite(v)); s1, s2 = sv[len(sv) // 3], sv[2 * len(sv) // 3]
        stable = {}
        for y in YEARS:
            for tk in control[f"{y}|tickets"]:
                v = sr[tk["day"]]; k = f"{y}|{'low' if not v >= s1 else 'high' if v >= s2 else 'mid'}"
                stable.setdefault(k, [0, 0.]); stable[k][0] += 1; stable[k][1] = round(stable[k][1] + tk["net"], 2)
        en08 = measure(replace(M.E032, regime_min=t1), T); ok, ch = robust(en08, control)
        mech = all(table[f"{y}|calm"][1] <= 0 for y in YEARS)
        res["EN08"] = dict(thresholds=dict(calm_below=round(t1, 4), active_from=round(t2, 4)), tickets_by_tier=table,
                           straddle_tiers=dict(low_below=round(s1, 4), high_from=round(s2, 4), tickets=stable),
                           arm=en08, robust=ok, checks=ch, mechanism_calm_loses_every_year=mech, passed=ok and mech)
        # ---- EN09
        add = measure(replace(M.E032, squeeze="add"), T); only = measure(replace(M.E032, squeeze="only"), T)
        ok, ch = robust(add, control)
        sigs = {y: sum(1 for t in T[y] if np.count_nonzero(M.squeeze_signals(t))) for y in YEARS}
        nulls = {y: [] for y in YEARS}
        real = dict(M._SQ)
        try:
            for s in range(40):
                rng = random.Random(f"en09-{s}")
                for y in YEARS:
                    for t in T[y]:
                        o = real[id(t)].copy(); i = np.flatnonzero(o)
                        if len(i):
                            d = rng.choice((1, -1)); o[i] = d if C.available_at(t, int(i[0]), d) else 0
                        M._SQ[id(t)] = o
                    nulls[y].append(M.run(T[y], replace(M.E032, squeeze="only"), "ordinary")["summary"]["net"])
        finally:
            M._SQ.clear(); M._SQ.update(real)
        null_med = {y: round(st.median(v), 2) for y, v in nulls.items()}
        pos2 = sum(only[f"{y}|ordinary"]["net"] > 0 for y in YEARS) >= 2
        above = all(only[f"{y}|ordinary"]["net"] > null_med[y] for y in YEARS)
        res["EN09"] = dict(signal_days=sigs, add=add, only=only, null_median=null_med, robust=ok, checks=ch,
                           only_positive_2_of_3=pos2, only_above_null_every_year=above, passed=ok and pos2 and above)
        # ---- EN10
        en10 = measure(replace(M.E032, bank_r=1.), T); ok, ch = robust(en10, control)
        changes = {}
        for y in YEARS:
            base = {(x["day"], x["entry"], x["side"]): x for x in control[f"{y}|tickets"] if x["lots"] == 1}
            new = {(x["day"], x["entry"], x["side"]): x for x in en10[f"{y}|tickets"] if x["lots"] == 1}
            diff = [(k, base[k]["net"], new[k]["net"], base[k]["exits"]) for k in base if k in new and abs(base[k]["net"] - new[k]["net"]) > .005]
            changes[y] = dict(changed=len(diff), better=sum(n > b for _, b, n, _ in diff), worse=sum(n < b for _, b, n, _ in diff),
                              truncated_2x=sum("TARGET" in ex for _, _, _, ex in diff), delta=round(sum(n - b for _, b, n, _ in diff), 2),
                              by_side={s: round(sum(n - b for k, b, n, _ in diff if k[2] == s), 2) for s in "CP"})
        res["EN10"] = dict(arm=en10, robust=ok, checks=ch, one_lot_changes=changes, passed=ok)
    finally:
        E.directions = C.ORIGINAL; M.AVAIL = None
    (HERE / "results2.json").write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print("PASSED", {k: res[k]["passed"] for k in ("EN08", "EN09", "EN10")})


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
