"""SN359: V8's order lifecycle on real depth (PLAN.md section 1; the details below are amendment A6, before any SN359
number).

Gold v5's replay at Rs 205 (parity Rs 8,50,882) on the days the real-quote archive covers (Sep 10 - Oct 28, 2026: the
replay ends Oct 28). For every original Gold decision (missed ones included), V8's orders on the archive's minute
snapshots of that contract (5 levels):
  entry: LIMIT at the snapshot's best ask + 2 ticks, at the entry minute's snapshot (or the next minute's if unusable);
         fills = whole lots of the quantity at levels <= the limit; the rest is cancelled (no resting fill assumed);
  adds:  at each add minute where paper added lots, the same LIMIT for paper's added lots, cut to what V8's paid premium
         + the add's premium + buy charges fits in the wallet (SN337's G1);
  exit:  at Gold's exit minute; reason "stop" -> MARKET (walk all bid levels); otherwise LIMIT at best bid - 2 ticks
         (levels >= the limit); any unfilled remainder sells as MARKET at each next usable snapshot (up to 5 minutes;
         left after that = marked at the last bid and counted "stuck").
  money: real fill prices, Zerodha charges, no stress. Compared with the replay's own modelled net at Rs 205 and with
         that net plus the Rs 205 per lot it charged (the replay at zero stress, approximately).
Reported: decisions, entered / partial / missed, lots paper vs V8, entry and exit slippage per unit against the replay's
modelled prices, sum of V8 net vs the replay's, the retained share, and the stuck count. fw4's SN346 stays frozen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
sys.path.insert(0, str(FNO / "2026-11-16-sn331"))
import gl  # noqa: E402
import qa  # noqa: E402
import sn339_350 as Q  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
OUT = HERE / "results-sn359.json"
TICK = 0.05
LOT = 65


def usable_at(rec, i, ahead=1):
    for k in range(i, min(qa.NM, i + ahead + 1)):
        if rec["usable"][k]:
            return k
    return None


def buy_limit(rec, k, need_units):
    lim = rec["ask"][k] + 2 * TICK
    got, cost = 0, 0.0
    for lv in range(5):
        p, q = rec["askp"][lv, k], rec["askq"][lv, k]
        if np.isnan(p) or np.isnan(q) or p > lim + 1e-9:
            continue
        take = min(q, need_units - got)
        got += take
        cost += take * p
        if got >= need_units:
            break
    lots = int(got // LOT)
    if lots == 0:
        return 0, None
    # whole lots only: take the cheapest units first
    left, c2 = lots * LOT, 0.0
    for lv in range(5):
        p, q = rec["askp"][lv, k], rec["askq"][lv, k]
        if np.isnan(p) or np.isnan(q) or p > lim + 1e-9 or left <= 0:
            continue
        take = min(q, left)
        c2 += take * p
        left -= take
    return lots, c2 / (lots * LOT)


def sell(rec, k, units, limit=None):
    """(units sold, proceeds) at snapshot k, levels >= limit (None = all levels)."""
    got, cash = 0, 0.0
    for lv in range(5):
        p, q = rec["bidp"][lv, k], rec["bidq"][lv, k]
        if np.isnan(p) or np.isnan(q) or (limit is not None and p < limit - 1e-9):
            continue
        take = min(q, units - got)
        got += take
        cash += take * p
        if got >= units:
            break
    return int(got), cash


def main():
    if OUT.exists():
        raise SystemExit("SN359 is run once")
    Q.install()
    C = Q.C
    orig = C.gold_one

    def capture(S, sg, *a, **kw):
        res = orig(S, sg, *a, **kw)
        if res is not None and Q.gw.LOG:
            Q.gw.LOG[-1]["strike"] = res[5]
        return res
    C.gold_one = capture
    row, days, log = Q.run(205.0)
    assert row["net"] == 850882
    arch = set(qa.days())
    out = []
    for x in log:
        d = x["day"]
        if d not in arch or d > "2026-10-28":
            continue
        q = qa.load(d)
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= d})
        rec = q["opt"].get(("NIFTY", exps[0], x["strike"], x["opt"])) if exps else None
        lots_paper = x["lots0"] + sum(a["added"] for a in x["adds"])
        r = {"day": d, "opt": x["opt"], "strike": x["strike"], "reason": x["reason"], "lots_paper": lots_paper,
             "replay_net205": round(x["net"], 1), "replay_net0_approx": round(x["net"] + 205.0 * lots_paper, 1)}
        if rec is None:
            r["v8"] = "no_contract_in_archive"
            out.append(r)
            continue
        k = usable_at(rec, x["i"])
        lots, px = (0, None) if k is None else buy_limit(rec, k, x["lots0"] * LOT)
        if lots == 0:
            r["v8"] = "missed_entry"
            out.append(r)
            continue
        pieces = [(px, lots)]
        r["entry_slip_per_unit"] = round(px - x["ask0"], 2)
        r["entry_partial"] = lots < x["lots0"]
        for a in x["adds"]:
            if a["added"] <= 0:
                continue
            ka = usable_at(rec, a["j"])
            if ka is None:
                continue
            paid = sum(e * n * LOT for e, n in pieces)
            want = a["added"]
            while want > 0 and paid + want * rec["ask"][ka] * LOT * 1.001 > x["wallet"]:
                want -= 1
            if want <= 0:
                continue
            la, pa = buy_limit(rec, ka, want * LOT)
            if la > 0:
                pieces.append((pa, la))
        units = sum(n for _e, n in pieces) * LOT
        cost_in = sum(e * n * LOT for e, n in pieces)
        avg_in = cost_in / units
        ke = usable_at(rec, x["j"])
        left, cash, stuck = units, 0.0, False
        tries = 0
        kk = ke
        while left > 0 and kk is not None and tries < 6:
            lim = None if (x["reason"] == "stop" or tries > 0) else rec["bid"][kk] - 2 * TICK
            g, c = sell(rec, kk, left, lim)
            left -= g
            cash += c
            tries += 1
            kk = usable_at(rec, kk + 1, 0) if kk + 1 < qa.NM else None
        if left > 0:
            stuck = True
            lastb = next((rec["bid"][z] for z in range(min(qa.NM - 1, x["j"] + 6), -1, -1) if not np.isnan(rec["bid"][z])), 0.0)
            cash += left * lastb
        avg_out = cash / units
        v8 = (avg_out - avg_in) * units - gl.wk.charges(avg_in, avg_out, units, "NFO")
        r.update(v8="entered", lots_v8=units // LOT, v8_net=round(v8, 1), exit_slip_per_unit=round(x["px"] - avg_out, 2), stuck=stuck,
                 exit_tries=tries)
        out.append(r)
    ent = [r for r in out if r.get("v8") == "entered"]
    res = {"decisions": len(out), "entered": len(ent), "missed": sum(r.get("v8") != "entered" for r in out),
           "missed_rows": [r for r in out if r.get("v8") != "entered"],
           "partial_entries": sum(1 for r in ent if r["entry_partial"]), "lots_paper": sum(r["lots_paper"] for r in ent),
           "lots_v8": sum(r["lots_v8"] for r in ent), "stuck": sum(1 for r in ent if r["stuck"]),
           "sum_v8_net": round(sum(r["v8_net"] for r in ent)), "sum_replay_net205": round(sum(r["replay_net205"] for r in ent)),
           "sum_replay_net0_approx": round(sum(r["replay_net0_approx"] for r in ent)),
           "sum_replay_net205_missed": round(sum(r["replay_net205"] for r in out if r.get("v8") != "entered")),
           "entry_slip_mean": round(float(np.mean([r["entry_slip_per_unit"] for r in ent])), 3) if ent else None,
           "exit_slip_mean": round(float(np.mean([r["exit_slip_per_unit"] for r in ent])), 3) if ent else None,
           "rows": out}
    if ent and res["sum_replay_net0_approx"]:
        res["retained_vs_replay0"] = round(res["sum_v8_net"] / res["sum_replay_net0_approx"], 3)
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("rows", "missed_rows")}))
    for r in out:
        print(json.dumps({k: r.get(k) for k in ("day", "reason", "lots_paper", "lots_v8", "replay_net205", "v8_net", "entry_slip_per_unit", "exit_slip_per_unit", "v8", "stuck")}))


if __name__ == "__main__":
    main()
