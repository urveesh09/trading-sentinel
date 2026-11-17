"""SN480: sell a failed add, keep the original lots (PLAN.md SN480, frozen at bf895633; details fixed here before any number).

Challenger = goldx fail_theta 0.0 (the future's close through the original entry level against the trade, after the add),
fail_exec "next" (minute j+1's bid: close bid if traded, else the mark), fail_fee Rs 23.60 a sale. Gold v5 otherwise unchanged.
Ledgers GOLD_30K, SELF_30K, ONE_15K; paths 2022, 2023-26; Rs 205 / 400.
Per cell: both summaries; paired daily difference (challenger - Gold) over the ledger's sessions with a 90% circular block
bootstrap CI of the total (block 20 sessions, 10,000 draws, seed 476); worst day; sum of losing days; worst month; refills;
Gold's top-5 days and the challenger's net on them; failed-add sales: count, their sale net, and the same add pieces' net in Gold
(the trade matched by day and entry minute); the difference without the single session that moved most in the total's direction;
asserts: sold lots <= held lots (in goldx), no piece bought after a failed sale.
Verdict (PLAN): RETURN pass = paired net > 0 at both stresses in both paths on GOLD_30K and > 0 without the most affected session;
RISK pass = worst day and losing-day sum smaller at both stresses in both paths while keeping >= 90% of Gold's 2023-26 net at both
stresses (GOLD_30K). ONE_15K and SELF_30K get the same two verdicts, reported beside it.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldx  # noqa: E402

g = goldx.gold
OUT = HERE / "results-sn480.json"
STRESSES = (205.0, 400.0)
PATHS = (("2022", g.Y22), ("2023-2026", g.Y2326))
LEDGERS = (("GOLD_30K", goldx.GOLD_30K), ("SELF_30K", goldx.SELF_30K), ("ONE_15K", goldx.ONE_15K))
CHALLENGER = {"fail_theta": 0.0, "fail_exec": "next", "fail_fee": 23.6}


def run(years, stress, wallet, **vx):
    days, log, _ = g.run(years, g.DEPLOYED, stress, wallet=wallet, **vx)
    return g.summary(days, log), days, log


def block_ci(x, block=20, draws=10000, seed=476, q=(0.05, 0.95)):
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n] % n
    tot = x[idx].sum(axis=1)
    return [round(float(np.quantile(tot, q[0]))), round(float(np.quantile(tot, q[1])))]


def compare(sb, db, lb, sc, dc, lc):
    nb = {d: n for d, _w, n, _t, _l in db}
    nc = {d: n for d, _w, n, _t, _l in dc}
    assert set(nb) == set(nc)
    order = sorted(nb)
    diff = [nc[d] - nb[d] for d in order]
    tot = sum(diff)
    sign = 1 if tot >= 0 else -1
    most = max(order, key=lambda d: sign * (nc[d] - nb[d])) if order else None
    top5 = sorted(order, key=lambda d: -nb[d])[:5]
    bykey = {(t["day"], t["i"]): t for t in lb}
    fails = [t for t in lc if t.get("fail")]
    add_gold, add_chal, matched = 0.0, 0.0, 0
    for t in fails:
        b = bykey.get((t["day"], t["i"]))
        if b is not None and len(b["pieces"]) > 1:
            matched += 1
            add_gold += sum(p[2] for p in b["pieces"][1:])
            add_chal += t["fail"]["net"]
    lose_b = sum(n for n in nb.values() if n < 0)
    lose_c = sum(n for n in nc.values() if n < 0)
    by_y = collections.defaultdict(float)
    for d, x in zip(order, diff):
        by_y[d[:4]] += x
    return {"gold": sb, "challenger": sc, "diff_total": round(tot), "diff_by_year": {y: round(v) for y, v in sorted(by_y.items())},
            "diff_ci90": block_ci(diff), "sessions": len(order), "sessions_changed": sum(abs(x) > 0.005 for x in diff),
            "most_affected_session": [most, round(nc[most] - nb[most])] if most else None,
            "diff_without_most_affected": round(tot - (nc[most] - nb[most])) if most else 0,
            "worst_day": [sb["worst_day"], sc["worst_day"]], "losing_day_sum": [round(lose_b), round(lose_c)],
            "worst_month": [sb["worst_month"], sc["worst_month"]], "refilled": [sb["refilled"], sc["refilled"]],
            "gold_top5": [[d, round(nb[d]), round(nc[d])] for d in top5],
            "failed_add_sales": len(fails), "failed_add_matched": matched, "failed_add_sale_net": round(add_chal), "same_add_pieces_net_in_gold": round(add_gold),
            "adds_gold": sum(1 for t in lb if len(t["pieces"]) > 1), "adds_challenger": sum(1 for t in lc if len(t["pieces"]) > 1 or t.get("fail")),
            "fail_events": [[t["day"], t["i"], t["fail"]["j_sig"], t["fail"]["j_exec"], t["fail"]["lots"], round(t["fail"]["net"]), round(t["net"]),
                             round(bykey[(t["day"], t["i"])]["net"]) if (t["day"], t["i"]) in bykey else None] for t in fails]}


def verdicts(cells, ledger):
    ret = all(cells[f"{ledger} {p} @{int(s)}"]["diff_total"] > 0 and cells[f"{ledger} {p} @{int(s)}"]["diff_without_most_affected"] > 0
              for p, _y in PATHS for s in STRESSES)
    risk = all(cells[f"{ledger} {p} @{int(s)}"]["worst_day"][1] > cells[f"{ledger} {p} @{int(s)}"]["worst_day"][0]
               and cells[f"{ledger} {p} @{int(s)}"]["losing_day_sum"][1] > cells[f"{ledger} {p} @{int(s)}"]["losing_day_sum"][0]
               for p, _y in PATHS for s in STRESSES)
    keep = all(cells[f"{ledger} 2023-2026 @{int(s)}"]["challenger"]["net"] >= 0.9 * cells[f"{ledger} 2023-2026 @{int(s)}"]["gold"]["net"]
               for s in STRESSES)
    return {"RETURN": "PASS" if ret else "FAIL", "RISK": "PASS" if (risk and keep) else "FAIL",
            "risk_parts": {"tail_smaller_everywhere": risk, "keeps_90pct_2023_26": keep}}


def main():
    if OUT.exists():
        raise SystemExit("SN480 is scored once")
    goldx.install()
    cells = {}
    for lname, wallet in LEDGERS:
        for pname, years in PATHS:
            for st in STRESSES:
                sb, db, lb = run(years, st, wallet)
                sc, dc, lc = run(years, st, wallet, **CHALLENGER)
                cells[f"{lname} {pname} @{int(st)}"] = compare(sb, db, lb, sc, dc, lc)
    parity = cells["GOLD_30K 2023-2026 @205"]["gold"]["net"]
    assert parity in (850882, 850883), parity
    res = {"challenger": CHALLENGER, "cells": cells, "verdict": {l: verdicts(cells, l) for l, _w in LEDGERS}}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, c in cells.items():
        print(f"{k:28s} gold {c['gold']['net']:>9} chal {c['challenger']['net']:>9} diff {c['diff_total']:>8} ci {c['diff_ci90']} w/o-most {c['diff_without_most_affected']:>8} "
              f"worst {c['worst_day']} lose {c['losing_day_sum']} fails {c['failed_add_sales']} sale {c['failed_add_sale_net']} vs gold-add {c['same_add_pieces_net_in_gold']}")
    print(json.dumps(res["verdict"], indent=1))


if __name__ == "__main__":
    main()
