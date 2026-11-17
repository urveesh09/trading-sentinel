"""SN476: runtime Gold against replay Gold (PLAN.md SN476, frozen at bf895633; details fixed here before any number).

A  live join: the receipt _local/prod-gold-*.json (sn476_pull.py, read-only). Eligible = N11_PAPER rows entered on or after
   sn_gold_wallet.started. Each -> its sn_gold_positions row, its sn_gold_skips row, else DIVERGENCE. NIFTY evaluations of the
   same sessions by (leg, accepted, reason). Day rows: trades = positions that day, net = their sum, refill = max(0, -net).
B  pre-start shadow: N11_PAPER rows before Gold's start, through sn_gold's pure rules (lots_for, itm_depth, pick_contract,
   day_stop) on the quote archive (export 20261117T103003Z): the last usable record of each front-weekly strike in the minute
   before the paper entry's minute; wallet Rs 30,000; vol_up from fno_n11_gate; one position at a time (a row whose entry is
   before the previous shadow entry's paper exit is "position_open"); room = 20% of the wallet (each shadow is that day's first
   priced trade unless an earlier one exists; realized is not simulated -> disclosed).
C  signal sets: RUNTIME = N09's DIAG paper twin with the runtime gate (fno_n11.stand_aside at 0.85, need 20, exits strictly before
   the entry; vol reading = N09's vol_table rebuilt from the same daily bars N09 / SN366 read: n08 daily-2023 + complements
   daily-2026 for 2023-26; SN366 daily-2022 for 2022); paper history 2023-26 DIAG for 2023-26, 2021L + 2022 DIAG for 2022.
   Keys = (entry minute, strike, call). Gold v5 on RUNTIME vs DEPLOYED, GOLD_30K, both paths, Rs 205 / 400.
D  runtime-faithful stops: goldx stop_rule "close" on DEPLOYED.
E  pure-rule parity on every DEPLOYED Gold trade (2023-26 and 2022 @205): sn_gold.lots_for / pick_contract on the replay's own
   quotes at the entry minute (strikes N11 +- 4 steps that the lab can price: traded that minute; bid = the lab's bid close,
   ask = the lab's ask), day_stop vs the lab's first stop, scale_in_stop vs the lab's add stop, position_net vs the lab's net (for
   trades whose pieces all exit at one price), grow on stressed vs unstressed day nets (trades held fixed: the step dates).
"""
from __future__ import annotations

import bisect
import collections
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "python-engine"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import goldx  # noqa: E402

g = goldx.gold
OUT = HERE / "results-sn476.json"
SIM = ROOT / "docs" / "research" / "simulation"
N09L = SIM / "2026-11-01-fno-n09" / "_local"
SN366L = FNO / "2026-11-16-sn366" / "_local"
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel\_local\exports\20261117T103003Z")
DAILY = {"2326": (SIM / "2026-11-01-fno-n08/_local/daily-2023.json", FNO.parent / "simulation/2026-10-31-fno-complements/_local/daily-2026.json"),
         "22": (SN366L / "daily-2022.json",)}
STRESSES = (205.0, 400.0)


# ---------------------------------------------------------------- C: the runtime's signal set -------------------------------
def trailing_median(values, window=250, need=120):
    good = [v for v in values if v is not None and np.isfinite(v)][-window:]
    return float(np.median(good)) if len(good) >= need else None


def vol_table(paths):
    """N09's vol_table, line for line, over the given daily sources."""
    rows = {}
    for p in paths:
        for row in json.loads(Path(p).read_text(encoding="utf-8"))["rows"]:
            rows[row[0]] = row
    days = sorted(rows)
    out, atr, readings, prev = {}, None, [], None
    for i, day in enumerate(days):
        if readings:
            out[day] = (readings[-1], trailing_median(readings[:-1]))
        _d, _o, high, low, close = rows[day]
        tr = high - low if prev is None else max(high - low, abs(high - prev), abs(low - prev))
        atr = tr if atr is None else atr + (tr - atr) / 14
        if i >= 14:
            readings.append(atr / close * 100)
        prev = close
    return out


