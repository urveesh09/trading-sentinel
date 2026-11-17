"""SN460: usable exit depth on qualified entries (PLAN.md section 1, frozen at 83e1b444; details fixed here before any number).

A. Production's paper stops: FNO_PAPER NIFTY positions, CLOSED the same day on a sealed archive day, exit_reason in
   (underlying_stop, premium_backstop, trail_stop); trigger time T = exit_time (the order's time; no separate trigger clock is
   stored). Causal state = the contract's last raw record in the minute before T's minute (SN464's raw reader): best spread,
   best and 5-level bid units, the record's receipt lag (received - provider, s), the volume change over the previous 5 minutes.
   Label = the first raw minute record after T whose provider time is > T, usable, with a 5-level bid holding the request:
   elapsed s (provider time - T), fw2's bucket (on time <= 10 s, late <= 120 s, else unresolved) and the walked bid's extra loss
   against the trigger mark (that state's best bid) x the request. Requests: the position's own quantity, one lot, six lots.
B. Gold's 6-lot replay exits inside the archive (SN464's rows): their exit reasons, and how many are observed hard exits.
C. Plumbing only (the Nov 16 recorder copy, before any forward start): synthetic exit orders every 600 s (09:25 - 15:05) on the
   front weekly ATM CE and PE; the time to the first fresh packet with 5-level bid >= 1 lot / 6 lots after T + 0.5 s at packet
   level, against the minute view (the last packet of each 60 s bucket, observed at the bucket's end); medians and the walked
   price difference a lot.
Classifier (first snapshot rule / depth rule / logistic) only with >= 30 independent stop dates; otherwise INSUFFICIENT.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
import sn464  # noqa: E402
import fw2  # noqa: E402

qa = sn464.qa
OUT = HERE / "results-sn460.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
REC = Path(r"C:\Users\Urveesh\AppData\Local\Temp\claude\f191b6166a36c84a\b7c0aa9b-c954-4f08-9df8-57422081ea0c\scratchpad\rec\2026-11-16")
STOPS = ("underlying_stop", "premium_backstop", "trail_stop")


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(IST)


def pts(r):
    return ts(r["provider_timestamp_utc"]) if r.get("provider_timestamp_utc") else None


def bids(r):
    return sn464.levels(r, "bid")


def usable(r):
    return r is not None and r.get("depth_state") == "USABLE" and not r.get("crossed_depth") and not r.get("locked_depth")


def walk_px(lv, need):
    got, cost = 0, 0.0
    for p, q in lv:
        t = min(q, need - got)
        cost += t * p
        got += t
        if got >= need:
            return cost / need
    return None


def part_a():
    man = qa.manifest()
    sealed = set(man["quote_days"]) - set(man["unsealed_days"])
    con = sqlite3.connect(f"file:{(qa.EXPORT / 'fno-replay.sqlite').as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT expiry, strike, opt_type, qty, lot_size, exit_time, exit_premium, exit_reason FROM fno_positions "
                       "WHERE source='FNO_PAPER' AND underlying='NIFTY' AND status='CLOSED' AND exit_reason IN (?,?,?)", STOPS).fetchall()
    out, cache = [], {}
    for exp, k, o, qty, lot, xt, xp, why in rows:
        T = ts(xt)
        d = T.date().isoformat()
        r = {"day": d, "reason": why, "qty": int(qty), "exit_clock": T.strftime("%H:%M:%S")}
        if d not in sealed:
            r["state"] = "NOT_IN_ARCHIVE"
            out.append(r)
            continue
        key = ("NIFTY", str(exp)[:10], int(round(float(k))), o)
        if (d, key) not in cache:
            cache[(d, key)] = sn464.raw_minutes(d, key)
        anym, mine, _w = cache[(d, key)]
        m0 = T.hour * 60 + T.minute - 555
        st = mine.get(m0 - 1)
        if not usable(st):
            r["state"] = "NO_CAUSAL_STATE"
            out.append(r)
            continue
        lv = bids(st)
        ask = sn464.levels(st, "ask")
        r.update(state="LABELLED", spread=round(ask[0][0] - lv[0][0], 2) if ask and lv else None, best_bid_units=lv[0][1] if lv else 0,
                 bid5_units=sum(x[1] for x in lv), receipt_lag_s=None, trigger_mark=lv[0][0] if lv else None)
        try:
            r["receipt_lag_s"] = round((ts(st["received_at_utc"]) - pts(st)).total_seconds(), 2)
        except Exception:
            pass
        v0, v5 = (mine.get(m0 - 1) or {}).get("volume"), (mine.get(m0 - 6) or {}).get("volume")
        r["vol_change_5m"] = (v0 - v5) if v0 is not None and v5 is not None else None
        for tag, need in (("own", int(qty)), ("one_lot", int(lot or 65)), ("six_lots", 6 * int(lot or 65))):
            lab = {"bucket": "unresolved", "elapsed_s": None, "extra_loss": None}
            for mm in range(m0, m0 + 10):
                x = mine.get(mm)
                if not usable(x) or pts(x) is None or pts(x) <= T:
                    continue
                b = bids(x)
                if sum(q for _p, q in b) >= need:
                    e = (pts(x) - T).total_seconds()
                    px = walk_px(b, need)
                    lab = {"bucket": "on_time" if e <= fw2.ON_TIME else ("late" if e <= fw2.LATE else "unresolved"), "elapsed_s": round(e, 1),
                           "extra_loss": round((r["trigger_mark"] - px) * need, 1) if r["trigger_mark"] else None}
                    break
            r[tag] = lab
        r["paper_exit_premium"] = xp
        out.append(r)
    lab = [r for r in out if r["state"] == "LABELLED"]
    res = {"stop_events": len(out), "states": dict(collections.Counter(r["state"] for r in out)),
           "by_reason": dict(collections.Counter(r["reason"] for r in out)),
           "independent_stop_dates": len({r["day"] for r in out}), "labelled_dates": len({r["day"] for r in lab})}
    for tag in ("own", "one_lot", "six_lots"):
        res[tag] = {"buckets": dict(collections.Counter(r[tag]["bucket"] for r in lab)),
                    "median_elapsed_s": float(np.median([r[tag]["elapsed_s"] for r in lab if r[tag]["elapsed_s"] is not None])) if lab else None,
                    "mean_extra_loss": round(float(np.mean([r[tag]["extra_loss"] for r in lab if r[tag]["extra_loss"] is not None])), 1) if lab else None}
    res["classifier"] = "RUN" if res["independent_stop_dates"] >= 30 else "INSUFFICIENT (fewer than 30 independent stop dates)"
    res["rows"] = out
    return res


def part_b():
    p = HERE / "results-sn464.json"
    rows = json.loads(p.read_text(encoding="utf-8"))["rows"]
    return {"gold_trades": len(rows), "reasons": dict(collections.Counter(r["reason"] for r in rows)),
            "observed_hard_exits": sum(1 for r in rows if r["exit_minutes"][0]["state_held"] in ("ZERO_BID", "PARTIAL"))}


def part_c():
    import fw5  # noqa: E402
    day = fw2.Day(REC, fw5.load_open(REC))
    res = {"label": "PLUMBING (Nov 16 recorder copy)"}
    for tag, need in (("one_lot", day.lot), ("six_lots", 6 * day.lot)):
        el_p, el_m, dpx = [], [], []
        for T in range(600, 21001, 600):
            atm = day.atm(float(T))
            if atm is None:
                continue
            for side in ("CE", "PE"):
                tok = day.opt.get((day.front, atm, side))
                if tok is None or tok not in day.D:
                    continue
                d = day.D[tok]
                t = d["t"]
                k = int(np.searchsorted(t, T + fw2.EXIT_LAT))
                pk = next((j for j in range(k, len(t)) if d["ok"][j] and d["b5"][j] >= need), None)
                buckets = {}
                for j in range(k, len(t)):
                    buckets[int(t[j] // 60)] = j
                mk = next(((b + 1) * 60, j) for b, j in sorted(buckets.items()) if d["ok"][j] and d["b5"][j] >= need) if buckets else None
                if pk is None or mk is None:
                    continue
                el_p.append(float(t[pk] - T))
                el_m.append(float(mk[0] - T))
                pp, pm = fw2.walk(d["bids"][:, pk], d["bidq"][:, pk], need), fw2.walk(d["bids"][:, mk[1]], d["bidq"][:, mk[1]], need)
                if pp is not None and pm is not None:
                    dpx.append((pp - pm) * day.lot)
        res[tag] = {"orders": len(el_p), "median_elapsed_packet_s": float(np.median(el_p)) if el_p else None,
                    "median_elapsed_minute_s": float(np.median(el_m)) if el_m else None,
                    "mean_packet_minus_minute_rupees_a_lot": round(float(np.mean(dpx)), 1) if dpx else None}
    return res


def main():
    if OUT.exists():
        raise SystemExit("SN460 is scored once")
    res = {"A_paper_stops": part_a(), "B_gold_replay": part_b(), "C_plumbing": part_c()}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != "rows"} if isinstance(v, dict) else v) for k, v in res.items()}, indent=1, default=float))


if __name__ == "__main__":
    main()
