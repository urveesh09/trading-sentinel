"""SN312: Gold's contracts at real prices (PLAN.md, frozen at 94c772cd).

1. Gold v5's replay (gw, cash "mtm" = Gold v5) records each trade's in-the-money depth (strike vs N11's strike) and lots.
2. On the sealed minute archive (SN101's 41 days, Sep 10 - Nov 12 2026; NIFTY option expiry days skipped, as Gold does):
   NIFTY front-weekly CE / PE at ATM and 1-3 strikes in the money, every 15 minutes 09:30-15:00: the real cost of
   buying and selling n = 1, 2, 3, 4, 6 lots at once (walking five levels; "no depth" counted) against Gold's model
   (sn01_sim ask_of / bid_of on the mid: half the P75 spread each side) - both with Zerodha charges.
3. Gold's own replayed trades inside the archive window: real ask walk at the entry minute and real bid walk at the
   exit minute vs the replay's prices, per lot.
4. The frozen rule: weighted by Gold's (depth, lots) mix, if real - model > Rs 100 a lot, replay Gold v5 with that excess
   added per lot (by depth) against N11's strike (no in-the-money step) under the same corrected costs; else confirmed."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
import gw  # noqa: E402
import qa  # noqa: E402
import sn290  # noqa: E402

ow, C, L, M = gw.ow, gw.C, gw.L, gw.M
NS = (1, 2, 3, 4, 6)
CLOCKS = list(range(15, 346, 15))
TRADES: list = []


def capture_install():
    gw.install()
    inner = C.gold_one

    def gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
        res = inner(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
        if res is not None:
            net, j, lots, ask, px, strike = res
            sign = 1 if sg["opt"] == "CE" else -1
            TRADES.append({"day": S.day, "i": sg["i"], "j": j, "opt": sg["opt"], "n11_strike": sg["strike"], "strike": strike,
                           "depth": int(round((sg["strike"] - strike) * sign / M.STEP)), "lots": lots, "ask": ask, "px": px, "net": net,
                           "expert": sg["expert"]})
        return res
    C.gold_one = gold_one


def nearest_n(lots):
    return next((n for n in NS if n >= lots), NS[-1])


def grid():
    rows = []
    days = sorted(x.stem.replace("quotes-", "") for x in qa.LOCAL.glob("quotes-*.pkl"))
    for day in days:
        try:
            q = qa.load(day)
        except Exception:
            continue
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY"})
        if day in exps:
            continue
        e = sn290.front(q, day)
        fk = sorted(k for k in q["fut"] if k[0] == "NIFTY")
        if e is None or not fk:
            continue
        fut = q["fut"][fk[0]]
        lot = q["lot"]["NIFTY"]
        for i in CLOCKS:
            fm = sn290.mid(fut, i)
            if fm is None:
                continue
            K = int(round(fm / 50.0) * 50)
            for opt in ("CE", "PE"):
                sign = 1 if opt == "CE" else -1
                for dep in range(4):
                    rec = q["opt"].get(("NIFTY", e, K - sign * 50 * dep, opt))
                    if rec is None:
                        continue
                    m = sn290.mid(rec, i)
                    if m is None:
                        continue
                    for n in NS:
                        qty = n * lot
                        rb = sn290.walk(rec["askp"][:, i], rec["askq"][:, i], qty) if rec["usable"][i] else None
                        rs = sn290.walk(rec["bidp"][:, i], rec["bidq"][:, i], qty) if rec["usable"][i] else None
                        ma, mb = M.ask_of(m), M.bid_of(m)
                        model = (ma - mb) * qty + M.charges(ma, mb, qty)
                        if rb is None or rs is None:
                            rows.append({"day": day, "i": i, "opt": opt, "dep": dep, "n": n, "nodepth": True, "prem": m})
                            continue
                        real = (rb - rs) * qty + M.charges(rb, rs, qty)
                        rows.append({"day": day, "i": i, "opt": opt, "dep": dep, "n": n, "nodepth": False, "prem": m,
                                     "real_per_lot": real / n, "model_per_lot": model / n, "excess_per_lot": (real - model) / n})
    return rows


def summarise(rows):
    out = {}
    for opt in ("CE", "PE"):
        for dep in range(4):
            for n in NS:
                rs = [r for r in rows if r["opt"] == opt and r["dep"] == dep and r["n"] == n]
                ok = [r for r in rs if not r["nodepth"]]
                if not rs:
                    continue
                x = np.array([r["excess_per_lot"] for r in ok]) if ok else np.array([np.nan])
                out[f"{opt} itm{dep} x{n}"] = {"cases": len(rs), "no_depth_share": round(1 - len(ok) / len(rs), 3),
                                               "premium_mean": round(float(np.mean([r["prem"] for r in rs])), 1),
                                               "real_per_lot": round(float(np.mean([r["real_per_lot"] for r in ok])), 1) if ok else None,
                                               "model_per_lot": round(float(np.mean([r["model_per_lot"] for r in ok])), 1) if ok else None,
                                               "excess_mean": round(float(np.nanmean(x)), 1), "excess_p90": round(float(np.nanpercentile(x, 90)), 1)}
    return out


def gold_in_archive(trades):
    have = {x.stem.replace("quotes-", "") for x in qa.LOCAL.glob("quotes-*.pkl")}
    out = []
    for t in trades:
        if t["day"] not in have:
            continue
        q = qa.load(t["day"])
        e = sn290.front(q, t["day"])
        rec = q["opt"].get(("NIFTY", e, int(t["strike"]), t["opt"]))
        lot = q["lot"]["NIFTY"]
        if rec is None:
            out.append({"day": t["day"], "missing": True})
            continue
        qty = t["lots"] * lot
        rb = sn290.walk(rec["askp"][:, t["i"]], rec["askq"][:, t["i"]], qty) if t["i"] < qa.NM and rec["usable"][t["i"]] else None
        rs = sn290.walk(rec["bidp"][:, t["j"]], rec["bidq"][:, t["j"]], qty) if t["j"] < qa.NM and rec["usable"][t["j"]] else None
        out.append({"day": t["day"], "depth": t["depth"], "lots": t["lots"], "opt": t["opt"], "replay_ask": t["ask"], "real_ask": rb,
                    "replay_exit": round(t["px"], 2), "real_exit_bid": rs,
                    "entry_gap_per_lot": None if rb is None else round((rb - t["ask"]) * lot, 1),
                    "exit_gap_per_lot": None if rs is None else round((t["px"] - rs) * lot, 1)})
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn312.json"
    if out_path.exists():
        raise SystemExit("SN312 is run once")
    capture_install()
    row, _days, _log = ow.run_wallet(C.V5, ow.GOLD_30K, None)
    assert row["net"] == 850882, row["net"]
    mix = collections.Counter((t["opt"], t["depth"], nearest_n(t["lots"])) for t in TRADES)
    print("SN312 Gold trades", len(TRADES), "mix", dict(collections.Counter((t["depth"], t["lots"]) for t in TRADES)), flush=True)
    rows = grid()
    summ = summarise(rows)
    for k, v in summ.items():
        print("SN312", k, json.dumps(v), flush=True)
    w = [(summ.get(f"{o} itm{d} x{n}", {}).get("excess_mean"), c) for (o, d, n), c in mix.items()]
    w = [(x, c) for x, c in w if x is not None and not np.isnan(x)]
    weighted = sum(x * c for x, c in w) / sum(c for _x, c in w)
    inside = gold_in_archive(TRADES)
    res = {"gold_trades": len(TRADES), "mix_depth_lots": {f"{k[0]} itm{k[1]} x{k[2]}": c for k, c in mix.items()},
           "grid": summ, "grid_cases": len(rows), "weighted_excess_per_lot": round(weighted, 1), "gold_trades_in_archive": inside}
    print("SN312 weighted excess per lot", round(weighted, 1), "| Gold trades inside the archive", json.dumps(inside), flush=True)
    res["rule"] = "replay" if weighted > 100 else "model confirmed (weighted excess <= Rs 100 a lot): nothing replayed"
    if weighted > 100:
        res["note"] = "the frozen rule calls for the corrected-cost replay (sn312b.py, written only in this case)"
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