def diag_trades(year):
    if year in ("2021", "2022"):
        k = json.loads((SN366L / "n09" / f"keys-diag-{year}.json").read_text(encoding="utf-8"))["DIAG"]
        return json.loads((SN366L / "n09" / f"evals-{year}" / f"{k}.json").read_text(encoding="utf-8"))["trades"]
    k = json.loads((N09L / f"keys-diag-{year}.json").read_text(encoding="utf-8"))["DIAG"]
    return json.loads((N09L / f"evals-{year}" / f"{k}.json").read_text(encoding="utf-8"))["trades"]


def runtime_stream(years_hist, years_out, vt, ratio=0.85, need=20):
    hist = []
    for y in years_hist:
        hist += diag_trades(y)
    closes = sorted((dt.datetime.fromisoformat(t["exit_time"]), float(t["net_pnl"])) for t in hist if t.get("exit_time"))
    at = [c[0] for c in closes]
    nets = [c[1] for c in closes]
    out, stood = [], []
    for y in years_out:
        for t in diag_trades(y):
            now = dt.datetime.fromisoformat(t["entry_time"])
            atr, usual = vt.get(t["entry_time"][:10], (None, None))
            up = atr is not None and usual is not None and atr >= usual * ratio
            before = nets[:bisect.bisect_left(at, now)]
            stand = (not up) and len(before) >= need and sum(before[-need:]) <= 0
            sym = t["tradingsymbol"]
            strike = int(sym[-7:-2])
            rec = {"day": t["entry_time"][:10], "i": g.B.minute_of(t["entry_time"]), "j": g.B.minute_of(t["exit_time"]), "strike": strike,
                   "opt": sym[-2:], "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"], "expert": t["entry_expert"],
                   "gate": t.get("entry_gate") or "", "book": "RUNTIME", "sig_key": (t["entry_time"][:16], strike, sym[-2:] == "CE")}
            (stood if stand else out).append(rec)
    return out, stood


RUNTIME = {}
_orig = g._orig_stream


def dispatch(year, book="N11"):
    if book == "RUNTIME":
        return [x for x in RUNTIME["2022" if year == "2022" else "2326"] if x["day"][:4] == year]
    return _orig(year, book)


def keyset(years, books):
    out = {}
    for y in years:
        for b in books:
            for s in dispatch(y, b):
                out.setdefault((s["sig_key"][0], s["sig_key"][1], s["sig_key"][2]), s)
    return out


def gold_run(years, books, stress, wallet=goldx.GOLD_30K, **vx):
    days, log, _ = g.run(years, books, stress, wallet=wallet, **vx)
    s = g.summary(days, log)
    return s, days, log


# ---------------------------------------------------------------- E: pure-rule parity ---------------------------------------
CAPT = []
_gold_one = None


def capture_gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    res = _gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
    if res is not None:
        quotes = {}
        i = sg["i"]
        sign = 1 if sg["opt"] == "CE" else -1
        for k in range(-4, 5):
            strike = sg["strike"] + k * goldx.M.STEP
            r = S.option(strike, sg["opt"])
            if r is not None and r[6][i]:
                quotes[(float(strike), sg["opt"])] = SimpleNamespace(bid=float(r[4][i]), ask=goldx.M.ask_of(float(r[0][3][i])))
        CAPT.append({"day": S.day, "i": i, "sg_strike": sg["strike"], "opt": sg["opt"], "wallet": wallet, "full": full_lots, "vol_day": bool(vol_day),
                     "realized": realized, "loss": loss, "lab": {"net": res[0], "j": res[1], "lots": res[2], "ask": res[3], "px": res[4], "strike": res[5]},
                     "quotes": quotes, "sign": sign})
    return res


