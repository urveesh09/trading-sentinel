"""EN16 (next-expiry confirmation) and EN18 (strike by executable cost) on the 2026 recorded quotes (PLAN3.md).

Source: the forward-panel export 20261117T103003Z (Production's quote archive: about one snapshot a minute per
contract, real best bid/ask and 5-level depth, both weekly expiries, front futures). Read in place through the sn101
loader with every file hash-checked against the export manifest; day pickles are rebuilt into this study's _local/.
Sealed days only (Nov 17 is unsealed and excluded). Expiry sessions: 9 NIFTY (Tuesdays, holiday-shifted) and 10 SENSEX
(Thursdays), Sep 10 - Nov 13 2026. Minute index m = minutes since 09:15 (13:00 = 225).

Spot on an expiry afternoon is read as the expiring chain's synthetic forward at the strike nearest the future
(K + mid call - mid put): with hours to expiry there is no carry, so it is the index the contracts settle on.
Prices: buys walk the real ask depth for whole lots, sells walk the real bid depth; a sell needs a usable quote in
the exit minute or the one before (the archive's drift pitfall). Charges: the engine's NFO / BFO schedules."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path.insert(0, str(ROOT / "python-engine")); sys.path.insert(0, str(ROOT / "docs/research/fno/2026-11-13-sn101"))
import expiry_paper as EP  # noqa: E402
import qa  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261117T103003Z")
qa.LOCAL = HERE / "_local" / "quotes-20261117"
qa.LOCAL.mkdir(parents=True, exist_ok=True)
BAND = {"NIFTY": (5., 20.), "SENSEX": (16.25, 65.)}
DIST = {"NIFTY": 200, "SENSEX": 400}
STEP = {"NIFTY": 50, "SENSEX": 100}
FEES = {"NIFTY": EP.fee_schedule("NFO"), "SENSEX": EP.fee_schedule("BFO")}
RESERVE = {1: 1250., -1: 2500.}
CAP = {1: 3, -1: 6}
M0, M1 = 225, 338          # decisions 13:00 .. 14:52 (exit by m+9 <= 15:01)


def sessions():
    m = qa.manifest(); sealed = set(qa.days())
    out = []
    for und, exps in m["option_expiries"].items():
        for e in exps:
            if e in sealed:
                nxt = [x for x in exps if x > e]
                out.append((e, und, nxt[0] if nxt else None))
    return sorted(out)


def mid(rec, i):
    if rec is None or not rec["usable"][i] or np.isnan(rec["bid"][i]) or np.isnan(rec["ask"][i]):
        return math.nan
    return (rec["bid"][i] + rec["ask"][i]) / 2


def opt(q, und, exp, k, typ):
    return q["opt"].get((und, exp, int(k), typ))


def strikes(q, und, exp):
    return sorted({k[2] for k in q["opt"] if k[0] == und and k[1] == exp})


def synth(q, und, exp, F, i):
    """K + mid(CE) - mid(PE) at the listed strike nearest F with both sides usable."""
    if not np.isfinite(F):
        return math.nan
    for k in sorted(strikes(q, und, exp), key=lambda k: abs(k - F))[:3]:
        c, p = mid(opt(q, und, exp, k, "CE"), i), mid(opt(q, und, exp, k, "PE"), i)
        if np.isfinite(c) and np.isfinite(p):
            return k + c - p
    return math.nan


def band_pick(q, und, exp, S, i, d, skip=0):
    """Nearest OTM strike (plus `skip` steps further out) in the band, inside the distance, usable at i."""
    lo, hi = BAND[und]; typ = "CE" if d > 0 else "PE"; out = []
    for k in sorted((k for k in strikes(q, und, exp) if 0 < d * (k - S) <= DIST[und]), key=lambda k: d * k):
        r = opt(q, und, exp, k, typ)
        if r is not None and r["usable"][i] and np.isfinite(r["ask"][i]) and np.isfinite(r["bid"][i]) and lo <= r["ask"][i] <= hi:
            out.append(k)
    if len(out) <= skip:
        return None
    k = out[skip]
    if skip and k != out[0] + d * STEP[und] * skip:
        return None                                                  # the alternative is exactly the adjacent strike
    return k


def trade(q, und, exp, k, d, m, lots):
    """Buy `lots` at the m+1 ask depth; sell at the first bid <= 0.65 x entry (m+2..m+9) or at m+9's bid depth."""
    r = opt(q, und, exp, k, "CE" if d > 0 else "PE"); lot = q["lot"][und]; units = lots * lot; fee = FEES[und]
    b = m + 1
    if r is None or not r["usable"][b]:
        return None
    buy = qa.walk_cost(r["askp"][:, b], r["askq"][:, b], units)
    if buy is None:
        return None
    exit_i, reason = None, "CLOCK"
    for i in range(m + 2, m + 10):
        if r["usable"][i] and np.isfinite(r["bid"][i]) and r["bid"][i] <= .65 * buy:
            exit_i, reason = i, "STOP"; break
    if exit_i is None:
        exit_i = qa.last_before(r, m + 9, m + 8)
    if exit_i is None:
        return dict(status="NO_EXIT_QUOTE")
    sell = qa.walk_cost(r["bidp"][:, exit_i], r["bidq"][:, exit_i], units)
    if sell is None:
        return dict(status="THIN_EXIT")
    pnl = (sell - buy) * units - EP.buy_charges(buy, units, fee) - EP.sell_charges(sell, units, fee)
    return dict(status="OK", buy=round(buy, 2), sell=round(sell, 2), lots=lots, pnl=round(pnl, 2), reason=reason)


