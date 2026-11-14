"""SN209 - TEST, real quotes and the two unseen exams (PLAN.md SN208 + SN209 rules, applied to WK-S by the
amendment). Frozen before it runs; run once.
Candidates (nothing chosen here): WK-S (SN204 pick), its runner-up, WK-S sized by SN205 rule B (2 lots at rho <= 0.8,
1 lot at rho <= 1.1, skip above; it passed its frozen check), and for the record the always-sell ATM straddle (k1
settle) and the defined-risk WK-A (SN203, failed development).
1. TEST: the development engine on the weeks whose first session is on or after 2026-08-20 (HAR walk-forward).
2. Real quotes (forward-panel archive, Sep 10 - Nov 12 2026, 15:15): for WK-S's legs on NIFTY and SENSEX, the real
   half-spread vs the model's; the sell price walking the bid depth for one lot vs the model bid; TEST entries inside
   the archive repriced on the real bid depth.
3. Exams: NIFTY weekly expiries Dec 2 2021 - Mar 24 2022 and SENSEX Oct 4 2024 - Apr 30 2026 (SN201 mirrors, never read
   before this run), lot 65 / 20, NFO / BFO charges, Rs 100 per leg-lot; rule B with the frozen development HAR beta.
Pass rules 4 (TEST >= 0) and 5 (NIFTY exam > 0 and SENSEX exam > 0)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat  # noqa: E402
import wk  # noqa: E402

sys.path.insert(0, str(wk.FNO / "2026-11-13-sn101"))
import qa  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261113T103001Z")
I_ARCH = 360                                   # 15:15 in the archive's minute index (09:15 = 0)


def ledger(trades, lots=None):
    lots = lots or [1] * len(trades)
    x = np.array([t["net"] * n for t, n in zip(trades, lots)])
    q, mo = {}, {}
    for t, v in zip(trades, x):
        q[feat.quarter(t["entry"])] = q.get(feat.quarter(t["entry"]), 0.0) + v
        mo[t["exit_day"][:7]] = mo.get(t["exit_day"][:7], 0.0) + v
    order = np.argsort(x)
    return {"weeks": int(sum(n > 0 for n in lots)), "net": round(float(x.sum())), "mean": round(float(x[np.array(lots) > 0].mean())) if any(lots) else 0,
            "win_pct": round(100 * float((x[np.array(lots) > 0] > 0).mean()), 1) if any(lots) else 0.0,
            "worst": round(float(x.min())) if len(x) else 0, "best": round(float(x.max())) if len(x) else 0,
            "by_quarter": {k: round(v) for k, v in sorted(q.items())},
            "months_positive": f"{sum(v > 0 for v in mo.values())} of {len(mo)}", "worst_month": round(min(mo.values())) if mo else 0,
            "worst_5": [{"entry": trades[i]["entry"], "expiry": trades[i]["expiry"], "net": round(float(x[i])), "reason": trades[i]["reason"],
                         "move_pct": round(100 * (trades[i]["S_T"] / trades[i]["S0"] - 1), 2) if trades[i].get("S_T") and trades[i].get("S0") else None}
                        for i in order[:5]],
            "weeks_list": [{"entry": t["entry"], "net": round(t["net"] * n), "lots": n} for t, n in zip(trades, lots)]}


def rule_b_lots(dl, trades, beta=None):
    out = []
    for t in trades:
        r = dl.rho(t, beta)
        out.append(1 if r is None else (2 if r <= 0.8 else (1 if r <= 1.1 else 0)))
    return out


def candidates(mk, data, weeks, picks, beta=None):
    dl = feat.Daily(data)
    A, B = picks["WK-S"], picks["runner-up"]
    a_tr = wk.book(mk, data, weeks, A)
    out = {"WK-S " + wk.vname(A): ledger(a_tr), "runner-up " + wk.vname(B): ledger(wk.book(mk, data, weeks, B)),
           "WK-S sized by SN205 rule B": ledger(a_tr, rule_b_lots(dl, a_tr, beta)),
           "record: always-sell ATM straddle k1 settle": ledger(wk.book(mk, data, weeks, ("STRADDLE", 1, "settle", None))),
           "record: WK-A (defined risk) IC 1.0/1.0 k1 settle": ledger(wk.book(mk, data, weeks, ("IC 1.0/1.0", 1, "settle", None)))}
    return out, a_tr


def real_quotes(test_trades):
    days = qa.days()
    rows = {"NIFTY": [], "SENSEX": []}
    by_day = {}
    for d in days:
        q = qa.load(d)
        by_day[d] = q
        for und, mk in (("NIFTY", wk.NIFTY), ("SENSEX", wk.SENSEX)):
            exps = sorted({k[1] for k in q["opt"] if k[0] == und and k[1] > d})
            if not exps:
                continue
            e = exps[0]
            mids = {}
            for (u, ee, k, o), rec in q["opt"].items():
                if u == und and ee == e:
                    i = qa.last_before(rec, I_ARCH, I_ARCH - 10)
                    if i is not None:
                        mids[(k, o)] = (rec, i)
            ks = sorted({k for k, o in mids if o == "CE"} & {k for k, o in mids if o == "PE"})
            if not ks:
                continue
            mid = lambda k, o: (mids[(k, o)][0]["bid"][mids[(k, o)][1]] + mids[(k, o)][0]["ask"][mids[(k, o)][1]]) / 2  # noqa: E731
            K0 = min(ks, key=lambda k: abs(mid(k, "CE") - mid(k, "PE")))
            Q = mid(K0, "CE") + mid(K0, "PE")
            dd = wk.dist(mk, 0.5 * Q)
            for k, o in ((K0 + dd, "CE"), (K0 - dd, "PE")):
                if (k, o) not in mids:
                    continue
                rec, i = mids[(k, o)]
                b, a, m = rec["bid"][i], rec["ask"][i], mid(k, o)
                fill = qa.walk_cost(rec["bidp"][:, i], rec["bidq"][:, i], q["lot"][und])
                rows[und].append({"day": d, "mid": m, "real_half": (a - b) / 2, "model_half": (wk.ask(mk, m) - wk.bid(mk, m)) / 2,
                                  "real_sell_1lot": fill, "model_bid": wk.bid(mk, m)})
    out = {}
    for und, r in rows.items():
        if not r:
            continue
        lot = wk.NIFTY["lot"] if und == "NIFTY" else wk.SENSEX["lot"]
        rs = [x for x in r if x["real_sell_1lot"] is not None]
        out[und] = {"legs": len(r), "days": len({x["day"] for x in r}), "mid_median": round(float(np.median([x["mid"] for x in r])), 2),
                    "real_half_spread_mean": round(float(np.mean([x["real_half"] for x in r])), 3),
                    "model_half_spread_mean": round(float(np.mean([x["model_half"] for x in r])), 3),
                    "real_sell_minus_model_bid_rs_per_leg_lot": round(float(np.mean([(x["real_sell_1lot"] - x["model_bid"]) * lot for x in rs])), 1) if rs else None,
                    "one_lot_fillable_pct": round(100 * len(rs) / len(r), 1)}
    rep = []
    for t in test_trades:
        q = by_day.get(t["entry"])
        if q is None:
            continue
        adj, ok = 0.0, True
        for k, o, sg in t["legs"]:
            rec = q["opt"].get(("NIFTY", t["expiry"], k, o))
            i = qa.last_before(rec, I_ARCH, I_ARCH - 10) if rec else None
            if i is None:
                ok = False
                break
            fill = qa.walk_cost(rec["bidp"][:, i], rec["bidq"][:, i], wk.NIFTY["lot"])
            m = (rec["bid"][i] + rec["ask"][i]) / 2
            if fill is None:
                ok = False
                break
            adj += (fill - wk.bid(wk.NIFTY, m)) * wk.NIFTY["lot"]
        if ok:
            rep.append({"entry": t["entry"], "model_net": round(t["net"]), "real_entry_adjustment": round(adj), "net_on_real_entry": round(t["net"] + adj)})
    out["TEST entries repriced"] = {"weeks": len(rep), "model_net": sum(x["model_net"] for x in rep),
                                    "net_on_real_entry": sum(x["net_on_real_entry"] for x in rep), "rows": rep}
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn209.json"
    if out_path.exists():
        raise SystemExit("SN209 is scored once")
    picks = pickle.loads((wk.LOCAL / "sn204-picks.pkl").read_bytes())
    har = pickle.loads((wk.LOCAL / "sn205-har.pkl").read_bytes())
    res = {}
    D = wk.dev_data()
    test_weeks = wk.split(wk.expiries(D), "test")
    res["TEST"], test_tr = candidates(wk.NIFTY, D, test_weeks, picks)
    res["TEST"]["weeks_available"] = len(test_weeks)
    print("SN209 TEST:", json.dumps({k: {x: v[x] for x in ("weeks", "net", "win_pct", "worst")} for k, v in res["TEST"].items() if isinstance(v, dict)}), flush=True)
    res["real_quotes"] = real_quotes(test_tr)
    print("SN209 real quotes:", json.dumps({k: v for k, v in res["real_quotes"].items() if k != "TEST entries repriced"}),
          json.dumps({k: v for k, v in res["real_quotes"]["TEST entries repriced"].items() if k != "rows"}), flush=True)
    for und, mk in (("NIFTY", wk.NIFTY), ("SENSEX", wk.SENSEX)):
        E = wk.exam_data(und)
        weeks = wk.expiries(E)
        res[f"exam {und}"], _t = candidates(mk, E, weeks, picks, beta=har["beta"])
        res[f"exam {und}"]["weeks_available"] = len(weeks)
        print(f"SN209 exam {und}:", json.dumps({k: {x: v[x] for x in ("weeks", "net", "win_pct", "worst", "worst_month", "months_positive")}
                                               for k, v in res[f"exam {und}"].items() if isinstance(v, dict)}), flush=True)
    a = "WK-S " + wk.vname(picks["WK-S"])
    res["pass"] = {"4 TEST >= 0": bool(res["TEST"][a]["net"] >= 0), "5a NIFTY exam > 0": bool(res["exam NIFTY"][a]["net"] > 0),
                   "5b SENSEX exam > 0": bool(res["exam SENSEX"][a]["net"] > 0)}
    print("SN209 pass:", json.dumps(res["pass"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
