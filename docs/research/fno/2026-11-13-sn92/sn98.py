"""SN98 - expiry mornings priced (SN10's 56 expiry days of 10-second opening-ATM options; PLAN.md).
Entries: the straddle at 09:20 or 09:30, or one leg at 09:30 in the direction of 09:15-09:30; filter: cheap (price
ratio PR <= the choose-half median) or always; exits: 13:00 or +40% of the combined premium. Day limit Rs 3,000, one
lot per leg, Rs 15k. Choose on Sep 2025 - Mar 2026, score on Apr - Sep 2026 (the score half was seen once by SN10:
development evidence only). NULL: random admission at 50% / random side."""
from __future__ import annotations

import itertools
import json
import math
import pickle
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

M = C.M
SPLIT = "2026-04-01"
END = 225 * 6 - 1           # 13:00
ROOM, WALLET = 3000.0, 15000.0


def load():
    d = pickle.load(open(C.FNO / "2026-11-12-sn10" / "_local" / "expiry10.pkl", "rb"))
    C.years()
    return d


def pr(day, rec, k):
    a = C.L.VOLT.get(day, (None, None))[0]
    ce, pe = rec["legs"]["CE"][3][k], rec["legs"]["PE"][3][k]
    idx = rec["s"]["index"][3][k // 6]
    if not a or np.isnan(ce) or np.isnan(pe):
        return None
    return float(ce + pe) / (float(idx) * a * math.sqrt(225 / 375))


def play(rec, kind, k, exit_, leg_stress, side=0):
    legsel = ("CE", "PE") if kind == "straddle" else (("CE",) if side > 0 else ("PE",))
    asks = {}
    for o in legsel:
        x = rec["legs"][o][3][k]
        if np.isnan(x):
            return None
        asks[o] = M.ask_of(float(x))
    if sum(asks.values()) * M.LOT > WALLET:
        return None
    cost_in = sum(asks.values())
    last = None
    for j in range(k + 1, END + 1):
        bids = {}
        for o in legsel:
            x = rec["legs"][o][3][j]
            if np.isnan(x):
                break
            bids[o] = M.bid_of(float(x))
        if len(bids) < len(legsel):
            continue
        net = sum((bids[o] - asks[o]) * M.LOT - M.charges(asks[o], bids[o], M.LOT) for o in legsel) - leg_stress * len(legsel)
        last = net
        if net <= -ROOM or (exit_ == "+40%" and sum(bids.values()) >= 1.4 * cost_in):
            return net
    return last if last is not None else -leg_stress * len(legsel)


if __name__ == "__main__":
    out_path = HERE / "results-sn98.json"
    if out_path.exists():
        raise SystemExit("SN98 is scored once")
    days = load()
    choose = [d for d in sorted(days) if d < SPLIT]
    score = [d for d in sorted(days) if d >= SPLIT]
    ENTRIES = {"straddle 09:20": ("straddle", 29), "straddle 09:30": ("straddle", 89), "leg 09:30": ("leg", 89)}
    med = {en: float(np.median([x for x in (pr(d, days[d], k) for d in choose) if x is not None])) for en, (_kd, k) in ENTRIES.items()}
    res = {"days": {"choose": len(choose), "score": len(score)}, "pr_median_choose": med, "stress": {}}
    for sname, ls in (("house 100/leg", 100.0), ("strict 205/leg", 205.0)):
        table = {}
        for (en, (kind, k)), filt, ex, null in itertools.product(ENTRIES.items(), ("cheap", "always"), ("13:00", "+40%"), (False, True)):
            rng = random.Random(f"98|{en}|{filt}|{ex}")
            per = {}
            for half, ds in (("choose", choose), ("score", score)):
                nets = []
                for d in ds:
                    rec = days[d]
                    x = pr(d, rec, k)
                    ok = x is not None and (filt == "always" or x <= med[en])
                    if null and filt == "cheap":
                        ok = x is not None and rng.random() < 0.5
                    side = 0
                    if kind == "leg":
                        idx = rec["s"]["index"]
                        side = 1 if idx[3][14] >= idx[0][0] else -1
                        if null:
                            side = 1 if rng.random() < 0.5 else -1
                    if ok:
                        got = play(rec, kind, k, ex, ls, side)
                        nets.append(0.0 if got is None else got)
                    else:
                        nets.append(0.0)
                per[half] = {"net": round(sum(nets)), "won": sum(v > 0 for v in nets), "lost": sum(v < 0 for v in nets)}
            table[f"{'NULL ' if null else ''}{en} {filt} {ex}"] = per
        real = {k: v for k, v in table.items() if not k.startswith("NULL")}
        nul = {k: v for k, v in table.items() if k.startswith("NULL")}
        pick = max(real, key=lambda k: real[k]["choose"]["net"])
        npick = max(nul, key=lambda k: nul[k]["choose"]["net"])
        res["stress"][sname] = {"table": table, "pick": pick, "pick_score": real[pick]["score"], "null_pick": npick,
                                "null_score": nul[npick]["score"]}
        print(f"=== SN98 [{sname}]")
        for k, v in sorted(table.items(), key=lambda kv: -kv[1]["choose"]["net"]):
            print(f"  {k:36s} choose {v['choose']} score {v['score']}")
        print("  PICK", pick, "->", real[pick]["score"], "| NULL pick", npick, "->", nul[npick]["score"], flush=True)
    h = res["stress"]["house 100/leg"]
    res["PASS"] = h["pick_score"]["net"] > 0 and h["pick_score"]["net"] > h["null_score"]["net"] and \
        res["stress"]["strict 205/leg"]["pick_score"]["net"] > 0
    print("VERDICT", "PASS (development only)" if res["PASS"] else "NOT PROVEN")
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
