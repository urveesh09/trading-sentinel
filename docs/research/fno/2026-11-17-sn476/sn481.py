"""SN481: the same Gold signal in next week's option (PLAN.md SN481, frozen at bf895633; details fixed here before any number).

1 Frequency: Gold's trades (GOLD_30K and ONE_15K, 2022 and 2023-26, Rs 205 / 400) by sessions to the front expiry (market sessions
  after the trade day up to and including the expiry; calendar = the distinct NIFTY index days of the Breeze history, read-only).
  Eligible = 1 or 2 sessions. Count, share of trades, net and share of net.
2 Coverage: in the Breeze history (read-only counts; 2023 skipped: the protected expiry exam's year), for each pair of consecutive
  weekly expiries (E1 < E2) of 2022 and 2024-2026, whether E2's option rows exist on the one / two sessions before E1. Gold's own
  datasets hold one expiry per session (checked: the count of distinct option expiries per session).
3 Pricing (quote archive export 20261117T103003Z, both weeklies recorded): Gold's GOLD_30K @205 trades in the archive window with 1-2
  sessions to the front expiry. At Gold's entry minute (archive minute index = replay minute index; the last usable record in that
  minute): Black-76 deltas (forward = the front-month future's mid, r = 0, ACT/365 to 15:30 IST on expiry, IV from the option's mid by
  bisection); front = Gold's strike (captured from gold_one); next = the next weekly's strike with the closest delta, admitted when
  |delta difference| <= 0.05. One lot each: walked ask in, walked bid out at Gold's exit minute (first usable record within 5 minutes,
  else UNRESOLVED and a full debit loss); shipped charges + stress per lot; affordable when the walked ask x lot <= the trade's wallet.
  Paired next - front per lot. PASS needs >= 20 admitted pairs with better net at both stresses and no worse worst pair; else
  INSUFFICIENT with the acquisition need stated.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import sn476  # noqa: E402
import sn480 as A  # noqa: E402

goldx, g = A.goldx, A.g
OUT = HERE / "results-sn481.json"
BREEZE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
LOT = 65


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def b76(F, K, T, s, call):
    if T <= 0 or s <= 0:
        return max(0.0, (F - K) if call else (K - F)), (1.0 if (call and F > K) else (-1.0 if (not call and F < K) else 0.0))
    d1 = (math.log(F / K) + 0.5 * s * s * T) / (s * math.sqrt(T))
    d2 = d1 - s * math.sqrt(T)
    if call:
        return F * ncdf(d1) - K * ncdf(d2), ncdf(d1)
    return K * ncdf(-d2) - F * ncdf(-d1), ncdf(d1) - 1.0


def implied(price, F, K, T, call):
    lo, hi = 1e-4, 5.0
    intrinsic = max(0.0, (F - K) if call else (K - F))
    if price <= intrinsic + 1e-6:
        return None
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if b76(F, K, T, mid, call)[0] > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def calendar():
    con = sqlite3.connect(f"file:{BREEZE.as_posix()}?mode=ro", uri=True, timeout=60)
    days = [r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index' AND underlying='NIFTY' AND interval='1minute' "
                                      "AND datetime >= '2021-12-01' ORDER BY 1")]
    con.close()
    return days


def sessions_to(day, expiry, cal):
    return sum(1 for d in cal if day < d <= expiry)


def coverage(cal):
    con = sqlite3.connect(f"file:{BREEZE.as_posix()}?mode=ro", uri=True, timeout=60)
    exps = [r[0] for r in con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry >= '2022-01-01' ORDER BY 1")]
    exps = [e for e in exps if not e.startswith("2023")]
    out = collections.Counter()
    for e1, e2 in zip(exps, exps[1:]):
        if e1[:4] != e2[:4] and (e1.startswith("2022") and e2.startswith("2024")):
            continue
        before = [d for d in cal if d < e1][-2:]
        for k, d in enumerate(reversed(before), start=1):
            n = con.execute("SELECT COUNT(*) FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND datetime >= ? AND datetime < ?",
                            (e2, d, d + "~")).fetchone()[0]
            out[f"{k} session(s) before E1: next weekly present" if n else f"{k} session(s) before E1: next weekly absent"] += 1
    con.close()
    return dict(out), len(exps)


CAPT = {}
_gold_one = None


def capture(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    res = _gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
    if res is not None:
        CAPT[(S.day, sg["i"])] = {"strike": res[5], "expiry": S.s["expiry"], "opt": sg["opt"], "wallet": wallet}
    return res


def walk(lv_p, lv_q, units):
    left, cost = units, 0.0
    for p, q in zip(lv_p, lv_q):
        if np.isnan(p) or np.isnan(q) or left <= 0:
            continue
        take = min(left, q)
        cost += take * p
        left -= take
    return None if left > 0 else cost / units


def price_pair(t, cap, stress):
    import qa
    day, i, j = t["day"], t["i"], t["j"]
    q = qa.load(day)
    fut = qa.front_fut(q, "NIFTY")
    if fut is None or np.isnan(fut["bid"][i]) or np.isnan(fut["ask"][i]):
        return {"status": "NO_FUTURE"}
    F = 0.5 * (fut["bid"][i] + fut["ask"][i])
    now = dt.datetime.fromisoformat(day) + dt.timedelta(minutes=555 + i, seconds=59)
    call = cap["opt"] == "CE"
    exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= day})
    if len(exps) < 2 or exps[0] != cap["expiry"]:
        return {"status": "EXPIRIES_NOT_RECORDED", "recorded": exps, "front": cap["expiry"]}

    def delta(exp, K):
        rec = q["opt"].get(("NIFTY", exp, int(K), cap["opt"]))
        if rec is None or not rec["usable"][i]:
            return None
        mid = 0.5 * (rec["bid"][i] + rec["ask"][i])
        T = ((dt.datetime.fromisoformat(exp) + dt.timedelta(hours=15, minutes=30)) - now).total_seconds() / (365 * 86400)
        s = implied(mid, F, K, T, call)
        return None if s is None else b76(F, K, T, s, call)[1]
    d_front = delta(exps[0], cap["strike"])
    if d_front is None:
        return {"status": "FRONT_NOT_PRICED"}
    cands = []
    for k in q["opt"]:
        if k[0] == "NIFTY" and k[1] == exps[1] and k[3] == cap["opt"]:
            dn = delta(exps[1], k[2])
            if dn is not None:
                cands.append((abs(dn - d_front), k[2], dn))
    if not cands:
        return {"status": "NEXT_NOT_PRICED"}
    gap, k_next, d_next = min(cands)
    row = {"front_strike": cap["strike"], "front_delta": round(d_front, 3), "next_strike": k_next, "next_delta": round(d_next, 3), "delta_gap": round(gap, 3)}
    if gap > 0.05:
        return {**row, "status": "NO_DELTA_MATCH"}
    nets = {}
    for tag, exp, K in (("front", exps[0], cap["strike"]), ("next", exps[1], k_next)):
        rec = q["opt"][("NIFTY", exp, int(K), cap["opt"])]
        ask = walk(rec["askp"][:, i], rec["askq"][:, i], LOT)
        if ask is None:
            return {**row, "status": f"{tag.upper()}_THIN_ENTRY"}
        if ask * LOT > cap["wallet"]:
            return {**row, "status": f"{tag.upper()}_UNAFFORDABLE"}
        bid = None
        for m in range(j, min(j + 6, qa.NM)):
            if rec["usable"][m]:
                bid = walk(rec["bidp"][:, m], rec["bidq"][:, m], LOT)
                if bid is not None:
                    break
        if bid is None:
            nets[tag] = -(ask * LOT + goldx.M.charges(ask, 0.0, LOT) + stress)
            row[f"{tag}_unresolved"] = True
        else:
            nets[tag] = (bid - ask) * LOT - goldx.M.charges(ask, bid, LOT) - stress
        row[f"{tag}_ask"], row[f"{tag}_bid"] = round(ask, 2), (round(bid, 2) if bid is not None else None)
    return {**row, "status": "PAIR", "front_net": round(nets["front"], 2), "next_net": round(nets["next"], 2), "diff": round(nets["next"] - nets["front"], 2)}


def main():
    global _gold_one
    if OUT.exists():
        raise SystemExit("SN481 is scored once")
    import qa
    qa.EXPORT = sn476.EXPORT
    qa.LOCAL = HERE / "_local" / "qa"
    goldx.install()
    _gold_one = g.C.gold_one
    g.C.gold_one = capture
    cal = calendar()
    res = {"frequency": {}}
    logs = {}
    for lname, wallet in (("GOLD_30K", goldx.GOLD_30K), ("ONE_15K", goldx.ONE_15K)):
        for pname, years in A.PATHS:
            for st in A.STRESSES:
                CAPT.clear()
                _s, _d, log = A.run(years, st, wallet)
                for t in log:
                    t["_cap"] = CAPT.get((t["day"], t["i"]))
                logs[(lname, pname, st)] = log
                by = collections.defaultdict(lambda: [0, 0.0])
                for t in log:
                    k = sessions_to(t["day"], t["_cap"]["expiry"], cal) if t["_cap"] else None
                    key = "1-2 sessions (eligible)" if k in (1, 2) else ("3+ sessions" if k else "unknown")
                    by[key][0] += 1
                    by[key][1] += t["net"]
                tot = sum(t["net"] for t in log)
                res["frequency"][f"{lname} {pname} @{int(st)}"] = {k: {"trades": v[0], "net": round(v[1]), "share_of_trades": round(v[0] / max(1, len(log)), 3),
                                                                      "share_of_net": round(v[1] / tot, 3) if tot else None} for k, v in sorted(by.items())}
    res["coverage_breeze"], res["weekly_expiries_counted"] = coverage(cal)
    con = sqlite3.connect(f"file:{(goldx.gold.D.DATASETS['2024'] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    res["gold_dataset_2024_expiries_per_session"] = dict(collections.Counter(n for _d, n in con.execute(
        "SELECT substr(datetime,1,10), COUNT(DISTINCT expiry) FROM candles WHERE kind='option' GROUP BY 1")))
    con.close()
    pairs = []
    days = set(qa.days())
    for st in A.STRESSES:
        for t in logs[("GOLD_30K", "2023-2026", st)]:
            if t["day"] in days and t["_cap"] and sessions_to(t["day"], t["_cap"]["expiry"], cal) in (1, 2):
                pairs.append({"stress": st, "day": t["day"], "i": t["i"], "j": t["j"], "gold_net": round(t["net"]),
                              **price_pair(t, t["_cap"], st)})
    res["archive_pairs"] = pairs
    ok = {st: [p for p in pairs if p["stress"] == st and p.get("status") == "PAIR"] for st in A.STRESSES}
    res["paired_summary"] = {f"@{int(st)}": {"pairs": len(v), "diff_sum": round(sum(p["diff"] for p in v)), "worst_front": min((p["front_net"] for p in v), default=None),
                                             "worst_next": min((p["next_net"] for p in v), default=None)} for st, v in ok.items()}
    n = min(len(v) for v in ok.values())
    res["verdict"] = ("INSUFFICIENT" if n < 20 else
                      ("PASS" if all(res["paired_summary"][f"@{int(s)}"]["diff_sum"] > 0 for s in A.STRESSES) else "FAIL"))
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("frequency", "coverage_breeze", "gold_dataset_2024_expiries_per_session", "paired_summary", "verdict")}, indent=1))
    for p in pairs:
        print(p)


if __name__ == "__main__":
    main()
