"""SN323 (when Gold's entries fail) and SN324 (one targeted challenger), PLAN.md frozen before any number.

Gold v5 at Rs 30,000 growing (stop 3), Jan 2023 - Oct 28 2026, on sn301's instrumented walk (parity asserted). Each Gold
trade is joined to its N11 / R0.85 record (stored evals) for N11's own setup invalidation level, initial_stop_underlying.
SN323, per trade, on the index closes (the harness's underlying): the first minute the index covers 25% / 50% / 100% of
the distance from the entry minute's close to that level against the trade; the adverse / favourable excursion in the
first 1, 2 and 5 minutes; classes (100% within 1 minute, within 5, later before the exit, never).
SN324: the class = the expert with the largest losing total among experts with >= 15 trades (mechanical). Candidate: that
class waits one minute and is cancelled if that minute's close has covered >= 25% of the distance against it; otherwise it
enters at that minute's ask (Gold's `late` path). Control: the same class always one minute late. Others on time."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import gw  # noqa: E402
import sn310_311 as G  # noqa: E402

ow, C, L, M = gw.ow, gw.C, gw.L, gw.M
N11 = M.ROOT / "docs/research/simulation/2026-11-02-fno-n11/_local"
YEARS = ("2023", "2024", "2025", "2026")
FRACTION = 0.25
REC: dict = {}
TRADES: list = []
MODE = {"name": "g0", "cls": None}


def setup_levels():
    out = {}
    for y in YEARS:
        keys = json.loads((N11 / f"keys-panel-{y}.json").read_text(encoding="utf-8"))
        for book in ("N11", "R0.85"):
            if book not in keys:
                continue
            data = json.loads((N11 / "evals" / f"{keys[book]}.json").read_text(encoding="utf-8"))
            for t in data["trades"]:
                ctx = t["n091_entry"]["native_gate_context"]
                k = (t["entry_time"][:16], int(round(ctx["strike"])), bool(ctx["is_call"]))
                out.setdefault(k, {"stop": t.get("initial_stop_underlying") or t.get("stop_underlying"),
                                   "entry_u": t.get("entry_underlying"), "atr": t.get("atr_at_entry")})
    return out


def install():
    gw.install()
    inner = C.gold_one

    def gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
        i = sg["i"]
        c = S.F["c"]
        d = 1 if sg["opt"] == "CE" else -1
        lv = REC.get(sg.get("sig_key"))
        dist = abs(lv["entry_u"] - lv["stop"]) if lv and lv["stop"] is not None and lv["entry_u"] is not None else None
        in_cls = MODE["cls"] is not None and sg["expert"] == MODE["cls"]
        vv = v
        if in_cls and MODE["name"] in ("control", "candidate"):
            if MODE["name"] == "candidate" and dist and i + 1 < len(c) and d * (c[i] - c[i + 1]) >= FRACTION * dist:
                TRADES.append({"day": S.day, "i": i, "expert": sg["expert"], "cancelled": True})
                return None
            vv = {**v, "late": 1}
        res = inner(S, sg, vv, wallet, full_lots, ctx, vol_day, realized, loss)
        if res is not None:
            net, j, lots, ask, px, strike = res
            row = {"day": S.day, "i": i, "j": j, "opt": sg["opt"], "expert": sg["expert"], "net": net, "lots": lots, "cancelled": False,
                   "dist": dist}
            if MODE["name"] == "g0" and dist:
                hi = min(j, len(c) - 1)
                path = d * (c[i] - c[i:hi + 1])                  # adverse move in index points, from the entry minute
                fav = -path
                for f in (0.25, 0.5, 1.0):
                    hit = np.flatnonzero(path >= f * dist)
                    row[f"t_adv_{int(f * 100)}"] = int(hit[0]) if len(hit) else None
                for k in (1, 2, 5):
                    seg = path[: k + 1]
                    row[f"mae_{k}"] = float(seg.max() / dist)
                    row[f"mfe_{k}"] = float(fav[: k + 1].max() / dist)
            TRADES.append(row)
        return res
    C.gold_one = gold_one


def anatomy(rows):
    rows = [r for r in rows if r.get("dist")]

    def cls(r):
        t = r.get("t_adv_100")
        return "never" if t is None else ("within_1m" if t <= 1 else ("within_5m" if t <= 5 else "later"))

    out = {"joined": len(rows)}
    for name, grp in (("losers", [r for r in rows if r["net"] < 0]), ("winners", [r for r in rows if r["net"] > 0])):
        c = collections.Counter(cls(r) for r in grp)
        out[name] = {"n": len(grp), "net": round(sum(r["net"] for r in grp)), "classes": dict(c),
                     "class_net": {k: round(sum(r["net"] for r in grp if cls(r) == k)) for k in c},
                     **{f"mae_{k}_median": round(float(np.median([r[f'mae_{k}'] for r in grp])), 3) for k in (1, 2, 5)},
                     **{f"share_mae1_ge_{int(f * 100)}": round(float(np.mean([r['mae_1'] >= f for r in grp])), 3) for f in (0.25, 0.5)}}
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["expert"], r["opt"])].append(r)
    out["by_expert_side"] = {f"{e} {o}": {"n": len(g), "net": round(sum(x["net"] for x in g)),
                                          "losers_mae1_ge25": sum(1 for x in g if x["net"] < 0 and x["mae_1"] >= 0.25),
                                          "winners_mae1_ge25": sum(1 for x in g if x["net"] > 0 and x["mae_1"] >= 0.25)}
                             for (e, o), g in sorted(by.items())}
    # the would-be filter seen from SN323 alone: trades with >= 25% adverse at +1 minute
    flag = [r for r in rows if r["mae_1"] >= FRACTION]
    out["mae1_ge25"] = {"n": len(flag), "losers": sum(r["net"] < 0 for r in flag), "winners": sum(r["net"] > 0 for r in flag),
                        "net": round(sum(r["net"] for r in flag)), "biggest_winner_flagged": round(max((r["net"] for r in flag), default=0.0))}
    return out


def run(mode, cls, stress):
    MODE.update(name=mode, cls=cls)
    TRADES.clear()
    row, days, log = G.run(None, stress)
    return row, days, log, list(TRADES)


if __name__ == "__main__":
    out_path = HERE / "results-sn323-324.json"
    if out_path.exists():
        raise SystemExit("SN323-SN324 are run once")
    REC.update(setup_levels())
    install()
    row0, days0, log0, tr0 = run("g0", None, 205.0)
    assert row0["net"] == 850882, row0["net"]
    res = {"parity_net": row0["net"], "SN323": anatomy(tr0)}
    print("SN323", json.dumps(res["SN323"]), flush=True)
    # the class, mechanically: the largest losing total among experts with >= 15 trades
    by = collections.defaultdict(list)
    for r in tr0:
        by[r["expert"]].append(r["net"])
    elig = {e: sum(x for x in v if x < 0) for e, v in by.items() if len(v) >= 15}
    cls = min(elig, key=elig.get)
    res["SN324_class"] = {"expert": cls, "losing_totals": {e: round(v) for e, v in elig.items()}}
    print("SN324 class", cls, flush=True)
    arms = {}
    for stress in (205.0, 400.0):
        for mode in ("g0", "control", "candidate"):
            row, days, log, tr = run(mode, cls, stress) if not (mode == "g0" and stress == 205.0) else (row0, days0, log0, tr0)
            m = {"panel_net": row["net"], "whole": G.metrics(row, days, log),
                 "halves": {h: G.metrics(row, days, log, lo, hi) for h, lo, hi in G.HALVES},
                 "cancelled": sum(1 for t in tr if t.get("cancelled")), "class_trades": sum(1 for t in tr if t.get("expert") == cls and not t.get("cancelled"))}
            arms[(mode, stress)] = (m, tr)
            res[f"{mode} @{int(stress)}"] = m
            print("SN324", mode, int(stress), json.dumps({k: m[k] for k in ("panel_net", "cancelled", "class_trades")}), json.dumps(m["whole"]), flush=True)
    dec = {}
    ok = True
    for stress in (205.0, 400.0):
        mc, trc = arms[("control", stress)]
        mk, trk = arms[("candidate", stress)]
        ctl = {(t["day"], t["i"]): t["net"] for t in trc if not t.get("cancelled") and t.get("expert") == cls}
        canc = [(t["day"], t["i"]) for t in trk if t.get("cancelled")]
        avoided = -sum(ctl[k] for k in canc if k in ctl and ctl[k] < 0)
        missed = sum(ctl[k] for k in canc if k in ctl and ctl[k] > 0)
        conds = {"avoided_gt_missed": avoided > missed}
        for part, x, y in [("whole", mk["whole"], mc["whole"])] + [(h, mk["halves"][h], mc["halves"][h]) for h, _a, _b in G.HALVES]:
            conds[f"{part}: net"] = x["net_days"] > y["net_days"]
            conds[f"{part}: refills"] = x["refilled"] <= y["refilled"]
            conds[f"{part}: positive_months"] = x["positive_months"] >= y["positive_months"]
            conds[f"{part}: worst_month"] = x["worst_month"] >= y["worst_month"]
        dec[f"@{int(stress)}"] = {"avoided_losses": round(avoided), "missed_winners": round(missed), "cancelled": len(canc), "conditions": conds}
        ok = ok and all(conds.values())
    dec["promote_to_paper_shadow"] = ok
    res["decision"] = dec
    print("SN324 decision", json.dumps(dec), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
