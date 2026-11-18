"""PLAN4.md section 4 (harness repair R1) and EN34's feasibility, on the 2026 recorded quotes.

rec2026.py and its results stay as frozen receipts. This file fixes the auditor's faults (docs/EXPIRY_RESEARCH_EN26_EN35.md
section 2C) in separately named functions:
  - a scheduled clock exit never uses an earlier quote: the first fresh quote at or after m+9, up to 15:14, or UNRESOLVED
    (booked at minus premium and fees in the funded outcome);
  - lots are sized from the decision-minute ask with a limit of ask x 1.08 against a reserve fixed at the decision;
    the m+1 walked fill must be at or below that limit, else REFUSED;
  - the front future is the dated nearest expiry on or after the day (the archive holds one per index a day, so this
    cannot change a pick; it is still enforced);
  - a quote counts only if usable and its age (receipt - provider) is at most 10 seconds;
  - refused and unexitable decisions stay in the counts.
EN16-R1 / EN18-R1 apply round 3's own verdict rules. EN34 uses decision-time asks only."""
from __future__ import annotations
import math
import numpy as np
import rec2026 as Q

qa, EP = Q.qa, Q.EP
AGE = 10.
FLAT = 359                      # minute index of 15:14 (minutes since 09:15)
M0, M1 = Q.M0, Q.M1


def fresh(r, i):
    return (r is not None and 0 <= i < qa.NM and bool(r["usable"][i]) and np.isfinite(r["bid"][i]) and np.isfinite(r["ask"][i])
            and np.isfinite(r["age"][i]) and r["age"][i] <= AGE)


def mid(r, i):
    return (r["bid"][i] + r["ask"][i]) / 2 if fresh(r, i) else math.nan


def front(q, und, day):
    ks = sorted(k for k in q["fut"] if k[0] == und and k[1] >= day)
    return q["fut"][ks[0]] if ks else None


def synth(q, und, exp, F, i):
    if not np.isfinite(F):
        return math.nan
    for k in sorted(Q.strikes(q, und, exp), key=lambda k: abs(k - F))[:3]:
        c, p = mid(Q.opt(q, und, exp, k, "CE"), i), mid(Q.opt(q, und, exp, k, "PE"), i)
        if np.isfinite(c) and np.isfinite(p):
            return k + c - p
    return math.nan


def band_pick(q, und, exp, S, i, d, skip=0):
    lo, hi = Q.BAND[und]; typ = "CE" if d > 0 else "PE"; out = []
    for k in sorted((k for k in Q.strikes(q, und, exp) if 0 < d * (k - S) <= Q.DIST[und]), key=lambda k: d * k):
        r = Q.opt(q, und, exp, k, typ)
        if fresh(r, i) and lo <= r["ask"][i] <= hi:
            out.append(k)
    if len(out) <= skip:
        return None
    k = out[skip]
    if skip and k != out[0] + d * Q.STEP[und] * skip:
        return None
    return k


def cost_share(q, und, exp, k, d, i):
    r = Q.opt(q, und, exp, k, "CE" if d > 0 else "PE"); lot = q["lot"][und]
    a, b = r["ask"][i], r["bid"][i]
    return ((a - b) * lot + EP.buy_charges(a, lot, Q.FEES[und]) + EP.sell_charges(b, lot, Q.FEES[und])) / (a * lot)


def decision_lots(q, und, k, d, exp, m, most=None):
    """Lots and limit fixed at the decision minute m: limit = ask_m x 1.08 (tick-rounded down), whole reserve inside."""
    r = Q.opt(q, und, exp, k, "CE" if d > 0 else "PE"); lot = q["lot"][und]; f = Q.FEES[und]
    if not fresh(r, m):
        return 0, None
    limit = math.floor(round(r["ask"][m] * 1.08 / .05, 6)) * .05
    for n in range(most or Q.CAP[d], 0, -1):
        if limit * n * lot + EP.buy_charges(limit, n * lot, f) + n * EP.order_fee(f) <= Q.RESERVE[d]:
            return n, round(limit, 2)
    return 0, None


