"""Round-9 freeze and one-shot development score (IMPL9.md). Freeze before any candidate money exists.

  score9.py selftest   whole pipeline on a truncated registry/calendar; prints counts only, writes selftest9.json
  score9.py freeze     writes freeze9.json (code/data/registry/procedure hashes); refuses if it exists
  score9.py score      once: refuses changed code/data, an uncommitted freeze, or an earlier start
"""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
import hashlib, json, math, os, platform, subprocess, sys, time
import numpy as np
import round8  # noqa: F401
import data8, lab8, signals8, score8
import signals9 as S9, lab9, families9 as F, search9 as SR, stats9
L7 = lab8.L7; L4 = L7.L4

HERE = Path(__file__).resolve().parent
FILES9 = ("IMPL9.md", "families9.json", "families9-own.json", "round8.py", "signals9.py", "lab9.py", "families9.py", "search9.py",
          "stats9.py", "score9.py", "test9.py", "test9_unit.py", "calibration9.json", "calibration9-holm.json")
FREEZE = HERE / "freeze9.json"
SC = ("ordinary", "adverse", "catastrophe")
CATEGORY = {**{f: "profit" for f in ("EN96", "EN97", "EN98", "EN101", "EN104", "EN105", "EN106", "EN107", "EN108", "EN109", "EN110")},
            **{f: "risk" for f in ("EN99", "EN100", "EN102", "EN103")}}
UNION = {"signal": ("EN96", "EN97"), "management": ("EN101", "EN102")}


def git(*a):
    return subprocess.check_output(["git", *a], cwd=HERE, text=True).strip()


def sources():
    return {**{f: HERE / f for f in FILES9}, "spec/EXPIRY_RESEARCH_EN96_EN105.md": HERE.parents[2] / "EXPIRY_RESEARCH_EN96_EN105.md",
            **{"round8/" + k: p for k, p in score8.source_paths().items()}}


def write(path, obj):
    path = Path(path); tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(score8.clean(obj), f, indent=1, allow_nan=False); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


# ------------------------------------------------------------------ running one configuration
def canon_day(d):
    return (d["net"], d["trades"], d["intents"], d["rejected"], tuple((p["j"], p["entry_i"], p.get("exit_i"), p["lots"], round(p["net"], 2),
            tuple((e["i"], e["side"], e.get("reason"), e["lots"], e["price"]) for e in p["events"])) for p in d["positions"]))


def slim(d):
    return {k: d[k] for k in ("day", "net", "trades", "fees", "minutes_in", "marked_worst", "intents", "rejected", "unresolved", "adds9")}


def ticket(t, p):
    sells = [e for e in p["events"] if e["side"] == "SELL"]
    ext = p.get("_ext9")
    return dict(day=t.day, m=int(t.minute[p["decision_i"]]), d=int(p["direction"]), K=float(t.strikes[p["j"]]), lots=int(p["lots"]),
                net=round(p["net"], 2), fees=round(p["fees"], 2), first_exit=sells[0].get("reason") if sells else "UNRESOLVED",
                exits=[e.get("reason") for e in sells], entry_i=int(p["entry_i"]), exit_i=p.get("exit_i"), unresolved=bool(p.get("unresolved")),
                entry=round(float(p["first"]), 2), reserve=round(p["reserve"], 2), added=int(p.get("stage_added", 0)), planned=p.get("planned9"),
                ext="EXTENDED" if isinstance(ext, dict) else "DECLINED" if ext is False else None, z=p.get("z9"), event_i=p.get("event_i9"),
                hold=int(p.get("exit_i", t.n) - p["entry_i"]))


def run_indep(book, rule, idx=None, scen=SC):
    """Independent sessions: Rs 30,000 cash and the full day budget every session."""
    out = {sc: {} for sc in scen}; tickets = []; h = hashlib.sha256(); ok = True
    for sc in scen:
        for k in (range(len(book)) if idx is None else idx):
            t = book[k]; det = sc != "catastrophe"
            d = lab9.run_day9(t, rule, sc, 30000., L7.budget_of(rule), det)
            if det:
                h.update(repr(canon_day(d)).encode())
                ok &= abs(sum(p["net"] for p in d["positions"]) - d["net"]) < .02 and all(p["reserve"] <= p["room"] + .02 for p in d["positions"])
                if sc == "ordinary":
                    tickets.extend(ticket(t, p) for p in d["positions"])
            out[sc][k] = slim(d)
    return out, tickets, h.hexdigest()[:20], ok


def metrics(days, tickets=None):
    vals = [d["net"] for d in days]; top = sorted(vals, reverse=True) + [0., 0.]; years = defaultdict(float)
    for d in days:
        years[d["day"][:4]] += d["net"]
    m = dict(net=round(sum(vals), 2), without_best=round(sum(vals) - max(top[0], 0), 2), without_top2=round(SR.without_top2(vals), 2),
             sessions=len(days), trades=sum(d["trades"] for d in days), traded_expiries=sum(d["trades"] > 0 for d in days),
             worst=round(min(vals, default=0.), 2), worst_marked=round(min([d["marked_worst"] for d in days], default=0.), 2),
             fees=round(sum(d["fees"] for d in days), 2), minutes_in=sum(d["minutes_in"] for d in days), unresolved=sum(d["unresolved"] for d in days),
             tail_days=sum(v >= 2500 for v in vals), by_year={k: round(v, 2) for k, v in sorted(years.items())},
             per_expiry=round(sum(vals) / max(1, len(days)), 2))
    if tickets is not None:
        m.update(winners=sum(x["net"] > 0 for x in tickets), avg_win=round(float(np.mean([x["net"] for x in tickets if x["net"] > 0])), 2) if any(x["net"] > 0 for x in tickets) else None,
                 avg_loss=round(float(np.mean([x["net"] for x in tickets if x["net"] <= 0])), 2) if any(x["net"] <= 0 for x in tickets) else None,
                 by_side={s: round(sum(x["net"] for x in tickets if x["d"] == v), 2) for s, v in (("CALL", 1), ("PUT", -1))})
        fx = defaultdict(float); fn = Counter()
        for x in tickets:
            fx[x["first_exit"]] += x["net"]; fn[x["first_exit"]] += 1
        m["by_first_exit"] = {k: dict(n=fn[k], net=round(fx[k], 2)) for k in sorted(fx)}
    return m


