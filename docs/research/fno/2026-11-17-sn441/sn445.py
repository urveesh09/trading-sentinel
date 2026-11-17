"""SN445: Gold's cost at its own clock and size (PLAN.md section 1, frozen at f56f5807; details fixed here before any number).
Read only; insufficient rows are kept.

A. SN440's paper rounds re-referenced (fno_positions, FNO_PAPER, NIFTY, CLOSED, same-day, front expiry in gl):
   model     wk.ask / wk.bid of the last COMPLETE minute bar before each fill (gl index m - 1 for a fill inside minute m)
   extra     (paper entry - model ask) x lot + (model bid - paper exit) x lot, per lot (positive = real dearer)
   archive   (sealed quote days only) the last raw snapshot of the contract whose provider timestamp is <= the fill time:
             displacement in seconds, the walked ask / bid for the round's full quantity there, the paper price minus
             that walk per lot, and the front future's move from that snapshot to the next one x the recorded delta x
             lot (the market moving inside the gap), reported apart
   fees      Zerodha charges for the round's own quantity, per lot
B. Gold's own replay trades inside the archive (the deployed 2023-26 path at Rs 205, entries on sealed days from Sep 10):
   the contract (strike from gold_one's return, Gold's front weekly), entry minute i and exit minute j as the replay has
   them, the initial lots. Real = the walked ask for lots x 65 at archive snapshot i + 1 (the first after the replay's fill
   at bar i's close; snapshot i, just before, also shown) and the walked bid at snapshot j + 1. real - model per lot =
   (real ask - ask0) x 65 + (model exit px - real bid) x 65, by lot bucket 1 / 2-3 / 4+; INSUFFICIENT if 5 levels cannot
   hold the quantity or a snapshot is missing.
C. Dated STT: the replay charges 0.15% on every option sale; the dated rate is 0.0625% before Oct 1, 2024, 0.1% to
   Mar 31, 2026 and 0.15% after. The difference on Gold's 2023-26 trades (exit price x exited quantity), at Rs 205 / 400.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import sn441  # noqa: E402
import op  # noqa: E402

qa, C = sn441.qa, sn441.C
gl, wk = op.gl, op.wk
OUT = HERE / "results-sn445.json"
EXPORT = qa.EXPORT
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
LOT = 65


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(IST)


def walk(levels, qty):
    got, cost = 0, 0.0
    for p, q in levels:
        if not p or not q or p <= 0 or q <= 0:
            continue
        take = min(q, qty - got)
        cost += take * p
        got += take
        if got >= qty:
            return cost / qty
    return None


def raw_day(day, want):
    """{key: [(provider ts IST datetime, asks [(p, q)], bids [(p, q)], ltp)]} for wanted (underlying, expiry, strike, type)."""
    m = qa.manifest()["files_sha256"]
    out = {}
    for k in sorted(x for x in m if x.startswith(f"quotes/{day}/") and x.endswith(".jsonl.gz")):
        b = (EXPORT / k).read_bytes()
        assert hashlib.sha256(b).hexdigest() == m[k]
        for line in gzip.decompress(b).decode("utf-8").splitlines():
            r = json.loads(line)
            c = r["contract"]
            key = (c["underlying"], c["expiry"], int(round(float(c["strike"]))), c["instrument_type"])
            if key not in want or not r.get("provider_timestamp_utc"):
                continue
            ok = r.get("depth_state") == "USABLE" and not r.get("crossed_depth") and not r.get("locked_depth")
            if not ok:
                continue
            out.setdefault(key, []).append((ts(r["provider_timestamp_utc"]),
                                            [(x.get("price"), x.get("quantity")) for x in (r.get("sell_depth") or [])],
                                            [(x.get("price"), x.get("quantity")) for x in (r.get("buy_depth") or [])], r.get("ltp")))
    for v in out.values():
        v.sort(key=lambda z: z[0])
    return out


def before(snaps, t):
    xs = [z for z in snaps if z[0] <= t]
    return xs[-1] if xs else None


def after(snaps, t):
    xs = [z for z in snaps if z[0] > t]
    return xs[0] if xs else None


def part_a(smp, sealed):
    con = sqlite3.connect(f"file:{(EXPORT / 'fno-replay.sqlite').as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT expiry, strike, opt_type, lots, lot_size, entry_time, entry_premium, exit_time, exit_premium, delta_at_entry "
                       "FROM fno_positions WHERE source='FNO_PAPER' AND underlying='NIFTY' AND status='CLOSED'").fetchall()
    out = []
    raws = {}
    for exp, k, o, lots, lot, et, ep, xt, xp, dl in rows:
        te, tx = ts(et), ts(xt)
        d = te.date().isoformat()
        if d not in smp.s or tx.date() != te.date() or smp.s[d]["expiry"] != str(exp)[:10]:
            continue
        s = smp.s[d]
        k = int(round(float(k)))
        lot = int(lot or 65)
        qty = int(lots or 1) * lot
        me = te.hour * 60 + te.minute - 555
        mx = tx.hour * 60 + tx.minute - 555
        ce, cx = gl.opx(s, k, o, me - 1, look=2), gl.opx(s, k, o, mx - 1, look=2)
        if ce is None or cx is None:
            continue
        r = {"day": d, "lots": int(lots or 1), "hour": te.hour,
             "extra_complete_bar_per_lot": round((ep - wk.ask(smp.mk, ce)) * lot + (wk.bid(smp.mk, cx) - xp) * lot, 2),
             "fees_per_lot": round(wk.charges(ep, xp, qty, "NFO") / max(1, int(lots or 1)), 2)}
        if d in sealed:
            if d not in raws:
                want = {("NIFTY", str(e)[:10], int(round(float(kk))), oo) for e, kk, oo, *_ in rows if ts(_[2]).date().isoformat() == d}
                q = qa.load(d)
                fk = max(((int(rr["usable"].sum()), kk) for kk, rr in q["fut"].items() if kk[0] == "NIFTY"), default=(0, None))[1]
                if fk is not None:
                    want.add(("NIFTY", fk[1], 0, "FUT"))
                raws[d] = (raw_day(d, want), fk)
            raw, fk = raws[d]
            sn = raw.get(("NIFTY", str(exp)[:10], k, o), [])
            fs = raw.get(("NIFTY", fk[1], 0, "FUT"), []) if fk else []
            for tag, t, px, side in (("entry", te, ep, "ask"), ("exit", tx, xp, "bid")):
                z = before(sn, t)
                if z is None:
                    r[f"{tag}_archive"] = "NO_SNAPSHOT"
                    continue
                w = walk(z[1] if side == "ask" else z[2], qty)
                r[f"{tag}_displacement_s"] = round((t - z[0]).total_seconds(), 1)
                r[f"{tag}_paper_minus_walk_per_lot"] = None if w is None else round(((px - w) if side == "ask" else (w - px)) * lot, 2)
                f0, f1 = before(fs, t), after(fs, t)
                if f0 and f1 and f0[3] and f1[3] and dl is not None:
                    r[f"{tag}_market_move_per_lot"] = round(abs(float(dl)) * (f1[3] - f0[3]) * (1 if o == "CE" else -1) * lot * (1 if side == "ask" else -1), 2)
        out.append(r)
    res = {"rounds": len(out)}
    xs = [r["extra_complete_bar_per_lot"] for r in out]
    res["extra_complete_bar_per_lot"] = {"mean": round(float(np.mean(xs)), 1), "median": round(float(np.median(xs)), 1),
                                         "p90": round(float(np.percentile(xs, 90)), 1), "share_above_205": round(float(np.mean([x > 205 for x in xs])), 3)}
    for tag in ("entry", "exit"):
        dsp = [r[f"{tag}_displacement_s"] for r in out if f"{tag}_displacement_s" in r]
        pw = [r[f"{tag}_paper_minus_walk_per_lot"] for r in out if r.get(f"{tag}_paper_minus_walk_per_lot") is not None]
        mm = [r[f"{tag}_market_move_per_lot"] for r in out if f"{tag}_market_move_per_lot" in r]
        res[f"archive_{tag}"] = {"n": len(dsp), "displacement_s_median": float(np.median(dsp)) if dsp else None,
                                 "paper_minus_walk_per_lot_mean": round(float(np.mean(pw)), 1) if pw else None,
                                 "paper_minus_walk_per_lot_median": round(float(np.median(pw)), 1) if pw else None,
                                 "market_move_per_lot_mean": round(float(np.mean(mm)), 1) if mm else None}
    res["fees_per_lot_median"] = round(float(np.median([r["fees_per_lot"] for r in out])), 1)
    res["rows"] = out
    return res


def part_b(sealed):
    import gold  # noqa: E402
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
    out = []
    for x in log:
        if x["day"] not in sealed:
            continue
        k, exp = strikes.get((x["day"], x["i"]), (None, None))
        typ = x["opt"]
        q = qa.load(x["day"])
        rec = q["opt"].get(("NIFTY", exp, k, typ)) if k is not None else None
        r = {"day": x["day"], "i": x["i"], "j": x["j"], "lots": x["lots0"], "strike": k, "expiry": exp, "opt": typ, "ask0": x["ask0"],
             "model_exit": round(float(x["px"]), 2), "replay_net": round(x["net"], 1), "adds": sum(a.get("added", 0) for a in x.get("adds", []) if isinstance(a, dict))}
        if rec is None:
            r["state"] = "UNRECORDED"
            out.append(r)
            continue
        qty = x["lots0"] * LOT

        def wl(i, side):
            if not (0 <= i < qa.NM) or not rec["usable"][i]:
                return None
            p, qq = (rec["askp"][:, i], rec["askq"][:, i]) if side == "ask" else (rec["bidp"][:, i], rec["bidq"][:, i])
            return qa.walk_cost(p, qq, qty)
        ea, ea0, xb = wl(x["i"] + 1, "ask"), wl(x["i"], "ask"), wl(x["j"] + 1, "bid")
        r["real_ask_after"], r["real_ask_before"], r["real_exit_bid"] = ea, ea0, xb
        if ea is None or xb is None:
            r["state"] = "INSUFFICIENT"
        else:
            r["state"] = "OK"
            r["real_minus_model_per_lot"] = round((ea - x["ask0"]) * LOT + (x["px"] - xb) * LOT, 1)
            r["entry_part_per_lot"] = round((ea - x["ask0"]) * LOT, 1)
            r["exit_part_per_lot"] = round((x["px"] - xb) * LOT, 1)
        out.append(r)
    res = {"trades_in_window": len(out), "states": {s: sum(1 for r in out if r["state"] == s) for s in ("OK", "INSUFFICIENT", "UNRECORDED")}}
    for name, lo, hi in (("1 lot", 1, 1), ("2-3 lots", 2, 3), ("4+ lots", 4, 999), ("all", 1, 999)):
        xs = [r for r in out if r["state"] == "OK" and lo <= r["lots"] <= hi]
        res[name] = {"n": len(xs), "mean_real_minus_model_per_lot": round(float(np.mean([r["real_minus_model_per_lot"] for r in xs])), 1) if xs else None,
                     "entry_part": round(float(np.mean([r["entry_part_per_lot"] for r in xs])), 1) if xs else None,
                     "exit_part": round(float(np.mean([r["exit_part_per_lot"] for r in xs])), 1) if xs else None}
    res["rows"] = out
    return res, log


def part_c():
    import gold  # noqa: E402
    res = {}
    for st in (205.0, 400.0):
        days, log, _ = gold.run(gold.Y2326, gold.DEPLOYED, st)
        tot, by = 0.0, {}
        for x in log:
            q = sum(p[1] for p in x.get("pieces", [])) * LOT
            rate = 0.000625 if x["day"] < "2024-10-01" else (0.001 if x["day"] < "2026-04-01" else 0.0015)
            diff = (0.0015 - rate) * float(x["px"]) * q
            tot += diff
            by[x["day"][:4]] = by.get(x["day"][:4], 0.0) + diff
        net = gold.summary(days, log)["net"]
        res[f"@{int(st)}"] = {"replay_net": net, "dated_stt_saving": round(tot), "by_year": {y: round(v) for y, v in sorted(by.items())},
                             "share_of_net": round(tot / net, 4) if net else None}
    return res


def main():
    if OUT.exists():
        raise SystemExit("SN445 is run once")
    man = qa.manifest()
    sealed = set(man["quote_days"]) - set(man["unsealed_days"])
    smp, _d, _a = op.setup()
    res = {"A_paper_rounds": part_a(smp, sealed)}
    print("A", json.dumps({k: v for k, v in res["A_paper_rounds"].items() if k != "rows"}), flush=True)
    b, _log = part_b(sealed)
    res["B_gold_trades"] = b
    print("B", json.dumps({k: v for k, v in b.items() if k != "rows"}), flush=True)
    res["C_dated_stt"] = part_c()
    print("C", json.dumps(res["C_dated_stt"]), flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
