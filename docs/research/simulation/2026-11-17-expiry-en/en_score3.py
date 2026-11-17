"""EN11-EN25 scorer: PLAN3.md's frozen rules applied mechanically -> results3.json + anatomy3.json, once.
`freeze` hashes the plan, labs and scorers; `score` refuses unless the freeze is committed and unchanged, and leaves a
start receipt so a second score is refused even if the first one is interrupted."""
from __future__ import annotations
import hashlib, json, statistics as st, subprocess, sys, time
from collections import defaultdict
from pathlib import Path
import en_lab3 as L3
import exam2023b as C
import rec2026, en15_breadth as breadth, en11_seconds as seconds

HERE = Path(__file__).resolve().parent
FILES = ("PLAN3.md", "en_lab3.py", "en_score3.py", "rec2026.py", "en15_breadth.py", "en11_seconds.py", "en_lab2.py", "en_lab.py", "en_base.py",
         "exam2023b.py", "exam2023.py")
RESULTS, ANAT, START = HERE / "results3.json", HERE / "anatomy3.json", HERE / "results3-started.json"
SC = ("ordinary", "adverse", "catastrophe"); YEARS = (2023, 2024, 2025)
E, LOT = L3.E, L3.LOT
R_EXIT = ("EN11", "EN12", "EN20", "EN21", "EN22", "EN24", "EN25")
R_NEW = ("EN13", "EN14", "EN17", "EN19", "EN23")
SEEDS = 40


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def freeze():
    assert not RESULTS.exists() and not START.exists()
    (HERE / "freeze3.json").write_text(json.dumps(dict(files={f: sha(HERE / f) for f in FILES}, head=git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


def window(m):return "13:00-13:30" if m < 810 else "13:30-14:00" if m < 840 else "14:00-14:30" if m < 870 else "14:30-15:00" if m < 900 else "15:00+"


def tickets(r, by):
    out, missed = [], []
    for d in r["days"]:
        t = by[d["day"]]
        for p in d["positions"]:
            sells = [e for e in p["events"] if e.get("side") == "SELL"]
            row = dict(day=p["day"], key=f'{p["day"]}|{int(p["decision_i"])}|{int(p["direction"])}',
                       side="PAIR" if p["direction"] == 0 else "P" if p["direction"] < 0 else "C", minute=int(t.minute[p["decision_i"]]),
                       lots=p["lots"], entry=round(float(p["entry"]), 4), net=p["net"], origin=p.get("origin"),
                       peak=round(p["peak"] / p["entry"], 2) if p.get("peak") and p["entry"] else None,
                       path="+".join(e["reason"] for e in sells) or ("UNRESOLVED" if p.get("unresolved") else ""),
                       first=sells[0]["reason"] if sells else ("UNRESOLVED" if p.get("unresolved") else ""),
                       added=p.get("added", 0), retry=bool(p.get("retry")))
            if sells and sells[0]["reason"] == "TARGET_BASE":
                s = sells[0]; paid = p["entry"] * p["lots"] * LOT + p["events"][0]["fees"]
                row.update(sold_at_2x=s["lots"], covered=bool(s["price"] * s["lots"] * LOT - s["fees"] >= paid - .005))
            out.append(row)
        missed += [f'{m["day"]}|{m["decision_i"]}|{m["direction"]}' for m in d.get("missed", [])]
    return out, missed


def measure(rule, T, by):
    out = {}
    for y in YEARS:
        for sc in SC:
            r = L3.run(T[y], rule, sc, details=sc == "ordinary")
            s = r["summary"]; out[f"{y}|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades", "fees", "unresolved")}
            if sc == "ordinary":
                out[f"{y}|tickets"], out[f"{y}|missed"] = tickets(r, by)
                out[f"{y}|days_traded"] = sorted({d["day"] for d in r["days"] if d["trades"]})
    return out


def table(ts, key):
    g = defaultdict(lambda: [0, 0, 0.])
    for x in ts:
        k = key(x); g[k][0] += 1; g[k][1] += x["net"] > 0; g[k][2] += x["net"]
    return {k: dict(tickets=v[0], winners=v[1], net=round(v[2], 2)) for k, v in sorted(g.items())}


def anatomy(a, c):
    out = {}
    for y in YEARS:
        ts, cs = a[f"{y}|tickets"], c[f"{y}|tickets"]
        mine, ctl = {x["key"]: x for x in ts}, {x["key"]: x for x in cs}
        added = [x for k, x in mine.items() if k not in ctl]; removed = [x for k, x in ctl.items() if k not in mine]
        changed = [(x, ctl[k]) for k, x in mine.items() if k in ctl and abs(x["net"] - ctl[k]["net"]) > .005]
        ctl_days = set(c[f"{y}|days_traded"])
        out[y] = dict(net=a[f"{y}|ordinary"]["net"], tickets=len(ts), winners=sum(x["net"] > 0 for x in ts),
                      by_side=table(ts, lambda x: x["side"]), by_exit=table(ts, lambda x: x["path"]), by_first_exit=table(ts, lambda x: x["first"]),
                      by_window=table(ts, lambda x: window(x["minute"])),
                      on_e032_days=table(ts, lambda x: "E03.2 traded that day" if x["day"] in ctl_days else "E03.2 empty day"),
                      best=sorted(ts, key=lambda x: -x["net"])[:3], worst=sorted(ts, key=lambda x: x["net"])[:3],
                      vs_control=dict(added=len(added), added_net=round(sum(x["net"] for x in added), 2), added_winners=sum(x["net"] > 0 for x in added),
                                      removed=len(removed), removed_net=round(sum(x["net"] for x in removed), 2),
                                      removed_winners=sum(x["net"] > 0 for x in removed),
                                      changed=len(changed), changed_delta=round(sum(p["net"] - q["net"] for p, q in changed), 2),
                                      changed_better=sum(p["net"] > q["net"] for p, q in changed), changed_worse=sum(p["net"] < q["net"] for p, q in changed),
                                      biggest=sorted([dict(day=p["day"], side=p["side"], was=q["net"], now=p["net"], was_path=q["path"], now_path=p["path"])
                                                      for p, q in changed], key=lambda z: abs(z["now"] - z["was"]), reverse=True)[:4]))
    return out


def robust(a, c):
    ch = {}
    for y in YEARS:
        ch[f"{y}_ordinary"] = a[f"{y}|ordinary"]["net"] >= c[f"{y}|ordinary"]["net"]
        ch[f"{y}_adverse"] = a[f"{y}|adverse"]["net"] >= c[f"{y}|adverse"]["net"]
        ch[f"{y}_without_best"] = a[f"{y}|ordinary"]["without_best"] >= c[f"{y}|ordinary"]["without_best"]
    ch["severe_sum"] = sum(a[f"{y}|catastrophe"]["net"] for y in YEARS) >= sum(c[f"{y}|catastrophe"]["net"] for y in YEARS) - 1000
    ch["worst_day"] = min(a[f"{y}|ordinary"]["worst"] for y in YEARS) >= -2500
    ch["adverse_sum_positive"] = sum(a[f"{y}|adverse"]["net"] for y in YEARS) > 0
    return ch


def new_checks(a, nulls):
    ch = {}
    for y in YEARS:
        ch[f"{y}_positive"] = a[f"{y}|ordinary"]["net"] > 0
        ch[f"{y}_without_best_ge_0"] = a[f"{y}|ordinary"]["without_best"] >= 0
        ch[f"{y}_above_null"] = a[f"{y}|ordinary"]["net"] > nulls[y]
    ch["adverse_sum_positive"] = sum(a[f"{y}|adverse"]["net"] for y in YEARS) > 0
    ch["worst_day"] = min(a[f"{y}|ordinary"]["worst"] for y in YEARS) >= -2500
    return ch


def changed_classes(a, c):
    """EN11 / EN22: losses saved vs winners cut on the same tickets, and stops that would have recovered."""
    out = dict(saved=0, saved_rs=0., cut=0, cut_rs=0., stopped_would_recover=0, their_now=0., their_control=0., first_exits={})
    for y in YEARS:
        ctl = {x["key"]: x for x in c[f"{y}|tickets"]}
        for x in a[f"{y}|tickets"]:
            q = ctl.get(x["key"])
            if not q or abs(x["net"] - q["net"]) <= .005:
                continue
            out["first_exits"][x["first"]] = out["first_exits"].get(x["first"], 0) + 1
            if x["net"] > q["net"]:
                out["saved"] += 1; out["saved_rs"] = round(out["saved_rs"] + x["net"] - q["net"], 2)
            else:
                out["cut"] += 1; out["cut_rs"] = round(out["cut_rs"] + x["net"] - q["net"], 2)
            if x["net"] < 0 < q["net"]:
                out["stopped_would_recover"] += 1; out["their_now"] = round(out["their_now"] + x["net"], 2)
                out["their_control"] = round(out["their_control"] + q["net"], 2)
    return out


def score():
    fz = json.loads((HERE / "freeze3.json").read_text())
    assert all(sha(HERE / f) == h for f, h in fz["files"].items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *FILES, "freeze3.json"), "freeze not committed"
    assert not RESULTS.exists() and not START.exists(), "scored once"
    START.write_text(json.dumps(dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), freeze_head=fz["head"]), indent=2) + "\n")
    res, anat = pipeline(L3.tapes(), SEEDS, fz["head"])
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    ANAT.write_text(json.dumps({k: {str(y): v for y, v in a.items()} for k, a in anat.items()}, indent=1, default=str) + "\n", encoding="utf-8")
    print("VERDICTS", {k: res[k]["verdict"] for k in ("EN11", "EN12", "EN13", "EN14", "EN15", "EN16", "EN17", "EN18", "EN19", "EN20",
                                                     "EN21", "EN22", "EN23", "EN24", "EN25")})