def compare(xs, ys):
    key = lambda x: (x["day"], x["m"], x["d"])
    a = {key(x): x for x in xs}; b = {key(x): x for x in ys}; common = a.keys() & b.keys()
    changed = [k for k in common if abs(a[k]["net"] - b[k]["net"]) > .011]
    return dict(matched=len(common), matched_changed=len(changed), matched_net_delta=round(sum(a[k]["net"] - b[k]["net"] for k in common), 2),
                matched_gain_on_reference_losers=round(sum(a[k]["net"] - b[k]["net"] for k in common if b[k]["net"] <= 0), 2),
                matched_change_on_reference_winners=round(sum(a[k]["net"] - b[k]["net"] for k in common if b[k]["net"] > 0), 2),
                candidate_only=len(a.keys() - b.keys()), candidate_only_net=round(sum(a[k]["net"] for k in a.keys() - b.keys()), 2),
                candidate_only_winners=sum(a[k]["net"] > 0 for k in a.keys() - b.keys()),
                reference_only=len(b.keys() - a.keys()), reference_only_net=round(sum(b[k]["net"] for k in b.keys() - a.keys()), 2),
                reference_only_winners=sum(b[k]["net"] > 0 for k in b.keys() - a.keys()),
                changed_expiries=len({k[0] for k in changed} | {k[0] for k in a.keys() ^ b.keys()}))


def paired(days, a, b):
    diff = [x["net"] - y["net"] for x, y in zip(a, b)]
    r = stats9.infer(days, diff)
    return dict(mean=round(float(np.mean(diff)), 3), lo=r["lo"], hi=r["hi"], p_descriptive=r["p"], groups=r["groups"])


