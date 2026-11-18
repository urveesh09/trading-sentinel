"""Round-9 checks before the freeze. Prints and writes only equality/mechanics receipts, never candidate money.

  test9.py parity      run_day9 (hooks off) == lab8.run_day8 on every round-8 arm, session, fill level; wallets too
  test9.py reproduce   reference cells built from specs == their archived references (EN87, EN87 one lot)
  test9.py causal      feature/threshold/arm prefix tests (future minutes and later sessions erased)
  test9.py unit        synthetic mechanics of every new hook
"""
from dataclasses import replace
from pathlib import Path
import copy, json, math, sys, time, unittest
import numpy as np
import round8  # noqa: F401
import data8, lab8, signals8
import signals9 as S9, lab9, families9 as F
L7 = lab8.L7; L4 = L7.L4; E = L7.E
HERE = Path(__file__).resolve().parent
SC = ("ordinary", "adverse", "catastrophe")


def write(name, obj):
    (HERE / name).write_text(json.dumps(obj, indent=1, default=str) + "\n", encoding="utf-8")


def load(prep9=True):
    B, _ = data8.historical_books()
    for u, book in B.items():
        signals8.prepare(book)
        if prep9:
            F.prepare9(book)
    return B


def canon(day):
    """Order-ledger identity of one simulated session."""
    pos = [(p["j"], p["direction"], p["entry_i"], p.get("exit_i"), p["lots"], round(p["net"], 2), round(p["fees"], 2),
            tuple((e["i"], e["side"], e.get("reason"), e["lots"], e["price"], e["fees"]) for e in p["events"])) for p in day["positions"]]
    return (day["net"], day["trades"], day["spent"], day["fees"], day["unresolved"], day["rejected"], day["intents"], day["minutes_in"],
            day["marked_worst"], tuple(pos))


def parity(B):
    bad = []; n = 0; t0 = time.time()
    for name, arm in lab8.ARMS.items():
        for u, book in B.items():
            if u == "SENSEX" and arm.setup8:
                continue
            r9 = lab9.R9(arm)
            for sc in SC:
                for t in book:
                    a = lab8.run_day8(t, arm, sc, 30000., L7.budget_of(arm), True)
                    b = lab9.run_day9(t, r9, sc, 30000., L7.budget_of(r9), True)
                    n += 1
                    if canon(a) != canon(b):
                        bad.append((name, u, sc, t.day))
            for sc in ("ordinary", "adverse"):
                wa = lab8.wallet(book, arm, sc); wb = lab9.wallet9(book, r9, sc)
                if [(d["day"], d["net"], d["P"], d["W"], d["scale"]) for d in wa["days"]] != [(d["day"], d["net"], d["P"], d["W"], d["scale"]) for d in wb["days"]]:
                    bad.append((name, u, "wallet", sc))
    out = dict(status="PASS" if not bad else "FAIL", arm_days=n, mismatches=bad[:50], seconds=round(time.time() - t0, 1))
    write("parity9.json", out); print("PARITY", out["status"], n, len(bad), flush=True)
    return out


def run_spec(book, cfg):
    rule = cfg.rule()
    for t in book:
        F.build(t, cfg.spec, cfg.id, rule)
    return rule


