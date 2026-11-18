"""Round-10 freeze and one-shot development score (IMPL10.md sections 6-9). Freeze before any round-10 money exists.

  score10.py selftest   whole pipeline on a truncated registry/calendar; prints counts only, writes selftest10.json
  score10.py freeze     writes freeze10.json (code/data/registry/procedure hashes); refuses if it exists
  score10.py score      once: refuses changed code/data, an uncommitted freeze, or an earlier start
"""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
import hashlib, json, math, os, platform, subprocess, sys, time
import numpy as np
import round10  # noqa: F401
import data8, score8
import score9, stats9
from data8 import L7
import signals9 as S9
import lab10, features10 as FX, families10 as FM, learn10 as LN, data10
L4 = L7.L4
HERE = Path(__file__).resolve().parent
FILES10 = ("IMPL10.md", "families10-proposed.json", "families10-own.json", "round10.py", "lab10.py", "features10.py", "hmm10.py",
           "families10.py", "learn10.py", "data10.py", "score10.py", "phase10.py", "test10.py", "test10_unit.py", "phase0-10.json",
           "PHASE0-10.md")
FREEZE = HERE / "freeze10.json"
SC = ("ordinary", "adverse", "catastrophe")
INITIAL, OUTER, INNER, NBLK = 100, 20, 60, 3
FLOOR = 5
EN117_DEFAULT = "EN117:{:04d}"
LEARNED_FIXED = {"EN118": ("REF:EN87", "REF:E03_env", "EN118:ctl:fixed_nearer_100_8_at_e03", "EN118:ctl:fixed_nearer_150_12_at_e03", "EN111:0018", "EN117_DEFAULT"),
                 "EN120": ("REF:EN87", "EN111:0018", "EN117_DEFAULT", "EN120:ctl:fixed_priority_union"),
                 "EN116": ("REF:EN87", "EN111:0018")}


def git(*a):
    return subprocess.check_output(["git", *a], cwd=HERE, text=True).strip()


def sources():
    out = {f: HERE / f for f in FILES10}
    out["spec/EXPIRY_RESEARCH_EN111_EN120.md"] = HERE.parents[2] / "EXPIRY_RESEARCH_EN111_EN120.md"
    for f in ("round8.py", "signals9.py", "lab9.py", "families9.py", "score9.py", "stats9.py", "search9.py"):
        out["round9/" + f] = HERE.parent / "2026-11-18-expiry-en96" / f
    out.update({"round8/" + k: p for k, p in score8.source_paths().items()})
    return out


write = score9.write


def en117_default(reg):
    return next(c.id for c in reg if c.family == "EN117" and c.kind == "CELL" and c.settings == dict(excursion=.25, target="MIDPOINT", stop_buffer=.5, cost_coverage=2))


# ------------------------------------------------------------------ one configuration
def ticket(t, p):
    x = score9.ticket(t, p)
    x.update(tag=p.get("tag10"), orders=len(p["events"]), first_reason=x["first_exit"],
             A=(p.get("_h114") or {}).get("A"), wall_reached=(p.get("_h125") or {}).get("reached", 0),
             fast_confirm=(p.get("_h113") or {}).get("confirmed", 0), fallback=bool((p.get("_h113") or {}).get("fallback") or (p.get("_h114") or {}).get("fallback")),
             gross=round(p["net"] + p["fees"], 2), premium_at_risk=round(p["reserve"], 2))
    return x


def run_indep(book, rule, idx=None, scen=SC):
    out = {sc: {} for sc in scen}; tickets = []; h = hashlib.sha256(); ok = True; notes = Counter()
    for sc in scen:
        for k in (range(len(book)) if idx is None else idx):
            t = book[k]; det = sc != "catastrophe"
            d = lab10.run_day10(t, rule, sc, 30000., L7.budget_of(rule), det)
            if det:
                h.update(repr(score9.canon_day(d)).encode())
                ok &= abs(sum(p["net"] for p in d["positions"]) - d["net"]) < .02 and all(p["reserve"] <= p["room"] + .02 for p in d["positions"])
                if sc == "ordinary":
                    tickets.extend(ticket(t, p) for p in d["positions"])
                    for n in d["notes_detail"]:
                        notes[n[0]] += 1
            out[sc][k] = score9.slim(d)
    return out, tickets, h.hexdigest()[:20], ok, dict(notes)


def wallet_of(book, rule, idx, sc):
    w = lab10.wallet_steps([(book[k], rule) for k in idx], sc)
    return w


def wsum(w):
    return {k: w[k] for k in ("P", "swept", "wallet", "liq_dd", "halted", "first_halt")}