# ------------------------------------------------------------------ the pipeline
def pipeline(B, reg, verbose=True, stageb=True):
    t0 = time.time(); log = (lambda *x: print(f"[{time.time() - t0:.0f}s]", *x, flush=True)) if verbose else (lambda *x: None)
    res = dict(evaluation="DEVELOPMENT ONLY: every session already studied; no qualification", configs={}, unavailable={}, families={},
               data_limits={"SENSEX": "OI not supplied: OI-dependent cells DATA UNAVAILABLE (null money)",
                            "packet": "EN99 packet block SOURCE-GATED: one recorded expiry, >=20 synchronized covered expiries required"},
               inference="DESCRIPTIVE ONLY: calibration9.json / calibration9-holm.json show over-rejection under negatively skewed nulls")
    anat = dict(days={}, tickets={}, logs={}, stageb={}, en105={})
    rules = {}; bank = {}; tick = {}
    for u, book in B.items():
        days = [t.day for t in book]
        for c in reg:
            if c.family == "EN105" or not c.spec:
                continue
            key = f"{c.id}|{u}"
            if u == "SENSEX" and c.spec.needs_oi():
                res["unavailable"][key] = "DATA UNAVAILABLE: SENSEX OI not supplied"; continue
            if c.spec.mgmt and c.spec.mgmt[0] == "RND":
                continue                                                  # needs the EN101 training rate (below)
            rule = c.rule()
            for t in book:
                F.build(t, c.spec, c.id, rule)
            out, tk, h, ok = run_indep(book, rule)
            rules[key] = rule; bank[key] = dict(ordinary=out["ordinary"], adverse=out["adverse"], catastrophe=out["catastrophe"], hash=h, reconciled=ok)
            tick[key] = tk
        log("indep done", u, sum(k.endswith("|" + u) for k in bank))
        if u == "NIFTY":
            for cap in (12, 16, 24):
                rates = []
                for c in reg:
                    if c.family == "EN101" and c.kind == "CELL" and c.settings["absolute_hold_minutes"] == cap:
                        tk = [x for x in tick[f"{c.id}|NIFTY"] if x["day"] < book[SR.INITIAL].day and x["ext"]]
                        rates.append(sum(x["ext"] == "EXTENDED" for x in tk) / len(tk) if tk else 0.)
                p = float(np.mean(rates)) if rates else 0.
                c = next(x for x in reg if x.id == f"EN101:ctl:random_extension_{cap}")
                c.spec = replace(c.spec, mgmt=("RND", cap, round(p, 6))); c.note += f"; training rate {p:.4f}"
                key = f"{c.id}|NIFTY"; rule = c.rule()
                for t in book:
                    F.build(t, c.spec, c.id, rule)
                out, tk, h, ok = run_indep(book, rule)
                rules[key] = rule; bank[key] = dict(ordinary=out["ordinary"], adverse=out["adverse"], catastrophe=out["catastrophe"], hash=h, reconciled=ok)
                tick[key] = tk
        for key in [k for k in bank if k.endswith("|" + u)]:
            r = rules[key]; o = [bank[key]["ordinary"][k] for k in range(len(book))]
            a = [bank[key]["adverse"][k] for k in range(len(book))]; ca = [bank[key]["catastrophe"][k] for k in range(len(book))]
            wo = lab9.wallet9(book, r, "ordinary"); wa = lab9.wallet9(book, r, "adverse")
            cid = key.rsplit("|", 1)[0]; cfg = next(x for x in reg if x.id == cid)
            row = dict(family=cfg.family, kind=cfg.kind, block=cfg.block, settings=cfg.settings, note=cfg.note, hash=bank[key]["hash"],
                       reconciled=bank[key]["reconciled"], ordinary=metrics(o, tick[key]), adverse=metrics(a), catastrophe=metrics(ca),
                       wallet={sc: {k: w[k] for k in ("P", "swept", "wallet", "liq_dd", "halted", "first_halt")} for sc, w in (("ordinary", wo), ("adverse", wa))})
            ref = F.FAMILY_REFERENCE.get(cfg.family)
            if u == "SENSEX":
                ref = "REF:E03_env" if cfg.family not in ("EN106",) else "REF:E032_native"
            if ref and f"{ref}|{u}" in bank and ref != cid:
                rb = bank[f"{ref}|{u}"]
                row["vs_reference"] = dict(reference=ref, ordinary=paired(days, o, [rb["ordinary"][k] for k in range(len(book))]),
                                           adverse=paired(days, a, [rb["adverse"][k] for k in range(len(book))]),
                                           tickets=compare(tick[key], tick[f"{ref}|{u}"]))
            res["configs"][key] = row
            anat["days"][key] = dict(ordinary=[d["net"] for d in o], adverse=[d["net"] for d in a], trades=[d["trades"] for d in o],
                                     wallet_ordinary=[(d["P"], d["scale"]) for d in wo["days"]])
            anat["tickets"][key] = tick[key]
        anat["logs"][u] = {k: v for k, v in summarize_logs(book, reg).items()}
        log("metrics done", u)
    # behaviour dedup groups (ordinary + adverse ledgers)
    groups = defaultdict(list)
    for key, b in bank.items():
        groups[(key.rsplit("|", 1)[1], b["hash"])].append(key.rsplit("|", 1)[0])
    res["dedup"] = {u: [sorted(v) for (uu, _), v in groups.items() if uu == u and len(v) > 1] for u in B}
    res["dedup_counts"] = {u: dict(configs=sum(1 for k in bank if k.endswith("|" + u)), distinct=sum(1 for (uu, _) in groups if uu == u)) for u in B}
    book = B["NIFTY"]; days = [t.day for t in book]
    nb = {k.rsplit("|", 1)[0]: v for k, v in bank.items() if k.endswith("|NIFTY")}
    nr = {k.rsplit("|", 1)[0]: v for k, v in rules.items() if k.endswith("|NIFTY")}
    # family max-t (uncalibrated diagnostic) on adverse paired differences, full fixed grid
    for fam in sorted({c.family for c in reg if c.kind == "CELL"}, key=lambda f: int(f[2:])):
        ref = F.FAMILY_REFERENCE[fam]
        cells = [c.id for c in reg if c.family == fam and c.kind == "CELL" and c.id in nb]
        diffs = {c: [nb[c]["adverse"][k]["net"] - nb[ref]["adverse"][k]["net"] for k in range(len(book))] for c in cells}
        res["families"][fam] = dict(reference=ref, cells=len([c for c in reg if c.family == fam and c.kind == "CELL"]), run_cells=len(cells),
                                    maxt_uncalibrated=stats9.maxt(days, diffs) if cells else None)
    if not stageb:
        return res, anat
    # ---------------- Stage B
    n = len(book); bounds = SR.boundaries(n); finals = bounds + [n]
    cand = {fam: [c.id for c in reg if c.family == fam and c.kind == "CELL" and c.id in nb] for fam in res["families"] if fam != "EN105"}
    sets = dict(cand)
    sets["UNION:signal"] = cand["EN96"] + cand["EN97"]; sets["UNION:management"] = cand["EN101"] + cand["EN102"]
    sets["GENE:entry"] = [c for c in cand["EN99"] if not c.startswith("EN99:immediate")]
    sets["GENE:size"] = [c for c in cand["EN103"] if not c.startswith("EN103:full")]
    sel = {}
    for name, cs in sets.items():
        fam = name.split(":")[1] if name.startswith(("UNION", "GENE")) else name
        ref = F.FAMILY_REFERENCE[{"signal": "EN96", "management": "EN101", "entry": "EN99", "size": "EN103"}.get(fam, fam)]
        sel[name] = {}
        for s in finals:
            pick, why, recs = SR.select_family(book, nb, nr, cs, ref, s)
            sel[name][s] = dict(pick=pick, why=why)
            anat["stageb"].setdefault(name, {})[str(s)] = recs
        log("stage B", name, [sel[name][s]["pick"] for s in finals])
    res["stageb"] = dict(boundaries=bounds, final=n, initial=SR.INITIAL, outer=SR.OUTER, inner=SR.INNER,
                         selections={k: {str(s): v for s, v in d.items()} for k, d in sel.items()})
    # ---------------- EN105 per boundary
    specs = {c.id: c.spec for c in reg}
    gene_sets = {"signal": "UNION:signal", "context": "EN98", "entry": "GENE:entry", "contract": "EN100", "management": "UNION:management", "size": "GENE:size"}
    for s in finals:
        chosen = {g: sel[nm][s]["pick"] for g, nm in gene_sets.items()}
        comp = {g: specs[c] if c else None for g, c in chosen.items()}
        idx_in = list(range(s - SR.INNER, s)); idx_out = list(range(s, min(s + SR.OUTER, n)))
        recs = []; outer = {}; onelot = {}
        for g in SR.genotypes():
            sp = SR.compose(comp, g); key = f"EN105|s{s}|{SR.gid(g)}"; rule = F.rule_of(sp, key)
            for k in idx_in + idx_out:
                F.build(book[k], sp, key, rule)
            o, _, h, ok = run_indep(book, rule, idx_in + idx_out, ("ordinary", "adverse"))
            nb[key] = dict(ordinary=o["ordinary"], adverse=o["adverse"], hash=h, reconciled=ok); nr[key] = rule
            r = SR.evaluate(book, nb, key, rule, "REF:EN87", s, sum(g)); r["genotype"] = SR.gid(g); r["hash"] = h; recs.append(r)
            if idx_out:
                outer[SR.gid(g)] = dict(ordinary=round(sum(o["ordinary"][k]["net"] for k in idx_out), 2), adverse=round(sum(o["adverse"][k]["net"] for k in idx_out), 2),
                                        parents=sum(o["ordinary"][k]["trades"] for k in idx_out))
            sp1 = SR.compose(comp, g, one_lot=True); key1 = key + "|one"; rule1 = F.rule_of(sp1, key1)
            for k in idx_in + idx_out:
                F.build(book[k], sp1, key1, rule1)
            o1, _, _, _ = run_indep(book, rule1, idx_in + idx_out, ("ordinary", "adverse"))
            onelot[SR.gid(g)] = dict(inner_adverse=round(sum(o1["adverse"][k]["net"] for k in idx_in), 2),
                                     outer_adverse=round(sum(o1["adverse"][k]["net"] for k in idx_out), 2) if idx_out else None)
        pick, why = SR.choose(recs)
        best = next((r for r in recs if r["id"] == pick), None)
        anat["en105"][str(s)] = dict(components=chosen, genotypes=recs, outer=outer, one_lot=onelot, pick=pick, why=why,
                                     ablation=ablation(recs, outer))
        sel.setdefault("EN105", {})[s] = dict(pick=pick, why=why, genotype=best["genotype"] if best else None)
        for k in idx_in + idx_out:                                        # free composed arrays except the chosen genotype
            t = book[k]
            for key in [x for x in t.sig9 if x.startswith(f"EN105|s{s}|") and (pick is None or not x.startswith(pick))]:
                t.sig9.pop(key, None); t.meta9.pop(key, None); t.logs9.pop(key, None)
        log("EN105", s, pick)
    res["stageb"]["selections"]["EN105"] = {str(s): v for s, v in sel["EN105"].items()}
    # ---------------- stitched outer wallets and outer paired results
    stitched = {}
    for fam in [f for f in res["families"]]:
        ref = F.FAMILY_REFERENCE[fam]; picks = sel[fam]
        pol = []
        for k in range(SR.INITIAL, n):
            s = max(b for b in bounds if b <= k); pol.append(picks[s]["pick"] or ref)
        pairs = [(book[k], nr[c]) for k, c in zip(range(SR.INITIAL, n), pol)]
        refp = [(book[k], nr[ref]) for k in range(SR.INITIAL, n)]
        out = {}
        for sc in ("ordinary", "adverse"):
            w = lab9.wallet_steps(pairs, sc); wr = lab9.wallet_steps(refp, sc)
            out["wallet_" + sc] = {k: w[k] for k in ("P", "swept", "liq_dd", "halted", "first_halt")}
            out["reference_wallet_" + sc] = {k: wr[k] for k in ("P", "swept", "liq_dd", "halted", "first_halt")}
            a = [nb[c][sc][k] for k, c in zip(range(SR.INITIAL, n), pol)]; b = [nb[ref][sc][k] for k in range(SR.INITIAL, n)]
            out["indep_" + sc] = dict(net=round(sum(d["net"] for d in a), 2), reference=round(sum(d["net"] for d in b), 2),
                                      parents=sum(d["trades"] for d in a), without_top2=round(SR.without_top2([d["net"] for d in a]), 2),
                                      paired=paired(days[SR.INITIAL:], a, b))
        out["policy"] = pol; out["fallback_folds"] = sum(picks[s]["pick"] is None for s in bounds)
        for ctl in ("REF:E03_env", "REF:E032_native", "REF:EN87"):
            for sc in ("ordinary", "adverse"):
                w = lab9.wallet_steps([(book[k], nr[ctl]) for k in range(SR.INITIAL, n)], sc)
                out.setdefault("context_wallets", {})[f"{ctl}|{sc}"] = {k: w[k] for k in ("P", "liq_dd", "halted", "first_halt")}
        stitched[fam] = out
    res["stitched"] = stitched
    log("stitched done")
    res["labels"], res["champions"] = label(res, reg, nb, book, sel)
    return res, anat


