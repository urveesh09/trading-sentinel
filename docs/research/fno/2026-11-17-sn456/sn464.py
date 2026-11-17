"""SN464: why Gold's six-lot exits were missing (PLAN.md section 2, frozen at 83e1b444; details fixed here before any number).
Read only. All ten SN445 B trades stay in the denominator; SN445's own 6-of-10 result is kept beside the new states.

Trades: SN445 B's hooked Gold run (DEPLOYED 2023-26 at Rs 205, parity 8,50,882 / 883), trades on sealed archive days.
Quantities: SN445 walked the initial lots (lots0 x 65); the held quantity at the exit is the sum of Gold's entry pieces
(initial + adds) x 65. Both are reported; the states below use the HELD quantity (SN445's lots0 result is recomputed beside).
Snapshot grid: qa's minute index m = provider-timestamp minute - 555; the LAST raw record of the contract in that minute is
the minute's book (qa's own rule). The exit decision at index j arrives at snapshot j + 1 (SN445's convention).
States per minute m (j + 1 .. j + 6, and the entry side i + 1 .. i + 6 on the ask):
  FEED_STOPPED       no raw record of any contract in minute m
  INSTRUMENT_ABSENT  other contracts recorded in m, this one not (the strike window recorded for that expiry / type kept)
  NOT_USABLE         last record's depth_state != USABLE, or crossed / locked (the state kept)
  ZERO_BID           usable, but no positive bid level (ZERO_ASK on the entry side)
  PARTIAL            5-level bid quantity < requested
  FULL               5-level bid quantity >= requested
Per trade (exit): the first FULL minute within 5 minutes (j + 1 .. j + 6) and before the session's last recorded minute;
a V8-style partial exit (from j + 1, at each usable snapshot sell min(remaining, the 5 levels' quantity) at the walked
prices) with the quantity still open at j + 6 and at the end; the sold units' average price; cost against the model exit
price per lot of the held quantity; and a no-recovery scenario (unsold units lose their whole exit value).
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn441"))
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import sn441  # noqa: E402
import gold  # noqa: E402

qa = sn441.qa
OUT = HERE / "results-sn464.json"
LOT, GRACE = 65, 5


def raw_minutes(day, key):
    """(any_minutes set, this contract's {m: last record}, {m: strikes recorded for key's expiry/type})."""
    m = qa.manifest()["files_sha256"]
    anym, mine, window = set(), {}, collections.defaultdict(set)
    recs = []
    for k in sorted(x for x in m if x.startswith(f"quotes/{day}/") and x.endswith(".jsonl.gz")):
        b = (qa.EXPORT / k).read_bytes()
        assert hashlib.sha256(b).hexdigest() == m[k]
        for line in gzip.decompress(b).decode("utf-8").splitlines():
            recs.append(json.loads(line))
    for r in recs:
        raw = r.get("provider_timestamp_raw")
        if not raw:
            continue
        mm = int(raw[11:13]) * 60 + int(raw[14:16]) - 555
        c = r["contract"]
        anym.add(mm)
        if c["underlying"] == key[0] and c["expiry"] == key[1] and c["instrument_type"] == key[3]:
            window[mm].add(int(round(float(c["strike"]))))
            if int(round(float(c["strike"]))) == key[2]:
                mine[mm] = r
    return anym, mine, window


def levels(r, side):
    d = r.get("buy_depth" if side == "bid" else "sell_depth") or []
    return [(float(x["price"]), int(x["quantity"])) for x in d[:5] if (x.get("price") or 0) > 0 and (x.get("quantity") or 0) > 0]


def state(mm, anym, mine, need, side):
    if mm not in anym:
        return "FEED_STOPPED", None
    r = mine.get(mm)
    if r is None:
        return "INSTRUMENT_ABSENT", None
    if r.get("depth_state") != "USABLE" or r.get("crossed_depth") or r.get("locked_depth"):
        return "NOT_USABLE", r.get("depth_state")
    lv = levels(r, side)
    q = sum(x[1] for x in lv)
    if q <= 0:
        return "ZERO_BID" if side == "bid" else "ZERO_ASK", 0
    return ("FULL" if q >= need else "PARTIAL"), q


def walk(lv, qty):
    got, cost = 0, 0.0
    for p, q in lv:
        t = min(q, qty - got)
        cost += t * p
        got += t
        if got >= qty:
            break
    return got, cost


def trades():
    gw = gold.T.Q.gw
    orig = gw._ORIG["gold_one"]
    strikes = {}

    def rec_one(S, sg, *a, **kw):
        r = orig(S, sg, *a, **kw)
        if r is not None:
            strikes[(S.day, sg["i"])] = (r[5], S.s.get("expiry"))
        return r
    gold.install()
    gw._ORIG["gold_one"] = rec_one
    try:
        days, log, _ = gold.run(gold.Y2326, gold.DEPLOYED, 205.0)
    finally:
        gw._ORIG["gold_one"] = orig
    assert gold.summary(days, log)["net"] in (850882, 850883)
    man = qa.manifest()
    sealed = set(man["quote_days"]) - set(man["unsealed_days"])
    return [(x, strikes.get((x["day"], x["i"]), (None, None))) for x in log if x["day"] in sealed]


def main():
    if OUT.exists():
        raise SystemExit("SN464 is scored once")
    rows = []
    for x, (k, exp) in trades():
        key = ("NIFTY", exp, k, x["opt"])
        held = sum(int(p[1]) for p in x["pieces"])
        need_h, need_0 = held * LOT, x["lots0"] * LOT
        anym, mine, window = raw_minutes(x["day"], key)
        last_m = max(anym) if anym else None
        j, i = x["j"], x["i"]
        ex = []
        for mm in range(j + 1, j + 2 + GRACE):
            s, info = state(mm, anym, mine, need_h, "bid")
            s0, _ = state(mm, anym, mine, need_0, "bid")
            w = sorted(window.get(mm, ()))
            ex.append({"m": mm, "state_held": s, "state_lots0": s0, "info": info,
                       "window": [w[0], w[-1], len(w)] if w else None})
        en = []
        for mm in range(i + 1, i + 2 + GRACE):
            s, info = state(mm, anym, mine, need_0, "ask")
            w = sorted(window.get(mm, ()))
            en.append({"m": mm, "state": s, "info": info, "window": [w[0], w[-1], len(w)] if w else None})
        first_full_5 = next((e["m"] for e in ex if e["state_held"] == "FULL"), None)
        first_full_eod = None
        for mm in range(j + 1, (last_m or j) + 1):
            if state(mm, anym, mine, need_h, "bid")[0] == "FULL":
                first_full_eod = mm
                break
        # V8-style partial exit
        rem, sold, cash, open5 = need_h, 0, 0.0, None
        for mm in range(j + 1, (last_m or j) + 1):
            s, _ = state(mm, anym, mine, 1, "bid")
            if s in ("FULL", "PARTIAL"):
                got, c = walk(levels(mine[mm], "bid"), rem)
                rem -= got
                sold += got
                cash += c
            if mm == j + 1 + GRACE:
                open5 = rem
            if rem <= 0:
                break
        if open5 is None:
            open5 = rem
        px = float(x["px"])
        avg = cash / sold if sold else None
        cost_obs = None if avg is None else round((px - avg) * sold / held, 1)
        no_rec = round(((px * need_h) - (cash + 0.0 * rem)) / held, 1)
        r = {"day": x["day"], "contract": list(key), "i": i, "j": j, "exit_clock": f"{(555 + j) // 60:02d}:{(555 + j) % 60:02d}",
             "lots0": x["lots0"], "held_lots": held, "reason": x.get("reason"), "model_exit_px": round(px, 2), "replay_net": round(x["net"], 1),
             "exit_minutes": ex, "entry_minutes": en, "first_full_within_5": first_full_5, "first_full_to_end": first_full_eod,
             "last_recorded_minute": last_m, "partial_exit": {"sold_units": sold, "open_at_5min": open5, "open_at_end": rem,
                                                              "avg_px": None if avg is None else round(avg, 2)},
             "observed_cost_per_held_lot_vs_model": cost_obs, "no_recovery_cost_per_held_lot": no_rec}
        rows.append(r)
    res = {"trades": len(rows),
           "sn445_kept": "6 OK / 4 INSUFFICIENT on the initial lots (results-sn445.json)",
           "held_differs_from_lots0": sum(r["held_lots"] != r["lots0"] for r in rows),
           "exit_state_at_arrival_held": dict(collections.Counter(r["exit_minutes"][0]["state_held"] for r in rows)),
           "exit_state_at_arrival_lots0": dict(collections.Counter(r["exit_minutes"][0]["state_lots0"] for r in rows)),
           "entry_state_at_arrival": dict(collections.Counter(r["entry_minutes"][0]["state"] for r in rows)),
           "full_within_5_held": sum(r["first_full_within_5"] is not None for r in rows),
           "full_by_end_held": sum(r["first_full_to_end"] is not None for r in rows),
           "exits_at_1510": [r["day"] for r in rows if r["j"] == 355],
           "partial_exit_open_at_5min_units": {r["day"] + f" i{r['i']}": r["partial_exit"]["open_at_5min"] for r in rows},
           "mean_observed_cost_per_held_lot_resolved": round(float(np.mean([r["observed_cost_per_held_lot_vs_model"] for r in rows
                                                                              if r["partial_exit"]["open_at_end"] == 0])), 1) if any(r["partial_exit"]["open_at_end"] == 0 for r in rows) else None,
           "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
