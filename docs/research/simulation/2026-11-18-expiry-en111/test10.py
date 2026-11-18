"""Round-10 acceptance before the freeze (IMPL10.md section 9). No round-10 money is printed or inspected.

  test10.py unit     synthetic mechanics for every round-10 hook (test10_unit), writes test10-unit.json
  test10.py data     parity, references, dependencies, causal prefixes on the sealed books, writes the other receipts
"""
from copy import copy
from dataclasses import replace
import hashlib, json, math, sys, time, unittest
import numpy as np
import round10  # noqa: F401
import data8, signals8, lab8
from data8 import L7
import score9, families9 as F9, signals9 as S9, lab9
import lab10, features10 as FX, families10 as FM, hmm10, learn10 as LN, data10
HERE = FM.HERE
R9DIR = HERE.parent / "2026-11-18-expiry-en96"
SC = ("ordinary", "adverse", "catastrophe")


def write(name, obj):
    score9.write(HERE / name, obj)


def h_ledger(book, rule, idx=None, scen=("ordinary", "adverse", "catastrophe"), run=None):
    run = run or lab10.run_day10; h = hashlib.sha256()
    for sc in scen:
        for k in (range(len(book)) if idx is None else idx):
            t = book[k]; det = sc != "catastrophe"
            d = run(t, rule, sc, 30000., L7.budget_of(rule), det)
            if det:
                h.update(repr(score9.canon_day(d)).encode())
    return h.hexdigest()[:20]


# ------------------------------------------------------------------ parity with round 9 (hooks off)
def parity(B):
    res = json.loads((R9DIR / "results9.json").read_text()); anat = json.loads((R9DIR / "anatomy9.json").read_text())
    reg = F9.registry(); bad = []; n = 0
    for c in reg:
        if c.family == "EN105" or not c.spec:
            continue
        for u, book in B.items():
            key = f"{c.id}|{u}"
            if key not in res["configs"]:
                continue
            if c.spec.mgmt and c.spec.mgmt[0] == "RND":
                cap = c.spec.mgmt[1]; rates = []
                for x in reg:
                    if x.family == "EN101" and x.kind == "CELL" and x.settings["absolute_hold_minutes"] == cap:
                        tk = [y for y in anat["tickets"][f"{x.id}|NIFTY"] if y["day"] < book[100].day and y["ext"]]
                        rates.append(sum(y["ext"] == "EXTENDED" for y in tk) / len(tk) if tk else 0.)
                c.spec = replace(c.spec, mgmt=("RND", cap, round(float(np.mean(rates)) if rates else 0., 6)))
            rule = c.rule()
            for t in book:
                F9.build(t, c.spec, c.id, rule)
            got = h_ledger(book, lab10.R10(rule))
            n += 1
            if got != res["configs"][key]["hash"]:
                bad.append(key)
    out = dict(status="PASS" if not bad and n == len(res["configs"]) else "FAIL", checked=n, round9_configs=len(res["configs"]), mismatches=bad)
    write("test10-parity.json", out); print("parity", out["status"], n, len(bad), flush=True)
    return out


# ------------------------------------------------------------------ references reproduced by reference-equal cells
def references(B):
    reg = FM.registry(); byid = {c.id: c for c in reg}; rows = []
    pairs = []
    for c in reg:
        st = c.settings
        if c.family == "EN121" and st["contract"] == "LEGACY" and st["target"] == 1.0 and st["hold"] == 8:
            pairs.append((c.id, "REF:" + st["book"]))
        if c.family == "EN122" and st["geometry"] == "DEFAULT" and st["gate"] == "NONE":
            if (st["window_end"], st["put_mult"], st["money"]) == (900, 2, "NATIVE"):
                pairs.append((c.id, "REF:E032_native"))
            if (st["window_end"], st["put_mult"], st["money"]) == (870, 1, "ENVELOPE"):
                pairs.append((c.id, "REF:E03_env"))
    pairs.append(("EN111:0001", "REF:EN87"))
    pairs.append(("EN112:ctl:fixed_target_only", "EN111:0007"))
    pairs.append(("EN113:ctl:fixed12", "EN111:0003"))
    pairs.append(("EN114:ctl:fixed_8_base_only", "REF:EN87"))
    for a, b in pairs:
        for u, book in B.items():
            ca, cb = byid[a], byid[b]
            if u == "SENSEX" and not (FM.sensex_ok(ca.spec) and FM.sensex_ok(cb.spec)):
                continue
            ha = cell_hash(book, ca); hb = cell_hash(book, cb)
            rows.append(dict(cell=a, reference=b, index=u, equal=ha == hb))
    out = dict(status="PASS" if all(r["equal"] for r in rows) else "FAIL", checks=rows)
    write("test10-references.json", out); print("references", out["status"], len(rows), flush=True)
    return out


