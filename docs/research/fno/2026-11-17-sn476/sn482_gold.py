"""SN482 (Gold v5 unchanged on NIFTY 2020 + Jan-Aug 2021) and SN490 (the round's frozen candidates on the same dates), scored once
(PLAN.md SN482 / SN490, frozen at bf895633; details fixed here before any Gold number on these dates).

Data: this slot's exam replays (sn482_exam.py: N11 and R0.85 panel books per point = Gold's DEPLOYED feed, read by sn392.stream's
conversion plus bar_ts) and datasets (sn482_build.py). Gold's sessions: sn01_data.build_year on each dataset (expiry days drop out,
as in every Gold year), cached in _local. One path "2020-21" = ("2020", "2021E") from Jan 2020, Gold's volatility table from the path's
own minutes (the convention of every path so far).
SN482: Gold v5 on ONE_15K first, then GOLD_30K (Rs 30k at 2020-01-01), Rs 205 / 400. Primary = the current lot (65), Gold's harness
rule for every year so far; DATED view beside it: the lot of the contract (75 for front-weekly expiries up to 2021-07-29, 50 after;
an assumption stated in the README, NSE's 2021 revision circular was not fetched). Reported: summary, by year and month, trades,
months positive, worst day / month, refills, best-5 days' share, coverage (sessions in the datasets, Gold sessions, sessions with
signals). Lower tail at Rs 400: worst day, worst month, losing-day sum.
SN490: on the 2020-21 path, paired with Gold (sn480.compare), ONE_15K and GOLD_30K, Rs 205 / 400: SN480's challenger (fail_theta 0,
next minute, Rs 23.60), SN478's FAST, SN489's frozen rule (adds off for EFF and OR20). Development paths 2022 / 2023-26 recomputed
for the same candidates (GOLD_30K). Strongest survivor = the largest Rs 400 GOLD_30K paired gain on 2020-21 among candidates whose
GOLD_30K paired difference is > 0 in 2022, 2023-26 and 2020-21 at both stresses; at most one; else none.
"""
from __future__ import annotations

import collections
import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
sys.path.insert(0, str(HERE))
import sn478  # noqa: E402
import sn480 as A  # noqa: E402

goldx, g = A.goldx, A.g
D, G = g.D, g.G
OUT2 = HERE / "results-sn482.json"
OUT0 = HERE / "results-sn490.json"
MINE = ("2020", "2021E")
Y2021 = ("2020", "2021E")
DATASET = {y: LOCAL / f"dataset-nifty-{y}" for y in MINE}
CANDS = {"SN480 failed add": dict(A.CHALLENGER), "SN478 FAST": "fast", "SN489 adds only TPB / SHIPPED": {"no_add": frozenset({"EFF", "OR20"})}}
_real_load = G._orig_load
_real_stream = sn478.dispatch


def load_year(year):
    if year not in MINE:
        return _real_load(year)
    p = LOCAL / f"sn01-cache-{year}.pkl"
    if not p.exists():
        data = D.build_year(year)
        p.write_bytes(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
    return pickle.loads(p.read_bytes())


def stream_mine(year, book):
    keys = json.loads((LOCAL / f"keys-exam-{year}.json").read_text(encoding="utf-8"))
    data = json.loads((LOCAL / f"exam-evals-{year}" / f"{keys['panel|' + book]}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:
        ctx = t["n091_entry"]["native_gate_context"]
        sym = t["tradingsymbol"]
        i = g.B.minute_of(t["entry_time"])
        out.append({"day": t["entry_time"][:10], "i": i, "j": g.B.minute_of(t["exit_time"]), "strike": int(round(ctx["strike"])),
                    "opt": "CE" if ctx["is_call"] else "PE", "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"],
                    "expert": t["entry_expert"], "gate": t.get("entry_gate") or "", "book": book,
                    "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"]), "bar_ts": t["bar_ts"],
                    "bar_end": g.B.minute_of(t["bar_ts"]) + 5, "i_orig": i})
    return out


def dispatch(year, book="N11"):
    if year in MINE:
        xs = stream_mine(year, book)
        if sn478.MODE["fast"]:
            xs = [{**x, "i": x["bar_end"]} if x["bar_end"] < x["i"] else x for x in xs]
        return xs
    return _real_stream(year, book)


LOT = {"dated": False}
_ow_play = None


def dated_play(S, sigs, v, wallet, full_lots, ctx, vol_day):
    old = goldx.M.LOT
    if LOT["dated"]:
        goldx.M.LOT = 75 if S.s["expiry"] <= "2021-07-29" else 50
    try:
        return _ow_play(S, sigs, v, wallet, full_lots, ctx, vol_day)
    finally:
        goldx.M.LOT = old


def run_path(years, st, wallet, cand=None):
    if cand == "fast":
        sn478.MODE["fast"] = True
        try:
            return A.run(years, st, wallet)
        finally:
            sn478.MODE["fast"] = False
    return A.run(years, st, wallet, **(cand or {}))