def parity_e(log, capt, stress):
    import sn_gold
    from fno_costs import calc_fno_costs
    out = collections.Counter()
    ex = collections.defaultdict(list)
    by = {(x["day"], x["i"]): x for x in log}
    for c in capt:
        t = by.get((c["day"], c["i"]))
        if t is None:
            out["capture_without_log"] += 1
            continue
        lots_rt = sn_gold.lots_for(c["wallet"], c["vol_day"]) if c["full"] > 1 else 1
        lots_lab = max(1, c["full"]) if c["full"] <= 1 else (c["full"] if c["vol_day"] else max(1, c["full"] // 2))
        out["lots_rule_same" if lots_rt == lots_lab or c["full"] <= 1 else "lots_rule_diff"] += 1
        pick = sn_gold.pick_contract(c["quotes"], float(c["sg_strike"]), c["opt"], lots_lab, c["wallet"], goldx.M.LOT)
        if pick is None:
            out["pick_none"] += 1
            ex["pick_none"].append([c["day"], c["i"]])
        else:
            same = abs(pick[0] - c["lab"]["strike"]) < 1e-6 and pick[2] == c["lab"]["lots"] and abs(pick[1].ask - c["lab"]["ask"]) < 1e-6
            out["pick_same" if same else "pick_diff"] += 1
            if not same:
                ex["pick_diff"].append([c["day"], c["i"], pick[0], pick[2], c["lab"]["strike"], c["lab"]["lots"]])
        ask, lots = t["ask0"], t["lots0"]
        qty = lots * goldx.M.LOT
        rt_stop = sn_gold.day_stop(ask, qty, t["room"])
        d_tick = round((t["stop0"] - rt_stop) / 0.05)
        out[f"stop0_minus_runtime_ticks={d_tick}" if abs(d_tick) <= 8 else "stop0_minus_runtime_ticks>8"] += 1
        if rt_stop >= ask:
            out["runtime_lot_loop_would_act"] += 1
        for a in t["adds"]:
            if a.get("added"):
                pieces = [[ask, lots], [a["ask"], a["added"]]]
                s_rt = sn_gold.scale_in_stop(pieces, goldx.M.LOT, t["room"])
                s_lab = a.get("stop_after")
                if s_lab is not None:
                    dd = round((max(t["stop0"], s_lab) - max(rt_stop, s_rt)) / 0.05)
                    out[f"add_stop_minus_runtime_ticks={dd}" if abs(dd) <= 8 else "add_stop_minus_runtime_ticks>8"] += 1
        if t.get("fail") is None:
            px = t["px"]
            pcs = [[e, n] for e, n, _pn in t["pieces"]]
            assert stress == sn_gold.STRESS_PER_LOT
            net_rt, stressed_rt = sn_gold.position_net(pcs, px, goldx.M.LOT)
            diff = round(t["net"] - stressed_rt, 2)
            out["net_same_paise" if abs(diff) < 0.01 else "net_diff"] += 1
            if abs(diff) >= 0.01:
                ex["net_diff"].append([t["day"], t["i"], round(t["net"], 2), round(stressed_rt, 2)])
            out["charges_check_calc_fno_costs"] += int(abs(goldx.M.charges(ask, px, qty) - calc_fno_costs(ask, px, qty)) < 1e-9)
    return dict(out), {k: v[:12] for k, v in ex.items()}


def grow_steps(days, log, stress, start=30000.0, cap=3):
    lots_by_day = collections.defaultdict(int)
    for t in log:
        lots_by_day[t["day"]] += sum(n for _e, n, _p in t["pieces"]) + (t["fail"]["lots"] if t.get("fail") else 0)
    res = {}
    for kind in ("stressed", "unstressed"):
        W, steps, prog, dates = start, 0, 0.0, []
        for d, _w, n, _t, _l in days:
            x = n + (stress * lots_by_day[d] if kind == "unstressed" else 0.0)
            prog += x
            while prog >= W and steps < cap:
                prog -= W
                W *= 1.5
                steps += 1
                dates.append(d)
        res[kind] = dates
    return res


# ---------------------------------------------------------------- A / B -----------------------------------------------------
def live_join():
    rec = sorted((HERE / "_local").glob("prod-gold-*.json"))[-1]
    blob = rec.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == rec.with_suffix(".sha256").read_text().strip()
    P = json.loads(blob)
    start = P["sn_gold_wallet"][0]["started"]
    paper = [r for r in P["fno_n11_paper"] if r["source"] == "N11_PAPER"]
    pos = {r["n11_paper_id"]: r for r in P["sn_gold_positions"]}
    skips = {r["n11_paper_id"]: r for r in P["sn_gold_skips"]}
    eligible = [r for r in paper if str(r["entry_time"])[:10] >= start]
    joined = []
    for r in eligible:
        joined.append({"id": r["id"], "bar_ts": r["bar_ts"], "gold": pos.get(r["id"], {}).get("id"), "skip": skips.get(r["id"], {}).get("reason"),
                       "status": "MATCHED" if r["id"] in pos else ("SKIP_DOCUMENTED" if r["id"] in skips else "DIVERGENCE")})
    sessions = sorted({str(s["evaluated_at"])[:10] for s in P["fno_signals"]})
    ev = {}
    for day in sessions:
        if day < start:
            continue
        c = collections.Counter()
        for s in P["fno_signals"]:
            if str(s["evaluated_at"])[:10] == day and s["underlying"] == "NIFTY":
                c[f"{s['leg']}|{s['accepted']}|{(s['reject_reason'] or '')}"] += 1
        ev[day] = dict(c.most_common())
    days_ok = []
    for drow in P["sn_gold_days"]:
        ps = [p for p in P["sn_gold_positions"] if p["session_date"] == drow["session_date"] and p["status"] == "CLOSED"]
        net = sum(float(p["net"]) for p in ps)
        days_ok.append({"day": drow["session_date"], "trades_row": drow["trades"], "trades_positions": len(ps), "net_row": drow["net"], "net_positions": round(net, 2),
                        "refill_row": drow["refill"], "refill_expected": round(max(0.0, -net), 2),
                        "ok": drow["trades"] == len(ps) and abs(drow["net"] - net) < 0.01 and abs(drow["refill"] - max(0.0, -net)) < 0.01})
    pre = [r for r in paper if str(r["entry_time"])[:10] < start]
    return P, {"receipt": rec.name, "receipt_sha256": hashlib.sha256(blob).hexdigest(), "gold_started": start, "paper_rows_total": len(paper),
               "paper_rows_before_start": len(pre), "eligible": len(eligible), "joined": joined,
               "divergences": sum(j["status"] == "DIVERGENCE" for j in joined), "nifty_evaluations_since_start": ev,
               "wallet": P["sn_gold_wallet"][0], "day_rows": days_ok}, pre


def shadow(P, pre):
    import qa
    import sn_gold
    qa.EXPORT = EXPORT
    qa.LOCAL = HERE / "_local" / "qa"
    gate = {r["session_date"]: r for r in P["fno_n11_gate"]}
    out, last_exit = [], {}
    for r in sorted(pre, key=lambda x: x["entry_time"]):
        day = str(r["entry_time"])[:10]
        t_in = dt.datetime.fromisoformat(r["entry_time"])
        m = t_in.hour * 60 + t_in.minute - 555
        row = {"id": r["id"], "day": day, "bar_ts": r["bar_ts"], "n11_symbol": r["tradingsymbol"], "n11_ask": r["entry_premium"], "paper_net_1lot": round(float(r["net"] or 0), 2)}
        if day in last_exit and last_exit[day] > t_in:
            row["runtime"] = "position_open"
            out.append(row)
            continue
        q = qa.load(day)
        n11_strike = int(r["tradingsymbol"][-7:-2])
        opt = r["tradingsymbol"][-2:]
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= day})
        quotes = {}
        if exps:
            for k, rec in q["opt"].items():
                if k[0] == "NIFTY" and k[1] == exps[0] and k[3] == opt:
                    i = qa.last_before(rec, m - 1)
                    if i is not None:
                        quotes[(float(k[2]), opt)] = SimpleNamespace(bid=float(rec["bid"][i]), ask=float(rec["ask"][i]))
        vol_day = bool(gate.get(day, {}).get("vol_up"))
        wallet = 30000.0
        lots = sn_gold.lots_for(wallet, vol_day)
        pick = sn_gold.pick_contract(quotes, float(n11_strike), opt, lots, wallet, 65)
        row.update(expiry=exps[0] if exps else None, vol_day=vol_day, lots_wanted=lots, quotes_seen=len(quotes))
        if pick is None:
            row["runtime"] = "no_affordable_contract"
        else:
            strike, qq, lots2 = pick
            room = 0.2 * wallet
            stop = sn_gold.day_stop(qq.ask, lots2 * 65, room)
            while lots2 > 1 and stop >= qq.ask:
                lots2 -= 1
                stop = sn_gold.day_stop(qq.ask, lots2 * 65, room)
            row.update(runtime="ENTRY", strike=strike, depth_itm=int(round((n11_strike - strike) / 50 * (1 if opt == "CE" else -1))), ask=qq.ask, lots=lots2,
                       stop=stop, premium=round(qq.ask * lots2 * 65, 2))
            last_exit[day] = dt.datetime.fromisoformat(r["exit_time"]) if r.get("exit_time") else t_in
        out.append(row)
    return out


