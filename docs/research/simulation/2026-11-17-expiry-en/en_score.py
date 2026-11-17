"""EN03-EN05 scorer: applies PLAN.md's frozen decision rules mechanically -> results.json.
`freeze` writes freeze.json (file hashes + git head); `score` refuses unless that freeze is committed and the
files are unchanged. NIFTY 2024 + 2025 only (SEEN, in-sample)."""
from __future__ import annotations
import hashlib, json, random, subprocess, sys
from dataclasses import replace, asdict
from pathlib import Path
import en_lab as N

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-auction"))
import riskdial as D  # noqa: E402  (skeptical(), bootstrap(), drawdown(), SEED)

FILES = ("PLAN.md", "en_base.py", "en_lab.py", "en_score.py")
SC = ("ordinary", "adverse", "catastrophe")
ARMS = {"E032": {}}
for v in (.65, .60, .55): ARMS[f"EN03_eff{v:.2f}"] = dict(put_eff=v)
for v in (2.5, 3., 3.5): ARMS[f"EN04_put{v:g}x"] = dict(put_mult=v)
for v in (1.1, 1.2, 1.3): ARMS[f"EN05_run{v:g}"] = dict(put_runner=v)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def freeze():
    (HERE / "freeze.json").write_text(json.dumps(dict(files={f: sha(HERE / f) for f in FILES}, head=git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


def verify():
    fz = json.loads((HERE / "freeze.json").read_text())
    assert all(sha(HERE / f) == h for f, h in fz["files"].items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *FILES, "freeze.json"), "freeze not committed"
    return fz


def measure(rule):
    T = N.B.tapes(); out = {}
    for y in (2024, 2025):
        for sc in SC:
            r = N.run(T[y], rule, sc, details=(sc == "ordinary"))
            s = r["summary"]; out[f"{y}|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades")}
            if sc == "ordinary":
                out[f"{y}|tickets"] = [dict(day=p["day"], side="P" if p["direction"] < 0 else "C", lots=p["lots"], entry=p["entry"], net=p["net"],
                                            exits=[e["reason"] for e in p["events"][1:]]) for d in r["days"] for p in d["positions"]]
    both = T[2024] + T[2025]
    for sc in SC:
        r = N.run(both, rule, sc); s = r["summary"]; nets = [d["net"] for d in r["days"]]
        out[f"both|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades")}
        if sc == "adverse":
            out["skeptical"] = D.bootstrap(D.skeptical(nets), random.Random(D.SEED))
    out["risk_plan"] = dict(loss_year=out["skeptical"]["loss_year_chance"] <= .30, drawdown=out["skeptical"]["drawdown_p95"] <= 5000,
                            severe=out["both|catastrophe"]["net"] >= -6250)
    return out


def beats(a, c):
    checks = {}
    for y in (2024, 2025):
        checks[f"{y}_ordinary"] = a[f"{y}|ordinary"]["net"] >= c[f"{y}|ordinary"]["net"]
        checks[f"{y}_adverse"] = a[f"{y}|adverse"]["net"] >= c[f"{y}|adverse"]["net"]
        checks[f"{y}_without_best"] = a[f"{y}|ordinary"]["without_best"] >= c[f"{y}|ordinary"]["without_best"]
    checks["severe"] = a["both|catastrophe"]["net"] >= c["both|catastrophe"]["net"] - 1000
    checks["worst_day"] = a["both|ordinary"]["worst"] >= -2500
    return all(checks.values()), checks


def score():
    fz = verify(); res = {"freeze_head": fz["head"], "arms": {}}
    for name, extra in ARMS.items():
        rule = replace(N.E032, **extra); m = measure(rule); res["arms"][name] = dict(rule=extra, **m)
        print(name, {k: (v["net"], v["trades"]) for k, v in m.items() if "|" in k and "tickets" not in k}, flush=True)
    c = res["arms"]["E032"]; dec = {}
    for name in ARMS:
        if name != "E032":
            ok, checks = beats(res["arms"][name], c); dec[name] = dict(beats=ok, checks=checks, risk_plan=res["arms"][name]["risk_plan"])
    en03 = None
    for v in ("0.65", "0.60", "0.55"):
        if dec[f"EN03_eff{v}"]["beats"]: en03 = float(v)
        else: break
    en04 = 3. if all(dec[f"EN04_put{v}x"]["beats"] and all(dec[f"EN04_put{v}x"]["risk_plan"].values()) for v in ("2.5", "3", "3.5")) else None
    en05 = 1.2 if dec["EN05_run1.2"]["beats"] and (dec["EN05_run1.1"]["beats"] or dec["EN05_run1.3"]["beats"]) else None
    adopted = {k: v for k, v in (("put_eff", en03), ("put_mult", en04), ("put_runner", en05)) if v is not None}
    res["decisions"] = dict(per_arm=dec, EN03=en03, EN04=en04, EN05=en05, adopted=adopted)
    if len(adopted) >= 2:
        combo = measure(replace(N.E032, **adopted)); res["arms"]["COMBO"] = dict(rule=adopted, **combo)
        ok, checks = beats(combo, c)
        singles = [f"EN03_eff{en03:.2f}" if en03 else None, "EN04_put3x" if en04 else None, "EN05_run1.2" if en05 else None]
        over = all(combo[f"both|{sc}"]["net"] >= res["arms"][s][f"both|{sc}"]["net"] for s in singles if s for sc in ("ordinary", "adverse"))
        res["decisions"]["COMBO"] = dict(beats=ok, checks=checks, over_singles=over)
        cand = dict(adopted) if ok and over else None
    else:
        cand = dict(adopted) if adopted else None
    if cand is None and adopted:
        best = max(adopted.items(), key=lambda kv: res["arms"][{"put_eff": f"EN03_eff{en03:.2f}" if en03 else "", "put_mult": "EN04_put3x", "put_runner": "EN05_run1.2"}[kv[0]]]["both|adverse"]["net"])
        cand = {best[0]: best[1]}
    res["decisions"]["candidate"] = cand
    (HERE / "results.json").write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print("DECISIONS", json.dumps({k: v for k, v in res["decisions"].items() if k != "per_arm"}))


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
