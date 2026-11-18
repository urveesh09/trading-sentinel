"""EN41-EN55 scorer: PLAN5.md's frozen rules applied mechanically, once.

    python en_score5.py selftest   whole pipeline on a few sessions and two seeds; nothing written, no rupees printed
    python en_score5.py freeze     hashes the plan, this round's files, every transitive lab / loader / fee module, both
                                   data bindings and the results4 receipt used for parity -> freeze5.json
    python en_score5.py score      refuses unless the freeze is committed and unchanged; start receipt; results5.json +
                                   anatomy5.json, once"""
from __future__ import annotations
import hashlib, json, math, statistics as st, subprocess, sys, time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import numpy as np
import en_lab5 as L5

HERE = Path(__file__).resolve().parent
SIM = HERE.parent; EN = SIM / "2026-11-17-expiry-en"; REPO = HERE.parents[3]
LOCAL_FILES = ("PLAN5.md", "en_lab5.py", "en_score5.py")
EXTERNAL = {**{f: EN / f for f in ("en_lab4.py", "en4_data.py", "en_lab3.py", "en_lab2.py", "en_lab.py", "en_base.py", "exam2023.py",
                                    "exam2023b.py", "data-binding4.json", "results4.json")},
            "r8b_lab.py": SIM / "2026-11-03-expiry-round8/r8b_lab.py", "e031_lab.py": SIM / "2026-11-03-expiry-e031/lab.py",
            "e03_lab.py": SIM / "2026-11-03-expiry-e03/e03_lab.py", "e02_lab.py": SIM / "2026-11-03-expiry-e02/e02_lab.py",
            "data.py": SIM / "2026-11-03-expiry-e02/data.py", "expiry_paper.py": REPO / "python-engine/expiry_paper.py",
            "cost_schedules.py": REPO / "python-engine/cost_schedules.py", "data-binding.json": SIM / "2026-11-02-expiry-e02/data-binding.json"}
RESULTS, ANAT, START, FREEZE = HERE / "results5.json", HERE / "anatomy5.json", HERE / "results5-started.json", HERE / "freeze5.json"
SC = ("ordinary", "adverse", "catastrophe"); SEEDS = 40; PERM = 20000
ENTRIES = ("EN44", "EN45", "EN49", "EN51", "EN52", "EN54")
DIRECTIONAL = ("EN44", "EN45", "EN49")
MODS = {"EN46": "E032_sym", "EN47": "E032_sym", "EN50": "E032_sym", "EN53": "E032_30k"}
FORWARD_ONLY = {"EN55": "E032_30k"}
NO_DATA = {"EN41": "DATA_UNAVAILABLE", "EN42": "DATA_UNAVAILABLE", "EN43": "DATA_UNAVAILABLE", "EN48": "INCONCLUSIVE"}
UNAVAILABLE_BOOKS = {"EN44": ("SENSEX",)}          # no morning option bars: Breeze SENSEX rows start 12:00


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def _paths():
    return {**{f: HERE / f for f in LOCAL_FILES}, **EXTERNAL}