def ablation(recs, outer):
    by = {r["genotype"]: r for r in recs}; out = {}
    for k, name in enumerate(SR.GENES):
        d_in, d_out = [], []
        for g in by:
            if g[k] == "0":
                h = g[:k] + "1" + g[k + 1:]
                d_in.append(by[h]["inner_adverse"] - by[g]["inner_adverse"])
                if outer:
                    d_out.append(outer[h]["adverse"] - outer[g]["adverse"])
        out[name] = dict(inner_adverse_mean_change=round(float(np.mean(d_in)), 2), outer_adverse_mean_change=round(float(np.mean(d_out)), 2) if d_out else None,
                         identical_pairs=sum(1 for g in by if g[k] == "0" and by[g]["hash"] == by[g[:k] + "1" + g[k + 1:]]["hash"]))
    pairs = {}
    for a in range(6):
        for b in range(a + 1, 6):
            vals = []
            for g in by:
                if g[a] == "0" and g[b] == "0":
                    s = list(g); g10 = s.copy(); g10[a] = "1"; g01 = s.copy(); g01[b] = "1"; g11 = s.copy(); g11[a] = "1"; g11[b] = "1"
                    f = lambda x: by["".join(x)]["inner_adverse"]
                    vals.append(f(g11) - f(g10) - f(g01) + f(s))
            pairs[f"{SR.GENES[a]}x{SR.GENES[b]}"] = round(float(np.mean(vals)), 2)
    out["pair_interactions_inner_adverse"] = pairs
    return out