def quarters(days):
    q = defaultdict(float)
    for d in days:
        q[d["day"][:4] + "Q" + str((int(d["day"][5:7]) - 1) // 3 + 1)] += d["net"]
    return {k: round(v, 2) for k, v in sorted(q.items())}


def reachable(days, w):
    if not w["first_halt"]:
        return None
    s = 0.
    for d in days:
        if d["day"] >= w["first_halt"]:
            break
        s += d["net"]
    return dict(first_halt=w["first_halt"], indep_before_halt=round(s, 2), wallet_P=w["P"], indep_total=round(sum(d["net"] for d in days), 2))


# ------------------------------------------------------------------ dynamic controls (registered by rule in IMPL10)
def rates112(book, reg):
    out = {}
    for c in reg:
        if c.family == "EN112" and c.kind == "CELL":
            ctx, asg, prof, rk = c.spec.bp; n = g = 0
            for t in book[:INITIAL]:
                for i in np.flatnonzero(FM.en87_dirs(t)):
                    n += 1; g += bool(FM.room112(t, i, ctx, asg, rk))
            out[c.id] = g / n if n else 0.
    return out


def dyn112(reg, rates):
    out = []
    for c in reg:
        if c.family == "EN112" and c.kind == "CELL":
            ctx, asg, prof, rk = c.spec.bp
            out.append(FM.Config(f"EN112:dyn:random_{c.id[6:].replace(':', '_')}", "EN112", "control", "DYNAMIC", dict(rate=round(rates[c.id], 6), matches=c.id),
                                 FM.Spec10(build="RND112", bp=(ctx, asg, prof, rk, round(rates[c.id], 6)), needs=("OI",)), ("REF:EN87", c.id),
                                 "random room assignment at the cell's training room rate (dates < 100)"))
    return out


def dyn114(reg, tick):
    out = []
    for c in reg:
        if c.family == "EN114" and c.kind == "CELL":
            tk = [x for x in tick.get(f"{c.id}|NIFTY", []) if x["day"] < BOOK_DAY100]
            h = int(round(float(np.mean([x["hold"] for x in tk])))) if tk else 8
            h = max(1, h); scope = c.spec.kw[2][1][2]
            kw = (("hold", h),) + ((("mg10", "HOLDALL"), ("mgp10", (h,))) if scope == "BASE_AND_RUNNER" else ())
            out.append(FM.Config(f"EN114:dyn:matched_{c.id.split(':')[1]}", "EN114", "control", "DYNAMIC", dict(hold=h, scope=scope, matches=c.id),
                                 FM.Spec10(arm="EN87", kw=kw, needs=("OI",)), ("REF:EN87", c.id), "fixed hold = the cell's mean training holding minutes"))
    return out


BOOK_DAY100 = None
REASON = {}


# ------------------------------------------------------------------ fixed / causal configurations
def run_fixed(B, cfgs, bank, tick, rules, log):
    for c in cfgs:
        if c.spec is None or c.spec.learned:
            continue
        for u, book in B.items():
            key = f"{c.id}|{u}"
            if key in bank:
                continue
            if u == "SENSEX" and not FM.sensex_ok(c.spec):
                bank[key] = None; REASON[key] = "DATA UNAVAILABLE: SENSEX OI not supplied"; continue
            rule = c.rule()
            for t in book:
                FM.build(t, c.spec, c.id, rule)
            out, tk, h, ok, notes = run_indep(book, rule)
            idx = range(len(book))
            w = {sc: wallet_of(book, rule, idx, sc) for sc in ("ordinary", "adverse")}
            stress = None
            if u == "NIFTY":
                rs = replace(rule, entry_delay=rule.entry_delay + 1)
                stress = round(sum(lab10.run_day10(t, rs, "adverse", 30000., L7.budget_of(rs), False)["net"] for t in book), 2)
            bank[key] = dict(ordinary=[out["ordinary"][k] for k in idx], adverse=[out["adverse"][k] for k in idx],
                             catastrophe=[out["catastrophe"][k] for k in idx], hash=h, reconciled=ok, notes=notes,
                             wallet={sc: wsum(v) for sc, v in w.items()}, wallet_days={sc: [(x["P"], x["scale"]) for x in v["days"]] for sc, v in w.items()},
                             entry_plus1_adverse=stress, first=0)
            tick[key] = tk; rules[key] = rule
        log("fixed", c.id)


# ------------------------------------------------------------------ learned configurations
class Learner:
    """Walk-forward fits for one learned configuration on one index (fits cached by fit date)."""

    def __init__(self, cfg, book, labels, u):
        self.cfg, self.book, self.labels, self.u = cfg, book, labels, u
        self.kind = cfg.spec.learned; self.bp = cfg.spec.bp; self.cache = {}

    def train(self, f):
        return [e for k in range(f) for e in self.labels[k]]

    def model(self, f):
        if f not in self.cache:
            if self.kind == "EN118":
                learner, reg, k, feats = self.bp
                self.cache[f] = LN.Model118(learner, reg, k, feats, self.train(f), f, seed=1180000 + f)
            else:
                self.cache[f] = LN.Model120(self.bp[0], self.train(f), f, seed=1200000 + f)
        return self.cache[f]

    def segment(self, start, dates, key):
        """Write policy arrays for `dates` (a contiguous segment beginning at `start`) under array key `key`.
        EN118: one fit at `start`. EN120: refit every cadence dates from `start`; margin state persists through the segment."""
        logs = []
        if self.kind == "EN118":
            m = self.model(start)
            for k in dates:
                t = self.book[k]; choice, lg = LN.policy118(m, self.labels[k]); LN.write_policy(t, key, choice); logs.append((k, m.id, lg))
            return logs
        if self.bp[0] == "UNION":
            for k in dates:
                t = self.book[k]; LN.write_policy(t, key, LN.union_policy(self.labels[k])); logs.append((k, "UNION", []))
            return logs
        if self.bp[0] == "PASTPNL":
            for k in dates:
                t = self.book[k]; p = self.pastpnl[k]
                evs = self.labels[k]; ch = {}
                for e in sorted(evs, key=lambda e: e["i"]):
                    if e["i"] in ch:
                        continue
                    if p in ("EN87", "EN111") and e["en87"]:
                        ch[e["i"]] = (LN.PROFILES120[p], e["d"], None)
                    elif p == "EN117" and e["setup"] == "RANGE":
                        ch[e["i"]] = ("RANGE", e["d"], e["levels"])
                LN.write_policy(t, key, ch); logs.append((k, p, []))
            return logs
        depth, cadence, margin = self.bp; state = {"current": "EN87"}
        for n, k in enumerate(dates):
            f = start + (n // cadence) * cadence
            m = self.model(f); t = self.book[k]
            choice, lg = LN.policy120(m, self.labels[k], margin, state); LN.write_policy(t, key, choice); logs.append((k, m.id, lg))
        return logs


def outer_dates(n):
    return list(range(INITIAL, n))


def boundaries(n):
    return list(range(INITIAL, n, OUTER))


def blocks_of(s):
    idx = list(range(s - INNER, s)); k = INNER // NBLK
    return [idx[b * k:(b + 1) * k] for b in range(NBLK)]


def run_learned(B, cfgs, labels, bank, tick, rules, seg_rules, fixed_adverse, log):
    """Per learned config and index: outer walk-forward path (dates 100..n-1) plus inner windows for each boundary."""
    learners = {}
    for c in cfgs:
        if c.spec is None or not c.spec.learned:
            continue
        for u, book in B.items():
            key = f"{c.id}|{u}"
            if u == "SENSEX" and not FM.sensex_ok(c.spec):
                bank[key] = None; REASON[key] = "DATA UNAVAILABLE: SENSEX OI not supplied"; continue
            if len(book) < INITIAL + 1:
                bank[key] = None; REASON[key] = f"{u}: {len(book)} dates < the {INITIAL}-date walk-forward start"; continue
            n = len(book); L = Learner(c, book, labels[u], u)
            if c.spec.learned == "EN120" and c.spec.bp[0] == "PASTPNL":
                L.pastpnl = pastpnl_choice(fixed_adverse, n)
            learners[key] = L
            # outer path (UNION / PASTPNL fit nothing: full calendar from date 0)
            logs = []; full = c.spec.learned == "EN120" and c.spec.bp[0] in ("UNION", "PASTPNL")
            if full:
                logs += L.segment(0, list(range(n)), f"{c.id}|o")
            elif c.spec.learned == "EN118":
                for s in boundaries(n):
                    ds = list(range(s, min(s + OUTER, n))); kk = f"{c.id}|o"
                    logs += L.segment(s, ds, kk)
            else:
                logs += L.segment(INITIAL, outer_dates(n), f"{c.id}|o")
            rule = lab10.R10(L7.E03_ENV, sig9=f"{c.id}|o")
            idx = list(range(n)) if full else outer_dates(n)
            out, tk, h, ok, notes = run_indep(book, rule, idx)
            w = {sc: wallet_of(book, rule, idx, sc) for sc in ("ordinary", "adverse")}
            rs = replace(rule, entry_delay=1)
            stress = round(sum(lab10.run_day10(book[k], rs, "adverse", 30000., 2500., False)["net"] for k in idx), 2) if u == "NIFTY" else None
            bank[key] = dict(ordinary=[out["ordinary"][k] for k in idx], adverse=[out["adverse"][k] for k in idx], catastrophe=[out["catastrophe"][k] for k in idx],
                             hash=h, reconciled=ok, notes=notes, wallet={sc: wsum(v) for sc, v in w.items()},
                             wallet_days={sc: [(x["P"], x["scale"]) for x in v["days"]] for sc, v in w.items()}, entry_plus1_adverse=stress, first=idx[0],
                             decisions=summ_logs(logs), models=sorted({x[1] for x in logs}))
            tick[key] = tk; rules[key] = rule
            # inner windows per boundary (fits strictly before each inner block)
            for s in ([] if full else boundaries(n) + [n]):
                if c.spec.learned == "EN118":
                    for b in blocks_of(s):
                        kk = f"{c.id}|f{b[0]}"
                        if kk not in seg_rules:
                            L.segment(b[0], b, kk); seg_rules[kk] = lab10.R10(L7.E03_ENV, sig9=kk)
                else:
                    kk = f"{c.id}|w{s}"
                    L.segment(s - INNER, list(range(s - INNER, s)), kk); seg_rules[kk] = lab10.R10(L7.E03_ENV, sig9=kk)
            log("learned", key, bank[key]["decisions"])
    return learners


def summ_logs(logs):
    c = Counter()
    for k, mid, lg in logs:
        for i, what in lg:
            c[what] += 1
    return dict(c)


def pastpnl_choice(fixed_adverse, n):
    """EN79-style: each date's profile = best cumulative adverse P&L of the fixed profile ledgers on earlier dates (ties EN87)."""
    out = {}; cum = {p: 0. for p in fixed_adverse}
    for k in range(n):
        best = max(cum.items(), key=lambda kv: (round(kv[1], 6), kv[0] == "EN87"))
        out[k] = best[0] if best[1] > cum["EN87"] + 1e-9 else "EN87"
        for p in cum:
            cum[p] += fixed_adverse[p][k]["net"]
    return out


# ------------------------------------------------------------------ selection (IMPL10 4.11)
def inner_record(book, bank, seg_rules, cid, rule, s, learned, ref_id="REF:EN87"):
    blocks = blocks_of(s); idx = [k for b in blocks for k in b]
    ref = bank[f"{ref_id}|NIFTY"] if ref_id != "CASH" else dict(adverse=[dict(net=0.)] * len(book), first=0)
    if learned == "EN118":
        rk = {k: seg_rules[f"{cid}|f{b[0]}"] for b in blocks for k in b}
    elif learned == "EN120":
        rk = {k: seg_rules[f"{cid}|w{s}"] for k in idx}
    else:
        rk = {k: rule for k in idx}
    if learned:
        o = {}; a = {}
        for k in idx:
            o[k] = lab10.run_day10(book[k], rk[k], "ordinary", 30000., 2500., False)
            a[k] = lab10.run_day10(book[k], rk[k], "adverse", 30000., 2500., False)
    else:
        f = bank[f"{cid}|NIFTY"]; o = {k: f["ordinary"][k - f["first"]] for k in idx}; a = {k: f["adverse"][k - f["first"]] for k in idx}
    impr = [float(np.mean([a[k]["net"] - ref["adverse"][k - ref["first"]]["net"] for k in b])) for b in blocks]
    wo = lab10.wallet_steps([(book[k], rk[k]) for k in idx], "ordinary"); wa = lab10.wallet_steps([(book[k], rk[k]) for k in idx], "adverse")
    parents = sum(o[k]["trades"] for k in idx)
    checks = dict(support=parents >= FLOOR, no_halt=wo["halted"] == 0 and wa["halted"] == 0)
    return dict(id=cid, objective=round(float(np.median(impr)), 4), blocks=[round(x, 3) for x in impr], parents=parents,
                wallet_ordinary=wo["P"], wallet_adverse=wa["P"], checks=checks, passed=all(checks.values()))


def select(book, bank, rules, seg_rules, cells, fixed, s, learned, ref_id="REF:EN87"):
    recs = [inner_record(book, bank, seg_rules, c, rules.get(f"{c}|NIFTY"), s, learned, ref_id) for c in cells if bank.get(f"{c}|NIFTY")]
    frecs = [inner_record(book, bank, seg_rules, c, rules.get(f"{c}|NIFTY"), s, None, ref_id) for c in fixed if bank.get(f"{c}|NIFTY")]
    ok = sorted([r for r in recs if r["passed"]], key=lambda r: (-r["objective"], r["id"]))
    fok = sorted([r for r in frecs if r["passed"]], key=lambda r: (-r["objective"], r["id"]))
    if ok and (not fok or ok[0]["objective"] > fok[0]["objective"] + 1e-12):
        pick, why = ok[0]["id"], "LEARNED_OR_CELL"
    elif fok:
        pick, why = fok[0]["id"], "FIXED_COMPARATOR"
    else:
        pick, why = "REF:EN87", "FALLBACK"
    return dict(pick=pick, why=why, passed=len(ok), candidates=len(recs), best_cell=ok[0]["id"] if ok else None,
                best_cell_objective=ok[0]["objective"] if ok else None, best_fixed=fok[0]["id"] if fok else None,
                best_fixed_objective=fok[0]["objective"] if fok else None), recs + frecs


def stitched(book, bank, rules, sel, n, learned_ids, ref_id="REF:EN87"):
    pairs = []; pol = []
    for k in range(INITIAL, n):
        s = max(b for b in boundaries(n) if b <= k); p = sel[s]["pick"]; pol.append(p)
        pairs.append((book[k], rules[f"{p}|NIFTY"]))           # learned rules point at their outer walk-forward arrays
    out = dict(reference=ref_id)
    for sc in ("ordinary", "adverse"):
        w = lab10.wallet_steps(pairs, sc)
        out["wallet_" + sc] = wsum(w)
        if ref_id == "CASH":
            out["reference_wallet_" + sc] = dict(P=0., swept=0., wallet=30000., liq_dd=0., halted=0, first_halt=None); b = [0.] * (n - INITIAL)
        else:
            wr = lab10.wallet_steps([(book[k], rules[f"{ref_id}|NIFTY"]) for k in range(INITIAL, n)], sc)
            out["reference_wallet_" + sc] = wsum(wr); b = [indep_day(bank, ref_id, k, sc) for k in range(INITIAL, n)]
        a = [indep_day(bank, p, k, sc) for k, p in zip(range(INITIAL, n), pol)]
        diff = [x - y for x, y in zip(a, b)]
        out["indep_" + sc] = dict(net=round(sum(a), 2), reference=round(sum(b), 2), paired_mean=round(float(np.mean(diff)), 3),
                                  paired_without_top2=round(score9.SR.without_top2(diff), 2))
    out["policy"] = pol; out["fallback_folds"] = sum(sel[s]["why"] == "FALLBACK" for s in boundaries(n))
    out["fixed_folds"] = sum(sel[s]["why"] == "FIXED_COMPARATOR" for s in boundaries(n))
    return out


def indep_day(bank, cid, k, sc):
    f = bank[f"{cid}|NIFTY"]
    return f[sc][k - f["first"]]["net"]


# ------------------------------------------------------------------ comparisons and labels
def days_of(bank, key, sc, idx):
    f = bank[key]
    return [f[sc][k - f["first"]] for k in idx]


def compare_row(B, bank, tick, key, cid_ref, u):
    book = B[u]; f = bank[key]; idx = list(range(f["first"], len(book)))
    days = [book[k].day for k in idx]
    if cid_ref == "CASH":
        zero = [dict(net=0.) for _ in idx]
        return dict(reference="CASH", ordinary=score9.paired(days, days_of(bank, key, "ordinary", idx), zero),
                    adverse=score9.paired(days, days_of(bank, key, "adverse", idx), zero), changed_parents=sum(d["trades"] for d in days_of(bank, key, "ordinary", idx)))
    rk = f"{cid_ref}|{u}"
    if not bank.get(rk):
        return None
    g = bank[rk]
    if g["first"] > f["first"]:
        return None
    a_o = days_of(bank, key, "ordinary", idx); a_a = days_of(bank, key, "adverse", idx)
    b_o = days_of(bank, rk, "ordinary", idx); b_a = days_of(bank, rk, "adverse", idx)
    tk = score9.compare([x for x in tick[key]], [x for x in tick[rk] if x["day"] >= book[f["first"]].day])
    diff = [x["net"] - y["net"] for x, y in zip(a_a, b_a)]
    years = defaultdict(float)
    for d, v in zip(days, diff):
        years[d[:4]] += v
    return dict(reference=cid_ref, ordinary=score9.paired(days, a_o, b_o), adverse=score9.paired(days, a_a, b_a), tickets=tk,
                changed_parents=tk["matched_changed"] + tk["candidate_only"] + tk["reference_only"],
                adverse_sum=round(sum(diff), 2), adverse_without_top2=round(score9.SR.without_top2(diff), 2),
                adverse_by_year={k: round(v, 2) for k, v in sorted(years.items())}, identical=g["hash"] == f["hash"])


def support_label(n):
    return "ACTIVATION-LIMITED" if n < 5 else "SPARSE ECONOMIC SCREEN" if n < 20 else "SCREENED"


def config_row(B, bank, tick, cfg, u):
    key = f"{cfg.id}|{u}"; f = bank[key]; book = B[u]
    o, a, ca = f["ordinary"], f["adverse"], f["catastrophe"]
    row = dict(family=cfg.family, kind=cfg.kind, block=cfg.block, settings=cfg.settings, note=cfg.note, hash=f["hash"], reconciled=f["reconciled"],
               first_date=book[f["first"]].day, ordinary=score9.metrics(o, tick[key]), adverse=score9.metrics(a), catastrophe=score9.metrics(ca),
               quarters_adverse=quarters(a), losing_dates_adverse=sum(d["net"] < 0 for d in a), wallet=f["wallet"],
               reachable=dict(ordinary=reachable(o, f["wallet"]["ordinary"]), adverse=reachable(a, f["wallet"]["adverse"])),
               entry_plus1_adverse=f["entry_plus1_adverse"], notes=f["notes"], orders=sum(x["orders"] for x in tick[key]),
               premium_at_risk=round(sum(x["premium_at_risk"] for x in tick[key]), 2), decisions=f.get("decisions"))
    row["vs"] = [x for x in (compare_row(B, bank, tick, key, r, u) for r in cfg.comparator) if x]
    if row["vs"]:
        p = row["vs"][0]; row["support"] = support_label(p["changed_parents"]); row["duplicate_of_primary"] = bool(p.get("identical"))
    return row


def candidate_checks(res, reg, cfg, nbh):
    r = res["configs"].get(f"{cfg.id}|NIFTY")
    if not r or not r.get("vs") or cfg.kind != "CELL" or cfg.spec.learned:
        return None
    p = r["vs"][0]
    if p["reference"] == "CASH":
        comp_w = dict(ordinary=dict(P=0., halted=0), adverse=dict(P=0., halted=0)); comp_e1 = 0.
    else:
        cr = res["configs"].get(f"{p['reference']}|NIFTY")
        if not cr:
            return None
        comp_w = cr["wallet"]; comp_e1 = cr["entry_plus1_adverse"]
    yrs = p.get("adverse_by_year", {})
    nb = [res["configs"][f"{x}|NIFTY"]["vs"][0]["adverse"]["mean"] for x in nbh if f"{x}|NIFTY" in res["configs"] and res["configs"][f"{x}|NIFTY"].get("vs")]
    sx = res["configs"].get(f"{cfg.id}|SENSEX")
    sx_ok = True
    if sx and sx.get("vs"):
        v = sx["vs"][0]
        sx_ok = (v["adverse_sum"] if "adverse_sum" in v else v["adverse"]["mean"]) >= 0
    checks = dict(support=p["changed_parents"] >= 20, paired=p["adverse"]["mean"] > 0 and p.get("adverse_without_top2", p["adverse"]["mean"]) >= 0,
                  years=sum(v > 0 for v in yrs.values()) >= 3,
                  wallets=all(r["wallet"][sc]["halted"] == 0 and r["wallet"][sc]["P"] >= comp_w[sc]["P"] for sc in ("ordinary", "adverse")),
                  plateau=bool(nb) and sum(v > 0 for v in nb) >= len(nb) / 2,
                  entry_plus1=r["entry_plus1_adverse"] is not None and comp_e1 is not None and r["entry_plus1_adverse"] > comp_e1,
                  sensex=sx_ok)
    return dict(checks=checks, passed=all(checks.values()), score=round(p.get("adverse_without_top2", 0.) / max(1, r["adverse"]["sessions"]), 3),
                neighbours=len(nb), neighbours_positive=sum(v > 0 for v in nb))


def learned_candidate(st):
    ok = (st["wallet_adverse"]["halted"] == 0 and st["wallet_adverse"]["P"] > st["reference_wallet_adverse"]["P"]
          and st["indep_adverse"]["paired_mean"] > 0 and st["indep_adverse"]["paired_without_top2"] >= 0 and st["fallback_folds"] <= 2
          and st["fixed_folds"] == 0)
    return ok


# ------------------------------------------------------------------ the pipeline
def pipeline(B, reg, verbose=True, limit_learned=None):
    t0 = time.time(); log = (lambda *x: print(f"[{time.time() - t0:.0f}s]", *x, flush=True)) if verbose else (lambda *x: None)
    global BOOK_DAY100
    BOOK_DAY100 = B["NIFTY"][INITIAL].day if len(B["NIFTY"]) > INITIAL else "9999"
    res = dict(evaluation="DEVELOPMENT ONLY: every session already studied; no qualification", configs={}, unavailable={},
               data_limits={"SENSEX": "OI not supplied: OI-dependent configurations DATA UNAVAILABLE",
                            "EN119": "SOURCE-GATED: >=20 synchronized packet expiries required; TR01 Nov 16-17 exports only (1-2 sessions)"},
               inference="DESCRIPTIVE ONLY (round-9 calibration receipts show over-rejection)")
    bank, tick, rules, seg_rules = {}, {}, {}, {}
    reg = list(reg)
    rates = rates112(B["NIFTY"], reg); reg += dyn112(reg, rates)
    assert len({c.id for c in reg}) == len(reg), "duplicate configuration ids"
    order = [c for c in reg if c.kind == "REFERENCE"] + [c for c in reg if c.kind != "REFERENCE"]
    run_fixed(B, [c for c in order if c.spec is not None and not c.spec.learned], bank, tick, rules, lambda *x: None)
    log("fixed done", sum(1 for v in bank.values() if v))
    d114 = dyn114(reg, tick); reg += d114
    run_fixed(B, d114, bank, tick, rules, lambda *x: None)
    log("dynamic EN114 done")
    labels = {u: LN.label_events(book) for u, book in B.items()}
    res["label_counts"] = {u: dict(events=sum(len(v) for v in lab.values()), dates=sum(1 for v in lab.values() if v)) for u, lab in labels.items()}
    log("labels", res["label_counts"])
    e117 = en117_default(reg)
    fixed_adverse = {"EN87": bank["REF:EN87|NIFTY"]["adverse"], "EN111": bank["EN111:0018|NIFTY"]["adverse"], "EN117": bank[f"{e117}|NIFTY"]["adverse"]}
    learned = [c for c in reg if c.spec is not None and c.spec.learned]
    if limit_learned is not None:
        learned = learned[:limit_learned]
    learners = run_learned(B, learned, labels, bank, tick, rules, seg_rules, fixed_adverse, log)
    log("learned done", len(learners))
    for c in reg:
        for u in B:
            key = f"{c.id}|{u}"
            if c.spec is None:
                res["unavailable"][key] = "SOURCE_GATED"; continue
            if key not in bank:
                continue
            if bank[key] is None:
                res["unavailable"][key] = REASON.get(key, "NOT RUN"); continue
            res["configs"][key] = config_row(B, bank, tick, c, u)
    log("rows done", len(res["configs"]))
    groups = defaultdict(list)
    for key, b in bank.items():
        if b:
            groups[(key.rsplit("|", 1)[1], b["hash"], b["first"])].append(key.rsplit("|", 1)[0])
    res["dedup"] = {u: [sorted(v) for (uu, _, _), v in groups.items() if uu == u and len(v) > 1] for u in B}
    res["dedup_counts"] = {u: dict(configs=sum(1 for k, v in bank.items() if v and k.endswith("|" + u)), distinct=sum(1 for (uu, _, _) in groups if uu == u)) for u in B}
    # selection: learned families and views for every family
    book = B["NIFTY"]; n = len(book); bounds = boundaries(n) + [n]
    res["selection"] = {}; anat_sel = {}
    fams = sorted({c.family for c in reg if c.kind == "CELL" and c.spec is not None}, key=lambda f: int(f[2:]))
    for fam in fams:
        cells = [c.id for c in reg if c.family == fam and c.kind == "CELL" and c.spec is not None and bank.get(f"{c.id}|NIFTY")]
        if not cells:
            continue
        lk = next((c.spec.learned for c in reg if c.family == fam and c.kind == "CELL" and c.spec is not None), "")
        prim = next(c.comparator[0] for c in reg if c.family == fam and c.kind == "CELL" and c.spec is not None)
        fixed = [x.replace("EN117_DEFAULT", e117) for x in LEARNED_FIXED.get(fam, (prim, "REF:EN87"))]
        fixed = [x for x in dict.fromkeys(fixed) if x != "CASH" and x not in cells]
        sel = {}; recs = {}; ref_id = "REF:EN87" if fam in LEARNED_FIXED else prim
        for s in bounds:
            sel[s], recs[str(s)] = select(book, bank, rules, seg_rules, cells, fixed, s, lk if lk else None, ref_id)
        st = stitched(book, bank, rules, sel, n, cells, ref_id)
        res["selection"][fam] = dict(view="LEARNED-POLICY SELECTION (IMPL10 4.11)" if fam in LEARNED_FIXED else "CHRONOLOGICAL VIEW (descriptive)",
                                     fixed_comparators=fixed, picks={str(s): v for s, v in sel.items()}, stitched=st)
        anat_sel[fam] = recs
        log("selection", fam, [sel[s]["pick"] for s in bounds])
    # nomination
    cands = []
    res["candidates"] = {}
    for c in reg:
        if c.kind == "CELL" and c.spec is not None and not c.spec.learned:
            ck = candidate_checks(res, reg, c, FM.neighbours(reg, c))
            if ck:
                res["candidates"][c.id] = ck
                if ck["passed"]:
                    cands.append((ck["score"], c.id))
    for fam in ("EN116", "EN118", "EN120"):
        if fam in res["selection"]:
            st = res["selection"][fam]["stitched"]; ok = learned_candidate(st)
            res["candidates"][fam + ":procedure"] = dict(passed=ok, stitched_gain_adverse=round(st["wallet_adverse"]["P"] - st["reference_wallet_adverse"]["P"], 2))
            if ok:
                cands.append((round(st["indep_adverse"]["paired_without_top2"] / max(1, n - INITIAL), 3), fam + ":procedure"))
    cands.sort(key=lambda x: (-x[0], x[1]))
    res["champions"] = [dict(config=c, score=s) for s, c in cands[:2]]
    res["registry_counts"] = FM.counts(reg)
    anat = dict(days={k: dict(ordinary=[d["net"] for d in v["ordinary"]], adverse=[d["net"] for d in v["adverse"]], trades=[d["trades"] for d in v["ordinary"]],
                              first=v["first"], wallet_ordinary=v["wallet_days"]["ordinary"]) for k, v in bank.items() if v},
                tickets=tick, selection=anat_sel)
    res["diagnostics"] = diagnostics(B, res, bank, tick, labels, learners, reg)
    return res, anat, reg


# ------------------------------------------------------------------ diagnostics (descriptive)
def diagnostics(B, res, bank, tick, labels, learners, reg):
    out = {}
    book = B["NIFTY"]
    # EN116 forecast: next-5-minute |dF|/ATR and ER by state
    fc = {}
    for c in reg:
        if c.family == "EN116" and c.kind == "CELL":
            K, refit, pers, v = c.spec.bp; rows = {True: [], False: []}
            for t in book:
                a = FM.state116(t, K, refit, pers, v)
                if a is None:
                    continue
                F = t.f[:, 3]; A = t.features[10][:, 4]
                for i in np.flatnonzero(FX.window(t)):
                    if i + 5 < t.n and np.isfinite([F[i], F[i + 5], A[i]]).all() and A[i] > 0:
                        w = F[i:i + 6]; den = float(np.abs(np.diff(w)).sum())
                        if np.isfinite(w).all():
                            rows[bool(a[i])].append((abs(F[i + 5] - F[i]) / A[i], abs(w[-1] - w[0]) / den if den > 0 else 0.))
            allr = rows[True] + rows[False]
            fc[c.id] = {k: dict(n=len(v), move=round(float(np.mean([x[0] for x in v])), 4) if v else None, er=round(float(np.mean([x[1] for x in v])), 4) if v else None)
                        for k, v in (("active", rows[True]), ("inactive", rows[False]), ("all", allr))}
    out["EN116_next5_forecast"] = fc
    # EN117 profitable rejects: gate-off control tickets not present in the gated cell
    pr = {}
    for c in reg:
        if c.family == "EN117" and c.kind == "CELL":
            st = c.settings; off = f"EN117:ctl:gate_off_b{float(st['excursion'])}_{st['target'].lower()}_s{float(st['stop_buffer'])}|NIFTY"
            key = f"{c.id}|NIFTY"
            if off in tick and key in tick:
                have = {(x["day"], x["m"]) for x in tick[key]}
                rej = [x for x in tick[off] if (x["day"], x["m"]) not in have]
                pr[c.id] = dict(rejected=len(rej), rejected_winners=sum(x["net"] > 0 for x in rej), rejected_net=round(sum(x["net"] for x in rej), 2),
                                gross=round(sum(x["gross"] for x in rej), 2), fees=round(sum(x["fees"] for x in rej), 2))
    out["EN117_rejected_by_gate_vs_gate_off"] = pr
    # EN118 / EN120: realised labels of chosen actions (predicted winners that lost)
    lw = {}
    for key, L in learners.items():
        if not key.endswith("|NIFTY"):
            continue
        cid = key.rsplit("|", 1)[0]; tk = tick.get(key, [])
        lw[cid] = dict(parents=len(tk), losers=sum(x["net"] <= 0 for x in tk), by_tag={k: round(sum(x["net"] for x in tk if x["tag"] == k), 2) for k in sorted({x["tag"] or "" for x in tk})},
                       decisions=bank[key].get("decisions"))
    out["learned_decisions"] = lw
    # EN120 blocked good trades: EN87 winners on dates >= 100 absent from each controller ledger
    bl = {}
    e87 = [x for x in tick["REF:EN87|NIFTY"] if x["day"] >= book[INITIAL].day]
    for c in reg:
        if c.family == "EN120":
            key = f"{c.id}|NIFTY"
            if key in tick:
                have = {(x["day"], x["m"]) for x in tick[key]}
                miss = [x for x in e87 if (x["day"], x["m"]) not in have]
                bl[c.id] = dict(en87_parents_absent=len(miss), absent_winners=sum(x["net"] > 0 for x in miss), absent_net=round(sum(x["net"] for x in miss), 2))
    out["EN120_EN87_parents_absent"] = bl
    out["EN119_source_gate"] = dict(required_synchronized_expiries=20, available="TR01 2026-11-16/17 exports (1-2 sessions), read-only", status="SOURCE_GATED")
    return out


# ------------------------------------------------------------------ freeze / score / selftest
def freeze():
    if FREEZE.exists():
        raise RuntimeError("freeze10.json exists")
    for name in ("test10-parity.json", "test10-references.json", "test10-dependencies.json", "test10-causal.json", "test10-unit.json", "selftest10.json"):
        assert json.loads((HERE / name).read_text())["status"] == "PASS", name
    B, bindings = data8.historical_books()
    reg = FM.registry()
    import scipy
    f = dict(head_before_freeze=git("rev-parse", "HEAD"), created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             files={k: data8.sha(p) for k, p in sources().items()}, data=data8.sealed_manifest(B, bindings), arrays=score8.array_manifest(B),
             environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
             counts=FM.counts(reg), registry=[dict(id=c.id, family=c.family, block=c.block, kind=c.kind, settings=c.settings, note=c.note,
                                                   comparator=list(c.comparator), spec=asdict(c.spec) if c.spec else None) for c in reg],
             dynamic_controls=["EN112:dyn:random_* (room rate on dates < 100)", "EN114:dyn:matched_* (mean training hold)"],
             selection=dict(initial=INITIAL, outer=OUTER, inner=INNER, inner_blocks=NBLK, floor_parents=FLOOR, fixed_comparators=LEARNED_FIXED),
             nomination="IMPL10 section 7, at most two", evaluation="development only; all sessions already studied", inference="descriptive only")
    write(FREEZE, f); print("FROZEN", len(f["files"]), "files", f["counts"], flush=True)


def verify_freeze():
    f = json.loads(FREEZE.read_text()); bad = [k for k, p in sources().items() if data8.sha(p) != f["files"].get(k)]
    if bad:
        raise RuntimeError("changed frozen files: " + str(bad))
    B, bindings, _ = data10.load(False)
    assert bindings == f["data"]["files"], "sealed data changed"
    assert score8.array_manifest(B) == f["arrays"], "tape inputs changed"
    return f, B


def score():
    for p in (HERE / "results10.json", HERE / "results10-started.json"):
        if p.exists():
            raise RuntimeError("one-shot score already started; preserve the evidence")
    f, B = verify_freeze()
    st = git("status", "--porcelain", "--", *[str(HERE / x) for x in FILES10], str(FREEZE))
    if st:
        raise RuntimeError("commit frozen code first: " + st)
    fd = os.open(HERE / "results10-started.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(dict(head=git("rev-parse", "HEAD"), freeze_sha256=data8.sha(FREEZE), utc=time.time()), h); h.flush(); os.fsync(h.fileno())
    try:
        res, anat, reg = pipeline(B, FM.registry())
        res["head"] = git("rev-parse", "HEAD"); res["freeze_sha256"] = data8.sha(FREEZE)
        write(HERE / "results10.json", res); write(HERE / "anatomy10.json", anat)
        with open(HERE / "trials10.jsonl", "w", encoding="utf-8") as fh:
            for c in reg:
                for u in B:
                    key = f"{c.id}|{u}"; row = res["configs"].get(key)
                    fh.write(json.dumps(dict(id=c.id, index=u, family=c.family, kind=c.kind, settings=c.settings,
                                             status="SCORED" if row else res["unavailable"].get(key, "NOT_RUN"), hash=row["hash"] if row else None,
                                             parents=row["ordinary"]["trades"] if row else None, head=res["head"], freeze=res["freeze_sha256"]), default=str) + "\n")
        reg_dir = HERE / "registration10"; reg_dir.mkdir(exist_ok=True)
        for ch in res["champions"]:
            cid = ch["config"]; c = next((x for x in reg if x.id == cid), None)
            write(reg_dir / f"{cid.replace(':', '_')}.json", dict(champion=ch, settings=c.settings if c else None, spec=asdict(c.spec) if c else None,
                  rule=asdict(c.rule()) if c and not c.spec.learned else None,
                  status="NOMINATED FOR A NEW PROSPECTIVE PAPER OBSERVATION ONLY; not qualified, not promoted, not deployed",
                  forward=dict(primary="paired adverse net per scheduled covered expiry vs its frozen comparator", floors=dict(covered_expiries=40, funded_parents=20),
                               review="one final review; owner decides"), freeze_sha256=res["freeze_sha256"], head=res["head"]))
    except BaseException as e:
        write(HERE / "failure10.json", dict(type=type(e).__name__, error=str(e))); raise
    print("SCORE COMPLETE", flush=True)


def selftest():
    """Whole pipeline on 130 NIFTY + 40 SENSEX sessions and a subsample of every family; prints counts only (no money)."""
    B, _, _ = data10.load(False)
    B = {"NIFTY": B["NIFTY"][:130], "SENSEX": B["SENSEX"][:40]}
    reg = FM.registry(); keep = []
    seen = Counter()
    for c in reg:
        if c.kind == "REFERENCE" or c.id in ("EN111:0018", "EN111:0010") or c.id == en117_default(reg) or c.id.startswith("EN118:ctl:fixed") \
                or c.id == "EN120:ctl:fixed_priority_union" or seen[(c.family, c.kind)] < 2:
            keep.append(c); seen[(c.family, c.kind)] += 1
    res, anat, reg2 = pipeline(B, keep, verbose=True)
    out = dict(status="PASS", configs=len(res["configs"]), unavailable=len(res["unavailable"]), selection=sorted(res["selection"]),
               reconciled=all(v["reconciled"] for v in res["configs"].values()), dedup=res["dedup_counts"], champions=len(res["champions"]),
               label_counts=res["label_counts"])
    assert out["reconciled"]
    write(HERE / "selftest10.json", out); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"selftest": selftest, "freeze": freeze, "score": score}[sys.argv[1]]()