def reproduce(B):
    reg = {c.id: c for c in F.registry()}; book = B["NIFTY"]; checks = {}
    def find(fam, **st):
        hit = [c.id for c in reg.values() if c.family == fam and c.kind == "CELL" and all(c.settings.get(k) == v for k, v in st.items())]
        assert len(hit) == 1, (fam, st, hit)
        return hit[0]
    en87 = find("EN96", lookback_minutes=15, percentile=80, prior_covered_expiries=20)
    pairs = [(en87, "REF:EN87"), (find("EN97", half_width=2, anchor="CURRENT_ATM", aggregation="POOLED"), "REF:EN87"),
             (find("EN99", style="IMMEDIATE"), "REF:EN87"), (find("EN100", chooser="LEGACY", max_friction_ratio="UNBOUNDED"), "REF:EN87_ONE_LOT"),
             (find("EN103", initial_fraction=1), "REF:EN87"), (find("EN106", window_end=870, put_mult=1, money="MATCHED"), "REF:EN87"),
             (find("EN108", efficiency=.7, premium_high=20, percentile=80), "REF:EN87"),
             (find("EN109", weak_lots=0, agree_lots=3, strong_z=1.5), "REF:EN87"), (find("EN109", weak_lots=0, agree_lots=3, strong_z=2.0), "REF:EN87"),
             (find("EN110", stop=.35, target=1.0, runner_keep=.5), "REF:EN87"),
             (find("EN106", mode="GATE", percentile=80), find("EN106", window_end=900, put_mult=2, money="NATIVE"))]
    for a, b in pairs:
        ca, cb = reg[a], reg[b]
        assert ca.spec and cb.spec, (a, b)
        ra = run_spec(book, ca); rb = run_spec(book, cb) if not cb.spec.lab8_arm else cb.rule()
        diff = [t.day for t in book for sc in SC
                if canon(lab9.run_day9(t, ra, sc, 30000., L7.budget_of(ra), True)) != canon(lab9.run_day9(t, rb, sc, 30000., L7.budget_of(rb), True))]
        checks[f"{a} == {b}"] = dict(settings=ca.settings, equal=not diff, differing_sessions=diff[:10])
    gate_eq = all(np.array_equal(t.sig9[en87], t.signals8["GATE"]) for t in book)
    q_eq = all((np.isnan(t.q9["REF"]) and np.isnan(t.threshold8)) or t.q9["REF"] == t.threshold8 for t in book)
    ctx = reg[find("EN98", max_signed_atr_extension="UNBOUNDED", min_er10=0)]; rc = run_spec(book, ctx); ref = reg["REF:EN87"].rule()
    differ = [t.day for t in book if canon(lab9.run_day9(t, rc, "ordinary", 30000., 2500., True)) != canon(lab9.run_day9(t, ref, "ordinary", 30000., 2500., True))]
    invalid = sum(1 for t in book for x in t.logs9.get(ctx.id, []) if not x["kept"])
    checks["EN98 unbounded/0 vs EN87"] = dict(settings=ctx.settings, sessions_differing=len(differ), events_without_valid_features=invalid,
                                              note="equal except where X or ER10 is unavailable at an EN87 clock")
    ok = all(v.get("equal", True) for v in checks.values()) and gate_eq and q_eq
    out = dict(status="PASS" if ok else "FAIL", gate_array_equals_round8=gate_eq, reference_threshold_equals_round8=q_eq, checks=checks)
    write("reproduce9.json", out); print("REPRODUCE", out["status"], flush=True)
    return out


# ------------------------------------------------------------------ causal prefix tests
def truncated(t, m):
    """A copy of the session with every bar after index m erased (future unknown)."""
    c = copy.copy(t)
    for name in ("x", "f", "q", "oi8"):
        a = getattr(t, name).astype(float, copy=True); a[m + 1:] = np.nan; setattr(c, name, a)
    c.close = t.close.astype(float, copy=True); c.close[m + 1:] = np.nan
    c.features = {k: v.copy() for k, v in t.features.items()}
    for v in c.features.values():
        v[m + 1:] = np.nan
    c.frame8 = dict(t.frame8); c.frame8["components"] = t.frame8["components"].copy(); c.frame8["components"][m + 1:] = np.nan
    base, innov = signals8.parity_innovation(c); c.frame8["innovation"] = innov
    for k in ("_look9",):
        if hasattr(c, k):
            delattr(c, k)
    return c