def numeric_axis(values):
    return all(isinstance(v, (int, float)) or v == "UNBOUNDED" for v in values)


def neighbours(reg, cid):
    c = next(x for x in reg if x.id == cid)
    fam = json.loads((HERE / ("families9.json" if int(c.family[2:]) <= 105 else "families9-own.json")).read_text())
    block = next(b for f in fam["families"] if f["slot"] == c.family for b in f["blocks"] if b["id"] == c.block)
    out = []
    for ax, vals in block["axes"].items():
        if not numeric_axis(vals) or len(vals) < 2:
            continue
        k = vals.index(c.settings[ax])
        for j in (k - 1, k + 1):
            if 0 <= j < len(vals):
                st = dict(c.settings, **{ax: vals[j]})
                hit = [x.id for x in reg if x.family == c.family and x.block == c.block and x.settings == st]
                out += hit
    return out


def label(res, reg, nb, book, sel):
    labels = {}; cands = []
    for fam, info in res["families"].items():
        st = res["stitched"][fam]; ref = info["reference"]
        folds = [sel[fam][s]["pick"] for s in res["stageb"]["boundaries"]]
        picked = [p for p in folds if p]
        mode = Counter(picked).most_common(1)[0][0] if picked else None
        cells = [c.id for c in reg if c.family == fam and c.kind == "CELL" and f"{c.id}|NIFTY" in res["configs"]]
        pos = [c for c in cells if res["configs"][f"{c}|NIFTY"].get("vs_reference", {}).get("adverse", {}).get("mean", 0) > 0]
        nonref = [c for c in cells if "vs_reference" in res["configs"][f"{c}|NIFTY"] and res["configs"][f"{c}|NIFTY"]["vs_reference"]["tickets"]["matched_changed"]
                  + res["configs"][f"{c}|NIFTY"]["vs_reference"]["tickets"]["candidate_only"] + res["configs"][f"{c}|NIFTY"]["vs_reference"]["tickets"]["reference_only"] > 0]
        share = len([c for c in pos if c in nonref]) / len(nonref) if nonref else 0.
        med = float(np.median([res["configs"][f"{c}|NIFTY"]["vs_reference"]["adverse"]["mean"] for c in nonref])) if nonref else 0.
        plateau = None
        if mode and fam != "EN105":
            nbs = neighbours(reg, mode)
            vals = [res["configs"][f"{x}|NIFTY"]["vs_reference"]["adverse"]["mean"] for x in nbs if f"{x}|NIFTY" in res["configs"] and "vs_reference" in res["configs"][f"{x}|NIFTY"]]
            plateau = dict(cell=mode, neighbours=nbs, positive=sum(v > 0 for v in vals), share=round(sum(v > 0 for v in vals) / len(vals), 3) if vals else None)
        full = res["configs"].get(f"{mode}|NIFTY") if mode and fam != "EN105" else None
        dev = (st["wallet_ordinary"]["P"] > 0 and st["wallet_adverse"]["P"] > 0 and not st["wallet_ordinary"]["halted"] and not st["wallet_adverse"]["halted"]
               and st["wallet_adverse"]["P"] >= st["reference_wallet_adverse"]["P"] and st["indep_adverse"]["paired"]["mean"] > 0
               and st["indep_ordinary"]["parents"] >= 10)
        if fam != "EN105":
            dev = dev and plateau is not None and (plateau["share"] or 0) >= .5 and full is not None and full["adverse"]["net"] > 0 \
                and full["ordinary"]["without_top2"] >= 0 and not full["wallet"]["ordinary"]["halted"] and not full["wallet"]["adverse"]["halted"]
        if st["fallback_folds"] >= 3:
            lab = "INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds)"
        elif dev:
            lab = "DEVELOPMENT CANDIDATE — studied data only"; cands.append(fam)
        elif share >= .5 and med > 0:
            lab = "MECHANISM ONLY — most cells beat the reference on the full grid, the chronological selection did not hold"
        else:
            lab = "NO IMPROVEMENT"
        labels[fam] = dict(label=lab, most_selected=mode, fold_picks=folds, final_pick=sel[fam][res["stageb"]["final"]]["pick"],
                           grid_share_positive=round(share, 3), grid_median_adverse_gain=round(med, 3), plateau=plateau,
                           stitched_gain_adverse=round(st["wallet_adverse"]["P"] - st["reference_wallet_adverse"]["P"], 2))
    champs = []
    for cat in ("profit", "risk"):
        pool = [f for f in cands if CATEGORY[f] == cat and labels[f]["final_pick"]]
        if pool:
            f = max(pool, key=lambda f: (labels[f]["stitched_gain_adverse"], f))
            champs.append(dict(family=f, category=cat, config=labels[f]["final_pick"], reference=res["families"][f]["reference"]))
    return labels, champs