def funded_lots(q, und, k, d, exp, m):
    r = opt(q, und, exp, k, "CE" if d > 0 else "PE"); lot = q["lot"][und]
    if r is None or not r["usable"][m + 1] or np.isnan(r["ask"][m + 1]):
        return 0
    a = r["ask"][m + 1]
    for n in range(CAP[d], 0, -1):
        if a * n * lot + EP.buy_charges(a, n * lot, FEES[und]) + n * EP.order_fee(FEES[und]) <= RESERVE[d]:
            return n
    return 0


def cost_share(q, und, exp, k, d, i):
    r = opt(q, und, exp, k, "CE" if d > 0 else "PE"); lot = q["lot"][und]
    a, b = r["ask"][i], r["bid"][i]
    return ((a - b) * lot + EP.buy_charges(a, lot, FEES[und]) + EP.sell_charges(b, lot, FEES[und])) / (a * lot)


def day_data(day):
    q = qa.load(day)
    return q


def en16():
    rows = []
    for day, und, nxt in sessions():
        q = day_data(day); fut = qa.front_fut(q, und)
        F = np.array([mid(fut, i) for i in range(qa.NM)]); last = -99
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
            tr = trade(q, und, day, k, d, m, 1) if k else None
            rows.append(dict(day=day, und=und, m=m, d=d, confirmed=conf, fut_move=round(float(d * (F[m + 8] - F[m])), 2),
                             strike=k, trade=tr))
    out = {}
    for g, sel in (("confirmed", True), ("unconfirmed", False), ("unavailable", None)):
        rs = [r for r in rows if r["confirmed"] is sel]
        tp = [r["trade"]["pnl"] for r in rs if r["trade"] and r["trade"].get("status") == "OK"]
        out[g] = dict(n=len(rs), hit=round(float(np.mean([r["fut_move"] > 0 for r in rs])), 4) if rs else None,
                      mean_move=round(float(np.mean([r["fut_move"] for r in rs])), 2) if rs else None,
                      trades=len(tp), mean_pnl=round(float(np.mean(tp)), 2) if tp else None, sum_pnl=round(float(sum(tp)), 2),
                      by_index={u: dict(n=sum(r["und"] == u for r in rs),
                                        hit=round(float(np.mean([r["fut_move"] > 0 for r in rs if r["und"] == u])), 4) if any(r["und"] == u for r in rs) else None)
                                for u in ("NIFTY", "SENSEX")})
    c, u = out["confirmed"], out["unconfirmed"]
    if c["n"] < 30:
        verdict = "INCONCLUSIVE"
    else:
        ok = (c["hit"] - u["hit"] >= .05) and c["mean_pnl"] is not None and c["mean_pnl"] > 0 and (u["mean_pnl"] is None or c["mean_pnl"] > u["mean_pnl"])
        verdict = "PASS" if ok else "FAIL"
    return dict(groups=out, verdict=verdict, rows=rows)


