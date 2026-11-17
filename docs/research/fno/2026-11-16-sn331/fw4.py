"""SN332 / SN333 / SN349 forward candidates, SN346 V8 fill realism and SN340's one-wallet score, on tick-recorder packets
(PLAN.md frozen at 95287d3f; this file frozen before Nov 18's session is collected). Execution: sn301/fw2.py's contract.
Scored ONCE on SN300a's first 20 verified, qualified sessions, after its verdict (session 20 = Dec 23):  python fw4.py verdict

SN349  the failed break on the futures mid: a 30-second break of the 3-minute range, back inside within 120 s; buy the
       opposite front-weekly ATM option 1 s after the failure; hold 300 s.
SN332  the same failures, only when in the 10 s after the failure >= 3 separate futures packets show five-level quantity on
       the rejected side (asks after an upside break, bids after a downside one) >= 1.5 x its median over the 60 s before
       the break; buy 1 s after the 10 s window; hold 120 s. Control: the same failures without the condition, same clock.
SN333  bursts: the front future's mid moves >= 0.05% in 10 s (one per 60 s). Shared = the next month's mid moved >= 70% as
       many points, solo < 30%. SHARED-follow buys with the burst, SOLO-fade against it, 1 s after; hold 60 s. Control:
       every burst followed.
SN346  every V8 intent (Production's sn_gold_v8_intents, read-only, if the shadow ran): would its limit have filled within
       3 s of the intent (ask <= limit with one lot of depth) and at what price, against paper.
SN340  each candidate's trades in Gold's wallet on FLAT sessions (fwd2's one-wallet contract); pass = net > 0 at Rs 205 and
       Rs 400, positive without the best session, beats its control per trade, >= 30 trades on >= 10 sessions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path[:0] = [str(FNO / "2026-11-16-sn301"), str(FNO / "2026-11-16-sn316")]
import fw2  # noqa: E402
import fw3  # noqa: E402
import fwd2  # noqa: E402

N = fw3.N
W0, W1 = fw3.W0, fw3.W1


def option_for(day, t, side):
    K = day.atm(t)
    return day.opt.get((day.front, K, side)) if K else None


def failures(day, U):
    out = []
    for e in fw3.events(U):
        te = e["te"]
        f = next((k for k in range(te + 1, min(N, te + 121)) if not np.isnan(U.c[k]) and e["s"] * (U.c[k] - e["lvl"]) < 0), None)
        if f is not None:
            out.append({**e, "f": f})
    return out


def depth_rebuilt(day, e):
    f = day.D[day.fut]
    side_q = f["a5"] if e["s"] > 0 else f["b5"]
    pre = (f["t"] >= e["te"] - 90) & (f["t"] < e["te"] - 30)
    if not pre.any():
        return False
    med = float(np.median(side_q[pre]))
    win = (f["t"] > e["f"]) & (f["t"] <= e["f"] + 10)
    return int((side_q[win] >= 1.5 * med).sum()) >= 3 if med > 0 else False


def next_future(day):
    m = day.meta
    futs = sorted((x["expiry"], t) for t, x in m.items() if x["type"] == "FUT" and x["underlying"] == "NIFTY" and x["expiry"] > day.day)
    return futs[1][1] if len(futs) > 1 else None


def bursts(day, U):
    nxt = next_future(day)
    if nxt is None or nxt not in day.D:
        return []
    mid = lambda d: np.where((d["bid"] > 0) & (d["ask"] > 0), (d["bid"] + d["ask"]) / 2, d["ltp"])  # noqa: E731
    g2 = fw3.grid(day, nxt, mid)
    out, last = [], -10 ** 9
    for t in range(W0, W1):
        if t - last < 60 or np.isnan(U.c[t]) or np.isnan(U.c[t - 10]) or np.isnan(g2[t]) or np.isnan(g2[t - 10]):
            continue
        d1 = U.c[t] - U.c[t - 10]
        if abs(d1) < 0.0005 * U.c[t - 10]:
            continue
        r = (g2[t] - g2[t - 10]) / d1
        out.append({"t": t, "s": 1 if d1 > 0 else -1, "kind": "shared" if r >= 0.7 else ("solo" if r < 0.3 else "mixed")})
        last = t
    return out


def run(folder, loaded=None):
    day = fw2.Day(folder, loaded)
    q = fw2.fw.qualify(day)
    out = {"qualify": q, "SN349": [], "SN332": [], "SN333": []}
    if not q["ok"]:
        return out
    U = fw3.Under(day)
    for e in failures(day, U):
        side = "PE" if e["s"] > 0 else "CE"
        tok = option_for(day, float(e["f"]), side)
        if tok is None:
            continue
        out["SN349"].append({"t": e["f"], "trade": fw2.trade(day, tok, float(e["f"] + 1), 300.0)})
        cond = depth_rebuilt(day, e)
        out["SN332"].append({"t": e["f"], "cond": cond, "trade": fw2.trade(day, tok, float(e["f"] + 11), 120.0)})
    for b in bursts(day, U):
        follow = "CE" if b["s"] > 0 else "PE"
        fade = "PE" if b["s"] > 0 else "CE"
        tf, tz = option_for(day, float(b["t"]), follow), option_for(day, float(b["t"]), fade)
        row = {"t": b["t"], "kind": b["kind"]}
        row["follow"] = fw2.trade(day, tf, float(b["t"] + 1), 60.0) if tf else None
        row["fade"] = fw2.trade(day, tz, float(b["t"] + 1), 60.0) if (tz and b["kind"] == "solo") else None
        out["SN333"].append(row)
    return out


def _arm(rows_by_day, pick, q, labels, recs):
    nets = {d: 0.0 for d in q}
    n4 = 0.0
    trades, sess = 0, set()
    wallet_net = 0.0
    for d in q:
        w = float((recs[d].get("gold") or {}).get("wallet_before") or 30000.0)
        realized = 0.0
        for r in rows_by_day[d]:
            t = pick(r)
            if not t or t.get("missed"):
                continue
            nets[d] += t["net205"]
            n4 += t["net400"]
            trades += 1
            sess.add(d)
            if labels[d] == "FLAT" and t["debit"] <= w - fwd2.RESERVE and 0.2 * w + realized >= fw2.STOP:
                realized += t["net205"]
        if labels[d] == "FLAT":
            wallet_net += realized
    tot = sum(nets.values())
    return {"trades": trades, "sessions": len(sess), "net205": round(tot), "net400": round(n4), "per_trade": round(tot / trades, 1) if trades else None,
            "without_best": round(tot - max(nets.values(), default=0.0)), "wallet_flat_net": round(wallet_net)}


def verdict():
    out = HERE / "results-sn340-forward.json"
    if out.exists():
        raise SystemExit("SN340 is scored once")
    sa_path = FNO / "2026-11-16-sn301" / "results-sn300a.json"
    if not sa_path.exists():
        raise SystemExit("SN340 is scored after SN300a's verdict, on the same sessions")
    sa = json.loads(sa_path.read_text(encoding="utf-8"))
    q, labels = sa["sessions"], sa["labels"]
    recs = {d: json.loads((fwd2.REC / f"{d}.json").read_text(encoding="utf-8")) for d in q}
    per = {d: run(fwd2.ARCH / d) for d in q}
    arms = {
        "SN349 reversal": ({d: per[d]["SN349"] for d in q}, lambda r: r["trade"]),
        "SN332 depth rebuilt": ({d: per[d]["SN332"] for d in q}, lambda r: r["trade"] if r["cond"] else None),
        "SN332 control": ({d: per[d]["SN332"] for d in q}, lambda r: r["trade"]),
        "SN333 shared follow": ({d: per[d]["SN333"] for d in q}, lambda r: r["follow"] if r["kind"] == "shared" else None),
        "SN333 solo fade": ({d: per[d]["SN333"] for d in q}, lambda r: r["fade"]),
        "SN333 control (all follow)": ({d: per[d]["SN333"] for d in q}, lambda r: r["follow"]),
    }
    res = {"sessions": q}
    for name, (rows, pick) in arms.items():
        res[name] = _arm(rows, pick, q, labels, recs)
    refs = {"SN349 reversal": None, "SN332 depth rebuilt": "SN332 control", "SN333 shared follow": "SN333 control (all follow)",
            "SN333 solo fade": "SN333 control (all follow)"}
    res["verdicts"] = {}
    for name, ref in refs.items():
        x = res[name]
        if any(v == "UNKNOWN" for v in labels.values()) or x["trades"] < 30 or x["sessions"] < 10:
            res["verdicts"][name] = "INSUFFICIENT"
            continue
        ok = x["net205"] > 0 and x["net400"] > 0 and x["without_best"] > 0 and x["wallet_flat_net"] > 0
        if ref:
            ok &= x["per_trade"] > (res[ref]["per_trade"] or -1e9)
        res["verdicts"][name] = "PASS" if ok else "FAIL"
    res["SN346_v8_fill_realism"] = v8_fill_realism(q)
    print(json.dumps(res, indent=1), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


def v8_fill_realism(q):
    """For each V8 intent on these sessions (Production, read-only): did a packet within 3 s show ask <= limit (BUY) or
    bid >= limit (SELL) with one lot of depth, and the price gap to the paper price."""
    import subprocess
    code = ("import json,sqlite3; c=sqlite3.connect('file:/data/cache.db?mode=ro', uri=True); "
            "r=c.execute(\"SELECT name FROM sqlite_master WHERE name='sn_gold_v8_intents'\").fetchone(); "
            "print(json.dumps([] if not r else [list(x) for x in c.execute('SELECT session_date,kind,at,token,side,qty,order_type,limit_price,paper_price FROM sn_gold_v8_intents')]))")
    r = subprocess.run(["docker", "exec", "-u", "quantuser", "python-engine", "python", "-c", code], capture_output=True, text=True)
    rows = json.loads(r.stdout) if r.returncode == 0 else []
    import datetime as dt
    out = []
    for day, kind, at, token, side, qty, otype, limit, paper in rows:
        if day not in q or limit is None:
            continue
        loaded = fw2.load_day(fwd2.ARCH / day)
        D = loaded[1].get(int(token))
        if D is None:
            out.append({"day": day, "kind": kind, "result": "no packets"})
            continue
        t0 = fw2.IST.localize(dt.datetime.fromisoformat(day + "T09:15:00")).timestamp()
        ts = dt.datetime.fromisoformat(at).timestamp() - t0
        k = np.flatnonzero((D["t"] >= ts) & (D["t"] <= ts + 3))
        hit = None
        for i in k:
            if side == "BUY" and 0 < D["ask"][i] <= limit and D["a5"][i] >= qty:
                hit = float(D["ask"][i])
                break
            if side == "SELL" and D["bid"][i] >= limit and D["b5"][i] >= qty:
                hit = float(D["bid"][i])
                break
        out.append({"day": day, "kind": kind, "filled_3s": hit is not None, "price": hit, "paper": paper})
    return {"intents": len(out), "filled_within_3s": sum(1 for x in out if x.get("filled_3s")), "rows": out}


if __name__ == "__main__":
    if sys.argv[1] == "verdict":
        verdict()
    elif sys.argv[1] == "dev":
        r = run(Path(sys.argv[2]))
        print("qualify", r["qualify"].get("ok"), {k: len(v) for k, v in r.items() if k != "qualify"})