def trade(q, und, exp, k, d, m, lots, limit):
    """Decision at m; buy at m+1 by walking the ask depth (<= limit); stop at the first fresh bid <= 0.65 x entry in
    m+2..m+9; otherwise the clock exit at the first fresh quote at or after m+9 that the bid depth can fill, up to 15:14."""
    r = Q.opt(q, und, exp, k, "CE" if d > 0 else "PE"); lot = q["lot"][und]; units = lots * lot; f = Q.FEES[und]
    b = m + 1
    if not fresh(r, b):
        return dict(status="REFUSED_NO_QUOTE")
    buy = qa.walk_cost(r["askp"][:, b], r["askq"][:, b], units)
    if buy is None:
        return dict(status="REFUSED_THIN")
    if buy > limit + 1e-9:
        return dict(status="REFUSED_LIMIT")
    paid = buy * units + EP.buy_charges(buy, units, f)
    exit_i, reason, sell = None, "CLOCK", None
    for i in range(m + 2, m + 10):
        if fresh(r, i) and r["bid"][i] <= .65 * buy:
            s = qa.walk_cost(r["bidp"][:, i], r["bidq"][:, i], units)
            if s is not None:
                exit_i, reason, sell = i, "STOP", s; break
    if exit_i is None:
        for i in range(m + 9, FLAT + 1):
            if fresh(r, i):
                s = qa.walk_cost(r["bidp"][:, i], r["bidq"][:, i], units)
                if s is not None:
                    exit_i, sell = i, s; break
    if exit_i is None:
        return dict(status="UNRESOLVED", buy=round(buy, 2), lots=lots, pnl=round(-paid - lots * EP.order_fee(f), 2))
    pnl = (sell - buy) * units - EP.buy_charges(buy, units, f) - EP.sell_charges(sell, units, f)
    return dict(status="OK", buy=round(buy, 2), sell=round(sell, 2), lots=lots, pnl=round(pnl, 2), reason=reason, exit_i=exit_i)


def _booked(tr):
    return tr is not None and tr.get("status") in ("OK", "UNRESOLVED")


def en16():
    rows = []
    for day, und, nxt in Q.sessions():
        q = qa.load(day); fut = front(q, und, day)
        F = np.array([mid(fut, i) if fut is not None else math.nan for i in range(qa.NM)]); last = -99
        for m in range(M0, M1):
            if m < last + 10 or not np.isfinite([F[m], F[m - 3], F[m + 8]]).all():
                continue
            chg = F[m] / F[m - 3] - 1
            if abs(chg) < .0004:
                continue
            last = m; d = 1 if chg > 0 else -1
            conf = None
            if nxt:
                a, b = synth(q, und, nxt, F[m], m), synth(q, und, nxt, F[m - 3], m - 3)
                if np.isfinite([a, b]).all():
                    conf = bool(np.sign(a - b) == d and abs(a - b) >= .5 * abs(F[m] - F[m - 3]))
            S = synth(q, und, day, F[m], m); k = band_pick(q, und, day, S, m, d) if np.isfinite(S) else None
            tr = None
            if k:
                _, limit = decision_lots(q, und, k, d, day, m, most=1)
                tr = trade(q, und, day, k, d, m, 1, limit) if limit else dict(status="REFUSED_RESERVE")
            rows.append(dict(day=day, und=und, m=m, d=d, confirmed=conf, fut_move=round(float(d * (F[m + 8] - F[m])), 2), strike=k, trade=tr))
    out = {}
    for g, sel in (("confirmed", True), ("unconfirmed", False), ("unavailable", None)):
        rs = [r for r in rows if r["confirmed"] is sel]
        tp = [r["trade"]["pnl"] for r in rs if _booked(r["trade"])]
        st = {}
        for r in rs:
            s = (r["trade"] or {}).get("status", "NO_STRIKE"); st[s] = st.get(s, 0) + 1
        out[g] = dict(n=len(rs), hit=round(float(np.mean([r["fut_move"] > 0 for r in rs])), 4) if rs else None,
                      trades=len(tp), mean_pnl=round(float(np.mean(tp)), 2) if tp else None, sum_pnl=round(float(sum(tp)), 2), statuses=st)
    c, u = out["confirmed"], out["unconfirmed"]
    if c["n"] < 30:
        verdict = "INCONCLUSIVE"
    else:
        ok = (c["hit"] - u["hit"] >= .05) and c["mean_pnl"] is not None and c["mean_pnl"] > 0 and (u["mean_pnl"] is None or c["mean_pnl"] > u["mean_pnl"])
        verdict = "PASS" if ok else "FAIL"
    return dict(groups=out, verdict=verdict)