def causal(B):
    book = B["NIFTY"]; rng = np.random.default_rng(9); fails = []; checked = 0
    reps = [F.STD(L) for L in S9.LOOKBACKS] + [(15, w, a, g) for w in S9.WIDTHS for a in S9.ANCHORS for g in S9.AGGS]
    for t in [book[k] for k in rng.choice(len(book), 12, replace=False)]:
        for m in rng.integers(240, 300, 3):
            c = truncated(t, int(m))
            for rep in reps:
                if rep == S9.REF_REP:
                    continue
                full = np.array([S9.rep_score(t, i, rep) for i in range(m - 5, m + 1)])
                pre = np.array([S9.rep_score(c, i, rep) for i in range(m - 5, m + 1)])
                checked += 1
                if not np.array_equal(full, pre, equal_nan=True):
                    fails.append((t.day, int(m), rep))
            for d in (1, -1):
                a = (S9.er10(t, m), S9.extension(t, m, d)); b = (S9.er10(c, m), S9.extension(c, m, d)); checked += 1
                if not np.array_equal(np.array(a), np.array(b), equal_nan=True):
                    fails.append((t.day, int(m), "context", d))
            e_full = S9.basis_innovation(t)[:m + 1]; e_pre = S9.basis_innovation(c)[:m + 1]; checked += 1
            if not np.array_equal(e_full, e_pre, equal_nan=True):
                fails.append((t.day, int(m), "basis"))
            s_full = t.frame8["innovation"][:m + 1]; s_pre = c.frame8["innovation"][:m + 1]; checked += 1
            if not np.array_equal(s_full, s_pre, equal_nan=True):
                fails.append((t.day, int(m), "syn"))
            ev = t.signals8["GATE"].copy(); ev[m + 1:] = 0
            S = t.S9[F.skey(S9.REF_REP)]; Sc = S.copy(); Sc[m + 1:] = np.nan
            for style, ttl, amt in (("CONFIRM", 3, .1), ("RECLAIM", 5, .25)):
                a, pa, _ = S9.arms99(t, ev, S, t.q9["REF"], style, ttl, amt, 1.08, L7.E03_ENV)
                b, pb, _ = S9.arms99(c, ev, Sc, t.q9["REF"], style, ttl, amt, 1.08, L7.E03_ENV); checked += 1
                if not np.array_equal(a[:m + 1], b[:m + 1]):
                    fails.append((t.day, int(m), "arms99", style))
            a, _, _ = S9.arms104(t, t.e03, S, t.q9["REF"], t.q9[F.qkey(F.skey(S9.REF_REP), 20, 70)], 3, "STRUCTURE_HOLDS", L7.E03_ENV)
            ec = t.e03.copy(); ec[m + 1:] = 0
            b, _, _ = S9.arms104(c, ec, Sc, t.q9["REF"], t.q9[F.qkey(F.skey(S9.REF_REP), 20, 70)], 3, "STRUCTURE_HOLDS", L7.E03_ENV); checked += 1
            if not np.array_equal(a[:m + 1], b[:m + 1]):
                fails.append((t.day, int(m), "arms104"))
    # thresholds: a session's q is unchanged when every later session is removed
    saved = {t.day: dict(t.q9) for t in book}; prefix_fail = []
    for k in (25, 60, 130):
        sub = book[:k + 1]
        F.prepare9(sub)
        if any(not (np.isnan(saved[sub[-1].day][q]) and np.isnan(v) or saved[sub[-1].day][q] == v) for q, v in sub[-1].q9.items()):
            prefix_fail.append(sub[-1].day)
    F.prepare9(book)
    restored = all(all((np.isnan(saved[t.day][q]) and np.isnan(v)) or saved[t.day][q] == v for q, v in t.q9.items()) for t in book)
    out = dict(status="PASS" if not fails and not prefix_fail and restored else "FAIL", feature_prefix_checks=checked, failures=fails[:30],
               threshold_prefix_sessions=[book[k].day for k in (25, 60, 130)], threshold_prefix_failures=prefix_fail, rebuild_identical=restored)
    write("causal9.json", out); print("CAUSAL", out["status"], checked, len(fails), prefix_fail, flush=True)
    return out


if __name__ == "__main__":
    what = sys.argv[1:] or ["parity", "reproduce", "causal"]
    if "unit" in what:
        import test9_unit
        r = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test9_unit))
        write("unit9.json", dict(status="PASS" if r.wasSuccessful() else "FAIL", tests=r.testsRun, failures=len(r.failures), errors=len(r.errors),
                                 detail=[str(x[0]) for x in r.failures + r.errors]))
        what = [w for w in what if w != "unit"]
    if what:
        B = load()
        for w in what:
            {"parity": parity, "reproduce": reproduce, "causal": causal}[w](B)