def summarize_logs(book, reg):
    out = defaultdict(Counter)
    for t in book:
        for key, logs in t.logs9.items():
            for x in logs:
                if "status" in x:
                    out[key][x["status"]] += 1
                elif "kept" in x:
                    out[key]["KEPT" if x["kept"] else "DROPPED"] += 1
    return {k: dict(v) for k, v in out.items()}


# ------------------------------------------------------------------ diagnostics (descriptive, after the score's main loop)
def diagnostics(B, res, anat):
    import execution8
    book = B["NIFTY"]; out = {}
    rows = []
    for t in book:
        q = t.q9["REF"]; S = t.S9[F.skey(S9.REF_REP)]
        for i in np.flatnonzero(t.e03):
            d = int(t.e03[i])
            if not (np.isfinite(q) and q > 0 and np.isfinite(S[i])):
                continue
            z = d * S[i] / q
            for sc in ("ordinary", "adverse"):
                a = execution8.fixed_action(t, int(i), d, L7.E03_ENV, sc)
                if a["status"] == "FILLED":
                    rows.append((sc, z, a["net"]))
    bins = [(-9, 0), (0, 1), (1, 1.5), (1.5, 2), (2, 99)]
    out["EN109_dose_response_one_lot_8min"] = {sc: [dict(z=f"[{a},{b})", n=sum(1 for s, z, v in rows if s == sc and a <= z < b),
                                                       mean=round(float(np.mean([v for s, z, v in rows if s == sc and a <= z < b])), 2) if any(s == sc and a <= z < b for s, z, v in rows) else None)
                                                  for a, b in bins] for sc in ("ordinary", "adverse")}
    # EN96: activity-matched random retention of E03 signals (40 seeds), per (quarter, 30-minute) bin
    import random
    en87 = res["configs"]["REF:EN87|NIFTY"]; dist = []
    def binof(t, i):
        return (t.day[:4] + "Q" + str((int(t.day[5:7]) - 1) // 3 + 1), int(t.minute[i]) // 30)
    elig = defaultdict(list); kept = Counter()
    for k, t in enumerate(book):
        q = t.q9["REF"]; S = t.S9[F.skey(S9.REF_REP)]
        for i in np.flatnonzero(t.e03 & S9.window(t)):
            if np.isfinite(q) and np.isfinite(S[i]):
                elig[binof(t, i)].append((k, int(i), int(t.e03[i])))
                if t.signals8["GATE"][i]:
                    kept[binof(t, i)] += 1
    for seed in range(40):
        rng = random.Random(9640 + seed); pick = defaultdict(dict)
        for b, xs in elig.items():
            for k, i, d in rng.sample(xs, min(kept[b], len(xs))):
                pick[k][i] = d
        tot = {"ordinary": 0., "adverse": 0.}
        for k, t in enumerate(book):
            a = np.zeros(t.n, np.int8)
            for i, d in pick[k].items():
                a[i] = d
            t.sig9["DIAG:random"] = a; t.meta9["DIAG:random"] = {}
            r = lab9.R9(L7.E03_ENV, sig9="DIAG:random")
            for sc in tot:
                tot[sc] += lab9.run_day9(t, r, sc, 30000., 2500.)["net"]
        dist.append(tot)
    for t in book:
        t.sig9.pop("DIAG:random", None); t.meta9.pop("DIAG:random", None)
    for sc in ("ordinary", "adverse"):
        v = sorted(x[sc] for x in dist); obs = en87[sc]["net"]
        out.setdefault("EN96_random_retention", {})[sc] = dict(seeds=40, median=round(float(np.median(v)), 2), p90=round(float(np.percentile(v, 90)), 2),
                                                               en87=obs, en87_rank=sum(x < obs for x in v))
    out["EN96_random_retention"]["eligible_signals"] = sum(len(v) for v in elig.values()); out["EN96_random_retention"]["kept_signals"] = sum(kept.values())
    # EN97: basket diagnostics at EN87 events and the leave-traded-pair test
    diag = []; ltp = Counter()
    tk = {(x["day"], x["m"], x["d"]): x for x in anat["tickets"]["REF:EN87|NIFTY"]}
    for t in book:
        for i in np.flatnonzero(t.signals8["GATE"]):
            d = int(t.signals8["GATE"][i]); dg = S9.rep_diagnostics(t, S9.REF_REP, int(i)); diag.append(dg)
            x = tk.get((t.day, int(t.minute[i]), d))
            if x:
                pairs = [(c, p) for c, p in data8.basket(t, int(i)) if float(t.strikes[c]) != x["K"] and float(t.strikes[p]) != x["K"]]
                s = S9.ref_score(t, int(i), 15, pairs) if len(pairs) >= 3 else math.nan
                ltp["still_agrees" if np.isfinite(s) and d * s > t.q9["REF"] else "unavailable" if not np.isfinite(s) else "no_longer_agrees"] += 1
    out["EN97_reference_basket"] = dict(events=len(diag), mean_valid_pairs=round(float(np.mean([x["valid_pairs"] for x in diag])), 3),
                                        mean_largest_share=round(float(np.nanmean([x.get("largest_share") or np.nan for x in diag])), 3),
                                        atm_changed_share=round(float(np.mean([bool(x.get("atm_changed")) for x in diag])), 3),
                                        leave_traded_pair_out=dict(ltp))
    # EN96 companion: every EN96 cell on the common support where all 32 cells have a valid threshold (H=40 warmup)
    keys = [F.qkey(F.skey(F.STD(L)), H, p) for L in S9.LOOKBACKS for H in F.HS for p in F.PS]
    common = [k for k, t in enumerate(book) if all(np.isfinite(t.q9[x]) for x in keys)]
    rows = {}
    for key, row in res["configs"].items():
        cid, u = key.rsplit("|", 1)
        if u != "NIFTY" or row["family"] != "EN96" or row["kind"] != "CELL":
            continue
        dd = anat["days"][key]; rr = anat["days"]["REF:EN87|NIFTY"]
        rows[cid] = dict(ordinary=round(sum(dd["ordinary"][k] for k in common), 2), adverse=round(sum(dd["adverse"][k] for k in common), 2),
                         paired_adverse_mean=round(float(np.mean([dd["adverse"][k] - rr["adverse"][k] for k in common])), 3) if common else None)
    out["EN96_common_40_warmup"] = dict(sessions=len(common), first=book[common[0]].day if common else None,
                                       reference_ordinary=round(sum(anat["days"]["REF:EN87|NIFTY"]["ordinary"][k] for k in common), 2),
                                       reference_adverse=round(sum(anat["days"]["REF:EN87|NIFTY"]["adverse"][k] for k in common), 2), cells=rows)
    # EN99 expired-arm markouts (missed opportunity): bid at +8 minus event ask, one lot, per arm status
    mk = defaultdict(list)
    for t in book:
        sp = L4.spec_of(t)
        for key, logs in t.logs9.items():
            if not key.startswith("EN99:"):
                continue
            for x in logs:
                if x.get("status") in ("TTL_EXPIRED", "INFORMATION_LOST", "WINDOW_END") and "j" in x:
                    b = x["event_i"] + 8
                    if b < t.n and np.isfinite(t.q[b, x["j"], 3]):
                        mk[key].append((L4.bid_of(t.q[b, x["j"], 3]) - x["ask0"]) * sp.lot)
    out["EN99_unfilled_arm_markout_8min_one_lot"] = {k: dict(n=len(v), mean=round(float(np.mean(v)), 2), share_positive=round(float(np.mean([y > 0 for y in v])), 3))
                                                     for k, v in mk.items() if v}
    return out


# ------------------------------------------------------------------ freeze / score / selftest
def load():
    B, bindings = data8.historical_books()
    for u, book in B.items():
        signals8.prepare(book); F.prepare9(book)
    return B, bindings


def freeze():
    if FREEZE.exists():
        raise RuntimeError("freeze9.json exists")
    for name in ("parity9.json", "reproduce9.json", "causal9.json", "unit9.json", "selftest9.json"):
        assert json.loads((HERE / name).read_text())["status"] == "PASS", name
    B, bindings = data8.historical_books()
    reg = F.registry()
    import scipy
    f = dict(head_before_freeze=git("rev-parse", "HEAD"), created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             files={k: data8.sha(p) for k, p in sources().items()}, data=data8.sealed_manifest(B, bindings), arrays=score8.array_manifest(B),
             environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
             counts=F.counts(reg), registry=[dict(id=c.id, family=c.family, block=c.block, kind=c.kind, settings=c.settings, note=c.note,
                                                  spec=asdict(c.spec) if c.spec else None) for c in reg],
             stage_b=dict(initial=SR.INITIAL, outer=SR.OUTER, inner=SR.INNER, inner_blocks=SR.NBLK, boundaries=SR.boundaries(len(B["NIFTY"])),
                          final_boundary=len(B["NIFTY"]), objective="median inner-block paired adverse net per scheduled expiry vs family reference",
                          constraints=["support >=10 funded parents and activity in >=2 inner blocks", "reconciled", "no halt (ordinary, adverse inner wallets)",
                                       "inner wallet P > 0 ordinary and adverse", "inner ordinary net without best two >= 0", "median block improvement >= 0"],
                          tie_break=["lower ordinary liquidation drawdown", "fewer modified components", "variant id"], fallback="family reference"),
             evaluation="development only; all sessions already studied", inference="descriptive only (calibration receipts)",
             champions="at most two in total (one profit/continuation, one risk/entry), IMPL9 section 6")
    write(FREEZE, f); print("FROZEN", len(f["files"]), "files", f["counts"], flush=True)


def verify_freeze():
    f = json.loads(FREEZE.read_text()); bad = [k for k, p in sources().items() if data8.sha(p) != f["files"].get(k)]
    if bad:
        raise RuntimeError("changed frozen files: " + str(bad))
    B, bindings = load()
    assert bindings == f["data"]["files"], "sealed data changed"
    assert score8.array_manifest(B) == f["arrays"], "tape inputs changed"
    return f, B


def score():
    for p in (HERE / "results9.json", HERE / "results9-started.json"):
        if p.exists():
            raise RuntimeError("one-shot score already started; preserve the evidence")
    f, B = verify_freeze()
    st = git("status", "--porcelain", "--", *[str(HERE / x) for x in FILES9], str(FREEZE))
    if st:
        raise RuntimeError("commit frozen code first: " + st)
    fd = os.open(HERE / "results9-started.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(dict(head=git("rev-parse", "HEAD"), freeze_sha256=data8.sha(FREEZE), utc=time.time()), h); h.flush(); os.fsync(h.fileno())
    try:
        reg = F.registry(); res, anat = pipeline(B, reg)
        res["diagnostics"] = diagnostics(B, res, anat)
        res["head"] = git("rev-parse", "HEAD"); res["freeze_sha256"] = data8.sha(FREEZE)
        write(HERE / "results9.json", res); write(HERE / "anatomy9.json", anat)
        with open(HERE / "trials9.jsonl", "w", encoding="utf-8") as fh:
            for c in reg:
                for u in B:
                    key = f"{c.id}|{u}"; row = res["configs"].get(key)
                    fh.write(json.dumps(dict(id=c.id, index=u, family=c.family, block=c.block, kind=c.kind, settings=c.settings,
                                             status="SCORED" if row else res["unavailable"].get(key, "SOURCE_GATED" if not c.spec else "COMPOSED_PER_FOLD" if c.family == "EN105" else "NOT_RUN"),
                                             hash=row["hash"] if row else None, parents=row["ordinary"]["trades"] if row else None,
                                             head=res["head"], freeze=res["freeze_sha256"]), default=str) + "\n")
            for s, v in anat["en105"].items():
                for r in v["genotypes"]:
                    fh.write(json.dumps(dict(id=f"EN105:genotype:{int(r['genotype'], 2) + 1:04d}", boundary=int(s), composed=v["components"], hash=r["hash"],
                                             passed=r["passed"], parents=r["parents"], head=res["head"], freeze=res["freeze_sha256"])) + "\n")
        reg_dir = HERE / "registration9"; reg_dir.mkdir(exist_ok=True)
        for ch in res["champions"]:
            c = next((x for x in reg if x.id == ch["config"]), None)
            if c is None and ch["family"] == "EN105":
                e = anat["en105"][str(res["stageb"]["final"])]; g = tuple(int(x) for x in ch["config"].rsplit("|", 1)[1])
                comp = {k: (next(x for x in reg if x.id == v).spec if v else None) for k, v in e["components"].items()}
                spec = SR.compose(comp, g); settings = dict(genotype=SR.gid(g), components=e["components"])
                rule = F.rule_of(spec, "EN105|champion")
            else:
                spec = c.spec if c else None; settings = c.settings if c else None; rule = c.rule() if c else None
            write(reg_dir / f"{ch['family']}.json", dict(champion=ch, settings=settings, spec=asdict(spec) if spec else None,
                  rule=asdict(rule) if rule else None, status="NOMINATED FOR A NEW PROSPECTIVE TEST ONLY; not qualified, not promoted",
                  forward=dict(primary="paired adverse net per scheduled covered expiry vs its frozen reference", also_required="positive adverse own-cash wallet, no halt",
                               floors=dict(covered_expiries=40, funded_parents=20, max_scheduled=100), indices="index-specific; SENSEX OI-dependent cells unavailable",
                               multiplicity="Holm over the registered champion-index cells", interim="mechanics/risk only, one final review"),
                  freeze_sha256=res["freeze_sha256"], head=res["head"]))
    except BaseException as e:
        write(HERE / "failure9.json", dict(type=type(e).__name__, error=str(e))); raise
    print("SCORE COMPLETE", flush=True)


def selftest():
    """The whole pipeline on a 70-session NIFTY prefix (and 30 SENSEX) with a reduced registry; counts only."""
    B, _ = load()
    B = {"NIFTY": B["NIFTY"][:70], "SENSEX": B["SENSEX"][:30]}
    SR.INITIAL, SR.OUTER, SR.INNER = 40, 10, 18
    reg = F.registry(); keep = []
    seen = Counter()
    for c in reg:
        if c.kind != "CELL" or c.family == "EN105" or seen[c.family] < 3 or c.id.startswith("EN101:ctl:random"):
            keep.append(c); seen[c.family] += c.kind == "CELL"
    keep += [c for c in reg if c.kind != "CELL" and c not in keep]
    res, anat = pipeline(B, keep, verbose=False)
    res["diagnostics"] = diagnostics(B, res, anat)
    ok = bool(res["stageb"]["selections"]) and "EN105" in res["stageb"]["selections"] and all(v["reconciled"] for v in res["configs"].values())
    score8.clean(res); score8.clean(anat)
    out = dict(status="PASS" if ok else "FAIL", configs=len(res["configs"]), unavailable=len(res["unavailable"]), families=len(res["families"]),
               boundaries=res["stageb"]["boundaries"], en105_folds=len(anat["en105"]), labels=len(res["labels"]), dedup=res["dedup_counts"],
               note="truncated registry/calendar; no money printed or used")
    write(HERE / "selftest9.json", out); print("SELFTEST", out["status"], {k: v for k, v in out.items() if k != "note"}, flush=True)


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
