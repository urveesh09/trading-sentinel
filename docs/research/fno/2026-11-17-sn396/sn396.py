"""SN396 A + B (PLAN.md section 1, frozen at 00693405): the opening trade on the real clock, and the model's opening
cost against real quotes. Run once; writes results-sn396.json.

A (gl DEV + TEST, the AUCTION sessions of SN382 with g != 0): the ITM (2 then 1), ATM and coin-ITM legs under ORIGINAL /
  HONEST / LATE (op.py), held 20 / 60 minutes with the Rs 3,000 stop, Rs 205 / 400. Parity first: ORIGINAL must give
  SN382's 171 sessions, 146 fills, +45.6 / -137.5 per session (60 m) and SN394b's 124 readings / 73 CHEAP / +396.3. Then
  per clock: per session, fills, states, without the best day, periods, sources, paired vs ATM / coin on common fills,
  and the CHEAP split by the frozen cutoff and by the causal tercile; label, strike and depth changes vs ORIGINAL.
B (the real-quote archive, sealed days that are also gl sessions, non-expiry, AUCTION sessions): the auction-side ATM /
  1-ITM / 2-ITM contracts at the HONEST strike. The archive snapshots once a minute at about hh:mm:27, so the entry
  quote is the snapshot in [09:16:00, 09:17:00) and the exit quote the one in [10:16:00, 10:17:00) (both inside the
  ORIGINAL bars). Per contract: real walked one-lot ask vs gl's modelled ask on the 09:16 close, real walked bid vs the
  modelled bid on the 10:16 close; the real extra round-trip cost per lot (entry + exit) against the Rs 205 / 400 stress;
  the real mid vs the Breeze 09:15 and 09:16 closes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402

gl, wk = op.gl, op.wk
OUT = HERE / "results-sn396.json"
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
              r"\_local\exports\20261116T103002Z")
LOCAL = HERE / "_local"
WINDOWS = (("09:15:00", "09:17:00"), ("10:15:00", "10:17:00"), ("11:00:00", "11:01:00"))


# ---- A ------------------------------------------------------------------------------------------------------------------
def score(smp, au, clock, H=(20, 60)):
    rows = []
    for d, a in sorted(au.items()):
        if a["g"] == 0:
            continue
        s = smp.s[d]
        side = "CE" if a["g"] > 0 else "PE"
        r = {"day": d, "src": a["how"], "period": "post" if d >= op.SPLIT else "pre"}
        for arm, sd, dep in (("ITM", side, (2, 1)), ("ATM", side, (0,)), ("COIN_ITM", op.coin(d), (2, 1))):
            x = {}
            for st in (205.0, 400.0):
                pos, depth, state, jf = op.leg(smp, s, sd, 1, clock, st, dep)
                x["state"], x["depth"] = state, depth
                if pos is None:
                    continue
                x["strike"], x["fill"] = pos.legs[0][0], pos.fills[0]
                for h in H:
                    net, _j, _w = gl.walk(pos, s, jf, jf + h, room=op.STOP)
                    x[f"{h}m@{int(st)}"] = None if net is None else round(net, 2)
            r[arm] = x
        rows.append(r)
    return rows


def val(r, arm, k):
    x = r[arm]
    return (x.get(k) or 0.0) if x["state"] == "FILLED" else 0.0


def summary(rows, arm="ITM"):
    out = {"sessions": len(rows), "fills": sum(r[arm]["state"] == "FILLED" for r in rows),
           "states": {s: sum(r[arm]["state"] == s for r in rows) for s in ("FILLED", "INADMISSIBLE", "MISSED", "NO_PRICE")}}
    for h in (20, 60):
        for st in (205, 400):
            k = f"{h}m@{st}"
            xs = [val(r, arm, k) for r in rows]
            out[f"per_session {k}"] = op.per_session(xs)
            if h == 60:
                out[f"without_best_day {k}"] = op.without_best(xs)
    for c in ("ATM", "COIN_ITM"):
        com = [r for r in rows if r[arm]["state"] == "FILLED" and r[c]["state"] == "FILLED"
               and r[arm].get("60m@205") is not None and r[c].get("60m@205") is not None]
        dd = np.array([r[arm]["60m@205"] - r[c]["60m@205"] for r in com])
        out[f"paired vs {c} 60m@205"] = {"common": len(com), "mean": round(float(dd.mean()), 1) if len(dd) else None,
                                         "se": round(float(dd.std(ddof=1) / np.sqrt(len(dd))), 1) if len(dd) > 1 else None}
    return out


def part_a(smp, au):
    res, rows = {}, {}
    for clock in op.CLOCKS:
        rows[clock] = score(smp, au, clock)
    o = summary(rows["ORIGINAL"])
    assert o["sessions"] == 171 and o["fills"] == 146, (o["sessions"], o["fills"])
    assert o["per_session 60m@205"] == 45.6 and o["per_session 60m@400"] == -137.5, (o["per_session 60m@205"], o["per_session 60m@400"])
    jm = {c: op.jumps(smp, c) for c in op.CLOCKS}
    lab = {c: {"fixed": op.labels(jm[c], True), "moving": op.labels(jm[c], False)} for c in op.CLOCKS}
    for clock, rs in rows.items():
        c = res[clock] = {"all": summary(rs)}
        for per in ("pre", "post"):
            c[f"all {per}"] = summary([r for r in rs if r["period"] == per])
        for src in ("match_row", "fallback_0915_open"):
            c[f"all {src}"] = summary([r for r in rs if r["src"] == src])
        for how in ("fixed", "moving"):
            L = lab[clock][how]
            withr = [r for r in rs if r["day"] in L]
            ch = [r for r in withr if L[r["day"]] == "CHEAP"]
            c[f"CHEAP {how}"] = {"with_reading": len(withr), "cheap": len(ch), **summary(ch)}
            c[f"OTHER {how}"] = summary([r for r in withr if L[r["day"]] != "CHEAP"])
            for per in ("pre", "post"):
                c[f"CHEAP {how} {per}"] = summary([r for r in ch if r["period"] == per])
            # per session over every AUCTION session, cheap only traded (fw9's per_session_all)
            for st in (205, 400):
                c[f"CHEAP {how} over all sessions 60m@{st}"] = op.per_session([val(r, "ITM", f"60m@{st}") if L.get(r["day"]) == "CHEAP" else 0.0 for r in rs])
    m = res["ORIGINAL"]["CHEAP moving"]
    assert (m["with_reading"], m["cheap"], m["per_session 60m@205"]) == (124, 73, 396.3), (m["with_reading"], m["cheap"], m["per_session 60m@205"])
    ch = {}
    o_rows = {r["day"]: r for r in rows["ORIGINAL"]}
    for clock in ("HONEST", "LATE"):
        x = {"strike_changed": 0, "depth_changed": 0, "state_changed": 0}
        for r in rows[clock]:
            q = o_rows[r["day"]]["ITM"]
            x["strike_changed"] += r["ITM"].get("strike") != q.get("strike") and r["ITM"]["state"] == q["state"] == "FILLED"
            x["depth_changed"] += r["ITM"].get("depth") != q.get("depth")
            x["state_changed"] += r["ITM"]["state"] != q["state"]
        for how in ("fixed", "moving"):
            a_, b_ = lab["ORIGINAL"][how], lab[clock][how]
            com = [d for d in a_ if d in b_ and d in o_rows]
            x[f"cheap_label_changed {how}"] = sum((a_[d] == "CHEAP") != (b_[d] == "CHEAP") for d in com)
            x[f"common_readings {how}"] = len(com)
        ch[clock] = x
    res["changes_vs_ORIGINAL"] = ch
    res["jump_corr_ORIGINAL_HONEST"] = round(float(np.corrcoef([jm["ORIGINAL"][d] for d in jm["ORIGINAL"] if d in jm["HONEST"]],
                                                               [jm["HONEST"][d] for d in jm["ORIGINAL"] if d in jm["HONEST"]])[0, 1]), 3)
    return res, rows


# ---- B ------------------------------------------------------------------------------------------------------------------
def archive_day(day):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"arch-{day}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    man = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))["files_sha256"]
    out = {}
    for k in sorted(x for x in man if x.startswith(f"quotes/{day}/") and x.endswith(".jsonl.gz")):
        b = (EXPORT / k).read_bytes()
        assert hashlib.sha256(b).hexdigest() == man[k], k
        for line in gzip.decompress(b).decode("utf-8").splitlines():
            r = json.loads(line)
            t = (r.get("provider_timestamp_raw") or "")[11:19]
            if not any(a <= t < b_ for a, b_ in WINDOWS):
                continue
            c = r["contract"]
            if c["underlying"] != "NIFTY":
                continue
            ok = r.get("depth_state") == "USABLE" and not r.get("crossed_depth") and not r.get("locked_depth")
            key = ("FUT", c["expiry"]) if c["instrument_type"] == "FUT" else (c["instrument_type"], c["expiry"], int(round(float(c["strike"]))))
            out.setdefault(key, []).append({"t": t, "ok": ok, "ltp": r.get("ltp"),
                                            "bids": [(x["price"], x["quantity"]) for x in (r.get("buy_depth") or []) if x.get("price") and x.get("quantity")],
                                            "asks": [(x["price"], x["quantity"]) for x in (r.get("sell_depth") or []) if x.get("price") and x.get("quantity")]})
    p.write_bytes(pickle.dumps(out))
    return out


def snap(recs, lo, hi):
    xs = [r for r in recs or [] if lo <= r["t"] < hi and r["ok"] and r["bids"] and r["asks"]]
    return xs[-1] if xs else None


def walk(levels, need):
    got = cost = 0.0
    for p, q in levels:
        take = min(q, need - got)
        cost += take * p
        got += take
        if got >= need:
            return cost / need
    return None


def part_b(smp, au):
    man = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
    sealed = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    days = [d for d in sealed if d in au and d in smp.s and au[d]["g"] != 0]
    per = {"ATM": [], "ITM1": [], "ITM2": []}
    for d in days:
        s = smp.s[d]
        A = archive_day(d)
        side = "CE" if au[d]["g"] > 0 else "PE"
        atm = gl.atm(smp, s, 0)
        sgn = -1 if side == "CE" else 1
        for name, dep in (("ATM", 0), ("ITM1", 1), ("ITM2", 2)):
            k = atm + sgn * dep * 50
            recs = A.get((side, s["expiry"], k))
            e1, x1 = snap(recs, "09:16:00", "09:17:00"), snap(recs, "10:16:00", "10:17:00")
            e0 = snap(recs, "09:15:00", "09:16:00")
            c0, c1, c61 = gl.opx(s, k, side, 0, look=0), gl.opx(s, k, side, 1, look=0), gl.opx(s, k, side, 61, look=0)
            if e1 is None or x1 is None or c1 is None or c61 is None:
                continue
            ra, rb = walk(e1["asks"], op.LOT), walk(x1["bids"], op.LOT)
            if ra is None or rb is None:
                continue
            ma, mb = wk.ask(smp.mk, c1), wk.bid(smp.mk, c61)
            mid1 = 0.5 * (e1["bids"][0][0] + e1["asks"][0][0])
            per[name].append({"day": d, "t_entry": e1["t"], "t_exit": x1["t"], "real_ask": ra, "model_ask": ma, "real_bid": rb, "model_bid": mb,
                              "entry_extra": (ra - ma) * op.LOT, "exit_extra": (mb - rb) * op.LOT, "real_spread": (e1["asks"][0][0] - e1["bids"][0][0]) * op.LOT,
                              "model_spread": (wk.ask(smp.mk, c1) - wk.bid(smp.mk, c1)) * op.LOT,
                              "mid_vs_close0916": abs(mid1 - c1), "mid_vs_close0915": None if c0 is None else abs(mid1 - c0),
                              "mid0915_vs_close0915": None if (e0 is None or c0 is None) else abs(0.5 * (e0["bids"][0][0] + e0["asks"][0][0]) - c0)})
    out = {"days": len(days)}
    for name, xs in per.items():
        if not xs:
            out[name] = {"n": 0}
            continue
        tot = np.array([x["entry_extra"] + x["exit_extra"] for x in xs])
        med = lambda k: round(float(np.median([x[k] for x in xs if x[k] is not None])), 2)  # noqa: E731
        mean = lambda k: round(float(np.mean([x[k] for x in xs if x[k] is not None])), 2)  # noqa: E731
        out[name] = {"n": len(xs), "extra_round_trip_per_lot_mean": round(float(tot.mean()), 1), "extra_round_trip_per_lot_median": round(float(np.median(tot)), 1),
                     "extra_p75": round(float(np.percentile(tot, 75)), 1), "extra_p90": round(float(np.percentile(tot, 90)), 1),
                     "share_above_205": round(float((tot > 205).mean()), 3), "share_above_400": round(float((tot > 400).mean()), 3),
                     "entry_extra_mean": mean("entry_extra"), "exit_extra_mean": mean("exit_extra"),
                     "real_spread_lot_median": med("real_spread"), "model_spread_lot_median": med("model_spread"),
                     "mid_vs_close0916_median": med("mid_vs_close0916"), "mid_vs_close0915_median": med("mid_vs_close0915"),
                     "mid0915_vs_close0915_median": med("mid0915_vs_close0915"), "rows": xs}
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN396 A + B are run once")
    smp, days, au = op.setup()
    resA, _rows = part_a(smp, au)
    for clock in op.CLOCKS:
        c = resA[clock]
        print(clock, json.dumps({k: {x: c[k].get(x) for x in ("sessions", "fills", "cheap", "per_session 60m@205", "per_session 60m@400", "without_best_day 60m@205")}
                                 for k in ("all", "all pre", "all post", "CHEAP fixed", "CHEAP moving")}), flush=True)
    print("changes", json.dumps(resA["changes_vs_ORIGINAL"]), flush=True)
    resB = part_b(smp, au)
    print("B", json.dumps({k: ({x: v[x] for x in v if x != "rows"} if isinstance(v, dict) else v) for k, v in resB.items()}), flush=True)
    OUT.write_text(json.dumps({"A": resA, "B": resB}, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
