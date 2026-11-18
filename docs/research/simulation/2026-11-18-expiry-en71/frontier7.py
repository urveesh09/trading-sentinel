"""EN71: the tradable-information and execution frontier (PLAN7.md). Diagnostic; no strategy is scored here.

One canonical decision table keyed (index, date, decision bar) on two clock sets: the 5-minute grid 13:00-14:25 and
E03's own causal signal bars in the matched window. Under each row the two sides are dependent actions: the frozen
E03 chooser's contract (choose4, matched Rs 2,500 envelope), bought at the next bar (+ delay) inside its capped limit
and sold at the first executable bar 8 bars later (a fixed hold; untradeable ceilings use the same later executable
bars, never a high or low touch). Per action: signed future move, after-fee net, the no-spread counterfactual,
fees, affordability.

Forecasts per row: E03's causal side; a seeded random side; cash. Untradeable diagnostic ceilings, labelled as such:
C1 direction known over the hold (contract and clock fixed); C2 the best executable action at the fixed decision and
hold (both sides x EN56 offsets, or cash); C3 EN56's whole-day hindsight maximum. Synthetic predictors choose the
direction-oracle's side with probability p in (.50, .55, .60, .70, .80, 1.00), declared before scoring: the expected
net per row is exact (p x oracle side + (1 - p) x other side); 200 seeded draws give the dispersion. Bar delays 0-3;
Nov 17 packet delays 1 / 3 / 10 s are a pilot (one session)."""
from __future__ import annotations
import math, random, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import en_lab7 as L7  # noqa: E402

L6, L4, E = L7.L6, L7.L4, L7.E
PS = (.50, .55, .60, .70, .80, 1.00)
DELAYS = (0, 1, 2, 3)
GRID = tuple(range(780, 866, 5))
HOLD = 8


def act(t, i, d, delay=0, scenario="ordinary"):
    """The E03 chooser's action for side d at bar i: dict(status, net, gross, fees, nospread, dF) - status FILLED /
    UNAFFORDABLE / NO_FILL / MISSING."""
    sp = L4.spec_of(t); LOT = sp.lot
    if i + 1 + delay + HOLD >= t.n or not np.isfinite(t.close[i]):
        return dict(status="MISSING", net=0.)
    pick = L4.choose4(sp, t, i, d, L7.E03_ENV, 2500., 30000.)
    if not pick:
        return dict(status="UNAFFORDABLE", net=0.)
    j, lots, limit = pick; b = i + 1 + delay
    f, p = L6._exe(sp, t, b, j, "BUY", scenario, lots)
    if not f or p is None or p > limit:
        return dict(status="NO_FILL", net=0.)
    u = f * LOT; bf = L4.fee(sp, p, u, True); e0 = b + HOLD; ef = L6.at(t, 915); sale = None
    for k in range(min(e0, ef), t.n):
        fs, p2 = L6._exe(sp, t, k, j, "SELL", scenario, f)
        if fs:
            sale = (k, p2); break
    F = t.f[:, 3]; ke = min(e0, t.n - 1)
    dF = d * (F[ke] - F[i]) if np.isfinite([F[ke], F[i]]).all() else math.nan
    o1 = float(t.q[b, j, 0]) if np.isfinite(t.q[b, j, 0]) else p
    if sale is None:
        return dict(status="FILLED", net=round(-p * u - bf, 2), gross=round(-p * u, 2), fees=round(bf, 2), nospread=round(-o1 * u - bf, 2), dF=dF,
                    unresolved=1, lots=f)
    k, p2 = sale; sf = L4.fee(sp, p2, u, False); ok_ = float(t.q[k, j, 0]) if np.isfinite(t.q[k, j, 0]) else p2
    return dict(status="FILLED", net=round((p2 - p) * u - bf - sf, 2), gross=round((p2 - p) * u, 2), fees=round(bf + sf, 2),
                nospread=round((ok_ - o1) * u - bf - sf, 2), dF=dF, lots=f)


def e03_bars(t):
    dirs, _, _ = L7.signals7(t, L7.E03_ENV)
    return [(int(i), int(dirs[i])) for i in np.flatnonzero(dirs)]


def table(book, scenario="ordinary"):
    """Rows: dict(day, i, m, clock ('grid' | 'e03'), e03_side, acts={(d, delay): act})."""
    rows = []
    for t in book:
        e03 = dict(e03_bars(t)); seen = set(); start = len(rows)
        for m in GRID:
            i = L6.at(t, m)
            if i < t.n and t.minute[i] == m:
                seen.add(i); rows.append(dict(day=t.day, i=i, m=m, clock="grid", e03_side=e03.get(i, 0), t=t))
        for i, d in e03.items():
            rows.append(dict(day=t.day, i=i, m=int(t.minute[i]), clock="e03", e03_side=d, t=t))
        for r in rows[start:]:
            r["acts"] = {(d, dl): act(t, r["i"], d, dl, scenario) for d in (1, -1) for dl in DELAYS}
    return rows