def en18():
    rows = []
    for day, und, _ in sessions():
        q = day_data(day); fut = qa.front_fut(q, und)
        for m in range(M0, M1):
            F = mid(fut, m)
            S = synth(q, und, day, F, m)
            if not np.isfinite(S):
                continue
            for d in (1, -1):
                kb = band_pick(q, und, day, S, m, d)
                if kb is None:
                    continue
                ka = band_pick(q, und, day, S, m, d, skip=1)
                cb = cost_share(q, und, day, kb, d, m)
                ca = cost_share(q, und, day, ka, d, m) if ka else math.nan
                ra = opt(q, und, day, ka, "CE" if d > 0 else "PE") if ka else None
                pick_alt = bool(ka and np.isfinite(ca) and ca < cb and ra["aq"][m] >= q["lot"][und])
                kr = ka if pick_alt else kb
                one = {n: trade(q, und, day, k, d, m, 1) for n, k in (("base", kb), ("rule", kr))}
                fund = {n: trade(q, und, day, k, d, m, funded_lots(q, und, k, d, day, m)) if funded_lots(q, und, k, d, day, m) else None
                        for n, k in (("base", kb), ("rule", kr))}
                rows.append(dict(day=day, und=und, m=m, d=d, base=kb, alt=ka, rule=kr, alt_chosen=pick_alt,
                                 cost_base=round(cb, 5), cost_rule=round(ca if pick_alt else cb, 5),
                                 one={n: (v["pnl"] if v and v.get("status") == "OK" else None) for n, v in one.items()},
                                 fund={n: (v["pnl"] if v and v.get("status") == "OK" else None) for n, v in fund.items()}))
    res = {}
    for u in ("NIFTY", "SENSEX"):
        rs = [r for r in rows if r["und"] == u and r["fund"]["base"] is not None and r["fund"]["rule"] is not None]
        days = sorted({r["day"] for r in rs})
        per = {dd: (np.mean([r["fund"]["rule"] for r in rs if r["day"] == dd]), np.mean([r["fund"]["base"] for r in rs if r["day"] == dd])) for dd in days}
        res[u] = dict(n=len(rs), alt_chosen=sum(r["alt_chosen"] for r in rs), sessions=len(days),
                      fund_rule=round(float(np.mean([r["fund"]["rule"] for r in rs])), 2) if rs else None,
                      fund_base=round(float(np.mean([r["fund"]["base"] for r in rs])), 2) if rs else None,
                      one_rule=round(float(np.mean([r["one"]["rule"] for r in rs if r["one"]["rule"] is not None])), 2) if rs else None,
                      one_base=round(float(np.mean([r["one"]["base"] for r in rs if r["one"]["base"] is not None])), 2) if rs else None,
                      cost_rule=round(float(np.mean([r["cost_rule"] for r in rs])), 5) if rs else None,
                      cost_base=round(float(np.mean([r["cost_base"] for r in rs])), 5) if rs else None,
                      sessions_rule_ge_base=sum(a >= b for a, b in per.values()))
    allr = [r for r in rows if r["fund"]["base"] is not None and r["fund"]["rule"] is not None]
    sess = {(r["day"], r["und"]) for r in allr}
    ge = sum(np.mean([x["fund"]["rule"] for x in allr if (x["day"], x["und"]) == s]) >= np.mean([x["fund"]["base"] for x in allr if (x["day"], x["und"]) == s]) for s in sess)
    ok = all(res[u]["fund_rule"] is not None and res[u]["fund_rule"] > res[u]["fund_base"] for u in res) and ge >= .6 * len(sess) \
        and float(np.mean([r["cost_rule"] for r in allr])) < float(np.mean([r["cost_base"] for r in allr]))
    return dict(by_index=res, sessions=len(sess), sessions_rule_ge_base=int(ge), verdict="PASS" if ok else "FAIL",
                rows_sample=rows[:5], n_rows=len(rows))


def check():
    s = sessions()
    assert len(s) == 19 and sum(u == "NIFTY" for _, u, _ in s) == 9, s
    for day, und, nxt in s:
        q = day_data(day); assert qa.front_fut(q, und) is not None and nxt and strikes(q, und, nxt), (day, und)
    print("CHECK_OK rec2026:", len(s), "sealed expiry sessions (9 NIFTY, 10 SENSEX), every day file hash-checked, next expiry listed on each")


def score():
    return dict(EN16=en16(), EN18=en18())


if __name__ == "__main__":
    check()