# ---------------------------------------------------------------- main -------------------------------------------------------
def main():
    global _gold_one
    if OUT.exists():
        raise SystemExit("SN476 is scored once")
    goldx.install()
    assert g.C is goldx.gw.C and goldx.L.walk is goldx.walk
    g._orig_stream = dispatch
    res = {}
    P, res["A_live_join"], pre = live_join()
    res["B_pre_start_shadow"] = shadow(P, pre)
    vt = {"2326": vol_table(DAILY["2326"]), "22": vol_table(DAILY["22"])}
    RUNTIME["2326"], stood_2326 = runtime_stream(("2023", "2024", "2025", "2026"), ("2023", "2024", "2025", "2026"), vt["2326"])
    RUNTIME["2022"], stood_22 = runtime_stream(("2021", "2022"), ("2022",), vt["22"])
    C = {}
    for pname, years, st_list, rt in (("2022", g.Y22, stood_22, RUNTIME["2022"]), ("2023-2026", g.Y2326, stood_2326, RUNTIME["2326"])):
        dep = keyset(years, g.DEPLOYED)
        run = keyset(years, ("RUNTIME",))
        by_year = {}
        for y in years:
            dk = {k for k in dep if k[0][:4] == y}
            rk = {k for k in run if k[0][:4] == y}
            by_year[y] = {"deployed": len(dk), "runtime": len(rk), "both": len(dk & rk), "deployed_only": len(dk - rk), "runtime_only": len(rk - dk),
                          "runtime_stood_aside_0.85": sum(1 for s in st_list if s["day"][:4] == y)}
        C[pname] = {"keys_by_year": by_year}
        for st in STRESSES:
            sd, dd, ld = gold_run(years, g.DEPLOYED, st)
            sr, dr, lr = gold_run(years, ("RUNTIME",), st)
            kd = {(t["day"], t["i"]) for t in ld}
            kr = {(t["day"], t["i"]) for t in lr}
            C[pname][f"@{int(st)}"] = {"DEPLOYED": sd, "RUNTIME": sr, "diff_net": sr["net"] - sd["net"],
                                       "gold_trades_both": len(kd & kr), "gold_trades_deployed_only": len(kd - kr), "gold_trades_runtime_only": len(kr - kd),
                                       "net_deployed_only_trades": round(sum(t["net"] for t in ld if (t["day"], t["i"]) not in kr)),
                                       "net_runtime_only_trades": round(sum(t["net"] for t in lr if (t["day"], t["i"]) not in kd))}
    res["C_signal_sets"] = C
    D = {}
    for pname, years in (("2022", g.Y22), ("2023-2026", g.Y2326)):
        for st in STRESSES:
            s0, d0, l0 = gold_run(years, g.DEPLOYED, st)
            s1, d1, l1 = gold_run(years, g.DEPLOYED, st, stop_rule="close")
            D[f"{pname} @{int(st)}"] = {"bar_low_fill (Gold)": s0, "close_bid (runtime-like)": s1, "diff_net": s1["net"] - s0["net"],
                                        "stops_gold": sum(t["reason"] == "stop" for t in l0), "stops_close_rule": sum(t["reason"] == "stop" for t in l1)}
    res["D_runtime_faithful_stops"] = D
    E = {}
    _gold_one = g.C.gold_one
    g.C.gold_one = capture_gold_one
    try:
        for pname, years in (("2022", g.Y22), ("2023-2026", g.Y2326)):
            CAPT.clear()
            s, days, log = gold_run(years, g.DEPLOYED, 205.0)
            counts, examples = parity_e(log, list(CAPT), 205.0)
            E[pname] = {"net_check": s["net"], "trades": len(log), "counts": counts, "examples": examples, "growth_step_dates": grow_steps(days, log, 205.0)}
    finally:
        g.C.gold_one = _gold_one
    res["E_pure_rule_parity"] = E
    res["E_structural_differences"] = [
        "add trigger and extension trail: replay = NIFTY INDEX minute close and index 1-minute ATR (sn01_sim.features); runtime = live NIFTY FUTURE price sampled at management ticks and the future's 1-minute ATR from Kite candles",
        "stop: replay = the minute's bid low touches the stop, filled at min(stop, open bid); runtime = the bid sampled about once a minute at or below the stop, booked at that bid (D)",
        "stop formula: replay's room reserves the Rs 205 stress per lot; runtime's day_stop / scale_in_stop use shipped charges only (E: stop0 - runtime ticks)",
        "wallet growth and refill: replay grows on stressed day nets; runtime close_day grows / refills on unstressed nets (E: growth_step_dates)",
        "entry clock: replay = the first minute close after the 5-minute bar (+59 s) or later; live paper rows entered a median ~31 s after the bar (SN478)",
        "quotes: replay = a modeled bid/ask from the minute's trade print, a strike counts only on a traded minute; runtime = live best bid/ask, any strike with bid and ask > 0",
        "signal set: runtime = every N11 paper-record signal gated at 0.85; replay = the N11 and R0.85 books' trades (C)",
        "expiry filter: replay skips a signal whose contract is not the session's front expiry; runtime has no such filter",
        "lot loop: runtime removes lots while the stop is at or above the ask and skips when one lot cannot fit; the replay has neither",
        "N11 exit: replay sells at N11's exit minute's bid; runtime sells at the next management tick (<= 55 s) after the paper row closes",
    ]
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"A": {k: res["A_live_join"][k] for k in ("gold_started", "eligible", "divergences", "paper_rows_before_start")},
                      "B": [(r["id"], r.get("runtime"), r.get("strike"), r.get("lots"), r.get("ask")) for r in res["B_pre_start_shadow"]],
                      "C": {p: {k: (v if not isinstance(v, dict) or "DEPLOYED" not in v else {"dep": v["DEPLOYED"]["net"], "rt": v["RUNTIME"]["net"], "diff": v["diff_net"]})
                                for k, v in C[p].items()} for p in C},
                      "D": {k: v["diff_net"] for k, v in D.items()}, "E": {p: E[p]["counts"] for p in E}}, indent=1, default=str))


if __name__ == "__main__":
    main()