def freeze():
    assert not RESULTS.exists() and not START.exists()
    FREEZE.write_text(json.dumps(dict(files={k: sha(p) for k, p in _paths().items()}, head=git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


def window(m):
    return ("09:45-11:00" if m < 660 else "11:00-12:30" if m < 750 else "12:30-13:30" if m < 810 else "13:30-14:30" if m < 870
            else "14:30-15:00" if m < 900 else "15:00+")


def tickets(r, by):
    out = []
    for d in r["days"]:
        t = by[d["day"]]
        for p in d["positions"]:
            sells = [e for e in p["events"] if e.get("side") == "SELL"]
            out.append(dict(day=p["day"], key=f'{p["day"]}|{int(p["decision_i"])}|{int(p["direction"])}', symbol=p.get("symbol"),
                            side="S" if p["direction"] == 0 else "P" if p["direction"] < 0 else "C", minute=int(t.minute[p["decision_i"]]),
                            lots=p["lots"], entry=round(float(p["entry"]), 4), net=p["net"], origin=p.get("origin"),
                            path="+".join(e["reason"] for e in sells) or ("UNRESOLVED" if p.get("unresolved") else ""),
                            first_exit=sells[0]["reason"] if sells else ("UNRESOLVED" if p.get("unresolved") else ""), fees=p["fees"]))
    return out


def metrics(days, tk):
    v = [d["net"] for d in days]; top = sorted(v, reverse=True)
    gains = sum(x for x in v if x > 0); loss = -sum(x for x in v if x < 0)
    yrs = defaultdict(float)
    for d in days:
        yrs[d["day"][:4]] += d["net"]
    return dict(net=round(sum(v), 2), without_top2=round(sum(v) - sum(top[:2]), 2), worst=round(min(v, default=0.), 2),
                tickets=len(tk), expiries=len({x["day"] for x in tk}), winners=sum(x["net"] > 0 for x in tk),
                profit_factor=round(gains / loss, 3) if loss else None, by_year={k: round(x, 2) for k, x in sorted(yrs.items())},
                unresolved=sum(d["unresolved"] for d in days), fees=round(sum(d["fees"] for d in days), 2))


def measure(arm, B, wallet=True, start=30000., retain=.5):
    out = {}
    for b, book in B.items():
        by = {t.day: t for t in book}
        for sc in SC:
            r = L5.run_fixed(book, arm, sc, details=sc == "ordinary")
            tk = tickets(r, by) if sc == "ordinary" else [None] * r["summary"]["trades"]
            out[f"{b}|{sc}"] = metrics(r["days"], tk if sc == "ordinary" else [])
            if sc == "ordinary":
                out[f"{b}|tickets"] = tk; out[f"{b}|daily"] = [d["net"] for d in r["days"]]
                out[f"{b}|refusals"] = dict(defaultdict(int, {}))
                for d in r["days"]:
                    k = d.get("refusal")
                    if k:
                        out[f"{b}|refusals"][k] = out[f"{b}|refusals"].get(k, 0) + 1
            else:
                out[f"{b}|{sc}"]["tickets"] = r["summary"]["trades"]
        if wallet:
            for sc in ("ordinary", "adverse"):
                w = L5.run_wallet(book, arm, sc, start=start, retain=retain)
                out[f"{b}|wallet_{sc}"] = dict(P=w["P"], swept=w["swept"], wallet=w["wallet"], halted=w["halted"], first_halt=w["first_halt"],
                                               drawdown=w["summary"]["drawdown"], worst=w["summary"]["worst"], trades=w["summary"]["trades"])
    return out


def strip(a):
    return {k: v for k, v in a.items() if not any(s in k for s in ("|tickets", "|daily"))}


def perm_p(x, seed=L5.SEED):
    """One-sided sign-flip permutation p-value for mean(x) > 0 (expiry days are the resampling unit)."""
    x = np.asarray(x, float)
    if not len(x) or not np.any(x):
        return 1.0
    rng = np.random.default_rng(seed); obs = x.mean()
    flips = rng.choice((-1., 1.), size=(PERM, len(x)))
    return float((np.sum((flips * x).mean(1) >= obs) + 1) / (PERM + 1))


def holm(ps):
    keys = sorted(ps, key=ps.get); m = len(keys); out = {}; run = 0.
    for k_, k in enumerate(keys):
        run = max(run, min(1., (m - k_) * ps[k])); out[k] = round(run, 4)
    return out


def vs(a, c, b):
    mine, ctl = {x["key"]: x for x in a[f"{b}|tickets"]}, {x["key"]: x for x in c[f"{b}|tickets"]}
    added = [x for k, x in mine.items() if k not in ctl]; removed = [x for k, x in ctl.items() if k not in mine]
    changed = [(x, ctl[k]) for k, x in mine.items() if k in ctl and abs(x["net"] - ctl[k]["net"]) > .005]
    return added, removed, changed


def table(ts, key):
    g = defaultdict(lambda: [0, 0, 0.])
    for x in ts:
        k = key(x); g[k][0] += 1; g[k][1] += x["net"] > 0; g[k][2] += x["net"]
    return {k: dict(tickets=v[0], winners=v[1], net=round(v[2], 2)) for k, v in sorted(g.items())}


def anatomy(a, c, B):
    out = {}
    for b in B:
        ts = a[f"{b}|tickets"]; ad, rm, ch = vs(a, c, b)
        out[b] = dict(net=a[f"{b}|ordinary"]["net"], tickets=len(ts), winners=sum(x["net"] > 0 for x in ts),
                      by_side=table(ts, lambda x: x["side"]), by_first_exit=table(ts, lambda x: x["first_exit"]),
                      by_window=table(ts, lambda x: window(x["minute"])), by_year=a[f"{b}|ordinary"]["by_year"],
                      best=sorted(ts, key=lambda x: -x["net"])[:3], worst=sorted(ts, key=lambda x: x["net"])[:3],
                      vs_control=dict(added=len(ad), added_net=round(sum(x["net"] for x in ad), 2), added_winners=sum(x["net"] > 0 for x in ad),
                                      removed=len(rm), removed_net=round(sum(x["net"] for x in rm), 2), removed_winners=sum(x["net"] > 0 for x in rm),
                                      changed=len(ch), changed_delta=round(sum(p["net"] - q["net"] for p, q in ch), 2),
                                      changed_better=sum(p["net"] > q["net"] for p, q in ch), changed_worse=sum(p["net"] < q["net"] for p, q in ch)))
    return out


def pipeline(B, seeds, head, quiet=False):
    L5.install(); L5.EXITSPEC.clear(); L5._CACHE.clear(); L5.GATE.clear(); del L5.DIAG49[:]
    L5.prepare(B, quiet)
    res = dict(freeze_head=head, sessions={b: len(v) for b, v in B.items()}, status={}); anat = {}
    arms = {"E032_25k": measure(L5.E032, B, start=25000., retain=0.)}
    for name, arm in L5.ARMS.items():
        arms[name] = measure(arm, B)
        if not quiet:
            print(name, "measured", flush=True)
    for k, v in arms.items():
        res[k] = dict(summary=strip(v))
    # matched random-side nulls for the directional new setups (fixed-cap books)
    nulls = {}
    for name in DIRECTIONAL:
        vals = defaultdict(list)
        try:
            for s in range(seeds):
                L5.L3.NULL = f"en5-{name}-{s}"
                for b, book in B.items():
                    vals[b].append(L5.run_fixed(book, L5.ARMS[name])["summary"]["net"])
        finally:
            L5.L3.NULL = None
        nulls[name] = {b: round(st.median(v), 2) for b, v in vals.items()}
    res["nulls"] = nulls
    # verdicts
    ps = {}
    for name in ENTRIES:
        a = arms[name]; rec = res[name]; rec["books"] = {}
        live = [b for b in B if b not in UNAVAILABLE_BOOKS.get(name, ())]
        for b in B:
            if b not in live:
                rec["books"][b] = dict(verdict="DATA_UNAVAILABLE"); continue
            o, ad = a[f"{b}|ordinary"], a[f"{b}|adverse"]
            ch = dict(ordinary_positive=o["net"] > 0, adverse_positive=ad["net"] > 0, without_top2_positive=o["without_top2"] > 0,
                      worst_day=o["worst"] >= -2500)
            if name in DIRECTIONAL:
                ch["above_null"] = o["net"] > nulls[name][b]
            sup = o["tickets"] >= 30 and o["expiries"] >= 20
            rec["books"][b] = dict(checks=ch, support=dict(tickets=o["tickets"], expiries=o["expiries"]),
                                   verdict="INCONCLUSIVE" if not sup else "PASS" if all(ch.values()) else "FAIL")
        vs_ = [rec["books"][b]["verdict"] for b in live]
        rec["dev"] = "PASS" if vs_ and all(v == "PASS" for v in vs_) else "FAIL" if "FAIL" in vs_ else "INCONCLUSIVE"
        ps[name] = perm_p([x for b in live for x in a[f"{b}|daily"]])
    for name, ctl in MODS.items():
        a, c = arms[name], arms[ctl]; rec = res[name]; rec["books"] = {}; aff = set()
        for b in B:
            o, ad, co, cad = a[f"{b}|ordinary"], a[f"{b}|adverse"], c[f"{b}|ordinary"], c[f"{b}|adverse"]
            ch = dict(ordinary=o["net"] >= co["net"], adverse=ad["net"] >= cad["net"], without_top2=o["without_top2"] >= co["without_top2"],
                      worst_day=o["worst"] >= co["worst"] - 250, adverse_positive=ad["net"] > 0)
            x1, x2, x3 = vs(a, c, b); aff |= {x["key"] for x in x1} | {x["key"] for x in x2} | {p["key"] for p, _ in x3}
            prot = o["worst"] >= co["worst"] and a[f"{b}|wallet_ordinary"]["drawdown"] <= c[f"{b}|wallet_ordinary"]["drawdown"] and o["net"] >= co["net"] - 1000
            rec["books"][b] = dict(checks=ch, protection=prot, verdict="PASS" if all(ch.values()) else "FAIL")
        exp = {k.split("|")[0] for k in aff}; rec["support"] = dict(affected=len(aff), expiries=len(exp))
        sup = len(aff) >= 20 and len(exp) >= 10
        vs_ = [rec["books"][b]["verdict"] for b in B]
        rec["dev"] = "INCONCLUSIVE" if not sup else "PASS" if all(v == "PASS" for v in vs_) else "FAIL"
        rec["protection"] = all(rec["books"][b]["protection"] for b in B)
        ps[name] = perm_p([x - y for b in B for x, y in zip(a[f"{b}|daily"], c[f"{b}|daily"])])
    for name, ctl in FORWARD_ONLY.items():
        res[name]["dev"] = "FORWARD-ONLY (configuration selected on these sessions)"
    adj = holm(ps); res["tests"] = dict(raw={k: round(v, 4) for k, v in ps.items()}, holm=adj)
    for name in ENTRIES + tuple(MODS):
        d = res[name]["dev"]
        res["status"][name] = ("FORWARD CANDIDATE" + ("" if adj[name] <= .05 else " (screening pass; not significant after Holm)")) if d == "PASS" else \
            ("PROTECTION ONLY" if name in MODS and res[name].get("protection") and d != "INCONCLUSIVE" else d)
    res["status"].update({k: v for k, v in NO_DATA.items()}); res["status"]["EN55"] = "FORWARD-ONLY"
    res["no_data"] = dict(
        EN41="Needs receipt-clock futures depth packets. TR01 (Production Docker volume, since Nov 13) holds at most two expiry sessions and has not been exported or sealed; its export is a separate, owner-authorised task.",
        EN42="Same data as EN41.",
        EN43="Needs dated NIFTY/SENSEX weights and sub-minute constituent prices; only Kite 15-minute bars (Jan-Jul 2026, current basket) are held.",
        EN48="Officially verified RBI decision dates in the scored history: Aug 8 2024 (2024-25 schedule, RBI press release of Mar 27 2024) is the only one on a NIFTY expiry session; far below 30 tickets on 20 expiries. The 2023-24 schedule was not verified in this round.")
    # capital (auditor section 4): the three E03.2 controls as continuous wallets
    res["capital"] = {k: {b: {sc: arms[k][f"{b}|wallet_{sc}"] for sc in ("ordinary", "adverse")} for b in B} for k in ("E032_25k", "E032_30k", "E032_sym", "EN55")}
    # diagnostics
    D = {}
    rows = L5.DIAG49
    for b in B:
        r = [x for x in rows if x[0] == b]
        D[f"EN49_{b}"] = dict(rows=len(r), mean_label=round(float(np.mean([x[4] for x in r])), 4) if r else None,
                              share_mu_pos=round(float(np.mean([x[2] > 0 for x in r])), 4) if r else None,
                              share_mu_and_p5_pos=round(float(np.mean([x[2] > 0 and x[3] > 0 for x in r])), 4) if r else None,
                              max_mu=round(max((x[2] for x in r), default=float("nan")), 4) if r else None,
                              calibration_top_decile=_calib(r))
    g = defaultdict(int)
    for k, v in L5.GATE.items():
        g[f"{k[0]}|{k[3]}|{v}"] += 1
    D["EN46_gate"] = dict(g)
    for b in B:
        n1 = {x["key"]: x for x in arms["EN47_native1_diag"][f"{b}|tickets"]}
        same = [(x, n1[x["key"]]) for x in arms["EN47"][f"{b}|tickets"] if x["key"] in n1]
        D[f"EN47_{b}"] = dict(common=len(same), different_strike=sum(x["symbol"] != y["symbol"] for x, y in same),
                              common_net=round(sum(x["net"] for x, _ in same), 2), native1_common_net=round(sum(y["net"] for _, y in same), 2))
        for n in ("EN50", "EN51", "EN52", "EN54", "EN44", "EN45"):
            D[f"{n}_{b}_exits"] = table(arms[n][f"{b}|tickets"], lambda x: x["path"])
        D[f"EN51_{b}_refusals"] = arms["EN51"][f"{b}|refusals"]; D[f"EN54_{b}_refusals"] = arms["EN54"][f"{b}|refusals"]
    res["diagnostics"] = D
    for name, a in arms.items():
        ctl = MODS.get(name) or FORWARD_ONLY.get(name) or ("E032_sym" if name in ENTRIES else "E032_30k")
        anat[name] = anatomy(a, arms[ctl], B)
        anat[name]["tickets"] = {b: a[f"{b}|tickets"] for b in B}
    return res, anat


def _calib(r):
    if len(r) < 50:
        return None
    mu = np.array([x[2] for x in r]); y = np.array([x[4] for x in r]); q = np.quantile(mu, [.1, .9])
    return dict(bottom_decile_label=round(float(y[mu <= q[0]].mean()), 4), top_decile_label=round(float(y[mu >= q[1]].mean()), 4))


def score():
    fz = json.loads(FREEZE.read_text())
    assert all(sha(p) == fz["files"][k] for k, p in _paths().items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *LOCAL_FILES, "freeze5.json"), "freeze not committed"
    assert not RESULTS.exists() and not START.exists(), "scored once"
    START.write_text(json.dumps(dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), freeze_head=fz["head"]), indent=2) + "\n")
    res, anat = pipeline(L5.books(), SEEDS, fz["head"])
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    ANAT.write_text(json.dumps(anat, indent=1, default=str) + "\n", encoding="utf-8")
    print("STATUS", res["status"])


def selftest():
    B = {k: v[:45] for k, v in L5.books().items()}
    res, anat = pipeline(B, 2, "selftest", quiet=True)
    json.dumps(res, default=str); json.dumps(anat, default=str)
    print("SELFTEST_OK", sorted(res["status"]), "keys", len(res))


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