def report(s, days, log):
    nets = [n for _d, _w, n, _t, _l in days]
    months = collections.defaultdict(float)
    for d, _w, n, _t, _l in days:
        months[d[:7]] += n
    best5 = sorted(nets, reverse=True)[:5]
    return {**s, "months_table": {m: round(v) for m, v in sorted(months.items())}, "losing_day_sum": round(sum(x for x in nets if x < 0)),
            "best5": [round(x) for x in best5], "best5_share_of_net": round(sum(best5) / s["net"], 3) if s["net"] > 0 else None,
            "days_traded": sum(1 for x in nets if x != 0),
            "replay_sessions_by_year": dict(collections.Counter(d[:4] for d, _w, _n, _t, _l in days)),
            "per_replay_session_by_year": {y: round(v / sum(1 for d, *_r in days if d[:4] == y), 1) for y, v in s["by_year"].items()}, "puts": sum(1 for t in log if t.get("opt") == "PE"), "calls": sum(1 for t in log if t.get("opt") == "CE"),
            "puts_net": round(sum(t["net"] for t in log if t.get("opt") == "PE")), "calls_net": round(sum(t["net"] for t in log if t.get("opt") == "CE")),
            "by_expert": {e: round(sum(t["net"] for t in log if t.get("expert") == e)) for e in sorted({t.get("expert") for t in log})}}


def main():
    global _ow_play
    if OUT2.exists() or OUT0.exists():
        raise SystemExit("SN482 / SN490 are scored once")
    goldx.install()
    for y in MINE:
        D.DATASETS[y] = DATASET[y]
    G._orig_load = load_year
    g._orig_stream = dispatch
    sn478._gold_one = g.C.gold_one
    g.C.gold_one = sn478.fast_gold_one
    _ow_play = g.ow.play_day
    g.ow.play_day = dated_play
    cov = {}
    for y in MINE:
        man = json.loads((DATASET[y] / "manifest.json").read_text(encoding="utf-8"))
        cov[y] = {"dataset_sessions": len(man["sessions"]), "gold_sessions": len(load_year(y)["sessions"]),
                  "N11_signals": len(stream_mine(y, "N11")), "R0.85_signals": len(stream_mine(y, "R0.85"))}
    R2 = {"coverage": cov, "cells": {}}
    for lot in ("current_65", "dated"):
        LOT["dated"] = lot == "dated"
        for lname, wallet in (("ONE_15K", goldx.ONE_15K), ("GOLD_30K", goldx.GOLD_30K)):
            for st in A.STRESSES:
                s, days, log = run_path(Y2021, st, wallet)
                R2["cells"][f"{lot} {lname} @{int(st)}"] = report(s, days, log)
    LOT["dated"] = False
    OUT2.write_text(json.dumps(R2, indent=1), encoding="utf-8")
    R0 = {"cells": {}}
    for name, cand in CANDS.items():
        for lname, wallet in (("ONE_15K", goldx.ONE_15K), ("GOLD_30K", goldx.GOLD_30K)):
            paths = (("2020-21", Y2021),) + (A.PATHS if lname == "GOLD_30K" else ())
            for pname, years in paths:
                for st in A.STRESSES:
                    sb, db, lb = run_path(years, st, wallet)
                    sc, dc, lc = run_path(years, st, wallet, cand)
                    c = A.compare(sb, db, lb, sc, dc, lc)
                    c.pop("fail_events", None)
                    R0["cells"][f"{name} | {lname} {pname} @{int(st)}"] = c
    surv = {}
    for name in CANDS:
        ok = all(R0["cells"][f"{name} | GOLD_30K {p} @{int(s)}"]["diff_total"] > 0 for p in ("2020-21", "2022", "2023-2026") for s in A.STRESSES)
        if ok:
            surv[name] = R0["cells"][f"{name} | GOLD_30K 2020-21 @400"]["diff_total"]
    R0["survivors"] = surv
    R0["strongest_survivor"] = max(surv, key=surv.get) if surv else None
    OUT0.write_text(json.dumps(R0, indent=1), encoding="utf-8")
    print(json.dumps(cov, indent=1))
    for k, c in R2["cells"].items():
        print(f"{k:28s} net {c['net']:>9} by_year {c['by_year']} trades {c['trades']} months+ {c['months_positive']}/{c['months']} worst_day {c['worst_day']} "
              f"worst_month {c['worst_month']} refilled {c['refilled']} best5 {c['best5_share_of_net']} puts {c['puts_net']} calls {c['calls_net']}")
    for k, c in R0["cells"].items():
        print(f"{k:58s} gold {c['gold']['net']:>9} cand {c['challenger']['net']:>9} diff {c['diff_total']:>9} ci {c['diff_ci90']}")
    print("survivors", R0["survivors"], "strongest", R0["strongest_survivor"])


if __name__ == "__main__":
    main()
