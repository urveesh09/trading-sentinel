"""EN26-EN40 + the fresh 2026 NIFTY / SENSEX exam: PLAN4.md's frozen rules applied mechanically, once.

    python en_score4.py selftest   the whole pipeline on a few days and two seeds; nothing written, no rupees printed
    python en_score4.py freeze     hashes the plan, the new files and every transitively imported lab / loader / fee
                                   module and both data bindings -> freeze4.json
    python en_score4.py score      refuses unless the freeze is committed and unchanged; start receipt; writes
                                   results4.json + anatomy4.json once"""
from __future__ import annotations
import hashlib, json, math, random, statistics as st, subprocess, sys, time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import numpy as np
import en_lab4 as L4
import en4_data as D4
import rec2026b, en33_lag

HERE = Path(__file__).resolve().parent
SIM = HERE.parent; REPO = HERE.parents[3]
LOCAL_FILES = ("PLAN4.md", "en4_data.py", "en_lab4.py", "en_score4.py", "rec2026b.py", "en33_lag.py", "en_lab3.py", "en_lab2.py",
               "en_lab.py", "en_base.py", "exam2023b.py", "exam2023.py", "rec2026.py", "data-binding4.json")
EXTERNAL = {"r8b_lab.py": SIM / "2026-11-03-expiry-round8/r8b_lab.py", "e031_lab.py": SIM / "2026-11-03-expiry-e031/lab.py",
            "e03_lab.py": SIM / "2026-11-03-expiry-e03/e03_lab.py", "e02_lab.py": SIM / "2026-11-03-expiry-e02/e02_lab.py",
            "data.py": SIM / "2026-11-03-expiry-e02/data.py", "riskdial.py": SIM / "2026-11-03-expiry-auction/riskdial.py",
            "expiry_paper.py": REPO / "python-engine/expiry_paper.py", "cost_schedules.py": REPO / "python-engine/cost_schedules.py",
            "qa.py": REPO / "docs/research/fno/2026-11-13-sn101/qa.py", "data-binding.json": SIM / "2026-11-02-expiry-e02/data-binding.json"}
RESULTS, ANAT, START, FREEZE = HERE / "results4.json", HERE / "anatomy4.json", HERE / "results4-started.json", HERE / "freeze4.json"
SC = ("ordinary", "adverse", "catastrophe"); YEARS = ("2023", "2024", "2025"); X1 = ("N-X1", "S-X1"); X2 = ("N-X2", "S-X2")
SEEDS = 40
R_EXIT = ("EN26", "EN27", "EN28", "EN29", "EN31", "EN36", "EN37", "EN38")
EXAM_ONLY = ("EN39", "EN40")
HELD_EXIT, HELD_NEW = ("EN21", "EN25", "EN12"), ("EN14",)
R_NEW = ("EN30", "EN32")
DIAG = ("EN26_cat_diag", "EN28_opt_diag", "EN31_flip_diag", "EN35_diag", "EN11", "EN12_full_sale_diag", "EN13", "EN14_immediate_diag")
KS = (1., 1.5, 2., 2.5, 3.)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def _paths():
    return {**{f: HERE / f for f in LOCAL_FILES}, **EXTERNAL}