def cell_hash(book, c, idx=None):
    rule = c.rule()
    for k in (range(len(book)) if idx is None else idx):
        FM.build(book[k], c.spec, c.id, rule)
    return h_ledger(book, rule, idx, ("ordinary", "adverse"))


# ------------------------------------------------------------------ typed dependencies (REVIEW10 R3)
def strip_oi(B):
    """A NIFTY copy whose OI source is declared unavailable, re-prepared through the same causal chain."""
    book = []
    for t in B["NIFTY"]:
        u = copy(t)
        for name in ("sig9", "meta9", "logs9", "state10", "logs10"):
            setattr(u, name, {})
        if hasattr(u, "_look9"):
            del u._look9
        data8.attach(u, data8.Source(data8.Path(t.oi_source8["path"]), False, t.oi_source8["identity"]))
        book.append(u)
    signals8.prepare(book); F9.prepare9(book)
    FM.prepare10({"NIFTY": book}, False)
    return book


def dependencies(B):
    nb = B["NIFTY"]
    g = [k for k, t in enumerate(nb) if (FM.en87_dirs(t) != 0).any()]
    rest = [k for k in range(len(nb)) if k not in g]
    idx = sorted(set(g + rest[::max(1, len(rest) // 20)]))
    reg = FM.registry(); rows = []
    ref = next(c for c in reg if c.id == "REF:EN87"); before = cell_hash(nb, ref, idx)
    ob = strip_oi(B)
    assert cell_hash(nb, ref, idx) == before, "stripping OI from the copy changed the original book"
    for c in reg:
        if c.spec is None or c.spec.learned:
            continue
        a = cell_hash(nb, c, idx); b = cell_hash(ob, c, idx)
        declared = "OI" in c.spec.needs
        rows.append(dict(id=c.id, declared_oi=declared, changes_without_oi=a != b,
                         ok=(a == b) if not declared else True, declared_unused=declared and a == b))
    bad = [r["id"] for r in rows if not r["ok"]]
    unused = [r["id"] for r in rows if r["declared_unused"]]
    out = dict(status="PASS" if not bad else "FAIL", sessions=len(idx), checked=len(rows), undeclared_oi_users=bad, declared_but_unchanged=unused,
               note="learned EN118/EN120 policies: OI enters only through declared features and the EN87 fallback (needs OI / OI_OPTIONAL)")
    write("test10-dependencies.json", out); print("dependencies", out["status"], len(rows), "unused", len(unused), flush=True)
    return out


# ------------------------------------------------------------------ causal prefixes
def snapshot(book):
    out = []
    for t in book:
        out.append(dict(q10=dict(t.q10), ext10={k: dict(v) for k, v in t.ext10.items()}, vref=t.vref10,
                        er=None if t.er_rank_ref10 is None else hashlib.sha256(np.asarray(t.er_rank_ref10).tobytes()).hexdigest(),
                        r10={b: [dict(e) for e in v] for b, v in t.range10.items()},
                        hmm={str(k): (r["model"], None if r.get("pT") is None else hashlib.sha256(np.asarray(r["pT"]).tobytes()).hexdigest()) for k, r in t.hmm10.items()}))
    return out


def same(a, b):
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def truncate(t, m):
    u = copy(t)
    u.q = t.q.copy(); u.q[m + 1:] = np.nan
    u.f = t.f.astype(float).copy(); u.f[m + 1:] = np.nan
    u.x = t.x.astype(float).copy(); u.x[m + 1:] = np.nan
    u.close = t.close.astype(float).copy(); u.close[m + 1:] = np.nan
    u.oi8 = t.oi8.copy(); u.oi8[m + 1:] = np.nan
    u.features = {k: v.copy() for k, v in t.features.items()}
    for v in u.features.values():
        v[m + 1:] = np.nan
    return u


def causal(B):
    nb = B["NIFTY"]; rows = {}
    full = snapshot(nb)
    K = 120
    FM.prepare10({"NIFTY": nb[:K]}, False)
    part = snapshot(nb[:K])
    rows["session_prefix_features"] = all(same(full[k], part[k]) for k in range(K))
    FM.prepare10({"NIFTY": nb}, False)
    rows["restored"] = same(snapshot(nb), full)
    # within-session prefixes: features at bars <= m do not change when later bars are erased
    bad = 0; n = 0
    for k in range(0, len(nb), 13):
        t = nb[k]
        for m in (790, 820, 860):
            i = int(np.searchsorted(t.minute, m)); u = truncate(t, i)
            a = FX.minute_obs(t)[:i + 1]; b = FX.minute_obs(u)[:i + 1]
            n += 1; bad += not np.array_equal(np.nan_to_num(a, nan=-9e9), np.nan_to_num(b, nan=-9e9))
            for buf in (0., .25):
                ea = [e for e in FX.range_events(t, buf) if e["i"] <= i]; eb = FX.range_events(u, buf)
                n += 1; bad += not same(ea, eb)
            for L in (1, 3):
                a = FX.fast_series(t, L)[:i + 1]; b = FX.fast_series(u, L)[:i + 1]
                n += 1; bad += not np.array_equal(np.nan_to_num(a, nan=-9e9), np.nan_to_num(b, nan=-9e9))
            for j in range(0, len(t.strikes), 7):
                fa = lab10.response_fit(t, i, j, 40, 10.); fb = lab10.response_fit(u, i, j, 40, 10.)
                n += 1; bad += fa != fb
            for d in (1, -1):
                n += 1; bad += lab10.wall_of(t, i, d) != lab10.wall_of(u, i, d)
                n += 1; bad += not same(FX.accel(t, i, d), FX.accel(u, i, d))
                fa, fb = FX.nominal_friction(t, i, d), FX.nominal_friction(u, i, d)
                n += 1; bad += not (fa == fb or (math.isnan(fa) and math.isnan(fb)))
    rows["within_session_prefix"] = dict(checks=n, mismatches=bad)
    # learned fits read only earlier dates: perturbing labels on/after the fit date changes nothing
    labels = LN.label_events(nb)
    f = 120; train = [e for k in range(f) for e in labels[k]]
    m1 = LN.Model118("RIDGE", "LIGHT", 1, "WITH_OI", train, f, seed=7)
    m2 = LN.Model118("STUMP", "HEAVY", 0, "WITH_OI", train, f, seed=7)
    t1 = LN.Model120(2, train, f, seed=7)
    test = [e for k in range(f, len(nb)) for e in labels[k]]
    before = (LN.policy118(m1, test)[0], LN.policy118(m2, test)[0], LN.policy120(t1, test, .1, dict(current="EN87"))[0])
    for e in test:
        e["dir8"] = -99.
        for a in e["label"]:
            e["label"][a] = dict(ordinary=(9e9, 1), adverse=(9e9, 1))
    train2 = [e for k in range(f) for e in labels[k]]
    m1b = LN.Model118("RIDGE", "LIGHT", 1, "WITH_OI", train2, f, seed=7); m2b = LN.Model118("STUMP", "HEAVY", 0, "WITH_OI", train2, f, seed=7)
    t1b = LN.Model120(2, train2, f, seed=7)
    after = (LN.policy118(m1b, test)[0], LN.policy118(m2b, test)[0], LN.policy120(t1b, test, .1, dict(current="EN87"))[0])
    rows["learned_fit_prefix"] = same(before, after) and m1.id == m1b.id and t1.id == t1b.id
    # restart equality: the controller state serialised at a split point reproduces the same later decisions
    st = dict(current="EN87"); seq = []
    for k in range(f, len(nb)):
        seq.append(LN.policy120(t1, labels[k], .1, st)[0])
    st2 = dict(current="EN87"); half = (len(nb) - f) // 2
    for k in range(f, f + half):
        LN.policy120(t1, labels[k], .1, st2)
    saved = json.loads(json.dumps(st2)); seq2 = []
    for k in range(f + half, len(nb)):
        seq2.append(LN.policy120(t1, labels[k], .1, saved)[0])
    rows["controller_restart_equality"] = same(seq[half:], seq2)
    # HMM: refit determinism and prefix (fits on a truncated calendar equal the full run's)
    a = hmm10.states116(nb, 2, 5); b = hmm10.states116(nb[:K], 2, 5)
    rows["hmm_prefix_and_determinism"] = all(x["model"] == y["model"] and (x.get("pT") is None or np.array_equal(x["pT"], y["pT"])) for x, y in zip(a[:K], b))
    ok = rows["session_prefix_features"] and rows["restored"] and rows["within_session_prefix"]["mismatches"] == 0 and rows["learned_fit_prefix"] \
        and rows["controller_restart_equality"] and rows["hmm_prefix_and_determinism"]
    out = dict(status="PASS" if ok else "FAIL", **rows)
    write("test10-causal.json", out); print("causal", out["status"], rows, flush=True)
    return out


def data(parts=("parity", "references", "causal", "dependencies")):
    t0 = time.time(); B, _, _ = data10.load(False); print("loaded", round(time.time() - t0), flush=True)
    fns = dict(parity=parity, references=references, causal=causal, dependencies=dependencies)
    out = {k: fns[k](B)["status"] for k in parts}
    print(out, round(time.time() - t0), flush=True)


def unit():
    import test10_unit
    suite = unittest.defaultTestLoader.loadTestsFromModule(test10_unit)
    r = unittest.TextTestRunner(verbosity=1).run(suite)
    out = dict(status="PASS" if r.wasSuccessful() else "FAIL", tests=r.testsRun, failures=len(r.failures), errors=len(r.errors),
               detail=[str(x[0]) for x in r.failures + r.errors])
    write("test10-unit.json", out); print(out)


if __name__ == "__main__":
    if sys.argv[1] == "data":
        data(tuple(sys.argv[2:]) or ("parity", "references", "causal", "dependencies"))
    else:
        unit()
