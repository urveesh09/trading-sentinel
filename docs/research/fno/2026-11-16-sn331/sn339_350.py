"""SN339 (finite refill reserve), SN342 (the wage Gold V8 can pay), SN347 (N11's stood-aside signals at half size on Gold's
empty days), SN348 (more growth steps) and SN350 (the V8 configuration), PLAN.md frozen at 95287d3f before any number.

All on Gold v5's replay (sn301/gw.py; parity asserted at Rs 8,50,882), Jan 2023 - Oct 28 2026, Rs 205 and Rs 400 stress.
Pool accounting (SN339 / SN342): the owner's spare cash R plus banked profits. A losing day is refilled from the pool; a
winning day's profit goes into it. A session starts only if the pool can cover a full day stop (20% of the wallet);
otherwise Gold pauses that session. At each month end everything in the pool above R is withdrawn (the wage).
  SN339: R = Rs 30,000 and Rs 60,000.   SN342: R = one wallet (the wallet at that month end).
SN347: on sessions with no N11 / R0.85 signal, the NO_STAND book's signals are taken at half Gold's lots.
SN348: the growth cap at 4 and 5 steps instead of 3; lots above SN341's ceiling pay SN341's measured excess per lot
(post-hoc on the trade log; none if SN341 finds no size over its bar).
Pass for SN347 / SN348 against Gold v5, at Rs 205 and Rs 400 and in both halves: net higher; refills <= 1.10 x; positive
months not fewer; worst month not worse. SN350: the V8 configuration = Gold v5 plus every pass, replayed together."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import gw  # noqa: E402
import sn310_311 as G  # noqa: E402

ow, C, L = gw.ow, gw.C, gw.L
_PLAY, _SIG, _SIZE = ow.play_day, L.sig_of, C.size_ext
POOL = {"on": False, "R": None, "pool": 0.0, "month": None, "withdrawn": [], "paused": 0, "paused_with_signals": 0, "min_pool": 1e18,
        "R_is_wallet": False}
EXTRA = {"on": False}


def pool_play(S, sigs, v, wallet, full_lots, ctx, vol_day):
    if not POOL["on"]:
        return _PLAY(S, sigs, v, wallet, full_lots, ctx, vol_day)
    m = S.day[:7]
    if POOL["month"] is not None and m != POOL["month"]:
        keep = wallet if POOL["R_is_wallet"] else POOL["R"]
        out = max(0.0, POOL["pool"] - keep)
        POOL["withdrawn"].append((POOL["month"], out))
        POOL["pool"] -= out
    POOL["month"] = m
    if POOL["pool"] < 0.2 * wallet:
        POOL["paused"] += 1
        POOL["paused_with_signals"] += bool(sigs)
        ow.DAYLOG.append((S.day, wallet, 0.0, 0, 0.0))
        return 0.0
    net = _PLAY(S, sigs, v, wallet, full_lots, ctx, vol_day)
    POOL["pool"] += net
    POOL["min_pool"] = min(POOL["min_pool"], POOL["pool"])
    return net


def sig_extra(Y, day, v):
    base = _SIG(Y, day, v)
    if base or not v.get("no_stand_half"):
        return base
    return [{**s, "half": True} for s in Y.sigs("NO_STAND").get(day, [])]


def size_half(S, sg, v, full, ctx, vol_day):
    lots = _SIZE(S, sg, v, full, ctx, vol_day)
    return max(1, lots // 2) if sg.get("half") else lots


def install():
    gw.install()
    ow.play_day = pool_play
    L.sig_of = sig_extra
    C.size_ext = size_half


def run(stress, wallet=ow.GOLD_30K, **vx):
    v = {**C.V5, **vx}
    old_w, old_s = ow.GOLD_30K, L.STRESS
    L.STRESS = stress
    gw.LOG.clear()
    try:
        row, days, _ = ow.run_wallet(v, wallet, None)
    finally:
        L.STRESS = old_s
    return row, days, list(gw.LOG)


def pooled(stress, R=None, R_is_wallet=False, wallet=ow.GOLD_30K, **vx):
    POOL.update(on=True, R=R, pool=float(R if R is not None else wallet[1]), month=None, withdrawn=[], paused=0, paused_with_signals=0,
                min_pool=1e18, R_is_wallet=R_is_wallet)
    try:
        row, days, log = run(stress, wallet, **vx)
    finally:
        POOL["on"] = False
    w = [x for _m, x in POOL["withdrawn"]]
    runs, cur = 0, 0
    for x in w:
        cur = cur + 1 if x <= 0 else 0
        runs = max(runs, cur)
    return {"net": round(sum(n for _d, _w, n, _t, _l in days)), "paused_sessions": POOL["paused"], "paused_with_signals": POOL["paused_with_signals"],
            "withdrawn_total": round(sum(w)), "months": len(w), "months_paid": sum(x > 0 for x in w),
            "avg_month_withdrawal": round(sum(w) / max(1, len(w))), "longest_unpaid_months": runs,
            "per_session_wage": round(sum(w) / max(1, sum(1 for _ in days))), "min_pool": round(POOL["min_pool"]),
            "last_12_months_avg": round(sum(w[-12:]) / max(1, len(w[-12:])))}


def compare(a, b):
    """a's metrics against b's under the frozen rule."""
    out = {}
    for part, x, y in [("whole", a["whole"], b["whole"])] + [(h, a["halves"][h], b["halves"][h]) for h, _l, _u in G.HALVES]:
        out[part] = {"net": x["net_days"] > y["net_days"], "refills": x["refilled"] <= 1.10 * y["refilled"],
                     "positive_months": x["positive_months"] >= y["positive_months"], "worst_month": x["worst_month"] >= y["worst_month"]}
    return out


def metrics(row, days, log):
    return {"whole": G.metrics(row, days, log), "halves": {h: G.metrics(row, days, log, lo, hi) for h, lo, hi in G.HALVES}}


if __name__ == "__main__":
    out_path = HERE / "results-sn339-350.json"
    if out_path.exists():
        raise SystemExit("SN339-SN350 are run once")
    install()
    res = {}
    base = {}
    for st in (205.0, 400.0):
        row, days, log = run(st)
        if st == 205.0:
            assert row["net"] == 850882, row["net"]
        base[st] = metrics(row, days, log)
        res[f"gold_v5 @{int(st)}"] = base[st]["whole"]
    # SN339 / SN342
    for st in (205.0, 400.0):
        for R in (30000.0, 60000.0):
            res[f"SN339 R={int(R)} @{int(st)}"] = pooled(st, R=R)
            print("SN339", int(R), int(st), json.dumps(res[f"SN339 R={int(R)} @{int(st)}"]), flush=True)
        res[f"SN342 R=wallet @{int(st)}"] = pooled(st, R_is_wallet=True)
        print("SN342", int(st), json.dumps(res[f"SN342 R=wallet @{int(st)}"]), flush=True)
    # SN347
    s347 = {}
    for st in (205.0, 400.0):
        row, days, log = run(st, no_stand_half=True)
        s347[st] = metrics(row, days, log)
        res[f"SN347 @{int(st)}"] = {**s347[st]["whole"], "extra_trades": sum(1 for x in log) - base[st]["whole"]["trades"]}
        print("SN347", int(st), json.dumps(res[f"SN347 @{int(st)}"]), flush=True)
    c347 = {f"@{int(st)}": compare(s347[st], base[st]) for st in (205.0, 400.0)}
    res["SN347_conditions"] = c347
    res["SN347_pass"] = all(all(v.values()) for x in c347.values() for v in x.values())
    # SN348 (with SN341's ceiling if it exists)
    s341 = json.loads((HERE / "results-sn341.json").read_text(encoding="utf-8")) if (HERE / "results-sn341.json").exists() else {}
    ceiling = s341.get("lot_ceiling") if s341.get("first_size_over_the_bar") else None
    excess = 0.0
    if ceiling is not None:
        over = s341["first_size_over_the_bar"]
        excess = max(v["excess_mean"] for k, v in s341["grid"].items() if k.endswith(f"x{over}") and v["excess_mean"] is not None)
    res["SN348_ceiling"] = {"lot_ceiling": ceiling, "excess_per_lot_above": excess}
    c348 = {}
    for cap in (4, 5):
        wal = (f"30k grow stop {cap}", 30000.0, "grow", cap)
        per = {}
        for st in (205.0, 400.0):
            row, days, log = run(st, wallet=wal)
            m = metrics(row, days, log)
            if ceiling is not None:
                adj = sum(excess * max(0, sum(p[1] for p in x["pieces"]) - ceiling) for x in log)
                m["ceiling_cost"] = round(adj)
                m["whole"]["net_days"] -= round(adj)
            per[st] = m
            res[f"SN348 stop {cap} @{int(st)}"] = {**m["whole"], "ceiling_cost": m.get("ceiling_cost", 0)}
            print("SN348", cap, int(st), json.dumps(res[f"SN348 stop {cap} @{int(st)}"]), flush=True)
            res[f"SN348 stop {cap} wage @{int(st)}"] = pooled(st, R_is_wallet=True, wallet=wal)
        c348[cap] = {f"@{int(st)}": compare(per[st], base[st]) for st in (205.0, 400.0)}
    res["SN348_conditions"] = {str(k): v for k, v in c348.items()}
    res["SN348_pass"] = {str(cap): all(all(v.values()) for x in c348[cap].values() for v in x.values()) for cap in (4, 5)}
    # SN350
    cfg = {"growth_cap": 3, "no_stand_half": False}
    if res["SN347_pass"]:
        cfg["no_stand_half"] = True
    passing = [cap for cap in (4, 5) if res["SN348_pass"][str(cap)]]
    if passing:
        cfg["growth_cap"] = max(passing)
    wal = (f"30k grow stop {cfg['growth_cap']}", 30000.0, "grow", cfg["growth_cap"])
    res["SN350_config"] = cfg
    for st in (205.0, 400.0):
        row, days, log = run(st, wallet=wal, no_stand_half=cfg["no_stand_half"])
        res[f"SN350 V8 @{int(st)}"] = {**G.metrics(row, days, log), "wage": pooled(st, R_is_wallet=True, wallet=wal, no_stand_half=cfg["no_stand_half"])}
        print("SN350", int(st), json.dumps(res[f"SN350 V8 @{int(st)}"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
