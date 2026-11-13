"""SN110 - the same account (PLAN.md): Gold v5 + a straddle companion opened at 10:00 only when admitted, no Gold
position is open, its premium leaves >= Rs 15,000 of the wallet free, and with 10% of the wallet as its own stop
(inside the shared 20% day room). A Gold signal while it is open sells both legs that minute (at the bid marks), then
Gold enters. Every wallet; paired daily difference; maximum drawdown; worst-5% mean; the Gold v6 bar."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402

C, M = pa.C, pa.M
L = C.L
DAYLOG: list = []
COMP: list = []


def play_day_straddle(S, sigs, v, wallet, full_lots, ctx, vol_day):
    cfg = v.get("straddle")
    if cfg is None:
        net = C.combo_play_day(S, sigs, v, wallet, full_lots, ctx, vol_day)
        DAYLOG.append((S.day, net))
        return net
    loss = v.get("loss_share", 0.2) * wallet
    realized, free, ntr, gk = 0.0, 0, 0, 0
    gold = sorted(sigs, key=lambda x: x["i"])
    E = pa.I10 + cfg.get("late", 0)
    pending = bool(cfg["admit"](S.day))
    while True:
        while gk < len(gold) and (gold[gk]["i"] < free or gold[gk]["i"] >= M.EXIT_MIN or gold[gk]["expiry"] != S.s["expiry"]):
            gk += 1
        g_i = gold[gk]["i"] if gk < len(gold) else None
        if pending and free > E:
            pending = False
        if pending and (g_i is None or g_i > E):
            pending = False
            got = pa.path(S, E, leg_stress=cfg["stress"])
            if got is not None and got[1] <= wallet - cfg["reserve"]:
                room = min(cfg["room_share"] * wallet, loss + realized)
                net, j, why = pa.settle(got[2], E, room, stop_at=g_i, fallback=-2 * cfg["stress"])
                realized += net
                COMP.append({"day": S.day, "net": net, "why": why, "wallet": wallet})
                free = j if why == "forced" else j + 1
                if loss + realized < loss * 0.05:
                    break
            continue
        if g_i is None:
            break
        sg = gold[gk]
        gk += 1
        if ntr >= v.get("max_trades", 99):
            break
        res = C.gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
        if res is None:
            continue
        net, j, lots, ask, px, strike = res
        ntr += 1
        realized += net
        ctx.closed.append((S.day, j, sg["expert"], net / lots))
        free = j + 1
        if loss + realized < loss * 0.05:
            break
    DAYLOG.append((S.day, realized))
    return realized


def run_wallet(v, w):
    L.play_day = play_day_straddle
    L.size = C.size_ext
    old = L.WALLETS
    L.WALLETS = (w,)
    DAYLOG.clear()
    try:
        r = L.run(C.years(), None, v)
    finally:
        L.WALLETS = old
    return C.panel(r)[w[0]], list(DAYLOG)


def risk(days):
    x = np.array([n for _d, n in days])
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    k = max(1, int(round(0.05 * len(x))))
    return {"max_drawdown": round(dd), "worst_5pct_mean": round(float(np.sort(x)[:k].mean()))}


def arm(admit, stress=205.0, late=0):
    return {**C.V5, "straddle": {"admit": admit, "stress": stress, "late": late, "reserve": 15000.0, "room_share": 0.10}}


if __name__ == "__main__":
    out_path = HERE / "results-sn110.json"
    if out_path.exists():
        raise SystemExit("SN110 is scored once")
    adm = pa.admission()
    sn95l = lambda d: pa.sn95l(adm, d)  # noqa: E731
    arms = {"SN95-L strict": arm(sn95l), "SN95-L 400/leg": arm(sn95l, 400.0), "SN95-L 1 min late": arm(sn95l, late=1)}
    p102 = HERE / "results-sn102.json"
    if p102.exists():
        r102 = json.loads(p102.read_text(encoding="utf-8"))
        if r102["verdict"]["all days"]["PASS"]:
            days102 = set(r102["models"]["loyo | FULL"]["admitted_days"]["all days"])
            adm102 = lambda d: d in days102  # noqa: E731
            arms.update({"SN102 strict": arm(adm102), "SN102 400/leg": arm(adm102, 400.0), "SN102 1 min late": arm(adm102, late=1)})
    never = arm(lambda d: False)
    res = {"wallets": {}}
    for w in C.BIG_WALLETS:
        base, bdays = run_wallet(C.V5, w)
        chk, _ = run_wallet(never, w)
        assert chk["net"] == base["net"], ("parity", w[0], chk["net"], base["net"])
        row = {"v5": {**base, **risk(bdays)}}
        bmap = dict(bdays)
        for name, v in arms.items():
            COMP.clear()
            p, days = run_wallet(v, w)
            diff = [(d, n - bmap[d]) for d, n in days]
            new_day = sum(x for d, x in diff if bmap[d] == 0)
            overlap = sum(x for d, x in diff if bmap[d] != 0)
            row[name] = {**p, **risk(days), "increment": p["net"] - base["net"], "increment_pct": round(100 * (p["net"] - base["net"]) / base["net"], 1),
                         "paired_new_days": round(new_day), "paired_overlap_days": round(overlap),
                         "companion_trades": len(COMP), "companion_net": round(sum(c["net"] for c in COMP)),
                         "forced_by_gold": sum(c["why"] == "forced" for c in COMP)}
        res["wallets"][w[0]] = row
        print(f"--- {w[0]}: v5 net {base['net']} dd {row['v5']['max_drawdown']} worst5% {row['v5']['worst_5pct_mean']}")
        for name in arms:
            x = row[name]
            print(f"   {name:18s} net {x['net']:>9} (+{x['increment']}, {x['increment_pct']}%) dd {x['max_drawdown']} worst5% {x['worst_5pct_mean']} "
                  f"by year {x['by_year']} companion {x['companion_trades']} trades {x['companion_net']} forced {x['forced_by_gold']} "
                  f"new-day {x['paired_new_days']} overlap {x['paired_overlap_days']}", flush=True)
    verdict = {}
    for name in [a for a in arms if "400" not in a and "late" not in a]:
        stem = name.split(" strict")[0]
        ok = True
        for w in ("30k fixed", "30k grow stop 3"):
            x, b = res["wallets"][w][name], res["wallets"][w]["v5"]
            ok &= x["increment_pct"] >= 15 and x["max_drawdown"] <= b["max_drawdown"] and x["worst_5pct_mean"] >= b["worst_5pct_mean"]
            for rob in (f"{stem} 400/leg", f"{stem} 1 min late"):
                if rob in res["wallets"][w]:
                    ok &= res["wallets"][w][rob]["increment"] > 0
        verdict[name] = {"GOLD_V6_BAR": bool(ok),
                         "increment_pct_30k_fixed": res["wallets"]["30k fixed"][name]["increment_pct"],
                         "increment_pct_30k_grow3": res["wallets"]["30k grow stop 3"][name]["increment_pct"]}
    res["verdict"] = verdict
    print("VERDICT", verdict, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
