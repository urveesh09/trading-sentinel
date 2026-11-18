"""Phase zero (IMPL10.md section 8): outcome-blind activation, state and action counts. No P&L, no position outcome:
signal clocks and nominal windows (decision+1 .. +12 bars) only. Writes phase0-10.json."""
from collections import Counter, defaultdict
import json, math, sys, time
import numpy as np
import round10  # noqa: F401
from data8 import L7, basket as basket8
import signals9 as S9
import lab9, lab10, features10 as FX, families10 as FM, hmm10, data10, learn10
L4 = L7.L4
HERE = FM.HERE


def nominal(t, i):
    return int(i) + 1, min(t.n, int(i) + 13)


def first_of_runs(sig):
    idx = np.flatnonzero(sig)
    return [int(i) for i in idx if i == 0 or sig[i - 1] != sig[i]]


def main():
    t0 = time.time()
    B, _, _ = data10.load()
    out = dict(scope="outcome-blind: no P&L; signal minutes and nominal windows only", generated_s=None)
    nb = B["NIFTY"]
    ev87 = {k: [int(i) for i in np.flatnonzero(FM.en87_dirs(t))] for k, t in enumerate(nb)}
    out["EN87_signal_minutes"] = sum(len(v) for v in ev87.values())
    out["EN87_signal_dates"] = sum(1 for v in ev87.values() if v)
    out["EN87_runs"] = sum(len(first_of_runs(FM.en87_dirs(t))) for t in nb)
    # EN112
    st = {}
    for rk in ("rank40", "rank_all"):
        for ctx in ("EXTENSION_RANK", "ACCELERATION", "BOTH"):
            c = Counter()
            for k, t in enumerate(nb):
                for i in ev87[k]:
                    e = t.ext10.get(i); f = None if e is None else FM.fresh_state(e, ctx, rk)
                    c["missing" if f is None else "fresh" if f else "mature"] += 1
            st[f"{rk}|{ctx}"] = dict(c)
    rank_def = [t.ext10[i]["rank40"] is not None for k, t in enumerate(nb) for i in ev87[k]]
    out["EN112"] = dict(states=st, rank40_defined_share=round(float(np.mean(rank_def)), 4) if rank_def else None,
                        n40_median=float(np.median([t.ext10[i]["n40"] for k, t in enumerate(nb) for i in ev87[k]])))
    # EN113
    r113 = {}
    ratio = defaultdict(list)
    for L in (1, 3, 5):
        for p in (80, 90):
            c = Counter()
            for k, t in enumerate(nb):
                q = t.q10[f"L{L}|p{p}"]
                for i in ev87[k]:
                    a, b = nominal(t, i); pos = dict(entry_i=a, direction=int(np.sign(FM.en87_dirs(t)[i])))
                    D = [lab10.fast_D(t, x, pos, L, q) for x in range(a, b)]
                    conf = [D[n] and D[n - 1] for n in range(1, len(D)) if D[n] is not None and D[n - 1] is not None]
                    c["any_confirm"] += bool(any(conf)); c["windows"] += 1
                    at8 = a + 8
                    if at8 < b and at8 - 1 >= a:
                        x, y = lab10.fast_D(t, at8, pos, L, q), lab10.fast_D(t, at8 - 1, pos, L, q)
                        c["missing_at8"] += x is None or y is None
                        c["confirm_at8"] += bool(x and y)
                    if p == 80:
                        pairs = lab9.fixed_pairs(t, pos, S9.REF_REP)
                        for xx in range(a, b):
                            sf = S9.ref_score(t, xx, L, pairs) if pairs else math.nan; sc = t.S10[L][xx]
                            if np.isfinite(sf) and np.isfinite(sc):
                                ratio[L].append((abs(sf), abs(sc)))
            r113[f"L{L}|p{p}"] = dict(c)
    out["EN113"] = dict(counts=r113, fixed_vs_current_abs_median={L: [round(float(np.median([x[0] for x in v])), 6), round(float(np.median([x[1] for x in v])), 6)]
                                                                for L, v in ratio.items()})
    # EN114
    ex = defaultdict(Counter); miss = 0
    for k, t in enumerate(nb):
        for i in ev87[k]:
            a, b = nominal(t, i); v0 = lab10.v0_of(t, i); F = t.f[:, 3]
            if not np.isfinite(v0):
                miss += 1; continue
            for bud in (4, 8, 12):
                hit = None
                for x in range(a, min(t.n, a + 17)):
                    seg = F[a - 1:x + 1]
                    if not np.isfinite(seg).all():
                        break
                    A = float(np.sum(np.diff(seg) ** 2)) / v0
                    if x - a >= 4 and A >= bud:
                        hit = x - a; break
                ex[bud]["never_by_16" if hit is None else ("<=8" if hit <= 8 else "9-12" if hit <= 12 else "13-16")] += 1
    out["EN114"] = dict(exhaustion_age={b: dict(c) for b, c in ex.items()}, v0_missing=miss)
    # EN115
    sp = L4.NIFTY; diff = Counter()
    for W in (20, 40, 60):
        for lam in (1., 10.):
            for rp in (0., 1.):
                c = Counter()
                for k, t in enumerate(nb):
                    for i in ev87[k]:
                        d = int(FM.en87_dirs(t)[i]); r = lab10.R10(L7.E03_ENV, chooser9="RESP", max_lots=1, admit9=True, resp10=(W, lam, rp, "MODEL"))
                        note = []
                        rp_ = lab10.resp_pick(sp, t, i, d, r, 2500., 30000., note)
                        nr = lab9.contract_pick(sp, t, i, d, lab10.R10(L7.E03_ENV, chooser9="NEAREST", max_lots=1, admit9=True), 2500., 30000.)
                        lg = L4.choose4(sp, t, i, d, lab10.R10(L7.E03_ENV, max_lots=1), 2500., 30000.)
                        c["n"] += 1; c["fallback"] += bool(note)
                        c["none"] += rp_ is None
                        if rp_ and nr:
                            c["differs_from_nearest"] += rp_[0] != nr[0]
                        if rp_ and lg:
                            c["differs_from_legacy1"] += rp_[0] != lg[0]
                diff[f"W{W}|l{int(lam)}|rp{int(rp)}"] = dict(c)
    out["EN115"] = diff
    # EN116
    h = {}
    for K in (2, 3):
        for refit in (1, 5):
            recs = [t.hmm10[(K, refit)] for t in nb]
            fb = Counter(r["fallback"] or "MODEL" for r in recs)
            occ = {}
            for pers in ("IMMEDIATE", "TWO_BAR_HYSTERESIS"):
                for v in ("HMM", "ER", "RND"):
                    on = []; at = []
                    for k, t in enumerate(nb):
                        a = FM.state116(t, K, refit, pers, v)
                        if a is None:
                            continue
                        on.append(float(a[FX.window(t)].mean())); at += [bool(a[i]) for i in ev87[k]]
                    occ[f"{pers}|{v}"] = dict(window_occupancy=round(float(np.mean(on)), 4) if on else None, active_at_EN87=int(sum(at)), EN87_minutes=len(at))
            models = len({r["model"] for r in recs if r["model"]})
            h[f"K{K}|R{refit}"] = dict(fallback=dict(fb), distinct_models=models, occupancy=occ)
    out["EN116"] = h
    # EN117
    e117 = {}
    for u, book in B.items():
        for buf in (0., .25):
            n = sum(len(t.range10[buf]) for t in book); dates = sum(1 for t in book if t.range10[buf])
            gate = Counter()
            sp = L4.spec_of(book[0])
            for t in book:
                for ev in t.range10[buf]:
                    r = lab10.R10(L7.E03_ENV, chooser9="NEAREST", max_lots=1)
                    pk = lab9.contract_pick(sp, t, ev["i"], ev["d"], r, 2500., 30000.)
                    if pk is None:
                        gate["unaffordable"] += 1; continue
                    for tg in ("MIDPOINT", "OPPOSITE_QUARTILE"):
                        lv = FX.range_levels(ev, tg, .5)
                        for cov in (1., 2.):
                            gate[f"{tg}|cov{int(cov)}"] += lab10.cost_gate(sp, t, ev["i"], ev["d"], pk[0], dict(range10=lv), cov)
            e117[f"{u}|b{buf}"] = dict(events=n, dates=dates, calls=sum(e["d"] > 0 for t in book for e in t.range10[buf]), gate_pass=dict(gate))
    out["EN117"] = e117
    # EN118 / EN120 support feasibility (applicable-event dates, not funded)
    sup = {}
    for u, book in B.items():
        dates = defaultdict(set)
        for k, t in enumerate(book):
            for e in learn10.events(t):
                if e["setup"] == "E03":
                    dates["E03"].add(k)
                if e["en87"]:
                    dates["EN87"].add(k)
                if e["setup"] == "RANGE":
                    dates["RANGE"].add(k)
        sup[u] = {s: {str(b): sum(1 for d in v if d < b) for b in (40, 60, 100, 120, 140, 160, 180, 197)} for s, v in dates.items()}
    out["EN118_EN120_applicable_dates_before"] = sup
    # EN121 / EN122 contract differences and windows
    e121 = {}
    for u, book in B.items():
        sp = L4.spec_of(book[0]); c = Counter()
        for t in book:
            for i in np.flatnonzero(FM.e03w(t, 870)):
                i = int(i); d = int(t.e03[i])
                lg = L4.choose4(sp, t, i, d, L7.E03_ENV, 2500., 30000.)
                n1 = lab9.contract_pick(sp, t, i, d, lab10.R10(L7.E03_ENV, chooser9="NEAREST", max_lots=1, admit9=True), 2500., 30000.)
                ns = lab9.contract_pick(sp, t, i, d, lab10.R10(L7.E03_ENV, chooser9="NEAREST", admit9=True), 2500., 30000.)
                c["e03_minutes"] += 1; c["legacy_none"] += lg is None; c["nearest1_none"] += n1 is None
                if lg and n1:
                    c["nearest_differs"] += lg[0] != n1[0]
                if ns:
                    c[f"same_room_lots_{ns[1]}"] += 1
        c["e03_minutes_900"] = int(sum(int((FM.e03w(t, 900) != 0).sum()) for t in book))
        c["e03_calls_870"] = int(sum(int((FM.e03w(t, 870) > 0).sum()) for t in book))
        if u == "NIFTY":
            c["callgate_removed_870"] = int(sum(int(((FM.e03w(t, 870) > 0) & ~(FM.en87_dirs(t, 870) > 0)).sum()) for t in book))
        e121[u] = dict(c)
    out["EN121_EN122"] = e121
    # EN125 walls in nominal windows
    w = Counter(); dist = []
    for k, t in enumerate(nb):
        for i in ev87[k]:
            d = int(FM.en87_dirs(t)[i]); a, b = nominal(t, i)
            W = lab10.wall_of(t, a, d)
            if W is None:
                w["no_wall"] += 1; continue
            A = t.features[10][i, 4]; dist.append(d * (W - float(t.close[a])) / A if np.isfinite(A) and A > 0 else math.nan)
            for off, name in ((0., "AT"), (25., "HALF")):
                for hh in (8, 12):
                    reach = any(np.isfinite(t.close[x]) and d * (float(t.close[x]) - W) >= -off for x in range(a, min(b, a + hh + 1)))
                    w[f"reach_{name}_{hh}"] += reach
            w["n"] += 1
    out["EN125"] = dict(counts=dict(w), wall_distance_atr_quartiles=[round(float(x), 3) for x in np.nanpercentile(dist, [25, 50, 75])] if dist else None)
    out["generated_s"] = round(time.time() - t0, 1)
    (HERE / "phase0-10.json").write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