def en18():
    rows = []
    for day, und, _ in Q.sessions():
        q = qa.load(day); fut = front(q, und, day)
        for m in range(M0, M1):
            S = synth(q, und, day, mid(fut, m) if fut is not None else math.nan, m)
            if not np.isfinite(S):
                continue
            for d in (1, -1):
                kb = band_pick(q, und, day, S, m, d)
                if kb is None:
                    continue
                ka = band_pick(q, und, day, S, m, d, skip=1)
                cb = cost_share(q, und, day, kb, d, m)
                ca = cost_share(q, und, day, ka, d, m) if ka else math.nan
                ra = Q.opt(q, und, day, ka, "CE" if d > 0 else "PE") if ka else None
                pick_alt = bool(ka and np.isfinite(ca) and ca < cb and ra["aq"][m] >= q["lot"][und])
                kr = ka if pick_alt else kb
                fund = {}
                for n, k in (("base", kb), ("rule", kr)):
                    lots, limit = decision_lots(q, und, k, d, day, m)
                    fund[n] = trade(q, und, day, k, d, m, lots, limit) if lots else dict(status="REFUSED_RESERVE")
                rows.append(dict(day=day, und=und, m=m, d=d, alt_chosen=pick_alt, cost_base=cb, cost_rule=ca if pick_alt else cb,
                                 fund={n: (v["pnl"] if _booked(v) else None) for n, v in fund.items()},
                                 status={n: v.get("status") for n, v in fund.items()}))
    res = {}
    for u in ("NIFTY", "SENSEX"):
        rs = [r for r in rows if r["und"] == u and r["fund"]["base"] is not None and r["fund"]["rule"] is not None]
        res[u] = dict(n=len(rs), rows=sum(r["und"] == u for r in rows), alt_chosen=sum(r["alt_chosen"] for r in rs),
                      fund_rule=round(float(np.mean([r["fund"]["rule"] for r in rs])), 2) if rs else None,
                      fund_base=round(float(np.mean([r["fund"]["base"] for r in rs])), 2) if rs else None,
                      cost_rule=round(float(np.mean([r["cost_rule"] for r in rs])), 5) if rs else None,
                      cost_base=round(float(np.mean([r["cost_base"] for r in rs])), 5) if rs else None)
    allr = [r for r in rows if r["fund"]["base"] is not None and r["fund"]["rule"] is not None]
    sess = {(r["day"], r["und"]) for r in allr}
    ge = sum(np.mean([x["fund"]["rule"] for x in allr if (x["day"], x["und"]) == s]) >= np.mean([x["fund"]["base"] for x in allr if (x["day"], x["und"]) == s]) for s in sess)
    ok = all(res[u]["fund_rule"] is not None and res[u]["fund_rule"] > res[u]["fund_base"] for u in res) and ge >= .6 * len(sess) \
        and bool(allr) and float(np.mean([r["cost_rule"] for r in allr])) < float(np.mean([r["cost_base"] for r in allr]))
    st = {}
    for r in rows:
        s = r["status"]["base"]; st[s] = st.get(s, 0) + 1
    return dict(by_index=res, sessions=len(sess), sessions_rule_ge_base=int(ge), verdict="PASS" if ok else "FAIL", base_statuses=st, n_rows=len(rows))


