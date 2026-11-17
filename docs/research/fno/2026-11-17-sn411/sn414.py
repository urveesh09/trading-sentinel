"""SN414: the bank-sector move NIFTY hides - stage 1, cash level and the NIFTY expression (PLAN.md section 1, frozen at
e5cc95b7; details fixed here before any SN414 number).

Data: Kite 15-minute bars of BANKNIFTY's 12 constituents (docs/research/kite/2026-10-05-momentum-h1/_local/raw, Jan 1 -
Jul 31, 2026); NIFTY from gl's minute index closes at the same bar ends; Breeze's BANKNIFTY daily bars for the proxy gate;
Gold's DEPLOYED 2023-26 replay log (exit minutes) for "Gold flat". A Kite bar labelled hh:mm closes at hh:mm+14:59, so
bar k's close = the price at the next boundary (HONEST: a decision at a boundary uses closes up to it).
Basket weights (frozen, approximate): HDFCBANK .28 ICICIBANK .25 SBIN .09 KOTAKBANK .08 AXISBANK .08 CANBK .04 INDUSINDBK
.03 BANKBARODA .03 FEDERALBNK .03 IDFCFIRSTB .03 AUBANK .03 PNB .03; intraday returns only (bar to bar within a day).
Proxy gate: corr(basket daily close-to-close, Breeze BANKNIFTY daily close-to-close) >= 0.95, else the slot stops.
Decision clocks 10:30, 11:00, 11:30, 12:00, 12:30, 13:00. At clock t:
  r_b, r_n = basket / NIFTY return over the previous 30 minutes (two bars); beta = OLS of 15-minute basket on NIFTY
  returns over the previous 20 sessions; residual = r_b - beta r_n; z = residual / std of 30-minute residuals over the
  previous 20 sessions (every clock); trigger if |z| >= 2, |r_n| <= 0.15%, >= 70% of basket weight with constituent
  30-minute returns of the residual's sign, and no Gold position open at t. First trigger per session.
Outcomes (direction = the residual's sign): (a) the basket's next 45 minutes (three bars), bp; (b) the residual's
continuation over the same 45 minutes (bp, with the same beta); (c) NIFTY expression: HONEST ITM 2 then 1 on the
residual's side at t, 45 minutes, Rs 3,000 stop, Rs 205 / 400 (gl); controls: (c) with a seeded coin side at the same
triggers; and the basket's next 45 minutes at the same clocks on untriggered sessions with a seeded coin sign.
Hurdle for a BANKNIFTY option (SN413 A observations, front ATM, affordable only): 1e4 x [((stress + charges) / lot) / 0.5
+ the hour-scaled decay premium x 45 / (2 x remaining session minutes to expiry)] / index close, in bp.
Advance to quotes only if >= 30 triggers, mean (a) > 0 with t > 2 and mean (a) > the median hurdle at Rs 205.
Reported for Jan - Apr and May - Jul separately and pooled.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
import op  # noqa: E402

gl, wk = op.gl, op.wk
OUT = HERE / "results-sn414.json"
RAW = FNO.parent / "kite" / "2026-10-05-momentum-h1" / "_local" / "raw"
W = {"HDFCBANK": .28, "ICICIBANK": .25, "SBIN": .09, "KOTAKBANK": .08, "AXISBANK": .08, "CANBK": .04, "INDUSINDBK": .03,
     "BANKBARODA": .03, "FEDERALBNK": .03, "IDFCFIRSTB": .03, "AUBANK": .03, "PNB": .03}
CLOCKS = ("10:30", "11:00", "11:30", "12:00", "12:30", "13:00")
BARS = [f"{h:02d}:{m:02d}" for h in range(9, 16) for m in (0, 15, 30, 45) if "09:15" <= f"{h:02d}:{m:02d}" <= "15:15"]


def load_bars():
    out = {}
    for s in W:
        rows = []
        for f in sorted(RAW.glob(f"{s}_15minute_*.json")):
            rows += json.loads(f.read_text(encoding="utf-8"))["data"]["candles"]
        for r in rows:
            out.setdefault(r[0][:10], {}).setdefault(s, {})[r[0][11:16]] = float(r[4])
    return {d: v for d, v in out.items() if len(v) == len(W)}


def bar_index(hhmm):          # gl minute index of the close of the 15-minute bar starting at hhmm
    return int(hhmm[:2]) * 60 + int(hhmm[3:]) - 555 + 14


def gold_log():
    sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
    import sn403 as T
    T.Q.install()
    P, B, D, L, C, G, Q = T.P, T.B, T.D, T.L, T.C, T.G, T.Q
    B.stream = P.stream
    D.DATASETS["2022"] = P.SN366L / "dataset-nifty-2022"
    D.load_year = G.load_2022
    for mod in (B, L, C):
        mod.YEARS = ("2023", "2024", "2025", "2026")
    C._YEARS = None
    L.VOLT.clear()
    C.panel = lambda r: {w: {} for w in r}
    C.V5["books"] = ("N11", "R0.85")
    _row, _days, log = Q.run(205.0)
    busy = collections.defaultdict(list)
    for x in log:
        busy[x["day"]].append((x["i"], x["j"]))
    return busy


def main():
    if OUT.exists():
        raise SystemExit("SN414 is run once")
    bars = load_bars()
    days = sorted(bars)
    res = {"sessions_with_all_constituents": len(days), "range": [days[0], days[-1]]}
    # proxy gate
    con = sqlite3.connect(f"file:{op.sn353b.HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    bn = {r[0][:10]: float(r[1]) for r in con.execute("SELECT datetime, close FROM candles WHERE underlying='BANKNIFTY' AND interval='1day' AND datetime>=? AND datetime<?",
                                                          (days[0], "2026-08-01"))}
    last = {d: sum(W[s] * bars[d][s][max(bars[d][s])] for s in W) for d in days}
    b_ret, n_ret = [], []
    for a, b in zip(days, days[1:]):
        if a in bn and b in bn:
            rb = sum(W[s] * (bars[b][s][max(bars[b][s])] / bars[a][s][max(bars[a][s])] - 1.0) for s in W)
            b_ret.append(rb)
            n_ret.append(bn[b] / bn[a] - 1.0)
    corr = float(np.corrcoef(b_ret, n_ret)[0, 1]) if len(b_ret) > 10 else None
    res["proxy_gate"] = {"pairs": len(b_ret), "corr_daily": None if corr is None else round(corr, 4), "pass": bool(corr is not None and corr >= 0.95)}
    print("proxy", res["proxy_gate"], flush=True)
    if not res["proxy_gate"]["pass"]:
        OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
        return
    smp, _gd, _au = op.setup()
    busy = gold_log()

    def basket_ret(d, h0, h1):
        return sum(W[s] * (bars[d][s][h1] / bars[d][s][h0] - 1.0) for s in W if h0 in bars[d][s] and h1 in bars[d][s])

    def nifty_close(d, hh):
        s = smp.s.get(d)
        if s is None:
            return None
        v = s["index"][3][bar_index(hh)]
        return None if np.isnan(v) else float(v)
    # 15-minute return pairs per day for beta, and 30-minute residuals per day for sigma
    pairs, res30 = {}, {}
    for d in days:
        if d not in smp.s:
            continue
        pr = []
        for h0, h1 in zip(BARS, BARS[1:]):
            n0, n1 = nifty_close(d, h0), nifty_close(d, h1)
            if n0 and n1:
                pr.append((basket_ret(d, h0, h1), n1 / n0 - 1.0))
        pairs[d] = pr
    usable = [d for d in days if d in pairs]
    trig, untrig = [], []
    for k, d in enumerate(usable):
        if k < 20:
            continue
        hist = [p for x in usable[k - 20:k] for p in pairs[x]]
        xb, xn = np.array([p[0] for p in hist]), np.array([p[1] for p in hist])
        beta = float((xn * xb).sum() / (xn * xn).sum()) if (xn * xn).sum() > 0 else 1.0
        rs = []
        for x in usable[k - 20:k]:
            for c in CLOCKS:
                i1 = BARS.index(c) - 1
                h0, h1 = BARS[i1 - 2], BARS[i1]
                n0, n1 = nifty_close(x, h0), nifty_close(x, h1)
                if n0 and n1:
                    rs.append(basket_ret(x, h0, h1) - beta * (n1 / n0 - 1.0))
        sig = float(np.std(rs)) if len(rs) > 30 else None
        if not sig:
            continue
        fired = False
        for c in CLOCKS:
            i1 = BARS.index(c) - 1                            # the last completed bar before clock c
            h0, h1, h4 = BARS[i1 - 2], BARS[i1], BARS[i1 + 3]
            n0, n1, n4 = nifty_close(d, h0), nifty_close(d, h1), nifty_close(d, h4)
            if not (n0 and n1 and n4):
                continue
            rb, rn = basket_ret(d, h0, h1), n1 / n0 - 1.0
            resid = rb - beta * rn
            z = resid / sig
            sgn = 1 if resid > 0 else -1
            breadth = sum(W[s] for s in W if h0 in bars[d][s] and h1 in bars[d][s] and np.sign(bars[d][s][h1] / bars[d][s][h0] - 1.0) == sgn)
            m = int(c[:2]) * 60 + int(c[3:]) - 555
            gold_on = any(i <= m - 1 < j for i, j in busy.get(d, []))
            fwd_b = basket_ret(d, h1, h4)
            fwd_n = n4 / n1 - 1.0
            row = {"day": d, "clock": c, "z": z, "dir": sgn, "rn": rn, "breadth": breadth, "beta": beta, "gold_on": gold_on,
                   "fwd_basket_bp": 1e4 * fwd_b * sgn, "fwd_resid_bp": 1e4 * (fwd_b - beta * fwd_n) * sgn, "period": "Jan-Apr" if d < "2026-05-01" else "May-Jul"}
            hit = abs(z) >= 2 and abs(rn) <= 0.0015 and breadth >= 0.70 and not gold_on
            if hit and not fired:
                fired = True
                s = smp.s[d]
                for nm, side in (("nifty", "CE" if sgn > 0 else "PE"), ("coin", random.Random(f"sn414-{d}-{c}").choice(("CE", "PE")))):
                    for st in (205.0, 400.0):
                        pos, _dep, state, jf = op.leg(smp, s, side, m, "HONEST", st)
                        net = gl.walk(pos, s, jf, jf + 45, room=op.STOP)[0] if pos is not None else None
                        row[f"{nm}@{int(st)}"] = net if net is not None else 0.0
                        row[f"{nm}_state"] = state
                trig.append(row)
            elif not hit:
                cs = random.Random(f"sn414u-{d}-{c}").choice((-1, 1))
                untrig.append({**row, "coin_basket_bp": 1e4 * fwd_b * cs})

    def summ(rs):
        if not rs:
            return {"n": 0}
        a = np.array([r["fwd_basket_bp"] for r in rs])
        out = {"n": len(rs), "basket45_mean_bp": round(float(a.mean()), 2), "basket45_t": round(float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))), 2) if len(a) > 2 else None,
               "basket45_share_positive": round(float((a > 0).mean()), 3), "resid45_mean_bp": round(float(np.mean([r["fwd_resid_bp"] for r in rs])), 2)}
        for nm in ("nifty", "coin"):
            for st in (205, 400):
                xs = [r.get(f"{nm}@{st}") for r in rs if f"{nm}@{st}" in r]
                out[f"{nm}_option_per_trigger@{st}"] = op.per_session(xs) if xs else None
        return out
    for per in ("Jan-Apr", "May-Jul", "all"):
        pick = (lambda r: True) if per == "all" else (lambda r, per=per: r["period"] == per)
        res[f"TRIGGERED {per}"] = summ([r for r in trig if pick(r)])
        u = [r for r in untrig if pick(r)]
        res[f"UNTRIGGERED coin {per}"] = {"n": len(u), "basket45_mean_bp": round(float(np.mean([r["coin_basket_bp"] for r in u])), 2) if u else None,
                                          "abs_basket45_mean_bp": round(float(np.mean([abs(r["fwd_basket_bp"]) for r in u])), 2) if u else None}
    res["triggers_by_clock"] = dict(collections.Counter(r["clock"] for r in trig))
    # hurdle from SN413 A
    obs = json.loads((HERE / "results-sn413a.json").read_text(encoding="utf-8"))["observations"]
    cal = [o for o in obs if o["und"] == "BANKNIFTY" and o["rank"] == "front" and o["depth"] == 0 and o["pass"]]
    idx = {}
    for d in sorted({o["day"] for o in cal}):
        import csv
        import io
        p = HERE / "_local" / "nse" / f"idx-{d.replace('-', '')}.csv"
        for r in csv.DictReader(io.StringIO(p.read_text(encoding="utf-8", errors="replace"))):
            if r["Index Name"].strip() == "Nifty Bank":
                idx[d] = float(r["Closing Index Value"])
    hurdles = {205: [], 400: []}
    for o in cal:
        S = idx.get(o["day"])
        if not S:
            continue
        rem_min = max(1, o["dte"]) * 375
        theta45 = o["close"] * 45.0 / (2.0 * rem_min)
        for st in (205, 400):
            per_unit = (st + wk.charges(o["close"], o["close"], o["lot"], "NFO")) / o["lot"]
            hurdles[st].append(1e4 * (per_unit / 0.5 + theta45) / S)
    res["bank_option_hurdle_bp"] = {st: {"n": len(v), "median": round(float(np.median(v)), 2) if v else None, "p90": round(float(np.percentile(v, 90)), 2) if v else None}
                                    for st, v in hurdles.items()}
    a = res["TRIGGERED all"]
    res["advance_to_quotes"] = bool(a.get("n", 0) >= 30 and (a.get("basket45_t") or 0) > 2 and a["basket45_mean_bp"] > 0
                                    and res["bank_option_hurdle_bp"][205]["median"] is not None and a["basket45_mean_bp"] > res["bank_option_hurdle_bp"][205]["median"])
    res["triggers"] = trig
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "triggers"}, indent=1, default=float))


if __name__ == "__main__":
    main()