def freeze():
    assert not RESULTS.exists() and not START.exists()
    FREEZE.write_text(json.dumps(dict(files={k: sha(p) for k, p in _paths().items()}, head=git("rev-parse", "HEAD"),
                                      export_sha256=json.loads((HERE / "data-binding4.json").read_text())["export_sha256"]), indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


# ---------------------------------------------------------------- measurement
def window(m):
    return "13:00-13:30" if m < 810 else "13:30-14:00" if m < 840 else "14:00-14:30" if m < 870 else "14:30-15:00" if m < 900 else "15:00+"


def tickets(r, by):
    out, missed = [], []
    for d in r["days"]:
        t = by[d["day"]]; lot = L4.spec_of(t).lot
        for p in d["positions"]:
            sells = [e for e in p["events"] if e.get("side") == "SELL"]
            row = dict(day=p["day"], key=f'{p["day"]}|{int(p["decision_i"])}|{int(p["direction"])}',
                       side="P" if p["direction"] < 0 else "C", minute=int(t.minute[p["decision_i"]]), lots=p["lots"],
                       entry=round(float(p["entry"]), 4), first=round(float(p["first"]), 4), net=p["net"], origin=p.get("origin"),
                       peak=round(p["peak"] / p["entry"], 2) if p.get("peak") and p["entry"] else None,
                       path="+".join(e["reason"] for e in sells) or ("UNRESOLVED" if p.get("unresolved") else ""),
                       first_exit=sells[0]["reason"] if sells else ("UNRESOLVED" if p.get("unresolved") else ""),
                       added=p.get("added", 0), fallback=p.get("fallback_lots", 0), fees=p["fees"],
                       hold=int((p.get("exit_i") or t.n) - p["entry_i"]))
            if sells and sells[0]["reason"] == "TARGET_BASE":
                s = sells[0]; paid = p["entry"] * p["lots"] * lot + p["events"][0]["fees"]
                row.update(sold_at_2x=s["lots"], covered=bool(s["price"] * s["lots"] * lot - s["fees"] >= paid - .005))
            out.append(row)
        missed += [f'{m["day"]}|{m["decision_i"]}|{m["direction"]}' for m in d.get("missed", [])]
    return out, missed


def measure(rule, books, by):
    out = {}
    for b, ts in books.items():
        for sc in SC:
            r = L4.run4(ts, rule, sc, details=sc == "ordinary")
            s = r["summary"]; out[f"{b}|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades", "fees", "unresolved")}
            if sc == "ordinary":
                out[f"{b}|tickets"], out[f"{b}|missed"] = tickets(r, by)
                out[f"{b}|days_traded"] = sorted({d["day"] for d in r["days"] if d["trades"]})
                out[f"{b}|daily"] = [d["net"] for d in r["days"]]
    return out


def table(ts, key):
    g = defaultdict(lambda: [0, 0, 0.])
    for x in ts:
        k = key(x); g[k][0] += 1; g[k][1] += x["net"] > 0; g[k][2] += x["net"]
    return {k: dict(tickets=v[0], winners=v[1], net=round(v[2], 2)) for k, v in sorted(g.items())}


def vs(a, c, b):
    mine, ctl = {x["key"]: x for x in a[f"{b}|tickets"]}, {x["key"]: x for x in c[f"{b}|tickets"]}
    added = [x for k, x in mine.items() if k not in ctl]; removed = [x for k, x in ctl.items() if k not in mine]
    changed = [(x, ctl[k]) for k, x in mine.items() if k in ctl and abs(x["net"] - ctl[k]["net"]) > .005]
    return added, removed, changed


def anatomy(a, c, books):
    out = {}
    for b in books:
        ts = a[f"{b}|tickets"]; added, removed, changed = vs(a, c, b); ctl_days = set(c[f"{b}|days_traded"])
        out[b] = dict(net=a[f"{b}|ordinary"]["net"], tickets=len(ts), winners=sum(x["net"] > 0 for x in ts),
                      by_side=table(ts, lambda x: x["side"]), by_first_exit=table(ts, lambda x: x["first_exit"]),
                      by_window=table(ts, lambda x: window(x["minute"])), by_origin=table(ts, lambda x: x["origin"] or ""),
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


def moved(an, books):
    return sum(an[b]["vs_control"][k] for b in books for k in ("added", "removed", "changed"))


def affected(a, c, books):
    keys = set()
    for b in books:
        added, removed, changed = vs(a, c, b)
        keys |= {x["key"] for x in added} | {x["key"] for x in removed} | {p["key"] for p, _ in changed}
    return len(keys), len({k.split("|")[0] for k in keys})


# ---------------------------------------------------------------- verdict rules (PLAN4.md section 6)
def r_exit_d(a, c):
    ch = {}
    for y in YEARS:
        ch[f"{y}_ordinary"] = a[f"{y}|ordinary"]["net"] >= c[f"{y}|ordinary"]["net"]
        ch[f"{y}_adverse"] = a[f"{y}|adverse"]["net"] >= c[f"{y}|adverse"]["net"]
        ch[f"{y}_without_best"] = a[f"{y}|ordinary"]["without_best"] >= c[f"{y}|ordinary"]["without_best"]
    ch["severe_sum"] = sum(a[f"{y}|catastrophe"]["net"] for y in YEARS) >= sum(c[f"{y}|catastrophe"]["net"] for y in YEARS) - 1000
    ch["worst_day"] = min(a[f"{y}|ordinary"]["worst"] for y in YEARS) >= -2500
    ch["adverse_sum_positive"] = sum(a[f"{y}|adverse"]["net"] for y in YEARS) > 0
    return ch


def r_new_d(a, nulls):
    ch = {}
    for y in YEARS:
        ch[f"{y}_positive"] = a[f"{y}|ordinary"]["net"] > 0
        ch[f"{y}_without_best_ge_0"] = a[f"{y}|ordinary"]["without_best"] >= 0
        ch[f"{y}_above_null"] = a[f"{y}|ordinary"]["net"] > nulls[y]
    ch["adverse_sum_positive"] = sum(a[f"{y}|adverse"]["net"] for y in YEARS) > 0
    ch["worst_day"] = min(a[f"{y}|ordinary"]["worst"] for y in YEARS) >= -2500
    return ch


def r_exit_x(a, c, b):
    return dict(ordinary=a[f"{b}|ordinary"]["net"] >= c[f"{b}|ordinary"]["net"], adverse=a[f"{b}|adverse"]["net"] >= c[f"{b}|adverse"]["net"],
                without_best=a[f"{b}|ordinary"]["without_best"] >= c[f"{b}|ordinary"]["without_best"],
                severe=a[f"{b}|catastrophe"]["net"] >= c[f"{b}|catastrophe"]["net"] - 1000, worst_day=a[f"{b}|ordinary"]["worst"] >= -2500,
                adverse_positive=a[f"{b}|adverse"]["net"] > 0)


def r_new_x(a, null, b):
    return dict(ordinary_positive=a[f"{b}|ordinary"]["net"] > 0, adverse_positive=a[f"{b}|adverse"]["net"] > 0,
                without_best_ge_0=a[f"{b}|ordinary"]["without_best"] >= 0, above_null=a[f"{b}|ordinary"]["net"] > null,
                worst_day=a[f"{b}|ordinary"]["worst"] >= -2500)


def verdict(checks, informative):
    return "INCONCLUSIVE" if not informative else "PASS" if all(checks.values()) else "FAIL"


# ---------------------------------------------------------------- risk dial (RISK_PLAN.md's computation, copied verbatim)
CASH, BOOT_YEARS, BLOCK, SEED = 25000., 20000, 4, 20261103


def drawdown(v):
    cur = peak = m = 0.
    for x in v:
        cur += x; peak = max(peak, cur); m = max(m, peak - cur)
    return m


def skeptical(nets):
    v = list(nets); v.remove(max(v)); mu = st.mean(v)
    return [x - .5 * mu for x in v]


def bootstrap(series, rng, years=BOOT_YEARS):
    n = len(series); starts = list(range(n - BLOCK + 1))
    finals, dds, logs = [], [], []
    for _ in range(years):
        year = []
        while len(year) < 52:
            s0 = rng.choice(starts); year.extend(series[s0:s0 + BLOCK])
        year = year[:52]; total = sum(year)
        finals.append(total); dds.append(drawdown(year))
        logs.append(math.log(max(1e-9, (CASH + total) / CASH)))
    finals.sort(); dds.sort()
    return dict(loss_year_chance=round(sum(x < 0 for x in finals) / years, 4), year_p5=round(finals[int(.05 * years)], 2),
                year_median=round(finals[years // 2], 2), drawdown_p95=round(dds[int(.95 * years)], 2),
                median_log_growth=round(sorted(logs)[years // 2], 5))


def risk_dial(records, boot_years=BOOT_YEARS):
    out = {}
    for name, ts in records.items():
        out[name] = {}
        for k in KS:
            rule = replace(L4.E032, size_k=k)
            runs = {sc: L4.run4(ts, rule, sc) for sc in SC}
            adv = [d["net"] for d in runs["adverse"]["days"]]
            b = bootstrap(skeptical(adv), random.Random(SEED), boot_years)
            out[name][str(k)] = dict(ordinary=runs["ordinary"]["summary"]["net"], adverse=runs["adverse"]["summary"]["net"],
                                     severe=runs["catastrophe"]["summary"]["net"], worst=runs["ordinary"]["summary"]["worst"],
                                     drawdown=runs["ordinary"]["summary"]["drawdown"], **b,
                                     passes=dict(loss_year=b["loss_year_chance"] <= .30, drawdown=b["drawdown_p95"] <= 5000,
                                                 severe=runs["catastrophe"]["summary"]["net"] >= -6250))
    ok = [k for k in KS if all(all(out[n][str(k)]["passes"].values()) for n in out)]
    return dict(records=out, recommended_k=max(ok) if ok else 1.0, passing=ok)


# ---------------------------------------------------------------- the pipeline
def pipeline(dev, exam, seeds, head, quiet=False, boot_years=BOOT_YEARS, recorded=True):
    L4._patch(); L4.THETA = 0.6924; L4.UNAV.clear()
    books_d = {y: dev[int(y)] for y in YEARS}
    books_x = {**{b: exam[b] for b in X1 + X2}, "N-ALL": exam["N-X1"] + exam["N-X2"], "S-ALL": exam["S-X1"] + exam["S-X2"]}
    books = {**books_d, **books_x}
    by = {t.day: t for ts in books.values() for t in ts}
    res = dict(freeze_head=head, theta=L4.THETA, cohorts={b: len(ts) for b, ts in books.items()},
               excluded=json.loads((HERE / "data-binding4.json").read_text())["excluded"])
    anat = {}
    control = measure(L4.E032, books, by); e031 = measure(L4.E031, books, by)
    strip = lambda a: {k: v for k, v in a.items() if not any(s in k for s in ("|tickets", "|missed", "|daily", "|days_traded"))}  # noqa: E731
    res["E032"] = strip(control); res["E031"] = strip(e031)
    res["E032_unavailable"] = {b: sum(1 for (day, _, _) in L4.UNAV if day in {t.day for t in ts}) for b, ts in books.items()}
    anat["E03.2 (control)"] = anatomy(control, control, books); anat["E03.1"] = anatomy(e031, control, books)
    arms = {}
    for name in L4.ARMS:
        arms[name] = measure(L4.rule_for(name), books, by)
        if not quiet:
            print(name, "measured", flush=True)
    # matched nulls: new setups (random side at the same minutes) and E03.2 / E03.1 random entries
    nulls = {}
    for name in R_NEW + HELD_NEW:
        v = defaultdict(list)
        try:
            for s in range(seeds):
                L4.L3.NULL = f"en4-{name}-{s}"
                for b in YEARS + X1:
                    v[b].append(L4.run4(books[b], L4.rule_for(name), "ordinary")["summary"]["net"])
        finally:
            L4.L3.NULL = None
        nulls[name] = {b: round(st.median(v[b]), 2) for b in v}
    for name, rule in (("E032", L4.E032), ("E031", L4.E031)):
        v = defaultdict(list)
        try:
            for s in range(seeds):
                L4.RANDOM = f"en4-{name}-{s}"
                for b in X1:
                    v[b].append(L4.run4(books[b], rule, "ordinary")["summary"]["net"])
        finally:
            L4.RANDOM = None
        nulls[name] = {b: round(st.median(v[b]), 2) for b in v}
    res["nulls"] = nulls
    # verdicts
    status = {}
    for name, a in arms.items():
        an = anatomy(a, control, books); anat[name] = an
        rec = dict(summary=strip(a))
        if name in R_EXIT + HELD_EXIT + EXAM_ONLY:
            if name in EXAM_ONLY:
                rec["dev"] = dict(verdict="SELECTED_ON_DEV")
            else:
                ch = r_exit_d(a, control); rec["dev"] = dict(checks=ch, moved=moved(an, YEARS), verdict=verdict(ch, moved(an, YEARS) >= 6))
            rec["exam"] = {}
            for b in X1:
                ch = r_exit_x(a, control, b); rec["exam"][b] = dict(checks=ch, moved=moved(an, (b,)), verdict=verdict(ch, moved(an, (b,)) >= 3))
            n, days = affected(a, control, YEARS + X1); rec["evidence"] = dict(affected=n, expiries=days, met=n >= 20 and days >= 10)
        elif name in R_NEW + HELD_NEW:
            ch = r_new_d(a, nulls[name]); n = sum(a[f"{y}|ordinary"]["trades"] for y in YEARS)
            if name == "EN30":
                ch["beats_EN14"] = sum(a[f"{y}|ordinary"]["net"] for y in YEARS) > sum(arms["EN14"][f"{y}|ordinary"]["net"] for y in YEARS)
            if name == "EN14":
                ch["beats_immediate"] = sum(a[f"{y}|ordinary"]["net"] for y in YEARS) > sum(arms["EN14_immediate_diag"][f"{y}|ordinary"]["net"] for y in YEARS)
            rec["dev"] = dict(checks=ch, tickets=n, verdict=verdict(ch, n >= 10))
            rec["exam"] = {}
            for b in X1:
                ch = r_new_x(a, nulls[name][b], b); nb = a[f"{b}|ordinary"]["trades"]
                rec["exam"][b] = dict(checks=ch, tickets=nb, null_median=nulls[name][b], verdict=verdict(ch, nb >= 8))
            tk = [x for b in YEARS + X1 for x in a[f"{b}|tickets"]]
            rec["evidence"] = dict(tickets=len(tk), expiries=len({x["day"] for x in tk}), met=len(tk) >= 30 and len({x["day"] for x in tk}) >= 20)
        else:
            rec["dev"] = dict(verdict="DIAGNOSTIC")
        res[name] = rec
    for name in R_EXIT + HELD_EXIT + EXAM_ONLY + R_NEW + HELD_NEW:
        rec = res[name]; dv = rec["dev"]["verdict"]; xv = [rec["exam"][b]["verdict"] for b in X1]
        if dv == "PASS" and all(v == "PASS" for v in xv) and rec["evidence"]["met"]:
            s = "CANDIDATE"
        elif all(v == "PASS" for v in xv):
            s = "EXAM-ONLY PASS"
        elif any(v == "PASS" for v in xv):
            s = "ONE-INDEX"
        elif "FAIL" in xv + [dv]:
            s = "FAIL"
        else:
            s = "INCONCLUSIVE"
        status[name] = s
    if res["EN32"]["dev"]["tickets"] < 10:
        status["EN32"] = "NOT FEASIBLE"
    ready = all(res[n]["dev"]["verdict"] == "PASS" for n in ("EN27", "EN28", "EN29"))
    an = anat["EN35_diag"]
    res["EN35_diag"]["exam"] = {b: dict(checks=r_exit_x(arms["EN35_diag"], control, b), moved=moved(an, (b,))) for b in X1}
    if ready:
        xs = [verdict(res["EN35_diag"]["exam"][b]["checks"], res["EN35_diag"]["exam"][b]["moved"] >= 3) for b in X1]
        status["EN35"] = "CANDIDATE" if all(v == "PASS" for v in xs) else "FAIL" if "FAIL" in xs else "INCONCLUSIVE"
    else:
        status["EN35"] = "NOT READY"
    res["status"] = status
    # the E03-family exam on each X1 book (tests 7, 1, 5, 6)
    fam = {}
    for b in X1:
        c, o = control, e031
        t7 = dict(ordinary=c[f"{b}|ordinary"]["net"] > 0, adverse=c[f"{b}|adverse"]["net"] > 0, without_best=c[f"{b}|ordinary"]["without_best"] > 0,
                  worst_day=c[f"{b}|ordinary"]["worst"] >= -2500)
        t1 = dict(ordinary=o[f"{b}|ordinary"]["net"] > 0, adverse=o[f"{b}|adverse"]["net"] > 0, without_best=o[f"{b}|ordinary"]["without_best"] > 0,
                  worst_day=o[f"{b}|ordinary"]["worst"] >= -1250, above_random=o[f"{b}|ordinary"]["net"] > nulls["E031"][b])
        t5 = dict(ordinary=c[f"{b}|ordinary"]["net"] > o[f"{b}|ordinary"]["net"], adverse=c[f"{b}|adverse"]["net"] > o[f"{b}|adverse"]["net"],
                  without_best=c[f"{b}|ordinary"]["without_best"] > o[f"{b}|ordinary"]["without_best"],
                  worst=c[f"{b}|ordinary"]["worst"] >= 2 * o[f"{b}|ordinary"]["worst"])
        ts = o[f"{b}|tickets"]; puts = [x["net"] for x in ts if x["side"] == "P"]; calls = [x["net"] for x in ts if x["side"] == "C"]
        t6 = dict(put_per_ticket=round(st.mean(puts), 2) if puts else None, call_per_ticket=round(st.mean(calls), 2) if calls else None,
                  holds=bool(puts and calls and st.mean(puts) > st.mean(calls)))
        fam[b] = dict(test7_E032_stands=dict(checks=t7, passed=all(t7.values()), random_median=nulls["E032"][b]),
                      test1_E031_stands=dict(checks=t1, passed=all(t1.values())), test5_E032_over_E031=dict(checks=t5, passed=all(t5.values())),
                      test6_put_asymmetry=t6)
    res["family_exam"] = fam
    # slot diagnostics (owner's anatomy rule)
    res["diagnostics"] = diagnostics(arms, control, books)
    res["risk_dial"] = risk_dial({"NIFTY 2023-25 + N-X1": books_d["2023"] + books_d["2024"] + books_d["2025"] + books["N-X1"],
                                  "S-X1": books["S-X1"]}, boot_years)
    res["EN33"] = en33_lag.score(books["S-X1"]); status["EN33"] = res["EN33"]["verdict"]
    if recorded:
        rb = rec2026b.score(); res["EN16_R1"], res["EN18_R1"], res["EN34"] = rb["EN16_R1"], rb["EN18_R1"], rb["EN34"]
        status["EN34"] = res["EN34"]["verdict"]
    for name, a in arms.items():
        anat[name]["tickets"] = {b: a[f"{b}|tickets"] for b in books}
    anat["E03.2 (control)"]["tickets"] = {b: control[f"{b}|tickets"] for b in books}
    anat["E03.1"]["tickets"] = {b: e031[f"{b}|tickets"] for b in books}
    return res, anat


def diagnostics(arms, control, books):
    D = {}
    keysets = YEARS + X1
    def classes(a):
        out = dict(saved=0, saved_rs=0., cut=0, cut_rs=0., winners_turned_losers=0, by_new_exit={})
        for b in keysets:
            _, _, changed = vs(a, control, b)
            for p, q in changed:
                if p["net"] > q["net"]:
                    out["saved"] += 1; out["saved_rs"] = round(out["saved_rs"] + p["net"] - q["net"], 2)
                else:
                    out["cut"] += 1; out["cut_rs"] = round(out["cut_rs"] + p["net"] - q["net"], 2)
                out["winners_turned_losers"] += p["net"] < 0 < q["net"]
                out["by_new_exit"][p["first_exit"]] = out["by_new_exit"].get(p["first_exit"], 0) + 1
        return out
    for n in ("EN26", "EN26_cat_diag", "EN11", "EN29", "EN12_full_sale_diag"):
        D[n] = classes(arms[n])
    for n in ("EN27", "EN21", "EN35_diag"):
        ad = [x for b in keysets for x in arms[n][f"{b}|tickets"] if x["added"]]
        ctl = {x["key"]: x for b in keysets for x in control[f"{b}|tickets"]}
        half = [x for b in keysets for x in arms[n][f"{b}|tickets"] if not x["added"] and x["key"] in ctl and ctl[x["key"]]["lots"] >= 2]
        D[n + "_adds"] = dict(added=len(ad), added_winners=sum(x["net"] > 0 for x in ad), added_net=round(sum(x["net"] for x in ad), 2),
                              added_control_net=round(sum(ctl[x["key"]]["net"] for x in ad if x["key"] in ctl), 2),
                              half_only=len(half), half_only_net=round(sum(x["net"] for x in half), 2),
                              half_only_control_net=round(sum(ctl[x["key"]]["net"] for x in half), 2))
    for n in ("EN28", "EN28_opt_diag", "EN25"):
        ctl = {x["key"]: x for b in keysets for x in control[f"{b}|tickets"]}
        ms = [k for b in keysets for k in arms[n][f"{b}|missed"]]
        ts = [x for b in keysets for x in arms[n][f"{b}|tickets"]]
        same = [(x, ctl[x["key"]]) for x in ts if x["key"] in ctl]
        D[n + "_entry"] = dict(missed=len(ms), missed_control_winners=sum(ctl[k]["net"] > 0 for k in ms if k in ctl),
                               missed_control_net=round(sum(ctl[k]["net"] for k in ms if k in ctl), 2),
                               fallback_tickets=sum(1 for x in ts if x["fallback"]),
                               mean_entry_vs_control_pct=round(100 * float(np.mean([x["entry"] / q["entry"] - 1 for x, q in same])), 3) if same else None,
                               same_tickets=len(same))
    for n in ("EN31", "EN31_flip_diag"):
        rv = [x for b in keysets for x in arms[n][f"{b}|tickets"] if x["origin"] in ("REVERSE", "FLIP")]
        D[n + "_reversals"] = dict(reversals=len(rv), winners=sum(x["net"] > 0 for x in rv), net=round(sum(x["net"] for x in rv), 2),
                                   by_book={b: sum(1 for x in arms[n][f"{b}|tickets"] if x["origin"] in ("REVERSE", "FLIP")) for b in keysets})
    for n in ("EN30", "EN14", "EN14_immediate_diag", "EN32", "EN13"):
        D[n + "_book"] = {b: dict(tickets=arms[n][f"{b}|ordinary"]["trades"], net=arms[n][f"{b}|ordinary"]["net"]) for b in keysets}
    feas = {}
    for b in keysets:
        tot = ok = 0
        for t in books[b]:
            dd = L4.setup_signals(t, L4.ARMS["EN32"])[0]
            for i in np.flatnonzero(dd):
                tot += 1; ok += L4.choose_atm(L4.spec_of(t), t, int(i), int(dd[i]), 1250.) is not None
        feas[b] = dict(signals=tot, affordable=ok)
    D["EN32_feasibility"] = feas
    for n in ("EN36", "EN37", "EN38", "EN39", "EN40"):
        rm = []
        for b in keysets:
            _, removed, _ = vs(arms[n], control, b); rm += removed
        D[n + "_removed"] = dict(removed=len(rm), removed_winners=sum(x["net"] > 0 for x in rm), removed_net=round(sum(x["net"] for x in rm), 2))
    return D


def score():
    fz = json.loads(FREEZE.read_text())
    assert all(sha(p) == fz["files"][k] for k, p in _paths().items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *LOCAL_FILES, "freeze4.json"), "freeze not committed"
    assert not RESULTS.exists() and not START.exists(), "scored once"
    START.write_text(json.dumps(dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), freeze_head=fz["head"]), indent=2) + "\n")
    import en_lab2 as M
    res, anat = pipeline(M.tapes(), D4.tapes(), SEEDS, fz["head"])
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    ANAT.write_text(json.dumps(anat, indent=1, default=str) + "\n", encoding="utf-8")
    print("STATUS", res["status"])


def selftest():
    import en_lab2 as M
    dev = {y: v[:3] for y, v in M.tapes().items()}; ex = {k: v[:6] for k, v in D4.tapes().items()}
    res, anat = pipeline(dev, ex, 2, "selftest", quiet=True, boot_years=50, recorded=False)
    json.dumps(res, default=str); json.dumps(anat, default=str)
    print("SELFTEST_OK", sorted(res["status"]), "keys", len(res))


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
