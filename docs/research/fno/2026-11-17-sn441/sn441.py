"""SN441: a common two-sided decision ledger for direction (PLAN.md section 1, frozen at f56f5807; details fixed here before
any number). Diagnostics, never strategy P&L.

Panel: SN412's 42 sealed archive days (qa, walked one-lot prices, lot 65, entry <= Rs 15,000), clocks 10:00 / 11:00 / 13:00,
both 1-ITM sides (ATM from the front future's last price at the clock) on the front expiry; an expiring contract to 13:30.
Legal exit (`legal`): a stop at the first usable snapshot whose mark (walked bid, charges, stress) <= -Rs 3,000; else the
walked bid at the first usable snapshot at or after the scheduled exit (clock + 60, or 13:30 for an expiring contract), within
5 minutes; else UNRESOLVED. Exits are found per stress (205 / 400); the gross and fees-only views reuse the 205 exit price.
States: ENTERED, NO_QUOTE (no walked ask at the clock or no contract), UNAFFORDABLE, UNRESOLVED.
Common cells: both sides ENTERED and resolved at both stresses. better / worse / coin = max / min / mean of the two sides;
p* = -mean(worse) / (mean(better) - mean(worse)) (the auditor's illustrative constant-probability equation).
Decomposition: p* gross (no charges, no stress), fees only, fees + 205, fees + 400; the coin mean under SN428's old exit
(`sn428.trade`, the last mark before a missing exit) against the legal rule on the same cells; single-side means on every
resolved row against common cells. 2,000 date-block bootstrap resamples (seed 441) for coin and p*.
Parity: sn428.trade over SN428's own cell definitions reproduces its receipt's 'all @205' BASE and SIDE means.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn426"))
import sn428  # noqa: E402  (its C = sn412: qa on the sealed export, walked(), charges())

C = sn428.C
qa = C.qa
OUT = HERE / "results-sn441.json"
CLOCKS = sn428.CLOCKS
LOT, ROOM, STOP, GRACE = 65, 15000.0, 3000.0, 5


def legal(ask, bid, e, x_sched, stress, fees=True):
    """-> (state, net, exit_minute, exit_bid). Entry at the walked ask of minute e."""
    a = ask[e]
    if np.isnan(a):
        return "NO_QUOTE", None, None, None
    if a * LOT + C.charges(a, 0.0) > ROOM:
        return "UNAFFORDABLE", None, None, None
    n_all = len(bid)

    def net(b):
        return (b - a) * LOT - (C.charges(a, b) if fees else 0.0) - stress
    for x in range(e + 1, min(x_sched, n_all)):
        b = bid[x]
        if np.isnan(b):
            continue
        if net(b) <= -STOP:
            return "ENTERED", net(b), x, float(b)
    for x in range(x_sched, min(x_sched + GRACE + 1, n_all)):
        b = bid[x]
        if not np.isnan(b):
            return "ENTERED", net(b), x, float(b)
    return "UNRESOLVED", None, None, None


def label_of(d, front, gold_days):
    return "EXPIRY" if front == d else "GOLD" if d in gold_days else ("EMPTY" if d <= "2026-10-28" else "NO_REPLAY")


def build():
    man = qa.manifest()
    days = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    gold_days = {x["day"] for x in json.loads(C.RUNS.read_text(encoding="utf-8"))["2023-2026 DEPLOYED @205"]["log"]}
    rows, parity = [], {"BASE": [], "SIDE": []}
    for d in days:
        q = qa.load(d)
        cons = sn428.contracts(q, d)
        exps = sorted({k[1] for k in cons})
        if not exps:
            continue
        front = exps[0]
        expiring = front == d
        lab = label_of(d, front, gold_days)
        fut = qa.front_fut(q, "NIFTY")
        walked = {k: (C.walked(v, "ask"), C.walked(v, "bid")) for k, v in cons.items()}
        for c, e in CLOCKS.items():
            if expiring and e >= 255:
                continue
            F = fut["ltp"][e] if fut is not None else np.nan
            atm = None if np.isnan(F) else int(round(F / 50.0) * 50)
            x_sched = min(e + 60, 255 if expiring else 355)
            coin = random.Random(f"sn428-{d}-{c}").choice(("CE", "PE"))
            # SN428 parity on its own definitions (old exit rule)
            old = {}
            for s in ("CE", "PE"):
                lg = None if atm is None else walked.get(("NIFTY", front, atm + (-50 if s == "CE" else 50), s))
                old[s] = None if lg is None else sn428.trade(lg[0], lg[1], e, x_sched, 205.0, False)
            parity["BASE"].append(old[coin])
            sv = [v for v in old.values() if v is not None]
            parity["SIDE"].append(max(sv) if sv else None)
            row = {"day": d, "clock": c, "label": lab, "coin": coin, "expiring": expiring}
            for s in ("CE", "PE"):
                k = None if atm is None else ("NIFTY", front, atm + (-50 if s == "CE" else 50), s)
                lg = walked.get(k) if k else None
                if lg is None:
                    row[s] = {"state": "NO_QUOTE"}
                    continue
                ask, bid = lg
                r = {}
                for st in (205.0, 400.0):
                    state, n, x, b = legal(ask, bid, e, x_sched, st)
                    r[f"state@{int(st)}"] = state
                    r[f"net@{int(st)}"] = None if n is None else round(n, 2)
                    r[f"x@{int(st)}"] = x
                    if st == 205.0 and b is not None:
                        a = float(ask[e])
                        r["gross"] = round((b - a) * LOT, 2)
                        r["fees_only"] = round((b - a) * LOT - C.charges(a, b), 2)
                    o = sn428.trade(ask, bid, e, x_sched, st, False)
                    r[f"old@{int(st)}"] = None if o is None else round(o, 2)
                r["state"] = r["state@205"] if r["state@205"] != "ENTERED" else r["state@400"]
                row[s] = r
            rows.append(row)
    return rows, parity


def p_star(better, worse):
    mb, mw = float(np.mean(better)), float(np.mean(worse))
    if mw >= 0:
        return 0.0
    if mb <= 0:
        return None
    return -mw / (mb - mw)


def common(rows):
    out = []
    for r in rows:
        if all(isinstance(r[s], dict) and r[s].get("state@205") == "ENTERED" and r[s].get("state@400") == "ENTERED" for s in ("CE", "PE")):
            out.append(r)
    return out


def view(cells, key):
    b = [max(r["CE"][key], r["PE"][key]) for r in cells]
    w = [min(r["CE"][key], r["PE"][key]) for r in cells]
    coin = [(x + y) / 2 for x, y in zip(b, w)]
    ps = p_star(b, w) if cells else None
    return {"cells": len(cells), "dates": len({r["day"] for r in cells}), "mean_better": round(float(np.mean(b))) if b else None,
            "mean_worse": round(float(np.mean(w))) if w else None, "coin": round(float(np.mean(coin))) if coin else None,
            "p_star": None if ps is None else round(ps, 3),
            "ce_better_share": round(float(np.mean([r["CE"][key] >= r["PE"][key] for r in cells])), 3) if cells else None}


def boot(cells, key, seed=441, n=2000):
    rng = random.Random(seed)
    by = {}
    for r in cells:
        by.setdefault(r["day"], []).append(r)
    ds = sorted(by)
    coins, ps = [], []
    for _ in range(n):
        smp = [r for _k in range(len(ds)) for r in by[ds[rng.randrange(len(ds))]]]
        b = [max(r["CE"][key], r["PE"][key]) for r in smp]
        w = [min(r["CE"][key], r["PE"][key]) for r in smp]
        coins.append(float(np.mean([(x + y) / 2 for x, y in zip(b, w)])))
        p = p_star(b, w)
        ps.append(1.0 if p is None else p)
    q = lambda xs, a: round(float(np.percentile(xs, a)), 3)  # noqa: E731
    return {"coin_90ci": [round(q(coins, 5)), round(q(coins, 95))], "p_star_90ci": [q(ps, 5), q(ps, 95)]}


def main():
    if OUT.exists():
        raise SystemExit("SN441 is run once")
    rows, parity = build()
    rec = json.loads((FNO / "2026-11-17-sn426" / "results-sn428.json").read_text(encoding="utf-8"))
    pb = [x for x in parity["BASE"] if x is not None]
    ps_ = [x for x in parity["SIDE"] if x is not None]
    res = {"parity": {"BASE_mean": round(float(np.mean(pb))), "BASE_receipt": rec["all @205"]["BASE"]["mean"],
                      "SIDE_mean": round(float(np.mean(ps_))), "SIDE_receipt": rec["all @205"]["SIDE"]["mean"],
                      "BASE_priced": len(pb), "SIDE_priced": len(ps_)}}
    res["parity"]["ok"] = res["parity"]["BASE_mean"] == res["parity"]["BASE_receipt"] and res["parity"]["SIDE_mean"] == res["parity"]["SIDE_receipt"]
    sides = [(r, s) for r in rows for s in ("CE", "PE")]
    res["row_states"] = {}
    for lab in ("ALL", "EMPTY", "GOLD", "EXPIRY", "NO_REPLAY"):
        sel = [(r, s) for r, s in sides if lab == "ALL" or r["label"] == lab]
        cnt = {}
        for r, s in sel:
            st = r[s]["state"]
            cnt[st] = cnt.get(st, 0) + 1
        res["row_states"][lab] = cnt
    cm = common(rows)
    for lab in ("ALL", "EMPTY", "GOLD", "EXPIRY"):
        cells = [r for r in cm if lab == "ALL" or r["label"] == lab]
        blk = {k: view(cells, k) for k in ("gross", "fees_only", "net@205", "net@400")}
        if cells:
            blk["boot@205"] = boot(cells, "net@205")
            blk["boot@400"] = boot(cells, "net@400")
            for st in (205, 400):
                okc = [r for r in cells if r["CE"].get(f"old@{st}") is not None and r["PE"].get(f"old@{st}") is not None]
                blk[f"alignment@{st}"] = {"cells": len(okc),
                                          "coin_old_exit": round(float(np.mean([(r["CE"][f"old@{st}"] + r["PE"][f"old@{st}"]) / 2 for r in okc]))) if okc else None,
                                          "coin_legal_exit": round(float(np.mean([(r["CE"][f"net@{st}"] + r["PE"][f"net@{st}"]) / 2 for r in okc]))) if okc else None,
                                          "rows_exit_moved": sum(1 for r in okc for s in ("CE", "PE") if r[s][f"old@{st}"] != r[s][f"net@{st}"])}
        for st in (205, 400):
            one = [r[s][f"net@{st}"] for r in rows for s in ("CE", "PE") if (lab == "ALL" or r["label"] == lab)
                   and isinstance(r[s], dict) and r[s].get(f"state@{st}") == "ENTERED"]
            blk[f"single_side_mean_all_resolved@{st}"] = {"rows": len(one), "mean": round(float(np.mean(one))) if one else None}
        for c in CLOCKS:
            cc = [r for r in cells if r["clock"] == c]
            blk[f"clock {c} @205"] = view(cc, "net@205")
        res[f"common {lab}"] = blk
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