def selftest():
    """The whole pipeline on two days a year and two null seeds; nothing written, no rupees printed."""
    T = {y: v[:2] for y, v in L3.tapes().items()}
    res, anat = pipeline(T, 2, "selftest", quiet=True)
    json.dumps(res, default=str); json.dumps({k: {str(y): v for y, v in a.items()} for k, a in anat.items()}, default=str)
    print("SELFTEST_OK", sorted(k for k in res if k.startswith("EN")))


def pipeline(T, seeds, head, quiet=False):
    E.directions = C.masked; L3.AVAIL = C.available_at; L3.M.AVAIL = C.available_at
    try:
        by = {t.day: t for y in YEARS for t in T[y]}
        res = dict(freeze_head=head); anat = {}
        control = measure(L3.E032, T, by); res["E032"] = {k: v for k, v in control.items() if "|tickets" not in k and "|missed" not in k}
        anat["E03.2 (control)"] = anatomy(control, control)
        arms = {}
        for name, rule in L3.ARMS.items():
            arms[name] = measure(rule, T, by)
            if not quiet:
                print(name, {y: arms[name][f"{y}|ordinary"]["net"] for y in YEARS}, flush=True)
        nulls = {}
        for name in R_NEW:
            v = {y: [] for y in YEARS}
            try:
                for s in range(seeds):
                    L3.NULL = f"en3-{name}-{s}"
                    for y in YEARS:
                        v[y].append(L3.run(T[y], L3.ARMS[name], "ordinary")["summary"]["net"])
            finally:
                L3.NULL = None
            nulls[name] = {y: round(st.median(v[y]), 2) for y in YEARS}
        for name, a in arms.items():
            rec = dict(summary={k: v for k, v in a.items() if "|tickets" not in k and "|missed" not in k})
            anat[name] = anatomy(a, control)
            if name in R_EXIT:
                ch = robust(a, control); moved = sum(anat[name][y]["vs_control"][k] for y in YEARS for k in ("added", "removed", "changed"))
                rec.update(checks=ch, moved_tickets=moved, verdict="INCONCLUSIVE" if moved < 6 else "PASS" if all(ch.values()) else "FAIL")
            elif name in R_NEW:
                ch = new_checks(a, nulls[name]); n = sum(a[f"{y}|ordinary"]["trades"] for y in YEARS)
                if name == "EN14":
                    ch["beats_immediate"] = sum(a[f"{y}|ordinary"]["net"] for y in YEARS) > sum(arms["EN14_immediate_diag"][f"{y}|ordinary"]["net"] for y in YEARS)
                rec.update(checks=ch, null_median=nulls[name], tickets=n, verdict="INCONCLUSIVE" if n < 10 else "PASS" if all(ch.values()) else "FAIL")
            else:
                rec["verdict"] = "DIAGNOSTIC"
            res[name] = rec
        # slot diagnostics (anatomy, owner's rule)
        diag = {"EN11": changed_classes(arms["EN11"], control), "EN22": changed_classes(arms["EN22"], control)}
        tb = [x for y in YEARS for x in arms["EN12"][f"{y}|tickets"] if "sold_at_2x" in x]
        cb = {x["key"]: x for y in YEARS for x in control[f"{y}|tickets"] if "sold_at_2x" in x}
        diag["EN12"] = dict(split_tickets=len(tb), covered=sum(x["covered"] for x in tb), lots_sold_at_2x=sum(x["sold_at_2x"] for x in tb),
                            control_lots_sold_at_2x=sum(cb[x["key"]]["sold_at_2x"] for x in tb if x["key"] in cb),
                            runner_paths=table(tb, lambda x: x["path"]),
                            delta_on_split_tickets=round(sum(x["net"] - cb[x["key"]]["net"] for x in tb if x["key"] in cb), 2),
                            control_split_tickets=len(cb), control_covered=sum(x["covered"] for x in cb.values()))
        rt = [x for y in YEARS for x in arms["EN20"][f"{y}|tickets"] if x["retry"]]
        diag["EN20"] = dict(retries=len(rt), retry_winners=sum(x["net"] > 0 for x in rt), retry_net=round(sum(x["net"] for x in rt), 2))
        ad = [x for y in YEARS for x in arms["EN21"][f"{y}|tickets"] if x["added"]]
        ctl_all = {x["key"]: x for y in YEARS for x in control[f"{y}|tickets"]}
        nad = [x for y in YEARS for x in arms["EN21"][f"{y}|tickets"] if not x["added"] and x["key"] in ctl_all and ctl_all[x["key"]]["lots"] >= 2]
        diag["EN21"] = dict(added=len(ad), added_winners=sum(x["net"] > 0 for x in ad), added_net=round(sum(x["net"] for x in ad), 2),
                            added_control_net=round(sum(ctl_all[x["key"]]["net"] for x in ad if x["key"] in ctl_all), 2),
                            half_only=len(nad), half_only_net=round(sum(x["net"] for x in nad), 2),
                            half_only_control_net=round(sum(ctl_all[x["key"]]["net"] for x in nad), 2))
        ms = [k for y in YEARS for k in arms["EN25"][f"{y}|missed"]]
        diag["EN25"] = dict(missed=len(ms), missed_in_control=sum(k in ctl_all for k in ms),
                            missed_control_winners=sum(ctl_all[k]["net"] > 0 for k in ms if k in ctl_all),
                            missed_control_net=round(sum(ctl_all[k]["net"] for k in ms if k in ctl_all), 2))
        res["diagnostics"] = diag
        res["recorded2026"] = rec2026.score(); res["EN15"] = breadth.score(); res["EN11_seconds"] = seconds.score()
        res["EN16"] = dict(verdict=res["recorded2026"]["EN16"]["verdict"]); res["EN18"] = dict(verdict=res["recorded2026"]["EN18"]["verdict"])
        for name, a in arms.items():
            anat[name]["tickets"] = {y: a[f"{y}|tickets"] for y in YEARS}
        anat["E03.2 (control)"]["tickets"] = {y: control[f"{y}|tickets"] for y in YEARS}
    finally:
        E.directions = C.ORIGINAL; L3.AVAIL = None; L3.M.AVAIL = None
    return res, anat


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