def _oracle(r, dl):
    a, b = r["acts"][(1, dl)], r["acts"][(-1, dl)]
    dF = next((x["dF"] for x in (a, b) if x.get("dF") is not None and np.isfinite(x.get("dF", math.nan))), math.nan)
    if not np.isfinite(dF):
        return None
    if dF == 0:
        return (a, b, .5)
    return (a, b, 1.) if dF > 0 else (b, a, 1.)


def predictor(rows, clock, dl, p):
    """Exact expected net per row for the p-predictor, aggregated per expiry."""
    per = defaultdict(float); n = 0
    for r in rows:
        if r["clock"] != clock:
            continue
        o = _oracle(r, dl)
        if o is None:
            continue
        good, bad, w = o
        if w == .5:
            v = .5 * good["net"] + .5 * bad["net"]
        else:
            v = p * good["net"] + (1 - p) * bad["net"]
        per[r["day"]] += v; n += 1
    return per, n


def draws(rows, clock, dl, p, k=200, seed=20261119):
    """Totals of k seeded realisations (the dispersion around the exact expectation)."""
    tot = []
    for s in range(k):
        rng = random.Random(f"{seed}-{clock}-{dl}-{p}-{s}"); x = 0.
        for r in rows:
            if r["clock"] != clock:
                continue
            o = _oracle(r, dl)
            if o is None:
                continue
            good, bad, w = o
            x += (good if rng.random() < (p if w == 1. else .5) else bad)["net"]
        tot.append(x)
    return tot


def ci_by_expiry(per, days, B=5000, seed=20261119):
    """Mean per expiry over all sessions (no-decision sessions count zero) and a 95% percentile bootstrap over expiries."""
    x = np.array([per.get(d, 0.) for d in days]); rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (B, len(x)))].mean(1)
    return dict(mean_per_expiry=round(float(x.mean()), 2), lo=round(float(np.percentile(m, 2.5)), 2), hi=round(float(np.percentile(m, 97.5)), 2),
                total=round(float(x.sum()), 2))


def frontier(book):
    days = [t.day for t in book]; rows = table(book)
    out = dict(rows=dict(grid=sum(r["clock"] == "grid" for r in rows), e03=sum(r["clock"] == "e03" for r in rows)))
    cov = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for (d, dl), a in r["acts"].items():
            if dl == 0:
                cov[r["clock"]][a["status"]] += 1
    out["coverage"] = {k: dict(v) for k, v in cov.items()}
    # forecasts at E03's clocks: its causal side, a random side, cash
    e3 = [r for r in rows if r["clock"] == "e03"]
    hit = [np.sign(r["acts"][(r["e03_side"], 0)].get("dF", math.nan)) for r in e3 if r["acts"][(r["e03_side"], 0)]["status"] == "FILLED"]
    hit = [h for h in hit if np.isfinite(h) and h != 0]
    out["e03_forecast"] = dict(decisions=len(e3), filled_signed=len(hit), right=int(sum(h > 0 for h in hit)),
                               accuracy=round(sum(h > 0 for h in hit) / max(1, len(hit)), 4))
    side = defaultdict(float); rnd = defaultdict(float)
    for r in e3:
        side[r["day"]] += r["acts"][(r["e03_side"], 0)]["net"]
        rnd[r["day"]] += .5 * (r["acts"][(1, 0)]["net"] + r["acts"][(-1, 0)]["net"])
    out["e03_side_fixed_hold"] = ci_by_expiry(side, days); out["random_side_fixed_hold"] = ci_by_expiry(rnd, days)
    # ceilings (untradeable)
    c1 = {}; c2 = defaultdict(float)
    for clock in ("grid", "e03"):
        per, n = predictor(rows, clock, 0, 1.)
        c1[clock] = dict(ci_by_expiry(per, days), decisions=n)
    for r in rows:
        if r["clock"] == "grid":
            c2[r["day"]] += max(0., r["acts"][(1, 0)]["net"], r["acts"][(-1, 0)]["net"])
    out["C1_direction_known"] = c1; out["C2_best_action_fixed_clock_grid_chooser"] = ci_by_expiry(c2, days)
    # predictor frontier x delay x clock
    fr = {}
    for clock in ("grid", "e03"):
        for dl in DELAYS:
            for p in PS:
                per, n = predictor(rows, clock, dl, p)
                v = ci_by_expiry(per, days); v["decisions"] = n; v["per_decision"] = round(v["total"] / max(1, n), 2)
                fr[f"{clock}|d{dl}|p{p:.2f}"] = v
        be = {}
        for dl in DELAYS:
            xs = [(p, fr[f"{clock}|d{dl}|p{p:.2f}"]["per_decision"]) for p in PS]
            be[f"d{dl}"] = next((p for p, v in xs if v > 0), None)
        fr[f"{clock}|first_p_paying"] = be
    out["frontier"] = fr
    tot = draws(rows, "grid", 0, .5); tot1 = draws(rows, "grid", 0, 1.)
    out["harness"] = dict(useless_p50_total_draws=dict(mean=round(float(np.mean(tot)), 2), p05=round(float(np.percentile(tot, 5)), 2),
                                                      p95=round(float(np.percentile(tot, 95)), 2), share_positive=round(float(np.mean(np.array(tot) > 0)), 3)),
                          oracle_p100_total_draws=dict(mean=round(float(np.mean(tot1)), 2)))
    # spread / fee anatomy of the direction-known action on the grid
    an = defaultdict(float); k = 0
    for r in rows:
        if r["clock"] != "grid":
            continue
        o = _oracle(r, 0)
        if o and o[0]["status"] == "FILLED":
            an["net"] += o[0]["net"]; an["nospread"] += o[0]["nospread"]; an["fees"] += o[0]["fees"]; an["gross"] += o[0]["gross"]; k += 1
    out["oracle_grid_anatomy"] = dict({a: round(v / max(1, k), 2) for a, v in an.items()}, actions=k)
    return out, rows