def en34():
    """EN34 feasibility: one whole lot of the next expiry's ATM or first OTM strike, by side, at every minute 13:00-15:00,
    priced by walking the decision-time ask depth plus fees and one exit order charge per lot."""
    out = {}
    for day, und, nxt in Q.sessions():
        if not nxt:
            continue
        q = qa.load(day); fut = front(q, und, day); lot = q["lot"][und]; f = Q.FEES[und]; step = Q.STEP[und]
        for m in range(M0, 345):
            S = synth(q, und, day, mid(fut, m) if fut is not None else math.nan, m)
            if not np.isfinite(S):
                continue
            atm = round(S / step) * step
            for d in (1, -1):
                best = math.inf
                for k in (atm, atm + d * step):
                    r = Q.opt(q, und, nxt, int(k), "CE" if d > 0 else "PE")
                    if not fresh(r, m):
                        continue
                    a = qa.walk_cost(r["askp"][:, m], r["askq"][:, m], lot)
                    if a is not None:
                        best = min(best, a * lot + EP.buy_charges(a, lot, f) + EP.order_fee(f))
                g = out.setdefault((und, d), dict(minutes=0, feasible=0, costs=[]))
                if np.isfinite(best):
                    g["minutes"] += 1; g["costs"].append(best); g["feasible"] += best <= Q.RESERVE[d]
    res = {f"{u}|{'CE' if d > 0 else 'PE'}": dict(minutes=g["minutes"], feasible=g["feasible"],
                                                 share=round(g["feasible"] / g["minutes"], 4) if g["minutes"] else None,
                                                 median_cost=round(float(np.median(g["costs"])), 2) if g["costs"] else None,
                                                 reserve=Q.RESERVE[d])
           for (u, d), g in sorted(out.items())}
    tot = sum(v["minutes"] for v in res.values()); feas = sum(v["feasible"] for v in res.values())
    share = feas / tot if tot else 0.
    return dict(by_index_side=res, share=round(share, 4), verdict="NOT FEASIBLE" if share < .05 else "DATA_UNAVAILABLE")


def score():
    return dict(EN16_R1=en16(), EN18_R1=en18(), EN34=en34())


def check():
    """Repair regression cases on a synthetic record (counts only)."""
    z = lambda v: np.full(qa.NM, v, float)  # noqa: E731
    r = {"bid": z(10.), "ask": z(10.1), "usable": np.ones(qa.NM, bool), "age": z(1.), "aq": z(1e6),
         "askp": np.vstack([z(10.1)] + [z(np.nan)] * 4), "askq": np.vstack([z(1e6)] + [z(np.nan)] * 4),
         "bidp": np.vstack([z(10.)] + [z(np.nan)] * 4), "bidq": np.vstack([z(1e6)] + [z(np.nan)] * 4)}
    q = {"opt": {("NIFTY", "2026-01-06", 25000, "CE"): r}, "fut": {}, "lot": {"NIFTY": 65}}
    m = 250
    r["usable"][m + 9] = False                                           # the scheduled clock quote is missing
    t = trade(q, "NIFTY", "2026-01-06", 25000, 1, m, 1, 11.)
    assert t["status"] == "OK" and t["exit_i"] == m + 10, t            # waits forward, never m+8
    r["usable"][m + 9:] = False
    assert trade(q, "NIFTY", "2026-01-06", 25000, 1, m, 1, 11.)["status"] == "UNRESOLVED"
    r["usable"][:] = True; r["age"][m + 1] = 30.
    assert trade(q, "NIFTY", "2026-01-06", 25000, 1, m, 1, 11.)["status"] == "REFUSED_NO_QUOTE"    # stale entry quote
    r["age"][:] = 1.; r["askp"][0, m + 1] = 12.
    assert trade(q, "NIFTY", "2026-01-06", 25000, 1, m, 1, 11.)["status"] == "REFUSED_LIMIT"       # m+1 above the decision limit
    r["askp"][0, :] = 10.1; r["ask"][m] = 20.
    assert decision_lots(q, "NIFTY", 25000, 1, "2026-01-06", m) == (0, None)                        # sized at m's ask, not m+1's
    r["ask"][m] = 15.
    assert decision_lots(q, "NIFTY", 25000, 1, "2026-01-06", m) == (1, 16.2)
    s = Q.sessions(); assert len(s) == 19
    print("CHECK_OK rec2026b: forward-only clock exit, unresolved, stale and above-limit refusals, decision-time sizing;", len(s), "sessions")


if __name__ == "__main__":
    check()