def paired_side_share(t_rows):
    """The audit's F2: share of EN56 library rows that sit in matched opposite-side pairs (same i, offset, R, h)."""
    keys = defaultdict(set)
    for r in t_rows:
        keys[(r[0], r[3], r[4], r[7])].add(r[2])
    paired = sum(len(v) for v in keys.values() if len(v) == 2)
    return dict(rows=len(t_rows), in_pairs=paired, share=round(paired / max(1, len(t_rows)), 4))


def packet_pilot():
    """Nov 17, one session: the grid's chooser actions filled on recorder depth at 1 / 3 / 10 s, held 8 minutes."""
    import pk7
    pk6 = pk7.pk6
    P = pk6.decode(); T1 = pk6.tape(); L6.KEEP6.append(T1); idx, fut, opts = pk6.tokens(); books_ = {k: pk6.Book(P[v]) for k, v in opts.items() if v in P}
    sp = L4.NIFTY; out = defaultdict(list)
    for m in GRID:
        i = L6.at(T1, m)
        if i >= T1.n or T1.minute[i] != m:
            continue
        for d in (1, -1):
            pick = L4.choose4(sp, T1, i, d, L7.E03_ENV, 2500., 30000.)
            if not pick:
                continue
            j, lots, limit = pick; K = float(T1.strikes[j]); kind = "CE" if d > 0 else "PE"; ob = books_.get((K, kind))
            if ob is None:
                continue
            s = m * 60.; units = lots * sp.lot
            for lat in (1., 3., 10.):
                old = pk6.LAT; pk6.LAT = lat
                try:
                    b = pk6.market(ob, s, "BUY", units, limit); sl = pk6.market(ob, s + HOLD * 60., "SELL", units, .05) if b else None
                finally:
                    pk6.LAT = old
                net = None
                if b and sl:
                    net = round((sl[1] - b[1]) * units - pk6.fees_nfo(b[1], units, True) - pk6.fees_nfo(sl[1], units, False), 2)
                k1 = pk6.Book(P[fut["token"]]).at(s); k2 = pk6.Book(P[fut["token"]]).at(s + HOLD * 60.)
                fb = pk6.Book(P[fut["token"]])
                dF = d * (fb.mid(k2) - fb.mid(k1)) if k1 is not None and k2 is not None else None
                out[f"lat{int(lat)}"].append(dict(m=m, d=d, net=net, dF=dF))
    res = {}
    for k, xs in out.items():
        ok = [x for x in xs if x["net"] is not None and x["dF"] is not None]
        orc = [x["net"] for x in ok if x["dF"] > 0]; anti = [x["net"] for x in ok if x["dF"] < 0]
        res[k] = dict(actions=len(xs), filled=len(ok), oracle_side_mean=round(float(np.mean(orc)), 2) if orc else None,
                      wrong_side_mean=round(float(np.mean(anti)), 2) if anti else None,
                      p_curve={f"{p:.2f}": round(p * float(np.mean(orc)) + (1 - p) * float(np.mean(anti)), 2) for p in PS} if orc and anti else None)
    return dict(session="2026-11-17", pilot=True, note="one recorded session: code and coverage only, no verdict", latency=res)
